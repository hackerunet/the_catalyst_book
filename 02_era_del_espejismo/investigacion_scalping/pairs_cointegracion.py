"""
pairs_cointegracion.py — Candidato #3 (investigación scalping, 2026-07-01):
pairs / market-neutral estadístico sobre el basket del proyecto
(ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, LINKUSDT).

Nunca construido en el proyecto (Test F, "clase pendiente genuina" per
PLAN_DE_PRUEBAS.md). Script AUTOCONTENIDO — no importa ni modifica ningún
archivo de v26_tendencia/, v28_copilot/ ni stable_v25_prototype/ (excepto
LEER el cache de klines ya descargado, de solo lectura). No usa
statsmodels/scipy (no instalados en el venv) — implementa a mano:
  - Regresión OLS (hedge ratio, vía numpy.linalg.lstsq)
  - Test ADF de 1 rezago sobre el spread (Engle-Granger paso 2), con
    t-estadístico calculado a mano (coef / std-error)
  - Half-life de reversión a la media (AR(1) tipo Ornstein-Uhlenbeck)
  - Backtest de z-score OUT-OF-SAMPLE (hedge ratio y mu/sigma del spread
    estimados SOLO en el período de formación, aplicados sin look-ahead al
    período de prueba) con costos reales de 2 patas (taker 0.05%+0.05%/lado
    cada pata, apertura+cierre — el peor caso honesto).

Metodología (pre-registrada, NO escaneada — todos los umbrales son
convención estándar de la literatura de pairs trading, no ajustados a estos
datos):
  - Formación = primer 60% de la serie (2023-06→2025-03 aprox.), Prueba =
    últimos 40% (fuera de muestra real, nunca visto por el hedge ratio).
  - Umbral de cointegración: t-ADF (1 rezago, con constante) < -2.86
    (crítico ADF univariado ~5%, aproximación conservadora — ver caveat
    abajo: el crítico correcto de Engle-Grangünger de 2 pasos es MÁS
    negativo, ~-3.3/-3.9, así que -2.86 es un piso permisivo, no estricto).
  - Half-life razonable para ser operable: 1h <= HL <= 30 días.
  - Entrada z-score: |z| >= 2.0 | Salida: |z| <= 0.5 | Stop de cola: |z| >= 4.0
    (salir a mercado, evita ruina si la relación se rompe estructuralmente).
  - Costos: taker 0.05% comisión + 0.05% slippage POR LADO POR PATA
    (idéntico a config.BT_TAKER_FEE/BT_SLIPPAGE del proyecto), 2 patas,
    apertura+cierre = 4x ese costo por ciclo completo sobre el notional de
    cada pata.

Criterio de "candidato con mérito" (para el reporte, NO un pre-registro
formal de despliegue): al menos 1 par con t-ADF < -2.86, half-life en rango,
Y PnL neto de costos POSITIVO en el período de prueba fuera de muestra.

Uso: python3 pairs_cointegracion.py
Salida: pairs_cointegracion_resultado.json + tabla por stdout.
"""
import itertools
import json
import os
import pickle

import numpy as np
import pandas as pd

CACHE = '/Users/hackerunet/openclaw-binance-trading/bot_alpha_portfolio/stable_v25_prototype/wf_cache_1h_26280_2026-06-11_0000.pkl'

FEE = 0.0005
SLIP = 0.0005
COSTO_LADO = FEE + SLIP          # 0.001 por lado por pata
ENTRY_Z = 2.0
EXIT_Z = 0.5
STOP_Z = 4.0
NOTIONAL_POR_PATA = 250.0         # ~ escala de una posición del proyecto (balance 500, 2 patas)
FORMACION_FRAC = 0.6


def cargar():
    with open(CACHE, 'rb') as f:
        raw = pickle.load(f)
    # alinear por timestamp común (inner join)
    dfs = {s: d.set_index('time')['close'].rename(s) for s, d in raw.items()}
    df = pd.concat(dfs.values(), axis=1, join='inner').dropna()
    return df


def ols_beta(y, x):
    """y = a + b*x + eps. Retorna (a, b, resid, se_b)."""
    X = np.column_stack([np.ones(len(x)), x])
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    a, b = coef
    resid = y - X @ coef
    n, k = X.shape
    sigma2 = float(resid @ resid) / (n - k)
    xtx_inv = np.linalg.inv(X.T @ X)
    se_b = float(np.sqrt(sigma2 * xtx_inv[1, 1]))
    return a, b, resid, se_b


def adf_1lag(spread):
    """ADF con 1 rezago y constante sobre `spread`. Retorna t-estadístico de
    la reversión (coeficiente de spread_{t-1} en la regresión de Δspread)."""
    s = np.asarray(spread)
    ds = np.diff(s)
    s_lag = s[:-1]
    ds_lag1 = np.diff(s)[:-1] if len(ds) > 1 else np.array([])
    # regresión: ds[1:] = c + gamma*s_lag[1:] + delta*ds_lag1 + eps
    y = ds[1:]
    X = np.column_stack([np.ones(len(y)), s_lag[1:], ds_lag1])
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    n, k = X.shape
    sigma2 = float(resid @ resid) / (n - k)
    xtx_inv = np.linalg.inv(X.T @ X)
    se_gamma = float(np.sqrt(sigma2 * xtx_inv[1, 1]))
    gamma = coef[1]
    t_stat = gamma / se_gamma if se_gamma > 0 else 0.0
    return float(t_stat), float(gamma)


def half_life(spread):
    s = np.asarray(spread)
    s_lag = s[:-1]
    ds = np.diff(s)
    X = np.column_stack([np.ones(len(s_lag)), s_lag])
    coef, _, _, _ = np.linalg.lstsq(X, ds, rcond=None)
    beta = coef[1]
    if beta >= 0:
        return None  # no reversión (spread es explosivo o random walk)
    return float(-np.log(2) / beta)


def backtest_zscore(spread_test, mu, sigma, precio_a, precio_b, beta):
    """z-score mean reversion OOS. spread_test/precio_a/precio_b alineados
    por índice. Retorna dict con pnl neto, trades, wr."""
    z = (spread_test - mu) / sigma
    posicion = 0  # 0 plano, 1 = long spread (long A / short B*beta), -1 = short spread
    entry_a = entry_b = None
    trades = []
    for i in range(len(z)):
        zi = z.iloc[i]
        pa, pb = precio_a.iloc[i], precio_b.iloc[i]
        if posicion == 0:
            if zi >= ENTRY_Z:
                posicion = -1
                entry_a, entry_b = pa, pb
            elif zi <= -ENTRY_Z:
                posicion = 1
                entry_a, entry_b = pa, pb
        else:
            salir = abs(zi) <= EXIT_Z or abs(zi) >= STOP_Z
            if salir:
                qa = NOTIONAL_POR_PATA / entry_a
                qb = (NOTIONAL_POR_PATA * abs(beta)) / entry_b
                if posicion == 1:   # long A, short B
                    pnl_a = (pa - entry_a) * qa
                    pnl_b = (entry_b - pb) * qb
                else:               # short A, long B
                    pnl_a = (entry_a - pa) * qa
                    pnl_b = (pb - entry_b) * qb
                costos = (qa * (entry_a + pa) + qb * (entry_b + pb)) * COSTO_LADO
                pnl_neto = pnl_a + pnl_b - costos
                trades.append(pnl_neto)
                posicion = 0
                entry_a = entry_b = None
    return {
        'trades': len(trades),
        'pnl_neto_usd': round(sum(trades), 2),
        'wr': round(sum(1 for p in trades if p > 0) / len(trades) * 100, 1) if trades else None,
        'pnl_por_trade': round(sum(trades) / len(trades), 3) if trades else None,
    }


def main():
    df = cargar()
    n = len(df)
    corte = int(n * FORMACION_FRAC)
    print(f"Datos alineados: {n} velas 1h ({df.index[0]} → {df.index[-1]})")
    print(f"Formación: {df.index[0]} → {df.index[corte]} ({corte} velas)")
    print(f"Prueba (OOS): {df.index[corte]} → {df.index[-1]} ({n - corte} velas)\n")

    logp = np.log(df)
    symbols = list(df.columns)
    resultados = []

    for a, b in itertools.combinations(symbols, 2):
        y_form = logp[a].iloc[:corte].values
        x_form = logp[b].iloc[:corte].values
        alpha, beta, resid_form, se_b = ols_beta(y_form, x_form)

        t_adf, gamma = adf_1lag(resid_form)
        hl = half_life(resid_form)
        mu_form, sigma_form = float(resid_form.mean()), float(resid_form.std())

        spread_full = logp[a] - beta * logp[b]
        spread_test = spread_full.iloc[corte:]

        coint_ok = t_adf < -2.86
        hl_ok = hl is not None and (1 / 24) <= hl <= 30  # 1h a 30 días (en unidades de vela=1h → hl en horas)
        # half_life() está en unidades de VELA (1h) porque resid_form es 1h
        hl_dias = hl / 24 if hl else None
        hl_ok = hl is not None and (1.0 <= hl <= 30 * 24)  # entre 1h y 30 días, en horas

        bt = None
        if sigma_form > 0:
            bt = backtest_zscore(spread_test, mu_form, sigma_form,
                                 df[a].iloc[corte:], df[b].iloc[corte:], beta)

        fila = {
            'par': f"{a}/{b}", 'beta_hedge': round(float(beta), 4),
            't_adf_formacion': round(t_adf, 3), 'cointegra_5pct_naive': bool(coint_ok),
            'half_life_horas': round(hl, 1) if hl else None,
            'half_life_dias': round(hl_dias, 2) if hl_dias else None,
            'half_life_en_rango': bool(hl_ok),
            **({f'oos_{k}': v for k, v in bt.items()} if bt else {}),
        }
        resultados.append(fila)

    resultados.sort(key=lambda f: f['t_adf_formacion'])

    print(f"{'par':<16}{'beta':>8}{'t_ADF':>9}{'coint?':>8}{'HL(d)':>8}"
          f"{'HL_ok':>7}{'oos_trades':>12}{'oos_pnl$':>11}{'oos_wr%':>9}")
    for f in resultados:
        print(f"{f['par']:<16}{f['beta_hedge']:>8.3f}{f['t_adf_formacion']:>9.2f}"
              f"{'SI' if f['cointegra_5pct_naive'] else 'no':>8}"
              f"{f.get('half_life_dias') or float('nan'):>8.1f}"
              f"{'SI' if f['half_life_en_rango'] else 'no':>7}"
              f"{f.get('oos_trades', 0):>12}{f.get('oos_pnl_neto_usd', 0):>11.2f}"
              f"{f.get('oos_wr') if f.get('oos_wr') is not None else float('nan'):>9.1f}")

    candidatos = [f for f in resultados if f['cointegra_5pct_naive'] and f['half_life_en_rango']
                 and f.get('oos_pnl_neto_usd', -1) is not None and f.get('oos_pnl_neto_usd', -1) > 0]
    print(f"\nPares que cumplen los 3 criterios (cointegra + half-life en rango + PnL OOS neto > 0): "
          f"{len(candidatos)}/{len(resultados)}")
    for c in candidatos:
        print(f"  {c}")

    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pairs_cointegracion_resultado.json')
    with open(ruta, 'w') as f:
        json.dump({'n_velas': n, 'corte_formacion': corte,
                   'formacion_inicio': str(df.index[0]), 'formacion_fin': str(df.index[corte]),
                   'prueba_inicio': str(df.index[corte]), 'prueba_fin': str(df.index[-1]),
                   'pares': resultados, 'candidatos_3_criterios': candidatos}, f, indent=1, ensure_ascii=False)
    print(f"\nGuardado: {ruta}")


if __name__ == '__main__':
    main()
