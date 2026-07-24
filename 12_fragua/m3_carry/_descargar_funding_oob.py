"""Descarga UNA VEZ el historial de funding real de la canasta OOB desde la API pública de Binance
(sin autenticación, /fapi/v1/fundingRate). Se guarda en un cache PROPIO dentro de Fragua/ (aislamiento:
no se toca bot_alpha_portfolio/). Solo hace falta correrlo una vez; el resultado se versiona como .pkl.
"""
import pickle
import time
import requests
import pandas as pd

SYMBOLS = ['BTCUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']
END_MS = int(pd.Timestamp('2026-06-12').timestamp() * 1000)
START_MS = int(pd.Timestamp('2022-06-12').timestamp() * 1000)   # mismo rango que el cache de V27-B


def descargar_uno(symbol):
    out = []
    cursor = START_MS
    while cursor < END_MS:
        r = requests.get('https://fapi.binance.com/fapi/v1/fundingRate',
                          params={'symbol': symbol, 'startTime': cursor, 'limit': 1000}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        out.extend(data)
        last_t = data[-1]['fundingTime']
        if last_t <= cursor:
            break
        cursor = last_t + 1
        time.sleep(0.15)
    df = pd.DataFrame(out)
    df['time'] = pd.to_datetime(df['fundingTime'], unit='ms')
    df['rate'] = df['fundingRate'].astype(float)
    return df[['time', 'rate']].drop_duplicates(subset='time').reset_index(drop=True)


if __name__ == '__main__':
    cache = {}
    for sym in SYMBOLS:
        print(f"descargando funding real de {sym}...")
        cache[sym] = descargar_uno(sym)
        print(f"  {sym}: {len(cache[sym])} eventos, {cache[sym]['time'].min()} -> {cache[sym]['time'].max()}")
    with open('funding_cache_oob.pkl', 'wb') as f:
        pickle.dump(cache, f)
    print("Guardado: funding_cache_oob.pkl")
