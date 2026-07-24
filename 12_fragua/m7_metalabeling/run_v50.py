"""M7 - Meta-Labeling ML (López de Prado) sobre V26.

Entrena un Random Forest para predecir si una señal de V26 debe ser tomada o ignorada.
No genera señales nuevas, solo clasifica las existentes (1 = tomar, 0 = descartar).
Usa un split temporal simple (In-Sample / Out-Of-Sample) para validación.
"""
import os
import sys
import pandas as pd
import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
except ImportError:
    print("Falta scikit-learn. Por favor instalalo con 'pip install scikit-learn'")
    sys.exit(1)

# Añadir el path al backtest
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIR_BT = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype')
sys.path.insert(0, DIR_BT)

from backtest import BacktestV25, pnl_neto_cierre

def get_trades_and_features():
    # Corremos el backtest
    print("Corriendo motor honesto V26 para generar señales base...")
    bt = BacktestV25(candles=8760) # 4 años
    bt.cargar_datos()
    bt.correr()
    
    trades = bt.trades
    dfs = bt.dfs
    print(f"Backtest completado. {len(trades)} trades generados.")
    
    X = []
    y = []
    metadata = []
    
    for t in trades:
        sym = t['symbol']
        t_in = t['entry_time']
        t_out = t.get('exit_time', None)
        if t_out is None: continue # Trade abierto
        
        # PnL neto
        pnl = pnl_neto_cierre(t, t['exit_price'], t_out)
        label = 1 if pnl > 0 else 0
        
        # Features at entry time
        df = dfs[sym]
        row = df[df['time'] == t_in]
        if row.empty:
            continue
            
        row = row.iloc[0]
        
        # Extraemos features técnicas
        # Usando los nombres correctos de las columnas en df
        features = {
            'adx': float(row.get('ADX', 0)),
            'rsi': float(row.get('RSI', 0)),
            'atr_pct': float(row.get('ATR', 0)) / float(row['close']),
            'distancia_ema50': float(row['close']) / float(row.get('EMA_50', row['close'])) - 1.0,
            'distancia_ema200': float(row['close']) / float(row.get('EMA_200', row['close'])) - 1.0,
            'distancia_ema21': float(row['close']) / float(row.get('EMA_21', row['close'])) - 1.0,
            'macd_hist': float(row.get('MACD_Hist', 0)),
            'vol_ratio': float(row['volume']) / float(row.get('Volume_MA', 1)),
            'side': 1 if t['type'] == 'LONG' else -1
        }
        
        X.append(features)
        y.append(label)
        metadata.append({
            'symbol': sym,
            'entry_time': t_in,
            'pnl': pnl,
            'qty': t['qty'],
            'entry_price': t['entry_price'],
            'type': t['type']
        })
        
    return pd.DataFrame(X), pd.Series(y), pd.DataFrame(metadata)

def main():
    X, y, meta = get_trades_and_features()
    
    if len(X) == 0:
        print("No hay trades suficientes.")
        return
        
    # Ordenar por tiempo para el split temporal (Out-Of-Sample estricto)
    meta = meta.sort_values('entry_time')
    X = X.loc[meta.index]
    y = y.loc[meta.index]
    
    # Split 75% in-sample, 25% out-of-sample
    split_idx = int(len(X) * 0.75)
    
    X_train, y_train = X.iloc[:split_idx], y.iloc[:split_idx]
    X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]
    meta_train = meta.iloc[:split_idx]
    meta_test = meta.iloc[split_idx:]
    
    print(f"\nDatos In-Sample (Entrenamiento): {len(X_train)} trades")
    print(f"Datos Out-Of-Sample (Prueba): {len(X_test)} trades")
    
    # Modelo Random Forest (ideal para esto sin escalar)
    clf = RandomForestClassifier(n_estimators=100, max_depth=5, min_samples_leaf=5, random_state=42, class_weight='balanced')
    clf.fit(X_train, y_train)
    
    # Predecir
    y_pred_train = clf.predict(X_train)
    y_pred_test = clf.predict(X_test)
    
    print("\n--- Resultados Out-Of-Sample (OOS) ---")
    print(classification_report(y_test, y_pred_test, target_names=['Saltar (0)', 'Tomar (1)']))
    
    # Evaluar impacto en PnL
    pnl_base = meta_test['pnl'].sum()
    
    meta_test = meta_test.copy()
    meta_test['ml_pred'] = y_pred_test
    
    # PnL Filtrado (solo trades donde el modelo dice 1)
    trades_tomados = meta_test[meta_test['ml_pred'] == 1]
    pnl_ml = trades_tomados['pnl'].sum()
    
    winrate_base = (meta_test['pnl'] > 0).mean()
    winrate_ml = (trades_tomados['pnl'] > 0).mean() if len(trades_tomados) > 0 else 0
    
    print("\n--- Impacto Financiero OOS ---")
    print(f"PnL V26 Original (USD): ${round(pnl_base, 2)} ({len(meta_test)} trades, WR: {round(winrate_base*100, 1)}%)")
    print(f"PnL V26 + ML     (USD): ${round(pnl_ml, 2)} ({len(trades_tomados)} trades, WR: {round(winrate_ml*100, 1)}%)")
    print(f"Mejora en PnL: {round((pnl_ml - pnl_base) / abs(pnl_base) * 100 if pnl_base != 0 else 0, 2)}%")
    
    # Feature importance
    print("\nImportancia de las variables (Features):")
    importances = clf.feature_importances_
    features = X.columns
    for f, imp in sorted(zip(features, importances), key=lambda x: x[1], reverse=True):
        print(f"  {f}: {round(imp, 4)}")

if __name__ == '__main__':
    main()
