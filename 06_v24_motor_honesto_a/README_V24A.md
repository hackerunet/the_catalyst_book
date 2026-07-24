# V24-FABLE-A — Sistema Único de Momentum

Rediseño de la ESTRATEGIA desde cero, partiendo de las conclusiones del ciclo
V22 como traders profesionales — en lugar de seguir parchando lo que tiene
fallas. Corre sobre el **mismo motor honesto de V24-FABLE** (reloj global,
intravela pesimista, comisión 0.05% + slippage 0.05% + funding 0.01%/8h,
riesgo plano), de modo que **V24 vs V24A es una comparación A/B limpia sobre
la misma ventana congelada**.

## La tesis

Todo lo que funcionó en V22 (dentro Y fuera de la ventana de ajuste) era una
sola cosa: **momentum alineado con tendencia**. Todo lo que falló era el resto:
la reversión a la media (Puerta C, −$195 OOS), el régimen BAJA_VOLATILIDAD
(único régimen negativo OOS), y la complejidad acumulada de 7 filtros minados
sobre una ventana. V24A apuesta a UN sistema coherente con pocos parámetros
estándar, en vez de tres sub-estrategias con taxonomía de regímenes.

## El sistema

**FILTRO DE TENDENCIA** (reemplaza al clasificador de 4 regímenes):
- LONG: precio > MA99, EMA9 > MA99, y **MA99 con pendiente al alza** (~6h).
- SHORT: espejo. Sin tendencia → no se opera. La pendiente es la novedad:
  precio sobre una MA99 plana es rango, y en rango este sistema no tiene edge.

**DISPARADOR 1 — Breakout** (etiqueta 'A', riesgo 1%):
- Cierre rompe Donchian(24) con persistencia de 2 velas *(validado V22)*
- Body ≥ ATR *(la mejora más grande del proyecto)*
- Volumen ≥ 1.5× su media *(validado)* · RSI ≤80 / ≥20 *(validado)*

**DISPARADOR 2 — Impulso** (etiqueta 'B', riesgo 1%):
- Marubozu/Engulfing en dirección de la tendencia *(el componente con más
  muestra y más robusto de V22)*
- Volumen > media · RSI ≤70 / ≥30 *(validados en este contexto)*

**SALIDA ÚNICA** (la gran diferencia con la ex-Puerta B y su 1R/1R frágil a
costos — con comisión+slippage el TP de 1R perdía ~0.2R por trade):
- Stop inicial: **2.5× ATR**, acotado a [1.5%, 4%] del precio (adaptativo;
  el 3% plano era la restricción activa en casi todos los full-risk losers,
  y ATR×1.5 ya se probó y era demasiado apretado)
- Breakeven a +1R (ahora para AMBOS disparadores)
- TP parcial 50% a **2R** + runner con trailing *(estructura validada)*
- **TIME STOP 48h**: si nunca alcanzó +0.5R, cierre a mercado (un trade
  muerto paga funding y bloquea cupo de exposición sin tesis vigente)
- Cierre táctico por agotamiento estructural (heredado, ahora también en backtest)

**ELIMINADO por completo**: Puerta C / reversión a la media, el gating por
régimen, TENDENCIA_EMERGENTE como caso especial, el riesgo 0.4%, los stops
de porcentaje plano. Con el motor de reloj global, C ya NO es "load-bearing"
(eso era un artefacto del backtest secuencial), así que se puede borrar limpio.

## Qué esperar

- MENOS trades que V22/V24 (el filtro de pendiente + un solo sistema) —
  eso es deliberado: menos fricción de costos, más calidad por trade.
- El número que importa: PnL neto vs `benchmark_buy_hold_pct` en la MISMA
  ventana, y la comparación V24 vs V24A en la ventana fija.
- Los parámetros (2.5×ATR, 2R, 48h, 6 velas de pendiente) son convenciones
  estándar elegidas a priori, NO minadas de la ventana congelada — pero la
  única validación que cuenta sigue siendo forward / walk-forward.

## Operación

- Puerto dashboard/API: **8057** (8053=V21, 8054=V22, 8055=V23, 8056=V24)
- Log: `mesa_v24a.out` / `v24a_live.log` · Telegram prefix: `[V24A_MOMENTUM]`
- Lanzar (siempre venv + `-u`):
  ```
  cd bot_alpha_portfolio/v24-fable-a && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u mesa_de_dinero.py > mesa_v24a.out 2>&1 & disown
  ```
- Mismas advertencias que V24: cuenta testnet compartida (SINC_BALANCE) y
  token de Telegram compartido (los getUpdates compiten) — no lanzar en
  paralelo con V22/V23/V24 sin decidir cómo manejar eso.
