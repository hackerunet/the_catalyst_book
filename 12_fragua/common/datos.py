"""Carga y alineación de datos OHLCV — READ-ONLY sobre los caches existentes.

Los motores cross-sectional necesitan una MATRIZ de precios alineada en el tiempo (todos los símbolos en
los mismos timestamps). Este módulo lee un cache `.pkl` del motor vivo (dict {símbolo: DataFrame OHLCV})
SIN modificarlo, y devuelve estructuras alineadas.

Aislamiento: solo hace `pickle.load` de un archivo; no importa nada de bot_alpha_portfolio.
"""
import os
import pickle
import numpy as np
import pandas as pd

# Caches 1h de 3 años ya producidos por el motor vivo (read-only, no se escriben ni se mueven).
CACHE_1H_ORIGINAL = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'bot_alpha_portfolio', 'stable_v25_prototype',
    'wf_cache_1h_26280_2026-06-11.pkl')

# Basket fuera de canasta (OOB) estándar del proyecto — nunca usado en el diseño de ninguna señal.
CACHE_1H_OOB = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'bot_alpha_portfolio', 'stable_v25_prototype',
    'wf_cache_1h_26280_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl')

# Caches 4h de 4 años (8760 barras) — el timeframe de V26 y de V47+.
CACHE_4H_ORIGINAL = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'bot_alpha_portfolio', 'stable_v25_prototype',
    'wf_cache_4h_8760_2026-06-11.pkl')

CACHE_4H_OOB = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'bot_alpha_portfolio', 'stable_v25_prototype',
    'wf_cache_4h_8760_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl')


def cargar_cache(ruta):
    """Devuelve el dict {símbolo: DataFrame OHLCV} tal cual está en el pkl (read-only)."""
    with open(ruta, 'rb') as f:
        return pickle.load(f)


def alinear(raw, columna='close'):
    """Alinea todos los símbolos en su intersección de timestamps.

    Devuelve (times, symbols, M) donde:
      - times   : np.ndarray de timestamps comunes (ordenados)
      - symbols : lista de símbolos (orden estable)
      - M       : np.ndarray shape (T, S) con `columna` (p.ej. 'close') de cada símbolo por timestamp.

    Usa INNER JOIN sobre 'time' — solo timestamps presentes en TODOS los símbolos. Sin relleno hacia
    adelante (evita inventar precios). Fable: verificar que no hay NaN en M tras la alineación (ítem A1/D1).
    """
    symbols = list(raw.keys())
    series = []
    for s in symbols:
        df = raw[s][['time', columna]].copy()
        df = df.set_index('time')[columna].rename(s)
        series.append(df)
    mat = pd.concat(series, axis=1, join='inner').sort_index()
    if not mat.index.is_unique:
        # Fix Fable 2026-07-04: un timestamp duplicado en cualquier símbolo multiplica filas en el
        # inner-join (producto cartesiano) y corrompe la matriz EN SILENCIO. Mejor reventar acá.
        raise ValueError("Timestamps duplicados tras la alineación — cache corrupto o símbolo con filas repetidas.")
    times = mat.index.to_numpy()
    M = mat.to_numpy(dtype=float)
    if np.isnan(M).any():
        raise ValueError("Hay NaN tras la alineación inner-join — datos inconsistentes.")
    return times, symbols, M


def horas_por_barra(intervalo):
    """Horas que representa una barra del intervalo dado (para funding y anualización)."""
    tabla = {'1m': 1/60, '5m': 5/60, '15m': 0.25, '30m': 0.5,
             '1h': 1.0, '2h': 2.0, '4h': 4.0, '1d': 24.0}
    if intervalo not in tabla:
        raise ValueError(f"Intervalo no soportado: {intervalo}")
    return tabla[intervalo]
