"""
estrategias_tempranas.py — Re-test honesto de las 3 estrategias categoría-3 de
la "era del espejismo" (V38/V39/V40, 2026-07-03). Ver pre-registro en el libro.

Cada función porta la SEÑAL DE ENTRADA verbatim del código original
(bot_v13/estrategia_v13.py, bot_v19_C/estrategia_v19_C.py,
bot_v18_C/estrategia_v18_C.py) — mismos detectores de patrón, mismos filtros,
mismos umbrales — para juzgar la ESTRATEGIA como fue concebida, no una variante.
Retornan ('LONG'|'SHORT'|None, etiqueta) leyendo la última vela cerrada del df.

El sizing/TP/SL y la salida los pone el harness (estrategia._armar_senial +
EXIT_MODE), IGUAL que para todos los ENTRY_MODE — así la comparación con dos
salidas (escalera vs tendencia) es limpia y single-variable.

Módulo PURO (sin I/O). Detectores de patrón replicados de los archivos
originales (definiciones ligeramente distintas a patrones.py — se usa la
original a propósito, para fidelidad del re-test).
"""


# --- Detectores de patrón (verbatim de los archivos v13/v18_C/v19_C) ---
def _hammer(c):
    body = abs(c['close'] - c['open']) or 0.0001
    lower = (c['open'] - c['low']) if c['close'] > c['open'] else (c['close'] - c['low'])
    upper = (c['high'] - c['close']) if c['close'] > c['open'] else (c['high'] - c['open'])
    return lower > 2 * body and upper < body


def _shooting_star(c):
    body = abs(c['close'] - c['open']) or 0.0001
    lower = (c['open'] - c['low']) if c['close'] > c['open'] else (c['close'] - c['low'])
    upper = (c['high'] - c['close']) if c['close'] > c['open'] else (c['high'] - c['open'])
    return upper > 2 * body and lower < body


def _bull_engulf(cur, prev):
    return (prev['close'] < prev['open'] and cur['close'] > cur['open']
            and cur['close'] > prev['open'] and cur['open'] < prev['close'])


def _bear_engulf(cur, prev):
    return (prev['close'] > prev['open'] and cur['close'] < cur['open']
            and cur['close'] < prev['open'] and cur['open'] > prev['close'])


def _morning_star(cur, prev, prev2):
    prev_body = abs(prev['close'] - prev['open']) or 0.0001
    prev2_body = abs(prev2['close'] - prev2['open'])
    return (prev2['close'] < prev2['open'] and cur['close'] > cur['open']
            and prev_body < prev2_body * 0.5
            and cur['close'] > (prev2['open'] + prev2['close']) / 2)


def _evening_star(cur, prev, prev2):
    prev_body = abs(prev['close'] - prev['open']) or 0.0001
    prev2_body = abs(prev2['close'] - prev2['open'])
    return (prev2['close'] > prev2['open'] and cur['close'] < cur['open']
            and prev_body < prev2_body * 0.5
            and cur['close'] < (prev2['open'] + prev2['close']) / 2)


# ---------------------------------------------------------------------------
# V38 — CAZA DE LIQUIDEZ / LIQUIDITY SWEEP (bot_v13/estrategia_v13.py)
# ---------------------------------------------------------------------------
def senial_sweep(df):
    """Barrido de swing (10 velas desplazado) + retorno adentro + patrón +
    EMA200 del lado correcto + volumen spike + RSI contra-momentum + filtro de
    volatilidad. Verbatim de compute_signals_and_trades de v13."""
    if len(df) < 12:
        return None, None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    c = cur['close']
    atr = cur['ATR']
    rsi = cur['RSI']
    if atr <= 0 or (atr / c) <= 0.008:   # filtro de volatilidad (lateral) de v13
        return None, None
    vol_spike_cur = cur['volume'] > cur['Vol_SMA_10'] * 1.5
    vol_spike_prev = prev['volume'] > prev['Vol_SMA_10'] * 1.5
    has_volume = vol_spike_cur or vol_spike_prev  # (queda como convicción, no gate en v13)

    # LONG: barrido del swing low de 10 velas (últimas 7 velas), retorno arriba,
    # sobre EMA200, hammer/engulfing, RSI<50 (venía cayendo = contra-momentum).
    swing_low = cur['Last_Swing_Low_10']
    ventana = df.iloc[-8:]  # SWEEP_MAX_CANDLES+1 = 8
    sweep_l = (ventana['low'] < swing_low).any()
    ret_in_l = c > swing_low
    if (sweep_l and ret_in_l and c > cur['EMA_200'] and rsi < 50
            and (_hammer(cur) or _bull_engulf(cur, prev))):
        pat = 'Bullish Hammer' if _hammer(cur) else 'Bullish Engulfing'
        return 'LONG', f'Sweep {pat}{" +vol" if has_volume else ""}'

    swing_high = cur['Last_Swing_High_10']
    sweep_s = (ventana['high'] > swing_high).any()
    ret_in_s = c < swing_high
    if (sweep_s and ret_in_s and c < cur['EMA_200'] and rsi > 50
            and (_shooting_star(cur) or _bear_engulf(cur, prev))):
        pat = 'Shooting Star' if _shooting_star(cur) else 'Bearish Engulfing'
        return 'SHORT', f'Sweep {pat}{" +vol" if has_volume else ""}'

    return None, None


# ---------------------------------------------------------------------------
# V39 — INSTITUTIONAL SWING REJECTION (bot_v19_C/estrategia_v19_C.py)
# ---------------------------------------------------------------------------
def senial_swing_rejection(df):
    """Macro EMA84/200 + Bollinger extremo + swing rejection 15 + RSI momentum
    + pullback EMA21 + patrón + volumen. Verbatim de v19_C (con su gate final
    RSI<65 LONG / >35 SHORT y sl_val>=ATR)."""
    if len(df) < 25:
        return None, None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    rsi = cur['RSI']

    # LONG
    if cur['EMA_84'] >= cur['EMA_200']:  # macro alcista requerido (>=, el código usa <return)
        # Bollinger extremo: al menos una de las 2 últimas perforó BB_LOWER
        if not (cur['low'] > cur['BB_LOWER'] and prev['low'] > prev['BB_LOWER']):
            # Swing rejection: curr.low <= swing_low_15 de prev, y no cerró bajo la banda
            if not (cur['low'] > prev['Swing_Low_15'] or cur['close'] <= cur['BB_LOWER']):
                # RSI momentum creciente
                if cur['RSI'] >= prev['RSI']:
                    pullback = cur['low'] < cur['EMA_21']
                    hm, en, ms = _hammer(cur), _bull_engulf(cur, prev), _morning_star(cur, prev, prev2)
                    if pullback and (hm or en or ms) and cur['volume'] >= cur['Volume_MA']:
                        if rsi < 65:
                            pat = 'Morning Star' if ms else ('Bullish Engulfing' if en else 'Bullish Hammer')
                            return 'LONG', f'SwingRej {pat}'

    # SHORT
    if cur['EMA_84'] <= cur['EMA_200']:
        if not (cur['high'] < cur['BB_UPPER'] and prev['high'] < prev['BB_UPPER']):
            if not (cur['high'] < prev['Swing_High_15'] or cur['close'] >= cur['BB_UPPER']):
                if cur['RSI'] <= prev['RSI']:
                    pullback = cur['high'] > cur['EMA_21']
                    ss, en, es = _shooting_star(cur), _bear_engulf(cur, prev), _evening_star(cur, prev, prev2)
                    if pullback and (ss or en or es) and cur['volume'] >= cur['Volume_MA']:
                        if rsi > 35:
                            pat = 'Evening Star' if es else ('Bearish Engulfing' if en else 'Shooting Star')
                            return 'SHORT', f'SwingRej {pat}'

    return None, None


# ---------------------------------------------------------------------------
# V40 — MACD STACK (bot_v18_C/estrategia_v18_C.py) — MACD como filtro dentro de
# un stack (NO aislado — ver nota de honestidad en el pre-registro de el libro)
# ---------------------------------------------------------------------------
def senial_macd_stack(df):
    """Macro EMA84/200 + MACD_Hist creciente y del signo correcto + RSI momentum
    + pullback EMA21 + patrón + volumen. Verbatim de v18_C."""
    if len(df) < 5:
        return None, None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    rsi = cur['RSI']

    # LONG
    if cur['EMA_84'] >= cur['EMA_200']:
        if cur['MACD_Hist'] > 0 and cur['MACD_Hist'] >= prev['MACD_Hist']:
            if cur['RSI'] >= prev['RSI']:
                pullback = cur['low'] < cur['EMA_21']
                hm, en, ms = _hammer(cur), _bull_engulf(cur, prev), _morning_star(cur, prev, prev2)
                if pullback and (hm or en or ms) and cur['volume'] >= cur['Volume_MA']:
                    if rsi < 65:
                        pat = 'Morning Star' if ms else ('Bullish Engulfing' if en else 'Bullish Hammer')
                        return 'LONG', f'MACD {pat}'

    # SHORT
    if cur['EMA_84'] <= cur['EMA_200']:
        if cur['MACD_Hist'] < 0 and cur['MACD_Hist'] <= prev['MACD_Hist']:
            if cur['RSI'] <= prev['RSI']:
                pullback = cur['high'] > cur['EMA_21']
                ss, en, es = _shooting_star(cur), _bear_engulf(cur, prev), _evening_star(cur, prev, prev2)
                if pullback and (ss or en or es) and cur['volume'] >= cur['Volume_MA']:
                    if rsi > 35:
                        pat = 'Evening Star' if es else ('Bearish Engulfing' if en else 'Shooting Star')
                        return 'SHORT', f'MACD {pat}'

    return None, None

def senial_v18_a(df):
    """V18_A: Bollinger Extremo.
    Macro EMA84/200 + Bollinger extremo + RSI momentum + pullback EMA21 + patrón + volumen."""
    if len(df) < 5:
        return None, None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    rsi = cur['RSI']
    
    # LONG
    if cur['EMA_84'] >= cur['EMA_200']:
        if not (cur['low'] > cur['BB_LOWER'] and prev['low'] > prev['BB_LOWER']):
            if cur['RSI'] >= prev['RSI']:
                pullback = cur['low'] < cur['EMA_21']
                hm, en, ms = _hammer(cur), _bull_engulf(cur, prev), _morning_star(cur, prev, prev2)
                if pullback and (hm or en or ms) and cur['volume'] >= cur['Volume_MA']:
                    if rsi < 65:
                        pat = 'Morning Star' if ms else ('Bullish Engulfing' if en else 'Bullish Hammer')
                        return 'LONG', f'BB {pat}'
                        
    # SHORT
    if cur['EMA_84'] <= cur['EMA_200']:
        if not (cur['high'] < cur['BB_UPPER'] and prev['high'] < prev['BB_UPPER']):
            if cur['RSI'] <= prev['RSI']:
                pullback = cur['high'] > cur['EMA_21']
                ss, en, es = _shooting_star(cur), _bear_engulf(cur, prev), _evening_star(cur, prev, prev2)
                if pullback and (ss or en or es) and cur['volume'] >= cur['Volume_MA']:
                    if rsi > 35:
                        pat = 'Evening Star' if es else ('Bearish Engulfing' if en else 'Shooting Star')
                        return 'SHORT', f'BB {pat}'
                        
    return None, None

def senial_v17_c(df):
    """V17_C: RSI Momentum.
    EMA84/200 + RSI creciente + pullback EMA21 + patrón + volumen."""
    if len(df) < 5:
        return None, None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    # LONG
    if cur['EMA_84'] >= cur['EMA_200']:
        if cur['RSI'] >= prev['RSI']:
            pullback = cur['low'] < cur['EMA_21']
            hm, en, ms = _hammer(cur), _bull_engulf(cur, prev), _morning_star(cur, prev, prev2)
            if pullback and (hm or en or ms) and cur['volume'] >= cur['Volume_MA']:
                pat = 'Morning Star' if ms else ('Bullish Engulfing' if en else 'Bullish Hammer')
                return 'LONG', f'RSI-Mom {pat}'

    # SHORT
    if cur['EMA_84'] <= cur['EMA_200']:
        if cur['RSI'] <= prev['RSI']:
            pullback = cur['high'] > cur['EMA_21']
            ss, en, es = _shooting_star(cur), _bear_engulf(cur, prev), _evening_star(cur, prev, prev2)
            if pullback and (ss or en or es) and cur['volume'] >= cur['Volume_MA']:
                pat = 'Evening Star' if es else ('Bearish Engulfing' if en else 'Shooting Star')
                return 'SHORT', f'RSI-Mom {pat}'

    return None, None

def senial_v22(df):
    """V22: Three-Door System.
    Importa dinámicamente la estrategia completa de V22 y mapea sus 3 puertas."""
    import sys
    import os
    # Add root folder to sys.path to import V22 modules
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
    
    from bot_alpha_portfolio.v22.estrategia_v22_Master import compute_signals_and_trades, compute_indicators
    
    # Asegurarnos de que el df tiene los indicadores propios de V22 calculados
    # Si compute_indicators falla por falta de columnas como volume o high/low/open/close, 
    # ya deberian estar ahí.
    df_v22 = compute_indicators(df)
    
    direction, trade_dict = compute_signals_and_trades(df_v22)
    if direction:
        # Extraer el motivo/patrón
        patron = trade_dict.get('pattern', f"V22_{trade_dict.get('puerta', '?')}")
        return direction, patron
        
    return None, None

DISPATCH = {
    'sweep': senial_sweep,
    'swing_rej': senial_swing_rejection,
    'macd_stack': senial_macd_stack,
    'v17_c': senial_v17_c,
    'v18_a': senial_v18_a,
    'v22': senial_v22
}
