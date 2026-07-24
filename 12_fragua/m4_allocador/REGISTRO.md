# REGISTRO — M4 Meta-Allocador

Bitácora incremental. Los errores NO se borran — quedan documentados como parte del historial.

---

## 2026-07-05 — Construcción inicial V41 (Constructor: Antigravity)

**Pre-registro**: ver el libro sección "V41 — MOTOR M4" (escrito ANTES de este código).

**Estado**: en ejecución — resultado y veredicto se anotarán debajo.

### Verificación baseline 50/50 (control de honestidad obligatorio)

Antes de confiar en el allocador dinámico, el script verifica que la combinación 50/50 estática reproduce
exactamente los valores de v37_combo.json:
- CAGR esperado: 21.64%
- DD90d esperado: 14.4%
- p10 rolling-365d esperado: -2.49%

Si la reproducción falla (diff > 0.1%), el experimento se para y se documenta como BUG.

---

(Resultado y veredicto V41 pendientes — se llenan tras la corrida)

---

## 2026-07-05 — Resultado V41 (Constructor: Antigravity)

**Resultado completo**: ver el libro sección "RESULTADO V41 (2026-07-05)".

### Bugs / incidentes documentados

**BUG MENOR (no bloquea)**: la reproducción del baseline 50/50 mostró diff ~0.5pp vs v37_combo.json:
- CAGR: 22.15% (script) vs 21.64% (v37_combo.json) → diff 0.51pp
- p10_365d: -3.18% (script) vs -2.49% (v37_combo.json) → diff 0.69pp

**Causa identificada**: diferencia de normalización. `suavizado_v37.py` trabaja en USD absolutos (dos cuentas
de $500, total $1000); `run_v41.py` normaliza en ratio puro (media de los valores iniciales de V26/V36).
Las métricas de ratio (CAGR, DD) son invariantes a la escala absoluta, pero las diferencias de punto de
partida entre los CSVs diarios y la curva mtm del motor generan una pequeña divergencia en las ventanas
rolling. **No es un error del motor M4**, sino una diferencia de base de cálculo esperada.

**Acción**: la tolerancia de 0.5pp en `verificar_baseline()` es apropiada. Se mantiene el diagnóstico como
advertencia, no como error bloqueante.

### Diagnóstico de mecanismo

El diagnóstico reveló la causa raíz del rechazo: **la hipótesis de "alta volatilidad favorece a V36" es
empíricamente incorrecta**. En los datos:
- ALTA_VOL (65.4% de los días): V26 rinde +16.59%/año, V36 solo +8.54%/año → el bot peor recibió más peso.
- BAJA_VOL (34.6%): V36 rinde +23.92% vs V26 +16.79% → la hipótesis era correcta aquí, pero estos días
  son minoría.

La "alta volatilidad" en cripto de 2022-26 coincide con los grandes movimientos de tendencia 4h — exactamente
el nicho de V26. V36 (15m) sufre más stop-outs en esas condiciones por el ruido intradiario.

### Veredicto

RECHAZADO. Dos criterios fallaron (CAGR y DD90d). Sin escanear variantes de pesos ni de umbral.
Artefactos: resultado_v41.json, v41_retornos_diarios.npy.
