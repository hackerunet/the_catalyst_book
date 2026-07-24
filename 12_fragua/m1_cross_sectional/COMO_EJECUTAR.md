# Cómo ejecutar — `m1_cross_sectional`

Laboratorio de motores nuevos con auditor independiente (Cap. 21-25).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd Fragua/m1_cross_sectional
python3 run_v44.py
```

## Qué esperar
Script(s) de investigación: run_v44.py, run_v45.py, run_v46.py. Cada uno reproduce un estudio del libro. Ver comentarios de cabecera.

---
*Contexto completo de esta estrategia: ver el libro "The Catalyst".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
