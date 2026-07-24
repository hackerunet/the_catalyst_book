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

def main():
    print("Iniciando Motor M1 - Short-Term Reversal (V45)...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} no encontrado.")
        return
        
    cache = pd.read_pickle(cache_path)
    symbols = list(cache.keys())
    print(f"Símbolos en canasta: {symbols}")
    
    # 1. Alinear precios diarios de todos los símbolos
    df_close = {}
    for sym in symbols:
        df = cache[sym].copy()
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        # Remuestrear a diario
        d = df.resample('1D').agg({'close': 'last'}).dropna()
        df_close[sym] = d['close']
        
    # Crear un DataFrame único con los precios de cierre diarios
    prices = pd.DataFrame(df_close)
    prices.dropna(inplace=True)
    
    # Parámetros del modelo
    lookback = 7  # 7 días de retorno para calcular el Reversal
    top_k = 2     # Vender en corto los 2 más fuertes
    bottom_k = 2  # Comprar los 2 más débiles
    fee_rate = 0.001 # 0.1% taker fee en cada rebalanceo (Binance estandar)
    
    # 2. Calcular Momentum Cross-Sectional (Retorno % en el lookback)
    momentum = prices.pct_change(periods=lookback)
    
    capital = 1000.0
    equity_curve = []
    dates = []
    
    # Mantener registro de posiciones previas para calcular fees de rebalanceo
    # pos_weights[sym] = peso en la cartera (-0.25, 0, 0.25)
    prev_weights = pd.Series(0.0, index=symbols)
    
    # Retornos diarios de cada símbolo para el día t
    daily_returns = prices.pct_change().shift(-1) # Retorno del cierre t al cierre t+1
    
    for t in range(lookback, len(prices)-1):
        date = prices.index[t]
        mom_t = momentum.iloc[t]
        
        # Rankear por momentum
        ranks = mom_t.rank(ascending=False) # 1 es el más alto (mayor retorno)
        
        target_weights = pd.Series(0.0, index=symbols)
        
        # Short top k (los más fuertes)
        shorts = ranks[ranks <= top_k].index
        for sym in shorts:
            target_weights[sym] = -0.5 / top_k
            
        # Long bottom k (los más débiles)
        longs = ranks[ranks >= (len(symbols) - bottom_k + 1)].index
        for sym in longs:
            target_weights[sym] = 0.5 / bottom_k
            
        # Calcular turnover (cambio de pesos) para deducir fees
        turnover = (target_weights - prev_weights).abs().sum()
        fee_cost = turnover * fee_rate
        
        # Retorno del portafolio en este día (sin apalancamiento neto, gross exposure = 1.0)
        port_ret = (target_weights * daily_returns.iloc[t]).sum() - fee_cost
        
        capital = capital * (1 + port_ret)
        
        equity_curve.append(capital)
        dates.append(prices.index[t+1]) # El retorno se materializa en t+1
        
        prev_weights = target_weights.copy()
        
    eq_series = pd.Series(equity_curve, index=dates)
    
    c = cagr(eq_series)
    dd = max_drawdown(eq_series)
    win_rate = (eq_series.pct_change() > 0).mean() * 100
    
    print("\n--- Resultados V45: Short-Term Reversal ---")
    print(f"Período: {dates[0].date()} a {dates[-1].date()}")
    print(f"CAGR: {c:.2f}%")
    print(f"Max Drawdown: {dd:.2f}%")
    print(f"Días Positivos (Win Rate Diario): {win_rate:.1f}%")
    print(f"Equidad Final: ${capital:.2f}")

if __name__ == '__main__':
    main()
