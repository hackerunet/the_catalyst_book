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
        payload = {'chat_id': self.chat_id, 'text': f"[V28] {texto}"}
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

    def mensaje_posicion(self, t, prob_rev, titulo, vol_ratio=None, prog_actual=None,
                         resumido=False, tendencia_activa=None):
        """Mensaje del copiloto: niveles en R, BREAKEVEN de costos (para que el
        trader no tome 'profit' que es pérdida neta), volumen y prob de reverso.

        resumido=True (2026-07-01, pedido del usuario — mensajes menos
        ruidosos): usado en los avisos DE SEGUIMIENTO (decil/retroceso/alerta
        de reverso), que se repiten muchas veces por operación. Omite lo que
        NO cambia (entrada/R/stop/objetivo/patrón — ya están en el mensaje de
        apertura y en /estado) y deja solo lo accionable: avance/pico,
        breakeven y reverso, en pocas líneas.

        tendencia_activa (2026-07-01, apoyo a la decisión aguantar/cobrar):
        resultado de estrategia.tendencia_actual(df) en el momento del aviso.
        Responde la pregunta central del post-mortem ("¿la tesis original
        sigue viva?") SIN automatizar nada — es solo display."""
        import estrategia
        import config
        icono = '🟢' if t['type'] == 'LONG' else '🔴'
        be, be_pts = estrategia.breakeven_info(t)

        if getattr(config, 'DETECTOR_CALIBRADO', False):
            etiqueta_rev = f"Reverso {prob_rev}%"
        else:
            etiqueta_rev = f"Reverso(score) {prob_rev}/100"

        etiqueta_tend = None
        if tendencia_activa is not None:
            if tendencia_activa == t['type']:
                etiqueta_tend = "Tendencia ✓ confirma"
            elif tendencia_activa == 'LATERAL':
                etiqueta_tend = "Tendencia ⚠️ perdió fuerza (LATERAL)"
            else:
                etiqueta_tend = f"Tendencia ⚠️ YA GIRÓ a {tendencia_activa}"

        if resumido:
            partes = [f"{icono} {t['symbol']} {t['type']} #{t['id']} — {titulo}"]
            if prog_actual is not None:
                partes.append(f"Avance {prog_actual:.0f}% (pico {t.get('peak_progress', 0):.0f}%)")
                falta_be = be_pts - prog_actual
                partes.append("BE ✅" if falta_be <= 0 else f"BE en {falta_be:.0f}pts")
            partes.append(etiqueta_rev)
            if etiqueta_tend:
                partes.append(etiqueta_tend)
            return " | ".join(partes)

        r_dist = abs(t['entry_price'] - t['sl'])
        lineas = [
            f"{icono} {titulo} — #{t['id']}",
            f"• Símbolo: {t['symbol']} | Tipo: {t['type']}",
            f"• Entrada: ${t['entry_price']:.4f} | R = ${r_dist:.4f}",
            f"• Stop (seguro, −1R): ${t['sl']:.4f}",
            f"• Objetivo máximo (2R, 100%): ${t['tp']:.4f}",
        ]
        if prog_actual is not None:
            falta_be = be_pts - prog_actual
            if falta_be > 0:
                lineas.append(f"• Breakeven: ${be:.4f} — ⚠️ FALTAN {falta_be:.0f} pts "
                              f"(cerrar antes = pérdida neta)")
            else:
                lineas.append(f"• Breakeven: ${be:.4f} — ✅ superado por {-falta_be:.0f} pts "
                              f"(tomar profit ya es ganancia neta)")
            lineas.append(f"• Avance actual: {prog_actual:.0f}% del recorrido a 2R "
                          f"(pico: {t.get('peak_progress', 0):.0f}%)")
        else:
            lineas.append(f"• Breakeven: ${be:.4f} (~{be_pts:.0f}% del recorrido)")
        if vol_ratio is not None:
            etiqueta_v = ('ALTO' if vol_ratio >= 1.5 else
                          'normal' if vol_ratio >= 0.8 else 'BAJO')
            lineas.append(f"• Volumen: {vol_ratio:.1f}x el promedio ({etiqueta_v})")
        # Detector de reverso: el viejo heurístico NO calibraba (P plana por
        # bucket) → se mostraba como SCORE. El calibrado (2026-06-24, validado
        # OOS corr +0.178, monotónico) SÍ es probabilidad real → se rotula así.
        if getattr(config, 'DETECTOR_CALIBRADO', False):
            lineas.append(f"• Prob. de reverso (calibrada, validada): {prob_rev}%")
        else:
            lineas.append(f"• Score de reverso (heurístico, no calibrado): {prob_rev}/100")
        if etiqueta_tend:
            lineas.append(f"• {etiqueta_tend}")
        lineas.append(f"• Patrón: {t.get('pattern', 'N/D')}")
        lineas.append(f"⏱ {_ahora().strftime('%Y-%m-%d %H:%M UTC')} — la salida entre "
                      f"el SL y el 2R es TUYA (botón 💰)")
        return "\n".join(lineas)

    # ---------------- recepción ----------------
    def polling(self, on_take_profit, on_continue, on_estado, on_horario=None,
                on_history=None):
        """
        Long-poll bloqueante (correr en un hilo). Callbacks:
          on_take_profit(trade_id) -> bool (True si cerró)
          on_continue(trade_id)    -> trade dict | None
          on_estado()              -> str  (solo lo EN CURSO)
          on_horario(texto)        -> str (V28: configurar ventana de operación)
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
                        if chat_id:
                            try:
                                requests.post(f"{self._base}/sendMessage",
                                              json={'chat_id': chat_id, 'text': '⛔ Acceso denegado.'},
                                              timeout=5)
                            except Exception:
                                pass
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
                        elif texto.startswith('/estado'):
                            self.enviar(on_estado())
                        elif texto.startswith('/horario') and on_horario:
                            self.enviar(on_horario(texto))
            except Exception:
                time.sleep(5)
