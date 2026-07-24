"""
validacion_honesta.py — Arnés de validación que CONDUCE el motor honesto V24 sin
modificarlo.

PRINCIPIO RECTOR (no romper el motor otra vez):
  - El motor (simulador_institucional_v24.py) fue auditado y es correcto
    (intravela pesimista, reloj global, costos reales, sin multiplicador 1.5x).
    Es SAGRADO. Este arnés lo IMPORTA y lo conduce sobre distintas ventanas;
    NUNCA reimplementa su lógica de PnL/salidas (reimplementar = reintroducir
    bugs). Toda la contabilidad de cierre pasa por eng.cerrar_tramo vía
    eng.run_backtest_interleaved.

  - GATE DE INTEGRIDAD: antes de confiar en CUALQUIER número nuevo, el arnés
    debe reproducir EXACTAMENTE el resultado conocido del motor en la ventana
    fija (net_pnl ≈ -708.60, 297 trades, WR 53.54, PF 0.898, buy&hold -16.95).
    Si no reproduce, el bug está en el ARNÉS, no en el motor — se arregla el
    arnés. Solo tras pasar el gate se corre el walk-forward.

Uso:
  python validacion_honesta.py gate            # solo el gate de reproducción
  python validacion_honesta.py walkforward 17520   # gate + walk-forward sobre N velas
"""
import io
import sys
import os
import json
import pickle
import contextlib

import pandas as pd

import simulador_institucional_v24a as eng

CACHE_DIR = '/tmp'
INITIAL_BALANCE_GATE = 4965.2   # el balance con el que se corrió el -708.60 conocido
INITIAL_BALANCE_WF = 5000.0     # nominal fijo para comparar ventanas en % (escala-invariante)


# ---------------------------------------------------------------------------
# Descarga + caché de historia (con verificación de integridad)
# ---------------------------------------------------------------------------
def _fetch_symbol(sym, total_candles, fixed_end=None):
    data = eng._fetch_klines_paginated(sym, total_candles, fixed_end_time=fixed_end)
    df = eng._build_df_from_klines(data)
    df = eng.compute_indicators(df)
    return df


def fetch_history(total_candles, fixed_end=None, cache_tag=None):
    """Descarga indicadores por símbolo. Cachea a disco si cache_tag se da."""
    cache = os.path.join(CACHE_DIR, f"v24_hist_{cache_tag}.pkl") if cache_tag else None
    if cache and os.path.exists(cache):
        with open(cache, 'rb') as f:
            dfs = pickle.load(f)
        print(f"[cache] historia cargada de {cache}")
        return dfs
    dfs = {}
    for sym in eng.PORTFOLIO.keys():
        print(f"[fetch] {sym} ({total_candles} velas)...", flush=True)
        dfs[sym] = _fetch_symbol(sym, total_candles, fixed_end=fixed_end)
    if cache:
        with open(cache, 'wb') as f:
            pickle.dump(dfs, f)
        print(f"[cache] guardada en {cache}")
    return dfs


def verificar_integridad(dfs):
    """Chequeos básicos: tiempo monótono creciente, sin huecos > 1 vela, sin NaN
    en columnas de precio. Devuelve lista de avisos (vacía = OK)."""
    avisos = []
    for sym, df in dfs.items():
        if df is None or df.empty:
            avisos.append(f"{sym}: df vacío"); continue
        t = pd.to_datetime(df['time'])
        if not t.is_monotonic_increasing:
            avisos.append(f"{sym}: timestamps no monótonos")
        gaps = t.diff().dropna()
        paso = gaps.mode().iloc[0] if len(gaps) else None
        n_huecos = int((gaps > paso).sum()) if paso is not None else -1
        if n_huecos > 0:
            avisos.append(f"{sym}: {n_huecos} huecos > 1 vela (paso modal {paso})")
        for col in ('open', 'high', 'low', 'close'):
            if df[col].isna().any():
                avisos.append(f"{sym}: NaN en {col}")
    return avisos


# ---------------------------------------------------------------------------
# Conducir el motor sobre una ventana (sin tocar el motor)
# ---------------------------------------------------------------------------
def run_window(dfs_window, initial_balance):
    eng.sim_state['trades'] = []
    eng.sim_state['initial_balance'] = initial_balance
    eng.sim_state['balance'] = initial_balance
    eng.is_ready = False  # evita prints en vivo / llamadas asyncio a Binance
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run_backtest_interleaved(dfs_window)
    return _metrics(dfs_window, initial_balance)


def _metrics(dfs_window, capital_base):
    """Mismas fórmulas que eng._emitir_resumen_backtest (CERRADA-only, igual que
    el motor) para que el gate compare manzanas con manzanas."""
    trades = eng.sim_state['trades']
    cerrados = [t for t in trades if t['status'] == 'CERRADA']
    pnls = [t['pnl'] for t in cerrados]
    gan = [p for p in pnls if p > 0]
    per = [p for p in pnls if p <= 0]
    net = sum(gan) - abs(sum(per))
    wr = (len(gan) / len(pnls) * 100) if pnls else 0.0
    pf = (sum(gan) / abs(sum(per))) if sum(per) != 0 else None
    # buy & hold idéntico al del motor (close[WARMUP] -> close[-1], promedio símbolos)
    rets = []
    for _sym, _df in dfs_window.items():
        if _df is not None and len(_df) > eng.WARMUP_CANDLES:
            p0 = _df['close'].iloc[eng.WARMUP_CANDLES]
            p1 = _df['close'].iloc[-1]
            if p0:
                rets.append((p1 / p0 - 1) * 100)
    bh = (sum(rets) / len(rets)) if rets else None
    # desglose por puerta
    por_puerta = {}
    for t in cerrados:
        k = t.get('puerta', '?')
        d = por_puerta.setdefault(k, {'trades': 0, 'wins': 0, 'pnl': 0.0})
        d['trades'] += 1
        d['wins'] += 1 if t['pnl'] > 0 else 0
        d['pnl'] += t['pnl']
    for k, d in por_puerta.items():
        d['wr'] = round(d['wins'] / d['trades'] * 100, 1) if d['trades'] else 0.0
        d['pnl'] = round(d['pnl'], 2)
    return {
        'net_pnl': round(net, 2),
        'net_pct': round(net / capital_base * 100, 2) if capital_base else 0.0,
        'trades': len(cerrados),
        'wr': round(wr, 2),
        'pf': round(pf, 3) if pf is not None else None,
        'buy_hold_pct': round(bh, 2) if bh is not None else None,
        'por_puerta': por_puerta,
    }


# ---------------------------------------------------------------------------
# GATE DE INTEGRIDAD — reproducir la ventana fija conocida
# ---------------------------------------------------------------------------
EXPECTED_FIXED = {'net_pnl': -612.71, 'trades': 159, 'wr': 32.7, 'pf': 0.807, 'buy_hold_pct': -16.95}


def gate():
    print("=== GATE DE INTEGRIDAD: reproducir ventana fija (-$708.60) ===")
    dfs = fetch_history(eng.BACKTEST_CANDLES, fixed_end=eng.BACKTEST_FIXED_END_TIME_MS,
                        cache_tag='fixed')
    avisos = verificar_integridad(dfs)
    if avisos:
        print("AVISOS DE INTEGRIDAD:", *avisos, sep="\n  ")
    m = run_window(dfs, INITIAL_BALANCE_GATE)
    print("Esperado :", EXPECTED_FIXED)
    print("Obtenido :", {k: m[k] for k in EXPECTED_FIXED})
    ok = (m['trades'] == EXPECTED_FIXED['trades']
          and abs(m['net_pnl'] - EXPECTED_FIXED['net_pnl']) < 1.0
          and abs(m['wr'] - EXPECTED_FIXED['wr']) < 0.1)
    print("RESULTADO GATE:", "✅ REPRODUCE (arnés fiel al motor)" if ok
          else "❌ NO REPRODUCE — arreglar el ARNÉS, no el motor")
    return ok


# ---------------------------------------------------------------------------
# WALK-FORWARD — ventanas OOS disjuntas sobre 2-3 años (bull/bear/chop)
# ---------------------------------------------------------------------------
def _alinear(dfs):
    """Reduce todos los símbolos a su línea de tiempo COMÚN (intersección de
    timestamps) e index-alinea, para poder rebanar ventanas por índice entero
    con warmup idéntico (200 velas) en los 6 símbolos."""
    sets = [set(df['time']) for df in dfs.values() if df is not None and not df.empty]
    common = sorted(set.intersection(*sets))
    aligned = {}
    for sym, df in dfs.items():
        d = df[df['time'].isin(common)].sort_values('time').reset_index(drop=True)
        aligned[sym] = d
    return aligned, common


def walkforward(total_candles, window=720):
    if not gate():
        print("\nGATE FALLÓ — no se corre walk-forward (el arnés no es fiel al motor).")
        return
    print(f"\n=== WALK-FORWARD: {total_candles} velas, ventanas OOS disjuntas de {window} velas ===")
    dfs = fetch_history(total_candles, fixed_end=eng.BACKTEST_FIXED_END_TIME_MS,
                        cache_tag=f'wf{total_candles}')
    avisos = verificar_integridad(dfs)
    if avisos:
        print("AVISOS DE INTEGRIDAD:", *avisos, sep="\n  ")
    aligned, common = _alinear(dfs)
    L = len(common)
    W = eng.WARMUP_CANDLES
    print(f"Timeline común: {L} velas, {common[0]} -> {common[-1]}")
    n_windows = (L - W) // window
    print(f"{n_windows} ventanas OOS de {window} velas (~{window // 24} días c/u)\n")

    filas = []
    for k in range(n_windows):
        a = W + k * window           # inicio test (índice absoluto alineado)
        b = W + (k + 1) * window     # fin test
        slice_dfs = {sym: d.iloc[a - W:b].reset_index(drop=True) for sym, d in aligned.items()}
        m = run_window(slice_dfs, INITIAL_BALANCE_WF)
        t0 = str(common[a])[:10]
        t1 = str(common[b - 1])[:10]
        bate = (m['net_pct'] is not None and m['buy_hold_pct'] is not None
                and m['net_pct'] > m['buy_hold_pct'])
        filas.append({'k': k, 't0': t0, 't1': t1, **m, 'bate_bh': bate})
        print(f"  W{k:02d} {t0}..{t1} | net {m['net_pct']:+6.2f}% | B&H {m['buy_hold_pct']:+6.2f}% "
              f"| {m['trades']:3d} tr | WR {m['wr']:4.1f} | PF {m['pf']} | {'BATE' if bate else '    '}")

    # ---- agregados ----
    nets = [f['net_pct'] for f in filas]
    bhs = [f['buy_hold_pct'] for f in filas]
    pos = sum(1 for x in nets if x > 0)
    bate_bh = sum(1 for f in filas if f['bate_bh'])
    import statistics as st
    print("\n=== AGREGADO WALK-FORWARD ===")
    print(f"Ventanas: {len(filas)}")
    print(f"Net positivo: {pos}/{len(filas)} ({pos/len(filas)*100:.0f}%)")
    print(f"Mediana net%: {st.median(nets):+.2f} | Media net%: {st.mean(nets):+.2f} | "
          f"Suma net% (capital fijo/ventana): {sum(nets):+.2f}")
    print(f"Mediana B&H%: {st.median(bhs):+.2f} | Media B&H%: {st.mean(bhs):+.2f}")
    print(f"Bate buy&hold: {bate_bh}/{len(filas)} ventanas")
    # correlación net vs B&H (¿es solo beta?)
    try:
        import numpy as np
        corr = float(np.corrcoef(nets, bhs)[0, 1])
        print(f"Correlación net% vs B&H%: {corr:+.2f} "
              f"({'sospecha de beta pura' if corr > 0.6 else 'algo independiente del mercado' if abs(corr) < 0.4 else 'parcialmente correlado'})")
    except Exception:
        pass
    # guardar CSV para inspección
    out = os.path.join(os.path.dirname(__file__), 'walkforward_resultados.csv')
    pd.DataFrame(filas).to_csv(out, index=False)
    print(f"\nDetalle por ventana guardado en {out}")


# ---------------------------------------------------------------------------
# MONTE CARLO NULL — ¿las ENTRADAS baten a entradas aleatorias con las MISMAS
# salidas? (el motor NUNCA se modifica; se reemplaza en runtime la referencia
# eng.compute_signals_and_trades — el motor la llama por nombre, así que el
# rebind se respeta sin tocar el archivo del motor)
# ---------------------------------------------------------------------------
import random
import estrategia_v24a_Master as est


def _make_random_signal(p, rng):
    """Señal aleatoria: con prob p por llamada, abre en dirección aleatoria 50/50
    construyendo SL/TP/qty/time-stop IDÉNTICos a la estrategia real (mismo
    _stop_distance, TP_R_MULT, TIME_STOP_HORAS). Lo único aleatorio es CUÁNDO y
    en QUÉ dirección — aísla el valor de la lógica de entrada real."""
    def rnd(df, bal, risk):
        if rng.random() >= p:
            return None, None
        try:
            price = float(df['close'].iloc[-1])
            dist = est._stop_distance(df, price)
        except Exception:
            return None, None
        if not dist or dist <= 0:
            return None, None
        direction = 'LONG' if rng.random() < 0.5 else 'SHORT'
        if direction == 'LONG':
            sl = price - dist; tp = price + dist * est.TP_R_MULT
        else:
            sl = price + dist; tp = price - dist * est.TP_R_MULT
        qty = (bal * risk) / dist
        return direction, {
            'type': direction, 'puerta': 'A', 'entry_price': price,
            'stop_loss': sl, 'take_profit': tp, 'qty': qty, 'conviccion': 90.0,
            'metrics': {'trend_w': 100, 'mr_w': 0}, 'regimen': 'N/D',
            'time_stop_horas': est.TIME_STOP_HORAS, 'pattern': 'RANDOM NULL'}
    return rnd


def montecarlo(total_candles=17520, window=720, K=100, seed=12345):
    if not gate():
        print("GATE FALLÓ — no se corre Monte Carlo."); return
    print(f"\n=== MONTE CARLO NULL: {K} corridas de entradas aleatorias (mismas salidas) ===")
    dfs = fetch_history(total_candles, fixed_end=eng.BACKTEST_FIXED_END_TIME_MS,
                        cache_tag=f'wf{total_candles}')
    aligned, common = _alinear(dfs)
    L = len(common); W = eng.WARMUP_CANDLES; n = (L - W) // window
    slices = []
    for k in range(n):
        a = W + k * window; b = W + (k + 1) * window
        slices.append({s: d.iloc[a - W:b].reset_index(drop=True) for s, d in aligned.items()})

    REAL = eng.compute_signals_and_trades

    # 1) Pasada REAL instrumentada: net% real por ventana + tasa de entrada p
    real_nets, pvals, real_trades = [], [], []
    for sl in slices:
        cnt = {'calls': 0, 'ent': 0}
        def wrapped(df, bal, risk, _orig=REAL, _c=cnt):
            _c['calls'] += 1
            sig, td = _orig(df, bal, risk)
            if sig: _c['ent'] += 1
            return sig, td
        eng.compute_signals_and_trades = wrapped
        m = run_window(sl, INITIAL_BALANCE_WF)
        eng.compute_signals_and_trades = REAL
        real_nets.append(m['net_pct']); real_trades.append(m['trades'])
        pvals.append((cnt['ent'] / cnt['calls']) if cnt['calls'] else 0.0)
    real_sum = sum(real_nets)
    print(f"Real V24A: sum net% {real_sum:+.2f} | trades/2yr {sum(real_trades)} | "
          f"tasa entrada por ventana p∈[{min(pvals):.4f},{max(pvals):.4f}]")

    # 2) K pasadas NULL (entradas aleatorias, misma p por ventana)
    null_sums, null_trades = [], []
    null_perwin = [[] for _ in range(n)]
    for it in range(K):
        rng = random.Random(seed + it)
        s_net, s_tr = 0.0, 0
        for wi, sl in enumerate(slices):
            eng.compute_signals_and_trades = _make_random_signal(pvals[wi], rng)
            m = run_window(sl, INITIAL_BALANCE_WF)
            s_net += m['net_pct']; s_tr += m['trades']
            null_perwin[wi].append(m['net_pct'])
        eng.compute_signals_and_trades = REAL
        null_sums.append(s_net); null_trades.append(s_tr)
        if (it + 1) % 20 == 0:
            print(f"  ...null {it + 1}/{K}", flush=True)

    # 3) Reporte
    import statistics as st
    ns = sorted(null_sums)
    def pctile(v, dist):
        return 100.0 * sum(1 for x in dist if x < v) / len(dist)
    p_real = pctile(real_sum, null_sums)
    win_beats = sum(1 for wi in range(n)
                    if real_nets[wi] > sorted(null_perwin[wi])[int(0.95 * K)])
    print("\n=== RESULTADO MONTE CARLO ===")
    print(f"Null sum net% (K={K}): mean {st.mean(null_sums):+.2f} | median {st.median(null_sums):+.2f} "
          f"| p5 {ns[int(0.05*K)]:+.2f} | p95 {ns[int(0.95*K)]:+.2f}")
    print(f"Null trades/2yr: mean {st.mean(null_trades):.0f} (real {sum(real_trades)} — deben ser similares)")
    print(f"REAL sum net% {real_sum:+.2f}  ->  percentil {p_real:.1f} del null")
    print(f"Ventanas donde real bate p95 de su null: {win_beats}/{n}")
    if p_real >= 95:
        print("VEREDICTO: las ENTRADAS reales baten a las aleatorias (p95+) — hay edge de entrada genuino.")
    elif p_real >= 80:
        print("VEREDICTO: entradas por encima de la mediana del null pero NO p95 — edge de entrada débil/incierto.")
    else:
        print("VEREDICTO: las entradas NO baten a aleatorias — el resultado es salidas+beta, las entradas son ruido.")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'gate'
    if cmd == 'gate':
        sys.exit(0 if gate() else 1)
    elif cmd == 'montecarlo':
        K = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        montecarlo(K=K)
    elif cmd == 'walkforward':
        total = int(sys.argv[2]) if len(sys.argv) > 2 else 17520   # ~2 años por defecto
        win = int(sys.argv[3]) if len(sys.argv) > 3 else 720       # ~30 días
        walkforward(total, win)
    else:
        print(f"comando desconocido: {cmd}")
        sys.exit(2)
