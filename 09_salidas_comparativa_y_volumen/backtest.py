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
from indicadores import calcular_indicadores, atr_diario

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
    # P1 (2026-07-04): motivo de cierre reservado para el mecanismo "cerrar y
    # replicar" — string único para que el hook de apertura de la réplica en
    # correr() lo reconozca sin ambigüedad.
    _MOTIVO_REPLICA = 'REPLICA: ganancia asegurada, reabre pierna nueva'

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
        self.rearm = {s: None for s in config.SYMBOLS}  # V27-A: dirección re-armada post-stop

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
        # V37-C: si hubo scale-out parcial, su PnL ya está en el balance —
        # aquí solo se realiza el resto; t['pnl'] reporta el total del trade.
        pnl_resto = pnl_neto_cierre(t, exit_price, exit_time)
        so = t.get('scale_out')
        t['pnl'] = pnl_resto + (so['pnl'] if so else 0.0)
        self.balance += pnl_resto
        self.forense.registrar_cierre(t)
        self.cooldown[t['symbol']] = exit_time + pd.Timedelta(hours=config.COOLDOWN_CANDLES)
        # V27-A: solo un cierre por STOP re-arma; cualquier otro motivo limpia
        if getattr(config, 'REENTRY_POST_STOP', False):
            self.rearm[t['symbol']] = t['type'] if 'STOP' in motivo else None

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

            # P1/P2 (2026-07-04): contador de velas LATERAL consecutivas —
            # mismo `tendencia_ahora` que ya usa el flip (regimen al CIERRE de
            # la vela, sin lookahead). Compartido entre las dos hipótesis: la
            # pregunta de fondo ("¿cuántas velas seguidas sin tendencia clara?")
            # es la misma; lo que difiere es la reacción (cerrar vs. cerrar+
            # replicar). Se testean con un solo flag activo a la vez.
            if tendencia_ahora == 'LATERAL':
                t['velas_lateral_consec'] = t.get('velas_lateral_consec', 0) + 1
            else:
                t['velas_lateral_consec'] = 0

            # P2: salida por agotamiento — cerrar SIN esperar el flip completo
            # si el régimen lleva EXHAUSTION_LATERAL_VELAS consecutivas LATERAL.
            if getattr(config, 'EXHAUSTION_EXIT_TENDENCIA', False) and \
                    t['velas_lateral_consec'] >= getattr(config, 'EXHAUSTION_LATERAL_VELAS', 2):
                self._cerrar(t, row['close'], ts,
                             f"AGOTAMIENTO: {t['velas_lateral_consec']} velas LATERAL")
                return

            # P1: cerrar y replicar — al alcanzar REPLICA_ARM_PROGRESS de avance
            # (intravela, mismo patrón pesimista que el scale-out) O al
            # confirmarse REPLICA_LATERAL_VELAS de régimen LATERAL. La réplica
            # se abre en correr(), después de este método (necesita el sub_df
            # completo hasta `i` para el sizing fresco, que _salidas_vela no
            # recibe).
            if getattr(config, 'REPLICA_TENDENCIA', False):
                nivel = estrategia.precio_replica(t)
                alcanzado_progreso = favorable >= nivel if t['type'] == 'LONG' else favorable <= nivel
                alcanzado_lateral = t['velas_lateral_consec'] >= getattr(config, 'REPLICA_LATERAL_VELAS', 2)
                if alcanzado_progreso or alcanzado_lateral:
                    precio_cierre = nivel if alcanzado_progreso else row['close']
                    self._cerrar(t, precio_cierre, ts, self._MOTIVO_REPLICA)
                    return

            # TEST 1 (2026-07-04, copia aislada v26_salida_test): ADX cayendo
            # desde un nivel ALTO — dinámica de decaimiento, no el nivel actual
            # (eso es P2/EXHAUSTION_EXIT_TENDENCIA). Requiere haber visto
            # ADX>=ADX_DECLINE_THRESHOLD desde la entrada, y LUEGO que ADX caiga
            # ADX_DECLINE_VELAS velas consecutivas (vs. la vela anterior).
            if getattr(config, 'ADX_DECLINE_EXIT_TENDENCIA', False):
                adx_actual = row['ADX']
                t['adx_max_visto'] = max(t.get('adx_max_visto', 0.0), adx_actual)
                adx_anterior = t.get('adx_anterior')
                if t['adx_max_visto'] >= getattr(config, 'ADX_DECLINE_THRESHOLD', 40.0) \
                        and adx_anterior is not None and adx_actual < adx_anterior:
                    t['adx_velas_cayendo'] = t.get('adx_velas_cayendo', 0) + 1
                else:
                    t['adx_velas_cayendo'] = 0
                t['adx_anterior'] = adx_actual
                if t['adx_velas_cayendo'] >= getattr(config, 'ADX_DECLINE_VELAS', 2):
                    self._cerrar(t, row['close'], ts,
                                 f"AGOTAMIENTO ADX: cayendo {t['adx_velas_cayendo']}v "
                                 f"desde pico {t['adx_max_visto']:.1f}")
                    return

            # TEST 2 (2026-07-04, copia aislada v26_salida_test): divergencia de
            # RSI — columnas vectoriales causales Div_Bajista/Div_Alcista de
            # indicadores.py (nuevo máximo/mínimo de precio de N velas que el
            # RSI no confirma).
            if getattr(config, 'RSI_DIVERGENCE_EXIT_TENDENCIA', False):
                col = 'Div_Bajista' if t['type'] == 'LONG' else 'Div_Alcista'
                if bool(row.get(col, False)):
                    self._cerrar(t, row['close'], ts, 'AGOTAMIENTO: divergencia de RSI')
                    return

            # V37-C: scale-out parcial intravela — DESPUÉS del stop (pesimista:
            # si la vela tocó ambos, gana el stop) y con fill al precio del
            # hito (misma convención que el objetivo 100% de la escalera).
            # El stop del resto NO se toca (diferencia clave con V31).
            if getattr(config, 'SCALE_OUT_TENDENCIA', False) \
                    and not t.get('scale_out'):
                nivel = estrategia.precio_scale_out(t)
                alcanzado = favorable >= nivel if t['type'] == 'LONG' \
                    else favorable <= nivel
                if alcanzado:
                    qty_parcial = t['qty'] * config.SCALE_OUT_FRACTION
                    parcial = pnl_neto_cierre({**t, 'qty': qty_parcial}, nivel, ts)
                    self.balance += parcial
                    t['qty'] -= qty_parcial
                    t['scale_out'] = {'ts': ts, 'pnl': parcial,
                                      'qty': qty_parcial, 'precio': nivel}
            res_close = estrategia.evaluar_salida(t, row['close'])
            if res_close['nuevo_peak'] is not None:
                t['peak_progress'] = res_close['nuevo_peak']
            # V31: ratchet del trailing stop al CIERRE (mismo patrón que el
            # decil de la escalera — nunca intravela, evita look-ahead).
            if res_close['nuevo_peak_fav'] is not None:
                t['peak_fav'] = res_close['nuevo_peak_fav']
            if res_close['nuevo_sl'] is not None:
                t['sl'] = res_close['nuevo_sl']

            # V69 (2026-07-11): trailing por INDICADOR — ratchet del SL hacia el
            # nivel del indicador al CIERRE (efectivo desde la vela siguiente,
            # igual que V31). SL = max(SL, nivel) LONG / min SHORT; nunca afloja.
            # Un solo flag activo a la vez. NADA vivo se toca.
            nivel_trail = None
            if getattr(config, 'TRAIL_VWAP_TENDENCIA', False):
                # VWAP anclado desde la entrada: acumulado precio-típico×volumen.
                tp_typ = (row['high'] + row['low'] + row['close']) / 3.0
                t['vwap_num'] = t.get('vwap_num', 0.0) + tp_typ * row['volume']
                t['vwap_den'] = t.get('vwap_den', 0.0) + row['volume']
                if t['vwap_den'] > 0:
                    nivel_trail = t['vwap_num'] / t['vwap_den']
            elif getattr(config, 'TRAIL_EMA_TENDENCIA', False):
                nivel_trail = row.get(f"EMA_{getattr(config, 'TRAIL_EMA_SPAN', 20)}")
            elif getattr(config, 'TRAIL_SWING_HTF_TENDENCIA', False):
                nivel_trail = row.get('Prev_Daily_Low') if t['type'] == 'LONG' \
                    else row.get('Prev_Daily_High')
            if nivel_trail is not None and nivel_trail == nivel_trail:  # no NaN
                if t['type'] == 'LONG':
                    t['sl'] = max(t['sl'], float(nivel_trail))
                else:
                    t['sl'] = min(t['sl'], float(nivel_trail))
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
        res_close = estrategia.evaluar_salida(t, row['close'], ts=ts)
        if res_close['nuevo_peak'] is not None:
            t['peak_progress'] = res_close['nuevo_peak']
        if res_close['nuevo_decil'] is not None:
            t['locked_decile'] = res_close['nuevo_decil']
        if res_close['cerrar']:
            self._cerrar(t, row['close'], ts, res_close['cerrar'])

    def _abrir_replica(self, sym, direccion, precio, ts, sub_df):
        """
        P1 (2026-07-04): abre una réplica en la MISMA dirección justo después
        de cerrar por avance/lateral alto (_MOTIVO_REPLICA). Sizing FRESCO —
        MISMA fórmula ATR-based que usa una entrada nueva (evaluar_entrada) —
        es una continuación mecánica de la pierna recién cerrada, no una señal
        de entrada distinta, así que no pasa por evaluar_entrada() ni exige
        patrón/cooldown: es la contraparte exacta de lo que se acaba de cerrar.
        """
        atr_d = atr_diario(sub_df)
        dist_tp = atr_d * config.TP_DAILY_ATR_MULT if atr_d else precio * 0.03
        dist_tp = min(max(dist_tp, precio * config.TP_MIN_PCT), precio * config.TP_MAX_PCT)
        dist_sl = dist_tp * config.SL_FRACTION_OF_TP
        if direccion == 'LONG':
            tp, sl = precio + dist_tp, precio - dist_sl
        else:
            tp, sl = precio - dist_tp, precio + dist_sl
        qty = (self.balance * config.RISK_PER_TRADE) / dist_sl
        t = {
            'id': str(uuid.uuid4())[:8],
            'symbol': sym,
            'type': direccion,
            'status': 'ABIERTA',
            'entry_time': ts,
            'entry_price': precio,
            'tp': tp, 'sl': sl, 'dist_sl': dist_sl,
            'qty': qty,
            'pattern': 'RÉPLICA (P1)',
            'peak_progress': 0.0,
            'peak_fav': 0.0,
            'locked_decile': 0,
            'velas_lateral_consec': 0,
            'exit_time': None, 'exit_price': None, 'exit_reason': None,
            'pnl': 0.0,
            'es_replica': True,
        }
        self.trades.append(t)
        self.forense.registrar_activacion(t, sub_df, {
            'patrones_detectados': [], 'prob_reversion': None,
            'riesgo_pct': config.RISK_PER_TRADE, 'balance': self.balance,
        })

    def _entrada_vela(self, sym, sub_df, ts, rs_basket=None, reentrada_armada=False):
        if self._abierta_en(sym):
            return
        cd = self.cooldown.get(sym)
        if cd is not None and ts < cd:
            return
        señal = estrategia.evaluar_entrada(sub_df, rs_basket=rs_basket, rs_symbol=sym,
                                           reentrada_armada=reentrada_armada)
        if not señal:
            return
        self.rearm[sym] = None  # una entrada (flip o re-entrada) consume el re-arme
        qty = (self.balance * config.RISK_PER_TRADE) / señal['dist_sl']
        t = {
            'id': str(uuid.uuid4())[:8],
            'symbol': sym,
            'type': señal['type'],
            'status': 'ABIERTA',
            'entry_time': ts,
            'entry_price': señal['entry_price'],
            'tp': señal['tp'], 'sl': señal['sl'], 'dist_sl': señal['dist_sl'],
            'qty': qty,
            'pattern': señal['pattern'],
            'peak_progress': 0.0,
            'peak_fav': 0.0,
            'locked_decile': 0,
            'velas_lateral_consec': 0,
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
                        direccion_previa = t['type']
                        self._salidas_vela(t, row, ts, tendencia_ahora=tendencia_ahora)
                        if t['status'] == 'ABIERTA':
                            # seguimiento forense por vela (igual que en vivo)
                            sub = self.dfs[sym].iloc[:i + 1]
                            prob = estrategia.prob_reversion(sub, t['type'])
                            self.forense.registrar_vela(t, {
                                'time': ts, 'open': row['open'], 'high': row['high'],
                                'low': row['low'], 'close': row['close'],
                                'volume': row['volume']}, prob)
                        elif t['exit_reason'] == self._MOTIVO_REPLICA:
                            # P1: la pierna se cerró realizando ganancia — abrir
                            # INMEDIATAMENTE la réplica en la misma dirección,
                            # sizing fresco. Ocurre en el mismo timestamp, antes
                            # de la fase de ENTRADAS de este mismo ciclo, así
                            # que _abierta_en(sym) ya la ve como ocupada.
                            self._abrir_replica(sym, direccion_previa, t['exit_price'], ts,
                                               self.dfs[sym].iloc[:i + 1])

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
                # V27-A: estado de re-arme — la pierna muere si la alineación
                # cambió; si persiste, la entrada no exige flip (el cooldown
                # lo chequea _entrada_vela como siempre)
                reentrada = False
                if getattr(config, 'REENTRY_POST_STOP', False) and self.rearm.get(sym):
                    if self._tendencia_en(sym, i) != self.rearm[sym]:
                        self.rearm[sym] = None
                    else:
                        reentrada = True
                self._entrada_vela(sym, self.dfs[sym].iloc[:i + 1], ts,
                                   rs_basket=rs_basket, reentrada_armada=reentrada)

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
