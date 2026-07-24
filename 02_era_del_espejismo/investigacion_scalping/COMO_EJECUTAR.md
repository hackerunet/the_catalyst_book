# Cómo ejecutar — `investigacion_scalping`

Investigación de scalping de la era temprana.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/investigacion_scalping
python3 atr_percentil_continua_15m.py
```

## Qué esperar
Contiene: atr_percentil_continua_15m.py, pairs_cointegracion.py.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
