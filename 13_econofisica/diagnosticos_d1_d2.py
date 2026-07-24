#!/usr/bin/env python3
"""
D1/D2 — Diagnósticos de econofísica sobre NUESTROS datos (info-only, sin PnL).
Pre-registro: el libro sección V60-V67 (2026-07-09).

D1 — Colas de ley de potencia (Clauset-Shalizi-Newman 2009, SIAM Review):
     ajuste MLE del exponente de cola alpha con xmin elegido por mínima distancia
     Kolmogorov-Smirnov (el método correcto, NO regresión log-log visual).
     Referencia empírica: ley cúbica inversa alpha≈3 en equities
     (Gopikrishnan et al. 1999). Pregunta: ¿cripto es igual, más pesada o más liviana?

D2 — Stylized facts (Cont 2001, Quantitative Finance):
     (1) no-gaussianidad: exceso de curtosis >> 0
     (2) ausencia de autocorrelación lineal: ACF(r) ~ 0 desde lag 1
     (3) clustering de volatilidad: ACF(|r|) positiva y de decaimiento lento

Solo lee los caches del harness. No toca ningún motor ni bot vivo.
Uso:  python3 diagnosticos_d1_d2.py            (corre los 4 timeframes)
Salida: diagnosticos_d1_d2.txt + diagnosticos_d1_d2.json
"""
import json
import os
import pickle

import numpy as np

DIR_HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', 'stable_v25_prototype')
CACHES = {
    '15m': 'wf_cache_15m_140160_2026-06-11_top4.pkl',
    '1h':  'wf_cache_1h_26280_2026-06-11.pkl',
    '4h':  'wf_cache_4h_8760_2026-06-11.pkl',
    '1d':  'wf_cache_crypto_1d.pkl',
}


# ---------- D1: ley de potencia por MLE (Clauset-Shalizi-Newman) ----------
def alpha_mle(x, xmin):
    x = x[x >= xmin]
    n = len(x)
    if n < 20:
        return None, n
    return 1.0 + n / np.sum(np.log(x / xmin)), n


def ks_powerlaw(x, xmin, alpha):
    """Distancia KS entre CDF empírica de la cola y la ley de potencia ajustada."""
    x = np.sort(x[x >= xmin])
    n = len(x)
    cdf_emp = np.arange(1, n + 1) / n
    cdf_fit = 1.0 - (xmin / x) ** (alpha - 1.0)
    return np.max(np.abs(cdf_emp - cdf_fit))


def fit_tail(returns):
    """Ajuste CSN completo: escanea xmin sobre los cuantiles de la cola, elige el
    de mínima KS (esto NO es escaneo de hipótesis — es EL método del paper)."""
    x = np.abs(returns)
    x = x[x > 0]
    if len(x) < 500:
        return None
    candidatos = np.quantile(x, np.linspace(0.80, 0.995, 40))
    mejor = None
    for xmin in candidatos:
        a, n = alpha_mle(x, xmin)
        if a is None or n < 50:
            continue
        d = ks_powerlaw(x, xmin, a)
        if mejor is None or d < mejor['ks']:
            mejor = {'alpha': float(a), 'xmin': float(xmin), 'n_cola': int(n), 'ks': float(d)}
    return mejor


# ---------- D2: stylized facts (Cont 2001) ----------
def acf(x, lags):
    x = x - x.mean()
    var = np.dot(x, x) / len(x)
    if var == 0:
        return [0.0] * len(lags)
    return [float(np.dot(x[:-k], x[k:]) / len(x) / var) for k in lags]


def stylized(returns):
    r = returns[np.isfinite(returns)]
    n = len(r)
    m, s = r.mean(), r.std()
    kurt_exceso = float(np.mean(((r - m) / s) ** 4) - 3.0) if s > 0 else None
    banda = 2.0 / np.sqrt(n)  # banda de significancia ~95% para ACF de ruido blanco
    acf_r = acf(r, [1, 2, 3, 5, 10])
    acf_abs = acf(np.abs(r), [1, 5, 10, 20, 50, 100])
    return {
        'n': int(n),
        'curtosis_exceso': kurt_exceso,          # gaussiana = 0
        'acf_retornos_lags_1_2_3_5_10': [round(v, 4) for v in acf_r],
        'acf_abs_lags_1_5_10_20_50_100': [round(v, 4) for v in acf_abs],
        'banda_ruido_2sigma': round(float(banda), 4),
        'clustering_volatilidad': bool(all(v > banda for v in acf_abs[:4])),
        'sin_autocorr_lineal': bool(all(abs(v) < 3 * banda for v in acf_r)),
    }


def main():
    out = {}
    lineas = ["=" * 78,
              "D1/D2 — ECONOFÍSICA EN NUESTROS DATOS (info-only) — " +
              "pre-registro el libro V60-V67",
              "=" * 78]
    for tf, fname in CACHES.items():
        path = os.path.join(DIR_HARNESS, fname)
        if not os.path.exists(path):
            lineas.append(f"[{tf}] cache no encontrado: {fname} — SALTADO")
            continue
        with open(path, 'rb') as f:
            data = pickle.load(f)
        out[tf] = {}
        lineas.append(f"\n### Timeframe {tf} ({fname})")
        pool = []
        for sym, df in data.items():
            c = df['close'].astype(float).values
            r = np.diff(np.log(c))
            r = r[np.isfinite(r)]
            pool.append(r)
            tail = fit_tail(r)
            sty = stylized(r)
            out[tf][sym] = {'D1_cola': tail, 'D2_stylized': sty}
            a = f"{tail['alpha']:.2f} (n_cola={tail['n_cola']})" if tail else "n/d"
            lineas.append(
                f"  {sym:<10} alpha={a:<22} curtosis_exceso={sty['curtosis_exceso']:.1f}  "
                f"clustering_vol={'SÍ' if sty['clustering_volatilidad'] else 'no'}  "
                f"sin_autocorr_lineal={'SÍ' if sty['sin_autocorr_lineal'] else 'NO'}")
        # pool agregado del timeframe
        rp = np.concatenate(pool)
        tail_p = fit_tail(rp)
        sty_p = stylized(rp)
        out[tf]['_POOL'] = {'D1_cola': tail_p, 'D2_stylized': sty_p}
        if tail_p:
            lineas.append(f"  {'POOL':<10} alpha={tail_p['alpha']:.2f} "
                          f"(n_cola={tail_p['n_cola']}, xmin={tail_p['xmin']:.4f}, "
                          f"KS={tail_p['ks']:.3f})  curtosis={sty_p['curtosis_exceso']:.1f}")
    lineas.append("\nLectura de referencia: equities alpha≈3 (ley cúbica inversa); "
                  "gaussiana: curtosis_exceso=0, sin clustering.")
    txt = "\n".join(lineas)
    print(txt)
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, 'diagnosticos_d1_d2.txt'), 'w') as f:
        f.write(txt + "\n")
    with open(os.path.join(base, 'diagnosticos_d1_d2.json'), 'w') as f:
        json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
