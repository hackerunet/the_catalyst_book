"""
suavizado_v37.py — V37: ¿se puede comprimir el tiempo-a-rentabilidad de V26?
(sesión 2026-07-03, pedido del usuario: "nadie va a esperar 2 años a que un bot
empiece a pagar; la vara es un producto bancario de ~12%/año, evaluable en ~1 año")

Este script NO toca ningún bot en vivo. Corre el MISMO motor honesto
(backtest.BacktestV25, un solo code path) con overrides en memoria, reconstruye
la curva de equity MARK-TO-MARKET (con no-realizado, igual que dd_real_v26.py
pero vectorizada), y mide las métricas que responden la objeción del usuario:

  - Retorno por AÑO calendario (mark-to-market, no solo realizado)
  - Distribución de retornos en TODAS las ventanas rolling de 365 días:
      mediana, p10, mínimo, % de ventanas > 0%, % > 12%, % > 25%
    (= "si alguien evalúa el bot en un año elegido al azar, ¿qué ve?")
  - Máximo período bajo el agua (días desde un pico de equity hasta recuperarlo)
  - MDD mark-to-market global y rolling 90d (gate de copy-trade)

Experimentos (cada uno guarda v37_<exp>.json + v37_eq_<exp>.csv con la equity diaria):
  --exp v26_base      control: V26 tal cual (4h, cruce, tendencia, maker, basket 6,
                      riesgo 0.33%, cooldown 8h) sobre el cache 4 años. DEBE reproducir
                      +130.59% / 426 trades / PF 1.918 / DD-cerrados 26.3%
                      (wf_resumen_continuo_control_testC.json) antes de confiar en nada.
  --exp v26_oob       control OOB: BTC/DOGE/AVAX/DOT/LTC/ATOM → +59.55% / 427 / 1.433 / 18.7
  --exp amplitud12    V37-A: los 12 símbolos juntos (6+6, ambos baskets ya validados
                      por separado) en UNA cuenta. --risk para el nivel (0.0033333 = cap 4%
                      apalancado; 0.0016667 = cap 2%, comparable al baseline).
  --exp v36_2y        control V36: 15m/patrones/tendencia/top-4/cooldown 2h sobre el cache
                      2 años. DEBE reproducir +61.92% / 509 / PF 1.584 / MDD90d 19.4 (repro_v36).
  --exp v36_4y        V36 sobre 4 años de 15m (2022-06→2026-06) — los primeros 2 años son
                      genuinamente OOS para V35/V36 (validado solo en 2024-26). Requiere
                      descargar el cache primero: --exp descargar_15m_4y.
  --exp descargar_15m_4y   descarga 140160 velas 15m × top-4 (una sola vez, cacheado)
  --exp combo         V37-B: correlación de retornos diarios V26 vs V36 + curva combinada
                      (lee los v37_eq_*.csv ya generados; no re-corre motores).
  --exp scaleout      V37-C: V26 + scale-out parcial (config.SCALE_OUT_TENDENCIA=True,
                      25% de la posición al llegar a +1R, stop original intacto en el resto).
                      --oob para el basket OOB.

Uso: /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 suavizado_v37.py --exp v26_base
"""
import argparse
import json
import os
import pickle

import numpy as np
import pandas as pd

import config
from indicadores import calcular_indicadores
from backtest import BacktestV25, BALANCE_INICIAL
from walkforward import ForenseNulo

DIR = os.path.dirname(os.path.abspath(__file__))

CACHE_4H_ORIG = 'wf_cache_4h_8760_2026-06-11_0000.pkl'
CACHE_4H_OOB = 'wf_cache_4h_8760_2026-06-11_0000_BTCU-DOGE-AVAX-DOTU-LTCU-ATOM.pkl'
CACHE_15M_2Y = 'wf_cache_15m_70080_2026-06-11.pkl'
CACHE_15M_4Y = 'wf_cache_15m_140160_2026-06-11_top4.pkl'

TOP4 = ['ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

# Configs base de los estudios de suavizado (los parámetros afinados de los
# motores en producción quedan en reserva; ver el libro):
CFG_V26 = dict(INTERVAL='4h', ENTRY_MODE='cruce', EXIT_MODE='tendencia',
               BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=8)
CFG_V36 = dict(INTERVAL='15m', ENTRY_MODE='patrones', EXIT_MODE='tendencia',
               BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=2)

RISK_DEFAULT = 0.02 / 6  # nivel de riesgo por operación usado en los estudios


# ---------------------------------------------------------------------------
def correr(caches, cfg, symbols=None, risk=RISK_DEFAULT):
    """Corre BacktestV25 con overrides en memoria. `caches` puede ser lista
    (se fusionan los dicts símbolo→df, p.ej. basket original + OOB)."""
    for k, v in cfg.items():
        setattr(config, k, v)
    config.RISK_PER_TRADE = risk
    if isinstance(caches, str):
        caches = [caches]
    raw = {}
    for c in caches:
        with open(os.path.join(DIR, c), 'rb') as f:
            raw.update(pickle.load(f))
    if symbols:
        raw = {s: raw[s] for s in symbols if s in raw}
    config.SYMBOLS = list(raw.keys())
    bt = BacktestV25(candles=len(next(iter(raw.values()))), forense_dir='/tmp/v37_forense')
    bt.forense = ForenseNulo()
    bt.dfs = {s: calcular_indicadores(d) for s, d in raw.items()}
    bt.correr()
    return bt


# ---------------------------------------------------------------------------
def equity_mtm(bt, balance_inicial=BALANCE_INICIAL):
    """Equity mark-to-market por timestamp (vectorizada — misma definición que
    dd_real_v26.equity_markto_market, O(sum duraciones) en vez de O(T×trades)).
    Soporta trades con scale-out parcial (t['scale_out'] = {ts, pnl})."""
    times = {s: d['time'].values for s, d in bt.dfs.items()}
    closes = {s: d['close'].values for s, d in bt.dfs.items()}
    timeline = np.array(sorted(set().union(*[set(v) for v in times.values()])))
    pos_de = {s: np.searchsorted(timeline, v) for s, v in times.items()}
    realizado = np.zeros(len(timeline))
    noreal = np.zeros(len(timeline))
    for t in bt.trades:
        if t['status'] != 'CERRADA':
            continue
        s = t['symbol']
        et = np.datetime64(t['entry_time'])
        xt = np.datetime64(t['exit_time'])
        so = t.get('scale_out')
        pnl_parcial = so['pnl'] if so else 0.0
        # realizado: el parcial en su ts; el resto al exit
        xi = np.searchsorted(timeline, xt)
        realizado[xi:] += t['pnl'] - pnl_parcial
        if so:
            si = np.searchsorted(timeline, np.datetime64(so['ts']))
            realizado[si:] += pnl_parcial
        # no-realizado: marcar velas [entry, exit) al cierre
        i0 = np.searchsorted(times[s], et)
        i1 = np.searchsorted(times[s], xt)
        if i1 <= i0:
            continue
        sign = 1.0 if t['type'] == 'LONG' else -1.0
        if so:
            isc = np.searchsorted(times[s], np.datetime64(so['ts']))
            isc = min(max(isc, i0), i1)
            q0 = t['qty'] + so['qty']   # qty original antes del parcial
            if isc > i0:
                seg = (closes[s][i0:isc] - t['entry_price']) * q0 * sign
                np.add.at(noreal, pos_de[s][i0:isc], seg)
            if i1 > isc:
                seg = (closes[s][isc:i1] - t['entry_price']) * t['qty'] * sign
                np.add.at(noreal, pos_de[s][isc:i1], seg)
        else:
            seg = (closes[s][i0:i1] - t['entry_price']) * t['qty'] * sign
            np.add.at(noreal, pos_de[s][i0:i1], seg)
    eq = pd.Series(balance_inicial + realizado + noreal,
                   index=pd.DatetimeIndex(timeline))
    return eq


def metricas_curva(eq):
    """Métricas de suavidad/tiempo-a-rentabilidad sobre la equity mtm."""
    peak = eq.cummax()
    dd_mtm = float(((peak - eq) / peak * 100).max())
    roll_peak = eq.rolling('90D').max()
    dd_90 = float(((roll_peak - eq) / roll_peak * 100).max())

    diaria = eq.resample('1D').last().ffill()
    # por año calendario (mark-to-market)
    por_año = {}
    fin_prev = None
    for año, grupo in diaria.groupby(diaria.index.year):
        ini = fin_prev if fin_prev is not None else grupo.iloc[0]
        fin = grupo.iloc[-1]
        por_año[int(año)] = round((fin / ini - 1) * 100, 2)
        fin_prev = fin

    # rolling 365 días (la pregunta del usuario: "¿qué ve alguien que evalúa 1 año?")
    r365 = (diaria / diaria.shift(365) - 1).dropna() * 100
    if len(r365):
        roll = {
            'n_ventanas': int(len(r365)),
            'mediana': round(float(r365.median()), 2),
            'p10': round(float(r365.quantile(0.10)), 2),
            'minimo': round(float(r365.min()), 2),
            'maximo': round(float(r365.max()), 2),
            'pct_ventanas_positivas': round(float((r365 > 0).mean() * 100), 1),
            'pct_ventanas_sobre_12': round(float((r365 > 12).mean() * 100), 1),
            'pct_ventanas_sobre_25': round(float((r365 > 25).mean() * 100), 1),
        }
    else:
        roll = None

    # bajo el agua: días máximos entre un pico y su recuperación
    peak_d = diaria.cummax()
    bajo = diaria < peak_d * (1 - 1e-9)
    max_under = cur = 0
    for b in bajo.values:
        cur = cur + 1 if b else 0
        max_under = max(max_under, cur)

    años_tot = (diaria.index[-1] - diaria.index[0]).days / 365.25
    cagr = (float(diaria.iloc[-1] / diaria.iloc[0]) ** (1 / años_tot) - 1) * 100 \
        if años_tot > 0 else None

    return {
        'dd_mtm_max': round(dd_mtm, 1),
        'dd_90d': round(dd_90, 1),
        'cagr_pct': round(cagr, 2) if cagr is not None else None,
        'por_año_mtm_pct': por_año,
        'rolling_365d': roll,
        'max_dias_bajo_agua': int(max_under),
    }


def dd_cerrados(bt):
    cerr = sorted((t for t in bt.trades if t['status'] == 'CERRADA'),
                  key=lambda t: t['exit_time'])
    bal = peak = BALANCE_INICIAL
    dd = 0.0
    for t in cerr:
        bal += t['pnl']
        peak = max(peak, bal)
        dd = max(dd, (peak - bal) / peak * 100)
    return round(dd, 1)


def reportar(nombre, bt, extra=None):
    r = bt.resumen()
    eq = equity_mtm(bt)
    m = metricas_curva(eq)
    # PnL REALIZADO por año (por exit_time — la contabilidad del registro
    # histórico de el libro; el mtm de metricas_curva es lo que VE la cuenta)
    real_año = {}
    for t in bt.trades:
        if t['status'] == 'CERRADA':
            y = int(pd.Timestamp(t['exit_time']).year)
            real_año[y] = round(real_año.get(y, 0.0) + t['pnl'], 2)
    m['por_año_realizado_usd'] = dict(sorted(real_año.items()))
    with open(os.path.join(DIR, f'v37_trades_{nombre}.pkl'), 'wb') as f:
        pickle.dump(bt.trades, f)
    out = {
        'exp': nombre,
        'pnl_pct': r['net_pnl_pct'], 'trades': r['trades'], 'wr': r['win_rate'],
        'pf': r['profit_factor'], 'bh_pct': r['benchmark_buy_hold_pct'],
        'dd_cerrados': dd_cerrados(bt),
        'ventana': f"{r['window_start']} → {r['window_end']}",
        **m,
        'por_motivo_salida': r['por_motivo_salida'],
        'por_simbolo': r['por_simbolo'],
        'config': {
            'symbols': config.SYMBOLS, 'interval': config.INTERVAL,
            'entry_mode': config.ENTRY_MODE, 'exit_mode': config.EXIT_MODE,
            'risk_per_trade': config.RISK_PER_TRADE,
            'cooldown_h': config.COOLDOWN_CANDLES,
            'fee': config.BT_TAKER_FEE, 'slippage': config.BT_SLIPPAGE,
            'scale_out': getattr(config, 'SCALE_OUT_TENDENCIA', False),
            'scale_out_r': getattr(config, 'SCALE_OUT_R', None),
            'scale_out_fraction': getattr(config, 'SCALE_OUT_FRACTION', None),
        },
    }
    if extra:
        out.update(extra)
    with open(os.path.join(DIR, f'v37_{nombre}.json'), 'w') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    eq.resample('1D').last().ffill().to_csv(os.path.join(DIR, f'v37_eq_{nombre}.csv'),
                                            header=['equity'])
    print(f"\n===== {nombre} =====")
    print(f"PnL {r['net_pnl_pct']:+.2f}% | trades {r['trades']} | WR {r['win_rate']}% | "
          f"PF {r['profit_factor']} | B&H {r['benchmark_buy_hold_pct']:+.2f}%")
    print(f"DD cerrados {out['dd_cerrados']}% | DD mtm {m['dd_mtm_max']}% | "
          f"DD 90d {m['dd_90d']}% | CAGR {m['cagr_pct']}%/año | "
          f"bajo agua máx {m['max_dias_bajo_agua']} días")
    print(f"Por año (mtm): {m['por_año_mtm_pct']}")
    if m['rolling_365d']:
        rr = m['rolling_365d']
        print(f"Rolling 365d ({rr['n_ventanas']} ventanas): mediana {rr['mediana']}% | "
              f"p10 {rr['p10']}% | mín {rr['minimo']}% | "
              f">0%: {rr['pct_ventanas_positivas']}% | >12%: {rr['pct_ventanas_sobre_12']}% | "
              f">25%: {rr['pct_ventanas_sobre_25']}%")
    print(f"Guardado: v37_{nombre}.json + v37_eq_{nombre}.csv")
    return out


# ---------------------------------------------------------------------------
def descargar_15m_4y():
    """Descarga 4 años de velas 15m del top-4 (una vez, cacheado)."""
    ruta = os.path.join(DIR, CACHE_15M_4Y)
    if os.path.isfile(ruta):
        print(f"INFO: ya existe {ruta}")
        return
    from binance_client import BinanceClient
    config.INTERVAL = '15m'
    total = int(4 * 365 * 24 * 4)  # 140160 velas de 15m
    end_ms = int(pd.Timestamp('2026-06-11').timestamp() * 1000)
    cliente = BinanceClient()
    raw = {}
    for sym in TOP4:
        print(f"INFO: descargando {total} velas 15m de {sym}...")
        raw[sym] = cliente.klines_paginated(sym, total, end_time_ms=end_ms)
        print(f"  {sym}: {len(raw[sym])} velas "
              f"({raw[sym]['time'].iloc[0]} → {raw[sym]['time'].iloc[-1]})")
    with open(ruta, 'wb') as f:
        pickle.dump(raw, f)
    print(f"Guardado: {ruta}")


def combo():
    """V37-B: correlación V26 (4h) vs V36 (15m) + curva combinada (misma cuenta,
    $500 + $500). Usa las equities diarias ya generadas."""
    def leer(nombre):
        p = os.path.join(DIR, f'v37_eq_{nombre}.csv')
        s = pd.read_csv(p, index_col=0, parse_dates=True)['equity']
        return s
    eq26 = leer('v26_base')
    nombre36 = 'v36_4y' if os.path.isfile(os.path.join(DIR, 'v37_eq_v36_4y.csv')) else 'v36_2y'
    eq36 = leer(nombre36)

    comun = eq26.index.intersection(eq36.index)
    a, b = eq26.loc[comun], eq36.loc[comun]
    ra, rb = a.pct_change().dropna(), b.pct_change().dropna()
    corr_d = float(ra.corr(rb))
    corr_s = float(a.resample('1W').last().pct_change().dropna()
                   .corr(b.resample('1W').last().pct_change().dropna()))

    combinada = a + b  # dos cuentas de $500 → base $1000 (la flota viva real)
    m_combo = metricas_curva(combinada)
    m_26 = metricas_curva(a)
    m_36 = metricas_curva(b)

    out = {
        'exp': 'combo', 'eq36_fuente': nombre36,
        'ventana_comun': f"{comun[0]} → {comun[-1]}",
        'correlacion_diaria': round(corr_d, 3),
        'correlacion_semanal': round(corr_s, 3),
        'v26_solo': m_26, 'v36_solo': m_36, 'combo_50_50': m_combo,
        'pnl_pct_v26_en_ventana': round(float(a.iloc[-1] / a.iloc[0] - 1) * 100, 2),
        'pnl_pct_v36_en_ventana': round(float(b.iloc[-1] / b.iloc[0] - 1) * 100, 2),
        'pnl_pct_combo': round(float(combinada.iloc[-1] / combinada.iloc[0] - 1) * 100, 2),
    }
    with open(os.path.join(DIR, 'v37_combo.json'), 'w') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    combinada.to_csv(os.path.join(DIR, 'v37_eq_combo.csv'), header=['equity'])
    print(json.dumps(out, indent=1, ensure_ascii=False))
    print("Guardado: v37_combo.json")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exp', required=True,
                    choices=['v26_base', 'v26_oob', 'amplitud12', 'v36_2y',
                             'descargar_15m_4y', 'v36_4y', 'combo', 'scaleout'])
    ap.add_argument('--risk', type=float, default=RISK_DEFAULT)
    ap.add_argument('--oob', action='store_true', help='(scaleout) usar basket OOB')
    ap.add_argument('--tag', type=str, default=None, help='sufijo extra del artefacto')
    args = ap.parse_args()

    if args.exp == 'v26_base':
        bt = correr(CACHE_4H_ORIG, CFG_V26, risk=args.risk)
        reportar('v26_base' + (f'_{args.tag}' if args.tag else ''), bt)
    elif args.exp == 'v26_oob':
        bt = correr(CACHE_4H_OOB, CFG_V26, risk=args.risk)
        reportar('v26_oob', bt)
    elif args.exp == 'amplitud12':
        bt = correr([CACHE_4H_ORIG, CACHE_4H_OOB], CFG_V26, risk=args.risk)
        nombre = f'amplitud12_r{args.risk:.6f}'.rstrip('0')
        reportar(nombre, bt)
    elif args.exp == 'v36_2y':
        bt = correr(CACHE_15M_2Y, CFG_V36, symbols=TOP4, risk=args.risk)
        reportar('v36_2y', bt)
    elif args.exp == 'descargar_15m_4y':
        descargar_15m_4y()
    elif args.exp == 'v36_4y':
        bt = correr(CACHE_15M_4Y, CFG_V36, symbols=TOP4, risk=args.risk)
        reportar('v36_4y', bt)
    elif args.exp == 'combo':
        combo()
    elif args.exp == 'scaleout':
        config.SCALE_OUT_TENDENCIA = True
        cache = CACHE_4H_OOB if args.oob else CACHE_4H_ORIG
        bt = correr(cache, CFG_V26, risk=args.risk)
        n_so = sum(1 for t in bt.trades if t.get('scale_out'))
        pnl_par = sum(t['scale_out']['pnl'] for t in bt.trades if t.get('scale_out'))
        reportar('scaleout' + ('_oob' if args.oob else ''), bt,
                 extra={'trades_con_scaleout': n_so,
                        'pnl_parciales_usd': round(pnl_par, 2)})


if __name__ == '__main__':
    main()
