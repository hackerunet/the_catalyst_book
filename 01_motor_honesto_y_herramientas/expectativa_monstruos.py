#!/usr/bin/env python3
"""MOTOR PROBABILÍSTICO DE EXPECTATIVA DE MONSTRUOS.
Objetivo: dado el estado/señales al ENTRAR un trade, estimar la expectativa de
crecimiento (P(pico >= X | señales) y E[pico | señales]). ¿Se puede predecir qué
trade será monstruo desde la entrada, o la 'lotería de monstruos' NO depende de
señales observables (como falló V50 meta-labeling)?

Honestidad: validación FUERA DE MUESTRA (split temporal 70/30 + OOB por símbolo).
Un motor solo sirve si su predicción tiene poder OOS, no solo in-sample.
"""
import argparse, os
import numpy as np
from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    HAY_SK = True
except ImportError:
    HAY_SK = False

MONSTRUO = 300.0  # pico de avance favorable >= 300% = monstruo (bucket del edge)

def prog(px, e, tp): return (px - e) / (tp - e) * 100.0

def feats_entrada(d, i, side):
    """Señales en el candle de ENTRADA (dirección-normalizado). i = índice de entrada."""
    row = d.iloc[i]; sign = 1.0 if side == 'LONG' else -1.0
    c = row['close']
    ema21 = row['EMA_21'] if row['EMA_21'] == row['EMA_21'] else c
    ema50 = row['EMA_50'] if row['EMA_50'] == row['EMA_50'] else c
    ema200 = row['EMA_200'] if row['EMA_200'] == row['EMA_200'] else c
    bbU, bbL = row['BB_UPPER'], row['BB_LOWER']
    rng_bb = max(bbU - bbL, 1e-9)
    return {
        'rsi_dir': row['RSI'] if side == 'LONG' else 100 - row['RSI'],
        'adx': row['ADX'],
        'macd_dir': row['MACD_Hist'] * sign,
        'overext21': (c - ema21) / ema21 * 100 * sign,
        'overext50': (c - ema50) / ema50 * 100 * sign,
        'atr_pct': row['ATR'] / c * 100 if c else 0,
        'vol_ratio': row['volume'] / row['Volume_MA'] if row['Volume_MA'] > 0 else 1.0,
        'body_atr': row['Body'] / row['ATR'] if row['ATR'] > 0 else 0,
        'bb_pos': (c - bbL) / rng_bb,
        'trend_gap': (ema50 - ema200) / ema200 * 100 * sign,  # fuerza/alineación de tendencia
        'squeeze': 1.0 if row.get('Squeeze_On', False) else 0.0,
    }

def dataset(engine):
    cfg = dict(CFG_V26 if engine == 'v26' else CFG_V36)
    cache = CACHE_4H_ORIG if engine == 'v26' else CACHE_15M_4Y
    syms = None if engine == 'v26' else TOP4
    bt = correr(cache, cfg, symbols=syms)
    dft = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in dft.items()}
    X, peak, meta = [], [], []
    for t in bt.trades:
        if t['status'] != 'CERRADA': continue
        s = t['symbol']; e = t['entry_price']; tp = t['tp']; side = t['type']
        i0 = int(np.searchsorted(tarr[s], np.datetime64(t['entry_time'])))
        i1 = int(np.searchsorted(tarr[s], np.datetime64(t['exit_time']))) + 1
        d = dft[s]
        if i0 < 210 or i1 - i0 < 2: continue   # warmup (EMA200) + trade con camino
        hi = d['high'].values[i0:i1]; lo = d['low'].values[i0:i1]
        fav = prog(hi, e, tp) if side == 'LONG' else prog(lo, e, tp)
        pk = float(np.max(fav))
        f = feats_entrada(d, i0, side)
        if any(v != v for v in f.values()): continue  # sin NaN
        X.append(f); peak.append(pk)
        meta.append({'sym': s, 't': t['entry_time'], 'pnl': t['pnl']})
    return X, np.array(peak), meta

def reporte(engine):
    X, peak, meta = dataset(engine)
    n = len(X); keys = list(X[0].keys())
    Xm = np.array([[x[k] for k in keys] for x in X])
    ismon = (peak >= MONSTRUO).astype(int)
    base = ismon.mean()
    print(f"\n{'='*82}\n  {engine.upper()} — {n} trades. Expectativa de crecimiento (pico de avance favorable)\n{'='*82}")
    # 1) INCONDICIONAL
    print("  [1] Expectativa INCONDICIONAL (la 'lotería' base, sin mirar señales):")
    for thr in (100, 200, 300, 500, 1000):
        p = (peak >= thr).mean() * 100
        print(f"      P(pico >= {thr:>5}%) = {p:>5.1f}%")
    print(f"      E[pico] mediano = {np.median(peak):.0f}% | promedio = {peak.mean():.0f}% | tasa monstruo(≥{int(MONSTRUO)}%) = {base*100:.1f}%")
    # 2) CONDICIONAL por feature — split temporal 70/30 (OOS)
    orden = np.argsort([m['t'] for m in meta])
    Xo, peako, ismono = Xm[orden], peak[orden], ismon[orden]
    cut = int(n * 0.70)
    print(f"\n  [2] ¿Alguna señal de ENTRADA sube la prob de monstruo? (tercil sup vs inf)")
    print(f"      medido IN-SAMPLE (train, {cut}) y OOS (test, {n-cut}). Base OOS = {ismono[cut:].mean()*100:.1f}%")
    print(f"      {'señal':12} {'IS: tasa inf→sup':>22} {'OOS: tasa inf→sup':>22} {'¿holdea OOS?':>13}")
    filas = []
    for j, k in enumerate(keys):
        col_tr, mon_tr = Xo[:cut, j], ismono[:cut]
        col_te, mon_te = Xo[cut:, j], ismono[cut:]
        q1t, q3t = np.quantile(col_tr, [0.33, 0.67])
        q1e, q3e = np.quantile(col_te, [0.33, 0.67])
        inf_tr = mon_tr[col_tr <= q1t].mean() * 100; sup_tr = mon_tr[col_tr >= q3t].mean() * 100
        inf_te = mon_te[col_te <= q1e].mean() * 100; sup_te = mon_te[col_te >= q3e].mean() * 100
        # "holdea" si el signo del gradiente (sup>inf o sup<inf) coincide IS y OOS y es material OOS
        signo_ok = np.sign(sup_tr - inf_tr) == np.sign(sup_te - inf_te)
        material = abs(sup_te - inf_te) >= 5
        filas.append((k, inf_tr, sup_tr, inf_te, sup_te, signo_ok and material))
    for k, it, st, ie, se, ok in sorted(filas, key=lambda x: -abs(x[4]-x[3])):
        print(f"      {k:12} {it:>8.1f}%→{st:<6.1f}% {ie:>10.1f}%→{se:<6.1f}% {'SÍ' if ok else 'no':>13}")
    # 3) MOTOR combinado — logistic P(monstruo|señales), OOS
    if HAY_SK and ismono[:cut].sum() > 5 and ismono[cut:].sum() > 3:
        mu, sd = Xo[:cut].mean(0), Xo[:cut].std(0) + 1e-9
        clf = LogisticRegression(max_iter=1000, class_weight='balanced')
        clf.fit((Xo[:cut]-mu)/sd, ismono[:cut])
        p_te = clf.predict_proba((Xo[cut:]-mu)/sd)[:, 1]
        auc = roc_auc_score(ismono[cut:], p_te) if len(set(ismono[cut:])) > 1 else float('nan')
        # lift: tasa de monstruo en el quintil de mayor score vs menor (OOS)
        q = np.quantile(p_te, [0.2, 0.8])
        alto = ismono[cut:][p_te >= q[1]].mean() * 100
        bajo = ismono[cut:][p_te <= q[0]].mean() * 100
        print(f"\n  [3] MOTOR combinado (logistic P(monstruo|11 señales)) — OOS (test):")
        print(f"      AUC OOS = {auc:.3f}  (0.5 = azar; >0.6 = señal real)")
        print(f"      Tasa de monstruo: quintil-score ALTO {alto:.1f}%  vs  BAJO {bajo:.1f}%  (base {ismono[cut:].mean()*100:.1f}%)")
        print(f"      Peso por señal (|coef| estandarizado, top 5):")
        for k, w in sorted(zip(keys, clf.coef_[0]), key=lambda x: -abs(x[1]))[:5]:
            print(f"        {k:12} {w:+.2f}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--engine', required=True, choices=['v26', 'v36'])
    a = ap.parse_args(); reporte(a.engine)
