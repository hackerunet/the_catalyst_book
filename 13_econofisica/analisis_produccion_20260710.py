#!/usr/bin/env python3
"""Análisis OBJETIVO de lo ocurrido en producción (2026-07-10, pedido del usuario):
1) ¿Qué régimen vieron los bots (con SU propio código) en 4h y 15m, y cuántos flips
   hubo — es un tramo de whipsaw inusual o normal?
2) ¿El día de −$10 está dentro de la distribución del backtest honesto, y con qué
   frecuencia ocurre? ¿"Desangra" la cuenta ese ritmo?
Solo datos públicos + curvas locales del backtest. NO toca los bots."""
import sys, os
import numpy as np
import pandas as pd
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
V26 = os.path.join(BASE, '..', 'v26_tendencia')
sys.path.insert(0, V26)
import config as cfg26              # noqa: E402
import indicadores as ind           # noqa: E402
import estrategia as est            # noqa: E402


def klines(sym, interval, limit=900):
    r = requests.get('https://fapi.binance.com/fapi/v1/klines',
                     params={'symbol': sym, 'interval': interval, 'limit': limit},
                     timeout=15)
    k = r.json()
    df = pd.DataFrame([{'time': pd.to_datetime(x[0], unit='ms'),
                        'open': float(x[1]), 'high': float(x[2]), 'low': float(x[3]),
                        'close': float(x[4]), 'volume': float(x[5])} for x in k])
    return ind.calcular_indicadores(df)


def serie_tendencia(df, n_ultimas):
    """tendencia_actual() del bot, vela a vela, para las últimas n velas."""
    out = []
    for i in range(len(df) - n_ultimas, len(df)):
        out.append((df['time'].iloc[i], est.tendencia_actual(df.iloc[:i + 1])))
    return out


def flips(serie):
    f = []
    for k in range(1, len(serie)):
        if serie[k][1] != serie[k - 1][1]:
            f.append((serie[k][0], serie[k - 1][1], serie[k][1]))
    return f


print('=' * 84)
print('1) RÉGIMEN VISTO POR LOS BOTS — últimas 72 h (con el MISMO código del bot)')
print('=' * 84)
for interval, syms, velas72 in (('4h', ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT'], 18),
                                ('15m', ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'], 288)):
    print(f'\n--- {interval} ---')
    tot_flips = 0
    for sym in syms:
        df = klines(sym, interval)
        s = serie_tendencia(df, velas72)
        fl = flips(s)
        tot_flips += len(fl)
        ahora = s[-1][1]
        resumen = ' | '.join(f"{str(t)[5:16]}: {a}→{b}" for t, a, b in fl[-4:])
        print(f'  {sym:<9} AHORA={ahora:<8} flips_72h={len(fl)}  {resumen}')
    print(f'  TOTAL flips 72h en {interval}: {tot_flips}')

print()
print('=' * 84)
print('2) ¿CUÁNTO WHIPSAW ES "NORMAL"? — flips por 72h en los 4 años del cache 4h')
print('=' * 84)
import pickle
cache = os.path.join(BASE, '..', 'stable_v25_prototype', 'wf_cache_4h_8760_2026-06-11.pkl')
dfs = pickle.load(open(cache, 'rb'))
flips_hist = []
for sym, raw in dfs.items():
    df = ind.calcular_indicadores(raw.copy())
    tends = [est.tendencia_actual(df.iloc[:i + 1]) for i in range(250, len(df))]
    cambios = [i for i in range(1, len(tends)) if tends[i] != tends[i - 1]]
    # flips por ventana de 18 velas (72h) rodante
    arr = np.zeros(len(tends))
    for c in cambios:
        arr[c] = 1
    roll = pd.Series(arr).rolling(18).sum().dropna()
    flips_hist.append(roll)
todos = pd.concat(flips_hist)
print(f'  flips/72h por símbolo 4h (4 años): mediana={todos.median():.0f}  p75={todos.quantile(.75):.0f}  '
      f'p90={todos.quantile(.90):.0f}  p99={todos.quantile(.99):.0f}  máx={todos.max():.0f}')

print()
print('=' * 84)
print('3) EL DÍA DE −$10 CONTRA EL BACKTEST HONESTO (combo V26+V36, $530, riesgo 0.25%)')
print('=' * 84)
d26 = pd.read_csv(os.path.join(BASE, '..', 'stable_v25_prototype', 'v37_eq_v26_base.csv'),
                  index_col=0, parse_dates=True)['equity'].astype(float)
d36 = pd.read_csv(os.path.join(BASE, '..', 'stable_v25_prototype', 'v37_eq_v36_4y.csv'),
                  index_col=0, parse_dates=True)['equity'].astype(float)
r26, r36 = d26.pct_change().dropna(), d36.pct_change().dropna()
m = min(len(r26), len(r36))
esc = 0.0025 / (0.02 / 6)
rc = (r26.values[:m] + r36.values[:m]) * esc          # combo en una cuenta
pnl_dia = 530.0 * rc
n = len(pnl_dia)
peores = np.sort(pnl_dia)[:8]
print(f'  días simulados: {n} (~4 años)')
print(f'  PnL diario: mediana ${np.median(pnl_dia):+.2f} | p05 ${np.percentile(pnl_dia,5):+.2f} | '
      f'p01 ${np.percentile(pnl_dia,1):+.2f} | peor ${pnl_dia.min():+.2f}')
dias_10 = int((pnl_dia <= -10).sum())
print(f'  días con pérdida ≥ $10: {dias_10} de {n}  (≈{dias_10/n*365:.0f} por año, '
      f'{dias_10/n*100:.1f}% de los días)')
print(f'  los 8 peores días del backtest: {[round(x,1) for x in peores]}')
# ¿y qué pasó DESPUÉS de esos días? (¿el sistema se recuperó?)
idx10 = np.where(pnl_dia <= -10)[0]
idx10 = idx10[idx10 < n - 30]
if len(idx10):
    fwd30 = [pnl_dia[i + 1:i + 31].sum() for i in idx10]
    fwd30 = np.array(fwd30)
    print(f'  30 días DESPUÉS de un día ≤−$10: mediana ${np.median(fwd30):+.2f} | '
          f'% positivos {100*(fwd30>0).mean():.0f}%')
# racha de sangrado tipo "N días así seguidos"
equity = 530 + np.cumsum(pnl_dia)
pico = np.maximum.accumulate(equity)
dd = pico - equity
print(f'  DD máximo en $ del combo (4 años, mark-to-market): ${dd.max():.2f} '
      f'(equity mínima ${equity.min():.2f} partiendo de $530)')
print(f'  ritmo REAL del backtest: PnL final 4 años ${equity[-1]-530:+.2f} '
      f'INCLUYENDO todos esos días malos')
