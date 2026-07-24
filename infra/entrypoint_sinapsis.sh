#!/bin/bash
set -e

echo "[INFO] Iniciando LA CARRERA DEL WIN RATE en instancia DEDICADA (TESTNET/paper)."
echo "[INFO]   SINAPSIS  (4h, patrones, salida-lateral) : SOL BNB XRP ADA LINK  -> WR ~36%, +80% en 4a"
echo "[INFO]   V72       (4h, cruce,    TP/SL dial 3.0) : DOGE AVAX DOT LTC ATOM -> WR ~76%, +2.6% en 4a"
echo "[INFO] Comparten cuenta demo (Binance demo no tiene subcuentas) pero CERO simbolos en comun = cero neteo."
echo "[INFO] Aislado de V26/V36 (mainnet): otra VM, otra cuenta Binance (demo-fapi), otro bucket."

# Aislamiento de ESTADO: esta VM sólo restaura/respalda las trades de Sinapsis.
# NO toca las trades reales de mainnet (v26/v36) que también viven como copias
# en esta imagen — evita mezclar/pisar estado entre entornos.
export STATE_SYNC_ONLY=sinapsis_lateral,v72_espejismo

echo "[INFO] Restaurando estado previo de Sinapsis desde GCS (si existe)..."
python3 -u /app/state_sync.py restore

touch /app/bot_alpha_portfolio/sinapsis_lateral/sinapsis.out
touch /app/bot_alpha_portfolio/v72_espejismo/v72.out

echo "[INFO] Lanzando SINAPSIS-LATERAL (4h · patrones · salida-lateral · testnet)..."
cd /app/bot_alpha_portfolio/sinapsis_lateral
python3 -u sinapsis_lateral.py > sinapsis.out 2>&1 &
PID_SIN=$!
echo "[INFO] Sinapsis lanzado. PID=$PID_SIN"

echo "[INFO] Lanzando V72_ESPEJISMO (4h · cruce · TP/SL dial 3.0 · testnet)..."
cd /app/bot_alpha_portfolio/v72_espejismo
python3 -u v72_espejismo.py > v72.out 2>&1 &
PID_V72=$!
echo "[INFO] V72 lanzado. PID=$PID_V72"

# Respaldo periódico de trades_sinapsis.json + forense/ a GCS (best-effort), para
# que un redeploy o una caída de VM no pierda la evidencia del forward test.
python3 -u /app/state_sync.py backup-loop &
PID_SYNC=$!
echo "[INFO] Backup periódico a GCS activo. PID=$PID_SYNC"

# Reflejar el log del bot en stdout (docker logs / Cloud Logging)
tail -f /app/bot_alpha_portfolio/sinapsis_lateral/sinapsis.out /app/bot_alpha_portfolio/v72_espejismo/v72.out &

# Mantener el contenedor vivo atado a los dos bots de la carrera
wait $PID_SIN $PID_V72
