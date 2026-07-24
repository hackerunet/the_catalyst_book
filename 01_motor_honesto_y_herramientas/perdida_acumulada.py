#!/usr/bin/env python3
"""
perdida_acumulada.py — ¿cuánto puede PERDER la cuenta (en $, desde su punto de
partida) por mes 3/6/9/12, con la config REAL en vivo? (mainnet 2026-07-09)

Config viva: UNA cuenta de $530, V26 (4h) + V36 (15m), cada trade 0.25% del balance.
Ambos bots operan sobre la MISMA cuenta -> sus P&L se SUMAN (exposición combinada).

Fuente: curvas de equity mark-to-market honestas de 4 años (V37), medidas a 0.33%
de riesgo; se re-escalan a 0.25% (el sizing es lineal en el % de riesgo).

Metodología: para CADA día de arranque posible en los 4 años, se simula empezar
FRESCO con $530 ese día y se mide, dentro de los primeros N meses, el PISO más bajo
que toca la cuenta (peor caída). El "peor caso" es el arranque más desfavorable de
la historia. Esto responde: '¿qué tan abajo puede ir mi cuenta si arranco en el peor
momento?' — en pérdida acumulada ($), no en % del balance.
"""
import numpy as np
import pandas as pd

BAL0 = 530.0
RISK_LIVE = 0.0025          # dial en vivo 0.25%
RISK_BT = 0.02 / 6          # las curvas se midieron a 0.33% (0.02/6)
SCALE = RISK_LIVE / RISK_BT # ~0.758


def load_ret(path):
    d = pd.read_csv(path, index_col=0, parse_dates=True)
    eq = d['equity'].astype(float).values
    r = np.diff(eq) / eq[:-1]
    return d.index[1:], r


idx26, r26 = load_ret('v37_eq_v26_base.csv')
idx36, r36 = load_ret('v37_eq_v36_4y.csv')
m = min(len(r26), len(r36))
r26, r36 = r26[:m], r36[:m]
# a 0.25% y COMBINADOS en una sola cuenta (P&L se suman)
rc = (r26 + r36) * SCALE
# curva continua desde $530 (contexto)
eq_cont = BAL0 * np.cumprod(1 + rc)

HOR = {'mes 3': 90, 'mes 6': 180, 'mes 9': 270, 'mes 12': 365}
n = len(rc)

# Para cada arranque t0: piso más bajo dentro de cada horizonte
peor_perd = {h: 0.0 for h in HOR}   # peor pérdida acumulada ($) desde $530
peor_piso = {h: BAL0 for h in HOR}  # piso de balance más bajo ($)
perd_list = {h: [] for h in HOR}
for t0 in range(0, n - 5):
    eq = BAL0
    minbal = BAL0
    day = 0
    for k in range(t0, n):
        eq *= (1 + rc[k])
        if eq < minbal:
            minbal = eq
        day += 1
        for h, d in HOR.items():
            if day == d:
                perd = BAL0 - minbal
                perd_list[h].append(perd)
                if perd > peor_perd[h]:
                    peor_perd[h] = perd
                    peor_piso[h] = minbal

print("=" * 74)
print("PÉRDIDA ACUMULADA desde $530 — config de referencia (V26+V36)")
print("Sobre 4 años de backtest honesto, TODOS los arranques posibles")
print("=" * 74)
print(f"{'Horizonte':<10} {'PEOR caso ($)':>16} {'piso ($)':>12} {'mediana ($)':>14} {'p90 ($)':>10}")
for h, d in HOR.items():
    arr = np.array(perd_list[h])
    print(f"{h:<10} {peor_perd[h]:>15.2f}  {peor_piso[h]:>11.2f} {np.median(arr):>13.2f} "
          f"{np.percentile(arr, 90):>10.2f}")

# Absolutos sobre TODA la corrida continua
pico = np.maximum.accumulate(eq_cont)
dd_pico = (pico - eq_cont)
piso_abs = eq_cont.min()
print("-" * 74)
print(f"Peor caída pico->valle (MDD) en 4 años continuos: ${dd_pico.max():.2f} "
      f"({dd_pico.max()/pico[dd_pico.argmax()]*100:.1f}%)")
print(f"Piso absoluto de la cuenta en 4 años (arrancando en $530): ${piso_abs:.2f}")
print(f"Balance final a 4 años (contexto de retorno): ${eq_cont[-1]:.2f}")
# outcome típico a 12 meses (equity a día 365 vs arranque, todos los t0)
out12 = [BAL0 * np.prod(1 + rc[t0:t0 + 365]) - BAL0 for t0 in range(0, n - 365)]
out12 = np.array(out12)
print("-" * 74)
print(f"Resultado NETO a 12 meses (todos los arranques): mediana ${np.median(out12):+.2f} | "
      f"peor ${out12.min():+.2f} | mejor ${out12.max():+.2f} | % arranques positivos {100*(out12>0).mean():.0f}%")

# ¿cuántos escenarios tocan pisos preocupantes?
for umbral in (300, 400, 450):
    toca = 0
    for t0 in range(0, n - 5):
        eq = BAL0
        for k in range(t0, n):
            eq *= (1 + rc[k])
            if eq <= umbral:
                toca += 1
                break
    print(f"Arranques (de {n-5}) en los que la cuenta llega a tocar ${umbral} en ALGÚN momento de 4 años: {toca}")
