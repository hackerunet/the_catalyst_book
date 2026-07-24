```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   █████ █   █ █████     ████  ███  █████  ███  █     █   █  ████ █████   ║
║     █   █   █ █        █     █   █   █   █   █ █      █ █  █       █     ║
║     █   █████ ████     █     █████   █   █████ █       █    ███    █     ║
║     █   █   █ █        █     █   █   █   █   █ █       █       █   █     ║
║     █   █   █ █████     ████ █   █   █   █   █ █████   █   ████    █     ║
║                                                                          ║
║         · laboratorio de investigación de trading cuantitativo ·         ║
║                                                                          ║
║   ────────────────────────────────────────────────────────────────────   ║
║   » motor honesto: reloj global, intravela pesimista, costos reales      ║
║   » validación: null-vs-azar · out-of-basket · walk-forward              ║
║   » casi todo lo que probamos perdió — que es justo lo correcto          ║
║   » lectura autorizada · la receta de producción queda en reserva        ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

> ### The Catalyst
> **El código detrás del libro.** Una investigación honesta —con rigor cuantitativo real—
> sobre qué funciona y qué no en el trading algorítmico de criptomonedas.
>
> *— The Hitchhiker's Guide to the Trading Automation Galaxy*

---

## Qué es esto

Este repositorio acompaña al libro **"The Catalyst"**. No es un producto ni una promesa de
rentabilidad: es el **registro completo de la investigación** —cada hipótesis, cada motor, cada
estrategia probada y **su veredicto honesto** (la enorme mayoría, rechazadas).

El corazón es un **motor de backtest honesto** que se niega a engañarse: ordena las velas con un
reloj global, resuelve el intravela de forma pesimista, cobra todos los costos, y valida cada
señal contra el azar (null Monte-Carlo), fuera de su canasta de diseño (OOB) y con walk-forward.
Es la máquina que demolió las "proyecciones de fantasía" de la era temprana y encontró los pocos
edges reales que sí sobrevivieron.

Las carpetas están **numeradas en el orden de lectura del libro**.

## Empezar

```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas numpy requests python-dotenv websockets ta
```

Cada carpeta trae un **`COMO_EJECUTAR.md`** con el comando exacto para probarla. Los backtests
descargan sus propios datos de Binance (o regeneran los caches en la primera corrida). Los bots
en vivo son **testnet / paper** — nunca uses dinero real para probar.

## El mapa

Abrí **[`INDICE_REPO.md`](INDICE_REPO.md)** para el mapa completo carpeta ↔ capítulo. En resumen:

| # | Carpeta | Parte del libro |
|---|---|---|
| `01` | motor honesto y herramientas | Fundamentos — el motor y su harness |
| `02` | era del espejismo | Las proyecciones de fantasía |
| `03`–`07` | v21 · v22 · v23 · v24 · v28 | El punto de inflexión (tres puertas, motor honesto) |
| `08`–`11` | salidas · carry · diagnóstico | Las leyes del proyecto |
| `12`–`13` | Fragua · econofísica | La búsqueda de un segundo motor |
| `14`–`15` | sinapsis · v72 espejismo | Los motores nuevos y "la carrera del win rate" |
| `infra/` | deploy, monitoreo | Camino a producción |

## En reserva

Los dos motores con **edge real (V26 y V36) no se publican** — la receta afinada y el código de
producción quedan en reserva. El libro los explica en detalle (Cap. 14–15); el código no se comparte.
Lo que sí está acá es todo lo demás: el método, el motor honesto, y las decenas de hipótesis que
la máquina desenmascaró.

---

<p align="center"><em>Probamos. No aseveramos.</em></p>
