"""
revision_manual.py — Procedimiento de revisión manual vela-por-vela (V28).

PROCEDIMIENTO (acordado 2026-07-01): el usuario elige UNA operación a la vez
("revisemos la de XRPUSDT del martes"), y este script arma el paquete de
datos para esa sesión — no decide nada ni cambia código. Se corre a pedido
del usuario, no automáticamente.

Uso:
  python3 revision_manual.py listar
      Lista los trades conocidos localmente (requiere trades_v28.json
      sincronizado desde GCS — bot_alpha_portfolio/v28_copilot/trades_v28.json).

  python3 revision_manual.py ver <trade_id>
      Arma el paquete completo para un trade_id de trades_v28.json/forense/.

  python3 revision_manual.py manual SYMBOL TIPO ENTRY_ISO [EXIT_ISO]
      Arma el paquete SIN depender de trades_v28.json/forense — útil cuando
      el archivo local todavía no está sincronizado con el estado real de la
      VM (ej. bloqueo de credenciales GCP). ENTRY_ISO/EXIT_ISO en UTC,
      formato "2026-06-28 14:00". Si no hay EXIT_ISO, se asume abierta (usa
      la última vela disponible).

Qué arma el paquete (para cualquiera de los 2 modos):
  1. Ventana de velas 1h: ANTES velas antes de la entrada → DESPUES velas
     después del cierre (o hasta ahora si sigue abierta) — con indicadores
     recalculados (mismo indicadores.py del bot).
  2. Contexto de ENTRADA: tendencia diaria, ADX/RSI/volumen en la vela de
     entrada, patrón (si hay forense).
  3. CAMINO del trade: avance % vela a vela desde la entrada — dónde está el
     pico, cuándo giró.
  4. Contexto de SALIDA: motivo, avance al cierre, giveback (pico − cierre).
  5. POST-MORTEM: qué hizo el precio en las velas DESPUÉS del cierre — ¿la
     tendencia se revirtió de verdad, o el bot salió de un ruido normal y el
     precio siguió a favor de la dirección original? Esta es la pregunta que
     el usuario quiere responder operación por operación.

No abre ni cierra nada, no toca config — solo lectura y cómputo.
"""
import json
import os
import sys
from datetime import datetime

import pandas as pd

import config
import estrategia
from binance_client import BinanceClient
from indicadores import calcular_indicadores

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
ANTES = 20
DESPUES = 30


def _cargar_trades():
    ruta = os.path.join(DIR_BASE, 'trades_v28.json')
    if not os.path.isfile(ruta):
        return None
    with open(ruta) as f:
        return json.load(f)


def listar():
    trades = _cargar_trades()
    if trades is None:
        print("No hay trades_v28.json local (falta sincronizar desde GCS). "
              "Usá 'manual SYMBOL TIPO ENTRY_ISO [EXIT_ISO]' con los datos que "
              "veas en Telegram/estado.")
        return
    trades = sorted(trades, key=lambda t: t.get('entry_time', ''))
    print(f"{'id':>10} | {'symbol':9} | {'tipo':5} | {'entrada':16} | {'salida':16} | "
          f"{'pico%':>6} | {'PnL':>8} | motivo")
    for t in trades:
        print(f"{t['id']:>10} | {t['symbol']:9} | {t['type']:5} | "
              f"{str(t.get('entry_time',''))[:16]:16} | {str(t.get('exit_time') or '(abierta)')[:16]:16} | "
              f"{t.get('peak_progress',0):>5.0f}% | ${t.get('pnl',0):>+7.2f} | {t.get('exit_reason') or ''}")


def _ventana(symbol, entry_ts, exit_ts):
    cliente = BinanceClient()
    # bootstrap amplio hacia atrás/adelante centrado en el trade
    inicio = entry_ts - pd.Timedelta(hours=ANTES)
    fin = (exit_ts or pd.Timestamp.utcnow().tz_localize(None)) + pd.Timedelta(hours=DESPUES)
    total_horas = int((fin - inicio).total_seconds() // 3600) + 5
    df = cliente.klines_paginated(symbol, total_horas, end_time_ms=int(fin.timestamp() * 1000))
    return calcular_indicadores(df)


def _reporte(symbol, tipo, entry_time, exit_time, entry_price=None, sl=None,
            exit_price=None, exit_reason=None, pico=None, forense=None):
    entry_ts = pd.Timestamp(entry_time)
    exit_ts = pd.Timestamp(exit_time) if exit_time else None
    print(f"\n{'='*78}\nREVISIÓN — {symbol} {tipo} | entrada {entry_ts} | salida {exit_ts or '(abierta)'}\n{'='*78}")

    df = _ventana(symbol, entry_ts, exit_ts)
    i_entry = (df['time'] - entry_ts).abs().idxmin()
    fila_entry = df.iloc[i_entry]

    print("\n-- CONTEXTO DE ENTRADA --")
    print(f"  Precio: {entry_price if entry_price else fila_entry['close']:.4f} | "
          f"RSI {fila_entry['RSI']:.1f} | ADX {fila_entry['ADX']:.1f} | "
          f"vol/MA {fila_entry['volume']/fila_entry['Volume_MA']:.2f}x" if fila_entry['Volume_MA'] else "")
    if forense:
        act = forense.get('activacion', {})
        print(f"  Patrón: {act.get('patron', forense.get('pattern', 'N/D'))} | "
              f"prob_reversion al abrir: {act.get('prob_reversion', 'N/D')}")
    tend_diaria = None
    try:
        tend_diaria = estrategia.tendencia_actual(df.iloc[:i_entry + 1])
    except Exception:
        pass
    print(f"  Tendencia (motor) en la vela de entrada: {tend_diaria}")

    print("\n-- CAMINO DEL TRADE (vela a vela desde la entrada) --")
    t_fake = {'type': tipo, 'entry_price': entry_price or float(fila_entry['close']),
             'tp': None, 'sl': sl}
    # Si no tenemos tp real, aproximar con el sizing estándar del bot para que
    # el % de avance sea comparable al que vio el usuario en Telegram.
    if sl is not None and t_fake['tp'] is None:
        dist_sl = abs(t_fake['entry_price'] - sl)
        dist_tp = dist_sl / config.SL_FRACTION_OF_TP
        t_fake['tp'] = t_fake['entry_price'] + dist_tp if tipo == 'LONG' else t_fake['entry_price'] - dist_tp

    pico_visto = 0.0
    i_exit = len(df) - 1
    ep = t_fake['entry_price']
    for j in range(i_entry, len(df)):
        row = df.iloc[j]
        if exit_ts is not None and row['time'] > exit_ts:
            i_exit = j - 1
            break
        if t_fake['tp'] is not None:
            prog = estrategia.calcular_progreso(t_fake, row['close'])
            marca = ""
            if prog > pico_visto:
                pico_visto = prog
                marca = "  <-- nuevo pico"
            print(f"  {row['time']} close={row['close']:.4f} avance={prog:6.1f}%{marca}")
        else:
            # sin sl/tp real (modo manual sin esos datos): mostrar precio
            # crudo y % de movimiento desde la entrada (sin escala de R).
            mov = (row['close'] - ep) / ep * 100 if tipo == 'LONG' else (ep - row['close']) / ep * 100
            marca = ""
            if mov > pico_visto:
                pico_visto = mov
                marca = "  <-- nuevo pico"
            print(f"  {row['time']} close={row['close']:.4f} mov_desde_entrada={mov:6.2f}%{marca}")

    print("\n-- CONTEXTO DE SALIDA --")
    print(f"  Motivo: {exit_reason or 'N/D'} | Precio salida: {exit_price if exit_price else 'N/D'}")
    print(f"  Pico visto en esta ventana: {pico_visto:.1f}% "
          f"(el registrado por el bot: {pico if pico is not None else 'N/D'})")

    print("\n-- POST-MORTEM: ¿qué hizo el precio DESPUÉS del cierre? --")
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
            extremo = post['high'].max() if tipo == 'LONG' else post['low'].min()
            mov_extremo = abs(extremo - precio_cierre) / precio_cierre * 100
            print(f"  {len(post)} velas después del cierre | precio {DESPUES}h+ después: {ultimo:.4f} "
                  f"({'A FAVOR' if a_favor else 'EN CONTRA'} de la dirección original)")
            print(f"  Máximo movimiento a favor de la dirección original tras el cierre: "
                  f"{mov_extremo:.2f}% ({'sí hubo continuación' if mov_extremo > 1 else 'movimiento chico, probablemente ruido'})")
            tend_post = estrategia.tendencia_actual(df.iloc[:min(i_exit + 12, len(df))])
            print(f"  Tendencia (motor) ~12h después del cierre: {tend_post} "
                  f"({'se mantuvo' if tend_post == tipo else 'ya había girado'})")


def ver(trade_id):
    trades = _cargar_trades() or []
    t = next((x for x in trades if x['id'] == trade_id), None)
    if not t:
        print(f"trade_id {trade_id} no encontrado en trades_v28.json")
        return
    forense_path = os.path.join(DIR_BASE, 'forense', f"{trade_id}.json")
    forense = None
    if os.path.isfile(forense_path):
        with open(forense_path) as f:
            forense = json.load(f)
    _reporte(t['symbol'], t['type'], t['entry_time'], t.get('exit_time'),
            entry_price=t.get('entry_price'), sl=t.get('sl'),
            exit_price=t.get('exit_price'), exit_reason=t.get('exit_reason'),
            pico=t.get('peak_progress'), forense=forense)


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
