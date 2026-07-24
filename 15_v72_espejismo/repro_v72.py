#!/usr/bin/env python3
"""repro_v72.py — ¿el motor de ESTA carpeta reproduce el backtest validado?

Corre el backtest de V72 usando SU PROPIA config/estrategia (no la del harness)
y compara contra los números medidos el 2026-07-17 con `carrera_altcoins.py`:

    452 trades | WR 76.33% | PnL +2.61% | PF 1.071

Si no reproduce EXACTO, el código desplegable NO es el validado -> no desplegar.
Mismo patrón que repro_v36.py / repro_sinapsis.py (lección V24: un solo
code-path entre backtest y vivo).

Uso:  python3 repro_v72.py
"""
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from backtest import BacktestV25
from forense import RegistroForense
from indicadores import calcular_indicadores

CACHE = 'wf_cache_oob_4h.pkl'   # symlink al cache OOB 4h (BTC/DOGE/AVAX/DOT/LTC/ATOM)
ESPERADO = {'trades': 452, 'wr': 76.33, 'pnl_pct': 2.61, 'pf': 1.071}
TOL = {'trades': 0, 'wr': 0.05, 'pnl_pct': 0.05, 'pf': 0.005}
BALANCE = 500.0


class ForenseNulo:
    """Sin escritura a disco durante el repro.

    NO hereda de RegistroForense: si heredara, `__getattr__` solo se llamaría
    para lo que NO existe, y además interceptaría `_lock` devolviendo una
    función donde el motor espera un context manager. Un stub puro es más
    simple y no puede confundirse con el real.
    """
    def __getattr__(self, _):
        return lambda *a, **k: None


def main():
    print("=" * 72)
    print("  REPRO V72 — ¿el motor desplegable reproduce el backtest validado?")
    print("=" * 72)

    # 1) la config de ESTA carpeta debe ser la validada
    checks = [
        ('BINANCE_ENV', config.BINANCE_ENV, 'testnet'),
        ('INTERVAL', config.INTERVAL, '4h'),
        ('ENTRY_MODE', config.ENTRY_MODE, 'cruce'),
        ('EXIT_MODE', config.EXIT_MODE, 'escalera'),
        ('SL_FRACTION_OF_TP', config.SL_FRACTION_OF_TP, 3.0),
        ('PULLBACK_ARM_DECILE', config.PULLBACK_ARM_DECILE, 999),
        ('RISK_PER_TRADE', round(config.RISK_PER_TRADE, 6), round(0.02 / 6, 6)),
        ('SYMBOLS', config.SYMBOLS,
         ['DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']),
    ]
    print("\n  --- config ---")
    ok_cfg = True
    for nom, got, esp in checks:
        bien = got == esp
        ok_cfg &= bien
        print(f"    {'OK' if bien else '!!'} {nom:20} {got}")
    if not ok_cfg:
        raise SystemExit("\n  config NO es la validada — abortar")

    # 2) correr el backtest con el motor de esta carpeta
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE)
    with open(ruta, 'rb') as f:
        raw = pickle.load(f)
    raw = {s: d for s, d in raw.items() if s in config.SYMBOLS}
    if len(raw) != len(config.SYMBOLS):
        raise SystemExit(f"  cache no tiene los 5 símbolos: {list(raw)}")

    print(f"\n  --- backtest ({len(raw)} símbolos × {len(next(iter(raw.values())))} velas 4h) ---")
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v72_repro')
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()

    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    w = sum(1 for t in tr if t['pnl'] > 0)
    pnl = sum(t['pnl'] for t in tr)
    g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    obt = {'trades': n, 'wr': 100 * w / n, 'pnl_pct': 100 * pnl / BALANCE,
           'pf': g / p if p else 9.99}

    print("\n  --- comparación ---")
    ok = True
    for k, esp in ESPERADO.items():
        got = obt[k]
        bien = abs(got - esp) <= TOL[k]
        ok &= bien
        print(f"    {'OK' if bien else '!!'} {k:10} esperado {esp:>8} | obtenido {got:>8.2f}")

    print()
    if ok:
        print("  >>> REPRODUCE EXACTO — el código desplegable ES el validado.")
        print(f"  >>> Recordá: WR {obt['wr']:.2f}% con PnL {obt['pnl_pct']:+.2f}% "
              "es el PUNTO, no un fracaso.")
    else:
        print("  >>> NO REPRODUCE — NO desplegar hasta entender la diferencia.")
        raise SystemExit(1)


if __name__ == '__main__':
    main()
