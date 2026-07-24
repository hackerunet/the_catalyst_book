#!/usr/bin/env python3
"""
Framework de tracking de experimentos para V22.

Lee la ultima linea ALERTA_BACKTEST_RESUMEN de mesa_v22.out, la combina con
un identificador de cambio + descripcion, y la agrega como fila a
backtest_history.csv. Asi cada restart queda registrado y se puede comparar
el rendimiento por puerta/regimen a traves del tiempo, evitando regresiones
silenciosas.

Uso:
    python3 log_backtest.py <change_id> "<descripcion del cambio>"

Ejemplo:
    python3 log_backtest.py tp2r_be1r "Puerta A TP 3R->2R, breakeven vuelve a +1R"
"""
import sys
import json
import csv
import os
from datetime import date

LOG_FILE = os.path.join(os.path.dirname(__file__), 'mesa_v22.out')
CSV_FILE = os.path.join(os.path.dirname(__file__), 'backtest_history.csv')

PUERTAS = ['A', 'B', 'C']
REGIMENES = ['TENDENCIA', 'BAJA_VOLATILIDAD', 'RANGO', 'TENDENCIA_EMERGENTE']

FIELDNAMES = ['date', 'change_id', 'change_description',
              'capital_inicial', 'capital_final', 'net_pnl_usd', 'net_pnl_pct',
              'trades', 'win_rate', 'profit_factor']
for p in PUERTAS:
    FIELDNAMES += [f'{p}_trades', f'{p}_wr', f'{p}_pnl']
for r in REGIMENES:
    FIELDNAMES += [f'{r}_trades', f'{r}_wr', f'{r}_pnl']


def find_last_resumen(path):
    """
    Busca la ultima linea ALERTA_BACKTEST_RESUMEN_FIXED (ventana fija,
    apples-to-apples entre restarts). NO usa ALERTA_BACKTEST_RESUMEN (ventana
    "ahora - N velas", se desplaza en cada restart y no es comparable).
    """
    last = None
    with open(path) as f:
        for line in f:
            if 'ALERTA_BACKTEST_RESUMEN_FIXED|' in line:
                last = line.split('ALERTA_BACKTEST_RESUMEN_FIXED|', 1)[1].strip()
    if last is None:
        raise SystemExit(f"No ALERTA_BACKTEST_RESUMEN_FIXED found in {path}")
    return json.loads(last)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Uso: log_backtest.py <change_id> "<descripcion>"')
    change_id, description = sys.argv[1], sys.argv[2]

    data = find_last_resumen(LOG_FILE)
    por_puerta = data.get('por_puerta', {})
    por_regimen = data.get('por_regimen', {})

    row = {
        'date': date.today().isoformat(),
        'change_id': change_id,
        'change_description': description,
        'capital_inicial': data.get('capital_inicial'),
        'capital_final': data.get('capital_final'),
        'net_pnl_usd': data.get('net_pnl_usd'),
        'net_pnl_pct': data.get('net_pnl_pct'),
        'trades': data.get('trades'),
        'win_rate': data.get('win_rate'),
        'profit_factor': data.get('profit_factor'),
    }
    for p in PUERTAS:
        d = por_puerta.get(p, {})
        row[f'{p}_trades'] = d.get('trades')
        row[f'{p}_wr'] = d.get('win_rate')
        row[f'{p}_pnl'] = d.get('pnl')
    for r in REGIMENES:
        d = por_regimen.get(r, {})
        row[f'{r}_trades'] = d.get('trades')
        row[f'{r}_wr'] = d.get('win_rate')
        row[f'{r}_pnl'] = d.get('pnl')

    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    print(f"Logged {change_id} -> {CSV_FILE}")
    print(json.dumps(row, indent=2))


if __name__ == '__main__':
    main()
