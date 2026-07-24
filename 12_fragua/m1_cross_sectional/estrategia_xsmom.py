"""Estrategias de ranking cross-sectional — funciones PURAS de señal.

Un "ranker" es una función pura `ranker(M, t) -> pesos` donde:
  - M    : matriz de precios (T, S) alineada; M[i, s] = close del símbolo s en el timestamp i.
  - t    : índice de la barra ACTUAL. El ranker SOLO puede leer M[:t+1] (hasta el cierre de t inclusive).
           Leer M[t+1:] sería lookahead (prohibido — ítem A1 de HONESTIDAD.md).
  - pesos: np.ndarray (S,) de pesos objetivo como fracción del equity. Dollar-neutral: sum(pesos)=0,
           gross = sum(|pesos|). Devuelve None si no hay historia suficiente (el motor queda flat).

El motor (engine_xs) usa el MISMO code-path para el ranker real y el null aleatorio (ítem C1). Lo único
que cambia entre "estrategia real" y "azar" es esta función.
"""
import numpy as np


def _pesos_desde_ranking(orden, k, gross, S):
    """Construye el vector de pesos dollar-neutral: +gross/2/k a los top-k, -gross/2/k a los bottom-k.

    `orden` = índices de símbolos ordenados de PEOR a MEJOR (ascendente por el score de ranking).
    Long = los k mejores (final de `orden`); Short = los k peores (inicio de `orden`).

    Guard central (fix Fable 2026-07-04): con 2*k > S los lados long y short se SOLAPAN y el segundo
    asignado pisa al primero → libro NO neutral en silencio (p.ej. sum=-0.25, gross=0.75). El guard
    estaba solo en ranker_momentum; reversion y aleatorio pasaban sin error. Ahora vive aquí, cubre a
    TODOS los rankers.
    """
    if k < 1:
        raise ValueError(f"k ({k}) debe ser >= 1")
    if 2 * k > S:
        raise ValueError(f"2*k ({2 * k}) > número de símbolos ({S}) — los lados se solaparían")
    w = np.zeros(S, dtype=float)
    peso_lado = gross / 2.0 / k          # cada símbolo del lado largo/corto
    longs = orden[-k:]                    # k mejores
    shorts = orden[:k]                    # k peores
    w[longs] = +peso_lado
    w[shorts] = -peso_lado
    return w


def ranker_momentum(lookback, k, gross):
    """V44 — Momentum cross-sectional: rankea por retorno trailing de `lookback` barras.

    Long los k de mayor retorno, short los k de menor. Causal: usa M[t] y M[t-lookback], ambos <= t.
    """
    def _r(M, t):
        if t < lookback:
            return None
        S = M.shape[1]
        ret = M[t] / M[t - lookback] - 1.0          # retorno trailing por símbolo (causal)
        orden = np.argsort(ret, kind='stable')       # ascendente: peor→mejor
        return _pesos_desde_ranking(orden, k, gross, S)
    return _r


def ranker_reversion(lookback, k, gross):
    """V45 — Reversión de corto plazo cross-sectional: long los PEORES, short los MEJORES (invierte momentum).

    Mismo cálculo que momentum pero invierte los lados. Causal.
    """
    def _r(M, t):
        if t < lookback:
            return None
        S = M.shape[1]
        ret = M[t] / M[t - lookback] - 1.0
        orden = np.argsort(ret, kind='stable')       # ascendente: peor→mejor
        # invertir: los peores (inicio) van LONG, los mejores (final) van SHORT
        orden_inv = orden[::-1]
        return _pesos_desde_ranking(orden_inv, k, gross, S)
    return _r


def ranker_aleatorio(k, gross, rng, warmup=0):
    """NULL NAIVE por permutación — asigna long/short al AZAR cada rebalanceo. Determinista con `rng`.

    ⚠️ ADVERTENCIA (hallazgo Fable 2026-07-04, ítem E1): este null NO mantiene el turnover de la señal
    real. Una permutación fresca por rebalanceo rota MUCHO más que una señal persistente como momentum
    (medido en el cache real: null 1.35 vs real 0.56 por rebalanceo, 2.4x) → el null paga ~2.4x los
    costos → su distribución de PnL queda aplastada → el percentil del real queda INFLADO (sesgo
    OPTIMISTA; una config que pierde −53% salió percentil 100). NO usar para el criterio de aceptación
    E1 — usar `engine_xs.correr_null_desplazado` (null por rotación temporal de la señal real, que
    mantiene cadencia Y turnover). Se conserva solo como cota gruesa/diagnóstico.
    """
    def _r(M, t):
        if t < warmup:
            return None
        S = M.shape[1]
        orden = rng.permutation(S)                    # ranking aleatorio
        return _pesos_desde_ranking(orden, k, gross, S)
    return _r
