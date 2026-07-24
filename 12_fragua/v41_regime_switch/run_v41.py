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
    print("Cargando curvas de equity base...")
    eq_v26 = pd.read_csv('../../bot_alpha_portfolio/stable_v25_prototype/v37_eq_v26_base.csv', index_col=0, parse_dates=True)
    eq_v36 = pd.read_csv('../../bot_alpha_portfolio/stable_v25_prototype/v37_eq_v36_4y.csv', index_col=0, parse_dates=True)
    
    # Ambas curvas inician con 500, representando un split 50/50 de 1000.
    # Extraemos retornos diarios
    ret_v26 = eq_v26['equity'].pct_change().fillna(0)
    ret_v36 = eq_v36['equity'].pct_change().fillna(0)
    
    # Cargamos datos de BTC para medir la volatilidad (usamos cache de 4h)
    print("Cargando caché de BTC para régimen de volatilidad...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
    if not os.path.exists(cache_path):
        print("ERROR: No se encontró cache", cache_path)
        return
    cache = pd.read_pickle(cache_path)
    df_btc = cache['ETHUSDT'].copy()
    df_btc['time'] = pd.to_datetime(df_btc['time'], unit='ms')
    df_btc.set_index('time', inplace=True)
    
    # Resample a 1D
    btc_1d = df_btc.resample('1D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    # Calculamos Realized Volatility 30d (desviación estándar anualizada de retornos diarios)
    btc_ret = btc_1d['close'].pct_change()
    realized_vol = btc_ret.rolling(window=30).std() * np.sqrt(365) * 100
    
    # Alineamos todas las series al mismo índice
    idx = eq_v26.index.intersection(eq_v36.index).intersection(realized_vol.dropna().index)
    
    ret_v26 = ret_v26.loc[idx]
    ret_v36 = ret_v36.loc[idx]
    realized_vol = realized_vol.loc[idx]
    
    # Umbral de régimen: pre-registrado = MEDIANA histórica de la volatilidad en esta ventana
    vol_median = realized_vol.median()
    print(f"Mediana de volatilidad realizada 30d (BTC): {vol_median:.2f}%")
    
    # Definimos dos hipótesis de allocation dinámico
    # Variante A: V26 (4h) es mejor en baja volatilidad (chop lento), V36 (15m) mejor en alta vol
    # Variante B: V26 (4h) es mejor en alta volatilidad (tendencias largas), V36 (15m) mejor en baja vol
    
    # Simularemos el PnL con capital inicial = 1000, rebalanceo diario
    
    def simulate_regime(w_high_v26, w_high_v36, w_low_v26, w_low_v36, name):
        capital = 1000.0
        equity = [capital]
        
        for date in idx:
            vol = realized_vol.loc[date]
            
            # Decidimos pesos del día de hoy basados en el régimen (usamos vol del día anterior para evitar lookahead, 
            # pero realized_vol.loc[date] ya solo incluye hasta ese cierre diario, por lo que rebalancear a fin del día es válido)
            if vol > vol_median:
                w26, w36 = w_high_v26, w_high_v36
            else:
                w26, w36 = w_low_v26, w_low_v36
            
            # Retorno ponderado del día
            day_return = (w26 * ret_v26.loc[date]) + (w36 * ret_v36.loc[date])
            capital = capital * (1 + day_return)
            equity.append(capital)
            
        eq_series = pd.Series(equity, index=[idx[0] - pd.Timedelta(days=1)] + list(idx))
        
        dd = max_drawdown(eq_series)
        c = cagr(eq_series)
        print(f"--- {name} ---")
        print(f"CAGR: {c:.2f}% | Max DD: {dd:.2f}% | Final Equity: {capital:.2f}")
        return eq_series
        
    print("\nSimulando Variante Estática 50/50 (Baseline V37)")
    base_eq = simulate_regime(0.5, 0.5, 0.5, 0.5, "Estático 50/50")
    
    print("\nSimulando Variante A (Alta Vol = 70% V36 / Baja Vol = 70% V26)")
    eq_a = simulate_regime(0.3, 0.7, 0.7, 0.3, "Variante A")
    
    print("\nSimulando Variante B (Alta Vol = 70% V26 / Baja Vol = 70% V36)")
    eq_b = simulate_regime(0.7, 0.3, 0.3, 0.7, "Variante B")

if __name__ == '__main__':
    main()
