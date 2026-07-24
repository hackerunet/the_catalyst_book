"""Revisión read-only de las posiciones abiertas de V26: para cada una, evalúa
con la lógica REAL del bot (4h) si la tendencia que la abrió sigue vigente o
qué tan cerca está de un flip / del stop. No toca nada."""
import json
import requests

import config
import estrategia
from indicadores import calcular_indicadores, momentum_diario

TRADES = '/tmp/bugcheck2/v26_review.json'


def klines_4h(sym, n=600):
    r = requests.get('https://fapi.binance.com/fapi/v1/klines',
                     params={'symbol': sym, 'interval': '4h', 'limit': n}, timeout=20)
    import pandas as pd
    df = pd.DataFrame(r.json(), columns=['time', 'open', 'high', 'low', 'close',
                                         'volume', 'ct', 'qv', 'n', 'tbv', 'tqv', 'i'])
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
    return df[['time', 'open', 'high', 'low', 'close', 'volume']]


def main():
    trades = [t for t in json.load(open(TRADES)) if t['status'] == 'ABIERTA']
    print(f"{'='*92}\nREVISIÓN POSICIONES V26 (4h, seguimiento de tendencia) — lógica real del bot\n{'='*92}")
    for t in trades:
        sym = t['symbol']
        df = calcular_indicadores(klines_4h(sym))
        r = df.iloc[-1]
        precio = float(r['close'])
        e50, e200, adx = float(r['EMA_50']), float(r['EMA_200']), float(r['ADX'])
        diario = momentum_diario(df)
        tend = estrategia.tendencia_actual(df)

        entry, sl = t['entry_price'], t['sl']
        # unrealized % sobre nocional (SHORT)
        upnl_pct = (entry - precio) / entry * 100
        # progreso hacia el TP-ref (avance que ve el bot)
        prog = estrategia.calcular_progreso(t, precio)
        # distancia a stop: cuánto tiene que subir el precio para tocar el SL
        dist_sl = (sl - precio) / precio * 100
        # sobre-extensión vs EMA200 (a más negativo = más estirado abajo = más riesgo de rebote)
        overext = (precio - e200) / e200 * 100
        # "primera barrera" para perder la alineación SHORT: el precio cruzar la EMA50
        dist_ema50 = (e50 - precio) / precio * 100  # cuánto subir para tocar EMA50

        flip_seria = 'LONG' if tend == 'LONG' else None
        estado_tend = (f"SHORT vigente" if tend == 'SHORT'
                       else "LATERAL (alineación rota — no sostiene el short)" if tend == 'LATERAL'
                       else "FLIP a LONG (¡el bot cerraría!)")

        print(f"\n■ {sym} SHORT  | entry {entry}  precio {precio}  SL {sl:.4f}")
        print(f"   PnL no realizado: {upnl_pct:+.2f}% del nocional | avance que ve el bot: {prog:.0f}%")
        print(f"   Tendencia 4h AHORA: {estado_tend}")
        print(f"     · precio<EMA50: {precio<e50} (EMA50 {e50:.4f}, falta +{dist_ema50:.2f}% para tocarla)")
        print(f"     · EMA50<EMA200: {e50<e200} (EMA200 {e200:.4f})")
        print(f"     · ADX {adx:.1f} ({'fuerte ≥25' if adx>=25 else 'ok ≥20' if adx>=20 else 'DÉBIL <20'}) | momentum diario: {diario}")
        print(f"   Sobre-extensión vs EMA200: {overext:+.2f}% ({'muy estirado abajo → riesgo de rebote' if overext< -8 else 'moderado' if overext<-4 else 'normal'})")
        print(f"   Riesgo: si el precio SUBE +{dist_sl:.2f}% toca el STOP ({sl:.4f}) → cierre "
              f"{'en GANANCIA' if sl<entry else 'en PÉRDIDA de '+format((entry-sl)/entry*100,'+.2f')+'%'}")
    print(f"\n{'='*92}")
    print("Recordatorio mecánico: V26 NO trailing — solo cierra por (a) STOP estático o (b) FLIP")
    print("de alineación 4h al cierre de vela. El avance no realizado NO está protegido entre medio.")
    print("Para asegurar manualmente: botón TOMAR PROFIT en Telegram (cierra a mercado ya).")


if __name__ == '__main__':
    main()
