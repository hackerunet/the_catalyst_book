"""
diario_forense_claude.py — Sistema de Trazabilidad Forense V22 (reparado)

Graba dos tipos de entradas por operación:
  1. APERTURA: Contexto completo de mercado cuando el bot toma la decisión
     (velas previas + indicadores + RÉGIMEN detectado).
  2. CIERRE (post-mortem): Las 3 velas siguientes + PnL final + análisis de Claude CLI
     (best-effort) — pero la escritura de la entrada estructurada YA NO depende de que
     Claude responda. Esta es la corrección clave respecto a V21.

Diagnóstico de V21 (ver OPCION_1_BETA.md sección 1.4): de 9 aperturas registradas solo
se grabaron 5 cierres, y las 5 mostraban "Claude no disponible" — es decir, cuando el
subproceso `claude -p ...` lanzaba una EXCEPCIÓN (FileNotFoundError / TimeoutExpired,
no solo un código de salida distinto de cero), el bloque `run_analysis` completo abortaba
ANTES de llegar a `_append_entry`, perdiendo el registro estructurado del cierre por completo.

Corrección V22: se separa en tres pasos independientes — (1) serializar velas post-cierre,
(2) intentar el análisis de Claude envuelto en su propio try/except exhaustivo (nunca
puede impedir lo siguiente), y (3) escribir SIEMPRE la entrada CIERRE en el JSONL. El
análisis de Claude pasa a ser un "addendum" de mejor esfuerzo, no un requisito.

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
      - Los valores de todos los indicadores en la vela de entrada (incluye los nuevos
        de V22: ATR%, ADX, Bandas de Bollinger, RSI).
      - Las últimas 10 velas cerradas antes de la entrada (contexto OHLCV).
      - La razón de entrada (puerta, patrón, régimen detectado, condicionales evaluadas).
    No bloquea el motor — se ejecuta en hilo separado.
    """
    def _grabar():
        try:
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
                    "ATR_pct":        round(float(row.get("ATR_pct",       0)), 4),
                    "ADX":            round(float(row.get("ADX",           0)), 2),
                    "BB_Upper":       round(float(row.get("BB_Upper",      0)), 4),
                    "BB_Mid":         round(float(row.get("BB_Mid",        0)), 4),
                    "BB_Lower":       round(float(row.get("BB_Lower",      0)), 4),
                    "RSI":            round(float(row.get("RSI",           0)), 2),
                })

            vela_decision = velas_previas[-1] if velas_previas else {}

            precio = trade_data.get("entry_price", 0)
            razon = {
                "puerta":         trade_data.get("puerta", "A"),
                "patron":         trade_data.get("pattern", "N/A"),
                "regimen":        trade_data.get("regimen", "N/D"),
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
                    "ADX_nivel":           round(vela_decision.get("ADX", 0), 1),
                    "RSI_nivel":           round(vela_decision.get("RSI", 0), 1),
                    "Donchian_rotura":     "RESISTENCIA" if direction == "LONG" else "SOPORTE",
                    "volumen_vs_media":    "ALTO" if vela_decision.get("volume", 0) > vela_decision.get("Volume_MA", 1) else "NORMAL",
                }
            }

            entry = {
                "tipo":          "APERTURA",
                "trade_id":      trade_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "symbol":        symbol,
                "direction":     direction,
                "razon":         razon,
                "velas_contexto_previo": velas_previas,
            }
            _append_entry(entry)
            print(f"📋 [Forense] APERTURA registrada → {symbol} {direction} | Puerta {trade_data.get('puerta','A')} | Régimen: {trade_data.get('regimen','N/D')} | Patrón: {trade_data.get('pattern', 'N/A')}", flush=True)

        except Exception as e:
            print(f"⚠️ [Forense] Error en registrar_apertura ({symbol}): {e}")

    threading.Thread(target=_grabar, daemon=True).start()


def analisis_post_mortem_claude(symbol, direction, trade_data, siguientes_velas_df, pnl_final, exit_reason, trade_id="N/A"):
    """
    Llama al cerrar un trade. Captura las 3 velas siguientes + PnL + (si está disponible)
    un análisis cualitativo generado por Claude CLI, y guarda todo en trade_forensics.jsonl.

    REPARACIÓN V22: la escritura de la entrada estructurada (paso 3) ya NO depende de que
    el subproceso de Claude tenga éxito. Antes, una excepción al invocar `claude -p ...`
    (binario ausente del PATH del proceso, timeout, etc.) abortaba la función completa y
    el cierre quedaba sin registrar — por eso 4 de 9 trades nunca llegaron a tener su
    entrada CIERRE. Ahora cada paso está aislado: lo mínimo garantizado es siempre el
    registro estructurado (datos de mercado + PnL + razón de salida), y el análisis de
    Claude es un "addendum" de mejor esfuerzo que jamás bloquea ese registro.
    """
    def run_analysis():
        # --- PASO 1: Serializar velas posteriores al cierre (siempre se intenta) ---
        velas_post = []
        try:
            for i in range(min(3, len(siguientes_velas_df))):
                row = siguientes_velas_df.iloc[i] if hasattr(siguientes_velas_df, 'iloc') else {}
                velas_post.append({
                    "time":     str(row.get("time", f"vela_{i+1}")),
                    "open":     round(float(row.get("open",  0)), 4),
                    "high":     round(float(row.get("high",  0)), 4),
                    "low":      round(float(row.get("low",   0)), 4),
                    "close":    round(float(row.get("close", 0)), 4),
                    "volume":   round(float(row.get("volume",0)), 2),
                    "is_green": bool(row.get("Is_Green", False)),
                })
        except Exception as e:
            print(f"⚠️ [Forense] Error serializando velas post-cierre ({symbol}): {e}")

        # --- PASO 2: Análisis cualitativo de Claude — BEST EFFORT, aislado por completo ---
        analisis = "Claude no fue invocado (módulo de análisis cualitativo deshabilitado o pendiente)."
        try:
            precio_entrada = trade_data.get('entry_price', trade_data.get('sl', 0))
            prompt = f"""Eres un Analista Cuantitativo Forense especializado en crypto. Analiza este trade cerrado:

ACTIVO: {symbol} | DIRECCIÓN: {direction} | PUERTA: {trade_data.get('puerta', 'A')} | RÉGIMEN: {trade_data.get('regimen_mercado', trade_data.get('regimen', 'N/D'))} | PATRÓN: {trade_data.get('pattern', 'N/A')}
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
                ["claude", "--model", "claude-opus-4-8", "-p", prompt],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                timeout=45
            )
            if resultado.returncode == 0 and resultado.stdout.strip():
                analisis = resultado.stdout.strip()
            else:
                detalle_err = (resultado.stderr or "").strip() or f"código de salida {resultado.returncode}, sin stderr"
                analisis = f"Claude no disponible: {detalle_err[:200]}"
        except FileNotFoundError:
            analisis = "Claude no disponible: binario 'claude' no encontrado en el PATH del proceso del simulador."
        except subprocess.TimeoutExpired:
            analisis = "Claude no disponible: tiempo de espera agotado (45s) al invocar el análisis post-mortem."
        except Exception as e:
            analisis = f"Claude no disponible: excepción inesperada al invocar el análisis — {str(e)[:150]}"

        # --- PASO 3: Registrar SIEMPRE la entrada estructurada (esto es lo que alimenta el análisis) ---
        try:
            entry = {
                "tipo":              "CIERRE",
                "trade_id":          trade_id,
                "timestamp_utc":     datetime.now(timezone.utc).isoformat(),
                "symbol":            symbol,
                "direction":         direction,
                "puerta":            trade_data.get("puerta", "A"),
                "regimen":           trade_data.get("regimen_mercado", trade_data.get("regimen", "N/D")),
                "pnl":               pnl_final,
                "exit_reason":       exit_reason,
                "velas_post_entrada": velas_post,
                "claude_analysis":   analisis,
            }
            _append_entry(entry)
            resultado_str = "✅ GANADOR" if pnl_final > 0 else "❌ PERDEDOR"
            print(f"🔬 [Forense] CIERRE guardado → {symbol} {direction} | {resultado_str} ${pnl_final:.4f} | Puerta {trade_data.get('puerta','A')} | Régimen {trade_data.get('regimen_mercado', trade_data.get('regimen','N/D'))}", flush=True)
        except Exception as e:
            print(f"⚠️ [Forense] ERROR CRÍTICO: no se pudo registrar la entrada CIERRE de {symbol} ({trade_id}): {e}")

    threading.Thread(target=run_analysis, daemon=True).start()
