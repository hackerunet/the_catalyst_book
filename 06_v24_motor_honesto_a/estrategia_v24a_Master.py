"""
estrategia_v24a_Master.py — SISTEMA ÚNICO DE MOMENTUM (V24-FABLE-A)

Rediseño desde cero, partiendo de las CONCLUSIONES del ciclo V22 en lugar de
seguir parchando lo que tiene fallas. Lo que el proceso experimental demostró
(en ambas ventanas, congelada y reciente):

  ROBUSTO (se mantiene):
  - El edge real del sistema es MOMENTUM ALINEADO CON TENDENCIA. Puerta A
    (breakout) y Puerta B (impulso de vela) fueron los únicos componentes
    positivos dentro y fuera de la ventana de ajuste.
  - Persistencia de 2 velas en el breakout (el primer filtro que mejoró A en
    todos los ejes).
  - Convicción de vela (Body >= ATR) en breakouts (la mejora más grande del
    proyecto).
  - Guardas RSI: 80/20 en breakouts, 70/30 en impulsos (validadas exactamente
    en esos contextos, no se cruzan).
  - Volumen: >= 1.5x su media para breakouts (validado), > 1.0x para impulsos
    (el vol_ok original de B).
  - Estructura de salida 2R parcial + runner con trailing + breakeven a +1R.

  SE ABANDONA (probado y fallido, o nunca justificado):
  - Puerta C / reversión a la media: sin edge fuera de muestra (−$195 OOS),
    solo cruzó a positivo en la ventana exacta a la que se curve-fiteó. Con el
    motor de reloj global ya NO es "load-bearing" (eso era un artefacto del
    backtest secuencial de V22), así que por fin se puede eliminar limpio.
  - El clasificador de 4 regímenes: BAJA_VOLATILIDAD era el único régimen
    negativo OOS y solo existía para darle contexto a C. Se reemplaza por un
    FILTRO DE TENDENCIA directo (EMA9 vs MA99 + pendiente de MA99 al alza).
    classify_regime() se conserva SOLO como telemetría/etiquetado.
  - El caso especial TENDENCIA_EMERGENTE: la pendiente de MA99 + el requisito
    de volumen capturan la "tendencia naciente" con menos parámetros.
  - Stops de porcentaje plano (3%/2%/1%): eran la restricción activa en casi
    todos los full-risk losers de A. Se reemplazan por 2.5x ATR acotado a
    [1.5%, 4%] del precio (adaptativo; ATR*1.5 ya se probó y era demasiado
    apretado — 2.5x queda cerca del 3% típico pero se adapta a la volatilidad).

  NUEVO (principios estándar de trading, no minado de la ventana):
  - Pendiente de MA99 al alza/baja como condición de tendencia (no basta que
    el precio esté del lado correcto de una media plana).
  - TIME STOP: si en 48 velas (48h) el trade nunca alcanzó +0.5R, se cierra a
    mercado — un trade muerto paga funding y bloquea capital/exposición sin
    tesis vigente.

API idéntica a estrategia_v24_Master para que el motor (simulador) no cambie:
compute_indicators, compute_signals_and_trades(df, balance, risk_percent),
INTERVAL, check_multi_candle_exhaustion, classify_regime.
Etiquetas: breakout -> puerta 'A', impulso -> puerta 'B' (parsers de
mesa_de_dinero y log_backtest siguen funcionando sin cambios).
"""
import pandas as pd
import numpy as np

INTERVAL = '1h'

# Ventana usada para ubicar la volatilidad actual dentro de su propio histórico
# reciente (solo telemetría — classify_regime ya no gatea entradas).
REGIME_LOOKBACK = 100

# --- Parámetros del sistema (pocos, estándar, documentados) ---
ATR_STOP_MULT = 2.5        # stop = 2.5x ATR (adaptativo)
STOP_MIN_PCT = 0.015       # piso del stop: 1.5% del precio
STOP_MAX_PCT = 0.04        # techo del stop: 4% del precio
TP_R_MULT = 2.0            # TP parcial a 2R (validado en V22 vs 3R)
MA99_SLOPE_CANDLES = 6     # pendiente de MA99 medida sobre ~6h
VOL_BREAKOUT_MULT = 1.5    # volumen >= 1.5x media para breakouts (validado)
RSI_BREAKOUT_MAX = 80      # guardas RSI de breakout (validadas 80/20)
RSI_BREAKOUT_MIN = 20
RSI_IMPULSO_MAX = 70       # guardas RSI de impulso (validadas 70/30)
RSI_IMPULSO_MIN = 30
TIME_STOP_HORAS = 48       # cierre por tiempo si nunca alcanzó +0.5R
RIESGO_POR_TRADE = 0.01    # 1% plano para ambos disparadores


# =============================================================================
# INDICADORES (mismo set que V22/V24 — el dashboard y la telemetría los usan)
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

    # 2. Canal de Donchian (24 periodos) — disparador de breakout
    df['Donchian_High'] = df['high'].rolling(window=24).max().shift(1)
    df['Donchian_Low'] = df['low'].rolling(window=24).min().shift(1)

    # 3. Volumen — confirmación de participación real
    df['Volume_MA'] = df['volume'].rolling(window=20).mean()

    # 4. MACD (usado por el cierre táctico de agotamiento y telemetría)
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 5. Métricas de vela (cuerpo / color)
    df['Body'] = abs(df['close'] - df['open'])
    df['Is_Green'] = df['close'] > df['open']
    df['Is_Red'] = df['close'] < df['open']

    # 6. ATR / ATR% — stop adaptativo + telemetría de régimen
    df['ATR'] = _calculate_atr(df, period=14)
    df['ATR_pct'] = (df['ATR'] / df['close']) * 100

    # 7. ADX — solo telemetría (classify_regime); ya no gatea entradas
    df['ADX'] = _calculate_adx(df, period=14)

    # 8. RSI — guardas de agotamiento
    df['RSI'] = _calculate_rsi(df['close'], period=14)

    return df


def compute_indicators(df):
    return calculate_indicators(df)


# =============================================================================
# CLASIFICADOR DE RÉGIMEN — SOLO TELEMETRÍA EN V24A
# Se conserva para que las etiquetas de los logs/Telegram sigan siendo
# comparables con V22/V24, pero NINGUNA entrada se gatea con esto.
# =============================================================================
def classify_regime(df: pd.DataFrame) -> str:
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
    if atr_percentile <= 35:
        return 'BAJA_VOLATILIDAD'
    return 'RANGO'


# =============================================================================
# PATRÓN DE AGOTAMIENTO MULTIVELAS (cierre táctico — heredado sin cambios,
# ahora simulado también en backtest por el motor V24)
# =============================================================================
def check_multi_candle_exhaustion(df: pd.DataFrame, position_type: str = 'LONG') -> bool:
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

        if idx - anchor_idx < 2:
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

        return (highest_high - lowest_low) > (2.0 * anchor_body)

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

        if idx - anchor_idx < 2:
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

        return (highest_high - lowest_low) > (2.0 * anchor_body)

    return False


# =============================================================================
# DISPARADOR DE IMPULSO (Marubozu / Engulfing — el núcleo de la ex-Puerta B,
# el componente con más muestra y más robusto de todo el proyecto)
# =============================================================================
def detect_candle_pattern(df: pd.DataFrame):
    if len(df) < 3:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    candle_range = curr['high'] - curr['low']
    if candle_range <= 0:
        return None

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
        return 'LONG'
    if is_marubozu_bear or is_engulfing_bear:
        return 'SHORT'
    return None


# =============================================================================
# FILTRO DE TENDENCIA — reemplaza al clasificador de 4 regímenes como gate
# =============================================================================
def _trend_direction(df: pd.DataFrame):
    """
    'LONG' si EMA9 > MA99, precio > MA99 y MA99 con pendiente al alza sobre
    las últimas MA99_SLOPE_CANDLES velas; 'SHORT' espejo; None si no hay
    tendencia clara. La pendiente es lo que faltaba en V22: precio sobre una
    MA99 PLANA es rango, no tendencia — y el sistema solo tiene edge en
    tendencia (conclusión central del ciclo V22).
    """
    if len(df) < 99 + MA99_SLOPE_CANDLES + 1:
        return None

    price = df['close'].iloc[-1]
    ema9 = df['EMA_9'].iloc[-1]
    ma99_now = df['MA_99'].iloc[-1]
    ma99_prev = df['MA_99'].iloc[-1 - MA99_SLOPE_CANDLES]

    if pd.isna(ma99_now) or pd.isna(ma99_prev) or pd.isna(ema9):
        return None

    if price > ma99_now and ema9 > ma99_now and ma99_now > ma99_prev:
        return 'LONG'
    if price < ma99_now and ema9 < ma99_now and ma99_now < ma99_prev:
        return 'SHORT'
    return None


def _stop_distance(df: pd.DataFrame, price: float) -> float:
    """Stop adaptativo: 2.5x ATR acotado a [1.5%, 4%] del precio."""
    atr = df['ATR'].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return price * STOP_MAX_PCT
    dist = atr * ATR_STOP_MULT
    return min(max(dist, price * STOP_MIN_PCT), price * STOP_MAX_PCT)


# =============================================================================
# ORQUESTADOR — un solo sistema, dos disparadores, una estructura de salida
# =============================================================================
def compute_signals_and_trades(df: pd.DataFrame, current_balance: float = 500.0, risk_percent: float = 0.01):
    """
    SISTEMA ÚNICO DE MOMENTUM:

      FILTRO (ambos disparadores): _trend_direction() — EMA9/MA99 alineadas,
      precio del lado correcto, MA99 con pendiente en la dirección del trade.

      DISPARADOR 1 — BREAKOUT (etiqueta puerta 'A', convicción 90):
        cierre rompe Donchian(24) con persistencia de 2 velas + Body >= ATR +
        volumen >= 1.5x media + RSI no extremo (<=80 long / >=20 short).

      DISPARADOR 2 — IMPULSO (etiqueta puerta 'B', convicción 75):
        Marubozu/Engulfing + volumen > media + RSI no sobrecomprado/vendido
        (<=70 long / >=30 short).

      SALIDA (idéntica para ambos): stop 2.5x ATR (acotado 1.5%-4%), TP
      parcial 50% a 2R + runner con trailing y breakeven a +1R (motor V24),
      time stop de 48h si nunca alcanzó +0.5R, cierre táctico por agotamiento.

      RIESGO: 1% plano del balance por trade.
    """
    try:
        if len(df) < 110:
            return None, None

        current_price = df['close'].iloc[-1]
        regimen = classify_regime(df)  # solo telemetría
        tendencia = _trend_direction(df)
        if tendencia is None:
            return None, None

        rsi = df['RSI'].iloc[-1]
        vol = df['volume'].iloc[-1]
        vol_ma = df['Volume_MA'].iloc[-1]
        vol_ma_ok = (vol_ma is not None) and not pd.isna(vol_ma) and vol_ma > 0

        # ----------------- DISPARADOR 1: BREAKOUT -----------------
        if tendencia == 'LONG':
            breakout = (current_price > df['Donchian_High'].iloc[-1]
                        and df['close'].iloc[-2] > df['Donchian_High'].iloc[-2])
            vela_decisiva = df['Body'].iloc[-1] >= df['ATR'].iloc[-1]
            vol_fuerte = vol_ma_ok and vol >= vol_ma * VOL_BREAKOUT_MULT
            rsi_ok = rsi <= RSI_BREAKOUT_MAX
            if breakout and vela_decisiva and vol_fuerte and rsi_ok:
                dist = _stop_distance(df, current_price)
                sl_price = current_price - dist
                tp_price = current_price + dist * TP_R_MULT
                qty = (current_balance * risk_percent) / dist
                return 'LONG', {
                    'type': 'LONG', 'puerta': 'A',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 90.0,
                    'metrics': {'trend_w': 100, 'mr_w': 0},
                    'regimen': regimen,
                    'time_stop_horas': TIME_STOP_HORAS,
                    'pattern': 'V24A Breakout Donchian (tendencia confirmada)'
                }
        else:  # SHORT
            breakout = (current_price < df['Donchian_Low'].iloc[-1]
                        and df['close'].iloc[-2] < df['Donchian_Low'].iloc[-2])
            vela_decisiva = df['Body'].iloc[-1] >= df['ATR'].iloc[-1]
            vol_fuerte = vol_ma_ok and vol >= vol_ma * VOL_BREAKOUT_MULT
            rsi_ok = rsi >= RSI_BREAKOUT_MIN
            if breakout and vela_decisiva and vol_fuerte and rsi_ok:
                dist = _stop_distance(df, current_price)
                sl_price = current_price + dist
                tp_price = current_price - dist * TP_R_MULT
                qty = (current_balance * risk_percent) / dist
                return 'SHORT', {
                    'type': 'SHORT', 'puerta': 'A',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 90.0,
                    'metrics': {'trend_w': 100, 'mr_w': 0},
                    'regimen': regimen,
                    'time_stop_horas': TIME_STOP_HORAS,
                    'pattern': 'V24A Breakdown Donchian (tendencia confirmada)'
                }

        # ----------------- DISPARADOR 2: IMPULSO -----------------
        patron = detect_candle_pattern(df)
        if patron == tendencia:
            vol_ok = (not vol_ma_ok) or vol > vol_ma
            if tendencia == 'LONG':
                rsi_ok = rsi <= RSI_IMPULSO_MAX
            else:
                rsi_ok = rsi >= RSI_IMPULSO_MIN
            if vol_ok and rsi_ok:
                dist = _stop_distance(df, current_price)
                if tendencia == 'LONG':
                    sl_price = current_price - dist
                    tp_price = current_price + dist * TP_R_MULT
                else:
                    sl_price = current_price + dist
                    tp_price = current_price - dist * TP_R_MULT
                qty = (current_balance * risk_percent) / dist
                return tendencia, {
                    'type': tendencia, 'puerta': 'B',
                    'entry_price': current_price,
                    'stop_loss': sl_price, 'take_profit': tp_price,
                    'qty': qty, 'conviccion': 75.0,
                    'metrics': {'trend_w': 80, 'mr_w': 20},
                    'regimen': regimen,
                    'time_stop_horas': TIME_STOP_HORAS,
                    'pattern': 'V24A Impulso de Vela (Marubozu/Engulfing en tendencia)'
                }

        return None, None

    except Exception as e:
        print(f"Error evaluando señales V24A_Master: {e}")
        return None, None
