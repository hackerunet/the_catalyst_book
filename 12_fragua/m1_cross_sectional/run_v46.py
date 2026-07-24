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
    print("Iniciando Motor M1 - Carry Cross-Sectional (V46)...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
    fund_path = '../../bot_alpha_portfolio/v27b_carry/funding_cache.pkl'
    
    if not os.path.exists(cache_path) or not os.path.exists(fund_path):
        print("ERROR: Archivos de caché no encontrados.")
        return
        
    cache = pd.read_pickle(cache_path)
    fund_cache = pd.read_pickle(fund_path)
    
    symbols = ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']
    print(f"Símbolos en canasta: {symbols}")
    
    # 1. Preparar precios de cierre diarios
    df_close = {}
    for sym in symbols:
        df = cache[sym].copy()
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        d = df.resample('1D').agg({'close': 'last'}).dropna()
        df_close[sym] = d['close']
        
    prices = pd.DataFrame(df_close).dropna()
    
    # 2. Preparar tasas de funding diarias (suma de las 3 tasas de 8h del día)
    df_fund = {}
    for sym in symbols:
        df = fund_cache[sym].copy()
        # Asegurar datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        # Sumar funding rates del día
        f_daily = df.resample('1D').agg({'rate': 'sum'}).fillna(0)
        df_fund[sym] = f_daily['rate']
        
    funding = pd.DataFrame(df_fund)
    
    # Alinear fechas
    idx = prices.index.intersection(funding.index)
    prices = prices.loc[idx]
    funding = funding.loc[idx]
    
    # Parámetros del modelo
    top_k = 2     # Vender en corto los 2 con funding MÁS POSITIVO
    bottom_k = 2  # Comprar los 2 con funding MÁS NEGATIVO (o menos positivo)
    fee_rate = 0.001 # 0.1% taker fee en cada rebalanceo
    
    capital = 1000.0
    equity_curve = []
    dates = []
    
    prev_weights = pd.Series(0.0, index=symbols)
    daily_returns = prices.pct_change().shift(-1)
    
    # El funding t es lo cobrado en el día t. Al decidir al cierre de t, recibiremos el funding de t+1.
    funding_returns = funding.shift(-1)
    
    # Iteramos cada día
    for t in range(len(prices)-1):
        date = prices.index[t]
        
        # Usamos el funding rate de la ventana t para decidir el posicionamiento para t+1
        # Promedio movil de 3 días de funding para suavizar señales ruidosas de 1 día
        if t < 3:
            continue
        
        fund_signal = funding.iloc[t-2:t+1].mean()
        
        # Rankear por funding (1 es el más positivo)
        ranks = fund_signal.rank(ascending=False)
        
        target_weights = pd.Series(0.0, index=symbols)
        
        # Short top k (funding más positivo -> pagan los longs a los shorts, recibimos funding)
        shorts = ranks[ranks <= top_k].index
        for sym in shorts:
            target_weights[sym] = -0.5 / top_k
            
        # Long bottom k (funding más negativo o menos positivo -> pagan los shorts a los longs, recibimos funding)
        longs = ranks[ranks >= (len(symbols) - bottom_k + 1)].index
        for sym in longs:
            target_weights[sym] = 0.5 / bottom_k
            
        # Turnover
        turnover = (target_weights - prev_weights).abs().sum()
        fee_cost = turnover * fee_rate
        
        # PnL Direccional
        dir_ret = (target_weights * daily_returns.iloc[t]).sum()
        
        # PnL de Funding (ganamos funding positivo cuando estamos cortos, ganamos funding negativo cuando estamos largos)
        # funding rate es pagado por LONG a SHORT.
        # Retorno_funding_SHORT = funding_rate (si es positivo, el corto gana)
        # Retorno_funding_LONG = -funding_rate (si es negativo, el largo gana porque -(-rate) es positivo)
        # Por tanto, retorno_funding = - target_weights * funding_rate
        fund_ret = -(target_weights * funding_returns.iloc[t]).sum()
        
        port_ret = dir_ret + fund_ret - fee_cost
        
        capital = capital * (1 + port_ret)
        
        equity_curve.append(capital)
        dates.append(prices.index[t+1])
        
        prev_weights = target_weights.copy()
        
    eq_series = pd.Series(equity_curve, index=dates)
    
    c = cagr(eq_series)
    dd = max_drawdown(eq_series)
    win_rate = (eq_series.pct_change() > 0).mean() * 100
    
    print("\n--- Resultados V46: Carry Cross-Sectional ---")
    print(f"Período: {dates[0].date()} a {dates[-1].date()}")
    print(f"CAGR: {c:.2f}%")
    print(f"Max Drawdown: {dd:.2f}%")
    print(f"Días Positivos (Win Rate Diario): {win_rate:.1f}%")
    print(f"Equidad Final: ${capital:.2f}")

if __name__ == '__main__':
    main()
