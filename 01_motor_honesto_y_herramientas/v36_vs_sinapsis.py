#!/usr/bin/env python3
"""V36 vs Sinapsis-lateral — ¿cuál va a la cuenta que se fondea?

Compara con las métricas que un copiador ve en el perfil de Binance:
  Win Rate | ROI | Profit Factor | Max DD | MDD-90d (el gate) | horizontes rodantes
Cada uno en SU canasta/timeframe validado (no son intercambiables: V36 es 15m top-4,
Sinapsis es 4h con los 6 originales) + su OOB.

Sinapsis auto-chequea reproducción contra repro_sinapsis.py (879/34.93%/+77.91%/1.41).
SOLO LECTURA.
"""
import numpy as np

from suavizado_v37 import (correr, equity_mtm, CFG_V36, CACHE_4H_ORIG, CACHE_4H_OOB,
                           CACHE_15M_4Y, TOP4)

CACHE_15M_OOB = 'wf_cache_15m_70080_2026-06-11_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl'
OOB6 = ['BTCUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']

# OJO: correr() hace setattr sobre el config GLOBAL — los flags NO se resetean solos
# entre corridas. Cada config declara EXPLÍCITAMENTE todo lo que la otra toca, o V36
# hereda el exhaustion-exit de Sinapsis (bug detectado: daba 5545 trades en vez de 1065).
CFG_SINAPSIS = dict(INTERVAL='4h', ENTRY_MODE='patrones', EXIT_MODE='tendencia',
                    EXHAUSTION_EXIT_TENDENCIA=True, EXHAUSTION_LATERAL_VELAS=2,
                    BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=8)
CFG_V36_LIMPIO = dict(CFG_V36, EXHAUSTION_EXIT_TENDENCIA=False)   # <- el reseteo explícito

REPRO = dict(trades=879, wr=34.93, roi=77.91, pf=1.41)   # repro_sinapsis.py
REPRO_V36 = dict(trades=1065, wr=25.63)                  # medido hoy con CFG_V36 limpio


def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    gan = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    per = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)

    eq = equity_mtm(bt, balance_inicial=balance)
    v = eq.values
    t0 = eq.index.values.astype('datetime64[s]').astype(np.int64)
    mdd = float(np.max((np.maximum.accumulate(v) - v) / np.maximum.accumulate(v))) * 100
    mdd90, j = 0.0, 0
    for i in range(len(v)):
        while t0[i] - t0[j] > 90 * 24 * 3600:
            j += 1
        pk = np.max(v[j:i + 1])
        mdd90 = max(mdd90, (pk - v[i]) / pk)
    anios = (t0[-1] - t0[0]) / (365.25 * 24 * 3600)
    roi = 100 * pnl / balance
    return dict(n=n, wr=100 * w / n, roi=roi, pf=gan / per if per else 9.99,
                mdd=mdd, mdd90=mdd90 * 100, anios=anios,
                cagr=100 * ((1 + roi / 100) ** (1 / anios) - 1), eq=eq)


def horizontes(eq):
    v = eq.values
    t = eq.index.values.astype('datetime64[s]').astype(np.int64)
    out = {}
    for dias in (30, 180, 365):
        sec = dias * 24 * 3600
        rs, j = [], 0
        for i in range(len(v)):
            while t[i] - t[j] > sec:
                j += 1
            if t[i] - t[j] >= sec * 0.95:
                rs.append((v[i] - v[j]) / v[j] * 100)
        rs = np.array(rs) if rs else np.array([0.0])
        out[dias] = (np.median(rs), np.min(rs), 100 * np.mean(rs > 0))
    return out


def main():
    res = {}
    print("Corriendo Sinapsis IS (4h, 6 símbolos)...")
    res[('SIN', 'IS')] = medir(correr(CACHE_4H_ORIG, CFG_SINAPSIS))
    m = res[('SIN', 'IS')]
    ok = (abs(m['n'] - REPRO['trades']) <= 3 and abs(m['wr'] - REPRO['wr']) <= .6
          and abs(m['roi'] - REPRO['roi']) <= .6 and abs(m['pf'] - REPRO['pf']) <= .05)
    print(f"  repro vs repro_sinapsis.py: {'✅ EXACTO' if ok else '🔴 DIFIERE'}"
          f" ({m['n']} trades, WR {m['wr']:.2f}%, {m['roi']:+.2f}%, PF {m['pf']:.2f})")

    print("Corriendo Sinapsis OOB...")
    res[('SIN', 'OOB')] = medir(correr(CACHE_4H_OOB, CFG_SINAPSIS))

    print("Corriendo V36 IS (15m, top-4)... (tarda)")
    res[('V36', 'IS')] = medir(correr(CACHE_15M_4Y, CFG_V36_LIMPIO, symbols=TOP4))
    m6 = res[('V36', 'IS')]
    ok6 = (abs(m6['n'] - REPRO_V36['trades']) <= 3 and abs(m6['wr'] - REPRO_V36['wr']) <= .6)
    print(f"  control anti-leak V36: {'✅ LIMPIO' if ok6 else '🔴 CONFIG CONTAMINADO'}"
          f" ({m6['n']} trades, WR {m6['wr']:.2f}% — esperado {REPRO_V36['trades']}/"
          f"{REPRO_V36['wr']}%)")
    if not ok6:
        raise SystemExit("V36 heredó flags de Sinapsis — no confiar en la comparación")

    print("Corriendo V36 OOB (15m)...")
    res[('V36', 'OOB')] = medir(correr(CACHE_15M_OOB, CFG_V36_LIMPIO, symbols=OOB6))

    print(f"\n{'='*92}\n  V36 vs SINAPSIS — lo que ve un copiador en el perfil de Binance\n{'='*92}")
    print(f"  {'motor':10} {'ventana':6} {'años':>5} {'trades':>7} {'WIN RATE':>9} {'ROI':>9}"
          f" {'CAGR':>8} {'PF':>6} {'MaxDD':>7} {'MDD-90d':>9} {'gate':>6}")
    print(f"  {'-'*10} {'-'*6} {'-'*5} {'-'*7} {'-'*9} {'-'*9} {'-'*8} {'-'*6} {'-'*7} {'-'*9} {'-'*6}")
    for (mot, ven), r in res.items():
        gate = '✅' if r['mdd90'] < 25 else '🔴'
        print(f"  {mot:10} {ven:6} {r['anios']:>5.1f} {r['n']:>7} {r['wr']:>8.2f}% "
              f"{r['roi']:>+8.1f}% {r['cagr']:>+7.1f}% {r['pf']:>6.3f} {r['mdd']:>6.1f}% "
              f"{r['mdd90']:>8.1f}% {gate:>6}")

    print(f"\n  --- Horizontes rodantes (mediana / peor / % positivo) ---")
    print(f"  {'motor':10} {'ventana':6} {'1 mes':>24} {'6 meses':>24} {'1 año':>24}")
    for (mot, ven), r in res.items():
        h = horizontes(r['eq'])
        s = ''.join(f"{h[d][0]:>+7.1f}%{h[d][1]:>+7.1f}%{h[d][2]:>7.0f}%  " for d in (30, 180, 365))
        print(f"  {mot:10} {ven:6} {s}")

    print(f"\n  >>> WIN RATE — el número que decide la venta:")
    for mot in ('V36', 'SIN'):
        i, o = res[(mot, 'IS')]['wr'], res[(mot, 'OOB')]['wr']
        print(f"      {mot:10} IS {i:.2f}%  ->  OOB {o:.2f}%   "
              f"({'GENERALIZA ✅' if abs(i-o) < 4 else 'se degrada 🔴'})")


if __name__ == '__main__':
    main()
