import requests
import time
import hmac
import hashlib
import os
from urllib.parse import urlencode

# Extract API Keys
BINANCE_API_KEY = ""
BINANCE_SECRET_KEY = ""
with open('/Users/hackerunet/openclaw-binance-trading/.env', 'r') as f:
    for line in f:
        if line.startswith('BINANCE_API_KEY'):
            BINANCE_API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('BINANCE_SECRET_KEY'):
            BINANCE_SECRET_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")

def peticion_firmada(method, endpoint, params=None, version="v2"):
    if params is None:
        params = {}
    params['timestamp'] = int(time.time() * 1000)
    query_string = urlencode(params)
    signature = hmac.new(
        BINANCE_SECRET_KEY.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    params['signature'] = signature
    url = f"https://testnet.binancefuture.com/fapi/{version}/{endpoint}"
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    
    if method == 'GET':
        return requests.get(url, headers=headers, params=params)

try:
    res = peticion_firmada('GET', 'account')
    data = res.json()
    if 'totalWalletBalance' in data:
        print(f"BALANCE REAL EN BINANCE TESTNET: ${data['totalWalletBalance']} USDT")
        print(f"BALANCE DISPONIBLE PARA OPERAR: ${data['availableBalance']} USDT")
    else:
        print(f"Error fetching account data: {data}")
except Exception as e:
    print(f"Error: {e}")
