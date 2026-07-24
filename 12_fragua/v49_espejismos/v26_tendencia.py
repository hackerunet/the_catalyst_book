"""
V26_TENDENCIA — punto de entrada (clon de stable_v25_prototype, config
validada por los tests C/D del 2026-06-11 — ver el libro "TEST C"):

  4h | entrada = flip de alineación (EMA50/200 + ADX>=20 + momentum diario)
     | salida = stop de protección o flip opuesto (SIN TP, SIN escalera)
  Backtest continuo 4 años: +147.36% vs B&H +49.42%, PF 2.03, DD 20.9%,
  pctl 100 vs null. PERFIL: semanas de stops chicos (−0.33% c/u) + pocas
  posiciones de 1-6 meses que pagan todo — NO juzgar antes de 3+ meses.

Lanzamiento (requiere TELEGRAM_TOKEN_V26 en .env — crear bot en @BotFather):
  cd bot_alpha_portfolio/v26_tendencia && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u v26_tendencia.py > v26.out 2>&1 & disown

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
    log("STATUS: iniciando V26_TENDENCIA (testnet, paper trading, 4h, salida de tendencia)")
    if not config.TELEGRAM_TOKEN:
        log("❌ ERROR FATAL: falta TELEGRAM_TOKEN_V26 en .env — V26 exige token "
            "propio (V25 corre en paralelo; compartir token rompe el getUpdates "
            "de ambos). Crear bot en @BotFather y definir TELEGRAM_TOKEN_V26.")
        return
    assert config.ENTRY_MODE == 'cruce' and config.EXIT_MODE == 'tendencia' \
        and config.INTERVAL == '4h', "config de V26 alterada — revisar config.py"

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
        }, daemon=True).start()
    threading.Thread(target=hilo_balance, daemon=True).start()

    telegram.enviar(
        "🚀 V26_TENDENCIA OPERATIVO (testnet, 4h, seguimiento de tendencia)\n"
        f"• Mercados: {', '.join(config.SYMBOLS)} — motores independientes\n"
        "• Entrada: FLIP de alineación 4h (EMA50/200 + ADX≥20 + momentum diario)\n"
        "• Salida: stop de protección o FLIP opuesto — SIN TP, SIN escalera\n"
        "• Backtest continuo 4 años: +147% vs B&H +49%, PF 2.0, DD 21%\n"
        "• PERFIL: semanas de stops chicos (−0.33% c/u) + pocas posiciones de\n"
        "  1-6 meses que pagan todo — NO juzgar antes de 3+ meses\n"
        "• Botón TOMAR PROFIT activo siempre | /estado = lo EN CURSO |\n"
        "  /history = operaciones cerradas de hoy\n"
        "⚠️ Paper-trading: el forward test ES la validación, no usar capital real")

    # --- heartbeat ---
    while True:
        time.sleep(300)
        with gestor.lock:
            abiertas = len(gestor.abiertas())
            bal = gestor.balance['usd']
        log(f"HEARTBEAT: WS={'OK' if estado_ws['ok'] else 'DOWN'} | abiertas={abiertas} | balance=${bal:.2f}")


if __name__ == '__main__':
    main()
