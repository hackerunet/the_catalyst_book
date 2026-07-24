"""
giveback_analisis.py — ¿los picos grandes de avance (186%, 90%, etc.) se
recuperan o se devuelven al stop? Pregunta del usuario 2026-07-01: tras un
pico ~186% en V26, la posición nunca se recuperó y varias posiciones que
llegaron a ~90% terminaron en stop loss de nuevo.

Corre el motor honesto de V26 (config de referencia,
riesgo 0.33%/símbolo) sobre el cache de 4 años ya existente, y para CADA
trade usa el peak_progress ya trackeado por el motor (telemetría, no afecta
la decisión de salida) para bucketear: cuántos trades alcanzan cada rango de
pico, y de esos, qué fracción termina en FLIP (ganador real) vs STOP (se
devolvió) vs ADMIN, más el "giveback" (pico - progreso al cierre) de los que
terminan en STOP.

Responde con evidencia de 4 años (no la muestra chica en vivo) si el patrón
"pico grande → nunca se recupera → stop" es la norma histórica de esta
estrategia o algo nuevo/peor que lo documentado.

Uso: python3 giveback_analisis.py
"""
import estrategia
from dd_real_v26 import correr, BALANCE_INICIAL

BUCKETS = [(-1e9, 0), (0, 25), (25, 50), (50, 75), (75, 100),
           (100, 150), (150, 200), (200, 1e9)]


def bucket_de(p):
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return f"{lo:.0f}-{hi:.0f}%" if hi < 1e9 else f">={lo:.0f}%"
    return "?"


def main():
    bt = correr('wf_cache_4h_8760_2026-06-11_0000.pkl',
                risk=None if False else __import__('config').PORTFOLIO_RISK_CAP / len(__import__('config').SYMBOLS))
    cerrados = [t for t in bt.trades if t['status'] == 'CERRADA']
    print(f"\nTotal trades cerrados: {len(cerrados)}\n")

    grupos = {}
    for t in cerrados:
        pico = t.get('peak_progress', 0.0)
        b = bucket_de(pico)
        grupos.setdefault(b, []).append(t)

    orden = [f"{lo:.0f}-{hi:.0f}%" if hi < 1e9 else f">={lo:.0f}%" for lo, hi in BUCKETS]
    print(f"{'bucket pico':>12} | {'n':>4} | {'FLIP(win)':>10} | {'STOP':>6} | {'ADMIN':>6} | "
          f"{'PnL total':>10} | {'PnL prom':>9} | {'giveback prom (solo STOP)':>26}")
    print("-" * 110)
    for b in orden:
        ts = grupos.get(b, [])
        if not ts:
            continue
        n = len(ts)
        flips = sum(1 for t in ts if 'FLIP' in (t['exit_reason'] or ''))
        stops = sum(1 for t in ts if 'STOP' in (t['exit_reason'] or ''))
        admin = n - flips - stops
        pnl_total = sum(t['pnl'] for t in ts)
        pnl_prom = pnl_total / n
        # giveback: pico - progreso en el cierre, solo para los que cerraron por STOP
        givebacks = []
        for t in ts:
            if 'STOP' in (t['exit_reason'] or ''):
                prog_exit = estrategia.calcular_progreso(t, t['exit_price'])
                givebacks.append(t.get('peak_progress', 0.0) - prog_exit)
        gb_prom = sum(givebacks) / len(givebacks) if givebacks else 0.0
        print(f"{b:>12} | {n:>4} | {flips:>10} | {stops:>6} | {admin:>6} | "
              f"${pnl_total:>+9.2f} | ${pnl_prom:>+8.2f} | {gb_prom:>25.1f}pp")

    # Detalle de los picos MUY grandes (>=150%) — casos como el "186%" del usuario
    print("\n" + "=" * 110)
    print("DETALLE — trades con pico de avance >= 150% (el rango del caso '186%' reportado)")
    print("=" * 110)
    grandes = sorted([t for t in cerrados if t.get('peak_progress', 0) >= 150],
                     key=lambda t: -t['peak_progress'])
    for t in grandes:
        prog_exit = estrategia.calcular_progreso(t, t['exit_price'])
        dur = (t['exit_time'] - t['entry_time'])
        print(f"  {t['symbol']:9} {t['type']:5} pico {t['peak_progress']:6.1f}% → cierre "
              f"{prog_exit:6.1f}% ({t['exit_reason']:35}) | PnL ${t['pnl']:+7.2f} | "
              f"dur {dur.days}d{dur.seconds//3600}h | entrada {t['entry_time']:%Y-%m-%d %H:%M}")

    print(f"\nn trades con pico>=150%: {len(grandes)} | de esos, terminaron en FLIP (ganador): "
          f"{sum(1 for t in grandes if 'FLIP' in (t['exit_reason'] or ''))} | en STOP (se devolvió todo): "
          f"{sum(1 for t in grandes if 'STOP' in (t['exit_reason'] or ''))}")

    # Resumen global WR / concentración
    r = bt.resumen()
    ganadores = [t for t in cerrados if t['pnl'] > 0]
    print(f"\nGlobal: {r['trades']} trades | WR {r['win_rate']}% | PnL {r['net_pnl_pct']:+.2f}%")
    print(f"Ganadores: {len(ganadores)} ({len(ganadores)/len(cerrados)*100:.1f}%) — "
          f"de esos, ¿cuántos NUNCA superaron pico 150%? "
          f"{sum(1 for t in ganadores if t.get('peak_progress',0) < 150)}")


if __name__ == '__main__':
    main()
