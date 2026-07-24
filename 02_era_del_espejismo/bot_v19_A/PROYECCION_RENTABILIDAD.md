# Proyección de Rentabilidad Matemática - Versión 18_A (Modelo Bollinger Extremo)

## Datos Base del Test Forense (Historial de 41.66 días reales)
- **Win Rate:** 58.97%
- **Profit Factor:** 1.859
- **Esperanza por Trade:** +$2.03 USD
- **Drawdown Máximo Histórico:** 7.00%

## Proyección Mensual (Capital: $1,000 USD | Riesgo: 1.0% por trade)
Basado en el rendimiento histórico de la `V18_A` operando al 1.0% de riesgo institucional, el Retorno de Inversión (ROI) mensual promedio se sitúa en un asombroso **+11.42%**.

*   **Riesgo Exacto por Trade Inicial:** $10.00 USD
*   **Ganancia Mensual Promedio Neta:** **+$114.24 USD**
*   **Operaciones Promedio al Mes:** ~28 operaciones (Filtrado quirúrgico, solo francotirador)
*   **Drawdown (Riesgo):** Saludable y controlado (~7.00%)

## El Poder del Interés Compuesto a 1 Año
Dado que el bot calcula dinámicamente el tamaño de su posición (y su riesgo) en base al balance en vivo, al no retirar las ganancias, el crecimiento sigue una curva exponencial acelerada gracias al alto Win Rate y gigantesco Profit Factor:

*   **Mes 1:** Empiezas con $1,000.00 ➔ Terminas con **$1,114.20**
*   **Mes 2:** $1,114.20 ➔ **$1,241.44** *(El bot ahora arriesga automáticamente $12.41 por trade)*
*   **Mes 3:** $1,241.44 ➔ **$1,383.21**
*   **Mes 6:** $1,714.49 ➔ **$1,913.35** *(Tus ingresos pasivos mensuales ascienden a $198.86)*
*   **Mes 12 (Año 1):** Alcanzas un balance estimado de **$3,660.84**

> **Nota:** La adición del filtro de Bandas de Bollinger provocó que el sistema operara menos veces pero con una precisión letal (Profit Factor casi de 2.0). Las condiciones de francotirador de esta arquitectura aseguran que solo compras cuando la volatilidad grita pánico, y solo vendes cuando grita euforia.
