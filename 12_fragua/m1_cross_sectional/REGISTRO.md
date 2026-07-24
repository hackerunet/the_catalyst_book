# REGISTRO — M1 Cross-Sectional

Bitácora incremental. Los errores NO se borran — quedan documentados como parte del historial (igual que
el libro).

---

## 2026-07-04 — Construcción inicial (Constructor: Opus)

**Qué se construyó**: motor cross-sectional dollar-neutral (long top-k / short bottom-k), con rankers puros
(momentum / reversión / aleatorio-null), contabilidad de PnL con drift de pesos, costos sobre turnover,
funding pesimista sobre gross, y test contra el azar con percentil.

**Self-tests (respuestas analíticas calculadas a mano)** — `selftest_m1.py`, **9/9 OK**:
| Test | Verifica | Resultado esperado |
|---|---|---|
| `test_momentum_elige_bien` | ranking correcto + neutralidad | long mejor, short peor, sum=0, gross=1 |
| `test_pnl_rebalanceo_cada_barra` | PnL, rebal cada barra, sin costos | equity == **1.10** exacto |
| `test_pnl_hold_sin_rebalanceo` | PnL, hold, = buy&hold long/short | equity == **1.20** exacto |
| `test_costo_entrada_exacto` | contabilidad de costo de turnover | equity == **1.1988** exacto |
| `test_dollar_neutral_siempre` | neutralidad post-rebalanceo | net_expo ~ 0 |
| `test_anti_lookahead` | causalidad de la señal | peso en t inmune a t+1 |
| `test_null_determinista` | reproducibilidad del null | mismo seed → misma dist. |
| `test_funding_reduce_equity` | funding es costo, no regalo | ON <= OFF |
| `test_percentil_null` | cálculo del percentil | 100 / 0 / 60 correctos |

**Smoke test sobre datos reales** (NO es resultado, solo integración): carga el cache 1h de 3 años
(26280×6, sin NaN), alinea, corre una config naive (momentum 7d, k=1, rebal diario) sin crashear; equity
finita, sin NaN. El PnL de esa config naive es malo (−68%) — irrelevante, es solo prueba de mecánica.

**Puntos de honestidad declarados abiertos para Fable**:
1. Funding pesimista sobre gross (ítem B3) — ¿aceptable como piso o hay que modelar per-símbolo ya?
2. Justicia del null (ítem E1) — ¿el azar tiene el mismo perfil de turnover que la señal real?
3. Caso asimétrico del drift (D1) — los tests cubren ±10% simétrico; falta un caso a mano asimétrico.

**Estado**: 🔨 esperando validación de Fable. Sin backtests serios aún.

---

## (Fable escribe debajo de esta línea)

### Validación Fable — 2026-07-04

**Método**: auditoría de lectura línea por línea de los 6 archivos + verificación A MANO de los 3 tests
analíticos + micro-experimentos de medición (cache real 26280×6, read-only) ANTES de tocar nada, para
tener baseline pre-fix. Después: fixes, tests nuevos que capturan cada bug, y control de no-regresión
(el path real reproduce el baseline pre-fix EXACTO, 11 decimales).

#### Verificación de los 3 tests analíticos (a mano, independiente del código)
- **1.10**: t=1 entra flat→[+.5,−.5] (PnL 0); t=2 port_ret = .5·.10 + (−.5)(−.10) = .10 → 1.10 ✓
- **1.20**: drift tras t=2: w=[.5, −.40909]; t=3: .5·.1 + .40909·.1 = .090909 → 1.10·1.090909 = 1.20
  exacto = buy&hold de nocional fijo (.105+.095) ✓
- **1.1988**: turnover de entrada = gross = 1.0 → costo 0.001 → 0.999·1.20 ✓
- Además, los tests 1.10/1.20 SÍ pinnean el orden del loop: si el rebalanceo ocurriera ANTES del PnL
  (lookahead clásico), 1.10 daría 1.21 y fallaría. No son tests decorativos.

#### ERRORES ENCONTRADOS (4) — todos arreglados, cada uno con test que lo captura

**ERROR 1 (el central) — E1: null por permutación INJUSTO, percentil inflado (sesgo OPTIMISTA).**
- Dónde: `estrategia_xsmom.ranker_aleatorio` + `engine_xs.correr_null` (diseño, no un typo).
- Qué estaba mal: una permutación fresca por rebalanceo NO mantiene el turnover de una señal
  persistente. **Medido en el cache real** (momentum 7d, k=2, rebal 24h, 1088 rebalanceos):
  turnover real **0.560**/rebal vs null **1.347**/rebal (≈ el teórico 4/3 para k=2,S=6) = **2.4x**.
  El null pagaba 2.4x los costos (≈0.135%/rebal × 1088 ≈ −77% solo de costos) → mediana null −87% →
  **una config que PIERDE −53.26% salía percentil 100.0**. Cualquier backtest serio habría producido
  un espejismo de "señal" que era pura asimetría de costos.
- Arreglo: **`engine_xs.correr_null_desplazado`** — null por rotación temporal circular de la señal
  REAL: precomputa los libros objetivo reales (causalmente, con `M[:t+1]`) y cada sim aplica la misma
  secuencia rotada `off` rebalanceos (off aleatorio determinista, `min_offset` excluye la identidad y
  los solapes; recomendado ≈ lookback/rebal_every). Mantiene cadencia, turnover y costos; destruye la
  alineación señal↔retorno; de yapa controla el sesgo estático de símbolo (más estricto). El null viejo
  quedó como `correr_null_permutacion` con advertencia grande (cota gruesa, NO apto para E1).
- Verificación (cache real, misma config): turnover desplazado ≈ real; percentil real pasa de
  **100.0 (viejo) → 77.5 (justo)**, mediana null −62.89% vs −86.05%. En sintético persistente:
  real=0.302, desplazado=0.305, permutación=1.341. Test: `test_null_desplazado_turnover_justo`.
- Nota de honestidad declarada: el null rotado NO es causal (usa la señal de otro momento vía el wrap
  circular) — es un control estadístico, no una estrategia operable; válido y estándar para un null.

**ERROR 2 — D2: guard `2k>S` solo existía en momentum → reversion/aleatorio rompían la neutralidad EN SILENCIO.**
- Dónde: `estrategia_xsmom.py` — el guard estaba dentro de `ranker_momentum` (línea ~41) y NO en
  `_pesos_desde_ranking`.
- Qué estaba mal: con 2k>S los lados se solapan y el segundo asignado pisa al primero. Medido:
  `ranker_reversion(k=2)` con S=3 devolvía `w=[−.25,−.25,+.25]` → **sum=−0.25, gross=0.75** — libro
  net-short sin error ni aviso. Lo mismo `ranker_aleatorio` (o sea: el propio NULL podía correr
  no-neutral).
- Arreglo: guard central en `_pesos_desde_ranking` (cubre a los 3 rankers y a cualquier ranker futuro
  que la use), + guard `k>=1`. Eliminado el duplicado de momentum.
  Test: `test_guard_neutralidad_todos_los_rankers`.

**ERROR 3 — D3/D1: quiebra no manejada → equity NEGATIVA y el motor seguía operando.**
- Dónde: `engine_xs.correr` (paso (1) del loop; el guard `denom != 0` de la línea ~60 solo evitaba la
  división por cero exacta, no el caso `port_ret < −1`).
- Qué estaba mal: un short que pierde >100% del equity en una barra (p.ej. el shorteado sube +344%)
  dejaba equity negativa y el loop seguía: pesos con signo invertido sin sentido, pnl −169%, curva
  negativa. `metricas.cagr` con total negativo dio −100 de pura casualidad (exponente par); con otro
  horizonte habría dado nan/complejo.
- Arreglo: clamp de quiebra tras el paso de PnL — `equity<=0` → equity=0, libro cerrado, curva en 0
  hasta el final, `net_rets` cerrados en −1, flag **`quebro: True`** en el resultado. Guard adicional
  en `metricas.cagr` (total<=0 → −100%). Es honesto además de correcto: en futuros reales eso es
  liquidación/bancarrota, no un número negativo que "se recupera" multiplicativamente.
  Test: `test_quiebra_clamp`.

**ERROR 4 (menor) — datos: `alinear` no detectaba timestamps duplicados.**
- Dónde: `common/datos.py` `alinear()`.
- Qué estaba mal: un timestamp duplicado en cualquier símbolo multiplica filas en el inner-join
  (producto cartesiano) y corrompe la matriz EN SILENCIO (el chequeo de NaN no lo atrapa).
- Arreglo: `mat.index.is_unique` o ValueError. El cache actual está limpio (verificado: 26280×6, 0
  duplicados, 0 NaN, 0 gaps — la suposición de barras uniformes del funding vale para este cache).
  Test: `test_datos_alinear_duplicados`.

**ENDURECIMIENTO (no era bug de los rankers actuales, pero era un agujero estructural) — A1:**
el engine pasaba la matriz COMPLETA `M` al ranker; la causalidad dependía de la disciplina del ranker.
Ahora `correr` pasa **`M[:t+1]`** (vista numpy, sin copia): leer el futuro es IMPOSIBLE por construcción.
Verificado que no cambia nada para los rankers actuales (no-regresión exacta) y que un ranker "tramposo"
que lee la última fila disponible obtiene M[t]. Nota: `correr_null_desplazado` no entra en conflicto con
el slicing porque precomputa los targets FUERA del engine (tabla), no lee M dentro.
Test: `test_engine_no_pasa_futuro`.

#### Los 3 puntos abiertos del constructor

**(a) Funding pesimista sobre gross (B3): ACEPTABLE como piso, con regla de reporte doble.**
Medido en cache real (3 años, gross=1): drag relativo ≈ **−27.9%** (k=1: −68.26% con funding vs −56.01%
sin; ratio 0.7215), que coincide exacto con el teórico (1−0.0001/8)^26112 ≈ e^−0.326. Es grande pero:
(i) solo puede DEPRIMIR resultados — protege contra falsos positivos, que es lo que importa en esta fase;
(ii) para MOMENTUM ni siquiera es absurdo: un libro momentum long-calientes/short-fríos plausiblemente
paga funding en AMBAS patas (funding positivo en los que suben — lo paga el long; negativo en los que
caen — lo paga el short), así que "pagar la tasa base 0.01%/8h sobre el gross" es un caso-malo realista,
no una caricatura. (iii) El riesgo real es el FALSO NEGATIVO: un edge de ~+8%/año moriría por funding.
**Regla fijada**: todo backtest serio reporta funding ON y OFF; si un candidato pasa E1 con funding OFF
pero muere solo por funding ON → modelar funding per-símbolo ANTES de rechazarlo (esos datos son los
mismos de V46). Para V45 (reversión, libro anti-momentum) el piso es más punitivo que la realidad
esperable — misma regla lo cubre.

**(b) Justicia del null (E1): ERA INJUSTO — el hallazgo central de esta validación.** Ver ERROR 1.
Respuesta cuantitativa a la pregunta del constructor: no, el azar NO tenía el mismo perfil de turnover —
rotaba 2.4x más, y el percentil estaba inflado hasta el absurdo (percentil 100 para una config −53%).
Arreglado con el null desplazado; la dispersión del null ahora refleja "misma mecánica, otro timing" y
no "misma mecánica, el doble de costos".

**(c) Drift asimétrico (D1): CORRECTO — verificado con caso analítico a mano.** Construí (sin costos):
S0 100→101→121.2→127.26, S1 100→100→110→88; entrada [+.5,−.5] en t=1. A mano: t=2 port_ret=+0.05
(el short PIERDE cuando su precio sube +10% ✓), drift w=[4/7, −11/21], net drift = +1/21 (el libro queda
net-long tras una barra donde ambos suben ✓ — coincide con `net_expo[1]`); t=3 port_ret = (4/7)(.05) +
(11/21)(.2) = 2/15 (el short GANA cuando cae −20% ✓) → equity = 1.05·17/15 = **1.19 exacto** = buy&hold
de nocional fijo (.13+.06). El motor lo reproduce a 1e−12. Además pinneé el turnover contra pesos
DRIFTEADOS (rebalanceo en t=3: |1/2−9/17|+|−1/2+44/119| = **19/119**) — antes ningún test verificaba
que el turnover se mide contra el libro drifteado y no contra el target anterior.
Tests: `test_drift_asimetrico`, `test_turnover_sobre_pesos_drifteados`.

#### Notas de segundo orden (deliberadas, documentadas, NO arregladas por inmateriales)
1. El funding de la barra t se cobra sobre el gross POST-drift (fin de barra) en vez del gross al inicio
   de la barra — error de orden 0.0001×|drift| por barra, sin dirección sistemática clara, igual para
   real y null.
2. El costo de rebalanceo se cobra sobre el equity pre-costo y los pesos target se aplican al equity
   post-costo — segundo orden (0.1% de 0.1%), estándar.
3. Si el calendario cae en la última barra, ese rebalanceo cobra costo sin barra futura que ganar —
   pesimista, simétrico real/null.
4. `gross`/`net_expo` por barra se registran POST-rebalanceo (en barras de rebalanceo muestran el libro
   nuevo); el funding usa su propio gross inline — `net_expo_medio_abs` con rebal_every=1 es ~0 por
   construcción y NO mide la fuga por drift entre rebalanceos (que existe y es esperada; el caso
   asimétrico la exhibe: +1/21 tras una barra). Interpretar con eso en mente.
5. Ranker que devuelve None en medio de la corrida = el motor MANTIENE el libro drifteado (no liquida).
   Con los rankers actuales no pasa post-warmup; documentado como semántica.
6. `alinear` es inner-join: un símbolo listado más tarde acorta la ventana común de TODO el basket (no
   introduce sesgo de supervivencia por sí mismo, pero el que elige el basket debe saberlo). El basket
   OOB con historia corta reduciría la ventana — chequear T tras alinear.
7. `correr_null_desplazado` asume `warmup >= lookback` del ranker (si no, algunos targets son None y el
   null "sostiene" en el wrap — degradación menor, documentada).

#### Checklist HONESTIDAD.md — resultado final
| Ítem | Resultado | Evidencia |
|---|---|---|
| A1 señal solo con datos ≤ t | ✅ (endurecido a estructural: `M[:t+1]`) | `test_engine_no_pasa_futuro` |
| A2 retorno t→t+1, nunca se cobra lo rankeado | ✅ orden del loop verificado; pinneado por 1.10/1.20 | análisis + tests analíticos |
| A3 sin center/shift(−n)/stats globales | ✅ rankers revisados; test de perturbación del futuro | `test_anti_lookahead` |
| B1 costos sobre turnover real | ✅ | `test_costo_entrada_exacto`, `test_turnover_sobre_pesos_drifteados` |
| B2 constantes = motor vivo | ✅ verificado contra `stable_v25_prototype/config.py:232-234` (0.0005/0.0005/0.0001) | lectura directa |
| B3 funding modelado/documentado | ✅ pesimista sobre gross, medido −27.9%/3a, regla ON+OFF fijada | punto (a) |
| B4 pesimista ante la duda | ✅ turnover completo, funding bruto, percentil con empates en contra | lectura |
| C1 un code-path real+null | ✅ ambos nulls pasan por el MISMO `correr` | lectura + tests |
| C2 sin ramas solo-backtest | ✅ (no existe modo vivo aún; nada que divergir) | lectura |
| D1 drift correcto (incl. asimétrico) | ✅ | `test_drift_asimetrico` (1.19 exacto, a mano) |
| D2 neutralidad verificada | ✅ (bug de guard arreglado) | `test_guard_neutralidad_todos_los_rankers`, `test_dollar_neutral_siempre` |
| D3 equity multiplicativa + DD mtm | ✅ (quiebra clampeada) | `test_quiebra_clamp` |
| D4 tests analíticos | ✅ 16/16, los 3 originales verificados a mano | selftest_m1.py |
| E1 null bien definido (cadencia/turnover/costos) | ✅ **tras el fix** (antes ❌: turnover 2.4x, pctl 100 espurio) | `correr_null_desplazado`, `test_null_desplazado_turnover_justo` |
| E2 null determinista | ✅ ambos nulls | `test_null_determinista` |
| E3 criterio pre-registrado pctl≥70 | ✅ herramienta lista; el criterio se aplica por estrategia | `percentil_vs_null` |
| F1 basket-agnóstico | ✅ `correr(M,...)` no sabe de símbolos; `alinear` genérico | lectura |
| F2 hook de correlación vs V26/V36 | ✅ `metricas.correlacion` (alineación temporal la hace el caller — nota) | lectura |
| G1 determinismo bit a bit | ✅ path real sin RNG; nulls sembrados | `test_null_determinista` |
| G2 no-regresión | ✅ post-fixes, el path real reproduce el baseline pre-fix EXACTO (k=1: −68.26413772447081, k=2: −53.26020542991483) | corrida de control |

#### VEREDICTO: ✅ **VALIDADO** — M1 queda listo para backtests serios, con 3 condiciones de uso
1. **El percentil E1 se calcula con `correr_null_desplazado`** (min_offset ≈ lookback/rebal_every).
   `correr_null_permutacion` NO vale para aceptar nada (queda como cota gruesa/diagnóstico).
2. **Reportar funding ON y OFF** en todo backtest serio; si un candidato muere SOLO por funding,
   modelar per-símbolo antes de rechazar (punto (a)).
3. **Chequear el flag `quebro`** y el T resultante de `alinear` (ventana común) en cada corrida.

Costo de la validación en números: 4 bugs (1 de primer orden que habría invalidado TODOS los percentiles,
2 de corrección silenciosa, 1 de datos), 1 endurecimiento estructural, 7 tests nuevos (9→16), 0 cambios
fuera de `Fragua/`, no-regresión exacta del path real.

---

## 2026-07-05 — V45: Reversión cross-sectional (Constructor: Antigravity)

**Pre-registro**: el libro sección "V45 — FACTOR DE REVERSIÓN CROSS-SECTIONAL" (escrito ANTES del código).

### Resultado

| Métrica | V45 (reversión 168h) | Null desplazado (n=200) |
|---|---|---|
| PnL (funding ON) | −73.20% | mediana −63.27% |
| PnL (funding OFF) | −62.85% | — |
| Profit Factor | 0.949 | — |
| Max DD | 75.5% | — |
| Percentil vs null | **22.5** | — |
| Criterio (PnL>0 ∧ PF>1 ∧ pctl≥70) | **NO PASA** | — |

### Bugs / incidentes documentados

**Ninguno**. El código de `run_v45.py` usa `ranker_reversion` ya validado por Fable (2026-07-04) y el
motor `engine_xs` sin modificaciones. La corrida fue limpia.

### Diagnóstico de mecanismo

Percentil 22.5 indica que V45 rinde PEOR que el 77.5% de las simulaciones aleatorias — la señal va en la
dirección OPUESTA a la hipótesis. Los ganadores relativos de la semana SIGUEN ganando (momentum de muy
corto plazo persiste en cripto 2023-26), y los perdedores SIGUEN perdiendo.

Esto es coherente con la literatura: el efecto "short-term reversal" en cripto (a diferencia de acciones)
opera a escalas de horas, no días. A escala de 1 semana domina el momentum, no la reversión.

### Veredicto

RECHAZADO in-sample. OOB no corrido (per pre-registro). Sin escanear variantes de lookback.

**Estado de M1**: los tres factores intentados — momentum (V44, pctlIS 77.5, OOB negativo), carry (V46,
pctlIS 59, OOB negativo), reversión (V45, pctlIS 22.5, OOB no corrido) — han sido rechazados.
El espacio cross-sectional con datos OHLCV+funding y estas definiciones está agotado.
