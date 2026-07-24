#!/usr/bin/env python3
"""FASE 1c — desenmascaramiento: correr el top-6 de la Fase 1a con null-vs-azar
(pctl) IN-SAMPLE y FUERA DE CANASTA (OOB). Muestra que las de mayor Sharpe
in-sample (exhaustion) fallan OOB mientras las trend-following (flip) aguantan.
Reusa el walkforward.py ya probado (subprocess) — un solo code-path."""
import os, subprocess, json, sys
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
PY = '/Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3'
OOB = 'BTCUSDT,DOGEUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,ATOMUSDT'
MC = '80'

# top-6 de la Fase 1a: (nombre, entrada, [flags de salida])
COMBOS = [
 ('continua_exhaustion','continua',['--exhaustion-exit']),  # top PnL/Sharpe in-sample
 ('cruce_exhaustion','cruce',['--exhaustion-exit']),
 ('patrones_exhaustion','patrones',['--exhaustion-exit']),
 ('cruce_flip','cruce',[]),                                  # el edge REAL de V26
 ('continua_flip','continua',[]),
 ('donchian_flip','donchian',[]),
]

def run(nombre, entrada, flags, oob):
    tag = f"f1c_{nombre}_{'oob' if oob else 'is'}"
    cmd = [PY,'walkforward.py','--interval','4h','--entrada',entrada,'--salida','tendencia',
           *flags,'--continuo','--fee','0.0002','--slippage','0.0002','--years','4',
           '--end','2026-06-11 00:00','--mc',MC,'--tag',tag]
    if oob: cmd += ['--symbols',OOB]
    subprocess.run(cmd, cwd=DIR, capture_output=True, text=True)
    try:
        d = json.load(open(os.path.join(DIR, f'wf_resumen_{tag}.json')))
        return (nombre, oob, d.get('pnl_pct'), d.get('pf'), d.get('max_drawdown_pct'), d.get('percentil_vs_null'))
    except Exception as e:
        return (nombre, oob, None, None, None, None)

jobs = [(c[0],c[1],c[2],oob) for c in COMBOS for oob in (False, True)]
print(f"Corriendo {len(jobs)} runs (top-6 × IS/OOB, mc={MC})...", flush=True)
res = {}
with ThreadPoolExecutor(max_workers=4) as ex:
    for r in ex.map(lambda j: run(*j), jobs):
        res[(r[0], r[1])] = r
        print(f"  {r[0]} {'OOB' if r[1] else 'IS '}: PnL={r[2]} pctl={r[5]}", flush=True)

print(f"\n{'='*88}\n  FASE 1c — el top-6 in-sample puesto a prueba (null + OOB)\n{'='*88}")
print(f"  {'combo':22} {'IS PnL%':>9} {'IS pctl':>8} {'OOB PnL%':>9} {'OOB pctl':>9}  veredicto")
for c in COMBOS:
    isr = res.get((c[0],False)); oob = res.get((c[0],True))
    ip, ipc = (isr[2], isr[5]) if isr else (None,None)
    op, opc = (oob[2], oob[5]) if oob else (None,None)
    # veredicto: aguanta si OOB PnL>0 y OOB pctl>=90
    ok = (op is not None and op>0 and (opc or 0)>=90)
    vd = 'AGUANTA OOB ✓' if ok else ('cede/rompe OOB ✗')
    print(f"  {c[0]:22} {str(round(ip,1) if ip is not None else None):>9} {str(ipc):>8} {str(round(op,1) if op is not None else None):>9} {str(opc):>9}  {vd}")
print("\n  (IS pctl 100 + OOB pctl ≥90 = edge que se replica; IS alto pero OOB pctl bajo = espejismo de búsqueda)")
print("FASE_1C_DONE", flush=True)
