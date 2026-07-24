"""
ab_entrada_rapida.py — A/B HONESTO: "entrada más rápida" vs el flip validado (V26).

NO toca el código ni los bots vivos. Importa el MISMO motor honesto de V26
(backtest.BacktestV25 + estrategia.py + indicadores.py) y corre una comparación
donde la ÚNICA variable que cambia es la VELOCIDAD de las EMAs que definen la
tendencia (estrategia.tendencia_actual lee df['EMA_50'] / df['EMA_200'] por
nombre — así que sobrescribir solo esas dos columnas con spans más rápidos hace
que el mismo motor entre/salga antes, sin tocar la lógica).

  - Baseline  : EMA 50/200  (la config validada de V26 = test C, +147%/4 años)
  - Variante 1: EMA 20/50   (par de tendencia "rápido" clásico)
  - Variante 2: EMA 20/100  (intermedio)

Todo lo demás idéntico: 4h, entrada=flip de alineación (cruce), salida=stop o
flip opuesto (tendencia), costos maker 0.02%/lado, riesgo 0.33%, cooldown 2 velas.
Corrida CONTINUA de N años hasta HOY (métrica de decisión para salidas lentas,
per el libro — el ventaneo con cierre administrativo es inválido aquí).

Criterio (mismo que el test D): una variante "gana" solo si PnL continuo >=
baseline Y max drawdown <= baseline. Si mejora una a costa de la otra, gana el
mejor retorno/DD; se reporta honestamente.

Uso:  python3 ab_entrada_rapida.py [años]   (def. 4)
"""
import os
import sys
import pickle

import pandas as pd

V26 = os.path.abspath('../v26_tendencia')
sys.path.insert(0, V26)

import config                       # noqa: E402
import estrategia                   # noqa: E402
from indicadores import calcular_indicadores  # noqa: E402
from binance_client import BinanceClient      # noqa: E402
import backtest                     # noqa: E402
from backtest import BacktestV25, BALANCE_INICIAL  # noqa: E402

AÑOS = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
# 2º arg opcional: lista de símbolos separada por comas (validación out-of-basket).
# Override SOLO en este proceso de prueba — config.SYMBOLS del bot vivo intacto.
if len(sys.argv) > 2 and sys.argv[2]:
    config.SYMBOLS = [s.strip().upper() for s in sys.argv[2].split(',') if s.strip()]

# --- overrides SOLO en este proceso (config.py del bot vivo intacto) ---
config.INTERVAL = '4h'
config.ENTRY_MODE = 'cruce'
config.EXIT_MODE = 'tendencia'
config.COOLDOWN_CANDLES = 8          # 2 velas de 4h (en horas, como el motor)
config.BT_TAKER_FEE = 0.0002         # maker (igual que test C)
config.BT_SLIPPAGE = 0.0002


class ForenseNulo:
    dir = '(off)'
    def registrar_activacion(self, *a, **k): pass
    def registrar_vela(self, *a, **k): pass
    def registrar_cierre(self, *a, **k): pass


def cargar_datos(años):
    total = int(años * 365 * 6)  # velas 4h
    tag = "-".join(s[:4] for s in config.SYMBOLS)
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"ab_cache_4h_{total}_{tag}.pkl")
    if os.path.isfile(ruta):
        print(f"INFO: cache {ruta}")
        with open(ruta, 'rb') as f:
            return pickle.load(f)
    cli = BinanceClient()
    raw = {}
    for s in config.SYMBOLS:
        print(f"INFO: descargando {total} velas 4h de {s} (hasta HOY)...")
        raw[s] = cli.klines_paginated(s, total)   # end_time=None → hasta ahora
        print(f"  {s}: {len(raw[s])} velas ({raw[s]['time'].iloc[0]} → {raw[s]['time'].iloc[-1]})")
    with open(ruta, 'wb') as f:
        pickle.dump(raw, f)
    return raw


def dfs_con_ema(raw, fast, slow):
    """Indicadores normales, pero EMA_50/EMA_200 redefinidas con spans dados."""
    out = {}
    for s, df in raw.items():
        d = calcular_indicadores(df)
        d = d.copy()
        d['EMA_50'] = d['close'].ewm(span=fast, adjust=False).mean()
        d['EMA_200'] = d['close'].ewm(span=slow, adjust=False).mean()
        out[s] = d
    return out


def max_drawdown(cerrados):
    """Max drawdown % sobre la curva de equity por trades cerrados (cronológica)."""
    eq = BALANCE_INICIAL
    pico = eq
    dd = 0.0
    for t in sorted(cerrados, key=lambda x: x['exit_time']):
        eq += t['pnl']
        pico = max(pico, eq)
        dd = max(dd, (pico - eq) / pico)
    return dd * 100


def correr(raw, fast, slow, recientes_dias=10):
    dfs = dfs_con_ema(raw, fast, slow)
    bt = BacktestV25(candles=0, forense_dir='/tmp/ab_forense')
    bt.forense = ForenseNulo()
    bt.dfs = dfs
    bt.correr()
    r = bt.resumen()
    cerrados = [t for t in bt.trades if t['status'] == 'CERRADA']
    dd = max_drawdown(cerrados)

    # PnL por año
    por_año = {}
    for t in cerrados:
        y = pd.Timestamp(t['exit_time']).year
        por_año[y] = por_año.get(y, 0.0) + t['pnl']

    # trades abiertos en los últimos N días (el rally actual)
    corte = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=recientes_dias)
    recientes = [t for t in bt.trades if pd.Timestamp(t['entry_time']) >= corte]

    return {'r': r, 'dd': dd, 'por_año': por_año, 'recientes': recientes,
            'n_cerrados': len(cerrados)}


def main():
    raw = cargar_datos(AÑOS)
    ini = min(df['time'].iloc[0] for df in raw.values())
    fin = max(df['time'].iloc[-1] for df in raw.values())
    print(f"\nVentana CONTINUA: {ini} → {fin}  (basket {', '.join(config.SYMBOLS)})")
    print("Misma estrategia/salida/costos; única diferencia = velocidad de EMAs.\n")

    configs = [('Baseline 50/200 (V26 validado)', 50, 200),
               ('Variante 20/50  (rápida)', 20, 50),
               ('Variante 20/100 (intermedia)', 20, 100)]
    resultados = []
    for nombre, fast, slow in configs:
        print(f"=== corriendo: {nombre} ===")
        res = correr(raw, fast, slow)
        resultados.append((nombre, res))
        r = res['r']
        print(f"  PnL {r['net_pnl_pct']:+.2f}% | PF {r['profit_factor']} | "
              f"WR {r['win_rate']}% | trades {r['trades']} | DD {res['dd']:.1f}% | "
              f"B&H {r['benchmark_buy_hold_pct']:+.2f}%\n")

    # ---- tabla comparativa ----
    print("=" * 84)
    print(" A/B — ENTRADA RÁPIDA vs FLIP VALIDADO  (corrida continua, motor honesto)")
    print("=" * 84)
    print(f" {'config':<32}{'PnL%':>9}{'PF':>7}{'WR%':>7}{'trades':>8}{'DD%':>7}{'ret/DD':>8}")
    base_pnl = base_dd = None
    for nombre, res in resultados:
        r = res['r']
        pnl, dd = r['net_pnl_pct'], res['dd']
        rdd = (pnl / dd) if dd > 0 else float('inf')
        if base_pnl is None:
            base_pnl, base_dd = pnl, dd
        print(f" {nombre:<32}{pnl:>+8.2f}%{str(r['profit_factor']):>7}"
              f"{r['win_rate']:>6.1f}%{r['trades']:>8}{dd:>6.1f}%{rdd:>8.2f}")
    print(f"\n B&H del basket en la ventana: {resultados[0][1]['r']['benchmark_buy_hold_pct']:+.2f}%")

    # ---- PnL por año ----
    print("\n--- PnL por año (USD sobre $500) ---")
    años = sorted({y for _, res in resultados for y in res['por_año']})
    print(f" {'config':<32}" + "".join(f"{y:>9}" for y in años))
    for nombre, res in resultados:
        print(f" {nombre:<32}" + "".join(f"{res['por_año'].get(y,0):>+9.1f}" for y in años))

    # ---- comportamiento en el rally reciente ----
    print("\n--- ¿Entró en los últimos 10 días (el rally actual)? ---")
    for nombre, res in resultados:
        rec = res['recientes']
        if not rec:
            print(f" {nombre:<32} 0 entradas")
        else:
            print(f" {nombre:<32} {len(rec)} entrada(s):")
            for t in rec:
                est = t['status']
                pnl = f"{t['pnl']:+.2f}" if est == 'CERRADA' else 'abierta'
                print(f"     {pd.Timestamp(t['entry_time']).strftime('%m-%d %Hh')} "
                      f"{t['symbol']:<8} {t['type']:<5} @ {t['entry_price']:.4f}  "
                      f"→ {est} {pnl} ({t.get('exit_reason','—')})")

    # ---- veredicto pre-registrado ----
    print("\n" + "=" * 84)
    print(" VEREDICTO (criterio test D: gana solo si PnL >= baseline Y DD <= baseline)")
    print("=" * 84)
    for nombre, res in resultados[1:]:
        r = res['r']
        mejor_pnl = r['net_pnl_pct'] >= base_pnl
        mejor_dd = res['dd'] <= base_dd
        if mejor_pnl and mejor_dd:
            v = "GANA (mejor en ambos ejes)"
        elif mejor_pnl and not mejor_dd:
            v = "TRADE-OFF (más PnL pero más drawdown)"
        elif not mejor_pnl and mejor_dd:
            v = "TRADE-OFF (menos PnL pero menos drawdown)"
        else:
            v = "PIERDE (peor en ambos ejes)"
        print(f" {nombre:<32} PnL {r['net_pnl_pct']:+.2f}% vs {base_pnl:+.2f} | "
              f"DD {res['dd']:.1f}% vs {base_dd:.1f}%  → {v}")


if __name__ == '__main__':
    main()
