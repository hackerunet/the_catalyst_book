# M1 — Motor Cross-Sectional (ranking multi-símbolo)

Motor de backtest para estrategias **cross-sectional**: rankea N símbolos por un factor cada rebalanceo,
va LONG el top-k / SHORT el bottom-k (dollar-neutral), y mantiene con drift entre rebalanceos. Habilita
V44 (momentum cross-sectional), V45 (reversión), y sirve de base para V46 (carry como factor).

## Archivos
- `estrategia_xsmom.py` — rankers PUROS (señal): `ranker_momentum`, `ranker_reversion`, `ranker_aleatorio`
  (null naive, ⚠️ sesgado — ver abajo). El único punto que cambia entre estrategia real y azar.
- `engine_xs.py` — el motor: contabilidad de PnL con drift de pesos, costos sobre turnover, funding sobre
  gross, clamp de quiebra, y el test contra el azar: **`correr_null_desplazado` (null JUSTO, usar este
  para E1)** / `correr_null_permutacion` (naive, solo cota gruesa) / `percentil_vs_null`. Un solo
  code-path real+null.
- `selftest_m1.py` — 16 tests con respuestas ANALÍTICAS conocidas (9 del constructor + 7 de la validación
  Fable). **Todos pasan** (verificado 2026-07-04).
- `REGISTRO.md` — bitácora: diseño, self-tests, y (lo llena Fable) errores + arreglos + veredicto.
- `../common/` — `costos.py` (espejo de constantes del motor vivo), `datos.py` (carga read-only),
  `metricas.py` (equity → CAGR/Sharpe/maxDD/PF/correlación).

## Decisiones de diseño (para que Fable las audite)
1. **Anti-lookahead**: los pesos en `t` se fijan con `M[:t+1]` y ganan el retorno de `t→t+1`. El ranker
   nunca lee `M[t+1:]`. (Test `test_anti_lookahead`.)
2. **Drift de pesos = mantener nocionales fijos** entre rebalanceos. El PnL de cartera por barra =
   `w · ret`, y los pesos-fracción se re-normalizan por `(1+ret)/(1+port_ret)`. Verificado igual a un
   buy&hold long/short de nocional fijo (Test `test_pnl_hold_sin_rebalanceo` → 1.20 exacto).
3. **Turnover** = `sum|target − w_driftado|`; costo = turnover × (taker+slippage) = turnover × 0.001.
   Cobrado solo en rebalanceos. (Test `test_costo_entrada_exacto` → 1.1988 exacto.)
4. **Funding**: PESIMISTA — drag sobre el gross bruto (`FUNDING_8H` por 8h). Documentado en `costos.py`
   como límite conservador; el funding neto real de un libro neutral requiere datos per-símbolo (y ES la
   señal de V46). Punto explícito de honestidad a evaluar (ítem B3).
5. **Null** — CORREGIDO EN LA VALIDACIÓN (2026-07-04): el null por permutación aleatoria NO mantiene el
   turnover de una señal persistente (medido en el cache real: azar 1.35 vs momentum 0.56 por rebalanceo,
   2.4x) → pagaba 2.4x los costos → percentil INFLADO (una config que pierde −53% daba percentil 100).
   El null para E1 es ahora **`correr_null_desplazado`**: rotación temporal circular de la señal real —
   mantiene cadencia Y turnover (medido: real 0.560, desplazado ≈0.56, permutación 1.347) y además
   controla el sesgo estático de símbolo. Con el null justo, la misma config da percentil 77.5.
   (Tests `test_null_desplazado_turnover_justo`, `test_null_determinista`.)
6. **Dollar-neutral**: `sum(pesos)=0`, `gross=sum|pesos|`, guard central `2k<=S` en TODOS los rankers.
   (Tests `test_dollar_neutral_siempre`, `test_guard_neutralidad_todos_los_rankers`.)
7. **Quiebra** (agregado en la validación): `port_ret <= −1` (short que pierde >100% del equity en una
   barra) → equity clampeada en 0, libro cerrado, flag `quebro=True`. (Test `test_quiebra_clamp`.)
8. **Anti-lookahead estructural** (agregado en la validación): el engine pasa `M[:t+1]` al ranker — leer
   el futuro es imposible por construcción. (Test `test_engine_no_pasa_futuro`.)

## Qué NECESITA validar Fable (antes de cualquier backtest serio)
Recorrer `../HONESTIDAD.md` ítem por ítem contra este motor. Puntos de atención especial:
- **B3 funding**: ¿el drag pesimista sobre gross es aceptable como piso, o el resultado depende tanto del
  funding que hay que modelarlo per-símbolo ya? (Para momentum puede ser secundario; para V46 es central.)
- **D1/D2**: ¿la contabilidad del drift es correcta en TODOS los casos (incluye el signo de los shorts)?
  Los tests cubren el caso simétrico ±10%; conviene un caso asimétrico a mano.
- **A2**: confirmar que el retorno de la barra `t` lo ganan los pesos de `t−1` y no los recién fijados en `t`
  (el orden de las operaciones en el loop de `correr`).
- **E1**: ¿el null aleatorio es un null JUSTO? (mismo turnover esperado, misma cadencia). ¿O el azar tiene
  sistemáticamente más/menos turnover que la señal real, sesgando el percentil?
- **Métrica de turnover/net_expo**: `net_expo_medio_abs` mezcla barras post-rebalanceo (0) y driftadas
  (≠0) — verificar que se interpreta bien y no esconde una fuga de neutralidad.

## Estado
✅ **VALIDADO por Fable (2026-07-04)** — auditoría completa contra `../HONESTIDAD.md`, 4 bugs encontrados
y arreglados (null injusto E1, guard de neutralidad, quiebra, duplicados en alinear), anti-lookahead
endurecido a estructural, 16/16 self-tests, no-regresión exacta del path real. Detalle completo en
`REGISTRO.md`. **Regla para los backtests serios: el percentil E1 se calcula con `correr_null_desplazado`
(min_offset ≈ lookback/rebal_every), y se reporta PnL con funding ON y OFF** (el funding pesimista sobre
gross cuesta ~28% relativo en 3 años; si un candidato muere SOLO por funding, modelar per-símbolo antes
de rechazarlo).
