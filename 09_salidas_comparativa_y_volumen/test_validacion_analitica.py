# -*- coding: utf-8 -*-
"""
Validación analítica de TEST 1 (ADX decline) y TEST 2 (divergencia RSI)
en la copia aislada v26_salida_comparativa/ — ejercita el código REAL de los
archivos, no una re-implementación.

NOTA (2026-07-05, auditoría de la comparativa): este archivo fue copiado
literalmente desde v26_salida_test/ con un `sys.path.insert` hardcodeado a
esa carpeta vieja. Al correrlo desde v26_salida_comparativa/, ese path
absoluto ganaba la resolución de imports por sobre el directorio del propio
script, así que `config`/`backtest`/`walkforward` importados eran en
realidad los de v26_salida_test/ — el suite pasaba, pero no estaba
ejercitando el código de esta copia. Corregido a una ruta relativa al
propio archivo (funciona sin importar desde qué cwd se invoque).
"""
import sys, os, math
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from indicadores import calcular_indicadores

FALLOS = []

def check(nombre, cond, detalle=''):
    tag = 'OK ' if cond else 'FAIL'
    print(f"[{tag}] {nombre} {detalle}")
    if not cond:
        FALLOS.append(nombre)

# ===========================================================================
# PARTE A — TEST 2: columnas Div_Bajista / Div_Alcista
# ===========================================================================
print("=" * 70)
print("PARTE A — Div_Bajista/Div_Alcista (indicadores.py)")
print("=" * 70)

def df_sintetico(closes):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=n, freq='4h'),
        'open': closes, 'high': closes * 1.001, 'low': closes * 0.999,
        'close': closes, 'volume': np.full(n, 1000.0),
    })

# A.1 — oráculo por loop independiente sobre un random walk (300 velas)
rng = np.random.default_rng(7)
closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
df = calcular_indicadores(df_sintetico(closes))

LB = 14
esp_baj, esp_alc = [], []
for i in range(len(df)):
    if i < LB:  # menos de 14 velas PREVIAS completas -> rolling da NaN -> False
        esp_baj.append(False); esp_alc.append(False); continue
    prev_close = df['close'].iloc[i - LB:i]   # exactamente las 14 previas, SIN la actual
    prev_rsi = df['RSI'].iloc[i - LB:i]
    c, r = df['close'].iloc[i], df['RSI'].iloc[i]
    if prev_rsi.isna().any() or math.isnan(r):
        # el rolling max de un tramo con NaN de warmup de RSI: pandas rolling
        # con min_periods=14 da NaN si hay NaN en la ventana -> comparación False
        mb = False; ma = False
    else:
        mb = (c >= prev_close.max()) and (r < prev_rsi.max())
        ma = (c <= prev_close.min()) and (r > prev_rsi.min())
    esp_baj.append(bool(mb)); esp_alc.append(bool(ma))

igual_b = (df['Div_Bajista'].values == np.array(esp_baj)).all()
igual_a = (df['Div_Alcista'].values == np.array(esp_alc)).all()
check("A.1 oráculo-loop == vectorizado (Div_Bajista, 300 velas)", igual_b,
      f"({int(df['Div_Bajista'].sum())} señales)")
check("A.1 oráculo-loop == vectorizado (Div_Alcista, 300 velas)", igual_a,
      f"({int(df['Div_Alcista'].sum())} señales)")

# A.2 — primeras 14 velas: siempre False (min_periods del rolling)
check("A.2 primeras 14 velas todas False",
      not df['Div_Bajista'].iloc[:LB].any() and not df['Div_Alcista'].iloc[:LB].any())

# A.3 — caso a mano: pico fuerte -> retroceso -> nuevo máximo débil = divergencia
#   velas 0-14: sube 100->114 | vela 15: salto a 130 (RSI pico) |
#   velas 16-20: retroceso a 120 | velas 21-30: sube despacio hasta 131.5
closes2 = list(range(100, 115)) + [130] + [128, 126, 124, 122, 120] + \
          [121, 122.5, 124, 125.5, 127, 128.5, 129.5, 130.2, 130.8, 131.5]
df2 = calcular_indicadores(df_sintetico(closes2))
# la vela 28 (close=130.2) es el primer "nuevo máximo" (>130, el pico de la vela 15
# ya salió de la ventana de 14 previas? no: ventana de la vela 28 = velas 14..27,
# max=130 (vela 15). 130.2>=130 ✓). Verificar cada componente por separado:
i = 28
prev_c = df2['close'].iloc[i-LB:i]; prev_r = df2['RSI'].iloc[i-LB:i]
c, r = df2['close'].iloc[i], df2['RSI'].iloc[i]
print(f"    vela {i}: close={c} vs max_prev={prev_c.max()} | RSI={r:.2f} vs maxRSI_prev={prev_r.max():.2f}")
check("A.3 componente nuevo_max (a mano)", c >= prev_c.max())
check("A.3 componente RSI-no-confirma (a mano)", r < prev_r.max())
check("A.3 Div_Bajista=True en el nuevo máximo débil", bool(df2['Div_Bajista'].iloc[i]))

# A.4 — el shift(1) importa: en pleno retroceso (velas 16-20) close NO es nuevo
# máximo (el pico previo 130 está en la ventana) => Div_Bajista debe ser False,
# aunque el RSI sí esté por debajo de su máximo previo (si faltara el shift en
# max_close, "close >= max incl. sí misma" sería SIEMPRE True y esto dispararía).
for j in range(16, 21):
    check(f"A.4 vela {j} (retroceso): Div_Bajista=False (no hay nuevo máximo)",
          not bool(df2['Div_Bajista'].iloc[j]))
# ...y en las velas donde además RSI<maxRSI_prev sí se cumple (17-20, tras el
# warmup-fill de 50.0 del RSI), un shift faltante habría disparado divergencia:
for j in range(17, 21):
    pr = df2['RSI'].iloc[j-LB:j]
    check(f"A.4b vela {j}: RSI<maxRSI_prev (condición que dispararía sin shift)",
          df2['RSI'].iloc[j] < pr.max())

# A.5 — dtype bool puro (sin NaN que pudiera dar bool(NaN)=True en row.get)
check("A.5 dtype bool sin NaN", df['Div_Bajista'].dtype == bool and df['Div_Alcista'].dtype == bool
      and not df['Div_Bajista'].isna().any() and not df['Div_Alcista'].isna().any())

# ===========================================================================
# PARTE B — TEST 1: contador de ADX cayendo desde pico (código real)
# ===========================================================================
print()
print("=" * 70)
print("PARTE B — ADX decline (backtest._salidas_vela y walkforward._salidas_vela_mc)")
print("=" * 70)

config.EXIT_MODE = 'tendencia'
config.ADX_DECLINE_EXIT_TENDENCIA = True
config.RSI_DIVERGENCE_EXIT_TENDENCIA = False
config.EXHAUSTION_EXIT_TENDENCIA = False
config.REPLICA_TENDENCIA = False
config.SCALE_OUT_TENDENCIA = False
config.TRAILING_STOP_TENDENCIA = False
config.REENTRY_POST_STOP = False

from backtest import BacktestV25
import walkforward as wf

class ForenseNulo:
    def registrar_cierre(self, t): pass
    def registrar_vela(self, *a, **k): pass
    def registrar_apertura(self, *a, **k): pass

def trade_nuevo():
    return {'symbol': 'TESTUSDT', 'type': 'LONG', 'status': 'ABIERTA',
            'entry_time': pd.Timestamp('2024-01-01'), 'entry_price': 100.0,
            'tp': 110.0, 'sl': 50.0, 'dist_sl': 5.0, 'qty': 1.0,
            'peak_progress': 0.0, 'peak_fav': 0.0, 'locked_decile': 0,
            'velas_lateral_consec': 0, 'pnl': 0.0,
            'exit_time': None, 'exit_price': None, 'exit_reason': None}

def fila(adx, ts):
    return pd.Series({'open': 100.0, 'high': 100.1, 'low': 99.9, 'close': 100.0,
                      'volume': 1000.0, 'ADX': adx,
                      'Div_Bajista': False, 'Div_Alcista': False}), ts

def correr_secuencia_real(adx_seq):
    """Alimenta la secuencia de ADX al _salidas_vela REAL; devuelve (idx_cierre|None, motivo, t)."""
    bt = BacktestV25.__new__(BacktestV25)   # sin __init__: no toca disco
    bt.balance = 500.0; bt.trades = []; bt.cooldown = {}; bt.forense = ForenseNulo()
    t = trade_nuevo()
    for k, adx in enumerate(adx_seq):
        row, ts = fila(adx, pd.Timestamp('2024-01-01') + pd.Timedelta(hours=4 * (k + 1)))
        bt._salidas_vela(t, row, ts, tendencia_ahora='LONG')
        if t['status'] == 'CERRADA':
            return k, t['exit_reason'], t
    return None, None, t

def correr_secuencia_mc(adx_seq):
    t = trade_nuevo()
    for k, adx in enumerate(adx_seq):
        row, ts = fila(adx, pd.Timestamp('2024-01-01') + pd.Timedelta(hours=4 * (k + 1)))
        res = wf._salidas_vela_mc(t, row, ts, tendencia_ahora='LONG')
        if res is not None:
            return k, res, t
    return None, None, t

# B.1 — pico nunca llega a 40: jamás dispara aunque caiga muchas velas seguidas
seq = [30, 35, 39, 38, 37, 36, 35, 34, 33]
k, motivo, t = correr_secuencia_real(seq)
check("B.1 max<40: nunca cierra (real)", k is None,
      f"(contador quedó en {t.get('adx_velas_cayendo')})")
check("B.1 contador se queda en 0 con max<40", t.get('adx_velas_cayendo') == 0)
k2, res2, _ = correr_secuencia_mc(seq)
check("B.1 paridad null: tampoco cierra", k2 is None)

# B.2 — pico 42, caída con RESET intermedio por vela igual (41,41):
# velas: 42(max) | 41(cae,c=1) | 41(igual->reset c=0) | 40.5(cae,c=1) | 40.0(cae,c=2 -> CIERRA)
seq = [42, 41, 41, 40.5, 40.0]
k, motivo, t = correr_secuencia_real(seq)
check("B.2 cierra exactamente en la vela idx=4 (real)", k == 4, f"(k={k})")
check("B.2 motivo con pico correcto", motivo == 'AGOTAMIENTO ADX: cayendo 2v desde pico 42.0',
      f"({motivo!r})")
check("B.2 precio de cierre = close de la vela", t['exit_price'] == 100.0)
k2, res2, _ = correr_secuencia_mc(seq)
check("B.2 paridad null: cierra en la misma vela", k2 == 4, f"(k={k2})")
check("B.2 paridad null: mismo precio, es_replica=False",
      res2 is not None and res2[0] == 100.0 and res2[2] is False)

# B.2b — sin el reset, habría cerrado en idx=3 (40.5 sería la 2da caída tras 41).
# Confirmar que NO cerró en idx=3 ya está implícito en k==4 (el reset funcionó).

# B.3 — caída de solo 1 vela intercalada: nunca acumula 2 -> no cierra
seq = [45, 44, 46, 45, 47, 46, 48]
k, motivo, t = correr_secuencia_real(seq)
check("B.3 caídas no consecutivas: no cierra", k is None,
      f"(contador final={t.get('adx_velas_cayendo')})")

# B.4 — NaN al inicio: max() con primer arg guardado no se contamina; luego funciona
seq = [float('nan'), float('nan'), 45, 44, 43]
k, motivo, t = correr_secuencia_real(seq)
check("B.4 NaN inicial no rompe ni dispara espurio; cierra en idx=4", k == 4,
      f"(k={k}, motivo={motivo!r})")
check("B.4 pico reportado=45.0", motivo == 'AGOTAMIENTO ADX: cayendo 2v desde pico 45.0',
      f"({motivo!r})")
k2, res2, _ = correr_secuencia_mc(seq)
check("B.4 paridad null con NaN", k2 == 4)

# B.5 — el umbral se evalúa sobre el MÁXIMO histórico del trade, no el ADX actual:
# tras ver 42, ADX puede caer por debajo de 40 y sigue contando
seq = [42, 39, 38]
k, motivo, t = correr_secuencia_real(seq)
check("B.5 sigue contando bajo 40 si el pico fue >=40 (cierra idx=2)", k == 2, f"(k={k})")

# B.6 — SHORT: mismo mecanismo (el exit no depende de la dirección)
def correr_secuencia_real_short(adx_seq):
    bt = BacktestV25.__new__(BacktestV25)
    bt.balance = 500.0; bt.trades = []; bt.cooldown = {}; bt.forense = ForenseNulo()
    t = trade_nuevo(); t['type'] = 'SHORT'; t['sl'] = 200.0; t['tp'] = 90.0
    for k, adx in enumerate(adx_seq):
        row, ts = fila(adx, pd.Timestamp('2024-01-01') + pd.Timedelta(hours=4 * (k + 1)))
        bt._salidas_vela(t, row, ts, tendencia_ahora='SHORT')
        if t['status'] == 'CERRADA':
            return k, t['exit_reason'], t
    return None, None, t
k, motivo, t = correr_secuencia_real_short([42, 41, 40])
check("B.6 SHORT cierra igual (idx=2)", k == 2, f"({motivo!r})")

# B.7 — TEST 2 en el motor real: Div_Bajista=True cierra un LONG, no un SHORT
config.ADX_DECLINE_EXIT_TENDENCIA = False
config.RSI_DIVERGENCE_EXIT_TENDENCIA = True
bt = BacktestV25.__new__(BacktestV25)
bt.balance = 500.0; bt.trades = []; bt.cooldown = {}; bt.forense = ForenseNulo()
t = trade_nuevo()
row = pd.Series({'open': 100.0, 'high': 100.1, 'low': 99.9, 'close': 100.0, 'volume': 1000.0,
                 'ADX': 30.0, 'Div_Bajista': True, 'Div_Alcista': False})
bt._salidas_vela(t, row, pd.Timestamp('2024-01-02'), tendencia_ahora='LONG')
check("B.7 LONG + Div_Bajista=True -> cierra por divergencia",
      t['status'] == 'CERRADA' and t['exit_reason'] == 'AGOTAMIENTO: divergencia de RSI')
t2 = trade_nuevo(); t2['type'] = 'SHORT'; t2['sl'] = 200.0
bt._salidas_vela(t2, row, pd.Timestamp('2024-01-02'), tendencia_ahora='SHORT')
check("B.7 SHORT + Div_Bajista=True (Div_Alcista=False) -> NO cierra", t2['status'] == 'ABIERTA')
# paridad null
t3 = trade_nuevo()
res3 = wf._salidas_vela_mc(t3, row, pd.Timestamp('2024-01-02'), tendencia_ahora='LONG')
check("B.7 paridad null divergencia", res3 is not None and res3[0] == 100.0 and res3[2] is False)

# B.8 — prioridad del STOP intravela sobre los exits nuevos (pesimista):
# vela que toca el stop Y tendría señal de agotamiento -> gana el stop
config.ADX_DECLINE_EXIT_TENDENCIA = True
config.RSI_DIVERGENCE_EXIT_TENDENCIA = False
bt = BacktestV25.__new__(BacktestV25)
bt.balance = 500.0; bt.trades = []; bt.cooldown = {}; bt.forense = ForenseNulo()
t = trade_nuevo(); t['sl'] = 99.95  # el low de la fila (99.9) lo toca
# pre-cargar estado de caída: pico 42, ya 1 vela cayendo
t['adx_max_visto'] = 42.0; t['adx_anterior'] = 41.0; t['adx_velas_cayendo'] = 1
row = pd.Series({'open': 100.0, 'high': 100.1, 'low': 99.9, 'close': 100.0, 'volume': 1000.0,
                 'ADX': 40.0, 'Div_Bajista': False, 'Div_Alcista': False})
bt._salidas_vela(t, row, pd.Timestamp('2024-01-02'), tendencia_ahora='LONG')
check("B.8 stop intravela gana al agotamiento (pesimista)",
      t['status'] == 'CERRADA' and t['exit_reason'] == 'STOP DE PROTECCIÓN'
      and t['exit_price'] == 99.95)
t4 = trade_nuevo(); t4['sl'] = 99.95
t4['adx_max_visto'] = 42.0; t4['adx_anterior'] = 41.0; t4['adx_velas_cayendo'] = 1
res4 = wf._salidas_vela_mc(t4, row, pd.Timestamp('2024-01-02'), tendencia_ahora='LONG')
check("B.8 paridad null: stop primero", res4 is not None and res4[0] == 99.95)

print()
print("=" * 70)
if FALLOS:
    print(f"RESULTADO: {len(FALLOS)} FALLOS -> {FALLOS}")
    sys.exit(1)
print("RESULTADO: TODOS LOS CHECKS PASAN")
