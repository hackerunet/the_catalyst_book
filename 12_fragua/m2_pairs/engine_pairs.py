"""M2 — Motor de backtest PAIRS / STAT-ARB (2 patas, cointegración + z-score).

Modela lo que ni M0 ni M1 pueden: una cartera de 2 patas simultáneas (long A / short B en
proporción del hedge ratio), con señal de z-score del spread, filtro de cointegración rolling,
y protección contra breakdown (stop de emergencia en z-score extremo).

Propiedades de honestidad (ver ../HONESTIDAD.md):
  - Anti-lookahead ESTRUCTURAL: el hedge ratio y el z-score de la barra t se calculan con datos
    estrictamente hasta t (ventana rolling causal). El trade en t gana el retorno de t→t+1.
  - Contabilidad: PnL neto de costos completos (fee+slippage por cambio de posición, funding
    sobre gross). Cada cambio de posición (entrada/salida/flip) paga 2× costos (dos patas).
  - Null JUSTO: `correr_null_desplazado` — rota el z-score temporalmente, preserva la cadencia
    de trades (= mismo número de entradas/salidas, desplazadas en el tiempo).
  - Determinista: misma entrada + misma semilla → mismo resultado.

NO importa nada de bot_alpha_portfolio. Costos vienen de ../common/costos.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common import costos, metricas  # noqa: E402


# ─── Cointegración y spread ───────────────────────────────────────────

def _ols_hedge_ratio(y, x):
    """Hedge ratio β por OLS: y = α + β·x + ε.  Devuelve (α, β)."""
    n = len(y)
    sx = x.sum()
    sy = y.sum()
    sxx = (x * x).sum()
    sxy = (x * y).sum()
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.0, 1.0  # fallback: hedge 1:1
    beta = (n * sxy - sx * sy) / denom
    alpha = (sy - beta * sx) / n
    return float(alpha), float(beta)


def _adf_pvalue_approx(residuos, max_lag=None):
    """P-value aproximado del test ADF sobre los residuos del spread.

    Implementación simplificada SIN statsmodels: regresión ADF manual (Δr_t = γ·r_{t-1} + e_t),
    estadístico t de γ, comparado contra tabla de valores críticos de MacKinnon (n grande).
    Solo necesitamos saber si p < 0.05 (cointegrado) o no.

    Valores críticos asintóticos de MacKinnon para ADF sin constante (caso de residuos de
    regresión, que ya tienen media ~0):
      1%: -2.58, 5%: -1.95, 10%: -1.62
    Para residuos Engle-Granger (2 variables), los valores son más estrictos:
      1%: -3.90, 5%: -3.34, 10%: -3.04
    Usamos los de Engle-Granger (conservadores).
    """
    r = np.asarray(residuos, dtype=float)
    n = len(r)
    if n < 30:
        return 1.0  # no hay suficientes datos

    dr = np.diff(r)        # Δr_t = r_t - r_{t-1}
    r_lag = r[:-1]          # r_{t-1}

    # OLS: dr = gamma * r_lag + e
    sx = r_lag.sum()
    sy = dr.sum()
    sxx = (r_lag * r_lag).sum()
    sxy = (r_lag * dr).sum()
    nn = len(dr)
    denom = nn * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 1.0

    gamma = (nn * sxy - sx * sy) / denom
    alpha_hat = (sy - gamma * sx) / nn

    # Residuos y std error de gamma
    e = dr - (alpha_hat + gamma * r_lag)
    s2 = (e * e).sum() / max(nn - 2, 1)
    se_gamma = np.sqrt(s2 * nn / max(denom, 1e-15))

    if se_gamma < 1e-15:
        return 1.0

    t_stat = gamma / se_gamma

    # Valores críticos Engle-Granger (2 variables, asintóticos)
    if t_stat < -3.90:
        return 0.001  # p < 1%
    elif t_stat < -3.34:
        return 0.03   # p < 5%
    elif t_stat < -3.04:
        return 0.08   # p < 10%
    else:
        return 0.50   # no rechazamos H0 (no cointegrado)


def calcular_spread_rolling(Pa, Pb, ventana):
    """Calcula hedge ratio, spread, y z-score rolling de forma CAUSAL.

    Para cada barra t:
      - hedge ratio β_t: OLS de Pa[t-ventana+1:t+1] sobre Pb[t-ventana+1:t+1]
      - spread_t = Pa[t] - β_t · Pb[t]
      - z-score_t = (spread_t - media_spread[t-ventana+1:t+1]) / std_spread[t-ventana+1:t+1]
      - cointegrado_t: ADF p-value < 0.05 sobre los residuos de la ventana

    Devuelve:
      hedge_ratio : (T,) — NaN antes de `ventana`
      spread      : (T,) — NaN antes de `ventana`
      z_score     : (T,) — NaN antes de `ventana`
      cointegrado : (T,) bool — False antes de `ventana`
    """
    T = len(Pa)
    hedge_ratio = np.full(T, np.nan)
    spread = np.full(T, np.nan)
    z_score = np.full(T, np.nan)
    cointegrado = np.zeros(T, dtype=bool)

    for t in range(ventana - 1, T):
        # Ventana causal: [t - ventana + 1, t + 1)
        i0 = t - ventana + 1
        ya = Pa[i0:t + 1]
        yb = Pb[i0:t + 1]

        alpha, beta = _ols_hedge_ratio(ya, yb)
        hedge_ratio[t] = beta

        # Spread = Pa - β·Pb (residuos de la regresión)
        resid = ya - beta * yb
        spread[t] = resid[-1]

        mu = resid.mean()
        sigma = resid.std(ddof=0)
        if sigma > 1e-12:
            z_score[t] = (resid[-1] - mu) / sigma
        else:
            z_score[t] = 0.0

        # Test de cointegración sobre los residuos de esta ventana
        p = _adf_pvalue_approx(resid)
        cointegrado[t] = (p < 0.05)

    return hedge_ratio, spread, z_score, cointegrado


# ─── Motor de backtest ────────────────────────────────────────────────

def correr(Pa, Pb, z_score, cointegrado, hpb,
           z_entry=2.0, z_exit=0.5, z_stop=4.0,
           aplicar_funding=True, equity_inicial=1.0):
    """Corre el backtest de pairs trading sobre un par (A, B).

    Lógica de posición:
      - Estado: FLAT, LONG_SPREAD (long A, short B), SHORT_SPREAD (long B, short A)
      - Entrada:
        · z > +z_entry Y cointegrado → SHORT_SPREAD (spread caro, vender)
        · z < -z_entry Y cointegrado → LONG_SPREAD (spread barato, comprar)
      - Salida:
        · LONG_SPREAD:  z > -z_exit (= cruzó de vuelta hacia 0) → FLAT
        · SHORT_SPREAD: z < +z_exit → FLAT
        · |z| > z_stop → FLAT (stop de emergencia, breakdown de cointegración)
        · cointegración se pierde (p >= 0.05) Y estamos en posición → FLAT (protección)
      - NO hay flip directo (de LONG a SHORT sin pasar por FLAT): primero cierra, luego reevalúa.

    Contabilidad:
      - Cada CAMBIO de posición (FLAT→posición o posición→FLAT) paga 2× costos (dos patas).
      - Funding sobre gross (= 2 × nocional de una pata, constante mientras hay posición).
      - PnL por barra = retorno_A · peso_A + retorno_B · peso_B (pesos con signo: +1 long, -1 short).

    Args:
      Pa, Pb     : arrays (T,) de precios de los dos activos
      z_score    : array (T,) del z-score causal del spread
      cointegrado: array (T,) bool
      hpb        : horas por barra
      z_entry, z_exit, z_stop: umbrales
      aplicar_funding: si cobrar drag de funding
      equity_inicial: capital de arranque

    Returns dict con curva de equity, retornos, métricas, y log de trades.
    """
    T = len(Pa)
    equity = equity_inicial
    eq_curve = np.empty(T, dtype=float)
    eq_curve[0] = equity
    net_rets = np.empty(T - 1, dtype=float)

    # Estado de posición: 0 = FLAT, +1 = LONG_SPREAD, -1 = SHORT_SPREAD
    pos = 0
    n_trades = 0
    n_stops = 0
    n_coint_exits = 0
    trades_log = []  # [(barra_entrada, barra_salida, pos, pnl_pct)]
    entry_bar = -1

    for t in range(1, T):
        z = z_score[t - 1]  # z-score conocido al INICIO de la barra t (calculado con datos hasta t-1)
        coint = cointegrado[t - 1]

        ret_a = Pa[t] / Pa[t - 1] - 1.0
        ret_b = Pb[t] / Pb[t - 1] - 1.0

        # PnL de la posición actual
        if pos == 1:   # LONG spread: long A, short B
            port_ret = ret_a - ret_b
        elif pos == -1:  # SHORT spread: short A, long B
            port_ret = ret_b - ret_a
        else:
            port_ret = 0.0

        # Funding (sobre gross = 2 × nocional de una pata = 2.0 en unidades de equity)
        if pos != 0 and aplicar_funding:
            port_ret -= costos.costo_funding(2.0, hpb)

        # ── Lógica de salida (evaluar ANTES de nueva entrada) ──
        cerrar = False
        motivo = ''
        if pos != 0:
            if not np.isnan(z):
                if abs(z) > z_stop:
                    cerrar = True
                    motivo = 'STOP'
                    n_stops += 1
                elif pos == 1 and z > -z_exit:
                    cerrar = True
                    motivo = 'REVERSION'
                elif pos == -1 and z < z_exit:
                    cerrar = True
                    motivo = 'REVERSION'
            if not cerrar and not coint:
                cerrar = True
                motivo = 'COINT_LOST'
                n_coint_exits += 1

        if cerrar:
            # Costo de cerrar las 2 patas
            port_ret -= costos.costo_rebalanceo(2.0)
            trades_log.append((entry_bar, t, pos, equity * (1 + port_ret) - equity, motivo))
            pos = 0
            n_trades += 1

        # ── Lógica de entrada (solo si FLAT) ──
        if pos == 0 and not np.isnan(z) and coint:
            if z < -z_entry:
                pos = 1  # LONG spread
                port_ret -= costos.costo_rebalanceo(2.0)
                entry_bar = t
            elif z > z_entry:
                pos = -1  # SHORT spread
                port_ret -= costos.costo_rebalanceo(2.0)
                entry_bar = t

        equity *= (1.0 + port_ret)
        if equity <= 0:
            equity = 0.0
            pos = 0
            eq_curve[t:] = 0.0
            net_rets[t - 1:] = 0.0
            break
        eq_curve[t] = equity
        net_rets[t - 1] = port_ret

    # Cierre administrativo si hay posición abierta al final
    if pos != 0:
        trades_log.append((entry_bar, T - 1, pos, equity - equity_inicial, 'ADMIN'))
        n_trades += 1

    horas_totales = (T - 1) * hpb
    return {
        'equity': eq_curve,
        'retornos_netos': net_rets,
        'pnl_pct': (eq_curve[-1] / eq_curve[0] - 1.0) * 100,
        'cagr': metricas.cagr(eq_curve, horas_totales),
        'max_dd': metricas.max_drawdown(eq_curve),
        'pf': metricas.profit_factor(net_rets),
        'sharpe': metricas.sharpe(net_rets, 365.25 * 24 / hpb),
        'n_trades': n_trades,
        'n_stops': n_stops,
        'n_coint_exits': n_coint_exits,
        'trades': trades_log,
    }


def correr_null_desplazado(Pa, Pb, z_score_real, cointegrado_real, hpb, n=200,
                           z_entry=2.0, z_exit=0.5, z_stop=4.0,
                           aplicar_funding=True, equity_inicial=1.0, min_offset=None):
    """Corre `n` nulls desplazando el z-score temporalmente.

    El desplazamiento preserva la FORMA del z-score (y por tanto la cadencia de trades) pero
    desalinea la señal de los retornos reales → cualquier resultado positivo del null es azar.

    Per lección M1 (Fable 2026-07-04): el offset mínimo debe ser >= la ventana de cointegración
    para que la señal desplazada no solape con la original en la misma ventana.
    """
    T = len(Pa)
    if min_offset is None:
        min_offset = 720  # = ventana de cointegración default
    max_offset = T - min_offset
    if max_offset <= min_offset:
        return np.array([])

    offsets = np.linspace(min_offset, max_offset, n, dtype=int)
    pnls = np.empty(n, dtype=float)

    for i, off in enumerate(offsets):
        z_shift = np.roll(z_score_real, off)
        c_shift = np.roll(cointegrado_real, off)
        # Las primeras `off` barras del z-score desplazado son basura (envuelven) — marcar como NaN
        z_shift[:off] = np.nan
        c_shift[:off] = False
        res = correr(Pa, Pb, z_shift, c_shift, hpb,
                     z_entry=z_entry, z_exit=z_exit, z_stop=z_stop,
                     aplicar_funding=aplicar_funding, equity_inicial=equity_inicial)
        pnls[i] = res['pnl_pct']

    return pnls


def percentil_vs_null(pnl_real, pnls_null):
    """Percentil del PnL real en la distribución null."""
    if len(pnls_null) == 0:
        return np.nan
    return float(np.sum(pnls_null < pnl_real) / len(pnls_null) * 100)
