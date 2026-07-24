"""
atr_percentil_continua_15m.py — Candidato #2 (investigación scalping, 2026-07-01):
"momentum de continuación filtrado por ATR-percentile alto".

NO modifica ningún archivo del proyecto. Importa el motor honesto de
stable_v25_prototype/ (BacktestV25 + estrategia.py) SIN TOCAR DISCO y aplica
un monkeypatch en memoria de `estrategia.evaluar_entrada` (mismo patrón ya
usado en el proyecto por v24-fable/validacion_honesta.py para el null de
Monte Carlo: "monkeypatches ... engine file untouched").

Hipótesis: la familia de entrada 'continua' (tendencia alineada, SIN capa de
patrones de vela — la version MÁS agresiva/de mayor cadencia ya implementada)
fue la PEOR configuración jamás medida en el proyecto a 1h (−8.69%/62d,
2026-06-11, "los patrones SÍ servían de freno de cadencia"). La pregunta:
¿restringir esas entradas al top-40% de volatilidad reciente (percentil ATR
>= 60, mismo umbral ya usado — sin éxito por estar roto — en el intento de
V28 backtest_reconocimiento.py) mejora el ratio WR/costo lo suficiente para
compensar la MAYOR cadencia de 'continua' (sin filtro de patrón)?

NOTA IMPORTANTE (hallazgo, no hipótesis): config.VOLATILIDAD_MIN_PCT existe
en v28_copilot/config.py pero NO está conectado a ningún filtro real en
estrategia.py/indicadores.py/backtest.py de esa carpeta — es un flag muerto.
El número documentado en el libro (2026-06-12, filtro ATR>=p60 mejora +1R/+2R
con -19% de señales) NO es reproducible con el código actual de v28_copilot
(verificado: correr backtest_reconocimiento.py --vol-min 60 da resultados
IDÉNTICOS con y sin el filtro). Este script implementa el filtro de forma
independiente (fuera de v28_copilot, sin tocarlo) para medir el mecanismo.

Definición (NO escaneada — percentil 60 reusa el mismo umbral redondo del
intento original de V28, no un número nuevo):
  ATR_PCTL_MIN = 60  → percentil del ATR actual sobre su ventana móvil de
  las últimas ATR_PCTL_WINDOW=200 velas (~misma escala que WARMUP_CANDLES).
  Si el ATR actual no está en el percentil >=60 de su propio histórico
  reciente, la entrada se bloquea (mismo símbolo puede entrar en otro
  momento si la volatilidad sube).

Metodología: ventaneo NO solapado (igual que V29-B) sobre el cache 15m de 2
años ya existente (wf_cache_15m_70080_2026-06-11.pkl, reusado — SIN
descarga), interval=15m, entrada='continua', salida='escalera' (default —
TP corto, apto para el perfil "profits agresivos cortos" del nicho), costos
TAKER por defecto (0.05%/lado — el peor caso honesto para un scalper que no
garantiza fills maker). Null Monte Carlo reducido (mc=30) por ventana para
una señal aproximada de "¿supera al azar?" sin consumir todo el presupuesto
de tiempo de esta investigación.

Uso: python3 atr_percentil_continua_15m.py
Salida: atr_percentil_continua_15m_resultado.json + tabla por stdout.
"""
import json
import os
import random
import sys

import numpy as np
import pandas as pd

DIR_V25 = '/Users/hackerunet/openclaw-binance-trading/bot_alpha_portfolio/stable_v25_prototype'
sys.path.insert(0, DIR_V25)

import config          # noqa: E402
import estrategia      # noqa: E402
import walkforward as wf  # noqa: E402
from backtest import BALANCE_INICIAL  # noqa: E402

ATR_PCTL_MIN = 60
ATR_PCTL_WINDOW = 200

_orig_evaluar_entrada = estrategia.evaluar_entrada


def _evaluar_entrada_filtrada(df, rs_basket=None, rs_symbol=None, reentrada_armada=False):
    if len(df) >= ATR_PCTL_WINDOW:
        atr_now = df['ATR'].iloc[-1]
        if pd.isna(atr_now):
            return None
        ventana_atr = df['ATR'].iloc[-ATR_PCTL_WINDOW:]
        pctl = float((ventana_atr < atr_now).mean() * 100)
        if pctl < ATR_PCTL_MIN:
            return None
    return _orig_evaluar_entrada(df, rs_basket=rs_basket, rs_symbol=rs_symbol,
                                  reentrada_armada=reentrada_armada)


def correr_pase(raw, wins, usar_filtro, mc, seed=42):
    estrategia.evaluar_entrada = _evaluar_entrada_filtrada if usar_filtro else _orig_evaluar_entrada
    rng = random.Random(seed)
    filas = []
    for k, slices in enumerate(wins, 1):
        bt = wf.correr_ventana(slices)
        r = bt.resumen()
        n_por_sym = {}
        for t in bt.trades:
            n_por_sym[t['symbol']] = n_por_sym.get(t['symbol'], 0) + 1
        fila = {
            'ventana': k, 'inicio': r['window_start'], 'fin': r['window_end'],
            'trades': r['trades'], 'wr': r['win_rate'], 'pf': r['profit_factor'],
            'pnl_pct': r['net_pnl_pct'], 'bh_pct': r['benchmark_buy_hold_pct'],
        }
        if mc > 0 and r['trades'] > 0:
            nulls = [wf.mc_run(bt.dfs, n_por_sym, rng) for _ in range(mc)]
            nulls_pct = sorted(p / BALANCE_INICIAL * 100 for p in nulls)
            mejor_que = sum(1 for p in nulls_pct if p < r['net_pnl_pct'])
            fila['percentil_vs_null'] = round(mejor_que / len(nulls_pct) * 100, 1)
            fila['null_mediana_pct'] = round(nulls_pct[len(nulls_pct) // 2], 2)
        filas.append(fila)
        print(f"  [{'FILTRO' if usar_filtro else 'BASE  '}] V{k:02d} {fila['inicio'][:10]}"
              f"→{fila['fin'][:10]} | trades {fila['trades']:>3} | WR {fila['wr']:>5}% | "
              f"PF {fila['pf']} | PnL {fila['pnl_pct']:+6.2f}% | B&H {fila['bh_pct']:+7.2f}%"
              + (f" | pctl {fila.get('percentil_vs_null','—')}" if mc else ''))
        sys.stdout.flush()
    return filas


def agregar(filas):
    pnls = [f['pnl_pct'] for f in filas]
    pctls = [f['percentil_vs_null'] for f in filas if 'percentil_vs_null' in f]
    return {
        'ventanas': len(filas),
        'trades_total': sum(f['trades'] for f in filas),
        'pnl_mediana_pct': round(sorted(pnls)[len(pnls) // 2], 2) if pnls else None,
        'pnl_suma_pct': round(sum(pnls), 2),
        'ventanas_positivas': f"{sum(1 for p in pnls if p > 0)}/{len(filas)}",
        'pctl_vs_null_mediano': round(sorted(pctls)[len(pctls) // 2], 1) if pctls else None,
    }


def main():
    config.INTERVAL = '15m'
    config.COOLDOWN_CANDLES = 2 * 0.25
    config.ENTRY_MODE = 'continua'   # sin capa de patrones — la entrada más agresiva ya implementada
    # EXIT_MODE queda en default 'escalera' (TP corto + deciles — perfil "profits cortos")
    # BT_TAKER_FEE/BT_SLIPPAGE quedan en default (0.0005/0.0005, taker honesto)

    end_ms = int(pd.Timestamp('2026-06-11').timestamp() * 1000)
    raw = wf.cargar_historico(70080, end_ms, '15m_70080_2026-06-11')  # reusa cache existente
    wins = wf.ventanas(raw, 6000)  # mismas 11 ventanas que V29-B
    print(f"\n{len(wins)} ventanas de 6000 velas 15m\n")

    print("--- PASE 1: BASELINE (continua, sin filtro ATR) ---")
    filas_base = correr_pase(raw, wins, usar_filtro=False, mc=30)
    print("\n--- PASE 2: FILTRADO (continua, ATR percentil >= 60) ---")
    filas_filt = correr_pase(raw, wins, usar_filtro=True, mc=30)

    estrategia.evaluar_entrada = _orig_evaluar_entrada  # restaurar (higiene, mismo proceso)

    agg_base = agregar(filas_base)
    agg_filt = agregar(filas_filt)

    print("\n" + "=" * 70)
    print("RESUMEN — candidato #2: momentum 'continua' filtrado por ATR-percentil")
    print("=" * 70)
    print(f"BASELINE  : {agg_base}")
    print(f"FILTRADO  : {agg_filt}")

    out = {'baseline': agg_base, 'filtrado': agg_filt,
           'baseline_detalle': filas_base, 'filtrado_detalle': filas_filt,
           'config': {'interval': '15m', 'entry_mode': 'continua', 'exit_mode': 'escalera',
                      'atr_pctl_min': ATR_PCTL_MIN, 'atr_pctl_window': ATR_PCTL_WINDOW,
                      'fee': config.BT_TAKER_FEE, 'slippage': config.BT_SLIPPAGE,
                      'window': 6000, 'years': 2, 'end': '2026-06-11', 'mc': 30}}
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'atr_percentil_continua_15m_resultado.json')
    with open(ruta, 'w') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\nGuardado: {ruta}")


if __name__ == '__main__':
    main()
