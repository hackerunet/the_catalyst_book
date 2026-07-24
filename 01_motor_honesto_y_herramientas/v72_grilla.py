#!/usr/bin/env python3
"""V72 — GRILLA COMPLETA: ¿el win rate es un dial en TODOS los timeframes?

Tesis a falsificar: WR ≈ SL/(TP+SL), independiente del timeframe, de la canasta
y de la señal. Si se cumple en 15m / 1h / 4h / 1d y en 2 canastas, el win rate
queda demostrado como PARÁMETRO, no como habilidad.

Entrada FIJA en todas las filas: `cruce` (la de V26). Lo único que cambia es la
estructura de salida. WR medido NETO (pnl_neto_cierre) = "breakeven +1".
SOLO LECTURA. No toca ningún bot vivo.
"""
import pickle

import numpy as np

from suavizado_v37 import correr, equity_mtm, DIR

DIALS = (0.75, 2.0, 3.0, 4.0)

# (etiqueta, cache, símbolos|None, cooldown_horas)
GRILLA = [
    ('15m', 'orig', 'wf_cache_15m_140160_2026-06-11_top4.pkl', None, 2),
    ('15m', 'OOB',  'wf_cache_15m_70080_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl', None, 2),
    ('1h',  'orig', 'wf_cache_1h_26280_2026-06-11.pkl', None, 8),
    ('1h',  'OOB',  'wf_cache_1h_26280_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl', None, 8),
    ('4h',  'orig', 'wf_cache_4h_8760_2026-06-11_0000.pkl', None, 8),
    ('4h',  'OOB',  'wf_cache_4h_8760_2026-06-11_0000_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl', None, 8),
    ('1d',  'orig', 'wf_cache_crypto_1d.pkl', None, 8),
]

BASE = dict(ENTRY_MODE='cruce', PULLBACK_ARM_DECILE=999, TIME_STOP_HOURS=None,
            BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002,
            EXHAUSTION_EXIT_TENDENCIA=False, SCALE_OUT_TENDENCIA=False,
            REPLICA_TENDENCIA=False, TRAILING_STOP_TENDENCIA=False,
            CLIMAX_EXIT_TENDENCIA=False, CLIMAX_FADE_EXIT_TENDENCIA=False,
            CLIMAX_FADE_FUNNEL=False, REENTRY_POST_STOP=False)


def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    if not n:
        return None
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    v = equity_mtm(bt, balance_inicial=balance).values
    mdd = float(np.max((np.maximum.accumulate(v) - v) / np.maximum.accumulate(v))) * 100
    return dict(n=n, wr=100 * w / n, roi=100 * pnl / balance,
                pf=g / p if p else 9.99, mdd=mdd, gan=g / w if w else 0,
                per=p / (n - w) if n > w else 0)


def main():
    print("=" * 104)
    print("  V72 — GRILLA COMPLETA · ¿el win rate es un dial en TODOS los timeframes?")
    print("  Entrada FIJA: cruce. Solo cambia la salida. WR NETO de comisiones.")
    print("=" * 104)
    print(f"  {'TF':4} {'canasta':7} {'salida':16} {'trades':>6} {'WR NETO':>8} {'teór':>6} "
          f"{'error':>7} {'PnL':>10} {'PF':>6} {'MaxDD':>7} {'gan.prom':>9}")
    print(f"  {'-'*4} {'-'*7} {'-'*16} {'-'*6} {'-'*8} {'-'*6} {'-'*7} {'-'*10} {'-'*6} {'-'*7} {'-'*9}")

    errores = []
    for tf, canasta, cache, syms, cd in GRILLA:
        with open(f"{DIR}/{cache}", 'rb') as f:
            simbolos = list(pickle.load(f).keys())
        cfg0 = dict(BASE, INTERVAL=tf, COOLDOWN_CANDLES=cd)

        m = medir(correr(cache, dict(cfg0, EXIT_MODE='tendencia'), symbols=syms))
        if m:
            print(f"  {tf:4} {canasta:7} {'FLIP (correr)':16} {m['n']:>6} {m['wr']:>7.2f}% "
                  f"{'—':>6} {'—':>7} {m['roi']:>+9.2f}% {m['pf']:>6.3f} {m['mdd']:>6.1f}% "
                  f"${m['gan']:>+8.2f}")

        for slf in DIALS:
            m = medir(correr(cache, dict(cfg0, EXIT_MODE='escalera',
                                         SL_FRACTION_OF_TP=slf), symbols=syms))
            if not m:
                continue
            teo = 100 * slf / (1 + slf)
            err = m['wr'] - teo
            errores.append(err)
            print(f"  {tf:4} {canasta:7} {'TP/SL dial '+str(slf):16} {m['n']:>6} "
                  f"{m['wr']:>7.2f}% {teo:>5.0f}% {err:>+6.1f}pp {m['roi']:>+9.2f}% "
                  f"{m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")
        print()

    e = np.array(errores)
    print("=" * 104)
    print(f"  VEREDICTO — error del WR real vs el teórico SL/(TP+SL), sobre {len(e)} celdas:")
    print(f"    error medio {e.mean():+.2f}pp | error absoluto medio {np.abs(e).mean():.2f}pp"
          f" | máx {np.abs(e).max():.2f}pp")
    print(f"    >>> {'CONFIRMADO: el WR lo fija el dial, no la señal ni el timeframe'
                     if np.abs(e).mean() < 5 else 'el dial NO predice bien — revisar'}")
    print("=" * 104)


if __name__ == '__main__':
    main()
