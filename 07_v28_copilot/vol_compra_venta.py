"""
vol_compra_venta.py — Tarea 2026-07-01: ¿el desbalance de volumen COMPRA vs
VENTA (taker buy/sell, no solo magnitud vs promedio) añade señal al detector
de reverso ya calibrado, tal como propuso el usuario ("si prob_reversion>=30%
Y volumen de venta > volumen de compra, considerar cerrar")?

Distinto de vol_debil.py (2026-06-25, YA RECHAZADO): ese test usó volumen TOTAL
vs su propia media/vela anterior (magnitud). Este usa el desbalance
DIRECCIONAL taker_buy_base_asset_volume vs total — un feature que el detector
calibrado NO tiene (solo tiene vol_ratio = volumen total/MA). Requiere
re-descargar klines con la columna taker-buy (el cache .pkl la descarta).

Mide, sobre estados open-trade EN GANANCIA (prog>=floor) del motor real (1h,
patrones, copilot calibrado), la tasa de reverso real condicionada a
sell_ratio (1 - taker_buy/total) en la vela actual, tanto marginal como
específicamente dentro del grupo que YA dispara alerta (prob_calibrada>=30),
que es la propuesta exacta del usuario.

Uso: python3 vol_compra_venta.py [--years 2] [--floor 20] [--drop 20] [--horizon 6]
"""
import argparse
import time
import requests
import pandas as pd
import numpy as np

import config
import estrategia
from indicadores import calcular_indicadores
from backtest import BacktestV25


def fetch_con_taker(symbol, total, interval='1h'):
    rows = []
    end_time = None
    while len(rows) < total:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit=1000"
        if end_time:
            url += f"&endTime={end_time}"
        r = requests.get(url, timeout=15).json()
        if not r or (isinstance(r, dict) and 'code' in r):
            break
        rows = r + rows
        end_time = r[0][0] - 1
        if len(r) < 1000:
            break
        time.sleep(0.15)
    rows = rows[-total:]
    df = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume',
                                     'ct', 'qav', 'n', 'tb', 'tq', 'ig'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    for c in ('open', 'high', 'low', 'close', 'volume', 'tb'):
        df[c] = df[c].astype(float)
    df['sell_ratio'] = 1.0 - (df['tb'] / df['volume'].replace(0, np.nan))
    return df[['time', 'open', 'high', 'low', 'close', 'volume', 'sell_ratio']]


class Col:
    dir = '(vol_compra_venta, sin I/O)'

    def __init__(self):
        self.series = {}
        self.meta = {}

    def registrar_activacion(self, t, sub_df, extra):
        self.meta[t['id']] = {'symbol': t['symbol'], 'type': t['type']}

    def registrar_vela(self, t, vela, prob):
        self.series.setdefault(t['id'], []).append(
            (vela['time'], estrategia.calcular_progreso(t, vela['close']), prob))

    def registrar_cierre(self, t):
        m = self.meta.setdefault(t['id'], {})
        m['exit_time'] = t.get('exit_time')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=float, default=2.0)
    ap.add_argument('--floor', type=int, default=20)
    ap.add_argument('--drop', type=int, default=20)
    ap.add_argument('--horizon', type=int, default=6)
    args = ap.parse_args()

    config.DETECTOR_CALIBRADO = True
    config.AUTO_CIERRE_REVERSA = False  # solo medir, no tocar el motor de decisión

    total = int(args.years * 365 * 24)
    dfs_raw = {}
    for sym in config.SYMBOLS:
        print(f"INFO: descargando {total} velas 1h de {sym} (con taker-buy)...")
        dfs_raw[sym] = fetch_con_taker(sym, total)

    bt = BacktestV25(candles=total, forense_dir='/tmp/v28_volcv_forense')
    bt.forense = Col()
    bt.dfs = {s: calcular_indicadores(d) for s, d in dfs_raw.items()}
    print("INFO: corriendo motor...")
    bt.correr()

    col = bt.forense
    idx = {s: {ts: i for i, ts in enumerate(d['time'])} for s, d in bt.dfs.items()}
    rows = []
    for tid, serie in col.series.items():
        m = col.meta.get(tid, {})
        sym = m.get('symbol')
        if not sym:
            continue
        df = bt.dfs[sym]
        for k in range(len(serie) - 1):
            ts, prog, prob = serie[k]
            if prog is None or prog < args.floor:
                continue
            i = idx[sym].get(ts)
            if i is None:
                continue
            fut = [p for (_, p, _) in serie[k + 1:k + 1 + args.horizon] if p is not None]
            reverso = 1 if any(p <= prog - args.drop for p in fut) else 0
            sell_ratio = df['sell_ratio'].iloc[i]
            if pd.isna(sell_ratio):
                continue
            rows.append({'reverso': reverso, 'prob_calibrada': prob,
                        'sell_ratio': sell_ratio, 'sell_mayor': 1 if sell_ratio > 0.5 else 0})
    d = pd.DataFrame(rows)
    n = len(d)
    base = d['reverso'].mean() * 100
    print(f"\n{'='*70}\n{n} estados en ganancia (prog>={args.floor}) | tasa BASE reverso = {base:.1f}%\n{'='*70}")

    print("\n-- Marginal: sell_ratio > 50% (venta domina la vela) --")
    g1 = d[d['sell_mayor'] == 1]['reverso']; g0 = d[d['sell_mayor'] == 0]['reverso']
    print(f"  venta>compra (n={len(g1)}): P(reverso)={g1.mean()*100:.1f}%  | "
          f"compra>=venta (n={len(g0)}): P(reverso)={g0.mean()*100:.1f}%  | spread {(g1.mean()-g0.mean())*100:+.1f}pp")

    print("\n-- PROPUESTA EXACTA DEL USUARIO: dentro de prob_calibrada>=30 (ya dispara alerta) --")
    sub = d[d['prob_calibrada'] >= 30]
    print(f"  n en esta zona: {len(sub)} | tasa de reverso ya (sin filtro de volumen): {sub['reverso'].mean()*100:.1f}%")
    g1 = sub[sub['sell_mayor'] == 1]['reverso']; g0 = sub[sub['sell_mayor'] == 0]['reverso']
    if len(g1) and len(g0):
        print(f"  + venta>compra (n={len(g1)}): P(reverso)={g1.mean()*100:.1f}%  | "
              f"+ compra>=venta (n={len(g0)}): P(reverso)={g0.mean()*100:.1f}%  | spread {(g1.mean()-g0.mean())*100:+.1f}pp")

    print("\n-- Umbral 40 (el techo real observado en la calibración) vs 30 (propuesta del usuario) --")
    for umbral in (25, 30, 35, 40):
        s = d[d['prob_calibrada'] >= umbral]
        print(f"  prob>={umbral}: n={len(s):5} | P(reverso)={s['reverso'].mean()*100 if len(s) else float('nan'):5.1f}% "
              f"| falsas alarmas (no revierte)={100-s['reverso'].mean()*100 if len(s) else float('nan'):5.1f}%")


if __name__ == '__main__':
    main()
