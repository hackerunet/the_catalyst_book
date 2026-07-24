"""
diagnostico_mercado.py — VISUALIZADOR + ANÁLISIS DE OPORTUNIDADES (SOLO LECTURA).

NO toca ni el motor ni la estrategia de ningún bot. Importa los módulos PROPIOS
del bot indicado (config/indicadores/estrategia/patrones/binance_client) sin
modificarlos y llama EXACTAMENTE a `estrategia.tendencia_actual` y
`estrategia.evaluar_entrada` — la misma decisión que toma el bot en vivo — para:

  1. Dibujar (ASCII) el movimiento de cada símbolo en los últimos N días.
  2. Reproducir, vela cerrada por vela cerrada, la decisión del bot y atribuir
     POR QUÉ se abstuvo (qué "puerta" lo bloqueó).
  3. Listar los momentos que estuvieron MÁS CERCA de ser una entrada
     ("casi-entradas") para juzgar si las reglas son demasiado rígidas.

Uso:
    python3 diagnostico_mercado.py <carpeta_bot> [dias]

Ej:
    python3 diagnostico_mercado.py ../v26_tendencia 5
    python3 diagnostico_mercado.py ../stable_v25_prototype 5
    python3 diagnostico_mercado.py ../v28_copilot 5
"""
import os
import sys

import pandas as pd

# ----- cargar los módulos PROPIOS del bot indicado (sin modificarlos) -----
BOT_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '../v26_tendencia')
DIAS = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
sys.path.insert(0, BOT_DIR)

import config              # noqa: E402
import indicadores         # noqa: E402
import estrategia          # noqa: E402
from patrones import detectar_patrones, PATRONES_DE_MECHA  # noqa: E402
from binance_client import BinanceClient  # noqa: E402

BARS_POR_DIA = {'1h': 24, '2h': 12, '4h': 6, '1d': 1}
INTERVALO = config.INTERVAL
VELAS_VENTANA = int(round(DIAS * BARS_POR_DIA.get(INTERVALO, 24)))

SPARK = '▁▂▃▄▅▆▇█'


def sparkline(vals):
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return SPARK[0] * len(vals)
    return ''.join(SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in vals)


def chart_ascii(times, closes, marcas, alto=12, ancho_max=96):
    """Gráfico de línea ASCII del cierre + fila de tendencia (L/S/·) debajo."""
    n = len(closes)
    paso = max(1, n // ancho_max)
    idx = list(range(0, n, paso))
    cs = [closes[i] for i in idx]
    ms = [marcas[i] for i in idx]
    lo, hi = min(cs), max(cs)
    rng = hi - lo if hi - lo > 1e-12 else 1.0
    grid = [[' '] * len(cs) for _ in range(alto)]
    for col, v in enumerate(cs):
        fila = alto - 1 - int((v - lo) / rng * (alto - 1))
        grid[fila][col] = '•'
    out = []
    for r, fila in enumerate(grid):
        precio = hi - (hi - lo) * r / (alto - 1)
        out.append(f"  {precio:>11.4f} |{''.join(fila)}")
    out.append(f"  {'tendencia':>11} |{''.join(ms)}")
    out.append(f"  {'(cada ' + str(paso) + ' velas)':>11} |"
               f"{times[idx[0]].strftime('%m-%d %Hh')} → {times[idx[-1]].strftime('%m-%d %Hh')}")
    return '\n'.join(out)


def razon_no_entrada(df_hist):
    """
    Re-deriva (solo lectura) la PRIMERA puerta que bloqueó la entrada, en el
    mismo orden que estrategia.evaluar_entrada. Devuelve (codigo, detalle).
    El veredicto final se valida contra evaluar_entrada (abajo).
    """
    if len(df_hist) < config.WARMUP_CANDLES:
        return 'WARMUP', 'historia insuficiente'

    c = df_hist['close'].iloc[-1]
    e50, e200 = df_hist['EMA_50'].iloc[-1], df_hist['EMA_200'].iloc[-1]
    adx = df_hist['ADX'].iloc[-1]
    diario = indicadores.momentum_diario(df_hist)

    # --- puerta de tendencia ---
    if pd.isna(e50) or pd.isna(e200):
        return 'LATERAL', 'EMA sin datos'
    if adx < config.ADX_LATERAL_MAX:
        return 'LATERAL_ADX', f'ADX={adx:.1f} < {config.ADX_LATERAL_MAX}'
    apilada_long = c > e50 > e200
    apilada_short = c < e50 < e200
    if not (apilada_long or apilada_short):
        return 'LATERAL_EMA', 'precio/EMA50/EMA200 no apiladas'
    lado = 'LONG' if apilada_long else 'SHORT'
    if diario != lado:
        return 'LATERAL_DIARIO', f'apilado {lado} pero momentum diario={diario}'

    tendencia = lado  # tendencia_actual daría esto

    modo = getattr(config, 'ENTRY_MODE', 'patrones')
    if modo == 'cruce':
        if estrategia.tendencia_actual(df_hist.iloc[:-1]) == tendencia:
            return 'SIN_FLIP', f'tendencia {tendencia} ya estaba activa (no es el cruce)'
    elif modo == 'patrones':
        patrones = detectar_patrones(df_hist)
        if any(p['tipo'] == 'incertidumbre' for p in patrones):
            return 'VETO_DOJI', 'doji presente'
        atr = df_hist['ATR'].iloc[-1]
        body = df_hist['Body'].iloc[-1]
        rango = float(df_hist['high'].iloc[-1] - df_hist['low'].iloc[-1])
        vma = df_hist['Volume_MA'].iloc[-1]
        vol = df_hist['volume'].iloc[-1]
        cands = [p for p in patrones if p['dir'] == tendencia]
        if not cands:
            return 'SIN_PATRON', f'sin patrón a favor de {tendencia}'
        # ¿algún candidato falla solo por convicción o por volumen?
        falla_body = falla_vol = False
        for p in cands:
            es_mecha = p['nombre'] in PATRONES_DE_MECHA
            conv_ok = (rango >= atr * config.WICK_RANGE_MIN_ATR_FRACTION) if es_mecha \
                else (body >= atr * config.BODY_MIN_ATR_FRACTION)
            if not conv_ok:
                falla_body = True
                continue
            if p['tipo'] == 'continuacion':
                vol_ok = (not pd.isna(vma)) and vma > 0 and vol > vma
            else:
                vol_ok = (not pd.isna(vma)) and vma > 0 and vol >= vma * config.REVERSAL_VOL_FLOOR
            if not vol_ok:
                falla_vol = True
        if falla_body and not falla_vol:
            return 'SIN_CONVICCION', f'patrón {tendencia} pero cuerpo/rango < umbral'
        if falla_vol:
            return 'SIN_VOLUMEN', f'patrón {tendencia} pero volumen insuficiente'
        return 'SIN_PATRON', f'patrón {tendencia} no cumple geometría'

    # --- guarda RSI (común) ---
    rsi = df_hist['RSI'].iloc[-1]
    if tendencia == 'LONG' and rsi > config.RSI_MAX_LONG:
        return 'RSI_GUARD', f'LONG con RSI={rsi:.0f} > {config.RSI_MAX_LONG}'
    if tendencia == 'SHORT' and rsi < config.RSI_MIN_SHORT:
        return 'RSI_GUARD', f'SHORT con RSI={rsi:.0f} < {config.RSI_MIN_SHORT}'

    return 'ENTRADA', f'{tendencia}'


def marca_tendencia(cod):
    if cod == 'ENTRADA':
        return '★'
    if cod.startswith('LATERAL') or cod == 'WARMUP':
        return '·'
    return 'L' if False else ('S')  # placeholder, sobreescrito abajo


def main():
    print("=" * 78)
    print(f" DIAGNÓSTICO DE MERCADO — bot: {os.path.basename(BOT_DIR)}")
    print(f" intervalo={INTERVALO} | modo_entrada={getattr(config,'ENTRY_MODE','patrones')}"
          f" | modo_salida={getattr(config,'EXIT_MODE','escalera')}")
    print(f" ventana = últimos {DIAS:g} días ({VELAS_VENTANA} velas de {INTERVALO})")
    print(f" símbolos = {', '.join(config.SYMBOLS)}")
    print("=" * 78)

    cli = BinanceClient()
    total = max(config.BOOTSTRAP_CANDLES, 520 + VELAS_VENTANA)

    resumen_global = {}
    for sym in config.SYMBOLS:
        try:
            df = cli.klines_paginated(sym, total)
        except Exception as e:
            print(f"\n[{sym}] ERROR al traer datos: {e}")
            continue
        df = indicadores.calcular_indicadores(df)
        df = df.reset_index(drop=True)
        # excluir la última vela (en formación) para evaluar solo velas CERRADAS
        n = len(df) - 1
        ini = max(config.WARMUP_CANDLES, n - VELAS_VENTANA)

        codigos, marcas, casi = [], [], []
        for i in range(ini, n):
            hist = df.iloc[:i + 1]
            cod, det = razon_no_entrada(hist)
            # veredicto autoritativo del bot (la decisión real):
            real = estrategia.evaluar_entrada(hist)
            if (real is not None) != (cod == 'ENTRADA'):
                cod = 'ENTRADA' if real is not None else cod  # confía en el bot
            codigos.append(cod)
            if cod == 'ENTRADA':
                m = '★'
            elif cod in ('LATERAL_ADX', 'LATERAL_EMA', 'LATERAL_DIARIO', 'LATERAL', 'WARMUP'):
                m = '·'
            else:
                # tendencia alineada pero entrada bloqueada por filtro fino
                t = estrategia.tendencia_actual(hist)
                m = 'L' if t == 'LONG' else ('S' if t == 'SHORT' else '?')
            marcas.append(m)
            # casi-entradas: tendencia alineada y bloqueo "fino", o ADX casi 20
            if cod in ('SIN_PATRON', 'SIN_CONVICCION', 'SIN_VOLUMEN', 'VETO_DOJI',
                       'RSI_GUARD', 'SIN_FLIP'):
                casi.append((df['time'].iloc[i], df['close'].iloc[i], cod, det))
            elif cod == 'LATERAL_ADX':
                adxv = df['ADX'].iloc[i]
                if adxv >= config.ADX_LATERAL_MAX - 3:
                    casi.append((df['time'].iloc[i], df['close'].iloc[i],
                                 'ADX_CERCA', det))

        win = df.iloc[ini:n]
        closes = win['close'].tolist()
        times = win['time'].tolist()
        chg = (closes[-1] / closes[0] - 1) * 100
        tend_now = estrategia.tendencia_actual(df.iloc[:n])
        adx_now = df['ADX'].iloc[n - 1]
        rsi_now = df['RSI'].iloc[n - 1]

        print(f"\n{'─'*78}\n■ {sym}   {INTERVALO}   "
              f"Δ{DIAS:g}d = {chg:+.2f}%   "
              f"rango [{min(closes):.4f} – {max(closes):.4f}]")
        print(f"  estado AHORA: tendencia={tend_now}  ADX={adx_now:.1f}  RSI={rsi_now:.0f}"
              f"  cierre={closes[-1]:.4f}")
        print(chart_ascii(times, closes, marcas))

        # conteo de puertas
        from collections import Counter
        cnt = Counter(codigos)
        tot = len(codigos)
        def pct(k): return f"{cnt.get(k,0)} ({cnt.get(k,0)/tot*100:.0f}%)" if tot else "0"
        lateral = sum(cnt.get(k, 0) for k in
                      ('LATERAL_ADX', 'LATERAL_EMA', 'LATERAL_DIARIO', 'LATERAL', 'WARMUP'))
        alineadas = tot - lateral
        print(f"  velas evaluadas: {tot} | LATERAL (no-operable): {lateral} "
              f"({lateral/tot*100:.0f}%) | tendencia alineada: {alineadas} "
              f"({alineadas/tot*100:.0f}%)")
        print(f"     · ADX<{config.ADX_LATERAL_MAX}: {pct('LATERAL_ADX')}   "
              f"EMA no apiladas: {pct('LATERAL_EMA')}   "
              f"momentum diario discrepa: {pct('LATERAL_DIARIO')}")
        if getattr(config, 'ENTRY_MODE', 'patrones') == 'cruce':
            print(f"     · alineada sin flip: {pct('SIN_FLIP')}   "
                  f"RSI guard: {pct('RSI_GUARD')}   ENTRADAS: {pct('ENTRADA')}")
        else:
            print(f"     · sin patrón: {pct('SIN_PATRON')}   sin convicción: "
                  f"{pct('SIN_CONVICCION')}   sin volumen: {pct('SIN_VOLUMEN')}   "
                  f"veto doji: {pct('VETO_DOJI')}   RSI guard: {pct('RSI_GUARD')}   "
                  f"ENTRADAS: {pct('ENTRADA')}")

        if casi:
            print(f"  casi-entradas / momentos más cerca ({len(casi)}):")
            for t, p, cod, det in casi[-8:]:
                print(f"     {t.strftime('%m-%d %Hh')}  {p:>11.4f}  [{cod}] {det}")
        else:
            print("  casi-entradas: ninguna (mercado lejos de cualquier setup)")

        resumen_global[sym] = {
            'chg': chg, 'tend_now': tend_now, 'adx_now': adx_now,
            'lateral_pct': lateral / tot * 100 if tot else 0,
            'entradas': cnt.get('ENTRADA', 0), 'casi': len(casi)}

    # ---- resumen final ----
    print(f"\n{'='*78}\n RESUMEN — {os.path.basename(BOT_DIR)} (últimos {DIAS:g} días)\n{'='*78}")
    print(f" {'símbolo':<10}{'Δ%':>9}{'tend.ahora':>12}{'ADX':>7}"
          f"{'%LATERAL':>10}{'entradas':>10}{'casi':>7}")
    tot_ent = 0
    for sym, r in resumen_global.items():
        tot_ent += r['entradas']
        print(f" {sym:<10}{r['chg']:>+8.2f}%{r['tend_now']:>12}{r['adx_now']:>7.1f}"
              f"{r['lateral_pct']:>9.0f}%{r['entradas']:>10}{r['casi']:>7}")
    print(f"\n TOTAL ENTRADAS que el bot HABRÍA generado en la ventana: {tot_ent}")
    print("=" * 78)


if __name__ == '__main__':
    main()
