import pandas as pd
import numpy as np
import sys
import os

def max_drawdown(equity_series):
    peak = equity_series.expanding(min_periods=1).max()
    dd = (equity_series - peak) / peak
    return dd.min() * 100

def cagr(equity_series):
    days = (equity_series.index[-1] - equity_series.index[0]).days
    if days < 1: return 0
    ret = equity_series.iloc[-1] / equity_series.iloc[0]
    return (ret ** (365.25 / days) - 1) * 100

def backtest_pair(cache, sym_A, sym_B, window=120, z_entry=2.0, z_exit=0.0):
    df_A = cache[sym_A].copy()
    df_B = cache[sym_B].copy()
    
    df_A['time'] = pd.to_datetime(df_A['time'], unit='ms')
    df_B['time'] = pd.to_datetime(df_B['time'], unit='ms')
    df_A.set_index('time', inplace=True)
    df_B.set_index('time', inplace=True)
    
    # Precios de cierre en intervalos de 4h
    prices = pd.DataFrame({'A': df_A['close'], 'B': df_B['close']}).dropna()
    
    # Ratio A/B
    ratio = prices['A'] / prices['B']
    
    # Z-score móvil
    ma = ratio.rolling(window=window).mean()
    std = ratio.rolling(window=window).std()
    zscore = (ratio - ma) / std
    
    # Señales
    # +1 = Long Ratio (Comprar A, Vender B)
    # -1 = Short Ratio (Vender A, Comprar B)
    # 0 = Neutral
    
    position = pd.Series(0, index=prices.index)
    current_pos = 0
    
    for i in range(window, len(zscore)):
        z = zscore.iloc[i]
        
        if current_pos == 0:
            if z < -z_entry:
                current_pos = 1
            elif z > z_entry:
                current_pos = -1
        elif current_pos == 1:
            if z >= z_exit:
                current_pos = 0
        elif current_pos == -1:
            if z <= z_exit:
                current_pos = 0
                
        position.iloc[i] = current_pos
        
    # Retornos en t+1 para evitar lookahead
    # Si pos = 1 (Long Ratio): Gano si A sube más que B. (Retorno_A - Retorno_B)
    # En rigor, si asigno 50% capital a A y 50% capital a B:
    # Port_Ret = 0.5 * Retorno_A + (-0.5) * Retorno_B
    ret_A = prices['A'].pct_change().shift(-1).fillna(0)
    ret_B = prices['B'].pct_change().shift(-1).fillna(0)
    
    # Cuando position = 1: 0.5 * ret_A - 0.5 * ret_B
    # Cuando position = -1: -0.5 * ret_A + 0.5 * ret_B
    # Esto asume gross exposure = 1.0 (apalanque 1x)
    
    port_ret = position * (0.5 * ret_A - 0.5 * ret_B)
    
    # Costos de transacción (0.1% taker cada vez que cambiamos posición en CADA pata = 0.2% total)
    pos_diff = position.diff().abs().fillna(0)
    fee_cost = pos_diff * 0.002
    
    net_ret = port_ret - fee_cost
    
    capital = 1000.0
    equity = [capital]
    for r in net_ret.iloc[:-1]:
        capital = capital * (1 + r)
        equity.append(capital)
        
    eq_series = pd.Series(equity, index=prices.index)
    
    trades = (pos_diff > 0).sum() / 2  # Aproximadamente round-trips
    
    return eq_series, trades

def main():
    print("Iniciando Motor M2 - Pairs Trading (V47)...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} no encontrado.")
        return
        
    cache = pd.read_pickle(cache_path)
    
    pares = [('ETHUSDT', 'SOLUSDT'), ('ADAUSDT', 'XRPUSDT'), ('BNBUSDT', 'ETHUSDT')]
    
    for sym_A, sym_B in pares:
        print(f"\nEvaluando par: {sym_A} vs {sym_B}")
        # Usamos 120 velas 4h = 20 días para el rolling z-score
        eq_series, trades = backtest_pair(cache, sym_A, sym_B, window=120, z_entry=2.0, z_exit=0.0)
        
        c = cagr(eq_series)
        dd = max_drawdown(eq_series)
        
        print(f"Trades aprox: {int(trades)}")
        print(f"CAGR: {c:.2f}% | Max DD: {dd:.2f}% | Final Equity: ${eq_series.iloc[-1]:.2f}")

if __name__ == '__main__':
    main()
