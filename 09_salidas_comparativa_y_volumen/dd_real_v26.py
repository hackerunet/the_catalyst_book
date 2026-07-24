"""
dd_real_v26.py — DD VERDADERO de V26 (mark-to-market), no el de balance-por-trade.

El --continuo del walkforward mide el DD sobre el balance de trades CERRADOS, lo
que SUBESTIMA el drawdown real: un trend-follower devuelve mucho avance NO
realizado antes de que el flip cierre el trade. Binance mide el MDD sobre la
equity mark-to-market (con no-realizado), diariamente, en ventana rolling de 90
días. Este script reconstruye esa curva y mide:
  - Max DD global (4 años)
  - Peor DD rolling de 90 días (la métrica del gate de lead trader)

Corre el motor real (4h, cruce, tendencia, maker) sobre el cache, saca los
trades, y reconstruye la equity por timestamp marcando las posiciones abiertas
al precio de cierre de cada vela.

Uso: python3 dd_real_v26.py [--risk 0.0033333] [--cache wf_cache_4h_8760_2026-06-11_0000.pkl]
"""
import argparse
import pickle
import os

import numpy as np
import pandas as pd

import config
from indicadores import calcular_indicadores
from backtest import BacktestV25

BALANCE_INICIAL = 500.0


def correr(cache, risk):
    # Config de V26 (igual que Test C / OOB), overrides en memoria
    config.INTERVAL = '4h'
    config.ENTRY_MODE = 'cruce'
    config.EXIT_MODE = 'tendencia'
    config.BT_TAKER_FEE = 0.0002
    config.BT_SLIPPAGE = 0.0002
    config.RISK_PER_TRADE = risk
    with open(os.path.join(os.path.dirname(__file__), cache), 'rb') as f:
        raw = pickle.load(f)
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v26_dd_forense')
    from walkforward import ForenseNulo
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()
    return bt


def equity_markto_market(bt):
    """Curva de equity por timestamp = inicial + realizado(cerrados<=t) +
    no-realizado(abiertos en t, marcados al cierre de la vela)."""
    trades = bt.trades
    # timeline global (todos los timestamps de todos los símbolos)
    todos = sorted(set().union(*[set(d['time']) for d in bt.dfs.values()]))
    # mapas precio por (sym, ts)
    precio = {s: dict(zip(d['time'], d['close'])) for s, d in bt.dfs.items()}
    # precomputar por trade: entry_time, exit_time, dir, entry, qty, pnl
    filas = []
    eq = []
    for ts in todos:
        realizado = 0.0
        noreal = 0.0
        for t in trades:
            et = t['entry_time']; xt = t.get('exit_time')
            if et > ts:
                continue
            if xt is not None and xt <= ts:
                realizado += t['pnl']
            else:
                # abierto en ts → marcar al precio de la vela
                p = precio[t['symbol']].get(ts)
                if p is None:
                    continue
                if t['type'] == 'LONG':
                    noreal += (p - t['entry_price']) * t['qty']
                else:
                    noreal += (t['entry_price'] - p) * t['qty']
        eq.append((ts, BALANCE_INICIAL + realizado + noreal))
    return pd.DataFrame(eq, columns=['ts', 'equity'])


def max_dd(equity):
    peak = equity.cummax()
    dd = (peak - equity) / peak * 100
    return dd.max()


def peor_dd_rolling(df, dias=90):
    """Peor DD dentro de cualquier ventana de `dias` (la métrica de Binance)."""
    df = df.set_index('ts')
    eq = df['equity']
    win = f'{dias}D'
    # para cada t: pico en [t-90d, t] y DD actual respecto a ese pico
    roll_peak = eq.rolling(win).max()
    dd = (roll_peak - eq) / roll_peak * 100
    return dd.max()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--risk', type=float, default=config.PORTFOLIO_RISK_CAP / len(config.SYMBOLS))
    ap.add_argument('--cache', default='wf_cache_4h_8760_2026-06-11_0000.pkl')
    args = ap.parse_args()

    print(f"INFO: corriendo V26 continuo con RISK_PER_TRADE={args.risk:.5f} "
          f"(={args.risk*len(config.SYMBOLS)*100:.1f}% cap)")
    bt = correr(args.cache, args.risk)
    r = bt.resumen()
    cerrados = sorted((t for t in bt.trades if t['status'] == 'CERRADA'), key=lambda t: t['exit_time'])

    # DD por balance de cerrados (el viejo, para comparar)
    bal = peak = BALANCE_INICIAL; dd_cerr = 0.0
    for t in cerrados:
        bal += t['pnl']; peak = max(peak, bal)
        dd_cerr = max(dd_cerr, (peak - bal) / peak * 100)

    df_eq = equity_markto_market(bt)
    dd_mtm = max_dd(df_eq['equity'])
    dd_90 = peor_dd_rolling(df_eq, 90)

    print("\n" + "=" * 64)
    print(f"V26 — DD analysis | {r['window_start']} → {r['window_end']}")
    print("=" * 64)
    print(f"PnL: {r['net_pnl_pct']:+.2f}%  | trades {r['trades']} | WR {r['win_rate']}% | PF {r['profit_factor']}")
    print(f"DD por balance de trades CERRADOS (el viejo):  {dd_cerr:.1f}%")
    print(f"DD VERDADERO mark-to-market (máx 4 años):       {dd_mtm:.1f}%")
    print(f"PEOR DD rolling 90 días (= métrica de Binance): {dd_90:.1f}%  {'✅ <25%' if dd_90 < 25 else '🔴 >=25%'}")


if __name__ == '__main__':
    main()
