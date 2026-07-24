# V26_TENDENCIA — bot de seguimiento de tendencia 4h (forward test)

Clon de `stable_v25_prototype/` con la config validada por los **tests C/D del
2026-06-11** (sesión modelo invitado — detalle completo en el libro,
secciones "TEST C" / "TEST D" / "CIERRE DE SESIÓN MODELO INVITADO").

## Estrategia (todo en config.py, código compartido con V25)
- **Timeframe**: 4h (`INTERVAL='4h'`), 6 símbolos, motores independientes.
- **Entrada** (`ENTRY_MODE='cruce'`): SOLO en la vela donde la alineación
  completa (precio>EMA50>EMA200 + ADX≥20 + momentum diario EMA20-1D) SE VUELVE
  verdadera — el flip. Sin patrones, sin filtros extra (squeeze, fuerza
  relativa y Donchian fueron testeados y RECHAZADOS — entran tarde/peor).
- **Salida** (`EXIT_MODE='tendencia'`): stop de protección estático (tick a
  tick) o **flip de alineación opuesta** (al cierre de cada vela 4h). SIN take
  profit, SIN escalera de deciles — la rentabilidad vive en la cola derecha.
  El botón 💰 TOMAR PROFIT manual de Telegram sigue activo en todo momento.
- **Riesgo**: 0.33% por trade (tope global 2% = 6 × 0.33%), 5x, testnet.

## Por qué existe (evidencia)
Corrida continua 4 años (motor honesto, costos maker 0.02%/lado):
**+147.36% vs buy&hold +49.42% | PF 2.03 | DD 20.9% | percentil 100 vs null
aleatorio | 6/6 símbolos positivos**. Primer resultado honesto positivo del
proyecto. Cautelas: fills maker optimistas (stops son market), ~8º config
sobre los mismos datos → **este forward test ES la validación**.

## Perfil esperado (calibrar expectativas ANTES de mirar el PnL)
- WR ~18%: semanas/meses de stops chicos (−0.33% c/u) entre ganadores.
- Los ganadores son posiciones de **1-6 meses** (en el backtest, top-5 trades
  = 76% del PnL de 4 años). 2022-23 fue ~2 años de sangrado antes de pagar.
- **NO juzgar antes de 3+ meses o ≥1 tendencia completa cobrada.** Cadencia
  ~8-9 trades/mes entre los 6 símbolos.

## Lanzar
1. Crear bot en @BotFather y añadir a `.env`: `TELEGRAM_TOKEN_V26=<token>`
   (OBLIGATORIO — sin él el proceso se niega a arrancar; V25 usa otro token).
2. ```
   cd bot_alpha_portfolio/v26_tendencia && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u v26_tendencia.py > v26.out 2>&1 & disown
   ```
3. Verificar en `v26.out`: `precisión cargada`, 6× bootstrap, `WS conectado: 6
   streams kline_4h`, mensaje OPERATIVO en Telegram, HEARTBEAT cada 5 min.
4. Apagar: `kill -TERM <pid>` (confirmar cwd con `lsof -p <pid> | grep cwd`).

## Evaluación
- Comparar fills/decisiones contra `backtest.py --candles N --end <fecha>`
  sobre la misma ventana (mismo code path de decisión).
- Forense por trade en `forense/`; persistencia en `trades_v26.json`.
- Fase 2 (pendiente): entradas post-only limit (supuesto maker del backtest).
