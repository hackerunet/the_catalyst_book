#!/usr/bin/env python3
"""¿Qué símbolos son los mayores PERDEDORES históricos, y qué pasa si los sacás?

Motiva: el récord de copy-trade se le vende a un HUMANO. Demasiadas operaciones
en rojo = producto invendible aunque el ROI cierre. Pregunta: ¿hay símbolos que
aporten sobre todo operaciones perdedoras y poco PnL (o negativo)?

Mide, por símbolo (4 años, motor honesto, config de referencia):
  n trades | perdedoras | WR | PnL | PnL/trade | aporte al CONTEO de rojas
y hace leave-one-out: sacar el símbolo X, ¿qué pasa con WR/PnL/# rojas?

CAVEAT (V57/Tarea#40): recortar por PnL histórico es curve-fitting por recency
(V35 recortó por LIQUIDEZ a propósito, y ADA —que era GANADOR— cayó). Esto MIDE;
no recomienda por sí solo. SOLO LECTURA.
"""
import argparse
from collections import defaultdict

import numpy as np

from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4


def stats(trades):
    n = len(trades)
    if not n:
        return dict(n=0, perd=0, wr=0.0, pnl=0.0, ppt=0.0)
    perd = sum(1 for t in trades if t['pnl'] <= 0)
    pnl = sum(t['pnl'] for t in trades)
    return dict(n=n, perd=perd, wr=100.0 * (n - perd) / n, pnl=pnl, ppt=pnl / n)


def reporte(engine):
    cfg = dict(CFG_V26 if engine == 'v26' else CFG_V36)
    cache = CACHE_4H_ORIG if engine == 'v26' else CACHE_15M_4Y
    syms = None if engine == 'v26' else TOP4
    bt = correr(cache, cfg, symbols=syms)
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']

    por = defaultdict(list)
    for t in tr:
        por[t['symbol']].append(t)

    tag = 'V26 (4h, cruce+flip)' if engine == 'v26' else 'V36 (15m, patrones+flip)'
    g = stats(tr)
    print(f"\n{'=' * 86}\n  POR SÍMBOLO — {tag}  [4 años]\n{'=' * 86}")
    print(f"  TOTAL: {g['n']} trades | {g['perd']} en rojo ({100*g['perd']/g['n']:.1f}%)"
          f" | WR {g['wr']:.1f}% | PnL ${g['pnl']:+,.2f}")

    print(f"\n  {'símbolo':10} {'trades':>7} {'rojas':>7} {'WR':>7} {'PnL':>10} {'PnL/trade':>10}"
          f" {'% de rojas':>11}")
    print(f"  {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*10} {'-'*11}")
    orden = sorted(por.items(), key=lambda kv: stats(kv[1])['pnl'])
    for s, ts in orden:
        st = stats(ts)
        print(f"  {s:10} {st['n']:>7} {st['perd']:>7} {st['wr']:>6.1f}% "
              f"${st['pnl']:>+9,.2f} ${st['ppt']:>+9.2f} {100*st['perd']/g['perd']:>10.1f}%")

    print(f"\n  --- LEAVE-ONE-OUT: ¿qué pasa si SACÁS ese símbolo? ---")
    print(f"  {'sacar':10} {'trades':>7} {'rojas':>7} {'WR':>7} {'PnL':>10} {'ΔPnL':>10}"
          f" {'Δrojas':>8}")
    print(f"  {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*10} {'-'*8}")
    for s, _ in orden:
        resto = [t for t in tr if t['symbol'] != s]
        st = stats(resto)
        print(f"  {s:10} {st['n']:>7} {st['perd']:>7} {st['wr']:>6.1f}% "
              f"${st['pnl']:>+9,.2f} ${st['pnl']-g['pnl']:>+9,.2f} "
              f"{st['perd']-g['perd']:>+8}")

    # ¿el WR mejora sacando a alguien? (la métrica que ve el copiador)
    mejor_wr = max(
        ((s, stats([t for t in tr if t['symbol'] != s])) for s, _ in orden),
        key=lambda kv: kv[1]['wr'])
    print(f"\n  >>> Sacar {mejor_wr[0]} da el MEJOR WR posible: {mejor_wr[1]['wr']:.1f}%"
          f" (vs {g['wr']:.1f}% actual) — y cuesta ${mejor_wr[1]['pnl']-g['pnl']:+,.2f} de PnL")
    print(f"  >>> Ningún recorte de 1 símbolo puede subir el WR arriba de"
          f" {mejor_wr[1]['wr']:.1f}% — el WR bajo es del MÉTODO, no de un símbolo.")
    return {s: stats(ts) for s, ts in por.items()}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['v26', 'v36'], default='v26')
    a = ap.parse_args()
    reporte(a.engine)
