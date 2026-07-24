# Cómo ejecutar — `stable_v25_prototype`

El motor honesto y su harness (Cap. 2-4, 12-13, 18, 26-27). Aquí viven `indicadores.py`, `backtest.py`, `walkforward.py` (reloj global, intravela pesimista, costos, null-vs-azar, OOB) y decenas de estudios `run_*.py` / `diag_*.py`.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```

## Configuración (bots en vivo)
Creá un `.env` en la raíz del repo con:
```
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
BINANCE_ENV=testnet   # NUNCA mainnet para probar
TELEGRAM_TOKEN_...=...   # bot de @BotFather; hacele /start antes
TELEGRAM_CHAT_ID=...
```
> Los bots de este repo están forzados o pensados para **testnet/paper** — nunca uses dinero real para probar.

## Ejecutar
```bash
cd bot_alpha_portfolio/stable_v25_prototype
python3 stable_v25_prototype.py
```

## Qué esperar
Arranca el bot: bootstrap de velas, conexión WebSocket a Binance y polling de Telegram. Requiere `.env` con llaves de Binance y un token de Telegram (ver abajo).

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
