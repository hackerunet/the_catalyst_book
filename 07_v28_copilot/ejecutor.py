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
import re
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


class Horario:
    """V28: ventana horaria de CREACIÓN de operaciones (hora LOCAL del server),
    configurable por Telegram con /horario. Sin horario → opera siempre.
    Las posiciones ABIERTAS nunca se tocan por horario: siguen hasta su meta
    (SL o 2R) y sus avisos no se apagan."""

    def __init__(self):
        self.ruta = os.path.join(config.DIR_BASE, 'horario_v28.json')
        self.inicio = None  # minutos desde medianoche, hora local
        self.fin = None
        try:
            if os.path.isfile(self.ruta):
                with open(self.ruta) as f:
                    d = json.load(f)
                self.inicio, self.fin = d.get('inicio'), d.get('fin')
        except Exception:
            pass

    def _guardar(self):
        try:
            with open(self.ruta, 'w') as f:
                json.dump({'inicio': self.inicio, 'fin': self.fin}, f)
        except Exception as e:
            log(f"WARN guardando horario: {e}")

    @staticmethod
    def _a_minutos(h, m, ampm):
        h = int(h) % 12
        if ampm.upper() == 'PM':
            h += 12
        return h * 60 + int(m or 0)

    @staticmethod
    def _fmt(minutos):
        h, m = divmod(int(minutos), 60)
        ampm = 'AM' if h < 12 else 'PM'
        return f"{h % 12 or 12:02d}:{m:02d} {ampm}"

    def configurar(self, texto):
        """'/horario 08 AM a 10 PM' | '/horario off' | '/horario' (ver)."""
        resto = texto.strip()[len('/horario'):].strip()
        if not resto:
            return self.descripcion()
        if resto.lower() in ('off', 'borrar', 'siempre', 'no'):
            self.inicio = self.fin = None
            self._guardar()
            return '🕐 Horario eliminado — vuelvo a operar SIEMPRE (24/7).'
        m = re.match(r'(?i)^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s+a\s+'
                     r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$', resto)
        if not m:
            return ('Formato: /horario 08 AM a 10 PM\n'
                    'También: /horario off (operar siempre) | /horario (ver actual)')
        self.inicio = self._a_minutos(m.group(1), m.group(2), m.group(3))
        self.fin = self._a_minutos(m.group(4), m.group(5), m.group(6))
        self._guardar()
        return '✅ Guardado.\n' + self.descripcion()

    def descripcion(self):
        if self.inicio is None or self.fin is None:
            return ('🕐 Sin horario configurado — opero SIEMPRE (24/7).\n'
                    'Para limitar: /horario 08 AM a 10 PM')
        return (f"🕐 Horario de operación: {self._fmt(self.inicio)} a {self._fmt(self.fin)} "
                f"(hora local del servidor).\nSolo CREO operaciones en esa ventana; "
                f"las abiertas siguen hasta su meta (SL o 2R) con todos sus avisos.")

    def permite_ahora(self):
        if self.inicio is None or self.fin is None:
            return True
        ahora = datetime.now()  # hora LOCAL del servidor, a propósito
        mins = ahora.hour * 60 + ahora.minute
        if self.inicio == self.fin:
            return True
        if self.inicio < self.fin:
            return self.inicio <= mins < self.fin
        return mins >= self.inicio or mins < self.fin  # ventana nocturna (cruza 00:00)


HORARIO = Horario()


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
        prog_cierre = estrategia.calcular_progreso(t, exit_price)
        pico = int(t.get('peak_progress', 0))
        revirtio = pico >= 20 and prog_cierre < pico - 15
        self.telegram.enviar(
            f"{icono} POSICIÓN CERRADA — #{t['id']} {t['symbol']} {t['type']}\n"
            f"• Motivo: {motivo}\n"
            f"• Salida: ${exit_price:.4f} (entrada ${t['entry_price']:.4f})\n"
            f"• Avance AL CIERRE: {int(prog_cierre)}%"
            + (f"  ⚠️ había llegado a {pico}% y revirtió\n" if revirtio
               else f" (máx que tuvo: {pico}%)\n")
            + f"• PnL neto: ${t['pnl']:+,.2f}")
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
        """Seguimiento forense por vela cerrada + ALERTA DE REVERSO (V28):
        si prob_reversion cruza el umbral con trade abierto, aviso urgente
        (histéresis −10 para no spamear)."""
        umbral = getattr(config, 'ALERTA_REVERSO_PROB', None)
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] == self.symbol and t['status'] == 'ABIERTA':
                    prob = estrategia.prob_reversion(self.df, t['type'])
                    self.forense.registrar_vela(t, vela, prob)
                    if not umbral:
                        continue
                    if prob >= umbral and not t.get('alerta_reverso_activa'):
                        t['alerta_reverso_activa'] = True
                        prog = estrategia.calcular_progreso(t, self.ultimo_precio)
                        tend = estrategia.tendencia_actual(self.df)
                        self.telegram.enviar(
                            "🚨 " + self.telegram.mensaje_posicion(
                                t, prob, 'REVERSO ALTO',
                                prog_actual=prog, resumido=True, tendencia_activa=tend),
                            botones_trade_id=t['id'])
                    elif prob < umbral - 10 and t.get('alerta_reverso_activa'):
                        t['alerta_reverso_activa'] = False

    def _vol_ratio_actual(self):
        """Volumen de la última vela vs su media (None si no computable)."""
        try:
            vma = self.df['Volume_MA'].iloc[-1]
            vol = self.df['volume'].iloc[-1]
            if vma and not pd.isna(vma) and vma > 0:
                return float(vol / vma)
        except Exception:
            pass
        return None

    # ---------------- salidas (tick a tick) ----------------
    def gestionar_salidas(self, precio):
        hubo_cambio_peak = False
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] != self.symbol or t['status'] != 'ABIERTA':
                    continue
                # SALVAVIDAS ratchet+reverso: el detector de reverso solo se
                # calcula (es caro: usa el df completo) cuando el avance ya
                # retrocedió a tocar el decil asegurado — ahí sí se pasa la prob
                # a evaluar_salida para que decida el cierre. Lazy: en el tick
                # normal (sin retroceso) no se computa. Mismo code path de
                # decisión que el backtest (evaluar_salida con prob).
                prob_rev = None
                if getattr(config, 'AUTO_CIERRE_REVERSA', False):
                    locked = t.get('locked_decile', 0)
                    if locked >= config.LOCK_STEP_PCT \
                            and estrategia.calcular_progreso(t, precio) <= locked:
                        prob_rev = estrategia.prob_reversion(self.df, t['type'])
                res = estrategia.evaluar_salida(t, precio, prob_reversion_actual=prob_rev)
                if res['nuevo_peak'] is not None:
                    t['peak_progress'] = res['nuevo_peak']
                    hubo_cambio_peak = True
                if res['nuevo_decil'] is not None:
                    t['locked_decile'] = res['nuevo_decil']
                    t['retroceso_avisado'] = None  # pico nuevo → re-armar avisos de retroceso
                    # (2026-07-01: se probó throttlear este aviso a cada 20% en
                    # vez de 10% para bajar ruido — el usuario lo revirtió:
                    # reaccionar a tiempo importa más que menos mensajes. Aviso
                    # cada LOCK_STEP_PCT (10%) como siempre; el ruido se reduce
                    # separando /estado de /history, no bajando la frecuencia.)
                    dfi = _df_indicado(self.df)
                    prob = estrategia.prob_reversion(dfi, t['type'])
                    prog = estrategia.calcular_progreso(t, precio)
                    tend = estrategia.tendencia_actual(dfi)
                    self.telegram.enviar(
                        self.telegram.mensaje_posicion(
                            t, prob, f"Progreso {res['nuevo_decil']}%",
                            prog_actual=prog, resumido=True, tendencia_activa=tend),
                        botones_trade_id=t['id'])
                # AVISO DE RETROCESO (2026-06-24, spec del usuario — INFO pura, NO
                # cierra: automatizar el cierre destruye el edge, V33). Si el
                # avance cae a un decil POR DEBAJO del pico ya alcanzado, avisar
                # una vez por cada nivel inferior (re-armado al hacer pico nuevo).
                # Da visibilidad al "devolver el avance" para que el trader decida
                # — el hueco que faltaba (caso LINK 2026-06-24, 64%→pérdida).
                locked = t.get('locked_decile', 0)
                if locked >= getattr(config, 'RETROCESO_MIN_PICO', 30):
                    prog_r = estrategia.calcular_progreso(t, precio)
                    cur_dec = int(prog_r // config.LOCK_STEP_PCT) * config.LOCK_STEP_PCT
                    ya = t.get('retroceso_avisado')
                    if cur_dec < locked and (ya is None or cur_dec < ya):
                        t['retroceso_avisado'] = cur_dec
                        hubo_cambio_peak = True  # forzar persistencia del dedup
                        dfi = _df_indicado(self.df)
                        prob = estrategia.prob_reversion(dfi, t['type'])
                        tend = estrategia.tendencia_actual(dfi)
                        self.telegram.enviar(
                            self.telegram.mensaje_posicion(
                                t, prob, "⚠️ Retroceso",
                                prog_actual=prog_r, resumido=True, tendencia_activa=tend),
                            botones_trade_id=t['id'])
                if res['cerrar']:
                    self.gestor.cerrar_trade(t, precio, res['cerrar'])
                    self._activar_cooldown()
        # BUGFIX (2026-06-23, mismo hallazgo en V26): peak_progress/locked_decile
        # solo se persistían a disco al abrir o cerrar una operación — en una
        # posición de larga duración sin otra apertura/cierre, el respaldo en
        # GCS quedaba congelado en el valor de la apertura. Sin riesgo de
        # seguridad (el cierre usa precio en vivo vs SL/TP, nunca este campo)
        # pero se perdía el avance histórico si el contenedor se reiniciaba.
        if hubo_cambio_peak:
            self.gestor.guardar()

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
        if not HORARIO.permite_ahora():
            return  # fuera del horario configurado: no se CREAN operaciones
        if self.gestor.abierta_en(self.symbol):
            return  # chequeo rápido sin lock — optimización, no la garantía
        if self.cooldown_hasta and ahora_utc() < self.cooldown_hasta:
            return

        self.ultima_tendencia = estrategia.tendencia_actual(self.df)
        señal = estrategia.evaluar_entrada(self.df)
        if not señal:
            diag = diagnostico_entrada(self.df)
            log(f"[DIAG] {self.symbol}: {diag}")
            return

        with self.gestor.lock:
            # BUGFIX (2026-06-22, caso ADAUSDT duplicado en vivo): re-chequear
            # DENTRO del mismo lock que el registro de la operación. Antes el
            # chequeo y el registro eran dos bloqueos separados con la
            # evaluación de la señal sin protección entre medio — si
            # evaluar_entrada() se invocaba dos veces casi al mismo tiempo
            # (ej. el WS reentrega la misma vela cerrada en una reconexión),
            # ambas pasaban el chequeo antes de que la primera registrara su
            # operación, y las dos disparaban una orden de mercado idéntica.
            # Resultado real: 2x2026 ADA vendidos, solo 1 operación trackeada,
            # la otra mitad quedó huérfana en Binance sin gestión de ningún
            # bot. Ahora el chequeo+registro es atómico: si dos llamadas se
            # solapan, la primera en tomar el lock gana; la segunda ve la
            # posición ya abierta y no duplica nada.
            if self.gestor.abierta_en(self.symbol):
                return
            balance = self.gestor.balance['usd']
            qty = (balance * config.RISK_PER_TRADE) / señal['dist_sl']
            t = {
                'id': str(uuid.uuid4())[:8],
                'symbol': self.symbol,
                'type': señal['type'],
                'status': 'ABIERTA',
                'entry_time': ahora_utc(),
                'entry_price': señal['entry_price'],
                'tp': señal['tp'], 'sl': señal['sl'],
                'qty': qty,
                'pattern': señal['pattern'],
                'peak_progress': 0.0,
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
            self.telegram.mensaje_posicion(
                t, señal['prob_reversion'], 'NUEVA OPERACIÓN MONTADA',
                vol_ratio=self._vol_ratio_actual(), prog_actual=0.0),
            botones_trade_id=t['id'])
        log(f"ENTRADA #{t['id']} {self.symbol} {señal['type']} @ {señal['entry_price']} patrón={t['pattern']}")
        self.gestor.guardar()


def _df_indicado(df):
    """Indicadores válidos en la ÚLTIMA fila para LECTURA (display/avisos).
    BUGFIX 2026-06-25: la vela EN FORMACIÓN se guarda solo con OHLCV → sus
    columnas de indicadores quedan en NaN hasta que la vela cierra. Leer esa
    fila hacía caer prob_reversion al fallback (50%) y tendencia_actual a
    LATERAL (espurios) en /estado y avisos. Recalcular asegura la última fila.
    No afecta trading (entradas leen al cierre; salidas usan precio)."""
    try:
        if df is not None and not df.empty:
            return calcular_indicadores(df)
    except Exception:
        pass
    return df


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
            f"• {HORARIO.descripcion().splitlines()[0]}"
            + ('' if HORARIO.permite_ahora() else ' — ⏸ AHORA FUERA DE HORARIO (no creo operaciones)'),
        ]
        for sym, eng in engines.items():
            # Calcular al vuelo desde el df (con datos del bootstrap), no del
            # atributo cacheado: ese solo se setea al CERRAR una vela, así que
            # justo tras un restart mostraba 'N/D' hasta el primer cierre.
            tend, v = 'N/D', None
            try:
                dfi = _df_indicado(eng.df)
                if dfi is not None and not dfi.empty:
                    tend = estrategia.tendencia_actual(dfi)
                    v = dfi['time'].iloc[-1]
            except Exception:
                pass
            lineas.append(f"   {sym}: tendencia {tend} | última vela {v.strftime('%H:%M') if v is not None else 'N/D'}")

        abiertas = gestor.abiertas()
        lineas.append(f"\n📂 Posiciones abiertas: {len(abiertas)}")
        for t in abiertas:
            # AVANCE ACTUAL (no el pico) como número principal — el pico viejo
            # mostrado como 'avance' inducía a cerrar creyendo que se ganaba
            # cuando la posición ya había revertido (caso LINK 2026-06-24).
            eng = engines.get(t['symbol'])
            rev = '—'
            prog_now = None
            try:
                if eng is not None and eng.ultimo_precio:
                    prog_now = estrategia.calcular_progreso(t, eng.ultimo_precio)
                dfi = _df_indicado(eng.df) if eng is not None else None
                if dfi is not None and not dfi.empty:
                    rev = f"{estrategia.prob_reversion(dfi, t['type']):.0f}%"
            except Exception:
                pass
            ahora = f"{int(prog_now)}%" if prog_now is not None else 'N/D'
            pico = int(t.get('peak_progress', 0))
            alerta = ' ⚠️' if (prog_now is not None and pico >= 20 and prog_now < 5) else ''
            lineas.append(
                f"   #{t['id']} {t['symbol']} {t['type']} @ ${t['entry_price']:.4f}"
                f" | AHORA {ahora}{alerta} (pico {pico}%, aseg {t.get('locked_decile', 0)}%)"
                f" | reverso {rev}")

        lineas.append("\nℹ️ /history — operaciones cerradas de hoy (ya no en curso)")
    return "\n".join(lineas)


def generar_history(gestor):
    """'/history' — operaciones del día YA CERRADAS (no en curso). Separado de
    /estado (2026-07-01) para bajar ruido sin bajar la frecuencia de avisos:
    /estado muestra solo lo EN CURSO; el historial del día vive aquí."""
    with gestor.lock:
        hoy = ahora_utc().date()
        cerrados_hoy = [t for t in gestor.trades if t['status'] == 'CERRADA'
                        and t.get('exit_time') and t['exit_time'].date() == hoy]
        pnl_hoy = sum(t.get('pnl', 0.0) for t in cerrados_hoy)
        icono = '✅' if pnl_hoy >= 0 else '❌'
        lineas = [f"{icono} HISTORIAL DE HOY: {len(cerrados_hoy)} operaciones cerradas "
                  f"| PnL ${pnl_hoy:+,.2f}"]
        if not cerrados_hoy:
            lineas.append("   (ninguna operación cerrada hoy todavía)")
        for t in cerrados_hoy:
            e = t['entry_time'].strftime('%H:%M') if t.get('entry_time') else '?'
            s = t['exit_time'].strftime('%H:%M')
            r = '✅' if t.get('pnl', 0) > 0 else '❌'
            lineas.append(f"   {r} {e}→{s} {t['symbol']} {t['type']} "
                          f"${t.get('pnl', 0):+,.2f} ({t.get('exit_reason', '?')})")
    return "\n".join(lineas)
