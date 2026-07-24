"""
config.py — Configuración central de STABLE_V25_PROTOTYPE.

Único lugar donde se cargan credenciales (.env del proyecto, igual que los
bots previos) y se definen parámetros de estrategia/ejecución. Ningún otro
módulo lee variables de entorno directamente.
"""
import os
from dotenv import load_dotenv

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BASE, '..', '..', '.env'))

# --- Credenciales (de los bots previos del proyecto) ---
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

# Token/chat de las mesas V21/V22; aislable con TELEGRAM_TOKEN_V25 en .env
TELEGRAM_TOKEN_COMPARTIDO = 'PONE_TU_TOKEN_DE_TELEGRAM_AQUI'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_V25', TELEGRAM_TOKEN_COMPARTIDO)
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

BOT_NOMBRE = 'STABLE_V25_PROTOTYPE'

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

# Decil mínimo desde el cual el cierre-por-reversa se ARMA (añadido 2026-06-11).
# Hallazgo forense del primer backtest: TODOS los cierres "REVERSA desde 10%"
# salieron en pérdida neta — el piso 10−8 = 2% del recorrido (~0.06-0.1% de
# precio) está DEBAJO del breakeven de costos (≈0.2% de nocional ida+vuelta).
# Con piso 20−8 = 12% del recorrido el cierre ya es ganancia neta real.
# Esto NO reduce oportunidades (no toca entradas): solo evita convertir
# "asegurar profit" en "asegurar una pérdida pequeña". La notificación de
# deciles a Telegram sigue desde 10%.
PULLBACK_ARM_DECILE = 20

# V32 (2026-06-21): time-stop — cierre a mercado si tras TIME_STOP_HOURS desde
# la entrada el trade NUNCA alcanzó LOCK_STEP_PCT (10%) de progreso. Solo
# EXIT_MODE='escalera'. Diagnóstico forense (324 trades, 3000 velas):
# 80/108 stops nunca llegan a decil 10 (duración mediana 16.5h, máx 109h —
# capital muerto, no falla instantánea); de 164 ganadores reales, solo 6
# (3.7%) tardan >36h en su primer decil 10, y esos 6 tenían progreso ≈0% en
# la hora 36 (cerrarlos ahí da breakeven, no pérdida). 36h elegido sobre 24h
# por sacrificar menos ganadores (6 vs 17 de 164). Default None = inactivo;
# solo walkforward.py lo activa.
TIME_STOP_HOURS = None

ADX_LATERAL_MAX = 20
RSI_MAX_LONG = 78
RSI_MIN_SHORT = 22
COOLDOWN_CANDLES = 2

# Modo de entrada (experimento 2026-06-11, pregunta del usuario: ¿los patrones
# de vela añaden ruido a la estrategia clásica de tendencia?):
#   'patrones'      — tendencia + 1 vela-patrón de confirmación (spec V25, EN VIVO)
#   'continua'      — tendencia alineada en cualquier cierre de vela (sin patrones)
#   'cruce'         — solo en la vela donde la tendencia SE VUELVE alineada (la
#                     estrategia EMA50/200 clásica publicada, sin capa de patrones)
#   'donchian'      — ruptura del canal de 20 velas con tendencia alineada (TEST D)
#   'rsi_reversion' — V29-A (2026-06-20): cruce de RSI por 30/70 como señal
#                     PRIMARIA, SIN filtro de tendencia (clase nunca probada
#                     de forma aislada — ver el libro). Default OFF.
# Solo walkforward.py lo cambia (en memoria); el bot en vivo usa 'patrones'.
ENTRY_MODE = 'patrones'

# V29-A (2026-06-20): umbrales de cruce de RSI para ENTRY_MODE='rsi_reversion'
# — mismos valores redondos 30/70 ya usados como filtro de exhaución en Puerta
# B de V22, ahora como señal primaria. NO escaneados.
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# V30 (2026-06-21): filtro de momentum para confirmaciones de patrones tipo
# 'reversion' (no 'continuacion') — bloquear si MACD_Hist está del lado
# contrario a la dirección del trade. Diagnóstico forense del trade SOL
# perdedor del 2026-06-20 motivó la hipótesis, pero un chequeo de sanidad en
# n=3 ya mostró que NO separa limpio ganadoras de perdedoras — se testea con
# el walk-forward completo, no se decide de una operación. Default OFF; solo
# walkforward.py lo activa (en memoria).
FILTRO_MACD_REVERSION = False

# Tarea #41 (2026-07-03): candidatos "pendientes menores" del PLAN_DE_PRUEBAS
# (sección INTRADÍA/1h) — requieren pre-registro + walk-forward per metodología.
#
# (a) EXCLUIR_MARUBOZU_BAJISTA — excluir el patrón "Marubozu bajista" como vela
#     de confirmación de entrada (modo 'patrones'). En 33 ops vivas de V28
#     (2026-07-01, sección V34) fue 14 trades, WR 42.9%, −$75.18 (~todo el PnL
#     negativo del bot). Evidencia chica (n=14). Exclusión pura, zero-parámetro
#     (NO un umbral escaneado de convicción). Default OFF; solo walkforward.py.
EXCLUIR_MARUBOZU_BAJISTA = False
#
# (b) FILTRO_SESION_HORAS_BLOQUEADAS — filtro de sesión horaria (nunca explorado
#     en esta familia). Bloquea entradas nuevas cuya vela de señal cierra dentro
#     de la ventana de MENOR liquidez de cripto perps (identificada por el perfil
#     de VOLUMEN del basket, no por el PnL: bloque contiguo 8h UTC de menor
#     volumen medio = 22:00–06:00 UTC). Set de horas UTC bloqueadas o None
#     (inactivo). Default OFF; solo walkforward.py lo activa (en memoria).
FILTRO_SESION_HORAS_BLOQUEADAS = None  # p.ej. {22, 23, 0, 1, 2, 3, 4, 5}

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
# Solo walkforward.py lo cambia (en memoria); el bot en vivo NO cambia.
EXIT_MODE = 'escalera'

# V31 (2026-06-21): trailing stop para EXIT_MODE='tendencia' — el sistema solo
# tiene STOP estático o FLIP, nada intermedio; el perfil de V26 (WR~18%, pocos
# ganadores enormes) significa que TODO el edge vive en la cola — la idea es
# asegurar parte de esa cola sin capar el ganador. Una vez que la excursión
# favorable alcanza TRAILING_ARM_R (mismo umbral +2R ya validado en los
# experimentos de breakeven de V22, no un número nuevo), el stop ratchetea a
# peak - TRAILING_DISTANCE_R (en unidades de R = dist_sl del trade). Nunca se
# afloja. Antes de armarse, el stop sigue estático (protege el perfil de WR
# bajo). Solo walkforward.py lo activa; V26 vivo NO cambia hasta que valide.
TRAILING_STOP_TENDENCIA = False
TRAILING_ARM_R = 2.0
TRAILING_DISTANCE_R = 1.0

# V37-C (2026-07-03): SCALE-OUT PARCIAL + RUNNER ÍNTEGRO para EXIT_MODE=
# 'tendencia' — mecanismo DISTINTO al trailing de V31 (rechazado): V31 movía
# el stop de TODA la posición (cualquier retroceso normal post-arme cortaba el
# 100% del ganador; FLIP 83→6, PnL −90%). Aquí NINGÚN stop se mueve: al
# alcanzar la excursión favorable +SCALE_OUT_R (en unidades de R = dist_sl,
# mismo hito +1R de los experimentos de breakeven de V22), se realiza
# SCALE_OUT_FRACTION de la posición a ese precio; el resto conserva el stop
# ORIGINAL y la salida por flip intactos (el perfil validado del Test C).
# Hipótesis: flujo de caja temprano que sube el piso de las ventanas de 1 año
# a costo acotado de cola (solo se capa el 25% de cada ganador). Default OFF;
# solo suavizado_v37.py lo activa (en memoria). El bot V26 vivo NO cambia.
SCALE_OUT_TENDENCIA = False
SCALE_OUT_R = 1.0
SCALE_OUT_FRACTION = 0.25

# V27-A (2026-06-12, modelo invitado): re-entrada post-stop en tendencia
# vigente — tras un cierre por STOP el símbolo queda "re-armado": si la
# alineación persiste al pasar el cooldown, re-entra sin esperar flip nuevo
# (diagnóstico contrafactual: +$208 en 4 años dejados en la mesa). Solo
# walkforward.py lo activa; V26 vivo NO cambia hasta que valide.
REENTRY_POST_STOP = False

# P2 (2026-07-04, pregunta 3 del usuario — "agotamiento de tendencia" en vez
# de solo flip completo): para EXIT_MODE='tendencia', cerrar la posición si
# el régimen (tendencia_actual, MISMO umbral ADX_LATERAL_MAX ya usado en toda
# la estrategia) se vuelve LATERAL durante EXHAUSTION_LATERAL_VELAS velas
# consecutivas — sin esperar el flip a la alineación COMPLETAMENTE opuesta.
# EXHAUSTION_LATERAL_VELAS=2 reusa el patrón de "confirmación de 2 velas" ya
# usado en el proyecto (V22 TENDENCIA_EMERGENTE) — no es un número nuevo.
# Prior del proyecto: 4to intento de la familia "salir antes del flip por una
# señal de decaimiento" (V31 trailing, V33 prob. calibrada, V37-C scale-out,
# los 3 rechazados) — mecanismo DISTINTO (reglas de régimen, no ML ni
# distancia de precio), se testea con su propio veredicto honesto.
# Solo walkforward.py lo activa; V26/V36 vivos NO cambian hasta que valide.
EXHAUSTION_EXIT_TENDENCIA = False
EXHAUSTION_LATERAL_VELAS = 2

# P1 (2026-07-04, pregunta 2 del usuario — "cerrar y replicar"): para
# EXIT_MODE='tendencia', al alcanzar REPLICA_ARM_PROGRESS de avance (150% —
# reusa el límite de bucket ya existente en giveback_analisis.py, no un
# número nuevo) O al confirmarse REPLICA_LATERAL_VELAS velas LATERAL
# consecutivas (mismo mecanismo de conteo que EXHAUSTION_EXIT_TENDENCIA),
# cerrar la posición COMPLETA (realiza la ganancia) y abrir INMEDIATAMENTE
# una réplica en la MISMA dirección con sizing fresco (misma fórmula
# ATR-based que cualquier entrada nueva) — la réplica sigue las reglas
# normales (stop propio + flip) desde ahí y puede volver a disparar el mismo
# mecanismo. Diferencia mecánica declarada vs V31 (rechazado): V31 movía el
# stop de LA MISMA posición; acá se cierra del todo y la ganancia ya
# cristalizada queda protegida pase lo que pase con la réplica — mecanismo
# genuinamente distinto, se testea con su propio veredicto honesto, no se
# asume el resultado de V31 por analogía.
# Solo walkforward.py lo activa; V26/V36 vivos NO cambian hasta que valide.
REPLICA_TENDENCIA = False
REPLICA_ARM_PROGRESS = 150.0
REPLICA_LATERAL_VELAS = 2

# ============================================================================
# COPIA AISLADA v26_salida_test (2026-07-04) — pedido del usuario tras señalar
# que la P2 ya probada era una versión SIMPLIFICADA de "agotamiento de
# tendencia" (solo nivel de ADX vía tendencia_actual/LATERAL). Faltaban dos
# piezas de la hipótesis original, cada una testeada SEPARADA (no combinada):
# ============================================================================

# TEST 1 — ADX cayendo desde un nivel ALTO (dinámica, no nivel). Distinto de
# P2 (que mira si ADX está POR DEBAJO del umbral lateral existente, 20): esto
# exige que el trade haya visto ADX>=40 (el umbral citado en la hipótesis
# original, no escaneado) en algún momento desde la entrada, y LUEGO caiga
# ADX_DECLINE_VELAS velas consecutivas (mismo patrón de confirmación de 2
# velas ya usado en el proyecto — V22, P2). Cierra SIN esperar el flip.
ADX_DECLINE_EXIT_TENDENCIA = False
ADX_DECLINE_THRESHOLD = 40.0
ADX_DECLINE_VELAS = 2

# TEST 2 — Divergencia de RSI: el precio hace un nuevo máximo/mínimo de
# RSI_DIVERGENCE_LOOKBACK velas (14 = el propio período del RSI, no un número
# nuevo) pero el RSI en esa vela NO confirma (es menor/mayor que su propio
# máximo/mínimo en la misma ventana, EXCLUYENDO la vela actual — columnas
# Div_Bajista/Div_Alcista de indicadores.py, vectorizadas y causales). Cierra
# SIN esperar el flip.
RSI_DIVERGENCE_EXIT_TENDENCIA = False
RSI_DIVERGENCE_LOOKBACK = 14

# --- Calidad de la vela de confirmación (añadido 2026-06-11, caso 2002d074:
# entrada SHORT confirmada por una vela de 0.42x ATR con 8.5% del volumen
# promedio — sin convicción ni participación). A/B en ventana congelada antes
# de quedar en vivo; ver el libro. ---
# Los patrones de continuación ya exigen volumen > Volume_MA; los de
# reversión/confirmación no exigían NADA — piso mínimo de participación:
REVERSAL_VOL_FLOOR = 0.5     # volumen >= 0.5x Volume_MA para reversión/confirmación
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
TRADES_FILE = os.path.join(DIR_BASE, 'trades_v25.json')
FORENSE_DIR = os.path.join(DIR_BASE, 'forense')
FORENSE_BACKTEST_DIR = os.path.join(DIR_BASE, 'forense_backtest')
