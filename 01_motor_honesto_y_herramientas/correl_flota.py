"""
correl_flota.py — Correlación de la curva de equity de una estrategia candidata
vs V26 (4h) y V36 (15m), para el Hilo B (V38/V39/V40, 2026-07-03).

El objetivo del usuario NO es otro edge redundante, sino un edge NO-CORRELACIONADO
con la flota viva (V26+V36) — porque ESE es el que suaviza más la curva combinada
(lección V37: p10 de la ventana de 1 año pasó de −14.3% a −2.5% al combinar dos
edges de correlación 0.67). Cuanto MÁS BAJA la correlación de un candidato con
V26 y V36, MÁS valioso para la flota.

Reconstruye la equity diaria de la estrategia candidata con el motor honesto
(mismo BacktestV25) y la correlaciona (retornos diarios) contra las equities ya
generadas por V37 (v37_eq_v26_base.csv de 4 años, v37_eq_v36_4y.csv de 4 años).

Uso: python3 correl_flota.py --entrada sweep --salida tendencia [--interval 1h]
"""
import argparse
import os
import pickle

import numpy as np
import pandas as pd

import config
from indicadores import calcular_indicadores
from backtest import BacktestV25, BALANCE_INICIAL
from walkforward import ForenseNulo

DIR = os.path.dirname(os.path.abspath(__file__))


def equity_diaria(bt):
    """Equity mark-to-market diaria (misma definición que dd_real/suavizado)."""
    times = {s: d['time'].values for s, d in bt.dfs.items()}
    closes = {s: d['close'].values for s, d in bt.dfs.items()}
    timeline = np.array(sorted(set().union(*[set(v) for v in times.values()])))
    pos_de = {s: np.searchsorted(timeline, v) for s, v in times.items()}
    realizado = np.zeros(len(timeline))
    noreal = np.zeros(len(timeline))
    for t in bt.trades:
        if t['status'] != 'CERRADA':
            continue
        s = t['symbol']
        xi = np.searchsorted(timeline, np.datetime64(t['exit_time']))
        realizado[xi:] += t['pnl']
        i0 = np.searchsorted(times[s], np.datetime64(t['entry_time']))
        i1 = np.searchsorted(times[s], np.datetime64(t['exit_time']))
        if i1 <= i0:
            continue
        sign = 1.0 if t['type'] == 'LONG' else -1.0
        seg = (closes[s][i0:i1] - t['entry_price']) * t['qty'] * sign
        np.add.at(noreal, pos_de[s][i0:i1], seg)
    eq = pd.Series(BALANCE_INICIAL + realizado + noreal,
                   index=pd.DatetimeIndex(timeline))
    return eq.resample('1D').last().ffill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--entrada', required=True)
    ap.add_argument('--salida', default='tendencia')
    ap.add_argument('--interval', default='1h')
    ap.add_argument('--cache', default='wf_cache_1h_26280_2026-06-11.pkl')
    ap.add_argument('--fee', type=float, default=0.0002)
    ap.add_argument('--slippage', type=float, default=0.0002)
    args = ap.parse_args()

    config.INTERVAL = args.interval
    config.ENTRY_MODE = args.entrada
    config.EXIT_MODE = args.salida
    config.BT_TAKER_FEE = args.fee
    config.BT_SLIPPAGE = args.slippage
    with open(os.path.join(DIR, args.cache), 'rb') as f:
        raw = pickle.load(f)
    config.SYMBOLS = list(raw.keys())
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/correl_forense')
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()

    cand = equity_diaria(bt)
    r26 = pd.read_csv(os.path.join(DIR, 'v37_eq_v26_base.csv'),
                      index_col=0, parse_dates=True)['equity']
    r36 = pd.read_csv(os.path.join(DIR, 'v37_eq_v36_4y.csv'),
                      index_col=0, parse_dates=True)['equity']

    def corr(a, b):
        idx = a.index.intersection(b.index)
        ra = a.loc[idx].pct_change().replace([np.inf, -np.inf], np.nan)
        rb = b.loc[idx].pct_change().replace([np.inf, -np.inf], np.nan)
        m = ra.notna() & rb.notna()
        return round(float(ra[m].corr(rb[m])), 3), int(m.sum())

    c26, n26 = corr(cand, r26)
    c36, n36 = corr(cand, r36)
    r = bt.resumen()
    print(f"\n{args.entrada} / {args.salida} — PnL {r['net_pnl_pct']:+.2f}% | "
          f"trades {r['trades']} | PF {r['profit_factor']}")
    print(f"Correlación diaria vs V26: {c26} (n={n26})")
    print(f"Correlación diaria vs V36: {c36} (n={n36})")
    print(f"CORREL_RESUMEN|{{'entrada':'{args.entrada}','salida':'{args.salida}',"
          f"'pnl_pct':{r['net_pnl_pct']},'pf':{r['profit_factor']},"
          f"'corr_v26':{c26},'corr_v36':{c36}}}")


if __name__ == '__main__':
    main()
