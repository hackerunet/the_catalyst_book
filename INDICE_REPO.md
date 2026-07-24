# Índice del repositorio — mapa carpeta ↔ libro

Este repositorio acompaña el libro **"The Catalyst"**. Cada carpeta corresponde a una
parte de la historia. La tabla de abajo mapea **cada carpeta del código → el capítulo del
libro** donde se explica, en **orden de lectura**.

> **Cómo está ordenado**: para que las carpetas aparezcan en git en el mismo orden que el
> libro, se recomienda subirlas con un prefijo numérico (`01_`, `02_`, …). El script
> `armar_repo_libro.sh` construye una **copia ordenada** con esos prefijos (sin tocar los
> originales que corren en producción). Cada carpeta trae un `COMO_EJECUTAR.md` con el
> comando exacto para probarla.

> **⚠️ NO se publican `v26_tendencia/` ni `v36_15m/`** — son los dos motores con edge real,
> corriendo (o pausados) en la cuenta del autor. La receta queda en reserva. El libro los
> explica; el código no se comparte.

---

## Parte I — Fundamentos (Cap. 1–4)
Conceptos: vocabulario, indicadores, cómo se prueba sin engañarse, cómo se mide.
| # | Carpeta actual | Qué es |
|---|---|---|
| 01 | `bot_alpha_portfolio/stable_v25_prototype` | **El motor honesto y sus herramientas** — `indicadores.py` (Cap. 2), `backtest.py` + `walkforward.py` (Cap. 3–4: reloj global, intravela pesimista, costos, null-vs-azar, OOB). Es el corazón técnico de todo el libro; también aparece en Cap. 12–13, 18, 22, 26–27. |

## Parte II — La era del espejismo (Cap. 5–8)
Las primeras estrategias, las proyecciones de fantasía, el pecado de los 41 días.
| # | Carpeta actual | Qué es |
|---|---|---|
| 02 | `bot_v13` … `bot_v19_C` (15 carpetas) | **Los bots tempranos** — caza de liquidez (v13), cruces de EMA (v14–v17), RSI/Bollinger (v17–v18), swing rejection (v19). Corrían sobre el motor viejo (sesgado). Sus `PROYECCION_RENTABILIDAD.md` son las "proyecciones de fantasía" del Cap. 7. |
| 03 | `bot_alpha_portfolio/investigacion_scalping` | Investigación de scalping de esa era (bibliografía + pruebas). |

## Parte III — El punto de inflexión (Cap. 9–12)
Las tres puertas y el +41% falso, el motor honesto que lo demolió, la re-auditoría.
| # | Carpeta actual | Qué es |
|---|---|---|
| 04 | `bot_alpha_portfolio/v21` · `v21_stable_prototype` | V21 (baseline de control de la era de las tres puertas). |
| 05 | `bot_alpha_portfolio/v22` | **El sistema de tres puertas** (Cap. 9) — `mesa_de_dinero.py` (watchdog) + `simulador_institucional_v22.py` + `estrategia_v22_Master.py`. El +41% que resultó ser artefacto del motor. |
| 06 | `bot_alpha_portfolio/v23` | V23 — allocador quality-ranked (en espera, no corrió). |
| 07 | `bot_alpha_portfolio/v24-fable` · `v24-fable-a` | **El motor honesto** (Cap. 10) — la estrategia de V22 sobre un motor reparado; demostró que el edge era del bug. `v24-fable-a` = estrategia rediseñada sobre el motor honesto. |

## Parte IV — Las estrategias que sí funcionan (Cap. 13–15)
V25 y la familia de 1h (muerta), V26 (primer edge), V36 (segundo edge).
| # | Carpeta actual | Qué es |
|---|---|---|
| 08 | `bot_alpha_portfolio/v28_copilot` | V28 — el copiloto 1h (retirado; sin edge mecánico, valor en la capa humana). |
| — | `bot_alpha_portfolio/v26_tendencia` | **🔒 V26 — NO SE PUBLICA.** El primer edge honesto (Cap. 14). |
| — | `bot_alpha_portfolio/v36_15m` | **🔒 V36 — NO SE PUBLICA.** El segundo edge (Cap. 15). |

## Parte V — Las leyes del proyecto (Cap. 16–19)
El museo de experimentos fallidos, las cinco leyes, V37, dónde estamos.
| # | Carpeta actual | Qué es |
|---|---|---|
| 09 | `bot_alpha_portfolio/v26_salida_test` | Hipótesis P1/P2 y Test 1/2 de salida (Cap. 16, 22) — copia aislada, validada por Fable. |
| 10 | `bot_alpha_portfolio/v26_salida_comparativa` | **La comparativa completa de salidas** (Cap. 26) — todas las salidas probadas sobre el motor honesto, ninguna gana al flip. También el V73 (volumen). |
| 11 | `bot_alpha_portfolio/v27b_carry` | V27-B — carry de funding delta-neutral (Cap. 23, análisis de datos públicos). |

## Parte VI — Estado actual y camino a producción (Cap. 20)
Infra, deploy, monitoreo.
| # | Carpeta actual | Qué es |
|---|---|---|
| 12 | `bot_alpha_portfolio/diagnostico` | Herramienta de diagnóstico de mercado (read-only) — reproduce la decisión viva de cada bot. |
| — | (raíz) `deploy_gcp.sh`, `Dockerfile.cloud`, `entrypoint.sh`, `state_sync.py`, `monitor_salud.py` | La infra de producción en GCP (Cap. 20). *(No son una carpeta; se suben en la raíz del repo del libro.)* |

## Parte VII — La búsqueda de un segundo motor (Cap. 21–28)
Fragua (laboratorio con auditor), los factores descartados, pairs, brute-force, física.
| # | Carpeta actual | Qué es |
|---|---|---|
| 13 | `Fragua/` (todo) | **El laboratorio Fragua** (Cap. 21) — motores nuevos con auditor independiente: `m1_cross_sectional` (momentum/reversión, Cap. 23), `m2_pairs`/`m2_pairs_trading` (cointegración, Cap. 24), `m3_carry`/`m3_basis_trade` (carry, Cap. 23), `m4_allocador`/`v41_regime_switch` (régimen, Cap. 23, 25), `m7_metalabeling` (ML, Cap. 25), `laboratorio_gbm` (opciones/GBM), `v48_p3_replicas` · `v49_espejismos` · `v36_exits` · `m0_variantes` (auditoría del Cap. 25). |
| 14 | `bot_alpha_portfolio/investigacion_econofisica` | **La última frontera** (Cap. 28) — econofísica: entropía, MF-DFA, LPPLS, Omori, RMT, transfer entropy, crowding. Bibliografía + 8 hipótesis, todas rechazadas. Incluye la bitácora del forward test (`BITACORA_MAINNET.md`). |

## Parte VIII/IX — El forward test y los motores nuevos (Cap. 29–33)
El dinero real, René, la carrera del win rate, el epílogo.
| # | Carpeta actual | Qué es |
|---|---|---|
| 15 | `bot_alpha_portfolio/sinapsis_lateral` | **Sinapsis** — el candidato "vendible" (WR 34% que generaliza): 4h, patrones + salida-lateral. Vivo en testnet. |
| 16 | `bot_alpha_portfolio/v72_espejismo` | **V72 "El Espejismo"** (Cap. 32) — la demostración de que el win rate es un dial. Corre en testnet junto a Sinapsis ("La Carrera"). |

---

### Notas
- Las carpetas `v18`, `v19`, `v20` de `bot_alpha_portfolio/` son restos de numeración vieja; revisar su contenido antes de subir (pueden ser duplicados o stubs).
- Todo `.py` de investigación asume el `trading_env` (venv del proyecto) y, en muchos casos, los caches OHLCV que viven en `stable_v25_prototype/`. Ver el `COMO_EJECUTAR.md` de cada carpeta.
- El QR final del libro apunta a este repo (lo agrega el autor).
