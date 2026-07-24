"""
timing_entradas.py — ¿V28 entra TARDE a las tendencias?

Para cada entrada del motor real (1h, patrones, copilot) mide cuánto del
movimiento reciente YA había ocurrido al entrar ('frac_done'):
  - SHORT: frac_done = (max20 - entry) / (max20 - min20)  → 1.0 = entró en el
    PISO del rango (tarde, casi todo el desplome ya pasó); 0.0 = en el techo (temprano).
  - LONG: simétrico.
Luego correlaciona con el resultado (peak alcanzado, PnL) para ver si las
entradas tardías rinden peor. También reporta sobre-extensión vs EMA200 al entrar.

Uso: python3 timing_entradas.py [--candles 3000] [--end 2026-06-25] [--n 20]
"""
import argparse
import numpy as np
import pandas as pd

import config
from backtest import BacktestV25


class ColectorTiming:
    dir = '(timing, sin I/O)'

    def __init__(self, n=20):
        self.n = n
        self.ent = {}   # id -> dict

    def registrar_activacion(self, t, sub_df, extra):
        rec = sub_df.iloc[-self.n:]
        hi, lo = float(rec['high'].max()), float(rec['low'].min())
        rng = hi - lo
        e = t['entry_price']
        frac = None
        if rng > 0:
            frac = (hi - e) / rng if t['type'] == 'SHORT' else (e - lo) / rng
        e200 = sub_df['EMA_200'].iloc[-1]
        overext = abs(e - e200) / e200 * 100 if (e200 and not pd.isna(e200)) else None
        self.ent[t['id']] = {'type': t['type'], 'pattern': t['pattern'],
                             'frac_done': frac, 'overext': overext}

    def registrar_vela(self, *a, **k):
        pass

    def registrar_cierre(self, t):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candles', type=int, default=3000)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--n', type=int, default=20, help='ventana de velas para el rango reciente')
    args = ap.parse_args()
    end_ms = int(pd.Timestamp(args.end).timestamp() * 1000) if args.end else None

    bt = BacktestV25(args.candles, end_time_ms=end_ms)
    bt.forense = ColectorTiming(args.n)
    bt.cargar_datos()
    bt.correr()

    col = bt.forense
    rows = []
    for t in bt.trades:
        if t['status'] != 'CERRADA':
            continue
        e = col.ent.get(t['id'])
        if not e or e['frac_done'] is None:
            continue
        peak = t.get('peak_progress', 0.0)
        if t['exit_reason'].startswith('OBJETIVO'):
            peak = max(peak, 100.0)
        rows.append({**e, 'peak': peak, 'pnl': t['pnl'],
                     'gana': 1 if t['pnl'] > 0 else 0})
    df = pd.DataFrame(rows)
    n = len(df)
    print(f"\n{'='*68}\n¿V28 ENTRA TARDE? — {n} entradas | ventana rango={args.n} velas")
    print(f"frac_done: 1.0 = entró al final del movimiento (TARDE), 0.0 = al inicio (temprano)")
    print('='*68)
    if n < 30:
        print("muestra chica"); return
    print(f"\nfrac_done medio: {df['frac_done'].mean():.2f} | mediana: {df['frac_done'].median():.2f}")
    print(f"sobre-extensión vs EMA200 media al entrar: {df['overext'].mean():.2f}%")

    print(f"\n--- por tercil de 'qué tan tarde' entró ---")
    df['banda'] = pd.cut(df['frac_done'], [-0.01, 0.33, 0.67, 10],
                         labels=['TEMPRANO (0-0.33)', 'MEDIO (0.33-0.67)', 'TARDE (0.67+)'])
    for b, g in df.groupby('banda', observed=True):
        print(f"  {b:20} n={len(g):4} ({len(g)/n*100:4.0f}%) | WR {g['gana'].mean()*100:5.1f}% | "
              f"peak medio {g['peak'].mean():5.1f}% | PnL medio ${g['pnl'].mean():+.2f}")

    # ¿qué fracción entró 'tarde' (>0.67)?
    tarde = (df['frac_done'] > 0.67).mean() * 100
    temprano = (df['frac_done'] < 0.33).mean() * 100
    print(f"\nResumen: {tarde:.0f}% de las entradas fueron TARDÍAS (>0.67), {temprano:.0f}% tempranas (<0.33)")
    # correlación frac_done vs resultado
    print(f"correlación frac_done↔PnL: {df['frac_done'].corr(df['pnl']):+.3f} "
          f"(negativa = entrar tarde rinde peor)")
    print(f"correlación frac_done↔peak: {df['frac_done'].corr(df['peak']):+.3f}")


if __name__ == '__main__':
    main()
