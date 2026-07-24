"""
estrategia.py — Cerebro de decisión PURO (sin I/O, sin órdenes, sin Telegram).

Tanto el ejecutor en vivo (ejecutor.py) como el backtest (backtest.py) llaman
EXACTAMENTE estas funciones — un solo code path de decisión (lección del motor
honesto V24: backtest y vivo nunca deben divergir en lógica).

Decisiones:
- tendencia_actual(df)        → 'LONG' | 'SHORT' | 'LATERAL'
- evaluar_entrada(df)         → señal dict | None (sin qty: eso es del ejecutor)
- evaluar_salida(t, precio)   → dict {cerrar, nuevo_peak, nuevo_decil} (no muta t)
- prob_reversion(df, tipo)    → 5-95%
"""
import pandas as pd

import config
from indicadores import atr_diario, momentum_diario
from patrones import detectar_patrones, PATRONES_DE_MECHA


def tendencia_actual(df):
    """
    Régimen 1h: precio vs EMA50 vs EMA200 + fuerza ADX >= umbral.
    Momentum diario (cierre 1D vs EMA20 diaria) debe COINCIDIR.
    'LATERAL' = no operar (único momento de abstención del bot).
    """
    if len(df) < config.WARMUP_CANDLES:
        return 'LATERAL'
    c = df['close'].iloc[-1]
    e50, e200 = df['EMA_50'].iloc[-1], df['EMA_200'].iloc[-1]
    adx = df['ADX'].iloc[-1]
    if pd.isna(e50) or pd.isna(e200) or adx < config.ADX_LATERAL_MAX:
        return 'LATERAL'
    diario = momentum_diario(df)
    if c > e50 > e200 and diario == 'LONG':
        return 'LONG'
    if c < e50 < e200 and diario == 'SHORT':
        return 'SHORT'
    return 'LATERAL'


def diagnostico_entrada(df):
    """
    Diagnóstico PURO (sin efectos) — reporta en texto corto por qué
    evaluar_entrada() retornaría None en este cierre de vela.
    Solo para logging; no afecta decisiones. Retorna string con el motivo.
    """
    if len(df) < config.WARMUP_CANDLES:
        return f"warmup ({len(df)}/{config.WARMUP_CANDLES} velas)"

    c = df['close'].iloc[-1]
    e50 = df['EMA_50'].iloc[-1]
    e200 = df['EMA_200'].iloc[-1]
    adx = df['ADX'].iloc[-1]
    diario = momentum_diario(df)

    # Desglose de por qué tendencia == LATERAL
    if pd.isna(e50) or pd.isna(e200):
        return "EMA NaN (datos insuficientes)"
    if adx < config.ADX_LATERAL_MAX:
        # Reportar la estructura aunque ADX sea bajo
        if c > e50 > e200:
            estructura = "alcista"
        elif c < e50 < e200:
            estructura = "bajista"
        else:
            estructura = "mixta"
        return f"LATERAL: ADX={adx:.1f}<{config.ADX_LATERAL_MAX} | estructura {estructura} | diario={diario}"

    tendencia = tendencia_actual(df)
    if tendencia == 'LATERAL':
        # ADX ok pero estructura no alineada
        pos_e50 = "C>E50" if c > e50 else "C<E50"
        pos_e200 = "E50>E200" if e50 > e200 else "E50<E200"
        return f"LATERAL: ADX={adx:.1f} OK pero {pos_e50}, {pos_e200}, diario={diario} — sin alineación"

    modo = getattr(config, 'ENTRY_MODE', 'patrones')
    if modo == 'cruce':
        tend_prev = tendencia_actual(df.iloc[:-1])
        if tend_prev == tendencia:
            return f"tendencia={tendencia} (ADX={adx:.1f}) pero NO es cruce (ya era {tend_prev} antes)"

    elif modo == 'patrones':
        patrones = detectar_patrones(df)
        if any(p['tipo'] == 'incertidumbre' for p in patrones):
            return f"tendencia={tendencia} (ADX={adx:.1f}) pero DOJI detectado → incertidumbre"
        atr = df['ATR'].iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return f"tendencia={tendencia} pero ATR inválido"
        alineados = [p for p in patrones if p['dir'] == tendencia]
        if not alineados:
            nombres = [p['nombre'] for p in patrones] if patrones else ['ninguno']
            return (f"tendencia={tendencia} (ADX={adx:.1f}) pero sin patrón alineado "
                    f"(detectados: {', '.join(nombres)})")
        # Hay patrón alineado — ¿por qué no pasó?
        rechazos = []
        for p in alineados:
            es_mecha = p['nombre'] in PATRONES_DE_MECHA
            if es_mecha:
                rango = float(df['high'].iloc[-1] - df['low'].iloc[-1])
                if rango < atr * config.WICK_RANGE_MIN_ATR_FRACTION:
                    rechazos.append(f"{p['nombre']}: rango {rango:.4f} < {atr * config.WICK_RANGE_MIN_ATR_FRACTION:.4f}")
                    continue
            else:
                body = df['Body'].iloc[-1]
                if body < atr * config.BODY_MIN_ATR_FRACTION:
                    rechazos.append(f"{p['nombre']}: body {body:.4f} < {atr * config.BODY_MIN_ATR_FRACTION:.4f}")
                    continue
            vma = df['Volume_MA'].iloc[-1]
            vol = df['volume'].iloc[-1]
            if pd.isna(vma) or vma <= 0:
                rechazos.append(f"{p['nombre']}: Volume_MA inválido")
                continue
            if p['tipo'] == 'continuacion' and vol <= vma:
                rechazos.append(f"{p['nombre']}: vol {vol:.0f} <= VMA {vma:.0f}")
            elif p['tipo'] != 'continuacion' and vol < vma * config.REVERSAL_VOL_FLOOR:
                rechazos.append(f"{p['nombre']}: vol {vol:.0f} < {vma * config.REVERSAL_VOL_FLOOR:.0f} (floor)")
        if rechazos:
            return f"tendencia={tendencia} (ADX={adx:.1f}) patrones rechazados: {'; '.join(rechazos[:3])}"
        # Si llegó aquí, el patrón pasó body/vol — debe ser RSI
        rsi = df['RSI'].iloc[-1]
        if tendencia == 'LONG' and rsi > config.RSI_MAX_LONG:
            return f"tendencia=LONG pero RSI={rsi:.1f} > {config.RSI_MAX_LONG}"
        if tendencia == 'SHORT' and rsi < config.RSI_MIN_SHORT:
            return f"tendencia=SHORT pero RSI={rsi:.1f} < {config.RSI_MIN_SHORT}"

    # Si no caímos en ningún rechazo conocido, la señal debería existir
    return f"tendencia={tendencia} (ADX={adx:.1f}) — señal debería pasar (revisar lógica)"



def prob_reversion(df, tipo_posicion):
    """
    Probabilidad heurística (5-95%) de reversión inmediata contra la posición.
    Variables: RSI extremo, MACD_Hist perdiendo fuerza 2 velas, patrón de
    reversión OPUESTO, sobre-extensión vs EMA200, doji presente.
    """
    try:
        prob = 15.0
        rsi = df['RSI'].iloc[-1]
        if tipo_posicion == 'LONG' and rsi >= 70:
            prob += min((rsi - 70) * 2.5, 25)
        if tipo_posicion == 'SHORT' and rsi <= 30:
            prob += min((30 - rsi) * 2.5, 25)

        mh = df['MACD_Hist']
        if tipo_posicion == 'LONG' and mh.iloc[-1] < mh.iloc[-2] < mh.iloc[-3]:
            prob += 20
        if tipo_posicion == 'SHORT' and mh.iloc[-1] > mh.iloc[-2] > mh.iloc[-3]:
            prob += 20

        opuesto = 'SHORT' if tipo_posicion == 'LONG' else 'LONG'
        for pat in detectar_patrones(df):
            if pat['dir'] == opuesto and pat['tipo'] == 'reversion':
                prob += 25
                break
            if pat['tipo'] == 'incertidumbre':
                prob += 10

        e200 = df['EMA_200'].iloc[-1]
        if not pd.isna(e200) and e200 > 0:
            dist = abs(df['close'].iloc[-1] - e200) / e200 * 100
            if dist > 5:
                prob += min((dist - 5) * 2, 15)

        return round(min(max(prob, 5), 95), 1)
    except Exception:
        return 50.0


def evaluar_entrada(df, rs_basket=None, rs_symbol=None, reentrada_armada=False):
    if len(df) < config.WARMUP_CANDLES:
        return None

    modo = getattr(config, 'ENTRY_MODE', 'patrones')
    import estrategias_tempranas as _et
    if modo in _et.DISPATCH:
        direccion, etiqueta = _et.DISPATCH[modo](df)
        if direccion is None:
            return None
        
        precio = float(df['close'].iloc[-1])
        atr_d = atr_diario(df)
        dist_tp = atr_d * config.TP_DAILY_ATR_MULT if atr_d else precio * 0.03
        dist_tp = min(max(dist_tp, precio * config.TP_MIN_PCT), precio * config.TP_MAX_PCT)
        dist_sl = dist_tp * config.SL_FRACTION_OF_TP

        if direccion == 'LONG':
            tp, sl = precio + dist_tp, precio - dist_sl
        else:
            tp, sl = precio - dist_tp, precio + dist_sl

        return {
            'type': direccion,
            'entry_price': precio,
            'tp': tp,
            'sl': sl,
            'dist_sl': dist_sl,
            'pattern': etiqueta,
            'patrones_detectados': [],
            'prob_reversion': prob_reversion(df, direccion),
        }

    tendencia = tendencia_actual(df)
    if tendencia == 'LATERAL':
        return None

    modo = getattr(config, 'ENTRY_MODE', 'patrones')
    patrones = []
    if modo == 'patrones':
        patrones = detectar_patrones(df)
        if any(p['tipo'] == 'incertidumbre' for p in patrones):
            return None  # doji → incertidumbre → no entrar

        # Convicción mínima de la vela disparadora (lección V22 body>=ATR; caso
        # 2002d074: una micro-vela de 0.42x ATR "confirmó" un evening star).
        # Patrones de CUERPO: Body >= 0.5x ATR. Patrones de MECHA (hammer etc.,
        # cuerpo pequeño por definición): rango total >= 0.75x ATR — misma barra
        # de convicción, métrica fiel a la geometría de cada patrón.
        atr = df['ATR'].iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return None
        body_ok = df['Body'].iloc[-1] >= atr * config.BODY_MIN_ATR_FRACTION
        rango_ok = float(df['high'].iloc[-1] - df['low'].iloc[-1]) \
            >= atr * config.WICK_RANGE_MIN_ATR_FRACTION

        confirmacion = None
        vma = df['Volume_MA'].iloc[-1]
        vol = df['volume'].iloc[-1]
        vma_valida = (not pd.isna(vma)) and vma > 0
        for p in patrones:
            if p['dir'] == tendencia:
                if not (rango_ok if p['nombre'] in PATRONES_DE_MECHA else body_ok):
                    continue
                if p['tipo'] == 'continuacion':  # continuación exige participación
                    vol_ok = vma_valida and vol > vma
                else:
                    # reversión/confirmación: piso mínimo de participación
                    # (caso 2002d074: evening star con 8.5% del volumen promedio)
                    vol_ok = vma_valida and vol >= vma * config.REVERSAL_VOL_FLOOR
                if vol_ok:
                    confirmacion = p
                    break
        if not confirmacion:
            return None
        etiqueta = f"{confirmacion['nombre']} ({confirmacion['tipo']})"
    elif modo == 'cruce':
        # Estrategia clásica EMA50/200 SIN capa de patrones: entrar SOLO en la
        # vela donde la tendencia SE VUELVE alineada (cruce/flip) — o, con
        # V27-A re-armado (post-stop, alineación viva), en cualquier vela.
        if reentrada_armada:
            etiqueta = 'Re-entrada post-stop (tendencia vigente)'
        else:
            if tendencia_actual(df.iloc[:-1]) == tendencia:
                return None  # ya estaba alineada — no es el cruce
            etiqueta = 'Cruce de tendencia (sin patrones)'
    elif modo == 'donchian':
        # TEST D: ruptura del canal Donchian de 20 velas (clásico Turtle, sin
        # escanear) con la tendencia ya alineada — el único disparador
        # honesto-positivo de la historia del proyecto (Puerta A de V24).
        if len(df) < 22:
            return None
        if tendencia == 'LONG':
            if not df['close'].iloc[-1] > df['high'].iloc[-21:-1].max():
                return None
        else:
            if not df['close'].iloc[-1] < df['low'].iloc[-21:-1].min():
                return None
        etiqueta = 'Ruptura Donchian 20 (tendencia alineada)'
    else:  # 'continua' — tendencia alineada, sin patrones, cualquier vela
        etiqueta = 'Tendencia alineada (sin patrones)'

    # TEST A (2026-06-11): filtro de régimen por squeeze TTM — un cruce/entrada
    # dentro de compresión de volatilidad (BB dentro de Keltner) es whipsaw
    # probable. Default OFF (config.FILTRO_SQUEEZE); el bot en vivo no cambia.
    # RESULTADO: RECHAZADO (mediana −1.21→−1.51, pctl 88→80; el squeeze no
    # discrimina el chop 4h en cripto) — queda solo como referencia histórica.
    if getattr(config, 'FILTRO_SQUEEZE', False) and 'Squeeze_On' in df.columns \
            and bool(df['Squeeze_On'].iloc[-1]):
        return None

    # TEST B (2026-06-11): fuerza relativa del basket — LONG solo en la mitad
    # SUPERIOR del ranking de ROC a 20 días entre los símbolos; SHORT solo en
    # la mitad INFERIOR. Default OFF (config.FILTRO_RS); bot en vivo no cambia.
    if getattr(config, 'FILTRO_RS', False) and rs_basket and rs_symbol in rs_basket \
            and len(rs_basket) >= 4:
        orden = sorted(rs_basket, key=rs_basket.get, reverse=True)  # líder primero
        pos = orden.index(rs_symbol)
        mitad = len(orden) / 2
        if tendencia == 'LONG' and pos >= mitad:
            return None  # rezagado: no comprar
        if tendencia == 'SHORT' and pos < mitad:
            return None  # líder: no shortear

    rsi = df['RSI'].iloc[-1]
    if tendencia == 'LONG' and rsi > config.RSI_MAX_LONG:
        return None
    if tendencia == 'SHORT' and rsi < config.RSI_MIN_SHORT:
        return None

    precio = float(df['close'].iloc[-1])
    atr_d = atr_diario(df)
    dist_tp = atr_d * config.TP_DAILY_ATR_MULT if atr_d else precio * 0.03
    dist_tp = min(max(dist_tp, precio * config.TP_MIN_PCT), precio * config.TP_MAX_PCT)
    dist_sl = dist_tp * config.SL_FRACTION_OF_TP

    if tendencia == 'LONG':
        tp, sl = precio + dist_tp, precio - dist_sl
    else:
        tp, sl = precio - dist_tp, precio + dist_sl

    return {
        'type': tendencia,
        'entry_price': precio,
        'tp': tp,
        'sl': sl,
        'dist_sl': dist_sl,
        'pattern': etiqueta,
        'patrones_detectados': patrones,
        'prob_reversion': prob_reversion(df, tendencia),
    }


def salida_por_flip(tendencia_ahora, tipo_posicion):
    """
    TEST C (EXIT_MODE='tendencia'): cerrar cuando la alineación completa se
    invierte — el sistema entraría del lado opuesto ("stop and reverse"
    clásico, cero parámetros). LATERAL no cierra (solo el flip confirmado).
    """
    opuesto = 'SHORT' if tipo_posicion == 'LONG' else 'LONG'
    return tendencia_ahora == opuesto


def calcular_progreso(t, precio):
    """% de avance del precio hacia el TP (0-100+). Negativo si va en contra."""
    if t['type'] == 'LONG':
        recorrido = t['tp'] - t['entry_price']
        avance = precio - t['entry_price']
    else:
        recorrido = t['entry_price'] - t['tp']
        avance = t['entry_price'] - precio
    if recorrido <= 0:
        return 0.0
    return avance / recorrido * 100.0


def evaluar_salida(t, precio):
    """
    PURA — no muta el trade. Dado el estado actual del trade y un precio,
    retorna {'cerrar': motivo|None, 'nuevo_peak': float|None, 'nuevo_decil': int|None}.

    Reglas (spec V25):
      1. STOP de protección.
      2. OBJETIVO 100% del profit calculado.
      3. Asegurar cada 10% de avance (decil).
      4. Cierre inmediato si el avance retrocede 8 pts desde el decil asegurado.
    """
    res = {'cerrar': None, 'nuevo_peak': None, 'nuevo_decil': None}

    if t['type'] == 'LONG' and precio <= t['sl']:
        res['cerrar'] = 'STOP DE PROTECCIÓN'
        return res
    if t['type'] == 'SHORT' and precio >= t['sl']:
        res['cerrar'] = 'STOP DE PROTECCIÓN'
        return res

    prog = calcular_progreso(t, precio)
    if prog > t.get('peak_progress', 0):
        res['nuevo_peak'] = prog

    # TEST C / V26 (EXIT_MODE='tendencia'): sin TP ni escalera — la única
    # salida automática a nivel de precio es el STOP (arriba); el flip de
    # alineación lo evalúa el motor al CIERRE de vela (salida_por_flip, que
    # necesita el df completo). El peak queda como telemetría.
    if getattr(config, 'EXIT_MODE', 'escalera') == 'tendencia':
        return res

    if prog >= 100:
        res['cerrar'] = 'OBJETIVO 100% ALCANZADO'
        return res

    decil = int(prog // config.LOCK_STEP_PCT) * config.LOCK_STEP_PCT
    if decil > t.get('locked_decile', 0) and decil >= config.LOCK_STEP_PCT:
        res['nuevo_decil'] = decil

    # El cierre-por-reversa solo se ARMA desde PULLBACK_ARM_DECILE (20%):
    # hallazgo forense 2026-06-11 — con piso 10−8 = 2% del recorrido el cierre
    # quedaba DEBAJO del breakeven de costos y "aseguraba" pérdidas pequeñas.
    # Los deciles se siguen asegurando/notificando desde 10% (spec req. 4).
    locked = max(t.get('locked_decile', 0), res['nuevo_decil'] or 0)
    if locked >= config.PULLBACK_ARM_DECILE and prog < locked - config.PULLBACK_CLOSE_PCT:
        res['cerrar'] = (f'REVERSA: retrocedió {config.PULLBACK_CLOSE_PCT}pts '
                         f'desde {locked}% — profit asegurado')
    return res
