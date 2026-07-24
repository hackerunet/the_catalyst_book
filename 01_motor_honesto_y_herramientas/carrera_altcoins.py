"""Canastas de la carrera, SIN ETH ni BTC (pedido del usuario) — re-medición.
Sinapsis: SOL BNB XRP ADA LINK   |   V72: DOGE AVAX DOT LTC ATOM
Cero solape -> cero neteo en la cuenta testnet compartida."""
import numpy as np
from suavizado_v37 import correr, equity_mtm, CACHE_4H_ORIG, CACHE_4H_OOB

ALT_SIN = ['SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']
ALT_V72 = ['DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']

BASE = dict(INTERVAL='4h', TIME_STOP_HOURS=None, BT_TAKER_FEE=0.0002,
            BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=8, SCALE_OUT_TENDENCIA=False,
            REPLICA_TENDENCIA=False, TRAILING_STOP_TENDENCIA=False,
            CLIMAX_EXIT_TENDENCIA=False, CLIMAX_FADE_EXIT_TENDENCIA=False,
            CLIMAX_FADE_FUNNEL=False, REENTRY_POST_STOP=False)

CFG_SIN = dict(BASE, ENTRY_MODE='patrones', EXIT_MODE='tendencia',
               EXHAUSTION_EXIT_TENDENCIA=True, EXHAUSTION_LATERAL_VELAS=2,
               SL_FRACTION_OF_TP=0.75, PULLBACK_ARM_DECILE=20)
CFG_V72 = dict(BASE, ENTRY_MODE='cruce', EXIT_MODE='escalera',
               EXHAUSTION_EXIT_TENDENCIA=False,
               SL_FRACTION_OF_TP=3.0, PULLBACK_ARM_DECILE=999)

def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    if not n: return None
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr); g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    v = equity_mtm(bt, balance_inicial=balance).values
    mdd = float(np.max((np.maximum.accumulate(v)-v)/np.maximum.accumulate(v)))*100
    return dict(n=n, wr=100*w/n, roi=100*pnl/balance, pf=g/p if p else 9.99,
                mdd=mdd, gan=g/w if w else 0, per=p/(n-w) if n>w else 0)

print("="*94)
print("  LA CARRERA — canastas SIN ETH ni BTC, 4h, 4 años, cuenta testnet compartida")
print("="*94)
print(f"  {'bot':10} {'canasta':34} {'trades':>6} {'WR':>7} {'PnL':>9} {'PF':>6} {'MaxDD':>7} {'gan.prom':>9}")
print(f"  {'-'*10} {'-'*34} {'-'*6} {'-'*7} {'-'*9} {'-'*6} {'-'*7} {'-'*9}")

for nom, cfg, cache, syms in [
        ('SINAPSIS', CFG_SIN, CACHE_4H_ORIG, ALT_SIN),
        ('V72', CFG_V72, CACHE_4H_OOB, ALT_V72)]:
    m = medir(correr(cache, cfg, symbols=syms))
    print(f"  {nom:10} {' '.join(s.replace('USDT','') for s in syms):34} {m['n']:>6} "
          f"{m['wr']:>6.2f}% {m['roi']:>+8.2f}% {m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")

print("\n  --- referencia: las mismas configs CON los majors (lo ya medido) ---")
for nom, cfg, cache, syms, etq in [
        ('SINAPSIS', CFG_SIN, CACHE_4H_ORIG, None, 'ETH SOL BNB XRP ADA LINK (6)'),
        ('V72', CFG_V72, CACHE_4H_OOB, None, 'BTC DOGE AVAX DOT LTC ATOM (6)')]:
    m = medir(correr(cache, cfg, symbols=syms))
    print(f"  {nom:10} {etq:34} {m['n']:>6} {m['wr']:>6.2f}% {m['roi']:>+8.2f}% "
          f"{m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")
