#!/usr/bin/env python3
"""
claude_bridge.py — canal de DOBLE VÍA por Telegram entre el usuario y Claude.

NO es un agente con herramientas: no puede correr backtests, editar código ni
ejecutar comandos. Es un asistente de preguntas y respuestas sobre el estado
del proyecto, con contexto fresco (trades reales de V26/V28 desde GCS) en
cada respuesta, vía la API de Anthropic directa. Para pedir cambios reales
(nuevo backtest, fix de código, etc.) el usuario tiene que volver a una
sesión de Claude Code normal — este bridge lo dice explícitamente si se lo
piden.

Reusa el patrón de polling de bot_alpha_portfolio/v26_tendencia/telegram_bot.py.
Token: intenta OPENCLAW_TELEGRAM_TOKEN primero (canal dedicado); si falla el
getMe, cae a TELEGRAM_TOKEN_V26 — y reintenta el dedicado cada CHEQUEO_TOKEN
iteraciones para auto-promoverse apenas el usuario lo arregle en @BotFather.
"""
import os
import time
import traceback

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from google.cloud import storage

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BASE, '.env'))

TOKEN_DEDICADO = os.getenv('OPENCLAW_TELEGRAM_TOKEN', '')
TOKEN_FALLBACK = os.getenv('TELEGRAM_TOKEN_V26', '')
CHAT_ID = os.getenv('OPENCLAW_TELEGRAM_ALLOWED_USERS', '1214526208').split(',')[0].strip()
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
BUCKET_NAME = os.getenv('BOTS_STATE_BUCKET', '')
MODEL = 'claude-sonnet-4-6'
CHEQUEO_TOKEN_CADA = 20  # cada N vueltas del loop, re-probar el token dedicado

client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

CONTEXTO_FIJO = """Sos el asistente de desarrollo del proyecto de trading algorítmico \
"openclaw-binance-trading" (Binance Futures TESTNET, paper trading, sin capital real).

Objetivo del usuario: que los bots sean rentables, en un rango de 30-45% anual o mejor.

Flota viva (todo en GCP, VM openclaw-bots-vm, São Paulo):
- V26_TENDENCIA: el ÚNICO bot con edge validado por walk-forward (4 años de backtest: \
+147% vs buy&hold +49%, profit factor 2.03). Entradas en 4h por cruce de tendencia \
(EMA50/200 + ADX + momentum diario), salidas por flip opuesto o stop — SIN take-profit \
fijo, así que una operación puede tardar semanas o meses en cerrar. Cadencia esperada: \
~8-9 operaciones por mes entre 6 símbolos (ETH/SOL/BNB/XRP/ADA/LINK). Lanzado 2026-06-11. \
El propio historial del proyecto espera 1-2 años de resultado plano/negativo antes de que \
el trend-following empiece a pagar realmente — no hay que sacar conclusiones de pocos días.
- V28_COPILOT: asistente de trading 1h, NO autónomo (el trader decide la salida). Su \
métrica de éxito es la calidad de reconocimiento de patrones, NO el PnL — no lo evalúes \
por rentabilidad.
- V25: fue DECOMISIONADO el 2026-06-20 (su estrategia nunca tuvo edge real y duplicaba \
señales con V28 en la misma cuenta de testnet, contaminando las métricas). Ya no corre.

Reglas de cómo responder:
- Español, corto, directo, sin vender humo. Este proyecto tiene una cultura fuerte de no \
inflar resultados ni declarar éxito prematuro — si la muestra es chica, decilo.
- NO podés ejecutar acciones (no hay herramientas conectadas a vos): no podés correr \
backtests, tocar código, ni hacer SSH. Si te piden algo así, decí que hay que pedirlo en \
una sesión de Claude Code normal (la terminal/app de escritorio), no acá.
- Si te preguntan por números concretos de trades/PnL, usá los datos reales que se \
incluyen abajo en "DATOS ACTUALES" — no inventes cifras."""


def _gcs_cat(blob_path):
    try:
        if not BUCKET_NAME:
            return None
        bucket = storage.Client().bucket(BUCKET_NAME)
        blob = bucket.blob(blob_path)
        if blob.exists():
            return blob.download_as_text()
    except Exception:
        pass
    return None


def cargar_datos_actuales():
    partes = []
    for carpeta, archivo, nombre in [
        ('v26_tendencia', 'trades_v26.json', 'V26'),
        ('v28_copilot', 'trades_v28.json', 'V28'),
    ]:
        contenido = _gcs_cat(f'{carpeta}/{archivo}')
        if contenido:
            partes.append(f"--- {nombre} ({archivo}) ---\n{contenido[:6000]}")
        else:
            partes.append(f"--- {nombre}: no se pudo leer {archivo} de GCS ---")
    return '\n\n'.join(partes)


def responder(pregunta):
    if not client:
        return "ANTHROPIC_API_KEY no configurada — no puedo responder ahora."
    datos = cargar_datos_actuales()
    system = f"{CONTEXTO_FIJO}\n\nDATOS ACTUALES (trades reales desde GCS):\n{datos}"
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=system,
            messages=[{'role': 'user', 'content': pregunta}],
        )
        return msg.content[0].text if msg.content else "(respuesta vacía)"
    except Exception as e:
        return f"Error llamando a la API de Anthropic: {e}"


def _token_valido(token):
    if not token:
        return False
    try:
        r = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
        return r.json().get('ok', False)
    except Exception:
        return False


def elegir_token():
    if _token_valido(TOKEN_DEDICADO):
        return TOKEN_DEDICADO, False
    return TOKEN_FALLBACK, True


def polling():
    print('[CLAUDE_BRIDGE] iniciando...', flush=True)
    token, usando_fallback = elegir_token()
    if not token:
        print('[CLAUDE_BRIDGE] ERROR: ningún token válido (ni dedicado ni fallback). Saliendo.', flush=True)
        return
    print(f"[CLAUDE_BRIDGE] activo {'(via fallback V26)' if usando_fallback else '(token dedicado)'}", flush=True)
    last_update = 0
    vueltas = 0
    while True:
        vueltas += 1
        if vueltas % CHEQUEO_TOKEN_CADA == 0:
            nuevo_token, nuevo_fallback = elegir_token()
            if nuevo_token != token:
                token = nuevo_token
                usando_fallback = nuevo_fallback
                print(f"[CLAUDE_BRIDGE] cambio de token {'(via fallback V26)' if usando_fallback else '(dedicado recuperado)'}", flush=True)
        base = f'https://api.telegram.org/bot{token}'
        try:
            res = requests.get(f'{base}/getUpdates',
                               params={'offset': last_update + 1, 'timeout': 30}, timeout=40)
            data = res.json()
            if not data.get('ok'):
                time.sleep(3)
                continue
            for upd in data['result']:
                last_update = upd['update_id']
                msg = upd.get('message', {})
                chat_id = str(msg.get('chat', {}).get('id', ''))
                texto = msg.get('text', '')
                if chat_id != CHAT_ID or not texto:
                    continue
                print(f"[CLAUDE_BRIDGE] pregunta: {texto[:80]}", flush=True)
                try:
                    requests.post(f'{base}/sendChatAction',
                                   json={'chat_id': chat_id, 'action': 'typing'}, timeout=5)
                except Exception:
                    pass
                respuesta = responder(texto)
                prefijo = '[CLAUDE — vía bot V26]\n\n' if usando_fallback else ''
                requests.post(f'{base}/sendMessage',
                               json={'chat_id': chat_id, 'text': f'{prefijo}{respuesta}'}, timeout=15)
        except Exception:
            print('[CLAUDE_BRIDGE] ERROR en el loop:', flush=True)
            traceback.print_exc()
            time.sleep(5)


if __name__ == '__main__':
    polling()
