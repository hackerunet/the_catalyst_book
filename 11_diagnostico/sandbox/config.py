"""
config.py — Configuración central de V26_TENDENCIA (clon de stable_v25_prototype
con la config validada por los tests C/D del 2026-06-11: 4h + entrada por flip
de alineación + salida de seguimiento de tendencia; ver el libro "TEST C").

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

# V26: token PROPIO OBLIGATORIO (TELEGRAM_TOKEN_V26 en .env, crear en
# @BotFather) — V25 corre en paralelo con su propio token; compartir token
# rompe el getUpdates de ambos. El entrypoint se NIEGA a arrancar sin él.
TELEGRAM_TOKEN_COMPARTIDO = ''  # sin fallback compartido, a propósito
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_V26', '')
TELEGRAM_CHAT_ID = '1214526208'  # ÚNICO chat autorizado

# --- Endpoints (de los bots previos) ---
TESTNET_BASE = 'https://demo-fapi.binance.com'   # órdenes + cuenta (testnet)
DATA_BASE = 'https://fapi.binance.com'           # klines públicos
# FIX 2026-06-11: el stream era el de SPOT (stream.binance.com) mientras
# bootstrap/backtest/órdenes usan FUTUROS — precios casi iguales pero volumen
# ~10x menor; el trade 2002d074 (XRP SHORT) solo existió en datos spot (el
# evening star falla en las velas de futuros). Ahora todo es el mismo mercado.
WS_URL_BASE = 'wss://fstream.binance.com'        # stream multiplexado FUTUROS

BOT_NOMBRE = 'V26_TENDENCIA'

# --- Mercados: 3-6 símbolos, motores independientes ---
SYMBOLS = ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']

INTERVAL = '4h'              # V26: timeframe validado por el test C (continuo 4 años)
BOOTSTRAP_CANDLES = 600      # 4h → ~100 días: EMA200 4h + EMA20 diaria
MAX_CANDLES = 800            # ~133 días de contexto en memoria
WARMUP_CANDLES = 210         # mínimo de velas antes de evaluar señales (~35 días)

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

ADX_LATERAL_MAX = 20
RSI_MAX_LONG = 78
RSI_MIN_SHORT = 22
COOLDOWN_CANDLES = 8         # en HORAS (= 2 velas de 4h, igual que el harness)

# Modo de entrada (experimento 2026-06-11, pregunta del usuario: ¿los patrones
# de vela añaden ruido a la estrategia clásica de tendencia?):
#   'patrones'  — tendencia + 1 vela-patrón de confirmación (spec V25, EN VIVO)
#   'continua'  — tendencia alineada en cualquier cierre de vela (sin patrones)
#   'cruce'     — solo en la vela donde la tendencia SE VUELVE alineada (la
#                 estrategia EMA50/200 clásica publicada, sin capa de patrones)
# V26: entrada por FLIP de alineación (cruce), validada por el test C
# (continuo 4 años: +147.36% vs B&H +49.42%, PF 2.03, pctl 100 vs null) y
# re-confirmada vs Donchian en el test D. Sin capa de patrones a 4h.
ENTRY_MODE = 'cruce'

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
# V26: salida de SEGUIMIENTO DE TENDENCIA (test C): sin TP ni escalera; salida
# = stop de protección (tick a tick) o flip de alineación opuesta (al cierre
# de cada vela 4h). El TP manual por botón de Telegram sigue disponible.
EXIT_MODE = 'tendencia'

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

# FASE 2 (2026-06-11): entrada como MAKER — limit post-only al precio de
# señal + fallback market a los 10 min si no llena. Es el supuesto de costos
# del backtest del test C (0.02%/lado); el fallback garantiza que toda señal
# se llena (como asume el backtest). Solo ejecución — la señal no cambia.
ENTRY_EXECUTION = 'maker'
ENTRY_MAKER_TIMEOUT_MIN = 10

TAKER_FEE = 0.0005           # contabilidad interna en vivo

# --- Costos del BACKTEST (motor honesto V24: comisión + slippage + funding) ---
BT_TAKER_FEE = 0.0005
BT_SLIPPAGE = 0.0005
BT_FUNDING_8H = 0.0001

# --- Rutas de datos ---
TRADES_FILE = os.path.join(DIR_BASE, 'trades_v26.json')
FORENSE_DIR = os.path.join(DIR_BASE, 'forense')
FORENSE_BACKTEST_DIR = os.path.join(DIR_BASE, 'forense_backtest')
