"""V42 y V43 — Meta-allocador dinámico M4: Volatility Targeting y Risk Parity.

Pre-registro: el libro sección "M4 - V42/V43".
V42: Volatility Targeting sobre la cartera 50/50 estática.
V43: Risk Parity (asignación de capital inversamente proporcional a la volatilidad de cada estrategia).
"""
import os
import sys
import numpy as np
import pandas as pd

DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIR_V37 = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype')

CSV_V26 = os.path.join(DIR_V37, 'v37_eq_v26_base.csv')
CSV_V36 = os.path.join(DIR_V37, 'v37_eq_v36_4y.csv')

VOL_WINDOW = 90
TARGET_VOL = 0.60  # 60% annualized volatility target for V42

def max_drawdown_90d(eq_series):
    roll_peak = eq_series.rolling('90D').max()
    dd = (roll_peak - eq_series) / roll_peak * 100.0
    return float(dd.max())

def max_drawdown_global(eq_series):
    peak = eq_series.cummax()
    dd = (peak - eq_series) / peak * 100.0
    return float(dd.max())

def cagr_pct(eq_series):
    dias = (eq_series.index[-1] - eq_series.index[0]).days
    anios = dias / 365.25
    if anios <= 0: return None
    total = float(eq_series.iloc[-1] / eq_series.iloc[0])
    if total <= 0: return -100.0
    return round((total ** (1.0 / anios) - 1.0) * 100.0, 2)

def rolling_365d(eq_series):
    r365 = (eq_series / eq_series.shift(365) - 1.0).dropna() * 100.0
    if len(r365) == 0: return None
    return {
        'mediana': round(float(r365.median()), 2),
        'p10': round(float(r365.quantile(0.10)), 2),
        'minimo': round(float(r365.min()), 2),
    }

def print_metrics(name, eq_series):
    cagr = cagr_pct(eq_series)
    dd90 = max_drawdown_90d(eq_series)
    ddg = max_drawdown_global(eq_series)
    r365 = rolling_365d(eq_series)
    pnl = round(float(eq_series.iloc[-1] / eq_series.iloc[0] - 1.0) * 100.0, 2)
    print(f"[{name}]")
    print(f"  PnL total: {pnl}% | CAGR: {cagr}%")
    print(f"  Max DD Global: {round(ddg, 2)}% | Max DD 90d: {round(dd90, 2)}%")
    if r365:
        print(f"  Rolling 365d -> Mediana: {r365['mediana']}%, p10: {r365['p10']}%, Min: {r365['minimo']}%")
    print("-" * 60)


def main():
    if not os.path.exists(CSV_V26) or not os.path.exists(CSV_V36):
        print("Faltan los archivos de equity de V37. Debes correr suavizado_v37.py primero.")
        return

    df26 = pd.read_csv(CSV_V26, index_col=0, parse_dates=True)
    df36 = pd.read_csv(CSV_V36, index_col=0, parse_dates=True)
    
    # Align dates
    df = df26.join(df36, how='inner', lsuffix='_v26', rsuffix='_v36')
    df['ret_v26'] = df['equity_v26'].pct_change().fillna(0)
    df['ret_v36'] = df['equity_v36'].pct_change().fillna(0)
    
    # Baseline: Static 50/50 Combo
    df['ret_combo'] = 0.5 * df['ret_v26'] + 0.5 * df['ret_v36']
    df['eq_combo'] = (1.0 + df['ret_combo']).cumprod() * 1000.0
    
    print_metrics("BASELINE (V37 50/50 Estático)", df['eq_combo'])

    # ---------------------------------------------------------
    # V42: Volatility Targeting on Combo
    # ---------------------------------------------------------
    # Rolling annualized vol of the combo
    df['combo_vol_90d_ann'] = df['ret_combo'].rolling(VOL_WINDOW).std() * np.sqrt(365)
    # Forward fill starting NaNs using first valid to avoid dropping early data entirely
    df['combo_vol_90d_ann'] = df['combo_vol_90d_ann'].bfill()
    
    # Calculate scale factor: Target Vol / Realized Vol
    df['leverage'] = TARGET_VOL / df['combo_vol_90d_ann']
    # Let's not clip to see the true mathematical effect of Vol-Targeting
    # df['leverage'] = df['leverage'].clip(upper=1.0)
    
    df['ret_v42'] = df['ret_combo'] * df['leverage']
    df['eq_v42'] = (1.0 + df['ret_v42']).cumprod() * 1000.0
    
    print_metrics(f"V42 (Vol-Targeting, Target={int(TARGET_VOL*100)}%, Uncapped)", df['eq_v42'])
    print(f"  Vol Realizada Mediana: {round(df['combo_vol_90d_ann'].median()*100, 2)}%")
    print(f"  Leverage Mediano: {round(df['leverage'].median(), 2)}x")
    print("-" * 60)

    # ---------------------------------------------------------
    # V43: Risk Parity
    # ---------------------------------------------------------
    df['vol_v26_90d'] = df['ret_v26'].rolling(VOL_WINDOW).std()
    df['vol_v36_90d'] = df['ret_v36'].rolling(VOL_WINDOW).std()
    df['vol_v26_90d'] = df['vol_v26_90d'].bfill()
    df['vol_v36_90d'] = df['vol_v36_90d'].bfill()
    
    # Risk parity weights (inversely proportional to vol)
    inv_vol26 = 1.0 / df['vol_v26_90d']
    inv_vol36 = 1.0 / df['vol_v36_90d']
    sum_inv = inv_vol26 + inv_vol36
    
    df['w_v26'] = inv_vol26 / sum_inv
    df['w_v36'] = inv_vol36 / sum_inv
    
    df['ret_v43'] = df['w_v26'] * df['ret_v26'] + df['w_v36'] * df['ret_v36']
    df['eq_v43'] = (1.0 + df['ret_v43']).cumprod() * 1000.0
    
    print_metrics("V43 (Risk Parity)", df['eq_v43'])


if __name__ == '__main__':
    main()
