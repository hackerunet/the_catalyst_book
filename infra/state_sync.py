#!/usr/bin/env python3
"""Sincroniza trades_*.json y forense/ de los 3 bots con un bucket GCS.

Objetivo: que un redeploy (que destruye la VM y reconstruye el contenedor desde
el código local) no borre el estado/evidencia acumulada en la nube. restore()
se corre ANTES de lanzar los bots (recupera lo último respaldado); backup-loop
corre en paralelo a los bots y sube el estado cada INTERVALO segundos.

Best-effort: cualquier fallo (bucket sin permisos, sin red, primera corrida sin
backup previo) se loguea y se ignora — nunca debe bloquear el arranque de los bots.
"""
import os
import sys
import time
import traceback

BUCKET = os.environ.get('BOTS_STATE_BUCKET')
BASE = '/app/bot_alpha_portfolio'

# (carpeta del bot, nombre del archivo de trades)
# V28 se mantiene en la lista aunque el bot esté retirado (2026-07-01): su
# evidencia forense en GCS se sigue restaurando/preservando, y si se reactiva
# como "asistente del humano" retoma su estado sin cambios aquí.
BOTS = [
    ('stable_v25_prototype', 'trades_v25.json'),
    ('v26_tendencia', 'trades_v26.json'),
    ('v28_copilot', 'trades_v28.json'),
    ('v36_15m', 'trades_v36.json'),
    ('sinapsis_lateral', 'trades_sinapsis.json'),
    ('v72_espejismo', 'trades_v72.json'),
]

# STATE_SYNC_ONLY (aislamiento, 2026-07-11): si se define (carpetas coma-separadas),
# el sync se limita a esos bots. La VM de Sinapsis corre en instancia/bucket propios
# y sólo debe tocar su estado — NO restaurar/respaldar las trades reales de mainnet
# (v26/v36) que también viven como copias en su imagen. Sin la var, comportamiento
# histórico (todos los bots) — la VM de mainnet no cambia.
_solo = os.environ.get('STATE_SYNC_ONLY', '').strip()
if _solo:
    _permitidas = {s.strip() for s in _solo.split(',') if s.strip()}
    BOTS = [b for b in BOTS if b[0] in _permitidas]


def _bucket():
    from google.cloud import storage
    return storage.Client().bucket(BUCKET)


def restore():
    if not BUCKET:
        print('[STATE_SYNC] BOTS_STATE_BUCKET no configurado, sin restore.', flush=True)
        return
    try:
        bucket = _bucket()
        for carpeta, trades_file in BOTS:
            local_dir = os.path.join(BASE, carpeta)
            blob = bucket.blob(f'{carpeta}/{trades_file}')
            if blob.exists():
                blob.download_to_filename(os.path.join(local_dir, trades_file))
                print(f'[STATE_SYNC] restaurado {carpeta}/{trades_file}', flush=True)

            prefix = f'{carpeta}/forense/'
            forense_dir = os.path.join(local_dir, 'forense')
            os.makedirs(forense_dir, exist_ok=True)
            n = 0
            for blob in bucket.list_blobs(prefix=prefix):
                rel = blob.name[len(prefix):]
                if not rel:
                    continue
                dest = os.path.join(forense_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                blob.download_to_filename(dest)
                n += 1
            if n:
                print(f'[STATE_SYNC] restaurados {n} archivos forenses de {carpeta}', flush=True)
    except Exception:
        print('[STATE_SYNC] ERROR en restore (los bots arrancan igual, sin estado previo):', flush=True)
        traceback.print_exc()


def backup_once():
    if not BUCKET:
        return
    try:
        bucket = _bucket()
        for carpeta, trades_file in BOTS:
            local_dir = os.path.join(BASE, carpeta)
            local_trades = os.path.join(local_dir, trades_file)
            if os.path.isfile(local_trades):
                bucket.blob(f'{carpeta}/{trades_file}').upload_from_filename(local_trades)

            forense_dir = os.path.join(local_dir, 'forense')
            if os.path.isdir(forense_dir):
                for root, _, files in os.walk(forense_dir):
                    for fn in files:
                        local_path = os.path.join(root, fn)
                        rel = os.path.relpath(local_path, forense_dir)
                        bucket.blob(f'{carpeta}/forense/{rel}').upload_from_filename(local_path)
    except Exception:
        print('[STATE_SYNC] ERROR en backup (se reintenta en el próximo ciclo):', flush=True)
        traceback.print_exc()


def backup_loop(interval=60):
    print(f'[STATE_SYNC] backup-loop activo cada {interval}s hacia gs://{BUCKET}', flush=True)
    while True:
        time.sleep(interval)
        backup_once()


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'restore'
    if cmd == 'restore':
        restore()
    elif cmd == 'backup-loop':
        backup_loop()
    elif cmd == 'backup-once':
        backup_once()
    else:
        print(f'[STATE_SYNC] comando desconocido: {cmd}', flush=True)
