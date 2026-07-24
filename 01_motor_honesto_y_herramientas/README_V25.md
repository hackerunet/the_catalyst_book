# STABLE_V25_PROTOTYPE — Momentum diario + ejecución 1h + control por Telegram

Bot independiente (un solo proceso, sin watchdog ni dashboard) que cumple la
especificación del usuario del 2026-06-10. Paper trading en Binance Futures
**testnet** (`demo-fapi.binance.com`).

## Arquitectura modular (refactor 2026-06-11 — sin monolito)

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Credenciales (.env) + parámetros. Único lector de entorno. |
| `binance_client.py` | Autorización y TODA la comunicación con Binance: REST firmado (testnet), klines públicos, stream WebSocket. |
| `indicadores.py` | Indicadores técnicos puros (EMA/ATR/ADX/RSI/MACD + diario). |
| `patrones.py` | Biblioteca de 18 patrones de vela (módulo puro). |
| `estrategia.py` | Decisiones de entrada/salida **PURAS** — el bot en vivo y el backtest llaman exactamente las mismas funciones (lección V24: un solo code path). |
| `ejecutor.py` | Ejecutor en vivo: `GestorTrades` + `SymbolEngine` por símbolo. |
| `telegram_bot.py` | Envío + polling de Telegram con callbacks inyectados. |
| `forense.py` | Registro forense por operación (ver abajo). |
| `backtest.py` | Backtest honesto sobre la misma estrategia (ver abajo). |
| `stable_v25_prototype.py` | Solo cablea módulos y levanta hilos. Mismo comando de lanzamiento. |

## Forense por operación

Cada trade (vivo → `forense/`, backtest → `forense_backtest/<run>/`) genera un
JSON `<trade_id>.json` con: **activación** (tendencia, patrón disparador,
TODOS los patrones presentes, indicadores completos, prob. de reversión,
parámetros entrada/tp/sl/qty y las últimas 30 velas OHLCV que produjeron la
señal), **seguimiento** (una entrada por vela mientras vive: OHLCV + progreso
+ decil asegurado + prob. reversión) y **cierre** (precio, motivo, PnL, avance
máximo, duración). Con esto se evalúa a posteriori si la estrategia funciona,
dónde falla y qué mejorar.

## Backtest honesto (`backtest.py`)

Motor heredado de V24-FABLE: **reloj global** (símbolos entrelazados por
timestamp), **orden intravela pesimista** (extremo adverso primero, ratchets
al cierre de vela), **costos completos** (comisión 0.05% + slippage 0.05% por
lado + funding 0.01%/8h) y **benchmark buy&hold** de la misma ventana. Corre
la MISMA `estrategia.py` que el bot en vivo y emite forense por trade +
resumen por símbolo / por patrón disparador / por motivo de salida.

```
python3 backtest.py                    # 1500 velas (~62 días)
python3 backtest.py --candles 3000     # ~125 días
python3 backtest.py --end 2026-06-09   # ventana congelada reproducible
```
No necesita API keys (datos públicos); no envía Telegram ni órdenes.

## Cómo opera

1. **6 mercados** (ETH/SOL/BNB/XRP/ADA/LINK), cada uno con un `SymbolEngine`
   independiente — sin tope de exposición cruzado ni interferencia entre
   motores. Una posición máx. por símbolo, riesgo 1% del balance c/u, 5x.
2. **Tendencia**: momentum DIARIO (cierre 1D vs EMA20 diaria) + régimen 1h
   (precio vs EMA50 vs EMA200) + fuerza ADX≥20. **Solo se abstiene en mercado
   LATERAL** (ADX<20 / medias sin orden) o con DOJI (incertidumbre).
3. **Entrada**: tendencia detectada → espera **1 vela-patrón de confirmación**
   de una biblioteca de 18 patrones (engulfing alcista/bajista, marubozu,
   hammer, shooting star, hanging man, inverted hammer, piercing line, dark
   cloud cover, morning/evening star, three white soldiers/black crows,
   harami, tweezer top/bottom, doji) + confirmación de volumen para patrones
   de continuación + guardas RSI (no perseguir agotamiento).
4. **Objetivo**: 1× ATR diario (el movimiento típico de un día), acotado a
   [1.5%, 8%] del precio. **Stop**: mitad del objetivo (riesgo:beneficio 1:2).
5. **Escalera de profit**: cada 10% de avance hacia el objetivo se "asegura"
   (decil) y se notifica; si el avance **retrocede 8 puntos** desde el último
   decil asegurado → cierre inmediato tomando la ganancia. Al 100% → cierre.
6. **Telegram** (solo chat 1214526208): cada posición y cada decil envía
   mensaje con botones **[💰 TOMAR PROFIT]** / **[▶️ CONTINUAR]** referenciados
   por `trade_id` — el botón de profit funciona EN CUALQUIER MOMENTO. El
   mensaje incluye: entrada, tipo, objetivo, stop, avance %, decil asegurado,
   **probabilidad de reversión** (RSI extremo + MACD perdiendo fuerza + patrón
   opuesto + sobre-extensión vs EMA200) y patrón de confirmación.
   `/estado` → uptime, WS, balance, tendencia por símbolo, posiciones abiertas
   y resumen de HOY (horas de cada operación + PnL).
7. **Latencia**: datos por WebSocket multiplexado (sin polling de precios),
   salidas evaluadas **a nivel de tick**; hilos dedicados (WS / Telegram /
   balance). REST firmado solo para órdenes y cuenta (Binance no acepta
   órdenes futures por el stream público).

## Operación

```
cd bot_alpha_portfolio/stable_v25_prototype && \
nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u stable_v25_prototype.py > v25.out 2>&1 & disown
```

- Historial de operaciones persistido en `trades_v25.json` (sobrevive restarts,
  alimenta `/estado`).
- Credenciales: `.env` → `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` (igual que
  los bots previos).
- **⚠️ Token de Telegram compartido** con las mesas V21/V22 por defecto: si
  otra mesa está corriendo, los `getUpdates` compiten y se roban mensajes.
  Define `TELEGRAM_TOKEN_V25` en `.env` (bot nuevo de @BotFather) para aislarlo
  — el código lo toma automáticamente.

## Advertencia de honestidad

El veredicto del motor honesto (2026-06-10) mostró que ninguna estrategia del
proyecto tiene edge demostrado; la base de V25 (cruce EMA50/200 + ADX + acción
del precio) es la estrategia trend-following más publicada, pero **no está
validada por nuestro propio walk-forward**. V25 es un prototipo forward de
paper-trading: su valor es medir en vivo-adelante, no una promesa de
rentabilidad. **No usar capital real.**
