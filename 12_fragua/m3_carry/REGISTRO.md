# REGISTRO — M3 Carry (extensión de funding real sobre M1)

## 2026-07-04 — Construcción inicial (Constructor: Opus)

**Motivación**: V44 (momentum cross-sectional en M1) pasó los 3 criterios in-sample pero falló fuera de
canasta por PnL negativo, aunque el percentil OOB seguía fuerte (81.5) — la condición de uso #2 de la
validación de Fable decía explícitamente: si un candidato muere solo por funding, modelar per-símbolo
antes de rechazar. M3 construye ese modelo.

**Qué se construyó**:
1. `funding_real.py` — alineación de funding real (2 fuentes: cache existente de V27-B para la canasta
   original, cache nuevo descargado de la API pública de Binance para la canasta OOB) a matrices (T,S)
   sincronizadas con los timestamps del motor.
2. Extensión de `engine_xs.correr()` (y sus dos funciones de null) con el parámetro opcional
   `funding_matrix` — aditivo, `None` por default reproduce EXACTO el comportamiento anterior.
3. `estrategia_carry.ranker_carry` — el factor de carry (long funding negativo, short funding positivo).

**Self-tests (5/5 OK)**:
| Test | Verifica |
|---|---|
| `test_matrices_funding_caso_tasa_cero` | Tasa real de 0% no se confunde con "sin evento" (bug propio, ver abajo) |
| `test_matrices_funding_colision_hora` | Colisiones de redondeo se suman y se reportan, no se pierden |
| `test_formula_funding_real_en_motor` | `-w·rate` exacto (equity == 0.9985 a mano) |
| `test_funding_matrix_none_no_regresion` | `funding_matrix=None` == comportamiento pre-M3 |
| `test_ranker_carry_elige_bien` | Long tasa más negativa, short tasa más positiva, neutral |

**No-regresión de M1 confirmada dos veces**: 16/16 self-tests de `selftest_m1.py` siguen pasando después
de extender `engine_xs.py`, y el baseline de V44 (k=1: −68.26413772447081%, k=2: −53.26020542991483%) se
reproduce dígito por dígito.

**Bug propio encontrado y corregido ANTES de pasar a validación**: la primera versión de
`matrices_funding` usaba `.replace(0.0, np.nan).ffill()` para el forward-fill de la tasa conocida — eso
trata cualquier tasa real de exactamente 0% como "sin evento" y haría *forward-fill* incorrecto del
último valor NO-cero anterior en vez de registrar la caída real a 0%. Arreglado con una máscara explícita
`presente` (basada en si hubo un evento, no en el valor). Test `test_matrices_funding_caso_tasa_cero`
construido específicamente para que este bug, si reaparece, haga fallar la suite.

**Smoke test end-to-end (NO es resultado, solo integración)**: corrido sobre las 2 canastas reales completas
(3 años, 26280 barras × 6 símbolos cada una) sin crashear; ~3.285 eventos de funding por símbolo en 3 años
(≈3/día × 3 años = 3285.6 — coincide casi exacto, buena señal de que la alineación no pierde ni duplica
eventos), 0 colisiones de hora en ningún símbolo de ninguna canasta.

**Estado**: 🔨 esperando validación de Fable. Sin backtests serios (V46, o V44 con funding real) aún.

---

## (Fable escribe debajo de esta línea)

### Validación Fable — 2026-07-04 (incremental, en curso)

**Método**: mismo protocolo que M1 — lectura línea por línea de lo NUEVO (`funding_real.py`,
`estrategia_carry.py`, `selftest_m3.py`, el diff de `engine_xs.py`), verificación a mano de los tests
analíticos, micro-experimentos sobre los caches reales (read-only) ANTES de tocar nada, y no-regresión
tras cualquier fix.

**Paso 0 — estado de partida (verificado antes de cualquier cambio):**
- `selftest_m1.py`: **16/16 OK** — los fixes de la validación de M1 siguen intactos tras la extensión.
- `selftest_m3.py`: **5/5 OK**.
- **No-regresión independiente**: `funding_matrix=None` (y también omitir el parámetro) reproduce el
  baseline de V44 EXACTO, dígito por dígito: k=1 −68.26413772447081%, k=2 −53.26020542991483%
  (`ranker_momentum(lookback=168)`, rebal 24, warmup 168, funding ON, cache original 26280×6). ✅
  La extensión es genuinamente aditiva en el path viejo.

(Hallazgos de la auditoría se agregan abajo a medida que salen.)

#### Micro-experimentos sobre datos reales (read-only, pre-fix) — los 4 puntos del constructor

**(1) Redondeo de hora (`.dt.round('h')`) — CAUSAL, con demostración estructural, no solo empírica.**
- Jitter medido en los 13 símbolos de ambos caches: **0 a +30 ms** (el evento ocurre siempre unos ms
  DESPUÉS del borde de hora, nunca antes; ningún evento a >60s de un borde). El round siempre asigna el
  evento a su hora verdadera.
- Pero el argumento decisivo no es el jitter chico sino la **convención de timestamps del cache de
  precios**: verificado en `binance_client._df_de_klines` (columna 0 del kline = **OPEN time**) y en el
  cache mismo (barras 01:00…00:00). La barra rotulada H cierra en H+1h real; el motor decide/ejecuta al
  CIERRE de la barra. Un evento asignado a la barra H se usa para decidir recién en H+1h real. Round a
  la hora más cercana desplaza un evento a lo sumo 30 min hacia atrás ⇒ el evento verdadero ocurrió a más
  tardar en H+30min < H+1h = momento de la decisión. **Con etiquetas open-time y barras 1h, round('h')
  no puede crear lookahead con NINGÚN jitter < 30 min** — y el jitter real es de milisegundos. ✅
- Nota si alguien reusa esto con etiquetas close-time: ahí la holgura desaparece (la decisión en H usaría
  un evento liquidado en H+jitter). No es el caso de estos caches.

**(2) Hallazgo de datos — SOLUSDT tuvo funding a intervalos de 2h/4h** (eventos en TODAS las horas pares;
n=4458 vs 4383 del resto del cache V27-B). El supuesto "espaciado 8h" del docstring no es universal.
Dentro de la ventana de precios de 3 años (2023-06-12→2026-06-11) el espaciado es 8h limpio en los 12
símbolos, pero el supuesto queda documentado como NO estructural — por eso los guards de gaps que se
agregan abajo reportan `max_gap_horas` en vez de asumir 8h.

**(3) Cobertura dentro de la ventana — perfecta en ambas canastas**: 3285 eventos/símbolo (≈3/día×3 años),
gap máximo 8h, 0 eventos caídos por falta de barra (el cache de precios no tiene huecos), primer evento a
7h del inicio de ventana, último en la última barra. El conteo del constructor (~3285) se reproduce. ✅

**(4) El bug de tasa-cero del constructor era REAL y de primer orden, no un caso teórico:**
**BNBUSDT tiene 2.417 eventos con rate == 0.0 EXACTO (55% de sus 4.383 eventos)** — Binance mantuvo el
funding de BNB clavado en 0 por tramos largos. Con el bug (`replace(0.0, nan).ffill()`), la `conocida` de
BNB habría forward-filleado tasas viejas no-cero a través de AÑOS de régimen de tasa 0 — corrupción de
señal de primer orden en 1 de 6 símbolos de la canasta original de V46. Verifiqué además que el test
`test_matrices_funding_caso_tasa_cero` discrimina el bug: revirtiéndolo mentalmente, las celdas B[8:10]
darían 0.0005 en vez de 0.0 y el assert (con mensaje específico) falla. También hay 1 evento de tasa 0.0
en AVAX y 1 en ATOM (canasta OOB). El fix del constructor es load-bearing. ✅

**(5) Signo de `-w·rate` verificado contra el motor vivo** (`stable_v25_prototype/backtest.py::pnl_neto_cierre`,
líneas 63-74, leído directamente): LONG resta funding cuando rate>0, SHORT lo suma — mismo convenio.
En M3: w>0,rate>0 → paga; w<0,rate>0 → cobra; w>0,rate<0 → cobra; w<0,rate<0 → paga. Los 4 casos correctos
por álgebra; el self-test del constructor solo cubría 2 de los 4 (ambos "paga") y sin drift — se agrega
un caso analítico a mano con drift y los 4 combos (ver fixes). ✅

**(6) Hueco pre-ventana en `conocida` (bug menor, confirmado en datos reales)**: las barras 0–6 de ambas
canastas tienen `conocida == 0.0` para TODOS los símbolos, aunque una tasa real estaba publicada (el
evento de 2023-06-12 00:00, una hora antes del inicio de la ventana). El "último valor conocido" en esas
barras NO es 0. Sin efecto en corridas reales (warmup≫8), pero contradice la semántica documentada y
degenera el libro del ranker si alguien corre con warmup<8. Se arregla con seed pre-ventana (abajo).

#### ERRORES ARREGLADOS (3) + GUARDS (2) — cada uno con test que lo captura

**FIX 1 — `conocida` pre-ventana sembrada con la última tasa publicada antes de la ventana**
(`funding_real.py`). Antes: 0.0 hasta el primer evento en ventana (hallazgo (6) arriba — confirmado en
las barras 0–6 de ambos caches reales). Ahora: la última tasa publicada ANTES de `times[0]` siembra el
ffill (si no existe, 0.0 como antes). El pago pre-ventana NO se cobra (está fuera de M — solo se hereda
el conocimiento). Colateral positivo: elimina el libro degenerado del ranker de carry en warmups chicos
(todas las `conocida[0]` reales quedan pobladas). Test: `test_conocida_seed_pre_ventana`.

**FIX 2 — `conocida` en colisiones de hora usaba la SUMA de los eventos colididos**
(`funding_real.py`). "Última tasa conocida" debe ser una tasa que EXISTIÓ (la del último evento
publicado), no un agregado. `pagos` sigue sumando (correcto: ambos pagos ocurren). Path nunca tomado en
los caches reales (0 colisiones medidas) — fix semántico, con orden cronológico por tiempo REAL
garantizado antes del groupby. Test: `test_matrices_funding_colision_hora` (extendido).

**FIX 3 — quiebra por funding no clampeada en la misma barra** (`engine_xs.py`, paso (3b) nuevo).
El clamp de quiebra (1b) corre tras el PnL; un funding con |w·rate| ≥ 1 (imposible con tasas reales
—máx medido |rate|=2%—, posible con una matriz corrupta/sintética) dejaba equity NEGATIVA durante una
barra entera: la curva registraba un punto negativo y el rebalanceo de esa barra operaba con equity sin
sentido; el clamp recién actuaba en la barra siguiente. Ahora el mismo clamp corre también tras el paso
de funding. Inalcanzable en los paths preexistentes (funding pesimista ≤ gross·1.25e-5·hpb ≪ 1) — la
no-regresión lo confirma. Test: `test_quiebra_por_funding_clampeada`.

**GUARD 4 — shape de `funding_matrix` validada contra M** (`engine_xs.py`). Una matriz construida con
otros times/símbolos se indexaba desalineada EN SILENCIO (o rompía por broadcast según el caso). Ahora
`ValueError`. La correspondencia de timestamps sigue siendo responsabilidad del caller (construir con los
MISMOS times/symbols de `datos.alinear`) — el guard atrapa el desalineo de forma, que es el detectable.
Test: `test_guard_shape_funding_matrix`.

**GUARD 5 — datos de funding: tres fallos que antes pasaban EN SILENCIO como optimismo**
(`funding_real.py`): (a) tasa NaN → poison silencioso del equity vía `w @ fm[t]` → ahora ValueError;
(b) símbolo con CERO eventos dentro de la ventana (el típico mismatch de timestamps/tz deja
`isin`→all-False y "funding=0 para siempre", optimista) → ValueError; (c) evento dentro de la ventana
cuya hora no existe como barra de precio (el pago se perdía en el `reindex`, optimista) → ValueError con
escape hatch explícito `permitir_eventos_sin_barra=True` (documentado como optimista; meta lo cuenta).
Además la meta ahora reporta por símbolo: `eventos_en_ventana`, `eventos_sin_barra`, `colisiones_hora`,
`max_gap_horas` (el espaciado 8h NO es estructural — ver hallazgo SOL) y `seed_pre_ventana`.
Test: `test_guards_datos_funding`.

**Tests nuevos que pinnean propiedades que los 5 originales no cubrían:**
- `test_funding_con_drift_y_signos` — caso analítico A MANO: funding sobre pesos POST-drift con los 4
  combos de signo (long-paga, short-paga, long-cobra, short-cobra); equity esperada
  `1.075·(1−0.063/43)·(1+0.142/43)` exacta a 1e−12. El test del constructor cubría 2 de 4 combos (ambos
  "paga") y sin drift.
- `test_conocida_causal_futuro_no_afecta` — A1 para el funding: perturbar un evento FUTURO no cambia
  `conocida` en barras previas ni la decisión de `ranker_carry` en t previos. Importante porque
  `conocida` vive FUERA del anti-lookahead estructural `M[:t+1]` del engine — su causalidad ahora queda
  pinneada por test propio, no solo por lectura.

#### Verificación de no-regresión POST-fixes (todo junto)
- `selftest_m1.py`: **16/16 OK**. `selftest_m3.py`: **11/11 OK** (5 originales + 6 nuevos).
- **Baseline V44 EXACTO** dígito por dígito tras tocar `correr()`: k=1 −68.26413772447081%,
  k=2 −53.26020542991483% (con `funding_matrix=None` y omitiendo el parámetro). ✅
- **Control diferencial de matrices reales** (pre-fix vs post-fix, ambas canastas): `pagos` bit-idéntica;
  `conocida` difiere EXCLUSIVAMENTE en las barras 0–6 (el seed pre-ventana — exactamente lo esperado);
  meta consistente (3285 eventos/símbolo, 0 colisiones, max gap 8h; seed de BNB = 0.0, coherente con su
  régimen de tasa clavada en 0). ✅
- **Smoke de integridad end-to-end** (NO es resultado de estrategia): motor + `pagos` real +
  `ranker_carry` + `correr_null_desplazado` en ambas canastas: equity finita y ≥0, `quebro=False`, null
  finito, **determinismo bit a bit** re-corriendo real y null con la misma semilla. ✅

#### Notas de segundo orden (deliberadas, documentadas, NO arregladas por inmateriales)
1. El funding del evento asignado a la barra H se aplica con los pesos POST-drift de esa barra (valuados
   al cierre H+1h). El NOCIONAL es el correcto (el libro no cambia entre rebalanceos); la diferencia está
   en el denominador equity (una barra de drift) — mismo orden y misma naturaleza que la nota #1 de M1
   (~|rate|·|drift| por evento, sin dirección sistemática).
2. Un rebalanceo ejecutado al cierre H coincide en el reloj con el snapshot de funding de H: el motor
   asume que el libro NUEVO paga ese funding (en la realidad depende de milisegundos). Diferencia =
   rate × turnover de esa barra — segundo orden, sin dirección sistemática.
3. En una colisión de hora, `pagos` suma ambos eventos y los cobra con el peso de una sola barra (los dos
   eventos reales habrían tenido nocionales ligeramente distintos por drift intra-hora). Solo en el path
   should-never-happen (0 colisiones reales); meta lo reporta.
4. `eventos_promedio_por_simbolo` ahora cuenta eventos EN VENTANA (antes: barras con evento). Idéntico
   (3285) cuando no faltan barras — el único caso que el guard 5(c) permite por default.
5. El recomendado `min_offset ≈ lookback/rebal_every` del null desplazado no aplica literalmente al
   carry (no tiene lookback): la escala de persistencia de la señal es el régimen de funding
   (días-semanas). Offsets chicos → percentil PESIMISTA (dirección segura). El pre-registro de V46 debe
   fijar `min_offset_rebalanceos` explícito (sugerencia: ≥ 7 días / rebal_every).

#### Checklist HONESTIDAD.md — M3 (foco en lo nuevo; lo de M1 ya certificado no se re-lista)
| Ítem | Resultado | Evidencia |
|---|---|---|
| A1 señal con datos ≤ t (funding) | ✅ ffill estrictamente forward + seed pre-ventana causal; round('h') estructuralmente causal con etiquetas open-time (demostración + jitter medido ≤30ms) | `test_conocida_causal_futuro_no_afecta`, micro-exp (1) |
| A2 retorno t→t+1 | ✅ sin cambios en el orden del loop; funding en (3), decisión en (4) — 1h real de holgura entre publicación y decisión | lectura + convención open-time verificada |
| A3 sin center/shift(−n)/stats globales | ✅ `ffill()` es forward-only; no hay normalización global | lectura + test causal |
| B1 costos sobre turnover | ✅ sin cambios (no-regresión exacta) | baseline V44 |
| B2 constantes espejo | ✅ intactas; funding real solo reemplaza el PISO cuando se pasa la matriz | lectura |
| B3 funding modelado | ✅ **per-símbolo, firmado, por evento real** — exactamente el refinamiento que la condición de uso #2 de M1 exigía; signo verificado contra `pnl_neto_cierre` del motor vivo (backtest.py:63-74) y con caso analítico de 4 combos | `test_funding_con_drift_y_signos`, micro-exp (5) |
| B4 pesimista ante la duda | ✅ pérdidas de pagos silenciosas ahora revientan; escape hatch explícito y documentado | `test_guards_datos_funding` |
| C1 un code-path real+null | ✅ ambos nulls aceptan y propagan `funding_matrix` al MISMO `correr` | lectura + smoke |
| C2 sin ramas solo-backtest | ✅ un carry vivo experimenta exactamente estos flujos (por evento, firmado) | lectura |
| D1 drift correcto | ✅ funding sobre pesos post-drift (mismo punto que el piso de M1); caso a mano con drift | `test_funding_con_drift_y_signos` |
| D2 neutralidad | ✅ `ranker_carry` usa `_pesos_desde_ranking` (guard central de M1) | `test_ranker_carry_elige_bien` |
| D3 equity multiplicativa + quiebra | ✅ (quiebra por funding clampeada en la misma barra — FIX 3) | `test_quiebra_por_funding_clampeada` |
| D4 tests analíticos | ✅ 11/11 M3 + 16/16 M1; 0.9985 y 1.075·(1−0.063/43)·(1+0.142/43) verificados a mano | selftests |
| E1 null justo | ✅ `correr_null_desplazado` + funding real: misma cadencia/turnover/costos/funding, solo rota la señal | smoke + lectura |
| E2 null determinista | ✅ verificado bit a bit con funding real | smoke |
| E3 criterio pre-registrado | ✅ herramienta lista; pctl≥70 se fija en el pre-registro de V46 (con nota 5 sobre min_offset) | — |
| F1 basket-agnóstico | ✅ corrido en ambas canastas sin cambios de código (cache OOB propio de Fragua) | smoke |
| F2 hook correlación | ✅ sin cambios (sigue pendiente de ejercitarse con datos reales — pendiente conocido de M1) | — |
| G1 determinismo | ✅ real y null bit a bit con funding real | smoke |
| G2 no-regresión | ✅ V44 exacto post-fixes + control diferencial de matrices (pagos idéntico; conocida solo barras 0–6) | corrida de control |

#### Los 4 puntos que el constructor dejó abiertos — respuestas
1. **Signo y timing de `-w·rate`**: CORRECTO en los 4 combos (verificado por álgebra, contra el motor
   vivo, y con caso analítico a mano con drift — el test del constructor solo cubría 2 combos sin drift).
   Timing: el evento de la barra H se cobra dentro de esa misma hora con el libro correcto (segundo orden
   documentado en notas 1-2).
2. **Causalidad de `ranker_carry`/`conocida`**: SÍ es una laguna DISTINTA al slicing `M[:t+1]` (la
   estructura vive afuera del mecanismo estructural), y por eso quedó pinneada con test propio de
   perturbación del futuro. El ffill es estrictamente forward; el seed pre-ventana usa solo eventos
   ANTERIORES a `times[0]`. Causal. ✅
3. **Redondeo de hora**: NO puede crear lookahead en estos caches — argumento estructural (etiquetas
   open-time ⇒ la decisión ocurre en H+1h real; round desplaza a lo sumo 30 min hacia atrás) + medición
   (jitter real 0 a +30 ms, 0 eventos a >60s de un borde de hora, en los 13 símbolos de ambos caches).
   Advertencia escrita en el módulo para un futuro reuso con etiquetas close-time. ✅
4. **Colisiones y símbolos faltantes**: símbolo entero faltante → KeyError (ya existía). Huecos PARCIALES
   → ANTES: silencio optimista (pagos perdidos / funding=0); AHORA: guards (FIX/GUARD 5) + meta con
   `max_gap_horas` por símbolo. En los caches reales no hay huecos (max gap 8h, 3285 eventos/símbolo,
   cobertura hasta los bordes de la ventana en las 2 canastas). ✅

#### VEREDICTO: ✅ **VALIDADO** — M3 queda listo para V46 y para el re-test de V44 con funding real, con condiciones de uso
1. **Las matrices se construyen con los MISMOS `times`/`symbols` que devolvió `datos.alinear()`** para la
   M que se le pasa al motor (el engine valida shape; los timestamps son responsabilidad del caller).
2. **Al motor va `pagos`; al ranker va `conocida` — NUNCA al revés.** Pasar `conocida` como
   `funding_matrix` cobraría la última tasa conocida TODAS las barras (~8x el funding real). Es el
   footgun más peligroso de la API; el run script de V46 debe nombrar las variables explícitamente.
3. **Chequear en cada corrida**: flag `quebro`, y en meta `colisiones_hora == 0`, `eventos_sin_barra == 0`
   y `max_gap_horas` razonable (~8h) por símbolo.
4. **Pre-registro de V46**: fijar `min_offset_rebalanceos` explícito (el default 1 es válido pero
   desperdicia sims por solape; sugerencia ≥ 7 días / rebal_every — dirección pesimista en cualquier caso).
5. **El re-test de V44 con funding real** (la pregunta que motivó M3) es legítimo per la condición de uso
   #2 de la validación de M1 — no es escaneo de variantes: es reemplazar un piso declarado-pesimista por
   el modelo exacto pre-comprometido. Reportar las tres variantes (piso pesimista / funding real / OFF)
   para que la comparación quede completa.

Costo de la validación en números: 3 fixes (1 confirmado en datos reales, 2 de robustez semántica/motor),
2 guards contra fallos silenciosos optimistas, 6 tests nuevos (5→11), 0 cambios fuera de `Fragua/`,
no-regresión exacta del baseline V44 y control diferencial de matrices en ambas canastas.
