"""Fase 2: Cuantitativo - Movimiento Browniano y Exponente de Hurst.

El Exponente de Hurst (H) mide la memoria de largo plazo de una serie de tiempo:
H = 0.5 -> Movimiento Browniano (Random Walk / Ruido puro).
H > 0.5 -> Persistencia (Tendencia).
H < 0.5 -> Anti-persistencia (Reversión a la media).

Si H es predictivo, podríamos usarlo como un filtro:
Solo tomar señales de V26 (Tendencia) cuando H > 0.5.
"""
import os
import sys
import numpy as np
import pandas as pd

DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIR_DATA = os.path.abspath(os.path.join(DIR_SCRIPT, '..', '..', 'claw_data'))

def compute_hurst(ts, max_lag=20):
    """Calcula el Exponente de Hurst usando la varianza de las diferencias de rezagos."""
    lags = range(2, max_lag)
    # std de la diferencia de precios en distintos lags
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    # Polyfit log(tau) vs log(lags)
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0] * 2.0  # H = poly[0] * 2

def compute_rolling_hurst(series, window=90, max_lag=20):
    """Aplica compute_hurst en ventanas móviles."""
    hurst_vals = []
    for i in range(len(series)):
        if i < window:
            hurst_vals.append(np.nan)
        else:
            window_data = series.iloc[i-window:i].values
            hurst_vals.append(compute_hurst(window_data, max_lag=max_lag))
    return pd.Series(hurst_vals, index=series.index)

def load_data(symbol='ETHUSDT', timeframe='4h'):
    path = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype', 'wf_cache_4h_8760_2026-06-11.pkl')
    if not os.path.exists(path):
        print(f"Error: No se encontró la data {path}")
        return None
    cache = pd.read_pickle(path)
    if symbol not in cache:
        print(f"Error: Símbolo {symbol} no en cache")
        return None
    df = cache[symbol]
    df = df.sort_index()
    return df

def main():
    print("Cargando datos OHLCV (ETHUSDT 4h)...")
    df = load_data('ETHUSDT', '4h')
    if df is None: return
    
    # Filtro: desde 2022 para ser comparable con V26
    df = df.loc['2022-01-01':]
    
    print("Calculando Exponente de Hurst rolling (90 días = 540 velas)...")
    # 540 velas de 4h = 90 días
    df['hurst_90d'] = compute_rolling_hurst(np.log(df['close']), window=540, max_lag=30)
    
    df.dropna(subset=['hurst_90d'], inplace=True)
    
    print("\nEstadísticas del Exponente de Hurst (ETHUSDT 4h):")
    print(df['hurst_90d'].describe())
    
    # Evaluar si el Hurst ayuda a predecir retornos futuros (Tendencia)
    # Retorno futuro a 7 días (42 velas)
    df['ret_future_7d'] = df['close'].shift(-42) / df['close'] - 1.0
    
    # Correlacionar el Hurst actual con la magnitud del movimiento futuro absoluto
    # H > 0.5 sugiere que habrá un fuerte movimiento direccional
    df['abs_ret_future'] = df['ret_future_7d'].abs()
    corr = df['hurst_90d'].corr(df['abs_ret_future'])
    print(f"\nCorrelación Hurst(90d) vs Magnitud de Movimiento Futuro (7d): {round(corr, 4)}")
    
    # Separar en regímenes
    df_tendencia = df[df['hurst_90d'] > 0.5]
    df_reversion = df[df['hurst_90d'] < 0.5]
    
    print(f"\nRégimen de Tendencia (H > 0.5): {len(df_tendencia)} velas ({round(len(df_tendencia)/len(df)*100, 1)}%)")
    print(f"  Retorno futuro abs mediano: {round(df_tendencia['abs_ret_future'].median()*100, 2)}%")
    print(f"Régimen de Reversión (H < 0.5): {len(df_reversion)} velas ({round(len(df_reversion)/len(df)*100, 1)}%)")
    print(f"  Retorno futuro abs mediano: {round(df_reversion['abs_ret_future'].median()*100, 2)}%")

if __name__ == '__main__':
    main()
