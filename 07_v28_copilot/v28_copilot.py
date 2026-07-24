"""
STABLE_V25_PROTOTYPE — punto de entrada (arquitectura desacoplada).

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
from ejecutor import GestorTrades, SymbolEngine, generar_estado, generar_history, log, HORARIO
from forense import RegistroForense
from telegram_bot import TelegramBot

START_TIME = datetime.now(timezone.utc)
estado_ws = {'ok': False, 'desde': None}


def main():
    log("STATUS: iniciando V28_COPILOT (asistente de trading 1h, testnet)")
    if not config.TELEGRAM_TOKEN:
        log("❌ ERROR FATAL: falta TELEGRAM_TOKEN_V28 en .env — V28 exige token "
            "propio (V25/V26 corren en paralelo con los suyos). Crear bot en "
            "@BotFather y definir TELEGRAM_TOKEN_V28.")
        return
    assert config.EXIT_MODE == 'copilot' and config.TP_R_MULT == 2.0 \
        and config.INTERVAL == '1h', "config de V28 alterada — revisar config.py"

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

    threading.Thread(target=stream_klines, args=(on_kline, estado_ws), daemon=True).start()
    threading.Thread(
        target=telegram.polling,
        kwargs={
            'on_take_profit': lambda tid: gestor.cerrar_por_id(
                tid, 'TOMA DE PROFIT MANUAL (Telegram)', precio_actual),
            'on_continue': gestor.marcar_continuar,
            'on_estado': lambda: generar_estado(gestor, engines, estado_ws, START_TIME),
            'on_history': lambda: generar_history(gestor),
            'on_horario': HORARIO.configurar,
        }, daemon=True).start()
    threading.Thread(target=hilo_balance, daemon=True).start()

    telegram.enviar(
        "🤝 V28_COPILOT OPERATIVO — tu asistente de trading (testnet, 1h)\n"
        f"• Mercados: {', '.join(config.SYMBOLS)}\n"
        "• YO: detecto la oportunidad (tendencia + patrón + volumen), monto la\n"
        "  operación con STOP seguro (−1R) y objetivo máximo 2R, y te aviso:\n"
        "  entrada, cada 10% del recorrido, BREAKEVEN de costos, volumen y\n"
        "  probabilidad de reverso (🚨 alerta urgente si se dispara)\n"
        "• VOS: decidís cuándo tomar el profit (botón 💰, válido siempre)\n"
        "• Solo cierro solo: stop tocado o 2R alcanzado\n"
        "• /estado = solo lo EN CURSO | /history = operaciones cerradas de hoy\n"
        "• /horario 08 AM a 10 PM para limitar cuándo CREO operaciones\n"
        "  (las abiertas siempre siguen hasta su meta)\n"
        "⚠️ Soy información, no edge: la calidad de la SALIDA es tuya")

    # --- heartbeat ---
    while True:
        time.sleep(300)
        with gestor.lock:
            abiertas = len(gestor.abiertas())
            bal = gestor.balance['usd']
        log(f"HEARTBEAT: WS={'OK' if estado_ws['ok'] else 'DOWN'} | abiertas={abiertas} | balance=${bal:.2f}")


if __name__ == '__main__':
    main()
