#!/bin/bash
# =============================================================================
# deploy_sinapsis.sh — despliega SINAPSIS-LATERAL en una instancia DEDICADA y
# MÍNIMA (e2-micro), AISLADA de V26/V36 (que corren en mainnet en otra VM).
#
#   - VM propia (sinapsis-vm), la más pequeña (e2-micro, ~$6-7/mes).
#   - Imagen propia (openclaw-sinapsis) — sólo lanza sinapsis_lateral.
#   - Bucket de estado propio (…-sinapsis-state) — no mezcla con mainnet.
#   - TESTNET/paper (la config de Sinapsis fuerza demo-fapi; llaves de testnet).
#   - SIN IP estática: testnet no exige whitelist de IP (a diferencia de mainnet).
#
# Prerrequisito: TELEGRAM_TOKEN_SINAPSIS en .env (crear bot nuevo en @BotFather
# y hacerle /start ANTES de desplegar). El repro-test debe estar en verde:
#   cd bot_alpha_portfolio/sinapsis_lateral && python3 repro_sinapsis.py
# =============================================================================
set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"                 # Artifact Registry (pull cross-región OK)
VM_ZONE="southamerica-east1-a"        # São Paulo — FUERA de EE.UU. (geo-bloqueo Binance)
REPO_NAME="bots-repo"
IMAGE_NAME="openclaw-sinapsis"
FULL_IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"
VM_NAME="sinapsis-vm"
STATE_BUCKET="${PROJECT_ID}-sinapsis-state"

echo ">> [1/6] Verificando token de Sinapsis en .env..."
if ! grep -q '^TELEGRAM_TOKEN_SINAPSIS=' .env 2>/dev/null; then
    echo "❌ Falta TELEGRAM_TOKEN_SINAPSIS en .env. Crear bot en @BotFather, hacerle"
    echo "   /start, y añadir la línea TELEGRAM_TOKEN_SINAPSIS=<token> al .env. Abortando."
    exit 1
fi

echo ">> [2/6] Recreando VM dedicada si ya existe..."
if gcloud compute instances describe $VM_NAME --zone=${VM_ZONE} >/dev/null 2>&1; then
    echo "   La VM '$VM_NAME' ya existe — se borra y recrea (el estado se restaura desde GCS)."
    gcloud compute instances delete $VM_NAME --zone=${VM_ZONE} --quiet
fi

echo ">> [3/6] Verificando bucket de estado propio de Sinapsis..."
if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${STATE_BUCKET}" \
        --location="${VM_ZONE%-*}" --uniform-bucket-level-access
else
    echo "   gs://${STATE_BUCKET} ya existe (se conserva la evidencia previa)."
fi

echo ">> [4/6] Verificando Artifact Registry..."
gcloud artifacts repositories describe $REPO_NAME --location=$REGION >/dev/null 2>&1 || \
    gcloud artifacts repositories create $REPO_NAME --repository-format=docker \
        --location=$REGION --description="Imágenes privadas de los bots"
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

echo ">> [5/6] Construyendo y subiendo la imagen dedicada de Sinapsis..."
docker build --platform linux/amd64 -f Dockerfile.sinapsis -t $FULL_IMAGE_PATH .
docker push $FULL_IMAGE_PATH

echo ">> [6/6] Creando la VM mínima (e2-micro) e inyectando el contenedor..."
gcloud compute instances create-with-container $VM_NAME \
    --machine-type=e2-micro \
    --zone=${VM_ZONE} \
    --container-image=$FULL_IMAGE_PATH \
    --container-restart-policy=always \
    --container-env=BOTS_STATE_BUCKET=${STATE_BUCKET},STATE_SYNC_ONLY=sinapsis_lateral \
    --scopes=https://www.googleapis.com/auth/devstorage.read_write,https://www.googleapis.com/auth/logging.write \
    --tags=bots-secure \
    --metadata=enable-oslogin=TRUE,google-logging-enabled=TRUE

echo "=========================================================================="
echo "  SINAPSIS-LATERAL DESPLEGADO (instancia dedicada, testnet/paper)          "
echo "=========================================================================="
echo "  VM: $VM_NAME (e2-micro, ${VM_ZONE})  ·  imagen: $IMAGE_NAME  ·  bucket: $STATE_BUCKET"
echo "  Verificar arranque por Telegram (@tu_bot_sinapsis → OPERATIVO + /estado)."
echo "  Logs:  gcloud compute ssh $VM_NAME --tunnel-through-iap --zone=${VM_ZONE} \\"
echo "           --command='sudo docker logs \$(sudo docker ps -q --filter name=klt-) 2>&1 | tail -50'"
echo "  V26/V36 en mainnet NO se tocan (otra VM, otra cuenta)."
