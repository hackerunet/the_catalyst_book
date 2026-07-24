"""Métricas de una curva de equity — las mismas nociones que usa el motor vivo.

Todo se calcula sobre la serie de retornos por periodo o la curva de equity resultante. Sin dependencias
del motor vivo.
"""
import numpy as np


def curva_equity(retornos_periodo, equity_inicial=1.0):
    """Curva de equity multiplicativa a partir de retornos netos por periodo (ya con costos).

    equity[0] = equity_inicial ; equity[t+1] = equity[t] * (1 + r[t]).
    Devuelve np.ndarray de longitud len(retornos)+1.
    """
    eq = np.empty(len(retornos_periodo) + 1, dtype=float)
    eq[0] = equity_inicial
    for i, r in enumerate(retornos_periodo):
        eq[i + 1] = eq[i] * (1.0 + r)
    return eq


def max_drawdown(equity):
    """Máximo drawdown (fracción positiva, p.ej. 0.21 = 21%) sobre la curva de equity mark-to-market."""
    pico = np.maximum.accumulate(equity)
    dd = (equity - pico) / pico
    return float(-dd.min())  # dd es <=0; devolvemos magnitud positiva


def cagr(equity, horas_totales):
    """Retorno anual compuesto dado el retorno total y el tiempo transcurrido (en horas)."""
    anios = horas_totales / (365.25 * 24)
    if anios <= 0:
        return 0.0
    total = equity[-1] / equity[0]
    if total <= 0.0:
        # Quiebra (equity terminal 0 o negativa): el CAGR compuesto no está definido — devolvemos −100%.
        # (Fix Fable 2026-07-04: antes, un total negativo elevado a 1/anios daba resultados sin sentido
        # o complejos según la paridad del exponente.)
        return -1.0
    return float(total ** (1.0 / anios) - 1.0)


def sharpe(retornos_periodo, periodos_por_anio):
    """Sharpe anualizado (sin tasa libre de riesgo). Pesimista: usa std poblacional (ddof=0)."""
    r = np.asarray(retornos_periodo, dtype=float)
    if r.std(ddof=0) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=0) * np.sqrt(periodos_por_anio))


def profit_factor(retornos_periodo):
    """Profit factor = suma de retornos positivos / |suma de retornos negativos|.

    Nota: es un PF por-periodo (no por-trade), consistente con una estrategia de cartera que rebalancea.
    """
    r = np.asarray(retornos_periodo, dtype=float)
    ganancias = r[r > 0].sum()
    perdidas = -r[r < 0].sum()
    if perdidas == 0:
        return float('inf') if ganancias > 0 else 0.0
    return float(ganancias / perdidas)


def correlacion(retornos_a, retornos_b):
    """Correlación de Pearson entre dos series de retornos alineadas (para vs V26/V36)."""
    a = np.asarray(retornos_a, dtype=float)
    b = np.asarray(retornos_b, dtype=float)
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    if a.std(ddof=0) == 0 or b.std(ddof=0) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])
