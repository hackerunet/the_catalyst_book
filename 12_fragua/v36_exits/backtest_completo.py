"""
Backtest COMPLETO de Estrategias de Salida V36
===============================================
Genera un reporte exhaustivo trade-por-trade para CADA símbolo,
con métricas reales: precio entrada, precio salida, precio pico,
PnL por trade, duración, razón de cierre, equity acumulada,
drawdown corriente, win rate acumulado.

Compara V36 Base (Estructural EMA) vs Trailing Stop 5%.
"""
import pandas as pd
import numpy as np
import os
import sys
from datetime import timedelta

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_backtest(df, config, fee=0.001, initial_cap=10000.0):
    """
    Corre un backtest completo y devuelve:
    - trade_log: lista de dicts con CADA operación
    - equity_curve: Series con la equity en cada vela
    """
    cap = initial_cap
    in_trade = False
    entry_price = 0
    entry_time = None
    bars_in_trade = 0
    peak_price = 0
    
    trade_log = []
    equity = [cap]
    peak_equity = cap
    
    for i in range(1, len(df)):
        current_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        current_time = df.index[i]
        
        if in_trade:
            bars_in_trade += 1
            peak_price = max(peak_price, current_high)
            exit_triggered = False
            exit_reason = ""
            exit_price = current_close
            
            # Hard Stop Loss
            if config.get("hard_sl") is not None and not exit_triggered:
                hard_stop_price = entry_price * (1 - config["hard_sl"])
                if current_low < hard_stop_price:
                    exit_triggered = True
                    exit_reason = "Hard SL"
                    exit_price = hard_stop_price
            
            # Salida estructural (EMA cruza a la baja)
            if not df['bull_trend'].iloc[i] and not exit_triggered:
                exit_triggered = True
                exit_reason = "Flip EMA"
                exit_price = current_close
                
            # Smart Trailing Stop (solo se activa si la rentabilidad latente supera un umbral)
            if config.get("trailing_pct") is not None and not exit_triggered:
                peak_ret = (peak_price - entry_price) / entry_price
                activation_threshold = config.get("trailing_activation", 0.0)
                
                if peak_ret >= activation_threshold:
                    stop_price = peak_price * (1 - config["trailing_pct"])
                    if current_low < stop_price:
                        exit_triggered = True
                        exit_reason = f"Smart T-Stop (Activado en {activation_threshold*100}%)" if activation_threshold > 0 else "Trailing"
                        exit_price = stop_price
                    
            if exit_triggered:
                ret_pct = (exit_price - entry_price) / entry_price * 100
                pnl_usd = cap * (ret_pct / 100)
                cap = cap + pnl_usd - (cap * fee)  # fee de salida
                in_trade = False
                
                peak_ret_pct = (peak_price - entry_price) / entry_price * 100
                giveback_pct = peak_ret_pct - ret_pct if peak_ret_pct > 0 else 0
                
                # Drawdown de equity
                peak_equity = max(peak_equity, cap)
                dd_pct = (cap - peak_equity) / peak_equity * 100
                
                duration_hours = bars_in_trade * 4  # velas de 4h
                duration_days = duration_hours / 24
                
                trade_log.append({
                    "#": len(trade_log) + 1,
                    "Entrada": entry_time.strftime("%Y-%m-%d %H:%M"),
                    "Salida": current_time.strftime("%Y-%m-%d %H:%M"),
                    "Días": round(duration_days, 1),
                    "P.Entrada": round(entry_price, 2),
                    "P.Pico": round(peak_price, 2),
                    "P.Salida": round(exit_price, 2),
                    "Ret%": round(ret_pct, 2),
                    "PicoRet%": round(peak_ret_pct, 2),
                    "Giveback%": round(giveback_pct, 2),
                    "PnL$": round(pnl_usd, 2),
                    "Equity$": round(cap, 2),
                    "DD%": round(dd_pct, 2),
                    "Razón": exit_reason
                })
        
        # Check Entries
        if not in_trade and df['enter_long'].iloc[i]:
            in_trade = True
            entry_price = current_close
            entry_time = current_time
            bars_in_trade = 0
            peak_price = current_close
            cap = cap - (cap * fee)  # fee de entrada
            
        equity.append(cap)
        
    # Registrar trade abierto al finalizar
    if in_trade:
        ret_pct = (current_close - entry_price) / entry_price * 100
        pnl_usd = cap * (ret_pct / 100)
        
        peak_ret_pct = (peak_price - entry_price) / entry_price * 100
        giveback_pct = peak_ret_pct - ret_pct if peak_ret_pct > 0 else 0
        
        duration_hours = bars_in_trade * 4
        duration_days = duration_hours / 24
        
        trade_log.append({
            "#": len(trade_log) + 1,
            "Entrada": entry_time.strftime("%Y-%m-%d %H:%M"),
            "Salida": "ABIERTO (Actual)",
            "Días": round(duration_days, 1),
            "P.Entrada": round(entry_price, 2),
            "P.Pico": round(peak_price, 2),
            "P.Salida": round(current_close, 2),
            "Ret%": round(ret_pct, 2),
            "PicoRet%": round(peak_ret_pct, 2),
            "Giveback%": round(giveback_pct, 2),
            "PnL$": round(pnl_usd, 2),
            "Equity$": round(cap + pnl_usd, 2),
            "DD%": 0.0,
            "Razón": "Trade Abierto"
        })
    
    return trade_log, pd.Series(equity, index=df.index)


def print_full_report(sym, trade_log, equity_series, config_name, start_date=None):
    """Imprime reporte exhaustivo"""
    print(f"\n{'='*120}")
    print(f"  REPORTE COMPLETO: {sym} | Estrategia: {config_name}")
    
    if start_date:
        # Filtrar trades que salieron después de start_date o están abiertos
        filtered_log = []
        for t in trade_log:
            if t["Salida"] == "ABIERTO (Actual)":
                filtered_log.append(t)
            else:
                from datetime import datetime
                salida_dt = datetime.strptime(t["Salida"], "%Y-%m-%d %H:%M")
                if salida_dt >= start_date:
                    filtered_log.append(t)
        trade_log = filtered_log
        
        # Filtrar equity
        equity_series = equity_series[equity_series.index >= start_date]

    print(f"  Período Mostrado: {equity_series.index[0].strftime('%Y-%m-%d')} → {equity_series.index[-1].strftime('%Y-%m-%d')}")
    print(f"{'='*120}")
    
    if not trade_log:
        print("  SIN TRADES")
        return
    
    df_trades = pd.DataFrame(trade_log)
    
    # ---- TABLA COMPLETA DE TRADES ----
    print(f"\n  LISTA COMPLETA DE OPERACIONES ({len(trade_log)} trades):")
    print(f"  {'-'*116}")
    print(df_trades.to_string(index=False))
    
    # ---- ESTADÍSTICAS GLOBALES ----
    total = len(trade_log)
    wins = len([t for t in trade_log if t["Ret%"] > 0])
    losses = total - wins
    win_rate = wins / total * 100
    
    avg_win = np.mean([t["Ret%"] for t in trade_log if t["Ret%"] > 0]) if wins > 0 else 0
    avg_loss = np.mean([t["Ret%"] for t in trade_log if t["Ret%"] <= 0]) if losses > 0 else 0
    best_trade = max(trade_log, key=lambda t: t["Ret%"])
    worst_trade = min(trade_log, key=lambda t: t["Ret%"])
    
    max_dd = min(t["DD%"] for t in trade_log)
    avg_giveback = np.mean([t["Giveback%"] for t in trade_log if t["Giveback%"] > 0])
    avg_duration = np.mean([t["Días"] for t in trade_log])
    
    final_equity = trade_log[-1]["Equity$"]
    total_return = (final_equity / 10000 - 1) * 100
    
    # CAGR
    days = (equity_series.index[-1] - equity_series.index[0]).days
    cagr = ((final_equity / 10000) ** (365.25 / days) - 1) * 100 if days > 0 else 0
    
    # Profit Factor
    gross_profit = sum(t["PnL$"] for t in trade_log if t["PnL$"] > 0)
    gross_loss = abs(sum(t["PnL$"] for t in trade_log if t["PnL$"] < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    print(f"\n  {'='*60}")
    print(f"  RESUMEN ESTADÍSTICO")
    print(f"  {'='*60}")
    print(f"  Capital Inicial:      $10,000.00")
    print(f"  Capital Final:        ${final_equity:,.2f}")
    print(f"  Retorno Total:        {total_return:+.2f}%")
    print(f"  CAGR:                 {cagr:+.2f}%")
    print(f"  Profit Factor:        {pf:.3f}")
    print(f"  {'─'*60}")
    print(f"  Total Trades:         {total}")
    print(f"  Ganadores:            {wins} ({win_rate:.1f}%)")
    print(f"  Perdedores:           {losses} ({100-win_rate:.1f}%)")
    print(f"  {'─'*60}")
    print(f"  Ganancia Promedio:    {avg_win:+.2f}%")
    print(f"  Pérdida Promedio:     {avg_loss:+.2f}%")
    print(f"  Mejor Trade:          #{best_trade['#']} → {best_trade['Ret%']:+.2f}% ({best_trade['Entrada']})")
    print(f"  Peor Trade:           #{worst_trade['#']} → {worst_trade['Ret%']:+.2f}% ({worst_trade['Entrada']})")
    print(f"  {'─'*60}")
    print(f"  Max Drawdown Equity:  {max_dd:.2f}%")
    print(f"  Giveback Promedio:    {avg_giveback:.2f}%")
    print(f"  Duración Prom Trade:  {avg_duration:.1f} días")
    print(f"  {'='*60}")


def main():
    cache_path = '../../bot_alpha_portfolio/stable_v25_prototype/wf_cache_4h_8760_now.pkl'
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} no encontrado.")
        return
        
    cache = pd.read_pickle(cache_path)
    symbols = ['ETHUSDT', 'SOLUSDT']
    
    configs = [
        {"name": "V36 Base (Estructural EMA)", "trailing_pct": None, "hard_sl": None},
        {"name": "T-Stop 5% Agresivo (Sin Filtro)", "trailing_pct": 0.05, "hard_sl": None},
        {"name": "Smart Trailing 5% (Activación > 15%)", "trailing_pct": 0.05, "hard_sl": None, "trailing_activation": 0.15},
        {"name": "Smart Trailing 5% (Activación > 25%)", "trailing_pct": 0.05, "hard_sl": None, "trailing_activation": 0.25},
    ]
    
    from datetime import datetime, timedelta
    last_month_start = datetime.now() - timedelta(days=40) # Filtro de último mes (40 días para cubrir todo el mes pasado)
    
    for sym in symbols:
        df = cache[sym].copy()
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        
        # Indicadores
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)
        
        # Señales
        df['bull_trend'] = df['ema50'] > df['ema200']
        df['enter_long'] = (df['bull_trend']) & (~df['bull_trend'].shift(1).fillna(False)) & (df['close'] > df['ema50'])
        
        print(f"\n>>>> ANALISIS: ÚLTIMO MES ({last_month_start.strftime('%Y-%m-%d')} a Hoy)")
        for config in configs:
            trade_log, equity_series = run_backtest(df, config)
            print_full_report(sym, trade_log, equity_series, config["name"], start_date=last_month_start)


if __name__ == '__main__':
    main()
