"""Filas FLIP de la grilla V72, con SL_FRACTION_OF_TP EXPLÍCITO (=0.75, el de V26).
Corrige el leak: SLF define el stop del flip y su sizing, no solo el del dial."""
import numpy as np
from suavizado_v37 import correr, equity_mtm
from v72_grilla import GRILLA, BASE, medir

print("FILAS FLIP CORREGIDAS (SL_FRACTION_OF_TP=0.75 explícito en TODAS)")
print("="*88)
print(f"  {'TF':4} {'canasta':7} {'trades':>6} {'WR NETO':>8} {'PnL':>10} {'PF':>6} {'MaxDD':>7} {'gan.prom':>9}")
print(f"  {'-'*4} {'-'*7} {'-'*6} {'-'*8} {'-'*10} {'-'*6} {'-'*7} {'-'*9}")
for tf, canasta, cache, syms, cd in GRILLA:
    cfg = dict(BASE, INTERVAL=tf, COOLDOWN_CANDLES=cd, EXIT_MODE='tendencia',
               SL_FRACTION_OF_TP=0.75)          # <- el fix
    m = medir(correr(cache, cfg, symbols=syms))
    if m:
        print(f"  {tf:4} {canasta:7} {m['n']:>6} {m['wr']:>7.2f}% {m['roi']:>+9.2f}% "
              f"{m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan']:>+8.2f}")
