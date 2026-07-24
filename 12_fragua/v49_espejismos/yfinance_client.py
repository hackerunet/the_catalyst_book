import yfinance as yf
import pandas as pd
import numpy as np

class YFinanceClient:
    def klines_paginated(self, symbol, total_candles, end_time_ms=None):
        """
        Descarga velas usando yfinance y las formatea como el BinanceClient original.
        yfinance tiene un límite de 730 días para temporalidad de 1h.
        """
        # Calcular fecha inicio aprox. total_candles * 1h
        # 1 año = 8760 velas
        
        # En yfinance, el símbolo para EURUSD es "EURUSD=X"
        yf_sym = f"{symbol[:3]}{symbol[3:6]}=X" if "USD" in symbol else symbol
        
        # Como es 1h, usamos 720 days max.
        days = total_candles / 24
        period = f"{int(days)+1}d"
        
        print(f"Descargando {period} de {yf_sym} en yfinance (límite 730d max para 1h)")
        df = yf.download(yf_sym, period=period, interval='1h', progress=False)
        
        if df.empty:
            raise ValueError(f"No se pudieron descargar datos para {yf_sym}")
            
        # Limpiar multiindex de yf.download si lo hay
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        # yfinance index es tz-aware o no. Convertimos a timestamp ms
        df = df.reset_index()
        df.rename(columns={'Datetime': 'time', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        
        # Remove timezone info to match Binance format
        if df['time'].dt.tz is not None:
            df['time'] = df['time'].dt.tz_convert('UTC').dt.tz_localize(None)
        
        # Si no hay volumen, usar array de 0 o 1
        if df['volume'].sum() == 0 or df['volume'].isnull().all():
            df['volume'] = np.random.randint(100, 1000, size=len(df)) # Fake volume para evitar div/0
            
        # Limitar al total_candles pedido
        if len(df) > total_candles:
            df = df.iloc[-total_candles:]
            
        df.reset_index(drop=True, inplace=True)
        return df
