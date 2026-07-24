#!/usr/bin/env python3
"""Genera gráficos de VELAS reales (SVG auto-contenido) para el manual.
Cada gráfico usa datos OHLC reales del cache + la lógica de la estrategia
(cruces EMA, RSI, Bollinger...) y marca entrada/salida como un tablero de trade.
SVG con <style> propio (renderiza en cualquier navegador, sin var() en atributos)
y colores que funcionan en tema claro y oscuro (prefers-color-scheme)."""
import os, pickle
import numpy as np, pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, 'graficos_svg')
os.makedirs(OUT, exist_ok=True)

STYLE = """<style>
.cbg{fill:#FCFBF8} .cgrid{stroke:#E4E1D6;stroke-width:1} .up{fill:#2E7A50;stroke:#2E7A50}
.dn{fill:#A6392E;stroke:#A6392E} .wu{stroke:#2E7A50;stroke-width:1.4} .wd{stroke:#A6392E;stroke-width:1.4}
.e1{stroke:#C77D2E;stroke-width:2;fill:none} .e2{stroke:#7C8288;stroke-width:2;fill:none;stroke-dasharray:5 3}
.bb{stroke:#6E7AD6;stroke-width:1.3;fill:none;stroke-dasharray:3 3} .lvl{stroke:#7C8288;stroke-width:1;stroke-dasharray:4 3}
.txt{fill:#1B1F23;font-family:ui-monospace,Menlo,monospace} .txf{fill:#7C8288;font-family:ui-monospace,Menlo,monospace}
.mk-in{fill:#2E7A50} .mk-out{fill:#A6392E} .mkl{fill:#1B1F23;font-family:ui-monospace,Menlo,monospace;font-weight:bold}
.title{fill:#1B1F23;font-family:ui-monospace,Menlo,monospace;font-weight:bold} .badge-g{fill:#DEEBE2;stroke:#2E7A50}
.badge-r{fill:#F2DDD9;stroke:#A6392E} .bt-g{fill:#2E7A50} .bt-r{fill:#A6392E}
@media (prefers-color-scheme:dark){
 .cbg{fill:#1A1D20} .cgrid{stroke:#2A2D31} .up{fill:#5FB981;stroke:#5FB981} .dn{fill:#E2837A;stroke:#E2837A}
 .wu{stroke:#5FB981} .wd{stroke:#E2837A} .e1{stroke:#DFA054} .e2{stroke:#9EA2AD} .bb{stroke:#8B95E0}
 .lvl{stroke:#8B8880} .txt{fill:#E9E6DD} .txf{fill:#8B8880} .mk-in{fill:#5FB981} .mk-out{fill:#E2837A}
 .mkl{fill:#E9E6DD} .badge-g{fill:#1C2E23;stroke:#5FB981} .badge-r{fill:#35201E;stroke:#E2837A}
 .bt-g{fill:#5FB981} .bt-r{fill:#E2837A}}
</style>"""

def load(cache, sym):
    with open(os.path.join(DIR, cache), 'rb') as f:
        c = pickle.load(f)
    d = c[sym].copy().reset_index(drop=True)
    d['EMA50'] = d['close'].ewm(span=50, adjust=False).mean()
    d['EMA200'] = d['close'].ewm(span=200, adjust=False).mean()
    # RSI
    delta = d['close'].diff()
    g = delta.clip(lower=0).rolling(14).mean(); l = (-delta.clip(upper=0)).rolling(14).mean()
    d['RSI'] = 100 - 100/(1 + g/l)
    # Bollinger 20
    m = d['close'].rolling(20).mean(); s = d['close'].rolling(20).std()
    d['BBU'] = m + 2*s; d['BBL'] = m - 2*s
    return d

def candles_svg(d, i0, i1, title, sub, entrada=None, salida=None, emas=True,
                bollinger=False, badge=None, extras=None, W=720, H=380):
    """Dibuja velas [i0,i1) con marcadores. entrada/salida = (idx, label)."""
    sl = d.iloc[i0:i1].reset_index(drop=True)
    n = len(sl)
    padL, padR, padT, padB = 46, 14, 54, 46
    cw = (W - padL - padR) / n
    lo = sl['low'].min(); hi = sl['high'].max()
    if bollinger:
        lo = min(lo, sl['BBL'].min()); hi = max(hi, sl['BBU'].max())
    rng = (hi - lo) or 1
    def Y(p): return padT + (hi - p)/rng * (H - padT - padB)
    def X(k): return padL + k*cw + cw/2
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto;border:1px solid #d9d5c9;border-radius:8px">',
           STYLE, f'<rect class="cbg" x="0" y="0" width="{W}" height="{H}"/>',
           f'<text class="title" x="{W/2}" y="24" text-anchor="middle" font-size="15">{title}</text>',
           f'<text class="txf" x="{W/2}" y="42" text-anchor="middle" font-size="11">{sub}</text>']
    # grid horizontal (3 líneas de precio)
    for f in (0.0, 0.5, 1.0):
        p = lo + f*rng; y = Y(p)
        out.append(f'<line class="cgrid" x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}"/>')
        out.append(f'<text class="txf" x="6" y="{y+3:.1f}" font-size="9.5">{p:.4g}</text>')
    # bollinger
    if bollinger:
        for col, cls in (('BBU','bb'),('BBL','bb')):
            pts = " ".join(f"{X(k):.1f},{Y(sl[col].iloc[k]):.1f}" for k in range(n) if sl[col].iloc[k]==sl[col].iloc[k])
            out.append(f'<polyline class="{cls}" points="{pts}"/>')
    # velas
    bw = max(cw*0.62, 1.4)
    for k in range(n):
        o,h,l,c = sl['open'].iloc[k], sl['high'].iloc[k], sl['low'].iloc[k], sl['close'].iloc[k]
        up = c >= o; cls = 'up' if up else 'dn'; wc = 'wu' if up else 'wd'
        x = X(k)
        out.append(f'<line class="{wc}" x1="{x:.1f}" y1="{Y(h):.1f}" x2="{x:.1f}" y2="{Y(l):.1f}"/>')
        yb = Y(max(o,c)); hb = max(abs(Y(o)-Y(c)), 1.2)
        out.append(f'<rect class="{cls}" x="{x-bw/2:.1f}" y="{yb:.1f}" width="{bw:.1f}" height="{hb:.1f}"/>')
    # emas
    if emas:
        for col, cls in (('EMA50','e1'),('EMA200','e2')):
            pts = " ".join(f"{X(k):.1f},{Y(sl[col].iloc[k]):.1f}" for k in range(n) if sl[col].iloc[k]==sl[col].iloc[k])
            out.append(f'<polyline class="{cls}" points="{pts}"/>')
        out.append(f'<text class="e1txt txf" x="{W-padR-90}" y="{H-8}" font-size="9.5" fill="#C77D2E">— EMA50</text>')
        out.append(f'<text class="txf" x="{W-padR-40}" y="{H-8}" font-size="9.5">--- EMA200</text>')
    # marcadores
    def marca(ev, cls, tri_up):
        idx, lab = ev; k = idx - i0
        if k < 0 or k >= n: return
        x = X(k); y = Y(sl['low'].iloc[k]) + 16 if tri_up else Y(sl['high'].iloc[k]) - 16
        if tri_up:
            out.append(f'<polygon class="{cls}" points="{x:.1f},{y-9:.1f} {x-6:.1f},{y+2:.1f} {x+6:.1f},{y+2:.1f}"/>')
            out.append(f'<text class="mkl" x="{x:.1f}" y="{y+16:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
        else:
            out.append(f'<polygon class="{cls}" points="{x:.1f},{y+9:.1f} {x-6:.1f},{y-2:.1f} {x+6:.1f},{y-2:.1f}"/>')
            out.append(f'<text class="mkl" x="{x:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
    if entrada: marca(entrada, 'mk-in', True)
    if salida: marca(salida, 'mk-out', False)
    # marcadores extra: (idx, label, clase, tri_up)
    for ex in (extras or []):
        idx, lab, cls, up = ex
        k = idx - i0
        if k < 0 or k >= n: continue
        x = X(k); y = Y(sl['low'].iloc[k]) + 16 if up else Y(sl['high'].iloc[k]) - 16
        if up:
            out.append(f'<polygon class="{cls}" points="{x:.1f},{y-9:.1f} {x-6:.1f},{y+2:.1f} {x+6:.1f},{y+2:.1f}"/>')
            out.append(f'<text class="mkl" x="{x:.1f}" y="{y+16:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
        else:
            out.append(f'<polygon class="{cls}" points="{x:.1f},{y+9:.1f} {x-6:.1f},{y-2:.1f} {x+6:.1f},{y-2:.1f}"/>')
            out.append(f'<text class="mkl" x="{x:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
    if badge:
        bx = padL+6; out.append(f'<rect class="badge-{badge[1]}" x="{bx}" y="{padT+4}" width="{badge[2]}" height="22" rx="4"/>')
        out.append(f'<text class="bt-{badge[1]}" x="{bx+8}" y="{padT+19}" font-size="11" font-weight="bold">{badge[0]}</text>')
    out.append('</svg>')
    return "\n".join(out)

def cross_idx(d, golden=True, start=250):
    """Primer cruce EMA50/EMA200 (golden=alcista) desde start."""
    a, b = d['EMA50'].values, d['EMA200'].values
    for i in range(start, len(d)):
        if golden and a[i-1] <= b[i-1] and a[i] > b[i]: return i
        if not golden and a[i-1] >= b[i-1] and a[i] < b[i]: return i
    return None

def guardar(nombre, svg):
    with open(os.path.join(OUT, nombre), 'w') as f: f.write(svg)
    print(f"  {nombre}: {len(svg)} bytes")

# ---- V26: un trade real de tendencia (cruce dorado → flip) ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'ETHUSDT')
gi = cross_idx(d, True, 300)
di = cross_idx(d, False, gi+20) if gi else None
if gi and di:
    i0 = max(gi-25, 0); i1 = min(di+25, len(d))
    # recorte a ~120 velas máx para legibilidad
    if i1-i0 > 130: i1 = i0+130; di2 = di if di < i1 else None
    svg = candles_svg(d, i0, i1,
        "V26 — Estrategia base (cruce de tendencia 4h)",
        "ETHUSDT · entra cuando EMA50 cruza sobre EMA200 · sale cuando se invierte (flip)",
        entrada=(gi, "ENTRADA (cruce ↑)"), salida=(di if di<i1 else i1-1, "SALIDA (flip ↓)"),
        emas=True, badge=("Ganador dejado correr", "g", 168))
    guardar('v26_estrategia.svg', svg)

# ---- V36: 15m, misma lógica, más rápido ----
d15 = load('wf_cache_15m_140160_2026-06-11_top4.pkl', 'SOLUSDT')
gi = cross_idx(d15, True, 300)
di = cross_idx(d15, False, gi+20) if gi else None
if gi and di:
    i0 = max(gi-20, 0); i1 = min(di+20, len(d15))
    if i1-i0 > 130: i1 = i0+130
    svg = candles_svg(d15, i0, i1,
        "V36 — Misma estrategia, timeframe 15m",
        "SOLUSDT · cruce EMA50/200 en 15m · entra rápido, deja correr, sale por flip",
        entrada=(gi, "ENTRADA"), salida=(di if di<i1 else i1-1, "SALIDA (flip)"),
        emas=True, badge=("Tendencia rápida", "g", 130))
    guardar('v36_estrategia.svg', svg)

# ---- V17 RSI (espejismo): vender en RSI>70 mientras el precio sigue subiendo ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'SOLUSDT')
# buscar un tramo donde RSI cruza 70 y el precio SIGUE subiendo fuerte
best=None
for i in range(300, len(d)-40):
    if d['RSI'].iloc[i-1] < 70 <= d['RSI'].iloc[i]:
        fut = d['close'].iloc[i+30]/d['close'].iloc[i]-1
        if fut > 0.12 and (best is None or fut > best[1]): best=(i, fut)
if best:
    i0=max(best[0]-15,0); i1=min(best[0]+35,len(d))
    svg = candles_svg(d, i0, i1,
        "V17 — RSI Momentum (ESPEJISMO)",
        "Vender en RSI>70 asumiendo reversión — pero en una tendencia real el precio SIGUE",
        entrada=(best[0], "vende RSI>70 ✗"), emas=False,
        badge=("La señal falla: sigue subiendo", "r", 210))
    guardar('v17_rsi.svg', svg)

# ---- V18 Bollinger extremo (espejismo): romper banda no es reversión ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'BNBUSDT')
best=None
for i in range(300, len(d)-40):
    if d['close'].iloc[i-1] <= d['BBU'].iloc[i-1] and d['close'].iloc[i] > d['BBU'].iloc[i]:
        fut = d['close'].iloc[i+25]/d['close'].iloc[i]-1
        if fut > 0.10 and (best is None or fut > best[1]): best=(i, fut)
if best:
    i0=max(best[0]-15,0); i1=min(best[0]+30,len(d))
    svg = candles_svg(d, i0, i1,
        "V18 — Bollinger Extremo (ESPEJISMO)",
        "Apostar reversión al romper la banda — pero la ruptura suele ser el inicio de un régimen nuevo",
        entrada=(best[0], "vende ruptura ✗"), emas=False, bollinger=True,
        badge=("La ruptura CONTINÚA", "r", 168))
    guardar('v18_bollinger.svg', svg)

def linea_svg(serie, title, sub, bandas=None, marca_x=None, badge=None, W=720, H=340, ylab=""):
    """Gráfico de línea (para spread/z-score). serie = lista de valores.
    bandas = lista de (valor, etiqueta, clase). marca_x = (idx, label)."""
    n = len(serie); padL, padR, padT, padB = 46, 14, 54, 42
    vals = list(serie) + ([b[0] for b in (bandas or [])])
    lo, hi = min(vals), max(vals); rng = (hi-lo) or 1
    def Y(v): return padT + (hi-v)/rng*(H-padT-padB)
    def X(k): return padL + k/(n-1)*(W-padL-padR)
    out=[f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto;border:1px solid #d9d5c9;border-radius:8px">',
         STYLE, f'<rect class="cbg" x="0" y="0" width="{W}" height="{H}"/>',
         f'<text class="title" x="{W/2}" y="24" text-anchor="middle" font-size="15">{title}</text>',
         f'<text class="txf" x="{W/2}" y="42" text-anchor="middle" font-size="11">{sub}</text>']
    for b in (bandas or []):
        y=Y(b[0]); out.append(f'<line class="{b[2]}" x1="{padL}" y1="{y:.1f}" x2="{W-padR}" y2="{y:.1f}"/>')
        out.append(f'<text class="txf" x="{W-padR-4}" y="{y-3:.1f}" text-anchor="end" font-size="10">{b[1]}</text>')
    pts=" ".join(f"{X(k):.1f},{Y(serie[k]):.1f}" for k in range(n))
    out.append(f'<polyline points="{pts}" fill="none" stroke="#C77D2E" stroke-width="2.2"/>')
    if marca_x:
        k,lab=marca_x; x=X(k); out.append(f'<circle class="mk-out" cx="{x:.1f}" cy="{Y(serie[k]):.1f}" r="5"/>')
        out.append(f'<text class="mkl" x="{x:.1f}" y="{Y(serie[k])-12:.1f}" text-anchor="middle" font-size="10">{lab}</text>')
    if badge:
        out.append(f'<rect class="badge-{badge[1]}" x="{padL+6}" y="{padT+4}" width="{badge[2]}" height="22" rx="4"/>')
        out.append(f'<text class="bt-{badge[1]}" x="{padL+14}" y="{padT+19}" font-size="11" font-weight="bold">{badge[0]}</text>')
    out.append('</svg>'); return "\n".join(out)

# ---- V22 / cap9: salida estática tardía = GIVEBACK (pico → flip muy abajo) ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'XRPUSDT')
gi = cross_idx(d, True, 300); di = cross_idx(d, False, gi+30) if gi else None
if gi and di:
    i0=max(gi-20,0); i1=min(di+20,len(d))
    if i1-i0>130: i1=i0+130
    pk = i0 + int(d['high'].iloc[i0:i1].values.argmax())
    svg = candles_svg(d, i0, i1,
        "V22 — El riesgo de una salida tardía (giveback)",
        "XRPUSDT · el precio hace un pico enorme, pero la salida por flip confirma tarde y devuelve casi todo",
        entrada=(gi,"ENTRADA"), salida=(di if di<i1 else i1-1,"SALIDA tardía (flip)"),
        extras=[(pk,"PICO (no capturado)","mk-out",False)], emas=True,
        badge=("Devuelve la ganancia","r",158))
    guardar('v22_giveback.svg', svg)

# ---- P1 / cap22: cerrar y replicar = cortar antes de que la tendencia termine ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'BNBUSDT')
gi = cross_idx(d, True, 300); di = cross_idx(d, False, gi+30) if gi else None
if gi and di:
    i0=max(gi-15,0); i1=min(di+15,len(d))
    if i1-i0>120: i1=i0+120
    pk = i0 + int(d['high'].iloc[i0:i1].values.argmax())
    early = gi + max(int((pk-gi)*0.45), 3)   # cierre prematuro ~45% del camino al pico
    svg = candles_svg(d, i0, i1,
        "P1 — Cerrar y replicar (RECHAZADA)",
        "BNBUSDT · cerrar la posición temprano corta la ganancia ANTES de que la tendencia termine",
        entrada=(gi,"ENTRADA"), extras=[(early,"cierre P1 ✗","mk-out",False),(pk,"lo que seguía →","mk-in",False)],
        emas=True, badge=("Se pierde la continuación","r",184))
    guardar('p1_premature.svg', svg)

# ---- P2 / cap22: salir por sobre-extensión abandona la tendencia ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'SOLUSDT')
gi = cross_idx(d, True, 700); di = cross_idx(d, False, gi+30) if gi else None
if gi and di:
    i0=max(gi-15,0); i1=min(di+15,len(d))
    if i1-i0>120: i1=i0+120
    pk = i0 + int(d['high'].iloc[i0:i1].values.argmax())
    mid = gi + max(int((pk-gi)*0.4), 3)
    svg = candles_svg(d, i0, i1,
        "P2 — Salida por agotamiento (RECHAZADA)",
        "SOLUSDT · salir por 'sobre-extensión' abandona la tendencia que después sigue subiendo",
        entrada=(gi,"ENTRADA"), extras=[(mid,"sale por agotamiento ✗","mk-out",False),(pk,"la tendencia sigue →","mk-in",False)],
        emas=True, badge=("Abandona el trend","r",164))
    guardar('p2_exhaustion.svg', svg)

# ---- V45 / cap23: extremo de Bollinger = continuación, no reversión ----
d = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'ADAUSDT')
best=None
for i in range(300, len(d)-40):
    if d['close'].iloc[i-1] <= d['BBU'].iloc[i-1] and d['close'].iloc[i] > d['BBU'].iloc[i]:
        fut = d['close'].iloc[i+25]/d['close'].iloc[i]-1
        if fut>0.10 and (best is None or fut>best[1]): best=(i,fut)
if best:
    i0=max(best[0]-15,0); i1=min(best[0]+30,len(d))
    svg = candles_svg(d, i0, i1,
        "V45 — Reversión por extremo de Bollinger (RECHAZADA)",
        "ADAUSDT · apostar la reversión al romper la banda — pero el extremo marca CONTINUACIÓN",
        entrada=(best[0],"apuesta reversión ✗"), emas=False, bollinger=True,
        badge=("Continúa la tendencia","r",176))
    guardar('v45_reversion.svg', svg)

# ---- V47 / cap24: pairs — el spread cruza 2σ y DIVERGE (no revierte) ----
de = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'ETHUSDT')
db = load('wf_cache_4h_8760_2026-06-11_0000.pkl', 'BNBUSDT')
sp = np.log(de['close'].values) - np.log(db['close'].values)   # spread log
sser = pd.Series(sp)
z = (sser - sser.rolling(180).mean()) / sser.rolling(180).std()
z = z.dropna().values
# buscar un tramo donde z cruza +2 y sigue subiendo (diverge)
best=None
for i in range(1, len(z)-40):
    if z[i-1] < 2 <= z[i]:
        fut = z[i+30]-z[i]
        if fut>0.5 and (best is None or fut>best[1]): best=(i,fut)
if best:
    a=max(best[0]-40,0); b=min(best[0]+60,len(z))
    seg=list(z[a:b])
    svg = linea_svg(seg,
        "V47 — Pairs trading por cointegración (RECHAZADA)",
        "spread ETH–BNB (z-score) · entra al cruzar 2σ esperando reversión — pero DIVERGE",
        bandas=[(2,"entrada +2σ","lvl"),(0,"media","cgrid"),(-2,"−2σ","lvl")],
        marca_x=(best[0]-a,"cruza 2σ, sigue subiendo ✗"),
        badge=("El spread no revierte","r",176))
    guardar('v47_spread.svg', svg)

print("Listo. SVGs en", OUT)
