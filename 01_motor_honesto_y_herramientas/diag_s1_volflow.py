#!/usr/bin/env python3
"""S1 · FASE D (diagnóstico, info-only) — ¿la divergencia de VOLUMEN-FLUJO distingue
el techo FINAL de un ganador de los techos INTERMEDIOS?

Pregunta afilada (la que V58/clímax NO pudo responder): en cada vela donde un ganador
hace un NUEVO MÁXIMO de avance (el momento real de decidir "¿salgo o sigue?"), ¿la señal
de flujo (OBV/AD/CMF sin confirmar / distribución) dispara MÁS cuando ese máximo es el
FINAL (no viene un máximo mayor) que cuando es INTERMEDIO (viene uno mayor después)?

- Señal causal (solo pasado): OBV/AD/CMF de la vela actual.
- Etiqueta con futuro (legítimo en un DIAGNÓSTICO): ¿hay un máximo mayor después, dentro
  del trade? Igual que picos_monstruos usa argmax. Mide poder discriminante en hindsight.

Si NO separa (dispara igual en finales e intermedios) → como RSI/BB en el clímax, inútil
como salida → S1 se rechaza en Fase D, no se construye. SOLO LECTURA, no toca el motor.
"""
import argparse

import numpy as np
import pandas as pd

from suavizado_v37 import correr, CFG_V26, CACHE_4H_ORIG, CACHE_4H_OOB


def flujo_cols(d):
    """OBV, A/D y CMF(20) — todos CAUSALES (cumsum / rolling sobre pasado+actual)."""
    close = d['close'].values.astype(float)
    vol = d['volume'].values.astype(float)
    h = d['high'].values.astype(float)
    l = d['low'].values.astype(float)
    # OBV: suma acumulada de volumen firmado por la dirección del cierre
    obv = np.zeros(len(d))
    if len(d) > 1:
        obv[1:] = np.cumsum(np.sign(np.diff(close)) * vol[1:])
    # A/D: money-flow-multiplier × volumen, acumulado
    rng = np.maximum(h - l, 1e-9)
    mfm = ((close - l) - (h - close)) / rng          # [-1, 1]
    mfv = mfm * vol
    ad = np.cumsum(mfv)
    # CMF(20): flujo neto / volumen, ventana 20 (acotado [-1,1])
    mfv_s = pd.Series(mfv)
    vol_s = pd.Series(vol)
    cmf = (mfv_s.rolling(20).sum() / vol_s.rolling(20).sum().replace(0, np.nan)).values
    return obv, ad, cmf


def prog(px, e, tp):
    return (px - e) / (tp - e) * 100.0


def diag(nombre, cache, syms=None, min_peak=50.0):
    bt = correr(cache, dict(CFG_V26), symbols=syms)
    dft = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in dft.items()}
    flujo = {s: flujo_cols(d) for s, d in dft.items()}
    ganadores = [t for t in bt.trades if t['status'] == 'CERRADA' and t['pnl'] > 0]

    final, inter = [], []          # registros de señales en cada vela de nuevo-máximo
    n_trades = 0
    for t in ganadores:
        s = t['symbol']; e = t['entry_price']; tp = t['tp']; side = t['type']
        i0 = int(np.searchsorted(tarr[s], np.datetime64(t['entry_time'])))
        i1 = int(np.searchsorted(tarr[s], np.datetime64(t['exit_time']))) + 1
        d = dft[s]
        if i1 - i0 < 3:
            continue
        obv, ad, cmf = flujo[s]
        hi = d['high'].values; lo = d['low'].values
        fav = prog(hi[i0:i1], e, tp) if side == 'LONG' else prog(lo[i0:i1], e, tp)
        if float(np.max(fav)) < min_peak:
            continue
        n_trades += 1
        sign = 1.0 if side == 'LONG' else -1.0
        run = -1e18; obv_run = -1e18; ad_run = -1e18
        for kk in range(len(fav)):
            i = i0 + kk
            es_nuevo_max = kk >= 2 and fav[kk] > run + 1e-9
            if es_nuevo_max:
                # etiqueta: ¿viene un máximo MAYOR después (dentro del trade)?
                sube_mas = bool(np.any(fav[kk + 1:] > fav[kk] + 1e-9))
                cmf_i = cmf[i] * sign if cmf[i] == cmf[i] else np.nan
                rec = dict(
                    # OBV/AD NO confirman el nuevo máximo de precio (divergencia bajista)
                    obv_div=(sign * obv[i]) < obv_run,
                    ad_div=(sign * ad[i]) < ad_run,
                    # CMF (en dirección del trade) muestra distribución
                    cmf_neg=bool(cmf_i < 0) if cmf_i == cmf_i else False,
                    cmf_debil=bool(cmf_i < 0.05) if cmf_i == cmf_i else False,
                    progreso=fav[kk],
                )
                (inter if sube_mas else final).append(rec)
            run = max(run, fav[kk])
            obv_run = max(obv_run, sign * obv[i])
            ad_run = max(ad_run, sign * ad[i])

    def tasa(lst, k):
        return sum(r[k] for r in lst) / len(lst) * 100 if lst else 0.0

    print(f"\n{'=' * 82}")
    print(f"  S1 diagnóstico — {nombre}  ·  {n_trades} ganadores (pico ≥ {min_peak:.0f}%)")
    print(f"  velas de NUEVO MÁXIMO: {len(final)} FINALES  vs  {len(inter)} INTERMEDIAS")
    print(f"{'=' * 82}")
    # base: ¿qué fracción de las velas de nuevo-máximo son FINALES? (prior a vencer)
    base = len(final) / (len(final) + len(inter)) * 100 if (final or inter) else 0
    print(f"  Prior: solo el {base:.1f}% de las velas de nuevo-máximo SON el techo final")
    print(f"  (un ganador tiene ~{len(inter)//max(n_trades,1)} nuevos máximos antes del último).")
    print(f"  La pregunta real de salida: si la señal DISPARA, ¿qué prob. de ser el techo final?")
    print(f"\n  {'señal de flujo':14} {'@ FINAL':>9} {'@ INTER':>9} {'spread':>8} "
          f"{'P(final|señal)':>14} {'vs prior':>9}")
    print(f"  {'-'*14} {'-'*9} {'-'*9} {'-'*8} {'-'*14} {'-'*9}")
    for k in ('obv_div', 'ad_div', 'cmf_neg', 'cmf_debil'):
        nf = sum(r[k] for r in final)
        ni = sum(r[k] for r in inter)
        rf, ri = tasa(final, k), tasa(inter, k)
        prec = nf / (nf + ni) * 100 if (nf + ni) else 0     # P(techo final | señal dispara)
        liftp = prec / base if base > 0 else float('inf')
        print(f"  {k:14} {rf:>8.0f}% {ri:>8.0f}% {rf-ri:>+7.0f}pp {prec:>13.1f}% "
              f"{liftp:>8.2f}×")
    print(f"\n  Lo que importa NO es el spread: es P(final|señal) muy por encima del prior "
          f"({base:.1f}%).")
    print(f"  Si al dispararse la señal la prob. de ser el techo real apenas sube del prior,")
    print(f"  salir ahí corta ~el mismo % de monstruos que de techos reales (Ley 01).")
    print(f"  Umbral de interés HONESTO: P(final|señal) ≥ 2× el prior Y con recall razonable.")
    return final, inter


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-peak', type=float, default=50.0)
    a = ap.parse_args()
    print("### CANASTA ORIGINAL (in-sample) ###")
    diag("original", CACHE_4H_ORIG, None, a.min_peak)
    # también sobre los monstruos grandes (donde vive el edge)
    print("\n### solo MONSTRUOS (pico ≥ 200%) — canasta original ###")
    diag("original · monstruos", CACHE_4H_ORIG, None, 200.0)
