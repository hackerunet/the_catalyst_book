import numpy as np
from suavizado_v37 import correr, equity_mtm, CACHE_15M_4Y, TOP4

BASE = dict(INTERVAL='15m', ENTRY_MODE='cruce', PULLBACK_ARM_DECILE=999,
            TIME_STOP_HOURS=None, BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002,
            COOLDOWN_CANDLES=2, EXHAUSTION_EXIT_TENDENCIA=False,
            CLIMAX_FADE_EXIT_TENDENCIA=False, CLIMAX_FADE_FUNNEL=False)

def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    if not n: return None
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    v = equity_mtm(bt, balance_inicial=balance).values
    mdd = float(np.max((np.maximum.accumulate(v)-v)/np.maximum.accumulate(v)))*100
    return dict(n=n, wr=100*w/n, roi=100*pnl/balance, pf=g/p if p else 9.99,
                mdd=mdd, gan=g/w if w else 0, per=p/(n-w) if n>w else 0)

print("="*92)
print("  V72 a 15m — misma entrada (cruce), canasta top-4, 4 años")
print("="*92)
print(f"  {'config':30} {'trades':>6} {'WR NETO':>8} {'teór':>6} {'PnL':>10} {'PF':>6} {'MaxDD':>7} {'gan.prom':>9}")
print(f"  {'-'*30} {'-'*6} {'-'*8} {'-'*6} {'-'*10} {'-'*6} {'-'*7} {'-'*9}")

m = medir(correr(CACHE_15M_4Y, dict(BASE, EXIT_MODE='tendencia'), symbols=TOP4))
print(f"  {'15m cruce + FLIP (dejar correr)':30} {m['n']:>6} {m['wr']:>7.2f}% {'—':>6} "
      f"{m['roi']:>+9.2f}% {m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")

for slf in (0.75, 3.0):
    m = medir(correr(CACHE_15M_4Y, dict(BASE, EXIT_MODE='escalera', SL_FRACTION_OF_TP=slf), symbols=TOP4))
    teo = 100*slf/(1+slf)
    print(f"  {'15m cruce + TP/SL dial '+str(slf):30} {m['n']:>6} {m['wr']:>7.2f}% {teo:>5.0f}% "
          f"{m['roi']:>+9.2f}% {m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")
