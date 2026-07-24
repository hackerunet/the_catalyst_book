import subprocess
import os
import time
import sys
import threading
import json

import requests

TELEGRAM_TOKEN = "PONE_TU_TOKEN_DE_TELEGRAM_AQUI"
TELEGRAM_TARGET = "1214526208"

# --- V23: nombres internos actualizados (referencias de log + servicio objetivo) ---
LOG_FILE = 'v23_live.log'
SIMULADOR_TARGET = "simulador_institucional_v23.py"

REGIMEN_LABELS = {
    'TENDENCIA': '📈 Tendencia',
    'TENDENCIA_EMERGENTE': '🚀 Tendencia Emergente (ADX ascendente)',
    'RANGO': '↔️ Rango',
    'BAJA_VOLATILIDAD': '🌙 Baja Volatilidad',
    'INDEFINIDO': '❔ Indefinido',
    'N/D': '❔ N/D',
}

PUERTA_LABELS = {
    'A': 'Alta Convicción (Donchian Breakout)',
    'B': 'Impulso de Vela (Marubozu/Engulfing)',
    'C': 'Reversión a la Media (Bollinger/RSI Fade)',
}

PUERTA_ICONOS = {'A': '🟢', 'B': '🔵', 'C': '🟣'}
PUERTA_RIESGO = {'A': '1%', 'B': '1%', 'C': '0.4%'}


def log_diario(mensaje):
    with open(LOG_FILE, 'a') as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        f.write(f"[{timestamp}] {mensaje}\n")

def send_telegram(mensaje, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_TARGET, "text": f"[V23_MASTER] {mensaje}"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"MESA DE DINERO ERROR: Fallo al despachar Telegram: {e}")

last_update_id = 0

def telegram_polling():
    global last_update_id
    print("MESA DE DINERO V23: Iniciando polling interactivo de Telegram...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': last_update_id + 1, 'timeout': 30}
            res = requests.get(url, params=params, timeout=40)
            data = res.json()
            if data.get('ok'):
                for update in data['result']:
                    last_update_id = update['update_id']

                    chat_id = None
                    if 'message' in update:
                        chat_id = str(update['message']['chat']['id'])
                    elif 'callback_query' in update:
                        chat_id = str(update['callback_query']['message']['chat']['id'])

                    if chat_id != TELEGRAM_TARGET:
                        if chat_id:
                            print(f"⚠️ Intento de acceso no autorizado desde chat_id: {chat_id}")
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⛔ Acceso Denegado. Solo autorizado para ID oficial."})
                        continue

                    if 'callback_query' in update:
                        cb = update['callback_query']
                        cb_data = cb['data']
                        cb_id = cb['id']
                        if cb_data.startswith("close_trade|"):
                            symbol = cb_data.split("|")[1]
                            print(f"MESA DE DINERO V23: Cierre manual solicitado para {symbol} por Telegram.")
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={'callback_query_id': cb_id, 'text': f'Cerrando {symbol}...'})

                            try:
                                # V23 corre su dashboard/API en el puerto 8055 (8053=V21, 8054=V22 en paralelo)
                                r = requests.post("http://127.0.0.1:8055/api/close_trade", json={'symbol': symbol}, timeout=5)
                                if r.status_code == 200 and r.json().get('closed'):
                                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": f"✅ Orden de cierre ejecutada para {symbol}."})
                                else:
                                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": f"⚠️ No se pudo cerrar {symbol}. Puede que ya esté cerrada."})
                            except Exception as e:
                                print(f"Error comunicando con simulador: {e}")

                        elif cb_data == "ignore":
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={'callback_query_id': cb_id, 'text': 'Dejando correr...'})
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                          json={"chat_id": chat_id, "text": "⏳ Posición sigue abierta."})

        except Exception as e:
            time.sleep(5)

def run_mesa():
    log_diario("MESA DE DINERO V23: Inicializando servicio autónomo (Capa de Régimen Adaptativo).")
    send_telegram(
        "🚀 V23 OPERATIVA — Capa de Régimen Adaptativo\n"
        "• Sistema de Tres Puertas: A (Breakout 1%) · B (Impulso 1%) · C (Reversión a la Media 0.4%, NUEVA)\n"
        "• Clasificador de régimen por símbolo: TENDENCIA / RANGO / BAJA VOLATILIDAD\n"
        "• Límite de exposición correlacionada: máx. 3 posiciones simultáneas por dirección\n"
        "• Comisiones modeladas en cada cierre (0.04%/lado, taker)\n"
        "• Diario forense reparado: el registro estructurado de cierres ya no depende de Claude CLI\n"
        f"• Archivo: {SIMULADOR_TARGET}\n"
        "• Monitoreo de Salida Estándar: ON · Motor de Resiliencia: Armado"
    )

    threading.Thread(target=telegram_polling, daemon=True).start()

    while True:
        print(f"MESA DE DINERO V23: Iniciando proceso de {SIMULADOR_TARGET}...")
        process = subprocess.Popen(
            [sys.executable, SIMULADOR_TARGET],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            line = line.strip()
            if not line:
                continue

            print(f"[SIMULADOR_V23] {line}")

            # 1. Escucha Activa de Señales de Trade — ahora incluye RÉGIMEN detectado
            if line.startswith("ALERTA_TRADE|"):
                partes = line.split("|")
                if len(partes) >= 5:
                    _, tipo, patron, precio, balance = partes[:5]
                    puerta = partes[5] if len(partes) > 5 else 'A'
                    regimen = partes[6] if len(partes) > 6 else 'N/D'
                    icono = PUERTA_ICONOS.get(puerta, '⚪')
                    label = PUERTA_LABELS.get(puerta, 'Sub-estrategia desconocida')
                    regimen_label = REGIMEN_LABELS.get(regimen, regimen)
                    msg = (
                        f"{icono} NUEVA POSICIÓN ABIERTA — Puerta {puerta} | {label}\n"
                        f"• Operación: {tipo}\n"
                        f"• Régimen detectado: {regimen_label}\n"
                        f"• Patrón: {patron}\n"
                        f"• Precio de Entrada: ${float(precio):.2f}\n"
                        f"• Riesgo asignado: {PUERTA_RIESGO.get(puerta, '1%')} del Balance\n"
                        f"• Balance de Cuenta: ${float(balance):.2f}"
                    )
                    send_telegram(msg)
                    log_diario(f"TRADE EJECUTADO: Puerta {puerta} | Régimen {regimen} | {tipo} a ${float(precio):.2f}. Balance: ${float(balance):.2f}")

            # 1.5 Resumen estructurado del backtest histórico — se envía UNA vez,
            #     apenas termina de procesar los 6 símbolos, con el desglose por
            #     puerta y por régimen (la pieza clave para "determinar la mejor estrategia").
            elif line.startswith("ALERTA_BACKTEST_RESUMEN|"):
                try:
                    _, payload = line.split("|", 1)
                    r = json.loads(payload)

                    pf = r.get('profit_factor')
                    pf_str = f"{pf:.3f}" if isinstance(pf, (int, float)) else "∞ (sin pérdidas)"
                    pnl_pct = r.get('net_pnl_pct', 0.0)
                    icono_resultado = "✅" if pnl_pct > 0 else "❌"

                    bloques = [
                        f"{icono_resultado} RESULTADOS DEL BACKTEST HISTÓRICO — V23\n"
                        f"(Puerta A ahora acotada a régimen TENDENCIA)\n"
                        f"• Capital: ${r.get('capital_inicial', 0):,.2f} → ${r.get('capital_final', 0):,.2f}\n"
                        f"• PnL Neto: {pnl_pct:+.2f}% (${r.get('net_pnl_usd', 0):+,.2f})\n"
                        f"• Trades cerrados: {r.get('trades', 0)} | Win Rate: {r.get('win_rate', 0):.1f}% | Profit Factor: {pf_str}"
                    ]

                    for clave_dict, titulo in (('por_puerta', '🚪 Desglose por Puerta'), ('por_regimen', '🌐 Desglose por Régimen')):
                        grupo = r.get(clave_dict, {})
                        if not grupo:
                            continue
                        lineas = [titulo]
                        for k in sorted(grupo.keys()):
                            datos = grupo[k]
                            if clave_dict == 'por_puerta':
                                icono = PUERTA_ICONOS.get(k, '⚪')
                                etiqueta = f"Puerta {k} — {PUERTA_LABELS.get(k, 'Desconocida')}"
                            else:
                                icono = ''
                                etiqueta = REGIMEN_LABELS.get(k, k)
                            lineas.append(
                                f"{icono} {etiqueta}: {datos['trades']} trades | WR {datos['win_rate']:.1f}% | PnL ${datos['pnl']:+,.2f}"
                            )
                        bloques.append("\n".join(lineas))

                    msg = "\n\n".join(bloques)
                    send_telegram(msg)
                    log_diario(f"BACKTEST RESUMEN: PnL {pnl_pct:+.2f}% | Trades {r.get('trades',0)} | WR {r.get('win_rate',0):.1f}% | PF {pf_str}")
                except Exception as e:
                    print(f"MESA DE DINERO V23: Error procesando ALERTA_BACKTEST_RESUMEN: {e}")

            # 2. Escucha Activa de Cierres — ahora incluye Puerta y Régimen para análisis posterior
            elif line.startswith("ALERTA_CIERRE|"):
                partes = line.split("|")
                if len(partes) >= 6:
                    _, tipo, symbol, p_out, pnl, balance = partes[:6]
                    puerta = partes[6] if len(partes) > 6 else '?'
                    regimen = partes[7] if len(partes) > 7 else 'N/D'
                    pnl_f = float(pnl)
                    icono = "✅" if pnl_f > 0 else "❌"
                    resultado = "GANANCIA" if pnl_f > 0 else "PÉRDIDA"
                    regimen_label = REGIMEN_LABELS.get(regimen, regimen)
                    msg = (
                        f"{icono} POSICIÓN CERRADA ({tipo} {symbol}) — Puerta {puerta} | Régimen: {regimen_label}\n"
                        f"• Resultado: {resultado} de ${abs(pnl_f):.2f} (neto de comisiones)\n"
                        f"• Salida: ${float(p_out):.2f}\n"
                        f"• Balance de Cuenta: ${float(balance):.2f}"
                    )
                    send_telegram(msg)
                    log_diario(f"TRADE CERRADO: Puerta {puerta} | Régimen {regimen} | {tipo} {symbol}. PNL neto: ${pnl_f:.2f}. Balance: ${float(balance):.2f}")

            # 2.5 Escucha Activa de Progreso (Deciles) — el aviso clave para "TP ahora vs. dejar correr",
            #     ahora informado por la Puerta y el Régimen que originaron la operación.
            elif line.startswith("ALERTA_PROGRESO|"):
                partes = line.split("|")
                if len(partes) >= 6:
                    _, t_id, symbol, decil, pnl, rev_prob = partes[:6]
                    puerta = partes[6] if len(partes) > 6 else '?'
                    regimen = partes[7] if len(partes) > 7 else 'N/D'
                    label = PUERTA_LABELS.get(puerta, 'Sub-estrategia desconocida')
                    regimen_label = REGIMEN_LABELS.get(regimen, regimen)
                    objetivo_str = "3R (objetivo amplio — Puerta A)" if puerta == 'A' else (
                        "1R (objetivo corto — Puerta B)" if puerta == 'B' else "≈1-1.5R (retorno a la media — Puerta C)"
                    )
                    msg = (
                        f"📊 PROGRESO DEL TRADE ({symbol}) — Puerta {puerta} | {label}\n"
                        f"• Régimen al momento de entrar: {regimen_label}\n"
                        f"• Objetivo de la operación: {objetivo_str}\n"
                        f"• Avance hacia TP: {decil}%\n"
                        f"• PnL Flotante: ${float(pnl):.2f}\n"
                        f"• Probabilidad de Reversión: {rev_prob}%\n\n"
                        f"¿Deseas asegurar ganancia ahora o dejar correr hacia el objetivo completo?"
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "✅ TOMAR PROFIT AHORA", "callback_data": f"close_trade|{symbol}"}],
                            [{"text": "⏳ DEJAR CORRER", "callback_data": "ignore"}]
                        ]
                    }
                    send_telegram(msg, reply_markup=markup)
                    log_diario(f"PROGRESO {symbol}: Puerta {puerta} | Régimen {regimen} | {decil}%. PnL: ${float(pnl):.2f}. Prob Rev: {rev_prob}%")

            # 2.6 Cierres parciales (activación de runner) — también informativos del contexto
            elif line.startswith("ALERTA_PARCIAL|"):
                partes = line.split("|")
                if len(partes) >= 6:
                    tipo, symbol, tp, ganancia = partes[1], partes[2], partes[3], partes[4]
                    puerta = partes[6] if len(partes) > 6 else '?'
                    regimen = partes[7] if len(partes) > 7 else 'N/D'
                    regimen_label = REGIMEN_LABELS.get(regimen, regimen)
                    msg = (
                        f"🎯 CIERRE PARCIAL (50%) — RUNNER ACTIVO ({tipo} {symbol})\n"
                        f"• Puerta {puerta} | Régimen: {regimen_label}\n"
                        f"• Ganancia asegurada en este tramo: {ganancia}\n"
                        f"• El 50% restante queda corriendo con stop en breakeven y trailing dinámico."
                    )
                    send_telegram(msg)
                    log_diario(f"PARCIAL {symbol}: Puerta {puerta} | Régimen {regimen} | TP parcial alcanzado, runner activo. {ganancia}")

            # 3. Protocolo de Resiliencia (Desconexión WS)
            elif line.startswith("ALERTA_WS_DISCONNECT|"):
                partes = line.split("|", 1)
                error = partes[1] if len(partes) > 1 else "Desconocido"
                msg = (
                    f"⚠️ ALERTA DE RESILIENCIA ACTIVADA\n"
                    f"• Conexión WebSocket perdida en Binance Testnet.\n"
                    f"• Detalle: {error}\n"
                    f"• Acción Automática: Reiniciando el motor cuantitativo."
                )
                send_telegram(msg)
                log_diario(f"DESCONEXIÓN WS DETECTADA: {error}. Reiniciando motor...")
                process.terminate()
                time.sleep(3)
                break

        # Evaluamos caída inesperada sin evento WS
        if process.poll() is not None and process.returncode != 0:
            msg = f"⚠️ CRASH DETECTADO\n• {SIMULADOR_TARGET} finalizó (Code: {process.returncode}).\n• Acción: Reiniciando proceso..."
            send_telegram(msg)
            log_diario(f"CRASH DEL SISTEMA (Código {process.returncode}). Reiniciando...")
            time.sleep(5)

if __name__ == "__main__":
    run_mesa()
