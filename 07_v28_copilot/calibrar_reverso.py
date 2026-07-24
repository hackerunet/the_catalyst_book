"""
calibrar_reverso.py — V28: ¿se puede CALIBRAR el detector de reverso?

Contexto: el recon backtest probó que prob_reversion NO calibra (de hecho está
INVERTIDO: score alto → menos reverso real). Antes de reescribir el detector hay
que ver, con evidencia, qué features (si alguno) predicen un reverso inmediato.

Metodología (honesta, sin look-ahead):
 1. Reusa el cache de 3 años (wf_cache_1h_26280) — miles de estados, no una
    ventana de 54 días.
 2. Corre el MOTOR REAL (BacktestV25, modo copilot, AUTO_CIERRE_REVERSA OFF) para
    generar la distribución REAL de estados open-trade que el bot encuentra.
 3. Por cada vela con trade abierto (prog >= FLOOR), captura el vector de features
    del indicador EN ESA VELA (causal) y la etiqueta forward: ¿hubo reverso en las
    próximas N velas? (reverso = progreso cae >= DROP pts, o STOP).
 4. Análisis univariado: tasa de reverso por tercil de cada feature (¿separa?).
 5. Reporta correlación señal-feature. NO ajusta nada todavía — solo mide si hay
    señal explotable. Si no la hay, se reporta honestamente.

Uso: python3 calibrar_reverso.py [--cache wf_cache_1h_26280_2026-06-20_0000.pkl]
                                  [--floor 20] [--drop 20] [--horizon 6]
"""
import argparse
import pickle
import os

import numpy as np
import pandas as pd

import config
import estrategia
from indicadores import calcular_indicadores
from backtest import BacktestV25


class ColectorEstados:
    """Captura, por trade, la serie (ts, prog) + meta. Liviano: el lookup de
    features se hace DESPUÉS contra bt.dfs (fuera del hot loop)."""
    dir = '(calib, sin I/O)'

    def __init__(self):
        self.series = {}   # id -> [(ts, prog)]
        self.meta = {}     # id -> dict

    def registrar_activacion(self, t, sub_df, extra):
        self.meta[t['id']] = {'symbol': t['symbol'], 'type': t['type'],
                              'entry_time': t['entry_time']}

    def registrar_vela(self, t, vela, prob):
        self.series.setdefault(t['id'], []).append(
            (vela['time'], estrategia.calcular_progreso(t, vela['close'])))

    def registrar_cierre(self, t):
        m = self.meta.setdefault(t['id'], {})
        m['exit_time'] = t['exit_time']
        m['exit_reason'] = t['exit_reason']
        m['exit_prog'] = estrategia.calcular_progreso(t, t['exit_price'])


def correr_motor(raw):
    bt = BacktestV25(candles=len(next(iter(raw.values()))),
                     forense_dir='/tmp/v28_calib_forense')
    bt.forense = ColectorEstados()
    bt.dfs = {sym: calcular_indicadores(df) for sym, df in raw.items()}
    print(f"INFO: corriendo motor real sobre {len(next(iter(bt.dfs.values())))} velas "
          f"x {len(bt.dfs)} símbolos (modo {config.EXIT_MODE}, "
          f"AUTO_CIERRE_REVERSA={config.AUTO_CIERRE_REVERSA})...")
    bt.correr()
    return bt


def construir_dataset(bt, floor, drop, horizon):
    col = bt.forense
    idxmaps = {sym: {ts: i for i, ts in enumerate(df['time'])}
               for sym, df in bt.dfs.items()}
    filas = []
    for tid, serie in col.series.items():
        m = col.meta.get(tid, {})
        sym, tipo = m.get('symbol'), m.get('type')
        if sym is None:
            continue
        df = bt.dfs[sym]
        # punto terminal: progreso de salida (cubre stops entre muestras)
        serie_ext = serie + [(m.get('exit_time'), m.get('exit_prog'))]
        for k in range(len(serie) - 1):
            ts, prog = serie[k]
            if prog is None or prog < floor:
                continue
            i = idxmaps[sym].get(ts)
            if i is None or i < 30:
                continue
            r = df.iloc[i]
            # etiqueta forward: reverso = progreso futuro cae >= drop, o STOP
            futuros = [p for (_, p) in serie_ext[k + 1:k + 1 + horizon] if p is not None]
            reverso = 1 if any(p <= prog - drop for p in futuros) else 0

            close, e200 = r['close'], r['EMA_200']
            atr = r['ATR'] if r['ATR'] and not pd.isna(r['ATR']) else np.nan
            vma = r['Volume_MA']
            mh = df['MACD_Hist']
            mh0, mh1, mh2 = mh.iloc[i], mh.iloc[i - 1], mh.iloc[i - 2]
            rsi = r['RSI']
            # direccion-ajustado: signo = "a favor del reverso contra la posición"
            # SHORT: reverso = precio SUBE → RSI bajo (sobreventa), MACD subiendo,
            #        precio MUY por debajo de EMA200 (sobre-extensión a la baja).
            if tipo == 'SHORT':
                rsi_exh = max(0.0, 40.0 - rsi)            # qué tan sobrevendido
                macd_turn = mh0 - mh2                      # subiendo = +  (contra short)
                overext = -(close - e200) / e200 * 100 if e200 else 0.0  # debajo→+
            else:
                rsi_exh = max(0.0, rsi - 60.0)
                macd_turn = mh2 - mh0                      # bajando = + (contra long)
                overext = (close - e200) / e200 * 100 if e200 else 0.0

            filas.append({
                'reverso': reverso,
                'ts': ts,
                'prog': prog,
                'rsi': rsi,
                'rsi_exh': rsi_exh,
                'macd_turn': macd_turn,
                'overext': overext,
                'adx': r['ADX'],
                'vol_ratio': float(r['volume'] / vma) if (vma and not pd.isna(vma) and vma > 0) else np.nan,
                'body_atr': float(r['Body'] / atr) if atr and atr > 0 else np.nan,
                'squeeze': 1 if r['Squeeze_On'] else 0,
                'prob_actual': estrategia.prob_reversion(df.iloc[:i + 1], tipo),
            })
    return pd.DataFrame(filas)


def analizar(ds):
    n = len(ds)
    base = ds['reverso'].mean() * 100
    print(f"\n{'='*70}\nDATASET: {n} estados open-trade | tasa base de reverso = {base:.1f}%\n{'='*70}")
    if n < 100:
        print("Muestra muy chica — resultados no confiables.")
        return

    feats = ['prob_actual', 'rsi_exh', 'macd_turn', 'overext', 'adx',
             'vol_ratio', 'body_atr', 'prog']
    print(f"\n{'feature':12} | tasa reverso por TERCIL (bajo→alto) | spread | corr")
    print("-" * 70)
    rank = []
    for f in feats:
        s = ds[[f, 'reverso']].dropna()
        if len(s) < 60:
            print(f"{f:12} | (n insuficiente)")
            continue
        try:
            s['q'] = pd.qcut(s[f], 3, labels=False, duplicates='drop')
        except Exception:
            continue
        tasas = s.groupby('q')['reverso'].mean() * 100
        if len(tasas) < 2:
            print(f"{f:12} | (sin variación)")
            continue
        spread = tasas.iloc[-1] - tasas.iloc[0]
        corr = s[f].corr(s['reverso'])
        celdas = ' '.join(f"{t:5.1f}" for t in tasas)
        print(f"{f:12} | {celdas:30} | {spread:+6.1f} | {corr:+.3f}")
        rank.append((f, abs(corr), corr, spread))

    print("\n--- features ordenados por |correlación| con reverso real ---")
    for f, ac, c, sp in sorted(rank, key=lambda x: -x[1]):
        signo = "predice reverso" if c > 0 else "predice CONTINUACIÓN (inverso)"
        print(f"  {f:12} corr={c:+.3f}  spread tercil={sp:+5.1f}pp  → {signo}")

    # binario: squeeze
    if 'squeeze' in ds:
        g = ds.groupby('squeeze')['reverso'].mean() * 100
        print(f"\n  squeeze=0: {g.get(0, float('nan')):.1f}%  squeeze=1: {g.get(1, float('nan')):.1f}%  (reverso)")

    print(f"\n[recordatorio] prob_actual es el detector VIGENTE — si su corr es ~0 o "
          f"negativa, confirma que hay que reconstruirlo.")


FEATS_MODELO = ['overext', 'rsi_exh', 'vol_ratio', 'body_atr', 'adx']


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def ajustar(ds, feats=FEATS_MODELO, l2=1.0, iters=4000, lr=0.3):
    """Regresión logística a mano (numpy). Split TEMPORAL: entrena en el 70%
    más viejo, valida en el 30% más reciente (OOS real, sin leakage)."""
    d = ds.sort_values('ts').reset_index(drop=True)
    for f in feats:
        d[f] = d[f].fillna(d[f].median())
    corte = int(len(d) * 0.70)
    tr, te = d.iloc[:corte], d.iloc[corte:]
    print(f"\n{'='*70}\nAJUSTE LOGÍSTICO (split temporal) — train={len(tr)} (viejo) / "
          f"test={len(te)} (reciente, OOS)\nfeatures: {feats}\n{'='*70}")

    Xtr = tr[feats].to_numpy(float)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    Xtr_s = (Xtr - mu) / sd
    ytr = tr['reverso'].to_numpy(float)

    n, k = Xtr_s.shape
    Xb = np.hstack([np.ones((n, 1)), Xtr_s])
    w = np.zeros(k + 1)
    for _ in range(iters):
        p = _sigmoid(Xb @ w)
        grad = Xb.T @ (p - ytr) / n
        grad[1:] += (l2 / n) * w[1:]   # L2 (no penaliza intercepto)
        w -= lr * grad

    # --- validación OOS ---
    Xte_s = (te[feats].to_numpy(float) - mu) / sd
    pte = _sigmoid(np.hstack([np.ones((len(te), 1)), Xte_s]) @ w)
    corr_te = np.corrcoef(pte, te['reverso'].to_numpy(float))[0, 1]
    print(f"\nOOS corr(prob_pred, reverso_real) = {corr_te:+.3f}  "
          f"(detector viejo en su recon: +0.023)")
    print("\ncalibración OOS — tasa de reverso real por quintil de prob predicha:")
    q = pd.qcut(pte, 5, labels=False, duplicates='drop')
    tev = te.copy(); tev['q'] = q; tev['p'] = pte
    tasas = []
    for qi in sorted(tev['q'].unique()):
        sub = tev[tev['q'] == qi]
        tasas.append(sub['reverso'].mean() * 100)
        print(f"  Q{int(qi)+1}: prob_pred {sub['p'].min()*100:4.0f}-{sub['p'].max()*100:4.0f}% "
              f"| reverso real = {sub['reverso'].mean()*100:5.1f}% (n={len(sub)})")
    mono = all(tasas[i] <= tasas[i+1] for i in range(len(tasas)-1))
    print(f"  MONOTÓNICA OOS: {'SÍ ✓' if mono else 'NO ✗'}")

    print(f"\n--- PESOS para portar a estrategia.prob_reversion ---")
    print(f"# detector calibrado (calibrar_reverso.py, OOS corr {corr_te:+.3f})")
    print(f"DET_MU = {dict(zip(feats, [round(float(x),6) for x in mu]))}")
    print(f"DET_SD = {dict(zip(feats, [round(float(x),6) for x in sd]))}")
    print(f"DET_W  = {dict(zip(['intercept']+feats, [round(float(x),6) for x in w]))}")
    return w, mu, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default='wf_cache_1h_26280_2026-06-20_0000.pkl')
    ap.add_argument('--floor', type=int, default=20)
    ap.add_argument('--drop', type=int, default=20)
    ap.add_argument('--horizon', type=int, default=6)
    ap.add_argument('--fit', action='store_true', help='ajustar detector logístico + validar OOS')
    ap.add_argument('--from-cache-ds', default=None, help='cargar dataset pkl ya generado (salta el motor)')
    ap.add_argument('--out', default='/tmp/bugcheck2/calib_dataset.pkl')
    args = ap.parse_args()

    if args.from_cache_ds:
        ds = pd.read_pickle(args.from_cache_ds)
        print(f"INFO: dataset cargado de {args.from_cache_ds} ({len(ds)} filas)")
    else:
        ruta = os.path.join(os.path.dirname(__file__), args.cache)
        print(f"INFO: cargando cache {ruta}")
        with open(ruta, 'rb') as f:
            raw = pickle.load(f)
        print(f"INFO: {len(raw)} símbolos, {len(next(iter(raw.values())))} velas c/u")
        # garantizar config de generación de datos: modo copilot, salvavidas OFF
        config.AUTO_CIERRE_REVERSA = False
        bt = correr_motor(raw)
        ds = construir_dataset(bt, args.floor, args.drop, args.horizon)
        ds.to_pickle(args.out)
        print(f"INFO: dataset guardado en {args.out}")
    analizar(ds)
    if args.fit:
        ajustar(ds)


if __name__ == '__main__':
    main()
