# La Mesa de Dinero — código del libro

Este repositorio acompaña el libro **"La Mesa de Dinero"**. Las carpetas están numeradas
en el **orden de lectura del libro** (ver `INDICE_REPO.md` para el mapa carpeta ↔ capítulo).

Cada carpeta trae un **`COMO_EJECUTAR.md`** con el comando exacto para probarla.

## Empezar
```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```
Los backtests de investigación descargan sus propios datos de Binance (o regeneran los
caches `.pkl` en la primera corrida). Los bots en vivo son **testnet/paper** — nunca uses
dinero real para probar.

## Nota
Los dos motores con edge real (V26 y V36) **no se publican** — la receta afinada y el
código de producción quedan en reserva. El libro los explica en detalle (Cap. 14–15).
