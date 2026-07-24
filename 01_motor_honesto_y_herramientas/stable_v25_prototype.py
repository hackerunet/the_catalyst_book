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
from ejecutor import GestorTrades, SymbolEngine, generar_estado, log
from forense import RegistroForense
from telegram_bot import TelegramBot

START_TIME = datetime.now(timezone.utc)
estado_ws = {'ok': False, 'desde': None}


def main():
    log("STATUS: iniciando STABLE_V25_PROTOTYPE (testnet, paper trading, arquitectura modular)")
    if config.TELEGRAM_TOKEN == config.TELEGRAM_TOKEN_COMPARTIDO:
        log("⚠️ AVISO: usando el MISMO token de Telegram que las mesas V21/V22. "
            "Si otra mesa corre en paralelo, los getUpdates compiten. "
            "Define TELEGRAM_TOKEN_V25 en .env para aislarlo.")

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
        }, daemon=True).start()
    threading.Thread(target=hilo_balance, daemon=True).start()

    telegram.enviar(
        "🚀 STABLE_V25_PROTOTYPE OPERATIVO (testnet, arquitectura modular)\n"
        f"• Mercados: {', '.join(config.SYMBOLS)} — motores independientes\n"
        "• Estrategia: momentum diario (EMA20 1D) + régimen 1h (EMA50/200 + ADX≥20)\n"
        "• Entrada: tendencia + 1 vela-patrón (biblioteca de 18 patrones)\n"
        "• Salidas: asegura cada 10%; cierra si retrocede 8pts de lo asegurado\n"
        "• Forense por operación en forense/ | Backtest honesto: backtest.py\n"
        "• Botones de TOMAR PROFIT activos en todo momento | /estado para resumen\n"
        "⚠️ Prototipo paper-trading — sin edge validado, no usar capital real")

    # --- heartbeat ---
    while True:
        time.sleep(300)
        with gestor.lock:
            abiertas = len(gestor.abiertas())
            bal = gestor.balance['usd']
        log(f"HEARTBEAT: WS={'OK' if estado_ws['ok'] else 'DOWN'} | abiertas={abiertas} | balance=${bal:.2f}")


if __name__ == '__main__':
    main()
