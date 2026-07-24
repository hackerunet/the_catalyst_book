# Cómo ejecutar — `v26_salida_comparativa`

La comparativa completa de salidas (Cap. 26) + el estudio de volumen (V73). Ninguna salida le gana al flip.

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd bot_alpha_portfolio/v26_salida_comparativa
python3 walkforward.py --continuo --interval 4h --entrada cruce --salida tendencia --mc 100
```

## Qué esperar
Corre el backtest honesto (walk-forward o `--continuo`) con null-vs-azar y OOB. Descarga sus propios datos o usa los caches `.pkl` de `stable_v25_prototype/`.

---
*Contexto completo de esta estrategia: ver el libro "The Catalyst".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
