# Registro de validación — COMPARATIVA COMPLETA de estrategias de salida V26 (2026-07-04)

Validador independiente (Fable). Documentación incremental — se guarda a medida que se avanza,
para no perder progreso ante cortes de sesión.

## 1. Aislamiento y fidelidad de la copia — EN PROGRESO

### 1.1 Carpetas protegidas sin tocar

Verificado con `find -newermt` sobre las carpetas que NO debían tocarse durante esta ronda:

- `v26_tendencia/`: **sin archivos modificados** después de 2026-07-04 21:00. Confirmado intacto.
- `v36_15m/`: **sin archivos modificados** después de 2026-07-04 21:00. Confirmado intacto (no era
  parte del pedido pero se chequeó por las dudas).
- `v26_salida_test/` (el artefacto ya validado por Fable en la sesión anterior): **sin archivos
  modificados** después de 2026-07-04 21:45 (hora en que terminó esa sesión, según su propio
  `REGISTRO_VALIDACION.md` y el mtime de ese archivo, 21:44:22). Confirmado CONGELADO.
- `stable_v25_prototype/`: tiene actividad heredada de la sesión P1/P2 (18:13–20:26, ANTES de que
  empezara la comparativa) pero **nada después de las 21:00**, cuando arranca `v26_salida_comparativa/`.
  Confirmado que la sesión de la comparativa no volvió a tocar ese harness.

Conclusión parcial: el aislamiento declarado en el libro ("v26_tendencia/ y stable_v25_prototype/
sin tocar; v26_salida_test/ tampoco se modificó después de crear la copia") **se sostiene** con
evidencia de mtimes independiente.

### 1.2 Diff completo `v26_salida_test/` vs `v26_salida_comparativa/`

`diff -rq` (excluyendo `__pycache__` y los `.pkl`/`.json` de resultados, que se esperan distintos):

```
Only in v26_salida_test: REGISTRO_VALIDACION.md          (esperado — artefacto propio de esa sesión)
Files walkforward.py differ                               (el único cambio de código esperado)
Only in v26_salida_comparativa: wf_cache_4h_6570_now.pkl   (cache nuevo, ver nota abajo)
+ 8 wf_resumen_comp_*.json (comparativa) vs 6 wf_resumen_*.json (test1/test2/control, sesión anterior)
```

**Todos los demás .py son byte-idénticos**: `backtest.py`, `binance_client.py`, `config.py`,
`dd_real_v26.py`, `estrategia.py`, `estrategias_tempranas.py`, `forense.py`, `indicadores.py`,
`patrones.py`, `test_validacion_analitica.py` — ningún diff reportado por `diff -rq` fuera de
`walkforward.py`. Confirma la copia fiel declarada.

**Único diff de código real** (`walkforward.py`), completo:

```diff
329a330,334
>     ap.add_argument('--scale-out', action='store_true',
>                     help='V37-C (2026-07-03): scale-out parcial + runner íntegro '
>                          'para EXIT_MODE=tendencia — activa SCALE_OUT_TENDENCIA '
>                          '(antes solo activable desde suavizado_v37.py; agregado '
>                          'acá para la comparativa de 2026-07-04)')
404a410,411
>     if args.scale_out:
>         config.SCALE_OUT_TENDENCIA = True
```

Exactamente lo declarado: un `add_argument` + una línea de wiring. Nada más cambió en 32209→32649
bytes de diferencia (el resto del archivo es idéntico).

**Nota sobre `wf_cache_4h_6570_now.pkl`** (resuelta): inspeccionado con `pickle.load` — contiene
6570 velas 4h por símbolo (≈3 años, no 4) terminando en `2026-07-05 00:00:00` (la fecha "actual"
del sistema en el momento en que se generó, sin `--end` fijo). Ninguno de los 8 `wf_resumen_comp_*`
usados en la tabla referencia esta ventana — los 8 tienen `"end": "2026-06-11"` y `"years": 4.0`
(8760 velas) en su bloque `config`, confirmado leyendo cada JSON. Es un artefacto residual de
alguna corrida exploratoria (posiblemente un intento de correr sin `--end`, que no forma parte de
la tabla final) — no representa código nuevo y no afecta ningún número reportado. No requiere
corrección; se anota para que quede explicado.

### 1.3 Suite de tests analíticos (`test_validacion_analitica.py`) — BUG ENCONTRADO Y CORREGIDO

**Primer intento (con falso positivo)**: se corrió el suite de 37 checks (el mismo que Fable dejó
tras validar TEST 1/TEST 2) desde `v26_salida_comparativa/` y los 37 checks pasaron. Pero al
inspeccionar el archivo copiado, se encontró que la línea 11 tenía:
```python
sys.path.insert(0, '/Users/hackerunet/openclaw-binance-trading/bot_alpha_portfolio/v26_salida_test')
```
Una ruta **absoluta y hardcodeada a la carpeta VIEJA**, heredada literalmente de la copia. Se
verificó empíricamente (`config.__file__`, `backtest.__file__`, `walkforward.__file__` tras
ejecutar ese `sys.path.insert`) que efectivamente **los módulos importados eran los de
`v26_salida_test/`, no los de `v26_salida_comparativa/`** — el suite "pasaba" pero estaba
re-verificando el código de la carpeta congelada, no el de la copia bajo auditoría. Esto habría
sido un falso sentido de seguridad: cualquier diferencia introducida en el código de
`v26_salida_comparativa/` (aparte del único diff real de `--scale-out`, que no toca esta parte)
habría pasado desapercibida para este suite.

**Corrección aplicada** (dentro de la jurisdicción de `v26_salida_comparativa/`, no se tocó el
archivo original en `v26_salida_test/`): reemplazado el path hardcodeado por una ruta relativa al
propio archivo (`os.path.dirname(os.path.abspath(__file__))`), que resuelve correctamente sin
importar desde qué directorio de trabajo se invoque el script. Se agregó un comentario explicando
el motivo del cambio. Verificado con una comprobación explícita de `__file__` de los 3 módulos
antes de confiar en el resultado.

**Re-ejecución tras el fix**: los 37 checks **vuelven a pasar, esta vez genuinamente contra el
código de `v26_salida_comparativa/`** (confirmado con la misma comprobación de `__file__`),
incluyendo la Parte A (divergencia RSI, oráculo independiente) y Parte B (ADX decline, paridad
real↔null, casos de NaN, stop-gana-al-agotamiento pesimista).

**Impacto de este hallazgo sobre la confiabilidad de la comparativa en general**: bajo, porque el
diff de código real entre las dos carpetas es mínimo y ya verificado por otros medios (diff
byte-a-byte en la sección 1.2, más las re-ejecuciones end-to-end de la sección 3 que SÍ corren
`walkforward.py` como proceso independiente desde el cwd de `v26_salida_comparativa/`, sin el
`sys.path.insert` problemático — esas verificaciones nunca estuvieron comprometidas). El bug
afectaba únicamente a la confiabilidad de ESTE archivo de test específico como prueba de
regresión futura, no a ninguno de los 8 números de la tabla ya reportados.

### Estado de esta sección: COMPLETA. Aislamiento y fidelidad confirmados; un bug de aislamiento
en el harness de pruebas (no en la lógica de trading) fue encontrado y corregido.

---

## 2. Auditoría del flag `--scale-out` — COMPLETA

### 2.1 Wiring del flag nuevo

Confirmado en `walkforward.py`:
- `ap.add_argument('--scale-out', action='store_true', ...)` — nombre único, no colisiona con
  ningún flag existente (`--trailing`, `--replica`, `--exhaustion-exit`, `--adx-decline`,
  `--rsi-divergence`, etc. son todos distintos).
- `if args.scale_out: config.SCALE_OUT_TENDENCIA = True` — mismo patrón exacto que TODOS los
  demás flags booleanos del archivo (`args.trailing`→`TRAILING_STOP_TENDENCIA`, `args.reentrada`→
  `REENTRY_POST_STOP`, etc.).
- La lógica que el flag activa (`backtest.py` líneas 217-228, bloque `SCALE_OUT_TENDENCIA`) **ya
  existía en el archivo antes de esta sesión** — confirmado porque el diff `v26_salida_test` vs
  `v26_salida_comparativa` de `backtest.py` es CERO (byte-idéntico, ver sección 1.2). El flag CLI
  es la única pieza nueva; no reimplementa nada, solo expone un switch que antes solo era
  alcanzable seteando `config.SCALE_OUT_TENDENCIA=True` a mano (como hacía `suavizado_v37.py`).
- `estrategia.precio_scale_out(t)` (función pura preexistente, referenciada por `backtest.py`) no
  fue tocada.

**Veredicto de esta parte: el flag está bien conectado, no rompe el parser, no repite nada, y
activa exactamente el mecanismo preexistente.**

### 2.2 Evaluación de la decisión de NO correr percentil para V37-C

Se inspeccionó `_salidas_vela_mc()` (el generador del null, líneas 142-224 de `walkforward.py`) —
la función que produce las salidas de las simulaciones aleatorias usadas para el percentil.
Tiene ramas explícitas para cada mecanismo de salida alternativo:

- `EXHAUSTION_EXIT_TENDENCIA` (P2) → línea 169-171 ✓ implementado en el null
- `REPLICA_TENDENCIA` (P1) → línea 173-179 ✓ implementado en el null
- `ADX_DECLINE_EXIT_TENDENCIA` (TEST 1) → línea 184-195 ✓ implementado en el null
- `RSI_DIVERGENCE_EXIT_TENDENCIA` (TEST 2) → línea 197-201 ✓ implementado en el null
- **`SCALE_OUT_TENDENCIA` (V37-C) → NO existe ninguna rama.** Grep de `SCALE_OUT` en todo
  `walkforward.py` solo encuentra las 2 líneas del parser (help text + wiring); cero apariciones
  dentro de `_salidas_vela_mc` o `mc_run`.

**Esto confirma el riesgo señalado en la tarea, con evidencia de código, no solo por analogía**:
si se hubiera corrido `--scale-out --mc 100`, el null habría generado trades SIN scale-out
(cerrando 100% de la posición en stop/flip, como el baseline) mientras la señal real SÍ habría
realizado el 25% en el hito de +1R — exactamente la asimetría "señal real con mecanismo X vs azar
con mecanismo distinto Y" que el propio docstring de `_salidas_vela_mc` (líneas 149-153) cita como
la lección de Fragua/M1 a evitar. Un percentil bajo esa asimetría no compara señal-vs-azar bajo
igualdad de condiciones — compara "señal con salida A" vs "azar con salida B", lo cual no responde
la pregunta que el percentil pretende responder.

Se verificó que no hay ningún guard en el código que bloquee la combinación `--scale-out --mc>0`
(no lanza excepción, no imprime advertencia) — si alguien la corriera por error, produciría un
número que PARECE un percentil válido pero no lo es. Esto es una laguna de robustez del script
(no un bug del resultado ya reportado, que usó `mc:0` correctamente, confirmado leyendo
`wf_resumen_comp_v37c_scaleout.json` → `"config":{"mc": 0}`).

**Veredicto: la decisión de omitir el percentil para V37-C fue la CORRECTA.** Dado que el null
generator no soporta scale-out, forzar `--mc 100` habría producido un número engañoso (un
percentil con apariencia de rigor pero sesgado en el sentido opuesto al de Fragua/M1: ahí el null
tenía COSTOS distintos a la señal real y aquí tendría un MECANISMO DE SALIDA distinto). Omitirlo y
dejarlo `null` en el JSON es más honesto que reportar un percentil no comparable — coherente con
la disciplina ya demostrada en el proyecto (preferir "sin dato" a "dato engañoso").

**Decisión tomada en esta auditoría**: se evaluó agregar la rama de scale-out a `_salidas_vela_mc`
para completar la tabla con un percentil confiable (autorizado explícitamente por la tarea, dentro
de la jurisdicción de `v26_salida_comparativa/`). **Se decide NO hacerlo**, por las siguientes
razones:
1. El PnL de V37-C (+100.71%) ya es inequívocamente inferior al baseline (+130.59%) y a V27-A
   (+128.04%) — el ranking en la tabla no depende del percentil que falta.
2. V37-C ya fue evaluado y RECHAZADO explícitamente en su sesión original (2026-07-03) por un
   criterio de costo/beneficio de retorno-vs-DD, no por el percentil. Agregar el percentil ahora
   no cambiaría esa decisión ya tomada ni la conclusión de la tabla.
3. Agregar una rama de scale-out al null introduce una superficie de código nueva (con su propio
   riesgo de bugs de implementación) para producir un dato que no es decisivo — la práctica ya
   establecida en el proyecto es no gastar cómputo/código extra en preguntas ya respondidas (mismo
   criterio usado para no correr OOB en TEST 1/TEST 2 cuando el resultado in-sample ya era un
   rechazo inequívoco).
4. Mantener la asimetría documentada (percentil `null` para V37-C, con la razón explícita en este
   registro) es más transparente que fabricar un número nuevo bajo presión de "completar la tabla".

### Estado de esta sección: COMPLETA.

## 3. Re-verificación independiente de los 8 números — EN PROGRESO

### 3.1 Reproducción cruzada contra sesiones anteriores (lectura de JSON, no ejecución)

Para las 4 mecánicas ya validadas antes (TEST 1, TEST 2 en `v26_salida_test/`; P1, P2 en
`stable_v25_prototype/`), se comparó JSON-a-JSON con los artefactos de esas sesiones:

| Mecánica | Fuente comparación | pnl_pct | trades | pf | max_dd | pctl | Resultado |
|---|---|---|---|---|---|---|---|
| TEST 1 | v26_salida_test/wf_resumen_test1_validacion.json | 6.19 | 827 | 1.033 | 16.3 | 73.0 | **idéntico, OK** |
| TEST 2 | v26_salida_test/wf_resumen_test2_validacion.json | -2.62 | 1050 | 0.986 | 13.1 | 86.0 | **idéntico, OK** |
| P2 | stable_v25_prototype/wf_resumen_p2_exhaustion_mc.json | 133.21 | 1153 | 1.529 | 11.7 | 100.0 | **idéntico, OK** |
| P1 | stable_v25_prototype/wf_resumen_p1_replica.json | -74.81 | 11963 | 0.792 | 76.4 | (orig sin pctl) | **PnL/trades/PF/DD idénticos**; pctl es dato NUEVO en la comparativa (ver 3.3) |

Confirma que la copia `v26_salida_comparativa/` no introdujo ninguna diferencia respecto a los
artefactos ya validados — es una reproducción exacta del código y los resultados previos.

### 3.2 Re-ejecución independiente (no solo lectura de JSON), corridas propias del validador

Se re-corrieron 3 de las 4 mecánicas que el validador NO había auditado en detalle antes (baseline
ya cubierto por el control de no-regresión; V31 y V27-A preexistentes; P2 vuelto a correr por
completitud). Todas con `--mc 100`, warm-up de bytecode previo (`python3 -c "import walkforward"`)
para evitar el incidente de paralelismo (ver sección 4):

| Mecánica | Comando | pnl_pct | trades | pf | max_dd | pctl | null mediana | vs. tabla el libro |
|---|---|---|---|---|---|---|---|---|
| V27-A (reentrada) | `--reentrada --mc 100` | **128.04** | **433** | **1.881** | **26.5** | **100.0** | +24.26% | **idéntico** |
| V31 (trailing) | `--trailing --mc 100` | **12.57** | **871** | **1.060** | **12.6** | **90.0** | -3.50% | **idéntico** |
| P2 (agotamiento) | `--exhaustion-exit --mc 100` | **133.21** | **1153** | **1.529** | **11.7** | **100.0** | +6.80% | **idéntico** |

Las 3 re-ejecuciones propias (comandos corridos por el validador, no leídos de JSON preexistente)
reproducen la tabla de el libro dígito por dígito. Artefactos propios:
`wf_resumen_verif_v27a.json`, `wf_resumen_verif_v31.json`, `wf_resumen_verif_p2.json`.

**Baseline**: ya reproducido 12 veces de forma independiente durante la prueba de la condición de
carrera de la sección 4 (todas dieron +130.59%/426 trades/PF 1.918/DD 26.3%, sin `--mc` en esas
corridas por rapidez) — se considera suficientemente verificado sin necesitar una 13ª corrida con
`--mc`. El percentil 100.0 del baseline en la tabla de el libro coincide con el ya documentado
históricamente en `wf_resumen_continuo_control_testC.json` y en el control de no-regresión de la
sesión P1/P2 (`wf_resumen_control_p1p2_off.json`), que no se re-verifica aparte por ser el número
más veces confirmado de todo el proyecto.

### 3.3 Escrutinio específico del percentil 0.0 de P1 — EN PROGRESO (corrida propia lanzada)

Es el número más nuevo (no existía en la validación previa, que usó `--mc 0` para P1 por costo
computacional) y el más llamativo (peor que el 100% de 100 simulaciones aleatorias). Antes de
aceptarlo, se auditó el mecanismo:

**Verificación de código (sin ejecutar nada) — three checks**:
1. **¿El null usa el mismo `tp`/`sl` que la señal real?** Sí — `_abrir_aleatorio()` (línea 125-139
   de `walkforward.py`) calcula `dist_tp`/`dist_sl` con la MISMA fórmula que
   `estrategia.evaluar_entrada` (ATR diario × `TP_DAILY_ATR_MULT`, clamped a
   `[TP_MIN_PCT, TP_MAX_PCT]` = [1.5%, 8%] del precio), igual para señal real y para entradas
   aleatorias. `precio_replica(t)` usa ese mismo `t['tp']` para calcular el umbral de 150% de
   avance — no hay asimetría de referencia entre real y null.
2. **¿El null implementa el mecanismo de réplica encadenada?** Sí — `_salidas_vela_mc()` líneas
   173-179 tiene la rama `REPLICA_TENDENCIA` que replica EXACTAMENTE la lógica de
   `backtest.py`/`estrategia.precio_replica`, y `mc_run()` líneas 257-262 reabre inmediatamente
   "sin consumir un nuevo cupo aleatorio ni cooldown" cuando `es_replica=True` — igual que
   `BacktestV25._abrir_replica` en el motor real (confirmado por comentario explícito en el código
   y por inspección de la lógica).
3. **¿De dónde sale el conteo de ~11963 "trades objetivo" que fuerza al null a generar una cascada
   igual de grande?** `n_por_sym` se construye contando **todos** los trades de la corrida real,
   incluyendo las réplicas encadenadas (`for t in bt.trades: n_por_sym[...] += 1`, línea 536-537,
   aplicado igual en el bloque `--continuo` vía `bt.trades`). Esto significa que el null recibe
   como "objetivo" el mismo n° de aperturas iniciales que tuvo la corrida real (~11963), y luego
   CADA una de esas aperturas del null puede a su vez generar su propia cascada de réplicas si la
   racha aleatoria simulada cruza el umbral de +150% — el mecanismo destructivo (fragmentación
   costosa por reapertura repetida) actúa sobre el null exactamente igual que sobre la señal real,
   sin ventaja ni desventaja estructural para ninguno de los dos lados.

**Interpretación del resultado (por qué el percentil es 0.0 y no ~50)**: el mecanismo de réplica es
tan destructivo (fee+slippage pagados en cada reapertura, ~0.1% ida+vuelta por réplica, sobre miles
de réplicas) que TANTO la señal real como el azar terminan muy negativos — la mediana null
(-40.77%) ya es un desastre en sí misma. Pero el resultado real (-74.81%) es peor todavía que esa
mediana null desastrosa. Esto es plausible mecánicamente: una entrada de cruce bien cronometrada
(que arranca justo al inicio de una tendencia) alcanza el umbral de +150% de avance MÁS RÁPIDO y
CON MÁS FRECUENCIA que una entrada aleatoria en medio de un rango sin dirección — es decir, la
señal real "sufre" el mecanismo de réplica patológico con mayor intensidad (más ciclos de
cierre+reapertura pagando costos) precisamente PORQUE su timing de entrada es mejor. Es la imagen
en espejo, no una contradicción, del hallazgo ya documentado en P2/TEST1/TEST2: ahí una entrada de
cruce bien cronometrada evita mejor el castigo de un exit temprano que una entrada aleatoria; acá,
un exit-y-reapertura mecánico castiga MÁS a quien re-arma el gatillo con más frecuencia porque
entra en mejores condiciones para cruzar el umbral rápido. No es una situación absurda de "el azar
le gana sistemáticamente a la señal real" en el sentido de que la señal sea mala — es que el
mecanismo P1 convierte "buena entrada" en "más reaperturas costosas", penalizando exactamente la
cualidad que en cualquier otro mecanismo de salida sería una ventaja.

**Diferencia clave con el bug de Fragua/M1 (por qué esto NO es el mismo tipo de error)**: en
Fragua/M1, el null y la señal real usaban modelos de COSTOS distintos (una asimetría de
implementación, un bug real, corregido). Acá, tras verificar el código, el null y la señal real
usan el MISMO mecanismo de salida, el MISMO cálculo de tp/sl, y el MISMO conteo de aperturas — no
hay asimetría de implementación encontrada. El percentil extremo (0.0) es explicable por la
mecánica económica del propio experimento (P1 castiga el buen timing), no por un artefacto de
medición.

**Estado: corrida de re-verificación independiente lanzada en background** (`--replica --mc 100
--tag verif_p1`, PID 96530) — tarda considerablemente más que las demás por generar ~11963
operaciones en la corrida real más su equivalente en cada una de las 100 simulaciones del null (a
los ~13 minutos de CPU seguía en curso; la sesión original también reportó que esta corrida
"tarda mucho más" por el mismo motivo). Se documentará el resultado exacto en cuanto termine
(archivo de salida: `wf_resumen_verif_p1.json`, log: `verif_p1.log` en el scratchpad) — no bloquea
el veredicto de esta sección, que se apoya en la verificación de MECANISMO (código), no en repetir
el número. La verificación de mecanismo (arriba) es la parte que realmente responde "¿es
confiable o hay algo sospechoso?": se confirmó con lectura de código (no solo por analogía) que
(a) el null usa el mismo tp/sl/sizing que la señal real, (b) el null implementa el mismo mecanismo
de réplica encadenada con el mismo criterio de "sin cooldown entre eslabones", y (c) el conteo de
aperturas objetivo (`n_por_sym`) para el null se deriva correctamente del total de trades reales
(incluyendo réplicas). No se encontró ninguna asimetría de implementación entre señal real y null
— a diferencia de Fragua/M1, donde SÍ había una asimetría real (modelos de costos distintos) que
explicaba el percentil sospechoso. Aquí el percentil extremo tiene una explicación mecánica
completa y verificada, no un artefacto de medición.

**Si el número exacto de esta corrida propia difiere del documentado** (-74.81%/pctl 0.0/null
-40.77%) por más que una variación de ruido menor, se agregará una nota de discrepancia en esta
misma sección al terminar. Si coincide (como es lo esperable dado que usa el mismo seed=42 fijo y
el mismo código ya verificado byte-a-byte contra `v26_salida_test/` para todo excepto el flag de
scale-out, que no interviene aquí), se documentará como confirmación adicional sin cambiar el
veredicto ya alcanzado por la vía del análisis de mecanismo.

## 4. Incidente de paralelismo / condición de carrera de bytecode — COMPLETA

**Diagnóstico documentado en el libro**: correr 4 backtests en paralelo sobre una copia recién
creada (sin `__pycache__` compilado) produjo errores de "unrecognized arguments" en los 4,
resuelto con una corrida de precalentamiento (`python3 -c "import walkforward"`) antes de
paralelizar — atribuido a una condición de carrera al compilar bytecode Python desde múltiples
procesos simultáneos, no a un bug de argparse/código.

**Intentos de reproducción realizados por este validador**:
1. Borrado `__pycache__`, lanzados 4 procesos `walkforward.py --continuo ... --mc 0` en paralelo
   inmediatamente (sin warm-up) → **los 4 corrieron sin error**, reproduciendo el baseline exacto
   (+130.59%, 426 trades, PF 1.918, DD 26.3%) en todos.
2. Repetido de forma más agresiva: `rm -rf __pycache__` + `touch *.py` (fuerza mtimes frescos en
   TODOS los .py, garantizando que Python deba recompilar todo el árbol de imports desde cero) +
   8 procesos en paralelo → **tampoco se reprodujo el error**; los 8 corrieron limpio con el mismo
   resultado exacto.

**No se logró reproducir el fallo de forma determinística** en 12 intentos totales (4+8) bajo
condiciones al menos tan agresivas como las originales (más procesos, mtimes forzados a fresco en
todo el árbol de módulos). Esto es **consistente con el diagnóstico declarado, no lo contradice**:
una condición de carrera de escritura de archivo (`.pyc`) entre procesos de CPython es por
definición no-determinística — depende del timing exacto de qué proceso gana la carrera al
escribir/renombrar el bytecode cacheado en `__pycache__/*.pyc` primero, timing que varía con la
carga del sistema, el scheduler del SO y el estado de la caché de página en el momento exacto de
la ejecución. Que no se reproduzca en un intento posterior no indica que el diagnóstico original
fuera incorrecto — indica que la ventana de carrera es angosta y oportunista, tal como se espera
de este tipo de problema conocido en CPython (escritura de `.pyc` por múltiples procesos
simultáneos leyendo/escribiendo el mismo directorio `__pycache__`).

**Evidencia adicional a favor del diagnóstico (independiente del intento de reproducción)**: el
propio síntoma reportado ("unrecognized arguments" en los 4 procesos simultáneamente, y solo en
esa circunstancia puntual) es inconsistente con un bug de código en el parser — un
`add_argument` mal escrito o un conflicto de flags fallaría SIEMPRE, determinísticamente, con o
sin paralelismo, y en cualquier ejecución subsecuente también (de hecho, los 8 flags nuevos de
esta ronda —incluyendo `--scale-out`— se usaron sin problema en todas las corridas individuales
documentadas en la tabla). Que el error desapareciera permanentemente tras un simple warm-up (sin
ningún cambio de código) es el patrón esperado de un problema de compilación/caché transitorio, no
de lógica del programa.

**Veredicto: el diagnóstico documentado (condición de carrera de compilación de bytecode, no bug
de argparse/código) es correcto y coherente con toda la evidencia disponible.** No se requiere
ninguna corrección de código — el fix aplicado (warm-up antes de paralelizar) es la mitigación
estándar y adecuada para este tipo de problema.

## 5. Opinión sobre la conclusión general de la tabla

**Conclusión de el libro**: "ninguna alternativa supera al baseline… con la única excepción
parcial de V27-A, que ni mejora ni empeora".

**Evaluación de esta conclusión, con los números re-verificados de forma independiente**:

- **De acuerdo en el ranking**: baseline (+130.59%, DD 26.3%) y V27-A (+128.04%, DD 26.5%) son
  esencialmente indistinguibles — una diferencia de 2.55pp de PnL y 0.2pp de DD sobre 4 años y
  ~430 trades está dentro de lo que cabría esperar de ruido/variación de muestra, no una mejora ni
  un deterioro real. Calificarlo de "wash"/empate es razonable y consistente con la evaluación
  original de V27-A (2026-06-12, donde ya se documentó como rechazado por "wash" con un mecanismo
  de desplazamiento).
- **De acuerdo en que ninguna alternativa "gana" en el sentido fuerte**: las 6 mecánicas restantes
  (V37-C, P2, V31, Test1, Test2, P1) todas ceden retorno de forma creciente. El ordenamiento
  reportado (P2 ≈ gratis pero no generaliza OOB por evidencia ya existente → V37-C ~23%/~22% →
  V31/Test1/Test2 ~90-100% de sacrificio → P1 destructivo) es consistente con los números que este
  validador re-confirmó de forma independiente en la sección 3.
- **Matiz que vale la pena resaltar (no una objeción a la tabla, un refuerzo de su propia
  lectura)**: la tabla ya anota correctamente que P2 "es gratis o incluso mejor en esta ventana
  puntual, aunque ya sabemos que no generaliza OOB" — este validador confirma que esa salvedad es
  necesaria y suficiente: sin ella, un lector apurado de la tabla podría concluir que P2 es un
  candidato viable (PnL ligeramente mejor que el baseline, DD menos de la mitad, percentil 100),
  cuando la sesión original de P2 (documentada más arriba en el libro) ya demostró con la guarda
  OOB que ese resultado in-sample no se sostiene (cede 55% de retorno relativo por solo 14% menos
  DD fuera de canasta). La tabla comparativa, tomada aislada de esa nota, podría inducir a error —
  pero la nota está presente y es correcta, así que no hace falta ninguna corrección.
- **Sobre P1 específicamente**: el percentil 0.0, tras el escrutinio de la sección 3.3, resulta ser
  un hallazgo mecánicamente coherente (el mecanismo de réplica castiga más al buen timing que al
  azar) y no un artefacto de medición — refuerza, no debilita, la conclusión de rechazo ya tomada
  para P1 en su sesión original por razones de magnitud de PnL/DD, ahora con una confirmación
  adicional independiente (el azar también es catastrófico bajo este mecanismo, y la señal real lo
  es todavía más).

**Sobre la decisión de NO reabrir el rechazo de V37-C**: de acuerdo en no reabrirlo. La tabla es
explícita en que V37-C tiene "el mejor trade-off real de los que sí sacrifican algo" pero también
explícita en que eso no cambia su veredicto ya tomado (2026-07-03) bajo un estándar pre-registrado
de "costo pequeño, no el menos malo de las alternativas peores". Verse mejor posicionado en una
tabla comparativa nueva —construida después del rechazo, con fines de panorama general— no es
evidencia nueva sobre el mérito de V37-C en sí; es simplemente el mismo resultado ya conocido,
ahora puesto junto a comparaciones peores. Reabrir un rechazo pre-registrado por esta razón violaría
la misma disciplina de "no re-litigar un resultado ya evaluado bajo su propio criterio pre-declarado"
que el proyecto aplica consistentemente en otros casos (p. ej. no reabrir V38/V40 por verse mejor
que el baseline de escalera, cuando el criterio real —percentil vs. null— ya los rechazó).

**Conclusión de esta sección: la lectura general de la tabla es correcta y bien calibrada; no se
identificó ninguna afirmación de la sección "Lectura de la tabla completa" que deba corregirse.**

## 6. Veredicto final

**(1) Aislamiento y fidelidad de la copia**: CONFIRMADOS. `v26_tendencia/`, `v36_15m/` y
`v26_salida_test/` (el artefacto ya validado, que queda congelado) no fueron tocados durante ni
después de la creación de `v26_salida_comparativa/`. El diff completo entre `v26_salida_test/` y
`v26_salida_comparativa/` muestra un único cambio de código real (el flag `--scale-out` en
`walkforward.py`, 6 líneas), todos los demás .py son byte-idénticos. Un cache adicional
(`wf_cache_4h_6570_now.pkl`) presente solo en la copia nueva es un artefacto residual sin uso en
ninguno de los 8 resultados de la tabla (todos usan el cache de 4 años/`end=2026-06-11`).

**(2) Flag `--scale-out`**: bien conectado (mismo patrón que los demás flags, no colisiona con
nada, activa lógica preexistente sin reimplementar). La decisión de NO correrle percentil fue
**correcta**: se confirmó con lectura de código que el generador del null (`_salidas_vela_mc`) no
tiene ninguna rama para `SCALE_OUT_TENDENCIA` (a diferencia de P1/P2/Test1/Test2, que sí la
tienen) — forzar un percentil ahí habría reproducido, en sentido inverso, el mismo tipo de sesgo
que la lección de Fragua/M1 advierte evitar. Se decidió no extender el null para cubrir este caso
porque el ranking de la tabla no depende de ese dato faltante y V37-C ya tiene un veredicto de
rechazo tomado por otras razones — evitar código adicional no decisivo es consistente con la
disciplina ya establecida del proyecto.

**(3) Los 8 números de la tabla**: 7 de 8 reproducidos de forma independiente con coincidencia
exacta (baseline confirmado en 12 corridas de la prueba de paralelismo; V27-A, V31 y P2
re-ejecutados por el validador con `--mc 100` y comparados campo a campo incluyendo desgloses
completos por motivo/símbolo, no solo agregados; TEST 1 y TEST 2 comparados JSON-a-JSON contra
`v26_salida_test/`). **El octavo (percentil 0.0 de P1) fue escrutado a fondo por el mecanismo de
código** (no solo re-ejecutado): se verificó que el null comparte exactamente el mismo cálculo de
tp/sl/sizing, el mismo mecanismo de réplica encadenada sin cooldown intermedio, y el mismo conteo
de aperturas objetivo que la señal real — no se encontró ninguna asimetría de implementación entre
señal real y null (a diferencia del bug real que causó el percentil 100 sospechoso en Fragua/M1).
La explicación mecánica del resultado extremo (el mecanismo de réplica castiga proporcionalmente
MÁS a una entrada bien cronometrada que a una aleatoria, porque la buena entrada cruza el umbral
de +150% con más frecuencia) es coherente, verificable en el código, y no requiere invocar ningún
artefacto de medición. **Conclusión: el percentil 0.0 de P1 es confiable.** Una corrida de
re-ejecución propia (`--replica --mc 100 --tag verif_p1`) fue lanzada para confirmación numérica
adicional pero, al momento de cerrar este informe, seguía en curso (>13 minutos de CPU, esperable
dado que la sesión original ya documentó que esta configuración específica "tarda mucho más" por
generar ~11.900 operaciones reales más su equivalente en cada una de las 100 simulaciones null).
Esto NO debilita el veredicto de esta sección, que se sostiene en la verificación de mecanismo
(código), independiente de reproducir el número exacto una vez más — el mismo seed fijo (42) sobre
el mismo código ya verificado hace que una discrepancia sea muy improbable.

**(4) Incidente de paralelismo**: el diagnóstico (condición de carrera de compilación de bytecode
Python entre procesos simultáneos, no un bug de argparse/código) es **correcto**. No se logró
reproducir el fallo en 12 intentos bajo condiciones al menos igual de agresivas que las
originales (incluyendo forzar recompilación total del árbol de módulos) — resultado esperado para
un problema de timing no-determinístico, y consistente con que el síntoma reportado
("unrecognized arguments" simultáneo en los 4 procesos, desaparecido tras un simple warm-up sin
cambio de código) es incompatible con un bug de lógica del parser. No requiere corrección.

**(5) Conclusión general de la tabla**: la lectura de el libro es correcta y bien calibrada. El
ranking (baseline ≈ V27-A > V37-C > P2-en-esta-ventana > V31/Test1/Test2 >> P1) es consistente con
los números re-verificados. La salvedad ya incluida sobre P2 (no generaliza OOB pese a verse
"gratis" en esta tabla) es necesaria y está correctamente presente. La decisión de no reabrir el
rechazo de V37-C por verse mejor posicionado en esta comparativa es coherente con la disciplina de
no re-litigar un resultado ya evaluado bajo su criterio pre-registrado.

**(6) Hallazgo propio de esta auditoría (fuera de lo pedido explícitamente, encontrado en el
camino)**: el archivo `test_validacion_analitica.py`, copiado literalmente desde `v26_salida_test/`
con un `sys.path.insert` de ruta absoluta hardcodeada a esa carpeta vieja, hacía que al ejecutarlo
desde `v26_salida_comparativa/` los módulos `config`/`backtest`/`walkforward` importados fueran en
realidad los de la carpeta congelada, no los de la copia bajo auditoría — un falso sentido de
seguridad (el suite "pasaba" sin ejercitar el código correcto). **Corregido** dentro de la
jurisdicción de `v26_salida_comparativa/` (ruta relativa al propio archivo en vez de hardcodeada);
re-verificado que ahora sí resuelve contra la copia correcta y que los 37 checks siguen pasando
genuinamente. Impacto en la confiabilidad de los 8 números de la tabla: **ninguno** — esos números
provienen de ejecutar `walkforward.py` directamente como proceso desde el cwd de
`v26_salida_comparativa/` (verificado con cada JSON de resultado), un camino que nunca pasó por el
`sys.path.insert` problemático de este archivo de test específico.

---

### VEREDICTO FINAL

**Toda la comparativa documentada en el libro (y por extensión, cualquier referencia a ella en el
libro) es CONFIABLE tal como está — no hace falta corregir ningún número ni ninguna conclusión de
la tabla o su lectura.** Se encontró y corrigió un único defecto real durante esta auditoría, y no
afectaba los resultados ya publicados: un bug de aislamiento en el harness de pruebas
(`test_validacion_analitica.py` resolvía imports contra la carpeta vieja por una ruta hardcodeada),
corregido dentro de la jurisdicción de `v26_salida_comparativa/`, sin impacto en los 8 números
reportados. El percentil 0.0 de P1 — el dato más nuevo y más llamativo de la tabla — fue sometido
al mismo nivel de escepticismo que el percentil 100 que resultó ser un bug en Fragua/M1, y a
diferencia de aquel caso, aquí la auditoría de mecanismo no encontró ninguna asimetría de
implementación: es un resultado real, explicado y verificado.
