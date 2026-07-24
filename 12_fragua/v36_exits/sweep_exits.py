import pandas as pd
import numpy as np
import os
import sys

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
    print("Iniciando Barrido de Salidas V36 (Exit Strategy Matrix)...")
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_now.pkl'
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} no encontrado.")
        return
        
    cache = pd.read_pickle(cache_path)
    symbols = ['ETHUSDT', 'SOLUSDT'] # Enfoque en ETH y SOL (las que superaron 140%+)
    
    for sym in symbols:
        df = cache[sym].copy()
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        
        # 1. Base Entry Logic (Proxy V26)
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['atr'] = df['high'].rolling(14).max() - df['low'].rolling(14).min() # ATR simplificado
        
        # Condición de entrada estricta (Inicio de tendencia)
        df['bull_trend'] = df['ema50'] > df['ema200']
        df['enter_long'] = (df['bull_trend']) & (~df['bull_trend'].shift(1).fillna(False)) & (df['close'] > df['ema50'])
        
        fee = 0.001
        configs = [
            {"name": "Estructural (V36 Base)", "trailing_pct": None, "time_stop": None, "rsi_exhaust": False, "hard_sl": None},
            {"name": "Aggressive T-Stop 5%", "trailing_pct": 0.05, "time_stop": None, "rsi_exhaust": False, "hard_sl": None},
            {"name": "T-Stop 5% + Hard SL 5%", "trailing_pct": 0.05, "time_stop": None, "rsi_exhaust": False, "hard_sl": 0.05},
            {"name": "T-Stop 5% + Hard SL 3%", "trailing_pct": 0.05, "time_stop": None, "rsi_exhaust": False, "hard_sl": 0.03},
        ]
        
        results = []
        for config in configs:
            eq = [1000.0]
            cap = 1000.0
            in_trade = False
            entry_price = 0
            bars_in_trade = 0
            peak_price = 0
            
            total_giveback_pct = 0.0
            total_winning_trades = 0
            
            trade_log = []
            
            for i in range(1, len(df)):
                current_close = df['close'].iloc[i]
                current_high = df['high'].iloc[i]
                current_low = df['low'].iloc[i]
                current_time = df.index[i]
                
                # Check Exits if in trade
                if in_trade:
                    bars_in_trade += 1
                    peak_price = max(peak_price, current_high)
                    exit_triggered = False
                    exit_reason = ""
                    
                    # Hard Stop Loss
                    if config.get("hard_sl") is not None and not exit_triggered:
                        hard_stop_price = entry_price * (1 - config["hard_sl"])
                        if current_low < hard_stop_price:
                            exit_triggered = True
                            exit_reason = "Hard SL"
                            current_close = hard_stop_price
                    
                    # Salida estructural (V36 base: EMA cruza a la baja o pierde la EMA50 con fuerza)
                    if not df['bull_trend'].iloc[i] and not exit_triggered:
                        exit_triggered = True
                        exit_reason = "Estructural EMA"
                        
                    # Trailing Stop
                    if config["trailing_pct"] is not None and not exit_triggered:
                        stop_price = peak_price * (1 - config["trailing_pct"])
                        if current_low < stop_price:
                            exit_triggered = True
                            exit_reason = "Trailing Stop"
                            current_close = stop_price # Asume salida al toque del stop
                            
                    # Time Stop
                    if config["time_stop"] is not None and not exit_triggered:
                        if bars_in_trade >= config["time_stop"]:
                            exit_triggered = True
                            exit_reason = "Time Stop"
                            
                    # RSI Exhaustion
                    if config["rsi_exhaust"] and not exit_triggered:
                        if df['rsi'].iloc[i] > 75 and (current_close > entry_price * 1.05): # Agotamiento en ganancia
                            exit_triggered = True
                            exit_reason = "RSI Exhaust"
                            
                    if exit_triggered:
                        ret = (current_close - entry_price) / entry_price
                        cap = cap * (1 + ret) - (cap * fee) # fee de salida
                        in_trade = False
                        
                        giveback_pct = 0
                        peak_ret = (peak_price - entry_price) / entry_price
                        if peak_price > entry_price and current_close > entry_price:
                            giveback_pct = peak_ret - ret
                            total_giveback_pct += giveback_pct
                            total_winning_trades += 1
                            
                        trade_log.append({
                            "Entry_Time": entry_time,
                            "Exit_Time": current_time,
                            "Entry_Price": entry_price,
                            "Peak_Price": peak_price,
                            "Exit_Price": current_close,
                            "Peak_Ret_%": peak_ret * 100,
                            "Actual_Ret_%": ret * 100,
                            "Giveback_%": giveback_pct * 100,
                            "Reason": exit_reason
                        })
                        
                # Check Entries
                if not in_trade and df['enter_long'].iloc[i]:
                    in_trade = True
                    entry_price = current_close
                    entry_time = current_time
                    bars_in_trade = 0
                    peak_price = current_close
                    cap = cap - (cap * fee) # fee de entrada
                    
                eq.append(cap)
                
            eq_series = pd.Series(eq, index=df.index)
            c = cagr(eq_series)
            d = max_drawdown(eq_series)
            avg_giveback = (total_giveback_pct / total_winning_trades * 100) if total_winning_trades > 0 else 0
            
            # Trade Stats
            total_trades = len(trade_log)
            win_trades = len([t for t in trade_log if t["Actual_Ret_%"] > 0])
            win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
            
            results.append({
                "Estrategia": config["name"], 
                "Trades": total_trades,
                "WinRate%": win_rate,
                "CAGR%": c, 
                "MaxDD%": d, 
                "AvgGiveback%": avg_giveback
            })
            
            # Guardar CSV de trades para detalle
            pd.DataFrame(trade_log).to_csv(f"trades_{config['name'].replace(' ', '_').replace('/', '_')}.csv", index=False)
            
        # Generar Reporte
        print(f"\n=============================================")
        print(f"RESULTADOS GLOBALES {sym} (Velas 4h, 2022-2026)")
        print(f"=============================================")
        res_df = pd.DataFrame(results)
        print(res_df.to_string(index=False))
        
        # Analisis profundo de Giveback V36
        print("\n\n=============================================")
        print(f"ANÁLISIS PROFUNDO DE OPERACIONES (MUESTRA)")
        print(f"=============================================")
        df_base = pd.read_csv("trades_Estructural_(V36_Base).csv")
        df_base = df_base.sort_values(by="Peak_Ret_%", ascending=False).head(5)
        print("\nTop 5 trades de mayor subida (V36 Estructural Base):")
        print("Muestra como el bot llega a picos enormes pero sale muy abajo:")
        print(df_base[['Entry_Time', 'Exit_Time', 'Entry_Price', 'Peak_Price', 'Exit_Price', 'Peak_Ret_%', 'Actual_Ret_%', 'Giveback_%']].to_string(index=False))
        
        df_aggr = pd.read_csv("trades_Aggressive_T-Stop_5%.csv")
        df_aggr = df_aggr.sort_values(by="Peak_Ret_%", ascending=False).head(5)
        print("\nTop 5 trades de mayor subida (Con T-Stop 5%):")
        print("Muestra como el bot sí captura la cima limitando el Giveback:")
        print(df_aggr[['Entry_Time', 'Exit_Time', 'Entry_Price', 'Peak_Price', 'Exit_Price', 'Peak_Ret_%', 'Actual_Ret_%', 'Giveback_%']].to_string(index=False))

if __name__ == '__main__':
    main()
