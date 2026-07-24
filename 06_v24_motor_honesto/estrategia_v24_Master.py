import pandas as pd
import numpy as np

INTERVAL = '1h'

# Ventana usada para ubicar la volatilidad actual dentro de su propio histórico reciente
REGIME_LOOKBACK = 100


# =============================================================================
# INDICADORES
# =============================================================================
def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def _calculate_adx(df: pd.DataFrame, period: int = 14):
    high, low, close = df['high'], df['low'], df['close']

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx.fillna(0.0)


def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Medias móviles (estructura / sesgo de tendencia)
    df['MA_7'] = df['close'].rolling(window=7).mean()
    df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['MA_99'] = df['close'].rolling(window=99).mean()

    # 2. Canal de Donchian (Soporte/Resistencia) - 24 periodos
    df['Donchian_High'] = df['high'].rolling(window=24).max().shift(1)
    df['Donchian_Low'] = df['low'].rolling(window=24).min().shift(1)

    # 3. Volumen — confirmación de impulso (Puerta B)
    df['Volume_MA'] = df['volume'].rolling(window=20).mean()

    # 4. MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 5. Métricas de vela (cuerpo / color) — Puerta B
    df['Body'] = abs(df['close'] - df['open'])
    df['Is_Green'] = df['close'] > df['open']
    df['Is_Red'] = df['close'] < df['open']

    # ----- NUEVO V22: indicadores de RÉGIMEN y REVERSIÓN A LA MEDIA -----
    # 6. ATR / ATR% — volatilidad absoluta y relativa (clasificador de régimen)
    df['ATR'] = _calculate_atr(df, period=14)
    df['ATR_pct'] = (df['ATR'] / df['close']) * 100

    # 7. ADX — fuerza de tendencia (clasificador de régimen)
    df['ADX'] = _calculate_adx(df, period=14)

    # 8. Bandas de Bollinger (20, 2) — estructura de rango / objetivo de reversión (Puerta C)
    df['BB_Mid'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (bb_std * 2)
    df['BB_Lower'] = df['BB_Mid'] - (bb_std * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Mid'].replace(0, np.nan)

    # 9. RSI — extremos de sobrecompra / sobreventa (Puerta C)
    df['RSI'] = _calculate_rsi(df['close'], period=14)

    return df


def compute_indicators(df):
    return calculate_indicators(df)


# =============================================================================
# CLASIFICADOR DE RÉGIMEN (núcleo de la mejora V22)
# =============================================================================
def _emergente_direction(df: pd.DataFrame, idx: int):
    """
    Evalúa si la vela `idx` cumple las condiciones de tendencia emergente:
    ADX subiendo desde < 20 con pendiente mínima de 2 puntos en 3 velas, MACD
    histograma acelerando en una dirección, y precio del lado correcto de MA_99.

    Retorna 'LONG', 'SHORT' o None. Usado tanto por classify_regime (vela actual)
    como por compute_signals_and_trades (vela anterior, para confirmación).
    """
    if idx < 3 or 'MACD_Hist' not in df.columns or 'MA_99' not in df.columns or 'ADX' not in df.columns:
        return None

    adx_now = df['ADX'].iloc[idx]
    adx_1 = df['ADX'].iloc[idx - 1]
    adx_2 = df['ADX'].iloc[idx - 2]
    adx_rising_from_low = (
        adx_now > adx_1 > adx_2
        and adx_2 < 20
        and (adx_now - adx_2) >= 2.0
    )
    if not adx_rising_from_low:
        return None

    mh0 = df['MACD_Hist'].iloc[idx]
    mh1 = df['MACD_Hist'].iloc[idx - 1]
    mh2 = df['MACD_Hist'].iloc[idx - 2]
    price = df['close'].iloc[idx]
    ma99 = df['MA_99'].iloc[idx]

    if mh0 < mh1 < mh2 < 0 and price < ma99:
        return 'SHORT'
    if mh0 > mh1 > mh2 > 0 and price > ma99:
        return 'LONG'
    return None


def classify_regime(df: pd.DataFrame) -> str:
    """
    Clasifica el contexto actual del símbolo en uno de tres regímenes, combinando
    fuerza de tendencia (ADX) con la posición de la volatilidad actual (ATR%) dentro
    de su propio histórico reciente (percentil sobre REGIME_LOOKBACK velas).

    Retorna: 'TENDENCIA' | 'RANGO' | 'BAJA_VOLATILIDAD' | 'INDEFINIDO'

    - TENDENCIA:        ADX alto -> favorece estrategias de momentum/breakout (Puerta A/B).
    - RANGO:            ADX bajo + volatilidad media/alta -> oscilación entre soporte/resistencia,
                        favorece reversión a la media (Puerta C).
    - BAJA_VOLATILIDAD: ADX bajo + volatilidad comprimida (percentil bajo) -> mercado "dormido",
                        ideal para fades de bajo riesgo cerca de la media (Puerta C, tamaño reducido).
    """
    if len(df) < REGIME_LOOKBACK + 20 or 'ADX' not in df.columns:
        return 'INDEFINIDO'

    idx = len(df) - 1
    adx_now = df['ADX'].iloc[idx]
    atr_pct_now = df['ATR_pct'].iloc[idx]

    ventana = df['ATR_pct'].iloc[idx - REGIME_LOOKBACK: idx + 1]
    if ventana.isna().all():
        return 'INDEFINIDO'
    atr_percentile = (ventana < atr_pct_now).mean() * 100

    if adx_now >= 25:
        return 'TENDENCIA'

    # Early-trend gate: ADX rising from below 20 with min. 2-point slope over 3
    # candles + MACD histogram accelerating in one direction + price on the
    # correct side of MA99. Catches the first leg of a trend before ADX crosses
    # 25 (ADX lags by design).
    if _emergente_direction(df, idx):
        return 'TENDENCIA_EMERGENTE'

    if atr_percentile <= 35:
        return 'BAJA_VOLATILIDAD'
    else:
        return 'RANGO'


# =============================================================================
# PATRONES DE AGOTAMIENTO Y VELA (heredados de V21, sin cambios de lógica)
# =============================================================================
def check_multi_candle_exhaustion(df: pd.DataFrame, position_type: str = 'LONG') -> bool:
    """
    Evalúa el patrón de agotamiento sobre las últimas velas del DataFrame de forma bidireccional.
    """
    if len(df) < 5:
        return False

    idx = len(df) - 1

    if position_type == 'LONG':
        macd_is_down = df['MACD'].iloc[idx] < df['MACD_Signal'].iloc[idx]
        if not macd_is_down:
            return False

        anchor_idx = -1
        highest_high = -1
        for i in range(idx - 3, idx):
            if df['Is_Green'].iloc[i] and df['high'].iloc[i] > highest_high:
                highest_high = df['high'].iloc[i]
                anchor_idx = i

        if anchor_idx == -1:
            return False

        anchor_body = df['Body'].iloc[anchor_idx]
        if anchor_body == 0:
            anchor_body = df['close'].iloc[anchor_idx] * 0.0001

        candles_after_anchor = idx - anchor_idx
        if candles_after_anchor < 2:
            return False

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

        if not valid_structure:
            return False

        accumulated_drop = highest_high - lowest_low
        if accumulated_drop > (2.0 * anchor_body):
            return True

        return False

    elif position_type == 'SHORT':
        macd_is_up = df['MACD'].iloc[idx] > df['MACD_Signal'].iloc[idx]
        if not macd_is_up:
            return False

        anchor_idx = -1
        lowest_low = float('inf')
        for i in range(idx - 3, idx):
            if df['Is_Red'].iloc[i] and df['low'].iloc[i] < lowest_low:
                lowest_low = df['low'].iloc[i]
                anchor_idx = i

        if anchor_idx == -1:
            return False

        anchor_body = df['Body'].iloc[anchor_idx]
        if anchor_body == 0:
            anchor_body = df['close'].iloc[anchor_idx] * 0.0001

        candles_after_anchor = idx - anchor_idx
        if candles_after_anchor < 2:
            return False

        valid_structure = True
        highest_high = df['high'].iloc[anchor_idx]
        prev_high = df['high'].iloc[anchor_idx]
        prev_low = df['low'].iloc[anchor_idx]

        for i in range(anchor_idx + 1, idx + 1):
            curr_high = df['high'].iloc[i]
            curr_low = df['low'].iloc[i]
            if curr_high <= prev_high or curr_low <= prev_low:
                valid_structure = False
                break
            if curr_high > highest_high:
                highest_high = curr_high
            prev_high = curr_high
            prev_low = curr_low

        if not valid_structure:
            return False

        accumulated_rise = highest_high - lowest_low
        if accumulated_rise > (2.0 * anchor_body):
            return True

        return False

    return False


def detect_candle_pattern(df: pd.DataFrame, b_risk=0.01):
    """
    Puerta B — Impulso de Vela (Marubozu / Engulfing). Sin cambios respecto a V21.
    Retorna: ('LONG_B', b_risk), ('SHORT_B', b_risk) o (None, 0)
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

    is_marubozu_bull = is_green and (body / candle_range) >= 0.80
    is_marubozu_bear = is_red and (body / candle_range) >= 0.80

    prev_body_top = max(prev['open'], prev['close'])
    prev_body_bottom = min(prev['open'], prev['close'])
    curr_body_top = max(curr['open'], curr['close'])
    curr_body_bottom = min(curr['open'], curr['close'])

    is_engulfing_bull = (
        is_green and prev['Is_Red'] and
        curr_body_bottom < prev_body_bottom and
        curr_body_top > prev_body_top
    )
    is_engulfing_bear = (
        is_red and prev['Is_Green'] and
        curr_body_top > prev_body_top and
        curr_body_bottom < prev_body_bottom
    )

    if is_marubozu_bull or is_engulfing_bull:
        return 'LONG_B', 0.01
    elif is_marubozu_bear or is_engulfing_bear:
        return 'SHORT_B', 0.01

    return None, 0


# =============================================================================
# PUERTA C — REVERSIÓN A LA MEDIA (NUEVA EN V22)
# Activa únicamente cuando el régimen del símbolo es RANGO o BAJA_VOLATILIDAD,
# es decir, exactamente en los contextos donde la Puerta A (breakout) y la
# Puerta B (impulso) casi nunca disparan — esto es lo que eleva la cadencia
# de participación diaria sin relajar los filtros de alta convicción existentes.
# =============================================================================
def detect_mean_reversion_signal(df: pd.DataFrame):
    """
    Detecta extremos de precio mediante el cruce de dos confirmaciones:
      1. El precio toca/perfora una banda de Bollinger (extremo estructural).
      2. El RSI(14) confirma sobrecompra/sobreventa (extremo de momentum).
    La apuesta es al retorno hacia la media móvil (BB_Mid), con objetivo y
    riesgo más cortos que Puertas A/B — coherente con un régimen sin tendencia.

    Retorna: ('LONG_C', riesgo) | ('SHORT_C', riesgo) | (None, 0)
    """
    if len(df) < 30:
        return None, 0

    curr = df.iloc[-1]
    rsi = curr.get('RSI', 50.0)
    price = curr['close']
    bb_low = curr.get('BB_Lower', price)
    bb_up = curr.get('BB_Upper', price)

    if pd.isna(bb_low) or pd.isna(bb_up) or pd.isna(rsi):
        return None, 0

    # Fade alcista: precio en/baja la banda inferior + RSI en sobreventa
    # Bloqueado si el histograma MACD lleva 3 velas acelerando a la baja:
    # oversold en una tendencia bajista activa no es un rebote, es una trampa.
    if price <= bb_low and rsi <= 32:
        if len(df) >= 4 and 'MACD_Hist' in df.columns:
            mh = df['MACD_Hist']
            if mh.iloc[-1] < mh.iloc[-2] < mh.iloc[-3] < 0:
                return None, 0
        return 'LONG_C', 0.004

    # Fade bajista: precio en/sobre la banda superior + RSI en sobrecompra
    # Bloqueado si el histograma MACD lleva 3 velas acelerando al alza.
    if price >= bb_up and rsi >= 68:
        if len(df) >= 4 and 'MACD_Hist' in df.columns:
            mh = df['MACD_Hist']
            if mh.iloc[-1] > mh.iloc[-2] > mh.iloc[-3] > 0:
                return None, 0
        return 'SHORT_C', 0.004

    return None, 0


# =============================================================================
# ORQUESTADOR DE SEÑALES — Sistema de Tres Puertas + Clasificación de Régimen
# =============================================================================
def compute_signals_and_trades(df: pd.DataFrame, current_balance: float = 500.0, risk_percent: float = 0.01):
    """
    V22: Sistema de Tres Puertas guiado por régimen de mercado.

    Puerta A (Alta Convicción / TENDENCIA):  Breakout Donchian 24h + alineación de medias + MACD.
                                              Riesgo: risk_percent (≈1%). TP: 3R. Conviccion: 95%.
                                              Gateada a régimen == TENDENCIA (ver nota junto al código:
                                              el primer backtest forense mostró que disparaba también
                                              en RANGO con 23.8% WR, arrastrando el PF agregado).
    Puerta B (Impulso de Vela / TENDENCIA):   Marubozu/Engulfing + lado correcto de MA99 + volumen.
                                              Riesgo: 1% fijo. TP: 1R. Conviccion: 75%.
    Puerta C (Reversión a la Media / RANGO o BAJA_VOLATILIDAD — NUEVA):
                                              Fade de extremos (Bollinger + RSI) hacia la media.
                                              Riesgo: 0.4% fijo (reducido). TP: retorno a BB_Mid.
                                              Conviccion: 60%. Solo se evalúa si el régimen NO es
                                              de tendencia — es decir, en los huecos donde A y B
                                              casi nunca participan.

    Prioridad: A > B > C. El régimen detectado se adjunta a TODA señal devuelta para
    trazabilidad forense y para los avisos de Telegram (saber "por qué" se operó).
    """
    try:
        if len(df) < 100:
            return None, None

        current_price = df['close'].iloc[-1]
        regimen = classify_regime(df)

        # ===================================================================
        # PUERTA A — BREAKOUT INSTITUCIONAL (riesgo: risk_percent)
        # Acotada a régimen TENDENCIA: el primer backtest forense de V22 mostró
        # que A disparaba también en RANGO (21 trades, 23.8% WR, -$375) — una
        # herramienta de momentum cazando rupturas falsas en mercado lateral.
        # Gatearla a TENDENCIA elimina ese arrastre y libera cupo de exposición
        # correlacionada para que Puerta C opere donde sí tiene ventaja (RANGO).
        # ===================================================================
        es_tendencia = (regimen == 'TENDENCIA')

        # TENDENCIA_EMERGENTE: exige confirmación de 2 velas consecutivas en la
        # misma dirección antes de habilitar Puerta A. Evita disparar en el primer
        # tick de ADX/MACD que luego se revierte (falsa partida).
        if regimen == 'TENDENCIA_EMERGENTE':
            idx_now = len(df) - 1
            dir_now = _emergente_direction(df, idx_now)
            dir_prev = _emergente_direction(df, idx_now - 1)
            # Filtro de confirmación por volumen (2026-06-10): _emergente_direction()
            # detecta la primera pierna de una tendencia (ADX subiendo desde <20 +
            # MACD acelerando), pero sin participación real (volumen) algunas de
            # estas señales tempranas son ruido que revierte de inmediato. Exigir
            # volumen >= 1.5x su media de 20 velas (escalada del umbral 1.0x que ya
            # usa el vol_ok de Puerta B) filtra esos falsos arranques.
            vol_confirmado = False
            if 'Volume_MA' in df.columns:
                vol_ma = df['Volume_MA'].iloc[idx_now]
                if vol_ma and vol_ma > 0:
                    vol_confirmado = df['volume'].iloc[idx_now] >= vol_ma * 1.5
            if dir_now and dir_now == dir_prev and vol_confirmado:
                es_tendencia = True

        breakout_long = current_price > df['Donchian_High'].iloc[-1]
        ma_align_long = df['MA_7'].iloc[-1] > df['MA_99'].iloc[-1] and df['EMA_9'].iloc[-1] > df['MA_99'].iloc[-1]
        macd_bullish = df['MACD'].iloc[-1] > df['MACD_Signal'].iloc[-1] and df['MACD_Hist'].iloc[-1] > 0

        # TENDENCIA (no emergente): exige que las 3 condiciones también se hayan
        # cumplido en la vela anterior. Filtra picos de ruptura de una sola vela
        # que revierten de inmediato (TENDENCIA_EMERGENTE ya tiene su propio gate
        # de 2 velas via _emergente_direction()).
        confirmacion_long = True
        if regimen == 'TENDENCIA':
            prev_breakout_long = df['close'].iloc[-2] > df['Donchian_High'].iloc[-2]
            prev_ma_align_long = df['MA_7'].iloc[-2] > df['MA_99'].iloc[-2] and df['EMA_9'].iloc[-2] > df['MA_99'].iloc[-2]
            prev_macd_bullish = df['MACD'].iloc[-2] > df['MACD_Signal'].iloc[-2] and df['MACD_Hist'].iloc[-2] > 0
            # Filtro de agotamiento RSI (2026-06-09): un breakout que dispara con
            # RSI ya en sobrecompra extrema (>80) está persiguiendo un movimiento
            # ya agotado en momentum -> alto riesgo de reversión inmediata.
            rsi_no_agotado_long = df['RSI'].iloc[-1] <= 80
            # Filtro de conviccion de vela (2026-06-10): la vela de ruptura debe
            # tener un cuerpo (Body) al menos tan grande como el ATR -> vela
            # decisiva, no una ruptura debil/indecisa con alto riesgo de reversion.
            vela_decisiva_long = df['Body'].iloc[-1] >= df['ATR'].iloc[-1]
            confirmacion_long = prev_breakout_long and prev_ma_align_long and prev_macd_bullish and rsi_no_agotado_long and vela_decisiva_long

        if es_tendencia and breakout_long and ma_align_long and macd_bullish and confirmacion_long:
            donchian_low = df['Donchian_Low'].iloc[-1]
            sl_price = max(donchian_low, current_price * 0.97)
            risk_amount = current_price - sl_price
            if risk_amount <= 0:
                risk_amount = current_price * 0.03
            tp_price = current_price + (risk_amount * 2.0)
            qty = (current_balance * risk_percent) / risk_amount
            return 'LONG', {
                'type': 'LONG', 'puerta': 'A',
                'entry_price': current_price,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'qty': qty, 'conviccion': 95.0,
                'metrics': {'trend_w': 100, 'mr_w': 0},
                'regimen': regimen,
                'pattern': 'V22_A Donchian Breakout' if regimen == 'TENDENCIA' else 'V22_A Early-Trend Breakout'
            }

        breakout_short = current_price < df['Donchian_Low'].iloc[-1]
        ma_align_short = df['MA_7'].iloc[-1] < df['MA_99'].iloc[-1] and df['EMA_9'].iloc[-1] < df['MA_99'].iloc[-1]
        macd_bearish = df['MACD'].iloc[-1] < df['MACD_Signal'].iloc[-1] and df['MACD_Hist'].iloc[-1] < 0

        # Mismo gate de confirmación de 2 velas que en el LONG, ver comentario arriba.
        confirmacion_short = True
        if regimen == 'TENDENCIA':
            prev_breakout_short = df['close'].iloc[-2] < df['Donchian_Low'].iloc[-2]
            prev_ma_align_short = df['MA_7'].iloc[-2] < df['MA_99'].iloc[-2] and df['EMA_9'].iloc[-2] < df['MA_99'].iloc[-2]
            prev_macd_bearish = df['MACD'].iloc[-2] < df['MACD_Signal'].iloc[-2] and df['MACD_Hist'].iloc[-2] < 0
            # Filtro de agotamiento RSI (2026-06-09): un breakout que dispara con
            # RSI ya en sobreventa extrema (<20) está persiguiendo un movimiento
            # ya agotado en momentum -> alto riesgo de reversión inmediata.
            rsi_no_agotado_short = df['RSI'].iloc[-1] >= 20
            # Filtro de conviccion de vela (2026-06-10): mismo criterio que en LONG.
            vela_decisiva_short = df['Body'].iloc[-1] >= df['ATR'].iloc[-1]
            confirmacion_short = prev_breakout_short and prev_ma_align_short and prev_macd_bearish and rsi_no_agotado_short and vela_decisiva_short

        if es_tendencia and breakout_short and ma_align_short and macd_bearish and confirmacion_short:
            donchian_high = df['Donchian_High'].iloc[-1]
            sl_price = min(donchian_high, current_price * 1.03)
            risk_amount = sl_price - current_price
            if risk_amount <= 0:
                risk_amount = current_price * 0.03
            tp_price = current_price - (risk_amount * 2.0)
            qty = (current_balance * risk_percent) / risk_amount
            return 'SHORT', {
                'type': 'SHORT', 'puerta': 'A',
                'entry_price': current_price,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'qty': qty, 'conviccion': 95.0,
                'metrics': {'trend_w': 100, 'mr_w': 0},
                'regimen': regimen,
                'pattern': 'V22_A Donchian Breakdown' if regimen == 'TENDENCIA' else 'V22_A Early-Trend Breakdown'
            }

        # ===================================================================
        # PUERTA B — IMPULSO DE VELA (riesgo: 1% fijo, TP: 1R)
        # ===================================================================
        pattern_signal, b_risk = detect_candle_pattern(df)

        if pattern_signal:
            price_above_ma99 = current_price > df['MA_99'].iloc[-1]
            price_below_ma99 = current_price < df['MA_99'].iloc[-1]

            vol_ok = True
            if 'Volume_MA' in df.columns:
                vol_ma = df['Volume_MA'].iloc[-1]
                if vol_ma and vol_ma > 0:
                    vol_ok = df['volume'].iloc[-1] > vol_ma

            # Filtro de sobrecompra/sobreventa RSI (2026-06-09): una vela de
            # impulso que dispara con RSI ya en zona clásica de sobrecompra/
            # sobreventa (>70 / <30) suele ser una vela climática de
            # agotamiento, no el inicio de un impulso nuevo -> alto riesgo de
            # reversión antes de alcanzar el TP=1R ajustado.
            rsi_ok_long = df['RSI'].iloc[-1] <= 70
            rsi_ok_short = df['RSI'].iloc[-1] >= 30

            if pattern_signal == 'LONG_B' and price_above_ma99 and vol_ok and rsi_ok_long:
                sl_price = max(df['low'].iloc[-1], current_price * 0.98)
                risk_amount = current_price - sl_price
                if risk_amount <= 0:
                    risk_amount = current_price * 0.02
                tp_price = current_price + risk_amount
                qty = (current_balance * b_risk) / risk_amount
                return 'LONG', {
                    'type': 'LONG', 'puerta': 'B',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 75.0,
                    'metrics': {'trend_w': 70, 'mr_w': 30},
                    'regimen': regimen,
                    'pattern': 'V22_B Candle Impulse'
                }

            elif pattern_signal == 'SHORT_B' and price_below_ma99 and vol_ok and rsi_ok_short:
                sl_price = min(df['high'].iloc[-1], current_price * 1.02)
                risk_amount = sl_price - current_price
                if risk_amount <= 0:
                    risk_amount = current_price * 0.02
                tp_price = current_price - risk_amount
                qty = (current_balance * b_risk) / risk_amount
                return 'SHORT', {
                    'type': 'SHORT', 'puerta': 'B',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 75.0,
                    'metrics': {'trend_w': 70, 'mr_w': 30},
                    'regimen': regimen,
                    'pattern': 'V22_B Candle Impulse'
                }

        # ===================================================================
        # PUERTA C — REVERSIÓN A LA MEDIA (NUEVA — riesgo reducido 0.4%)
        # Solo se evalúa fuera de TENDENCIA: es el complemento que llena los
        # días/símbolos donde A y B no encuentran condiciones — sin pisarles
        # el terreno, porque exige precisamente lo contrario (rango, no breakout).
        #
        # Gating a BAJA_VOLATILIDAD-only: probado y revertido DOS VECES antes,
        # 3er intento (2026-06-10) en curso ahora que Puerta A es rentable
        # (filtro body/ATR la dejó en 41 trades, +$443.60) -> ver el libro.
        # 1er intento (2026-06-09): mejoró Puerta C en aislamiento (33->15 trades,
        # WR 30.3%->53.3%, PnL -$208.49->+$70.33) pero el efecto cascada empeoró
        # Puerta A (78 trades, WR 20.5%, -$864.21), neto -$161.51.
        # 2do intento (2026-06-10), ya con los filtros RSI de A y B en su lugar:
        # Puerta C mejoró otra vez (40->19 trades, WR 25.0%->36.8%, PnL
        # -$414.82->-$154.44, +$260.38) pero la cascada volvió a ser negativa
        # (A +4 trades/-$143.35, B +7 trades/-$170.71), neto -$53.68.
        #
        # DESACTIVACIÓN COMPLETA probada y REVERTIDA (2026-06-10): se desactivó
        # Puerta C por completo (gate `if False`) porque fuera de muestra pierde
        # -$194.92 (vs -$91.17 congelada) y BAJA_VOLATILIDAD es el único régimen
        # negativo OOS. PERO el experimento `puertaC_disabled_fixedwindow` mostró
        # que NO se puede quitar limpiamente: en la ventana congelada el portafolio
        # EMPEORÓ -$390.70 (los cupos de exposición que liberaba C los reabsorbieron
        # A y B con peores entradas: A -$168.22 con los mismos 37 trades pero peor
        # composición, B -$313.64), y en la ventana live quedó plano (-$2.48: el
        # ahorro de +$194.92 de C se canceló exacto con peores fills de A/B). Es
        # decir: C no tiene ventaja propia, pero su ocupación de cupos es "load-
        # bearing" bajo el tope FIFO de exposición — quitarla solo deja entrar
        # trades aún peores. Para abandonar C de verdad hace falta primero cambiar
        # la arquitectura de exposición (ranking por calidad en vez de FIFO).
        # Por eso se mantiene activa. Ver el libro y backtest_history.csv.
        # ===================================================================
        if regimen == 'BAJA_VOLATILIDAD':
            mr_signal, c_risk = detect_mean_reversion_signal(df)

            if mr_signal == 'LONG_C':
                sl_price = min(df['low'].iloc[-1], current_price * 0.99)
                risk_amount = current_price - sl_price
                if risk_amount <= 0:
                    risk_amount = current_price * 0.01
                tp_price = df['BB_Mid'].iloc[-1]
                if pd.isna(tp_price) or tp_price <= current_price:
                    tp_price = current_price + (risk_amount * 1.2)
                qty = (current_balance * c_risk) / risk_amount
                return 'LONG', {
                    'type': 'LONG', 'puerta': 'C',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 60.0,
                    'metrics': {'trend_w': 20, 'mr_w': 80},
                    'regimen': regimen,
                    'pattern': 'V22_C Mean Reversion (Bollinger/RSI Fade)'
                }

            elif mr_signal == 'SHORT_C':
                sl_price = max(df['high'].iloc[-1], current_price * 1.01)
                risk_amount = sl_price - current_price
                if risk_amount <= 0:
                    risk_amount = current_price * 0.01
                tp_price = df['BB_Mid'].iloc[-1]
                if pd.isna(tp_price) or tp_price >= current_price:
                    tp_price = current_price - (risk_amount * 1.2)
                qty = (current_balance * c_risk) / risk_amount
                return 'SHORT', {
                    'type': 'SHORT', 'puerta': 'C',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 60.0,
                    'metrics': {'trend_w': 20, 'mr_w': 80},
                    'regimen': regimen,
                    'pattern': 'V22_C Mean Reversion (Bollinger/RSI Fade)'
                }

        return None, None

    except Exception as e:
        print(f"Error evaluando señales V22_Master: {e}")
        return None, None
