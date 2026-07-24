# mainnet_ops — snapshots del estado de operaciones en MAINNET

Cada archivo `ops_<UTC>.log` es una foto COMPLETA del registro de trades de los
bots vivos (V26 + V36) en dinero real, bajada de la VM en ese instante. Sirve
para: (1) tener el historial en el proyecto (la fuente oficial es Binance, esto
es un espejo local), (2) reconstruir/analizar operaciones (buenas/malas
decisiones) como en la bitácora del Día 1, (3) diffear el estado entre fechas.

Se genera con el comando `!` que corre en la sesión del usuario (la única que
alcanza GCP). Ver el comando en el libro / el mensaje que lo entregó.
NO contiene credenciales — solo datos de trades (entrada/salida/PnL/símbolo).
