#!/bin/bash

# Habilitar detención automática ante errores reales
set -e
set -o pipefail

# Función para manejar errores de forma limpia
error_handler() {
    echo ""
    echo "❌ ERROR FATAL: El comando falló en la línea $1."
    echo "El despliegue ha sido abortado. Por favor, revisa el error arriba."
    exit 1
}
# Configurar la trampa de errores
trap 'error_handler $LINENO' ERR

PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: No hay un proyecto de GCP configurado. Ejecuta: gcloud config set project TU_PROYECTO"
    exit 1
fi

# REGION = ubicación del Artifact Registry (la imagen ya vive aquí; el pull cross-región funciona).
REGION="us-central1"
# VM_ZONE = zona donde corre la VM. DEBE estar FUERA de EE.UU.: Binance geo-bloquea las IPs
# estadounidenses con HTTP 451 y los bots arrancan ciegos (bootstrap falla, 0 trades).
# São Paulo (southamerica-east1) está permitida por Binance y verificada operando sin 451.
# NO volver a us-central1 (ver ops_gcp_binance_geoblock.md / el libro).
VM_ZONE="southamerica-east1-a"
# IP externa ESTÁTICA reservada (región = VM_ZONE sin el sufijo de zona). La VM se
# borra y recrea en cada deploy; sin esta reserva, la IP efímera cambiaría en cada
# despliegue y ROMPERÍA el whitelist de la API key de mainnet (Binance rechazaría al
# bot en silencio). Reservada como 'openclaw-bots-ip' = <IP_ESTATICA_DE_TU_VM>. NO cambiar sin
# actualizar también la restricción de IP de la API key en Binance.
STATIC_IP_NAME="openclaw-bots-ip"
REPO_NAME="bots-repo"
IMAGE_NAME="openclaw-bots"
FULL_IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"
VM_NAME="openclaw-bots-vm"
# Bucket de respaldo de estado (trades_*.json + forense/) — sobrevive a la
# destrucción/recreación de la VM en cada despliegue. Ver state_sync.py.
STATE_BUCKET="${PROJECT_ID}-bots-state"

echo "=========================================================================="
echo "   CONSTRUCCIÓN LOCAL Y DESPLIEGUE A GOOGLE CLOUD (Imagen Privada)      "
echo "=========================================================================="

echo ">> [1/6] Validando si la instancia ya existe..."
# Al meter el comando dentro de un 'if', evitamos que bash dispare la trampa de error (ERR trap)
if gcloud compute instances describe $VM_NAME --zone=${VM_ZONE} >/dev/null 2>&1; then
    echo "⚠️  ADVERTENCIA: La máquina virtual '$VM_NAME' ya existe en GCP."
    echo "Eliminando la máquina anterior para evitar conflictos de despliegue..."
    gcloud compute instances delete $VM_NAME --zone=${VM_ZONE} --quiet
    echo "✅ Máquina anterior eliminada."
fi

echo ">> [1.5/6] Verificando bucket de respaldo de estado (GCS)..."
if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" >/dev/null 2>&1; then
    echo "Creando bucket privado gs://${STATE_BUCKET} en ${VM_ZONE%-*}..."
    gcloud storage buckets create "gs://${STATE_BUCKET}" \
        --location="${VM_ZONE%-*}" \
        --uniform-bucket-level-access
else
    echo "El bucket gs://${STATE_BUCKET} ya existe (la evidencia previa se conserva)."
fi

echo ">> [2/6] Verificando Artifact Registry privado..."
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION >/dev/null 2>&1; then
    echo "Creando Artifact Registry privado en tu cuenta..."
    gcloud artifacts repositories create $REPO_NAME \
        --repository-format=docker \
        --location=$REGION \
        --description="Repositorio privado para bots de trading"
else
    echo "El repositorio '$REPO_NAME' ya existe."
fi

echo ">> [3/6] Autenticando Docker local con Google Cloud..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

echo ">> [4/6] Construyendo la imagen Docker localmente (Linux/AMD64 para GCP)..."
docker build --platform linux/amd64 -f Dockerfile.cloud -t $FULL_IMAGE_PATH .

echo ">> [5/6] Subiendo imagen al Registro Privado de Google Cloud..."
docker push $FULL_IMAGE_PATH

echo "=========================================================================="
echo "   DESPLIEGUE DIRECTO A COMPUTE ENGINE                                  "
echo "=========================================================================="

echo ">> [6/6] Creando VM asegurada e inyectando el contenedor privado..."
gcloud compute instances create-with-container $VM_NAME \
    --machine-type=e2-micro \
    --zone=${VM_ZONE} \
    --address=${STATIC_IP_NAME} \
    --container-image=$FULL_IMAGE_PATH \
    --container-restart-policy=always \
    --container-env=BOTS_STATE_BUCKET=${STATE_BUCKET} \
    --scopes=https://www.googleapis.com/auth/devstorage.read_write,https://www.googleapis.com/auth/logging.write \
    --tags=bots-secure \
    --metadata=enable-oslogin=TRUE,google-logging-enabled=TRUE

echo "=========================================================================="
echo "   CONFIGURACIÓN DEL FIREWALL Y SEGURIDAD                               "
echo "=========================================================================="
echo "Ajustando el firewall para permitir solo IAP..."
# Usamos || true para ignorar el error si la regla no existe o ya existe
gcloud compute firewall-rules delete default-allow-icmp --quiet >/dev/null 2>&1 || true
gcloud compute firewall-rules delete default-allow-ssh --quiet >/dev/null 2>&1 || true

gcloud compute firewall-rules create allow-ssh-from-iap \
    --network=default \
    --action=allow \
    --direction=ingress \
    --rules=tcp:22 \
    --source-ranges=35.235.240.0/20 \
    --target-tags=bots-secure >/dev/null 2>&1 || true

echo ""
echo "=========================================================================="
echo "   ¡DESPLIEGUE COMPLETADO CON ÉXITO!                                      "
echo "=========================================================================="
echo "Para conectarte y ver los logs del contenedor:"
echo "1. Conéctate a la máquina vía IAP:"
echo "   gcloud compute ssh $VM_NAME --tunnel-through-iap --zone=${VM_ZONE}"
echo "2. Ya dentro de la VM, lista el contenedor nativo:"
echo "   docker ps"
echo "3. Mira los logs de tus bots:"
echo "   docker logs <ID_DEL_CONTENEDOR>"
