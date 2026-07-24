"""M3 — Ranker de carry cross-sectional: long el funding más NEGATIVO (te pagan por estar long),
short el más POSITIVO (te pagan por estar short). Reusa la misma construcción dollar-neutral de M1.

V46: rankea por la ÚLTIMA tasa de funding CONOCIDA (causal — la tasa real ya publicada al momento de la
decisión, nunca una futura). No hay "lookback" que promediar: el funding es un evento discreto, y usar
el último valor conocido (sin suavizar) es la elección más simple y menos arbitraria.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'm1_cross_sectional'))
import numpy as np
from estrategia_xsmom import _pesos_desde_ranking   # noqa: E402


def ranker_carry(conocida_matrix, k, gross):
    """Devuelve un ranker(M, t) que IGNORA M (precio) y usa `conocida_matrix[t]` (tasa de funding
    conocida en la barra t, ya forward-filled y alineada) para construir el libro.

    Long = símbolos con la tasa MÁS NEGATIVA (score = -rate, ascendente → los de rate más negativo
    quedan al final → orden[-k:] → long, coherente con `_pesos_desde_ranking`).
    Short = símbolos con la tasa MÁS POSITIVA.

    Nota (validación Fable 2026-07-04): los empates se resuelven por argsort estable (determinista pero
    arbitrario por índice de símbolo). Con datos reales no ocurre post-primer-evento (tasas float, y
    `matrices_funding` siembra `conocida` con la última tasa pre-ventana desde la barra 0). Si se usara
    con una `conocida` sintética toda-ceros (sin eventos previos), el libro sería degenerado
    (short símbolo 0 / long símbolo S-1) — usar warmup >= primer evento.
    """
    def _r(M, t):
        S = M.shape[1]
        score = -conocida_matrix[t]                 # negar: así "mejor" (final del orden) = rate más negativo
        orden = np.argsort(score, kind='stable')
        return _pesos_desde_ranking(orden, k, gross, S)
    return _r
