#!/usr/bin/env python3
"""S4 · FASE D (diagnóstico, info-only) — VSA / Wyckoff: ¿"no demand" o "stopping volume"
distinguen el techo FINAL de los INTERMEDIOS?

VSA (Volume Spread Analysis): relación entre volumen, spread (rango) y cierre.
- "no demand": subida (a favor) con volumen DECRECIENTE → sin convicción → debilidad.
- spread angosto: precio sube poco pese al esfuerzo → resultado vs esfuerzo bajo.
- "stopping volume": volumen climático + spread angosto → absorción, freno del movimiento.

Prior NEGATIVO declarado: vol_debil.py ya halló que la relación "volumen bajo = más
reversa" está INVERTIDA (bajo volumen → MENOS reversa). Este test lo cierra formalmente
en el contexto de SALIDA (techo final vs intermedio). SOLO LECTURA, no toca el motor.
"""
import argparse

import numpy as np

from suavizado_v37 import correr, CFG_V26, CACHE_4H_ORIG


def prog(px, e, tp):
    return (px - e) / (tp - e) * 100.0


def diag(nombre, cache, syms=None, min_peak=50.0):
    bt = correr(cache, dict(CFG_V26), symbols=syms)
    dft = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in dft.items()}
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
        op = d['open'].values; cl = d['close'].values
        vol = d['volume'].values; vma = d['Volume_MA'].values; atr = d['ATR'].values
        fav = prog(hi[i0:i1], e, tp) if side == 'LONG' else prog(lo[i0:i1], e, tp)
        if float(np.max(fav)) < min_peak:
            continue
        n_trades += 1
        for kk in range(len(fav)):
            i = i0 + kk
            if kk >= 2 and fav[kk] > np.max(fav[:kk]) + 1e-9:
                sube_mas = bool(np.any(fav[kk + 1:] > fav[kk] + 1e-9))
                rng = max(hi[i] - lo[i], 1e-9)
                volr = vol[i] / vma[i] if vma[i] == vma[i] and vma[i] > 0 else 1.0
                spread_atr = rng / atr[i] if atr[i] == atr[i] and atr[i] > 0 else 1.0
                rec = dict(
                    no_demand=bool(vol[i] < vol[i - 1]),        # sube con volumen menor que la vela previa
                    vol_bajo_ma=bool(volr < 1.0),               # nuevo máximo con volumen bajo-promedio
                    spread_angosto=bool(spread_atr < 0.7),      # rango angosto (esfuerzo>resultado)
                    stopping_vol=bool(volr > 1.5 and spread_atr < 0.8),  # clímax + freno
                )
                (inter if sube_mas else final).append(rec)

    def tasa(lst, k):
        return sum(r[k] for r in lst) / len(lst) * 100 if lst else 0.0

    base = len(final) / (len(final) + len(inter)) * 100 if (final or inter) else 0
    print(f"\n{'=' * 82}")
    print(f"  S4 diagnóstico (VSA) — {nombre}  ·  {n_trades} ganadores (pico ≥ {min_peak:.0f}%)")
    print(f"  {len(final)} techos FINALES vs {len(inter)} INTERMEDIOS · prior P(final) = {base:.1f}%")
    print(f"{'=' * 82}")
    print(f"  {'señal':16} {'@ FINAL':>9} {'@ INTER':>9} {'spread':>8} {'P(final|señal)':>14} {'vs prior':>9}")
    print(f"  {'-'*16} {'-'*9} {'-'*9} {'-'*8} {'-'*14} {'-'*9}")
    for k in ('no_demand', 'vol_bajo_ma', 'spread_angosto', 'stopping_vol'):
        nf = sum(r[k] for r in final); ni = sum(r[k] for r in inter)
        rf, ri = tasa(final, k), tasa(inter, k)
        prec = nf / (nf + ni) * 100 if (nf + ni) else 0
        liftp = prec / base if base > 0 else float('inf')
        marca = "  ← INVERTIDA" if rf < ri - 2 else ""
        print(f"  {k:16} {rf:>8.0f}% {ri:>8.0f}% {rf-ri:>+7.0f}pp {prec:>13.1f}% {liftp:>8.2f}×{marca}")
    print(f"\n  Útil solo si P(final|señal) ≥ ~2× prior ({base:.1f}%). 'INVERTIDA' = dispara MÁS")
    print(f"  en intermedios (confirmaría el hallazgo de vol_debil: bajo volumen ≠ reversa).")
    return final, inter


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-peak', type=float, default=50.0)
    a = ap.parse_args()
    print("### CANASTA ORIGINAL (in-sample) ###")
    diag("original", CACHE_4H_ORIG, None, a.min_peak)
