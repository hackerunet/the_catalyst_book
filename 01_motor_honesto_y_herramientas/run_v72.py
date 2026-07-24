#!/usr/bin/env python3
"""V72 "EL ESPEJISMO" — el win rate es un DIAL, no una habilidad.

Misma ENTRADA que V26 (cruce, 4h) — la ÚNICA variable es la estructura de salida:
  V26      : EXIT_MODE='tendencia' (stop + flip, sin TP)  -> WR 18%
  V72      : EXIT_MODE='escalera' con el pullback DESARMADO (PULLBACK_ARM_DECILE=999)
             = TP duro + STOP puro. El dial es SL_FRACTION_OF_TP:
                 dist_sl = dist_tp * SL_FRACTION_OF_TP
                 WR teórico ~ SL/(TP+SL) = SLF/(1+SLF)

El WR se mide NETO (pnl_neto_cierre: bruto − comisión − slippage − funding; ganadora
solo si pnl > 0) = el criterio "breakeven +1" del usuario.
Protección de dinero intacta: el sizing va por dist_sl -> riesgo en $ constante.
SOLO LECTURA. No toca ningún bot vivo.
"""
import numpy as np

from suavizado_v37 import correr, equity_mtm, CFG_V26, CACHE_4H_ORIG, CACHE_4H_OOB

BASE_V72 = dict(INTERVAL='4h', ENTRY_MODE='cruce', EXIT_MODE='escalera',
                PULLBACK_ARM_DECILE=999,   # desarma el cierre por retroceso -> TP/SL puro
                TIME_STOP_HOURS=None,
                BT_TAKER_FEE=0.0002, BT_SLIPPAGE=0.0002, COOLDOWN_CANDLES=8)


def medir(bt, balance=500.0):
    tr = [t for t in bt.trades if t['status'] == 'CERRADA']
    n = len(tr)
    if not n:
        return None
    w = sum(1 for t in tr if t['pnl'] > 0)           # NETO: "breakeven +1"
    be = sum(1 for t in tr if abs(t['pnl']) < 0.01)  # cuántas quedan en ~cero
    pnl = sum(t['pnl'] for t in tr)
    g = sum(t['pnl'] for t in tr if t['pnl'] > 0)
    p = -sum(t['pnl'] for t in tr if t['pnl'] <= 0)
    eq = equity_mtm(bt, balance_inicial=balance)
    v = eq.values
    mdd = float(np.max((np.maximum.accumulate(v) - v) / np.maximum.accumulate(v))) * 100
    gan_prom = g / w if w else 0
    per_prom = p / (n - w) if n > w else 0
    return dict(n=n, wr=100 * w / n, be=be, roi=100 * pnl / balance,
                pf=g / p if p else 9.99, mdd=mdd,
                gan_prom=gan_prom, per_prom=per_prom)


def fila(nom, m, teorico=None):
    t = f"{teorico:>5.0f}%" if teorico else "    —"
    print(f"  {nom:26} {m['n']:>5} {m['wr']:>7.2f}% {t} {m['roi']:>+9.2f}% "
          f"{m['pf']:>6.3f} {m['mdd']:>6.1f}% ${m['gan_prom']:>+6.2f} ${m['per_prom']:>+6.2f}")


def main():
    print("=" * 96)
    print('  V72 "EL ESPEJISMO" — misma entrada que V26 (cruce 4h), solo cambia la salida')
    print("  WR medido NETO de comisiones (= 'breakeven +1'). 4 años, maker, riesgo 0.33%.")
    print("=" * 96)

    for etiqueta, cache in [("CANASTA ORIGINAL (in-sample)", CACHE_4H_ORIG),
                            ("CANASTA OOB", CACHE_4H_OOB)]:
        print(f"\n### {etiqueta} ###")
        print(f"  {'config':26} {'trades':>5} {'WR NETO':>8} {'teór':>6} {'PnL':>10} "
              f"{'PF':>6} {'MaxDD':>7} {'gan.prom':>8} {'per.prom':>8}")
        print(f"  {'-'*26} {'-'*5} {'-'*8} {'-'*6} {'-'*10} {'-'*6} {'-'*7} {'-'*8} {'-'*8}")

        m26 = medir(correr(cache, CFG_V26))
        fila("V26 (flip, el lead)", m26)

        for slf in (0.75, 2.0, 3.0, 4.0):
            cfg = dict(BASE_V72, SL_FRACTION_OF_TP=slf)
            m = medir(correr(cache, cfg))
            teo = 100 * slf / (1 + slf)
            fila(f"V72 dial SLF={slf}", m, teo)

    print("\n" + "=" * 96)
    print("  LECTURA: el WR sube con el dial tal como predice SL/(TP+SL) — sin cambiar")
    print("  NADA de la señal. Lo que se paga por comprarlo está en la columna PnL.")
    print("=" * 96)


if __name__ == '__main__':
    main()
