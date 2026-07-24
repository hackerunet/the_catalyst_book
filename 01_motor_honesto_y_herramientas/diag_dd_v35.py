"""
diag_dd_v35.py — DIAGNÓSTICO de qué genera el DD de V35 (15m) y efecto de reducir símbolos.

Corre el motor V35 (15m/patrones/tendencia/maker, basket original, riesgo 0.33%)
UNA vez, reconstruye la equity mark-to-market por símbolo y responde:
  1. Peor ventana de 90d: cuándo, y qué posiciones estaban abiertas concurrentes en el fondo.
  2. Contribución de cada símbolo al DD (leave-one-out) y al PnL.
  3. Efecto ESTRUCTURAL del tamaño del basket: distribución de (DD 90d, PnL) sobre
     TODOS los subconjuntos de tamaño 3/4/5/6 — sin cherry-pick del mejor.

IMPORTANTE — aproximación: el sizing REAL compone sobre un balance compartido
(qty = balance*risk/dist_sl), así que la equity NO es estrictamente aditiva por
símbolo. Este script usa la descomposición aditiva de la corrida COMPLETA (ignora
que un basket más chico habría compuesto distinto) — es correcta para el ranking
cualitativo y el efecto de tamaño, PERO los DD/PnL absolutos de cada subconjunto
son APROXIMADOS. Los candidatos finalistas se validan exacto con
  dd_real_v35.py --symbols <lista>  (re-simula con sizing real).
"""
import argparse
import itertools
import os
import pickle

import numpy as np
import pandas as pd

import config
from indicadores import calcular_indicadores
from backtest import BacktestV25

BALANCE_INICIAL = 500.0
CACHE = 'wf_cache_15m_70080_2026-06-11.pkl'


def correr(cache=CACHE):
    config.INTERVAL = '15m'
    config.ENTRY_MODE = 'patrones'
    config.EXIT_MODE = 'tendencia'
    config.BT_TAKER_FEE = 0.0002
    config.BT_SLIPPAGE = 0.0002
    with open(os.path.join(os.path.dirname(__file__), cache), 'rb') as f:
        raw = pickle.load(f)
    config.SYMBOLS = list(raw.keys())
    config.RISK_PER_TRADE = config.PORTFOLIO_RISK_CAP / len(config.SYMBOLS)  # 0.33%/trade (cap 2%)
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v35_diag_forense')
    from walkforward import ForenseNulo
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()
    return bt


def contribs_por_simbolo(bt):
    """Devuelve (timeline, {sym: np.array de contribución a la equity por ts})."""
    timeline = sorted(set().union(*[set(d['time']) for d in bt.dfs.values()]))
    idx = {ts: i for i, ts in enumerate(timeline)}
    N = len(timeline)
    # precio de cada símbolo alineado al timeline global (ffill)
    precio = {}
    for s, d in bt.dfs.items():
        ser = pd.Series(d['close'].values, index=d['time'].values)
        ser = ser.reindex(timeline).ffill().bfill()
        precio[s] = ser.values.astype(float)
    contrib = {s: np.zeros(N) for s in bt.dfs}
    for t in bt.trades:
        s = t['symbol']
        ei = idx.get(t['entry_time'])
        if ei is None:
            continue
        cerrado = t['status'] == 'CERRADA' and t.get('exit_time') is not None
        xi = idx.get(t['exit_time'], N) if cerrado else N
        p = precio[s][ei:xi]
        if t['type'] == 'LONG':
            contrib[s][ei:xi] += (p - t['entry_price']) * t['qty']
        else:
            contrib[s][ei:xi] += (t['entry_price'] - p) * t['qty']
        if cerrado:
            contrib[s][xi:] += t['pnl']
    return timeline, contrib


def dd_metrics(equity, timeline):
    eq = pd.Series(equity, index=pd.DatetimeIndex(timeline))
    peak = eq.cummax()
    dd_glob = ((peak - eq) / peak * 100).max()
    roll_peak = eq.rolling('90D').max()
    dd90 = ((roll_peak - eq) / roll_peak * 100).max()
    return dd_glob, dd90


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=CACHE, help='pickle de velas (def: basket original 15m)')
    args = ap.parse_args()
    bt = correr(args.cache)
    r = bt.resumen()
    timeline, contrib = contribs_por_simbolo(bt)
    syms = list(contrib.keys())

    total = np.zeros(len(timeline))
    for s in syms:
        total += contrib[s]
    eq_full = BALANCE_INICIAL + total
    dd_glob, dd90 = dd_metrics(eq_full, timeline)

    print("=" * 70)
    print(f"V35 DIAG | {r['window_start']} → {r['window_end']} | riesgo 0.33%/trade")
    print("=" * 70)
    print(f"FULL basket: PnL {r['net_pnl_pct']:+.2f}% | PF {r['profit_factor']} | "
          f"DD mtm {dd_glob:.1f}% | DD 90d {dd90:.1f}%  (sanity vs 27.2%)")

    # --- PnL por símbolo (exacto) ---
    pnl_s = {s: contrib[s][-1] for s in syms}
    print("\n--- Contribución por símbolo ---")
    print(f"{'símbolo':10} {'PnL $':>9} {'DD90d SIN él (aprox)':>22}")
    for s in sorted(syms, key=lambda x: pnl_s[x]):
        eq_wo = BALANCE_INICIAL + (total - contrib[s])
        _, dd90_wo = dd_metrics(eq_wo, timeline)
        print(f"{s:10} {pnl_s[s]:+9.2f} {dd90_wo:>21.1f}%")

    # --- peor ventana 90d: fondo y posiciones abiertas concurrentes ---
    eq = pd.Series(eq_full, index=pd.DatetimeIndex(timeline))
    roll_peak = eq.rolling('90D').max()
    dd_ser = (roll_peak - eq) / roll_peak * 100
    ts_fondo = dd_ser.idxmax()
    print(f"\n--- Peor fondo de DD 90d: {ts_fondo} (DD {dd_ser.max():.1f}%) ---")
    abiertas = []
    for t in bt.trades:
        et = t['entry_time']; xt = t.get('exit_time')
        if et <= ts_fondo and (xt is None or xt > ts_fondo):
            d = bt.dfs[t['symbol']]
            ser = pd.Series(d['close'].values, index=d['time'].values).reindex(timeline).ffill().bfill()
            p = float(ser.loc[ts_fondo])
            ur = (p - t['entry_price']) * t['qty'] if t['type'] == 'LONG' else (t['entry_price'] - p) * t['qty']
            abiertas.append((t['symbol'], t['type'], ur))
    print(f"Posiciones abiertas concurrentes en el fondo: {len(abiertas)}")
    for s, ty, ur in sorted(abiertas, key=lambda x: x[2]):
        print(f"   {s:10} {ty:5} no-realizado ${ur:+.2f}")

    # --- efecto estructural del tamaño del basket (aprox aditiva) ---
    print("\n--- Efecto del TAMAÑO del basket (aprox aditiva, todos los subconjuntos) ---")
    print(f"{'tamaño':7} {'#combos':>7} {'DD90d min/med/max':>26} {'PnL% min/med/max':>26}")
    for k in (3, 4, 5, 6):
        dds, pnls = [], []
        for combo in itertools.combinations(syms, k):
            eq_sub = BALANCE_INICIAL + sum(contrib[s] for s in combo)
            _, d90 = dd_metrics(eq_sub, timeline)
            dds.append(d90)
            pnls.append((eq_sub[-1] - BALANCE_INICIAL) / BALANCE_INICIAL * 100)
        dds, pnls = np.array(dds), np.array(pnls)
        print(f"{k:^7} {len(dds):>7} "
              f"{dds.min():>7.1f}/{np.median(dds):>5.1f}/{dds.max():<6.1f}    "
              f"{pnls.min():>7.1f}/{np.median(pnls):>5.1f}/{pnls.max():<6.1f}")


if __name__ == '__main__':
    main()
