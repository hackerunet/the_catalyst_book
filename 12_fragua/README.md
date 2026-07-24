# Fragua — Motores de backtest para clases de estrategia nuevas

> Laboratorio de **motores de backtest** para las clases de estrategia que el motor actual
> (`stable_v25_prototype/`) NO puede modelar: cross-sectional, pairs/stat-arb, carry, meta-allocación,
> positioning, ML. Cada motor se construye aquí, se valida, y solo después se corren backtests serios.
> Índice de qué construir y por qué: `../INDICE_ESTRATEGIAS_PENDIENTES.md`.

## Metodología de trabajo (acordada 2026-07-04)

**División de roles estricta:**
- **Constructor (Claude/Opus)**: escribe el código de cada motor, sus estrategias puras y sus self-tests.
- **Validador (Fable 5)**: audita el nivel de honestidad de cada motor, valida operaciones y cálculos,
  busca errores de lógica, y **si encuentra errores, los arregla él mismo**. Aplica los MISMOS criterios de
  honestidad que rigen el motor actual (ver `HONESTIDAD.md`).

**Reglas duras (no negociables):**
1. **Aislamiento total**: NADA en `Fragua/` importa, modifica o depende de `bot_alpha_portfolio/` (ni el
   motor `stable_v25_prototype/`, ni los bots vivos `v26_tendencia/` / `v36_15m/`). Los motores son
   auto-contenidos. Las constantes compartidas (costos) se **espejan** con cita de origen, no se importan —
   así no hay acoplamiento ni riesgo de tocar código vivo.
2. **Fable NO toca el motor actual ni los dos bots vivos.** Su jurisdicción de arreglo es exclusivamente
   `Fragua/`.
3. **Datos read-only**: los motores leen los caches OHLCV existentes (`.pkl`) sin escribirlos ni moverlos.
   Descargas nuevas (OOB) van a caches propios dentro de `Fragua/`.
4. **Secuencia obligatoria por motor**: (a) construir → (b) self-tests pasan → (c) Fable valida honestidad
   y cálculos y arregla lo que encuentre → (d) SOLO ENTONCES se corren backtests serios (3 años, null, OOB).
   No se salta al backtest serio sin la validación de Fable.
5. **Todo se documenta, incluidos los errores.** Cada motor tiene su `REGISTRO.md` con: decisiones de
   diseño, self-tests, errores encontrados por Fable, cómo se arreglaron, y el estado de validación.

## Roster de motores

| Motor | Clase | Estado | Carpeta |
|---|---|---|---|
| **M1** | Cross-sectional / ranking (momentum, reversión, factores) | ✅ Validado por Fable + 1er backtest serio corrido (V44) | `m1_cross_sectional/` |
| M2 | Pairs / stat-arb (cointegración, 2 patas) | ⏳ Pendiente | — |
| **M3** | Carry con funding real (extensión de M1, para V46) | ✅ Validado por Fable (2026-07-04): 3 fixes + 2 guards, 11/11 self-tests, no-regresión V44 exacta — listo para V46 | `m3_carry/` |
| M4 | Meta-allocador de carteras (regime-switch, vol-target) | ⏳ Pendiente | — |
| M5 | Positioning (OI/funding/liquidaciones) | ⏳ Pendiente | — |
| M6 | Microestructura / order flow | ⏸️ Baja prioridad (fuera de alcance sin infra HFT) | — |
| M7 | ML / meta-labeling | ⏳ Pendiente | — |

## Estado actual
- **M1 construido y VALIDADO** (2026-07-04). Fable auditó los 20 ítems de `HONESTIDAD.md`, encontró y
  arregló 4 errores reales (el más grave: el null por permutación estaba sesgado — daba percentil 100 a
  una configuración que perdía −53%; corregido con un null de rotación temporal que preserva turnover).
  16/16 self-tests, no-regresión verificada independientemente. Detalle: `m1_cross_sectional/REGISTRO.md`.
- **Primer backtest serio corrido: V44 (momentum cross-sectional)** — pasó los 3 criterios in-sample
  (PnL +29.16%, PF 1.016, percentil 97.5) pero **falló fuera de canasta** por PnL negativo (−27.42%),
  aunque el percentil OOB seguía fuerte (81.5) — la señal de selección generaliza, pero el drag pesimista
  de funding (piso conservador validado por Fable) se come el margen absoluto. **RECHAZADO tal como está
  definido**, sin escanear variantes. Ruta pre-declarada: construir M3 para V46 (carry cross-sectional con
  funding real por símbolo) en vez de re-testear V44. Ver el libro sección "V44".

## ▶️ RETOMADO (2026-07-04) — el usuario pidió terminar Fragua y luego pasar a testear la salida

M3 construido (funding real + `ranker_carry`, extensión aditiva de `engine_xs.py` con no-regresión
verificada). Despachado a Fable para validación. Mientras se valida, el trabajo se mueve en paralelo a
las hipótesis de salida (P1/P2, sobre el motor YA validado de `stable_v25_prototype/` — independiente de
Fragua, no requiere el mismo gate de validación).

### Pendiente dentro de M1/M3 (para retomar sin perder contexto)

### Pendiente dentro de M1 (ya validado, pero con cabos sueltos conocidos)
1. **`ranker_reversion` (V45) nunca corrió un backtest serio** — el código existe y pasó los self-tests
   genéricos del motor, pero no tiene su propio pre-registro ni corrida in-sample/OOB. Sigue siendo, en
   rigor, "construido pero no probado" igual que M2–M7.
2. **Las "notas de segundo orden" del REGISTRO de Fable** — 7 puntos que quedaron documentados como
   *deliberadamente no arreglados por inmateriales* (orden del cobro de funding intra-barra, costo de
   rebalanceo sobre equity pre vs post, comportamiento si el ranker devuelve `None` a mitad de corrida,
   sesgo de ventana común en `alinear` con símbolos de historia corta, etc. — el detalle completo está en
   `m1_cross_sectional/REGISTRO.md`, sección "Notas de segundo orden"). Nadie los objetó, pero tampoco se
   re-confirmó cada uno con un test dedicado — quedan como riesgo residual bajo, no cero.
3. **`metricas.correlacion` nunca se ejercitó contra datos reales** — existe y tiene la firma correcta,
   pero como V44 nunca pasó la guarda OOB, jamás se llegó a calcular una correlación real vs las curvas de
   equity de V26/V36. Sigue sin validar en un caso de uso real.
4. ~~El "piso de funding pesimista" no tiene aún una alternativa construida~~ — **RESUELTO 2026-07-04**:
   M3 (funding real por símbolo) construido y validado por Fable. **V46 (el factor de carry en sí,
   usando M3) sigue sin correr** — es el paso pendiente de mayor prioridad, ver abajo.

### Pendiente en el roster general (sin construir, por lo tanto sin validar)
- **M2** (pairs / cointegración) — sin construir.
- **M4** (meta-allocador de carteras) — sin construir; es el de menor costo/mayor valor según el índice
  (opera sobre curvas ya existentes de V26/V36), pero tampoco se tocó.
- **M5** (positioning: OI/funding/liquidaciones) — sin construir, requiere ingesta de datos nuevos.
- **M6** (microestructura/order flow) — no recomendado por ahora (fuera de alcance sin infra HFT), pero
  sigue en el roster sin descartar formalmente.
- **M7** (ML / meta-labeling) — sin construir; es conceptualmente el más prometedor y el más fácil de
  auto-engañarse — necesitará su propia rúbrica de honestidad extendida (purged CV + embargo) antes de
  que Fable pueda validarlo con el checklist actual de `HONESTIDAD.md`, que no cubre esos ítems todavía.

### Nada de esto se toca hasta la próxima instrucción.
