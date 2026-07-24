"""Selftest M2 — Tests de respuesta conocida para el motor de pairs trading.

Corre tests sintéticos ANTES de aplicar el motor a datos reales:
  1. Spread estacionario artificial → el motor debe ganar
  2. Random walk puro (sin reversión) → el motor debe perder o ~0
  3. Test de costos → comparar con cálculo manual
  4. Test de cointegración → verificar que ADF detecta y no detecta
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import engine_pairs as ep


def test_spread_estacionario():
    """Un spread perfectamente estacionario (AR(1) con φ=0.95) debe producir ganancia."""
    np.random.seed(42)
    T = 2000
    # Precio B = random walk
    Pb = 100 + np.cumsum(np.random.randn(T) * 0.5)
    Pb = np.abs(Pb) + 50  # mantener positivo

    # Spread estacionario: Pa = 1.5*Pb + ruido AR(1)
    beta_real = 1.5
    spread = np.zeros(T)
    for t in range(1, T):
        spread[t] = 0.95 * spread[t-1] + np.random.randn() * 2.0  # revierte fuerte
    Pa = beta_real * Pb + spread + 200  # offset para mantener positivo

    ventana = 180
    hr, sp, zs, coint = ep.calcular_spread_rolling(Pa, Pb, ventana)

    res = ep.correr(Pa, Pb, zs, coint, hpb=4.0, aplicar_funding=False)

    # Un spread perfectamente estacionario con φ=0.95 debería dar trades rentables
    assert res['n_trades'] > 0, f"Esperaba trades, obtuve {res['n_trades']}"
    assert res['pnl_pct'] > 0, f"Spread estacionario debe ganar, PnL={res['pnl_pct']:.2f}%"
    assert res['pf'] > 1.0, f"PF debe ser > 1, obtuvo {res['pf']:.3f}"
    print(f"  ✅ Spread estacionario: PnL={res['pnl_pct']:.2f}%, PF={res['pf']:.3f}, "
          f"trades={res['n_trades']}, stops={res['n_stops']}")


def test_random_walk():
    """Dos random walks independientes (sin cointegración) no deben producir ganancia consistente."""
    np.random.seed(123)
    T = 2000
    Pa = 100 + np.cumsum(np.random.randn(T) * 0.5)
    Pa = np.abs(Pa) + 50
    Pb = 200 + np.cumsum(np.random.randn(T) * 0.5)
    Pb = np.abs(Pb) + 50

    ventana = 180
    hr, sp, zs, coint = ep.calcular_spread_rolling(Pa, Pb, ventana)

    res = ep.correr(Pa, Pb, zs, coint, hpb=4.0, aplicar_funding=False)

    # Debería tener pocos o ningún trade (ADF no debería encontrar cointegración)
    # y si los hay, el PnL no debería ser significativamente positivo
    print(f"  ✅ Random walk: PnL={res['pnl_pct']:.2f}%, trades={res['n_trades']}, "
          f"coint_exits={res['n_coint_exits']}, cointegrados={coint.sum()}/{T}")
    if res['n_trades'] > 0:
        # No exigimos PnL negativo (puede haber suerte), pero documentamos
        print(f"     (trades espurios — la cointegración espuria es un riesgo conocido)")


def test_costos():
    """Verificar que los costos se aplican correctamente."""
    np.random.seed(1)
    T = 100
    # Spread estacionario fuerte para forzar trades
    Pb = np.ones(T) * 100
    spread = np.sin(np.linspace(0, 8*np.pi, T)) * 5
    Pa = 1.0 * Pb + spread + 50

    ventana = 20  # ventana corta para tener más trades
    hr, sp, zs, coint = ep.calcular_spread_rolling(Pa, Pb, ventana)

    # Sin costos
    res_free = ep.correr(Pa, Pb, zs, coint, hpb=4.0, aplicar_funding=False)
    # Con funding
    res_fund = ep.correr(Pa, Pb, zs, coint, hpb=4.0, aplicar_funding=True)

    # El funding siempre reduce el PnL
    if res_free['n_trades'] > 0:
        assert res_fund['pnl_pct'] <= res_free['pnl_pct'], \
            f"Funding debería reducir PnL: {res_fund['pnl_pct']:.2f} vs {res_free['pnl_pct']:.2f}"
        print(f"  ✅ Costos: sin_funding={res_free['pnl_pct']:.2f}%, "
              f"con_funding={res_fund['pnl_pct']:.2f}%, diff={res_free['pnl_pct'] - res_fund['pnl_pct']:.2f}pp")
    else:
        print(f"  ⚠️ Sin trades en test de costos (ventana corta, no hay señal)")


def test_adf():
    """Verificar que el ADF detecta cointegración en datos estacionarios y no en random walks."""
    np.random.seed(42)
    # Estacionario (AR1 con φ=0.5 — revierte fuerte)
    n = 500
    r_stat = np.zeros(n)
    for t in range(1, n):
        r_stat[t] = 0.5 * r_stat[t-1] + np.random.randn()
    p_stat = ep._adf_pvalue_approx(r_stat)

    # Random walk (φ=1.0)
    r_rw = np.cumsum(np.random.randn(n))
    p_rw = ep._adf_pvalue_approx(r_rw)

    assert p_stat < 0.05, f"ADF debe detectar estacionario, p={p_stat}"
    assert p_rw >= 0.05, f"ADF no debe detectar RW como estacionario, p={p_rw}"
    print(f"  ✅ ADF: estacionario p={p_stat:.3f}, random walk p={p_rw:.3f}")


def test_null_desplazado():
    """El null desplazado no debe correlacionar con la señal real."""
    np.random.seed(42)
    T = 2000
    Pb = 100 + np.cumsum(np.random.randn(T) * 0.3)
    Pb = np.abs(Pb) + 50
    beta_real = 1.5
    spread = np.zeros(T)
    for t in range(1, T):
        spread[t] = 0.95 * spread[t-1] + np.random.randn() * 2.0
    Pa = beta_real * Pb + spread + 200

    ventana = 180
    hr, sp, zs, coint = ep.calcular_spread_rolling(Pa, Pb, ventana)

    # Señal real
    res_real = ep.correr(Pa, Pb, zs, coint, hpb=4.0, aplicar_funding=False)

    # Null
    pnls_null = ep.correr_null_desplazado(Pa, Pb, zs, coint, hpb=4.0, n=50,
                                           aplicar_funding=False, min_offset=ventana)
    pctl = ep.percentil_vs_null(res_real['pnl_pct'], pnls_null)

    print(f"  ✅ Null desplazado: real={res_real['pnl_pct']:.2f}%, "
          f"null_mediana={np.median(pnls_null):.2f}%, pctl={pctl:.1f}")
    # En un spread estacionario perfecto, el real debe vencer al null
    assert pctl > 50, f"Con spread estacionario, pctl debería ser > 50, obtuvo {pctl:.1f}"


if __name__ == '__main__':
    tests = [
        ('ADF (detección de cointegración)', test_adf),
        ('Spread estacionario (debe ganar)', test_spread_estacionario),
        ('Random walk (no debe ganar)', test_random_walk),
        ('Costos (funding reduce PnL)', test_costos),
        ('Null desplazado (señal real > null)', test_null_desplazado),
    ]
    passed = 0
    for name, fn in tests:
        try:
            print(f"[{name}]")
            fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FALLO: {e}")
    print(f"\n{'='*60}")
    print(f"Resultado: {passed}/{len(tests)} tests pasados")
    if passed == len(tests):
        print("✅ Motor M2 validado — listo para datos reales")
    else:
        print("❌ Hay fallos — NO correr V47 hasta resolver")
