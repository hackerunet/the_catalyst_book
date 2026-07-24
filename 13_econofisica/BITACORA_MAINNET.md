# Bitácora de producción — El forward test narrado en vivo
> Material para el libro ("The Catalyst"). NO es un registro diario obligatorio: son
> instantáneas de días con enseñanza. Cada entrada documenta QUÉ pasó, QUÉ decisión se
> tomó y POR QUÉ fue buena o mala, con evidencia — no con la conclusión de que los dos
> motores son el edge dada por sentada.

---

## Día 1 — 2026-07-10 · "El bautismo de fuego fue un percentil 95 de chop"

**Contexto**: los dos motores (V26 4h + V36 15m) llevaban ~17 h operando dinero real (arranque
2026-07-09, balance $530.71). El operador vio en `/estado` una posición SHORT de LINK en rojo, le
pareció que "el bot detectaba mal la tendencia" (4h lateral, 15m alcista a ojo), y **cerró posiciones
manualmente**. Con el JSON real de operaciones (bajado de GCS el mismo día) el cuadro exacto resultó
distinto de la primera impresión, y esa corrección ES parte del aprendizaje del Día 1:

- **LINK (V26, 4h, SHORT) NO la cerró el operador — tocó su stop sola** (`STOP DE PROTECCIÓN`, −$1.40).
- Lo que el operador **sí** cerró a mano fueron **4 LONGs de V36 (15m)**: BNB, SOL, ETH, XRP — abiertas
  LONG precisamente porque el 15m estaba alcista (V36 leyó la subida y se puso largo, no corto).

O sea: la sensación de "puros shorts peleando contra el rally" no era el cuadro real. El único short (LINK,
4h) murió solo en el stop; los 4 trades que el operador tocó eran LONGs a favor de la subida de 15m.

**Segunda corrección honesta — la pérdida FUE mucho más chica que la sensación.** Sumando el PnL real de las
5 operaciones del JSON: LINK −$1.40, BNB −$0.24, SOL −$0.09, ETH +$0.30, XRP −$0.30 = **−$1.74 realizado**
(≈ −0.33 % de la cuenta), más una posición ETH aún abierta. La impresión de "perdí como $10 / bajé a ~$486"
no la respalda el registro de operaciones — el balance real apenas se movió. Esto es en sí una lección del
Día 1: **la magnitud EMOCIONAL de la pérdida (ver todo en rojo a la vez) fue varias veces mayor que la
magnitud REAL** (−0.33 %). La aversión a la pérdida agranda lo que el número desmiente.

### Qué mostró la evidencia (no la impresión)

**1. El detector NO falló — el mercado hizo whipsaw en el peor 5-10% de la historia.**
Corriendo el código EXACTO del bot sobre las velas reales de las 72 h previas:

| | flips de tendencia en 72 h |
|---|---|
| ETH/SOL/BNB/XRP (4h) | 0-1 (tranquilos) |
| ADA (4h) | 3 |
| **LINK (4h)** | **4** (LATERAL→SHORT→LATERAL→SHORT→LATERAL) |
| V36 (15m) | abrió 4 LONGs (BNB/SOL/ETH/XRP) — el 15m sí alineó al alza |

Referencia de 4 años con el mismo código: **mediana = 1 flip/72 h, p90 = 3, p99 = 5**. LINK con 4 y ADA
con 3 = tramo de chop entre el percentil 90 y 99. No es que el bot "leyera mal": su definición de
tendencia se cumplió al cierre de cada vela (el SHORT de LINK se verificó vela por vela el día anterior)
y el régimen se dio vuelta a la vela siguiente, varias veces. **Eso ES un whipsaw**, el modo de falla
conocido y presupuestado del trend-following (por eso el win-rate es ~18 %). El operador arrancó mainnet
justo en el peor tramo posible para un seguidor de tendencia — mala suerte de calendario, no de código.

**2. Los dos motores NO se contradijeron: leen dos relojes distintos.**
El ojo ve precio subiendo intradía en 15m; el SHORT que preocupó al operador (LINK) era de 4h, donde el
régimen daba vuelta a vuelta. De hecho V36 (15m) LEYÓ la subida y abrió LONG en BNB/SOL/ETH/XRP — no peleó
contra el rally, se subió a él. La confusión fue mezclar el short de 4h (LINK, que además murió solo en el
stop) con la lectura de 15m: son dos motores en dos relojes distintos, no una contradicción.

**3. El día real fue MILD (−$1.74), no la cola — pero conviene saber cómo se ve un día malo de verdad.**
La pérdida realizada del Día 1 (−$1.74 ≈ −0.33 %) está cerca del día MEDIANO, no de la cola. Para calibrar
expectativas, así se ve la distribución diaria del backtest honesto (combo V26+V36, $530, riesgo 0.25 %,
1.460 días ≈ 4 años) — el Día 1 NO fue ninguno de los días malos de abajo:

| Métrica | Valor |
|---|---|
| Día mediano | **$0.00** ← el Día 1 real (−$1.74) queda por aquí |
| Percentil 5 diario | −$10.39 |
| Percentil 1 diario | −$22.88 · peor día en 4 años: −$67.55 |
| Días con pérdida ≥$10 | 75 de 1.460 = **~19 por año** (5.1 % de los días) |
| Resultado a 4 años **conteniendo** esos 75 días | **+$702.55** |
| Peor drawdown en $ del combo | **$129** (piso $470 desde $530) |

**Caveat honesto (los días malos se agrupan)**: cuando SÍ llegue un día de cola (≤−$10, ~19 al año), los
30 días siguientes tienen mediana **−$4.83** y solo el 42 % son positivos. El chop viene en tandas. Lo
estadísticamente esperable tras un día malo NO es un rebote inmediato, sino más días planos/rojos antes de
que pague. Quien no tolere eso, la palanca honesta es el DIAL (bajar riesgo 0.25 %→0.167 %, que corta
pérdidas Y ganancias en proporción), nunca intervenir trade a trade.

### Las 5 operaciones, con números reales (JSON de trades + camino de precio público)

Cada trade traído del JSON real de la cuenta, y su camino DESPUÉS del cierre reconstruido con klines
públicos de Binance Futures (engine-safe, no toca la cuenta). La pregunta central del operador: *¿habría
tocado el stop si la dejaba?*

| # | Operación | Entrada | Stop | Cerró @ | PnL real | ¿Tocó stop tras el cierre? | Si la dejaba, hoy |
|---|---|---|---|---|---|---|---|
| 1 | **LINK SHORT** (V26 4h) | 7.728 | 8.005 (+1.27 %) | **8.013 (STOP auto)** | **−$1.40** | ya tocó — así cerró | −$0.95 (volvió a bajar) |
| 2 | BNB LONG (V36) | 575.84 | 562.96 (−2.23 %) | 574.04 (manual) | −$0.24 | **no** (stop a 2 % de distancia) | +$0.04 |
| 3 | SOL LONG (V36) | 79.04 | 76.31 (−3.45 %) | 78.92 (manual) | −$0.09 | **no** | −$0.55 |
| 4 | ETH LONG (V36) | 1778.23 | 1724.9 (−3.0 %) | 1792.58 (manual) | **+$0.30** | **no** | +$0.31 |
| 5 | XRP LONG (V36) | 1.1141 | 1.0800 (−3.06 %) | 1.1069 (manual) | −$0.30 | **no** | −$0.34 |

**Lo que la evidencia dice de cada tipo de decisión:**

**LINK (el único short, y NO fue del operador): el stop hizo su trabajo, y el whipsaw se lo comió limpio.**
El precio pegó un pico a 8.013 —justo lo suficiente para disparar el stop en 8.005— y **enseguida volvió
a bajar a 7.926**. Es el whipsaw de manual: la mecha sube a tocar el stop y se devuelve. Si no hubiera
stop, hoy la posición estaría en −$0.95 (menos mala que el −$1.40 realizado) — pero seguiría negativa, con
el 4h ya en LATERAL. El stop no "se equivocó": acotó la pérdida a −0.26 % del balance, que es exactamente
su función. Ese −$1.40 es la **prima de seguro**, no un error.

**Los 4 LONGs que el operador cerró: NINGUNO estaba cerca de su stop.** Los stops estaban 2-3.5 % abajo;
el operador cerró los cuatro flotando a ±0.5 % de la entrada. La sensación de "todas iban a tocar el stop"
**no era cierta para estos cuatro** — estaban lejísimos del stop, ni de cerca. (La que sí tocó stop fue
LINK, que el operador no tocó.)

**En dinero, los cierres manuales fueron ~neutros esta vez:**
- Realizado cerrando: −0.24 − 0.09 + 0.30 − 0.30 = **−$0.34**
- Si los dejaba hasta ahora: +0.04 − 0.55 + 0.31 − 0.34 = **−$0.54**
- Cerrar ahorró ~**$0.20**. Casi gratis — porque es un día de CHOP y ninguno iba camino a un monstruo; en
  lateral, cerrar cerca de breakeven no cuesta casi nada.

### Por qué "el costo de perderlas > el costo del stop" — y por qué HOY no mordió

El operador lo intuyó bien como PRINCIPIO, y los números lo explican con precisión:

- El **stop es un costo conocido, chico y acotado**: −$1.40 máximo por posición (−0.26 % de la cuenta). Es
  la prima de seguro. Igual para todas, siempre.
- **Cerrar antes** convierte una posición ABIERTA —que conserva a la vez el piso del stop Y la opción sobre
  un monstruo— en una pérdida chica REALIZADA con **cero** upside. Lo que entregas es el boleto de lotería
  de la cola derecha.
- En un sistema donde **el 100 % de la ganancia viene de ~5 monstruos al año** (cada uno +$30 a +$150 en una
  cuenta de $500, análisis de giveback de V26), el valor esperado de ese boleto es MAYOR que los −$1.40 que
  intentas evitar. Por eso, **como política**, perder la posición cuesta más que comerte el stop.
- **PERO hoy, en el escenario actual, no mordió** — y los datos lo prueban: es un día de chop (LINK flipeó
  4× en 72 h, percentil 90-99 de whipsaw; los trends de 15m de V36 estaban débiles). En lateral el boleto
  vale casi nada porque no se está formando ningún monstruo. Por eso cerrar costó solo $0.20. **La tesis es
  sobre el valor esperado a lo largo de MUCHOS días, no sobre un día de chop puntual.**

**El nudo de la lección**: no se puede distinguir un día de chop del comienzo de un monstruo en tiempo real
(AUC 0.5 al entrar, V59; 96 % de los ganadores pasan por ±0 % antes de despegar, V57). Los días que cierras
"para no comerte el stop" serán, alguna vez, el día en que matas al monstruo que paga el año. El −$1.40 del
stop es seguro barato; el monstruo no capturado es caro. **La acción puntual de hoy fue defendible (chop,
ahorró $0.20); la política de cerrar siempre sería cara, y esa es precisamente la diferencia que el Día 1
enseña.**

### Estado de la cuenta al cierre del Día 1
PnL realizado del día: **−$1.74** (5 operaciones cerradas: 1 stop automático de LINK + 4 cierres manuales de
V36) sobre un balance de arranque de $530.71 → balance ≈ **$529** más una posición ETH aún abierta.
Cortacircuitos duro en $300 (piso histórico del backtest: $470, nunca alcanzado) · monitor de salud activo
(avisa si pérdida masiva >5 % o MDD-90d se acerca al gate). 1 día no valida ni refuta nada — el forward test
ES esto; el veredicto honesto llega con semanas.

### Resumen de aprendizajes del Día 1 (para el libro)
1. **La pérdida sentida > la pérdida real.** Ver todo en rojo a la vez pesó como "−$10"; el registro dice
   −$1.74 (−0.33 %). La aversión a la pérdida distorsiona la magnitud — el número es el ancla, no la emoción.
2. **El único que tocó stop (LINK) no lo cerró el operador — lo cerró el sistema, y bien.** El stop acotó a
   −$1.40 (−0.26 %) un whipsaw de percentil 90-99. Eso ES el diseño funcionando, no fallando.
3. **Los 4 cierres manuales no estaban ni cerca de su stop** (2-3.5 % de distancia). La intuición "iban a
   tocar el stop" no aplicaba a esos cuatro; aplicaba a LINK, que el operador no tocó.
4. **En chop, cerrar cerca de breakeven es casi gratis** ($0.20 esta vez). Como política de todos los días,
   cerca del comienzo de un monstruo, es caro — y no se puede distinguir un caso del otro en tiempo real.
5. **Decisión del operador de aquí en adelante: dejar correr.** Es la única compatible con el edge medido.

---

## Fin de la Semana 1 (parcial) — 2026-07-12 · "Plano es exactamente lo que debía verse"

**Contexto**: el reporte semanal automático (monitor_salud.py) disparó su primer resumen. Ojo con el marco:
el go-live fue el 2026-07-09, así que **son ~3 días, no 7** — el propio reporte lo dice ("historia
insuficiente (3d) — se necesita ≥7d"). El veredicto de "semana 1" real necesita ≥7 días; esto es un corte
temprano. La cadencia dominical del monitor cayó cerca del arranque.

### Los números (V26 + V36, mainnet, dinero real)
| | |
|---|---|
| Equity | $527.36 (desde $530.71 al arranque = **−$3.35, −0.63%**) |
| PnL realizado | **−$3.64** en 9 operaciones cerradas (≈ **−$0.40 por operación**) |
| No realizado | +$0.34 (3 posiciones abiertas, mezcladas) |
| Posiciones abiertas | ETH LONG (+$0.33) · SOL SHORT (−$0.35) · ADA SHORT (+$0.35) |
| MDD-90d | 0.8% (gate ≤25%) |
| Infra | v26 OK · v36 OK · disco 29% |

### Conclusiones (fin de semana 1)

1. **Tres días es RUIDO puro, y verlo plano es exactamente lo predicho.** Los horizontes que medí antes del
   despliegue lo dicen sin ambigüedad: a 1 mes el resultado es una moneda al aire (46% positivo); a 3 días no
   dice literalmente nada. Un −0.63% de equity en 72 horas está dentro de la banda de ruido esperada. **No
   hay nada que concluir sobre el edge — y ESA es la conclusión correcta.** Ni celebrar el ~plano ni asustarse
   por el −$3.64.

2. **El perfil de pérdida-topada funciona en dinero real.** 9 operaciones, −$0.40 promedio, cero blow-ups.
   Si las 9 hubieran sido stops completos serían ~−$12 (a 0.25%/trade); fueron −$3.64 → hubo mezcla de
   ganancias y pérdidas chicas, netas levemente negativas. El stop hace su trabajo: las pérdidas son chicas y
   contenidas, tal como el backtest prometía (peor perdedor histórico $3-5).

3. **No hay monstruo, ni debería haberlo todavía.** El edge entero vive en el ganador raro que tarda
   semanas/meses (V26 flipea ~cada 107 días por símbolo; V36 ~cada 7 días). Las 9 cerradas en 3 días son "lo
   chico" — casi todas de V36 (15m, más rápido), y la mayoría cierran cerca de breakeven o en pérdida
   pequeña, consistente con el hallazgo de que el 67% de los flips de V36 cierran bajo la entrada. La cola
   gorda —lo que paga— no ha tenido tiempo de aparecer.

4. **El test de disciplina de la Semana 1: no hacer nada.** La tentación humana es reaccionar al −$3.64 (o al
   ADA short que se ve raro). La acción correcta es cero — dejar correr. Contraste directo con el Día 1, donde
   cerré posiciones a mano; esta vez el aprendizaje se aplicó y las posiciones siguen su curso. El eslabón más
   volátil (yo) se mantuvo quieto.

5. **Infra sólida.** Ambos bots vivos, disco 29% (~50 años de runway), MDD-90d 0.8% (trivial a 3 días —
   ningún drawdown ha tenido tiempo de formarse; el número es real pero aún no informativo).

**Etiqueta honesta**: el monitor dice "🟢 EN CAMINO"; la lectura calibrada es **"dentro del ruido esperado,
sin señal aún"**. La expectativa sigue siendo la de siempre: semanas/meses de plano-a-rojo antes de que la
cola pague; el veredicto real llega con ≥1 tendencia completa cobrada, no con 9 trades chicos en 3 días.
*(Detalle por-operación: pendiente del JSON de trades de la cuenta — el aggregate se lee del resumen.)*

---

## Día 4 — 2026-07-13 · "El aviso de retroceso se lee como 'reversó, cierra ya' — y me confundió dos veces"

**Lo que pasó (dos veces, no una)**: llegó el aviso de RETROCESO y lo leí como *"TOMA PROFIT YA PORQUE
REVERSÓ"* — un mandato de cerrar. No lo es: el retroceso es **información pura** (la posición devolvió avance
desde su pico), NO una señal de cierre. Me confundí dos veces con el mismo mensaje. Registro esto con
claridad absoluta porque el patrón (confundir *retroceso* con *reversó*) tiene que quedar cerrado.

### Las dos operaciones, reconstruidas con precio real
| Operación | Bot | Cierre | Tomé | Si la dejaba (hoy) | Dejé sobre la mesa |
|---|---|---|---|---|---|
| ETH LONG `7977feb5` | **V36** | manual (por el aviso) | +$0.84 | +$1.92 (ETH 1794→1874, +4.4%) | **−$1.08** |
| ADA SHORT `dd2702b1` | **V26** | manual | +$1.08 | +$0.26 (ADA rebotó) | +$0.82 (ahorré) |

**El giro que corrige mi percepción**: yo creía que la metida de pata fue en V36 y no en V26. Al revés:
- La de **V36** costó poco (dejé ~$1 de upside porque ETH retomó la subida — el giveback era normal, no un
  reverso: el 91-93% de los que devuelven hacen nuevo máximo). Pero V36 no es el récord crítico.
- La de **V26** hizo plata (+$1.08 vs +$0.26 si la dejaba) — pero **fue en V26, el récord sistemático del
  copy-trade.** Tocar V26 contamina las stats oficiales. **Importa más EN QUÉ BOT intervine que si gané.**

### Qué DEBIÓ suceder, y por qué no debí intervenir
**No hacer nada. Dejar las dos correr.** Razones, con evidencia del propio proyecto:
1. El aviso de retroceso es informativo por diseño (V36 no cierra por él) — no es un mandato.
2. El giveback es NORMAL en tendencia; cortarlo capa ganadores (medido: 91-93% de los monstruos de V36 que
   devuelven a 0% hacen luego un nuevo máximo).
3. V26 y V36 son el récord intocado que sostiene el copy-trade; cada mano mía lo ensucia.
4. El edge entero del sistema es dejar correr — intervenir en el retroceso es exactamente lo que Sinapsis
   fue construido para hacer MECÁNICAMENTE, para que yo NO tenga que hacerlo a mano sobre los bots del récord.

### La causa RAÍZ: el mensaje se lee mal
El aviso decía "⚠️ … Probabilidad de **reversión** ahora: XX% … (botón 💰)". El ⚠️ + la palabra *reversión*
+ el botón de cierre lo hacen leer como "reversó → cierra ya", aunque la última línea aclare "solo
información". **Fix aplicado (display puro, sin tocar trading)**: el aviso ahora abre con "ℹ️ … devolvió
avance (NO es señal de cerrar)", reencuadra el retroceso como normal, y relabela el número de reverso como
"score heurístico (no calibrado)". La claridad va PRIMERO, no al final.

### Lo positivo de lo negativo
1. La confusión reveló un problema real de UX del mensaje — ahora arreglado, así que no vuelve a pasar.
2. **La prueba de que no-intervenir funciona ya está viva**: la ETH LONG de V26 (`3105a500`, pico 67.9%)
   sigue ABIERTA y en +$1.86 no realizado PRECISAMENTE porque NO la toqué. Es el primer posible monstruo del
   forward test — y está corriendo porque, en esa, me quedé quieto.
3. En dinero, el costo de las intervenciones fue mínimo (~$1 de upside en ETH; la de ADA hasta ganó). El
   daño real no fue monetario — fue tocar el récord. Lección barata.
4. Queda registrado: **el instinto de "cerrar en el retroceso" es correcto como tesis (es Sinapsis), pero
   equivocado como acción manual sobre V26/V36.** Deja que Sinapsis lo pruebe; deja los bots del récord correr.

---

## Día 7 — 2026-07-16 · "Llegamos a 200% y no recogió nada" — y el récord no era de nadie

**Contexto**: el operador vio una posición de ETH marcar **205% de avance** sin que el bot cobrara nada, y
varias operaciones en rojo. Su lectura: *"las operaciones comenzaron a perderse por una subida repentina del
ETHUSDT"*. Pidió tres cosas: por qué el aviso de round-trip **siempre** llega en 0 o negativo, cuántas veces
la tendencia no se recuperó tras uno, y una correlación entre los mayores perdedores históricos y los
símbolos activos — con una tesis de negocio detrás: **"un copy trade que no se vende es como haber
descubierto la fuente de la juventud y dejarla enterrada"**. Se bajaron los JSON reales de GCS (V26, V36 y
Sinapsis) y se corrió el motor honesto sobre 4 años. **Casi todas las premisas resultaron invertidas — y
apareció un problema estructural que nadie estaba mirando.**

### 1. El aviso llega en negativo porque ASÍ ESTÁ DEFINIDO (y porque el mercado también)

El disparo en `ejecutor.py:255` es literal: `if pico >= 50 and prog_ahora < 0 and (...)`. **`prog_ahora < 0`
ES la condición.** En 4 años: **0 de 430 avisos (V26) y 0 de 496 (V36)** llegaron con progreso ≥0 — es
imposible por construcción. Preguntar cuándo un round-trip no llegó en negativo es preguntar cuándo sonó la
alarma de incendio sin humo. (Lo que el operador recordaba como "aviso en positivo" es la **alerta de
RETROCESO**, solo de V36 — el par exacto que ya lo había confundido el Día 4.)

Pero hay una segunda razón, y esa sí es del mercado: **de los trades que pican ≥50%, tocan negativo el
95.4% (V26) y el 69.4% (V36)**. Round-tripear no es la excepción: es la norma.

**Las que nunca lo disparan son rarísimas — y ganan todas:**

| | Pican ≥50% y **avisan** | Pican ≥50% y **nunca** tocan negativo |
|---|---|---|
| V26 | 270 (95.4%) · +$664.84 · ganan 23.7% | **13 (4.6%) · +$292.77 · ganan 100%** |
| V36 | 399 (69.4%) · **−$14.57** · ganan 24.3% | **176 (30.6%) · +$1,413.04 · ganan 100%** |

**Hallazgo nuevo sobre V36**: *todo* su profit vive en los 176 limpios. Los 399 que avisan son un empate.
**El aviso no marca un trade que deberías cerrar — marca uno que ya está en el balde donde no hay plata.**

### 2. Cerrar en el aviso PIERDE — medido con costos reales sobre 4 años

| | Dejar correr | Cerrar en el primer aviso | Veredicto |
|---|---|---|---|
| **V26** (270 trades con aviso) | **+$664.84** | −$123.32 | **cerrar pierde $788.16** |
| **V36** (399 trades con aviso) | −$14.57 | −$137.26 | **cerrar pierde $122.69** |

Y ambos contrafactuales están **inflados a favor de cerrar** (primer orden: no cuentan que cerrar libera el
símbolo y desplaza la secuencia — lección V27-A/V32). El costo real es peor.

**El número que lo explica**: tras el aviso, **vuelve a positivo el 91.4% (V26) y el 86.9% (V36)**;
recuperación máxima mediana **+104% (V26)**, p90 **+770%**. Cerrás en −21% promedio justo donde 9 de cada 10
veces el mercado te devuelve la posición. La tendencia NO se recupera (sin pico nuevo) el 50.7% (V26) —
o sea el operador **tiene razón la mitad de las veces** — pero el pago es asimétrico 3:1: las que se
recuperan pagan +$1,224 y las que no cuestan −$394.

### 3. La ETH de V26 es la prueba viva, abierta en la cuenta

```
ETHUSDT LONG #3105a500 (entró 11-jul)
  entry $1,795.65 → $1,887.49 | avance AHORA +125.4% | PICO 205.4%
  rt_avisado_en_pico = 67.9%  → pico actual 205.4% (SE RECUPERÓ e hizo pico NUEVO)
  no realizado: +$2.18 (+1.67R) 🟢  ← la mejor posición de la flota
```

**Esa posición YA disparó un aviso de round-trip con pico 67.9%** — subió, se fue a negativo real, avisó. Si
se cerraba ahí, se cerraba en rojo. No se tocó → corrió a 205.4% y hoy es el único monstruo vivo. **El
argumento no es del backtest: está en la cuenta.**

### 4. La premisa del ETH estaba invertida

ETH a $1,887 con ambas posiciones **LONG** (V26 entró $1,795, V36 $1,869): **la subida del ETH es la que
produjo el 205%.** Las dos están en verde. Lo que perdía era otra cosa — SOL, ADA, XRP, BNB — y **ninguna
disparó round-trip**: picaron entre 8% y 32%, ni cerca del umbral de 50. No son round-trips: son trades
normales camino a su stop de −$1.20. Es el 73-82% que el sistema no acierta. El costo del boleto.

Y **"llegó a 200% y no recogió"** es correcto y por diseño: en `estrategia.py:356` el `return` de
`EXIT_MODE='tendencia'` está ANTES del objetivo del 100% y de la escalera de deciles — **ese código es
inalcanzable en V26/V36. No existe la toma de ganancia.** Solo stop o flip. El "200%" es una regla de medir,
no un objetivo.

### 5. La fuga real no son los bots: son los cierres manuales

| V36 (20 cerradas, **−$5.07**) | n | PnL | promedio |
|---|---|---|---|
| **TOMA DE PROFIT MANUAL** | 12 | +$3.00 | **+$0.25** |
| STOP | 4 | −$5.18 | **−$1.29** |
| FLIP | 4 | −$2.89 | −$0.72 |

**Ganás $0.25 y perdés $1.29 → necesitás 518% de acierto para empatar. Tenés 75%.** Setenta y cinco por
ciento de acierto **y perdiendo plata**: no es mala suerte, es aritmética. Es exactamente la *trampa del
acierto alto* que Sinapsis Fase 1 ya había cuantificado (escalera de deciles: WR 49-70%, PnL −53% a −68%).
**El operador está implementando a mano, sin querer, la única estrategia que el proyecto probó que pierde.**

**Y no está tocando los símbolos pequeños, como creía** — está podando el árbol que da fruta:

| Símbolo | Cierres manuales | Su PnL histórico en V26 |
|---|---|---|
| **XRPUSDT** | **4** | **+$168.49 (el #1)** |
| SOLUSDT | 3 | +$109.97 |
| **ETHUSDT** | **3** | +$126.24 |
| BNBUSDT | 2 | +$140.40 |
| ADAUSDT | 1 | +$103.75 |
| LINKUSDT | **0** | +$4.10 (el único breakeven) |

### 6. La correlación pedida: NO existen los símbolos perdedores

V26, 4 años, 426 trades, 349 en rojo (81.9%) — **los seis símbolos son netos positivos**:

| Símbolo | Trades | Rojas | WR | PnL |
|---|---|---|---|---|
| LINKUSDT | 83 | 70 | 15.7% | **+$4.10** |
| ADAUSDT | 69 | 54 | 21.7% | +$103.75 |
| SOLUSDT | 68 | 55 | 19.1% | +$109.97 |
| ETHUSDT | 65 | 51 | 21.5% | +$126.24 |
| BNBUSDT | 61 | 50 | 18.0% | +$140.40 |
| **XRPUSDT** | 80 | 69 | **13.8%** ← peor WR | **+$168.49** ← mejor PnL |

**XRP tiene el peor win rate y es el que más paga.** El leave-one-out remata la tesis: **el mejor WR que se
compra cortando un símbolo es 19.1%** (sacando XRP) — sube 1 punto porcentual y cuesta $168.49, el 26% de
todo el profit. V36 igual: los 4 positivos, mejor WR posible 26.6% (vs 25.6%). **El 18% de acierto no es de
ningún símbolo: es del método.** Ninguna cirugía de canasta lo arregla.

### 7. EL HALLAZGO GRANDE: el récord de mainnet no es de nadie

Las órdenes de V26 y V36 se mandan sin `positionSide` → **modo one-way → Binance NETEA por símbolo.**
Cuánto se pisan, medido sobre 4 años:

| Símbolo | Horas con posición V26 | Neteadas | % pisado | Choques | Misma dir | **Opuesta** |
|---|---|---|---|---|---|---|
| BNBUSDT | 28,672 | 26,380 | **92.0%** | 285 | 158 | 127 |
| ETHUSDT | 26,564 | 24,679 | **92.9%** | 231 | 138 | 93 |
| SOLUSDT | 26,356 | 24,627 | **93.4%** | 249 | 142 | 107 |
| XRPUSDT | 25,972 | 23,640 | **91.0%** | 270 | 153 | 117 |

**El 92.3% del tiempo que V26 tiene posición en un símbolo compartido, está neteada con una de V36.** 1,035
choques, **444 en dirección opuesta** (un bot cree tener una posición que en la cuenta está cancelada por el
otro). Ya está pasando: hoy V26 tiene ETH LONG y V36 tiene ETH LONG → Binance ve **una sola** posición.

**Consecuencia**: el récord que verá un copiador no es el de V26 (validado 4 años, pctl 100) ni el de V36 —
es una mezcla neteada que **no corresponde a ninguna estrategia jamás validada**. Todo el rigor de walk-
forward + null + OOB se evapora en la cuenta real por una decisión de arquitectura. **El arreglo no es de
estrategia: es un motor por cuenta.**

### 8. La cuenta solo-Sinapsis (el escenario vendible), medida

Repro-chequeada contra `repro_sinapsis.py`: 879 trades / WR 34.93% / +77.91% / PF 1.41 ✅ (exacto).

| | In-sample (4a) | **OOB (4a — la prueba honesta)** |
|---|---|---|
| **Win Rate** | **34.93%** | **34.04%** ← generaliza |
| ROI | +77.91% (~15.5%/año) | **+27.55% (~6.3%/año)** |
| Profit Factor | 1.410 | 1.166 |
| **MDD-90d** | **12.2%** ✅ | **12.3%** ✅ |
| Ventanas de 1 año positivas | 98% (peor −3.5%) | 83% (peor −8.9%) |

**El WR generaliza** (34.93 → 34.04): ese 35% es propiedad del método, no de la canasta. Es un número
prometible. El trade honesto, OOB contra OOB: **V26 da ~12.4%/año con 18% de WR; Sinapsis da ~6.3%/año con
34%.** *Sinapsis compra el doble de acierto y la mitad del drawdown al precio de la mitad del retorno.*

**La tesis de negocio del operador queda en pie, y ahora con precio**: con profit-share lo que manda es el
AUM, y 6.3%/año con 35% de acierto y curva suave retiene copiadores que 12.4%/año con 18% espanta. El 10% de
un AUM grande le gana al 10% de nada. Pero el WR combinado **diluye**: V26+V36 = 23.5%, los tres = 27.7%,
**solo Sinapsis = 34.9%**. Agregar motores no ayuda: **V26 es el ancla que hunde el WR.**

### Qué debió suceder / qué se decidió
1. **No intervenir.** Ni V26, ni V36 — y **tampoco Sinapsis**: se detectó que también se le cerró a mano una
   posición (LINK, pico 60.4%, +$0.15). Sinapsis **ES** el tomador de profit mecánico; cerrarla a mano anula
   justo la lógica que le da el WR 34.9% que se quiere vender, y su forward test deja de medir.
2. **El neteo es lo primero.** Mientras siga, ningún récord sirve. Decisión pendiente del operador (implica
   una segunda cuenta): un motor por cuenta.
3. **Nada se tocó**: los dos bots vivos siguen con su config intacta. Todo el análisis fue solo lectura.

### Correcciones de honestidad de esta sesión
- **Mía, del registro**: creía que Sinapsis estaba sin desplegar ("pendiente de token") — lleva días viva en
  testnet. El registro estaba desactualizado.
- **Mía, de los números**: dije que Sinapsis OOB rendía "~13%/año". **Es ~6.3%/año** (+27.55% en 4 años). El
  número que había citado venía de leer mal la ventana. Corregido arriba.
- **Del operador**: "el ETH nos hizo perder" (lo invertido: el ETH produjo el 205% y es lo único en verde);
  "solo toco los símbolos pequeños" (toca XRP y ETH, los dos mejores; LINK cero); "hay símbolos perdedores
  que sacar" (no existen: los 6 son positivos).

### Lo positivo de lo negativo
1. **La ETH #3105a500 demuestra la tesis en vivo**: sobrevivió su propio aviso de round-trip y es el único
   monstruo del forward test — está ahí porque no se tocó.
2. **La tesis de vendibilidad del operador es correcta y ahora tiene precio medido** (2× WR y ½ DD por ½
   retorno). No era una excusa: era una intuición de negocio válida que faltaba cuantificar.
3. **Apareció el problema del neteo**, que llevaba una semana corrompiendo el récord en silencio y que
   ninguna métrica de estrategia iba a revelar. Encontrarlo con $530 en juego y no con capital de copiadores
   es la clase de error barato que justifica un forward test.
4. Herramientas nuevas reutilizables: `roundtrip_analisis.py`, `correlacion_simbolos.py`,
   `netting_diagnostico.py`, `sinapsis_vendible.py` (esta última con auto-chequeo de reproducción).

### Pendiente
- **Leer el modo de posición de la cuenta real** (`positionSide/dual` + `positionRisk`) desde la VM —
  autorizado por el operador, bloqueado por expiración del token de gcloud. Confirmaría en la cuenta lo que
  el código ya dice (one-way → netea).
- **Decisión del operador**: un motor por cuenta (implica segunda cuenta de Binance), y cuál lleva el récord
  del lead.

---

## The Race — Win Rate (V72 y Sinapsis, testnet) vs ROI estadístico (V26, real) · desde 2026-07-17

Esta sección no narra un día: narra un **experimento en vivo** que arranca hoy y se lee en meses. Tres bots,
una sola pregunta que el proyecto entero viene respondiendo con backtests y que ahora se pone a competir con
dinero (real en uno, paper en dos), a la vista del operador, en Telegram, en tiempo real.

### La pregunta
¿Qué prefiere un ser humano cuando mira la pantalla: **acertar seguido** o **ganar dinero**? Y — más
incómodo — ¿se puede tener las dos cosas a la vez? El proyecto ya tiene la respuesta en el backtest. La
carrera existe para **verla ocurrir**, porque un número en una tabla no convence a nadie; una pantalla que
durante dos meses muestra al bot "malo" (18% de acierto) ganándole al bot "bueno" (76%) sí.

### Los tres competidores
| Bot | Dónde | Estrategia | Canasta | WR (backtest 4a) | Retorno (backtest 4a) | Ganadora promedio |
|---|---|---|---|---|---|---|
| **V26** (el campeón) | **MAINNET, dinero real** | cruce 4h + dejar correr (stop/flip) | ETH/SOL/BNB/XRP/ADA/LINK | **18.08%** | **+130.59%** | **$17.72** |
| **Sinapsis** | testnet | patrones 4h + salida-lateral | SOL/BNB/XRP/ADA/LINK | 36.21% | +80.31% | $4.54 |
| **V72 "El Espejismo"** | testnet | cruce 4h + TP/SL dial 3.0 | DOGE/AVAX/DOT/LTC/ATOM | **76.33%** | **+2.61%** | **$0.57** |

Los tres comparten el mismo cerebro de entrada en distinto grado: **V72 usa EXACTAMENTE la entrada de V26**
(cruce), solo cambia la salida. Sinapsis usa la entrada de patrones con una salida propia. Así la carrera
aísla lo que importa: **con la misma señal, la forma de cobrar decide todo.**

### La motivación (por qué esta carrera, y por qué ahora)
Todo empezó con una queja legítima del operador: un récord con 18% de acierto y 82% de operaciones en rojo
**no se le vende a nadie**, por más que el retorno cierre — y un copy-trade que no se vende es como encontrar
la fuente de la juventud y dejarla enterrada. La pregunta natural fue: *¿subimos el win rate?* La respuesta,
después de un día entero de mediciones, fue un hallazgo que da vuelta la premisa:

- **El win rate es un DIAL, no una habilidad.** En el motor, `dist_sl = dist_tp × SL_FRACTION_OF_TP`, y como
  la probabilidad de tocar el TP antes que el SL es ≈ `SL/(TP+SL)`, el win rate se fija con un solo número.
  Medido en una grilla de **28 celdas** (4 timeframes × 2 canastas × 4 posiciones del dial): el WR real
  coincide con la teoría con un **error absoluto medio de 1.36 puntos porcentuales**. Se puede pedir 43%,
  67%, 75% u 80% de acierto sin tocar una sola línea de la señal.
- **El precio de comprarlo es el retorno.** Correlación WR ↔ tamaño de la ganancia promedio: **−0.842**. El
  bot de 10% de acierto (V26 a 1 día) cobra $318 por trade ganador; el de 80% cobra $0.40. Factor 800×.
- **El edge de V26 no está en entrar bien — está en NO SALIR.** La misma entrada (`cruce`) rinde +130% con
  la salida "dejar correr" y ~0% con CUALQUIER estructura de TP/SL, en los cuatro timeframes. La señal no
  encuentra "buenos precios": encuentra **movimientos que corren**, y capados a 1 ATR lo que los hacía
  valiosos se evapora.

V72 es la puesta en escena de ese hallazgo. No busca ganar dinero — **se construyó esperando que NO gane**
(+2.61% en 4 años con 76% de acierto). Su valor es didáctico: mostrar en vivo cómo se ve un win rate
altísimo mientras te cuesta el retorno.

### Las hipótesis (qué va a pasar, y POR QUÉ)

**H1 — A corto plazo (semanas a ~1 mes), V72 puede ir "ganando", y eso NO refuta nada.**
V72 acierta 3 de cada 4 y cobra centavos: su curva es suave, casi plana, ligeramente arriba de cero.
Sinapsis y V26 son trend-followers: pierden chico muchas veces y esperan una racha grande. En cualquier
ventana de 1 mes, V26 es un volado (44.9% de meses positivos en el backtest) y hace ~9 operaciones. Es
perfectamente esperable que el mes 1 muestre a V72 con la curva más linda. **Por qué**: la varianza de una
suma de muchos premios chicos y seguros es baja; la de pocos premios enormes y raros es altísima. En una
ventana corta, la baja varianza *parece* superioridad. Es el espejismo, literalmente, funcionando en vivo.

**H2 — A mediano plazo (2-3+ meses, o al menos una tendencia grande cobrada), V26 y Sinapsis separan.**
Cuando aparezca UN movimiento sostenido en la canasta —y en cripto aparecen— el bot que dejó correr cobra
en una sola operación lo que V72 no junta en cientos. **Por qué**: el retorno del trend-following vive
enteramente en la cola derecha (en el backtest de V26, los 5 mejores trades = 76% del PnL neto; de 79
ganadores, cero tuvieron pico <150%). V72, por diseño, corta a 1 ATR: matemáticamente no puede tocar esa
cola. Su techo es su piso.

**H3 — Al cierre, el orden esperado por retorno es V26 > Sinapsis > V72; por win rate, exactamente al revés.**
V26 gana en dinero y pierde en acierto; V72 gana en acierto y no produce; Sinapsis queda en el medio en
ambos. **Por qué**: es la relación −0.842 hecha carne. Las dos métricas están estructuralmente en tensión;
ningún bot puede liderar las dos a la vez, y esta carrera lo va a mostrar con tres puntos en vez de una tabla.

**H4 — V72 termina cerca de cero, no en pérdida grande, pero por debajo de la inflación de costos si el
mercado no coopera.** En backtest OOB dio +2.61% en 4 años (esencialmente breakeven después de comisiones
maker). **Por qué**: con WR 76% y RR invertido (gana $0.57, arriesga ~3× eso), la esperanza matemática antes
de costos es ~0 por construcción; los costos la empujan levemente negativa salvo que la señal de entrada
aporte lo justo para compensarlos. Es el "pierde lento" del que hablamos: no un desastre, una sangría fina.

### Cómo se mide (para que la comparación sea honesta)
- **V26 es dinero real** (mainnet, ~$522, dial 0.25%); Sinapsis y V72 son **paper** (testnet, ~$5.000 de
  saldo demo, riesgo 0.33%). Los montos absolutos NO son comparables entre real y paper — se compara en
  **porcentaje de retorno** y en **win rate**, no en dólares.
- Sinapsis y V72 comparten la MISMA cuenta de testnet (Binance demo no tiene subcuentas) pero **canastas sin
  un solo símbolo en común** → cero neteo. Es la lección del 2026-07-16 (cuando V26+V36 compartían cuenta y
  se neteaban el 92.3% del tiempo) aplicada de entrada, por diseño, no como parche.
- **Sin ETH ni BTC en ninguno de los dos de testnet** (pedido del operador): saca los dos majors para que las
  dos canastas de altcoins sean comparables entre sí, sin un BTC o un ETH distorsionando el resultado.
- Cada bot tiene su token de Telegram, su archivo de operaciones (`trades_*.json`) y su forense — el logging
  queda identificado por bot, sin mezcla.
- **Regla de lectura pre-registrada**: no se declara nada antes de 3 meses O de que se cobre al menos una
  tendencia grande en alguna canasta. Un marcador de 1 mes es ruido con forma de conclusión.

### El caveat honesto que la carrera NO puede esconder
Sinapsis y V72 tienen backtest, no forward validado a años. V26 tiene 4 años + walk-forward + null + OOB +
el forward real corriendo. Si en dos meses V72 va arriba, eso **no** significa que el win rate alto sea mejor
— significa que todavía no apareció la tendencia que le da la razón a V26. La carrera es una demostración
pedagógica en vivo, no una re-validación. Su conclusión ya está escrita en el backtest; lo que aporta es
**verla pasar con dinero en pantalla**, que es la única prueba que un futuro copiador (o lector del libro) va
a creer.

### Estado
- **V72 construido** (`v72_espejismo/`), repro-test EXACTO (452 trades / WR 76.33% / +2.61% / PF 1.07 — el
  repro atrapó un bug de costos heredados de V26 antes de desplegar). Tres guardas de arranque: testnet
  obligatorio, config del dial intacta, cero solape con Sinapsis.
- **Sinapsis re-ajustado** a 5 altcoins (sin ETH), repro-test EXACTO (718 / 36.21% / +80.31% / PF 1.516).
- **Desplegados juntos** en la VM de testnet (`sinapsis-vm`, São Paulo), cuenta demo compartida, canastas
  disjuntas. Rollback: imagen `openclaw-sinapsis:pre-v72-20260717`.
- **V26 sigue solo y limpio en mainnet** — la carrera no lo toca; es el punto de referencia, no un participante
  que se pueda modificar.

---

## Las señales de volumen como salida — otra sugerencia de René, y otra pared · 2026-07-23

Esta investigación nació de una conversación con René, mi amigo que también opera. René miró el trabajo y
propuso dos cosas. La primera ya la habíamos hecho —y se lo dije—: sugirió hacer **ingeniería inversa** sobre
nuestro propio backtest, ir a las operaciones históricas y ver qué señales ocurrían en los momentos clave.
Eso es exactamente lo que hicimos meses atrás cuando reconstruimos, vela por vela, el pico de cada monstruo
para preguntarle a los indicadores qué gritaban en el techo (y la respuesta fue incómoda: en el pico casi
todo se ve igual que en cualquier otro momento). La segunda sugerencia de René sí era territorio nuevo: **usar
el volumen** —zonas de valor, oferta y demanda, flujo de compra/venta— pero **solo para decidir cuándo salir**,
sin tocar las entradas. Su intuición: si el bot entra bien pero suelta tarde, quizás el volumen sepa leer el
final de una tendencia mejor que el precio.

Me pareció una idea honesta y la probé con el mismo rigor de siempre: primero un diagnóstico barato (¿la
señal siquiera distingue el techo real?) antes de construir nada. Probé cuatro familias enteras de volumen:

- **Flujo acumulado** (OBV, línea de acumulación/distribución, Chaikin Money Flow): ¿el flujo deja de
  confirmar el nuevo máximo cuando el techo es de verdad?
- **Zonas de valor** (Volume Profile / área de valor): ¿el precio se aleja demasiado del "imán" de volumen en
  el techo real?
- **Volume Spread Analysis** (la escuela de Wyckoff: "no demand", volumen que frena): ¿la subida sin volumen
  avisa el agotamiento?
- **Order-flow** (Cumulative Delta): el dato más caro y directo — comprador agresivo contra vendedor agresivo.
  Para esto tuve que re-descargar datos que el código venía tirando a la basura. Es lo más cercano a "ver la
  mano del dinero grande" que se puede tener sin un feed institucional.

**Las cuatro chocaron con la misma pared, y es una pared que ya conocíamos con otro nombre.** El problema no
es qué señal de volumen: es que un ganador de este sistema hace veinte máximos nuevos antes del último, así
que el techo real es apenas uno de cada veinte momentos de decisión. Y en esos veinte, la posición se ve
idéntica —el volumen alto, el precio estirado, el flujo dudando— porque *eso es lo que es un monstruo* mientras
sube. Ninguna señal puntual, ni siquiera el order-flow, levanta esa probabilidad de forma útil. El dato más
limpio (que la subida se haga sin compra agresiva) resultó **al revés** de lo que uno esperaría: el volumen
bajo significa que la tendencia *continúa*, no que se agota. El techo verdadero llega con euforia y volumen,
no con silencio.

Le agradezco a René la sugerencia, porque no fue tiempo perdido: fue la prueba, medida y no opinada, de que
**la salida "tonta" de nuestro motor —esperar a que la tendencia se dé vuelta del todo— está tan cerca del
óptimo como se puede.** Ese 80% de ganancia que "dejamos sobre la mesa" en cada monstruo no es un defecto
esperando una señal más lista: es sencillamente **incapturable** en tiempo real, porque el retroceso normal y
la reversión final son indistinguibles hasta que ya pasaron. Es la misma lección que el libro repite con
distintos disfraces —nunca capar al ganador—, ahora confirmada también desde el volumen, con datos de
order-flow que tuvimos que ir a buscar especialmente para poder decir, con la conciencia tranquila, que la
pregunta quedó respondida. A veces el mejor resultado de una investigación es cerrar una puerta con evidencia,
para no volver a golpearla.
