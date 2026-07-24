# Motor M2 — Pairs / Stat-Arb (2 patas)

## Qué es

Motor de backtest para **pairs trading por cointegración**: opera simultáneamente dos patas
(long un activo, short otro) usando el z-score del spread como señal de entrada/salida.

## Diferencias con M1 (cross-sectional)

| Aspecto | M1 (cross-sectional) | M2 (pairs) |
|---|---|---|
| Señal | Ranking de N símbolos por factor | Z-score del spread de 2 símbolos |
| Posiciones | Long top-k / short bottom-k | Long 1 / short 1 (en hedge ratio) |
| Filtro | Ninguno (siempre en el mercado) | Cointegración rolling (si no hay, no operar) |
| Entrada | Cada rebalanceo | Solo cuando z-score excede ±2σ |
| Salida | Cada rebalanceo reemplaza los pesos | Reversión a ±0.5σ, o stop en ±4σ |

## Archivos

- `engine_pairs.py` — Motor de backtest (un solo code-path para real y null)
- `selftest_m2.py` — Tests de respuesta conocida
- `run_v47.py` — Backtest V47 (pairs por cointegración)
- `REGISTRO.md` — Bitácora de validación

## Datos

Lee del cache OHLCV 1h estándar del proyecto (`Fragua/common/datos.py`) sin importar nada
del motor vivo. No modifica ningún archivo fuera de esta carpeta.

## Limitaciones honestas

1. **La cointegración se rompe**: el test ADF es una estadística de muestra; una relación
   estacionaria en 30 días puede dejar de serlo mañana. El stop en ±4σ protege contra el breakdown.
2. **Costos de 2 patas**: cada trade paga fee+slippage por DOS lados (abrir y cerrar × 2 activos).
3. **Funding sobre gross**: el modelo pesimista cobra funding sobre todo el nocional expuesto.
4. **No hay garantía de ejecución simultánea**: en vivo, las dos patas no se llenan al mismo
   instante — el slippage asumido (0.05%/lado) cubre parcialmente esto.
