"""
retro_manual.py — Retrospectiva de los cierres MANUALES (¿buen timing?).

V26: para cada cierre manual, ¿se dio el FLIP después? ¿a qué precio? → ¿cobraste
     mejor o peor que dejar la salida del sistema (flip/stop)?
V26/V28 usa tendencia_actual de V26 (misma lógica).
V28: para cada cierre manual, si lo dejabas, ¿habría llegado a 2R (la meta) o
     habría tocado el STOP primero?

Datos: klines públicos (4h para V26, 1h para V28) desde la salida hacia adelante.
Solo lectura.
"""
import json
import requests
import pandas as pd
from datetime import datetime, timezone

import estrategia
from indicadores import calcular_indicadores

V26 = '/tmp/bugcheck2/v26_retro.json'
V28 = '/tmp/bugcheck2/v28_retro.json'


def klines(sym, interval, start_ms, limit=1000):
    out = []
    cur = start_ms
    while True:
        r = requests.get('https://fapi.binance.com/fapi/v1/klines',
                         params={'symbol': sym, 'interval': interval, 'startTime': cur, 'limit': 1000},
                         timeout=20).json()
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        cur = r[-1][0] + 1
        if len(out) > 4000:
            break
    df = pd.DataFrame(out, columns=['time', 'open', 'high', 'low', 'close', 'volume',
                                    'ct', 'qv', 'n', 'tbv', 'tqv', 'i'])
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
    return df[['time', 'open', 'high', 'low', 'close', 'volume']].drop_duplicates('time').reset_index(drop=True)


def analizar_v26():
    print("=" * 78)
    print("V26 — ¿se dio el FLIP después de tu cierre manual? (4h)")
    print("=" * 78)
    man = [t for t in json.load(open(V26)) if t['status'] == 'CERRADA' and 'MANUAL' in (t.get('exit_reason') or '')]
    for t in man:
        sym = t['symbol']
        ex = datetime.fromisoformat(t['exit_time'])
        # fetch 4h con warmup amplio antes del exit
        start = int((ex - pd.Timedelta(days=60)).timestamp() * 1000)
        df = calcular_indicadores(klines(sym, '4h', start))
        ex_ms = ex.timestamp() * 1000
        post = df[df['time'] > ex.replace(tzinfo=timezone.utc)]
        opp = 'LONG' if t['type'] == 'SHORT' else 'SHORT'
        flip_t = flip_p = None; sl_hit = None
        for _, row in post.iterrows():
            sub = df[df['time'] <= row['time']]
            if t['type'] == 'SHORT' and row['high'] >= t['sl'] and sl_hit is None:
                sl_hit = (row['time'], t['sl'])
            if estrategia.tendencia_actual(sub) == opp:
                flip_t, flip_p = row['time'], row['close']
                break
        # comparación: SHORT cobra más a menor precio
        manual_px = t['exit_price']
        print(f"\n■ {sym} {t['type']} | cerraste {ex:%m-%d %H:%M} @ {manual_px} (PnL ${t['pnl']:+.2f}, pico {t.get('peak_progress',0):.0f}%)")
        if flip_t:
            mejor = 'PEOR que tu cierre' if flip_p > manual_px else 'mejor que tu cierre'
            print(f"   FLIP a {opp}: {flip_t:%m-%d %H:%M} @ {flip_p:.4f} → el sistema habría cerrado ahí ({mejor})")
        else:
            ult = df['close'].iloc[-1]
            print(f"   SIN flip hasta ahora (tendencia sigue {estrategia.tendencia_actual(df)}); precio actual {ult:.4f} "
                  f"→ seguiría ABIERTA{' (y ya habría tocado STOP)' if sl_hit else ''}")
        if sl_hit:
            print(f"   (nota: tras tu cierre, el precio TOCÓ el stop {t['sl']:.4f} el {sl_hit[0]:%m-%d %H:%M})")


def analizar_v28():
    print("\n" + "=" * 78)
    print("V28 — si NO cerrabas, ¿habría llegado a 2R (meta) o STOP primero? (1h)")
    print("=" * 78)
    man = [t for t in json.load(open(V28)) if t['status'] == 'CERRADA' and 'MANUAL' in (t.get('exit_reason') or '')]
    llego2r = stop = sigue = 0
    for t in man:
        sym = t['symbol']; ex = datetime.fromisoformat(t['exit_time'])
        start = int(ex.timestamp() * 1000)
        df = klines(sym, '1h', start)
        post = df[df['time'] > ex.replace(tzinfo=timezone.utc)]
        res = 'sigue/ventana'
        for _, row in post.iterrows():
            if t['type'] == 'SHORT':
                if row['high'] >= t['sl']: res = 'STOP'; break
                if row['low'] <= t['tp']: res = '2R ✅'; break
            else:
                if row['low'] <= t['sl']: res = 'STOP'; break
                if row['high'] >= t['tp']: res = '2R ✅'; break
        if res == '2R ✅': llego2r += 1
        elif res == 'STOP': stop += 1
        else: sigue += 1
        print(f"  {sym:8} {t['type']:5} cerraste {ex:%m-%d %H:%M} @ {t['exit_price']} (pico {t.get('peak_progress',0):.0f}%, PnL ${t['pnl']:+.2f}) "
              f"→ si dejabas: {res}")
    n = len(man)
    print(f"\n  RESUMEN V28: de {n} cierres manuales → habría llegado a 2R: {llego2r} | habría STOPEADO: {stop} | sin resolver: {sigue}")


if __name__ == '__main__':
    analizar_v26()
    analizar_v28()
