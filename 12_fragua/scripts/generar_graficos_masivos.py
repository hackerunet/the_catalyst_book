import os
import pickle
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ASSETS_DIR = '/Users/hackerunet/book_assets'
os.makedirs(ASSETS_DIR, exist_ok=True)

CACHE_1H = 'bot_alpha_portfolio/stable_v25_prototype/wf_cache_1h_26280_2026-06-11.pkl'
CACHE_4H = 'bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_2026-06-11.pkl'
CACHE_15M = 'bot_alpha_portfolio/stable_v25_prototype/wf_cache_15m_35040_2026-06-11.pkl'

# Style config
plt.style.use('dark_background')
matplotlib.rcParams['axes.facecolor'] = '#1a1a1a'
matplotlib.rcParams['figure.facecolor'] = '#1a1a1a'
matplotlib.rcParams['grid.color'] = '#333333'
matplotlib.rcParams['text.color'] = '#e0e0e0'
matplotlib.rcParams['axes.labelcolor'] = '#e0e0e0'
matplotlib.rcParams['xtick.color'] = '#e0e0e0'
matplotlib.rcParams['ytick.color'] = '#e0e0e0'

def load_data(path, symbol):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    return pd.DataFrame(data[symbol])

def plot_candles(ax, df_slice, title):
    up = df_slice[df_slice.close >= df_slice.open]
    down = df_slice[df_slice.close < df_slice.open]
    ax.vlines(up.index, up.low, up.high, color='#00ff9d', linewidth=1)
    ax.vlines(down.index, down.low, down.high, color='#ff3366', linewidth=1)
    ax.bar(up.index, up.close - up.open, bottom=up.open, color='#00ff9d', width=0.8)
    ax.bar(down.index, down.open - down.close, bottom=down.close, color='#ff3366', width=0.8)
    ax.set_title(title, color='#e0e0e0')
    ax.grid(True, alpha=0.3)
    ax.set_xticks([])

def generate_v26_tendencia():
    df = load_data(CACHE_4H, 'ETHUSDT')
    df_slice = df.iloc[500:600].copy().reset_index(drop=True)
    sma9 = df_slice['close'].rolling(9).mean()
    sma21 = df_slice['close'].rolling(21).mean()
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V26 - Tendencia (Cruce + Salida Flip) en 4h")
    ax.plot(df_slice.index, sma9, color='cyan', label='SMA Rápida (9)')
    ax.plot(df_slice.index, sma21, color='orange', label='SMA Lenta (21)')
    
    # Simulate a flip exit (close drops below SMA21)
    flip_points = df_slice[(df_slice['close'] < sma21) & (df_slice['close'].shift(1) >= sma21.shift(1))].index
    if len(flip_points) > 0:
        ax.plot(flip_points, df_slice['close'].loc[flip_points], 'v', color='fuchsia', markersize=10, label='Salida Flip')
        
    ax.legend(loc='upper right', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v26_tendencia.png'), dpi=150)
    plt.close()

def generate_v36_15m():
    try:
        df = load_data(CACHE_15M, 'ETHUSDT')
    except:
        df = load_data(CACHE_1H, 'ETHUSDT') # Fallback if 15m not generated correctly
    df_slice = df.iloc[1200:1300].copy().reset_index(drop=True)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V36 - Patrones en 15m (Pin Bar)")
    
    # Highlight a pin bar (long lower wick)
    body = np.abs(df_slice['close'] - df_slice['open'])
    lower_wick = np.minimum(df_slice['close'], df_slice['open']) - df_slice['low']
    pin_bars = df_slice[(lower_wick > body * 3) & (df_slice['low'] < df_slice['low'].rolling(10).min().shift(1))].index
    
    if len(pin_bars) > 0:
        ax.plot(pin_bars, df_slice['low'].loc[pin_bars] - (df_slice['close'].mean()*0.005), '^', color='yellow', markersize=12, label='Patrón Pin Bar')
        
    ax.legend(loc='upper right', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v36_15m.png'), dpi=150)
    plt.close()

def generate_v17_rsi():
    df = load_data(CACHE_1H, 'SOLUSDT')
    df_slice = df.iloc[2000:2150].copy().reset_index(drop=True)
    
    # Simple RSI
    delta = df_slice['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2, 1]})
    plot_candles(ax1, df_slice, "V17_C - RSI Momentum (Falso Edge)")
    ax2.plot(df_slice.index, rsi, color='cyan', label='RSI (14)')
    ax2.axhline(70, color='red', linestyle='--')
    ax2.axhline(30, color='red', linestyle='--')
    
    overbought = df_slice[rsi > 70].index
    if len(overbought) > 0:
        ax1.plot(overbought, df_slice['high'].loc[overbought], 'v', color='fuchsia', markersize=6, alpha=0.5, label='Señal Corta (Falla por tendencia)')
        
    ax1.legend(loc='upper right', facecolor='#1a1a1a')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right', facecolor='#1a1a1a')
    ax2.set_xticks([])
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v17_rsi.png'), dpi=150)
    plt.close()

def generate_v18_bollinger():
    df = load_data(CACHE_1H, 'ETHUSDT')
    df_slice = df.iloc[3000:3150].copy().reset_index(drop=True)
    sma = df_slice['close'].rolling(20).mean()
    std = df_slice['close'].rolling(20).std()
    upper = sma + (std * 2.5) # Extreme bollinger
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V18_A - Bollinger Extremo (Trend atrapa al mean-reversion)")
    ax.plot(df_slice.index, upper, color='fuchsia', linestyle='--', label='Banda Superior (2.5σ)')
    
    breakouts = df_slice[df_slice['close'] > upper].index
    if len(breakouts) > 0:
        ax.plot(breakouts, df_slice['high'].loc[breakouts], 'v', color='yellow', markersize=8, label='Entrada Corta (Liquidadas)')
        
    ax.legend(loc='upper right', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v18_bollinger.png'), dpi=150)
    plt.close()

def generate_v24_honesto():
    df = load_data(CACHE_1H, 'ETHUSDT')
    df_slice = df.iloc[4000:4100].copy().reset_index(drop=True)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "V24 - Motor Honesto (Impacto de Slippage y Fee)")
    
    # Draw a simulated trade
    entry_idx = 20
    exit_idx = 70
    entry_price = df_slice['close'].iloc[entry_idx]
    exit_price = df_slice['close'].iloc[exit_idx]
    
    # Show slippage gap
    theoretical_entry = entry_price - (entry_price * 0.005)
    real_entry = entry_price + (entry_price * 0.002)
    
    ax.plot(entry_idx, theoretical_entry, '^', color='gray', markersize=8, label='Entrada Ideal (Sin fee)')
    ax.plot(entry_idx, real_entry, '^', color='cyan', markersize=12, label='Entrada Real (Motor Honesto)')
    ax.plot([entry_idx, entry_idx], [theoretical_entry, real_entry], color='red', linestyle=':', label='Slippage/Fee Gap')
    
    ax.legend(loc='lower left', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'v24_honesto.png'), dpi=150)
    plt.close()

def generate_p1_p2():
    df = load_data(CACHE_1H, 'ETHUSDT')
    df_slice = df.iloc[5000:5150].copy().reset_index(drop=True)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_candles(ax, df_slice, "P1/P2 - Salidas Prematuras vs Agotamiento")
    
    # Mock trade riding a trend
    entry = 10
    p1_exit = 40 # Closed early due to fixed target
    p2_exit = 110 # Closed due to trend exhaustion
    
    ax.plot(entry, df_slice['low'].iloc[entry]*0.99, '^', color='cyan', markersize=10, label='Entrada Long')
    ax.plot(p1_exit, df_slice['high'].iloc[p1_exit]*1.01, 'v', color='orange', markersize=10, label='P1: Cierre Prematuro (Fija)')
    ax.plot(p2_exit, df_slice['high'].iloc[p2_exit]*1.01, 'v', color='yellow', markersize=10, label='P2: Cierre Agotamiento')
    
    ax.legend(loc='upper left', facecolor='#1a1a1a')
    fig.tight_layout()
    plt.savefig(os.path.join(ASSETS_DIR, 'p1_p2_salidas.png'), dpi=150)
    plt.close()

if __name__ == '__main__':
    print("Generating massive charts...")
    generate_v26_tendencia()
    generate_v36_15m()
    generate_v17_rsi()
    generate_v18_bollinger()
    generate_v24_honesto()
    generate_p1_p2()
    print("Massive charts generated.")
