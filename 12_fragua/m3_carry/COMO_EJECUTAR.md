# Cómo ejecutar — `m3_carry`

Laboratorio de motores nuevos con auditor independiente (Cap. 21-25).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd Fragua/m3_carry
python3 run_v46.py
```

## Qué esperar
Script(s) de investigación: run_v46.py. Cada uno reproduce un estudio del libro. Ver comentarios de cabecera.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
