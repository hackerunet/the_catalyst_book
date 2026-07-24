"""
V72_ESPEJISMO — punto de entrada. Usa el MOTOR de V26; la estrategia es OTRA.

QUÉ ES: una demostración en vivo de que el win rate es un DIAL (WR ≈ SL/(TP+SL))
y no una habilidad. NO busca ganar plata — se espera que NO gane.

  4h | entrada = flip de alineación (EMA50/200 + ADX>=20 + momentum diario)
     |           ** LA MISMA DE V26 ** — así la única variable es la salida
     | salida  = TP duro + STOP (escalera con el pullback DESARMADO), dial 3.0
     |           => TP = 1/3 del SL => WR ~75% por pura geometría
  Backtest 4 años (DOGE/AVAX/DOT/LTC/ATOM): 452 trades, WR 76.33%, PnL +2.61%,
  PF 1.071, MaxDD 4.8%, ganadora promedio $0.57.
  CONTRASTE: V26, con la MISMA entrada y 18.08% de acierto, hace +130.59% con
  ganadora promedio $17.72 (33x). Acertar 4x más produce 50x menos.
  Ver el libro "V72 — EL ESPEJISMO" y la grilla de 28 celdas (error medio del
  dial vs la teoría: 1.36pp en 15m/1h/4h/1d × 2 canastas).

CORRE EN TESTNET (hardcodeado) y COMPARTE CUENTA con sinapsis_lateral — Binance
demo no tiene subcuentas. Por eso su canasta NO se solapa con la de Sinapsis
(SOL/BNB/XRP/ADA/LINK): cero símbolos en común = cero neteo. La lección del
2026-07-16 en mainnet (92.3% de horas neteadas) aplicada de entrada.

Lanzamiento (requiere TELEGRAM_TOKEN_V72 en .env — crear bot en @BotFather):
  cd bot_alpha_portfolio/v72_espejismo && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u v72_espejismo.py > v72.out 2>&1 & disown

Arquitectura desacoplada (idéntica a V25):

Módulos (cada responsabilidad en su archivo, sin monolito):
  config.py          — credenciales (.env) + parámetros. Único lector de entorno.
  binance_client.py  — autorización y TODA la comunicación con Binance
                       (REST firmado testnet + klines públicos + stream WS).
  indicadores.py     — indicadores técnicos puros.
  patrones.py        — biblioteca de 18 patrones de vela (puro).
  estrategia.py      — decisiones de entrada/salida PURAS, compartidas 1:1
                       entre el bot en vivo y el backtest.
  ejecutor.py        — ejecutor en vivo: GestorTrades + SymbolEngine por símbolo.
  telegram_bot.py    — envío + polling de Telegram (callbacks inyectados).
  forense.py         — registro forense por operación (activación + seguimiento
                       por vela + cierre) para evaluar la estrategia a posteriori.
  backtest.py        — backtest honesto (reloj global + intravela pesimista +
                       costos completos) sobre la MISMA estrategia. CLI:
                       `python3 backtest.py --candles 1500 [--end 2026-06-09]`

Este archivo solo CABLEA los módulos y levanta los hilos (WS / Telegram /
balance). El comando de lanzamiento no cambia:
  nohup .../trading_env/bin/python3 -u stable_v25_prototype.py > v25.out 2>&1 & disown
"""
import threading
import time
from datetime import datetime, timezone

import config
from binance_client import BinanceClient, stream_klines
from ejecutor import GestorTrades, SymbolEngine, generar_estado, generar_history, log
from forense import RegistroForense
from telegram_bot import TelegramBot

START_TIME = datetime.now(timezone.utc)
estado_ws = {'ok': False, 'desde': None}


def main():
    log(f"STATUS: iniciando V72_ESPEJISMO ({config.BINANCE_ENV.upper()}, 4h, "
        f"TP/SL dial {config.SL_FRACTION_OF_TP} → WR objetivo "
        f"~{100*config.SL_FRACTION_OF_TP/(1+config.SL_FRACTION_OF_TP):.0f}%)")
    if not config.TELEGRAM_TOKEN:
        log("❌ ERROR FATAL: falta TELEGRAM_TOKEN_V72 en .env — V72 exige token "
            "propio (Sinapsis corre en paralelo; compartir token rompe el "
            "getUpdates de ambos). Crear bot en @BotFather y definir "
            "TELEGRAM_TOKEN_V72.")
        return

    # Guarda 1 — NUNCA dinero real. V72 es una demostración que SE ESPERA que no
    # gane (+2.61% en 4 años con 76% de acierto); no tiene por qué tocar mainnet.
    assert config.BINANCE_ENV == 'testnet' and 'demo-fapi' in config.TESTNET_BASE, \
        "V72 SOLO corre en testnet — es una demostración, no un bot de producción"

    # Guarda 2 — la config del dial es la validada (452 trades / WR 76.33% / +2.61%).
    assert config.ENTRY_MODE == 'cruce' and config.EXIT_MODE == 'escalera' \
        and config.INTERVAL == '4h' and config.SL_FRACTION_OF_TP == 3.0 \
        and config.PULLBACK_ARM_DECILE == 999, \
        "config de V72 alterada — revisar config.py (dial=3.0, pullback desarmado)"

    # Guarda 3 — cero solape con Sinapsis: comparten la cuenta de testnet, así que
    # un símbolo en común significaría neteo (la lección del 2026-07-16 en mainnet).
    _sinapsis = {'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT'}
    _choque = _sinapsis & set(config.SYMBOLS)
    assert not _choque, f"SOLAPE con Sinapsis {_choque} — netearía la cuenta compartida"

    # --- cableado de módulos ---
    cliente = BinanceClient()
    telegram = TelegramBot()
    forense = RegistroForense(config.FORENSE_DIR)
    gestor = GestorTrades(cliente, telegram, forense)
    engines = {sym: SymbolEngine(sym, gestor, cliente, telegram, forense)
               for sym in config.SYMBOLS}

    # --- inicialización de cuenta/datos ---
    cliente.cargar_precision()
    b = cliente.obtener_balance()
    if b is not None:
        gestor.balance['usd'] = b
        gestor.balance['inicial'] = b
    cliente.configurar_leverage()

    for eng in engines.values():
        try:
            eng.bootstrap()
        except Exception as e:
            log(f"ERROR bootstrap {eng.symbol}: {e}")
        time.sleep(0.3)

    # --- hilos ---
    def on_kline(k):
        eng = engines.get(k['s'].upper())
        if eng is not None and not eng.df.empty:
            eng.actualizar_tick(k)

    def hilo_balance():
        while True:
            b = cliente.obtener_balance()
            if b is not None:
                with gestor.lock:
                    gestor.balance['usd'] = b
            time.sleep(15)

    def precio_actual(symbol):
        eng = engines.get(symbol)
        return eng.ultimo_precio if eng else None

    def cerrar_todo_cb(ejecutar):
        """Botón de pánico /cerrartodo (con confirmación) — cierra TODO a mercado."""
        abiertas = [t for t in gestor.trades if t['status'] == 'ABIERTA']
        if not ejecutar:
            if not abiertas:
                return "No hay posiciones abiertas."
            return (f"⚠️ {len(abiertas)} posiciones abiertas. Enviá  /cerrartodo si  "
                    "para CERRARLAS TODAS a mercado (esto NO se puede deshacer).")
        cerradas = gestor.cerrar_todas('CIERRE MANUAL MASIVO (Telegram /cerrartodo)', precio_actual)
        if not cerradas:
            return "No había posiciones abiertas."
        total = sum(p for _, _, p in cerradas)
        lineas = [f"✅ Cerradas {len(cerradas)} posiciones a mercado. PnL total ${total:+.2f}"]
        for s, ty, p in cerradas:
            lineas.append(f"  • {s} {ty}: ${p:+.2f}")
        return "\n".join(lineas)

    threading.Thread(target=stream_klines, args=(on_kline, estado_ws), daemon=True).start()
    threading.Thread(
        target=telegram.polling,
        kwargs={
            'on_take_profit': lambda tid: gestor.cerrar_por_id(
                tid, 'TOMA DE PROFIT MANUAL (Telegram)', precio_actual),
            'on_continue': gestor.marcar_continuar,
            'on_estado': lambda: generar_estado(gestor, engines, estado_ws, START_TIME),
            'on_history': lambda: generar_history(gestor),
            'on_cerrar_todo': cerrar_todo_cb,
        }, daemon=True).start()
    threading.Thread(target=hilo_balance, daemon=True).start()

    _real = config.BINANCE_ENV == 'mainnet'
    _modo = "🔴 MAINNET — DINERO REAL" if _real else "🧪 TESTNET (paper trading)"
    _foot = ("⚠️ DINERO REAL: opera con tu capital. /cerrartodo si → cierra TODO a mercado."
             if _real else
             "⚠️ Paper-trading: el forward test ES la validación, no usar capital real")
    telegram.enviar(
        f"🚀 V72_ESPEJISMO OPERATIVO — {_modo} (4h, TP/SL dial 3.0)\n⚠️ Esto NO busca ganar: demuestra que el WR es un dial.\nBacktest 4a: 76% de acierto, +2.6% de retorno.\n"
        f"• Entorno: {config.BINANCE_ENV.upper()} | Balance: ${gestor.balance['usd']:.2f} | "
        f"riesgo {config.RISK_PER_TRADE*100:.2f}%/trade\n"
        f"• Mercados: {', '.join(config.SYMBOLS)} — motores independientes\n"
        "• Entrada: FLIP de alineación 4h (EMA50/200 + ADX≥20 + momentum diario)\n"
        "• Salida: stop de protección o FLIP opuesto — SIN TP, SIN escalera\n"
        "• Backtest continuo 4 años: +147% vs B&H +49%, PF 2.0, DD 21%\n"
        "• PERFIL: semanas de stops chicos + pocas posiciones de 1-6 meses que pagan todo\n"
        "• Botón TOMAR PROFIT siempre | /estado | /history | /cerrartodo\n"
        + _foot)

    # --- heartbeat ---
    while True:
        time.sleep(300)
        with gestor.lock:
            abiertas = len(gestor.abiertas())
            bal = gestor.balance['usd']
        log(f"HEARTBEAT: WS={'OK' if estado_ws['ok'] else 'DOWN'} | abiertas={abiertas} | balance=${bal:.2f}")


if __name__ == '__main__':
    main()
