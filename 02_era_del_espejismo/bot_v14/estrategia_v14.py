import pandas as pd
import numpy as np

# === CONFIGURACIÓN GLOBAL DEL MOTOR V14 (PRICE ACTION HUMANO) ===
INTERVAL = '15m'
LIMIT = 1000

ATR_LEN = 14

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # 1. ATR para métricas informativas y SL dinámico
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    df['TR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df['ATR'] = df['TR'].rolling(window=ATR_LEN).mean()

    # 2. EMAs Macro (Simulando 1H en 15m)
    # EMA 21 en 1H = EMA 84 en 15m
    # EMA 50 en 1H = EMA 200 en 15m
    df['EMA_84'] = df['close'].ewm(span=84, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # 3. EMA Micro (Tendencia local 15m)
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()

    # 4. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df

def is_bullish_hammer(candle):
    body = abs(candle['close'] - candle['open'])
    lower_shadow = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
    upper_shadow = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
    if body == 0: body = 0.0001
    if lower_shadow > (2 * body) and upper_shadow < body:
        return True
    return False

def is_bearish_shooting_star(candle):
    body = abs(candle['close'] - candle['open'])
    lower_shadow = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
    upper_shadow = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
    if body == 0: body = 0.0001
    if upper_shadow > (2 * body) and lower_shadow < body:
        return True
    return False

def is_bullish_engulfing(current, prev):
    prev_is_red = prev['close'] < prev['open']
    curr_is_green = current['close'] > current['open']
    engulfs = current['close'] > prev['open'] and current['open'] < prev['close']
    return prev_is_red and curr_is_green and engulfs

def is_bearish_engulfing(current, prev):
    prev_is_green = prev['close'] > prev['open']
    curr_is_red = current['close'] < current['open']
    engulfs = current['close'] < prev['open'] and current['open'] > prev['close']
    return prev_is_green and curr_is_red and engulfs

def is_morning_star(curr, prev, prev2):
    # prev2 is red, prev is small body (doji/spin), curr is green closing well inside prev2
    prev2_red = prev2['close'] < prev2['open']
    curr_green = curr['close'] > curr['open']
    prev_body = abs(prev['close'] - prev['open'])
    prev2_body = abs(prev2['close'] - prev2['open'])
    if prev_body == 0: prev_body = 0.0001
    star_condition = prev_body < (prev2_body * 0.5)
    reversal = curr['close'] > ((prev2['open'] + prev2['close'])/2)
    return prev2_red and curr_green and star_condition and reversal

def is_evening_star(curr, prev, prev2):
    # prev2 is green, prev is small body, curr is red closing well inside prev2
    prev2_green = prev2['close'] > prev2['open']
    curr_red = curr['close'] < curr['open']
    prev_body = abs(prev['close'] - prev['open'])
    prev2_body = abs(prev2['close'] - prev2['open'])
    if prev_body == 0: prev_body = 0.0001
    star_condition = prev_body < (prev2_body * 0.5)
    reversal = curr['close'] < ((prev2['open'] + prev2['close'])/2)
    return prev2_green and curr_red and star_condition and reversal

def detect_v14_setup(df: pd.DataFrame, direction: str):
    if len(df) < 5:
        return False, 0.0, ""
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    # Filtro Macro (1H)
    uptrend_macro = curr['EMA_84'] > curr['EMA_200']
    downtrend_macro = curr['EMA_84'] < curr['EMA_200']
    
    pattern_name = ""
    conviction = 0
    
    if direction == 'LONG':
        if not uptrend_macro: return False, 0.0, ""
        
        # Evaluar micro tendencia (pullback)
        pullback = curr['low'] < curr['EMA_21'] # tocamos o perforamos la 21
        
        has_hammer = is_bullish_hammer(curr)
        has_engulfing = is_bullish_engulfing(curr, prev)
        has_mstar = is_morning_star(curr, prev, prev2)
        
        if pullback and (has_hammer or has_engulfing or has_mstar):
            if has_mstar: pattern_name = "Morning Star"; conviction = 90
            elif has_engulfing: pattern_name = "Bullish Engulfing"; conviction = 85
            else: pattern_name = "Bullish Hammer"; conviction = 80
            return True, conviction, pattern_name
            
    elif direction == 'SHORT':
        if not downtrend_macro: return False, 0.0, ""
        
        # Evaluar micro tendencia (pullback)
        pullback = curr['high'] > curr['EMA_21'] # tocamos o perforamos la 21
        
        has_sstar = is_bearish_shooting_star(curr)
        has_engulfing = is_bearish_engulfing(curr, prev)
        has_estar = is_evening_star(curr, prev, prev2)
        
        if pullback and (has_sstar or has_engulfing or has_estar):
            if has_estar: pattern_name = "Evening Star"; conviction = 90
            elif has_engulfing: pattern_name = "Bearish Engulfing"; conviction = 85
            else: pattern_name = "Shooting Star"; conviction = 80
            return True, conviction, pattern_name

    return False, 0.0, ""

def compute_signals_and_trades(df: pd.DataFrame, current_balance: float, risk_percent: float):
    if len(df) < 200: return None, None
    latest = df.iloc[-1]
    c = latest['close']
    atr = latest.get('ATR', 0)
    rsi = latest.get('RSI', 50)
    
    if pd.isna(atr) or atr == 0: return None, None
    
    is_long, conviccion_long, patron_long = detect_v14_setup(df, 'LONG')
    if is_long and rsi < 65: # Relajamos el RSI para capturar pullbacks en tendencias fuertes
        sl_price = df.tail(5)['low'].min() - (atr * 1.5) # SL dinámico bajo el pivot
        sl_val = c - sl_price
        if sl_val < atr * 1.0: return None, None # Mechas puras, no entrar
            
        qty = (current_balance * risk_percent) / sl_val if sl_val > 0 else 0
        tp_1r = c + sl_val
        
        # Devolvemos el objetivo 1R como TP para el cierre parcial
        return 'LONG', {
            'action': 'BUY', 'entry_type': 'MARKET', 'entry_price': c,
            'qty': qty, 'stop_loss': sl_price, 'take_profit': tp_1r,
            'conviccion': conviccion_long, 
            'metrics': {'strategy': f'v14_long_{patron_long.replace(" ", "_").lower()}', 'sl_dist': sl_val}
        }
        
    is_short, conviccion_short, patron_short = detect_v14_setup(df, 'SHORT')
    if is_short and rsi > 35:
        sl_price = df.tail(5)['high'].max() + (atr * 1.5)
        sl_val = sl_price - c
        if sl_val < atr * 1.0: return None, None
            
        qty = (current_balance * risk_percent) / sl_val if sl_val > 0 else 0
        tp_1r = c - sl_val
        
        return 'SHORT', {
            'action': 'SELL', 'entry_type': 'MARKET', 'entry_price': c,
            'qty': qty, 'stop_loss': sl_price, 'take_profit': tp_1r,
            'conviccion': conviccion_short,
            'metrics': {'strategy': f'v14_short_{patron_short.replace(" ", "_").lower()}', 'sl_dist': sl_val}
        }
        
    return None, None
