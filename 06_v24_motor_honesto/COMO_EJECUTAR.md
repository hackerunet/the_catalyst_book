# Cómo ejecutar — `v24-fable`

El motor honesto (Cap. 10) — la estrategia de V22 sobre un motor reparado.

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
cd bot_alpha_portfolio/v24-fable
python3 mesa_de_dinero.py
```

## Qué esperar
Watchdog: lanza el simulador como subproceso y relaya su salida. Requiere `.env`.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
