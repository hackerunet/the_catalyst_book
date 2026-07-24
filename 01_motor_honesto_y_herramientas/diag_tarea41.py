"""
diag_tarea41.py — Diagnóstico de MECANISMO (read-only) para la Tarea #41.
Corrida continua 3 años (config baseline: patrones + escalera, basket completo)
sobre el cache congelado. Buckea los trades cerrados:
  (a) por PATRÓN disparador  → aísla "Marubozu bajista" (count/WR/PnL).
  (b) por HORA de entrada UTC → y por la sesión bloqueada {22,23,0..5}.
No decide nada; solo explica por qué cada test dio lo que dio.
"""
import pickle, os
import pandas as pd
import config, estrategia
from backtest import BacktestV25
from indicadores import calcular_indicadores
from walkforward import ForenseNulo

DIR = os.path.dirname(os.path.abspath(__file__))
raw = pickle.load(open(os.path.join(DIR, 'wf_cache_1h_26280_2026-06-11.pkl'), 'rb'))

bt = BacktestV25(candles=26280, forense_dir='/tmp/diag_t41_forense')
bt.forense = ForenseNulo()
bt.dfs = {s: calcular_indicadores(df) for s, df in raw.items()}
bt.correr()

cerrados = [t for t in bt.trades if t['status'] == 'CERRADA']
print(f"\nTrades cerrados (continuo 3a): {len(cerrados)}")


def bucket(clave):
    g = {}
    for t in cerrados:
        g.setdefault(clave(t), []).append(t)
    return g


# --- (a) por patrón ---
print("\n=== (a) POR PATRÓN DISPARADOR ===")
gp = bucket(lambda t: t['pattern'])
for k in sorted(gp, key=lambda k: sum(x['pnl'] for x in gp[k])):
    v = gp[k]
    wr = sum(1 for x in v if x['pnl'] > 0) / len(v) * 100
    print(f"  {k:42s} n={len(v):>3} WR={wr:4.1f}% PnL=${sum(x['pnl'] for x in v):+8.2f}")

mb = [t for t in cerrados if t['pattern'].startswith('Marubozu bajista')]
if mb:
    wr = sum(1 for x in mb if x['pnl'] > 0) / len(mb) * 100
    print(f"\n  --> Marubozu bajista: n={len(mb)}, WR={wr:.1f}%, "
          f"PnL=${sum(x['pnl'] for x in mb):+.2f} "
          f"({len(mb)/len(cerrados)*100:.1f}% de los trades)")

# --- (b) por hora de entrada UTC ---
print("\n=== (b) POR HORA DE ENTRADA UTC ===")
gh = bucket(lambda t: pd.Timestamp(t['entry_time']).hour)
sesion = {22, 23, 0, 1, 2, 3, 4, 5}
in_s, out_s = [], []
for h in range(24):
    v = gh.get(h, [])
    if not v:
        continue
    wr = sum(1 for x in v if x['pnl'] > 0) / len(v) * 100
    pnl = sum(x['pnl'] for x in v)
    marca = ' <BLOQ>' if h in sesion else ''
    print(f"  {h:02d}h n={len(v):>3} WR={wr:4.1f}% PnL=${pnl:+8.2f}{marca}")
    (in_s if h in sesion else out_s).append((len(v), pnl))

n_in = sum(n for n, _ in in_s); p_in = sum(p for _, p in in_s)
n_out = sum(n for n, _ in out_s); p_out = sum(p for _, p in out_s)
print(f"\n  SESIÓN BLOQUEADA (22-06 UTC): n={n_in} ({n_in/len(cerrados)*100:.0f}% de trades), PnL=${p_in:+.2f}")
print(f"  RESTO (06-22 UTC):            n={n_out} ({n_out/len(cerrados)*100:.0f}% de trades), PnL=${p_out:+.2f}")
