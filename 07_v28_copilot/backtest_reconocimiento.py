"""
backtest_reconocimiento.py — V28_COPILOT: backtest de RECONOCIMIENTO (no PnL).

Pre-registro en el libro. Responde lo único que el copiloto promete:
  1. ¿Las entradas son OPORTUNAS? — % de señales que alcanzan +0.5R/+1R/+1.5R/
     +2R ANTES de tocar el SL (con TP=2R: progreso 25/50/75/100), y tiempo al pico.
  2. ¿prob_reversion está CALIBRADA? — en estados con progreso ≥20, ¿prob alta
     precede retrocesos reales (≥20 pts o stop en ≤6 velas) más que prob baja?
     Debe ser MONOTÓNICA para mostrarse como "probabilidad".
  3. Desglose por patrón disparador y ratio de volumen de entrada.

Corre el MISMO motor honesto (backtest.BacktestV25, modo copilot: stop + TP 2R,
sin pullback) sobre una ventana congelada. PnL se reporta solo como contexto.

Uso: python3 backtest_reconocimiento.py [--candles 1500] [--end 2026-06-11]
     [--vol-min 60]   ← reporta también con filtro de volatilidad
"""
import argparse

import pandas as pd

import config
import estrategia
from backtest import BacktestV25


class ColectorReconocimiento:
    """Sustituye al forense: captura por-vela (prob, progreso) y datos de entrada."""
    dir = '(reconocimiento, sin I/O)'

    def __init__(self):
        self.entrada = {}    # id -> {'vol_ratio': float|None}
        self.series = {}     # id -> [(ts, prob, prog)]

    def registrar_activacion(self, t, sub_df, extra):
        vma = sub_df['Volume_MA'].iloc[-1]
        vol = sub_df['volume'].iloc[-1]
        ratio = float(vol / vma) if (vma and not pd.isna(vma) and vma > 0) else None
        self.entrada[t['id']] = {'vol_ratio': ratio}

    def registrar_vela(self, t, vela, prob):
        prog = estrategia.calcular_progreso(t, vela['close'])
        self.series.setdefault(t['id'], []).append((vela['time'], prob, prog))

    def registrar_cierre(self, t):
        pass


def correr(candles, end_ms):
    bt = BacktestV25(candles, end_time_ms=end_ms)
    bt.forense = ColectorReconocimiento()
    bt.cargar_datos()
    bt.correr()
    return bt


def reporte(bt):
    col = bt.forense
    trades = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(trades)
    print(f"\nSeñales: {n} | ventana {bt.resumen()['window_start']} → "
          f"{bt.resumen()['window_end']}")
    if not n:
        return

    # --- 1. oportunidad de entrada (peak por cierres; OBJETIVO cuenta como 100) ---
    def peak_de(t):
        p = t.get('peak_progress', 0.0)
        if t['exit_reason'].startswith('OBJETIVO'):
            p = max(p, 100.0)
        return p

    print("\n--- OPORTUNIDAD DE ENTRADA (antes del SL; peak por cierres de vela, conservador) ---")
    for umbral, etiqueta in ((25, '+0.5R'), (50, '+1R'), (75, '+1.5R'), (100, '+2R (objetivo)')):
        k = sum(1 for t in trades if peak_de(t) >= umbral)
        print(f"  alcanza {etiqueta:14}: {k:4}/{n} = {k / n * 100:5.1f}%"
              + ("   ← barra pre-reg: ≥50%" if umbral == 25 else
                 "   ← barra pre-reg: ≥30%" if umbral == 50 else ""))
    sl_inmediato = sum(1 for t in trades
                       if 'STOP' in t['exit_reason'] and peak_de(t) < 10)
    print(f"  SL sin llegar ni al 10%: {sl_inmediato}/{n} = {sl_inmediato / n * 100:.1f}% "
          f"(el 'wrong almost immediately')")

    # tiempo al pico (solo señales que alcanzaron ≥25)
    tiempos = []
    for t in trades:
        if peak_de(t) >= 25 and t['id'] in col.series:
            s = col.series[t['id']]
            if s:
                ts_pico = max(s, key=lambda x: x[2])[0]
                tiempos.append((ts_pico - t['entry_time']) / pd.Timedelta(hours=1))
    if tiempos:
        tiempos.sort()
        print(f"  tiempo al pico (señales ≥+0.5R): mediana {tiempos[len(tiempos)//2]:.0f}h "
              f"| p90 {tiempos[int(len(tiempos)*0.9)]:.0f}h")

    # --- 2. calibración de prob_reversion ---
    print("\n--- CALIBRACIÓN prob_reversion (estados prog≥20; retroceso = −20pts o STOP en ≤6 velas) ---")
    buckets = {'<30': [], '30-45': [], '45-60': [], '>=60': []}
    for t in trades:
        s = col.series.get(t['id'], [])
        # punto terminal: progreso al precio de salida (cubre stops entre muestras)
        s = s + [(t['exit_time'], None, estrategia.calcular_progreso(t, t['exit_price']))]
        for i in range(len(s) - 1):
            ts, prob, prog = s[i]
            if prob is None or prog < 20:
                continue
            futuros = s[i + 1:i + 7]
            retro = any(p2 <= prog - 20 for _, _, p2 in futuros)
            b = ('<30' if prob < 30 else '30-45' if prob < 45 else
                 '45-60' if prob < 60 else '>=60')
            buckets[b].append(1 if retro else 0)
    tasas = []
    for b, vals in buckets.items():
        tasa = sum(vals) / len(vals) * 100 if vals else None
        tasas.append(tasa)
        print(f"  prob {b:6}: n={len(vals):5} | P(retroceso) = "
              f"{tasa:.1f}%" if vals else f"  prob {b:6}: n=0")
    validas = [t for t in tasas if t is not None]
    mono = all(validas[i] <= validas[i + 1] for i in range(len(validas) - 1)) \
        if len(validas) >= 2 else False
    print(f"  MONOTÓNICA: {'SÍ ✓ — mostrable como probabilidad' if mono else 'NO ✗ — mostrar como score heurístico'}")

    # --- 3. por patrón ---
    print("\n--- POR PATRÓN DISPARADOR (n, % ≥+0.5R, % ≥+1R, peak mediano) ---")
    grupos = {}
    for t in trades:
        grupos.setdefault(t['pattern'], []).append(t)
    for pat, ts_ in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
        peaks = sorted(peak_de(t) for t in ts_)
        a25 = sum(1 for p in peaks if p >= 25) / len(ts_) * 100
        a50 = sum(1 for p in peaks if p >= 50) / len(ts_) * 100
        print(f"  {pat[:44]:44} n={len(ts_):3} | ≥0.5R {a25:5.1f}% | "
              f"≥1R {a50:5.1f}% | peak med {peaks[len(peaks)//2]:.0f}%")

    # --- contexto (NO es el KPI) ---
    r = bt.resumen()
    print(f"\n[contexto, NO KPI] PnL si todo se cerrara mecánicamente en SL/2R: "
          f"{r['net_pnl_pct']:+.2f}% | WR {r['win_rate']}% | PF {r['profit_factor']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candles', type=int, default=1500)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--vol-min', type=float, default=None,
                    help='segunda pasada con filtro de volatilidad (percentil ATR)')
    args = ap.parse_args()
    end_ms = int(pd.Timestamp(args.end).timestamp() * 1000) if args.end else None

    print("=" * 78)
    print("RECONOCIMIENTO V28 — SIN filtro de volatilidad")
    print("=" * 78)
    reporte(correr(args.candles, end_ms))

    if args.vol_min is not None:
        config.VOLATILIDAD_MIN_PCT = args.vol_min
        print("\n" + "=" * 78)
        print(f"RECONOCIMIENTO V28 — CON filtro de volatilidad (percentil ATR ≥ {args.vol_min})")
        print("=" * 78)
        reporte(correr(args.candles, end_ms))


if __name__ == '__main__':
    main()
