# Cómo ejecutar — `laboratorio_gbm`

Laboratorio de motores nuevos con auditor independiente (Cap. 21-25).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd Fragua/laboratorio_gbm
python3 opciones_gbm_delta.py
```

## Qué esperar
Contiene: opciones_gbm_delta.py.

---
*Contexto completo de esta estrategia: ver el libro "The Catalyst".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
