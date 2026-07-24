"""M3 — Funding REAL por símbolo (reemplaza el piso pesimista de M1 cuando se le pasa al motor).

Dos fuentes, ambas read-only:
  - Canasta original (ETH/SOL/BNB/XRP/ADA/LINK + BTC): `bot_alpha_portfolio/v27b_carry/funding_cache.pkl`
    (ya existía, construido en la sesión V27-B).
  - Canasta OOB (BTC/DOGE/AVAX/DOT/LTC/ATOM): `Fragua/m3_carry/funding_cache_oob.pkl` (descargado por
    `_descargar_funding_oob.py` desde la API pública de Binance — cache PROPIO, no toca bot_alpha_portfolio).

Construye DOS matrices (T,S) alineadas a los timestamps de la matriz de precios:
  - `matriz_pagos`: dispersa — 0 en toda barra que no sea un evento de funding real, la tasa real en las
    barras donde sí lo es. Para la CONTABILIDAD (lo que efectivamente se paga/cobra). Si dos eventos
    colisionan en la misma hora (no ocurre en los caches reales), se SUMAN (ambos pagos ocurren).
  - `matriz_conocida`: la última tasa PUBLICADA en cada barra (forward-fill causal, sembrado con la última
    tasa publicada ANTES de la ventana si existe). Para el RANKING: a la hora de decidir el libro se usa
    la última tasa ya publicada, nunca una futura. En una colisión de hora, la conocida es la del ÚLTIMO
    evento (la última publicada), no la suma (fix Fable 2026-07-04 — la suma es correcta para pagar,
    no para "última tasa conocida").

NOTA de causalidad (validación Fable 2026-07-04): los timestamps del cache de precios son OPEN time
(verificado en binance_client._df_de_klines) — la barra rotulada H cierra en H+1h real, y el motor decide
al cierre. Con eso, `round('h')` no puede crear lookahead con ningún jitter < 30 min (el real medido es
de milisegundos, siempre positivo). Si alguna vez se reusa esto con timestamps CLOSE-time, esa holgura
desaparece — re-auditar.
"""
import os
import pickle
import numpy as np
import pandas as pd

RUTA_CACHE_ORIGINAL = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'bot_alpha_portfolio', 'v27b_carry', 'funding_cache.pkl')

RUTA_CACHE_OOB = os.path.join(os.path.dirname(__file__), 'funding_cache_oob.pkl')


def cargar_funding(ruta):
    with open(ruta, 'rb') as f:
        return pickle.load(f)


def matrices_funding(raw_funding, times, symbols, permitir_eventos_sin_barra=False):
    """Devuelve (matriz_pagos, matriz_conocida, meta), matrices (T, S) alineadas a `times`.

    IMPORTANTE: `times`/`symbols` deben ser EXACTAMENTE los que produjo `datos.alinear()` para la matriz
    de precios M que se le pasa al motor — el motor indexa funding_matrix[t] con el mismo t que M
    (engine_xs.correr valida shape, pero la correspondencia de timestamps es responsabilidad del caller).

    Los eventos reales traen unos pocos ms de jitter (medido: 0 a +30ms en los 13 símbolos de ambos
    caches); se redondean a la hora para alinear con barras de 1h (causal — ver nota del módulo).

    Guards de honestidad (fix Fable 2026-07-04 — antes estos casos pasaban EN SILENCIO):
      - tasas NaN en el cache → ValueError (poison silencioso del equity).
      - símbolo sin NINGÚN evento dentro de la ventana → ValueError (típico de un mismatch de timestamps
        o tz: la alternativa silenciosa era "funding = 0 para siempre", optimista).
      - evento dentro de la ventana cuya hora NO existe como barra → ValueError (el pago se perdería en
        silencio). Escape hatch explícito: `permitir_eventos_sin_barra=True` (documentadamente optimista).

    meta: colisiones_hora (total), eventos_promedio_por_simbolo, y `por_simbolo` con
    eventos_en_ventana / eventos_sin_barra / colisiones_hora / max_gap_horas (auditar cobertura:
    el espaciado 8h NO es estructural — SOLUSDT tuvo tramos de funding cada 2h/4h en 2022).
    """
    times_idx = pd.DatetimeIndex(times)
    T, S = len(times_idx), len(symbols)
    pagos = np.zeros((T, S), dtype=float)
    conocida = np.zeros((T, S), dtype=float)
    colisiones_totales = 0
    eventos_totales_en_ventana = 0
    por_simbolo = {}

    for j, sym in enumerate(symbols):
        if sym not in raw_funding:
            raise KeyError(f"Sin datos de funding real para {sym} — ¿cache incompleto?")
        df = raw_funding[sym][['time', 'rate']].copy()
        if df['rate'].isna().any():
            raise ValueError(f"{sym}: tasas NaN en el cache de funding — datos corruptos.")
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time', kind='stable')      # cronológico por tiempo REAL (para que 'last'
        df['time'] = df['time'].dt.round('h')           # en una colisión sea el último evento publicado)

        conteo = df.groupby('time').size()
        colisiones_sym = int((conteo > 1).sum())
        colisiones_totales += colisiones_sym
        suma = df.groupby('time')['rate'].sum()         # PAGOS: en colisión se pagan ambos → suma
        ultima = df.groupby('time')['rate'].last()      # CONOCIDA: la última tasa publicada

        # --- guards de cobertura dentro de la ventana ---
        en_ventana = conteo.index[(conteo.index >= times_idx[0]) & (conteo.index <= times_idx[-1])]
        if len(en_ventana) == 0:
            raise ValueError(
                f"{sym}: cero eventos de funding dentro de la ventana {times_idx[0]}..{times_idx[-1]} — "
                f"mismatch de timestamps/tz o cache que no cubre la ventana.")
        sin_barra = int((~en_ventana.isin(times_idx)).sum())
        if sin_barra and not permitir_eventos_sin_barra:
            raise ValueError(
                f"{sym}: {sin_barra} eventos de funding dentro de la ventana caen en horas sin barra de "
                f"precio — sus pagos se perderían en silencio (optimista). Revisar huecos del cache de "
                f"precios, o pasar permitir_eventos_sin_barra=True para aceptarlo explícitamente.")
        gaps_h = en_ventana.to_series().diff().dropna().dt.total_seconds() / 3600.0
        eventos_totales_en_ventana += len(en_ventana)

        # --- pagos: dispersa, alineada a las barras ---
        pagos[:, j] = suma.reindex(times_idx, fill_value=0.0).to_numpy()

        # --- conocida: última tasa publicada, ffill causal, sembrada con la última tasa pre-ventana ---
        # (fix Fable 2026-07-04: antes las barras anteriores al primer evento en ventana quedaban en 0.0
        #  aunque una tasa real estaba publicada — confirmado en ambos caches: barras 0..6 en 0.0 con el
        #  evento de 2023-06-12 00:00 publicado 1h antes de la ventana.)
        previas = ultima[ultima.index < times_idx[0]]
        seed = float(previas.iloc[-1]) if len(previas) else 0.0
        col = ultima.reindex(times_idx).to_numpy()      # NaN donde no hubo evento (incl. tasa 0.0 real)
        serie = pd.Series(col).ffill().fillna(seed)
        conocida[:, j] = serie.to_numpy()

        por_simbolo[sym] = {
            'eventos_en_ventana': int(len(en_ventana)),
            'eventos_sin_barra': sin_barra,
            'colisiones_hora': colisiones_sym,
            'max_gap_horas': float(gaps_h.max()) if len(gaps_h) else 0.0,
            'seed_pre_ventana': seed,
        }

    meta = {
        'colisiones_hora': colisiones_totales,
        'eventos_promedio_por_simbolo': int(eventos_totales_en_ventana / S) if S else 0,
        'por_simbolo': por_simbolo,
    }
    return pagos, conocida, meta
