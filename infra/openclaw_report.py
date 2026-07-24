#!/usr/bin/env python3
"""
openclaw_report.py — Canal de reporte de Telegram entre Claude y el operador,
separado de las alertas de trade de V26/V28 (que ya tienen sus propios bots).

Reusa el bot OPENCLAW_TELEGRAM_TOKEN ya configurado en .env (mismo chat
autorizado, OPENCLAW_TELEGRAM_ALLOWED_USERS) — pensado para reportes de
desarrollo/estrategia/progreso, no para señales de entrada/salida de trades.

Uso:
    python3 openclaw_report.py "texto del mensaje"
    python3 openclaw_report.py --file /tmp/mensaje.txt
"""
import os
import sys

import requests
from dotenv import load_dotenv

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BASE, '.env'))

TOKEN = os.getenv('OPENCLAW_TELEGRAM_TOKEN', '')
ENABLED = os.getenv('OPENCLAW_TELEGRAM_ENABLED', 'false').lower() == 'true'
CHAT_ID = os.getenv('OPENCLAW_TELEGRAM_ALLOWED_USERS', '').split(',')[0].strip() or '1214526208'
# Fallback (2026-06-20): OPENCLAW_TELEGRAM_TOKEN devolvió 401 Unauthorized el
# día que se armó este canal — algo lo invalidó. Mientras el usuario lo
# revisa en @BotFather, este script cae al bot de V26 (ya operativo) para
# que el canal no quede mudo. Quitar el fallback cuando OPENCLAW_TELEGRAM_TOKEN
# vuelva a funcionar de nuevo (este script ya reintenta el token dedicado
# primero en cada envío, así que se auto-corrige solo apenas el usuario lo arregle).
FALLBACK_TOKEN = os.getenv('TELEGRAM_TOKEN_V26', '')


def _intentar_envio(token: str, texto: str) -> tuple:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    try:
        r = requests.post(url, json={'chat_id': CHAT_ID, 'text': texto}, timeout=15)
        data = r.json()
        return data.get('ok', False), data
    except Exception as e:
        return False, {'error': str(e)}


def send(texto: str) -> bool:
    if not ENABLED:
        print('[OPENCLAW_REPORT] OPENCLAW_TELEGRAM_ENABLED=false, no se envía.', file=sys.stderr)
        return False
    if not CHAT_ID:
        print('[OPENCLAW_REPORT] Falta OPENCLAW_TELEGRAM_ALLOWED_USERS en .env.', file=sys.stderr)
        return False
    if TOKEN:
        ok, data = _intentar_envio(TOKEN, texto)
        if ok:
            return True
        print(f'[OPENCLAW_REPORT] OPENCLAW_TELEGRAM_TOKEN falló ({data}), probando fallback V26...', file=sys.stderr)
    if FALLBACK_TOKEN:
        ok, data = _intentar_envio(FALLBACK_TOKEN, f'[CLAUDE — vía bot V26, canal dedicado caído]\n\n{texto}')
        if ok:
            return True
        print(f'[OPENCLAW_REPORT] ERROR también en fallback: {data}', file=sys.stderr)
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Uso: python3 openclaw_report.py "mensaje"  |  --file <ruta>', file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == '--file':
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            msg = f.read()
    else:
        msg = ' '.join(sys.argv[1:])
    ok = send(msg)
    sys.exit(0 if ok else 2)
