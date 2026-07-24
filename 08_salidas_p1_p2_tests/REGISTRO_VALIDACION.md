# REGISTRO DE VALIDACIÓN — TEST 1 (ADX decline) y TEST 2 (divergencia RSI)
**Validador**: sesión independiente (Fable), 2026-07-04. Mismo estándar que las validaciones de Fragua/M1-M3.
**Alcance**: auditoría de los DOS experimentos de salida para V26 documentados en el libro
("TEST 1 y TEST 2 — completando la hipótesis de agotamiento") — implementación, causalidad,
paridad real↔null, reproducción de números, bug de presentación, decisión de saltar OOB, y aislamiento.
**Jurisdicción**: solo esta carpeta (`v26_salida_test/`). `v26_tendencia/` y `stable_v25_prototype/`
son SOLO LECTURA para esta sesión.

---

## 0. Aislamiento (regla dura) — ✅ VERIFICADO

Por fecha de modificación (`stat`):
- `v26_tendencia/`: ningún archivo tocado desde **2026-07-01 15:11** (el deploy de /history) — 3 días
  antes de la creación de esta carpeta.
- `stable_v25_prototype/`: código (.py) intacto desde **2026-07-04 18:13–18:19** (la sesión P1/P2,
  anterior); los archivos más recientes ahí (hasta 20:26) son solo artefactos JSON/caches de las corridas
  P1/P2, todos ANTERIORES a la creación de `v26_salida_test/` (~21:12).
- El diff completo `v26_salida_test/` vs `stable_v25_prototype/` toca EXACTAMENTE los 4 archivos
  declarados (config.py, indicadores.py, backtest.py, walkforward.py); los otros 6 .py son idénticos.
- El cache `wf_cache_4h_8760_2026-06-11.pkl` es copia byte-idéntica (MD5 `e3a076a7…` igual en ambas
  carpetas); los otros dos caches son symlinks read-only.

## 1. No-regresión (flags OFF) — ✅ REPRODUCE EXACTO

Corrido por el validador (no confiado del registro):
`walkforward.py --interval 4h --entrada cruce --salida tendencia --continuo --years 4 --end 2026-06-11
--fee 0.0002 --slippage 0.0002 --mc 0` →
**+130.59% | 426 trades | WR 18.08% | PF 1.918 | Max DD 26.3%** — dígito por dígito igual al baseline
histórico del Test C y a los dos controles guardados (`wf_resumen_control_copia.json` y
`wf_resumen_control_no_regresion.json`, verificados idénticos entre sí y con esta corrida, incluidos
los desgloses por motivo: FLIP 83/+$1,224.55, STOP 337/−$698.90, ADMIN 6/+$127.31).
Artefacto: `wf_resumen_validador_noregresion.json`.

## 2. Auditoría de implementación

### 2.1 TEST 1 — ADX cayendo desde pico (`ADX_DECLINE_EXIT_TENDENCIA`) — ✅ CORRECTO

Ejercitado el código REAL (`backtest._salidas_vela` y `walkforward._salidas_vela_mc`, no una
re-implementación) con secuencias de ADX controladas (`scratchpad/test_analitico.py`, parte B):

| Caso | Esperado | Resultado |
|---|---|---|
| ADX nunca ≥40 (30…39…33, cayendo 6 velas) | jamás dispara, contador queda 0 | ✅ |
| 42→41→41→40.5→40.0 | reset en la vela igual (41=41), cierra en la 5ª ("cayendo 2v desde pico 42.0") | ✅ |
| Caídas no consecutivas (45,44,46,45,47…) | nunca acumula 2, no cierra | ✅ |
| NaN de ADX al inicio (nan,nan,45,44,43) | no dispara espurio ni corrompe el máximo; cierra con pico 45.0 | ✅ |
| Pico 42, luego ADX cae bajo 40 (42,39,38) | sigue contando (el umbral es sobre el MÁXIMO visto), cierra | ✅ |
| SHORT | simétrico, cierra igual | ✅ |
| Vela que toca stop Y cumpliría agotamiento | gana el STOP (orden intravela pesimista preservado) | ✅ |

- **Causalidad**: usa `row['ADX']` de la vela actual (indicador rolling causal, motor pre-validado) y
  cierra al `close` de esa misma vela — la misma convención de decisión-al-cierre que el flip del
  baseline, así que la comparación contra el control es homogénea. El estado (`adx_max_visto`,
  `adx_anterior`, `adx_velas_cayendo`) solo acumula hacia adelante; cada trade nace como dict nuevo
  (entrada normal, réplica P1 y `_abrir_aleatorio` del null) → sin fuga de estado entre trades.
- **NaN**: `max(prev, nan)` en Python conserva `prev` (primer argumento) y `nan < x` es False → el
  mecanismo degrada a "no disparar", nunca a disparo espurio. Verificado ejecutando (caso B.4).
- **Defaults de `t.get(...)`**: `adx_max_visto`→0.0, `adx_anterior`→None, `adx_velas_cayendo`→0,
  idénticos carácter a carácter en motor real y null.

### 2.2 TEST 2 — Divergencia de RSI (`Div_Bajista`/`Div_Alcista`) — ✅ CORRECTO

- **Oráculo independiente**: loop a mano ("ventana = exactamente las 14 velas previas, sin la actual")
  sobre 300 velas de random walk vs las columnas vectorizadas del archivo → **coincidencia total**
  (2 señales bajistas, 23 alcistas, vector completo idéntico).
- **El `shift(1)` importa y está bien**: sin él, `close >= rolling(14).max()` incluiría la vela actual y
  sería SIEMPRE True (toda vela "sería nuevo máximo"). Caso a mano (pico a 130 → retroceso → nuevo
  máximo débil 130.2): en pleno retroceso (velas 16-20) el RSI está bajo su máximo previo pero
  `Div_Bajista=False` porque NO hay nuevo máximo (el pico previo sigue en la ventana) — exactamente lo
  que un shift faltante habría roto; y en la vela del nuevo máximo débil (close 130.2 ≥ máx-previo 130.0,
  RSI 78.2 < máx-RSI-previo 91.9) `Div_Bajista=True`, con ambos componentes verificados por separado.
- **Primeras 14 velas**: todas False (min_periods del rolling → NaN → comparación False). ✅
- **dtype**: bool puro sin NaN (las comparaciones pandas con NaN dan False; el `.fillna(False)` es
  redundante pero inofensivo) — importante porque el consumidor hace `bool(row.get(col, False))` y un
  NaN residual daría `bool(nan)=True` (disparo espurio). No puede ocurrir. ✅
- **Direccionalidad en el motor**: LONG+`Div_Bajista` cierra; SHORT+`Div_Bajista` NO cierra (usa
  `Div_Alcista`). Verificado ejecutando el motor real y el null. ✅
- **Nota no-bloqueante de semántica**: la definición es "nuevo extremo de precio de 14 velas cuyo RSI no
  supera su propio extremo previo" — una versión simple de divergencia (no compara swings pivotales).
  Es exactamente lo que el pre-registro describe, así que el test mide lo que dice medir; solo se anota
  que "divergencia" aquí es esta definición operativa y no la definición chartista de pivotes.

### 2.3 Paridad motor-real ↔ null (`_salidas_vela` vs `_salidas_vela_mc`) — ✅ EQUIVALENTES

- Diff mecánico de los bloques TEST 1/TEST 2 extraídos de ambos archivos: la lógica condicional y el
  manejo de estado son **carácter a carácter idénticos**; solo difiere el mecanismo de cierre
  (`self._cerrar(...)` vs `return (precio, ts, False)`) — ambos cierran al `close` de la vela y el
  llamador del null aplica el MISMO `pnl_neto_cierre` (fee+slippage+funding). El orden de evaluación es
  idéntico: stop pesimista → contador LATERAL → P2 → P1 → **TEST 1 → TEST 2** → ratchets → flip.
- Paridad verificada EJECUTANDO ambos con las mismas secuencias (no solo por lectura): mismos índices de
  cierre, mismos precios, en todos los casos de 2.1/2.2, incluido "stop gana al agotamiento".
- En modo continuo el null además comparte `bt.dfs` (mismos indicadores) y `bt._tendencia_en` (mismo
  memo de tendencia) que el motor real, y la frecuencia de trades del null se iguala a la del real BAJO
  EL MISMO EXIT (n_por_sym sale de la corrida real con el flag ON) — la comparación señal-vs-azar es
  bajo mecánica idéntica, exactamente la lección Fragua/M1.
- **Única asimetría detectada**: el motor real actualiza `t['peak_progress']` al cierre de vela y el
  null no. Es **pre-existente** (viene de la sesión P1/P2, no de estos tests), y es **inerte**: bajo
  `EXIT_MODE='tendencia'` ninguna decisión usa `peak_progress` (es telemetría; `precio_replica` usa
  tp/entry, no el peak). No sesga el percentil. Se documenta por transparencia.

## 3. Reproducción de los números — ✅ EXACTOS (determinismo confirmado, seed 42)

Ambos comandos re-corridos por el validador (mc=100):

| Métrica | TEST 1 doc. | TEST 1 re-corrido | TEST 2 doc. | TEST 2 re-corrido |
|---|---|---|---|---|
| PnL | +6.19% | **+6.19%** ✅ | −2.62% | **−2.62%** ✅ |
| PF | 1.033 | **1.033** ✅ | 0.986 | **0.986** ✅ |
| Max DD | 16.3% | **16.3%** ✅ | 13.1% | **13.1%** ✅ |
| Percentil vs null | 73.0 | **73.0** ✅ | 86.0 | **86.0** ✅ |
| Trades | 827 | **827** ✅ | 1050 | **1050** ✅ |

Los JSON re-corridos (`wf_resumen_test1_validacion.json`, `wf_resumen_test2_validacion.json`) son
idénticos a los originales también en los desgloses COMPLETOS por motivo y por símbolo (comparación
dict-a-dict, no solo los agregados). Null medianas: −4.56% (T1) y −12.37% (T2), iguales.

## 4. Bug de presentación del TEST 1 — ✅ CONFIRMADO COMO SOLO-PRESENTACIÓN

En `wf_resumen_test1_adx_decline.json` el motivo incluye el pico de ADX en el string → **155 grupos**
distintos de "AGOTAMIENTO ADX: cayendo 2v desde pico X". Verificado sumando:
- Grupos de agotamiento: **262 trades, +$949.84** — exactamente lo que dice el libro.
- Total por motivo: 262 + 14 (FLIP, +$2.17) + 551 (STOP, −$921.05) = **827 trades, $30.96** vs global
  reportado $30.94 → diferencia $0.02 = redondeo a 2 decimales acumulado sobre 157 grupos. Cuadra.
- La suma por símbolo también cuadra (827 trades, $30.93).
El PnL/conteo del motor son correctos; solo el resumen impreso queda fragmentado. En TEST 2 el motivo es
constante y no hay fragmentación (515 divergencia +$900.69 / 530 stops −$908.68 / 5 flip −$5.12 = 1050,
$−13.11 exacto — y el WR 98.3% del bucket citado en el libro coincide con el JSON).

**Arreglo sugerido si esta carpeta se reusa** (no aplicado — los artefactos originales deben seguir
reproduciéndose byte a byte durante la auditoría): sacar el pico del motivo (o truncarlo a etiqueta fija
"AGOTAMIENTO ADX" y llevar el pico a un campo aparte del trade).

## 5. Búsqueda activa de errores (más allá de lo pedido) — nada bloqueante

- **Look-ahead**: ninguno. Div_* usa shift(1)+rolling (trailing); ADX del propio cierre de vela; el memo
  de tendencia usa `iloc[:i+1]`; el null abre con `df.iloc[:i+1]`. Ningún camino toca datos futuros.
- **Casos límite**: NaN de ADX/RSI en warmup degradan a "no señal" (verificado ejecutando); ventana
  corta (<14 velas) → False; el warmup-fill del RSI a 50.0 (pre-existente en indicadores.py) hace que
  las primeras ventanas post-warmup tengan max-RSI-previo=50, lo que sesga la divergencia a NO disparar
  ahí (conservador, no espurio).
- **Estado entre trades**: cada apertura (normal/réplica/null) crea un dict nuevo → los contadores del
  TEST 1 no se filtran entre piernas.
- **Wiring CLI**: `--adx-decline`/`--rsi-divergence` setean los flags en memoria antes de correr; los
  defaults en config.py quedan en False (verificado — los flags OFF reproducen el baseline exacto).

## 6. Decisión de NO correr OOB — DE ACUERDO, con razonamiento propio

1. **La guarda OOB es un filtro descendente**: en este proyecto existe para desenmascarar resultados
   in-sample demasiado buenos (P2, V39, V44). El criterio de aceptación es una conjunción — hay que
   pasar en la ventana de diseño Y en OOB. Un test que ya falla en la ventana de diseño (la que le da a
   la hipótesis su mejor oportunidad) no puede ser rescatado por OOB bajo ese criterio.
2. **El margen de rechazo es enorme, no marginal**: TEST 1 cede el 95% del retorno (130.59→6.19) por 38%
   menos DD; TEST 2 cede el 102% (cruza a pérdida, PF<1). Ningún ruido de canasta plausible invierte eso.
3. **El escenario inverso a V44 no aplica**: en V44 el in-sample PASÓ y el OOB reveló el fallo — ahí el
   OOB era decisivo. Aquí ninguna rama del árbol de decisión cambia con el resultado OOB: si OOB saliera
   "mejor", el veredicto seguiría siendo rechazo (falla la ventana de diseño); si saliera peor, ídem.
   Correr análisis cuyo resultado no puede cambiar ninguna decisión es exactamente el hábito que la
   disciplina del proyecto evita.
4. **Percentiles no engañosos**: 73 y 86 están por debajo del umbral que el proyecto trata como señal
   fuerte (≥90); no hay un "percentil sospechosamente alto" que solo OOB pudiera desenmascarar. Y ambos
   son coherentes con el mecanismo documentado (la señal de cruce sigue aportando sobre el azar; el
   exit temprano se come el retorno vía over-trading — 551/530 stops vs 337 del control).
5. **Matiz honesto (no bloqueante)**: el criterio pre-registrado nombraba a OOB como la canasta de
   evaluación; saltarlo se desvía de la LETRA del pre-registro — pero en la dirección conservadora
   (rechazar antes y más barato). No introduce sesgo del lado de aceptación, que es el único lado que el
   pre-registro protege. Correcto dejarlo explícito en el registro, como ya hace el libro.

## 7. VEREDICTO FINAL

- **TEST 1 (ADX cayendo desde pico)**: implementación correcta, causal, con paridad real↔null exacta;
  números reproducidos dígito por dígito (+6.19%, PF 1.033, DD 16.3%, pctl 73, 827 trades). El único
  defecto es cosmético (fragmentación del resumen por el pico en el string), verificado sin efecto en
  los totales. **Los números son confiables. Rechazo correcto.**
- **TEST 2 (divergencia de RSI)**: columnas vectorizadas correctas (oráculo independiente coincide en el
  vector completo; shift(1) hace exactamente lo que debe), paridad real↔null exacta; números
  reproducidos dígito por dígito (−2.62%, PF 0.986, DD 13.1%, pctl 86, 1050 trades).
  **Los números son confiables. Rechazo correcto.**
- **Saltar OOB**: decisión razonable y bien fundada (sección 6) — con la desviación-de-letra del
  pre-registro anotada explícitamente, en la dirección conservadora.
- **Los resultados documentados en el libro pueden entrar al libro tal como están.** Nada que corregir
  en las conclusiones; la única mejora sugerida es la cosmética del motivo del TEST 1 si la carpeta se
  vuelve a usar.

**Artefactos de esta validación**: `wf_resumen_validador_noregresion.json`,
`wf_resumen_test1_validacion.json`, `wf_resumen_test2_validacion.json` y
`test_validacion_analitica.py` (harness de casos a mano — 37 checks, todos pasan; re-ejecutable con
`trading_env/bin/python3 test_validacion_analitica.py` desde esta carpeta), todos en esta carpeta.
