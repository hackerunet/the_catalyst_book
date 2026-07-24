"""
validar_c4.py — (1b) correlación/solape de C4 con V26 + (2) combinación V26+C4.

C4 = entrada por patrón de vela (V25/V28) + salida de tendencia (V26), 4h.
V26 = entrada por flip de alineación (cruce) + salida de tendencia, 4h.

Pregunta (1b): ¿C4 captura trades DISTINTOS de V26 (aditivo) o los mismos
(redundante)? Métricas: % de trades de C4 que solapan en tiempo+símbolo+dirección
con un trade de V26, y correlación de su PnL MENSUAL.

Pregunta (2): ¿la combinación (overlay equitativo, cada estrategia 0.33%/trade)
mejora el retorno/drawdown frente a cada una sola?

Usa el sandbox aislado; bots vivos intactos. Reutiliza los caches 4h ya bajados.
"""
import os
import sys
import pickle

import pandas as pd

sys.path.insert(0, os.path.abspath('sandbox'))
import config                                  # noqa: E402
from indicadores import calcular_indicadores   # noqa: E402
from backtest import BacktestV25, BALANCE_INICIAL  # noqa: E402

config.INTERVAL = '4h'
config.COOLDOWN_CANDLES = 8
config.BT_TAKER_FEE = 0.0002
config.BT_SLIPPAGE = 0.0002


class Nulo:
    dir = '(off)'
    def registrar_activacion(self, *a, **k): pass
    def registrar_vela(self, *a, **k): pass
    def registrar_cierre(self, *a, **k): pass


BASKETS = {
    'in-basket': ('ab_cache_4h_8760.pkl',
                  ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']),
    'out-basket': ('ab_cache_4h_8760_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl',
                   ['BTCUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']),
}


def correr(raw, syms, entry):
    config.SYMBOLS = list(syms)
    config.ENTRY_MODE = entry
    config.EXIT_MODE = 'tendencia'
    dfs = {s: calcular_indicadores(raw[s]) for s in syms}
    bt = BacktestV25(candles=0, forense_dir='/tmp/c4_forense')
    bt.forense = Nulo()
    bt.dfs = dfs
    bt.correr()
    return [t for t in bt.trades if t['status'] == 'CERRADA']


def dd_pct(trades, base):
    eq = pico = base
    dd = 0.0
    for t in sorted(trades, key=lambda x: x['exit_time']):
        eq += t['pnl']
        pico = max(pico, eq)
        dd = max(dd, (pico - eq) / pico)
    return dd * 100


def solape(c4, v26):
    """% de trades de C4 que coinciden en símbolo+dirección+tiempo con uno de V26."""
    if not c4:
        return 0.0
    cnt = 0
    for c in c4:
        for v in v26:
            if c['symbol'] == v['symbol'] and c['type'] == v['type'] \
                    and c['entry_time'] < v['exit_time'] and v['entry_time'] < c['exit_time']:
                cnt += 1
                break
    return cnt / len(c4) * 100


def mensual(trades):
    s = {}
    for t in trades:
        k = pd.Timestamp(t['exit_time']).to_period('M')
        s[k] = s.get(k, 0.0) + t['pnl']
    return pd.Series(s)


def main():
    for etiqueta, (fichero, syms) in BASKETS.items():
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), fichero)
        with open(ruta, 'rb') as f:
            raw = pickle.load(f)

        v26 = correr(raw, syms, 'cruce')
        c4 = correr(raw, syms, 'patrones')

        pnl_v = sum(t['pnl'] for t in v26)
        pnl_c = sum(t['pnl'] for t in c4)
        dd_v = dd_pct(v26, BALANCE_INICIAL)
        dd_c = dd_pct(c4, BALANCE_INICIAL)

        # (1b) solape + correlación mensual
        sol = solape(c4, v26)
        mv, mc = mensual(v26), mensual(c4)
        mm = pd.DataFrame({'v26': mv, 'c4': mc}).fillna(0.0)
        corr = mm['v26'].corr(mm['c4'])

        # (2) combinación: overlay equitativo (cada una 0.33%/trade, base $1000)
        combo = sorted(v26 + c4, key=lambda t: t['exit_time'])
        pnl_combo = pnl_v + pnl_c
        dd_combo = dd_pct(combo, 2 * BALANCE_INICIAL)
        pct = lambda usd, base: usd / base * 100

        rv = pct(pnl_v, BALANCE_INICIAL) / dd_v if dd_v else float('inf')
        rc = pct(pnl_c, BALANCE_INICIAL) / dd_c if dd_c else float('inf')
        rk = pct(pnl_combo, 2 * BALANCE_INICIAL) / dd_combo if dd_combo else float('inf')

        print("\n" + "=" * 78)
        print(f" BASKET {etiqueta.upper()}")
        print("=" * 78)
        print(f" V26 (cruce):     {len(v26):>4} trades | PnL {pct(pnl_v,500):>+7.2f}% "
              f"| DD {dd_v:>5.1f}% | ret/DD {rv:.2f}")
        print(f" C4  (velas):     {len(c4):>4} trades | PnL {pct(pnl_c,500):>+7.2f}% "
              f"| DD {dd_c:>5.1f}% | ret/DD {rc:.2f}")
        print(f"\n (1b) SOLAPE de C4 con V26 (mismo símbolo+dir+tiempo): {sol:.1f}% de los trades de C4")
        print(f"      Correlación de PnL MENSUAL V26↔C4: {corr:+.2f}  "
              f"(<0.3 = decorrelacionado/aditivo; >0.6 = redundante)")
        print(f"\n (2) COMBINACIÓN V26+C4 (overlay equitativo, base $1000):")
        print(f"      PnL {pct(pnl_combo, 1000):>+7.2f}% | DD {dd_combo:>5.1f}% | ret/DD {rk:.2f}")
        print(f"      → ret/DD combo {rk:.2f} vs V26 {rv:.2f} vs C4 {rc:.2f}  "
              f"({'MEJORA' if rk > max(rv, rc) else 'no mejora'} sobre la mejor individual)")


if __name__ == '__main__':
    main()
