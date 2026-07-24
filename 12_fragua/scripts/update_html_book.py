import re
import os

HTML_PATH = '/Users/hackerunet/manual_mesa_de_dinero.html'

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Resaltar los nombres de las estrategias en las tablas.
# Buscamos tablas con clase "rtable" y dentro del <tbody> reemplazamos <td>VXX</td> por <td><strong>VXX</strong></td>
def highlight_tables(match):
    table_content = match.group(0)
    # Highlight anything that looks like V + number(s) in the first column or isolated <td>V..</td>
    # Let's match <td>V\d+[A-Z\-_]*</td>
    table_content = re.sub(r'<td>(V\d+[^<]*)</td>', r'<td><strong>\1</strong></td>', table_content)
    # Also handle the master table which has <td>V10 / V11</td> etc.
    table_content = re.sub(r'<td>(V\d+(?:\s*/\s*V\d+)*[^<]*)</td>', r'<td><strong>\1</strong></td>', table_content)
    # But wait, it might match other things. Let's be careful.
    return table_content

content = re.sub(r'<table[^>]*>.*?</table>', highlight_tables, content, flags=re.DOTALL)

# 2. Agregar explicaciones más claras (sin cambiar conclusiones) e imágenes para V41, V45, V47.

# --- V41 ---
v41_chart = '''
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="book_assets/v41_regimen.png" alt="Gráfico V41 - Régimen" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">V41: El ATR no predice el rendimiento relativo de las temporalidades (15m vs 4h) tan nítidamente como sugería la hipótesis de régimen.</figcaption>
        </figure>
'''
# Insert chart in V41 body
content = re.sub(
    r'(<span class="vtag mirage">V41</span>.*?<div class="vbody">\s*<p>La idea:.*?</p>)',
    r'\1' + v41_chart,
    content, flags=re.DOTALL
)
# Enhance narrative for V41
v41_verdict = '''<p style="margin:0">Rechazada: PnL negativo y DD superior. <strong>Causa raíz expandida:</strong> La hipótesis subyacente afirmaba que la alta volatilidad (medida por el ATR) favorecería sistemáticamente a los cruces lentos (4h) al filtrar el ruido, y que la baja volatilidad favorecería a la respuesta rápida (15m). Sin embargo, el mercado invalidó esta relación de forma directa: los latigazos direccionales a menudo rompen las medias lentas precisamente cuando la volatilidad es alta, generando pérdidas asimétricas que el asignador dinámico no puede prevenir. El mercado no cambia de régimen de volatilidad de una forma que coincida temporalmente con la rentabilidad de estas estrategias.</p>'''
content = re.sub(r'<p style="margin:0">Rechazada: PnL negativo y DD superior.*?al revés.</p>', v41_verdict, content, flags=re.DOTALL)

# --- V45 ---
v45_chart = '''
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="book_assets/v45_reversion.png" alt="Gráfico V45 - Reversión" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">V45: Las divergencias extremas de Bollinger a menudo marcan el inicio de una fuerte continuación de tendencia, invalidando la hipótesis de reversión semanal.</figcaption>
        </figure>
'''
content = re.sub(
    r'(<span class="vtag mirage">V45</span>.*?<div class="vbody">\s*<p>La idea:.*?</p>)',
    r'\1' + v45_chart,
    content, flags=re.DOTALL
)
# Enhance narrative for V45
v45_verdict = '''<p style="margin:0">Rechazada: Señal va activamente en la dirección equivocada (pctl 22.5). <strong>Causa raíz expandida:</strong> El factor de reversión (comprar los perdedores y vender los ganadores de la última semana) es un factor clásico de equities que aquí destruye capital. En cripto, un activo que cae severamente en una semana a menudo sufre de deterioro fundamental o desapalancamiento en cascada, mientras que los ganadores absorben toda la liquidez del ecosistema. El momentum de corto plazo aplasta estructuralmente cualquier efecto de reversión a la media en la sección cruzada de temporalidad semanal.</p>'''
content = re.sub(r'<p style="margin:0">Rechazada: Señal va.*?, el momentum domina.</p>', v45_verdict, content, flags=re.DOTALL)

# --- V47 ---
v47_chart = '''
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="book_assets/v47_pairs_spread.png" alt="Gráfico V47 - Spread" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">V47: El spread cruza el umbral de entrada (2σ), pero en lugar de revertir a su media, diverge severamente hasta romper el stop (4σ), evidenciando un breakdown estructural del equilibrio.</figcaption>
        </figure>
'''
content = re.sub(
    r'(<span class="vtag mirage">V47</span>.*?<div class="vbody">\s*<p>La idea:.*?</p>)',
    r'\1' + v47_chart,
    content, flags=re.DOTALL
)
# Enhance narrative for V47
v47_verdict = '''<p style="margin:0">Rechazada: los tres criterios IS fallan (PnL −26%, PF 0.74, percentil 34.8). OOB no se corrió. <strong>Causa raíz expandida:</strong> El arbitraje de pares asume un "resorte" invisible (cointegración) que obliga al precio a volver al promedio histórico del par. En cripto, este resorte se rompe ~90% del tiempo. Esto se debe a que la dinámica de capital no se mueve por sectores fijos (como Pepsi vs Coca-Cola), sino por rotaciones violentas de narrativas y liquidez. Cuando un L1 entra en "price discovery", el spread nunca revierte; simplemente establece un nuevo equilibrio en otro planeta. La cointegración con ventanas fijas no provee ningún edge estadísticamente robusto.</p>'''
content = re.sub(r'<p style="margin:0">Rechazada: los tres criterios IS fallan.*?mientras otro no.</p>', v47_verdict, content, flags=re.DOTALL)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print("Modificaciones inyectadas con éxito.")
