#!/usr/bin/env python3
"""Análisis por PERÍODOS de evaluación (mensual/trimestral/semestral/anual, tope 1 año)
de las estrategias de salida sobre los motores vivos V26/V36.

Responde la pregunta del usuario: "no puedo prometer sobre 4 años; ¿qué se ve en un
mes / trimestre / semestre / año elegido al azar?"  Usa la equity MARK-TO-MARKET
(reutiliza correr() + equity_mtm() de suavizado_v37, un solo code path del motor honesto).

Uso:
  periodos_salidas.py --engine v26 --exit baseline   (o exhaustion/scaleout/trail_wide)
  periodos_salidas.py --csv v37_eq_v26_base.csv --nombre "V26 baseline"  (reusa curva ya hecha)
"""
import argparse, json, os
import numpy as np, pandas as pd
import config
from suavizado_v37 import correr, equity_mtm, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4

DIR = os.path.dirname(os.path.abspath(__file__))
HORIZONTES = [('1 mes', 30), ('3 meses (trim)', 91), ('6 meses (sem)', 182), ('1 año', 365)]

def stats_rolling(diaria, dias):
    r = (diaria / diaria.shift(dias) - 1).dropna() * 100
    if len(r) == 0:
        return None
    return dict(n=int(len(r)), mediana=round(float(r.median()),1),
                p10=round(float(r.quantile(0.10)),1), peor=round(float(r.min()),1),
                mejor=round(float(r.max()),1), pct_pos=round(float((r>0).mean()*100),0))

def por_periodo(diaria):
    out = {}
    for nom, d in HORIZONTES:
        out[nom] = stats_rolling(diaria, d)
    # por año calendario
    año = {}
    fin_prev = None
    for a, g in diaria.groupby(diaria.index.year):
        ini = fin_prev if fin_prev is not None else g.iloc[0]
        año[int(a)] = round((g.iloc[-1]/ini - 1)*100, 1)
        fin_prev = g.iloc[-1]
    return out, año

def equity_de(args):
    if args.csv:
        eq = pd.read_csv(os.path.join(DIR, args.csv), index_col=0, parse_dates=True).iloc[:,0]
        nombre = args.nombre or args.csv
    else:
        cfg = dict(CFG_V26 if args.engine=='v26' else CFG_V36)
        caches = CACHE_4H_ORIG if args.engine=='v26' else CACHE_15M_4Y
        syms = None if args.engine=='v26' else TOP4
        # flags de salida
        for k in ('TRAILING_STOP_TENDENCIA','SCALE_OUT_TENDENCIA','EXHAUSTION_EXIT_TENDENCIA','CLIMAX_EXIT_TENDENCIA'):
            setattr(config, k, False)
        if args.exit=='exhaustion': config.EXHAUSTION_EXIT_TENDENCIA = True
        elif args.exit=='scaleout': config.SCALE_OUT_TENDENCIA = True
        elif args.exit=='climax': config.CLIMAX_EXIT_TENDENCIA = True
        elif args.exit=='trail_wide':
            config.TRAILING_STOP_TENDENCIA=True; config.TRAILING_ARM_R=3.0; config.TRAILING_DISTANCE_R=2.0
        bt = correr(caches, cfg, symbols=syms)
        eq = equity_mtm(bt)
        nombre = f"{args.engine} {args.exit}"
    return eq.resample('1D').last().ffill(), nombre

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['v26','v36'])
    ap.add_argument('--exit', default='baseline', choices=['baseline','exhaustion','scaleout','trail_wide','climax'])
    ap.add_argument('--csv'); ap.add_argument('--nombre'); ap.add_argument('--tag')
    args = ap.parse_args()
    diaria, nombre = equity_de(args)
    periodos, año = por_periodo(diaria)
    print(f"\n### {nombre} — retorno sobre ventanas rodantes (todas las de cada tamaño)")
    print(f"{'período':16} {'mediana':>8} {'típico malo(p10)':>16} {'peor':>7} {'mejor':>7} {'% positivas':>12}")
    for nom,_ in HORIZONTES:
        s = periodos[nom]
        if s: print(f"{nom:16} {s['mediana']:>7}% {s['p10']:>15}% {s['peor']:>6}% {s['mejor']:>6}% {s['pct_pos']:>11}%")
    print(f"por año calendario: " + " | ".join(f"{a}:{v:+.0f}%" for a,v in año.items()))
    out = dict(nombre=nombre, periodos=periodos, por_año=año)
    tag = args.tag or (args.csv or f"{args.engine}_{args.exit}").replace('.csv','')
    with open(os.path.join(DIR, f"periodos_{tag}.json"),'w') as f: json.dump(out,f,indent=1,ensure_ascii=False)

if __name__ == '__main__':
    main()
