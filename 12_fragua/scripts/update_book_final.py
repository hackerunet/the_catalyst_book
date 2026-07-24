import re
import os

HTML_PATH = '/Users/hackerunet/manual_mesa_de_dinero.html'

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Concept of SUPERADA
superada_explanation = '''
  <div class="callout accent" id="superada-def">
    <span class="clabel">Definición: "SUPERADA"</span>
    <p>A lo largo de los apéndices y el historial temprano encontrarás varias estrategias marcadas como <span style="font-weight:bold; font-family:var(--mono); font-size:0.85em; border: 1px solid var(--ink); padding: 2px 6px; border-radius: 4px; margin-right: 4px;">Superada</span>. Este es un término técnico dentro de nuestra mesa de dinero que indica que la estrategia fue un <strong>prototipo útil que cumplió su propósito investigativo</strong> en su momento, pero fue fundamentalmente reemplazada por una arquitectura más robusta, limpia o universal (como la V26 o V36). No significa necesariamente que fuera perdedora, sino que su código o premisa evolucionó hacia algo mejor, enviando la versión original al archivo histórico.</p>
  </div>
'''
if 'id="superada-def"' not in content:
    # Insert it right after the Apéndice Visual or Apéndice A
    content = content.replace('<!-- APÉNDICE A -->', superada_explanation + '\n  <!-- APÉNDICE A -->')

# 2. Highlight names of strategies in tables
def highlight_tables(match):
    table_content = match.group(0)
    # If the table is already processed, skip to avoid nested strong tags.
    if '<td><strong>V' in table_content:
        return table_content
    # Highlight V10, V11, V17_C, etc.
    table_content = re.sub(r'<td>(V\d+(?:_[A-Z])?(?:\s*/\s*V\d+)*[^<]*)</td>', r'<td><strong>\1</strong></td>', table_content)
    # Highlight P1, P2, P3
    table_content = re.sub(r'<td>(P\d+[^<]*)</td>', r'<td><strong>\1</strong></td>', table_content)
    return table_content

content = re.sub(r'<table[^>]*>.*?</table>', highlight_tables, content, flags=re.DOTALL)


# 3. Add Graphics for V17_C, V18_A, V19_C, V22 (if they aren't already there)
# Note: V17_C and V18_A were already added in update_html_book_massive.py as a gallery!
# Let's check if V19_C and V22 are missing and add them to the gallery or their respective cards.
def inject_after_vbody(vtag, chart_path, alt_text, caption):
    global content
    if chart_path in content:
        return # already injected
    pattern = r'(<span class="vtag[^>]*>' + vtag + r'.*?<div class="vbody">)'
    chart_html = f'''
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="{chart_path}" alt="{alt_text}" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">{caption}</figcaption>
        </figure>
'''
    # We must only replace once
    content = re.sub(pattern, r'\1' + chart_html, content, count=1, flags=re.DOTALL)

# Injecting charts for V19_C and V22
inject_after_vbody(r'V19_C', 'book_assets/v19_c_swing.png', 'V19_C Swing Rejection', 'V19_C: Swing Rejection. El backtest reconstruido muestra que la "alta tasa de aciertos" era un subproducto de los stops amplios; las señales no poseían edge estadístico real vs Monte Carlo, siendo indistinguibles del azar.')
inject_after_vbody(r'V22', 'book_assets/v22_three_doors.png', 'V22 Three Doors', 'V22: Three-Door System. A pesar de su extrema complejidad (Gate A, B y C) y su lógica de régimen, el sistema evaluado honestamente resultó ser un espejismo: su aparente rentabilidad (+58% en Multi-Cripto) fue impulsada puramente por el beta alcista del mercado, fallando en superar el percentil 95 estadístico en todos los ejes.')

# 4. Clarify Failures for V17_C, V18_A, V19_C, V22
# The manual has <div class="verdict no">...<p>Rechazada...
# Let's expand their verdicts if they exist.
def expand_verdict(vtag, expansion_text):
    global content
    # Find the verdict inside the card for vtag
    vcard_pattern = r'(<div class="vcard[^>]*>.*?<span class="vtag[^>]*>' + vtag + r'.*?<div class="verdict[^>]*>.*?<p style="margin:0">)(.*?)(</p>.*?</div>.*?</div>)'
    
    def repl(m):
        original_text = m.group(2)
        if "Causa raíz expandida:" in original_text:
            return m.group(0) # already expanded
        return m.group(1) + original_text + " <strong>Causa raíz expandida:</strong> " + expansion_text + m.group(3)

    content = re.sub(vcard_pattern, repl, content, flags=re.DOTALL)

expand_verdict('V17_C', 'Las divergencias de RSI o condiciones de sobrecompra en cripto rara vez actúan como anclas de reversión a la media. En su lugar, el estado continuo de RSI extremo es la firma estadística de los regímenes de Price Discovery y momentum direccional puro.')
expand_verdict('V18_A', 'Perseguir extremos de Bandas de Bollinger asume que el activo respeta una distribución normal estática. En activos de cola pesada, cruzar 2.5σ suele ser el inicio del movimiento real, atrapando al sistema en el lado equivocado de la explosión de volatilidad.')
expand_verdict('V19_C', 'Sometida al motor honesto, la "tasa de acierto del 90%" desaparece. El aparente éxito histórico era un producto de no capar el riesgo, y la señal en sí misma probó ser estadísticamente indistinguible de entradas puramente aleatorias según el Monte Carlo.')
expand_verdict('V22', 'A pesar de poseer tres "puertas" lógicas complejas adaptadas a diferentes regímenes (Tendencia, Impulso, Reversión), la validación cruzada demostró que las puertas no tenían edge predictivo real (percentil ~53). El PnL positivo histórico era simplemente el resultado de estar expuesto "largo" durante un ciclo macroeconómico alcista generalizado (Buy & Hold encubierto).')

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("Actualizaciones inyectadas con éxito.")
