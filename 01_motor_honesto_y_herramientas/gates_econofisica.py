"""
gates_econofisica.py — Gates de régimen de la tanda V60-V67 (pre-registro el libro
2026-07-09). MÓDULO PURO: computa, para cada símbolo, un dict {timestamp: bloqueo}
donde bloqueo ∈ {'ALL','LONG','SHORT'} — las direcciones de ENTRADA bloqueadas en esa
vela. Timestamps ausentes = sin bloqueo. Todo CAUSAL (cada vela usa solo su pasado).

Activación: config.GATE_ECONO (default None = inerte) vía --gate en walkforward.py.
El motor real y el null MC consumen EL MISMO dict (lección M1/P1-P2: un solo code-path).

Nota de costo (declarada, no es escaneo): las métricas caras (entropía, MF-DFA, LPPLS)
se recalculan con un stride y se mantienen (forward-fill) entre recálculos — economía
de cómputo, los parámetros de las hipótesis no cambian.
"""
import numpy as np

import config

# stride de recálculo por timeframe (velas ≈ 1 día); forward-fill entre recálculos
_STRIDE = {'15m': 96, '1h': 24, '4h': 6, '1d': 1}


def _stride():
    return _STRIDE.get(getattr(config, 'INTERVAL', '4h'), 6)


def _log_ret(close):
    r = np.diff(np.log(close))
    return np.concatenate([[0.0], r])


# ---------------------------------------------------------------------------
# V60 — Entropía de permutación (Bandt-Pompe 2002; criterio de Sigaki et al 2019)
# ---------------------------------------------------------------------------
def _pe_norm(x, m=4):
    """Entropía de permutación normalizada (τ=1). x = ventana de retornos."""
    n = len(x) - m + 1
    if n < 30:
        return None
    # patrones ordinales vectorizados
    idx = np.arange(m) + np.arange(n)[:, None]
    patrones = np.argsort(x[idx], axis=1)
    # codificar cada permutación como entero
    codigo = (patrones * (m ** np.arange(m))).sum(axis=1)
    _, cuentas = np.unique(codigo, return_counts=True)
    p = cuentas / n
    H = -(p * np.log(p)).sum()
    return H / np.log(float(np.math.factorial(m))) if hasattr(np, 'math') else H / np.log(24.0)


def _pe_norm_safe(x, m=4):
    import math
    n = len(x) - m + 1
    if n < 30:
        return None
    idx = np.arange(m) + np.arange(n)[:, None]
    patrones = np.argsort(x[idx], axis=1)
    codigo = (patrones * (m ** np.arange(m))).sum(axis=1)
    _, cuentas = np.unique(codigo, return_counts=True)
    p = cuentas / n
    return float(-(p * np.log(p)).sum() / np.log(math.factorial(m)))


def gate_entropia(df, rng, ventana=200, m=4, n_shuffles=100):
    """Bloquea 'ALL' cuando la PE de la ventana es indistinguible de barajada:
    PE >= media(shuffles) - 2*sigma(shuffles). Recalcula cada stride velas."""
    close = df['close'].astype(float).values
    r = _log_ret(close)
    tiempos = df['time'].values
    st = _stride()
    bloqueos = {}
    bloqueado = False
    for i in range(ventana, len(df)):
        if (i - ventana) % st == 0:
            w = r[i - ventana + 1:i + 1]
            pe = _pe_norm_safe(w, m)
            if pe is None:
                bloqueado = False
            else:
                sh = np.empty(n_shuffles)
                wc = w.copy()
                for k in range(n_shuffles):
                    rng.shuffle(wc)
                    sh[k] = _pe_norm_safe(wc, m)
                umbral = sh.mean() - 2.0 * sh.std()
                bloqueado = pe >= umbral  # eficiente/aleatoria => bloquear
        if bloqueado:
            bloqueos[tiempos[i]] = 'ALL'
    return bloqueos


# ---------------------------------------------------------------------------
# V61 — Anchura del espectro multifractal, MF-DFA (Kantelhardt et al 2002)
# ---------------------------------------------------------------------------
def _mfdfa_delta_alpha(x, qs=(-4, -2, -1, 1, 2, 4), orden=1):
    """Δα = anchura del espectro de singularidades vía h(q) (MF-DFA, DFA-1)."""
    x = x - x.mean()
    perfil = np.cumsum(x)
    N = len(perfil)
    escalas = np.unique(np.logspace(np.log10(10), np.log10(N // 4), 12).astype(int))
    escalas = escalas[escalas >= orden + 2]
    if len(escalas) < 4:
        return None
    hq = []
    for q in qs:
        Fq = []
        for s in escalas:
            nseg = N // s
            if nseg < 4:
                continue
            seg = perfil[:nseg * s].reshape(nseg, s)
            t = np.arange(s)
            # detrending polinómico orden 1 vectorizado
            tm = t - t.mean()
            beta = (seg * tm).sum(axis=1) / (tm ** 2).sum()
            alfa0 = seg.mean(axis=1)
            resid = seg - (alfa0[:, None] + beta[:, None] * tm)
            F2 = (resid ** 2).mean(axis=1)
            F2 = F2[F2 > 0]
            if len(F2) < 2:
                continue
            if q == 0:
                Fq.append((s, np.exp(0.5 * np.mean(np.log(F2)))))
            else:
                Fq.append((s, (np.mean(F2 ** (q / 2.0))) ** (1.0 / q)))
        if len(Fq) < 4:
            return None
        ss = np.log([a for a, _ in Fq])
        ff = np.log([b for _, b in Fq])
        h = np.polyfit(ss, ff, 1)[0]
        hq.append((q, h))
    # tau(q) = q*h(q) - 1 ; alpha = dtau/dq ; Δα = max-min (aprox por diferencias)
    qs_a = np.array([q for q, _ in hq], dtype=float)
    hs = np.array([h for _, h in hq])
    tau = qs_a * hs - 1.0
    alpha = np.gradient(tau, qs_a)
    return float(alpha.max() - alpha.min())


def gate_mfdfa(df, ventana=1000):
    """Bloquea 'ALL' cuando Δα < mediana EXPANSIVA de su propia historia (espectro
    angosto = ruido). Recalcula cada stride velas."""
    close = df['close'].astype(float).values
    r = _log_ret(close)
    tiempos = df['time'].values
    st = _stride()
    bloqueos = {}
    historia = []
    bloqueado = False
    for i in range(ventana, len(df)):
        if (i - ventana) % st == 0:
            da = _mfdfa_delta_alpha(r[i - ventana + 1:i + 1])
            if da is not None:
                if len(historia) >= 10:
                    bloqueado = da < float(np.median(historia))
                else:
                    bloqueado = False
                historia.append(da)
        if bloqueado:
            bloqueos[tiempos[i]] = 'ALL'
    return bloqueos


# ---------------------------------------------------------------------------
# V62 — LPPLS causal sobre diario resampleado (Filimonov-Sornette 2013)
# ---------------------------------------------------------------------------
def _lppls_fit(logp):
    """Ajuste F-S de 3 parámetros no lineales (tc, m, w); lineales por OLS.
    Devuelve (tc_rel, m, w, damping) del mejor ajuste o None."""
    from scipy.optimize import minimize
    N = len(logp)
    t = np.arange(N, dtype=float)

    def sse(theta):
        tc, m, w = theta
        if tc <= N - 1 or not (0.01 <= m <= 1.2) or not (2 <= w <= 25):
            return 1e12
        dt = tc - t
        f = dt ** m
        g = f * np.cos(w * np.log(dt))
        h = f * np.sin(w * np.log(dt))
        X = np.column_stack([np.ones(N), f, g, h])
        try:
            beta, *_ = np.linalg.lstsq(X, logp, rcond=None)
        except np.linalg.LinAlgError:
            return 1e12
        resid = logp - X @ beta
        return float((resid ** 2).sum())

    mejor = None
    for tc0 in (N + 5, N + 20, N + 45):
        for m0 in (0.3, 0.6):
            for w0 in (7.0, 11.0):
                res = minimize(sse, x0=np.array([tc0, m0, w0]), method='Nelder-Mead',
                               options={'maxiter': 400, 'xatol': 0.5, 'fatol': 1e-8})
                if mejor is None or res.fun < mejor.fun:
                    mejor = res
    if mejor is None or mejor.fun >= 1e11:
        return None
    tc, m, w = mejor.x
    # recomputar lineales para el damping
    dt = tc - t
    f = dt ** m
    g = f * np.cos(w * np.log(dt))
    h = f * np.sin(w * np.log(dt))
    X = np.column_stack([np.ones(N), f, g, h])
    beta, *_ = np.linalg.lstsq(X, logp, rcond=None)
    A, B, C1, C2 = beta
    C = np.hypot(C1, C2)
    damping = (m * abs(B)) / (w * C) if (w * C) > 0 else 0.0
    return {'tc_rel': float(tc - (N - 1)), 'm': float(m), 'w': float(w),
            'B': float(B), 'damping': float(damping)}


def gate_lppls(df, ventana_dias=120):
    """Resamplea el df a DIARIO (causal), ajusta LPPLS por día con los filtros
    canónicos de Sornette (0.1<=m<=0.9, 6<=w<=13, tc<=60d, damping>=1).
    Burbuja positiva (B<0 en log-precio creciente) => bloquear LONGs;
    negativa => bloquear SHORTs. Propaga el flag del día a las velas intradía."""
    import pandas as pd
    d = df[['time', 'close']].copy()
    d = d.set_index('time').resample('1D').last().dropna()
    closes = d['close'].astype(float).values
    dias = d.index.values
    flags = {}  # dia -> 'LONG'|'SHORT'
    for k in range(ventana_dias, len(closes)):
        logp = np.log(closes[k - ventana_dias + 1:k + 1])
        fit = _lppls_fit(logp)
        if fit is None:
            continue
        ok = (0.1 <= fit['m'] <= 0.9 and 6 <= fit['w'] <= 13
              and 0 < fit['tc_rel'] <= 60 and fit['damping'] >= 1.0)
        if not ok:
            continue
        # B<0 => burbuja positiva (aceleración alcista) => riesgo de crash => bloquear LONG
        flags[dias[k]] = 'LONG' if fit['B'] < 0 else 'SHORT'
    if not flags:
        return {}
    bloqueos = {}
    tiempos = df['time'].values
    dias_velas = tiempos.astype('datetime64[D]')
    flag_dias = {np.datetime64(k, 'D'): v for k, v in flags.items()}
    for ts, dia in zip(tiempos, dias_velas):
        # causal: el flag calculado con el cierre del día D aplica desde el día D+1
        f = flag_dias.get(dia - np.timedelta64(1, 'D'))
        if f:
            bloqueos[ts] = f
    return bloqueos


# ---------------------------------------------------------------------------
# V64 — Ley de Omori: ventana de réplicas post-shock (Lillo-Mantegna 2003)
# ---------------------------------------------------------------------------
def gate_omori(df, sigma_ventana=100, k_sigma=4.0, ventana_replicas=24):
    close = df['close'].astype(float).values
    r = _log_ret(close)
    tiempos = df['time'].values
    bloqueos = {}
    hasta = -1
    for i in range(sigma_ventana, len(df)):
        s = r[i - sigma_ventana:i].std()
        if s > 0 and abs(r[i]) > k_sigma * s:
            hasta = max(hasta, i + ventana_replicas)
        if i <= hasta:
            bloqueos[tiempos[i]] = 'ALL'
    return bloqueos


# ---------------------------------------------------------------------------
# V65 — Acoplamiento sistémico RMT: fracción del modo mercado (Laloux et al 1999)
# ---------------------------------------------------------------------------
def gates_rmt(dfs, ventana=90, umbral=0.5):
    """Cross-symbol: correlación rodante de retornos del basket; bloquea 'ALL' en
    TODOS los símbolos cuando lambda_max/suma > umbral. Alinea por timestamp."""
    import pandas as pd
    series = {}
    for sym, df in dfs.items():
        s = pd.Series(_log_ret(df['close'].astype(float).values),
                      index=pd.DatetimeIndex(df['time']))
        series[sym] = s
    R = pd.DataFrame(series).dropna()
    if len(R) < ventana + 5:
        return {sym: {} for sym in dfs}
    ts_bloqueados = []
    vals = R.values
    idx = R.index
    st = max(_stride() // 2, 1)
    bloqueado = False
    for i in range(ventana, len(R)):
        if (i - ventana) % st == 0:
            sub = vals[i - ventana:i]
            sd = sub.std(axis=0)
            if (sd == 0).any():
                bloqueado = False
            else:
                C = np.corrcoef(sub, rowvar=False)
                ev = np.linalg.eigvalsh(C)
                bloqueado = float(ev[-1] / ev.sum()) > umbral
        if bloqueado:
            ts_bloqueados.append(idx[i])
    ts_set = {np.datetime64(t): 'ALL' for t in ts_bloqueados}
    out = {}
    for sym, df in dfs.items():
        tiempos = df['time'].values
        out[sym] = {t: 'ALL' for t in tiempos if np.datetime64(t) in ts_set}
    return out


# ---------------------------------------------------------------------------
# V66 — Herding: dispersión cross-sectional (Cont-Bouchaud 2000)
# ---------------------------------------------------------------------------
def gates_dispersion(dfs, ventana_ret=24):
    """Manada = std cross-sectional de los retornos de `ventana_ret` velas del
    basket < mediana EXPANSIVA. Bloquea 'ALL' en todos los símbolos."""
    import pandas as pd
    series = {}
    for sym, df in dfs.items():
        c = pd.Series(df['close'].astype(float).values,
                      index=pd.DatetimeIndex(df['time']))
        series[sym] = c
    P = pd.DataFrame(series).dropna()
    rets = P.pct_change(ventana_ret).dropna()
    disp = rets.std(axis=1)
    mediana_exp = disp.expanding(min_periods=50).median()
    manada = disp < mediana_exp
    ts_set = {np.datetime64(t): 'ALL' for t, v in manada.items() if v}
    out = {}
    for sym, df in dfs.items():
        tiempos = df['time'].values
        out[sym] = {t: 'ALL' for t in tiempos if np.datetime64(t) in ts_set}
    return out


# ---------------------------------------------------------------------------
# V67 — Crowding por funding (reflexividad; funding real cacheado V27-B)
# ---------------------------------------------------------------------------
def gates_funding(dfs, cache_path=None):
    """funding > p90 expansivo => bloquear LONG; < p10 => bloquear SHORT.
    Percentiles EXPANSIVOS por símbolo (causal). Funding se forward-fillea a velas."""
    import pandas as pd
    import pickle as pk
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    if cache_path is not None:
        rutas = [cache_path]
    else:
        # fusiona ambos caches de funding real (mismo formato time/rate): el de
        # v27b (BTC+ETH+basket original) y el OOB de M3 (BTC/DOGE/AVAX/DOT/LTC/ATOM)
        # — plomería de datos para que el gate funcione en cualquiera de los baskets.
        rutas = [os.path.join(base, '..', 'v27b_carry', 'funding_cache.pkl'),
                 os.path.join(base, '..', '..', 'Fragua', 'm3_carry',
                              'funding_cache_oob.pkl')]
    fc = {}
    for ruta in rutas:
        if os.path.exists(ruta):
            with open(ruta, 'rb') as f:
                fc.update(pk.load(f))
    out = {}
    for sym, df in dfs.items():
        out[sym] = {}
        datos = fc.get(sym)
        if datos is None:
            continue
        # formato v27b: lista/df de (timestamp, rate) — normalizar
        if isinstance(datos, pd.DataFrame):
            fd = datos.copy()
            tcol = 'fundingTime' if 'fundingTime' in fd.columns else fd.columns[0]
            rcol = 'fundingRate' if 'fundingRate' in fd.columns else fd.columns[1]
            ft = pd.to_datetime(fd[tcol], unit='ms', errors='coerce')
            if ft.isna().all():
                ft = pd.to_datetime(fd[tcol])
            fr = fd[rcol].astype(float).values
        else:
            arr = list(datos)
            ft = pd.to_datetime([a[0] for a in arr], unit='ms')
            fr = np.array([float(a[1]) for a in arr])
        s = pd.Series(fr, index=pd.DatetimeIndex(ft)).sort_index()
        p90 = s.expanding(min_periods=100).quantile(0.90)
        p10 = s.expanding(min_periods=100).quantile(0.10)
        estado = pd.Series(index=s.index, dtype=object)
        estado[s > p90] = 'LONG'
        estado[s < p10] = 'SHORT'
        estado = estado.dropna()
        if estado.empty:
            continue
        tiempos = pd.DatetimeIndex(df['time'])
        # asof: el último evento de funding conocido a cada vela (causal)
        pos = estado.index.searchsorted(tiempos, side='right') - 1
        tv = df['time'].values
        vals = estado.values
        for k, p in enumerate(pos):
            if p >= 0:
                # el estado de crowding solo aplica si el evento es reciente (<= 8h*3)
                if (tiempos[k] - estado.index[p]).total_seconds() <= 24 * 3600:
                    out[sym][tv[k]] = vals[p]
    return out


# ---------------------------------------------------------------------------
# V63 — Señal lead-lag por transfer entropy (Schreiber 2000; Dimpfl-Peter 2019)
# ---------------------------------------------------------------------------
def _te(x_bins, y_bins, nb=3):
    """TE(X→Y) con lag 1: sum p(y1,y0,x0)·log[ p(y1|y0,x0) / p(y1|y0) ]."""
    y1, y0, x0 = y_bins[1:], y_bins[:-1], x_bins[:-1]
    n = len(y1)
    idx = (y1 * nb + y0) * nb + x0
    c_yyx = np.bincount(idx, minlength=nb ** 3).astype(float)
    c_yx = np.bincount(y0 * nb + x0, minlength=nb ** 2).astype(float)
    c_yy = np.bincount(y1 * nb + y0, minlength=nb ** 2).astype(float)
    c_y = np.bincount(y0, minlength=nb).astype(float)
    te = 0.0
    for k in range(nb ** 3):
        if c_yyx[k] == 0:
            continue
        y1k = k // (nb * nb)
        y0k = (k // nb) % nb
        x0k = k % nb
        p_yyx = c_yyx[k] / n
        p_cond_full = c_yyx[k] / c_yx[y0k * nb + x0k]
        p_cond_red = c_yy[y1k * nb + y0k] / c_y[y0k]
        if p_cond_full > 0 and p_cond_red > 0:
            te += p_yyx * np.log(p_cond_full / p_cond_red)
    return te


def _binear(r, nb=3):
    """Discretización por cuantiles (terciles) DENTRO de la ventana (causal)."""
    q = np.quantile(r, [1 / 3, 2 / 3])
    return np.digitize(r, q)


def senales_te(dfs, df_lider, ventana=500, n_surr=100, seed=42, p_sig=95):
    """V63: cuando TE(líder→alt) > p95 de surrogates barajados (y > TE inversa,
    medición BIDIRECCIONAL per pre-registro), señal en la alt = dirección del
    último retorno del líder. Recalcula cada stride velas; la señal vale SOLO
    en las velas del tramo significativo. Devuelve {sym: {ts: 'LONG'|'SHORT'}}."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    lider = pd.Series(_log_ret(df_lider['close'].astype(float).values),
                      index=pd.DatetimeIndex(df_lider['time']))
    st = _stride()
    out = {}
    for sym, df in dfs.items():
        out[sym] = {}
        alt = pd.Series(_log_ret(df['close'].astype(float).values),
                        index=pd.DatetimeIndex(df['time']))
        par = pd.DataFrame({'x': lider, 'y': alt}).dropna()
        if len(par) < ventana + 10:
            continue
        xs, ys = par['x'].values, par['y'].values
        idxs = par.index
        ts_por_indice = {t: k for k, t in enumerate(pd.DatetimeIndex(df['time']))}
        significativo = False
        for i in range(ventana, len(par)):
            if (i - ventana) % st == 0:
                wx, wy = xs[i - ventana:i], ys[i - ventana:i]
                bx, by = _binear(wx), _binear(wy)
                te_xy = _te(bx, by)
                te_yx = _te(by, bx)
                surr = np.empty(n_surr)
                bxc = bx.copy()
                for k in range(n_surr):
                    rng.shuffle(bxc)
                    surr[k] = _te(bxc, by)
                umbral = np.percentile(surr, p_sig)
                significativo = (te_xy > umbral) and (te_xy > te_yx)
            if significativo:
                ts = idxs[i]
                if ts in ts_por_indice and xs[i] != 0:
                    out[sym][np.datetime64(ts)] = 'LONG' if xs[i] > 0 else 'SHORT'
    return out


# ---------------------------------------------------------------------------
def calcular_gates(dfs, tipo, seed=42):
    """Punto de entrada único. dfs = {sym: df con time/close (+indicadores)}."""
    rng = np.random.default_rng(seed)
    if tipo == 'entropia':
        return {sym: gate_entropia(df, rng) for sym, df in dfs.items()}
    if tipo == 'mfdfa':
        return {sym: gate_mfdfa(df) for sym, df in dfs.items()}
    if tipo == 'lppls':
        return {sym: gate_lppls(df) for sym, df in dfs.items()}
    if tipo == 'omori':
        return {sym: gate_omori(df) for sym, df in dfs.items()}
    if tipo == 'rmt':
        return gates_rmt(dfs)
    if tipo == 'dispersion':
        return gates_dispersion(dfs)
    if tipo == 'funding':
        return gates_funding(dfs)
    raise ValueError(f'gate desconocido: {tipo}')
