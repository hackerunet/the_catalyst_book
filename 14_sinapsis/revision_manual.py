"""
revision_manual.py — Procedimiento de revisión manual vela-por-vela (V26).

PROCEDIMIENTO (acordado 2026-07-01): el usuario elige UNA operación a la vez,
este script arma el paquete de datos para esa sesión conjunta — no decide ni
cambia nada. Se corre a pedido del usuario, no automáticamente.

Uso:
  python3 revision_manual.py listar
      Lista los trades conocidos localmente (requiere trades_v26.json
      sincronizado desde GCS).

  python3 revision_manual.py ver <trade_id>
      Arma el paquete completo para un trade_id de trades_v26.json.

  python3 revision_manual.py manual SYMBOL TIPO ENTRY_ISO [EXIT_ISO]
      Arma el paquete SIN depender de trades_v26.json — útil si el archivo
      local no está sincronizado con el estado real de la VM. ENTRY_ISO/
      EXIT_ISO en UTC, formato "2026-06-28 14:00". Velas de 4h (config.INTERVAL).
      Sin EXIT_ISO se asume abierta.

Qué arma el paquete:
  1. Ventana de velas 4h: ANTES velas antes de la entrada → DESPUES velas
     después del cierre (o hasta ahora si sigue abierta).
  2. Contexto de ENTRADA: EMA50/200 + ADX + momentum diario en la vela de
     entrada (mismo criterio de tendencia_actual que decide el cruce).
  3. CAMINO del trade: avance % (unidades de "recorrido a TP interno", igual
     a lo que muestra /estado) vela a vela — dónde está el pico, cuándo giró.
  4. Contexto de SALIDA: motivo (FLIP o STOP), avance al cierre, giveback.
  5. POST-MORTEM: la pregunta central del usuario — tras el cierre (sobre
     todo si fue por STOP con un pico grande), ¿la tendencia original
     realmente murió, o el precio retomó esa dirección poco después?
     Muestra tendencia_actual() en las velas posteriores al cierre y el
     movimiento de precio a favor/en contra de la dirección original.

No abre ni cierra nada, no toca config — solo lectura y cómputo.
"""
import json
import os
import sys

import pandas as pd

import config
import estrategia
from binance_client import BinanceClient
from indicadores import calcular_indicadores

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
ANTES = 15   # velas 4h antes de la entrada (~2.5 días de contexto previo)
DESPUES = 30  # velas 4h después del cierre (~5 días de post-mortem)


def _cargar_trades():
    ruta = os.path.join(DIR_BASE, 'trades_v26.json')
    if not os.path.isfile(ruta):
        return None
    with open(ruta) as f:
        return json.load(f)


def listar():
    trades = _cargar_trades()
    if trades is None:
        print("No hay trades_v26.json local (falta sincronizar desde GCS). "
              "Usá 'manual SYMBOL TIPO ENTRY_ISO [EXIT_ISO]' con los datos que "
              "veas en Telegram/estado.")
        return
    trades = sorted(trades, key=lambda t: t.get('entry_time', ''))
    print(f"{'id':>10} | {'symbol':9} | {'tipo':5} | {'entrada':16} | {'salida':16} | "
          f"{'pico%':>7} | {'PnL':>8} | motivo")
    for t in trades:
        print(f"{t['id']:>10} | {t['symbol']:9} | {t['type']:5} | "
              f"{str(t.get('entry_time',''))[:16]:16} | {str(t.get('exit_time') or '(abierta)')[:16]:16} | "
              f"{t.get('peak_progress',0):>6.0f}% | ${t.get('pnl',0):>+7.2f} | {t.get('exit_reason') or ''}")


def _ventana(symbol, entry_ts, exit_ts):
    cliente = BinanceClient()
    inicio = entry_ts - pd.Timedelta(hours=4 * ANTES)
    fin = (exit_ts or pd.Timestamp.utcnow().tz_localize(None)) + pd.Timedelta(hours=4 * DESPUES)
    total_velas = int((fin - inicio).total_seconds() // (4 * 3600)) + 5
    df = cliente.klines_paginated(symbol, total_velas, end_time_ms=int(fin.timestamp() * 1000))
    return calcular_indicadores(df)


def _reporte(symbol, tipo, entry_time, exit_time, entry_price=None, sl=None,
            exit_price=None, exit_reason=None, pico=None):
    entry_ts = pd.Timestamp(entry_time)
    exit_ts = pd.Timestamp(exit_time) if exit_time else None
    print(f"\n{'='*78}\nREVISIÓN V26 — {symbol} {tipo} | entrada {entry_ts} | "
          f"salida {exit_ts or '(abierta)'}\n{'='*78}")

    df = _ventana(symbol, entry_ts, exit_ts)
    i_entry = (df['time'] - entry_ts).abs().idxmin()
    fila_entry = df.iloc[i_entry]
    ep = entry_price or float(fila_entry['close'])

    print("\n-- CONTEXTO DE ENTRADA --")
    ema50, ema200, adx = fila_entry.get('EMA_50'), fila_entry.get('EMA_200'), fila_entry.get('ADX')
    print(f"  Precio: {ep:.4f} | EMA50 {ema50:.4f} | EMA200 {ema200:.4f} | ADX {adx:.1f}")
    tend_entrada = estrategia.tendencia_actual(df.iloc[:i_entry + 1])
    tend_prev = estrategia.tendencia_actual(df.iloc[:i_entry]) if i_entry > 0 else None
    print(f"  Tendencia (motor) en la entrada: {tend_entrada} "
          f"(vela anterior: {tend_prev}) {'<- FLIP recién confirmado' if tend_prev != tend_entrada else ''}")

    print("\n-- CAMINO DEL TRADE (vela a vela desde la entrada) --")
    t_fake = {'type': tipo, 'entry_price': ep, 'tp': None, 'sl': sl}
    if sl is not None:
        dist_sl = abs(ep - sl)
        dist_tp = dist_sl / config.SL_FRACTION_OF_TP
        t_fake['tp'] = ep + dist_tp if tipo == 'LONG' else ep - dist_tp

    pico_visto = 0.0
    i_exit = len(df) - 1
    for j in range(i_entry, len(df)):
        row = df.iloc[j]
        if exit_ts is not None and row['time'] > exit_ts:
            i_exit = j - 1
            break
        if t_fake['tp'] is not None:
            prog = estrategia.calcular_progreso(t_fake, row['close'])
        else:
            prog = (row['close'] - ep) / ep * 100 if tipo == 'LONG' else (ep - row['close']) / ep * 100
        marca = ""
        if prog > pico_visto:
            pico_visto = prog
            marca = "  <-- nuevo pico"
        tend_j = estrategia.tendencia_actual(df.iloc[:j + 1])
        flip = "  *** FLIP DE TENDENCIA ***" if tend_j != tipo and j > i_entry else ""
        print(f"  {row['time']} close={row['close']:.4f} avance={prog:6.1f}% tend={tend_j}{marca}{flip}")

    print("\n-- CONTEXTO DE SALIDA --")
    print(f"  Motivo: {exit_reason or 'N/D'} | Precio salida: {exit_price if exit_price else 'N/D'}")
    print(f"  Pico visto en esta ventana: {pico_visto:.1f}% "
          f"(el registrado por el bot: {pico if pico is not None else 'N/D'})")
    if pico_visto > 0 and exit_reason and 'STOP' in exit_reason:
        print(f"  ⚠️ GIVEBACK: se devolvió TODO el avance ({pico_visto:.1f}% -> STOP) — "
              f"este es el patrón que preguntás si es la norma histórica (sí lo es, ver conclusiones).")

    print("\n-- POST-MORTEM: ¿la tendencia original volvió después del cierre? --")
    if exit_ts is None:
        print("  (operación sigue abierta — no hay post-mortem todavía)")
    else:
        post = df[df['time'] > exit_ts]
        if post.empty:
            print("  (sin velas posteriores en la ventana descargada)")
        else:
            precio_cierre = exit_price or float(df.iloc[i_exit]['close'])
            ultimo = float(post['close'].iloc[-1])
            a_favor = (ultimo > precio_cierre) if tipo == 'LONG' else (ultimo < precio_cierre)
            print(f"  {len(post)} velas (4h) después del cierre | precio final: {ultimo:.4f} "
                  f"({'A FAVOR' if a_favor else 'EN CONTRA'} de la dirección original {tipo})")
            # ¿en algún momento posterior al cierre volvió a confirmarse la MISMA tendencia?
            volvio = False
            for j in range(i_exit + 1, len(df)):
                if estrategia.tendencia_actual(df.iloc[:j + 1]) == tipo:
                    volvio = True
                    print(f"  La tendencia (motor) volvió a marcar {tipo} en {df.iloc[j]['time']} "
                          f"({(df.iloc[j]['time'] - exit_ts)})  después del cierre")
                    break
            if not volvio:
                print(f"  La tendencia NUNCA volvió a marcar {tipo} en la ventana post-cierre "
                      f"({len(post)} velas / ~{len(post)*4}h) — el giro fue real, no ruido.")


def ver(trade_id):
    trades = _cargar_trades() or []
    t = next((x for x in trades if x['id'] == trade_id), None)
    if not t:
        print(f"trade_id {trade_id} no encontrado en trades_v26.json")
        return
    _reporte(t['symbol'], t['type'], t['entry_time'], t.get('exit_time'),
            entry_price=t.get('entry_price'), sl=t.get('sl'),
            exit_price=t.get('exit_price'), exit_reason=t.get('exit_reason'),
            pico=t.get('peak_progress'))


def manual(symbol, tipo, entry_iso, exit_iso=None):
    _reporte(symbol, tipo.upper(), entry_iso, exit_iso)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == 'listar':
        listar()
    elif cmd == 'ver':
        ver(sys.argv[2])
    elif cmd == 'manual':
        manual(*sys.argv[2:6])
    else:
        print(__doc__)
