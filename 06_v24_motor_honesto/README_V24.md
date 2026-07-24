# V24-FABLE — Motor de Backtest Honesto

Clon de V22 (estrategia **idéntica**: Tres Puertas + clasificador de régimen)
con el **motor de simulación reparado**. V24 no cambia QUÉ se opera — cambia
CÓMO se mide, porque la revisión independiente (2026-06-10) encontró que el
medidor de V22 estaba roto en varios puntos, con sesgos del mismo orden de
magnitud que el edge reportado.

## Fixes del motor (vs V22)

1. **Backtest de reloj global (entrelazado)** — `run_backtest_interleaved()`.
   V22 procesaba cada símbolo completo en secuencia compartiendo el balance:
   el balance "viajaba en el tiempo", el orden de símbolos era un parámetro
   oculto, y `MAX_SAME_DIRECTION_POSITIONS` casi nunca ataba. Ahora los 6
   símbolos avanzan juntos por timestamp (salidas primero, entradas después),
   y el tope de exposición se comporta como en vivo. El "efecto cascada"
   documentado 8 veces en V22 era en gran parte artefacto de esto.

2. **Orden intravela PESIMISTA** — en V22 el breakeven se armaba con el high
   de la misma vela ANTES de chequear el SL contra su low (y el trailing del
   RUNNER igual): asumía siempre el orden favorable high→low, convirtiendo
   pérdidas reales de −1R en salidas a ~$0. Ahora los stops se evalúan tal
   como quedaron al cierre de la vela anterior; breakeven/trailing se arman
   al final de la vela (en vivo, tick a tick, el armado intravela sigue
   siendo legítimo).

3. **Modelo de costos completo** — comisión taker 0.05%/lado (antes 0.04%),
   **slippage 0.05%/lado** (antes 0) y **funding 0.01%/8h** (antes 0; LONG
   paga, SHORT recibe, por cada marca 00/08/16 UTC cruzada). Todo en
   `cerrar_tramo()`, el ÚNICO punto de cálculo de PnL de cierre (V22 tenía 7
   sitios duplicando la fórmula).

4. **Un solo code path backtest/vivo** — el backtest ahora pasa la vela
   completa (incl. `close`) e indicadores causales: el auto-cierre de Puerta
   C y el cierre por AGOTAMIENTO ESTRUCTURAL (antes solo-vivo) quedan
   cubiertos por la regresión.

5. **Bugs corregidos** — `reversal_prob` se usaba sin asignar en el
   auto-cierre de Puerta C (UnboundLocalError latente / valor stale de otro
   trade) → ahora `_calc_reversal_prob()` con valores causales; el bloque
   "activación anticipada 0.5R" de B/C era código muerto inalcanzable →
   eliminado; el cierre manual por Telegram ignoraba RUNNERs → incluidos;
   `exit_time` tz-aware vs naive → normalizado.

6. **Riesgo plano 1%** — eliminado el multiplicador 1.5x post-ganador de V22
   (anti-martingala no documentada que amplificaba la dependencia de
   trayectoria y contaminaba cada comparación A/B).

7. **Benchmark buy & hold + metadatos de ventana** en cada resumen
   (`benchmark_buy_hold_pct`, `window_start`, `window_end`). Si la estrategia
   no supera comprar-y-mantener, lo que hay es beta del mercado, no edge.

## Advertencias que el motor NO puede arreglar

- **La "ventana viva" NO es out-of-sample**: comparte ~99% de las velas con
  la ventana fija (ambas son 3000 velas, extremos a horas/días de distancia).
  La única validación honesta es forward (datos posteriores al freeze) o un
  holdout disjunto jamás usado para seleccionar filtros.
- Los ~7 filtros de entrada heredados de V22 fueron seleccionados sobre UNA
  ventana congelada — re-validarlos por ablación walk-forward con este motor
  antes de confiar en ellos.

## Operación

- Puerto dashboard/API: **8056** (8053=V21, 8054=V22, 8055=V23)
- Log: `mesa_v24.out` / `v24_live.log`
- Lanzar (siempre venv + `-u`):
  ```
  cd bot_alpha_portfolio/v24-fable && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u mesa_de_dinero.py > mesa_v24.out 2>&1 & disown
  ```
- `backtest_history.csv` arranca VACÍO a propósito: los números de este motor
  no son comparables con las filas de V22. La primera corrida re-baseliniza.
- **NO lanzar en paralelo con V22/V23 sin considerar**: comparten cuenta
  testnet (SINC_BALANCE pisa el balance interno) y token de Telegram (los
  `getUpdates` compiten por el offset).
