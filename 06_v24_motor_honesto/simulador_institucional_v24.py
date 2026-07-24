import dash
from dash import dcc, html
from flask import request, jsonify
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
import diario_forense_claude
from diario_forense_claude import registrar_apertura, analisis_post_mortem_claude

import hmac
import hashlib
import os
import copy
from urllib.parse import urlencode
from dotenv import load_dotenv
from telemetria_quant import generar_reporte_cuantitativo
from agente_claude import validar_operacion_con_claude

from estrategia_v24_Master import compute_indicators, compute_signals_and_trades, INTERVAL, check_multi_candle_exhaustion, classify_regime

load_dotenv()
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')

# =========================================================================
# DICCIONARIO DE PORTAFOLIO Y RIESGO (ESCALABILIDAD HORIZONTAL)
# El riesgo base por símbolo se mantiene en 1% — la diferenciación fina por
# sub-estrategia (Puerta A=1%, B=1%, C=0.4%) ahora vive en estrategia_v24_Master,
# que devuelve su propio "risk" recomendado dentro de trade_data/compute_signals_and_trades.
# =========================================================================
PORTFOLIO = {
    'ETHUSDT': {'risk': 0.01},
    'SOLUSDT': {'risk': 0.01},
    'BNBUSDT': {'risk': 0.01},
    'XRPUSDT': {'risk': 0.01},
    'ADAUSDT': {'risk': 0.01},
    'LINKUSDT': {'risk': 0.01}
}

ASSET_RULES = {}

MAX_CANDLES = 1000

# Profundidad histórica para el backtest forense al arranque (1h x 3000 ~ 125 días).
# Independiente de MAX_CANDLES: este valor solo afecta la carga inicial vía
# _fetch_klines_paginated; el dataframe en vivo se sigue recortando a MAX_CANDLES.
BACKTEST_CANDLES = 3000

# --- BACKTEST DE REGRESIÓN: ventana fija (2026-06-09T00:00:00Z) ---
# El backtest forense original usa "ahora - BACKTEST_CANDLES velas", una ventana
# que se desplaza en cada restart, haciendo que backtest_history.csv compare
# manzanas con naranjas (componentes no tocados por un cambio podían variar
# cientos de dólares solo por el desplazamiento temporal). Este timestamp fijo
# congela la ventana de regresión para que cada restart reproduzca EXACTAMENTE
# las mismas BACKTEST_CANDLES velas, aislado del estado de trading en vivo
# (ver fetch_history). El backtest "en vivo" (ALERTA_BACKTEST_RESUMEN, sin
# sufijo) sigue usando datos recientes sin cambios.
BACKTEST_FIXED_END_TIME_MS = 1780963200000

# --- NUEVO V22: límite de exposición direccional correlacionada (OPCION_1_BETA 2.4) ---
# El diario forense de V21 reveló que el sistema dispara la MISMA apuesta direccional
# en varios símbolos casi a la vez (correlación entre criptoactivos). Este límite
# evita que el riesgo agregado del portafolio se concentre en una sola dirección.
MAX_SAME_DIRECTION_POSITIONS = 3

# --- MODELO DE COSTOS (V24: comisión + slippage + funding) ---
# El backtest de V22 solo modelaba comisión taker a 0.04%/lado. V24:
#   - Comisión taker 0.05%/lado (tarifa estándar de Binance Futures sin
#     descuento VIP/BNB — conservador).
#   - Slippage 0.05%/lado: todas las órdenes son MARKET (entrada, SL, TP,
#     cierres tácticos); rellenar al precio exacto del stop es ficción,
#     especialmente en velas rápidas. Modelado como costo proporcional al
#     precio en ambas puntas, sin perturbar la geometría SL/TP del trade.
#   - Funding 0.01%/8h (baseline típico de perpetuos): LONG paga, SHORT
#     recibe, cobrado por cada marca de funding (00/08/16 UTC) cruzada con
#     la posición abierta. Aproximación de tasa constante — el funding real
#     varía, pero ignorarlo por completo (V22) sesga al alza toda posición
#     mantenida horas/días con ~2x de nocional agregado.
TAKER_FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0005
FUNDING_RATE_8H = 0.0001

# Velas de calentamiento antes de evaluar señales (indicadores largos: MA_99,
# REGIME_LOOKBACK=100). Mismo valor que usaba el loop de V22 (range(200, ...)).
WARMUP_CANDLES = 200

# Estado Global Multihilo
data_lock = threading.Lock()
df_global = {sym: pd.DataFrame() for sym in PORTFOLIO.keys()}
is_ready = False
loop = None

# Estado de Simulación y Trazabilidad Global
sim_state = {
    'initial_balance': 500.0,
    'balance': 500.0,
    'trades': []
}


def costo_transaccion(qty, precio_entrada, precio_salida):
    """Comisión taker + slippage, aplicados a ambas puntas del tramo cerrado."""
    tasa = TAKER_FEE_RATE + SLIPPAGE_RATE
    return (qty * precio_entrada * tasa) + (qty * precio_salida * tasa)


def _naive_utc(ts):
    """Normaliza un timestamp a UTC naive (los klines de Binance llegan naive-UTC)."""
    if ts is None:
        return ts
    try:
        if getattr(ts, 'tzinfo', None) is not None:
            return ts.tz_convert('UTC').tz_localize(None)
    except Exception:
        pass
    return ts


_EPOCH = pd.Timestamp('1970-01-01')


def _eventos_funding(t_in, t_out):
    """Número de marcas de funding (00:00/08:00/16:00 UTC) en el intervalo (t_in, t_out]."""
    try:
        t_in = _naive_utc(pd.Timestamp(t_in))
        t_out = _naive_utc(pd.Timestamp(t_out))
        if t_out <= t_in:
            return 0
        horas_in = int((t_in - _EPOCH) // pd.Timedelta(hours=1))
        primera_marca = _EPOCH + pd.Timedelta(hours=(horas_in - horas_in % 8) + 8)
        if primera_marca > t_out:
            return 0
        return int((t_out - primera_marca) // pd.Timedelta(hours=8)) + 1
    except Exception:
        return 0


def cerrar_tramo(t, qty, exit_price, exit_time):
    """
    PnL NETO de un tramo cerrado (parcial, runner o cierre total):
    bruto − comisiones − slippage − funding acumulado desde la entrada.
    Único punto de cálculo de PnL de cierre — backtest y vivo usan exactamente
    el mismo código (en V22 había 7 sitios de cierre duplicando la fórmula).
    """
    if t['type'] == 'LONG':
        gross = (exit_price - t['entry_price']) * qty
    else:
        gross = (t['entry_price'] - exit_price) * qty

    funding = _eventos_funding(t.get('entry_time'), exit_time) * FUNDING_RATE_8H * qty * t['entry_price']
    if t['type'] == 'LONG':
        gross -= funding
    else:
        gross += funding

    return gross - costo_transaccion(qty, t['entry_price'], exit_price)


def _calc_reversal_prob(price, ma99, macd_hist, trade_type):
    """
    Probabilidad heurística de reversión (distancia a MA99 + signo del MACD_Hist).
    V24: recibe los valores CAUSALES de la vela actual desde el llamador — en
    V22 leía df_global[symbol].iloc[-1], que durante el backtest era la ÚLTIMA
    vela de toda la ventana (look-ahead), y la variable podía usarse sin asignar
    (UnboundLocalError latente en el auto-cierre de Puerta C).
    """
    if ma99 is None or pd.isna(ma99) or ma99 == 0:
        return 50.0
    dist = abs(price - ma99) / ma99 * 100
    prob = 20.0 + min(dist * 5, 40.0)
    mh = macd_hist if (macd_hist is not None and not pd.isna(macd_hist)) else 0.0
    if trade_type == 'LONG' and mh < 0:
        prob += 20.0
    if trade_type == 'SHORT' and mh > 0:
        prob += 20.0
    return min(prob, 99.0)


def contar_posiciones_por_direccion(direction):
    """Cuenta posiciones abiertas (ABIERTA o RUNNER) en una dirección dada, en TODO el portafolio."""
    return sum(1 for tr in sim_state['trades'] if tr['type'] == direction and tr['status'] in ('ABIERTA', 'RUNNER'))


# =========================================================================
# DESCUBRIMIENTO DE PRECISIONES Y LOTES MÍNIMOS DE BINANCE
# =========================================================================
def fetch_exchange_precision():
    global ASSET_RULES
    # Usamos la Testnet (demo-fapi) porque es ahí donde estás enviando las órdenes
    url = "https://demo-fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()

        for symbol_data in data['symbols']:
            sym = symbol_data['symbol']
            if sym in PORTFOLIO:
                ASSET_RULES[sym] = {
                    'qty_dec': symbol_data['quantityPrecision'],
                    'price_dec': symbol_data['pricePrecision']
                }

        print("INFO: Reglas de precisión de Binance cargadas dinámicamente:")
        for k, v in ASSET_RULES.items():
            print(f"      {k} -> Qty: {v['qty_dec']} decimales | Precio: {v['price_dec']} decimales")

    except Exception as e:
        print(f"ERROR CRÍTICO: No se pudo obtener la información de exchangeInfo: {e}")

# =========================================================================
# MOTOR CUANTITATIVO, GESTIÓN DE RIESGO Y RED
# =========================================================================
def initialize_real_balance():
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return
    url = "https://demo-fapi.binance.com/fapi/v2/account"
    timestamp = int(time.time() * 1000)
    query_string = urlencode({'timestamp': timestamp})
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    try:
        res = requests.get(f"{url}?{query_string}&signature={signature}", headers=headers)
        if res.status_code == 200:
            data = res.json()
            if 'availableBalance' in data:
                real_balance = float(data['availableBalance'])
                sim_state['initial_balance'] = real_balance
                sim_state['balance'] = real_balance
                print(f"INFO: Capital inicial ajustado desde Binance Testnet: ${real_balance:.2f}")
    except Exception as e:
        print(f"ERROR: No se pudo obtener el balance inicial de la API: {e}")

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

async def peticion_firmada_async(method, endpoint, params, version="v1"):
    url_base = f"https://demo-fapi.binance.com/fapi/{version}/{endpoint}"
    q = urlencode(params)
    sig = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), q.encode('utf-8'), hashlib.sha256).hexdigest()
    h = {'X-MBX-APIKEY': BINANCE_API_KEY}
    url_full = f"{url_base}?{q}&signature={sig}"

    if method == 'POST':
        return await asyncio.to_thread(requests.post, url_full, headers=h)
    elif method == 'GET':
        return await asyncio.to_thread(requests.get, url_full, headers=h)
    elif method == 'DELETE':
        return await asyncio.to_thread(requests.delete, url_full, headers=h)

async def sync_binance_balance():
    """
    Sincroniza el balance interno con el balance real de Binance Testnet
    cada 10 segundos, para que el motor de riesgo calcule la porción de lotaje
    usando la realidad y no el backtest virtual.
    """
    while True:
        if BINANCE_API_KEY and BINANCE_SECRET_KEY:
            try:
                params = {'timestamp': int(time.time() * 1000)}
                res = await peticion_firmada_async('GET', 'account', params, version='v2')
                if res.status_code == 200:
                    data = res.json()
                    if 'availableBalance' in data:
                        real_balance = float(data['availableBalance'])
                        if abs(sim_state['balance'] - real_balance) > 0.01:
                            print(f"SINC_BALANCE: Actualizando internal balance de {sim_state['balance']:.2f} a {real_balance:.2f} (Real Binance)", flush=True)
                            sim_state['balance'] = real_balance
            except Exception as e:
                pass
        await asyncio.sleep(10)

async def enviar_orden_binance(symbol, tipo_orden, qty, trade_id):
    """
    Motor de ejecución TAKER (MARKET). Entrada directa y agresiva al mercado.
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return

    qty_dec = ASSET_RULES.get(symbol, {}).get('qty_dec', 3)
    qty_fmt = round(qty, qty_dec)

    side = 'BUY' if tipo_orden == 'LONG' else 'SELL'

    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': qty_fmt,
        'timestamp': int(time.time() * 1000)
    }

    try:
        res = await peticion_firmada_async('POST', 'order', params)
        order_data = res.json()

        if 'orderId' not in order_data:
            print(f"ERROR API MARKET [{symbol}]: {order_data}", flush=True)
            for t in sim_state['trades']:
                if t['id'] == trade_id:
                    t['status'] = 'CANCELADA'
            return

        print(f"API MARKET [{symbol}]: ¡Orden de ENTRADA ejecutada con éxito! (Qty: {qty_fmt})", flush=True)

    except Exception as e:
        print(f"ERROR CRÍTICO: Fallo en orden MARKET ENTRADA para {symbol}: {e}", flush=True)

async def cerrar_orden_binance(symbol, tipo_orden, qty_estimado):
    """
    Ejecuta un MARKET order opuesto para cerrar la posición de forma programática.
    Consulta el amount exacto para evitar residuos decimales.
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return

    try:
        ts = int(time.time() * 1000)
        params_risk = {'timestamp': ts}
        res_risk = await peticion_firmada_async('GET', 'positionRisk', params_risk, version='v2')
        positions = res_risk.json()

        qty_real = 0.0
        for p in positions:
            if p['symbol'] == symbol:
                qty_real = abs(float(p['positionAmt']))
                break

        if qty_real == 0.0:
            print(f"API CIERRE [{symbol}]: Ya estaba cerrada en Binance (Qty=0).", flush=True)
            return

        qty_fmt = qty_real
    except Exception as e:
        print(f"ERROR obteniendo qty_real para cierre de {symbol}: {e}. Usando qty_estimado.", flush=True)
        qty_dec = ASSET_RULES.get(symbol, {}).get('qty_dec', 3)
        qty_fmt = round(qty_estimado, qty_dec)

    side = 'SELL' if tipo_orden == 'LONG' else 'BUY'

    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': qty_fmt,
        'reduceOnly': 'true',
        'timestamp': int(time.time() * 1000)
    }

    try:
        res = await peticion_firmada_async('POST', 'order', params)
        order_data = res.json()

        if 'orderId' not in order_data:
            print(f"ERROR API CIERRE [{symbol}]: {order_data}", flush=True)
            return

        print(f"API MARKET [{symbol}]: ¡Orden de CIERRE ejecutada con éxito! (Qty: {qty_fmt})", flush=True)

    except Exception as e:
        print(f"ERROR CRÍTICO: Fallo en orden MARKET CIERRE para {symbol}: {e}", flush=True)

def _notificar_cierre(t, symbol, etiqueta_pnl, alerta='ALERTA_CIERRE', post_mortem=True):
    """Print de alerta + orden de cierre en Binance + post-mortem (solo en vivo)."""
    if not is_ready:
        return
    if alerta == 'ALERTA_CIERRE_RUNNER':
        print(f"ALERTA_CIERRE_RUNNER|{t['type']}|{symbol}|{t['exit_price']:.4f}|{etiqueta_pnl:.4f}|Total PnL:{t['pnl']:.4f}|{t.get('puerta','?')}|{t.get('regimen_mercado','N/D')}", flush=True)
    else:
        print(f"ALERTA_CIERRE|{t['type']}|{symbol}|{t['exit_price']:.4f}|{t['pnl']:.4f}|{sim_state['balance']:.4f}|{t.get('puerta','?')}|{t.get('regimen_mercado','N/D')}", flush=True)
    try:
        asyncio.create_task(cerrar_orden_binance(symbol, t['type'], t['qty']))
    except RuntimeError:
        pass
    if post_mortem:
        df_post = df_global.get(symbol, pd.DataFrame())
        analisis_post_mortem_claude(symbol, t['type'], t, df_post.tail(3) if not df_post.empty else pd.DataFrame(), t['pnl'], t.get('exit_reason', '?'), t.get('id', '?'))


def evaluate_open_trades(candle, symbol, current_atr, ma99=None, macd_hist=None):
    """
    Evalúa salidas para los trades abiertos de `symbol` con la vela `candle`
    (en vivo: el snapshot acumulado de la vela en formación, tick a tick).

    V24 — ORDEN PESIMISTA (fix del look-ahead intravela de V22):
    Las salidas (SL / TP) se evalúan PRIMERO, contra los stops tal como
    quedaron al cierre de la vela anterior. Solo si el trade sigue abierto se
    arma el breakeven o se ratchetea el trailing usando los extremos de ESTA
    vela (efectivo desde la siguiente). En V22 el breakeven se armaba con el
    high de la misma vela ANTES de chequear el SL contra su low: en una vela
    OHLC el orden high/low es desconocido, y asumir siempre el orden favorable
    convertía pérdidas reales de -1R en salidas a ~$0 (sesgo optimista
    sistemático del mismo orden de magnitud que el PnL total del backtest).
    En vivo el código corre tick a tick, así que el armado intravela sigue
    ocurriendo de forma legítima (el high realmente ocurrió antes que el tick
    actual); el backtest queda del lado conservador.

    `candle` SIEMPRE incluye 'close' (V24): el auto-cierre de Puerta C — que en
    V22 jamás corría en backtest por el guard `'close' in candle` — ahora está
    cubierto por la regresión, unificando el comportamiento backtest/vivo.

    `ma99` / `macd_hist`: valores causales de la vela actual, provistos por el
    llamador para la probabilidad de reversión (V22 leía df_global.iloc[-1],
    que en backtest es la última vela de TODA la ventana — look-ahead).
    """
    global is_ready

    for t in sim_state['trades']:
        if t['symbol'] != symbol: continue

        if t['status'] == 'ABIERTA':
            risk_amount = abs(t['entry_price'] - t['sl'])

            # Tracking de máxima excursión (solo forense, no toca stops)
            if t['type'] == 'LONG':
                if 'highest_price' not in t: t['highest_price'] = t['entry_price']
                if candle['high'] > t['highest_price']: t['highest_price'] = candle['high']
                sl_hit = candle['low'] <= t['sl']
                tp_hit = candle['high'] >= t['tp']
            else:
                if 'lowest_price' not in t: t['lowest_price'] = t['entry_price']
                if candle['low'] < t['lowest_price']: t['lowest_price'] = candle['low']
                sl_hit = candle['high'] >= t['sl']
                tp_hit = candle['low'] <= t['tp']

            # --- 1) SALIDAS (stops de la vela anterior; si SL y TP caen en la
            # misma vela gana el SL — conservador, igual que V22) ---
            if sl_hit:
                t['status'] = 'CERRADA'
                t['exit_time'] = candle['time']
                t['exit_price'] = t['sl']
                t['exit_reason'] = 'STOP LOSS (Riesgo Asumido)'
                t['pnl'] = cerrar_tramo(t, t['qty'], t['exit_price'], candle['time'])
                sim_state['balance'] += t['pnl']
                _notificar_cierre(t, symbol, t['pnl'])
                continue

            if tp_hit:
                # 50% al TP + RUNNER con stop en breakeven. Aplica igual a las
                # tres puertas. (El bloque "activación anticipada a 0.5R" para
                # B/C de V22 era código muerto: vivía dentro del elif high>=tp,
                # donde high >= tp > half_r siempre — eliminado.)
                puerta = t.get('puerta', 'A')
                t['status'] = 'RUNNER'
                qty_cerrada = t['qty'] * 0.5
                partial_pnl = cerrar_tramo(t, qty_cerrada, t['tp'], candle['time'])
                t['pnl'] += partial_pnl
                sim_state['balance'] += partial_pnl
                t['qty'] = qty_cerrada  # Queda 50%
                t['sl'] = t['entry_price']  # Breakeven
                if is_ready:
                    print(f"ALERTA_PARCIAL|{t['type']}|{symbol}|{t['tp']:.4f}|+{partial_pnl:.4f}|RUNNER ACTIVO|{puerta}|{t.get('regimen_mercado','N/D')}", flush=True)
                    try:
                        asyncio.create_task(cerrar_orden_binance(symbol, t['type'], t['qty']))
                    except RuntimeError: pass
                continue

            # --- 2) TRADE SIGUE ABIERTO: progreso, auto-cierre C ---
            if risk_amount > 0 and t['qty'] > 0:
                if t['type'] == 'LONG':
                    current_pnl = (candle['close'] - t['entry_price']) * t['qty']
                else:
                    current_pnl = (t['entry_price'] - candle['close']) * t['qty']

                progress_pct = (current_pnl / (risk_amount * t['qty'])) * 100
                decil = int(progress_pct // 10) * 10

                # AUTO-CIERRE PUERTA C: progreso revirtió desde el pico + prob.
                # de reversión confirmada dos ticks/velas consecutivas.
                if t.get('puerta') == 'C' and t.get('last_reported_decil', 0) >= 30:
                    peak = t['last_reported_decil']
                    rev_prob_now = _calc_reversal_prob(candle['close'], ma99, macd_hist, t['type'])
                    if progress_pct < peak - 8 and rev_prob_now >= 42:
                        t['reversal_ticks'] = t.get('reversal_ticks', 0) + 1
                    else:
                        t['reversal_ticks'] = 0
                    if t.get('reversal_ticks', 0) >= 2:
                        t['status'] = 'CERRADA'
                        t['exit_time'] = candle['time']
                        t['exit_price'] = candle['close']
                        t['exit_reason'] = 'AUTO-CIERRE REVERSIÓN PUERTA C'
                        t['pnl'] = cerrar_tramo(t, t['qty'], t['exit_price'], candle['time'])
                        sim_state['balance'] += t['pnl']
                        _notificar_cierre(t, symbol, t['pnl'])
                        continue

                if decil >= 10 and decil > t.get('last_reported_decil', 0):
                    t['last_reported_decil'] = decil
                    reversal_prob = _calc_reversal_prob(candle['close'], ma99, macd_hist, t['type'])
                    if is_ready:
                        regimen = t.get('regimen_mercado', 'N/D')
                        puerta = t.get('puerta', '?')
                        print(f"ALERTA_PROGRESO|{t.get('id', '?')}|{symbol}|{decil}|{current_pnl:.4f}|{reversal_prob:.1f}|{puerta}|{regimen}", flush=True)

            # --- 3) BREAKEVEN A +1R (PUERTA A) — armado AL FINAL de la vela,
            # efectivo desde la siguiente (en vivo: desde el próximo tick) ---
            if t.get('puerta') == 'A' and not t.get('breakeven_armed') and risk_amount > 0:
                if t['type'] == 'LONG' and candle['high'] >= t['entry_price'] + risk_amount:
                    t['sl'] = t['entry_price']
                    t['breakeven_armed'] = True
                elif t['type'] == 'SHORT' and candle['low'] <= t['entry_price'] - risk_amount:
                    t['sl'] = t['entry_price']
                    t['breakeven_armed'] = True

        elif t['status'] == 'RUNNER':
            # V24: la salida se evalúa contra el trailing tal como quedó en la
            # vela ANTERIOR; el ratchet con el extremo de esta vela ocurre
            # después (efectivo desde la siguiente). En V22 el ratchet usaba el
            # high/low de la MISMA vela cuyo low/high luego testeaba el stop —
            # mismo look-ahead optimista que el breakeven.
            if t['type'] == 'LONG':
                if 'highest_price' not in t: t['highest_price'] = t['entry_price']
                if candle['high'] > t['highest_price']: t['highest_price'] = candle['high']

                if candle['low'] <= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'TRAILING STOP'
                    runner_pnl = cerrar_tramo(t, t['qty'], t['exit_price'], candle['time'])
                    t['pnl'] += runner_pnl
                    sim_state['balance'] += runner_pnl
                    _notificar_cierre(t, symbol, runner_pnl, alerta='ALERTA_CIERRE_RUNNER')
                else:
                    trailing_sl = t['highest_price'] - (t['tp'] - t['entry_price'])
                    if trailing_sl > t['sl']: t['sl'] = trailing_sl

            elif t['type'] == 'SHORT':
                if 'lowest_price' not in t: t['lowest_price'] = t['entry_price']
                if candle['low'] < t['lowest_price']: t['lowest_price'] = candle['low']

                if candle['high'] >= t['sl']:
                    t['status'] = 'CERRADA'
                    t['exit_time'] = candle['time']
                    t['exit_price'] = t['sl']
                    t['exit_reason'] = 'TRAILING STOP'
                    runner_pnl = cerrar_tramo(t, t['qty'], t['exit_price'], candle['time'])
                    t['pnl'] += runner_pnl
                    sim_state['balance'] += runner_pnl
                    _notificar_cierre(t, symbol, runner_pnl, alerta='ALERTA_CIERRE_RUNNER')
                else:
                    trailing_sl = t['lowest_price'] + (t['entry_price'] - t['tp'])
                    if trailing_sl < t['sl']: t['sl'] = trailing_sl

def _abrir_trade_backtest(sub_df, symbol, current_time):
    """
    Lógica de admisión de entradas del backtest — espejo exacto del camino en
    vivo (binance_ws_thread), salvo prints/órdenes reales.

    V24: riesgo PLANO (config['risk']). V22 subía el riesgo a 1.5x tras un
    trade ganador del mismo símbolo — una anti-martingala no documentada que
    convertía cada flip ganador/perdedor en un re-dimensionado del 50% del
    trade siguiente, amplificando la dependencia de trayectoria del backtest
    y contaminando cada comparación A/B (parte del "efecto cascada" de V22).
    Si se quiere recuperar, debe probarse como hipótesis explícita y separada.
    """
    config = PORTFOLIO[symbol]
    if any(t['status'] == 'ABIERTA' and t['symbol'] == symbol for t in sim_state['trades']):
        return

    signal, trade_data = compute_signals_and_trades(sub_df, sim_state['balance'], config['risk'])
    if not (signal and trade_data):
        return

    # Límite de exposición correlacionada — con el reloj global (ver
    # run_backtest_interleaved) este tope POR FIN ata en backtest igual que en vivo.
    if contar_posiciones_por_direccion(signal) >= MAX_SAME_DIRECTION_POSITIONS:
        return

    week_ago = current_time - pd.Timedelta(days=7)
    recent_losses = sum(1 for tr in sim_state['trades'] if tr['symbol'] == symbol and tr['status'] == 'CERRADA' and tr['pnl'] < 0 and tr['exit_time'] is not None and tr['exit_time'] >= week_ago)

    if recent_losses < 3 and sim_state['balance'] >= 5.0:
        w_trend = trade_data.get('metrics', {}).get('trend_w', 0)
        w_mr = trade_data.get('metrics', {}).get('mr_w', 0)
        regimen_dominante = 'MR' if w_mr > w_trend else 'TREND'

        sim_state['trades'].append({
            'id': str(uuid.uuid4())[:8],
            'symbol': symbol,
            'type': signal,
            'puerta': trade_data.get('puerta', 'A'),
            'status': 'ABIERTA',
            'regimen': regimen_dominante,
            'regimen_mercado': trade_data.get('regimen', 'N/D'),
            'entry_time': current_time,
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


def run_backtest_interleaved(dfs):
    """
    V24 — BACKTEST DE RELOJ GLOBAL (entrelazado por timestamp).

    V22 procesaba cada símbolo COMPLETO en secuencia (las 3000 velas de ETH,
    luego las de SOL, ...) compartiendo sim_state['balance']. Consecuencias:
      1. El balance "viajaba en el tiempo": los trades de febrero del símbolo
         N se dimensionaban con el PnL de TODA la ventana de los símbolos
         anteriores — algo que el trading en vivo jamás puede reproducir.
      2. El orden de los símbolos en PORTFOLIO era un parámetro oculto.
      3. MAX_SAME_DIRECTION_POSITIONS casi nunca ataba (nunca había dos
         símbolos abiertos "a la vez"), así que el backtest NO simulaba la
         cartera real y no puede validar cambios de asignación de exposición.
      4. El "efecto cascada" documentado 8 veces en el libro de V22 era en
         gran parte artefacto de (1)+(3) más el multiplicador 1.5x.

    Aquí todos los símbolos avanzan juntos sobre una línea de tiempo única:
    en cada timestamp se evalúan primero las SALIDAS de todos los símbolos y
    después las ENTRADAS (orden fijo de PORTFOLIO para determinismo). El tope
    de exposición y el balance compartido se comportan como en vivo, y un
    asignador por calidad (V23) se vuelve backtesteable.
    """
    index_maps = {}
    all_times = set()
    for sym, df in dfs.items():
        index_maps[sym] = {ts: i for i, ts in enumerate(df['time'])}
        if len(df) > WARMUP_CANDLES:
            all_times.update(df['time'].iloc[WARMUP_CANDLES:])

    symbols = [s for s in PORTFOLIO.keys() if s in dfs]

    for ts in sorted(all_times):
        # 1) Salidas de todos los símbolos en este timestamp
        for sym in symbols:
            df = dfs[sym]
            i = index_maps[sym].get(ts)
            if i is None or i < WARMUP_CANDLES:
                continue
            row = df.iloc[i]
            candle = {'time': ts, 'open': row['open'], 'high': row['high'],
                      'low': row['low'], 'close': row['close']}
            evaluate_open_trades(
                candle, sym,
                row['ATR'] if 'ATR' in df.columns else 0.0,
                ma99=row['MA_99'] if 'MA_99' in df.columns else None,
                macd_hist=row['MACD_Hist'] if 'MACD_Hist' in df.columns else None,
            )

        # 2) Cierre táctico por agotamiento + entradas, al cierre de cada vela.
        # V24: el cierre por AGOTAMIENTO ESTRUCTURAL existía SOLO en el camino
        # en vivo (binance_ws_thread) — el backtest nunca lo simulaba, otra
        # divergencia backtest/vivo de V22. Aquí se replica idéntico.
        for sym in symbols:
            df = dfs[sym]
            i = index_maps[sym].get(ts)
            if i is None or i < WARMUP_CANDLES:
                continue
            if not df.at[i, 'is_closed']:
                continue
            sub_df = df.iloc[:i+1]

            cerro_por_agotamiento = False
            for t in sim_state['trades']:
                if t['symbol'] == sym and t['status'] == 'ABIERTA':
                    if check_multi_candle_exhaustion(sub_df, t['type']):
                        t['status'] = 'CERRADA'
                        t['exit_time'] = ts
                        t['exit_price'] = df.at[i, 'close']
                        t['exit_reason'] = 'AGOTAMIENTO ESTRUCTURAL (V24)'
                        t['pnl'] = t.get('pnl', 0.0) + cerrar_tramo(t, t['qty'], t['exit_price'], ts)
                        sim_state['balance'] += t['pnl']
                        cerro_por_agotamiento = True
                    break

            # Igual que en vivo: si en esta vela hubo cierre táctico, no se
            # abre una entrada nueva en el mismo símbolo hasta la siguiente.
            if not cerro_por_agotamiento:
                _abrir_trade_backtest(sub_df, sym, ts)

    for sym in symbols:
        _auditoria_forense(sym)


def _auditoria_forense(symbol):
    # --- AUDITORÍA FORENSE DE TRADES (incluye régimen y puerta para análisis posterior) ---
    print(f"\n=== AUDITORÍA FORENSE DE TRADES [{symbol}] ===")
    for t in sim_state['trades']:
        if t['symbol'] == symbol and t['status'] == 'CERRADA':
            resultado = "GANADOR" if t['pnl'] > 0 else "PERDEDOR"
            m = t.get('metrics', {})

            if t['type'] == 'LONG':
                max_reach = t.get('highest_price', t['entry_price'])
                dist_reach_usd = max_reach - t['entry_price']
                dist_tp_faltante = t['tp'] - max_reach if t['tp'] > max_reach else 0
            else:
                max_reach = t.get('lowest_price', t['entry_price'])
                dist_reach_usd = t['entry_price'] - max_reach
                dist_tp_faltante = max_reach - t['tp'] if max_reach > t['tp'] else 0

            dist_reach_pct = (dist_reach_usd / t['entry_price']) * 100 if t['entry_price'] > 0 else 0

            print(f"[{t['type']}] {resultado}: ${t['pnl']:.2f}  |  Puerta: {t.get('puerta','?')}  |  Régimen: {t.get('regimen_mercado','N/D')}")
            print(f" ├─ Tiempos -> Entrada: {t['entry_time']} | Salida: {t.get('exit_time', 'N/A')}")
            print(f" ├─ Precios -> In: ${t['entry_price']} | Out: ${t['exit_price']:.2f} | Razón: {t.get('exit_reason', 'N/A')}")
            print(f" ├─ Recorrido-> Max Alcance: ${max_reach:.2f} (+{dist_reach_pct:.2f}%) | Faltó para TP: ${dist_tp_faltante:.2f}")
            print(f" ├─ Convicción: {t.get('conviccion', 0.0)}%")
            print(f" └─ Desglose -> Tendencia: {m.get('trend_w', 0)}% | MR: {m.get('mr_w', 0)}%")
    print("===============================================\n")

def _fetch_klines_paginated(symbol, total_candles, fixed_end_time=None):
    """
    Descarga hasta `total_candles` velas para `symbol`, paginando hacia atrás
    con `endTime` ya que Binance limita cada request a 1000 velas (limit=1000).

    Si `fixed_end_time` se especifica (epoch ms), la ventana termina ahí en
    lugar de "ahora" — usado para el backtest de regresión de ventana fija.
    """
    all_data = []
    end_time = fixed_end_time
    while len(all_data) < total_candles:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={INTERVAL}&limit=1000"
        if end_time:
            url += f"&endTime={end_time}"
        res = requests.get(url)
        res.raise_for_status()
        batch = res.json()

        if isinstance(batch, dict) and 'code' in batch:
            raise RuntimeError(f"Binance API error {symbol}: {batch.get('msg', batch)}")
        if not batch:
            break

        all_data = batch + all_data
        end_time = batch[0][0] - 1  # open time de la vela más antigua - 1ms
        if len(batch) < 1000:
            break
        time.sleep(0.2)

    return all_data[-total_candles:]


def _build_df_from_klines(data):
    columns = ['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tb', 'tq', 'ignore']
    df = pd.DataFrame(data, columns=columns)
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
    df['is_closed'] = True
    return df


def _emitir_resumen_backtest(tag, dfs=None):
    """
    Genera el reporte cuantitativo + desglose por puerta/régimen y emite
    `<tag>|<json>` para que mesa_de_dinero.py (tag=ALERTA_BACKTEST_RESUMEN) o
    log_backtest.py (tag=ALERTA_BACKTEST_RESUMEN_FIXED) lo consuman.

    V24: si se pasan los dataframes de la ventana, el resumen incluye además
    `benchmark_buy_hold_pct` (retorno promedio de comprar-y-mantener los
    símbolos del portafolio en la misma ventana — si la estrategia no supera
    esto, lo que hay es beta del mercado, no edge) y `window_start`/
    `window_end` (para hacer visible el solapamiento entre ventanas).
    """
    try:
        todos_los_trades_globales = sim_state.get('trades', [])
        capital_base = sim_state.get('initial_balance', 500.0)

        reporte_tv = generar_reporte_cuantitativo(todos_los_trades_globales, capital_inicial=capital_base)
        print(reporte_tv)

        # --- NUEVO V22: desglose forense por puerta y por régimen ---
        # Esta es la pieza de información que faltaba para "determinar la mejor estrategia":
        # cuántas señales aporta cada sub-estrategia y qué régimen las originó.
        cerrados = [t for t in todos_los_trades_globales if t['status'] == 'CERRADA']
        if cerrados:
            print(f"=== DESGLOSE FORENSE POR PUERTA / RÉGIMEN (V22) [{tag}] ===")
            for clave, etiqueta in (('puerta', 'Puerta'), ('regimen_mercado', 'Régimen')):
                grupos = {}
                for t in cerrados:
                    k = t.get(clave, 'N/D')
                    grupos.setdefault(k, []).append(t)
                for k, lst in sorted(grupos.items()):
                    wins = sum(1 for t in lst if t['pnl'] > 0)
                    pnl_total = sum(t['pnl'] for t in lst)
                    wr = (wins / len(lst) * 100) if lst else 0.0
                    print(f"  {etiqueta} {k}: {len(lst)} trades | Win Rate {wr:.1f}% | PnL acumulado ${pnl_total:,.2f}")
            print("====================================================")

            # --- NUEVO: resumen estructurado del backtest, para reenviar a Telegram ---
            # mesa_de_dinero.py escucha la línea ALERTA_BACKTEST_RESUMEN|<json> y la
            # traduce en un mensaje legible apenas termina el backtest histórico.
            # ALERTA_BACKTEST_RESUMEN_FIXED|<json> (ventana fija) es solo para
            # log_backtest.py / backtest_history.csv, no genera mensaje de Telegram.
            try:
                pnls = [t['pnl'] for t in cerrados]
                ganadores = [p for p in pnls if p > 0]
                perdedores = [p for p in pnls if p <= 0]
                beneficio_bruto = sum(ganadores)
                perdida_bruta = abs(sum(perdedores))
                net_pnl = beneficio_bruto - perdida_bruta
                wr_total = (len(ganadores) / len(pnls) * 100) if pnls else 0.0
                pf = (beneficio_bruto / perdida_bruta) if perdida_bruta > 0 else None

                desglose_puerta, desglose_regimen = {}, {}
                for clave, destino in (('puerta', desglose_puerta), ('regimen_mercado', desglose_regimen)):
                    grupos2 = {}
                    for t in cerrados:
                        k = t.get(clave, 'N/D')
                        grupos2.setdefault(k, []).append(t)
                    for k, lst in grupos2.items():
                        w = sum(1 for t in lst if t['pnl'] > 0)
                        destino[k] = {
                            'trades': len(lst),
                            'win_rate': round((w / len(lst) * 100), 1) if lst else 0.0,
                            'pnl': round(sum(t['pnl'] for t in lst), 2),
                        }

                # --- V24: benchmark buy & hold + metadatos de ventana ---
                benchmark_bh = None
                window_start, window_end = None, None
                if dfs:
                    rets = []
                    starts, ends = [], []
                    for _sym, _df in dfs.items():
                        if _df is not None and len(_df) > WARMUP_CANDLES:
                            p0 = _df['close'].iloc[WARMUP_CANDLES]
                            p1 = _df['close'].iloc[-1]
                            if p0:
                                rets.append((p1 / p0 - 1) * 100)
                            starts.append(_df['time'].iloc[WARMUP_CANDLES])
                            ends.append(_df['time'].iloc[-1])
                    if rets:
                        benchmark_bh = round(sum(rets) / len(rets), 2)
                    if starts and ends:
                        window_start = str(min(starts))
                        window_end = str(max(ends))

                resumen = {
                    'capital_inicial': round(capital_base, 2),
                    'capital_final': round(capital_base + net_pnl, 2),
                    'net_pnl_usd': round(net_pnl, 2),
                    'net_pnl_pct': round((net_pnl / capital_base * 100), 2) if capital_base else 0.0,
                    'trades': len(cerrados),
                    'win_rate': round(wr_total, 2),
                    'profit_factor': (round(pf, 3) if pf is not None else None),
                    'benchmark_buy_hold_pct': benchmark_bh,
                    'window_start': window_start,
                    'window_end': window_end,
                    'por_puerta': desglose_puerta,
                    'por_regimen': desglose_regimen,
                }
                print(f"{tag}|{json.dumps(resumen, ensure_ascii=False)}", flush=True)
            except Exception as e:
                print(f"⚠️ AVISO TELEMETRÍA: Error al generar resumen estructurado [{tag}]: {e}")

    except Exception as e:
        print(f"⚠️ AVISO TELEMETRÍA: Error al generar el reporte [{tag}]: {e}")


def fetch_history():
    global df_global, is_ready

    # --- FASE 1: BACKTEST DE REGRESIÓN (ventana fija, aislado) ---
    # Corre sobre una copia descartable de sim_state para que sus trades
    # "ABIERTA" de fecha fija (potencialmente muy lejos del precio actual) no
    # contaminen el estado de trading en vivo. Solo deja como rastro el
    # ALERTA_BACKTEST_RESUMEN_FIXED para backtest_history.csv.
    estado_real = copy.deepcopy(sim_state)
    sim_state['trades'] = []
    sim_state['balance'] = sim_state['initial_balance']

    dfs_fijos = {}
    for symbol in PORTFOLIO.keys():
        print(f"INFO: Descargando ventana fija para {symbol} {INTERVAL} ({BACKTEST_CANDLES} velas)...")
        try:
            data = _fetch_klines_paginated(symbol, BACKTEST_CANDLES, fixed_end_time=BACKTEST_FIXED_END_TIME_MS)
            dfs_fijos[symbol] = compute_indicators(_build_df_from_klines(data))
        except Exception as e:
            print(f"CRITICAL ERROR: Fallo descargando ventana fija {symbol}: {e}")

    run_backtest_interleaved(dfs_fijos)
    _emitir_resumen_backtest('ALERTA_BACKTEST_RESUMEN_FIXED', dfs_fijos)

    # Restaura el estado real antes de iniciar el backtest en vivo
    sim_state['trades'] = estado_real['trades']
    sim_state['balance'] = estado_real['balance']
    sim_state['initial_balance'] = estado_real['initial_balance']

    # --- FASE 2: BACKTEST "RECIENTE" (ventana "ahora - N velas") ---
    # Alimenta df_global y el estado de trading en vivo, como en V22.
    #
    # ADVERTENCIA DE HONESTIDAD (V24): esta ventana NO es out-of-sample
    # respecto a la fija. Ambas tienen BACKTEST_CANDLES velas y sus extremos
    # difieren en horas/días — comparten ~99% de los datos. Cualquier
    # divergencia entre ambas mide sensibilidad al desplazamiento de ventana
    # (dependencia de trayectoria), NO generalización. La única validación
    # honesta es forward (datos posteriores al freeze del código) o una
    # ventana de holdout disjunta jamás usada para seleccionar filtros.
    dfs_vivos = {}
    for symbol in PORTFOLIO.keys():
        print(f"INFO: Sincronizando datos históricos para {symbol} {INTERVAL} ({BACKTEST_CANDLES} velas)...")
        try:
            data = _fetch_klines_paginated(symbol, BACKTEST_CANDLES)
            df = compute_indicators(_build_df_from_klines(data))
            dfs_vivos[symbol] = df
            with data_lock:
                df_global[symbol] = df
        except Exception as e:
            print(f"CRITICAL ERROR: Fallo en extracción REST histórica {symbol}: {e}")

    run_backtest_interleaved(dfs_vivos)

    with data_lock:
        is_ready = True
    print("INFO: Caché histórico completado para todos los símbolos.")
    _emitir_resumen_backtest('ALERTA_BACKTEST_RESUMEN', dfs_vivos)

def binance_ws_thread():
    global loop
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
                    backoff = 1
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
                                    # V24: la vela completa (incl. close) + indicadores causales,
                                    # mismo contrato que usa el backtest — un solo code path.
                                    ma99_now = df_sym.iloc[-1]['MA_99'] if 'MA_99' in df_sym.columns else None
                                    macd_now = df_sym.iloc[-1]['MACD_Hist'] if 'MACD_Hist' in df_sym.columns else None
                                    evaluate_open_trades(
                                        {'time': candle_time, 'open': new_row['open'], 'high': new_row['high'],
                                         'low': new_row['low'], 'close': new_row['close']},
                                        symbol_event, current_atr, ma99=ma99_now, macd_hist=macd_now)
                                else:
                                    df_sym = pd.concat([df_sym, pd.DataFrame([new_row])], ignore_index=True)
                                    if len(df_sym) > MAX_CANDLES:
                                        df_sym = df_sym.iloc[-MAX_CANDLES:].reset_index(drop=True)

                                df_sym = compute_indicators(df_sym)
                                df_global[symbol_event] = df_sym

                                if is_candle_closed:
                                    ultima_vela = df_sym.iloc[-1]
                                    regimen_actual = classify_regime(df_sym)
                                    print(f"[{symbol_event}] Cierre: {ultima_vela['close']} | Régimen: {regimen_actual} | ADX: {ultima_vela.get('ADX', 0):.1f} | Vol: {ultima_vela['volume']}", flush=True)

                                    current_balance = sim_state['balance']
                                    config = PORTFOLIO[symbol_event]

                                    trade_abierto_sym = any(t['status'] == 'ABIERTA' and t['symbol'] == symbol_event for t in sim_state['trades'])

                                    if trade_abierto_sym:
                                        for t in sim_state['trades']:
                                            if t['symbol'] == symbol_event and t['status'] == 'ABIERTA':
                                                if check_multi_candle_exhaustion(df_sym, t['type']):
                                                    print(f"ALERTA_CIERRE_TACTICO|{t['type']}|{symbol_event}|Agotamiento detectado", flush=True)
                                                    t['status'] = 'CERRADA'
                                                    t['exit_time'] = candle_time
                                                    t['exit_price'] = ultima_vela['close']
                                                    t['exit_reason'] = 'AGOTAMIENTO ESTRUCTURAL (V22)'
                                                    t['pnl'] = t.get('pnl', 0.0) + cerrar_tramo(t, t['qty'], t['exit_price'], candle_time)
                                                    sim_state['balance'] += t['pnl']
                                                    try:
                                                        asyncio.create_task(cerrar_orden_binance(symbol_event, t['type'], t['qty']))
                                                    except RuntimeError: pass
                                                break

                                    if not trade_abierto_sym:
                                        # V24: riesgo PLANO. El multiplicador 1.5x post-ganador de
                                        # V22 (anti-martingala no documentada) se eliminó — ver
                                        # nota en _abrir_trade_backtest. Backtest y vivo idénticos.
                                        signal, trade_data = compute_signals_and_trades(
                                            df_sym, current_balance, config['risk']
                                        )

                                        if signal and trade_data:
                                            # --- V22: límite de exposición correlacionada (en vivo) ---
                                            if contar_posiciones_por_direccion(signal) >= MAX_SAME_DIRECTION_POSITIONS:
                                                print(f"FILTRO_CORRELACION|{symbol_event}|{signal}|Bloqueado: ya hay {contar_posiciones_por_direccion(signal)} posiciones {signal} abiertas (límite={MAX_SAME_DIRECTION_POSITIONS})", flush=True)
                                            else:
                                                week_ago = candle_time - pd.Timedelta(days=7)
                                                recent_losses = sum(1 for tr in sim_state['trades'] if tr['symbol'] == symbol_event and tr['status'] == 'CERRADA' and tr['pnl'] < 0 and tr['exit_time'] and tr['exit_time'] >= week_ago)

                                                if recent_losses < 3 and current_balance >= 5.0:
                                                    print(f"INFO: Solicitando validación de Claude Opus para trade {signal} en {symbol_event}...")
                                                    es_valido = True  # Validación síncrona eliminada — ahora es post-mortem (best-effort)

                                                    if es_valido:
                                                        c = trade_data['entry_price']
                                                        sl = trade_data['stop_loss']
                                                        tp = trade_data['take_profit']
                                                        qty = trade_data['qty']
                                                        puerta = trade_data.get('puerta', 'A')
                                                        regimen = trade_data.get('regimen', 'N/D')
                                                        patron_str = trade_data.get('pattern', f"{symbol_event} - V22")

                                                        if is_ready:
                                                            # --- V22: ALERTA_TRADE ahora incluye el RÉGIMEN detectado ---
                                                            # (campo añadido al final, compatible con el parser de mesa_de_dinero)
                                                            print(f"ALERTA_TRADE|{signal}|{patron_str}|{c}|{current_balance}|{puerta}|{regimen}", flush=True)

                                                        new_trade_id = str(uuid.uuid4())[:8]

                                                        sim_state['trades'].append({
                                                            'id': new_trade_id,
                                                            'symbol': symbol_event,
                                                            'type': signal,
                                                            'puerta': puerta,
                                                            'status': 'ABIERTA',
                                                            'regimen_mercado': regimen,
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

                                                        # --- FORENSE: registrar apertura con contexto completo (incluye régimen) ---
                                                        registrar_apertura(new_trade_id, symbol_event, signal, trade_data, df_sym)

                                                        if is_ready:
                                                            try:
                                                                asyncio.create_task(enviar_orden_binance(symbol_event, signal, qty, new_trade_id))
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

    loop.create_task(sync_binance_balance())
    loop.run_until_complete(ws_logic())

# =========================================================================
# INTERFAZ DE USUARIO REACTIVA (DASHBOARD MODERN UI/UX)
# =========================================================================
app = dash.Dash(__name__, title="Quant Terminal V24-Fable - Motor Honesto")

@app.server.route('/api/close_trade', methods=['POST'])
def api_close_trade():
    data = request.json
    if not data or 'symbol' not in data:
        return jsonify({'status': 'error', 'msg': 'symbol missing'}), 400

    symbol = data['symbol']

    try:
        r = requests.get(f'https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}', timeout=5)
        current_price = float(r.json()['price'])
    except:
        current_price = None

    closed = False
    for t in sim_state['trades']:
        # V24: el cierre manual también aplica a RUNNERs (en V22 un runner
        # activo no se podía cerrar por Telegram — quedaba vivo en Binance).
        if t['symbol'] == symbol and t['status'] in ('ABIERTA', 'RUNNER'):
            exit_ts = _naive_utc(pd.Timestamp.utcnow())
            t['status'] = 'CERRADA'
            t['exit_time'] = exit_ts

            if current_price:
                t['exit_price'] = current_price
                t['pnl'] = t.get('pnl', 0.0) + cerrar_tramo(t, t['qty'], current_price, exit_ts)
            else:
                t['exit_price'] = t['entry_price']
                t['pnl'] = t.get('pnl', 0.0) + cerrar_tramo(t, t['qty'], t['entry_price'], exit_ts)

            t['exit_reason'] = 'CIERRE MANUAL TELEGRAM'
            sim_state['balance'] += t['pnl']
            if is_ready:
                print(f"ALERTA_CIERRE|{t['type']}|{symbol}|{t['exit_price']:.4f}|{t['pnl']:.4f}|{sim_state['balance']:.4f}|{t.get('puerta','?')}|{t.get('regimen_mercado','N/D')}", flush=True)
                try:
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(cerrar_orden_binance(symbol, t['type'], t['qty']), loop)
                except Exception: pass
            closed = True
    return jsonify({'status': 'ok', 'closed': closed})


scorecard_style = {
    'backgroundColor': '#1a1a1a', 'padding': '15px', 'borderRadius': '8px',
    'textAlign': 'center', 'border': '1px solid #333', 'flex': '1', 'margin': '0 10px'
}
value_style = {'fontSize': '24px', 'fontWeight': 'bold', 'margin': '5px 0 0 0'}

app.layout = html.Div([
    html.H2("Terminal Cuantitativa Institucional V24-Fable - Motor de Backtest Honesto", style={'textAlign': 'center', 'color': '#00ffcc', 'fontFamily': 'monospace'}),

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
        empty_fig = go.Figure().update_layout(title="Iniciando escaneo multiplexado V24-Fable...", template='plotly_dark', paper_bgcolor='#0a0a0a', plot_bgcolor='#121212')
        return empty_fig, "0", "0", "0", "0", "$0.00", "0.00%", "0.00%", "$0.00", "Tiered: A/B 1% · C 0.4%", "$0.00"

    with data_lock:
        if selected_symbol not in df_global:
            selected_symbol = list(PORTFOLIO.keys())[0]
        df = df_global[selected_symbol].copy()
        trades = list(sim_state['trades'])
        balance = sim_state['balance']
        init_balance = sim_state['initial_balance']

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
    riesgo_str = "Tiered: A/B 1% · C 0.4%"

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

    if 'MA_7' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['MA_7'], mode='lines', name='MA 7', line=dict(color='#ff9900', width=1.5)))
    if 'EMA_9' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['EMA_9'], mode='lines', name='EMA 9', line=dict(color='#ff33cc', width=1.5)))
    if 'MA_99' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['MA_99'], mode='lines', name='MA 99 (Trend)', line=dict(color='#00bfff', width=2)))
    if 'Donchian_High' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['Donchian_High'], mode='lines', name='Resistencia (Donchian High)', line=dict(color='#ffffff', width=1, dash='dash')))
    if 'Donchian_Low' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['Donchian_Low'], mode='lines', name='Soporte (Donchian Low)', line=dict(color='#ffffff', width=1, dash='dash')))
    if 'BB_Upper' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['BB_Upper'], mode='lines', name='Bollinger Sup.', line=dict(color='#888888', width=1, dash='dot')))
    if 'BB_Lower' in df_view.columns:
        fig.add_trace(go.Scatter(x=df_view['time'], y=df_view['BB_Lower'], mode='lines', name='Bollinger Inf.', line=dict(color='#888888', width=1, dash='dot')))

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
    print("STATUS: Iniciando Motor Multiplexado V24-FABLE [BACKTEST RELOJ GLOBAL + COSTOS REALISTAS + INTRAVELA PESIMISTA]...")

    fetch_exchange_precision()
    initialize_real_balance()

    for sym in PORTFOLIO.keys():
        set_leverage(sym)

    fetch_history()

    t = threading.Thread(target=binance_ws_thread, daemon=True)
    t.start()

    print("Dash V24-Fable is running on http://127.0.0.1:8056/")
    app.run(port=8056, debug=False, use_reloader=False)
