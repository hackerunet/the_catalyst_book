#!/usr/bin/env python3
"""¿Cómo se ve una cuenta lead que corre SOLO Sinapsis? (el escenario vendible)

Mide exactamente lo que un copiador ve en el perfil de Binance:
  ROI | Win Rate | Max Drawdown | MDD-90d (el gate) | Sharpe
más el perfil de horizontes (ventanas rodantes) que decide si un humano AGUANTA.

Auto-chequeo: la config de acá debe REPRODUCIR el repro_sinapsis.py validado
(+77.91% | 879 trades | WR 34.93% | PF 1.41). Si no reproduce, no se confía.
SOLO LECTURA.
"""
import numpy as np

from suavizado_v37 import (correr, equity_mtm, CFG_V26, CACHE_4H_ORIG,
                           CACHE_4H_OOB, RISK_DEFAULT)

# Config de Sinapsis-lateral (= sinapsis_lateral/config.py, la que corre viva)
CFG_SINAPSIS = dict(INTERVAL='4h', ENTRY_MODE='patrones', EXIT_MODE='tendencia',
                    EXHAUSTION_EXIT_TENDENCIA=True, EXHAUSTION_LATERAL_VELAS=2,
                    BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=8)
REPRO = dict(pnl_pct=77.91, trades=879, wr=34.93, pf=1.41)


def metricas(bt, tag, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    gan = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    per = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    pf = gan / per if per else float('inf')

    # equity_mtm -> pd.Series indexada por DatetimeIndex
    eq = equity_mtm(bt, balance_inicial=balance)
    v = eq.values
    t0 = eq.index.values.astype('datetime64[s]').astype(np.int64)
    pico = np.maximum.accumulate(v)
    mdd = float(np.max((pico - v) / pico)) * 100

    # MDD-90d: peor caída medida contra el pico DENTRO de la ventana de 90 días
    # (la métrica del gate de Binance), no contra el pico histórico global.
    mdd90 = 0.0
    vent = 90 * 24 * 3600
    j = 0
    for i in range(len(v)):
        while t0[i] - t0[j] > vent:
            j += 1
        pk = np.max(v[j:i + 1])
        mdd90 = max(mdd90, (pk - v[i]) / pk)
    mdd90 *= 100

    print(f"\n{'=' * 78}\n  {tag}\n{'=' * 78}")
    print(f"  Operaciones: {n}  |  ganadoras {w}  |  **WIN RATE {100*w/n:.2f}%**")
    print(f"  ROI: {100*pnl/balance:+.2f}%   |  Profit Factor {pf:.3f}")
    print(f"  Max Drawdown: {mdd:.1f}%  |  **MDD-90d: {mdd90:.1f}%**"
          f"  (gate copy-trade: <25% {'✅' if mdd90 < 25 else '🔴'})")
    return dict(n=n, wr=100 * w / n, roi=100 * pnl / balance, pf=pf,
                mdd=mdd, mdd90=mdd90, eq=eq)


def horizontes(eq, tag):
    """Ventanas rodantes: ¿qué ve alguien que evalúa en 1/3/6/12 meses?"""
    v = eq.values
    t = eq.index.values.astype('datetime64[s]').astype(np.int64)
    print(f"\n  --- Horizontes rodantes ({tag}) — lo que ve un copiador ---")
    print(f"  {'ventana':>10} {'mediana':>9} {'p10':>8} {'peor':>8} {'% positivo':>11}")
    for dias, nom in [(30, '1 mes'), (90, '3 meses'), (180, '6 meses'), (365, '1 año')]:
        sec = dias * 24 * 3600
        rs = []
        j = 0
        for i in range(len(v)):
            while t[i] - t[j] > sec:
                j += 1
            if t[i] - t[j] >= sec * 0.95:
                rs.append((v[i] - v[j]) / v[j] * 100)
        if not rs:
            continue
        rs = np.array(rs)
        print(f"  {nom:>10} {np.median(rs):>8.1f}% {np.percentile(rs,10):>7.1f}%"
              f" {np.min(rs):>7.1f}% {100*np.mean(rs>0):>10.1f}%")


def main():
    print("Corriendo Sinapsis-lateral (4h, patrones + salida-lateral)...")
    bt = correr(CACHE_4H_ORIG, CFG_SINAPSIS)
    m = metricas(bt, 'CUENTA LEAD SOLO-SINAPSIS — canasta original (in-sample, 4 años)')

    # --- auto-chequeo de reproducción ---
    print(f"\n  --- Chequeo vs repro_sinapsis.py (config validada) ---")
    ok = True
    for k, esp in REPRO.items():
        got = dict(pnl_pct=m['roi'], trades=m['n'], wr=m['wr'], pf=m['pf'])[k]
        bien = abs(got - esp) <= (0.6 if k != 'trades' else 3)
        ok &= bien
        print(f"    {k:9} esperado {esp:>8} | obtenido {got:>8.2f}  {'OK' if bien else 'DIFIERE'}")
    print(f"  >>> {'REPRODUCE la config validada ✅' if ok else 'NO reproduce — no confiar 🔴'}")

    horizontes(m['eq'], 'in-sample')

    print("\nCorriendo OOB (canasta nunca usada para diseñar)...")
    bo = correr(CACHE_4H_OOB, CFG_SINAPSIS)
    mo = metricas(bo, 'SOLO-SINAPSIS — canasta OOB (la prueba honesta)')
    horizontes(mo['eq'], 'OOB')

    print(f"\n{'=' * 78}\n  COMPARACIÓN PARA EL PERFIL DE BINANCE\n{'=' * 78}")
    print(f"  {'cuenta':28} {'WR':>8} {'ROI 4a':>9} {'MDD-90d':>9}")
    print(f"  {'V26 sola (récord de hoy)':28} {'18.08%':>8} {'+130.6%':>9} {'19.8%':>9}")
    print(f"  {'Sinapsis sola (in-sample)':28} {m['wr']:>7.2f}% {m['roi']:>+8.1f}% {m['mdd90']:>8.1f}%")
    print(f"  {'Sinapsis sola (OOB)':28} {mo['wr']:>7.2f}% {mo['roi']:>+8.1f}% {mo['mdd90']:>8.1f}%")


if __name__ == '__main__':
    main()
