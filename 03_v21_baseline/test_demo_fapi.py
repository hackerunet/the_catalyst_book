import time, hmac, hashlib, os, requests
from urllib.parse import urlencode

BINANCE_API_KEY = ""
BINANCE_SECRET_KEY = ""
with open('/Users/hackerunet/openclaw-binance-trading/.env', 'r') as f:
    for line in f:
        if line.startswith('BINANCE_API_KEY'):
            BINANCE_API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
        elif line.startswith('BINANCE_SECRET_KEY'):
            BINANCE_SECRET_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")

def get_real_account():
    url = "https://demo-fapi.binance.com/fapi/v2/account"
    timestamp = int(time.time() * 1000)
    query_string = urlencode({'timestamp': timestamp})
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    res = requests.get(f"{url}?{query_string}&signature={signature}", headers=headers)
    print("STATUS", res.status_code)
    try:
        data = res.json()
        print("AVAILABLE BALANCE:", data.get('availableBalance'))
    except:
        print("TEXT", res.text)

get_real_account()
