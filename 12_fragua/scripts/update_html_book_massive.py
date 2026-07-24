import re
import os

HTML_PATH = '/Users/hackerunet/manual_mesa_de_dinero.html'

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

def inject_after_vbody(vtag, chart_path, alt_text, caption):
    global content
    # Find the block starting with <span class="vtag...">vtag</span>
    # and the very next <div class="vbody">
    
    # We will use regex to find this specific vcard and insert the figure at the top of vbody.
    pattern = r'(<span class="vtag[^>]*>' + vtag + r'.*?<div class="vbody">)'
    
    chart_html = f'''
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="{chart_path}" alt="{alt_text}" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">{caption}</figcaption>
        </figure>
'''
    content = re.sub(pattern, r'\1' + chart_html, content, flags=re.DOTALL)

# Injecting charts into existing vcards
inject_after_vbody(r'V26', 'book_assets/v26_tendencia.png', 'V26 Tendencia', 'V26: Señal basada en cruce de medias con salida dinámica en el cruce inverso ("flip"), capturando la totalidad del impulso direccional.')
inject_after_vbody(r'V35 → V36', 'book_assets/v36_15m.png', 'V36 15m', 'V36: Identificación de patrones de acción del precio en marcos de tiempo de 15m (ej. formaciones de rechazo) con confirmación de tendencia mayor.')
inject_after_vbody(r'V21 · V22', 'book_assets/p1_p2_salidas.png', 'V21 V22', 'V21/V22: Representación del riesgo inherente a salidas estáticas o lógicas defectuosas que ignoran la dinámica viva del mercado.')
inject_after_vbody(r'V24 · V24-A', 'book_assets/v24_honesto.png', 'V24 Motor Honesto', 'V24 (Motor Honesto): Visualización de la erosión del PnL debida a la brecha entre el precio teórico (sin fricción) y el spread/fee real que asume el motor al cruzar la liquidez.')
inject_after_vbody(r'P1', 'book_assets/p1_p2_salidas.png', 'Salidas P1', 'P1: Cerrar prematuramente la posición corta los beneficios antes de que la tendencia termine, destruyendo la asimetría ganancia/pérdida del sistema.')
inject_after_vbody(r'P2', 'book_assets/p1_p2_salidas.png', 'Salidas P2', 'P2: Forzar salidas por condiciones de sobre-extensión teóricas a menudo hace abandonar el trade antes de la fase de euforia/pánico más rentable.')

# For V17, V18, V19, create a gallery section and append it right before "Apéndice A"
gallery_html = '''
  <section class="chapter" id="apGallery">
    <header class="chapter-head">
      <span class="chlabel">Apéndice Visual</span>
      <h2>Galería de Espejismos Tempranos (La Era Oscura)</h2>
    </header>
    <p class="lede">Gráficos basados en los backtests tempranos que revelaron la fragilidad de depender exclusivamente de indicadores rezagados y señales ingenuas fuera de contexto.</p>
    
    <div style="display: flex; flex-direction: column; gap: 2rem;">
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="book_assets/v17_rsi.png" alt="V17 RSI Momentum" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">V17_C: RSI Momentum. Cuando el activo entra en verdadera tendencia, el oscilador permanece en sobrecompra prolongada. Intentar vender/revertir en RSI > 70 resultó sistemáticamente destructivo.</figcaption>
        </figure>
        
        <figure style="margin: 1.5rem 0; text-align: center;">
          <img src="book_assets/v18_bollinger.png" alt="V18 Bollinger Extremo" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;">
          <figcaption style="color: #888; font-size: 0.9em; margin-top: 0.5rem;">V18_A: Bollinger Extremo. Un precio rompiendo bandas lejanas (ej. 2.5σ) en cripto rara vez indica una reversión a la media inminente; suele ser el catalizador de un nuevo régimen de precios (ruptura), atrapando al trader que apuesta por la reversión.</figcaption>
        </figure>
    </div>
  </section>

  <!-- APÉNDICE A -->'''

# Insert the gallery before "APÉNDICE A"
content = content.replace('<!-- APÉNDICE A -->', gallery_html)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML actualizado con los gráficos masivos.")
