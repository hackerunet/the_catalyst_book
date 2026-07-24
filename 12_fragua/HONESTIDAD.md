# Rúbrica de Honestidad — checklist de validación para Fable

> Estos son los MISMOS criterios que hacen confiable al motor actual (`stable_v25_prototype/`) y que
> falsificaron todo lo que no tenía edge. Todo motor de `Fragua/` debe pasarlos ANTES de que sus números
> valgan algo. Fable audita cada motor contra esta lista y documenta el resultado en el `REGISTRO.md` del
> motor.

## A. Anti-lookahead (mirar el futuro = el pecado capital)
- [ ] **A1** La señal/peso en la barra `t` usa EXCLUSIVAMENTE datos hasta el cierre de `t` (nunca `t+1`).
- [ ] **A2** Los retornos se realizan de `t → t+1` (o `t` cierre → `t+1` cierre); jamás se rankea con el
  mismo retorno que después se cobra.
- [ ] **A3** Ningún indicador usa ventanas centradas (`center=True`), `.shift(-n)`, ni normalización con
  estadísticos de toda la serie (media/std global). Test: perturbar datos futuros NO debe cambiar una
  decisión pasada.

## B. Costos completos (el backtest ingenuo ignora costos = optimista)
- [ ] **B1** Comisión + slippage se cobran sobre el TURNOVER real de cada rebalanceo (no gratis, no una vez).
- [ ] **B2** Las constantes de costo coinciden con las del motor vivo (taker 0.05%, slippage 0.05%,
  funding 0.01%/8h) — espejadas, verificables.
- [ ] **B3** Funding modelado (o, si se omite, DOCUMENTADO como término no modelado y evaluado su signo/impacto
  — para libros market-neutral el funding es de primer orden, no despreciable).
- [ ] **B4** El costo es pesimista ante la duda (redondea en contra del sistema, nunca a favor).

## C. Un solo code-path (backtest ≠ vivo = divergencia silenciosa)
- [ ] **C1** La lógica de decisión (ranking/señal) es una función PURA, usada idéntica por el motor real y
  por el null. El null cambia solo la señal, nada de la contabilidad.
- [ ] **C2** No hay ramas "solo-backtest" que un futuro modo-vivo no ejecutaría igual.

## D. Contabilidad correcta (la mecánica del PnL)
- [ ] **D1** El PnL de cartera de un periodo = suma ponderada de retornos por peso, con pesos que driftean
  correctamente entre rebalanceos (un peso no se "resetea" mágicamente sin costo).
- [ ] **D2** Neutralidad verificada: si la estrategia dice ser dollar-neutral, `sum(pesos) ≈ 0` y
  `gross = sum(|pesos|)` = el objetivo, en cada rebalanceo.
- [ ] **D3** La curva de equity es multiplicativa y consistente: `equity[t+1] = equity[t]·(1 + ret − costos)`.
  El drawdown se mide sobre esa curva (mark-to-market).
- [ ] **D4** Los self-tests de respuesta ANALÍTICA conocida pasan (el motor reproduce un número calculable a
  mano dentro de tolerancia de float).

## E. Prueba contra el azar (PnL positivo NO basta)
- [ ] **E1** Existe un null bien definido (aleatorizar la SEÑAL manteniendo cadencia/turnover/costos), y el
  percentil del resultado real vs la distribución null se reporta.
- [ ] **E2** El null es determinista con semilla (reproducible).
- [ ] **E3** Criterio de aceptación pre-registrado: percentil ≥ 70 (además de PnL>0 y PF>1 donde aplique).

## F. Fuera de canasta (OOB) y correlación
- [ ] **F1** El motor puede correr sobre un basket de símbolos distinto sin cambios de código.
- [ ] **F2** Hook para medir correlación de la curva de equity diaria vs V26/V36 (el objetivo real: baja
  correlación).

## G. Determinismo y reproducibilidad
- [ ] **G1** Misma entrada + misma semilla → mismo resultado, bit a bit.
- [ ] **G2** Control de no-regresión: un cambio que NO debería afectar resultados, no los afecta.

---

### Veredicto de validación (lo llena Fable por motor)
Para cada motor, Fable escribe en su `REGISTRO.md`: qué ítems pasan ✅, cuáles fallan ❌ (con el error
concreto: archivo:línea + qué está mal), cómo lo arregló, y el veredicto final: **VALIDADO** (listo para
backtest serio) o **BLOQUEADO** (con la lista de lo que falta). Los errores encontrados NO se borran del
registro — quedan documentados como parte del historial, igual que en el libro.
