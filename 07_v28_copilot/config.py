"""
config.py — Configuración central de V28_COPILOT (asistente de trading 1h).

NO es un bot autónomo: detecta la oportunidad, monta la operación (entrada +
SL seguro + TP duro en 2R) y ACOMPAÑA al trader con información (deciles,
breakeven, prob de reverso, volumen). Entre el SL y el 2R la salida es 100%
del trader (botón TOMAR PROFIT). KPI = calidad de reconocimiento, NO PnL.
Pre-registro completo en el libro ("V28_COPILOT — ASISTENTE DE TRADING 1h").
"""
import os
from dotenv import load_dotenv

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BASE, '..', '..', '.env'))

# --- Credenciales (de los bots previos del proyecto) ---
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

# V28: token PROPIO OBLIGATORIO (TELEGRAM_TOKEN_V28 en .env, crear en
# @BotFather) — V25 y V26 corren en paralelo con sus tokens; compartir token
# rompe el getUpdates. El entrypoint se NIEGA a arrancar sin él.
TELEGRAM_TOKEN_COMPARTIDO = ''  # sin fallback, a propósito
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_V28', '')
TELEGRAM_CHAT_ID = '1214526208'  # ÚNICO chat autorizado

# --- Endpoints (de los bots previos) ---
TESTNET_BASE = 'https://demo-fapi.binance.com'   # órdenes + cuenta (testnet)
DATA_BASE = 'https://fapi.binance.com'           # klines públicos
# FIX 2026-06-11: el stream era el de SPOT (stream.binance.com) mientras
# bootstrap/backtest/órdenes usan FUTUROS — precios casi iguales pero volumen
# ~10x menor; el trade 2002d074 (XRP SHORT) solo existió en datos spot (el
# evening star falla en las velas de futuros). Ahora todo es el mismo mercado.
# FIX 2026-06-19: Binance migró su WS a entry points dedicados /public /market
# /private. La URL legacy (sin /market) conecta OK pero deja de empujar datos
# de kline/aggTrade (solo entrega /public) — handshake exitoso, cero mensajes,
# sin error ni desconexión, indistinguible de "todo bien" en los logs. Por
# esto los 3 bots llevaban desde el boot sin operar ni loguear [DIAG] alguno.
WS_URL_BASE = 'wss://fstream.binance.com/market'  # stream multiplexado FUTUROS

BOT_NOMBRE = 'V28_COPILOT'

# --- Mercados: 3-6 símbolos, motores independientes ---
SYMBOLS = ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']

INTERVAL = '1h'
BOOTSTRAP_CANDLES = 600      # ~25 días: EMA200 1h + EMA20 diaria
MAX_CANDLES = 800
WARMUP_CANDLES = 210         # mínimo de velas antes de evaluar señales

LEVERAGE = 5

# --- Riesgo (actualizado 2026-06-11, pedido del usuario: tope 2% del balance) ---
# Los 6 motores son INDEPENDIENTES a propósito (spec req. 1: sin interferencia,
# sin reducir oportunidades) — no hay presupuesto de riesgo compartido que un
# símbolo pueda agotarle a otro. Por eso el tope GLOBAL del 2% se garantiza por
# construcción: riesgo_por_trade = 2% / N símbolos ≈ 0.33% cada uno. Peor caso
# (los 6 motores con posición abierta y todos los stops golpeados a la vez):
# 6 × 0.33% = 2.0% del balance. Cada motor SIEMPRE puede tomar su señal.
PORTFOLIO_RISK_CAP = 0.02
RISK_PER_TRADE = PORTFOLIO_RISK_CAP / len(SYMBOLS)

# Tarea #40 (2026-06-25): tope de posiciones concurrentes (en cualquier dirección)
# para limitar la exposición correlacionada — cripto se mueve junto, así que 6
# shorts a la vez = una sola apuesta direccional grande. None = sin tope (todos
# los símbolos pueden abrir). Si se alcanza el tope, las señales nuevas se
# saltan hasta que se libere un slot. Default None (no cambia el motor en vivo);
# solo el backtest del cap lo activa hasta validar.
MAX_CONCURRENT = None

# Objetivo/stop anclados al momentum DIARIO
TP_DAILY_ATR_MULT = 1.0
TP_MIN_PCT = 0.015
TP_MAX_PCT = 0.08
# 0.5 → 0.75 (2026-06-11, A/B en ventana congelada): el stop a 0.5x del TP lo
# golpeaba el ruido normal de 1h — 83 stops (33% de trades, peak medio 1.8%)
# eran TODO el PnL negativo. Con 0.75x (mismo riesgo en $, qty menor): stops
# 83→54, WR 45.0→52.9%, PF 0.567→0.592, PnL −13.7%→−8.4%. RR pasa a 1:1.33.
SL_FRACTION_OF_TP = 0.75

# Escalera de profit (requisitos 4 y 5 del spec)
LOCK_STEP_PCT = 10           # asegura cada 10% de avance
PULLBACK_CLOSE_PCT = 8       # cierra si retrocede 8 pts desde lo asegurado

# Reducción de ruido (2026-07-01): NO se baja la frecuencia de avisos. Se
# probó throttlear el aviso de progreso a cada 20% (era AVISO_PROGRESO_STEP_PCT)
# y el usuario lo revirtió — reaccionar a tiempo importa más que menos mensajes.
# El aviso sigue cada LOCK_STEP_PCT=10% al subir Y al bajar. El ruido se reduce
# SEPARANDO comandos: /estado muestra solo lo EN CURSO; /history las cerradas
# del día (ejecutor.generar_estado / generar_history) — no tocando los avisos.

# Decil mínimo desde el cual el cierre-por-reversa se ARMA (añadido 2026-06-11).
# Hallazgo forense del primer backtest: TODOS los cierres "REVERSA desde 10%"
# salieron en pérdida neta — el piso 10−8 = 2% del recorrido (~0.06-0.1% de
# precio) está DEBAJO del breakeven de costos (≈0.2% de nocional ida+vuelta).
# Con piso 20−8 = 12% del recorrido el cierre ya es ganancia neta real.
# Esto NO reduce oportunidades (no toca entradas): solo evita convertir
# "asegurar profit" en "asegurar una pérdida pequeña". La notificación de
# deciles a Telegram sigue desde 10%.
PULLBACK_ARM_DECILE = 20

ADX_LATERAL_MAX = 20
RSI_MAX_LONG = 78
RSI_MIN_SHORT = 22
COOLDOWN_CANDLES = 2

# Modo de entrada (experimento 2026-06-11, pregunta del usuario: ¿los patrones
# de vela añaden ruido a la estrategia clásica de tendencia?):
#   'patrones'  — tendencia + 1 vela-patrón de confirmación (spec V25, EN VIVO)
#   'continua'  — tendencia alineada en cualquier cierre de vela (sin patrones)
#   'cruce'     — solo en la vela donde la tendencia SE VUELVE alineada (la
#                 estrategia EMA50/200 clásica publicada, sin capa de patrones)
# Solo walkforward.py lo cambia (en memoria); el bot en vivo usa 'patrones'.
ENTRY_MODE = 'patrones'

# TEST A (2026-06-11, modelo invitado): filtro de régimen por squeeze TTM —
# si BB(20,2σ) está completamente dentro de Keltner(EMA20±1.5×ATR20) en la
# vela de entrada (compresión/chop), se bloquea la entrada. Hipótesis: los
# cruces EMA50/200 dentro de un squeeze son whipsaws de rango (modo de falla
# V02/V11 del 4h-cruce). Solo walkforward.py lo activa (en memoria); el bot
# en vivo NO cambia.
FILTRO_SQUEEZE = False

# TEST B (2026-06-11, modelo invitado): filtro de fuerza relativa del basket —
# LONG solo si el símbolo está en la mitad SUPERIOR del ranking de ROC a
# RS_LOOKBACK_DAYS días entre los 6 símbolos al timestamp; SHORT solo en la
# mitad INFERIOR ("no comprar rezagados / no shortear líderes"). 20 días = el
# mismo horizonte del ancla de momentum diario (EMA20 1D), no un número nuevo.
# Solo walkforward.py lo activa (en memoria); el bot en vivo NO cambia.
FILTRO_RS = False
RS_LOOKBACK_DAYS = 20

# TEST C (2026-06-11, modelo invitado): modo de salida —
#   'escalera'  — spec V25: TP 1×ATR diario + deciles + pullback (EN VIVO)
#   'tendencia' — seguimiento de tendencia: SIN TP ni escalera; salida = stop
#                 de protección (igual que siempre) o FLIP de alineación
#                 completa al cierre (tendencia_actual == lado opuesto).
# Hipótesis: el cruce 4h tiene PF<1 con WR 55-65% = ganadores capados a ~1 día
# de movimiento; la rentabilidad del trend-following vive en la cola derecha.
# V28: modo 'copilot' — stop de protección + TP duro en 2R + deciles
# INFORMATIVOS (notificación cada 10% del recorrido), SIN cierre automático
# por pullback: entre el SL y el 2R la salida es decisión del trader.
EXIT_MODE = 'copilot'

# V28: el TP se define en R (R = distancia del SL, la ATR-validada de V25).
# "Objetivo de 2R como muy alto" (spec del usuario) — si llega, se cobra solo.
TP_R_MULT = 2.0

# V28: alerta urgente de reverso — cuando prob_reversion cruza ≥ este umbral
# con un trade abierto, aviso inmediato al trader (histéresis: se re-arma
# cuando baja del umbral − 10, para no spamear).
ALERTA_REVERSO_PROB = 60

# V28 (2026-06-24): AVISO DE RETROCESO (info pura, no cierra). Si el avance de
# una posición cayó a un decil por debajo de su pico, avisar — pero solo si el
# pico alcanzó al menos este nivel (debajo es ruido). Re-armado en cada pico
# nuevo; un aviso por cada decil inferior cruzado.
RETROCESO_MIN_PICO = 30

# SALVAVIDAS ratchet+reverso (2026-06-24, spec del usuario, REDISEÑADO):
# entre el SL y el 2R la salida sigue siendo del trader, EXCEPTO si — tras
# asegurar un decil D — el avance RETROCEDE a tocar D (prog <= D) Y el detector
# CALIBRADO de reverso confirma (prob_reversion >= PROB_REVERSION_MIN_CIERRE).
# Ahí se toma el profit automáticamente. Reemplaza el viejo gatillo absoluto
# (avance>=40 & prob>50) — ver evaluar_salida() rama copilot. Default OFF:
# solo walkforward.py lo activa hasta validar; el bot en vivo no cambia hasta
# decidir el despliegue.
AUTO_CIERRE_REVERSA = False
PROGRESO_MIN_CIERRE_REVERSA = 40   # (legado, ya no se usa en el gatillo ratchet)
PROB_REVERSION_MIN_CIERRE = 40     # umbral del detector calibrado (spec: >=40%)

# V34 (2026-07-01, diagnóstico de las 33 operaciones vivas): el detector
# CALIBRADO se computa con features puramente técnicos del estado actual
# (sobre-extensión vs EMA200, agotamiento RSI, vol_ratio, body/ATR, ADX) — no
# depende de que la posición ya tenga avance, así que también es evaluable EN
# EL MOMENTO DE LA SEÑAL (antes de abrir). En las 33 operaciones vivas:
# prob_reversion@entrada<30 -> WR 83.3%; 30-45 -> WR 52.6%; >=45 -> WR 0%
# (n=2, ambas stop completo). Filtro: NO abrir si la señal ya nace con
# prob_reversion >= PROB_REVERSION_MIN_CIERRE (reusa el umbral calibrado ya
# existente, no un número nuevo). Default OFF: solo walkforward.py lo activa
# hasta validar en 3 años/17 ventanas; el bot en vivo no cambia.
FILTRO_PROB_ENTRADA = False

# Detector de reverso CALIBRADO (calibrar_reverso.py, 2026-06-24): regresión
# logística sobre 25.285 estados de 3 años, validada OOS (corr +0.178 vs +0.023
# del heurístico viejo, calibración monotónica). Devuelve la probabilidad REAL
# de reverso. Si False, prob_reversion usa el heurístico viejo.
# DESPLEGADO 2026-06-24 (ON) SOLO PARA DISPLAY/ALERTA — AUTO_CIERRE_REVERSA
# sigue en False, así que el trading es IDÉNTICO al baseline (verificado en
# walkforward: detector-solo reproduce mediana 0.74 / suma 25.72 exacto). Solo
# mejora el número de reverso que ve el trader en Telegram (antes "siempre 15%").
DETECTOR_CALIBRADO = True

# V28: filtro opcional de "alta volatilidad" (spec) — solo tomar señales si el
# percentil del ATR (ventana WARMUP) es >= este valor. None = apagado; el
# backtest de reconocimiento reporta con y sin él para que el usuario decida.
VOLATILIDAD_MIN_PCT = None

# V27-A (2026-06-12, modelo invitado): re-entrada post-stop en tendencia
# vigente — tras un cierre por STOP el símbolo queda "re-armado": si la
# alineación persiste al pasar el cooldown, re-entra sin esperar flip nuevo
# (diagnóstico contrafactual: +$208 en 4 años dejados en la mesa). Solo
# walkforward.py lo activa; V26 vivo NO cambia hasta que valide.
REENTRY_POST_STOP = False

# --- Calidad de la vela de confirmación (añadido 2026-06-11, caso 2002d074:
# entrada SHORT confirmada por una vela de 0.42x ATR con 8.5% del volumen
# promedio — sin convicción ni participación). A/B en ventana congelada antes
# de quedar en vivo; ver el libro. ---
# Los patrones de continuación ya exigen volumen > Volume_MA; los de
# reversión/confirmación no exigían NADA — piso mínimo de participación:
# V30 STAGED para despliegue (2026-06-26): 0.5→1.0. El usuario aprobó desplegar
# V30 (filtro MACD + piso de volumen de reversión) PERO espera a que cierren las
# posiciones abiertas para hacer el redeploy. El cambio está en el código; el bot
# VIVO no cambia hasta correr deploy_gcp.sh. (Era 0.5; revertir a 0.5 + FILTRO
# False si se cancela el despliegue.)
REVERSAL_VOL_FLOOR = 1.0     # volumen >= 1.0x Volume_MA para reversión/confirmación (V30)

# V30 (2026-06-21, portado desde stable_v25_prototype): filtro de momentum
# para confirmaciones tipo 'reversion' — bloquear si MACD_Hist está del lado
# contrario al trade. Validado en el harness de V25 (mejora amplia: mediana
# -5.61%->-2.51%, 15/17 ventanas, combinado con REVERSAL_VOL_FLOOR=1.0). Bajo
# el modo copilot real: pctl vs azar 63→83, mediana +0.74→+1.27%. STAGED para
# despliegue 2026-06-26 (espera cierre de posiciones abiertas para el redeploy).
FILTRO_MACD_REVERSION = True
# Cuerpo mínimo de la vela disparadora en términos absolutos (lección V22
# body>=ATR): una micro-vela no puede "confirmar" una reversión de 3 velas.
BODY_MIN_ATR_FRACTION = 0.5  # Body >= 0.5x ATR (patrones de cuerpo)
# Para PATRONES_DE_MECHA (hammer/shooting star/etc.) el cuerpo es pequeño por
# definición — la barra de convicción equivalente es el rango total de la vela
# (añadido 2026-06-11: el filtro plano de cuerpo los eliminaba a todos).
WICK_RANGE_MIN_ATR_FRACTION = 0.75  # (high-low) >= 0.75x ATR (patrones de mecha)

# FASE 2 (2026-06-11): ejecución de la ORDEN de entrada (no toca la señal):
#   'market' — orden market directa (V25, default)
#   'maker'  — limit post-only al precio de señal + fallback market a los
#              ENTRY_MAKER_TIMEOUT_MIN si no llena (V26; supuesto del backtest)
ENTRY_EXECUTION = 'market'
ENTRY_MAKER_TIMEOUT_MIN = 10

TAKER_FEE = 0.0005           # contabilidad interna en vivo

# --- Costos del BACKTEST (motor honesto V24: comisión + slippage + funding) ---
BT_TAKER_FEE = 0.0005
BT_SLIPPAGE = 0.0005
BT_FUNDING_8H = 0.0001

# --- Rutas de datos ---
TRADES_FILE = os.path.join(DIR_BASE, 'trades_v28.json')
FORENSE_DIR = os.path.join(DIR_BASE, 'forense')
FORENSE_BACKTEST_DIR = os.path.join(DIR_BASE, 'forense_backtest')
