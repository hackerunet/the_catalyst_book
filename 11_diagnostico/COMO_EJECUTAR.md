# Cómo ejecutar — `diagnostico`

Herramienta read-only que reproduce la decisión viva de cada bot.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/diagnostico
python3 ab_entrada_rapida.py
```

## Qué esperar
Contiene: ab_entrada_rapida.py, diagnostico_mercado.py, mejora_v28.py, prueba_clases.py, validar_c4.py.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
