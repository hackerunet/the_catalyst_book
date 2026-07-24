# V23 — Quality-Ranked Exposure Allocator (HELD, not running)

Created 2026-06-10. V23 is a clone of V22 with ONE behavioral change: a **quality-ranked
exposure allocator** in the LIVE trading path. It is **built and held** — do NOT launch it
until V22's forward paper-trade window (~2 weeks) is evaluated.

## What's different from V22

**Only one thing.** When the `MAX_SAME_DIRECTION_POSITIONS = 3` cap is full for a direction:
- **V22 (FIFO):** rejects the incoming signal outright — first-come keeps the slot. A low-conviction
  Puerta C (60) position can block a high-conviction Puerta A (95) / B (75) signal just by arriving first.
- **V23 (quality-ranked):** if the incoming signal's conviction is **strictly greater** than the
  weakest open same-direction position, it **evicts** (closes at market) the weakest and admits the
  strong one. Otherwise it blocks as before.

Conviction is static per puerta (A=95 > B=75 > C=60), so with strict `>` only A evicts B/C and B
evicts C — never any churn within the same puerta. Eviction logs `ALLOCATOR_DESALOJO|...`.

Implementation: `posicion_mas_debil_misma_direccion()` + `desalojar_trade_vivo()` (top of
`simulador_institucional_v23.py`), wired into the live enforcement block (~line 932).

## CRITICAL: the allocator is LIVE-ONLY — and cannot be backtested on this engine

The backtest in this engine processes symbols **sequentially** (`fetch_history` runs each symbol's
full 3000-candle history to completion before the next), so it does NOT model concurrent multi-symbol
exposure — the `MAX_SAME_DIRECTION_POSITIONS` cap barely binds there (only via stale end-of-window
leftover trades). Therefore the allocator is deliberately applied **only in the live path**. The
backtest path is left identical to V22, so **V23's startup backtest should reproduce the V22 baseline
exactly** (`+$2,059.93` fixed-window) — that's the sanity check that nothing else drifted.

**V23 is validated FORWARD on testnet, not by backtest.** (See el libro "honesty pivot" 2026-06-10.)

## Config / wiring

- Port: **8055** (V21=8053, V22=8054).
- Simulador: `simulador_institucional_v23.py`. Watchdog: `mesa_de_dinero.py` (LOG_FILE `v23_live.log`,
  SIMULADOR_TARGET points at the v23 simulador). Telegram prefix `[V23_MASTER]` / `[SIMULADOR_V23]`.
- Backtest history: `backtest_history_v23.csv` (separate from V22). `log_backtest.py` reads `mesa_v23.out`.
- Strategy file is still `estrategia_v22_Master.py` (unchanged — same signals as V22; only the
  simulador's live allocation logic differs).

## Launch command (ONLY when ready — after V22's forward window)

```
cd bot_alpha_portfolio/v23 && nohup /Users/hackerunet/openclaw-binance-trading/trading_env/bin/python3 -u mesa_de_dinero.py > mesa_v23.out 2>&1 & disown
```
Then verify per the usual checklist: `lsof -p <simulador_pid> | grep TCP` ESTABLISHED, `mesa_v23.out`
contains `SINC_BALANCE` and `WebSocket Multiplexado conectado`, and the startup backtest
`ALERTA_BACKTEST_RESUMEN_FIXED` reproduces +$2,059.93 (proves only the live allocator changed).

## ⚠️ Shared-testnet-account caveat (must resolve before running V23 alongside V22)

V21, V22, and V23 all share the same Binance testnet account via the same `.env`. The V23 allocator
closes positions via `cerrar_orden_binance(symbol, type, qty)` — on a shared account this could close a
position another version opened, and the three bots' fills would contaminate each other. **Before
launching V23 live, either (a) stop V22, or (b) give V23 its own testnet sub-account/API keys.** Do NOT
run V22 (forward-validation subject) and V23 on the same account simultaneously — it would corrupt both
the forward results and the allocator test. This is a deployment decision to surface to the user.
