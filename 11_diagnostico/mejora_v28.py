"""
mejora_v28.py — ¿cómo hacer que V28 (copiloto 1h) PARTICIPE MÁS sin cambiar 1h?

V28 hoy: entrada=patrón de vela (restrictiva), salida copiloto SL −1R / TP 2R.
Problema: 0 trades en 5 días; demasiado restrictiva en tendencias.

Prueba (sandbox aislado; V28 vivo en GCP NO se toca) varias ENTRADAS a 1h con la
MISMA salida de copiloto (SL 1R / TP 2R = EXIT_MODE 'rr'), midiendo lo que de
verdad importa para un copiloto:
  - PARTICIPACIÓN: nº de señales (y cuántas en los últimos 10 días = el rally).
  - RECONOCIMIENTO (KPI de V28): % que alcanza +0.5R/+1R/+2R ANTES del SL
    (peak conservador por cierres; OBJETIVO=100), y % de 'SL inmediato' (<10%).
  - SOLAPE con la entrada actual (patrones): de las señales EXTRA, ¿cuántas son
    NUEVAS y de qué calidad? (¿añade oportunidades distintas o ruido?)
  - PnL mecánico SL/2R como CONTEXTO (no es el KPI: el humano decide entre SL y 2R).

Entradas probadas (todas 1h):
  patrones        = V28 actual (baseline)
  continua        = cualquier vela con tendencia alineada (sin exigir patrón)
  continua_rsi90  = igual, pero guard RSI relajado 90/10 (para no bloquear trends sobrecomprados)
  pullback        = retroceso a EMA50 en tendencia alineada
  ruptura         = ruptura Donchian20 + volumen, SIN gate de tendencia (caza el arranque)
"""
import os
import sys
import pickle

import pandas as pd

sys.path.insert(0, os.path.abspath('sandbox'))
import config                                  # noqa: E402
from indicadores import calcular_indicadores   # noqa: E402
from backtest import BacktestV25, BALANCE_INICIAL  # noqa: E402
from binance_client import BinanceClient       # noqa: E402

config.INTERVAL = '1h'
config.EXIT_MODE = 'rr'
config.RR_TP_MULT = 2.0
config.COOLDOWN_CANDLES = 2
config.BT_TAKER_FEE = 0.0005     # V28 entra a mercado (taker) — costos honestos
config.BT_SLIPPAGE = 0.0005

SYMS = ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']
# 1er arg opcional: lista de símbolos (validación out-of-basket); solo en este proceso.
if len(sys.argv) > 1 and sys.argv[1]:
    SYMS = [s.strip().upper() for s in sys.argv[1].split(',') if s.strip()]
CANDLES = 4500                    # ~187 días 1h (incluye el rally reciente + contexto)

# (label, entry_mode, rsi_max_long, rsi_min_short)
MODOS = [
    ('patrones (V28 actual)', 'patrones', 78, 22),
    ('continua',              'continua', 78, 22),
    ('continua_rsi90',        'continua', 90, 10),
    ('pullback',              'pullback', 78, 22),
    ('ruptura (sin gate)',    'ruptura',  78, 22),
]


class Nulo:
    dir = '(off)'
    def registrar_activacion(self, *a, **k): pass
    def registrar_vela(self, *a, **k): pass
    def registrar_cierre(self, *a, **k): pass


def cargar():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"v28_cache_1h_{CANDLES}_{'-'.join(s[:4] for s in SYMS)}.pkl")
    if os.path.isfile(ruta):
        with open(ruta, 'rb') as f:
            return pickle.load(f)
    cli = BinanceClient()
    raw = {}
    for s in SYMS:
        print(f"INFO: descargando {CANDLES} velas 1h de {s}...")
        raw[s] = cli.klines_paginated(s, CANDLES)
    with open(ruta, 'wb') as f:
        pickle.dump(raw, f)
    return raw


def peak_de(t):
    p = t.get('peak_progress', 0.0)
    if t['exit_reason'].startswith('OBJETIVO'):
        p = max(p, 100.0)
    return p


def correr(raw, entry, rsi_max, rsi_min):
    config.SYMBOLS = list(SYMS)
    config.ENTRY_MODE = entry
    config.RSI_MAX_LONG = rsi_max
    config.RSI_MIN_SHORT = rsi_min
    dfs = {s: calcular_indicadores(raw[s]) for s in SYMS}
    bt = BacktestV25(candles=0, forense_dir='/tmp/v28_forense')
    bt.forense = Nulo()
    bt.dfs = dfs
    bt.correr()
    return [t for t in bt.trades if t['status'] == 'CERRADA'], bt.resumen()


def es_nuevo(t, base):
    """True si el trade t NO solapa (símbolo+dir+tiempo) con ninguno del baseline."""
    for b in base:
        if t['symbol'] == b['symbol'] and t['type'] == b['type'] \
                and t['entry_time'] < b['exit_time'] and b['entry_time'] < t['exit_time']:
            return False
    return True


def main():
    raw = cargar()
    ini = min(df['time'].iloc[0] for df in raw.values())
    fin = max(df['time'].iloc[-1] for df in raw.values())
    corte = pd.Timestamp.now('UTC').tz_localize(None) - pd.Timedelta(days=10)
    print(f"\nVentana 1h: {ini} → {fin} | basket V28: {', '.join(SYMS)}")
    print("Salida = copiloto SL −1R / TP 2R. KPI = reconocimiento (no PnL).\n")

    base_trades = None
    print(f"{'entrada':<22}{'señales':>8}{'rec10d':>7}{'≥+0.5R':>8}{'≥+1R':>7}"
          f"{'≥+2R':>7}{'SLinm':>7}{'PnL%':>8}{'PF':>7}{'%nuevas':>9}{'≥1R(nuevas)':>12}")
    for label, entry, rmax, rmin in MODOS:
        try:
            trades, r = correr(raw, entry, rmax, rmin)
        except Exception as e:
            print(f"{label:<22} ERROR: {e}")
            continue
        n = len(trades)
        if n == 0:
            print(f"{label:<22}{0:>8}")
            continue
        a05 = sum(1 for t in trades if peak_de(t) >= 25) / n * 100
        a1 = sum(1 for t in trades if peak_de(t) >= 50) / n * 100
        a2 = sum(1 for t in trades if peak_de(t) >= 100) / n * 100
        slimm = sum(1 for t in trades if 'STOP' in t['exit_reason'] and peak_de(t) < 10) / n * 100
        rec10 = sum(1 for t in trades if pd.Timestamp(t['entry_time']) >= corte)

        if entry == 'patrones' and rmax == 78:
            base_trades = trades
            pct_nuevas = nuevas_1r = float('nan')
        else:
            nuevas = [t for t in trades if base_trades is None or es_nuevo(t, base_trades)]
            pct_nuevas = len(nuevas) / n * 100 if n else 0
            nuevas_1r = (sum(1 for t in nuevas if peak_de(t) >= 50) / len(nuevas) * 100
                         if nuevas else 0)

        nn = '' if pd.isna(pct_nuevas) else f"{pct_nuevas:>8.0f}%"
        n1 = '' if pd.isna(nuevas_1r) else f"{nuevas_1r:>11.0f}%"
        print(f"{label:<22}{n:>8}{rec10:>7}{a05:>7.0f}%{a1:>6.0f}%{a2:>6.0f}%"
              f"{slimm:>6.0f}%{r['net_pnl_pct']:>+7.1f}%{str(r['profit_factor']):>7}{nn}{n1}")

    print("\nbarras pre-reg V28 (reconocimiento): ≥+0.5R ≥50% · ≥+1R ≥30%")
    print("'%nuevas' = señales que NO solapan con la entrada actual (patrones);")
    print("'≥1R(nuevas)' = de esas nuevas, cuántas alcanzan +1R (calidad de lo AÑADIDO).")


if __name__ == '__main__':
    main()
