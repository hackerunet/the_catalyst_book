#!/usr/bin/env python3
"""V71 — salida por APAGADO DE CLÍMAX sobre V26. Dos variantes pre-registradas.

  V71-A (CLIMAX_FADE_EXIT_TENDENCIA): arma RSI>70 / dispara RSI<=70, desde el
         inicio del trade.
  V71-B (CLIMAX_FADE_FUNNEL, idea del usuario): lo mismo, pero SOLO se activa
         tras un round-trip (pico>=50 -> negativo) + pico nuevo. El flip manda
         en la primera pierna; el RSI manda en la segunda.

Métrica: corrida CONTINUA 4 años (per Test C), null MC con el MISMO mecanismo,
IS + OOB. Criterio pre-registrado en el libro. SOLO LECTURA (flags default OFF).
"""
import numpy as np

from suavizado_v37 import (correr, equity_mtm, CFG_V26, CACHE_4H_ORIG, CACHE_4H_OOB)

BASE = dict(roi=130.59, n=426, wr=18.08, pf=1.918)


def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    if not n:
        return dict(n=0, wr=0, roi=0, pf=0, mdd=0, motivos={})
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    eq = equity_mtm(bt, balance_inicial=balance)
    v = eq.values
    mdd = float(np.max((np.maximum.accumulate(v) - v) / np.maximum.accumulate(v))) * 100
    mot = {}
    for t in tr:
        k = str(t.get('exit_reason', '?')).split('(')[0].strip()[:26]
        a = mot.setdefault(k, [0, 0.0])
        a[0] += 1
        a[1] += t['pnl']
    return dict(n=n, wr=100 * w / n, roi=100 * pnl / balance,
                pf=g / p if p else 9.99, mdd=mdd, motivos=mot)


def corrida(nombre, cfg_extra, cache):
    cfg = dict(CFG_V26, CLIMAX_FADE_EXIT_TENDENCIA=False, CLIMAX_FADE_FUNNEL=False)
    cfg.update(cfg_extra)
    bt = correr(cache, cfg)
    m = medir(bt)
    print(f"\n  {nombre}")
    print(f"    PnL {m['roi']:+7.2f}%  | trades {m['n']:>4} | WR {m['wr']:5.2f}%"
          f" | PF {m['pf']:5.3f} | MaxDD {m['mdd']:5.1f}%")
    for k, (c, s) in sorted(m['motivos'].items(), key=lambda kv: -abs(kv[1][1])):
        print(f"      {k:28} n={c:>4}  ${s:>+9.2f}")
    return m


def main():
    print("=" * 78)
    print("  V71 — APAGADO DE CLÍMAX (RSI vuelve bajo 70) sobre V26 · continuo 4 años")
    print("=" * 78)

    print("\n### CANASTA ORIGINAL (in-sample) ###")
    ctrl = corrida("CONTROL (flags OFF) — debe dar el baseline", {}, CACHE_4H_ORIG)
    ok = (abs(ctrl['roi'] - BASE['roi']) < .02 and ctrl['n'] == BASE['n'])
    print(f"    >>> {'✅ reproduce el baseline' if ok else '🔴 REGRESIÓN — abortar'}")
    if not ok:
        raise SystemExit("control falló")

    a_is = corrida("V71-A · fade desde el inicio", dict(CLIMAX_FADE_EXIT_TENDENCIA=True),
                   CACHE_4H_ORIG)
    b_is = corrida("V71-B · FUNNEL (flip 1ra pierna, RSI 2da)",
                   dict(CLIMAX_FADE_FUNNEL=True), CACHE_4H_ORIG)

    print("\n### CANASTA OOB ###")
    ctrl_o = corrida("CONTROL OOB (flags OFF)", {}, CACHE_4H_OOB)
    a_oob = corrida("V71-A OOB", dict(CLIMAX_FADE_EXIT_TENDENCIA=True), CACHE_4H_OOB)
    b_oob = corrida("V71-B OOB", dict(CLIMAX_FADE_FUNNEL=True), CACHE_4H_OOB)

    print("\n" + "=" * 78)
    print("  RESUMEN — criterio: PnL>0 Y PF>1 Y costo de retorno PEQUEÑO vs beneficio de DD")
    print("=" * 78)
    print(f"  {'config':34} {'PnL':>9} {'PF':>7} {'MaxDD':>7} {'Δ PnL rel':>10} {'Δ DD rel':>9}")
    for nom, m, base in [("IS  baseline (flip)", ctrl, ctrl),
                         ("IS  V71-A fade", a_is, ctrl),
                         ("IS  V71-B funnel", b_is, ctrl),
                         ("OOB baseline (flip)", ctrl_o, ctrl_o),
                         ("OOB V71-A fade", a_oob, ctrl_o),
                         ("OOB V71-B funnel", b_oob, ctrl_o)]:
        dp = (m['roi'] - base['roi']) / abs(base['roi']) * 100 if base['roi'] else 0
        dd = (m['mdd'] - base['mdd']) / base['mdd'] * 100 if base['mdd'] else 0
        print(f"  {nom:34} {m['roi']:>+8.2f}% {m['pf']:>7.3f} {m['mdd']:>6.1f}%"
              f" {dp:>+9.1f}% {dd:>+8.1f}%")


if __name__ == '__main__':
    main()
