# TRIAGE — Física aplicada al trading de cripto (Fase 0)

> Clasificación honesta de las afirmaciones del texto divulgativo que motivó esta
> investigación (2026-07-09). Regla: **solo se testean las categorías ✅/⚠️ con una
> predicción falsable**. Las ❌ se documentan en el manual como pseudo-ciencia, con
> la explicación de POR QUÉ no son testeables — coherente con la política anti-humo
> del proyecto (marca de agua TESTNET, aviso legal, etc.).

| # | Afirmación del texto | Categoría | Por qué | Tratamiento |
|---|---|---|---|---|
| 1 | "La econofísica existe como campo y modela el mercado como sistema complejo" | ✅ Ciencia real | Campo académico real desde los 90 (Mantegna & Stanley, Bouchaud, Sornette; journals: Physica A, Quantitative Finance) | Investigar (Fase 1) y testear (V60-V67) |
| 2 | "Principio de Incertidumbre de Heisenberg: es imposible conocer el precio exacto y el impulso futuro simultáneamente" | ❌ Metáfora | Heisenberg es una relación de conmutación entre operadores en un espacio de Hilbert (ΔxΔp ≥ ℏ/2). El precio y su "impulso" NO son operadores no-conmutantes; no existe un ℏ del mercado. Ya desmontada en este proyecto (P2, 2026-07-04). La intuición subyacente (más precisión de nivel ⇒ menos información direccional) es un enunciado sobre RUIDO/SEÑAL, y su versión medible (trade-off costo×cadencia por timeframe) YA se midió (matriz 2026-06-11) | Desmontar en el manual con la física correcta |
| 3 | "Efecto observador cuántico: seguir un token masivamente altera su comportamiento" | ⚠️ Metáfora CON traducción real | Lo cuántico es falso (no hay colapso de función de onda), pero la REFLEXIVIDAD es real y clásica (Soros; crowding). El crowding es medible: funding rate extremo = exceso de apalancamiento de un lado | Testeable → V67 (crowding por funding, datos reales ya cacheados) |
| 4 | "Comportamiento caótico y dinámica de enjambre (fluidos/gases)" | ⚠️ Parcialmente real | "Caos" en sentido técnico (Lyapunov positivo, determinismo) NO está demostrado en mercados; lo que SÍ es real y medible son los stylized facts: colas de potencia, clustering de volatilidad, no-gaussianidad, multifractalidad | Diagnósticos D1/D2 + hipótesis V60/V61/V64 |
| 5 | "Los activos digitales son partículas" | ❌ Analogía sin contenido | No hay predicción falsable en la analogía por sí sola | Contexto en el manual (de dónde viene la analogía y qué sí es rescatable) |
| 6 | "Entrelazamiento cuántico ≈ correlación entre Bitcoin y acciones" | ❌ Metáfora | La correlación financiera es estadística CLÁSICA (no viola desigualdades de Bell, no hay no-localidad). El contenido real (co-movimiento BTC-equities) se estudia con econometría normal; el beta-hedge cripto ya se probó en este proyecto y se rechazó (2026-07-07) | Desmontar; citar el test propio |
| 7 | "La computación cuántica calculará millones de escenarios y amenaza la blockchain" | ✅ Real pero NO trading | Shor (factorización/ECDSA) y Grover son amenazas reales a la criptografía actual → criptografía post-cuántica (NIST). NO produce una señal de trading hoy | Sidebar del manual: riesgo de seguridad, no edge |

## Prior art propio (antecedentes directos, no repetir)
- **Hurst / GBM**: probado 2026-07-07 — corr −0.05 con el movimiento futuro, RECHAZADO.
- **Metáfora Heisenberg**: desmontada en P2 (2026-07-04).
- **Beta-hedge (≈"entrelazamiento")**: rechazado (alpha residual negativo + costos).
- **Filtros de régimen fallidos**: squeeze TTM, fuerza relativa, clímax, exhaustion — la vara para
  cualquier detector nuevo de régimen es alta y conocida.

## Qué se decide con esto
Solo pasan a hipótesis (Fase 2) las líneas 1, 3, 4 — traducidas a predicciones falsables con
parámetros canónicos de la literatura. Las líneas 2, 5, 6 van al manual como educación anti-humo.
La línea 7 va como sidebar informativo.
