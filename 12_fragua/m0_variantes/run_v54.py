import pandas as pd
import numpy as np
import os
import sys

def calculate_supertrend(df, period=10, multiplier=3):
    # Calcular ATR
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    hl2 = (high + low) / 2
    
    final_upperband = hl2 + (multiplier * atr)
    final_lowerband = hl2 - (multiplier * atr)
    
    supertrend = pd.Series(0.0, index=df.index)
    in_uptrend = pd.Series(True, index=df.index)
    
    for i in range(1, len(df)):
        # Upperband
        if close.iloc[i-1] <= final_upperband.iloc[i-1]:
            final_upperband.iloc[i] = min(final_upperband.iloc[i], final_upperband.iloc[i-1])
        # Lowerband
        if close.iloc[i-1] >= final_lowerband.iloc[i-1]:
            final_lowerband.iloc[i] = max(final_lowerband.iloc[i], final_lowerband.iloc[i-1])
            
        # Determinar tendencia
        if close.iloc[i] > final_upperband.iloc[i-1]:
            in_uptrend.iloc[i] = True
        elif close.iloc[i] < final_lowerband.iloc[i-1]:
            in_uptrend.iloc[i] = False
        else:
            in_uptrend.iloc[i] = in_uptrend.iloc[i-1]
            
            # Mantener la banda estricta según tendencia
            if in_uptrend.iloc[i]:
                final_lowerband.iloc[i] = final_lowerband.iloc[i-1]
            else:
                final_upperband.iloc[i] = final_upperband.iloc[i-1]
                
        # Guardar valor
        if in_uptrend.iloc[i]:
            supertrend.iloc[i] = final_lowerband.iloc[i]
        else:
            supertrend.iloc[i] = final_upperband.iloc[i]
            
    return supertrend, in_uptrend

def max_drawdown(equity_series):
    peak = equity_series.expanding(min_periods=1).max()
    dd = (equity_series - peak) / peak
    return dd.min() * 100

def cagr(equity_series):
    days = (equity_series.index[-1] - equity_series.index[0]).days
    if days < 1: return 0
    ret = equity_series.iloc[-1] / equity_series.iloc[0]
    return (ret ** (365.25 / days) - 1) * 100

def main():
    print("Iniciando Motor M0 - Variante V54 (Supertrend)...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} no encontrado.")
        return
        
    cache = pd.read_pickle(cache_path)
    symbols = ['ETHUSDT'] # Probar proxy direccional primero
    
    for sym in symbols:
        df = cache[sym].copy()
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        
        print(f"Calculando Supertrend para {sym} (puede tardar un momento)...")
        # Parámetros estándar: 10, 3
        st, in_uptrend = calculate_supertrend(df, 10, 3)
        df['uptrend'] = in_uptrend
        
        # Comparación contra EMA 50/200 de V26
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['ema_uptrend'] = df['ema50'] > df['ema200']
        
        # Backtest rudimentario 1x direccional puro
        # Retorno de la siguiente vela
        ret = df['close'].pct_change().shift(-1).fillna(0)
        
        # V54: Posición LONG si Supertrend en Uptrend
        pos_st = df['uptrend'].shift(1).fillna(False).astype(int)
        
        # V26_Proxy: Posición LONG si EMA50 > EMA200
        pos_ema = df['ema_uptrend'].shift(1).fillna(False).astype(int)
        
        # Costos 0.1% por cada cambio de posición
        fee = 0.001
        
        # Supertrend Equity
        eq_st = [1000.0]
        cap = 1000.0
        pos_diff_st = pos_st.diff().abs().fillna(0)
        for i in range(len(ret)-1):
            cap = cap * (1 + pos_st.iloc[i] * ret.iloc[i]) - (pos_diff_st.iloc[i] * cap * fee)
            eq_st.append(cap)
            
        # EMA Equity
        eq_ema = [1000.0]
        cap = 1000.0
        pos_diff_ema = pos_ema.diff().abs().fillna(0)
        for i in range(len(ret)-1):
            cap = cap * (1 + pos_ema.iloc[i] * ret.iloc[i]) - (pos_diff_ema.iloc[i] * cap * fee)
            eq_ema.append(cap)
            
        eq_series_st = pd.Series(eq_st, index=df.index)
        eq_series_ema = pd.Series(eq_ema, index=df.index)
        
        print(f"\n--- Resultados V54 (Supertrend) vs V26_Proxy (EMA50/200) para {sym} ---")
        print("Supertrend (10,3):")
        print(f"CAGR: {cagr(eq_series_st):.2f}% | Max DD: {max_drawdown(eq_series_st):.2f}%")
        print(f"Trades Aprox: {pos_diff_st.sum()}")
        
        print("\nEMA (50,200):")
        print(f"CAGR: {cagr(eq_series_ema):.2f}% | Max DD: {max_drawdown(eq_series_ema):.2f}%")
        print(f"Trades Aprox: {pos_diff_ema.sum()}")
        
        print("\nVeredicto local calculado.")

if __name__ == '__main__':
    main()
