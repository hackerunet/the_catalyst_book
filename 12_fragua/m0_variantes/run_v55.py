import json
import pandas as pd
import numpy as np

def main():
    print("Iniciando Análisis de Estacionalidad V55 sobre trades de V26...")
    
    trades_path = '../../bot_alpha_portfolio/stable_v25_prototype/v37_trades_v26_base.pkl'
    trades_list = pd.read_pickle(trades_path)
    df = pd.DataFrame(trades_list)
    
    # Extraer retorno en % (ignorando comisiones por un momento para ver el PnL bruto)
    # entry_price, exit_price, type (LONG/SHORT)
    if 'ret' not in df.columns:
        df['ret'] = np.where(df['type'] == 'LONG', 
                             df['exit_price'] / df['entry_price'] - 1.0,
                             df['entry_price'] / df['exit_price'] - 1.0)
                             
    df['win'] = df['ret'] > 0
    
    if not isinstance(df['entry_time'].iloc[0], pd.Timestamp):
        df['entry_time'] = pd.to_datetime(df['entry_time'])
    
    df['hour'] = df['entry_time'].dt.hour
    df['dayofweek'] = df['entry_time'].dt.dayofweek
    
    print("\n--- Análisis por Hora del Día (UTC) ---")
    hourly = df.groupby('hour').agg(
        trades=('ret', 'count'),
        win_rate=('win', 'mean'),
        avg_ret=('ret', 'mean'),
        sum_ret=('ret', 'sum')
    )
    print(hourly.sort_index())
    
    print("\n--- Análisis por Día de la Semana (0=Lunes, 6=Domingo) ---")
    daily = df.groupby('dayofweek').agg(
        trades=('ret', 'count'),
        win_rate=('win', 'mean'),
        avg_ret=('ret', 'mean'),
        sum_ret=('ret', 'sum')
    )
    print(daily.sort_index())
    
    print(f"\nTotal Trades: {len(df)}")
    print(f"Win Rate Global: {df['win'].mean()*100:.1f}%")

if __name__ == '__main__':
    main()
