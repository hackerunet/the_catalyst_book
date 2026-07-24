# Cómo ejecutar — `v27b_carry`

V27-B — carry de funding delta-neutral (Cap. 23), análisis de datos públicos.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/v27b_carry
python3 analizar_funding.py
```

## Qué esperar
Script(s) de investigación: analizar_funding.py. Cada uno reproduce un estudio del libro. Ver comentarios de cabecera.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
