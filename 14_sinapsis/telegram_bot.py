"""
telegram_bot.py — TODA la comunicación por Telegram, desacoplada.

El bot de Telegram no conoce la estrategia ni a Binance: recibe callbacks
(`on_take_profit`, `on_continue`, `on_estado`) inyectados desde el main.
Solo responde al chat autorizado (config.TELEGRAM_CHAT_ID).
"""
import time
from datetime import datetime, timezone

import requests

import config


def _ahora():
    return datetime.now(timezone.utc)


class TelegramBot:
    def __init__(self):
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self._base = f"https://api.telegram.org/bot{self.token}"

    # ---------------- envío ----------------
    def enviar(self, texto, botones_trade_id=None):
        payload = {'chat_id': self.chat_id, 'text': f"[SINAPSIS] {texto}"}
        if botones_trade_id:
            payload['reply_markup'] = {'inline_keyboard': [[
                {'text': '💰 TOMAR PROFIT AHORA', 'callback_data': f'tp|{botones_trade_id}'},
                {'text': '▶️ CONTINUAR', 'callback_data': f'cont|{botones_trade_id}'},
            ]]}
        try:
            res = requests.post(f"{self._base}/sendMessage", json=payload, timeout=5)
            data = res.json()
            if not data.get('ok'):
                # p.ej. 400 "chat not found" = el usuario nunca inició el chat
                # con el bot (falta /start) — antes esto fallaba EN SILENCIO.
                print(f"[TELEGRAM] ERROR envío: {data.get('error_code')} "
                      f"{data.get('description')}", flush=True)
        except Exception as e:
            print(f"[TELEGRAM] WARN envío: {e}", flush=True)

    def mensaje_posicion(self, t, prob_rev, titulo):
        """Formato del mensaje de posición (spec req. 8)."""
        avance = int(t.get('peak_progress', 0) // 10) * 10
        icono = '🟢' if t['type'] == 'LONG' else '🔴'
        return (
            f"{icono} {titulo} — #{t['id']}\n"
            f"• Símbolo: {t['symbol']} | Tipo: {t['type']}\n"
            f"• Entrada: ${t['entry_price']:.4f}\n"
            f"• Objetivo de profit (100%): ${t['tp']:.4f}\n"
            f"• Stop de protección: ${t['sl']:.4f}\n"
            f"• Avance hacia el profit: {max(avance, 0)}%"
            f" (asegurado: {t.get('locked_decile', 0)}%)\n"
            f"• Probabilidad de reversión ahora: {prob_rev}%\n"
            f"• Patrón de confirmación: {t.get('pattern', 'N/D')}\n"
            f"⏱ {_ahora().strftime('%Y-%m-%d %H:%M UTC')}"
        )

    def mensaje_alerta_roundtrip(self, t, prob_rev, prog_actual, tendencia_activa=None):
        """V34-V26 (2026-07-01): aviso de round-trip violento (pico grande ->
        negativo real). Solo informa — no cierra nada, la decisión es del
        usuario (caso BNBUSDT/SOLUSDT/ETHUSDT 24-jun/01-jul: la protección
        MECÁNICA de picos ya se probó y falló en V26, ver V31)."""
        icono = '🟢' if t['type'] == 'LONG' else '🔴'
        etiqueta_tend = None
        if tendencia_activa is not None:
            if tendencia_activa == t['type']:
                etiqueta_tend = "Tendencia ✓ confirma (podría ser un retroceso normal)"
            elif tendencia_activa == 'LATERAL':
                etiqueta_tend = "Tendencia ⚠️ perdió fuerza (LATERAL)"
            else:
                etiqueta_tend = f"Tendencia ⚠️ YA GIRÓ a {tendencia_activa}"
        lineas = [
            f"🚨 {icono} {t['symbol']} {t['type']} #{t['id']} — ROUND-TRIP VIOLENTO",
            f"• Llegó a un pico de {t.get('peak_progress', 0):.0f}% y ahora está en "
            f"{prog_actual:.0f}% (NEGATIVO real, no solo un retroceso menor)",
            f"• Probabilidad de reversión ahora: {prob_rev}%",
        ]
        if etiqueta_tend:
            lineas.append(f"• {etiqueta_tend}")
        lineas.append("Esto es solo información — V26 no cierra nada por esto, la decisión es tuya (botón 💰).")
        return "\n".join(lineas)

    # ---------------- recepción ----------------
    def polling(self, on_take_profit, on_continue, on_estado, on_history=None,
                on_cerrar_todo=None):
        """
        Long-poll bloqueante (correr en un hilo). Callbacks:
          on_take_profit(trade_id) -> bool (True si cerró)
          on_continue(trade_id)    -> trade dict | None
          on_estado()              -> str  (solo lo EN CURSO)
          on_history()             -> str  (operaciones cerradas de hoy)
        """
        last_update = 0
        print("[TELEGRAM] polling iniciado", flush=True)
        while True:
            try:
                res = requests.get(f"{self._base}/getUpdates",
                                   params={'offset': last_update + 1, 'timeout': 30},
                                   timeout=40)
                data = res.json()
                if not data.get('ok'):
                    time.sleep(3)
                    continue
                for upd in data['result']:
                    last_update = upd['update_id']

                    chat_id = None
                    if 'message' in upd:
                        chat_id = str(upd['message']['chat']['id'])
                    elif 'callback_query' in upd:
                        chat_id = str(upd['callback_query']['message']['chat']['id'])
                    if chat_id != self.chat_id:
                        # LOCKDOWN (2026-07-09): ignorar EN SILENCIO a cualquier chat no
                        # autorizado — ni siquiera responder "denegado" (responder ya es
                        # interactuar y confirma que el bot existe). SOLO
                        # config.TELEGRAM_CHAT_ID obtiene cualquier acción o respuesta.
                        continue

                    # --- botones (válidos en CUALQUIER momento de la posición) ---
                    if 'callback_query' in upd:
                        cb = upd['callback_query']
                        accion, _, tid = cb['data'].partition('|')
                        try:
                            requests.post(f"{self._base}/answerCallbackQuery",
                                          json={'callback_query_id': cb['id']}, timeout=5)
                        except Exception:
                            pass
                        if accion == 'tp':
                            if not on_take_profit(tid):
                                self.enviar(f"⚠️ La posición #{tid} ya estaba cerrada.")
                        elif accion == 'cont':
                            t = on_continue(tid)
                            if t:
                                self.enviar(f"⏳ Posición #{tid} ({t['symbol']} {t['type']}) "
                                            f"continúa hacia el objetivo.")
                            else:
                                self.enviar(f"⚠️ La posición #{tid} ya no está abierta.")

                    # --- comandos ---
                    elif 'message' in upd:
                        texto = (upd['message'].get('text') or '').strip().lower()
                        if texto.startswith('/history') and on_history:
                            self.enviar(on_history())
                        elif texto.startswith('/cerrartodo'):
                            if on_cerrar_todo:
                                # /cerrartodo pide confirmación; /cerrartodo si ejecuta
                                ejecutar = texto.replace('/cerrartodo', '').strip() in ('si', 'sí', 'confirmar')
                                self.enviar(on_cerrar_todo(ejecutar))
                        elif texto.startswith('/estado'):
                            self.enviar(on_estado())
            except Exception:
                time.sleep(5)
