import asyncio
import time
import hmac
import hashlib
import os
import requests
from urllib.parse import urlencode

BINANCE_API_KEY = ""
BINANCE_SECRET_KEY = ""
with open('/Users/hackerunet/openclaw-binance-trading/.env', 'r') as f:
    for line in f:
        if line.startswith('BINANCE_API_KEY'):
            BINANCE_API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('BINANCE_SECRET_KEY'):
            BINANCE_SECRET_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")

async def peticion_firmada_async(method, endpoint, params, version="v1"):
    url_base = f"https://testnet.binancefuture.com/fapi/{version}/{endpoint}"
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

async def test_sync():
    params = {'timestamp': int(time.time() * 1000)}
    res = await peticion_firmada_async('GET', 'account', params, version='v2')
    print("STATUS", res.status_code)
    data = res.json()
    if 'availableBalance' in data:
        print("BALANCE:", data['availableBalance'])
    else:
        print("ERROR:", data)

asyncio.run(test_sync())
