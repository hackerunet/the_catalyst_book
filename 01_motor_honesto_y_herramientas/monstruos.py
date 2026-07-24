#!/usr/bin/env python3
"""¿Cuántos 'monstruos' (trades de ganancia enorme) hubo, y cómo los manejó el FLIP?
Reconstruye el camino intra-trade vela-por-vela sobre TODO el backtest de 4 años
del motor vivo (V26 4h o V36 15m) y responde:
  1) ¿cuántos monstruos? (pico de avance favorable ≥ umbral)
  2) de esos, ¿cuántos el flip cobró bien (poco giveback) vs soltó lo ganado?
  3) ¿cuántos retrocedieron a 0% (breakeven) y LUEGO hicieron un pico MAYOR al previo?
"""
import argparse, os
import numpy as np, pandas as pd
from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4

def prog(px, entry, tp):
    return (px - entry) / (tp - entry) * 100.0  # positivo = a favor (LONG y SHORT)

def analizar(engine):
    cfg = dict(CFG_V26 if engine == 'v26' else CFG_V36)
    cache = CACHE_4H_ORIG if engine == 'v26' else CACHE_15M_4Y
    syms = None if engine == 'v26' else TOP4
    bt = correr(cache, cfg, symbols=syms)
    # dfs indexados por tiempo para slicing rápido
    df_t = {s: d.reset_index(drop=True) for s, d in bt.dfs.items()}
    tarr = {s: d['time'].values for s, d in df_t.items()}

    trades = [t for t in bt.trades if t['status'] == 'CERRADA']
    filas = []
    for t in trades:
        s = t['symbol']; e = t['entry_price']; tp = t['tp']; side = t['type']
        et = np.datetime64(t['entry_time']); xt = np.datetime64(t['exit_time'])
        i0 = int(np.searchsorted(tarr[s], et)); i1 = int(np.searchsorted(tarr[s], xt)) + 1
        d = df_t[s]
        hi = d['high'].values[i0:i1]; lo = d['low'].values[i0:i1]
        if len(hi) == 0:
            continue
        if side == 'LONG':
            fav = prog(hi, e, tp); adv = prog(lo, e, tp)
        else:
            fav = prog(lo, e, tp); adv = prog(hi, e, tp)
        peak = float(np.max(fav))
        exit_prog = prog(t['exit_price'], e, tp)
        giveback = peak - exit_prog
        # Q3: ¿retrocedió a ≤0% tras un pico, y luego hizo un pico MAYOR?
        run_peak = 0.0; peak_antes_dip = None; nuevo_max_tras_dip = False
        dipeo_a_cero = False
        for k in range(len(fav)):
            run_peak = max(run_peak, fav[k])
            if peak_antes_dip is None:
                if run_peak >= 30 and adv[k] <= 0:   # tras avanzar ≥30%, tocó breakeven
                    peak_antes_dip = run_peak; dipeo_a_cero = True
            else:
                if fav[k] > peak_antes_dip + 1e-9:
                    nuevo_max_tras_dip = True
        filas.append(dict(sym=s, side=side, peak=peak, exit_prog=exit_prog,
                          giveback=giveback, pnl=t['pnl'],
                          dip0=dipeo_a_cero, nuevo_max=nuevo_max_tras_dip))
    return filas, bt

def reporte(engine):
    filas, bt = analizar(engine)
    n = len(filas)
    print(f"\n{'='*84}\n  {engine.upper()} — {n} trades cerrados (4 años). Análisis de MONSTRUOS y giveback\n{'='*84}")
    # distribución de picos
    print("  Distribución del pico de avance favorable (cuántos trades ≥ X%):")
    for thr in (100, 200, 300, 500, 1000):
        c = sum(1 for f in filas if f['peak'] >= thr)
        pnl = sum(f['pnl'] for f in filas if f['peak'] >= thr)
        print(f"    pico ≥ {thr:>5}%:  {c:>4} trades  |  PnL de ese grupo ${pnl:>+9.2f}")
    # definir MONSTRUO = pico ≥ 200% (bucket donde vive el edge, per giveback_analisis)
    for MON in (200, 300):
        mons = [f for f in filas if f['peak'] >= MON]
        nm = len(mons)
        if nm == 0: continue
        # cómo terminó el flip en los monstruos
        cobro_bien = sum(1 for f in mons if f['giveback'] <= 50)          # retuvo casi todo
        solto_algo = sum(1 for f in mons if 50 < f['giveback'] and f['pnl'] > 0)  # devolvió pero ganó
        solto_a_perdida = sum(1 for f in mons if f['pnl'] <= 0)           # devolvió hasta perder
        gb_prom = np.mean([f['giveback'] for f in mons])
        pnl_mon = sum(f['pnl'] for f in mons)
        dip0 = sum(1 for f in mons if f['dip0'])
        nuevo = sum(1 for f in mons if f['nuevo_max'])
        print(f"\n  --- MONSTRUOS = pico ≥ {MON}% ({nm} trades, ${pnl_mon:+.0f} de PnL) ---")
        print(f"    (1) el flip COBRÓ BIEN (giveback ≤50%):        {cobro_bien:>4}  ({cobro_bien/nm*100:.0f}%)")
        print(f"    (1b) SOLTÓ lo ganado pero igual cerró en verde:  {solto_algo:>4}  ({solto_algo/nm*100:.0f}%)")
        print(f"    (1c) soltó TODO hasta cerrar en pérdida:         {solto_a_perdida:>4}  ({solto_a_perdida/nm*100:.0f}%)")
        print(f"         giveback promedio del monstruo: {gb_prom:.0f} puntos de avance")
        print(f"    (3) retrocedió a 0% (breakeven) EN ALGÚN MOMENTO: {dip0:>4}  ({dip0/nm*100:.0f}%)")
        print(f"        …y de esos, LUEGO hizo un pico MAYOR al previo: {nuevo:>4}  ({nuevo/max(dip0,1)*100:.0f}% de los que dipearon)")
    # Q3 global (todos los trades, no solo monstruos)
    dip0_all = sum(1 for f in filas if f['dip0'])
    nuevo_all = sum(1 for f in filas if f['nuevo_max'])
    print(f"\n  GLOBAL (los {n} trades): retrocedieron a 0% tras avanzar ≥30%: {dip0_all} "
          f"| de esos hicieron nuevo pico mayor: {nuevo_all} ({nuevo_all/max(dip0_all,1)*100:.0f}%)")

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--engine', required=True, choices=['v26','v36'])
    a = ap.parse_args(); reporte(a.engine)
