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
        # Default de balance: en testnet 500 (paper); en MAINNET 0.0 a propósito —
        # si la lectura real de balance fallara al arrancar, NO se defaultea a 500
        # (dimensionaría contra plata que no existe). Con 0.0 la guarda de
        # evaluar_entrada bloquea toda apertura hasta leer el balance real.
        _bal_def = 500.0 if config.BINANCE_ENV != 'mainnet' else 0.0
        self.balance = {'usd': _bal_def, 'inicial': _bal_def}
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
            # Rotación del archivo (2026-07-09): cota dura del historial PERSISTIDO
            # para que trades_*.json no crezca sin límite en operación de años. Mantiene
            # TODAS las abiertas + las últimas TRADES_HISTORY_CAP cerradas. El registro
            # completo siempre es consultable en Binance. Inerte hasta pasar el tope (no
            # muta self.trades en memoria — solo lo que se escribe a disco).
            cap = getattr(config, 'TRADES_HISTORY_CAP', 2000)
            if len(serial) > cap:
                abiertas = [d for d in serial if d.get('status') == 'ABIERTA']
                cerradas = [d for d in serial if d.get('status') != 'ABIERTA']
                serial = abiertas + cerradas[-max(cap - len(abiertas), 0):]
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

    def cerrar_todas(self, motivo, precio_actual_fn):
        """Botón de pánico /cerrartodo — cierra TODAS las posiciones abiertas a
        mercado. Devuelve lista de (symbol, type, pnl) de lo cerrado."""
        cerradas = []
        with self.lock:
            for t in list(self.trades):
                if t['status'] != 'ABIERTA':
                    continue
                precio = precio_actual_fn(t['symbol']) or t['entry_price']
                if self.cerrar_trade(t, precio, motivo):
                    cerradas.append((t['symbol'], t['type'], t.get('pnl', 0.0)))
        return cerradas

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
        hubo_cambio_peak = False
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] != self.symbol or t['status'] != 'ABIERTA':
                    continue
                res = estrategia.evaluar_salida(t, precio)
                if res['nuevo_peak'] is not None:
                    t['peak_progress'] = res['nuevo_peak']
                    hubo_cambio_peak = True

                # V34-V26 (2026-07-01): aviso de ROUND-TRIP VIOLENTO — informa,
                # no cierra (caso BNBUSDT: pico 70%->negativo 3 días->pico
                # 111%->negativo de nuevo). Se re-arma solo tras un pico
                # REALMENTE nuevo (mayor al último alertado) — un mismo techo
                # que oscila no re-alerta, pero un segundo ciclo pico-nuevo-
                # ->negativo sí.
                pico = t.get('peak_progress', 0)
                if pico >= config.ALERTA_ROUNDTRIP_MIN_PICO:
                    prog_ahora = estrategia.calcular_progreso(t, precio)
                    avisado_en = t.get('rt_avisado_en_pico')
                    if prog_ahora < 0 and (avisado_en is None or pico > avisado_en):
                        t['rt_avisado_en_pico'] = pico
                        hubo_cambio_peak = True  # forzar persistencia del dedup
                        prob = estrategia.prob_reversion(self.df, t['type'])
                        tend = estrategia.tendencia_actual(_df_indicado(self.df))
                        self.telegram.enviar(
                            self.telegram.mensaje_alerta_roundtrip(
                                t, prob, prog_ahora, tendencia_activa=tend),
                            botones_trade_id=t['id'])
                if res['nuevo_decil'] is not None:
                    t['locked_decile'] = res['nuevo_decil']
                    prob = estrategia.prob_reversion(self.df, t['type'])
                    self.telegram.enviar(
                        self.telegram.mensaje_posicion(t, prob, f"PROGRESO {res['nuevo_decil']}% ASEGURADO"),
                        botones_trade_id=t['id'])
                if res['cerrar']:
                    self.gestor.cerrar_trade(t, precio, res['cerrar'])
                    self._activar_cooldown()
        # BUGFIX (2026-06-23): antes, peak_progress/locked_decile solo se
        # persistían a disco (y por lo tanto al respaldo en GCS) al abrir o
        # cerrar una operación. En una posición de larga duración sin otras
        # aperturas/cierres (el caso normal de V26 — semanas/meses por
        # operación), el respaldo quedaba CONGELADO en el valor de la
        # apertura (típicamente 0%) aunque el avance real en vivo (visible en
        # Telegram, que lee el dict en memoria) siguiera subiendo. Sin riesgo
        # de seguridad (el cierre usa precio en vivo vs SL/flip, nunca este
        # campo) pero si el contenedor se reinicia antes del cierre, el
        # avance histórico se perdía. Ahora se persiste también aquí.
        if hubo_cambio_peak:
            self.gestor.guardar()

    def _activar_cooldown(self):
        self.cooldown_hasta = ahora_utc() + pd.Timedelta(hours=config.COOLDOWN_CANDLES)

    def _salida_flip_vela_cerrada(self):
        """SINAPSIS (EXIT_MODE='tendencia'): al CIERRE de cada vela evalúa, en
        este orden (idéntico al backtest _salidas_vela, single-code-path):
        1) salida-LATERAL (agotamiento): si el régimen lleva
           EXHAUSTION_LATERAL_VELAS velas LATERAL consecutivas → tomar profit sin
           esperar el flip completo (contador por-trade);
        2) flip de alineación completa (estrategia.salida_por_flip).
        Inerte en modo 'escalera'."""
        if getattr(config, 'EXIT_MODE', 'escalera') != 'tendencia':
            return
        tend = estrategia.tendencia_actual(self.df)
        lateral_on = getattr(config, 'EXHAUSTION_EXIT_TENDENCIA', False)
        n_lat = getattr(config, 'EXHAUSTION_LATERAL_VELAS', 2)
        with self.gestor.lock:
            for t in self.gestor.trades:
                if t['symbol'] != self.symbol or t['status'] != 'ABIERTA':
                    continue
                # 1) salida-LATERAL — contador por-trade, igual que el backtest
                if lateral_on:
                    if tend == 'LATERAL':
                        t['velas_lateral_consec'] = t.get('velas_lateral_consec', 0) + 1
                    else:
                        t['velas_lateral_consec'] = 0
                    if t['velas_lateral_consec'] >= n_lat:
                        self.gestor.cerrar_trade(
                            t, self.ultimo_precio,
                            f"AGOTAMIENTO: {t['velas_lateral_consec']} velas LATERAL")
                        self._activar_cooldown()
                        continue
                # 2) flip completo
                if estrategia.salida_por_flip(tend, t['type']):
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
            # BUGFIX (2026-06-22, mismo patrón causó un duplicado real en
            # V28/ADAUSDT — ver v28_copilot/ejecutor.py): re-chequear DENTRO
            # del mismo lock que el registro de la operación, atómico. Antes
            # el chequeo y el registro eran dos bloqueos separados con la
            # evaluación de la señal sin protección entre medio — dos
            # llamadas a evaluar_entrada() casi simultáneas (ej. el WS
            # reentrega la misma vela cerrada en una reconexión) podían pasar
            # ambas el chequeo antes de que la primera registrara su
            # operación, duplicando la orden de mercado.
            if self.gestor.abierta_en(self.symbol):
                return
            balance = self.gestor.balance['usd']
            # Validación de balance + CORTACIRCUITOS en mainnet: no abrir si la cuenta
            # real está por debajo del piso (MAINNET_STOP_EQUITY, o MIN_BALANCE si la
            # lectura falló y quedó en 0). Las posiciones ABIERTAS se siguen gestionando.
            _piso = max(config.MAINNET_MIN_BALANCE, getattr(config, 'MAINNET_STOP_EQUITY', 0))
            if config.BINANCE_ENV == 'mainnet' and balance < _piso:
                log(f"[SEGURIDAD] {self.symbol}: balance ${balance:.2f} < piso "
                    f"${_piso:.0f} (cortacircuitos mainnet) — NO se abre operación")
                return
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
            self.telegram.mensaje_posicion(t, señal['prob_reversion'], 'NUEVA POSICIÓN ABIERTA'),
            botones_trade_id=t['id'])
        log(f"ENTRADA #{t['id']} {self.symbol} {señal['type']} @ {señal['entry_price']} patrón={t['pattern']}")
        self.gestor.guardar()


def _df_indicado(df):
    """Indicadores válidos en la ÚLTIMA fila para LECTURA (display).
    BUGFIX 2026-06-25: la vela EN FORMACIÓN se guarda solo con OHLCV → sus
    indicadores quedan en NaN hasta cerrar, haciendo que tendencia_actual
    devuelva LATERAL espurio en /estado. Recalcular asegura la última fila.
    No afecta trading (el flip se evalúa al cierre con indicadores válidos)."""
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
            f"• Balance ({'MAINNET real 🔴' if config.BINANCE_ENV == 'mainnet' else 'testnet paper 🧪'}): "
            f"${gestor.balance['usd']:,.2f}",
            f"• Símbolos: {', '.join(config.SYMBOLS)}",
        ]
        for sym, eng in engines.items():
            # Calcular al vuelo desde el df (no del atributo cacheado, que solo
            # se setea al cerrar vela y quedaba en N/D para símbolos con posición).
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
            # AVANCE ACTUAL como número principal (el pico inducía a cerrar mal
            # creyendo que se ganaba cuando ya había revertido — caso 2026-06-24).
            eng = engines.get(t['symbol'])
            prog_now = None
            try:
                if eng is not None and eng.ultimo_precio:
                    prog_now = estrategia.calcular_progreso(t, eng.ultimo_precio)
            except Exception:
                pass
            ahora = f"{int(prog_now)}%" if prog_now is not None else 'N/D'
            pico = int(t.get('peak_progress', 0))
            alerta = ' ⚠️' if (prog_now is not None and pico >= 20 and prog_now < 5) else ''
            lineas.append(
                f"   #{t['id']} {t['symbol']} {t['type']} @ ${t['entry_price']:.4f}"
                f" | AHORA {ahora}{alerta} (pico {pico}%)")

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
