"""
diario_forense_claude.py — Sistema de Trazabilidad Forense V2

Graba dos tipos de entradas por operación:
  1. APERTURA: Contexto completo de mercado cuando el bot toma la decisión (velas previas + indicadores).
  2. CIERRE (post-mortem): Las 3 velas siguientes + PnL final + análisis de Claude CLI.

Formato de archivo: JSON Lines → 'trade_forensics.jsonl'
Cada línea es un JSON autónomo con tipo 'APERTURA' o 'CIERRE'.
"""
import os
import json
import threading
import subprocess
from datetime import datetime, timezone


FORENSICS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_forensics.jsonl")


def _append_entry(entry: dict):
    """Escribe una entrada en el archivo de forma thread-safe."""
    try:
        with open(FORENSICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"⚠️ [Forense] Error escribiendo en trade_forensics.jsonl: {e}")


def registrar_apertura(trade_id: str, symbol: str, direction: str, trade_data: dict, df_contexto):
    """
    Llama en el instante que se abre un trade.
    Captura:
      - Los valores de todos los indicadores en la vela de entrada.
      - Las últimas 10 velas cerradas antes de la entrada (contexto OHLCV).
      - La razón de entrada (puerta, patrón, condicionales evaluadas).
    No bloquea el motor — se ejecuta en hilo separado.
    """
    def _grabar():
        try:
            # Últimas 10 velas de contexto previo (OHLCV + indicadores clave)
            velas_previas = []
            for i in range(max(0, len(df_contexto) - 10), len(df_contexto)):
                row = df_contexto.iloc[i]
                velas_previas.append({
                    "time":           str(row.get("time", "")),
                    "open":           round(float(row.get("open",  0)), 4),
                    "high":           round(float(row.get("high",  0)), 4),
                    "low":            round(float(row.get("low",   0)), 4),
                    "close":          round(float(row.get("close", 0)), 4),
                    "volume":         round(float(row.get("volume", 0)), 2),
                    "is_green":       bool(row.get("Is_Green", False)),
                    "body":           round(float(row.get("Body",  0)), 4),
                    "MA_7":           round(float(row.get("MA_7",  0)), 4),
                    "EMA_9":          round(float(row.get("EMA_9", 0)), 4),
                    "MA_99":          round(float(row.get("MA_99", 0)), 4),
                    "Donchian_High":  round(float(row.get("Donchian_High", 0)), 4),
                    "Donchian_Low":   round(float(row.get("Donchian_Low",  0)), 4),
                    "MACD":           round(float(row.get("MACD",          0)), 6),
                    "MACD_Signal":    round(float(row.get("MACD_Signal",   0)), 6),
                    "MACD_Hist":      round(float(row.get("MACD_Hist",     0)), 6),
                    "Volume_MA":      round(float(row.get("Volume_MA",     0)), 2),
                })

            # Vela de decisión (la última)
            vela_decision = velas_previas[-1] if velas_previas else {}

            # Razones de decisión legibles
            precio = trade_data.get("entry_price", 0)
            razon = {
                "puerta":         trade_data.get("puerta", "A"),
                "patron":         trade_data.get("pattern", "N/A"),
                "conviccion_pct": trade_data.get("conviccion", 0),
                "precio_entrada": precio,
                "stop_loss":      trade_data.get("stop_loss", 0),
                "take_profit":    trade_data.get("take_profit", 0),
                "qty":            trade_data.get("qty", 0),
                "r_ratio":        round((trade_data.get("take_profit", 0) - precio) /
                                        max((precio - trade_data.get("stop_loss", precio * 0.97)), 0.0001), 2)
                                  if direction == "LONG" else
                                  round((precio - trade_data.get("take_profit", 0)) /
                                        max((trade_data.get("stop_loss", precio * 1.03) - precio), 0.0001), 2),
                "indicadores_en_decision": {
                    "MA_7_vs_MA99":        "SOBRE" if vela_decision.get("MA_7", 0) > vela_decision.get("MA_99", 0) else "BAJO",
                    "EMA_9_vs_MA99":       "SOBRE" if vela_decision.get("EMA_9", 0) > vela_decision.get("MA_99", 0) else "BAJO",
                    "MACD_direccion":      "ALCISTA" if vela_decision.get("MACD_Hist", 0) > 0 else "BAJISTA",
                    "Donchian_rotura":     "RESISTENCIA" if direction == "LONG" else "SOPORTE",
                    "volumen_vs_media":    "ALTO" if vela_decision.get("volume", 0) > vela_decision.get("Volume_MA", 1) else "NORMAL",
                }
            }

            entry = {
                "tipo":         "APERTURA",
                "trade_id":     trade_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "symbol":       symbol,
                "direction":    direction,
                "razon":        razon,
                "velas_contexto_previo": velas_previas,
            }
            _append_entry(entry)
            print(f"📋 [Forense] APERTURA registrada → {symbol} {direction} | Puerta {trade_data.get('puerta','A')} | Patrón: {trade_data.get('pattern', 'N/A')}", flush=True)

        except Exception as e:
            print(f"⚠️ [Forense] Error en registrar_apertura ({symbol}): {e}")

    threading.Thread(target=_grabar, daemon=True).start()


def analisis_post_mortem_claude(symbol, direction, trade_data, siguientes_velas_df, pnl_final, exit_reason, trade_id="N/A"):
    """
    Llama al cerrar un trade.
    Captura las 3 velas siguientes + PnL + análisis de Claude.
    Guarda todo en trade_forensics.jsonl.
    """
    def run_analysis():
        try:
            # Serializar velas siguientes
            velas_post = []
            for i in range(min(3, len(siguientes_velas_df))):
                row = siguientes_velas_df.iloc[i] if hasattr(siguientes_velas_df, 'iloc') else {}
                velas_post.append({
                    "time":    str(row.get("time", f"vela_{i+1}")),
                    "open":    round(float(row.get("open",  0)), 4),
                    "high":    round(float(row.get("high",  0)), 4),
                    "low":     round(float(row.get("low",   0)), 4),
                    "close":   round(float(row.get("close", 0)), 4),
                    "volume":  round(float(row.get("volume",0)), 2),
                    "is_green": bool(row.get("Is_Green", False)),
                })

            # Prompt para Claude
            precio_entrada = trade_data.get('entry_price', trade_data.get('sl', 0))
            prompt = f"""Eres un Analista Cuantitativo Forense especializado en crypto. Analiza este trade cerrado:

ACTIVO: {symbol} | DIRECCIÓN: {direction} | PUERTA: {trade_data.get('puerta', 'A')} | PATRÓN: {trade_data.get('pattern', 'N/A')}
ENTRADA: ${precio_entrada} | SL: ${trade_data.get('sl', 0)} | TP: ${trade_data.get('tp', 0)}
PnL FINAL: ${pnl_final:.4f} | RAZÓN DE SALIDA: {exit_reason}

VELAS POST-ENTRADA (1h):
{json.dumps(velas_post, indent=2)}

RESPONDE EN 3 SECCIONES:
1. VEREDICTO: ¿Fue una entrada correcta basándose en las velas siguientes? (1 oración)
2. DIAGNÓSTICO: ¿Qué pasó estructuralmente después de la entrada? (2-3 oraciones)
3. MEJORA: ¿Cómo el bot debería haber ajustado el SL/TP o evitado esta entrada? (1-2 oraciones)
"""

            resultado = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                timeout=30
            )
            analisis = resultado.stdout.strip() if resultado.returncode == 0 else f"Claude no disponible: {resultado.stderr.strip()[:100]}"

            entry = {
                "tipo":            "CIERRE",
                "trade_id":        trade_id,
                "timestamp_utc":   datetime.now(timezone.utc).isoformat(),
                "symbol":          symbol,
                "direction":       direction,
                "pnl":             pnl_final,
                "exit_reason":     exit_reason,
                "velas_post_entrada": velas_post,
                "claude_analysis": analisis,
            }
            _append_entry(entry)
            resultado_str = "✅ GANADOR" if pnl_final > 0 else "❌ PERDEDOR"
            print(f"🔬 [Forense] CIERRE guardado → {symbol} {direction} | {resultado_str} ${pnl_final:.4f}", flush=True)

        except Exception as e:
            print(f"⚠️ [Forense] Error en post_mortem ({symbol}): {e}")

    threading.Thread(target=run_analysis, daemon=True).start()
