#!/bin/bash
set -e

echo "[INFO] Iniciando bots en Google Cloud E2..."
echo "[INFO] Memory y ambiente de Claude cargado desde .claude"

# Restaurar trades_*.json y forense/ desde GCS (best-effort) ANTES de lanzar los bots,
# para que un redeploy no arranque con estado vacío si ya había evidencia respaldada.
echo "[INFO] Restaurando estado previo desde GCS (si existe)..."
python3 -u /app/state_sync.py restore

# Crear archivos de log vacíos para que tail no falle si aún no existen
touch /app/bot_alpha_portfolio/v26_tendencia/v26.out
touch /app/bot_alpha_portfolio/v36_15m/v36.out

# Bot V25 — APAGADO 2026-06-20: estrategia declarada muerta por walk-forward
# (1/17 ventanas positivas, PF<1; V29-A la reconfirmó hoy aún peor) y su
# netting compartido de cuenta testnet contaminaba las métricas de V26/V28
# (el usuario cerraba sus posiciones manualmente). Ver el libro. Para
# reactivar: restaurar este bloque + el PID_V25 en el `wait` de abajo.
# echo "[INFO] Lanzando V25 (1h Tendencia)..."
# cd /app/bot_alpha_portfolio/stable_v25_prototype
# python3 -u stable_v25_prototype.py > v25.out 2>&1 &
# PID_V25=$!

# Bot V26 — PAUSADO 2026-07-23 (decisión del operador vía Claude): el edge de V26
# exige aguantar rachas largas de pérdidas chicas (WR 18%; ~2 años planos en el
# backtest) para cobrar el monstruo raro, y el operador NO puede sostener ese
# drawdown ahora (retiro de $50, cuenta ~$467, sin colchón). V26 NO está roto —
# las 4 entradas recientes fueron flips frescos válidos (verificado contra el
# mercado real); es un problema de RUNWAY, no de estrategia. Se pausó con la
# cuenta en 0 posiciones (XRP short cerrado con /cerrartodo, ~-$0.30) para frenar
# el sangrado y preservar los ~$467. Para reactivar (cuando haya capital que se
# pueda dejar quieto meses): descomentar este bloque + PID_V26 en el `wait` y el
# `tail`, y arrancar con libro limpio. Ver el libro.
# echo "[INFO] Lanzando V26 (4h Seguimiento)..."
# cd /app/bot_alpha_portfolio/v26_tendencia
# python3 -u v26_tendencia.py > v26.out 2>&1 &
# PID_V26=$!

# Bot V28 — RETIRADO 2026-07-01 (decisión del usuario): sin edge mecánico
# (familia 1h; en vivo −$66/33 ops) y su netting contaminaba a V26/V36 en la
# cuenta compartida. NO borrado — el código queda para retomarlo como
# "asistente del humano" más adelante. Tenía 0 posiciones abiertas al retiro.
# Para reactivar: restaurar este bloque + PID_V28 en el `wait` y el `tail`.
# echo "[INFO] Lanzando V28 (1h Copilot)..."
# cd /app/bot_alpha_portfolio/v28_copilot
# python3 -u v28_copilot.py > v28.out 2>&1 &
# PID_V28=$!

# Bot V36 — 15m patrones + salida de tendencia, basket top-4 por liquidez
# (validado 2026-07-01, ver el libro sección V35; forward test junto a V26
# en la misma cuenta — netting por símbolo aceptado por el usuario).
echo "[INFO] Lanzando V36 (15m Patrones+Tendencia)..."
cd /app/bot_alpha_portfolio/v36_15m
python3 -u v36_15m.py > v36.out 2>&1 &
PID_V36=$!

echo "[INFO] Bots lanzados (V25, V28 y V26 apagados). PID: V36=$PID_V36"

# Respaldo periódico de trades_*.json + forense/ a GCS, en paralelo a los bots,
# para que el próximo redeploy (o una caída de VM) no pierda la evidencia.
python3 -u /app/state_sync.py backup-loop &
PID_SYNC=$!
echo "[INFO] Backup periódico a GCS activo. PID=$PID_SYNC"

# Canal Claude<->Telegram de doble vía (2026-06-20): NO es uno de los bots de
# trading, no toca Binance ni estrategia — solo responde preguntas sobre el
# estado del proyecto vía la API de Anthropic. Ver claude_bridge.py / el libro.
touch /app/claude_bridge.out
echo "[INFO] Lanzando puente Claude<->Telegram..."
cd /app
python3 -u claude_bridge.py > claude_bridge.out 2>&1 &
PID_BRIDGE=$!
echo "[INFO] Puente Claude<->Telegram activo. PID=$PID_BRIDGE"

# Vigilante de salud (2026-07-09): SOLO lee (cuenta/DD-90d/disco/procesos/zombies),
# alerta y manda resumen semanal a Telegram. Se lanza FUERA del `wait` a propósito:
# si el monitor muriera, los bots de trading NO se ven afectados (mínima intrusión).
touch /app/monitor.out
echo "[INFO] Lanzando vigilante de salud (monitor_salud)..."
cd /app
python3 -u monitor_salud.py > monitor.out 2>&1 &
PID_MONITOR=$!
echo "[INFO] Vigilante de salud activo. PID=$PID_MONITOR"

# Redirigir la salida de los logs a la salida estandar de Docker para poder verlos
tail -f /app/bot_alpha_portfolio/v36_15m/v36.out \
        /app/claude_bridge.out \
        /app/monitor.out &

# Esperar a que los procesos principales terminen (V26 pausado 2026-07-23)
wait $PID_V36 $PID_BRIDGE
