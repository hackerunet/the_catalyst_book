"""
walkforward.py — Validación multi-régimen de la estrategia V25 + null de
entradas aleatorias (Monte Carlo).

Responde la pregunta que UNA ventana bajista de 62 días no puede responder:
¿el PF<1 es un hecho de la estrategia o un artefacto del régimen?

Dos partes:

1. WALK-FORWARD: descarga N años de velas 1h (una sola vez, cacheado en
   pickle), parte el histórico en ventanas CONSECUTIVAS NO SOLAPADAS del mismo
   tamaño que la ventana de regresión (1500 velas ≈ 62 días) y corre el MISMO
   motor honesto (backtest.BacktestV25, misma estrategia.py que el bot en
   vivo) en cada una. Reporta PnL/WR/PF/buy&hold por ventana + agregados.
   La estrategia NO se re-ajusta por ventana (no tiene parámetros entrenables)
   — esto es evaluación out-of-sample pura en regímenes nunca vistos durante
   el tuning (todo el tuning fue sobre la ventana que termina 2026-06-11).

2. NULL DE ENTRADAS ALEATORIAS (lección del veredicto del motor honesto):
   M corridas donde las ENTRADAS son aleatorias (timestamps muestreados con la
   misma frecuencia por símbolo/ventana que la estrategia, dirección a cara o
   cruz) pero las SALIDAS son EXACTAMENTE las mismas (mismo TP por ATR diario,
   mismo SL, misma escalera de deciles vía estrategia.evaluar_salida, mismo
   orden intravela pesimista y mismos costos vía backtest.pnl_neto_cierre).
   Si el PnL real no supera claramente la distribución null (percentil >=95),
   la señal de entrada no aporta nada sobre el azar.

Uso (sin API keys, datos públicos; correr desde esta carpeta):
    python3 walkforward.py                          # 3 años, ventanas de 1500, 200 MC
    python3 walkforward.py --years 2 --mc 100
    python3 walkforward.py --end 2026-06-11         # reproducible
    python3 walkforward.py --interval 4h --years 4 --window 750
                                                    # variante 4h (misma estrategia,
                                                    # menor cadencia) SIN tocar config.py
    python3 walkforward.py --fee 0.0002 --slippage 0.0002
                                                    # sensibilidad de costos (maker)
Salida: wf_resumen.json (o wf_resumen_<tag>.json) + tabla por stdout.

Los overrides solo viven en este proceso (config se parchea en memoria) — el
bot en vivo y su config.py NO se tocan.
"""
import argparse
import json
import os
import pickle
import random
import sys
from datetime import datetime

import pandas as pd

import config
import estrategia
from backtest import BacktestV25, pnl_neto_cierre, BALANCE_INICIAL
from binance_client import BinanceClient
from indicadores import calcular_indicadores, atr_diario

DIR_BASE = os.path.dirname(os.path.abspath(__file__))


class ForenseNulo:
    """Sustituye RegistroForense en corridas masivas (sin I/O por trade)."""
    dir = '(desactivado)'

    def registrar_activacion(self, *a, **k):
        pass

    def registrar_vela(self, *a, **k):
        pass

    def registrar_cierre(self, *a, **k):
        pass


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def cargar_historico(total, end_ms, cache_tag):
    ruta = os.path.join(DIR_BASE, f"wf_cache_{cache_tag}.pkl")
    if os.path.isfile(ruta):
        print(f"INFO: usando cache {ruta}")
        with open(ruta, 'rb') as f:
            return pickle.load(f)
    raw = {}
    for sym in config.SYMBOLS:
        print(f"INFO: descargando {total} velas 1h de {sym}...")
        if "EURUSD" in sym:
            from yfinance_client import YFinanceClient
            cliente_yf = YFinanceClient()
            raw[sym] = cliente_yf.klines_paginated(sym, total, end_time_ms=end_ms)
        else:
            cliente = BinanceClient()
            raw[sym] = cliente.klines_paginated(sym, total, end_time_ms=end_ms)
        print(f"  {sym}: {len(raw[sym])} velas "
              f"({raw[sym]['time'].iloc[0]} → {raw[sym]['time'].iloc[-1]})")
    with open(ruta, 'wb') as f:
        pickle.dump(raw, f)
    return raw


def ventanas(raw, win):
    """Ventanas consecutivas NO solapadas de `win` velas, alineadas al FINAL
    del histórico (la última ventana = la ventana de regresión congelada)."""
    n_min = min(len(df) for df in raw.values())
    k = n_min // win
    out = []
    for j in range(k):
        fin = n_min - j * win
        ini = fin - win
        out.append({sym: df.iloc[len(df) - n_min + ini: len(df) - n_min + fin]
                    .reset_index(drop=True) for sym, df in raw.items()})
    return list(reversed(out))  # cronológico


# ---------------------------------------------------------------------------
# Parte 1: walk-forward con el motor real
# ---------------------------------------------------------------------------
def correr_ventana(slices):
    bt = BacktestV25(candles=len(next(iter(slices.values()))),
                     forense_dir='/tmp/v25_wf_forense')  # se descarta (ForenseNulo)
    bt.forense = ForenseNulo()
    bt.dfs = {sym: calcular_indicadores(df) for sym, df in slices.items()}
    bt.correr()
    return bt


# ---------------------------------------------------------------------------
# Parte 2: null de entradas aleatorias (mismas salidas, mismos costos)
# ---------------------------------------------------------------------------
def _abrir_aleatorio(sub_df, direccion, balance):
    """Réplica EXACTA del sizing/TP/SL de estrategia.evaluar_entrada, sin señal."""
    precio = float(sub_df['close'].iloc[-1])
    atr_d = atr_diario(sub_df)
    dist_tp = atr_d * config.TP_DAILY_ATR_MULT if atr_d else precio * 0.03
    dist_tp = min(max(dist_tp, precio * config.TP_MIN_PCT), precio * config.TP_MAX_PCT)
    dist_sl = dist_tp * config.SL_FRACTION_OF_TP
    if direccion == 'LONG':
        tp, sl = precio + dist_tp, precio - dist_sl
    else:
        tp, sl = precio - dist_tp, precio + dist_sl
    qty = (balance * config.RISK_PER_TRADE) / dist_sl
    return {'type': direccion, 'entry_price': precio, 'tp': tp, 'sl': sl,
            'qty': qty, 'peak_progress': 0.0, 'locked_decile': 0, 'status': 'ABIERTA'}


def _salidas_vela_mc(t, row, ts, tendencia_ahora=None):
    """Mismo orden intravela pesimista que BacktestV25._salidas_vela."""
    adverso = row['low'] if t['type'] == 'LONG' else row['high']
    favorable = row['high'] if t['type'] == 'LONG' else row['low']

    # TEST C: mismas salidas que el motor real (stop pesimista o flip al cierre)
    if getattr(config, 'EXIT_MODE', 'escalera') == 'tendencia':
        if estrategia.evaluar_salida(t, adverso)['cerrar']:
            return t['sl'], ts
        if estrategia.salida_por_flip(tendencia_ahora, t['type']):
            return row['close'], ts
        return None
    res = estrategia.evaluar_salida(t, adverso)
    if res['cerrar']:
        precio = t['sl'] if 'STOP' in res['cerrar'] else adverso
        return precio, ts
    if estrategia.calcular_progreso(t, favorable) >= 100:
        return t['tp'], ts
    res_close = estrategia.evaluar_salida(t, row['close'])
    if res_close['nuevo_peak'] is not None:
        t['peak_progress'] = res_close['nuevo_peak']
    if res_close['nuevo_decil'] is not None:
        t['locked_decile'] = res_close['nuevo_decil']
    if res_close['cerrar']:
        return row['close'], ts
    return None


def mc_run(dfs_ind, n_trades_por_sym, rng, tendencia_en=None):
    """Una corrida null: entradas aleatorias (frecuencia por símbolo igualada
    a la estrategia en esa ventana, dirección 50/50), salidas idénticas.
    tendencia_en(sym, i): lookup memoizado para el flip del TEST C."""
    pnl_total = 0.0
    balance = BALANCE_INICIAL
    for sym, df in dfs_ind.items():
        n_obj = n_trades_por_sym.get(sym, 0)
        if n_obj <= 0:
            continue
        elegibles = list(range(config.WARMUP_CANDLES, len(df) - 1))
        rng.shuffle(elegibles)
        candidatos = sorted(elegibles[:n_obj * 3])
        abiertos_hasta = -1
        tomados = 0
        for i in candidatos:
            if tomados >= n_obj or i <= abiertos_hasta:
                continue
            t = _abrir_aleatorio(df.iloc[:i + 1], rng.choice(('LONG', 'SHORT')), balance)
            t['entry_time'] = df['time'].iloc[i]
            j = i + 1
            cierre = None
            while j < len(df) and cierre is None:
                tend = tendencia_en(sym, j) if tendencia_en is not None else None
                cierre = _salidas_vela_mc(t, df.iloc[j], df['time'].iloc[j],
                                          tendencia_ahora=tend)
                j += 1
            if cierre is None:  # fin de ventana: cierre administrativo
                cierre = (float(df['close'].iloc[-1]), df['time'].iloc[-1])
            pnl = pnl_neto_cierre(t, cierre[0], cierre[1])
            pnl_total += pnl
            balance += pnl
            abiertos_hasta = j + config.COOLDOWN_CANDLES
            tomados += 1
    return pnl_total


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='Walk-forward + null aleatorio V25')
    ap.add_argument('--years', type=float, default=3.0)
    ap.add_argument('--window', type=int, default=1500)
    ap.add_argument('--mc', type=int, default=200, help='corridas null por ventana (0=off)')
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--interval', type=str, default=None,
                    help="override de timeframe (ej. 4h) solo en este proceso")
    ap.add_argument('--fee', type=float, default=None, help='override BT_TAKER_FEE')
    ap.add_argument('--slippage', type=float, default=None, help='override BT_SLIPPAGE')
    ap.add_argument('--entrada', type=str, default='patrones',
                    help='modo de entrada')
    ap.add_argument('--filtro-squeeze', action='store_true',
                    help='TEST A: bloquear entradas con squeeze TTM activo '
                         '(BB(20,2σ) dentro de Keltner(EMA20±1.5×ATR20))')
    ap.add_argument('--filtro-rs', action='store_true',
                    help='TEST B: fuerza relativa del basket — LONG solo en la '
                         'mitad superior del ranking ROC 20d, SHORT solo en la inferior')
    ap.add_argument('--salida', choices=['escalera', 'tendencia'],
                        help="TEST C: modo de salida — escalera (vivo) | tendencia (sin TP/escalera; stop de protección o flip de alineación)")
    ap.add_argument('--tag', type=str, default='',
                        help="sufijo del json de salida")
    ap.add_argument('--symbols', type=str, default='',
                        help="Coma-separated list of symbols to override config.SYMBOLS (e.g. ETHUSDT)")
    args = ap.parse_args()

    # --- overrides en memoria (el config.py del bot en vivo NO se modifica) ---
    if args.interval:
        config.INTERVAL = args.interval
        horas_vela = int(pd.Timedelta(args.interval).total_seconds() // 3600)
        # COOLDOWN_CANDLES se interpreta en HORAS en el motor — escalar a 2 velas
        config.COOLDOWN_CANDLES = 2 * horas_vela
    else:
        horas_vela = 1
    if args.fee is not None:
        config.BT_TAKER_FEE = args.fee
    if args.slippage is not None:
        config.BT_SLIPPAGE = args.slippage
    if args.entrada:
        config.ENTRY_MODE = args.entrada
    if args.filtro_squeeze:
        config.FILTRO_SQUEEZE = True
    if args.filtro_rs:
        config.FILTRO_RS = True
    if args.salida:
        config.EXIT_MODE = args.salida
    if args.symbols:
        config.SYMBOLS = [s.strip() for s in args.symbols.split(',') if s.strip()]

    total = int(args.years * 365 * 24 / horas_vela)
    end_ms = int(pd.Timestamp(args.end).timestamp() * 1000) if args.end else None
    cache_tag = f"{config.INTERVAL}_{total}_{len(config.SYMBOLS)}_{args.end or 'now'}".replace(':', '').replace(' ', '_')

    raw = cargar_historico(total, end_ms, cache_tag)
    wins = ventanas(raw, args.window)
    print(f"\nINFO: {len(wins)} ventanas de {args.window} velas "
          f"({args.window - config.WARMUP_CANDLES} efectivas c/u)\n")

    filas = []
    rng = random.Random(args.seed)
    for k, slices in enumerate(wins, 1):
        bt = correr_ventana(slices)
        r = bt.resumen()
        n_por_sym = {}
        for t in bt.trades:
            n_por_sym[t['symbol']] = n_por_sym.get(t['symbol'], 0) + 1

        fila = {
            'ventana': k,
            'inicio': r['window_start'], 'fin': r['window_end'],
            'trades': r['trades'], 'wr': r['win_rate'], 'pf': r['profit_factor'],
            'pnl_pct': r['net_pnl_pct'], 'bh_pct': r['benchmark_buy_hold_pct'],
        }

        if args.mc > 0 and r['trades'] > 0:
            dfs_ind = bt.dfs  # ya con indicadores
            # TEST C: el null comparte el memo de tendencia del motor (mismas salidas)
            tendencia_en = bt._tendencia_en \
                if getattr(config, 'EXIT_MODE', 'escalera') == 'tendencia' else None
            nulls = [mc_run(dfs_ind, n_por_sym, rng, tendencia_en=tendencia_en)
                     for _ in range(args.mc)]
            nulls_pct = sorted(p / BALANCE_INICIAL * 100 for p in nulls)
            mejor_que = sum(1 for p in nulls_pct if p < r['net_pnl_pct'])
            fila['null_mediana_pct'] = round(nulls_pct[len(nulls_pct) // 2], 2)
            fila['null_p95_pct'] = round(nulls_pct[int(len(nulls_pct) * 0.95)], 2)
            fila['percentil_vs_null'] = round(mejor_que / len(nulls_pct) * 100, 1)

        filas.append(fila)
        print(f"V{k:02d} {fila['inicio'][:10]}→{fila['fin'][:10]} | "
              f"trades {fila['trades']:>3} | WR {fila['wr']:>5}% | PF {fila['pf']} | "
              f"PnL {fila['pnl_pct']:+6.2f}% | B&H {fila['bh_pct']:+7.2f}%"
              + (f" | null med {fila.get('null_mediana_pct', '—')}% "
                 f"pctl {fila.get('percentil_vs_null', '—')}" if args.mc else ''))
        sys.stdout.flush()

    # ---- agregados ----
    pnls = [f['pnl_pct'] for f in filas]
    bhs = [f['bh_pct'] for f in filas]
    positivas = sum(1 for p in pnls if p > 0)
    vs_bh = sum(1 for f in filas if f['pnl_pct'] > f['bh_pct'])
    pctls = [f['percentil_vs_null'] for f in filas if 'percentil_vs_null' in f]

    agg = {
        'ventanas': len(filas),
        'pnl_total_pct_sum': round(sum(pnls), 2),
        'pnl_mediana_pct': round(sorted(pnls)[len(pnls) // 2], 2) if pnls else None,
        'ventanas_positivas': f"{positivas}/{len(filas)}",
        'ventanas_sobre_buyhold': f"{vs_bh}/{len(filas)}",
        'percentil_vs_null_mediano': round(sorted(pctls)[len(pctls) // 2], 1) if pctls else None,
        'config': {
            'interval': config.INTERVAL,
            'entry_mode': getattr(config, 'ENTRY_MODE', 'patrones'),
            'exit_mode': getattr(config, 'EXIT_MODE', 'escalera'),
            'filtro_squeeze': getattr(config, 'FILTRO_SQUEEZE', False),
            'filtro_rs': getattr(config, 'FILTRO_RS', False),
            'rs_lookback_days': getattr(config, 'RS_LOOKBACK_DAYS', None),
            'fee': config.BT_TAKER_FEE, 'slippage': config.BT_SLIPPAGE,
            'window': args.window, 'years': args.years, 'mc': args.mc,
            'seed': args.seed, 'end': args.end,
            'risk_per_trade': config.RISK_PER_TRADE,
            'sl_fraction': config.SL_FRACTION_OF_TP,
            'pullback_arm': config.PULLBACK_ARM_DECILE,
            'reversal_vol_floor': config.REVERSAL_VOL_FLOOR,
            'body_min_atr': config.BODY_MIN_ATR_FRACTION,
            'wick_range_min_atr': config.WICK_RANGE_MIN_ATR_FRACTION,
        },
        'ventanas_detalle': filas,
    }

    print("\n" + "=" * 70)
    print("WALK-FORWARD V25 — resumen multi-régimen")
    print("=" * 70)
    print(f"Ventanas: {agg['ventanas']} | positivas: {agg['ventanas_positivas']} | "
          f"sobre buy&hold: {agg['ventanas_sobre_buyhold']}")
    print(f"PnL mediano por ventana: {agg['pnl_mediana_pct']}% | "
          f"suma: {agg['pnl_total_pct_sum']}%")
    if pctls:
        print(f"Percentil mediano vs null aleatorio: {agg['percentil_vs_null_mediano']} "
              f"(>=95 en la mayoría de ventanas = la entrada aporta señal; "
              f"~50 = indistinguible del azar)")

    nombre = f"wf_resumen_{args.tag}.json" if args.tag else 'wf_resumen.json'
    ruta = os.path.join(DIR_BASE, nombre)
    with open(ruta, 'w') as f:
        json.dump(agg, f, indent=1, ensure_ascii=False)
    print(f"\nGuardado: {ruta}")
    print(f"WALKFORWARD_RESUMEN|{json.dumps({k: v for k, v in agg.items() if k != 'ventanas_detalle'}, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
