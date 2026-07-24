import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import requests
import threading
import asyncio
import websockets
import json
import time
import uuid
import hmac
import hashlib
import os
from urllib.parse import urlencode
from dotenv import load_dotenv
from telemetria_quant import generar_reporte_cuantitativo
from agente_claude import validar_operacion_con_claude

from estrategia_v15 import compute_indicators, compute_signals_and_trades, INTERVAL

load_dotenv()
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

# =========================================================================
# DICCIONARIO DE PORTAFOLIO Y RIESGO (ESCALABILIDAD HORIZONTAL)
# =========================================================================
PORTFOLIO = {
    'ETHUSDT': {'risk': 0.002},
    'SOLUSDT': {'risk': 0.002},
    'BNBUSDT': {'risk': 0.002},
    'XRPUSDT': {'risk': 0.002},
    'ADAUSDT': {'risk': 0.002},
    'LINKUSDT': {'risk': 0.002}
}

ASSET_RULES = {}

MAX_CANDLES = 1000

# Estado Global Multihilo
data_lock = threading.Lock()
df_global = {sym: pd.DataFrame() for sym in PORTFOLIO.keys()}
is_ready = False

# Estado de Simulación y Trazabilidad Global
sim_state = {
    'initial_balance': 500.0,
    'balance': 500.0,
    'trades': []
}

# =========================================================================
# DESCUBRIMIENTO DE PRECISIONES Y LOTES MÍNIMOS DE BINANCE
# =========================================================================
def fetch_exchange_precision():
    global ASSET_RULES
    # Usamos la Testnet (demo-fapi) porque es ahí donde estás enviando las órdenes Limit
    url = "https://demo-fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        
        for symbol_data in data['symbols']:
            sym = symbol_data['symbol']
            if sym in PORTFOLIO:
                # Binance Futures entrega la precisión directamente en estos campos
                ASSET_RULES[sym] = {
                    'qty_dec': symbol_data['quantityPrecision'],
                    'price_dec': symbol_data['pricePrecision']
                }
                
        print("INFO: Reglas de precisión de Binance cargadas dinámicamente:")
        for k, v in ASSET_RULES.items():
            print(f"      {k} -> Qty: {v['qty_dec']} decimales | Precio: {v['price_dec']} decimales")
            
    except Exception as e:
        print(f"ERROR CRÍTICO: No se pudo obtener la información de exchangeInfo: {e}")
        # En caso extremo, podrías detener el bot aquí con sys.exit(1)

# =========================================================================
# MOTOR CUANTITATIVO, GESTIÓN DE RIESGO Y RED
# =========================================================================
def get_real_balance():
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return sim_state['balance']
    url = "https://demo-fapi.binance.com/fapi/v2/balance"
    timestamp = int(time.time() * 1000)
    query_string = urlencode({'timestamp': timestamp})
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    try:
        res = requests.get(f"{url}?{query_string}&signature={signature}", headers=headers)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                if item['asset'] == 'USDT':
                    return float(item['balance'])
    except Exception as e:
        print(f"ERROR: No se pudo obtener el balance de la API: {e}")
    return sim_state['balance']

def set_leverage(symbol):
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        print(f"WARNING: API Keys no configuradas, omitiendo apalancamiento para {symbol}.")
        return
    url = "https://demo-fapi.binance.com/fapi/v1/leverage"
    timestamp = int(time.time() * 1000)
    params = {'symbol': symbol, 'leverage': 5, 'timestamp': timestamp}
    query_string = urlencode(params)
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    try:
        res = requests.post(f"{url}?{query_string}&signature={signature}", headers=headers)
        if res.status_code == 200:
            print(f"INFO: Apalancamiento a 5x configurado para {symbol}.")
    except Exception as e:
        print(f"ERROR: Excepción en set_leverage para {symbol}: {e}")

async def enviar_orden_binance(symbol, tipo_orden, precio_actual, sl, tp, qty, trade_id):
    """
    Motor de ejecución MAKER (LIMIT). Coloca orden, espera llenado y despliega escudos.
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        print(f"SIMULACIÓN LIMIT [{symbol}]: {tipo_orden} a {precio_actual} (SL: {sl}, TP: {tp})")
        return

    url_base = "https://demo-fapi.binance.com/fapi/v1/order"
    qty = 0.001 if qty < 0.001 else round(qty, 3)
    side = 'BUY' if tipo_orden == 'LONG' else 'SELL'
    sl_side = 'SELL' if tipo_orden == 'LONG' else 'BUY'

    # Redondeo para evitar errores de precisión de Binance
    limit_price = round(precio_actual, 2)

    def peticion_firmada(method, p):
        q = urlencode(p)
        sig = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), q.encode('utf-8'), hashlib.sha256).hexdigest()
        h = {'X-MBX-APIKEY': BINANCE_API_KEY}
        url_full = f"{url_base}?{q}&signature={sig}"
        if method == 'POST': return requests.post(url_full, headers=h)
        if method == 'GET': return requests.get(url_full, headers=h)
        if method == 'DELETE': return requests.delete(url_full, headers=h)

    # 1. Enviar orden LIMIT MAKER (GTX = Post Only)
    params_limit = {
        'symbol': symbol, 'side': side, 'type': 'LIMIT', 'timeInForce': 'GTX',
        'quantity': qty, 'price': limit_price, 'timestamp': int(time.time() * 1000)
    }

    try:
        res_limit = await asyncio.to_thread(peticion_firmada, 'POST', params_limit)
        order_data = res_limit.json()

        if 'orderId' not in order_data:
            print(f"ERROR API LIMIT [{symbol}]: {order_data}")
            return

        order_id = order_data['orderId']
        print(f"API MAKER [{symbol}]: Orden LIMIT enviada. Esperando fill a {limit_price}...")

        # 2. Polling loop (Bucle de espera de 5 minutos máximos)
        timeout_seconds = 300
        start_time = time.time()
        is_filled = False

        while time.time() - start_time < timeout_seconds:
            await asyncio.sleep(5) # Asincronía para no bloquear el Dash ni WebSockets

            check_params = {'symbol': symbol, 'orderId': order_id, 'timestamp': int(time.time() * 1000)}
            res_check = await asyncio.to_thread(peticion_firmada, 'GET', check_params)
            status_data = res_check.json()

            if status_data.get('status') == 'FILLED':
                is_filled = True
                break
            elif status_data.get('status') in ['CANCELED', 'EXPIRED', 'REJECTED']:
                print(f"API MAKER [{symbol}]: Orden LIMIT interrumpida externamente.")
                break

        # 3. Cancelación por Timeout y Sincronización UI
        if not is_filled:
            print(f"API MAKER [{symbol}]: Timeout. Cancelando orden LIMIT huérfana {order_id}...")
            cancel_params = {'symbol': symbol, 'orderId': order_id, 'timestamp': int(time.time() * 1000)}
            await asyncio.to_thread(peticion_firmada, 'DELETE', cancel_params)

            # --- CAPA DE TELEGRAM: ALERTA DE ORDEN ESCAPADA ---
            print(f"ALERTA_CANCELADA|{symbol}|{tipo_orden}|Precio {limit_price} no alcanzado en 5 min.", flush=True)

            for t in sim_state['trades']:
                if t['id'] == trade_id:
                    t['status'] = 'CANCELADA'
            return

            # Anulamos el trade en el Dashboard para liberar cupo a nuevas señales
            for t in sim_state['trades']:
                if t['id'] == trade_id:
                    t['status'] = 'CANCELADA'
            return

        print(f"API MAKER [{symbol}]: ¡Orden LIMIT Llenada! Desplegando escudos institucionales...")

        # 4. Despliegue de SL y TP
        p_sl = {
            'symbol': symbol, 'side': sl_side, 'type': 'STOP_MARKET',
            'stopPrice': round(sl, 2), 'closePosition': 'true', 'timestamp': int(time.time() * 1000)
        }
        await asyncio.to_thread(peticion_firmada, 'POST', p_sl)

        p_tp = {
            'symbol': symbol, 'side': sl_side, 'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': round(tp, 2), 'closePosition': 'true', 'timestamp': int(time.time() * 1000)
        }
        await asyncio.to_thread(peticion_firmada, 'POST', p_tp)

        print(f"API EJECUCIÓN [{symbol}]: Secuencia completada. Riesgo asimétrico activo.")

    except Exception as e:
        print(f"ERROR CRÍTICO: Fallo en secuencia MAKER para {symbol}: {e}")

def evaluate_open_trades(candle, symbol, current_atr):
    global is_ready

    for t in sim_state['trades']:
        if t['symbol'] != symbol: continue
        
        if t['status'] == 'ABIERTA':
            # --- EVALUACIÓN DE LONG ---
            if t['type'] == 'LONG':
                if 'highest_price' not in t: t['highest_price'] = t['entry_price']
                if candle['high'] > t['highest_price']: t['highest_price'] = candle['high']

                if candle['low'] <= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'STOP LOSS (Riesgo Asumido)'
                    t['pnl'] = (t['exit_price'] - t['entry_price']) * t['qty']
                    sim_state['balance'] += t['pnl']
                    if is_ready: print(f"ALERTA_CIERRE|{t['type']}|{symbol}|{t['exit_price']:.4f}|{t['pnl']:.4f}|{sim_state['balance']:.4f}", flush=True)
                elif candle['high'] >= t['tp']:
                    # Cierre parcial 50%
                    t['status'] = 'RUNNER'
                    partial_pnl = (t['tp'] - t['entry_price']) * (t['qty'] * 0.5)
                    t['pnl'] += partial_pnl
                    sim_state['balance'] += partial_pnl
                    t['qty'] = t['qty'] * 0.5 # Queda 50%
                    t['sl'] = t['entry_price'] # Breakeven
                    if is_ready: print(f"ALERTA_PARCIAL|{t['type']}|{symbol}|{t['tp']:.4f}|+{partial_pnl:.4f}|RUNNER ACTIVO", flush=True)

            # --- EVALUACIÓN DE SHORT ---
            elif t['type'] == 'SHORT':
                if 'lowest_price' not in t: t['lowest_price'] = t['entry_price']
                if candle['low'] < t['lowest_price']: t['lowest_price'] = candle['low']

                if candle['high'] >= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'STOP LOSS (Riesgo Asumido)'
                    t['pnl'] = (t['entry_price'] - t['exit_price']) * t['qty']
                    sim_state['balance'] += t['pnl']
                    if is_ready: print(f"ALERTA_CIERRE|{t['type']}|{symbol}|{t['exit_price']:.4f}|{t['pnl']:.4f}|{sim_state['balance']:.4f}", flush=True)
                elif candle['low'] <= t['tp']:
                    # Cierre parcial 50%
                    t['status'] = 'RUNNER'
                    partial_pnl = (t['entry_price'] - t['tp']) * (t['qty'] * 0.5)
                    t['pnl'] += partial_pnl
                    sim_state['balance'] += partial_pnl
                    t['qty'] = t['qty'] * 0.5
                    t['sl'] = t['entry_price'] # Breakeven
                    if is_ready: print(f"ALERTA_PARCIAL|{t['type']}|{symbol}|{t['tp']:.4f}|+{partial_pnl:.4f}|RUNNER ACTIVO", flush=True)

        elif t['status'] == 'RUNNER':
            # Gestión dinámica para el runner
            if t['type'] == 'LONG':
                if 'highest_price' not in t: t['highest_price'] = t['entry_price']
                if candle['high'] > t['highest_price']: t['highest_price'] = candle['high']
                
                # Trailing Stop Update (1R dinámico desde el máximo alcanzado)
                trailing_sl = t['highest_price'] - (t['tp'] - t['entry_price'])
                if trailing_sl > t['sl']: t['sl'] = trailing_sl
                
                # Check exit
                if candle['low'] <= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'TRAILING STOP'
                    runner_pnl = (t['exit_price'] - t['entry_price']) * t['qty']
                    t['pnl'] += runner_pnl
                    sim_state['balance'] += runner_pnl
                    if is_ready: print(f"ALERTA_CIERRE_RUNNER|{t['type']}|{symbol}|{t['exit_price']:.4f}|{runner_pnl:.4f}|Total PnL:{t['pnl']:.4f}", flush=True)
                    
            elif t['type'] == 'SHORT':
                if 'lowest_price' not in t: t['lowest_price'] = t['entry_price']
                if candle['low'] < t['lowest_price']: t['lowest_price'] = candle['low']
                
                # Trailing Stop Update (1R dinámico desde el mínimo alcanzado)
                trailing_sl = t['lowest_price'] + (t['entry_price'] - t['tp'])
                if trailing_sl < t['sl']: t['sl'] = trailing_sl
                
                # Check exit
                if candle['high'] >= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'TRAILING STOP'
                    runner_pnl = (t['entry_price'] - t['exit_price']) * t['qty']
                    t['pnl'] += runner_pnl
                    sim_state['balance'] += runner_pnl
                    if is_ready: print(f"ALERTA_CIERRE_RUNNER|{t['type']}|{symbol}|{t['exit_price']:.4f}|{runner_pnl:.4f}|Total PnL:{t['pnl']:.4f}", flush=True)

def process_historical_signals(df, symbol):
    config = PORTFOLIO[symbol]
    for i in range(200, len(df)):
        current_time = df.at[i, 'time']
        current_atr = df.at[i, 'ATR'] if 'ATR' in df.columns else 0.0

        evaluate_open_trades({'time': current_time, 'high': df.at[i, 'high'], 'low': df.at[i, 'low']}, symbol, current_atr)

        if df.at[i, 'is_closed']:
            sub_df = df.iloc[:i+1]
            trade_abierto_sym = any(t['status'] == 'ABIERTA' and t['symbol'] == symbol for t in sim_state['trades'])

            if not trade_abierto_sym:
                dynamic_risk = config['risk']
                closed_trades_sym = [t for t in sim_state['trades'] if t['symbol'] == symbol and t['status'] == 'CERRADA']

                if closed_trades_sym:
                    ultimo_trade = closed_trades_sym[-1]
                    if ultimo_trade['pnl'] > 0:
                        dynamic_risk = config['risk'] * 1.5

                signal, trade_data = compute_signals_and_trades(
                    sub_df, sim_state['balance'], dynamic_risk
                )

                if signal and trade_data:
                    # --- FILTRO SHORT-ONLY (HISTÓRICO) ---
                    #if signal == 'LONG':
                    #    continue
                    # -------------------------------------
                    week_ago = current_time - pd.Timedelta(days=7)
                    recent_losses = sum(1 for tr in sim_state['trades'] if tr['symbol'] == symbol and tr['status'] == 'CERRADA' and tr['pnl'] < 0 and tr['exit_time'] and tr['exit_time'] >= week_ago)
                    
                    if recent_losses < 3 and sim_state['balance'] >= 5.0:
                        #Capturamos los pesos directamente de la métrica forense
                        w_trend = trade_data.get('metrics', {}).get('trend_w', 0)
                        w_mr = trade_data.get('metrics', {}).get('mr_w', 0)
                        regimen_dominante = 'MR' if w_mr > w_trend else 'TREND'

                        sim_state['trades'].append({
                            'id': str(uuid.uuid4())[:8],
                            'symbol': symbol,
                            'type': signal,
                            'status': 'ABIERTA',
                            'regimen': regimen_dominante,
                            'entry_time': current_time,
                            'entry_price': trade_data['entry_price'],
                            'sl': trade_data['stop_loss'],
                            'tp': trade_data['take_profit'],
                            'qty': trade_data['qty'],
                            'conviccion': trade_data.get('conviccion', 0.0), # <-- Forense
                            'metrics': trade_data.get('metrics', {}),        # <-- Forense
                            'exit_time': None,
                            'exit_price': None,
                            'exit_reason': None,                             # <-- Forense
                            'pnl': 0.0
                        })
    # --- NUEVO BLOQUE DE TELEMETRÍA FORENSE AVANZADA (AL FINAL DE LA FUNCIÓN) ---
    print(f"\n=== AUDITORÍA FORENSE DE TRADES [{symbol}] ===")
    for t in sim_state['trades']:
        if t['symbol'] == symbol and t['status'] == 'CERRADA':
            resultado = "GANADOR" if t['pnl'] > 0 else "PERDEDOR"
            m = t.get('metrics', {})
            
            # Cálculo de Excursión Máxima a Favor (MFE)
            if t['type'] == 'LONG':
                max_reach = t.get('highest_price', t['entry_price'])
                dist_reach_usd = max_reach - t['entry_price']
                dist_tp_faltante = t['tp'] - max_reach if t['tp'] > max_reach else 0
            else:
                max_reach = t.get('lowest_price', t['entry_price'])
                dist_reach_usd = t['entry_price'] - max_reach
                dist_tp_faltante = max_reach - t['tp'] if max_reach > t['tp'] else 0
                
            dist_reach_pct = (dist_reach_usd / t['entry_price']) * 100 if t['entry_price'] > 0 else 0

            print(f"[{t['type']}] {resultado}: ${t['pnl']:.2f}")
            print(f" ├─ Tiempos -> Entrada: {t['entry_time']} | Salida: {t.get('exit_time', 'N/A')}")
            print(f" ├─ Precios -> In: ${t['entry_price']} | Out: ${t['exit_price']:.2f} | Razón: {t.get('exit_reason', 'N/A')}")
            print(f" ├─ Recorrido-> Max Alcance: ${max_reach:.2f} (+{dist_reach_pct:.2f}%) | Faltó para TP: ${dist_tp_faltante:.2f}")
            print(f" ├─ Convicción: {t.get('conviccion', 0.0)}%")
            print(f" └─ Desglose -> Tendencia: {m.get('trend_w', 0)}% | MR: {m.get('mr_w', 0)}% | Z-Score: {m.get('adx_zs', 0)}")
    print("===============================================\n")

def fetch_history():
    global df_global, is_ready
    for symbol in PORTFOLIO.keys():
        print(f"INFO: Sincronizando datos históricos para {symbol} {INTERVAL}...")
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={INTERVAL}&limit=1000"
        try:
            res = requests.get(url)
            res.raise_for_status()
            data = res.json()
            
            if isinstance(data, dict) and 'code' in data:
                print(f"CRITICAL ERROR: Binance API error {symbol}: {data.get('msg', data)}")
                continue

            columns = ['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tb', 'tq', 'ignore']
            df = pd.DataFrame(data, columns=columns)
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
            df['is_closed'] = True

            df = compute_indicators(df)
            process_historical_signals(df, symbol)

            with data_lock:
                df_global[symbol] = df
        except Exception as e:
            print(f"CRITICAL ERROR: Fallo en extracción REST histórica {symbol}: {e}")

    with data_lock:
        is_ready = True
    print("INFO: Caché histórico completado para todos los símbolos.")
    # --- INYECCIÓN DE TELEMETRÍA CUANTITATIVA ---
    try:
        # Extraemos directamente la lista de trades del estado global
        todos_los_trades_globales = sim_state.get('trades', [])
        capital_base = sim_state.get('initial_balance', 500.0)

        # Generamos y disparamos el reporte
        reporte_tv = generar_reporte_cuantitativo(todos_los_trades_globales, capital_inicial=capital_base)
        print(reporte_tv)

    except Exception as e:
        print(f"⚠️ AVISO TELEMETRÍA: Error al generar el reporte: {e}")
    # ---------------------------------------------

def binance_ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def ws_logic():
        global df_global
        streams = '/'.join([f"{sym.lower()}@kline_{INTERVAL}" for sym in PORTFOLIO.keys()])
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        backoff = 1

        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    print(f"INFO: Flujo WebSocket Multiplexado conectado a {len(PORTFOLIO)} pares.")
                    backoff = 1 # Reset backoff on successful connection
                    while True:
                        msg = await ws.recv()
                        payload = json.loads(msg)

                        if 'data' not in payload: continue
                        data = payload['data']['k']
                        symbol_event = data['s'].upper()
                        candle_time = pd.to_datetime(data['t'], unit='ms')

                        with data_lock:
                            df_sym = df_global[symbol_event]
                            if not df_sym.empty:
                                last_time = df_sym.iloc[-1]['time']
                                is_candle_closed = data['x']

                                new_row = {
                                    'time': candle_time, 'open': float(data['o']), 'high': float(data['h']),
                                    'low': float(data['l']), 'close': float(data['c']), 'volume': float(data['v']),
                                    'is_closed': is_candle_closed
                                }

                                if candle_time == last_time:
                                    for k, v in new_row.items():
                                        df_sym.at[df_sym.index[-1], k] = v
                                    current_atr = df_sym.iloc[-1]['ATR'] if 'ATR' in df_sym.columns else 0.0
                                    evaluate_open_trades({'time': candle_time, 'high': new_row['high'], 'low': new_row['low']}, symbol_event, current_atr)
                                else:
                                    df_sym = pd.concat([df_sym, pd.DataFrame([new_row])], ignore_index=True)
                                    if len(df_sym) > MAX_CANDLES:
                                        df_sym = df_sym.iloc[-MAX_CANDLES:].reset_index(drop=True)

                                df_sym = compute_indicators(df_sym)
                                df_global[symbol_event] = df_sym

                                if is_candle_closed:
                                    ultima_vela = df_sym.iloc[-1]
                                    print(f"[{symbol_event}] Cierre: {ultima_vela['close']} | EMA200: {ultima_vela.get('EMA_200', 'N/A')} | Vol: {ultima_vela['volume']}", flush=True)

                                    current_balance = get_real_balance()
                                    sim_state['balance'] = current_balance
                                    config = PORTFOLIO[symbol_event]

                                    trade_abierto_sym = any(t['status'] == 'ABIERTA' and t['symbol'] == symbol_event for t in sim_state['trades'])

                                    if not trade_abierto_sym:
                                        dynamic_risk = config['risk']
                                        closed_trades_sym = [t for t in sim_state['trades'] if t['symbol'] == symbol_event and t['status'] == 'CERRADA']

                                        if closed_trades_sym:
                                            ultimo_trade = closed_trades_sym[-1]
                                            if ultimo_trade['pnl'] > 0:
                                                dynamic_risk = config['risk'] * 1.5

                                        signal, trade_data = compute_signals_and_trades(
                                            df_sym, current_balance, dynamic_risk
                                        )

                                        if signal and trade_data:
                                            week_ago = candle_time - pd.Timedelta(days=7)
                                            recent_losses = sum(1 for tr in sim_state['trades'] if tr['symbol'] == symbol_event and tr['status'] == 'CERRADA' and tr['pnl'] < 0 and tr['exit_time'] and tr['exit_time'] >= week_ago)

                                            if recent_losses < 3 and current_balance >= 5.0:
                                                # --- VALIDACIÓN DE CLAUDE OPUS ---
                                                print(f"INFO: Solicitando validación de Claude Opus para trade {signal} en {symbol_event}...")
                                                es_valido = validar_operacion_con_claude(symbol_event, signal, trade_data)
                                                
                                                if es_valido:
                                                    c = trade_data['entry_price']
                                                    sl = trade_data['stop_loss']
                                                    tp = trade_data['take_profit']
                                                    qty = trade_data['qty']
                                                    
                                                    if is_ready:
                                                        patron_str = f"{symbol_event} - V13 LIMIT (QTY:{qty} SL:{sl} TP:{tp})"
                                                        print(f"ALERTA_TRADE|{signal}|{patron_str}|{c}|{current_balance}", flush=True)

                                                    new_trade_id = str(uuid.uuid4())[:8]

                                                    sim_state['trades'].append({
                                                        'id': new_trade_id,
                                                        'symbol': symbol_event,
                                                        'type': signal,
                                                        'status': 'ABIERTA',
                                                        'entry_time': candle_time,
                                                        'entry_price': trade_data['entry_price'],
                                                        'sl': trade_data['stop_loss'],
                                                        'tp': trade_data['take_profit'],
                                                        'qty': trade_data['qty'],
                                                        'conviccion': trade_data.get('conviccion', 0.0),
                                                        'metrics': trade_data.get('metrics', {}),
                                                        'exit_time': None,
                                                        'exit_price': None,
                                                        'exit_reason': None,
                                                        'pnl': 0.0
                                                    })

                                                    if is_ready:
                                                        try:
                                                            asyncio.create_task(enviar_orden_binance(symbol_event, signal, c, sl, tp, qty, new_trade_id))
                                                        except RuntimeError:
                                                            pass

            except websockets.exceptions.ConnectionClosedError as e:
                print(f"WARNING: Desconexión WS (Error {e.code}). Reconectando en {backoff}s...", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as e:
                print(f"WARNING: Pérdida de paquetes WS Multiplexado. Reconectando en {backoff}s... Detalle: {e}", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    loop.run_until_complete(ws_logic())

# =========================================================================
# INTERFAZ DE USUARIO REACTIVA (DASHBOARD MODERN UI/UX)
# =========================================================================
app = dash.Dash(__name__, title="Quant Terminal - Portfolio")

scorecard_style = {
    'backgroundColor': '#1a1a1a', 'padding': '15px', 'borderRadius': '8px',
    'textAlign': 'center', 'border': '1px solid #333', 'flex': '1', 'margin': '0 10px'
}
value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'margin': '5px 0 0 0'}

app.layout = html.Div([
    html.H2("Terminal Cuantitativa Institucional - Escáner de Portafolio", style={'textAlign': 'center', 'color': '#00ffcc', 'fontFamily': 'monospace'}),

    html.Div([
        html.Div([html.Div("Total Longs", style={'color': '#888'}), html.Div(id="score-longs", style={**value_style, 'color': '#00ff9d'})], style=scorecard_style),
        html.Div([html.Div("Total Shorts", style={'color': '#888'}), html.Div(id="score-shorts", style={**value_style, 'color': '#ff3366'})], style=scorecard_style),
        html.Div([html.Div("Operaciones Abiertas", style={'color': '#888'}), html.Div(id="score-open", style={**value_style, 'color': '#00bfff'})], style=scorecard_style),
        html.Div([html.Div("Operaciones Cerradas", style={'color': '#888'}), html.Div(id="score-closed", style={**value_style, 'color': '#b3b3b3'})], style=scorecard_style),
        html.Div([html.Div("Balance Global (USD)", style={'color': '#888'}), html.Div(id="score-balance", style={**value_style, 'color': '#ffffff'})], style=scorecard_style),
        html.Div([html.Div("P&L Total", style={'color': '#888'}), html.Div(id="score-pnl", style=value_style)], style=scorecard_style),
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '10px'}),

    html.Div([
        html.Div([html.Div("Win Rate (Acierto)", style={'color': '#888'}), html.Div(id="score-winrate", style={**value_style, 'color': '#00ffcc'})], style=scorecard_style),
        html.Div([html.Div("Profit Actual Total", style={'color': '#888'}), html.Div(id="score-profit", style={**value_style, 'color': '#00ff9d'})], style=scorecard_style),
        html.Div([html.Div("Riesgo Global / Trade", style={'color': '#888'}), html.Div(id="score-riesgo", style={**value_style, 'color': '#ffaa00'})], style=scorecard_style),
        html.Div([html.Div("Esperanza Matemática", style={'color': '#888'}), html.Div(id="score-esperanza", style={**value_style, 'color': '#b3b3b3'})], style=scorecard_style),
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '20px'}),

    html.Div([
        dcc.Dropdown(
            id='symbol-selector',
            options=[{'label': sym, 'value': sym} for sym in PORTFOLIO.keys()],
            value=list(PORTFOLIO.keys())[0],
            style={'backgroundColor': '#1a1a1a', 'color': '#000000', 'width': '300px', 'marginBottom': '10px'}
        )
    ], style={'display': 'flex', 'justifyContent': 'center'}),

    dcc.Graph(id='live-chart', style={'height': '70vh'}),
    dcc.Interval(id='interval-update', interval=1000, n_intervals=0)
], style={'backgroundColor': '#0a0a0a', 'padding': '20px', 'minHeight': '100vh', 'fontFamily': 'sans-serif'})

@app.callback(
    Output('live-chart', 'figure'),
    Output('score-longs', 'children'),
    Output('score-shorts', 'children'),
    Output('score-open', 'children'),
    Output('score-closed', 'children'),
    Output('score-balance', 'children'),
    Output('score-pnl', 'children'),
    Output('score-winrate', 'children'),
    Output('score-profit', 'children'),
    Output('score-riesgo', 'children'),
    Output('score-esperanza', 'children'),
    Input('interval-update', 'n_intervals'),
    Input('symbol-selector', 'value'),
    prevent_initial_call=False
)
def update_dashboard(n, selected_symbol):
    if not is_ready:
        empty_fig = go.Figure().update_layout(title="Iniciando escaneo multiplexado...", template='plotly_dark', paper_bgcolor='#0a0a0a', plot_bgcolor='#121212')
        return empty_fig, "0", "0", "0", "0", "$0.00", "0.00%", "0.00%", "$0.00", "1% del Balance Dinámico", "$0.00"

    with data_lock:
        df = df_global[selected_symbol].copy()
        trades = list(sim_state['trades'])
        balance = sim_state['balance']
        init_balance = sim_state['initial_balance']

    # Filtrar solo trades reales para la estadística (ignorar CANCELADAS por expiración de orden Limit)
    valid_trades = [t for t in trades if t['status'] != 'CANCELADA']

    total_longs = sum(1 for t in valid_trades if t['type'] == 'LONG')
    total_shorts = sum(1 for t in valid_trades if t['type'] == 'SHORT')
    open_trades = sum(1 for t in valid_trades if t['status'] == 'ABIERTA')
    closed_trades = sum(1 for t in valid_trades if t['status'] == 'CERRADA')

    pnl_value = balance - init_balance
    pnl_pct = (pnl_value / init_balance) * 100
    pnl_color = '#00ff9d' if pnl_value >= 0 else '#ff3366'
    pnl_str = html.Span(f"${pnl_value:,.2f} ({pnl_pct:,.2f}%)", style={'color': pnl_color})

    closed_trades_list = [t for t in valid_trades if t['status'] == 'CERRADA']
    winning_trades = sum(1 for t in closed_trades_list if t['pnl'] > 0)
    losing_trades = closed_trades - winning_trades

    win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    winrate_str = f"{win_rate:,.2f}%"

    profit_actual_total = sum(t['pnl'] for t in closed_trades_list)
    profit_str = f"${profit_actual_total:,.2f}"
    riesgo_str = "1% del Balance Global Dinámico"

    avg_win = sum(t['pnl'] for t in closed_trades_list if t['pnl'] > 0) / winning_trades if winning_trades > 0 else 0.0
    avg_loss = sum(abs(t['pnl']) for t in closed_trades_list if t['pnl'] <= 0) / losing_trades if losing_trades > 0 else 0.0
    prob_win = win_rate / 100.0
    prob_loss = 1.0 - prob_win
    esperanza = (prob_win * avg_win) - (prob_loss * avg_loss)
    esperanza_str = f"${esperanza:,.2f}"

    if df.empty:
        return go.Figure(), str(total_longs), str(total_shorts), str(open_trades), str(closed_trades), f"${balance:,.2f}", pnl_str, winrate_str, profit_str, riesgo_str, esperanza_str

    df_view = df.copy()
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

    fig.add_trace(go.Candlestick(
        x=df_view['time'], open=df_view['open'], high=df_view['high'], low=df_view['low'], close=df_view['close'],
        name=selected_symbol, increasing_line_color='#00ff9d', decreasing_line_color='#ff3366'
    ))

    if 'EMA_200' in df_view.columns:
        fig.add_trace(go.Scatter(
            x=df_view['time'], y=df_view['EMA_200'], mode='lines', name='EMA 200',
            line=dict(color='#00bfff', width=1.5)
        ))

    for t in valid_trades:
        if t['symbol'] != selected_symbol:
            continue

        if t['entry_time'] < df_view['time'].iloc[0] and t['status'] == 'CERRADA' and t['exit_time'] < df_view['time'].iloc[0]:
            continue

        start_t = t['entry_time']
        end_t = t['exit_time'] if t['status'] == 'CERRADA' else df_view['time'].iloc[-1]

        if t['type'] == 'LONG':
            fig.add_trace(go.Scatter(
                x=[t['entry_time']], y=[t['entry_price']], mode='markers',
                marker=dict(symbol='triangle-up', color='#00ff9d', size=14, line=dict(color='white', width=1)),
                showlegend=False, hoverinfo='skip'
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t['entry_time']], y=[t['entry_price']], mode='markers',
                marker=dict(symbol='triangle-down', color='#ffaa00', size=14, line=dict(color='white', width=1)),
                showlegend=False, hoverinfo='skip'
            ))

        fig.add_trace(go.Scatter(x=[start_t, end_t], y=[t['sl'], t['sl']], mode='lines', line=dict(color='#ff3366', width=2, dash='dot'), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=[start_t, end_t], y=[t['tp'], t['tp']], mode='lines', line=dict(color='#00ff9d', width=2, dash='dot'), showlegend=False, hoverinfo='skip'))

        if t['status'] == 'CERRADA':
            fig.add_trace(go.Scatter(
                x=[t['exit_time']], y=[t['exit_price']], mode='markers',
                marker=dict(symbol='x', color='#ff3366', size=10, line=dict(width=2)),
                showlegend=False, hoverinfo='skip'
            ))

    fig.update_layout(
        template='plotly_dark', margin=dict(l=30, r=30, t=30, b=30),
        plot_bgcolor='#121212', paper_bgcolor='#0a0a0a', xaxis_rangeslider_visible=False,
        hovermode='x unified', showlegend=True, uirevision='constant',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="Precio (USD)", gridcolor='#333333')

    return fig, str(total_longs), str(total_shorts), str(open_trades), str(closed_trades), f"${balance:,.2f}", pnl_str, winrate_str, profit_str, riesgo_str, esperanza_str

if __name__ == '__main__':
    print("STATUS: Iniciando Motor Multiplexado V2 [MODO LIMIT / MAKER]...")
    
    # 1. Cargar reglas de la API dinámicamente
    fetch_exchange_precision()

    # 2. Configurar apalancamiento
    for sym in PORTFOLIO.keys():
        set_leverage(sym)
    
    # 3. Sincronizar historial
    fetch_history()
    
    # 4. Lanzar el hilo de WebSockets
    t = threading.Thread(target=binance_ws_thread, daemon=True)
    t.start()
    
    # 5. Iniciar Dash
    app.run(debug=False, host='127.0.0.1', port=8050)
