"""Self-tests de M3 con respuestas ANALÍTICAS conocidas (calculadas a mano).

Cubre: (1) alineación de funding real incl. el caso límite "tasa real de exactamente 0%" (bug propio
encontrado y corregido antes de pasar el motor a validación), (2) la fórmula de funding real dentro del
motor (contribución = -w·rate), (3) el ranker de carry, (4) no-regresión del motor M1 sin tocar
(funding_matrix=None reproduce exacto lo de antes).

Correr:  python3 selftest_m3.py
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'm1_cross_sectional'))
sys.path.insert(0, os.path.dirname(__file__))
import engine_xs as eng                # noqa: E402
import estrategia_xsmom as est         # noqa: E402
from funding_real import matrices_funding    # noqa: E402
from estrategia_carry import ranker_carry    # noqa: E402

TOL = 1e-9


def test_matrices_funding_caso_tasa_cero():
    """El caso límite que motivó el fix: una tasa REAL de exactamente 0% en un evento posterior a un
    evento con tasa distinta de cero debe registrarse como 0% (el valor nuevo), NO como el último valor
    NO-cero anterior (bug: `replace(0.0, np.nan)` confundiría "evento con tasa 0" con "sin evento")."""
    times = pd.date_range('2024-01-01 00:00', periods=10, freq='1h')
    # Símbolo A: eventos en bar0 (0.0001) y bar8 (-0.0002) — caso normal, sin ceros.
    df_a = pd.DataFrame({'time': [times[0], times[8]], 'rate': [0.0001, -0.0002]})
    # Símbolo B: evento en bar0 (0.0005, no-cero) y bar8 (0.0 EXACTO — la tasa real cae a cero).
    df_b = pd.DataFrame({'time': [times[0], times[8]], 'rate': [0.0005, 0.0]})
    raw = {'A': df_a, 'B': df_b}

    pagos, conocida, meta = matrices_funding(raw, times, ['A', 'B'])

    # pagos: disperso, 0 en toda barra sin evento, el valor real en las que sí (incl. el 0.0 real de B).
    esperado_pagos_A = np.zeros(10); esperado_pagos_A[0] = 0.0001; esperado_pagos_A[8] = -0.0002
    esperado_pagos_B = np.zeros(10); esperado_pagos_B[0] = 0.0005; esperado_pagos_B[8] = 0.0
    assert np.allclose(pagos[:, 0], esperado_pagos_A, atol=TOL)
    assert np.allclose(pagos[:, 1], esperado_pagos_B, atol=TOL)

    # conocida (forward-fill CAUSAL): A = 0.0001 en bars 0-7, -0.0002 en bars 8-9.
    esperado_conocida_A = np.array([0.0001]*8 + [-0.0002]*2)
    assert np.allclose(conocida[:, 0], esperado_conocida_A, atol=TOL)

    # B — EL CASO CRÍTICO: 0.0005 en bars 0-7 (conocido desde bar0), y 0.0 EXACTO en bars 8-9 (el nuevo
    # valor real, NO el 0.0005 stale que daría el bug de "replace(0.0,nan)").
    esperado_conocida_B = np.array([0.0005]*8 + [0.0]*2)
    assert np.allclose(conocida[:, 1], esperado_conocida_B, atol=TOL), (
        f"conocida[B]={conocida[:,1]} — si da 0.0005 en bars 8-9 el bug de tasa-cero volvió")

    assert meta['eventos_promedio_por_simbolo'] == 2
    print("OK  test_matrices_funding_caso_tasa_cero (tasa real de 0% no se confunde con 'sin evento')")


def test_matrices_funding_colision_hora():
    """Si dos eventos del mismo símbolo redondean a la misma hora (no debería pasar con espaciado 8h,
    pero si el cache tuviera un duplicado), en PAGOS se SUMAN (ambos pagos ocurren) y se reporta en meta.
    En CONOCIDA (fix Fable): queda la del ÚLTIMO evento publicado, NO la suma — "última tasa conocida"
    es una tasa que existió, no un agregado."""
    times = pd.date_range('2024-01-01 00:00', periods=3, freq='1h')
    df = pd.DataFrame({'time': [times[0], times[0] + pd.Timedelta(seconds=5)], 'rate': [0.0001, 0.0002]})
    raw = {'A': df}
    pagos, conocida, meta = matrices_funding(raw, times, ['A'])
    assert abs(pagos[0, 0] - 0.0003) < TOL, pagos[:, 0]   # suma de ambos eventos redondeados a la misma hora
    assert meta['colisiones_hora'] == 1
    # conocida = la última tasa publicada (0.0002, el evento de las 00:00:05), no la suma 0.0003
    assert np.allclose(conocida[:, 0], 0.0002, atol=TOL), conocida[:, 0]
    print("OK  test_matrices_funding_colision_hora (pagos suma, conocida usa la última, meta reporta)")


def test_formula_funding_real_en_motor():
    """La contribución de funding real en el motor es exactamente -w·rate, aplicada en el mismo punto
    del loop (post-drift) que el modelo pesimista — verificado a mano.

    2 símbolos, entrada [+0.5,-0.5] en t=1 (sin costos de turnover, aislando el efecto de funding), precio
    CONSTANTE (así el drift no interfiere) — en t=2 se cobra/paga funding real: rate=[0.001, -0.002].
    Esperado: equity tras t=2 = equity_tras_t1 * (1 - (0.5*0.001 + (-0.5)*(-0.002)))
                              = equity_tras_t1 * (1 - (0.0005 + 0.001)) = equity_tras_t1 * 0.9985.
    """
    from common import costos as costos_m1
    viejo = (costos_m1.COSTO_POR_TURNOVER, costos_m1.FUNDING_8H)
    costos_m1.COSTO_POR_TURNOVER = 0.0   # aislar: sin costo de turnover en la entrada
    try:
        M = np.array([[100., 100.],
                      [100., 100.],
                      [100., 100.]])   # precio constante -> port_ret=0, drift=identidad, aislado
        r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
        # con precio constante ranker_momentum daría ret=0 en ambos y el orden es arbitrario/estable;
        # forzamos el libro manualmente para que el test sea inequívoco:
        def ranker_fijo(Mv, t):
            return np.array([0.5, -0.5]) if t == 1 else None

        fm = np.zeros((3, 2))
        fm[2] = [0.001, -0.002]   # evento de funding real SOLO en t=2

        res = eng.correr(M, ranker_fijo, hpb=1.0, rebal_every=1, warmup=1,
                         aplicar_funding=False, funding_matrix=fm)
        # equity tras t=1: entra [.5,-.5] sin costo (turnover cost=0) -> 1.0 (precio no se movió aún)
        # equity tras t=2: precio sigue igual (port_ret=0), pero se cobra funding real:
        esperado = 1.0 * (1.0 - (0.5*0.001 + (-0.5)*(-0.002)))   # = 0.9985
        assert abs(res['equity'][2] - esperado) < 1e-9, (res['equity'], esperado)
    finally:
        costos_m1.COSTO_POR_TURNOVER, costos_m1.FUNDING_8H = viejo
    print(f"OK  test_formula_funding_real_en_motor (equity == {esperado:.4f} exacto)")


def test_funding_matrix_none_no_regresion():
    """Con funding_matrix=None el motor debe comportarse IDÉNTICO a antes de agregar el parámetro."""
    rng = np.random.default_rng(7)
    M = 100 * np.cumprod(1 + rng.normal(0, 0.01, size=(300, 6)), axis=0)
    r = est.ranker_momentum(lookback=24, k=2, gross=1.0)
    a = eng.correr(M, r, hpb=1.0, rebal_every=8, warmup=24, aplicar_funding=True)
    b = eng.correr(M, r, hpb=1.0, rebal_every=8, warmup=24, aplicar_funding=True, funding_matrix=None)
    assert a['pnl_pct'] == b['pnl_pct'], (a['pnl_pct'], b['pnl_pct'])
    print("OK  test_funding_matrix_none_no_regresion (funding_matrix=None == comportamiento pre-M3)")


def test_ranker_carry_elige_bien():
    """ranker_carry: long el símbolo con la tasa MÁS NEGATIVA, short el de tasa MÁS POSITIVA."""
    conocida = np.array([[0.0005, -0.0010, 0.0002]])   # 1 barra, 3 símbolos
    M = np.zeros((1, 3))   # el ranker de carry no usa M — dummy
    r = ranker_carry(conocida, k=1, gross=1.0)
    w = r(M, 0)
    assert abs(w[1] - 0.5) < TOL, w    # símbolo 1 (-0.0010, la más negativa) -> LONG
    assert abs(w[0] + 0.5) < TOL, w    # símbolo 0 (+0.0005, la más positiva) -> SHORT
    assert abs(w[2]) < TOL, w          # símbolo 2 (+0.0002, intermedia) -> fuera
    assert abs(w.sum()) < TOL and abs(np.abs(w).sum() - 1.0) < TOL
    print("OK  test_ranker_carry_elige_bien (long tasa más negativa, short tasa más positiva)")


# ---------------------------------------------------------------------------
# Tests agregados por Fable (validación M3, 2026-07-04) — cada uno captura un bug
# arreglado en la auditoría o pinnea una propiedad que los tests del constructor no cubrían.
# ---------------------------------------------------------------------------

def test_funding_con_drift_y_signos():
    """Caso analítico A MANO: funding real aplicado sobre pesos POST-DRIFT, con los 4 combos de signo
    (el test del constructor cubría solo 2 — ambos 'paga' — y con precio constante, sin drift).

    Precios: S0 100→100→110→110 ; S1 100→100→95→95. Entrada [+0.5, −0.5] en t=1 (sin costo de turnover).
    t=2: ret=[+10%, −5%] → port_ret = .5·.1 + (−.5)(−.05) = 0.075 → equity 1.075.
         Drift: w0 = .5·1.10/1.075 = 22/43 ; w1 = −.5·0.95/1.075 = −19/43.
         Funding rate=[+0.002, −0.001] → LONG PAGA (rate>0) y SHORT PAGA (rate<0):
         w·rate = (22·0.002 − 19·0.001)/43 = 0.063/43 → equity ×= (1 − 0.063/43).
    t=3: precio quieto (drift identidad). rate=[−0.003, +0.004] → LONG COBRA y SHORT COBRA:
         w·rate = (−22·0.003 − 19·0.004)/43 = −0.142/43 → equity ×= (1 + 0.142/43).
    Esperado EXACTO: 1.075 · (1 − 0.063/43) · (1 + 0.142/43).
    """
    from common import costos as costos_m1
    viejo = costos_m1.COSTO_POR_TURNOVER
    costos_m1.COSTO_POR_TURNOVER = 0.0
    try:
        M = np.array([[100., 100.],
                      [100., 100.],
                      [110., 95.],
                      [110., 95.]])

        def ranker_fijo(Mv, t):
            return np.array([0.5, -0.5]) if t == 1 else None

        fm = np.zeros((4, 2))
        fm[2] = [0.002, -0.001]    # ambos lados PAGAN
        fm[3] = [-0.003, 0.004]    # ambos lados COBRAN

        res = eng.correr(M, ranker_fijo, hpb=1.0, rebal_every=1, warmup=1,
                         aplicar_funding=False, funding_matrix=fm)
        esperado = 1.075 * (1.0 - 0.063 / 43.0) * (1.0 + 0.142 / 43.0)
        assert abs(res['equity'][-1] - esperado) < 1e-12, (res['equity'], esperado)
        # y el funding del combo 'cobra' debe haber AUMENTADO el equity entre t=2 y t=3
        assert res['equity'][3] > res['equity'][2]
    finally:
        costos_m1.COSTO_POR_TURNOVER = viejo
    print(f"OK  test_funding_con_drift_y_signos (equity == {esperado:.12f} exacto, 4 combos de signo)")


def test_conocida_causal_futuro_no_afecta():
    """A1 para el funding: perturbar un evento FUTURO no puede cambiar `conocida` en barras anteriores
    (el ffill debe ser estrictamente hacia adelante) ni la decisión del ranker de carry en t previos.
    `conocida` vive FUERA del slicing M[:t+1] del engine — este test pinnea su causalidad propia."""
    times = pd.date_range('2024-01-01 00:00', periods=20, freq='1h')
    base = pd.DataFrame({'time': [times[2], times[15]], 'rate': [0.0004, 0.0009]})
    alterado = pd.DataFrame({'time': [times[2], times[15]], 'rate': [0.0004, -0.0777]})  # futuro distinto
    otro = pd.DataFrame({'time': [times[2], times[15]], 'rate': [-0.0006, 0.0001]})      # 2do símbolo fijo

    _, con_a, _ = matrices_funding({'A': base, 'B': otro}, times, ['A', 'B'])
    _, con_b, _ = matrices_funding({'A': alterado, 'B': otro}, times, ['A', 'B'])
    # hasta la barra 14 inclusive, conocida idéntica (el evento de la barra 15 no existe aún)
    assert np.array_equal(con_a[:15], con_b[:15]), "conocida cambió ANTES del evento futuro — lookahead"
    assert con_a[15, 0] != con_b[15, 0]   # y desde el evento sí difieren (sanidad del test)

    M = np.ones((20, 2))
    for t in range(3, 15):
        wa = ranker_carry(con_a, k=1, gross=1.0)(M[:t + 1], t)
        wb = ranker_carry(con_b, k=1, gross=1.0)(M[:t + 1], t)
        assert np.array_equal(wa, wb), f"decisión en t={t} afectada por un evento futuro"
    print("OK  test_conocida_causal_futuro_no_afecta (ffill estrictamente hacia adelante)")


def test_conocida_seed_pre_ventana():
    """BUG capturado (Fable): las barras anteriores al primer evento EN VENTANA quedaban con
    conocida=0.0 aunque una tasa real estaba publicada antes de la ventana (confirmado en ambos caches
    reales: barras 0..6 en 0.0 con el evento de 1h antes del inicio). La 'última tasa conocida' en esas
    barras es la del último evento PRE-ventana, no 0."""
    times = pd.date_range('2024-01-01 05:00', periods=6, freq='1h')   # ventana 05:00..10:00
    df = pd.DataFrame({'time': [pd.Timestamp('2024-01-01 00:00'),      # PRE-ventana (publicada, conocida)
                                pd.Timestamp('2024-01-01 08:00')],     # primer evento en ventana (barra 3)
                       'rate': [0.0007, -0.0002]})
    pagos, conocida, meta = matrices_funding({'A': df}, times, ['A'])
    assert np.allclose(conocida[:3, 0], 0.0007, atol=TOL), conocida[:, 0]   # seed pre-ventana, NO 0.0
    assert np.allclose(conocida[3:, 0], -0.0002, atol=TOL), conocida[:, 0]
    assert np.allclose(pagos[:3, 0], 0.0, atol=TOL)      # el pago pre-ventana NO se cobra (fuera de M)
    assert abs(pagos[3, 0] + 0.0002) < TOL
    assert meta['por_simbolo']['A']['seed_pre_ventana'] == 0.0007
    print("OK  test_conocida_seed_pre_ventana (última tasa pre-ventana siembra conocida, no se cobra)")


def test_guard_shape_funding_matrix():
    """Guard (Fable): una funding_matrix con shape distinto de M se indexaría desalineada en silencio.
    Ahora el engine revienta con ValueError."""
    M = np.ones((10, 3)) * 100.0
    fm_mala = np.zeros((8, 3))
    r = est.ranker_momentum(lookback=1, k=1, gross=1.0)
    try:
        eng.correr(M, r, hpb=1.0, rebal_every=1, warmup=1, funding_matrix=fm_mala)
        raise AssertionError("el engine aceptó una funding_matrix con shape != M.shape")
    except ValueError:
        pass
    print("OK  test_guard_shape_funding_matrix (shape desalineado → ValueError)")


def test_quiebra_por_funding_clampeada():
    """Fix (Fable): una tasa absurda (|w·rate| >= 1, imposible con datos reales pero posible con una
    matriz corrupta) dejaba el equity NEGATIVO durante una barra entera (el clamp de quiebra corría
    recién en la barra siguiente): curva con un punto negativo y rebalanceo con equity sin sentido.
    Ahora la quiebra por funding se clampea en la MISMA barra."""
    M = np.ones((5, 2)) * 100.0

    def ranker_fijo(Mv, t):
        return np.array([0.5, -0.5]) if t == 1 else None

    fm = np.zeros((5, 2))
    fm[2] = [3.0, -1.0]   # w·rate = .5·3 + (−.5)(−1) = 2.0 → equity ×(1−2) < 0
    res = eng.correr(M, ranker_fijo, hpb=1.0, rebal_every=1, warmup=1,
                     aplicar_funding=False, funding_matrix=fm)
    assert res['quebro'] is True
    assert (res['equity'] >= 0).all(), res['equity']
    assert res['equity'][-1] == 0.0
    assert abs(res['pnl_pct'] + 100.0) < TOL
    assert np.isfinite(res['retornos_netos']).all()
    print("OK  test_quiebra_por_funding_clampeada (quiebra por funding en la misma barra, curva >= 0)")


def test_guards_datos_funding():
    """Guards de datos (Fable) — casos que antes pasaban EN SILENCIO como 'funding 0' u optimismo:
    (a) símbolo sin eventos dentro de la ventana (típico mismatch de timestamps/tz) → ValueError;
    (b) evento en ventana cuya hora no tiene barra de precio (pago que se perdería) → ValueError,
        salvo escape hatch explícito permitir_eventos_sin_barra=True;
    (c) tasa NaN → ValueError."""
    times = pd.date_range('2024-01-01 00:00', periods=5, freq='1h')

    # (a) todos los eventos fuera de la ventana
    df_fuera = pd.DataFrame({'time': [pd.Timestamp('2023-01-01 00:00')], 'rate': [0.0001]})
    try:
        matrices_funding({'A': df_fuera}, times, ['A'])
        raise AssertionError("no reventó con cero eventos en ventana")
    except ValueError:
        pass

    # (b) evento en una hora SIN barra (times con hueco en la hora 2)
    times_hueco = times.delete(2)
    df_en_hueco = pd.DataFrame({'time': [times[0], times[2]], 'rate': [0.0001, 0.0005]})
    try:
        matrices_funding({'A': df_en_hueco}, times_hueco, ['A'])
        raise AssertionError("no reventó con un evento sin barra")
    except ValueError:
        pass
    # escape hatch explícito: no revienta, el pago se pierde (documentadamente optimista) y meta lo cuenta
    pagos, conocida, meta = matrices_funding({'A': df_en_hueco}, times_hueco, ['A'],
                                             permitir_eventos_sin_barra=True)
    assert meta['por_simbolo']['A']['eventos_sin_barra'] == 1
    assert abs(pagos.sum() - 0.0001) < TOL   # solo el evento con barra se cobra

    # (c) NaN en rate
    df_nan = pd.DataFrame({'time': [times[0], times[3]], 'rate': [0.0001, np.nan]})
    try:
        matrices_funding({'A': df_nan}, times, ['A'])
        raise AssertionError("no reventó con rate NaN")
    except ValueError:
        pass
    print("OK  test_guards_datos_funding (sin-eventos / evento-sin-barra / NaN → ValueError)")


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
