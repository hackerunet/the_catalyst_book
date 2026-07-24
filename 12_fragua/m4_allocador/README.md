# M4 — Motor Meta-Allocador

## Qué modela

M4 opera **sobre las curvas de equity ya producidas por otros motores** — no genera señales de mercado
propias. Dada una colección de curvas de equity diarias (p.ej. V26 y V36), produce una curva combinada
ponderando dinámicamente cada fuente según alguna señal de régimen.

Actualmente: un solo experimento, **V41**, que pondera V26↔V36 según el régimen de volatilidad de la
flota (vol realizada rolling 90d, umbral = mediana expandida causal).

## Qué NO modela

- No genera transacciones de mercado directas (los bots subyacentes ya las generan).
- No modela costos de rebalanceo del allocador (razonamiento: cambiar la ponderación contable entre dos
  bots ya en vivo no genera órdenes adicionales en Binance).
- No tiene OOB de basket — solo OOB temporal (la segunda mitad de la ventana de 4 años).

## Limitaciones honestas

1. **Curva de V36 en los primeros 2 años es genuinamente OOS** (su validación original cubría solo 2024-26),
   pero la curva de V26 se calculó sobre toda la ventana de 4 años — no es un backtest completamente virginal.
2. **Sin self-tests formales del motor M4** (el motor es solo pandas — álgebra de series). Se verifica
   manualmente que el baseline 50/50 reproduce v37_combo.json dígito a dígito antes de confiar en
   el resultado dinámico.
3. **Riesgo de correlación espuria régimen-ciclo** (declarado en el pre-registro V41): el diagnóstico
   de mecanismo es obligatorio, no opcional.

## Archivos

- run_v41.py — backtest del allocador dinámico V41 (regime-switching por volatilidad).
- REGISTRO.md — bitácora incremental (pre-registro, bugs, resultado, veredicto).
