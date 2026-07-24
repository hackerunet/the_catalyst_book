"""
vol_debil.py — Tarea: ¿el "volumen debilitándose" predice que el avance se devuelve?

Hipótesis del usuario (2026-06-25): con una posición en ganancia, si la vela en
la dirección del trade tiene volumen que NO supera al de la vela anterior, el
movimiento se debilita → más chance de reverso/giveback.

Mide, sobre estados open-trade EN GANANCIA (prog>=FLOOR) del motor real (1h,
patrones, copilot, 3 años), la tasa de reverso real (prog cae >=DROP en <=H velas
o STOP) condicionada a varios flags de volumen, y la compara con la tasa base.
NO toca nada en vivo.

Uso: python3 vol_debil.py [--floor 20] [--drop 20] [--horizon 6]
"""
import argparse
import pickle
import os

import numpy as np
import pandas as pd

import config
import estrategia
from indicadores import calcular_indicadores
from backtest import BacktestV25
from walkforward import ForenseNulo


class Col:
    dir = '(vol, sin I/O)'

    def __init__(self):
        self.series = {}   # id -> [(ts, prog)]
        self.meta = {}

    def registrar_activacion(self, t, sub_df, extra):
        self.meta[t['id']] = {'symbol': t['symbol'], 'type': t['type']}

    def registrar_vela(self, t, vela, prob):
        self.series.setdefault(t['id'], []).append(
            (vela['time'], estrategia.calcular_progreso(t, vela['close'])))

    def registrar_cierre(self, t):
        m = self.meta.setdefault(t['id'], {})
        m['exit_time'] = t.get('exit_time')
        m['exit_prog'] = estrategia.calcular_progreso(t, t['exit_price']) if t.get('exit_price') else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default='wf_cache_1h_26280_2026-06-20_0000.pkl')
    ap.add_argument('--floor', type=int, default=20)
    ap.add_argument('--drop', type=int, default=20)
    ap.add_argument('--horizon', type=int, default=6)
    args = ap.parse_args()

    with open(os.path.join(os.path.dirname(__file__), args.cache), 'rb') as f:
        raw = pickle.load(f)
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v28_vol_forense')
    bt.forense = Col()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    print("INFO: corriendo motor 3 años...")
    bt.correr()

    col = bt.forense
    idx = {s: {ts: i for i, ts in enumerate(d['time'])} for s, d in bt.dfs.items()}
    rows = []
    for tid, serie in col.series.items():
        m = col.meta.get(tid, {})
        sym, tipo = m.get('symbol'), m.get('type')
        if not sym:
            continue
        df = bt.dfs[sym]
        ext = serie + [(m.get('exit_time'), m.get('exit_prog'))]
        for k in range(len(serie) - 1):
            ts, prog = serie[k]
            if prog is None or prog < args.floor:
                continue
            i = idx[sym].get(ts)
            if i is None or i < 2:
                continue
            fut = [p for (_, p) in ext[k + 1:k + 1 + args.horizon] if p is not None]
            reverso = 1 if any(p <= prog - args.drop for p in fut) else 0
            r = df.iloc[i]; rp = df.iloc[i - 1]
            vol, volp = r['volume'], rp['volume']
            vma = r['Volume_MA']
            # vela en dirección del trade (continuación)
            if tipo == 'SHORT':
                cont = r['close'] < r['open']
            else:
                cont = r['close'] > r['open']
            rows.append({
                'reverso': reverso,
                'vol_decline': 1 if vol < volp else 0,                      # vol < vela anterior
                'vol_below_ma': 1 if (vma and not pd.isna(vma) and vol < vma) else 0,
                'cont_weak': 1 if (cont and vol < volp) else 0,             # continuación SIN confirmar volumen (hipótesis del usuario)
                'no_cont': 0 if cont else 1,                                # la vela ni siquiera va a favor
            })
    df = pd.DataFrame(rows)
    n = len(df); base = df['reverso'].mean() * 100
    print(f"\n{'='*64}\n{n} estados en ganancia (prog>={args.floor}) | tasa BASE de reverso = {base:.1f}%\n{'='*64}")
    for f, desc in [('vol_decline', 'volumen < vela anterior'),
                    ('cont_weak', 'continuación con volumen < anterior (HIPÓTESIS)'),
                    ('vol_below_ma', 'volumen < promedio (lo que ya usa el detector)'),
                    ('no_cont', 'la vela va EN CONTRA del trade')]:
        g1 = df[df[f] == 1]['reverso']; g0 = df[df[f] == 0]['reverso']
        if len(g1) and len(g0):
            p1, p0 = g1.mean() * 100, g0.mean() * 100
            print(f"\n  {desc}")
            print(f"    flag=SÍ (n={len(g1):5}): P(reverso)={p1:5.1f}%  | flag=NO (n={len(g0):5}): {p0:5.1f}%  | spread {p1-p0:+5.1f}pp")


if __name__ == '__main__':
    main()
