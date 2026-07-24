"""M1 — Motor de backtest CROSS-SECTIONAL (long top-k / short bottom-k, dollar-neutral).

Modela lo que el motor vivo NO puede: una cartera de N símbolos SIMULTÁNEOS que se rebalancea, con pesos
que driftean entre rebalanceos, costos sobre turnover, funding sobre gross, y un null contra el azar.
Un solo code-path para real y null (ítem C1 de HONESTIDAD.md).

Propiedades de honestidad clave (ver HONESTIDAD.md):
  - Anti-lookahead ESTRUCTURAL: el ranker recibe SOLO M[:t+1] (no puede leer el futuro aunque quiera);
    los pesos de la barra t se fijan con info hasta t y ganan el retorno de t→t+1.
  - Contabilidad: equity multiplicativa; pesos driftan por precio (= mantener nocionales fijos entre
    rebalanceos); turnover = sum|target - w_driftado|; funding pesimista sobre gross; quiebra clampeada
    en equity 0 (un libro con shorts puede perder >100% en una barra).
  - Null JUSTO (E1): `correr_null_desplazado` — rotación temporal de la señal real, mantiene cadencia
    Y turnover (el null por permutación quedó como cota gruesa: rota 2.4x más → percentil inflado).
  - Determinista: misma entrada + misma semilla del null → mismo resultado.

NO importa nada de bot_alpha_portfolio. Costos y datos vienen de ../common (espejo verificable).
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common import costos, metricas   # noqa: E402


def correr(M, ranker, hpb, rebal_every, warmup, aplicar_funding=True, equity_inicial=1.0,
           funding_matrix=None):
    """Corre el backtest cross-sectional sobre la matriz de precios M con el `ranker` dado.

    Args:
      M            : np.ndarray (T, S) de closes alineados.
      ranker       : fn(M, t) -> pesos (S,) o None. Función pura de señal.
      hpb          : horas por barra (para funding y anualización).
      rebal_every  : rebalancear cada `rebal_every` barras (anclado al `warmup`).
      warmup       : primera barra con señal válida (= lookback del ranker). La primera entrada ocurre en
                     `warmup`; los rebalanceos siguen en warmup, warmup+rebal_every, warmup+2*rebal_every...
                     Con rebal_every > T ⇒ solo la entrada inicial (buy-and-hold del libro long/short).
      aplicar_funding: si cobrar el drag PESIMISTA de funding sobre gross (ignorado si `funding_matrix`
                     no es None — ver abajo).
      equity_inicial: equity de arranque.
      funding_matrix: (M3, 2026-07-04) np.ndarray (T, S) opcional de tasas de funding REALES por
                     símbolo, alineadas a M (0 en barras sin evento real, la tasa real en las que sí —
                     ver `m3_carry/funding_real.py`). Si se provee, REEMPLAZA el modelo pesimista plano
                     por el costo/ingreso real y firmado: contribución = -w[s]·rate[s,t] sumada sobre
                     símbolos (LONG paga cuando rate>0, SHORT cobra cuando rate>0 — mismo signo que
                     `pnl_neto_cierre` del motor vivo). Con `funding_matrix=None` (default) el
                     comportamiento es IDÉNTICO al de antes de este cambio (no-regresión verificada).

    Returns dict con: equity (T,), retornos_netos (T-1,), turnover (T-1,), gross (T-1,), net_expo (T-1,),
      y métricas agregadas.
    """
    T, S = M.shape
    if funding_matrix is not None:
        funding_matrix = np.asarray(funding_matrix, dtype=float)
        if funding_matrix.shape != M.shape:
            # Guard Fable (validación M3, 2026-07-04): una matriz de funding construida con OTROS
            # times/símbolos que M se indexaría desalineada EN SILENCIO (o rompería raro por broadcast).
            # La correspondencia de timestamps sigue siendo responsabilidad del caller (construirla con
            # los MISMOS times/symbols de datos.alinear) — esto atrapa al menos el desalineo de forma.
            raise ValueError(
                f"funding_matrix.shape {funding_matrix.shape} != M.shape {M.shape} — debe construirse "
                f"con los MISMOS times/símbolos que M (m3_carry/funding_real.matrices_funding).")
    w = np.zeros(S, dtype=float)          # pesos actuales (fracción de equity)
    equity = equity_inicial
    eq_curve = np.empty(T, dtype=float)
    eq_curve[0] = equity
    net_rets = np.empty(T - 1, dtype=float)
    turn_series = np.zeros(T - 1, dtype=float)
    gross_series = np.zeros(T - 1, dtype=float)
    net_series = np.zeros(T - 1, dtype=float)

    quebro = False
    for t in range(1, T):
        eq_antes = equity
        ret = M[t] / M[t - 1] - 1.0                      # retorno de cada símbolo t-1 → t

        # (1) PnL del periodo: lo ganan los pesos que YA estaban puestos (fijados en/hasta t-1).
        port_ret = float(w @ ret)
        equity *= (1.0 + port_ret)

        # (1b) QUIEBRA (fix Fable 2026-07-04): un libro con shorts puede perder >100% en una barra
        #      (port_ret <= -1). Sin este clamp el equity quedaba NEGATIVO y el motor seguía operando
        #      con pesos sin sentido (se midió pnl −169% y curva negativa). Honesto = bancarrota:
        #      equity 0, libro cerrado, curva en 0 hasta el final.
        if equity <= 0.0:
            quebro = True
            equity = 0.0
            w = np.zeros(S, dtype=float)
            eq_curve[t:] = 0.0
            net_rets[t - 1] = -1.0
            if t <= T - 2:
                net_rets[t:] = 0.0
            break

        # (2) drift de pesos: mantener nocionales fijos = los pesos-fracción cambian con el precio.
        denom = 1.0 + port_ret
        w = w * (1.0 + ret) / denom

        # (3) funding: REAL por símbolo si se proveyó funding_matrix (M3); si no, el piso pesimista de M1.
        if funding_matrix is not None:
            equity *= (1.0 - float(w @ funding_matrix[t]))
        elif aplicar_funding:
            gross_now = float(np.abs(w).sum())
            equity *= (1.0 - costos.costo_funding(gross_now, hpb))

        # (3b) QUIEBRA por funding (fix Fable, validación M3 2026-07-04): con tasas reales (|rate|<=2%)
        #      es inalcanzable, pero una funding_matrix sintética/corrupta con |w·rate|>=1 dejaba equity
        #      negativa y el clamp de (1b) recién la atrapaba UNA BARRA DESPUÉS — la curva registraba un
        #      punto negativo y el rebalanceo de esta barra operaba con equity sin sentido. Mismo clamp.
        if equity <= 0.0:
            quebro = True
            equity = 0.0
            w = np.zeros(S, dtype=float)
            eq_curve[t:] = 0.0
            net_rets[t - 1] = -1.0
            if t <= T - 2:
                net_rets[t:] = 0.0
            break

        # (4) rebalanceo: fijar pesos objetivo con info HASTA t (causal); cobrar turnover.
        #     Calendario anclado al warmup: t = warmup, warmup+rebal_every, warmup+2*rebal_every, ...
        #     ANTI-LOOKAHEAD ESTRUCTURAL (fix Fable 2026-07-04): el ranker recibe M[:t+1] (vista, sin
        #     copia) — leer el futuro es IMPOSIBLE por construcción, no depende de la disciplina del
        #     ranker. M[:t+1] tiene t+1 filas; el índice t sigue siendo la barra actual.
        if t >= warmup and (t - warmup) % rebal_every == 0:
            target = ranker(M[:t + 1], t)
            if target is not None:
                turnover = float(np.abs(target - w).sum())
                equity *= (1.0 - costos.costo_rebalanceo(turnover))
                w = target
                turn_series[t - 1] = turnover

        eq_curve[t] = equity
        net_rets[t - 1] = equity / eq_antes - 1.0
        gross_series[t - 1] = float(np.abs(w).sum())
        net_series[t - 1] = float(w.sum())

    horas_totales = (T - 1) * hpb
    periodos_por_anio = (365.25 * 24) / hpb
    return {
        'equity': eq_curve,
        'retornos_netos': net_rets,
        'turnover': turn_series,
        'gross': gross_series,
        'net_expo': net_series,
        'pnl_pct': (eq_curve[-1] / eq_curve[0] - 1.0) * 100.0,
        'cagr_pct': metricas.cagr(eq_curve, horas_totales) * 100.0,
        'sharpe': metricas.sharpe(net_rets, periodos_por_anio),
        'max_dd_pct': metricas.max_drawdown(eq_curve) * 100.0,
        'profit_factor': metricas.profit_factor(net_rets),
        'turnover_medio': float(turn_series[turn_series > 0].mean()) if (turn_series > 0).any() else 0.0,
        'net_expo_medio_abs': float(np.abs(net_series).mean()),
        'quebro': quebro,
    }


def correr_null_permutacion(M, hacer_ranker_azar, hpb, rebal_every, warmup, n_sims, seed=42,
                            aplicar_funding=True, funding_matrix=None):
    """Null NAIVE por permutación aleatoria — ⚠️ NO APTO para el criterio de aceptación E1.

    HALLAZGO FABLE (2026-07-04): una permutación fresca por rebalanceo NO mantiene el turnover de una
    señal persistente (medido: null 1.35 vs momentum real 0.56 por rebalanceo, 2.4x) → el null paga
    ~2.4x los costos → percentil del real INFLADO (sesgo optimista: una config que pierde −53% dio
    percentil 100). Para E1 usar `correr_null_desplazado`. Este queda solo como cota gruesa.

    `hacer_ranker_azar(rng)` debe devolver un ranker aleatorio sembrado con ese rng (ver
    estrategia_xsmom.ranker_aleatorio). Determinista dado `seed` (ítem E2).
    Devuelve np.ndarray de pnl_pct de cada simulación.
    """
    rng = np.random.default_rng(seed)
    out = np.empty(n_sims, dtype=float)
    for i in range(n_sims):
        ranker_azar = hacer_ranker_azar(rng)
        res = correr(M, ranker_azar, hpb, rebal_every, warmup, aplicar_funding=aplicar_funding,
                     funding_matrix=funding_matrix)
        out[i] = res['pnl_pct']
    return out


def correr_null_desplazado(M, ranker_real, hpb, rebal_every, warmup, n_sims, seed=42,
                           aplicar_funding=True, min_offset_rebalanceos=1, funding_matrix=None):
    """Null JUSTO (ítem E1): rotación temporal circular de la señal REAL — mantiene cadencia,
    turnover y costos; destruye la alineación señal↔retorno-futuro.

    Mecánica: se precomputan los pesos objetivo reales en cada rebalanceo del calendario (causalmente,
    con M[:t+1]). Cada simulación del null aplica esa MISMA secuencia de libros rotada `off` rebalanceos
    (off aleatorio, determinista con `seed`): el libro que la señal real pidió en el rebalanceo j se
    aplica en el rebalanceo (j − off) mod J. Así:
      - la secuencia de turnovers objetivo es idéntica a la real (rotada) → mismos costos (±drift, ±1
        rebalanceo en el punto de empalme circular) — a diferencia del null por permutación;
      - se preserva cualquier sesgo estático de la señal (p.ej. "siempre long el símbolo X") → el
        percentil solo acredita el TIMING/selección alineada, no la inclinación estática. Más estricto
        y más honesto que el null por permutación.
    NOTA: el null rotado NO es causal (usa la señal de otro momento, incluso "futuro" vía el wrap) — es
    un control estadístico, no una estrategia operable. Eso es válido y estándar para un null.

    Args extra:
      min_offset_rebalanceos: excluye offsets en [0, min) y (J−min, J] — offsets chicos dejan el null
        muy solapado con la señal real (correlacionado → percentil PESIMISTA, dirección segura, pero
        desperdicia sims). Recomendado: ≈ lookback/rebal_every. Default 1 (solo excluye la identidad).

    Devuelve np.ndarray de pnl_pct de cada simulación. Determinista dado `seed` (E2/G1).
    """
    T = M.shape[0]
    ts = [t for t in range(1, T) if t >= warmup and (t - warmup) % rebal_every == 0]
    if not ts:
        raise ValueError("Sin rebalanceos en el calendario (warmup/rebal_every vs T).")
    targets = [ranker_real(M[:t + 1], t) for t in ts]   # causal por construcción (mismo slicing que correr)
    J = len(targets)
    m = max(1, int(min_offset_rebalanceos))   # m>=1 SIEMPRE: off=0 (y off=J) sería la identidad = el real
    validos = list(range(m, J - m + 1))
    if not validos:
        raise ValueError(f"min_offset_rebalanceos={m} no deja offsets válidos (J={J}).")
    rng = np.random.default_rng(seed)
    offs = rng.choice(validos, size=n_sims, replace=(n_sims > len(validos)))
    idx_de_t = {t: j for j, t in enumerate(ts)}
    out = np.empty(n_sims, dtype=float)
    for i, off in enumerate(offs):
        off = int(off)

        def ranker_tabla(Mv, t, _off=off):
            j = idx_de_t.get(int(t))
            if j is None:
                return None
            return targets[(j + _off) % J]

        res = correr(M, ranker_tabla, hpb, rebal_every, warmup, aplicar_funding=aplicar_funding,
                     funding_matrix=funding_matrix)
        out[i] = res['pnl_pct']
    return out


def percentil_vs_null(pnl_real, nulls):
    """Percentil del PnL real dentro de la distribución null (ítem E1). 100 = mejor que todos los azares."""
    nulls = np.asarray(nulls, dtype=float)
    if len(nulls) == 0:
        return None
    return round(float((nulls < pnl_real).mean() * 100.0), 1)
