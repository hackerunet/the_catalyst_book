"""Fase 3: Exploración Delta-Neutral Sintético (Beta Hedging).

Simula un portafolio Market-Neutral en Spot/Perp:
1. Va LONG en un Altcoin (ej. ETH, SOL).
2. Va SHORT en BTC de forma dinámica usando el Beta rolling.
3. Evalúa si el "Alpha" (rendimiento excedente) cubre los costos de rebalanceo (taker fees + slippage).
"""
import os
import sys
import numpy as np
import pandas as pd

DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
PATH_CACHE = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype', 'wf_cache_4h_8760_2026-06-11.pkl')

WINDOW_BETA = 180  # 30 días en velas de 4h
FEE_SLIPPAGE = 0.0010  # 0.10% total por lado para ser pesimistas

def load_data():
    if not os.path.exists(PATH_CACHE):
        print(f"Error: Cache no encontrado: {PATH_CACHE}")
        return None
    return pd.read_pickle(PATH_CACHE)

def test_beta_hedging(cache, altcoin='ETHUSDT', benchmark='BTCUSDT'):
    if altcoin not in cache or benchmark not in cache:
        print(f"Faltan símbolos {altcoin} o {benchmark}")
        return
    
    df_alt = cache[altcoin].copy()
    df_btc = cache[benchmark].copy()
    
    # Align dates
    df = pd.DataFrame(index=df_alt.index)
    df['ret_alt'] = df_alt['close'].pct_change()
    df['ret_btc'] = df_btc['close'].pct_change()
    df.dropna(inplace=True)
    
    # Calcular covarianza y varianza rolling para el Beta
    rolling_cov = df['ret_alt'].rolling(WINDOW_BETA).cov(df['ret_btc'])
    rolling_var = df['ret_btc'].rolling(WINDOW_BETA).var()
    df['beta'] = (rolling_cov / rolling_var).bfill()
    
    # Posición teórica
    # Vamos LONG en 1 unidad de capital en el Altcoin.
    # Vamos SHORT en 'beta' unidades de capital en BTC.
    
    # El retorno diario bruto de la posición neutral:
    df['ret_hedged_gross'] = df['ret_alt'] - df['beta'] * df['ret_btc']
    
    # Costos de rebalanceo:
    # Solo pagamos fee por la porción de BTC que ajustamos.
    # El peso de altcoin es constante 1. El peso de BTC es -Beta.
    # El cambio en peso de BTC es |Beta(t) - Beta(t-1)|
    delta_beta = df['beta'].diff().abs().fillna(0)
    df['rebalance_cost'] = delta_beta * FEE_SLIPPAGE
    
    df['ret_hedged_net'] = df['ret_hedged_gross'] - df['rebalance_cost']
    
    # Equity
    df['eq_gross'] = (1.0 + df['ret_hedged_gross']).cumprod()
    df['eq_net'] = (1.0 + df['ret_hedged_net']).cumprod()
    
    print(f"\n--- Delta-Neutral (Beta Hedging) {altcoin} vs {benchmark} ---")
    print(f"Ventana Beta: {WINDOW_BETA} velas de 4h (30 días)")
    print(f"Beta mediano: {round(df['beta'].median(), 2)}x")
    print(f"Costo acumulado (Drag): {round(df['rebalance_cost'].sum() * 100, 2)}% en {len(df)} velas")
    
    cagr_gross = (df['eq_gross'].iloc[-1]) ** (365.25 / (len(df)/6)) - 1
    cagr_net = (df['eq_net'].iloc[-1]) ** (365.25 / (len(df)/6)) - 1
    
    print(f"CAGR Bruto (sin costos): {round(cagr_gross * 100, 2)}%")
    print(f"CAGR Neto  (con costos): {round(cagr_net * 100, 2)}%")
    print(f"Sharpe Ratio (Neto): {round(df['ret_hedged_net'].mean() / df['ret_hedged_net'].std() * np.sqrt(365*6), 2)}")
    
    return df

def main():
    cache = load_data()
    if cache is None: return
    
    # Usamos ETHUSDT contra BTCUSDT (No tenemos BTCUSDT en el cache! Espera.)
    # Las keys del cache que vimos eran: ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']
    # Oops. BTCUSDT NO ESTÁ EN ESTE CACHE.
    
    # Vamos a usar el otro cache para BTCUSDT.
    path_cache_btc = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype', 'wf_cache_4h_8760_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl')
    cache_btc = pd.read_pickle(path_cache_btc)
    
    cache_full = {}
    cache_full.update(cache)
    cache_full.update(cache_btc)
    
    test_beta_hedging(cache_full, 'ETHUSDT', 'BTCUSDT')
    test_beta_hedging(cache_full, 'SOLUSDT', 'BTCUSDT')
    test_beta_hedging(cache_full, 'LINKUSDT', 'BTCUSDT')

if __name__ == '__main__':
    main()
