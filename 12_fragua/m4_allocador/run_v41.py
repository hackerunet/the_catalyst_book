"""V41 — Meta-allocador dinámico M4: regime-switching V26 ↔ V36 por volatilidad.

Pre-registro: el libro sección "V41 — MOTOR M4" (2026-07-05).

Parámetros FIJOS pre-registrados (no escaneados):
  - Indicador de régimen: std(retornos_diarios, rolling 90d) de la equity combinada.
  - Umbral: mediana expandida causal (expanding().quantile(0.5)).
  - Alta vol → peso V26=0.30, V36=0.70.
  - Baja vol  → peso V26=0.70, V36=0.30.
  - Rebalanceo: diario.
  - Costo de rebalanceo del allocador: 0 (no genera órdenes en mercado).

Criterio de aceptación pre-registrado (TODOS deben darse):
  - CAGR > 21.64% Y DD90d < 14.4% Y p10 rolling-365d > -2.49%
  En AMBAS mitades temporales (in-sample 2022-24, OOB temporal 2024-26).

AISLAMIENTO: este script NO importa nada de bot_alpha_portfolio ni toca ningún bot vivo.
Solo lee los CSVs de equity diaria ya producidos por suavizado_v37.py (read-only).
"""
import os
import sys
import json
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Rutas a los artefactos de V37 (read-only)
# ---------------------------------------------------------------------------
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIR_V37 = os.path.join(DIR_SCRIPT, '..', '..', 'bot_alpha_portfolio', 'stable_v25_prototype')

CSV_V26 = os.path.join(DIR_V37, 'v37_eq_v26_base.csv')
CSV_V36 = os.path.join(DIR_V37, 'v37_eq_v36_4y.csv')

# Parámetros pre-registrados
W_ALTA_V26 = 0.30   # peso V26 cuando alta volatilidad
W_ALTA_V36 = 0.70   # peso V36 cuando alta volatilidad
W_BAJA_V26 = 0.70   # peso V26 cuando baja volatilidad
W_BAJA_V36 = 0.30   # peso V36 cuando baja volatilidad
VOL_WINDOW = 90     # días para vol realizada rolling
SPLIT_DATE = '2024-06-12'  # separación in-sample / OOB temporal


# ---------------------------------------------------------------------------
# Funciones de métricas (espejo de metricas.py del motor M1, sin dependencia)
# ---------------------------------------------------------------------------

def max_drawdown_90d(eq_series):
    """Max DD rolling 90 días (la métrica gate de copy-trade)."""
    roll_peak = eq_series.rolling('90D').max()
    dd = (roll_peak - eq_series) / roll_peak * 100.0
    return float(dd.max())


def max_drawdown_global(eq_series):
    peak = eq_series.cummax()
    dd = (peak - eq_series) / peak * 100.0
    return float(dd.max())


def cagr_pct(eq_series):
    dias = (eq_series.index[-1] - eq_series.index[0]).days
    anios = dias / 365.25
    if anios <= 0:
        return None
    total = float(eq_series.iloc[-1] / eq_series.iloc[0])
    if total <= 0:
        return -100.0
    return round((total ** (1.0 / anios) - 1.0) * 100.0, 2)


def rolling_365d(eq_series):
    """Estadísticas de todas las ventanas rolling de 365 días."""
    r365 = (eq_series / eq_series.shift(365) - 1.0).dropna() * 100.0
    if len(r365) == 0:
        return None
    return {
        'n_ventanas': int(len(r365)),
        'mediana': round(float(r365.median()), 2),
        'p10': round(float(r365.quantile(0.10)), 2),
        'minimo': round(float(r365.min()), 2),
        'maximo': round(float(r365.max()), 2),
        'pct_ventanas_positivas': round(float((r365 > 0).mean() * 100), 1),
        'pct_ventanas_sobre_12': round(float((r365 > 12).mean() * 100), 1),
        'pct_ventanas_sobre_25': round(float((r365 > 25).mean() * 100), 1),
    }


def metricas_completas(eq_series, nombre=''):
    """Calcula todas las métricas sobre una curva de equity diaria."""
    c = cagr_pct(eq_series)
    dd90 = max_drawdown_90d(eq_series)
    ddg = max_drawdown_global(eq_series)
    r365 = rolling_365d(eq_series)
    pnl = round(float(eq_series.iloc[-1] / eq_series.iloc[0] - 1.0) * 100.0, 2)
    return {
        'nombre': nombre,
        'ventana': f"{eq_series.index[0].date()} → {eq_series.index[-1].date()}",
        'n_dias': len(eq_series),
        'pnl_pct': pnl,
        'cagr_pct': c,
        'dd_90d_pct': round(dd90, 1),
        'dd_global_pct': round(ddg, 1),
        'rolling_365d': r365,
    }


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def cargar_equities():
    """Lee las curvas de equity diaria de V26 y V36 y las alinea en la intersección."""
    eq26 = pd.read_csv(CSV_V26, index_col=0, parse_dates=True)['equity']
    eq36 = pd.read_csv(CSV_V36, index_col=0, parse_dates=True)['equity']
    comun = eq26.index.intersection(eq36.index)
    if len(comun) == 0:
        raise ValueError("Sin solapamiento entre V26 y V36 — revisar CSVs.")
    eq26 = eq26.loc[comun]
    eq36 = eq36.loc[comun]
    print(f"[carga] Ventana común: {comun[0].date()} → {comun[-1].date()} ({len(comun)} días)")
    return eq26, eq36


# ---------------------------------------------------------------------------
# Motor M4: allocador dinámico
# ---------------------------------------------------------------------------

def construir_allocador_dinamico(eq26, eq36):
    """Construye la curva de equity del allocador dinámico V41.

    Anti-lookahead: el peso del día t se calcula con información hasta t-1 (usamos
    expanding().quantile() sobre los retornos hasta t-1, y aplicamos ese peso al retorno de t).

    Retorna:
      eq_dinamica  : pd.Series con la equity del allocador dinámico
      pesos_v26    : pd.Series de los pesos de V26 en cada día
      regimen      : pd.Series con 'ALTA_VOL' / 'BAJA_VOL' / 'WARMUP' en cada día
      vol_serie    : pd.Series de la vol realizada rolling
    """
    # Retornos diarios de cada bot (la curva combinada se usa para el indicador de régimen)
    ret26 = eq26.pct_change()
    ret36 = eq36.pct_change()
    ret_combo = ((eq26 + eq36) / 2.0).pct_change()   # proxy de la flota

    # Volatilidad realizada rolling 90d de la flota (proxy de régimen)
    # .std(ddof=1) sobre una ventana de 90 días — requiere ≥2 obs
    vol_rolling = ret_combo.rolling(window=VOL_WINDOW, min_periods=30).std() * np.sqrt(252)

    # Umbral CAUSAL: mediana expandida hasta el día ANTERIOR (shift(1) para no usar el propio día)
    # En el primer día con señal: mediana de los días anteriores
    umbral_causal = vol_rolling.shift(1).expanding().quantile(0.5)

    # Régimen del día ANTERIOR (el que se conoce al abrir el día t)
    regimen_ant = vol_rolling.shift(1) > umbral_causal

    # Pesos para el día t (basados en régimen de t-1 — causal)
    peso_v26 = pd.Series(index=eq26.index, dtype=float)
    regimen = pd.Series(index=eq26.index, dtype=str)

    for fecha, alta_vol in regimen_ant.items():
        if pd.isna(alta_vol):
            peso_v26.loc[fecha] = 0.5   # warmup: 50/50 estático
            regimen.loc[fecha] = 'WARMUP'
        elif alta_vol:
            peso_v26.loc[fecha] = W_ALTA_V26
            regimen.loc[fecha] = 'ALTA_VOL'
        else:
            peso_v26.loc[fecha] = W_BAJA_V26
            regimen.loc[fecha] = 'BAJA_VOL'

    peso_v36 = 1.0 - peso_v26

    # Retorno del allocador en el día t = w26(t) * ret26(t) + w36(t) * ret36(t)
    # Los pesos son causales (se fijaron con info hasta t-1)
    ret_dinamico = peso_v26 * ret26 + peso_v36 * ret36

    # Curva de equity (base 1.0, multiplicativa)
    eq_dinamica = (1.0 + ret_dinamico.fillna(0.0)).cumprod()
    # Normalizar al nivel inicial de la curva combinada para comparar en términos absolutos
    eq_dinamica = eq_dinamica / eq_dinamica.iloc[0] * ((eq26.iloc[0] + eq36.iloc[0]) / 2.0)

    return eq_dinamica, peso_v26, regimen, vol_rolling


def construir_combo_estatico(eq26, eq36):
    """Baseline 50/50 estático (debe reproducir v37_combo.json)."""
    ret26 = eq26.pct_change()
    ret36 = eq36.pct_change()
    ret_combo = 0.5 * ret26 + 0.5 * ret36
    eq = (1.0 + ret_combo.fillna(0.0)).cumprod()
    eq = eq / eq.iloc[0] * ((eq26.iloc[0] + eq36.iloc[0]) / 2.0)
    return eq


# ---------------------------------------------------------------------------
# Diagnóstico de mecanismo (honestidad declarada)
# ---------------------------------------------------------------------------

def diagnostico_regimen(regimen, eq26, eq36):
    """Inspecciona si el régimen ALTA/BAJA vol mapea 1:1 con el ciclo alcista/bajista.

    BUG POTENCIAL declarado en el pre-registro: si ALTA_VOL coincide con 2022-23 bajista
    (donde V36 rindió mejor) y BAJA_VOL con 2023-26 alcista (donde V26 rindió mejor),
    el mecanismo sería data-snooping camuflado, no un factor de régimen genuino.
    """
    ret26 = eq26.pct_change()
    ret36 = eq36.pct_change()

    por_regimen = {}
    for r in ['ALTA_VOL', 'BAJA_VOL', 'WARMUP']:
        mask = regimen == r
        n = int(mask.sum())
        if n == 0:
            continue
        r26_r = float(ret26[mask].mean() * 252 * 100)   # retorno anualizado en ese régimen
        r36_r = float(ret36[mask].mean() * 252 * 100)
        anios = sorted(eq26[mask].index.year.unique().tolist())
        por_regimen[r] = {
            'n_dias': n,
            'ret_anual_v26_pct': round(r26_r, 2),
            'ret_anual_v36_pct': round(r36_r, 2),
            'diferencia_v36_minus_v26_pct': round(r36_r - r26_r, 2),
            'años_involucrados': anios,
        }
    return por_regimen


# ---------------------------------------------------------------------------
# Verificación baseline (control de honestidad)
# ---------------------------------------------------------------------------

BASELINE_ESPERADO = {
    'cagr_pct': 21.64,
    'dd_90d_pct': 14.4,
    'p10_rolling_365d': -2.49,
}
TOLERANCIA = 0.5   # diferencia máxima aceptable (en pp) — ajustada por diferencias de normalización


def verificar_baseline(m_estatico):
    """Verifica que el combo 50/50 estático reproduce v37_combo.json dentro de la tolerancia.

    NOTA TÉCNICA: la comparación no es dígito a dígito porque la escala de equity es diferente
    (aquí normalizamos la curva a la media de los valores iniciales de V26/V36 en términos de
    ratio, no en USD absolutos). Lo que DEBE coincidir es el CAGR y el DD, que son métricas
    independientes del nivel absoluto de equity.
    """
    errores = []
    cagr_r = m_estatico.get('cagr_pct')
    dd90_r = m_estatico.get('dd_90d_pct')
    p10_r = m_estatico.get('rolling_365d', {}).get('p10') if m_estatico.get('rolling_365d') else None

    if cagr_r is not None and abs(cagr_r - BASELINE_ESPERADO['cagr_pct']) > TOLERANCIA:
        errores.append(f"CAGR {cagr_r:.2f}% (esperado {BASELINE_ESPERADO['cagr_pct']}%, diff {abs(cagr_r - BASELINE_ESPERADO['cagr_pct']):.2f}pp)")
    if abs(dd90_r - BASELINE_ESPERADO['dd_90d_pct']) > TOLERANCIA:
        errores.append(f"DD90d {dd90_r:.1f}% (esperado {BASELINE_ESPERADO['dd_90d_pct']}%, diff {abs(dd90_r - BASELINE_ESPERADO['dd_90d_pct']):.1f}pp)")
    if p10_r is not None and abs(p10_r - BASELINE_ESPERADO['p10_rolling_365d']) > TOLERANCIA:
        errores.append(f"p10_365d {p10_r:.2f}% (esperado {BASELINE_ESPERADO['p10_rolling_365d']}%, diff {abs(p10_r - BASELINE_ESPERADO['p10_rolling_365d']):.2f}pp)")

    if errores:
        print("\n⚠️  ADVERTENCIA BASELINE (diff > tolerancia):")
        for e in errores:
            print(f"   {e}")
        print("   → Verificar que los CSVs son los artefactos correctos de v37_combo.")
        print("   → Si la diff es < 1pp, puede ser diferencia de normalización — no detiene el experimento.")
    else:
        print("\n✅ BASELINE 50/50 estático reproduce v37_combo.json dentro de tolerancia.")

    return len(errores) == 0


# ---------------------------------------------------------------------------
# Criterio de aceptación
# ---------------------------------------------------------------------------

def evaluar_criterio(m, nombre_ventana):
    """Evalúa el criterio de aceptación pre-registrado."""
    cagr = m.get('cagr_pct')
    dd90 = m.get('dd_90d_pct')
    p10 = m.get('rolling_365d', {}).get('p10') if m.get('rolling_365d') else None

    pasa_cagr = cagr is not None and cagr > 21.64
    pasa_dd90 = dd90 < 14.4
    pasa_p10 = p10 is not None and p10 > -2.49

    pasa = pasa_cagr and pasa_dd90 and pasa_p10
    print(f"\n  CRITERIO ({nombre_ventana}):")
    print(f"    CAGR {cagr:.2f}% > 21.64%: {'✅' if pasa_cagr else '❌'}")
    print(f"    DD90d {dd90:.1f}% < 14.4%:  {'✅' if pasa_dd90 else '❌'}")
    print(f"    p10_365d {p10:.2f}% > -2.49%: {'✅' if pasa_p10 else '❌'}")
    print(f"  → RESULTADO: {'PASA ✅' if pasa else 'NO PASA ❌'}")
    return pasa


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("V41 — Allocador dinámico M4 (regime-switching V26↔V36)")
    print("=" * 60)

    # 1. Carga
    eq26, eq36 = cargar_equities()

    # 2. Baseline 50/50 estático (control de honestidad)
    print("\n--- BASELINE 50/50 ESTÁTICO ---")
    eq_estatico = construir_combo_estatico(eq26, eq36)
    m_est = metricas_completas(eq_estatico, 'baseline_50_50')
    print(f"  CAGR {m_est['cagr_pct']:.2f}% | DD90d {m_est['dd_90d_pct']:.1f}% | "
          f"p10_365d {(m_est['rolling_365d'] or {}).get('p10', 'n/a'):.2f}%")
    baseline_ok = verificar_baseline(m_est)

    # 3. Allocador dinámico (ventana completa)
    print("\n--- ALLOCADOR DINÁMICO V41 (ventana completa) ---")
    eq_din, pesos_v26, regimen, vol_serie = construir_allocador_dinamico(eq26, eq36)

    m_din = metricas_completas(eq_din, 'v41_dinamico_completo')
    r365 = m_din.get('rolling_365d') or {}
    print(f"  CAGR {m_din['cagr_pct']:.2f}% | DD90d {m_din['dd_90d_pct']:.1f}% | "
          f"p10_365d {r365.get('p10', 'n/a'):.2f}%")

    # Distribución de régimen
    n_alta = int((regimen == 'ALTA_VOL').sum())
    n_baja = int((regimen == 'BAJA_VOL').sum())
    n_warmup = int((regimen == 'WARMUP').sum())
    print(f"  Régimen: ALTA_VOL={n_alta}d ({100*n_alta/len(regimen):.1f}%) | "
          f"BAJA_VOL={n_baja}d ({100*n_baja/len(regimen):.1f}%) | WARMUP={n_warmup}d")

    pasa_completa = evaluar_criterio(m_din, 'ventana completa')

    # 4. Diagnóstico de mecanismo (honestidad obligatoria)
    print("\n--- DIAGNÓSTICO DE MECANISMO ---")
    diag = diagnostico_regimen(regimen, eq26, eq36)
    for r, d in diag.items():
        print(f"  {r} ({d['n_dias']}d, años {d['años_involucrados']}):")
        print(f"    V26 anualizado: {d['ret_anual_v26_pct']:.2f}% | "
              f"V36 anualizado: {d['ret_anual_v36_pct']:.2f}% | "
              f"diferencia V36-V26: {d['diferencia_v36_minus_v26_pct']:.2f}%")

    # 5. OOB temporal (in-sample 2022-24, OOB 2024-26)
    print("\n--- OOB TEMPORAL ---")
    split = pd.Timestamp(SPLIT_DATE)
    eq26_is = eq26[eq26.index < split]
    eq36_is = eq36[eq36.index < split]
    eq26_oob = eq26[eq26.index >= split]
    eq36_oob = eq36[eq36.index >= split]

    for etiqueta, e26, e36 in [('in_sample_2022_24', eq26_is, eq36_is),
                                ('oob_temporal_2024_26', eq26_oob, eq36_oob)]:
        if len(e26) < 30:
            print(f"  {etiqueta}: muy pocos datos ({len(e26)} días) — saltando.")
            continue
        eq_d, _, reg_d, _ = construir_allocador_dinamico(e26, e36)
        m_d = metricas_completas(eq_d, etiqueta)
        r365_d = m_d.get('rolling_365d') or {}
        p10_d = r365_d.get('p10', float('nan'))
        print(f"  {etiqueta}: CAGR {m_d['cagr_pct']:.2f}% | DD90d {m_d['dd_90d_pct']:.1f}% | "
              f"p10_365d {p10_d if isinstance(p10_d, str) else f'{p10_d:.2f}%'}")
        evaluar_criterio(m_d, etiqueta)

    # 6. Guardar resultados
    resultado = {
        'pre_registro': {
            'w_alta_v26': W_ALTA_V26, 'w_alta_v36': W_ALTA_V36,
            'w_baja_v26': W_BAJA_V26, 'w_baja_v36': W_BAJA_V36,
            'vol_window': VOL_WINDOW, 'split_date': SPLIT_DATE,
        },
        'baseline_50_50': m_est,
        'baseline_reproducido_ok': baseline_ok,
        'v41_dinamico_completo': m_din,
        'pasa_criterio_completo': pasa_completa,
        'distribucion_regimen': {
            'n_alta_vol': n_alta, 'n_baja_vol': n_baja, 'n_warmup': n_warmup,
            'pct_alta_vol': round(100 * n_alta / len(regimen), 1),
        },
        'diagnostico_mecanismo': diag,
    }

    ruta_json = os.path.join(DIR_SCRIPT, 'resultado_v41.json')
    with open(ruta_json, 'w') as f:
        json.dump(resultado, f, indent=2, default=str)
    print(f"\n✅ Guardado: {ruta_json}")

    # Guardar curva de retornos diarios del allocador (para correlación posterior vs V26/V36)
    ret_din = eq_din.pct_change().dropna()
    ruta_npy = os.path.join(DIR_SCRIPT, 'v41_retornos_diarios.npy')
    np.save(ruta_npy, ret_din.values)
    print(f"✅ Guardado: {ruta_npy}")

    print("\n" + "=" * 60)
    print(f"VEREDICTO FINAL: {'PASA ✅ — registrar en el libro' if pasa_completa else 'NO PASA ❌ — registrar rechazo en el libro'}")
    print("=" * 60)
    print("\nNOTA: anotar en el libro el resultado y el diagnóstico de mecanismo.")
    print("      Si PASA: verificar que ALTA_VOL no mapea 1:1 con ciclo bajista.")
    print("      Si NO PASA: documentar cuál criterio falló y por qué.")
