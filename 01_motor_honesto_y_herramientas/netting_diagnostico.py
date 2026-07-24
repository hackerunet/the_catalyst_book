#!/usr/bin/env python3
"""¿Cuánto se pisan V26 y V36 en la MISMA cuenta? (daño del neteo)

Las órdenes de ambos bots van sin `positionSide` = modo ONE-WAY = Binance NETEA
por símbolo. Si los dos tienen posición abierta en el mismo símbolo:
  - misma dirección  -> Binance ve UNA posición de tamaño sumado; cuando uno
    cierra, es una REDUCCIÓN PARCIAL, no una operación cerrada de ese bot.
  - dirección opuesta -> se CANCELAN (parcial o totalmente). El bot cree que
    tiene una posición que en la cuenta no existe (o existe al revés).

En ambos casos el récord que ve un copiador NO es el de V26 ni el de V36.
Esto MIDE cuánto ocurre sobre 4 años. SOLO LECTURA.
"""
from collections import defaultdict

import numpy as np
import pandas as pd

from suavizado_v37 import correr, CFG_V26, CFG_V36, CACHE_4H_ORIG, CACHE_15M_4Y, TOP4


def intervalos(bt):
    """symbol -> lista de (entrada, salida, tipo) de cada trade cerrado."""
    d = defaultdict(list)
    for t in bt.trades:
        if t['status'] != 'CERRADA':
            continue
        d[t['symbol']].append((pd.Timestamp(t['entry_time']),
                               pd.Timestamp(t['exit_time']), t['type']))
    return d


def solapamiento(a, b):
    """Segundos de solape entre dos intervalos, y si son misma dirección."""
    ini = max(a[0], b[0])
    fin = min(a[1], b[1])
    if fin <= ini:
        return 0.0, None
    return (fin - ini).total_seconds(), (a[2] == b[2])


def main():
    print("Corriendo V26 (4h)...")
    v26 = intervalos(correr(CACHE_4H_ORIG, CFG_V26))
    print("Corriendo V36 (15m)... (tarda)")
    v36 = intervalos(correr(CACHE_15M_4Y, CFG_V36, symbols=TOP4))

    compartidos = sorted(set(v26) & set(v36))
    print(f"\n{'='*80}\n  DAÑO DEL NETEO — V26 y V36 en la MISMA cuenta (4 años)\n{'='*80}")
    print(f"  Símbolos de V26: {len(v26)} | de V36: {len(v36)} | COMPARTIDOS: "
          f"{len(compartidos)} -> {', '.join(compartidos)}")

    tot_v26 = tot_col = tot_mismo = tot_op = 0.0
    n_col = n_mismo = n_op = 0
    print(f"\n  {'símbolo':10} {'horas V26':>10} {'h. pisadas':>11} {'% pisado':>9}"
          f" {'choques':>8} {'misma dir':>10} {'opuesta':>8}")
    print(f"  {'-'*10} {'-'*10} {'-'*11} {'-'*9} {'-'*8} {'-'*10} {'-'*8}")
    for s in compartidos:
        h26 = sum((a[1] - a[0]).total_seconds() for a in v26[s])
        col = mismo = op = 0.0
        c = m = o = 0
        for a in v26[s]:
            for b in v36[s]:
                seg, igual = solapamiento(a, b)
                if seg <= 0:
                    continue
                col += seg
                c += 1
                if igual:
                    mismo += seg; m += 1
                else:
                    op += seg; o += 1
        print(f"  {s:10} {h26/3600:>10.0f} {col/3600:>11.0f} {100*col/h26:>8.1f}%"
              f" {c:>8} {m:>10} {o:>8}")
        tot_v26 += h26; tot_col += col; tot_mismo += mismo; tot_op += op
        n_col += c; n_mismo += m; n_op += o

    print(f"\n  >>> De las horas que V26 tuvo posición en los 4 símbolos compartidos,")
    print(f"      el {100*tot_col/tot_v26:.1f}% las pasó NETEADA con una posición de V36.")
    print(f"  >>> {n_col} choques: {n_mismo} misma dirección (tamaños se SUMAN),"
          f" {n_op} opuesta (se CANCELAN).")
    print(f"  >>> Horas neteadas: {tot_col/3600:,.0f}h "
          f"({tot_mismo/3600:,.0f}h sumando, {tot_op/3600:,.0f}h cancelando)")
    print(f"\n  LECTURA: en esas horas, el récord de Binance no refleja ni a V26 ni a V36.")
    print(f"  Las {n_op} colisiones opuestas son las graves: un bot cree tener una")
    print(f"  posición que en la cuenta está cancelada por el otro.")


if __name__ == '__main__':
    main()
