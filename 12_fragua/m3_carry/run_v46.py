"""V46 — Factor de carry cross-sectional, backtest serio. Ver pre-registro en el libro (2026-07-04).

Parámetros FIJOS pre-registrados (no escaneados, mismos que V44 para comparabilidad): k=2, gross=1.0,
rebal_every=24h. warmup=1 (no hay lookback — el ranking usa la última tasa YA conocida de funding).
Canasta original 3 años 1h, luego OOB con el mismo criterio.

IMPORTANTE (footgun de API, condición de uso de la validación de Fable): al motor va `pagos`
(funding_matrix=pagos); al ranker va `conocida`. Nunca al revés.
"""
import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'm1_cross_sectional')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from common import datos, metricas          # noqa: E402
import engine_xs as eng                     # noqa: E402
from estrategia_carry import ranker_carry   # noqa: E402
from funding_real import cargar_funding, matrices_funding, RUTA_CACHE_ORIGINAL, RUTA_CACHE_OOB  # noqa: E402

K = 2
GROSS = 1.0
REBAL_EVERY = 24
WARMUP = 1
N_NULL = 200
SEED = 42
MIN_OFFSET = 20  # sin lookback propio; reusa el mismo min_offset conservador de V44


def correr_config(cache_ohlcv, cache_funding, tag):
    raw_ohlcv = datos.cargar_cache(cache_ohlcv)
    times, syms, M = datos.alinear(raw_ohlcv, 'close')
    raw_funding = cargar_funding(cache_funding)
    pagos, conocida, meta_f = matrices_funding(raw_funding, times, syms)

    r = ranker_carry(conocida, k=K, gross=GROSS)

    res_on = eng.correr(M, r, hpb=1.0, rebal_every=REBAL_EVERY, warmup=WARMUP, funding_matrix=pagos)
    res_off = eng.correr(M, r, hpb=1.0, rebal_every=REBAL_EVERY, warmup=WARMUP, aplicar_funding=False)

    nulls_on = eng.correr_null_desplazado(M, r, hpb=1.0, rebal_every=REBAL_EVERY, warmup=WARMUP,
                                           n_sims=N_NULL, seed=SEED, funding_matrix=pagos,
                                           min_offset_rebalanceos=MIN_OFFSET)
    pctl_on = eng.percentil_vs_null(res_on['pnl_pct'], nulls_on)

    out = {
        'tag': tag, 'symbols': syms, 'k': K, 'gross': GROSS, 'rebal_every_h': REBAL_EVERY,
        'warmup': WARMUP, 'n_null': N_NULL, 'seed': SEED, 'min_offset_rebalanceos': MIN_OFFSET,
        'meta_funding': meta_f,
        'funding_on': {k: v for k, v in res_on.items() if k not in ('equity', 'retornos_netos', 'turnover', 'gross', 'net_expo')},
        'funding_off': {k: v for k, v in res_off.items() if k not in ('equity', 'retornos_netos', 'turnover', 'gross', 'net_expo')},
        'null_mediana_pct_on': float(np.median(nulls_on)),
        'percentil_vs_null_on': pctl_on,
    }
    print(f"\n=== {tag} ===")
    print(f"  símbolos: {syms}")
    print(f"  FUNDING ON : PnL {res_on['pnl_pct']:.2f}% | CAGR {res_on['cagr_pct']:.2f}% | "
          f"Sharpe {res_on['sharpe']:.2f} | maxDD {res_on['max_dd_pct']:.1f}% | PF {res_on['profit_factor']:.3f} | "
          f"quebro={res_on['quebro']}")
    print(f"  FUNDING OFF: PnL {res_off['pnl_pct']:.2f}% | PF {res_off['profit_factor']:.3f}")
    print(f"  NULL (n={N_NULL}): mediana {out['null_mediana_pct_on']:.2f}%")
    print(f"  PERCENTIL vs null (funding ON): {pctl_on}")
    criterio = (res_on['pnl_pct'] > 0 and res_on['profit_factor'] > 1 and pctl_on is not None and pctl_on >= 70)
    print(f"  CRITERIO (PnL>0 Y PF>1 Y pctl>=70): {'PASA' if criterio else 'NO PASA'}")
    out['pasa_criterio'] = criterio
    return out


if __name__ == '__main__':
    print("### V46 — factor de carry cross-sectional, canasta ORIGINAL ###")
    out_orig = correr_config(datos.CACHE_1H_ORIGINAL, RUTA_CACHE_ORIGINAL, 'v46_original')
    with open('resultado_v46_original.json', 'w') as f:
        json.dump(out_orig, f, indent=2, default=str)

    print("\n### V46 — validación OOB (siempre, para completar el cuadro sin importar si pasa in-sample) ###")
    out_oob = correr_config(datos.CACHE_1H_OOB, RUTA_CACHE_OOB, 'v46_oob')
    with open('resultado_v46_oob.json', 'w') as f:
        json.dump(out_oob, f, indent=2, default=str)
