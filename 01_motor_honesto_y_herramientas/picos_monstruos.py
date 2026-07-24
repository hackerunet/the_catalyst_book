#!/usr/bin/env python3
"""INGENIERÍA INVERSA: ¿qué señales ocurrieron en el CANDLE-PICO de los monstruos?
No imponemos una regla — vamos a los momentos donde los monstruos hicieron su máximo
avance y empezaron a bajar, medimos el estado de cada indicador/geometría ahí, y lo
comparamos contra TODOS los demás candles dentro de los trades (tasa base).
Una señal solo es útil si es MUCHO más frecuente en el pico que en el resto
(lift alto) — si no, se prende todo el tiempo y no sirve como salida.
"""
import argparse, os
import numpy as np
from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4

def prog(px, e, tp): return (px - e) / (tp - e) * 100.0

def features(d, i, side):
    """Snapshot de señales en el candle i (dirección-normalizado: 'a favor'/'extremo en
    la dirección del trade'). Devuelve dict de flags/valores. Requiere i>=2."""
    row = d.iloc[i]; prev = d.iloc[i-1]; prev2 = d.iloc[i-2]
    sign = 1.0 if side == 'LONG' else -1.0
    o,h,l,c = row['open'],row['high'],row['low'],row['close']
    body = abs(c-o); rng = max(h-l, 1e-9)
    up_wick = h - max(o,c); dn_wick = min(o,c) - l
    rsi = row['RSI']
    rsi_dir = rsi if side=='LONG' else 100-rsi          # alto = extremo en la dirección
    ema21 = row['EMA_21'] if row['EMA_21']==row['EMA_21'] else c
    ema50 = row['EMA_50'] if row['EMA_50']==row['EMA_50'] else c
    overext21 = (c-ema21)/ema21*100*sign                # + = extendido a favor
    overext50 = (c-ema50)/ema50*100*sign
    mh = row['MACD_Hist']*sign; mh1 = prev['MACD_Hist']*sign; mh2 = prev2['MACD_Hist']*sign
    adx = row['ADX']; adx2 = prev2['ADX']
    volr = row['volume']/row['Volume_MA'] if row['Volume_MA']>0 else 1.0
    bbU, bbL = row['BB_UPPER'], row['BB_LOWER']
    return dict(
        rsi_ext70 = rsi_dir>70,
        rsi_ext80 = rsi_dir>80,
        macd_gira = (mh < mh1) and (mh1 < mh2),          # momentum desacelera 2 velas a favor
        macd_cruza0 = (mh < 0) and (mh1 >= 0),           # MACD_Hist cruzó contra la dirección
        adx_cae = adx < adx2,                            # ADX cayendo (tendencia debilita)
        overext21_3 = overext21 > 3,                     # >3% sobre EMA21 a favor
        overext50_5 = overext50 > 5,                     # >5% sobre EMA50 a favor
        bb_rompe = (c>bbU) if side=='LONG' else (c<bbL), # cierre fuera de la banda
        vol_climax = volr > 1.5,                         # spike de volumen
        vol_seca = volr < 0.7,                           # volumen secándose
        mecha_rev = (up_wick if side=='LONG' else dn_wick) > 2*body and body < 0.3*rng,  # shooting star / hammer inverso
        vela_contra = (c<o) if side=='LONG' else (c>o),  # vela roja (LONG) / verde (SHORT)
        doji = body < 0.1*rng,
    )

def analizar(engine, MON=300):
    cfg = dict(CFG_V26 if engine=='v26' else CFG_V36)
    cache = CACHE_4H_ORIG if engine=='v26' else CACHE_15M_4Y
    syms = None if engine=='v26' else TOP4
    bt = correr(cache, cfg, symbols=syms)
    dft = {s: d.reset_index(drop=True) for s,d in bt.dfs.items()}
    tarr = {s: d['time'].values for s,d in dft.items()}
    trades = [t for t in bt.trades if t['status']=='CERRADA']

    pico_feats = []; base_feats = []
    n_mon = 0
    for t in trades:
        s=t['symbol']; e=t['entry_price']; tp=t['tp']; side=t['type']
        i0=int(np.searchsorted(tarr[s], np.datetime64(t['entry_time'])))
        i1=int(np.searchsorted(tarr[s], np.datetime64(t['exit_time'])))+1
        d=dft[s];
        if i1-i0 < 3: continue
        hi=d['high'].values[i0:i1]; lo=d['low'].values[i0:i1]
        fav = prog(hi,e,tp) if side=='LONG' else prog(lo,e,tp)
        peak=float(np.max(fav))
        if peak < MON: continue
        n_mon += 1
        kpeak = i0 + int(np.argmax(fav))
        if kpeak>=2: pico_feats.append(features(d,kpeak,side))
        # base: todos los otros candles del trade (donde estabas adentro y podías salir)
        for k in range(max(i0,2), i1):
            if k==kpeak: continue
            base_feats.append(features(d,k,side))
    # agregación
    def rate(lst, key):
        v=[f[key] for f in lst]; return sum(v)/len(v)*100 if v else 0
    print(f"\n{'='*80}\n  {engine.upper()} — señales en el PICO de {n_mon} monstruos (pico ≥ {MON}%)\n"
          f"  vs tasa base (los {len(base_feats)} candles restantes dentro de esos trades)\n{'='*80}")
    print(f"  {'señal':16} {'en el PICO':>11} {'tasa base':>11} {'lift (x)':>9}")
    keys=list(pico_feats[0].keys()) if pico_feats else []
    filas=[]
    for k in keys:
        rp=rate(pico_feats,k); rb=rate(base_feats,k)
        lift = rp/rb if rb>0 else float('inf')
        filas.append((k,rp,rb,lift))
    for k,rp,rb,lift in sorted(filas, key=lambda x:-x[3]):
        lf = f"{lift:.2f}" if lift!=float('inf') else "∞"
        print(f"  {k:16} {rp:>10.0f}% {rb:>10.0f}% {lf:>9}")
    print(f"\n  Lectura: lift>1 = más frecuente en el pico que en el resto. Pero fíjate en la"
          f"\n  columna 'tasa base': si una señal se prende en >30-40% de los candles normales,"
          f"\n  aunque tenga lift>1 va a dar demasiadas falsas alarmas para usarla como salida.")

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--engine',required=True,choices=['v26','v36'])
    ap.add_argument('--mon',type=int,default=300); a=ap.parse_args(); analizar(a.engine,a.mon)
