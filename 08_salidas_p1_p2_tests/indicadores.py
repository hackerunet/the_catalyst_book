"""
indicadores.py — Indicadores técnicos puros (sin I/O, sin estado).
Implementaciones probadas heredadas de los bots previos del proyecto.
"""
import pandas as pd
import numpy as np


def _atr(df, period=14):
    h, l, c = df['high'], df['low'], df['close']
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _adx(df, period=14):
    h, l, c = df['high'], df['low'], df['close']
    up, down = h.diff(), -l.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0)


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def calcular_indicadores(df):
    """Set completo de indicadores 1h. Todas las ventanas son causales."""
    df = df.copy()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['Volume_MA'] = df['volume'].rolling(20).mean()
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    df['ATR'] = _atr(df)
    df['ADX'] = _adx(df)
    df['RSI'] = _rsi(df['close'])
    df['Body'] = (df['close'] - df['open']).abs()
    # Squeeze TTM (test A 2026-06-11, parámetros canónicos pre-registrados, NO
    # escaneados): BB(20, 2σ poblacional) completamente DENTRO del canal de
    # Keltner(EMA20 ± 1.5×ATR(20)) = compresión de volatilidad (chop probable).
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std(ddof=0)
    ema20 = df['close'].ewm(span=20, adjust=False).mean()
    atr20 = _atr(df, 20)
    df['Squeeze_On'] = ((sma20 + 2.0 * std20 < ema20 + 1.5 * atr20) &
                        (sma20 - 2.0 * std20 > ema20 - 1.5 * atr20))

    # --- Columnas para el re-test de estrategias tempranas (V38/V39/V40,
    # 2026-07-03). Todas causales y vectorizadas; inofensivas si no se usan
    # (mismo patrón que Squeeze_On). NO tocan la lógica viva de V25/V26/V36. ---
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['EMA_84'] = df['close'].ewm(span=84, adjust=False).mean()   # ~EMA21 de 4h en 1h
    # Bandas de Bollinger (20, 2σ muestral, como el código v19_C original)
    std20s = df['close'].rolling(20).std()
    df['BB_SMA'] = sma20
    df['BB_UPPER'] = sma20 + 2.0 * std20s
    df['BB_LOWER'] = sma20 - 2.0 * std20s
    # Swings de V13 (sweep): máx/mín de 10 velas DESPLAZADO 1 (causal — el nivel
    # de liquidez es de las velas PREVIAS, no incluye la actual).
    df['Last_Swing_High_10'] = df['high'].rolling(10).max().shift(1)
    df['Last_Swing_Low_10'] = df['low'].rolling(10).min().shift(1)
    # Swings de V19_C (rejection): máx/mín de 15 velas SIN desplazar — el código
    # original lo lee de la vela -2 (prev), lo que ya lo hace causal en la señal.
    df['Swing_High_15'] = df['high'].rolling(15).max()
    df['Swing_Low_15'] = df['low'].rolling(15).min()
    df['Vol_SMA_10'] = df['volume'].rolling(10).mean()  # spike de V13

    # --- Divergencia de RSI (2026-07-04, Test "2" de salida por agotamiento).
    # Causal: shift(1) ANTES del rolling — la ventana de comparación excluye
    # SIEMPRE la vela actual, nunca mira el propio cierre contra sí mismo.
    # RSI_DIV_LOOKBACK = 14 (mismo período que el propio RSI, no un número nuevo).
    RSI_DIV_LOOKBACK = 14
    max_close_prev = df['close'].shift(1).rolling(RSI_DIV_LOOKBACK).max()
    max_rsi_prev = df['RSI'].shift(1).rolling(RSI_DIV_LOOKBACK).max()
    min_close_prev = df['close'].shift(1).rolling(RSI_DIV_LOOKBACK).min()
    min_rsi_prev = df['RSI'].shift(1).rolling(RSI_DIV_LOOKBACK).min()
    nuevo_max = df['close'] >= max_close_prev
    nuevo_min = df['close'] <= min_close_prev
    # Bajista (para LONG): nuevo máximo de precio, pero el RSI NO confirma (es
    # menor que su propio máximo previo) — la fuerza no acompaña al nuevo alto.
    df['Div_Bajista'] = (nuevo_max & (df['RSI'] < max_rsi_prev)).fillna(False)
    # Alcista (para SHORT): nuevo mínimo de precio, pero el RSI NO confirma.
    df['Div_Alcista'] = (nuevo_min & (df['RSI'] > min_rsi_prev)).fillna(False)
    return df


def atr_diario(df):
    """ATR(14) sobre velas DIARIAS re-muestreadas — movimiento típico de un día."""
    try:
        d = df.set_index('time').resample('1D').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        if len(d) < 15:
            return None
        return float(_atr(d).iloc[-1])
    except Exception:
        return None


def momentum_diario(df):
    """'LONG' si el cierre diario está sobre su EMA20 diaria, 'SHORT' si debajo."""
    try:
        d = df.set_index('time').resample('1D').agg({'close': 'last'}).dropna()
        if len(d) < 21:
            return None
        ema20 = d['close'].ewm(span=20, adjust=False).mean()
        if d['close'].iloc[-1] > ema20.iloc[-1]:
            return 'LONG'
        if d['close'].iloc[-1] < ema20.iloc[-1]:
            return 'SHORT'
    except Exception:
        pass
    return None
