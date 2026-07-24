import pandas as pd
import numpy as np

INTERVAL = '1h'

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # 1. Moving Averages
    df['MA_7'] = df['close'].rolling(window=7).mean()
    df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['MA_99'] = df['close'].rolling(window=99).mean()
    
    # 2. Donchian Channel (Support/Resistance) - 24 periods (V2: reduced from 48 for higher signal frequency)
    df['Donchian_High'] = df['high'].rolling(window=24).max().shift(1)
    df['Donchian_Low'] = df['low'].rolling(window=24).min().shift(1)
    
    # 4. Volume MA (20 periods) — used by Puerta B for impulse confirmation
    df['Volume_MA'] = df['volume'].rolling(window=20).mean()
    
    # 3. MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    # Pre-calculate body and wick metrics
    df['Body'] = abs(df['close'] - df['open'])
    df['Is_Green'] = df['close'] > df['open']
    df['Is_Red'] = df['close'] < df['open']
    
    return df

def compute_indicators(df):
    return calculate_indicators(df)

def check_multi_candle_exhaustion(df: pd.DataFrame, position_type: str = 'LONG') -> bool:
    """
    Evalúa el patrón de agotamiento sobre las últimas velas del DataFrame de forma bidireccional.
    """
    if len(df) < 5:
        return False
        
    idx = len(df) - 1
    
    if position_type == 'LONG':
        # MACD debe estar cruzado a la baja
        macd_is_down = df['MACD'].iloc[idx] < df['MACD_Signal'].iloc[idx]
        if not macd_is_down:
            return False
            
        # Identificar la "Vela Verde Ancla"
        anchor_idx = -1
        highest_high = -1
        for i in range(idx-3, idx):
            if df['Is_Green'].iloc[i] and df['high'].iloc[i] > highest_high:
                highest_high = df['high'].iloc[i]
                anchor_idx = i
                
        if anchor_idx == -1: return False
            
        anchor_body = df['Body'].iloc[anchor_idx]
        if anchor_body == 0: anchor_body = df['close'].iloc[anchor_idx] * 0.0001
            
        candles_after_anchor = idx - anchor_idx
        if candles_after_anchor < 2: return False
            
        valid_structure = True
        lowest_low = df['low'].iloc[anchor_idx]
        prev_high = df['high'].iloc[anchor_idx]
        prev_low = df['low'].iloc[anchor_idx]
        
        for i in range(anchor_idx + 1, idx + 1):
            curr_high = df['high'].iloc[i]
            curr_low = df['low'].iloc[i]
            if curr_high >= prev_high or curr_low >= prev_low:
                valid_structure = False
                break
            if curr_low < lowest_low:
                lowest_low = curr_low
            prev_high = curr_high
            prev_low = curr_low
            
        if not valid_structure: return False
            
        accumulated_drop = highest_high - lowest_low
        if accumulated_drop > (2.0 * anchor_body):
            return True
            
        return False

    elif position_type == 'SHORT':
        # MACD debe estar cruzado al alza
        macd_is_up = df['MACD'].iloc[idx] > df['MACD_Signal'].iloc[idx]
        if not macd_is_up:
            return False
            
        # Identificar la "Vela Roja Ancla"
        anchor_idx = -1
        lowest_low = float('inf')
        for i in range(idx-3, idx):
            if df['Is_Red'].iloc[i] and df['low'].iloc[i] < lowest_low:
                lowest_low = df['low'].iloc[i]
                anchor_idx = i
                
        if anchor_idx == -1: return False
            
        anchor_body = df['Body'].iloc[anchor_idx]
        if anchor_body == 0: anchor_body = df['close'].iloc[anchor_idx] * 0.0001
            
        candles_after_anchor = idx - anchor_idx
        if candles_after_anchor < 2: return False
            
        valid_structure = True
        highest_high = df['high'].iloc[anchor_idx]
        prev_high = df['high'].iloc[anchor_idx]
        prev_low = df['low'].iloc[anchor_idx]
        
        for i in range(anchor_idx + 1, idx + 1):
            curr_high = df['high'].iloc[i]
            curr_low = df['low'].iloc[i]
            # En SHORT, agotamiento significa que ya no hace bajos más bajos ni altos más bajos.
            # Hace altos más altos y bajos más altos.
            if curr_high <= prev_high or curr_low <= prev_low:
                valid_structure = False
                break
            if curr_high > highest_high:
                highest_high = curr_high
            prev_high = curr_high
            prev_low = curr_low
            
        if not valid_structure: return False
            
        accumulated_rise = highest_high - lowest_low
        if accumulated_rise > (2.0 * anchor_body):
            return True
            
        return False

    return False

def detect_candle_pattern(df: pd.DataFrame):
    """
    Detecta patrones de vela de alta calidad para la Puerta B:
    - Marubozu: cuerpo > 80% del rango total. Impulso limpio sin duda.
    - Engulfing: cuerpo actual contiene completamente el cuerpo anterior y son de colores opuestos.
    Retorna: ('LONG_B', 0.01), ('SHORT_B', 0.01) o (None, 0)
    """
    if len(df) < 3:
        return None, 0

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    candle_range = curr['high'] - curr['low']
    if candle_range <= 0:
        return None, 0

    body = curr['Body']
    is_green = curr['Is_Green']
    is_red = curr['Is_Red']

    # --- Marubozu ---
    is_marubozu_bull = is_green and (body / candle_range) >= 0.80
    is_marubozu_bear = is_red  and (body / candle_range) >= 0.80

    # --- Engulfing ---
    prev_body_top    = max(prev['open'], prev['close'])
    prev_body_bottom = min(prev['open'], prev['close'])
    curr_body_top    = max(curr['open'], curr['close'])
    curr_body_bottom = min(curr['open'], curr['close'])

    is_engulfing_bull = (
        is_green and prev['Is_Red'] and
        curr_body_bottom < prev_body_bottom and
        curr_body_top    > prev_body_top
    )
    is_engulfing_bear = (
        is_red and prev['Is_Green'] and
        curr_body_top    > prev_body_top and
        curr_body_bottom < prev_body_bottom
    )

    if is_marubozu_bull or is_engulfing_bull:
        return 'LONG_B', 0.01
    elif is_marubozu_bear or is_engulfing_bear:
        return 'SHORT_B', 0.01

    return None, 0

def check_exit_conditions_v21(df: pd.DataFrame, position_type: str, entry_price: float):
    # Función exportable si el orquestador la requiere para cerrar.
    # El simulador actual usa take_profit y stop_loss estáticos, 
    # pero podríamos integrarlo en el motor.
    pass

def compute_signals_and_trades(df: pd.DataFrame, current_balance: float = 500.0, risk_percent: float = 0.02):
    """
    V2: Sistema de Dos Puertas Paralelas Bidireccional.
    Puerta A (Alta Convicción): Breakout Donchian 24h + MA align + MACD. Riesgo: risk_percent (default 2%).
    Puerta B (Impulso de Vela): Marubozu/Engulfing + lado correcto MA99 + Volumen. Riesgo: 1% fijo. TP: 1R.
    Prioridad: Puerta A > Puerta B. Si A califica, no se evalúa B.
    """
    try:
        if len(df) < 100:
            return None, None

        current_price = df['close'].iloc[-1]

        # ===================================================================
        # PUERTA A — BREAKOUT INSTITUCIONAL (riesgo: risk_percent)
        # ===================================================================

        # A-LONG: precio rompe Donchian High + MAs alcistas + MACD alcista
        breakout_long   = current_price > df['Donchian_High'].iloc[-1]
        ma_align_long   = df['MA_7'].iloc[-1] > df['MA_99'].iloc[-1] and df['EMA_9'].iloc[-1] > df['MA_99'].iloc[-1]
        macd_bullish    = df['MACD'].iloc[-1] > df['MACD_Signal'].iloc[-1] and df['MACD_Hist'].iloc[-1] > 0

        if breakout_long and ma_align_long and macd_bullish:
            donchian_low = df['Donchian_Low'].iloc[-1]
            sl_price     = max(donchian_low, current_price * 0.97)
            risk_amount  = current_price - sl_price
            if risk_amount <= 0: risk_amount = current_price * 0.03
            tp_price     = current_price + (risk_amount * 3.0)
            qty          = (current_balance * risk_percent) / risk_amount
            return 'LONG', {
                'type': 'LONG', 'puerta': 'A',
                'entry_price': current_price,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'qty': qty, 'conviccion': 95.0,
                'metrics': {'trend_w': 100, 'mr_w': 0},
                'pattern': 'V21_A Donchian Breakout'
            }

        # A-SHORT: precio rompe Donchian Low + MAs bajistas + MACD bajista
        breakout_short  = current_price < df['Donchian_Low'].iloc[-1]
        ma_align_short  = df['MA_7'].iloc[-1] < df['MA_99'].iloc[-1] and df['EMA_9'].iloc[-1] < df['MA_99'].iloc[-1]
        macd_bearish    = df['MACD'].iloc[-1] < df['MACD_Signal'].iloc[-1] and df['MACD_Hist'].iloc[-1] < 0

        if breakout_short and ma_align_short and macd_bearish:
            donchian_high = df['Donchian_High'].iloc[-1]
            sl_price      = min(donchian_high, current_price * 1.03)
            risk_amount   = sl_price - current_price
            if risk_amount <= 0: risk_amount = current_price * 0.03
            tp_price      = current_price - (risk_amount * 3.0)
            qty           = (current_balance * risk_percent) / risk_amount
            return 'SHORT', {
                'type': 'SHORT', 'puerta': 'A',
                'entry_price': current_price,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'qty': qty, 'conviccion': 95.0,
                'metrics': {'trend_w': 100, 'mr_w': 0},
                'pattern': 'V21_A Donchian Breakdown'
            }

        # ===================================================================
        # PUERTA B — IMPULSO DE VELA (riesgo: 1% fijo, TP: 1R)
        # ===================================================================
        pattern_signal, b_risk = detect_candle_pattern(df)

        if pattern_signal:
            # Filtro de lado correcto de MA99
            price_above_ma99 = current_price > df['MA_99'].iloc[-1]
            price_below_ma99 = current_price < df['MA_99'].iloc[-1]

            # Filtro de volumen condicional (solo si Volume_MA está disponible y > 0)
            vol_ok = True
            if 'Volume_MA' in df.columns:
                vol_ma = df['Volume_MA'].iloc[-1]
                if vol_ma and vol_ma > 0:
                    vol_ok = df['volume'].iloc[-1] > vol_ma

            if pattern_signal == 'LONG_B' and price_above_ma99 and vol_ok:
                # SL estructural: mínimo de la vela actual o -2% máximo
                sl_price    = max(df['low'].iloc[-1], current_price * 0.98)
                risk_amount = current_price - sl_price
                if risk_amount <= 0: risk_amount = current_price * 0.02
                tp_price    = current_price + risk_amount  # TP = 1R
                qty         = (current_balance * b_risk) / risk_amount
                return 'LONG', {
                    'type': 'LONG', 'puerta': 'B',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 75.0,
                    'metrics': {'trend_w': 70, 'mr_w': 30},
                    'pattern': 'V21_B Candle Impulse'
                }

            elif pattern_signal == 'SHORT_B' and price_below_ma99 and vol_ok:
                sl_price    = min(df['high'].iloc[-1], current_price * 1.02)
                risk_amount = sl_price - current_price
                if risk_amount <= 0: risk_amount = current_price * 0.02
                tp_price    = current_price - risk_amount  # TP = 1R
                qty         = (current_balance * b_risk) / risk_amount
                return 'SHORT', {
                    'type': 'SHORT', 'puerta': 'B',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 75.0,
                    'metrics': {'trend_w': 70, 'mr_w': 30},
                    'pattern': 'V21_B Candle Impulse'
                }

        return None, None

    except Exception as e:
        print(f"Error evaluando señales V21_Master V2: {e}")
        return None, None
