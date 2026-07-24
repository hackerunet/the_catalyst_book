# Cómo ejecutar — `investigacion_econofisica`

La última frontera (Cap. 28) — econofísica. Bibliografía + 8 hipótesis (todas rechazadas) + la bitácora del forward test (`BITACORA_MAINNET.md`).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/investigacion_econofisica
python3 analisis_produccion_20260710.py
```

## Qué esperar
Contiene: analisis_produccion_20260710.py, diagnosticos_d1_d2.py.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
