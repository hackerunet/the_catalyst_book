# OPCIÓN 1 BETA — Plan de evolución de V21 (capa de régimen + frecuencia diaria)

> Documento de retoma. Generado tras revisión completa de logs (`v21_live.log`, `mesa.log`,
> `test_v21_*.log`, `trade_forensics.jsonl`) y del código (`estrategia_v21_Master.py`,
> `simulador_institucional_upgraded.py`, `mesa_de_dinero.py`, `telemetria_quant.py`,
> `diario_forense_claude.py`). No se modificó código en esta sesión — esto es un plan a
> retomar para una nueva versión (V22 / "OPCION_1_BETA").

---

## 1. Diagnóstico (datos extraídos de los logs, no opinión)

### 1.1 Backtest de validación más reciente (motor de V21, ~33 días, 6 símbolos, capital $4,969.60)
```
Net PnL:      +9.99%   ($4,969.60 → $5,466.10)
Trades:       66 (≈48 cerrados con desglose forense)
Win Rate:     43.94%   (29 ganadores / 37 perdedores)
Profit Factor: 1.239
Esperanza/trade: +$7.52
Max Drawdown: 8.63%
Avg Win/Loss: $88.69 / $56.10
Salidas:      35 por STOP LOSS · 13 por TRAILING STOP (runner)
```
Distribución de trades cerrados por símbolo: XRP 13, LINK 10, ADA 9, BNB 7, SOL 5, ETH 4
→ ritmo real: **~2 operaciones/día para todo el portafolio**, o **1 cada 5–8 días por símbolo**.

### 1.2 Operación en vivo (Binance Testnet, cuenta real de prueba)
- Balance actual: **$4,969.60**, **0 posiciones abiertas**, **0 trades ejecutados en ~23 h** desde
  el último arranque estable (07/Jun 13:32). Confirma en tiempo real el problema de baja cadencia.
- Hubo una ventana de inestabilidad el 06/Jun (6 reinicios con "CRASH DEL SISTEMA Código 1")
  antes de estabilizar — ya resuelto, pero documentado por si reaparece.

### 1.3 Hallazgo nuevo — concentración direccional oculta
Las 9 aperturas registradas en `trade_forensics.jsonl` son **todas SHORT, todas Puerta A
"Donchian Breakdown", y casi simultáneas en ETH/SOL/BNB/XRP/ADA/LINK**. Esto significa que el
sistema, en la práctica, no opera 6 edges independientes: cuando el mercado gira, dispara la
**misma apuesta direccional 6 veces a la vez** (correlación de criptoactivos). Las métricas
agregadas (PF, win rate) no muestran este riesgo de concentración — un solo movimiento adverso
de "BTC arrastra a las alts" puede activar el stop loss en varios símbolos al mismo tiempo.

### 1.4 Hallazgo nuevo — el diario forense de Claude está roto
`trade_forensics.jsonl` tiene 9 entradas APERTURA pero solo 5 CIERRE, y **las 5 dicen
`"Claude no disponible"`** (el subproceso `claude -p ...` retorna código de error sin stderr).
El feedback post-mortem — que es la pieza que retroalimenta el aprendizaje del sistema y que tú
identificaste como "el archivo más importante de la estrategia" — **no se está generando**. Solo
se está capturando la mitad del diario (contexto de apertura sí, análisis de cierre no).

### 1.5 Otros puntos confirmados al revisar el motor
- El backtest **no modela comisiones ni slippage**, pese a ejecutar órdenes `MARKET` (taker).
  En Binance Futures (~0.04–0.05%/lado) esto infla el +9.99% reportado.
- El 73% de las salidas son por Stop Loss (perfil "muchas pérdidas pequeñas, pocas ganancias
  grandes 3R") — válido como estilo trend-following, pero es la causa estructural de por qué el
  bot pasa la mayoría del tiempo sin operar: exige confluencia estricta (ruptura Donchian-24 +
  alineación MA7/EMA9/MA99 + MACD) para Puerta A (95% convicción).
- Riesgo uniforme de 1% para los 6 símbolos sin distinguir su volatilidad/régimen individual.
- Tamaño de muestra pequeño (48–66 trades) → PF 1.24 es estadísticamente débil, no concluyente.

**Conclusión del diagnóstico:** la arquitectura de gestión de riesgo (anti-martingala, circuit
breaker de 3 pérdidas/semana, trailing stop con runner, journaling) es sólida y profesional, pero
el *edge* medido es delgado, la muestra es pequeña, hay concentración direccional oculta, y el
diseño (alta confluencia + mismo filtro para todos los activos) produce baja cadencia por diseño
— justo lo que tú percibiste y pediste resolver.

---

## 2. Plan propuesto — Capa de Régimen Adaptativo (no reemplaza Puerta A, la complementa)

**Idea central:** en lugar de relajar los filtros actuales (lo que degradaría el PF ya delgado),
añadir una **capa de clasificación de régimen por símbolo** que permita usar la sub-estrategia
correcta según el contexto de cada activo en cada momento. Esto produce más señales de forma
natural — sin diluir la calidad de cada una — porque cada régimen tiene su propia herramienta.

### 2.1 Clasificador de régimen (nuevo, por símbolo, en cada vela cerrada)
Calcular un indicador de volatilidad/tendencia (ej. ATR% percentil, ancho de Bandas de Bollinger,
o ADX) y etiquetar cada par como:
- `TENDENCIA` (volatilidad direccional alta/ADX alto)
- `RANGO` (volatilidad lateral, precio oscilando entre soporte/resistencia)
- `BAJA VOLATILIDAD` (compresión, candidato a "squeeze")

### 2.2 Asignación de sub-estrategia según régimen
- **`TENDENCIA` → mantener Puerta A tal cual** (Donchian breakout, 95% convicción, riesgo 1%,
  TP 3R). Es la pieza más sólida del sistema actual — no tocarla.
- **`RANGO` / `BAJA VOLATILIDAD` (donde hoy NO pasa nada) → nueva "Puerta C" de reversión a la
  media**: fade de extremos en bandas de Bollinger/Donchian + RSI en sobrecompra/sobreventa, SL
  ajustado y objetivos más modestos (1–1.5R), operando con **riesgo reducido (0.3–0.5%)**. Esta
  es exactamente la oportunidad de "baja convicción pero alta frecuencia" que hoy llena los días
  muertos con cero actividad.

### 2.3 Presupuesto de riesgo escalonado (control de calidad agregada)
- Alta convicción / tendencia: 1% (igual que ahora)
- Exploración / rango: 0.3–0.5%
- Esto evita que el riesgo total del portafolio crezca solo porque se añaden más oportunidades —
  el riesgo agregado por día se mantiene acotado aunque el número de operaciones suba.

### 2.4 Mitigar la concentración direccional (punto 1.3)
Añadir un límite de exposición correlacionada: ej. "máximo N posiciones abiertas simultáneas en
la misma dirección (LONG o SHORT) entre todo el portafolio" o un ajuste de tamaño que reduzca el
riesgo de la 2da, 3ra... señal en la misma dirección dentro de una ventana corta de tiempo. Esto
convierte el riesgo de "una apuesta direccional x6" en una exposición controlada.

### 2.5 Higiene de backtest / validación
- Incorporar comisiones y slippage al motor de simulación antes de sacar conclusiones de
  rentabilidad — sin esto el +9.99% es optimista.
- Ampliar la muestra: correr 3–6 meses de backtest con validación walk-forward (varios regímenes
  de mercado) antes de escalar capital — 48–66 trades no bastan para confiar en PF 1.24.

### 2.6 Reparar el diario forense de Claude (punto 1.4)
Diagnosticar por qué `claude -p ...` retorna error sin stderr en el hilo del post-mortem
(`analisis_post_mortem_claude` en `diario_forense_claude.py`) — probablemente un problema de
entorno/PATH/auth al invocarse desde un hilo en background del simulador. Sin esto, la mitad del
feedback loop que retroalimenta la estrategia (y que tú valoras como pieza central) no funciona.

---

## 3. Mantener / extender — Comunicación con el trader vía Telegram

Requisito explícito tuyo: **conservar el aviso por Telegram cuando el bot está operando, para que
tú decidas si tomar el TP en ese momento o dejar correr la tendencia hacia el objetivo completo.**

Esto **ya existe parcialmente** en el sistema actual y debe preservarse/reforzarse en la nueva
versión:
- `simulador_institucional_upgraded.py::evaluate_open_trades` emite `ALERTA_PROGRESO|...` cada
  vez que una posición abierta avanza un decil (10%, 20%, ... ) hacia su TP, incluyendo una
  "probabilidad de reversión" estimada.
- `mesa_de_dinero.py` recibe esa alerta y envía un mensaje de Telegram con botones interactivos:
  **"✅ TOMAR PROFIT AHORA"** / **"⏳ DEJAR CORRER"**, y al pulsar "Tomar Profit" llama al endpoint
  `/api/close_trade` del simulador para cerrar la posición manualmente.
- También existen alertas de apertura (`ALERTA_TRADE`) y cierre (`ALERTA_CIERRE`) con contexto
  (símbolo, dirección, precio, balance, % de riesgo).

**Para la nueva versión (V22 / OPCION_1_BETA):**
- Conservar este flujo de decisión humano-en-el-loop tal cual (es valioso y ya funciona).
- Extender los mensajes de progreso para que indiquen también el **régimen detectado** en ese
  momento (TENDENCIA / RANGO / BAJA VOLATILIDAD) y la **puerta/sub-estrategia** que originó el
  trade — así tu decisión de "tomar TP ahora vs. dejar correr" estará informada por el contexto
  de régimen, no solo por el avance porcentual hacia el TP.
- Asegurar que las alertas de Puerta C (reversión a la media, objetivos más cortos) también
  disparen el mismo mecanismo de decisión, adaptado a su horizonte más corto (deciles más
  frecuentes, ya que sus TPs son de 1–1.5R en vez de 3R).

---

## 4. Próximos pasos al retomar este documento
1. Validar (con datos, no supuestos) la hipótesis de régimen: ¿cuántas señales adicionales por
   día generaría la Puerta C en los mismos 33 días del backtest, y con qué PF/win rate propio?
2. Diseñar y backtestear la Puerta C de forma aislada antes de integrarla al motor en vivo.
3. Reparar el post-mortem de Claude (sección 2.6) — es deuda técnica de bajo costo y alto valor
   informativo para iterar el sistema.
4. Añadir el límite de exposición correlacionada (sección 2.4) y volver a correr el backtest
   completo con comisiones/slippage modelados (sección 2.5) para obtener una cifra de
   rentabilidad realista antes de comparar V21 vs. V22.
5. Solo entonces decidir si V22 reemplaza a V21 en vivo o corre en paralelo (paper) para comparar.
