#!/usr/bin/env python3
"""
monitor_salud.py — Vigilante de salud de la operación (2026-07-09, go-live mainnet).

Proceso aparte dentro del contenedor (junto a V26/V36/state_sync/claude_bridge).
SOLO LEE — nunca toca los bots, ni su estado, ni Binance con órdenes. Diseñado para
ser lo MENOS intrusivo posible: si este proceso muere, los bots siguen igual.

Qué hace:
  • Chequeo RÁPIDO cada 15 min: ¿los procesos v26/v36 están vivos? ¿alguno zombie?
    ¿el disco pasó el umbral? → ALERTA INMEDIATA a Telegram (con dedup, sin spam).
  • Chequeo DIARIO al final del día (REPORT_HOUR_UTC): ¿hubo pérdida masiva hoy?
    ¿el MDD-90d rompió el gate de copy-trade (25%)? → alerta si algo compromete el objetivo.
  • Resumen SEMANAL (domingo): equity, posiciones, PnL de la semana, MDD-90d vs gate,
    ritmo vs objetivo 30-45% anual, salud de infra → enviado a Hackerunetbot.

Canal: OPENCLAW_TELEGRAM_TOKEN (bot @Hackerunetbot / Hackerunet_claude), fallback al
bot de V26 si el dedicado fallara. Solo al chat autorizado.

Lanzamiento (lo hace entrypoint.sh):  python3 -u /app/monitor_salud.py &
"""
import os
import sys
import time
import json
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

# --- rutas dentro del contenedor ---
APP = os.getenv('APP_DIR', '/app')
V26_DIR = f'{APP}/bot_alpha_portfolio/v26_tendencia'
V36_DIR = f'{APP}/bot_alpha_portfolio/v36_15m'

# Reusar la config de V26 para las llaves (ya seleccionadas por BINANCE_ENV) y la
# URL de cuenta. config.py no tiene efectos secundarios (solo lee .env). Así el
# monitor usa EXACTAMENTE las mismas credenciales/endpoint que el bot, sin duplicar.
sys.path.insert(0, V26_DIR)
try:
    import config as CFG
except Exception as e:  # pragma: no cover
    print(f"[MONITOR] FATAL: no pude importar config de V26: {e}", flush=True)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(os.path.join(APP, '.env'))

TG_TOKEN = os.getenv('OPENCLAW_TELEGRAM_TOKEN', '')
TG_FALLBACK = os.getenv('TELEGRAM_TOKEN_V26', '')
TG_CHAT = (os.getenv('OPENCLAW_TELEGRAM_ALLOWED_USERS', '') or '1214526208').split(',')[0].strip() or '1214526208'

STATE_FILE = f'{APP}/monitor_state.json'

# --- umbrales ---
GATE_MDD_90D = 0.25       # gate copy-trade de Binance (MDD-90d rolling <= 25%)
WARN_MDD_90D = 0.20       # aviso preventivo
MASSIVE_LOSS_PCT = 0.05   # caída >=5% del equity en un día -> alerta inmediata
DISK_WARN_PCT = 85.0
OBJ_ANUAL_MIN = 0.30      # objetivo copy-trade 30-45% anual
OBJ_ANUAL_MAX = 0.45
CHECK_EVERY = 900         # 15 min: chequeo rápido de infra
REPORT_HOUR_UTC = 23      # "final del día" (hora del contenedor = UTC)

BOTS_PROC = ('v26_tendencia.py', 'v36_15m.py')


def LOG(m):
    print(f"[MONITOR] {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z {m}", flush=True)


# ----------------------------- Telegram -----------------------------
def tg_send(texto):
    for tok, pref in ((TG_TOKEN, ''), (TG_FALLBACK, '[vía bot V26 — canal dedicado caído]\n')):
        if not tok:
            continue
        try:
            r = requests.post(f'https://api.telegram.org/bot{tok}/sendMessage',
                              json={'chat_id': TG_CHAT, 'text': pref + texto}, timeout=15)
            if r.json().get('ok'):
                return True
        except Exception as e:
            LOG(f'tg err {e}')
    LOG('tg: no se pudo enviar (ni dedicado ni fallback)')
    return False


# ----------------------------- Binance (solo lectura, firmado) -----------------------------
def _firmar(params):
    qs = urllib.parse.urlencode(params)
    sig = hmac.new(CFG.BINANCE_SECRET_KEY.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return qs + '&signature=' + sig


def api_cuenta():
    """GET /fapi/v2/account firmado — equity (wallet + no realizado)."""
    try:
        p = {'timestamp': int(time.time() * 1000), 'recvWindow': 5000}
        url = f'{CFG.TESTNET_BASE}/fapi/v2/account?' + _firmar(p)
        r = requests.get(url, headers={'X-MBX-APIKEY': CFG.BINANCE_API_KEY}, timeout=10)
        d = r.json()
        if isinstance(d, dict) and 'totalMarginBalance' in d:
            return {'equity': float(d['totalMarginBalance']),
                    'wallet': float(d['totalWalletBalance']),
                    'unrealized': float(d.get('totalUnrealizedProfit', 0.0))}
        LOG(f'api_cuenta respuesta inesperada: {str(d)[:200]}')
    except Exception as e:
        LOG(f'api_cuenta err {e}')
    return None


def api_posiciones():
    try:
        p = {'timestamp': int(time.time() * 1000), 'recvWindow': 5000}
        url = f'{CFG.TESTNET_BASE}/fapi/v2/positionRisk?' + _firmar(p)
        r = requests.get(url, headers={'X-MBX-APIKEY': CFG.BINANCE_API_KEY}, timeout=10)
        d = r.json()
        if isinstance(d, list):
            return [x for x in d if abs(float(x.get('positionAmt', 0) or 0)) > 0]
    except Exception as e:
        LOG(f'api_posiciones err {e}')
    return []


# ----------------------------- estado local (trades) -----------------------------
def _cargar(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def cerradas_combinadas():
    """(exit_time, pnl) de TODAS las operaciones cerradas de V26+V36, ordenadas."""
    out = []
    for path in (f'{V26_DIR}/trades_v26.json', f'{V36_DIR}/trades_v36.json'):
        for t in _cargar(path):
            if t.get('status') == 'ABIERTA':
                continue
            et, pnl = t.get('exit_time'), t.get('pnl')
            if not et or pnl is None:
                continue
            try:
                dt = datetime.fromisoformat(et)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                out.append((dt, float(pnl)))
            except Exception:
                pass
    out.sort(key=lambda x: x[0])
    return out


def mdd_90d(cerradas, equity_actual):
    """MDD-90d rolling sobre la curva de equity de operaciones CERRADAS (el gate)."""
    if len(cerradas) < 3:
        return None
    total = sum(p for _, p in cerradas)
    start = max(equity_actual - total, 1.0)  # capital ~inicial (aprox)
    eq, run = [], start
    for dt, p in cerradas:
        run += p
        eq.append((dt, run))
    peor = 0.0
    for i, (ti, ei) in enumerate(eq):
        pico = start
        for tj, ej in eq[:i + 1]:
            if tj >= ti - timedelta(days=90):
                pico = max(pico, ej)
        if pico > 0:
            peor = max(peor, (pico - ei) / pico)
    return peor


def pnl_ventana(cerradas, dias):
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    return sum(p for dt, p in cerradas if dt >= corte)


def pnl_hoy(cerradas):
    hoy = datetime.now(timezone.utc).date()
    return sum(p for dt, p in cerradas if dt.date() == hoy)


# ----------------------------- infra (procesos / disco) -----------------------------
def disco_pct():
    try:
        s = os.statvfs('/')
        return (s.f_blocks - s.f_bfree) / s.f_blocks * 100.0
    except Exception:
        return None


def procesos_bots():
    """{nombre: (vivo, zombie)} leyendo /proc (sin depender de `ps`)."""
    estado = {n: [False, False] for n in BOTS_PROC}
    try:
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmd = f.read().replace(b'\x00', b' ').decode(errors='ignore')
                for n in BOTS_PROC:
                    if n in cmd:
                        estado[n][0] = True
                        with open(f'/proc/{pid}/stat') as f:
                            st = f.read().rsplit(') ', 1)[-1].split(' ')[0]
                        if st == 'Z':
                            estado[n][1] = True
            except Exception:
                continue
    except Exception as e:
        LOG(f'procesos err {e}')
    return estado


# ----------------------------- persistencia del monitor -----------------------------
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(s):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(s, f)
    except Exception as e:
        LOG(f'save_state err {e}')


# ----------------------------- chequeos -----------------------------
def chequeo_rapido():
    """Infra: procesos + zombies + disco. Devuelve lista de alertas (strings)."""
    al = []
    for n, (vivo, zomb) in procesos_bots().items():
        if not vivo:
            al.append(f'❌ PROCESO CAÍDO: {n} no está corriendo')
        elif zomb:
            al.append(f'🧟 PROCESO ZOMBIE: {n}')
    d = disco_pct()
    if d is not None and d >= DISK_WARN_PCT:
        al.append(f'💾 DISCO ALTO: {d:.0f}% usado (umbral {DISK_WARN_PCT:.0f}%)')
    return al


def chequeo_diario(cuenta, cerradas):
    """Compromiso del objetivo: pérdida masiva del día o MDD-90d sobre el gate."""
    al = []
    if cuenta:
        eq = cuenta['equity']
        hoy = pnl_hoy(cerradas)
        if eq > 0 and hoy < -MASSIVE_LOSS_PCT * eq:
            al.append(f'🔴 PÉRDIDA MASIVA HOY: ${hoy:+.2f} ({hoy/eq*100:+.1f}% del equity ${eq:.2f})')
        if cuenta['unrealized'] < -MASSIVE_LOSS_PCT * eq:
            al.append(f'🔴 NO REALIZADO FUERTE: ${cuenta["unrealized"]:+.2f} '
                      f'({cuenta["unrealized"]/eq*100:+.1f}% del equity) en posiciones abiertas')
        mdd = mdd_90d(cerradas, eq)
        if mdd is not None and mdd > GATE_MDD_90D:
            al.append(f'⚠️ MDD-90d {mdd*100:.1f}% ROMPIÓ el gate de copy-trade ({GATE_MDD_90D*100:.0f}%)')
    return al


def texto_resumen(cuenta, cerradas, posiciones, st):
    L = [f"📊 RESUMEN SEMANAL — {datetime.now(timezone.utc):%Y-%m-%d} (UTC)",
         f"Entorno: {CFG.BINANCE_ENV.upper()}"]
    if cuenta:
        L.append(f"• Equity: ${cuenta['equity']:.2f}  (wallet ${cuenta['wallet']:.2f}, "
                 f"no realizado ${cuenta['unrealized']:+.2f})")
        # ritmo anualizado aprox vs objetivo (usa el primer equity observado)
        e0 = st.get('equity_inicial')
        t0 = st.get('fecha_inicio')
        if e0 and t0 and cuenta['equity'] > 0:
            try:
                dias = max((datetime.now(timezone.utc) - datetime.fromisoformat(t0)).total_seconds() / 86400, 1)
                if dias >= 7 and e0 > 0:
                    anual = (cuenta['equity'] / e0) ** (365.0 / dias) - 1
                    marca = '✅' if OBJ_ANUAL_MIN <= anual else ('🟡' if anual > 0 else '🔴')
                    L.append(f"• Ritmo anualizado ≈ {anual*100:+.1f}% {marca} "
                             f"(objetivo {OBJ_ANUAL_MIN*100:.0f}-{OBJ_ANUAL_MAX*100:.0f}%; {dias:.0f}d de historia)")
                else:
                    L.append(f"• Ritmo anualizado: historia insuficiente ({dias:.0f}d) — se necesita ≥7d")
            except Exception:
                pass
    else:
        L.append("• ⚠️ No pude leer la cuenta de Binance (revisar llaves/IP/permiso).")
    mdd = mdd_90d(cerradas, cuenta['equity'] if cuenta else 500.0)
    if mdd is not None:
        marca = '✅' if mdd <= WARN_MDD_90D else ('🟡' if mdd <= GATE_MDD_90D else '🔴')
        L.append(f"• MDD-90d: {mdd*100:.1f}% {marca} (gate copy-trade ≤{GATE_MDD_90D*100:.0f}%)")
    else:
        L.append("• MDD-90d: historia insuficiente (se necesitan ≥3 cierres)")
    L.append(f"• PnL realizado — semana ${pnl_ventana(cerradas, 7):+.2f} | "
             f"30d ${pnl_ventana(cerradas, 30):+.2f} | acumulado ${sum(p for _,p in cerradas):+.2f} "
             f"({len(cerradas)} cerradas)")
    L.append(f"• Posiciones abiertas ahora: {len(posiciones)}")
    for p in posiciones[:12]:
        try:
            L.append(f"   – {p['symbol']} {float(p['positionAmt']):+g} | "
                     f"no realizado ${float(p['unRealizedProfit']):+.2f}")
        except Exception:
            pass
    procs = procesos_bots()
    infra = ' | '.join(f"{n.split('_')[0]}={'OK' if v else 'CAÍDO'}{'/Z' if z else ''}"
                       for n, (v, z) in procs.items())
    d = disco_pct()
    L.append(f"• Infra: {infra} | disco {d:.0f}%" if d is not None else f"• Infra: {infra}")
    # veredicto simple
    ok_gate = (mdd is None) or (mdd <= GATE_MDD_90D)
    ok_infra = all(v and not z for v, z in procs.values())
    L.append("• Estado: " + ("🟢 EN CAMINO al objetivo copy-trade" if (ok_gate and ok_infra)
                             else "🟠 REVISAR (ver arriba)"))
    L.append("(Detalle completo y stats oficiales: la cuenta de Binance.)")
    return "\n".join(L)


# ----------------------------- loop principal -----------------------------
def main():
    LOG(f"iniciado. entorno={CFG.BINANCE_ENV} base={CFG.TESTNET_BASE} chat={TG_CHAT}")
    st = load_state()
    # registrar equity/fecha inicial la primera vez que se lea la cuenta
    while True:
        try:
            ahora = datetime.now(timezone.utc)
            cerradas = cerradas_combinadas()
            cuenta = api_cuenta()

            # --- chequeo rápido de infra + CORTACIRCUITOS de equity (cada ciclo, dedup) ---
            al_rapidas = chequeo_rapido()
            _piso = getattr(CFG, 'MAINNET_STOP_EQUITY', 0)
            if cuenta and CFG.BINANCE_ENV == 'mainnet' and _piso and cuenta['equity'] < _piso:
                al_rapidas.append(f"🛑 CORTACIRCUITOS: equity ${cuenta['equity']:.2f} < piso "
                                  f"${_piso:.0f} — los bots DEJARON DE ABRIR (las abiertas siguen)")
            previas = set(st.get('alertas_activas', []))
            nuevas = [a for a in al_rapidas if a not in previas]
            if nuevas:
                tg_send("🚨 ALERTA DE SALUD\n" + "\n".join(nuevas))
            resueltas = [a for a in previas if a not in al_rapidas]
            if resueltas:
                tg_send("✅ RESUELTO:\n" + "\n".join(resueltas))
            st['alertas_activas'] = al_rapidas

            # --- equity inicial (cuenta ya leída arriba, para el cortacircuitos) ---
            if cuenta and not st.get('equity_inicial'):
                st['equity_inicial'] = cuenta['equity']
                st['fecha_inicio'] = ahora.isoformat()

            # --- chequeo diario (fin del día) ---
            hoy_str = ahora.date().isoformat()
            if ahora.hour == REPORT_HOUR_UTC and st.get('last_daily') != hoy_str:
                st['last_daily'] = hoy_str
                al_diarias = chequeo_diario(cuenta, cerradas)
                if al_diarias:
                    tg_send(f"⚠️ CHEQUEO DIARIO ({hoy_str}) — algo compromete el objetivo:\n"
                            + "\n".join(al_diarias))
                LOG(f"chequeo diario hecho ({len(al_diarias)} alertas)")

            # --- resumen semanal (domingo, fin del día) ---
            iso_week = f"{ahora.isocalendar()[0]}-W{ahora.isocalendar()[1]:02d}"
            if ahora.weekday() == 6 and ahora.hour == REPORT_HOUR_UTC and st.get('last_weekly') != iso_week:
                st['last_weekly'] = iso_week
                posiciones = api_posiciones()
                tg_send(texto_resumen(cuenta, cerradas, posiciones, st))
                LOG(f"resumen semanal enviado ({iso_week})")

            save_state(st)
        except Exception as e:
            LOG(f'ciclo err {e}')
        time.sleep(CHECK_EVERY)


if __name__ == '__main__':
    main()
