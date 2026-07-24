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
