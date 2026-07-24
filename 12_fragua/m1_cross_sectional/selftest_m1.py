"""Self-tests de M1 con respuestas ANALÍTICAS conocidas (calculadas a mano).

Objetivo: pinnear la matemática del motor con casos donde el resultado correcto se puede computar a mano,
para que Fable pueda VERIFICAR (no solo confiar) cada propiedad de honestidad. Cada test cita el número
esperado y de dónde sale.

Correr:  python3 selftest_m1.py
Todos deben imprimir OK. Un fallo = un error de lógica que hay que arreglar ANTES de cualquier backtest serio.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common import costos                     # noqa: E402
import estrategia_xsmom as est                # noqa: E402
import engine_xs as eng                       # noqa: E402

TOL = 1e-9


def _sin_costos():
    """Context: pone costos a cero (para tests de PnL puro). Devuelve (viejo_turnover, viejo_funding)."""
    viejo = (costos.COSTO_POR_TURNOVER, costos.FUNDING_8H)
    costos.COSTO_POR_TURNOVER = 0.0
    costos.FUNDING_8H = 0.0
    return viejo


def _restaurar(viejo):
    costos.COSTO_POR_TURNOVER, costos.FUNDING_8H = viejo


def test_momentum_elige_bien():
    """El ranker de momentum debe ir LONG el que más subió y SHORT el que más bajó."""
    # 3 símbolos; retorno trailing (lookback 1) claro: S0 +10%, S1 0%, S2 -10%.
    M = np.array([[100., 100., 100.],
                  [110., 100.,  90.]])
    r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
    w = r(M, 1)
    assert abs(w[0] - 0.5) < TOL, w      # S0 long
    assert abs(w[1] - 0.0) < TOL, w      # S1 fuera
    assert abs(w[2] + 0.5) < TOL, w      # S2 short
    assert abs(w.sum()) < TOL            # dollar-neutral
    assert abs(np.abs(w).sum() - 1.0) < TOL   # gross = 1.0
    print("OK  test_momentum_elige_bien (long S0, short S2, neutral)")


def test_pnl_rebalanceo_cada_barra():
    """PnL analítico, rebalanceo cada barra, sin costos → equity final EXACTA = 1.10.

    Prices S0: 100→110→121 (+10%/barra), S1: 100→90→81 (-10%/barra). Long S0 / short S1 (0.5 c/u).
    Barra t=1: entra flat→[.5,-.5], PnL 0 (venía de cero). Barra t=2: port_ret = .5*.1 + (-.5)*(-.1)=.10.
    equity = 1.0 * 1.10 = 1.10. (Cálculo a mano en el docstring del test.)
    """
    viejo = _sin_costos()
    try:
        M = np.array([[100., 100.],
                      [110.,  90.],
                      [121.,  81.]])
        r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
        res = eng.correr(M, r, hpb=1.0, rebal_every=1, warmup=1, aplicar_funding=False)
        assert abs(res['equity'][-1] - 1.10) < 1e-9, res['equity']
    finally:
        _restaurar(viejo)
    print("OK  test_pnl_rebalanceo_cada_barra (equity == 1.10 exacto)")


def test_pnl_hold_sin_rebalanceo():
    """PnL analítico, HOLD (rebal_every enorme), sin costos → equity final EXACTA = 1.20.

    Mismos precios extendidos a t=3 (S0 133.1, S1 72.9). Entra en t=1 a [.5,-.5] y NO rebalancea.
    Es un buy&hold del libro long/short: dollar-PnL = .5*(133.1/110-1) - .5*(72.9/90-1)
      = .5*0.21 - .5*(-0.19) = .105 + .095 = .20 → equity 1.20. (Verificable a mano.)
    """
    viejo = _sin_costos()
    try:
        M = np.array([[100., 100.],
                      [110.,  90.],
                      [121.,  81.],
                      [133.1, 72.9]])
        r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
        res = eng.correr(M, r, hpb=1.0, rebal_every=10_000, warmup=1, aplicar_funding=False)
        assert abs(res['equity'][-1] - 1.20) < 1e-9, res['equity']
    finally:
        _restaurar(viejo)
    print("OK  test_pnl_hold_sin_rebalanceo (equity == 1.20 exacto)")


def test_costo_entrada_exacto():
    """Contabilidad de costo: una sola entrada (turnover=gross=1.0) cobra fee+slippage = 0.10% UNA vez.

    Con los costos REALES (0.001 por unidad de turnover) y funding off, la entrada en t=1 lleva el equity
    de 1.0 a 0.999; luego el hold hasta t=3 multiplica por 1.20 → final = 0.999 * 1.20 = 1.1988 exacto.
    """
    M = np.array([[100., 100.],
                  [110.,  90.],
                  [121.,  81.],
                  [133.1, 72.9]])
    r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
    res = eng.correr(M, r, hpb=1.0, rebal_every=10_000, warmup=1, aplicar_funding=False)
    esperado = 0.999 * 1.20   # = 1.1988
    assert abs(res['equity'][-1] - esperado) < 1e-9, (res['equity'][-1], esperado)
    # y el turnover registrado en la entrada debe ser exactamente 1.0
    assert abs(res['turnover'][0] - 1.0) < TOL, res['turnover'][:3]
    print(f"OK  test_costo_entrada_exacto (equity == {esperado:.4f}, turnover entrada == 1.0)")


def test_dollar_neutral_siempre():
    """En cada rebalanceo el libro es dollar-neutral (sum pesos ~0) — verificado vía net_expo medio ~0
    en un mercado real-ish aleatorio con rebalanceo frecuente."""
    rng = np.random.default_rng(0)
    T, S = 500, 6
    # random walk multiplicativo
    rets = rng.normal(0, 0.01, size=(T, S))
    M = 100 * np.cumprod(1 + rets, axis=0)
    r = est.ranker_momentum(lookback=24, k=2, gross=1.0)
    res = eng.correr(M, r, hpb=1.0, rebal_every=1, warmup=24, aplicar_funding=False)
    # Justo tras cada rebalanceo el net es 0; entre rebalanceos driftea. Con rebal cada barra, el net
    # medido (post-rebalanceo) debe ser ~0.
    assert res['net_expo_medio_abs'] < 1e-9, res['net_expo_medio_abs']
    print("OK  test_dollar_neutral_siempre (net_expo ~ 0 tras cada rebalanceo)")


def test_anti_lookahead():
    """Perturbar precios FUTUROS no debe cambiar el peso en t (la señal es causal — ítem A3)."""
    rng = np.random.default_rng(1)
    M = 100 * np.cumprod(1 + rng.normal(0, 0.01, size=(100, 5)), axis=0)
    r = est.ranker_momentum(lookback=10, k=1, gross=1.0)
    t = 50
    w_antes = r(M, t).copy()
    M2 = M.copy()
    M2[t + 1:] *= 1.5            # alterar TODO el futuro
    w_despues = r(M2, t)
    assert np.allclose(w_antes, w_despues), (w_antes, w_despues)
    print("OK  test_anti_lookahead (peso en t inmune a datos de t+1 en adelante)")


def test_null_determinista():
    """Mismo seed → misma distribución null, bit a bit (ítem E2/G1). Cubre AMBOS nulls."""
    rng = np.random.default_rng(2)
    M = 100 * np.cumprod(1 + rng.normal(0, 0.01, size=(400, 6)), axis=0)
    hacer = lambda rg: est.ranker_aleatorio(k=2, gross=1.0, rng=rg, warmup=24)
    a = eng.correr_null_permutacion(M, hacer, hpb=1.0, rebal_every=8, warmup=24, n_sims=20, seed=123)
    b = eng.correr_null_permutacion(M, hacer, hpb=1.0, rebal_every=8, warmup=24, n_sims=20, seed=123)
    assert np.array_equal(a, b), "null permutación no determinista con mismo seed"
    r = est.ranker_momentum(lookback=24, k=2, gross=1.0)
    c = eng.correr_null_desplazado(M, r, hpb=1.0, rebal_every=8, warmup=24, n_sims=15, seed=123)
    d = eng.correr_null_desplazado(M, r, hpb=1.0, rebal_every=8, warmup=24, n_sims=15, seed=123)
    assert np.array_equal(c, d), "null desplazado no determinista con mismo seed"
    print("OK  test_null_determinista (mismo seed → misma distribución, ambos nulls)")


def test_funding_reduce_equity():
    """Encender funding SIEMPRE reduce (o iguala) el equity vs apagarlo — es un costo, nunca un regalo."""
    rng = np.random.default_rng(3)
    M = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, size=(600, 6)), axis=0)
    r = est.ranker_momentum(lookback=24, k=2, gross=1.0)
    con = eng.correr(M, r, hpb=1.0, rebal_every=8, warmup=24, aplicar_funding=True)
    sin = eng.correr(M, r, hpb=1.0, rebal_every=8, warmup=24, aplicar_funding=False)
    assert con['equity'][-1] <= sin['equity'][-1] + TOL, (con['equity'][-1], sin['equity'][-1])
    print("OK  test_funding_reduce_equity (funding ON <= funding OFF)")


def test_percentil_null():
    """percentil_vs_null: un real por encima de todos los nulls → 100; por debajo de todos → 0."""
    nulls = np.array([1., 2., 3., 4., 5.])
    assert eng.percentil_vs_null(10.0, nulls) == 100.0
    assert eng.percentil_vs_null(0.0, nulls) == 0.0
    assert eng.percentil_vs_null(3.5, nulls) == 60.0   # 3 de 5 por debajo
    print("OK  test_percentil_null (percentil correcto)")


# ---------------------------------------------------------------------------
# Tests agregados por Fable (validación 2026-07-04) — cada uno captura un bug
# encontrado en la auditoría o pinnea una propiedad que los tests originales no cubrían.
# ---------------------------------------------------------------------------

def test_drift_asimetrico():
    """Caso ASIMÉTRICO a mano (punto abierto (c) del constructor): pesos ±0.5, retornos distintos por
    lado y por barra, incluye al short PERDIENDO cuando su precio sube y ganando cuando baja.

    Precios: S0: 100→101→121.2→127.26 ; S1: 100→100→110→88.
    Entrada t=1 (momentum lookback 1: S0 +1% > S1 0%) → w=[+0.5, −0.5], sin costos.
    Barra t=2: ret=[+20%, +10%] → port_ret = .5·.2 − .5·.1 = 0.05 → equity 1.05.
      Drift: w0 = .5·1.2/1.05 = 4/7 ; w1 = −.5·1.1/1.05 = −11/21 ; net = +1/21 (net LONG por drift).
    Barra t=3: ret=[+5%, −20%] → port_ret = (4/7)·.05 + (11/21)·.2 = 2/15 → equity = 1.05·17/15 = 1.19.
    Verificación independiente (buy&hold nocional fijo): .5·(127.26/101−1) − .5·(88/100−1)
      = .5·.26 + .5·.12 = .13 + .06 = 0.19 ✓.
    """
    viejo = _sin_costos()
    try:
        M = np.array([[100., 100.],
                      [101., 100.],
                      [121.2, 110.],
                      [127.26, 88.]])
        r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
        res = eng.correr(M, r, hpb=1.0, rebal_every=10_000, warmup=1, aplicar_funding=False)
        assert abs(res['equity'][-1] - 1.19) < 1e-12, res['equity']
        # neutralidad rota por drift (esperado y medible): net tras la barra t=2 = +1/21
        assert abs(res['net_expo'][1] - 1.0 / 21.0) < 1e-12, res['net_expo']
    finally:
        _restaurar(viejo)
    print("OK  test_drift_asimetrico (equity == 1.19 exacto, net drift == +1/21)")


def test_turnover_sobre_pesos_drifteados():
    """El turnover de un rebalanceo se mide contra los pesos DRIFTEADOS, no contra el target anterior.

    Mismos precios del caso asimétrico, rebal_every=2 → rebalanceos en t=1 y t=3.
    En t=3, tras PnL+drift: w = [(4/7)·1.05, (−11/21)·0.8] / (17/15) = [9/17, −44/119].
    Target = [.5, −.5] → turnover = |1/2−9/17| + |−1/2+44/119| = 1/34 + 31/238 = 19/119 ≈ 0.15966.
    (Calculado a mano; sin costos para no ensuciar el equity, que debe seguir en 1.19.)
    """
    viejo = _sin_costos()
    try:
        M = np.array([[100., 100.],
                      [101., 100.],
                      [121.2, 110.],
                      [127.26, 88.]])
        r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
        res = eng.correr(M, r, hpb=1.0, rebal_every=2, warmup=1, aplicar_funding=False)
        assert abs(res['turnover'][2] - 19.0 / 119.0) < 1e-12, res['turnover']
        assert abs(res['equity'][-1] - 1.19) < 1e-12, res['equity']
    finally:
        _restaurar(viejo)
    print("OK  test_turnover_sobre_pesos_drifteados (turnover == 19/119 exacto)")


def test_guard_neutralidad_todos_los_rankers():
    """BUG capturado (Fable): con 2k>S los lados se solapan y el libro quedaba NO-neutral EN SILENCIO
    (reversion y aleatorio no tenían el guard que momentum sí tenía; se midió sum=−0.25, gross=0.75)."""
    M = np.array([[100., 100., 100.],
                  [110., 100., 90.]])
    for nombre, ranker in [
        ('momentum', est.ranker_momentum(lookback=1, k=2, gross=1.0)),
        ('reversion', est.ranker_reversion(lookback=1, k=2, gross=1.0)),
        ('aleatorio', est.ranker_aleatorio(k=2, gross=1.0, rng=np.random.default_rng(0))),
    ]:
        try:
            ranker(M, 1)
            raise AssertionError(f"{nombre} con 2k>S no levantó ValueError")
        except ValueError:
            pass
    print("OK  test_guard_neutralidad_todos_los_rankers (2k>S revienta en los 3 rankers)")


def test_quiebra_clamp():
    """BUG capturado (Fable): un short que pierde >200% en una barra (port_ret ≤ −1) dejaba el equity
    NEGATIVO y el motor seguía operando (se midió pnl −169%, curva negativa, CAGR sin sentido).
    Ahora: quiebra honesta — equity 0, libro cerrado, curva en 0, métricas finitas."""
    M = np.array([[100., 100.],
                  [110., 90.],
                  [110., 400.],    # el short (S1) sube 344% en una barra → port_ret < −1
                  [120., 410.]])
    r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
    res = eng.correr(M, r, hpb=1.0, rebal_every=1, warmup=1, aplicar_funding=False)
    assert res['quebro'] is True
    assert (res['equity'] >= 0).all(), res['equity']
    assert res['equity'][-1] == 0.0
    assert abs(res['pnl_pct'] + 100.0) < TOL, res['pnl_pct']
    assert abs(res['max_dd_pct'] - 100.0) < TOL, res['max_dd_pct']
    assert abs(res['cagr_pct'] + 100.0) < TOL, res['cagr_pct']
    assert np.isfinite(res['retornos_netos']).all()
    # y una corrida sana debe reportar quebro=False
    M_ok = np.array([[100., 100.], [110., 90.], [121., 81.]])
    assert eng.correr(M_ok, r, hpb=1.0, rebal_every=1, warmup=1, aplicar_funding=False)['quebro'] is False
    print("OK  test_quiebra_clamp (equity clamp en 0, métricas finitas, flag quebro)")


def test_engine_no_pasa_futuro():
    """ANTI-LOOKAHEAD ESTRUCTURAL (Fable): el engine entrega al ranker SOLO M[:t+1]. Un ranker
    'tramposo' que lee la última fila disponible (M[-1]) debe obtener M[t], no el futuro — el resultado
    tiene que ser idéntico al del ranker causal explícito, y las filas visibles exactamente t+1."""
    vistos = []

    def tramposo(Mv, t):
        vistos.append((t, Mv.shape[0]))
        ret = Mv[-1] / Mv[0] - 1.0            # última fila que le den: si hay futuro, lo usa
        orden = np.argsort(ret, kind='stable')
        return est._pesos_desde_ranking(orden, 1, 1.0, Mv.shape[1])

    def causal(Mv, t):
        ret = Mv[t] / Mv[0] - 1.0
        orden = np.argsort(ret, kind='stable')
        return est._pesos_desde_ranking(orden, 1, 1.0, Mv.shape[1])

    rng = np.random.default_rng(7)
    M = 100 * np.cumprod(1 + rng.normal(0, 0.01, size=(60, 4)), axis=0)
    viejo = _sin_costos()
    try:
        a = eng.correr(M, tramposo, hpb=1.0, rebal_every=5, warmup=10, aplicar_funding=False)
        b = eng.correr(M, causal, hpb=1.0, rebal_every=5, warmup=10, aplicar_funding=False)
    finally:
        _restaurar(viejo)
    assert np.allclose(a['equity'], b['equity']), "el engine dejó ver el futuro"
    assert all(filas == t + 1 for t, filas in vistos), vistos
    print("OK  test_engine_no_pasa_futuro (el ranker recibe exactamente M[:t+1])")


def test_null_desplazado_turnover_justo():
    """JUSTICIA DEL NULL (ítem E1, el hallazgo central de la validación): el null por permutación rota
    mucho más que una señal persistente → paga más costos → percentil inflado. El null DESPLAZADO debe
    tener turnover ≈ igual al real. Datos sintéticos con tendencias persistentes (momentum rota poco)."""
    rng = np.random.default_rng(11)
    T, S = 900, 6
    mu = np.linspace(-0.002, 0.002, S)                     # drifts persistentes por símbolo
    rets = mu + rng.normal(0, 0.008, size=(T, S))
    M = 100 * np.cumprod(1 + rets, axis=0)
    r = est.ranker_momentum(lookback=48, k=2, gross=1.0)

    real = eng.correr(M, r, hpb=1.0, rebal_every=8, warmup=48, aplicar_funding=False)

    def turnover_de(ranker):
        return eng.correr(M, ranker, hpb=1.0, rebal_every=8, warmup=48,
                          aplicar_funding=False)['turnover_medio']

    # null desplazado: turnover por sim ≈ turnover real (misma secuencia de libros, rotada)
    ts = [t for t in range(1, T) if t >= 48 and (t - 48) % 8 == 0]
    J = len(ts)
    rng2 = np.random.default_rng(99)
    turns_desp = []
    for off in rng2.choice(range(6, J - 6 + 1), size=10, replace=False):
        targets = [r(M[:t + 1], t) for t in ts]
        idx = {t: j for j, t in enumerate(ts)}
        tabla = lambda Mv, t, _o=int(off): targets[(idx[int(t)] + _o) % J]
        turns_desp.append(turnover_de(tabla))
    t_desp = float(np.mean(turns_desp))

    # null permutación: turnover teórico ~4/3 para k=2,S=6 — MUY por encima del real
    rng3 = np.random.default_rng(5)
    turns_perm = [turnover_de(est.ranker_aleatorio(k=2, gross=1.0, rng=rng3, warmup=48))
                  for _ in range(10)]
    t_perm = float(np.mean(turns_perm))

    assert 0.7 * real['turnover_medio'] < t_desp < 1.3 * real['turnover_medio'], \
        (real['turnover_medio'], t_desp)
    assert t_perm > 2.0 * real['turnover_medio'], (real['turnover_medio'], t_perm)
    print(f"OK  test_null_desplazado_turnover_justo (real={real['turnover_medio']:.3f}, "
          f"desplazado={t_desp:.3f} ≈ real, permutación={t_perm:.3f} = sesgado)")


def test_datos_alinear_duplicados():
    """BUG capturado (Fable): un timestamp duplicado en un símbolo multiplica filas en el inner-join
    (producto cartesiano) y corrompía la matriz EN SILENCIO. Ahora alinear() revienta."""
    import pandas as pd
    from common import datos
    df_a = pd.DataFrame({'time': [1, 2, 2, 3], 'close': [10., 11., 11.5, 12.]})   # 2 duplicado
    df_b = pd.DataFrame({'time': [1, 2, 3], 'close': [20., 21., 22.]})
    try:
        datos.alinear({'A': df_a, 'B': df_b})
        raise AssertionError("alinear() no detectó timestamps duplicados")
    except ValueError:
        pass
    print("OK  test_datos_alinear_duplicados (duplicados → ValueError)")


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    fallos = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            fallos += 1
            print(f"FALLO  {t.__name__}: {e}")
        except Exception as e:
            fallos += 1
            print(f"ERROR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*50}\n{len(tests) - fallos}/{len(tests)} tests OK")
    sys.exit(1 if fallos else 0)
