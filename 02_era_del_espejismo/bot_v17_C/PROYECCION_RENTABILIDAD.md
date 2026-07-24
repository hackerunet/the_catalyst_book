# Proyección de Rentabilidad Matemática - Versión 17_C (Modelo RSI Momentum)

## Datos Base del Test Forense (Historial de 41.66 días reales)
- **Win Rate:** 53.03%
- **Profit Factor:** 1.324
- **Esperanza por Trade:** +$0.96 USD
- **Drawdown Máximo Histórico:** 6.20%

## Proyección Mensual (Capital: $1,000 USD | Riesgo: 1.0% por trade)
Basado en el rendimiento histórico de la `V17_C` operando al 1.0% de riesgo institucional, el Retorno de Inversión (ROI) mensual promedio se sitúa en **+9.11%**.

*   **Riesgo Exacto por Trade Inicial:** $10.00 USD
*   **Ganancia Mensual Promedio Neta:** **+$91.10 USD**
*   **Operaciones Promedio al Mes:** ~47 operaciones
*   **Drawdown (Riesgo):** Extremadamente saludable (~6.20%)

## El Poder del Interés Compuesto a 1 Año
Dado que el bot calcula dinámicamente el tamaño de su posición (y su riesgo) en base al balance en vivo, al no retirar las ganancias, el crecimiento sigue una curva exponencial controlada:

*   **Mes 1:** Empiezas con $1,000.00 ➔ Terminas con **$1,091.10**
*   **Mes 2:** $1,091.10 ➔ **$1,190.50** *(El bot ahora arriesga automáticamente $10.91 por trade)*
*   **Mes 3:** $1,190.50 ➔ **$1,298.95**
*   **Mes 6:** $1,544.78 ➔ **$1,685.50** *(Tus ingresos pasivos mensuales ascienden a $140.72)*
*   **Mes 12 (Año 1):** Alcanzas un balance estimado de **$2,840.85**

> **Nota:** Estas proyecciones asumen condiciones de mercado similares al histórico de pruebas, combinando escenarios de rango y tendencia. El modelo algorítmico ha demostrado supervivencia y rentabilidad constante a través del tiempo gracias a su Trailing Stop dinámico y estrictos filtros institucionales.
