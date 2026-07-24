"""
forense.py — Registro forense por operación.

Cada trade genera UN archivo JSON (`<dir>/<trade_id>.json`) con tres bloques:

  activacion  — el momento exacto en que el bot detectó la oportunidad:
                tendencia, patrón disparador, TODOS los patrones presentes,
                indicadores completos, probabilidad de reversión, parámetros
                de la posición (entrada/tp/sl/qty) y las últimas 30 velas
                OHLCV que produjeron la señal.
  seguimiento — una entrada por vela cerrada mientras la operación vive:
                OHLCV + progreso + peak + decil asegurado + prob. reversión.
  cierre      — salida: precio, motivo, PnL, avance máximo, duración.

Con esto se puede evaluar a posteriori si la estrategia funciona, dónde falla
y qué mejorar — sin depender de logs dispersos. Lo usan por igual el bot en
vivo (forense/) y el backtest (forense_backtest/<run>/).
"""
import json
import os
import threading
from datetime import datetime


class RegistroForense:
    def __init__(self, directorio):
        self.dir = directorio
        os.makedirs(self.dir, exist_ok=True)
        self._datos = {}          # trade_id -> dict en memoria
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _ruta(self, trade_id):
        return os.path.join(self.dir, f"{trade_id}.json")

    def _recuperar(self, trade_id):
        """Tras un restart, _datos está vacío pero el archivo del trade abierto
        existe en disco — se recarga para que seguimiento/cierre no se pierdan."""
        ruta = self._ruta(trade_id)
        if not os.path.isfile(ruta):
            return None
        try:
            with open(ruta) as f:
                datos = json.load(f)
            self._datos[trade_id] = datos
            return datos
        except Exception as e:
            print(f"[FORENSE] WARN no se pudo recuperar {trade_id}: {e}", flush=True)
            return None

    def _flush(self, trade_id):
        datos = self._datos.get(trade_id)
        if datos is None:
            return
        try:
            with open(self._ruta(trade_id), 'w') as f:
                json.dump(datos, f, indent=1, default=str)
        except Exception as e:
            print(f"[FORENSE] WARN no se pudo escribir {trade_id}: {e}", flush=True)

    @staticmethod
    def _velas_df(df, n=30):
        cols = ['time', 'open', 'high', 'low', 'close', 'volume']
        sub = df[cols].tail(n)
        return [
            {'time': str(r['time']), 'open': r['open'], 'high': r['high'],
             'low': r['low'], 'close': r['close'], 'volume': r['volume']}
            for _, r in sub.iterrows()
        ]

    @staticmethod
    def _indicadores_df(df):
        r = df.iloc[-1]
        out = {}
        for k in ('close', 'EMA_50', 'EMA_200', 'ATR', 'ADX', 'RSI',
                  'MACD', 'MACD_Signal', 'MACD_Hist', 'volume', 'Volume_MA'):
            try:
                v = r.get(k)
                out[k] = None if v is None else float(v)
            except Exception:
                out[k] = None
        return out

    # ------------------------------------------------------------------
    def registrar_activacion(self, t, df, extras=None):
        """Snapshot completo del momento en que se detectó la oportunidad."""
        with self._lock:
            self._datos[t['id']] = {
                'trade_id': t['id'],
                'symbol': t['symbol'],
                'type': t['type'],
                'estado': 'ABIERTA',
                'activacion': {
                    'timestamp': str(t.get('entry_time') or datetime.utcnow()),
                    'tendencia': t['type'],
                    'patron_disparador': t.get('pattern'),
                    'patrones_detectados': extras.get('patrones_detectados') if extras else None,
                    'prob_reversion': extras.get('prob_reversion') if extras else None,
                    'indicadores': self._indicadores_df(df),
                    'params': {
                        'entry_price': t['entry_price'],
                        'tp': t['tp'], 'sl': t['sl'],
                        'qty': t['qty'],
                        'riesgo_pct': extras.get('riesgo_pct') if extras else None,
                        'balance': extras.get('balance') if extras else None,
                    },
                    'velas_previas': self._velas_df(df, 30),
                },
                'seguimiento': [],
                'cierre': None,
            }
            self._flush(t['id'])

    def registrar_vela(self, t, vela, prob_rev=None):
        """Una entrada de seguimiento por vela cerrada mientras el trade vive.
        `vela` = dict {time, open, high, low, close, volume}."""
        with self._lock:
            datos = self._datos.get(t['id']) or self._recuperar(t['id'])
            if datos is None or datos['estado'] != 'ABIERTA':
                return
            datos['seguimiento'].append({
                'time': str(vela.get('time')),
                'open': vela.get('open'), 'high': vela.get('high'),
                'low': vela.get('low'), 'close': vela.get('close'),
                'volume': vela.get('volume'),
                'progreso': round(t.get('peak_progress', 0.0), 2),
                'decil_asegurado': t.get('locked_decile', 0),
                'prob_reversion': prob_rev,
            })
            self._flush(t['id'])

    def registrar_cierre(self, t):
        with self._lock:
            datos = self._datos.get(t['id']) or self._recuperar(t['id'])
            if datos is None:
                return
            datos['estado'] = 'CERRADA'
            duracion = None
            try:
                duracion = round((t['exit_time'] - t['entry_time']).total_seconds() / 3600, 2)
            except Exception:
                pass
            datos['cierre'] = {
                'timestamp': str(t.get('exit_time')),
                'precio': t.get('exit_price'),
                'motivo': t.get('exit_reason'),
                'pnl': round(t.get('pnl', 0.0), 4),
                'peak_progress': round(t.get('peak_progress', 0.0), 2),
                'decil_asegurado_final': t.get('locked_decile', 0),
                'duracion_horas': duracion,
            }
            self._flush(t['id'])
            # liberar memoria: el archivo queda en disco
            self._datos.pop(t['id'], None)
