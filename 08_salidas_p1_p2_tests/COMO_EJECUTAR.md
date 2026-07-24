# Cómo ejecutar — `v26_salida_test`

Hipótesis P1/P2 y Test 1/2 de salida (Cap. 16, 22), validadas por Fable.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/v26_salida_test
python3 walkforward.py --continuo --interval 4h --entrada cruce --salida tendencia --mc 100
```

## Qué esperar
Corre el backtest honesto (walk-forward o `--continuo`) con null-vs-azar y OOB. Descarga sus propios datos o usa los caches `.pkl` de `stable_v25_prototype/`.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
