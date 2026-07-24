import pandas as pd
import numpy as np

# === CONFIGURACIÓN GLOBAL DEL MOTOR V13 (HÍBRIDO: CUANTITATIVO + PRICE ACTION) ===
INTERVAL = '1h'
LIMIT = 1000

# Parámetros de Ventanas Temporales
SWING_WINDOW = 10         # Periodo para determinar Swing Highs/Lows
VOLUME_MOMENTUM_LEN = 10  # Media de volumen para confirmar el retorno tras el sweep
ATR_LEN = 14
SWEEP_MAX_CANDLES = 7     # Cuántas velas después del sweep permitimos para la confirmación

# === CÁLCULO DE INDICADORES Y ESTRUCTURA ===
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # 1. ATR para métricas informativas y SL dinámico
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    df['TR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df['ATR'] = df['TR'].rolling(window=ATR_LEN).mean()

    # 2. Identificar Swing Highs y Lows Locales (Liquidity Pools)
    df['Swing_High'] = df['high'].rolling(window=SWING_WINDOW, center=True).max()
    df['Swing_Low'] = df['low'].rolling(window=SWING_WINDOW, center=True).min()
    
    # Rellenar (forward fill) para tener los niveles pasados sin lookahead
    df['Last_Swing_High'] = df['high'].rolling(window=SWING_WINDOW).max().shift(1)
    df['Last_Swing_Low'] = df['low'].rolling(window=SWING_WINDOW).min().shift(1)

    # 3. Volumen Estricto (Volumen > 1.5 * media para atrapar sweeps institucionales confirmados)
    df['Vol_SMA'] = df['volume'].rolling(window=VOLUME_MOMENTUM_LEN).mean()
    df['Vol_Spike'] = df['volume'] > (df['Vol_SMA'] * 1.5)
    
    # 4. RSI (Dinámica de Kelly / Exits Tempranos / Filtro Mean Reversion)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 5. EMA para validación de ineficiencia estructural (Mean Reversion)
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

    return df

# === DETECCIÓN DE PATRONES DE PRICE ACTION ===
def is_bullish_hammer(candle):
    body = abs(candle['close'] - candle['open'])
    lower_shadow = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
    upper_shadow = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
    
    # Cola inferior al menos 2 veces el cuerpo, y cuerpo en la parte superior
    if lower_shadow > (2 * body) and upper_shadow < body:
        return True
    return False

def is_bearish_shooting_star(candle):
    body = abs(candle['close'] - candle['open'])
    lower_shadow = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
    upper_shadow = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
    
    # Cola superior al menos 2 veces el cuerpo, y cuerpo en la parte inferior
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

# === DETECCIÓN HÍBRIDA: LIQUIDITY SWEEP + PRICE ACTION ===
def detect_hybrid_setup(df: pd.DataFrame, direction: str):
    if len(df) < SWEEP_MAX_CANDLES + 2:
        return False, 0.0, 0.0, ""
    
    window = df.tail(SWEEP_MAX_CANDLES + 1)
    current_bar = window.iloc[-1]
    prev_bar = window.iloc[-2]
    
    # Convicción inicial basada en el volumen
    base_conviction = 70.0
    pattern_name = ""
    
    if direction == 'LONG':
        swing_low_level = current_bar['Last_Swing_Low']
        sweep_occurred = any(window['low'] < swing_low_level)
        returned_inside = current_bar['close'] > swing_low_level
        has_volume = current_bar['Vol_Spike'] or prev_bar['Vol_Spike']
        
        # Validar patrón de velas (Price Action)
        has_hammer = is_bullish_hammer(current_bar)
        has_engulfing = is_bullish_engulfing(current_bar, prev_bar)
        
        if sweep_occurred and returned_inside and current_bar['close'] > current_bar['EMA_200'] and (has_hammer or has_engulfing):
            if has_hammer: 
                base_conviction += 15.0
                pattern_name = "Bullish Hammer"
            elif has_engulfing: 
                base_conviction += 10.0
                pattern_name = "Bullish Engulfing"
            
            if has_volume: base_conviction += 10.0
            
            # Filtro adicional de ineficiencia: si está muy por debajo de la EMA 21, aumenta la convicción
            dist_ema = (current_bar['EMA_21'] - current_bar['close']) / current_bar['EMA_21']
            if dist_ema > 0.01: # Más de 1% lejos de EMA21
                base_conviction += 5.0
            
            return True, swing_low_level, min(base_conviction, 100.0), pattern_name
            
    elif direction == 'SHORT':
        swing_high_level = current_bar['Last_Swing_High']
        sweep_occurred = any(window['high'] > swing_high_level)
        returned_inside = current_bar['close'] < swing_high_level
        has_volume = current_bar['Vol_Spike'] or prev_bar['Vol_Spike']
        
        # Validar patrón de velas (Price Action)
        has_shooting_star = is_bearish_shooting_star(current_bar)
        has_engulfing = is_bearish_engulfing(current_bar, prev_bar)
        
        if sweep_occurred and returned_inside and current_bar['close'] < current_bar['EMA_200'] and (has_shooting_star or has_engulfing):
            if has_shooting_star: 
                base_conviction += 15.0
                pattern_name = "Shooting Star"
            elif has_engulfing: 
                base_conviction += 10.0
                pattern_name = "Bearish Engulfing"
            
            if has_volume: base_conviction += 10.0
            
            # Filtro adicional de ineficiencia: si está muy por encima de la EMA 21, aumenta la convicción
            dist_ema = (current_bar['close'] - current_bar['EMA_21']) / current_bar['EMA_21']
            if dist_ema > 0.01: # Más de 1% lejos de EMA21
                base_conviction += 5.0

            return True, swing_high_level, min(base_conviction, 100.0), pattern_name

    return False, 0.0, 0.0, ""

# === MOTOR DE DECISIÓN V13 ===
def compute_signals_and_trades(df: pd.DataFrame, current_balance: float, risk_percent: float):
    if len(df) < 50: return None, None
    latest = df.iloc[-1]
    c = latest['close']
    atr = latest.get('ATR', 0)
    rsi = latest.get('RSI', 50)
    
    if pd.isna(atr) or atr == 0:
        return None, None
    
    # Validar LONG
    is_long, sl_level, conviccion_long, patron_long = detect_hybrid_setup(df, 'LONG')
    if is_long and rsi < 50 and (atr / c) > 0.008: # RSI más estricto asegura momentum neutral/bajista antes del sweep + filtro lateral
        # Para el Stop Loss, nos aseguramos de estar debajo del barrido reciente
        recent_low = df.tail(SWEEP_MAX_CANDLES)['low'].min()
        sl_price = recent_low - (atr * 1.0) # Colchón amplio por debajo del sweep
        sl_val = c - sl_price
        
        if sl_val <= 0: sl_val = atr * 1.5
            
        # Take profit agresivo pero Set-and-Forget: R:R 1:3
        tp_price = c + (sl_val * 3.0)
        qty = (current_balance * risk_percent) / sl_val if sl_val > 0 else 0
        
        return 'LONG', {
            'action': 'BUY', 'entry_type': 'MARKET', 'entry_price': c,
            'qty': qty, 'stop_loss': sl_price, 'take_profit': tp_price,
            'conviccion': round(conviccion_long, 2), 
            'metrics': {'strategy': f'hybrid_long_{patron_long.replace(" ", "_").lower()}', 'sl_dist': round(sl_val, 2), 'trend_w': 20, 'mr_w': 80}
        }
        
    # Validar SHORT
    is_short, sl_level, conviccion_short, patron_short = detect_hybrid_setup(df, 'SHORT')
    if is_short and rsi > 50 and (atr / c) > 0.008: # RSI más estricto para SHORT + filtro lateral
        recent_high = df.tail(SWEEP_MAX_CANDLES)['high'].max()
        sl_price = recent_high + (atr * 1.0) # Colchón amplio por encima del sweep
        sl_val = sl_price - c
        
        if sl_val <= 0: sl_val = atr * 1.5
            
        # Take profit agresivo pero Set-and-Forget: R:R 1:3
        tp_price = c - (sl_val * 3.0)
        qty = (current_balance * risk_percent) / sl_val if sl_val > 0 else 0
        
        return 'SHORT', {
            'action': 'SELL', 'entry_type': 'MARKET', 'entry_price': c,
            'qty': qty, 'stop_loss': sl_price, 'take_profit': tp_price,
            'conviccion': round(conviccion_short, 2),
            'metrics': {'strategy': f'hybrid_short_{patron_short.replace(" ", "_").lower()}', 'sl_dist': round(sl_val, 2), 'trend_w': 20, 'mr_w': 80}
        }
        
    return None, None
