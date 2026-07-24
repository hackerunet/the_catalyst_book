"""oracle_exit_v26.py — ¿cuánto se "deja sobre la mesa" por no salir en el pico exacto?

Pregunta del usuario (2026-07-04): ¿cómo sabríamos si nuestros bots son malos saliendo?

Método: para cada trade cerrado, recalcula el PnL neto (MISMA función de costos que el motor real,
`pnl_neto_cierre` — fee+slippage+funding) como si hubiera cerrado exactamente en su `peak_progress`
(el máximo favorable ya trackeado por telemetría) en vez de en su cierre real. Esto es un límite
TEÓRICO/imposible de alcanzar en la práctica (nadie sabe el pico de antemano) — sirve para cuantificar
el TAMAÑO del hueco entre "lo que se pudo haber ganado" y "lo que se ganó", no para proponer una regla
implementable. Aproximación declarada: usa `exit_time` real (no el momento exacto del pico, que no se
trackea) para el cálculo de funding — efecto de segundo orden, no cambia la conclusión.

Uso: python3 oracle_exit_v26.py
"""
import estrategia
from dd_real_v26 import correr
from backtest import pnl_neto_cierre


def peak_price(t):
    """Precio correspondiente al peak_progress trackeado (misma fórmula que calcular_progreso, invertida)."""
    recorrido = (t['tp'] - t['entry_price']) if t['type'] == 'LONG' else (t['entry_price'] - t['tp'])
    avance = t.get('peak_progress', 0.0) / 100.0 * recorrido
    return t['entry_price'] + avance if t['type'] == 'LONG' else t['entry_price'] - avance


def main():
    bt = correr('wf_cache_4h_8760_2026-06-11_0000.pkl',
                risk=__import__('config').PORTFOLIO_RISK_CAP / len(__import__('config').SYMBOLS))
    cerrados = [t for t in bt.trades if t['status'] == 'CERRADA']

    pnl_real_total = sum(t['pnl'] for t in cerrados)
    pnl_oracle_total = 0.0
    filas = []
    for t in cerrados:
        pp = peak_price(t)
        pnl_oracle = pnl_neto_cierre(t, pp, t['exit_time'])
        pnl_oracle_total += pnl_oracle
        filas.append((t['symbol'], t['type'], t.get('peak_progress', 0.0), t['exit_reason'],
                      t['pnl'], pnl_oracle, pnl_oracle - t['pnl']))

    print(f"Trades cerrados: {len(cerrados)}")
    print(f"PnL REAL total:        ${pnl_real_total:,.2f}")
    print(f"PnL ORACLE total:      ${pnl_oracle_total:,.2f}  (cierre en el pico exacto de cada trade)")
    print(f"Hueco (oracle − real): ${pnl_oracle_total - pnl_real_total:,.2f}")
    print(f"El real captura el {pnl_real_total / pnl_oracle_total * 100:.1f}% del PnL-oracle.\n")

    # Desglose: ¿de dónde viene el hueco? Por motivo de cierre real.
    por_motivo = {}
    for _, _, _, motivo, real, oracle, hueco in filas:
        d = por_motivo.setdefault(motivo, {'n': 0, 'real': 0.0, 'oracle': 0.0, 'hueco': 0.0})
        d['n'] += 1
        d['real'] += real
        d['oracle'] += oracle
        d['hueco'] += hueco
    print(f"{'motivo de cierre':30} | {'n':>4} | {'PnL real':>12} | {'PnL oracle':>12} | {'hueco':>12}")
    for motivo, d in sorted(por_motivo.items(), key=lambda kv: -kv[1]['hueco']):
        print(f"{motivo:30} | {d['n']:4} | {d['real']:12,.2f} | {d['oracle']:12,.2f} | {d['hueco']:12,.2f}")

    # Top 10 huecos más grandes — para ver si son los STOP normales o los FLIP tardíos.
    print("\nTop 15 trades por hueco (oracle - real) más grande:")
    for sym, tipo, pico, motivo, real, oracle, hueco in sorted(filas, key=lambda f: -f[6])[:15]:
        print(f"  {sym:9} {tipo:5} pico {pico:7.1f}% | {motivo:28} | real {real:9,.2f} | "
              f"oracle {oracle:9,.2f} | hueco {hueco:9,.2f}")


if __name__ == '__main__':
    main()
