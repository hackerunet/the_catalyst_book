# Cómo ejecutar — `v72_espejismo`

V72 "El Espejismo" (Cap. 32) — demuestra que el win rate es un DIAL. TESTNET. WR ~76% con retorno ~0: acertar mucho no es ganar.

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
cd bot_alpha_portfolio/v72_espejismo
python3 v72_espejismo.py
```

## Qué esperar
Arranca el bot: bootstrap de velas, conexión WebSocket a Binance y polling de Telegram. Requiere `.env` con llaves de Binance y un token de Telegram (ver abajo).

---
*Contexto completo de esta estrategia: ver el libro "The Catalyst".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
