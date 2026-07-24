#!/usr/bin/env python3
"""Parcha el manual para que TODOS los gráficos rendericen y sea auto-contenido:
1. Reemplaza las <img> de estrategia por gráficos de VELAS SVG inline (reales).
2. Arregla mis SVGs esquemáticos que usan var() en atributos (no renderiza) →
   colores explícitos (tarjeta clara siempre legible).
3. Embebe las PNGs que existen como data-URI base64 (self-contained, funciona
   abierto desde cualquier carpeta). Quita las figuras cuya PNG no existe.
"""
import os, re, base64

MANUAL = '/Users/hackerunet/manual_mesa_de_dinero.html'
ASSETS = '/Users/hackerunet/book_assets'
SVGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'graficos_svg')

# paleta clara (del :root del manual) para los SVG esquemáticos
LIGHT = {
 'ink':'#1B1F23','ink-soft':'#52585E','ink-faint':'#7C8288','paper':'#F6F5F0',
 'paper-deep':'#EBE9E1','paper-card':'#FCFBF8','accent':'#9C5E1E','accent-strong':'#7A4715',
 'accent-soft':'#EDDCC0','rule':'#D9D5C9','pos':'#2E7A50','pos-soft':'#DEEBE2',
 'neg':'#A6392E','neg-soft':'#F2DDD9','hold':'#5B5F6B','hold-soft':'#E4E3E8','mono-bg':'#EFEDE4',
}

html = open(MANUAL).read()
n_svg = n_var = n_b64 = n_rm = 0

# --- 1. reemplazar <img> de estrategia por el SVG de velas inline ---
mapa = {
 'book_assets/v26_tendencia.png':'v26_estrategia.svg',
 'book_assets/v36_15m.png':'v36_estrategia.svg',
 'book_assets/v17_rsi.png':'v17_rsi.svg',
 'book_assets/v18_bollinger.png':'v18_bollinger.svg',
}
for png, svgf in mapa.items():
    svg = open(os.path.join(SVGDIR, svgf)).read()
    # reemplazar la etiqueta <img ... src="PNG" ...> completa por el svg
    pat = re.compile(r'<img[^>]*src="' + re.escape(png) + r'"[^>]*>')
    if pat.search(html):
        html = pat.sub(lambda m: svg, html, count=1)
        n_svg += 1

# --- 2. arreglar SVGs esquemáticos: var(--X) en atributos → hex claro ---
def fix_var(m):
    global n_var
    tok = m.group(1)
    n_var += 1
    return LIGHT.get(tok, '#888')
# solo dentro de bloques <svg>...</svg> que contengan var(--   (mis esquemáticos)
def fix_svg_block(m):
    block = m.group(0)
    if 'var(--' not in block:
        return block
    return re.sub(r'var\(--([a-z-]+)\)', fix_var, block)
html = re.sub(r'<svg\b.*?</svg>', fix_svg_block, html, flags=re.S)

# --- 3. imgs restantes: existe → base64; no existe → quitar la <figure> ---
def img_repl(m):
    global n_b64, n_rm
    src = m.group(1)
    fn = os.path.join('/Users/hackerunet', src)
    if os.path.exists(fn):
        with open(fn,'rb') as f: b = base64.b64encode(f.read()).decode()
        n_b64 += 1
        return m.group(0).replace(f'src="{src}"', f'src="data:image/png;base64,{b}"')
    return m.group(0)  # se maneja abajo si falta
# primero, quitar <figure>...</figure> que referencien una PNG inexistente
def figure_repl(m):
    global n_rm
    block = m.group(0)
    srcs = re.findall(r'src="(book_assets/[^"]+)"', block)
    for s in srcs:
        if not os.path.exists(os.path.join('/Users/hackerunet', s)):
            n_rm += 1
            return ''  # figura con imagen faltante → eliminar
    return block
html = re.sub(r'<figure\b.*?</figure>', figure_repl, html, flags=re.S)
# ahora base64 para las que quedan (existen)
html = re.sub(r'<img\b[^>]*src="(book_assets/[^"]+)"[^>]*>', img_repl, html)

open(MANUAL,'w').write(html)
print(f"SVG velas inline: {n_svg} | var() arreglados: {n_var} | PNG→base64: {n_b64} | figuras rotas quitadas: {n_rm}")
print(f"imgs a book_assets restantes (deberían ser 0): {len(re.findall(chr(34)+'book_assets', html))}")
