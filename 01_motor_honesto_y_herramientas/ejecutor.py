"""
ejecutor.py — Ejecutor de la estrategia en vivo.

Orquesta el ciclo de vida de las posiciones aplicando las decisiones PURAS de
estrategia.py. No sabe firmar peticiones (binance_client), no formatea
mensajes de chat (telegram_bot), no decide entradas/salidas (estrategia), no
escribe forense (forense) — solo coordina.

- GestorTrades: estado compartido de posiciones + persistencia + cierre.
- SymbolEngine: un motor INDEPENDIENTE por símbolo (spec req. 1) — datos,
  tendencia, cooldown y posición propios; salidas evaluadas tick a tick.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import pandas as pd

import config
import estrategia
from estrategia import diagnostico_entrada
from indicadores import calcular_indicadores


def ahora_utc():
    return datetime.now(timezone.utc)


def log(msg):
    print(f"[{ahora_utc().strftime('%H:%M:%S')}] {msg}", flush=True)


class GestorTrades:
    """Estado de posiciones + balance + persistencia + cierre unificado."""

    def __init__(self, cliente, telegram, forense):
        self.cliente = cliente
        self.telegram = telegram
        self.forense = forense
        self.lock = threading.RLock()
        self.trades = []
        self.balance = {'usd': 500.0, 'inicial': 500.0}
        self.cargar()

    # ---------------- persistencia ----------------
    def guardar(self):
        try:
            with self.lock:
                serial = []
                for t in self.trades:
                    d = dict(t)
                    for k in ('entry_time', 'exit_time'):
                        if isinstance(d.get(k), datetime):
                            d[k] = d[k].isoformat()
                    d.pop('patrones_detectados', None)
                    serial.append(d)
            with open(config.TRADES_FILE, 'w') as f:
                json.dump(serial, f, indent=1)
        except Exception as e:
            log(f"WARN persistencia: {e}")

    def cargar(self):
        try:
            if os.path.isfile(config.TRADES_FILE):
                with open(config.TRADES_FILE) as f:
                    data = json.load(f)
                for d in data:
                    for k in ('entry_time', 'exit_time'):
                        if d.get(k):
                            d[k] = datetime.fromisoformat(d[k])
                self.trades = data
                log(f"INFO: {len(self.trades)} trades cargados")
        except Exception as e:
            log(f"WARN cargando historial: {e}")

    # ---------------- consultas ----------------
    def buscar(self, tid):
        for t in self.trades:
            if t['id'] == tid:
                return t
        return None

    def abierta_en(self, symbol):
        return any(t['symbol'] == symbol and t['status'] == 'ABIERTA' for t in self.trades)

    def abiertas(self):
        return [t for t in self.trades if t['status'] == 'ABIERTA']

    # ---------------- cierre ----------------
    def cerrar_trade(self, t, exit_price, motivo):
        """Cierra: estado + PnL + orden reduceOnly + Telegram + forense."""
        if t['status'] != 'ABIERTA':
            return False
        t['status'] = 'CERRADA'
        t['exit_time'] = ahora_utc()
        t['exit_price'] = exit_price
        t['exit_reason'] = motivo
        if t['type'] == 'LONG':
            bruto = (exit_price - t['entry_price']) * t['qty']
        else:
            bruto = (t['entry_price'] - exit_price) * t['qty']
        fees = t['qty'] * (t['entry_price'] + exit_price) * config.TAKER_FEE
        t['pnl'] = bruto - fees

        side = 'SELL' if t['type'] == 'LONG' else 'BUY'
        threading.Thread(target=self.cliente.orden_market,
                         args=(t['symbol'], side, t['qty']),
                         kwargs={'reduce_only': True}, daemon=True).start()

        icono = '✅' if t['pnl'] > 0 else '❌'
        self.telegram.enviar(
            f"{icono} POSICIÓN CERRADA — #{t['id']} {t['symbol']} {t['type']}\n"
            f"• Motivo: {motivo}\n"
            f"• Salida: ${exit_price:.4f} (entrada ${t['entry_price']:.4f})\n"
            f"• Avance máximo alcanzado: {int(t.get('peak_progress', 0))}%\n"
            f"• PnL neto: ${t['pnl']:+,.2f}")
        log(f"CIERRE #{t['id']} {t['symbol']} {t['type']} {motivo} pnl={t['pnl']:+.2f}")
        self.forense.registrar_cierre(t)
        self.guardar()
        return True

    def cerrar_por_id(self, tid, motivo, precio_actual_fn):
        """Botón de Telegram — funciona en cualquier momento (spec req. 7)."""
        with self.lock:
            t = self.buscar(tid)
            if not t or t['status'] != 'ABIERTA':
                return False
            precio = precio_actual_fn(t['symbol']) or t['entry_price']
            return self.cerrar_trade(t, precio, motivo)

    def marcar_continuar(self, tid):
        with self.lock:
            t = self.buscar(tid)
            if t and t['status'] == 'ABIERTA':
                t['user_decision'] = 'CONTINUAR'
                return t
        return None


class SymbolEngine:
    """Motor independiente por símbolo: datos propios, posición propia,
    sin tope cruzado con otros símbolos (spec req. 1)."""

    def __init__(self, symbol, gestor, cliente, telegram, forense):
        self.symbol = symbol
        self.gestor = gestor
        self.cliente = cliente
        self.telegram = telegram
        self.forense = forense
        self.df = pd.DataFrame()
        self.ultimo_precio = None
        self.ultima_tendencia = None
        self.ultima_vela = None
        self.cooldown_hasta = None

    # ---------------- datos ----------------
    def bootstrap(self):
        df = self.cliente.klines(self.symbol)
        self.df = calcular_indicadores(df)
        self.ultimo_precio = float(self.df['close'].iloc[-1])
        log(f"{self.symbol}: bootstrap {len(self.df)} velas {config.INTERVAL}")

    def actualizar_tick(self, k):
        """Cada mensaje del WS: vela en formación + salidas a nivel de tick."""
        precio = float(k['c'])
        self.ultimo_precio = precio
        candle_time = pd.to_datetime(k['t'], unit='ms')
        fila = {'time': candle_time, 'open': float(k['o']), 'high': float(k['h']),
                'low': float(k['l']), 'close': precio, 'volume': float(k['v'])}

        if not self.df.empty and self.df['time'].iloc[-1] == candle_time:
            for col, val in fila.items():
                self.df.at[self.df.index[-1], col] = val
        else:
            self.df = pd.concat([self.df, pd.DataFrame([fila])], ignore_index=True)
            if len(self.df) > config.MAX_CANDLES:
                self.df = self.df.iloc[-config.MAX_CANDLES:].reset_index(drop=True)

        self.gestionar_salidas(precio)

        if k.get('x'):  # vela cerrada
            self.df = calcular_indicadores(self.df)
            self.ultima_vela = candle_time
            self._registrar_forense_vela(fila)
            self._salida_flip_vela_cerrada()
            self.evaluar_entrada()

    def _registrar_forense_vela(self, vela):
        """Seguimiento forense: una entrada por vela cerrada con trade vivo."""
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] == self.symbol and t['status'] == 'ABIERTA':
                    prob = estrategia.prob_reversion(self.df, t['type'])
                    self.forense.registrar_vela(t, vela, prob)

    # ---------------- salidas (tick a tick) ----------------
    def gestionar_salidas(self, precio):
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] != self.symbol or t['status'] != 'ABIERTA':
                    continue
                res = estrategia.evaluar_salida(t, precio, ts=ahora_utc())
                if res['nuevo_peak'] is not None:
                    t['peak_progress'] = res['nuevo_peak']
                if res['nuevo_peak_fav'] is not None:
                    t['peak_fav'] = res['nuevo_peak_fav']
                if res['nuevo_sl'] is not None:
                    t['sl'] = res['nuevo_sl']  # V31: ratchet del trailing stop
                if res['nuevo_decil'] is not None:
                    t['locked_decile'] = res['nuevo_decil']
                    prob = estrategia.prob_reversion(self.df, t['type'])
                    self.telegram.enviar(
                        self.telegram.mensaje_posicion(t, prob, f"PROGRESO {res['nuevo_decil']}% ASEGURADO"),
                        botones_trade_id=t['id'])
                if res['cerrar']:
                    self.gestor.cerrar_trade(t, precio, res['cerrar'])
                    self._activar_cooldown()

    def _activar_cooldown(self):
        self.cooldown_hasta = ahora_utc() + pd.Timedelta(hours=config.COOLDOWN_CANDLES)

    def _salida_flip_vela_cerrada(self):
        """V26 (EXIT_MODE='tendencia'): el flip de alineación completa se
        evalúa al CIERRE de cada vela — misma decisión que el backtest
        (estrategia.salida_por_flip). Inerte en modo 'escalera'."""
        if getattr(config, 'EXIT_MODE', 'escalera') != 'tendencia':
            return
        tend = estrategia.tendencia_actual(self.df)
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] == self.symbol and t['status'] == 'ABIERTA' \
                        and estrategia.salida_por_flip(tend, t['type']):
                    self.gestor.cerrar_trade(t, self.ultimo_precio,
                                             'FLIP DE TENDENCIA (alineación opuesta)')
                    self._activar_cooldown()

    def _ejecutar_orden_entrada(self, side, qty, precio_señal):
        """FASE 2: ejecución de la orden de entrada (corre en su propio hilo).
        'market' (default, V25) — market directa, como siempre.
        'maker' (V26) — limit post-only al precio de cierre de la señal (el
        supuesto de costos del backtest); si el exchange la rechaza (cruzaría
        el book) o no llena en ENTRY_MAKER_TIMEOUT_MIN, fallback a MARKET por
        el resto: el backtest asume que TODA señal se llena — perder el trade
        divergiría más del backtest que pagar taker ocasionalmente."""
        if getattr(config, 'ENTRY_EXECUTION', 'market') != 'maker':
            self.cliente.orden_market(self.symbol, side, qty)
            return
        res = self.cliente.orden_limit_postonly(self.symbol, side, qty, precio_señal)
        oid = res.get('orderId') if res else None
        if oid is None:
            log(f"{self.symbol}: post-only rechazada → fallback MARKET")
            self.cliente.orden_market(self.symbol, side, qty)
            return
        limite = ahora_utc() + pd.Timedelta(minutes=getattr(config, 'ENTRY_MAKER_TIMEOUT_MIN', 10))
        while ahora_utc() < limite:
            time.sleep(15)
            st = self.cliente.estado_orden(self.symbol, oid) or {}
            if st.get('status') == 'FILLED':
                log(f"{self.symbol}: entrada MAKER llena (orden {oid})")
                return
            if st.get('status') in ('CANCELED', 'EXPIRED', 'REJECTED'):
                break
        self.cliente.cancelar_orden(self.symbol, oid)
        st = self.cliente.estado_orden(self.symbol, oid) or {}
        try:
            resto = qty - float(st.get('executedQty') or 0)
        except Exception:
            resto = qty
        if resto > 0:
            log(f"{self.symbol}: maker no llenó en el plazo → MARKET por el resto ({resto:.6f})")
            self.cliente.orden_market(self.symbol, side, resto)

    # ---------------- entradas (al cierre de vela) ----------------
    def evaluar_entrada(self):
        with self.gestor.lock:
            if self.gestor.abierta_en(self.symbol):
                return
        if self.cooldown_hasta and ahora_utc() < self.cooldown_hasta:
            return

        self.ultima_tendencia = estrategia.tendencia_actual(self.df)
        señal = estrategia.evaluar_entrada(self.df)
        if not señal:
            diag = diagnostico_entrada(self.df)
            log(f"[DIAG] {self.symbol}: {diag}")
            return

        with self.gestor.lock:
            balance = self.gestor.balance['usd']
            qty = (balance * config.RISK_PER_TRADE) / señal['dist_sl']
            t = {
                'id': str(uuid.uuid4())[:8],
                'symbol': self.symbol,
                'type': señal['type'],
                'status': 'ABIERTA',
                'entry_time': ahora_utc(),
                'entry_price': señal['entry_price'],
                'tp': señal['tp'], 'sl': señal['sl'], 'dist_sl': señal['dist_sl'],
                'qty': qty,
                'pattern': señal['pattern'],
                'peak_progress': 0.0,
                'peak_fav': 0.0,
                'locked_decile': 0,
                'user_decision': None,
                'exit_time': None, 'exit_price': None, 'exit_reason': None,
                'pnl': 0.0,
            }
            self.gestor.trades.append(t)

        side = 'BUY' if señal['type'] == 'LONG' else 'SELL'
        threading.Thread(target=self._ejecutar_orden_entrada,
                         args=(side, qty, señal['entry_price']), daemon=True).start()

        self.forense.registrar_activacion(t, self.df, {
            'patrones_detectados': señal['patrones_detectados'],
            'prob_reversion': señal['prob_reversion'],
            'riesgo_pct': config.RISK_PER_TRADE,
            'balance': balance,
        })
        self.telegram.enviar(
            self.telegram.mensaje_posicion(t, señal['prob_reversion'], 'NUEVA POSICIÓN ABIERTA'),
            botones_trade_id=t['id'])
        log(f"ENTRADA #{t['id']} {self.symbol} {señal['type']} @ {señal['entry_price']} patrón={t['pattern']}")
        self.gestor.guardar()


def generar_estado(gestor, engines, estado_ws, start_time):
    """'/estado' — estado del proceso + resumen de HOY con horas y PnL."""
    with gestor.lock:
        uptime = ahora_utc() - start_time
        horas = int(uptime.total_seconds() // 3600)
        mins = int(uptime.total_seconds() % 3600 // 60)
        lineas = [
            f"⚙️ ESTADO {getattr(config, 'BOT_NOMBRE', 'STABLE_V25_PROTOTYPE')}",
            f"• Uptime: {horas}h {mins}m | WS: {'🟢 conectado' if estado_ws['ok'] else '🔴 desconectado'}",
            f"• Balance (testnet): ${gestor.balance['usd']:,.2f}",
            f"• Símbolos: {', '.join(config.SYMBOLS)}",
        ]
        for sym, eng in engines.items():
            tend = eng.ultima_tendencia or 'N/D'
            v = eng.ultima_vela
            lineas.append(f"   {sym}: tendencia {tend} | última vela {v.strftime('%H:%M') if v is not None else 'N/D'}")

        abiertas = gestor.abiertas()
        lineas.append(f"\n📂 Posiciones abiertas: {len(abiertas)}")
        for t in abiertas:
            lineas.append(
                f"   #{t['id']} {t['symbol']} {t['type']} @ ${t['entry_price']:.4f}"
                f" | avance {int(t.get('peak_progress', 0))}% (asegurado {t.get('locked_decile', 0)}%)")

        hoy = ahora_utc().date()
        cerrados_hoy = [t for t in gestor.trades if t['status'] == 'CERRADA'
                        and t.get('exit_time') and t['exit_time'].date() == hoy]
        pnl_hoy = sum(t.get('pnl', 0.0) for t in cerrados_hoy)
        icono = '✅' if pnl_hoy >= 0 else '❌'
        lineas.append(f"\n{icono} HOY: {len(cerrados_hoy)} operaciones | PnL ${pnl_hoy:+,.2f}")
        for t in cerrados_hoy:
            e = t['entry_time'].strftime('%H:%M') if t.get('entry_time') else '?'
            s = t['exit_time'].strftime('%H:%M')
            r = '✅' if t.get('pnl', 0) > 0 else '❌'
            lineas.append(f"   {r} {e}→{s} {t['symbol']} {t['type']} "
                          f"${t.get('pnl', 0):+,.2f} ({t.get('exit_reason', '?')})")
    return "\n".join(lineas)
