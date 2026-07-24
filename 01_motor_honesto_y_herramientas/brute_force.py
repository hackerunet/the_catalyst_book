#!/usr/bin/env python3
"""BRUTE-FORCE DISCIPLINADO — Fase 1a (calibración): entradas × salidas × 4h × cripto.
Reusa el motor honesto (correr + equity_mtm). Cada combo escribe una fila a
brute_force/resultados_f1a.csv (checkpointing: no recomputa). Al final aplica el
GAUNTLET estadístico: Deflated Sharpe Ratio (descuenta el nº de tests N) + la
comparación de la distribución observada contra la esperada bajo azar.
Ver PLAN_BRUTE_FORCE.md.
"""
import os, sys, csv, itertools, math
import numpy as np, pandas as pd
from multiprocessing import Pool

DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(DIR, 'brute_force'); os.makedirs(OUTDIR, exist_ok=True)
# parametrizable por entorno (multi-clase / multi-timeframe)
TAG = os.environ.get('BF_TAG', 'f1a')
CACHE = os.environ.get('BF_CACHE', 'wf_cache_4h_8760_2026-06-11_0000.pkl')
INTERVAL = os.environ.get('BF_INTERVAL', '4h')
COOLDOWN = {'15m':0.5,'1h':2,'4h':8,'1d':48}.get(INTERVAL, 8)
CSVF = os.path.join(OUTDIR, f'resultados_{TAG}.csv')

ENTRIES = ['cruce','patrones','donchian','rsi_reversion','sweep','swing_rejection','macd_stack','continua']
# cada salida = dict de flags a activar sobre el reset (EXIT_MODE default 'tendencia')
EXITS = {
 'flip':        {},
 'escalera':    {'EXIT_MODE':'escalera'},
 'trailing':    {'TRAILING_STOP_TENDENCIA':True},
 'scaleout':    {'SCALE_OUT_TENDENCIA':True},
 'exhaustion':  {'EXHAUSTION_EXIT_TENDENCIA':True},
 'climax':      {'CLIMAX_EXIT_TENDENCIA':True},
 'adx_decline': {'ADX_DECLINE_EXIT_TENDENCIA':True},
 'rsi_div':     {'RSI_DIVERGENCE_EXIT_TENDENCIA':True},
}
RESET = dict(EXIT_MODE='tendencia', TRAILING_STOP_TENDENCIA=False, SCALE_OUT_TENDENCIA=False,
             EXHAUSTION_EXIT_TENDENCIA=False, CLIMAX_EXIT_TENDENCIA=False,
             ADX_DECLINE_EXIT_TENDENCIA=False, RSI_DIVERGENCE_EXIT_TENDENCIA=False,
             REPLICA_TENDENCIA=False, TIME_STOP_HOURS=None, REENTRY_POST_STOP=False,
             FILTRO_SQUEEZE=False, FILTRO_RS=False, FILTRO_MACD_REVERSION=False)
COLS=['combo','entrada','salida','interval','pnl_pct','pf','max_dd_pct','sharpe_ann',
      'sharpe_per','skew','kurt','n_ret','trades','wr']

def worker(combo):
    entrada, sname = combo
    import config
    from suavizado_v37 import correr, equity_mtm, CFG_V26
    cfg = dict(CFG_V26)  # maker; sobre-escribimos interval/cooldown abajo
    cfg.update(RESET); cfg.update(EXITS[sname]); cfg['ENTRY_MODE']=entrada
    cfg['INTERVAL']=INTERVAL; cfg['COOLDOWN_CANDLES']=COOLDOWN
    try:
        bt = correr(CACHE, cfg)
        eq = equity_mtm(bt).resample('1D').last().ffill()
        ret = eq.pct_change().dropna()
        cerr = [t for t in bt.trades if t['status']=='CERRADA']
        pnl = float(eq.iloc[-1]/eq.iloc[0]-1)*100
        gp = sum(t['pnl'] for t in cerr if t['pnl']>0); gl=abs(sum(t['pnl'] for t in cerr if t['pnl']<0))
        pf = gp/gl if gl>0 else float('inf')
        dd = float(((eq.cummax()-eq)/eq.cummax()*100).max())
        sr_per = float(ret.mean()/ret.std()) if ret.std()>0 else 0.0
        sr_ann = sr_per*math.sqrt(365)
        wr = round(sum(1 for t in cerr if t['pnl']>0)/len(cerr)*100,1) if cerr else 0
        return dict(combo=f"{entrada}|{sname}", entrada=entrada, salida=sname, interval=INTERVAL,
            pnl_pct=round(pnl,2), pf=round(pf,3) if pf!=float('inf') else 999,
            max_dd_pct=round(dd,1), sharpe_ann=round(sr_ann,3), sharpe_per=sr_per,
            skew=round(float(ret.skew()),3), kurt=round(float(ret.kurtosis())+3,3),
            n_ret=len(ret), trades=len(cerr), wr=wr)
    except Exception as e:
        return dict(combo=f"{entrada}|{sname}", entrada=entrada, salida=sname, interval=INTERVAL,
            pnl_pct=None, pf=None, max_dd_pct=None, sharpe_ann=None, sharpe_per=0.0,
            skew=0, kurt=3, n_ret=0, trades=0, wr=0)

def hechos():
    if not os.path.exists(CSVF): return set()
    return set(r['combo'] for r in csv.DictReader(open(CSVF)))

def deflated_sharpe(sr_per_list, sr, skew, kurt, T, N):
    """DSR (Bailey & López de Prado). sr,skew,kurt = per-período. Descuenta N tests."""
    from scipy.stats import norm
    var_sr = np.var([s for s in sr_per_list if s==s], ddof=1)
    g = 0.5772156649
    if var_sr<=0 or N<2: return None
    sr0 = math.sqrt(var_sr) * ((1-g)*norm.ppf(1-1.0/N) + g*norm.ppf(1-1.0/(N*math.e)))
    denom = math.sqrt(max(1 - skew*sr + (kurt-1)/4.0*sr**2, 1e-9))
    return float(norm.cdf((sr - sr0)*math.sqrt(max(T-1,1))/denom)), sr0

def gauntlet():
    rows=[r for r in csv.DictReader(open(CSVF)) if r['sharpe_per'] not in ('','None')]
    for r in rows:
        for k in ('pnl_pct','pf','sharpe_per','sharpe_ann','skew','kurt','max_dd_pct'):
            r[k]=float(r[k]) if r[k] not in ('','None') else 0.0
        r['n_ret']=int(r['n_ret']); r['trades']=int(r['trades'])
    N=len(rows); sr_list=[r['sharpe_per'] for r in rows]
    print(f"\n{'='*78}\n  GAUNTLET — {N} combos (entradas × salidas, 4h cripto)\n{'='*78}")
    obs_max = max(sr_list)*math.sqrt(365)
    exp_max_null = math.sqrt(2*math.log(N))*np.std(sr_list, ddof=1)*math.sqrt(365)
    print(f"  Sharpe anual MÁXIMO observado: {obs_max:.2f}")
    print(f"  Sharpe anual máximo ESPERADO bajo azar (√(2·ln N)·σ): {exp_max_null:.2f}")
    print(f"  → si el observado no supera claramente al esperado-por-azar, los 'ganadores' son ruido.\n")
    for r in rows:
        dsr = deflated_sharpe(sr_list, r['sharpe_per'], r['skew'], r['kurt'], r['n_ret'], N)
        r['dsr']=round(dsr[0],3) if dsr else None
    rows.sort(key=lambda r:-(r['dsr'] or -1))
    print(f"  {'combo':30} {'PnL%':>8} {'PF':>6} {'ShAnl':>6} {'DSR':>6} {'trades':>6}")
    for r in rows[:15]:
        print(f"  {r['combo']:30} {r['pnl_pct']:>8.1f} {r['pf']:>6.2f} {r['sharpe_ann']:>6.2f} {str(r['dsr']):>6} {r['trades']:>6}")
    cand=[r for r in rows if r['pnl_pct']>0 and r['pf']>1 and (r['dsr'] or 0)>0.95]
    print(f"\n  Combos rentables (PnL>0 y PF>1): {sum(1 for r in rows if r['pnl_pct']>0 and r['pf']>1)}/{N}")
    print(f"  Combos que pasan DSR>0.95 (candidatos a null+OOB): {len(cand)}")
    for r in cand: print(f"    → {r['combo']} (DSR {r['dsr']}, ShAnl {r['sharpe_ann']:.2f})")
    if not cand: print("    (ninguno — consistente con la hipótesis nula; ver PLAN §8)")

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='gauntlet':
        gauntlet(); sys.exit()
    combos=[(e,s) for e in ENTRIES for s in EXITS]
    ya=hechos(); pend=[c for c in combos if f"{c[0]}|{c[1]}" not in ya]
    print(f"Total combos: {len(combos)} | ya hechos: {len(ya)} | pendientes: {len(pend)}", flush=True)
    nuevo = not os.path.exists(CSVF)
    f=open(CSVF,'a',newline=''); w=csv.DictWriter(f, fieldnames=COLS)
    if nuevo: w.writeheader(); f.flush()
    nproc=int(sys.argv[1]) if len(sys.argv)>1 and sys.argv[1].isdigit() else 6
    with Pool(nproc) as p:
        for i,res in enumerate(p.imap_unordered(worker, pend),1):
            w.writerow(res); f.flush()
            print(f"[{i}/{len(pend)}] {res['combo']}: PnL={res['pnl_pct']} PF={res['pf']} Sh={res['sharpe_ann']}", flush=True)
    f.close(); print("FASE_1A_DONE", flush=True)
    gauntlet()
