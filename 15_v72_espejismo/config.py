"""
config.py — Configuración central de V72_ESPEJIMO ("El Espejismo").

QUÉ ES: una DEMOSTRACIÓN, no un intento de ganar plata. Prueba en vivo que el
win rate es un DIAL (WR ≈ SL/(TP+SL)) y no una habilidad. Misma ENTRADA que V26
(cruce 4h); lo único distinto es la salida: TP duro + STOP en vez de dejar correr.
Backtest 4 años en esta canasta: 452 trades, WR 76.33%, PnL +2.61% (PF 1.071).
Es decir: acierta 3 de cada 4 veces y no produce nada — mientras V26, con la MISMA
entrada y 18% de acierto, hace +130%. Ver el libro "V72 — EL ESPEJISMO".

CORRE EN TESTNET Y COMPARTE CUENTA con sinapsis_lateral (Binance demo no tiene
subcuentas), por eso la canasta NO se solapa con la suya — cero neteo.

Único lugar donde se cargan credenciales (.env del proyecto, igual que los
bots previos) y se definen parámetros de estrategia/ejecución. Ningún otro
módulo lee variables de entorno directamente.
"""
import os
from dotenv import load_dotenv

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BASE, '..', '..', '.env'))

# --- Entorno: TESTNET HARDCODEADO, a propósito ---
# V72 es una DEMOSTRACIÓN de que el win rate es un dial (se espera que NO gane
# plata: ~+2.61% en 4 años con 76% de acierto). NUNCA debe tocar dinero real, ni
# por un descuido de .env. Por eso NO lee BINANCE_ENV: está fijo en 'testnet'.
# Mismo patrón que sinapsis_lateral. Para graduarlo a mainnet (no se prevé) hay
# que cambiar esta línea a mano.
BINANCE_ENV = 'testnet'
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

# V72: token PROPIO OBLIGATORIO (TELEGRAM_TOKEN_V72 en .env, bot @Hackerunet_v72bot).
# Comparte la CUENTA de testnet con Sinapsis (Binance demo no tiene subcuentas),
# pero NO puede compartir el token: Telegram entrega cada update UNA sola vez, así
# que dos procesos con el mismo token se roban los mensajes entre sí y los comandos
# caen en el bot equivocado al azar. El entrypoint se NIEGA a arrancar sin él.
TELEGRAM_TOKEN_COMPARTIDO = ''  # sin fallback compartido, a propósito
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_V72', '')
TELEGRAM_CHAT_ID = '1214526208'  # ÚNICO chat autorizado

# --- Endpoints (de los bots previos) ---
# BINANCE_ENV ya se definió arriba (junto a la selección de llaves). Aquí solo elige
# la URL de órdenes/cuenta. El nombre TESTNET_BASE se conserva por compatibilidad
# con binance_client.py. Para ir a mainnet: BINANCE_ENV=mainnet + llaves MAINNET_* + redeploy.
TESTNET_BASE = 'https://demo-fapi.binance.com' if BINANCE_ENV != 'mainnet' \
    else 'https://fapi.binance.com'              # órdenes + cuenta
DATA_BASE = 'https://fapi.binance.com'           # klines públicos (siempre real)
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

BOT_NOMBRE = 'V72_ESPEJISMO'

# --- Mercados: 3-6 símbolos, motores independientes ---
# CANASTA: solo ALTCOINS y SIN SOLAPE con Sinapsis (SOL/BNB/XRP/ADA/LINK).
# Comparten la cuenta de testnet (Binance demo no tiene subcuentas) -> cero
# simbolos en comun = cero neteo. Sin ETH ni BTC (pedido del usuario: que las
# dos canastas sean comparables, sin los majors distorsionando).
SYMBOLS = ['DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']

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
# DIAL DE RIESGO 2026-07-09 (go-live mainnet): bajado 0.02 -> 0.015 (2% -> 1.5%
# de tope agregado; 0.25%/trade). Baja el MDD-90d bajo el gate de copy-trade con
# más colchón, conservando ~+98% en 4 años de backtest (ver CAMINO_A_MAINNET.md).
PORTFOLIO_RISK_CAP = 0.02
# 0.02/6 = 0.33% - el valor EXACTO con el que se valido (RISK_DEFAULT del harness).
# NO usar /len(SYMBOLS)=5: daria 0.4% y el repro-test no reproduciria. Misma
# trampa que se documento en V36.
RISK_PER_TRADE = 0.02 / 6

# Piso de balance para OPERAR en mainnet (validación de balance, 2026-07-09): si
# BINANCE_ENV=mainnet y el balance real es < este piso (o falla la lectura), el bot
# NO abre operaciones (evita dimensionar contra una cuenta vacía / lectura fallida).
# En testnet no aplica (paper). Ver la guarda en ejecutor.evaluar_entrada.
MAINNET_MIN_BALANCE = 50.0

# CORTACIRCUITOS DE EQUITY (2026-07-09, pedido del usuario): en mainnet, si el balance
# real cae por debajo de este piso, los bots DEJAN DE ABRIR nuevas operaciones (las
# abiertas se siguen gestionando normal). Es una garantía DURA por encima del peor
# drawdown del backtest (~$401 en 4 años) — protege más allá de lo que la historia
# muestra. El monitor de salud alerta por Telegram si se cruza. Cambiar el número aquí
# ajusta el piso. En testnet no aplica.
MAINNET_STOP_EQUITY = 300.0

# Objetivo/stop anclados al momentum DIARIO
TP_DAILY_ATR_MULT = 1.0
TP_MIN_PCT = 0.015
TP_MAX_PCT = 0.08
# 0.5 → 0.75 (2026-06-11, A/B en ventana congelada): el stop a 0.5x del TP lo
# golpeaba el ruido normal de 1h — 83 stops (33% de trades, peak medio 1.8%)
# eran TODO el PnL negativo. Con 0.75x (mismo riesgo en $, qty menor): stops
# 83→54, WR 45.0→52.9%, PF 0.567→0.592, PnL −13.7%→−8.4%. RR pasa a 1:1.33.
# EL DIAL. dist_sl = dist_tp * SL_FRACTION_OF_TP -> WR ~ SLF/(1+SLF).
# 3.0 => TP = 1/3 del SL => WR teorico 75% (medido: 76.33% en esta canasta).
# Derivado de la teoria, NO escaneado.
SL_FRACTION_OF_TP = 3.0

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
# 999 = DESARMA el cierre por retroceso -> la escalera queda como TP duro + STOP
# puro (equivalente al modo 'copilot'). Sin esto cerraria por pullback y el WR
# ya no saldria del dial.
PULLBACK_ARM_DECILE = 999

# V34-V26 (2026-07-01): aviso de ROUND-TRIP VIOLENTO — informativo, NO cierra
# nada (V31 ya probó que un trailing/protección MECÁNICA en V26 destruye 90%
# del PnL porque corta cualquier giveback, chico o catastrófico). Este aviso
# es distinto: solo avisa cuando una posición que YA alcanzó un pico grande
# (>=ALERTA_ROUNDTRIP_MIN_PICO) cae a progreso NEGATIVO real — el patrón
# confirmado en BNBUSDT/SOLUSDT/ETHUSDT del 24-jun al 01-jul (pico 70-146%
# -> negativo real, en un caso hasta -41% durante 3 días). Se re-arma solo
# tras un pico REALMENTE nuevo (mayor al último alertado), así que un mismo
# techo que oscila no re-alerta — pero un segundo ciclo pico-nuevo->negativo
# sí. La decisión de cerrar sigue siendo 100% del usuario.
ALERTA_ROUNDTRIP_MIN_PICO = 50

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
# 'escalera' + PULLBACK_ARM_DECILE=999 = TP/SL puro. NO 'tendencia' (ese es V26).
EXIT_MODE = 'escalera'

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
# maker 0.02%/lado — es lo que se VALIDÓ (carrera_altcoins.py) y lo que el bot
# hace en vivo: ENTRY_EXECUTION='maker' (post-only con fallback). Con 0.0005
# (taker) el repro daba +1.59% en vez de +2.61%: mismos 452 trades y mismo WR
# 76.33%, solo cambiaba el dinero. El repro-test lo atrapó.
BT_TAKER_FEE = 0.0002
BT_SLIPPAGE = 0.0002
BT_FUNDING_8H = 0.0001

# --- Rutas de datos ---
TRADES_FILE = os.path.join(DIR_BASE, 'trades_v72.json')
FORENSE_DIR = os.path.join(DIR_BASE, 'forense')
FORENSE_BACKTEST_DIR = os.path.join(DIR_BASE, 'forense_backtest')
