"""
analizar_funding.py — V27-B: análisis del carry de funding delta-neutral.

Pre-registro completo en el libro ("V27-B — CARRY DE FUNDING DELTA-NEUTRAL").
Solo datos públicos (historial real de funding de Binance futuros). NO es un
bot — es el análisis que decide si vale la pena construir algo.

Posición: SHORT perp + LONG spot, mismo nocional → el short COBRA el funding
cuando es positivo y lo PAGA cuando es negativo.

Variantes (pre-registradas, sin escaneo):
  1. always-on : carry permanente, 1 ciclo de costos en todo el período.
  2. filtro    : en carry solo mientras la media móvil 7D del funding (causal,
                 hasta el evento anterior) sea > 0. 0.3% nocional por ciclo.

Uso:  python3 analizar_funding.py [--years 4]
Artefactos: funding_cache.pkl, resumen impreso (guardar a .txt con tee).
"""
import argparse
import os
import pickle
import time

import pandas as pd
import requests

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DATA_BASE = 'https://fapi.binance.com'
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'LINKUSDT']
COSTO_CICLO = 0.003          # 0.3% nocional por entrada+salida (2 patas, taker, slippage)
CAPITAL_FACTOR = 1.5         # capital = spot 1x + margen del short a 2x


def descargar_funding(symbol, start_ms, end_ms):
    """Historial completo de eventos de funding (paginado hacia adelante)."""
    rows = []
    t = start_ms
    while t < end_ms:
        r = requests.get(f"{DATA_BASE}/fapi/v1/fundingRate",
                         params={'symbol': symbol, 'startTime': t,
                                 'endTime': end_ms, 'limit': 1000}, timeout=15)
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        t = batch[-1]['fundingTime'] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['time'] = pd.to_datetime(df['fundingTime'], unit='ms')
    df['rate'] = df['fundingRate'].astype(float)
    return df[['time', 'rate']].drop_duplicates('time').reset_index(drop=True)


def analizar(df, filtro):
    """PnL del carry sobre nocional=1. filtro=True → variante 2 (MA7D>0)."""
    s = df.set_index('time')['rate']
    if filtro:
        ma = s.shift(1).rolling('7D').mean()
        en_carry = (ma > 0).fillna(False)
    else:
        en_carry = pd.Series(True, index=s.index)
    pnl = s.where(en_carry, 0.0)
    transiciones = int((en_carry != en_carry.shift(1).fillna(False)).sum())
    ciclos = max(transiciones / 2.0, 1.0) if filtro else 1.0
    costos = ciclos * COSTO_CICLO
    # serie diaria para drawdown del acumulado (neto de costos prorrateados al inicio)
    diario = pnl.resample('1D').sum()
    acum = diario.cumsum() - costos
    dd = float((acum.cummax() - acum).max())
    años = (s.index[-1] - s.index[0]).days / 365.25
    neto = float(pnl.sum()) - costos
    return {
        'años': round(años, 2),
        'bruto_pct': round(float(pnl.sum()) * 100, 2),
        'ciclos': int(ciclos),
        'neto_pct': round(neto * 100, 2),
        'anual_nocional_pct': round(neto / años * 100, 2),
        'anual_capital_pct': round(neto / años / CAPITAL_FACTOR * 100, 2),
        'dd_nocional_pct': round(dd * 100, 2),
        'dd_capital_pct': round(dd / CAPITAL_FACTOR * 100, 2),
        'pct_eventos_positivos': round(float((s > 0).mean()) * 100, 1),
        'por_año': {str(a): round(float(g.sum()) * 100, 2)
                    for a, g in pnl.groupby(pnl.index.year)},
        '_diario': pnl.resample('1D').sum(),  # para baskets
    }


def basket(diarios, etiqueta, años_ciclos):
    """Equal-weight: promedio del PnL diario por símbolo (nocional total = 1)."""
    df = pd.concat(diarios, axis=1).fillna(0.0)
    m = df.mean(axis=1)
    ciclos, años = años_ciclos
    costos = ciclos * COSTO_CICLO
    acum = m.cumsum() - costos
    dd = float((acum.cummax() - acum).max())
    neto = float(m.sum()) - costos
    return {'basket': etiqueta, 'neto_pct': round(neto * 100, 2),
            'anual_nocional_pct': round(neto / años * 100, 2),
            'anual_capital_pct': round(neto / años / CAPITAL_FACTOR * 100, 2),
            'dd_capital_pct': round(dd / CAPITAL_FACTOR * 100, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=float, default=4.0)
    args = ap.parse_args()
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(args.years * 365.25 * 24 * 3600 * 1000)

    ruta = os.path.join(DIR_BASE, 'funding_cache.pkl')
    if os.path.isfile(ruta):
        print(f"INFO: usando cache {ruta}")
        with open(ruta, 'rb') as f:
            datos = pickle.load(f)
    else:
        datos = {}
        for sym in SYMBOLS:
            print(f"INFO: descargando funding {sym}...")
            datos[sym] = descargar_funding(sym, start_ms, end_ms)
            print(f"  {sym}: {len(datos[sym])} eventos "
                  f"({datos[sym]['time'].iloc[0]} → {datos[sym]['time'].iloc[-1]})")
        with open(ruta, 'wb') as f:
            pickle.dump(datos, f)

    for filtro, titulo in ((False, 'VARIANTE 1 — ALWAYS-ON'),
                           (True, 'VARIANTE 2 — FILTRO MA7D>0 (la regla pre-registrada)')):
        print(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}")
        print(f"{'símbolo':10} | {'años':>4} | {'bruto%':>7} | {'ciclos':>6} | "
              f"{'neto%':>7} | {'anual/noc%':>10} | {'ANUAL/CAP%':>10} | {'DD/cap%':>7}")
        diarios, resultados = [], {}
        for sym in SYMBOLS:
            r = analizar(datos[sym], filtro)
            resultados[sym] = r
            diarios.append(r.pop('_diario').rename(sym))
            print(f"{sym:10} | {r['años']:>4} | {r['bruto_pct']:>7} | {r['ciclos']:>6} | "
                  f"{r['neto_pct']:>7} | {r['anual_nocional_pct']:>10} | "
                  f"{r['anual_capital_pct']:>10} | {r['dd_capital_pct']:>7}")
        años = max(r['años'] for r in resultados.values())
        ciclos_prom = sum(r['ciclos'] for r in resultados.values()) / len(resultados)
        for syms, et in ((['BTCUSDT', 'ETHUSDT'], 'BTC+ETH'),
                         (SYMBOLS, 'LOS 7')):
            sel = [d for d in diarios if d.name in syms]
            b = basket(sel, et, (ciclos_prom, años))
            print(f"BASKET {b['basket']:8} → neto {b['neto_pct']}% | "
                  f"anual/capital {b['anual_capital_pct']}% | DD/capital {b['dd_capital_pct']}%")
        print("\npor año (neto bruto %, por símbolo):")
        for sym in SYMBOLS:
            pa = resultados[sym]['por_año']
            print(f"  {sym:10} " + ' | '.join(f"{a}: {v:+.2f}" for a, v in sorted(pa.items())))

    print(f"\nUmbral pre-registrado: variante 2 ≥ 8%/año sobre CAPITAL con DD ≤ 10%")


if __name__ == '__main__':
    main()
