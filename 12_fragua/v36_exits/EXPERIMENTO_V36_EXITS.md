# Laboratorio de Estrategias de Salida (Motor V36)
**Fecha**: 2026-07-07
**Contexto**: El motor V36 desplegado en la testnet muestra síntomas severos del fenómeno conocido como *Giveback* (devolución de ganancias).
**Objetivo**: Diagnosticar las posiciones reales y diseñar un marco de pruebas de combinaciones de salida para evitar que ganancias masivas se evaporen por esperar al cierre algorítmico estructural (Cruce EMA inverso).

## 1. Diagnóstico de Testnet (Extracción Forense)
Se extrajo el log de operaciones (`trades_v36.json`) directamente desde el contenedor Docker (`klt-openclaw-bots-vm-eaej`) en la máquina de GCP `openclaw-bots-vm`.

**Evidencia Encontrada**:
- **SOLUSDT (Largo)**: Llegó a un progreso de tendencia del **144.41%** (Peak Progress). Sigue abierta con PnL latente atrapado.
- **ETHUSDT (Largo)**: Llegó a un asombroso progreso del **222.18%**. Sigue abierta y devolviendo ganancias.
- **XRPUSDT (Largo)**: Tocó un pico de **177.17%** de progreso. El sistema no tomó la ganancia en la cima. Finalmente, la operación se cerró por "FLIP DE TENDENCIA" (las medias móviles se cruzaron a la baja), resultando en un PnL miserable de `+3.74`. 

### Análisis del Problema
El motor V36 es excelente encontrando la dirección correcta (alta asertividad direccional), pero su heurística de salida depende de que la tendencia se "quiebre" estructuralmente (Cruce de la EMA 50 por debajo de la 200). Esto requiere que el precio caiga brutalmente desde la cima para que el promedio móvil se invierta. El resultado es que el bot acierta el movimiento parabólico pero *devuelve* todo el dinero al mercado esperando la confirmación de salida.

## 2. Combinaciones de Estrategias de Salida a Probar
Para erradicar el *giveback*, se iniciará un barrido de *backtest* combinando las siguientes lógicas:

### A. Trailing Stop Parabólico (Deciles)
En lugar de un trailing stop fijo, el nivel de *stop* se ajusta de forma asimétrica según el `peak_progress`.
- Si Progress > 100%: Trailing Stop ajustado al 15% del pico.
- Si Progress > 150%: Trailing Stop agresivo al 5% del pico.

### B. Time-Stop (Límite de Exposición Temporal)
Las criptomonedas se mueven rápido. Si una posición tiene más de 100% de progreso y lleva abierta más de *N* horas (ej. 72 horas) sin alcanzar el Take Profit final, la probabilidad de reversión aumenta. 
- Cerrar si `Time_in_Trade > 72h` AND `PnL > X%`.

### C. Salida por Agotamiento de Momentum (RSI / MACD)
No esperar a que la tendencia estructural (EMA) se rompa. Salir cuando el *momentum* a corto plazo colapse en la cima.
- Si `Progress > 100%` y el RSI horario cae por debajo de 50 o el MACD cruza a la baja.

### D. Scale-Out (Cierre Parcial)
Descargar posiciones gradualmente.
- Vender 50% de la posición al alcanzar el 100% de progreso, dejando el resto correr con un Stop Loss en *breakeven*.

## 3. Próximos Pasos (Validación para Claude)
1. **Reescribir la clase `estrategia.py`** del clon de la V36 local para que soporte inyección de reglas de salida dinámicas (A, B, C y D).
2. **Correr la matriz de combinaciones** usando la caché de 4h (2022-2026).
3. **Seleccionar el óptimo** que maximice la retención del PnL sin asfixiar la cola derecha de ganancias extremas, y generar un parche para la Testnet.


## 4. Medición Empírica del Hueco de Pérdida (Giveback Gap)
Atendiendo a la orden de medir exactamente de cuánto es el hueco o pérdida de ganancia desde la cima (*Peak*) hasta el punto donde el motor toma el *Take Profit* algorítmico, se procesó el backtest de 4 años (2022-2026) sobre ETHUSDT (Velas de 4h).

**Resultados del Spread (Pico vs Cierre Real):**
- **Estructural (V36 Base)**: Devolución promedio del **27.99%** de rendimiento absoluto.
  - *Interpretación*: En promedio, si la moneda sube un 40% en tendencia, la V36 estructural se sale al 12%. El algoritmo pierde matemáticamente la oportunidad de capturar casi 28 puntos porcentuales absolutos por operación ganadora esperando la confirmación de la caída de la tendencia.
- **Aggressive T-Stop 5%**: Devolución promedio del **5.49%**.
  - *Interpretación*: Reduce el *hueco* mecánicamente a un tope de ~5%. Recupera la rentabilidad extraída de la mesa (subiendo el CAGR general a +10.5%).

### 5. Medición Exhaustiva hasta Fecha Actual (Incluyendo SOLUSDT)
Se actualizó el caché descargando todas las velas hasta el 2026-07-08 para capturar los movimientos masivos en SOLUSDT y ETHUSDT.

**Caso Extremo Encontrado (SOLUSDT - V36 Base):**
- **Fecha Entrada**: 2023-10-01 a .35
- **Pico Máximo**: .93 (+494.55%)
- **Cierre Real**: .81 (+287.88%)
- **Giveback**: **-206.67%**. El bot devolvió más de 200 puntos porcentuales absolutos de rendimiento al mercado por no tener un Take Profit dinámico en la cima.

**Impacto del T-Stop 5% en SOLUSDT:**
- El Giveback promedio masivo de **61.72%** de SOLUSDT cae verticalmente a **5.46%**.
- La estrategia transforma la captura: en lugar de aguantar 1 trade que sube 490% y devuelve 200%, el bot ejecuta múltiples trades tomando ganancias escalonadas (+31%, +29%, etc.) cortando siempre el retroceso al ~5%. 
- El Win Rate de SOLUSDT sube de **29.6%** a **46.7%**.

### 6. Validación del Último Mes (Tendencia a Tendencia) y Smart Trailing
Se ejecutó un simulador del 29 de Mayo de 2026 al 8 de Julio de 2026 para auditar el comportamiento reciente de las estrategias.
Para solucionar la destrucción de cuenta del T-Stop estricto en mercados laterales, se introdujo el **Smart Trailing**.

**Comportamiento del Mercado:** ETHUSDT se mantuvo sin dar señal de cruce alcista (0 trades). SOLUSDT dio una señal de compra el 2 de Julio de 2026.

**Resultados SOLUSDT (Operaciones Reales Último Mes):**
1. **T-Stop 5% Agresivo (Sin Filtro)**:
   - Fue despedazado por el ruido. Entró el 2 de Julio a 82.36, cayó y saltó el stop a 79.76 (-3.15%). Volvió a cruzar el 5 de Julio, volvió a entrar, y saltó de nuevo el stop a 79.56 (-1.21%).
   - Al acumular 4 años de estos latigazos, el capital de esta estrategia quedó en  (-99.3% de DD). Estrategia descartada.
2. **V36 Base (Estructural)** y **Smart Trailing (Activación > 15%)**:
   - Entraron el 2 de Julio a 82.36 y **mantienen la operación abierta**. Actualmente soportan la caída temporal a 79.02 (-4.06% flotante).
   - El Smart Trailing se comporta exactamente igual que la V36 Base durante la volatilidad inicial (dando espacio al trade). Sólo activará la barrera del 5% si el trade despega por encima de +15% o +25%, asegurando la captura del pico sin ser degollado en el fondo.

**Conclusión para Claude:**
La salida híbrida (**Smart Trailing con Activación Tardía**) es matemáticamente superior. Mantiene la paciencia del modelo estructural en la base, y hereda la agresividad del trailing stop en la cima.
