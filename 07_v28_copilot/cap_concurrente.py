"""
cap_concurrente.py — Tarea #40: ¿ayuda al DD limitar posiciones concurrentes?

Corre el motor real de V28 (1h, patrones, copilot) sobre el cache, variando
MAX_CONCURRENT (None=sin tope/6, 4, 3, 2), y mide para cada nivel:
  - PnL neto
  - Max DD VERDADERO (mark-to-market, incluye no-realizado mientras la posición
    vive) — el de balance-por-trade subestima
  - Peor DD rolling 90 días
  - nº de trades (cuánta participación se pierde al capar)
Mismo enfoque que dd_real_v26.py. Responde si "máximo 3 a la vez" mejora el DD
y cuánto cuesta en retorno/participación.

Uso: python3 cap_concurrente.py [--cache wf_cache_1h_26280_2026-06-20_0000.pkl]
"""
import argparse
import pickle
import os

import pandas as pd

import config
from indicadores import calcular_indicadores
from backtest import BacktestV25
from walkforward import ForenseNulo

BALANCE_INICIAL = 500.0


def correr(raw, cap):
    config.MAX_CONCURRENT = cap
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v28_cap_forense')
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()
    return bt


def equity_mtm(bt):
    todos = sorted(set().union(*[set(d['time']) for d in bt.dfs.values()]))
    precio = {s: dict(zip(d['time'], d['close'])) for s, d in bt.dfs.items()}
    eq = []
    for ts in todos:
        real = noreal = 0.0
        for t in bt.trades:
            if t['entry_time'] > ts:
                continue
            if t.get('exit_time') is not None and t['exit_time'] <= ts:
                real += t['pnl']
            else:
                p = precio[t['symbol']].get(ts)
                if p is None:
                    continue
                noreal += (p - t['entry_price']) * t['qty'] if t['type'] == 'LONG' \
                    else (t['entry_price'] - p) * t['qty']
        eq.append((ts, BALANCE_INICIAL + real + noreal))
    return pd.DataFrame(eq, columns=['ts', 'equity'])


def dds(df):
    eq = df.set_index('ts')['equity']
    maxdd = ((eq.cummax() - eq) / eq.cummax() * 100).max()
    rp = eq.rolling('90D').max()
    dd90 = ((rp - eq) / rp * 100).max()
    return maxdd, dd90


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default='wf_cache_1h_26280_2026-06-20_0000.pkl')
    args = ap.parse_args()
    ruta = os.path.join(os.path.dirname(__file__), args.cache)
    print(f"INFO: cargando {ruta}")
    with open(ruta, 'rb') as f:
        raw = pickle.load(f)

    print(f"\n{'cap':>5} | {'PnL%':>8} | {'trades':>6} | {'MaxDD%':>7} | {'DD90d%':>7}")
    print("-" * 48)
    base_pnl = None
    for cap in [None, 4, 3, 2]:
        bt = correr(raw, cap)
        r = bt.resumen()
        maxdd, dd90 = dds(equity_mtm(bt))
        if base_pnl is None:
            base_pnl = r['net_pnl_pct']
        etq = 'sin' if cap is None else str(cap)
        print(f"{etq:>5} | {r['net_pnl_pct']:>+7.1f}% | {r['trades']:>6} | "
              f"{maxdd:>6.1f}% | {dd90:>6.1f}%")
    config.MAX_CONCURRENT = None


if __name__ == '__main__':
    main()
