#!/usr/bin/env python3
"""S2 · FASE D (diagnóstico, info-only) — ¿la sobre-extensión sobre el ÁREA DE VALOR
(Volume Profile) distingue el techo FINAL de los INTERMEDIOS?

Teoría (zonas de valor / market profile): el precio gravita al área de valor (donde se
negoció el 70% del volumen); alejarse mucho de ella = sobre-extensión que revierte. La
salida: cerrar cuando el precio está demasiado lejos POR ENCIMA del VAH (value-area high).

Área de valor CAUSAL: histograma volumen-por-precio de las últimas N velas ANTES de la
actual (stride para abaratar, forward-fill — el área se mueve lento). Mismo test afilado
que S1: ¿la señal dispara MÁS en el techo final que en los intermedios? P(final|señal) vs
prior. SOLO LECTURA, no toca el motor.
"""
import argparse

import numpy as np

from suavizado_v37 import correr, CFG_V26, CACHE_4H_ORIG


def value_area(d, N=120, B=40, stride=6):
    """POC / VAH / VAL causales sobre ventana móvil de N velas (volumen por precio típico)."""
    tp = ((d['high'] + d['low'] + d['close']) / 3).values.astype(float)
    vol = d['volume'].values.astype(float)
    n = len(d)
    poc = np.full(n, np.nan); vah = np.full(n, np.nan); val = np.full(n, np.nan)
    last = None
    for i in range(N, n):
        if last is not None and (i % stride) != 0:
            poc[i], vah[i], val[i] = last
            continue
        w_tp = tp[i - N:i]; w_v = vol[i - N:i]          # causal: velas ANTES de i
        lo, hi = w_tp.min(), w_tp.max()
        if hi <= lo:
            last = (tp[i - 1], tp[i - 1], tp[i - 1])
            poc[i], vah[i], val[i] = last
            continue
        edges = np.linspace(lo, hi, B + 1)
        idx = np.clip(np.digitize(w_tp, edges) - 1, 0, B - 1)
        hist = np.zeros(B)
        np.add.at(hist, idx, w_v)
        centers = (edges[:-1] + edges[1:]) / 2
        pidx = int(np.argmax(hist))
        total = hist.sum(); target = 0.7 * total
        lo_i = hi_i = pidx; acc = hist[pidx]
        while acc < target and (lo_i > 0 or hi_i < B - 1):
            down = hist[lo_i - 1] if lo_i > 0 else -1.0
            up = hist[hi_i + 1] if hi_i < B - 1 else -1.0
            if up >= down:
                hi_i += 1; acc += hist[hi_i]
            else:
                lo_i -= 1; acc += hist[lo_i]
        last = (centers[pidx], centers[hi_i], centers[lo_i])
        poc[i], vah[i], val[i] = last
    return poc, vah, val


def prog(px, e, tp):
    return (px - e) / (tp - e) * 100.0


def diag(nombre, cache, syms=None, min_peak=50.0):
    bt = correr(cache, dict(CFG_V26), symbols=syms)
    dft = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in dft.items()}
    va = {s: value_area(d) for s, d in dft.items()}
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
        poc, vah, val_ = va[s]
        hi = d['high'].values; lo = d['low'].values; cl = d['close'].values
        fav = prog(hi[i0:i1], e, tp) if side == 'LONG' else prog(lo[i0:i1], e, tp)
        if float(np.max(fav)) < min_peak:
            continue
        n_trades += 1
        sign = 1.0 if side == 'LONG' else -1.0
        run = -1e18
        for kk in range(len(fav)):
            i = i0 + kk
            if kk >= 2 and fav[kk] > run + 1e-9:
                sube_mas = bool(np.any(fav[kk + 1:] > fav[kk] + 1e-9))
                # borde del área de valor en la dirección del trade
                borde = vah[i] if side == 'LONG' else val_[i]
                ext = (cl[i] - borde) / borde * 100 * sign if borde == borde and borde > 0 else np.nan
                rec = dict(
                    ext_va_3=bool(ext > 3) if ext == ext else False,   # >3% fuera del área
                    ext_va_5=bool(ext > 5) if ext == ext else False,
                    ext_va_8=bool(ext > 8) if ext == ext else False,
                    # POC no sube (volumen no sigue al precio: el valor se queda atrás)
                    poc_estanca=bool((poc[i] * sign) <= (poc[i0 + kk - 2] * sign) + 1e-12)
                    if poc[i] == poc[i] else False,
                )
                (inter if sube_mas else final).append(rec)
            run = max(run, fav[kk])

    def tasa(lst, k):
        return sum(r[k] for r in lst) / len(lst) * 100 if lst else 0.0

    base = len(final) / (len(final) + len(inter)) * 100 if (final or inter) else 0
    print(f"\n{'=' * 82}")
    print(f"  S2 diagnóstico (Value Area) — {nombre}  ·  {n_trades} ganadores (pico ≥ {min_peak:.0f}%)")
    print(f"  {len(final)} techos FINALES vs {len(inter)} INTERMEDIOS · prior P(final) = {base:.1f}%")
    print(f"{'=' * 82}")
    print(f"  {'señal':14} {'@ FINAL':>9} {'@ INTER':>9} {'spread':>8} {'P(final|señal)':>14} {'vs prior':>9}")
    print(f"  {'-'*14} {'-'*9} {'-'*9} {'-'*8} {'-'*14} {'-'*9}")
    for k in ('ext_va_3', 'ext_va_5', 'ext_va_8', 'poc_estanca'):
        nf = sum(r[k] for r in final); ni = sum(r[k] for r in inter)
        rf, ri = tasa(final, k), tasa(inter, k)
        prec = nf / (nf + ni) * 100 if (nf + ni) else 0
        liftp = prec / base if base > 0 else float('inf')
        print(f"  {k:14} {rf:>8.0f}% {ri:>8.0f}% {rf-ri:>+7.0f}pp {prec:>13.1f}% {liftp:>8.2f}×")
    print(f"\n  Útil solo si P(final|señal) ≥ ~2× el prior ({base:.1f}%). Si no, corta monstruos.")
    return final, inter


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-peak', type=float, default=50.0)
    a = ap.parse_args()
    print("### CANASTA ORIGINAL (in-sample) ###")
    diag("original", CACHE_4H_ORIG, None, a.min_peak)
