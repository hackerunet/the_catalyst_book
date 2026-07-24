"""Constantes y funciones de costo — ESPEJADAS del motor vivo (no importadas).

Fuente de verdad (verificable, NO se importa para mantener aislamiento total):
  bot_alpha_portfolio/stable_v25_prototype/config.py
    BT_TAKER_FEE  = 0.0005   # 0.05% por lado
    BT_SLIPPAGE   = 0.0005   # 0.05% por lado
    BT_FUNDING_8H = 0.0001   # 0.01% cada 8 horas

Si esas constantes cambian en el motor vivo, hay que actualizar este espejo (Fable: verificar que coincidan
en cada validación — ítem B2 de HONESTIDAD.md).
"""

# --- Espejo de constantes (deben COINCIDIR con config.py del motor vivo) ---
TAKER_FEE = 0.0005
SLIPPAGE = 0.0005
FUNDING_8H = 0.0001

# Costo total por cambiar 1 unidad de nocional (una vuelta de un lado): fee + slippage.
COSTO_POR_TURNOVER = TAKER_FEE + SLIPPAGE  # 0.0010 = 0.10% del nocional movido


def costo_rebalanceo(turnover_fraccion):
    """Costo (como fracción del equity) de un rebalanceo dado su turnover.

    turnover_fraccion = sum_s |peso_nuevo[s] - peso_viejo_driftado[s]|  (en unidades de equity).
    Cada unidad de nocional que se compra o vende paga fee+slippage una vez.
    Pesimista por construcción: cobra el turnover COMPLETO (no netea maker/taker).
    """
    return turnover_fraccion * COSTO_POR_TURNOVER


def costo_funding(gross_expuesto, horas):
    """Drag de funding (fracción del equity) sobre el nocional bruto mantenido `horas` horas.

    CONSERVADOR / PESIMISTA: cobra funding sobre el nocional BRUTO (gross = long + short) como costo puro.
    En un libro dollar-neutral real, el lado corto RECIBE funding cuando es positivo, así que el neto suele
    ser menor (o incluso favorable) — modelarlo per-símbolo con datos reales de funding es el refinamiento
    (y es, de hecho, la señal del factor de carry V46). Mientras no se modele per-símbolo, este drag bruto
    es el límite pesimista y NO debe interpretarse como el funding neto real.

    Fable: este es un punto de honestidad a evaluar explícitamente (ítem B3). Es deliberadamente pesimista.
    """
    periodos_8h = horas / 8.0
    return gross_expuesto * FUNDING_8H * periodos_8h
