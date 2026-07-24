"""
binance_client.py — TODA la comunicación y autorización con Binance.

- REST firmado (HMAC) contra testnet demo-fapi: órdenes, cuenta, leverage,
  precisión. Único módulo que toca las credenciales.
- Klines públicos (bootstrap + paginado histórico para el backtest).
- Stream WebSocket multiplexado de klines (datos en tiempo real, sin polling).

Ningún otro módulo construye URLs de Binance ni firma peticiones.
"""
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pandas as pd
import requests
import websockets

import config


def log(msg):
    print(f"[BINANCE] {msg}", flush=True)


class BinanceClient:
    """Encapsula credenciales + REST firmado (testnet) + datos públicos."""

    def __init__(self):
        self.api_key = config.BINANCE_API_KEY
        self.secret = config.BINANCE_SECRET_KEY
        self.asset_rules = {}

    @property
    def autenticado(self):
        return bool(self.api_key and self.secret)

    # ---------------- REST firmado (órdenes / cuenta) ----------------
    def _firmado(self, method, endpoint, params, version='v1'):
        url = f"{config.TESTNET_BASE}/fapi/{version}/{endpoint}"
        params = dict(params)
        params['timestamp'] = int(time.time() * 1000)
        q = urlencode(params)
        sig = hmac.new(self.secret.encode(), q.encode(), hashlib.sha256).hexdigest()
        headers = {'X-MBX-APIKEY': self.api_key}
        fn = {'GET': requests.get, 'POST': requests.post, 'DELETE': requests.delete}[method]
        return fn(f"{url}?{q}&signature={sig}", headers=headers, timeout=10)

    def cargar_precision(self):
        try:
            res = requests.get(f"{config.TESTNET_BASE}/fapi/v1/exchangeInfo", timeout=10)
            for s in res.json().get('symbols', []):
                if s['symbol'] in config.SYMBOLS:
                    tick = None
                    for f in s.get('filters', []):
                        if f.get('filterType') == 'PRICE_FILTER':
                            tick = float(f['tickSize'])
                    self.asset_rules[s['symbol']] = {'qty_dec': s['quantityPrecision'],
                                                     'tick': tick}
            log(f"precisión cargada para {len(self.asset_rules)} símbolos")
        except Exception as e:
            log(f"ERROR cargando exchangeInfo: {e}")

    def configurar_leverage(self):
        if not self.autenticado:
            return
        for sym in config.SYMBOLS:
            try:
                self._firmado('POST', 'leverage', {'symbol': sym, 'leverage': config.LEVERAGE})
            except Exception as e:
                log(f"WARN leverage {sym}: {e}")

    def obtener_balance(self):
        """Balance disponible en testnet, o None si falla."""
        if not self.autenticado:
            return None
        try:
            res = self._firmado('GET', 'account', {}, version='v2')
            if res.status_code == 200:
                data = res.json()
                if 'availableBalance' in data:
                    return float(data['availableBalance'])
        except Exception:
            pass
        return None

    def orden_market(self, symbol, side, qty, reduce_only=False):
        """Orden MARKET en testnet. side: 'BUY'/'SELL'. Retorna respuesta o None."""
        if not self.autenticado:
            return None
        qty_dec = self.asset_rules.get(symbol, {}).get('qty_dec', 3)
        params = {'symbol': symbol, 'side': side, 'type': 'MARKET',
                  'quantity': round(qty, qty_dec)}
        if reduce_only:
            params['reduceOnly'] = 'true'
        try:
            res = self._firmado('POST', 'order', params)
            data = res.json()
            if 'orderId' not in data:
                log(f"ERROR orden {symbol} {side}: {data}")
                return None
            return data
        except Exception as e:
            log(f"ERROR crítico orden {symbol}: {e}")
            return None

    def orden_limit_postonly(self, symbol, side, qty, price):
        """FASE 2 (V26): orden LIMIT post-only (GTX) — entra como maker o es
        rechazada por el exchange si cruzaría el book. Retorna dict o None."""
        if not self.autenticado:
            return None
        regla = self.asset_rules.get(symbol, {})
        tick = regla.get('tick')
        if tick:
            price = round(round(price / tick) * tick, 10)
        precio_str = f"{price:.10f}".rstrip('0').rstrip('.')
        params = {'symbol': symbol, 'side': side, 'type': 'LIMIT',
                  'timeInForce': 'GTX', 'price': precio_str,
                  'quantity': round(qty, regla.get('qty_dec', 3))}
        try:
            res = self._firmado('POST', 'order', params)
            data = res.json()
            if 'orderId' not in data:
                log(f"WARN post-only {symbol} {side} @ {precio_str}: {data}")
                return None
            return data
        except Exception as e:
            log(f"ERROR post-only {symbol}: {e}")
            return None

    def estado_orden(self, symbol, order_id):
        if not self.autenticado:
            return None
        try:
            return self._firmado('GET', 'order',
                                 {'symbol': symbol, 'orderId': order_id}).json()
        except Exception:
            return None

    def cancelar_orden(self, symbol, order_id):
        if not self.autenticado:
            return None
        try:
            return self._firmado('DELETE', 'order',
                                 {'symbol': symbol, 'orderId': order_id}).json()
        except Exception:
            return None

    # ---------------- Datos públicos (sin credenciales) ----------------
    @staticmethod
    def _df_de_klines(rows):
        df = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume',
                                         'ct', 'qav', 'n', 'tb', 'tq', 'ig'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        for col in ('open', 'high', 'low', 'close', 'volume'):
            df[col] = df[col].astype(float)
        return df[['time', 'open', 'high', 'low', 'close', 'volume']]

    def klines(self, symbol, limit=None):
        """Bootstrap: una petición de klines recientes (máx. 1000)."""
        limit = min(limit or config.BOOTSTRAP_CANDLES, 1000)
        url = f"{config.DATA_BASE}/fapi/v1/klines?symbol={symbol}&interval={config.INTERVAL}&limit={limit}"
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        return self._df_de_klines(res.json())

    def klines_paginated(self, symbol, total, end_time_ms=None):
        """Histórico paginado hacia atrás (para el backtest). Patrón de V22/V24."""
        all_rows = []
        end_time = end_time_ms
        while len(all_rows) < total:
            url = f"{config.DATA_BASE}/fapi/v1/klines?symbol={symbol}&interval={config.INTERVAL}&limit=1000"
            if end_time:
                url += f"&endTime={end_time}"
            res = requests.get(url, timeout=15)
            res.raise_for_status()
            batch = res.json()
            if isinstance(batch, dict) and 'code' in batch:
                raise RuntimeError(f"Binance API error {symbol}: {batch}")
            if not batch:
                break
            all_rows = batch + all_rows
            end_time = batch[0][0] - 1
            if len(batch) < 1000:
                break
            time.sleep(0.2)
        return self._df_de_klines(all_rows[-total:])


def stream_klines(on_kline, estado_ws):
    """
    Stream WebSocket multiplexado de klines para todos los SYMBOLS (bloqueante,
    pensado para correr en su propio hilo). `on_kline(k)` recibe cada payload
    de vela; `estado_ws` es un dict compartido {'ok': bool, 'desde': dt}.
    Reconexión con backoff exponencial.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def ws_logic():
        streams = '/'.join(f"{s.lower()}@kline_{config.INTERVAL}" for s in config.SYMBOLS)
        url = f"{config.WS_URL_BASE}/stream?streams={streams}"
        backoff = 1
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    estado_ws['ok'] = True
                    log(f"WS conectado: {len(config.SYMBOLS)} streams kline_{config.INTERVAL}")
                    backoff = 1
                    while True:
                        msg = json.loads(await ws.recv())
                        if 'data' in msg:
                            on_kline(msg['data']['k'])
            except Exception as e:
                estado_ws['ok'] = False
                log(f"WS desconectado ({e}). Reintento en {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    loop.run_until_complete(ws_logic())
