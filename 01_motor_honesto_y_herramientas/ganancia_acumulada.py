#!/usr/bin/env python3
"""
ganancia_acumulada.py — el INVERSO de perdida_acumulada.py: ¿cuánto GANA la cuenta
(en $, desde $530) por mes 1/3/6/9/12? Mismo método, misma config de referencia
(V26+V36), mismos 4 años de backtest honesto, todos los arranques.
"""
import numpy as np
import pandas as pd

BAL0 = 530.0
SCALE = 0.0025 / (0.02 / 6)   # dial 0.25% sobre curvas medidas a 0.33%


def load_ret(path):
    d = pd.read_csv(path, index_col=0, parse_dates=True)
    eq = d['equity'].astype(float).values
    return np.diff(eq) / eq[:-1]


r26 = load_ret('v37_eq_v26_base.csv')
r36 = load_ret('v37_eq_v36_4y.csv')
m = min(len(r26), len(r36))
rc = (r26[:m] + r36[:m]) * SCALE     # combinados en una cuenta, a 0.25%
n = len(rc)

HOR = {'mes 1': 30, 'mes 3': 90, 'mes 6': 180, 'mes 9': 270, 'mes 12': 365}

runup = {h: [] for h in HOR}   # máximo run-up ($) alcanzado dentro del horizonte
neto = {h: [] for h in HOR}    # ganancia NETA ($) exactamente al mes N
for t0 in range(0, n - 5):
    eq = BAL0
    maxbal = BAL0
    day = 0
    for k in range(t0, n):
        eq *= (1 + rc[k])
        if eq > maxbal:
            maxbal = eq
        day += 1
        if day in HOR.values():
            for h, d in HOR.items():
                if day == d:
                    runup[h].append(maxbal - BAL0)
                    neto[h].append(eq - BAL0)

print("=" * 82)
print("GANANCIA ACUMULADA desde $530 — config de referencia (V26+V36)")
print("4 años de backtest honesto, TODOS los arranques posibles")
print("=" * 82)
print(f"{'Horizonte':<9} | {'MEJOR pico ($)':>14} {'techo ($)':>11} | "
      f"{'NETO al mes N: mediana':>22} {'mejor':>8} {'peor':>8} {'%+':>5}")
for h in HOR:
    ru = np.array(runup[h]); nt = np.array(neto[h])
    print(f"{h:<9} | {ru.max():>13.2f}  {BAL0+ru.max():>10.2f} | "
          f"{np.median(nt):>21.2f} {nt.max():>8.2f} {nt.min():>8.2f} {100*(nt>0).mean():>4.0f}%")

print("-" * 82)
# contexto acumulado
eq_cont = BAL0 * np.cumprod(1 + rc)
print(f"Balance final a 4 años continuos (arrancando $530): ${eq_cont[-1]:.2f}  "
      f"(+{(eq_cont[-1]/BAL0-1)*100:.0f}%)")
print(f"Techo absoluto tocado en 4 años: ${eq_cont.max():.2f}")
