"""
backtest.py — Backtest HONESTO de la estrategia V25 (motor heredado de V24-FABLE).

Corre EXACTAMENTE las mismas funciones de decisión que el bot en vivo
(estrategia.evaluar_entrada / evaluar_salida) sobre histórico real de Binance:

  1. RELOJ GLOBAL: los símbolos avanzan juntos por timestamp (salidas primero,
     entradas después) — nada de procesar un símbolo completo y luego otro.
  2. ORDEN INTRAVELA PESIMISTA: en cada vela se evalúa primero el extremo
     ADVERSO (low para LONG / high para SHORT): stop y cierre-por-reversa se
     resuelven ahí. Solo si sobrevive se chequea el objetivo 100% contra el
     extremo favorable, y los ratchets (peak / decil asegurado) se actualizan
     con el CIERRE de la vela (efectivos desde la siguiente). En vivo las
     salidas son tick a tick, así que el backtest queda del lado conservador.
  3. COSTOS COMPLETOS: comisión taker 0.05%/lado + slippage 0.05%/lado +
     funding 0.01%/8h (LONG paga, SHORT recibe, marcas 00/08/16 UTC).
  4. FORENSE COMPLETO: cada trade simulado genera el mismo archivo forense que
     en vivo (activación + seguimiento por vela + cierre) en forense_backtest/,
     más un resumen agregado por símbolo, por PATRÓN disparador y por motivo
     de salida — la base para evaluar si la estrategia funciona o no.
  5. BENCHMARK buy & hold de la misma ventana: si no lo supera, es beta, no edge.

Uso (no necesita API keys — datos públicos):
    python3 backtest.py                      # 1500 velas 1h (~62 días)
    python3 backtest.py --candles 3000       # ~125 días
    python3 backtest.py --end 2026-06-09     # ventana congelada reproducible
"""
import argparse
import json
import os
import uuid
from datetime import datetime

import pandas as pd

import config
import estrategia
from binance_client import BinanceClient
from forense import RegistroForense
from indicadores import calcular_indicadores

BALANCE_INICIAL = 500.0
_EPOCH = pd.Timestamp('1970-01-01')


# ---------------------------------------------------------------------------
# Costos (port del motor honesto V24)
# ---------------------------------------------------------------------------
def _eventos_funding(t_in, t_out):
    """Marcas de funding (00/08/16 UTC) en (t_in, t_out]."""
    try:
        if t_out <= t_in:
            return 0
        horas_in = int((t_in - _EPOCH) // pd.Timedelta(hours=1))
        primera = _EPOCH + pd.Timedelta(hours=(horas_in - horas_in % 8) + 8)
        if primera > t_out:
            return 0
        return int((t_out - primera) // pd.Timedelta(hours=8)) + 1
    except Exception:
        return 0


def pnl_neto_cierre(t, exit_price, exit_time):
    """PnL neto del cierre total: bruto − comisión − slippage − funding."""
    if t['type'] == 'LONG':
        gross = (exit_price - t['entry_price']) * t['qty']
    else:
        gross = (t['entry_price'] - exit_price) * t['qty']
    funding = _eventos_funding(t['entry_time'], exit_time) * config.BT_FUNDING_8H \
        * t['qty'] * t['entry_price']
    gross = gross - funding if t['type'] == 'LONG' else gross + funding
    tasa = config.BT_TAKER_FEE + config.BT_SLIPPAGE
    costos = t['qty'] * (t['entry_price'] + exit_price) * tasa
    return gross - costos


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------
class BacktestV25:
    def __init__(self, candles, end_time_ms=None, forense_dir=None):
        self.candles = candles
        self.end_time_ms = end_time_ms
        run_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        self.forense = RegistroForense(forense_dir or os.path.join(config.FORENSE_BACKTEST_DIR, run_id))
        self.balance = BALANCE_INICIAL
        self.trades = []
        self.cooldown = {s: None for s in config.SYMBOLS}  # ts hasta el que no reentrar
        self.dfs = {}
        self._trend_memo = {}  # (sym, i) -> tendencia (TEST C, EXIT_MODE='tendencia')

    def _tendencia_en(self, sym, i):
        """Tendencia al cierre de la vela i (memoizada — determinista por df)."""
        key = (sym, i)
        if key not in self._trend_memo:
            self._trend_memo[key] = estrategia.tendencia_actual(self.dfs[sym].iloc[:i + 1])
        return self._trend_memo[key]

    # ---------------- datos ----------------
    def cargar_datos(self):
        cliente = BinanceClient()
        for sym in config.SYMBOLS:
            print(f"INFO: descargando {self.candles} velas {config.INTERVAL} de {sym}...")
            df = cliente.klines_paginated(sym, self.candles, end_time_ms=self.end_time_ms)
            self.dfs[sym] = calcular_indicadores(df)

    # ---------------- ciclo de vida ----------------
    def _abierta_en(self, sym):
        return any(t['symbol'] == sym and t['status'] == 'ABIERTA' for t in self.trades)

    def _cerrar(self, t, exit_price, exit_time, motivo):
        t['status'] = 'CERRADA'
        t['exit_time'] = exit_time
        t['exit_price'] = exit_price
        t['exit_reason'] = motivo
        t['pnl'] = pnl_neto_cierre(t, exit_price, exit_time)
        self.balance += t['pnl']
        self.forense.registrar_cierre(t)
        self.cooldown[t['symbol']] = exit_time + pd.Timedelta(hours=config.COOLDOWN_CANDLES)

    def _salidas_vela(self, t, row, ts, tendencia_ahora=None):
        """Orden intravela PESIMISTA para un trade abierto en una vela."""
        adverso = row['low'] if t['type'] == 'LONG' else row['high']
        favorable = row['high'] if t['type'] == 'LONG' else row['low']

        # TEST C: salida de seguimiento de tendencia — stop de protección
        # intravela (pesimista, vía evaluar_salida que en este modo solo cierra
        # por STOP) o flip de alineación al CIERRE. Sin TP/escalera.
        if getattr(config, 'EXIT_MODE', 'escalera') == 'tendencia':
            res = estrategia.evaluar_salida(t, adverso)
            if res['cerrar']:
                self._cerrar(t, t['sl'], ts, res['cerrar'])
                return
            # SINAPSIS: salida-lateral (agotamiento) — tomar profit al CIERRE si el
            # régimen lleva EXHAUSTION_LATERAL_VELAS velas LATERAL consecutivas, ANTES
            # de esperar el flip completo. Contador por-trade = MISMO mecanismo que el
            # motor vivo (_salida_flip_vela_cerrada), single-code-path.
            if tendencia_ahora == 'LATERAL':
                t['velas_lateral_consec'] = t.get('velas_lateral_consec', 0) + 1
            else:
                t['velas_lateral_consec'] = 0
            if getattr(config, 'EXHAUSTION_EXIT_TENDENCIA', False) and \
                    t['velas_lateral_consec'] >= getattr(config, 'EXHAUSTION_LATERAL_VELAS', 2):
                self._cerrar(t, row['close'], ts,
                             f"AGOTAMIENTO: {t['velas_lateral_consec']} velas LATERAL")
                return
            res_close = estrategia.evaluar_salida(t, row['close'])
            if res_close['nuevo_peak'] is not None:
                t['peak_progress'] = res_close['nuevo_peak']
            if estrategia.salida_por_flip(tendencia_ahora, t['type']):
                self._cerrar(t, row['close'], ts, 'FLIP DE TENDENCIA (alineación opuesta)')
            return

        # 1) extremo adverso primero: stop o cierre-por-reversa
        res = estrategia.evaluar_salida(t, adverso)
        if res['cerrar']:
            if 'STOP' in res['cerrar']:
                exit_price = t['sl']          # stop-market al nivel del stop
            else:
                exit_price = adverso          # reversa: al extremo adverso (conservador)
            self._cerrar(t, exit_price, ts, res['cerrar'])
            return

        # 2) objetivo 100% contra el extremo favorable (fill al precio objetivo)
        if estrategia.calcular_progreso(t, favorable) >= 100:
            self._cerrar(t, t['tp'], ts, 'OBJETIVO 100% ALCANZADO')
            return

        # 3) ratchets con el CIERRE de la vela (efectivos desde la siguiente)
        res_close = estrategia.evaluar_salida(t, row['close'])
        if res_close['nuevo_peak'] is not None:
            t['peak_progress'] = res_close['nuevo_peak']
        if res_close['nuevo_decil'] is not None:
            t['locked_decile'] = res_close['nuevo_decil']
        if res_close['cerrar']:
            self._cerrar(t, row['close'], ts, res_close['cerrar'])

    def _entrada_vela(self, sym, sub_df, ts, rs_basket=None):
        if self._abierta_en(sym):
            return
        cd = self.cooldown.get(sym)
        if cd is not None and ts < cd:
            return
        señal = estrategia.evaluar_entrada(sub_df, rs_basket=rs_basket, rs_symbol=sym)
        if not señal:
            return
        qty = (self.balance * config.RISK_PER_TRADE) / señal['dist_sl']
        t = {
            'id': str(uuid.uuid4())[:8],
            'symbol': sym,
            'type': señal['type'],
            'status': 'ABIERTA',
            'entry_time': ts,
            'entry_price': señal['entry_price'],
            'tp': señal['tp'], 'sl': señal['sl'],
            'qty': qty,
            'pattern': señal['pattern'],
            'peak_progress': 0.0,
            'locked_decile': 0,
            'exit_time': None, 'exit_price': None, 'exit_reason': None,
            'pnl': 0.0,
        }
        self.trades.append(t)
        self.forense.registrar_activacion(t, sub_df, {
            'patrones_detectados': señal['patrones_detectados'],
            'prob_reversion': señal['prob_reversion'],
            'riesgo_pct': config.RISK_PER_TRADE,
            'balance': self.balance,
        })

    def correr(self):
        """Reloj global: todos los símbolos avanzan juntos por timestamp."""
        index_maps, all_times = {}, set()
        for sym, df in self.dfs.items():
            index_maps[sym] = {ts: i for i, ts in enumerate(df['time'])}
            if len(df) > config.WARMUP_CANDLES:
                all_times.update(df['time'].iloc[config.WARMUP_CANDLES:])

        symbols = [s for s in config.SYMBOLS if s in self.dfs]
        timeline = sorted(all_times)
        print(f"INFO: simulando {len(timeline)} timestamps x {len(symbols)} símbolos...")

        for n, ts in enumerate(timeline):
            # 1) SALIDAS de todos los símbolos en este timestamp
            for sym in symbols:
                i = index_maps[sym].get(ts)
                if i is None or i < config.WARMUP_CANDLES:
                    continue
                row = self.dfs[sym].iloc[i]
                tendencia_ahora = None
                if getattr(config, 'EXIT_MODE', 'escalera') == 'tendencia' \
                        and self._abierta_en(sym):
                    tendencia_ahora = self._tendencia_en(sym, i)
                for t in self.trades:
                    if t['symbol'] == sym and t['status'] == 'ABIERTA':
                        self._salidas_vela(t, row, ts, tendencia_ahora=tendencia_ahora)
                        if t['status'] == 'ABIERTA':
                            # seguimiento forense por vela (igual que en vivo)
                            sub = self.dfs[sym].iloc[:i + 1]
                            prob = estrategia.prob_reversion(sub, t['type'])
                            self.forense.registrar_vela(t, {
                                'time': ts, 'open': row['open'], 'high': row['high'],
                                'low': row['low'], 'close': row['close'],
                                'volume': row['volume']}, prob)

            # 2) ENTRADAS
            # TEST B: ROC del basket a RS_LOOKBACK_DAYS por timestamp (solo
            # plomería de datos — la regla de decisión vive en estrategia.py)
            rs_basket = None
            if getattr(config, 'FILTRO_RS', False):
                rs_lb = int(pd.Timedelta(days=config.RS_LOOKBACK_DAYS)
                            / pd.Timedelta(config.INTERVAL))
                rs_basket = {}
                for sym in symbols:
                    i = index_maps[sym].get(ts)
                    if i is not None and i >= rs_lb:
                        c0 = float(self.dfs[sym]['close'].iloc[i - rs_lb])
                        if c0 > 0:
                            rs_basket[sym] = float(self.dfs[sym]['close'].iloc[i]) / c0 - 1
            for sym in symbols:
                i = index_maps[sym].get(ts)
                if i is None or i < config.WARMUP_CANDLES:
                    continue
                self._entrada_vela(sym, self.dfs[sym].iloc[:i + 1], ts,
                                   rs_basket=rs_basket)

            if n % 200 == 0 and n:
                print(f"  ... {n}/{len(timeline)} ({len(self.trades)} trades)")

        # cierre administrativo de posiciones aún abiertas al final de la ventana
        for t in self.trades:
            if t['status'] == 'ABIERTA':
                df = self.dfs[t['symbol']]
                self._cerrar(t, float(df['close'].iloc[-1]), df['time'].iloc[-1],
                             'FIN DE VENTANA (administrativo)')

    # ---------------- reporte ----------------
    def resumen(self):
        cerrados = [t for t in self.trades if t['status'] == 'CERRADA']
        pnls = [t['pnl'] for t in cerrados]
        ganan = [p for p in pnls if p > 0]
        pierden = [p for p in pnls if p <= 0]
        bruto_g, bruto_p = sum(ganan), abs(sum(pierden))

        def grupo(clave_fn):
            grupos = {}
            for t in cerrados:
                grupos.setdefault(clave_fn(t), []).append(t)
            return {
                k: {'trades': len(v),
                    'win_rate': round(sum(1 for x in v if x['pnl'] > 0) / len(v) * 100, 1),
                    'pnl': round(sum(x['pnl'] for x in v), 2)}
                for k, v in sorted(grupos.items())
            }

        # benchmark buy & hold de la misma ventana
        rets = []
        starts, ends = [], []
        for sym, df in self.dfs.items():
            if len(df) > config.WARMUP_CANDLES:
                p0, p1 = df['close'].iloc[config.WARMUP_CANDLES], df['close'].iloc[-1]
                if p0:
                    rets.append((p1 / p0 - 1) * 100)
                starts.append(df['time'].iloc[config.WARMUP_CANDLES])
                ends.append(df['time'].iloc[-1])

        net = sum(pnls)
        return {
            'balance_inicial': BALANCE_INICIAL,
            'balance_final': round(self.balance, 2),
            'net_pnl_usd': round(net, 2),
            'net_pnl_pct': round(net / BALANCE_INICIAL * 100, 2),
            'trades': len(cerrados),
            'win_rate': round(len(ganan) / len(pnls) * 100, 2) if pnls else 0.0,
            'profit_factor': round(bruto_g / bruto_p, 3) if bruto_p > 0 else None,
            'benchmark_buy_hold_pct': round(sum(rets) / len(rets), 2) if rets else None,
            'window_start': str(min(starts)) if starts else None,
            'window_end': str(max(ends)) if ends else None,
            'por_simbolo': grupo(lambda t: t['symbol']),
            'por_patron': grupo(lambda t: t['pattern']),
            'por_motivo_salida': grupo(lambda t: t['exit_reason']),
        }


def main():
    ap = argparse.ArgumentParser(description='Backtest honesto de STABLE_V25')
    ap.add_argument('--candles', type=int, default=1500, help='velas 1h por símbolo (def. 1500)')
    ap.add_argument('--end', type=str, default=None,
                    help='fin de ventana ISO (ej. 2026-06-09) para regresión reproducible')
    args = ap.parse_args()

    end_ms = None
    if args.end:
        end_ms = int(pd.Timestamp(args.end).timestamp() * 1000)

    bt = BacktestV25(args.candles, end_time_ms=end_ms)
    bt.cargar_datos()
    bt.correr()
    r = bt.resumen()

    print("\n" + "=" * 64)
    print("RESUMEN BACKTEST V25 (motor honesto: pesimista + costos completos)")
    print("=" * 64)
    print(f"Ventana: {r['window_start']} → {r['window_end']}")
    print(f"Balance: ${r['balance_inicial']:.2f} → ${r['balance_final']:.2f} "
          f"({r['net_pnl_pct']:+.2f}%, ${r['net_pnl_usd']:+.2f})")
    print(f"Benchmark buy&hold misma ventana: {r['benchmark_buy_hold_pct']:+.2f}% "
          f"← si no lo superamos, es beta, no edge")
    print(f"Trades: {r['trades']} | WR: {r['win_rate']}% | PF: {r['profit_factor']}")
    for titulo, clave in (('POR SÍMBOLO', 'por_simbolo'), ('POR PATRÓN DISPARADOR', 'por_patron'),
                          ('POR MOTIVO DE SALIDA', 'por_motivo_salida')):
        print(f"\n--- {titulo} ---")
        for k, v in r[clave].items():
            print(f"  {k}: {v['trades']} trades | WR {v['win_rate']}% | PnL ${v['pnl']:+,.2f}")

    ruta = os.path.join(bt.forense.dir, 'resumen.json')
    with open(ruta, 'w') as f:
        json.dump(r, f, indent=1, ensure_ascii=False)
    print(f"\nForense por trade + resumen guardados en: {bt.forense.dir}")
    print(f"BACKTEST_RESUMEN|{json.dumps(r, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
