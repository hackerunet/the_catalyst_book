# Cómo ejecutar — `scripts`

Laboratorio de motores nuevos con auditor independiente (Cap. 21-25).

## Requisitos
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```


## Ejecutar
```bash
cd Fragua/scripts
python3 generar_graficos_libro.py
```

## Qué esperar
Contiene: generar_graficos_libro.py, generar_graficos_masivos.py, investigacion_delta_neutral.py, investigacion_gbm.py, update_book_final.py, update_html_book.py, update_html_book_massive.py.

---
*Contexto completo de esta estrategia: ver el libro "La Mesa de Dinero".
Los datos históricos (caches `.pkl`) que usan varios scripts viven en
`bot_alpha_portfolio/stable_v25_prototype/`.*
