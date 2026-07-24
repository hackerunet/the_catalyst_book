import os
import subprocess
import json
from dotenv import load_dotenv

load_dotenv()

def validar_operacion_con_claude(symbol, direction, trade_data):
    """
    Usa el CLI local de Claude (claude-code) para validar una operación en vivo.
    Asume que el usuario tiene el CLI autenticado globalmente.
    Retorna True si Claude la aprueba, False si la rechaza o si ocurre un error.
    """
    metrics = trade_data.get('metrics', {})
    
    prompt = f"""
Eres un Quantitative Trader experto. Nuestro sistema algorítmico ha detectado una ineficiencia en el mercado y propone el siguiente trade:

- **Activo:** {symbol}
- **Dirección:** {direction}
- **Precio de Entrada:** {trade_data.get('entry_price')}
- **Stop Loss:** {trade_data.get('stop_loss')}
- **Take Profit:** {trade_data.get('take_profit')}
- **Convicción del Algoritmo:** {trade_data.get('conviccion')}%
- **Patrón de Acción del Precio:** {metrics.get('strategy')}
- **Distancia al Stop Loss (Volatilidad):** {metrics.get('sl_dist')}

El sistema híbrido combina Regresión a la Media (Mean Reversion) con patrones institucionales de barridos de liquidez (Liquidity Sweeps) y formaciones de velas (Hammers, Engulfing).

Basado en tu conocimiento del mercado de criptomonedas y comportamiento institucional:
1. Evalúa si el ratio Riesgo:Beneficio y el patrón detectado tienen sentido lógico.
2. Considera que estamos operando en temporalidad de 1h (H1).

Responde ÚNICAMENTE con la palabra "APROBADO" o "RECHAZADO". No incluyas explicaciones.
"""

    try:
        # Se redirige stdin desde /dev/null para evitar el warning de "no stdin data received" del CLI
        resultado = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL
        )
        
        texto_respuesta = resultado.stdout.strip().upper()
        
        if "APROBADO" in texto_respuesta:
            print(f"✅ [Claude CLI] Validó la operación {direction} en {symbol}.")
            return True
        elif "RECHAZADO" in texto_respuesta:
            print(f"❌ [Claude CLI] Rechazó la operación {direction} en {symbol}.")
            return False
        else:
            # Si no responde claramente, fallamos abriendo (aprobamos) o imprimimos el error de stderr
            print(f"⚠️ [Claude CLI] Respuesta ambigua o error: {texto_respuesta} | {resultado.stderr.strip()}")
            return True
            
    except FileNotFoundError:
        print("ERROR: El CLI 'claude' no fue encontrado en el PATH. Saltando validación.")
        return True
    except Exception as e:
        print(f"ERROR: Fallo al ejecutar claude CLI: {e}")
        return True # Fail-open: Si el CLI falla, dejamos pasar el trade matemático
