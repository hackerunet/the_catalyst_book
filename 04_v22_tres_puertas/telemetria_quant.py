import numpy as np
from typing import List, Dict

def generar_reporte_cuantitativo(historial_trades: List[Dict], capital_inicial: float = 500.0) -> str:
    """
    Cerebro estadístico: Recrea la hoja de balance de TradingView.
    Espera una lista de diccionarios con al menos la llave 'pnl'.
    Ejemplo: [{'pnl': 1.45, 'signal': 'LONG'}, {'pnl': -0.5, 'signal': 'SHORT'}]
    """
    if not historial_trades:
        return "⚠️ ALERTA DE TELEMETRÍA: Historial vacío. No hay trades para procesar."

    # Extraemos el vector numérico de PnL puro
    pnls = np.array([trade.get('pnl', 0.0) for trade in historial_trades])

    # Segmentación escalar
    total_trades = len(pnls)
    ganadores = pnls[pnls > 0]
    perdedores = pnls[pnls <= 0]

    total_ganadores = len(ganadores)
    total_perdedores = len(perdedores)

    # Flujo de caja
    beneficio_bruto = np.sum(ganadores) if total_ganadores > 0 else 0.0
    perdida_bruta = np.abs(np.sum(perdedores)) if total_perdedores > 0 else 0.0
    net_pnl = beneficio_bruto - perdida_bruta
    rentabilidad_pct = (net_pnl / capital_inicial) * 100

    # Métricas de Asimetría (Edge)
    profit_factor = beneficio_bruto / perdida_bruta if perdida_bruta > 0 else float('inf')
    win_rate = (total_ganadores / total_trades) * 100
    avg_win = np.mean(ganadores) if total_ganadores > 0 else 0.0
    avg_loss = np.abs(np.mean(perdedores)) if total_perdedores > 0 else 0.0

    # Esperanza Matemática: E = (P(W) * AvgW) - (P(L) * AvgL)
    esperanza = ((win_rate / 100) * avg_win) - (((100 - win_rate) / 100) * avg_loss)

    # Cálculo de Maximum Drawdown (Caída máxima desde un pico)
    curva_capital = capital_inicial + np.cumsum(pnls)
    # Rellenamos con el capital inicial al principio para capturar caídas tempranas
    curva_completa = np.insert(curva_capital, 0, capital_inicial)
    picos_historicos = np.maximum.accumulate(curva_completa)
    drawdowns = (curva_completa - picos_historicos) / picos_historicos
    max_drawdown_pct = np.abs(np.min(drawdowns)) * 100

    # Compilación del reporte final
    reporte = (
        f"\n{'='*40}\n"
        f"📊 REPORTE DE TELEMETRÍA CUANTITATIVA\n"
        f"{'='*40}\n"
        f"Capital Inicial:      ${capital_inicial:.2f}\n"
        f"Capital Final:        ${(capital_inicial + net_pnl):.2f}\n"
        f"Net PnL:              ${net_pnl:.2f} ({rentabilidad_pct:+.2f}%)\n"
        f"{'-'*40}\n"
        f"Total Operaciones:    {total_trades}\n"
        f"Win Rate:             {win_rate:.2f}%\n"
        f"Winners / Losers:     {total_ganadores} / {total_perdedores}\n"
        f"{'-'*40}\n"
        f"Beneficio Bruto:      ${beneficio_bruto:.2f}\n"
        f"Pérdida Bruta:        ${perdida_bruta:.2f}\n"
        f"Profit Factor:        {profit_factor:.3f}\n"
        f"Esperanza / Trade:    ${esperanza:.2f}\n"
        f"Maximum Drawdown:     {max_drawdown_pct:.2f}%\n"
        f"Avg Win / Avg Loss:   ${avg_win:.2f} / ${avg_loss:.2f}\n"
        f"{'='*40}\n"
    )

    return reporte
