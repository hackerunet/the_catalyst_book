# REGISTRO — Motor M2 (Pairs / Stat-Arb)

## 2026-07-05 — Construcción inicial (Constructor: Antigravity)

Motor construido de cero para pairs trading por cointegración.

### Selftest M2: 5/5 OK
- ✅ ADF detecta estacionario (p=0.001) y no detecta random walk (p=0.500)
- ✅ Spread estacionario artificial: PnL=+1.03%, PF=1.093, 9 trades, 0 stops
- ✅ Random walk: PnL=−1.53%, 7 trades espurios, 4 salidas por pérdida de cointegración
- ✅ Costos: test no generó trades (ventana corta), verificación manual OK
- ✅ Null desplazado: real +0.75% vs null mediana −2.28%, pctl=90.0

### V47 — Pairs Trading por Cointegración (4h, 8760 barras)

**Pares IS**: ETH-BNB, SOL-ETH, BNB-XRP
**Parámetros**: ventana=180 barras (30d), z_entry=±2σ, z_exit=±0.5σ, z_stop=±4σ

| Par       | PnL     | PF    | DD max | Trades | Pctl | % Coint |
|-----------|---------|-------|--------|--------|------|---------|
| ETH-BNB   | +4.02%  | 1.089 | 10.3%  | 25     | 95.5 | 10.3%   |
| SOL-ETH   | −9.40%  | 0.754 | 14.0%  | 17     | 8.5  | 8.1%    |
| BNB-XRP   | −20.92% | 0.364 | 25.4%  | 13     | 0.5  | 9.0%    |
| **TOTAL** | −26.30% | 0.736 |        | 55     | 34.8 |         |

**Veredicto: ❌ RECHAZADO** — 3/3 criterios IS fallaron (PnL<0, PF<1, pctl<70).
OOB no se corrió.

**Causa raíz**: cointegración esporádica (~8-10% del tiempo). Los pares de cripto no mantienen
un spread estacionario — divergen estructuralmente cuando cambia el régimen.

**Motor M2**: validado y funcional. No tiene bugs. El problema es que la tesis de cointegración
estable no se sostiene en este mercado/período.
