# Cómo ejecutar — `v36_exits`

Laboratorio de motores nuevos con auditor independiente (Cap. 21-25).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd Fragua/v36_exits
python3 backtest_completo.py
```

## Qué esperar
Contiene: backtest_completo.py, sweep_exits.py.

---
*Contexto completo de esta estrategia: ver el libro "The Catalyst".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
