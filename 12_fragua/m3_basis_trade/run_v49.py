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
    print("Iniciando Motor M3 - Basis Trade Dinámico (V49)...")
    fund_path = '../../bot_alpha_portfolio/v27b_carry/funding_cache.pkl'
    
    if not os.path.exists(fund_path):
        print("ERROR: Archivo de caché de funding no encontrado.")
        return
        
    fund_cache = pd.read_pickle(fund_path)
    sym = 'BTCUSDT'
    
    df = fund_cache[sym].copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        
    # Agrupar por día (suma de los 3 funding rates de 8h del día)
    daily_fund = df.resample('1D').agg({'rate': 'sum'}).fillna(0)
    
    # Calcular la media móvil de 30 días del funding rate diario
    # Queremos activar el carry trade si la media de 30d es mayor a 0.09% por día (0.03% * 3)
    ma_30d = daily_fund['rate'].rolling(window=30).mean()
    
    threshold = 0.0009 # 0.09% diario
    fee_per_leg = 0.001
    total_entry_fee = 2 * fee_per_leg # 0.2% total para entrar (comprar spot, vender perp)
    total_exit_fee = 2 * fee_per_leg  # 0.2% total para salir
    
    # 1.0 = Adentro del mercado cobrando funding (Long Basis)
    # 0.0 = Afuera del mercado, en cash (0% retorno)
    position = pd.Series(0.0, index=daily_fund.index)
    
    current_pos = 0.0
    for i in range(len(ma_30d)):
        if pd.isna(ma_30d.iloc[i]):
            position.iloc[i] = 0.0
            continue
            
        rate_ma = ma_30d.iloc[i]
        
        if current_pos == 0.0:
            if rate_ma > threshold:
                current_pos = 1.0 # Entrar al mercado
        else:
            # Salir si cae debajo del umbral o de un umbral menor (e.g. 0.01% diario) para evitar whipsaw
            if rate_ma < 0.0003: # 0.01% por 8h
                current_pos = 0.0
                
        position.iloc[i] = current_pos
        
    # El retorno diario que ganamos es el funding rate de HOY si ayer cerramos Adentro.
    pos_shifted = position.shift(1).fillna(0)
    
    # Ganancia por funding
    # Si pos = 1, estamos cortos en Perp y largos en Spot -> cobramos el funding rate positivo.
    fund_ret = pos_shifted * daily_fund['rate']
    
    # Costos de transacción por cambio de posición
    pos_diff = position.diff().abs().fillna(0)
    fee_cost = pos_diff * total_entry_fee # 0.2% por cada flip (entrada o salida)
    
    net_ret = fund_ret - fee_cost
    
    capital = 1000.0
    equity = [capital]
    for r in net_ret:
        capital = capital * (1 + r)
        equity.append(capital)
        
    # equity array is 1 larger than net_ret, align it
    eq_series = pd.Series(equity[1:], index=daily_fund.index)
    
    c = cagr(eq_series)
    dd = max_drawdown(eq_series)
    time_in_market = (pos_shifted > 0).mean() * 100
    num_trades = (pos_diff > 0).sum() / 2 # Entradas y salidas
    
    print(f"\nResultados Carry Dinámico BTC (Umbral entrada > 0.03%/8h, salida < 0.01%/8h):")
    print(f"Período: {daily_fund.index[0].date()} a {daily_fund.index[-1].date()}")
    print(f"Tiempo en mercado: {time_in_market:.1f}%")
    print(f"Trades completos (round trips): {int(num_trades)}")
    print(f"CAGR: {c:.2f}%")
    print(f"Max Drawdown: {dd:.2f}%")
    print(f"Equidad Final: ${capital:.2f}")

if __name__ == '__main__':
    main()
