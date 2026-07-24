#!/usr/bin/env python3
"""Fase 2 — descarga OHLCV DIARIO de cripto/forex/commodities (yfinance) y lo
guarda en el formato del motor honesto (dict symbol→df con time[ms],ohlcv) para
que brute_force.py corra el mismo motor cross-asset. Timeframe 1D (historia larga,
comparación limpia entre clases). Forex no trae volumen → constante neutra."""
import os, pickle, time
import pandas as pd, numpy as np
import yfinance as yf

DIR = os.path.dirname(os.path.abspath(__file__))
PERIOD = '10y'

CLASES = {
 'crypto_1d':  ['BTC-USD','ETH-USD','SOL-USD','BNB-USD','XRP-USD','ADA-USD'],
 'forex_1d':   ['EURUSD=X','GBPUSD=X','USDJPY=X','AUDUSD=X','USDCAD=X','USDCHF=X'],
 'commod_1d':  ['GC=F','SI=F','CL=F','NG=F','HG=F','ZC=F'],
}

def fmt(ticker):
    for intento in range(3):
        try:
            d = yf.download(ticker, period=PERIOD, interval='1d', progress=False, auto_adjust=True)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300: return None
            out = pd.DataFrame({
                'time': pd.DatetimeIndex(d.index).astype('datetime64[ms]'),  # datetime, como los caches del motor
                'open': d['Open'].astype(float).values,
                'high': d['High'].astype(float).values,
                'low':  d['Low'].astype(float).values,
                'close':d['Close'].astype(float).values,
            })
            vol = d['Volume'].astype(float).values if 'Volume' in d else np.zeros(len(d))
            vol = np.where(np.nan_to_num(vol) > 0, vol, 1e6)  # forex/sin-volumen → neutro
            out['volume'] = vol
            return out.reset_index(drop=True)
        except Exception as e:
            time.sleep(2)
    return None

for tag, tickers in CLASES.items():
    cache = {}
    for t in tickers:
        df = fmt(t)
        sym = t.replace('-USD','USDT').replace('=X','').replace('=F','')  # nombre simple
        if df is not None:
            cache[sym] = df
            print(f"  {tag}: {sym:8} {len(df)} velas ({pd.to_datetime(df['time'].iloc[0],unit='ms').date()} → {pd.to_datetime(df['time'].iloc[-1],unit='ms').date()})", flush=True)
        else:
            print(f"  {tag}: {sym:8} FALLÓ", flush=True)
    path = os.path.join(DIR, f'wf_cache_{tag}.pkl')
    with open(path,'wb') as f: pickle.dump(cache, f)
    print(f"  -> guardado {tag}: {len(cache)} símbolos\n", flush=True)
print("DOWNLOAD_DONE")
