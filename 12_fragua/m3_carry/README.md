# M3 — Carry con funding REAL (extensión de M1)

No es un motor nuevo desde cero: **reusa la mecánica dollar-neutral ya validada de M1**
(`engine_xs.correr`, mismo drift de pesos, mismo turnover, mismo null desplazado) y le agrega dos cosas:

1. **Funding real por símbolo** (`funding_real.py`) — reemplaza el piso pesimista de M1 (tasa base plana
   sobre el gross, sin importar la dirección) por el costo/ingreso REAL y firmado de cada símbolo, leído
   del historial de funding real. Esto es lo que motivó construir M3: V44 (momentum cross-sectional)
   pasó in-sample pero murió en fuera-de-canasta SOLO por el funding pesimista (percentil OOB 81.5 —
   fuerte — pero PnL absoluto negativo) — la condición de uso de la validación de Fable decía exactamente
   "si un candidato muere solo por funding, modelar per-símbolo antes de rechazar".
2. **`ranker_carry`** (`estrategia_carry.py`) — el factor de carry propiamente dicho: long el funding más
   negativo (te pagan por estar long), short el más positivo. Habilita V46.

## Datos (ambos read-only, cero escritura fuera de `Fragua/`)
- Canasta original (ETH/SOL/BNB/XRP/ADA/LINK): `bot_alpha_portfolio/v27b_carry/funding_cache.pkl` (ya
  existía, de la sesión V27-B).
- Canasta OOB (BTC/DOGE/AVAX/DOT/LTC/ATOM): **descargada esta sesión** desde la API pública de Binance
  (`/fapi/v1/fundingRate`, sin autenticación) por `_descargar_funding_oob.py`, cacheada en
  `funding_cache_oob.pkl` — cache PROPIO dentro de `Fragua/`, nunca se tocó `bot_alpha_portfolio/`.
  4.452 eventos por símbolo, 2022-06-12 → 2026-07-04.

## Archivos
- `funding_real.py` — `matrices_funding(raw, times, symbols)` construye dos matrices (T,S) alineadas a
  los timestamps del motor: `pagos` (dispersa, 0 salvo en el evento real — para la contabilidad exacta) y
  `conocida` (forward-fill causal de la anterior — para que el ranker decida con la última tasa YA
  publicada, nunca una futura).
- `estrategia_carry.py` — `ranker_carry(conocida_matrix, k, gross)`, reusa `_pesos_desde_ranking` de M1
  (mismo guard de neutralidad, mismo mecanismo).
- `engine_xs.py` (en `m1_cross_sectional/`, **extendido** para M3) — parámetro nuevo `funding_matrix`:
  si se provee, la contribución de funding en cada barra es `-w · rate` (exacto, firmado, mismo convenio
  de signo que `pnl_neto_cierre` del motor vivo: LONG paga cuando rate>0, SHORT cobra). Con
  `funding_matrix=None` (default) el comportamiento es IDÉNTICO al de antes — verificado por
  no-regresión exacta (mismos PnL de V44: k=1 −68.264%, k=2 −53.260%, dígito por dígito).
- `selftest_m3.py` — 5 tests analíticos, incluido uno que atrapa un bug que encontré y arreglé yo mismo
  ANTES de pasarlo a validación (ver abajo).
- `_descargar_funding_oob.py` — script de una sola corrida, ya ejecutado; el cache queda versionado.

## Un bug propio, encontrado y corregido antes de la validación de Fable
Mi primera versión de `matrices_funding` usaba `.replace(0.0, np.nan).ffill()` para construir la matriz
`conocida` — pero eso confunde una **tasa real de exactamente 0%** con "no hubo evento", y en ese caso
haría *forward-fill* del valor NO-cero anterior en vez de registrar que la tasa real cayó a 0%. Lo
detecté al auditar mi propio código, lo arreglé usando una máscara explícita `presente` (True solo donde
hubo un evento real, independiente de su valor) en vez de inferir presencia desde el valor, y agregué
`test_matrices_funding_caso_tasa_cero` que falla si el bug reaparece. Documentado igual que cualquier otro
error del proyecto — no se descarta el borrador, se dejó el rastro.

## Qué necesita validar Fable
Recorrer `../HONESTIDAD.md` otra vez, con foco en lo NUEVO (no en lo que M1 ya validó):
- **B3 funding real**: ¿el signo/timing de `-w·rate` es correcto en todos los casos? ¿el forward-fill de
  `conocida` es genuinamente causal (nunca usa una tasa publicada después de `t`)?
- **A1/A2 con `ranker_carry`**: no usa `M` (precio) en absoluto — confirmar que igual respeta el
  slicing `M[:t+1]` sin romper nada (lee `conocida_matrix[t]`, una estructura externa al slicing — ¿es
  eso una laguna de causalidad distinta a la que resuelve el slicing de M?).
- **Alineación de funding**: ¿el redondeo a la hora (`.dt.round('h')`) puede, en algún caso límite del
  cache real, alinear un evento a la hora EQUIVOCADA (adelantarlo o atrasarlo) de forma que se vuelva
  no-causal? Los eventos reales verificados caen exactos en :00 con jitter de milisegundos/segundos, pero
  vale la pena confirmarlo con el cache real completo, no solo el sintético de los self-tests.
- **No-regresión**: confirmar independientemente que `funding_matrix=None` reproduce el baseline de V44
  exacto (ya verificado por el constructor, pero re-verificar es parte del proceso).

## Estado
✅ **VALIDADO por Fable (2026-07-04)** — ver veredicto completo y condiciones de uso en `REGISTRO.md`.
3 fixes + 2 guards aplicados durante la validación (seed pre-ventana de `conocida`, colisiones usan la
última tasa, quiebra-por-funding clampeada, guards de shape y de datos), 11/11 self-tests, no-regresión
exacta del baseline V44, control diferencial de matrices en ambas canastas. Listo para V46 y para el
re-test de V44 con funding real.

⚠️ **Footgun de API (condición de uso #2 del veredicto)**: al motor va `pagos` (`funding_matrix=pagos`);
al ranker va `conocida` (`ranker_carry(conocida, ...)`). NUNCA al revés — pasar `conocida` al motor
cobraría funding TODAS las barras (~8x el real).
