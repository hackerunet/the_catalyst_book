#!/usr/bin/env python3
"""S6 · FASE D (diagnóstico, info-only) — Cumulative Delta (order-flow): ¿la divergencia
del CVD distingue el techo FINAL de los INTERMEDIOS?

CVD = suma acumulada del delta por vela (taker_buy − taker_sell = 2·taker_buy − volume).
Es el ÚNICO dato genuinamente distinto del volumen agregado: mide si el nuevo máximo lo
hacen COMPRADORES agresivos (delta+) o es absorción de vendedores (delta−, precio sube
mientras el flujo agresivo neto es de venta = distribución).

Señales causales:
  - cvd_div: precio hace nuevo máximo pero el CVD (en dirección del trade) NO → divergencia
  - delta_neg: la vela del nuevo máximo tiene delta CONTRA la dirección (absorción)
  - delta_cae: el delta de la vela es menor que el de la previa (flujo agresivo debilitándose)

Mismo test que S1/S2/S4: P(techo final | señal) vs el prior. Usa el cache de delta
(descargar_delta.py) alineado por timestamp al cache OHLCV. SOLO LECTURA.
"""
import argparse
import pickle
import os

import numpy as np

from suavizado_v37 import correr, CFG_V26, CACHE_4H_ORIG, CACHE_4H_OOB, DIR

DELTA_ORIG = 'delta_cache_4h_orig.pkl'
DELTA_OOB = 'delta_cache_4h_oob.pkl'


def prog(px, e, tp):
    return (px - e) / (tp - e) * 100.0


def diag(nombre, cache, delta_file, syms=None, min_peak=50.0):
    bt = correr(cache, dict(CFG_V26), symbols=syms)
    dft = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in dft.items()}
    dcache = pickle.load(open(os.path.join(DIR, delta_file), 'rb'))
    # CVD y delta por símbolo, alineados por POSICIÓN (mismo cache/orden); se verifica el time.
    cvd = {}; delta = {}
    for s in dft:
        dd = dcache[s]
        assert np.array_equal(dd['time'].values, dft[s]['time'].values), f"desalineado {s}"
        da = dd['delta'].values.astype(float)
        delta[s] = da
        cvd[s] = np.cumsum(np.nan_to_num(da))
    ganadores = [t for t in bt.trades if t['status'] == 'CERRADA' and t['pnl'] > 0]

    final, inter = [], []
    n_trades = 0
    for t in ganadores:
        s = t['symbol']; e = t['entry_price']; tp = t['tp']; side = t['type']
        i0 = int(np.searchsorted(tarr[s], np.datetime64(t['entry_time'])))
        i1 = int(np.searchsorted(tarr[s], np.datetime64(t['exit_time']))) + 1
        d = dft[s]
        if i1 - i0 < 3:
            continue
        hi = d['high'].values; lo = d['low'].values
        cv = cvd[s]; de = delta[s]
        fav = prog(hi[i0:i1], e, tp) if side == 'LONG' else prog(lo[i0:i1], e, tp)
        if float(np.max(fav)) < min_peak:
            continue
        n_trades += 1
        sign = 1.0 if side == 'LONG' else -1.0
        run = -1e18; cvd_run = -1e18
        for kk in range(len(fav)):
            i = i0 + kk
            if kk >= 2 and fav[kk] > run + 1e-9:
                sube_mas = bool(np.any(fav[kk + 1:] > fav[kk] + 1e-9))
                rec = dict(
                    cvd_div=(sign * cv[i]) < cvd_run,           # CVD no confirma el nuevo máximo
                    delta_neg=(sign * de[i]) < 0,               # nuevo máximo hecho con delta en contra
                    delta_cae=(sign * de[i]) < (sign * de[i - 1]),  # flujo agresivo debilitándose
                )
                (inter if sube_mas else final).append(rec)
            run = max(run, fav[kk])
            cvd_run = max(cvd_run, sign * cv[i])

    def tasa(lst, k):
        return sum(r[k] for r in lst) / len(lst) * 100 if lst else 0.0

    base = len(final) / (len(final) + len(inter)) * 100 if (final or inter) else 0
    print(f"\n{'=' * 82}")
    print(f"  S6 diagnóstico (Cumulative Delta) — {nombre}  ·  {n_trades} ganadores (pico ≥ {min_peak:.0f}%)")
    print(f"  {len(final)} techos FINALES vs {len(inter)} INTERMEDIOS · prior P(final) = {base:.1f}%")
    print(f"{'=' * 82}")
    print(f"  {'señal':12} {'@ FINAL':>9} {'@ INTER':>9} {'spread':>8} {'P(final|señal)':>14} {'vs prior':>9}")
    print(f"  {'-'*12} {'-'*9} {'-'*9} {'-'*8} {'-'*14} {'-'*9}")
    for k in ('cvd_div', 'delta_neg', 'delta_cae'):
        nf = sum(r[k] for r in final); ni = sum(r[k] for r in inter)
        rf, ri = tasa(final, k), tasa(inter, k)
        prec = nf / (nf + ni) * 100 if (nf + ni) else 0
        liftp = prec / base if base > 0 else float('inf')
        marca = "  ← INVERTIDA" if rf < ri - 2 else ""
        print(f"  {k:12} {rf:>8.0f}% {ri:>8.0f}% {rf-ri:>+7.0f}pp {prec:>13.1f}% {liftp:>8.2f}×{marca}")
    print(f"\n  Útil solo si P(final|señal) ≥ ~2× prior ({base:.1f}%). El delta es el dato más")
    print(f"  direccional que tenemos — si ni él discrimina, la pared es definitiva.")
    return final, inter


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-peak', type=float, default=50.0)
    a = ap.parse_args()
    print("### CANASTA ORIGINAL (in-sample) ###")
    diag("original", CACHE_4H_ORIG, DELTA_ORIG, None, a.min_peak)
    print("\n### CANASTA OOB ###")
    diag("OOB", CACHE_4H_OOB, DELTA_OOB,
         ['BTCUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT'], a.min_peak)
