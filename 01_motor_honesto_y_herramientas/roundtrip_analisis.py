#!/usr/bin/env python3
"""Análisis del aviso de ROUND-TRIP (V26 4h / V36 15m).

Replica el disparo EXACTO del bot vivo (ejecutor.gestionar_salidas):
    pico = max(progreso favorable visto)
    if pico >= ALERTA_ROUNDTRIP_MIN_PICO (50):
        if prog_ahora < 0 and (avisado_en is None or pico > avisado_en):
            -> AVISO, avisado_en = pico

...sobre TODO el backtest del motor honesto, y responde:
  Q1  ¿Por qué el aviso siempre llega en 0/negativo? (¿es la condición o el mercado?)
  Q2  ¿Cuántos trades pican >=50% y NUNCA disparan el aviso? (el complemento invisible)
  Q3  Tras un aviso, ¿cuántas veces la tendencia NO se recuperó nunca?
  Q4  Distribución del PICO al momento del aviso (>50%, >80%, >100%...)
  Q5  Tras el aviso, ¿hasta dónde se recuperó? (nuevo máximo, >50%, >80%)

CAVEAT de método: el bot vivo evalúa tick a tick; aquí el camino se reconstruye
vela a vela con los extremos (high/low). Es la misma aproximación pesimista que
usa monstruos.py — puede disparar el aviso en la misma vela que hizo el pico.
SOLO LECTURA: no toca config de referencia ni ejecuta nada en Binance.
"""
import argparse

import numpy as np

from backtest import pnl_neto_cierre
from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4

MIN_PICO = 50.0  # = config.ALERTA_ROUNDTRIP_MIN_PICO (V26 y V36)


def prog(px, entry, tp):
    """Progreso hacia el objetivo: positivo = a favor (vale LONG y SHORT)."""
    return (px - entry) / (tp - entry) * 100.0


def camino(t, df_t, tarr):
    """Reconstruye (favorable, adverso, i0) vela a vela durante la vida del trade."""
    s, e, tp, side = t['symbol'], t['entry_price'], t['tp'], t['type']
    i0 = int(np.searchsorted(tarr[s], np.datetime64(t['entry_time'])))
    i1 = int(np.searchsorted(tarr[s], np.datetime64(t['exit_time']))) + 1
    d = df_t[s]
    hi = d['high'].values[i0:i1]
    lo = d['low'].values[i0:i1]
    if len(hi) == 0:
        return None, None, i0
    if side == 'LONG':
        return prog(hi, e, tp), prog(lo, e, tp), i0
    return prog(lo, e, tp), prog(hi, e, tp), i0


def precio_en_prog(t, p):
    """Precio que corresponde a un progreso dado (inverso de prog())."""
    return t['entry_price'] + (p / 100.0) * (t['tp'] - t['entry_price'])


def analizar(engine):
    cfg = dict(CFG_V26 if engine == 'v26' else CFG_V36)
    cache = CACHE_4H_ORIG if engine == 'v26' else CACHE_15M_4Y
    syms = None if engine == 'v26' else TOP4
    bt = correr(cache, cfg, symbols=syms)
    df_t = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in df_t.items()}

    trades, eventos = [], []
    for t in [x for x in bt.trades if x['status'] == 'CERRADA']:
        fav, adv, i0 = camino(t, df_t, tarr)
        if fav is None:
            continue
        pico_final = float(np.max(fav))

        # --- réplica exacta del disparo vivo ---
        run_peak, avisado_en = 0.0, None
        evs_trade = []
        for k in range(len(fav)):
            run_peak = max(run_peak, fav[k])       # vivo: peak se actualiza primero
            if run_peak >= MIN_PICO and adv[k] < 0 \
                    and (avisado_en is None or run_peak > avisado_en):
                avisado_en = run_peak
                evs_trade.append((k, run_peak))

        for (k, pico_aviso) in evs_trade:
            post = fav[k + 1:]
            max_post = float(np.max(post)) if len(post) else float(adv[k])
            eventos.append(dict(
                sym=t['symbol'], side=t['type'], pico_aviso=float(pico_aviso),
                prog_aviso=float(adv[k]), max_post=max_post,
                nuevo_max=bool(max_post > pico_aviso),
                recup_50=bool(max_post >= 50), recup_80=bool(max_post >= 80),
                recup_pos=bool(max_post > 0),
                pnl=float(t['pnl']), motivo=t.get('exit_reason'),
                gano=bool(t['pnl'] > 0)))

        # --- contrafactual: cerrar EN el PRIMER aviso (costos reales) ---
        # CAVEAT (lección V27-A/V32): es de PRIMER ORDEN — cerrar antes libera
        # el símbolo y desplaza toda la secuencia posterior. SOBREESTIMA.
        pnl_cf = None
        if evs_trade:
            k0, _ = evs_trade[0]
            px_cf = precio_en_prog(t, adv[k0])
            ts_cf = df_t[t['symbol']]['time'].values[i0 + k0]
            pnl_cf = float(pnl_neto_cierre(t, px_cf, ts_cf))

        trades.append(dict(
            sym=t['symbol'], peak=pico_final, pnl=float(t['pnl']),
            motivo=t.get('exit_reason'), n_avisos=len(evs_trade),
            aviso=bool(evs_trade), gano=bool(t['pnl'] > 0),
            pnl_cf=pnl_cf, toco_neg=bool(np.min(adv) < 0)))
    return trades, eventos


def pct(n, d):
    return f"{(100.0 * n / d):5.1f}%" if d else "  n/a"


def reporte(engine):
    trades, ev = analizar(engine)
    tag = 'V26 (4h, cruce+flip)' if engine == 'v26' else 'V36 (15m, patrones+flip)'
    print(f"\n{'=' * 74}\n  AVISO DE ROUND-TRIP — {tag}\n{'=' * 74}")
    print(f"Trades cerrados: {len(trades)} | PnL total: ${sum(t['pnl'] for t in trades):,.2f}")

    # ---- Q2: el complemento invisible ----
    picaron = [t for t in trades if t['peak'] >= MIN_PICO]
    con_av = [t for t in picaron if t['aviso']]
    sin_av = [t for t in picaron if not t['aviso']]
    print(f"\n--- Q2: de los que PICAN >={MIN_PICO:.0f}% (n={len(picaron)}) ---")
    print(f"  DISPARARON aviso (tocaron negativo): {len(picaron) and len(con_av):>3}"
          f" ({pct(len(con_av), len(picaron))})  PnL ${sum(t['pnl'] for t in con_av):>9,.2f}"
          f"  ganan {pct(sum(t['gano'] for t in con_av), len(con_av))}")
    print(f"  NUNCA dispararon (jamás negativo): {len(sin_av):>5}"
          f" ({pct(len(sin_av), len(picaron))})  PnL ${sum(t['pnl'] for t in sin_av):>9,.2f}"
          f"  ganan {pct(sum(t['gano'] for t in sin_av), len(sin_av))}")

    # ---- Q1: ¿es la condición o el mercado? ----
    print(f"\n--- Q1: ¿el aviso 'siempre llega en negativo' por definición? ---")
    print(f"  Avisos con prog>=0 al dispararse: 0 de {len(ev)} — "
          f"es IMPOSIBLE (la condición es prog<0)")
    print(f"  Trades que pican >={MIN_PICO:.0f}% y tocan negativo alguna vez: "
          f"{pct(len(con_av), len(picaron))} de los que pican")

    if not ev:
        print("\n(sin eventos de aviso)")
        return
    n = len(ev)
    print(f"\n--- Q4: PICO al momento del aviso (n={n} avisos) ---")
    for lo, hi in [(50, 80), (80, 100), (100, 200), (200, 500), (500, 10**9)]:
        g = [e for e in ev if lo <= e['pico_aviso'] < hi]
        et = f">{lo}%" if hi > 10**8 else f"{lo}-{hi}%"
        if g:
            print(f"  pico {et:>9}: {len(g):>3} avisos ({pct(len(g), n)})"
                  f"  PnL ${sum(e['pnl'] for e in g):>9,.2f}"
                  f"  terminan ganando {pct(sum(e['gano'] for e in g), len(g))}")
    print(f"  >>> pico >50%: {sum(1 for e in ev if e['pico_aviso'] > 50):>3} avisos"
          f"  ({pct(sum(1 for e in ev if e['pico_aviso'] > 50), n)})")
    print(f"  >>> pico >80%: {sum(1 for e in ev if e['pico_aviso'] > 80):>3} avisos"
          f"  ({pct(sum(1 for e in ev if e['pico_aviso'] > 80), n)})")

    # ---- Q5 / Q3: qué pasó DESPUÉS del aviso ----
    print(f"\n--- Q5: DESPUÉS del aviso (n={n}) ---")
    print(f"  Hizo un pico NUEVO (mayor al del aviso): {sum(e['nuevo_max'] for e in ev):>3}"
          f" ({pct(sum(e['nuevo_max'] for e in ev), n)})")
    print(f"  Volvió a positivo:                      {sum(e['recup_pos'] for e in ev):>3}"
          f" ({pct(sum(e['recup_pos'] for e in ev), n)})")
    print(f"  Se recuperó a >=50%:                    {sum(e['recup_50'] for e in ev):>3}"
          f" ({pct(sum(e['recup_50'] for e in ev), n)})")
    print(f"  Se recuperó a >=80%:                    {sum(e['recup_80'] for e in ev):>3}"
          f" ({pct(sum(e['recup_80'] for e in ev), n)})")

    nunca = [e for e in ev if not e['nuevo_max']]
    print(f"\n--- Q3: avisos donde la tendencia NO se recuperó (sin pico nuevo) ---")
    print(f"  n={len(nunca)} ({pct(len(nunca), n)})  PnL ${sum(e['pnl'] for e in nunca):>9,.2f}"
          f"  ganan {pct(sum(e['gano'] for e in nunca), len(nunca))}")
    reco = [e for e in ev if e['nuevo_max']]
    print(f"  vs. avisos que SÍ hicieron pico nuevo: n={len(reco)}"
          f"  PnL ${sum(e['pnl'] for e in reco):>9,.2f}"
          f"  ganan {pct(sum(e['gano'] for e in reco), len(reco))}")

    print(f"\n--- ¿Y si CERRABAS en el primer aviso? (contrafactual, costos reales) ---")
    print(f"  CAVEAT (lección V27-A/V32): es de PRIMER ORDEN — cerrar libera el símbolo")
    print(f"  y desplaza la secuencia posterior. SOBREESTIMA el beneficio de cerrar.")
    real = sum(t['pnl'] for t in con_av)
    cf = sum(t['pnl_cf'] for t in con_av if t['pnl_cf'] is not None)
    print(f"  Dejándolos correr (REAL):      ${real:>9,.2f}   ({len(con_av)} trades)")
    print(f"  Cerrando en el primer aviso:   ${cf:>9,.2f}")
    print(f"  >>> Cerrar en el aviso {'GANA' if cf > real else 'PIERDE'} "
          f"${abs(cf - real):,.2f} vs dejar correr")
    print(f"  Prog. medio al avisar: {np.mean([e['prog_aviso'] for e in ev]):.0f}%"
          f" (siempre negativo = siempre cerrás en pérdida)")
    print(f"  Máx recuperación post-aviso (mediana): "
          f"{np.median([e['max_post'] for e in ev]):.0f}% | "
          f"p90 {np.percentile([e['max_post'] for e in ev], 90):.0f}%")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['v26', 'v36', 'ambos'], default='ambos')
    a = ap.parse_args()
    for eng in (['v26', 'v36'] if a.engine == 'ambos' else [a.engine]):
        reporte(eng)
