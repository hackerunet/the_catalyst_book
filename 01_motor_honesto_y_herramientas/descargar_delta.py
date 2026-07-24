#!/usr/bin/env python3
"""S6 · paso de datos — re-descarga klines 4h MANTENIENDO el taker-buy volume (que
binance_client._df_de_klines parsea y descarta), alineado EXACTO a los timestamps de los
caches OHLCV existentes. Guarda un cache de delta aparte (no toca nada compartido).

delta por vela = taker_buy_base − taker_sell_base = 2·taker_buy − volume
  (>0 = compradores agresivos dominan; <0 = vendedores agresivos / absorción).

Salida: delta_cache_4h_orig.pkl y delta_cache_4h_oob.pkl → {symbol: DataFrame[time, volume, taker_buy, delta]}.
SOLO descarga pública (fapi.binance.com/klines), sin auth. No toca el motor ni los bots vivos.
"""
import pickle
import time

import numpy as np
import pandas as pd
import requests

BASE = 'https://fapi.binance.com'
CACHES = [
    ('wf_cache_4h_8760_2026-06-11_0000.pkl', 'delta_cache_4h_orig.pkl'),
    ('wf_cache_4h_8760_2026-06-11_0000_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl', 'delta_cache_4h_oob.pkl'),
]


def fetch_klines_delta(symbol, first_ms, last_ms):
    """Pagina hacia atrás desde last_ms hasta cubrir first_ms. Devuelve dict
    {openTime_ms: (volume, taker_buy_base)}."""
    out = {}
    end = last_ms + 1
    while True:
        r = requests.get(f"{BASE}/fapi/v1/klines",
                         params={'symbol': symbol, 'interval': '4h', 'limit': 1500, 'endTime': end},
                         timeout=20)
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            break
        for k in rows:
            ot = int(k[0])
            out[ot] = (float(k[5]), float(k[9]))   # volume, taker_buy_base
        earliest = int(rows[0][0])
        if earliest <= first_ms:
            break
        end = earliest - 1
        time.sleep(0.15)
    return out


def main():
    for cache_ohlcv, cache_delta in CACHES:
        d = pickle.load(open(cache_ohlcv, 'rb'))
        salida = {}
        print(f"\n=== {cache_ohlcv[:48]} ===")
        for sym, df in d.items():
            # ns -> ms robusto (el .view('int64') está roto en esta versión de pandas;
            # astype('datetime64[ms]') calza EXACTO con el openTime de Binance).
            ms = df['time'].values.astype('datetime64[ms]').astype('int64')
            first_ms, last_ms = int(ms.min()), int(ms.max())
            raw = fetch_klines_delta(sym, first_ms, last_ms)
            vol = np.array([raw.get(int(m), (np.nan, np.nan))[0] for m in ms])
            tbb = np.array([raw.get(int(m), (np.nan, np.nan))[1] for m in ms])
            delta = 2 * tbb - vol
            faltan = int(np.isnan(vol).sum())
            # sanity: el volumen bajado debe coincidir con el del cache OHLCV
            vol_cache = df['volume'].values.astype(float)
            difok = np.nanmax(np.abs(vol - vol_cache) / np.maximum(vol_cache, 1e-9))
            salida[sym] = pd.DataFrame({'time': df['time'].values, 'volume': vol,
                                        'taker_buy': tbb, 'delta': delta})
            print(f"  {sym:9} velas={len(ms)} faltan={faltan} "
                  f"vol_match(máx dif rel)={difok:.2e} "
                  f"delta_medio={np.nanmean(delta):+.0f}")
        pickle.dump(salida, open(cache_delta, 'wb'))
        print(f"  -> guardado {cache_delta}")


if __name__ == '__main__':
    main()
