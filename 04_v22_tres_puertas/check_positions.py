import requests
import time
import hmac
import hashlib
import os
from urllib.parse import urlencode

# Parse env file manually since dotenv might not be in the exact path
BINANCE_API_KEY = ""
BINANCE_SECRET_KEY = ""
with open('/Users/hackerunet/openclaw-binance-trading/.env', 'r') as f:
    for line in f:
        if line.startswith('BINANCE_API_KEY'):
            BINANCE_API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('BINANCE_SECRET_KEY'):
            BINANCE_SECRET_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")

def peticion_firmada(method, endpoint, params=None, version="v1"):
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
    elif method == 'POST':
        return requests.post(url, headers=headers, params=params)

try:
    if not BINANCE_API_KEY:
        print("No API Key found")
    else:
        res = peticion_firmada('GET', 'positionRisk', version='v2')
        data = res.json()
        open_positions = [p for p in data if float(p['positionAmt']) != 0.0]
        if open_positions:
            print("POSICIONES ABIERTAS EN BINANCE TESTNET:")
            for p in open_positions:
                print(f"- {p['symbol']}: {p['positionAmt']} @ {p['entryPrice']} (Unrealized PNL: {p['unRealizedProfit']})")
        else:
            print("NO HAY POSICIONES ABIERTAS EN BINANCE TESTNET.")
except Exception as e:
    print(f"Error: {e}")
