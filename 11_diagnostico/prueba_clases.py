"""
prueba_clases.py — Validación honesta de clases de estrategia COMPLEMENTARIAS a V26.

Usa el motor del SANDBOX (copia aislada de V26; los bots vivos NO se tocan).
Mismo motor honesto (reloj global, intravela pesimista, costos maker), única
diferencia por clase = la lógica de entrada/salida pre-registrada.

Clases (todas 4h, costos maker 0.02%/lado, riesgo 0.33% = 1R, cooldown 2 velas):
  NONREG  cruce + tendencia      → control: debe reproducir el baseline V26 (+121.9% in-basket)
  C1      ruptura + RR(2R)       → Donchian20 + volumen, sin gate de tendencia (la 1ª pierna)
  C2      meanrev + RR(1.5R)     → fade BB+RSI solo en lateral (ADX<20)
  C3      pullback + tendencia   → retroceso a EMA50 en tendencia (complementa V26)
  C4      patrones + tendencia   → VELAS+señal (V25/V28) con salida de V26 (pedido del usuario)

Cada clase se corre CONTINUO 4 años en dos baskets:
  in-basket     = ETH/SOL/BNB/XRP/ADA/LINK (desarrollo)
  out-of-basket = BTC/DOGE/AVAX/DOT/LTC/ATOM (jamás usados en el tuning)

Criterio: una clase "pasa" solo si PnL>0 Y >buy&hold Y se sostiene out-of-basket.
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


def max_drawdown(cerrados):
    eq = pico = BALANCE_INICIAL
    dd = 0.0
    for t in sorted(cerrados, key=lambda x: x['exit_time']):
        eq += t['pnl']
        pico = max(pico, eq)
        dd = max(dd, (pico - eq) / pico)
    return dd * 100


BASKETS = {
    'in-basket': ('ab_cache_4h_8760.pkl',
                  ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']),
    'out-basket': ('ab_cache_4h_8760_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl',
                   ['BTCUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'ATOMUSDT']),
}

# (nombre, ENTRY_MODE, EXIT_MODE, RR_TP_MULT|None)
SCEN = [
    ('NONREG cruce+tendencia',  'cruce',    'tendencia', None),
    ('C1 ruptura+RR2',          'ruptura',  'rr',        2.0),
    ('C2 meanrev+RR1.5',        'meanrev',  'rr',        1.5),
    ('C3 pullback+tendencia',   'pullback', 'tendencia', None),
    ('C4 velas(patrones)+tend', 'patrones', 'tendencia', None),
]


def correr(raw, syms, entry, exit_mode, rr):
    config.SYMBOLS = list(syms)
    config.ENTRY_MODE = entry
    config.EXIT_MODE = exit_mode
    if rr is not None:
        config.RR_TP_MULT = rr
    dfs = {s: calcular_indicadores(raw[s]) for s in syms}
    bt = BacktestV25(candles=0, forense_dir='/tmp/clases_forense')
    bt.forense = Nulo()
    bt.dfs = dfs
    bt.correr()
    r = bt.resumen()
    cerrados = [t for t in bt.trades if t['status'] == 'CERRADA']
    corte = pd.Timestamp.now('UTC').tz_localize(None) - pd.Timedelta(days=10)
    recientes = sum(1 for t in bt.trades if pd.Timestamp(t['entry_time']) >= corte)
    return {'pnl': r['net_pnl_pct'], 'pf': r['profit_factor'], 'wr': r['win_rate'],
            'tr': r['trades'], 'dd': max_drawdown(cerrados),
            'bh': r['benchmark_buy_hold_pct'], 'rec': recientes}


def main():
    for etiqueta, (fichero, syms) in BASKETS.items():
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), fichero)
        if not os.path.isfile(ruta):
            print(f"[{etiqueta}] FALTA cache {fichero} — corre antes ab_entrada_rapida.py")
            continue
        with open(ruta, 'rb') as f:
            raw = pickle.load(f)
        bh = None
        print("\n" + "=" * 86)
        print(f" BASKET {etiqueta.upper()}: {', '.join(syms)}")
        print("=" * 86)
        print(f" {'clase':<26}{'PnL%':>9}{'PF':>7}{'WR%':>7}{'trades':>8}"
              f"{'DD%':>7}{'>B&H?':>7}{'rec10d':>8}")
        for nombre, entry, exit_mode, rr in SCEN:
            try:
                res = correr(raw, syms, entry, exit_mode, rr)
            except Exception as e:
                print(f" {nombre:<26} ERROR: {e}")
                continue
            bh = res['bh']
            gana_bh = 'sí' if (res['pnl'] is not None and res['bh'] is not None
                               and res['pnl'] > res['bh']) else 'no'
            print(f" {nombre:<26}{res['pnl']:>+8.2f}%{str(res['pf']):>7}"
                  f"{res['wr']:>6.1f}%{res['tr']:>8}{res['dd']:>6.1f}%{gana_bh:>7}{res['rec']:>8}")
        print(f"\n buy&hold del basket: {bh:+.2f}%")


if __name__ == '__main__':
    main()
