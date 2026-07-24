import os
import sys
import pickle
import pandas as pd
import numpy as np
import matplotlib
# Use Agg backend for headless plotting
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Paths
ASSETS_DIR = '/Users/hackerunet/book_assets'
os.makedirs(ASSETS_DIR, exist_ok=True)

CACHE_1H = 'bot_alpha_portfolio/stable_v25_prototype/wf_cache_1h_26280_2026-06-11.pkl'
CACHE_4H = 'bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'

# Style config
plt.style.use('dark_background')
matplotlib.rcParams['axes.facecolor'] = '#1a1a1a'
matplotlib.rcParams['figure.facecolor'] = '#1a1a1a'
matplotlib.rcParams['grid.color'] = '#333333'
matplotlib.rcParams['text.color'] = '#e0e0e0'
matplotlib.rcParams['axes.labelcolor'] = '#e0e0e0'
matplotlib.rcParams['xtick.color'] = '#e0e0e0'
matplotlib.rcParams['ytick.color'] = '#e0e0e0'

def plot_candles(ax, df_slice, title):
    """Utility to plot candlesticks on a given matplotlib axis."""
    up = df_slice[df_slice.close >= df_slice.open]
    down = df_slice[df_slice.close < df_slice.open]
    
    # Plot wicks
    ax.vlines(up.index, up.low, up.high, color='#00ff9d', linewidth=1)
    ax.vlines(down.index, down.low, down.high, color='#ff3366', linewidth=1)
    
    # Plot bodies
    ax.bar(up.index, up.close - up.open, bottom=up.open, color='#00ff9d', width=0.8)
    ax.bar(down.index, down.open - down.close, bottom=down.close, color='#ff3366', width=0.8)
    
    ax.set_title(title, color='#e0e0e0')
    ax.grid(True, alpha=0.3)
    ax.set_xticks([])

def load_data(path, symbol):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    return pd.DataFrame(data[symbol])

def generate_v38_liquidity():
    # V38: Liquidity sweeps
    df = load_data(CACHE_1H, 'ETHUSDT')
    # Pick a slice where a sweep happens
    df_slice = df.iloc[500:600].copy().reset_index(drop=True)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V38 - Caza de Liquidez (Sweeps)")
    
    # Draw a mock resistance line being swept
    high_val = df_slice['high'].iloc[20:40].max()
    ax.axhline(high_val, color='orange', linestyle='--', label='Nivel de Liquidez')
    
    # Mark the sweep
    sweep_idx = df_slice['high'].idxmax()
    ax.plot(sweep_idx, df_slice['high'].iloc[sweep_idx], 'r^', markersize=10, label='Sweep (Trampa Alcista)')
    
    ax.legend(loc='upper right', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v38_liquidity_sweeps.png'), dpi=150)
    plt.close()

def generate_v40_macd():
    # V40: MACD
    df = load_data(CACHE_1H, 'ETHUSDT')
    df_slice = df.iloc[1000:1150].copy().reset_index(drop=True)
    
    # Calculate MACD
    exp1 = df_slice['close'].ewm(span=12, adjust=False).mean()
    exp2 = df_slice['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2, 1]})
    plot_candles(ax1, df_slice, "V40 - MACD como entrada primaria")
    
    # MACD Plot
    ax2.bar(df_slice.index, hist, color=np.where(hist > 0, '#00ff9d', '#ff3366'), alpha=0.5)
    ax2.plot(df_slice.index, macd, color='cyan', label='MACD Line')
    ax2.plot(df_slice.index, signal, color='orange', label='Signal Line')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', facecolor='#1a1a1a')
    ax2.set_xticks([])
    
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v40_macd.png'), dpi=150)
    plt.close()

def generate_v41_regime():
    # V41: Regime shift (Volatility)
    df = load_data(CACHE_4H, 'ETHUSDT')
    df_slice = df.iloc[2000:2300].copy().reset_index(drop=True)
    
    tr = np.maximum(df_slice['high'] - df_slice['low'], 
                    np.abs(df_slice['high'] - df_slice['close'].shift(1)))
    atr = tr.rolling(14).mean()
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2, 1]})
    plot_candles(ax1, df_slice, "V41 - Asignador Dinámico por Régimen (ATR)")
    
    ax2.plot(df_slice.index, atr, color='yellow', label='ATR (Volatilidad)')
    # Highlight high vol regime
    threshold = atr.mean() + atr.std()
    ax2.axhline(threshold, color='red', linestyle='--', label='Umbral Alta Volatilidad')
    
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', facecolor='#1a1a1a')
    ax2.set_xticks([])
    
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v41_regimen.png'), dpi=150)
    plt.close()

def generate_v45_reversion():
    # V45: Reversion (Bollinger Bands)
    df = load_data(CACHE_1H, 'SOLUSDT')
    df_slice = df.iloc[3000:3150].copy().reset_index(drop=True)
    
    sma = df_slice['close'].rolling(20).mean()
    std = df_slice['close'].rolling(20).std()
    upper = sma + (std * 2)
    lower = sma - (std * 2)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V45 - Reversión de corto plazo (Trend Momentum Domina)")
    
    ax.plot(df_slice.index, sma, color='gray', linestyle='--')
    ax.plot(df_slice.index, upper, color='cyan', alpha=0.5, label='Banda Superior (Corto)')
    ax.plot(df_slice.index, lower, color='fuchsia', alpha=0.5, label='Banda Inferior (Largo)')
    ax.fill_between(df_slice.index, upper, lower, color='cyan', alpha=0.05)
    
    # Mark a failed reversion where price hits lower band but keeps dropping
    hit_idx = df_slice[df_slice['close'] < lower].index
    if len(hit_idx) > 0:
        ax.plot(hit_idx, df_slice['close'].loc[hit_idx], 'v', color='yellow', markersize=8, label='Señal Reversión (Falla)')
    
    ax.legend(loc='upper right', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v45_reversion.png'), dpi=150)
    plt.close()

def generate_v47_pairs():
    # V47: Pairs trading cointegration breakdown
    df_eth = load_data(CACHE_4H, 'ETHUSDT')
    df_bnb = load_data(CACHE_4H, 'BNBUSDT')
    
    # Take a slice showing breakdown
    eth = df_eth['close'].iloc[4000:4300].values
    bnb = df_bnb['close'].iloc[4000:4300].values
    
    # Normalized prices for illustration
    eth_norm = eth / eth[0] * 100
    bnb_norm = bnb / bnb[0] * 100
    spread = eth_norm - bnb_norm
    
    # Z-score of spread
    z_score = (spread - np.mean(spread)) / np.std(spread)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2, 1]})
    ax1.plot(eth_norm, label='ETH (Normalizado)', color='cyan')
    ax1.plot(bnb_norm, label='BNB (Normalizado)', color='yellow')
    ax1.set_title("V47 - Pairs Trading por Cointegración (Ruptura de Spread)", color='#e0e0e0')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', facecolor='#1a1a1a')
    ax1.set_xticks([])
    
    ax2.plot(z_score, color='fuchsia', label='Z-Score del Spread')
    ax2.axhline(2, color='red', linestyle='--', alpha=0.5, label='Entrada (2σ)')
    ax2.axhline(-2, color='red', linestyle='--', alpha=0.5)
    ax2.axhline(4, color='orange', linestyle='-', alpha=0.5, label='Stop (4σ)')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', facecolor='#1a1a1a')
    ax2.set_xticks([])
    
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v47_pairs_spread.png'), dpi=150)
    plt.close()

if __name__ == '__main__':
    print("Generating charts...")
    generate_v38_liquidity()
    generate_v40_macd()
    generate_v41_regime()
    generate_v45_reversion()
    generate_v47_pairs()
    print("All charts generated.")
