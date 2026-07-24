"""
patrones.py — Biblioteca de patrones de vela (módulo puro, sin I/O).

18 detectores: continuación, reversión, confirmación y doji (incertidumbre).
Cada detector evalúa la ÚLTIMA vela cerrada del dataframe (con contexto de las
previas) y retorna dicts {nombre, dir: 'LONG'|'SHORT'|None, tipo}.
tipo ∈ {'reversion', 'continuacion', 'confirmacion', 'incertidumbre'}.
"""

# Patrones cuya señal es la MECHA — el cuerpo es pequeño POR DEFINICIÓN, así
# que los filtros de convicción deben medir el rango total de la vela, no el
# cuerpo (ver estrategia.evaluar_entrada, añadido 2026-06-11).
PATRONES_DE_MECHA = frozenset({'Hammer', 'Hanging man', 'Shooting star', 'Inverted hammer'})


def _vela(df, i):
    r = df.iloc[i]
    rango = r['high'] - r['low']
    cuerpo = abs(r['close'] - r['open'])
    return {
        'o': r['open'], 'h': r['high'], 'l': r['low'], 'c': r['close'],
        'rango': rango if rango > 0 else 1e-12,
        'cuerpo': cuerpo,
        'verde': r['close'] > r['open'],
        'roja': r['close'] < r['open'],
        'sup': r['high'] - max(r['open'], r['close']),   # mecha superior
        'inf': min(r['open'], r['close']) - r['low'],    # mecha inferior
    }


def _contexto_bajista(df):
    """Venía cayendo (contexto para patrones de reversión alcista)."""
    return df['close'].iloc[-2] < df['close'].iloc[-4]


def _contexto_alcista(df):
    return df['close'].iloc[-2] > df['close'].iloc[-4]


def detectar_patrones(df):
    """Escanea la última vela cerrada con la biblioteca completa."""
    out = []
    if len(df) < 6:
        return out
    a = _vela(df, -1)   # actual
    p = _vela(df, -2)   # previa
    pp = _vela(df, -3)  # antepenúltima

    # --- DOJI (incertidumbre — VETO de entrada) ---
    if a['cuerpo'] <= a['rango'] * 0.1:
        out.append({'nombre': 'Doji', 'dir': None, 'tipo': 'incertidumbre'})

    # --- MARUBOZU (continuación/confirmación de impulso) ---
    if a['cuerpo'] >= a['rango'] * 0.8:
        if a['verde']:
            out.append({'nombre': 'Marubozu alcista', 'dir': 'LONG', 'tipo': 'continuacion'})
        elif a['roja']:
            out.append({'nombre': 'Marubozu bajista', 'dir': 'SHORT', 'tipo': 'continuacion'})

    # --- ENGULFING (reversión fuerte) ---
    a_top, a_bot = max(a['o'], a['c']), min(a['o'], a['c'])
    p_top, p_bot = max(p['o'], p['c']), min(p['o'], p['c'])
    if a['verde'] and p['roja'] and a_bot < p_bot and a_top > p_top:
        out.append({'nombre': 'Engulfing alcista', 'dir': 'LONG', 'tipo': 'reversion'})
    if a['roja'] and p['verde'] and a_bot < p_bot and a_top > p_top:
        out.append({'nombre': 'Engulfing bajista', 'dir': 'SHORT', 'tipo': 'reversion'})

    # --- HAMMER / HANGING MAN (mecha inferior 2x cuerpo) ---
    if a['inf'] >= a['cuerpo'] * 2 and a['sup'] <= a['cuerpo']:
        if _contexto_bajista(df):
            out.append({'nombre': 'Hammer', 'dir': 'LONG', 'tipo': 'reversion'})
        elif _contexto_alcista(df):
            out.append({'nombre': 'Hanging man', 'dir': 'SHORT', 'tipo': 'reversion'})

    # --- SHOOTING STAR / INVERTED HAMMER (mecha superior 2x cuerpo) ---
    if a['sup'] >= a['cuerpo'] * 2 and a['inf'] <= a['cuerpo']:
        if _contexto_alcista(df):
            out.append({'nombre': 'Shooting star', 'dir': 'SHORT', 'tipo': 'reversion'})
        elif _contexto_bajista(df):
            out.append({'nombre': 'Inverted hammer', 'dir': 'LONG', 'tipo': 'reversion'})

    # --- PIERCING LINE / DARK CLOUD COVER ---
    if a['verde'] and p['roja'] and a['o'] < p['c'] and a['c'] > (p['o'] + p['c']) / 2 and a['c'] < p['o']:
        out.append({'nombre': 'Piercing line', 'dir': 'LONG', 'tipo': 'reversion'})
    if a['roja'] and p['verde'] and a['o'] > p['c'] and a['c'] < (p['o'] + p['c']) / 2 and a['c'] > p['o']:
        out.append({'nombre': 'Dark cloud cover', 'dir': 'SHORT', 'tipo': 'reversion'})

    # --- MORNING STAR / EVENING STAR (3 velas) ---
    if (pp['roja'] and p['cuerpo'] <= p['rango'] * 0.3 and a['verde']
            and a['c'] > (pp['o'] + pp['c']) / 2):
        out.append({'nombre': 'Morning star', 'dir': 'LONG', 'tipo': 'reversion'})
    if (pp['verde'] and p['cuerpo'] <= p['rango'] * 0.3 and a['roja']
            and a['c'] < (pp['o'] + pp['c']) / 2):
        out.append({'nombre': 'Evening star', 'dir': 'SHORT', 'tipo': 'reversion'})

    # --- THREE WHITE SOLDIERS / THREE BLACK CROWS (continuación) ---
    if (a['verde'] and p['verde'] and pp['verde']
            and a['c'] > p['c'] > pp['c']
            and a['cuerpo'] >= a['rango'] * 0.5 and p['cuerpo'] >= p['rango'] * 0.5):
        out.append({'nombre': 'Three white soldiers', 'dir': 'LONG', 'tipo': 'continuacion'})
    if (a['roja'] and p['roja'] and pp['roja']
            and a['c'] < p['c'] < pp['c']
            and a['cuerpo'] >= a['rango'] * 0.5 and p['cuerpo'] >= p['rango'] * 0.5):
        out.append({'nombre': 'Three black crows', 'dir': 'SHORT', 'tipo': 'continuacion'})

    # --- HARAMI (confirmación suave de giro) ---
    if p['roja'] and a['verde'] and a_top < p_top and a_bot > p_bot:
        out.append({'nombre': 'Harami alcista', 'dir': 'LONG', 'tipo': 'confirmacion'})
    if p['verde'] and a['roja'] and a_top < p_top and a_bot > p_bot:
        out.append({'nombre': 'Harami bajista', 'dir': 'SHORT', 'tipo': 'confirmacion'})

    # --- TWEEZER TOP / BOTTOM ---
    tol = a['rango'] * 0.1
    if abs(a['l'] - p['l']) <= tol and p['roja'] and a['verde'] and _contexto_bajista(df):
        out.append({'nombre': 'Tweezer bottom', 'dir': 'LONG', 'tipo': 'confirmacion'})
    if abs(a['h'] - p['h']) <= tol and p['verde'] and a['roja'] and _contexto_alcista(df):
        out.append({'nombre': 'Tweezer top', 'dir': 'SHORT', 'tipo': 'confirmacion'})

    return out
