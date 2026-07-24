import subprocess
import os
import time
import sys
import threading

import requests

TELEGRAM_TOKEN = "PONE_TU_TOKEN_DE_TELEGRAM_AQUI"
TELEGRAM_TARGET = "1214526208"

def log_diario(mensaje):
    with open('v21_live.log', 'a') as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        f.write(f"[{timestamp}] {mensaje}\n")

def send_telegram(mensaje, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_TARGET, "text": f"[V21_MASTER] {mensaje}"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"MESA DE DINERO ERROR: Fallo al despachar Telegram: {e}")

last_update_id = 0

def telegram_polling():
    global last_update_id
    print("MESA DE DINERO: Iniciando polling interactivo de Telegram...")
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
                            print(f"MESA DE DINERO: Cierre manual solicitado para {symbol} por Telegram.")
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={'callback_query_id': cb_id, 'text': f'Cerrando {symbol}...'})
                            
                            try:
                                r = requests.post("http://127.0.0.1:8053/api/close_trade", json={'symbol': symbol}, timeout=5)
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
    log_diario("MESA DE DINERO: Inicializando servicio autónomo.")
    send_telegram("✅ MESA DE DINERO ACTIVA\n• Monitoreo de Salida Estándar: ON\n• Archivo: simulador_institucional_upgraded.py\n• Motor de Resiliencia: Armado")
    
    threading.Thread(target=telegram_polling, daemon=True).start()
    
    while True:
        print("MESA DE DINERO: Iniciando proceso de simulador_institucional_upgraded.py...")
        process = subprocess.Popen(
            [sys.executable, "simulador_institucional_upgraded.py"],
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
                
            print(f"[SIMULADOR] {line}")
            
            # 1. Escucha Activa de Señales de Trade
            if line.startswith("ALERTA_TRADE|"):
                partes = line.split("|")
                if len(partes) >= 5:
                    _, tipo, patron, precio, balance = partes[:5]
                    puerta = partes[5] if len(partes) > 5 else 'A'
                    icono = "🟢" if puerta == 'A' else "🔵"
                    label = "Alta Convicción (Donchian Breakout)" if puerta == 'A' else "Impulso de Vela (Marubozu/Engulfing)"
                    msg = (
                        f"{icono} NUEVA POSICIÓN ABIERTA — Puerta {puerta} | {label}\n"
                        f"• Operación: {tipo}\n"
                        f"• Patrón: {patron}\n"
                        f"• Precio de Entrada: ${float(precio):.2f}\n"
                        f"• Riesgo: {'2%' if puerta == 'A' else '1%'} del Balance\n"
                        f"• Balance de Cuenta: ${float(balance):.2f}"
                    )
                    send_telegram(msg)
                    log_diario(f"TRADE EJECUTADO: Puerta {puerta} | {tipo} a ${float(precio):.2f}. Balance: ${float(balance):.2f}")
            
            # 2. Escucha Activa de Cierres (Alineada a la V2 Upgraded)
            elif line.startswith("ALERTA_CIERRE|"):
                partes = line.split("|")
                if len(partes) == 6:
                    # FIX: Extracción corregida para evitar ValueError con el Símbolo
                    _, tipo, symbol, p_out, pnl, balance = partes
                    pnl_f = float(pnl)
                    icono = "✅" if pnl_f > 0 else "❌"
                    resultado = "GANANCIA" if pnl_f > 0 else "PÉRDIDA"
                    msg = (
                        f"{icono} POSICIÓN CERRADA ({tipo} {symbol})\n"
                        f"• Resultado: {resultado} de ${abs(pnl_f):.2f}\n"
                        f"• Salida: ${float(p_out):.2f}\n"
                        f"• Balance de Cuenta: ${float(balance):.2f}"
                    )
                    send_telegram(msg)
                    log_diario(f"TRADE CERRADO: {tipo} {symbol}. PNL: ${pnl_f:.2f}. Balance: ${float(balance):.2f}")
                    
            # 2.5 Escucha Activa de Progreso (Deciles)
            elif line.startswith("ALERTA_PROGRESO|"):
                partes = line.split("|")
                if len(partes) == 6:
                    _, t_id, symbol, decil, pnl, rev_prob = partes
                    msg = (
                        f"📊 PROGRESO DEL TRADE ({symbol})\n"
                        f"• Avance hacia TP: {decil}%\n"
                        f"• PnL Flotante: ${float(pnl):.2f}\n"
                        f"• Probabilidad de Reversión: {rev_prob}%\n\n"
                        f"¿Deseas asegurar ganancia ahora?"
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "✅ TOMAR PROFIT AHORA", "callback_data": f"close_trade|{symbol}"}],
                            [{"text": "⏳ DEJAR CORRER", "callback_data": "ignore"}]
                        ]
                    }
                    send_telegram(msg, reply_markup=markup)
                    log_diario(f"PROGRESO {symbol}: {decil}%. PnL: ${float(pnl):.2f}. Prob Rev: {rev_prob}%")

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
            msg = f"⚠️ CRASH DETECTADO\n• simulador_institucional_upgraded.py finalizó (Code: {process.returncode}).\n• Acción: Reiniciando proceso..."
            send_telegram(msg)
            log_diario(f"CRASH DEL SISTEMA (Código {process.returncode}). Reiniciando...")
            time.sleep(5)

if __name__ == "__main__":
    run_mesa()