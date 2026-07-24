# BIBLIOGRAFÍA ANOTADA — Econofísica aplicada al trading de cripto (Fase 1)

> Investigación 2026-07-09/10 (V60+). **Regla de honestidad**: nada se cita sin fuente
> localizada; el nivel de verificación de cada entrada está marcado:
> `[WF]` = enlace abierto y verificado con WebFetch · `[BUSQ]` = localizado vía buscador
> (título/autores/venue confirmados por el índice de búsqueda, enlace no abierto).
> Las URLs pueden mover; el identificador estable es el DOI/arXiv ID.

---

## A. Fundacionales del campo

**A1. Mantegna, R.N. & Stanley, H.E. (2000).** *An Introduction to Econophysics: Correlations and Complexity in Finance.* Cambridge University Press. `[BUSQ]`
- Enlace: https://assets.cambridge.org/97805216/20086/frontmatter/9780521620086_frontmatter.pdf (frontmatter oficial de Cambridge) · reseña crítica: https://bactra.org/reviews/intro-to-econophysics/
- Primera monografía del campo en inglés. Scaling, correlaciones de corto/largo alcance, auto-similitud aplicados a series financieras. Ambos autores físicos estadísticos de primer nivel (Stanley: Boston University).
- **Predicción testeable que ofrece**: los retornos NO son gaussianos y muestran scaling — base de D1/D2 (diagnósticos).

**A2. Mandelbrot, B. (1963).** *The Variation of Certain Speculative Prices.* The Journal of Business, 36(4), 394-419. `[BUSQ]`
- Enlace (PDF cortesía académica): https://web.williams.edu/Mathematics/sjmiller/public_html/341Fa09/econ/Mandelbroit_VariationCertainSpeculativePrices.pdf · RePEc: https://ideas.repec.org/a/ucp/jnlbus/v36y1963p394.html
- El origen de todo: colas gordas en precios de algodón, distribución Lévy-estable en vez de gaussiana. 60+ años después sigue siendo el hecho empírico central.
- **Testeable**: distribución de retornos leptocúrtica (D1).

**A3. Bouchaud, J.-P. & Potters, M. (2003).** *Theory of Financial Risk and Derivative Pricing: From Statistical Physics to Risk Management* (2ª ed.). Cambridge University Press. `[BUSQ]`
- Enlace: https://www.cambridge.org/core/books/theory-of-financial-risk-and-derivative-pricing/5BBBA04CE72ED9E5E7C1C028D9A94FCB
- El puente riguroso física estadística → gestión de riesgo. Colas, correlaciones, RMT, pricing sin gaussianas.
- **Testeable**: el riesgo de cola real excede el gaussiano (valida nuestro sizing por stop, no por varianza).

**A4. Cont, R. (2001).** *Empirical properties of asset returns: stylized facts and statistical issues.* Quantitative Finance, 1(2), 223-236. `[BUSQ]`
- Enlace: https://iopscience.iop.org/article/10.1088/1469-7688/1/2/304
- EL catálogo canónico de los "stylized facts": colas gordas, clustering de volatilidad, ausencia de autocorrelación lineal, agregación gaussiana, efecto apalancamiento.
- **Testeable**: D2 verifica estos hechos en NUESTROS datos de cripto (15m/1h/4h/1d).

**A5. Gopikrishnan, P., Plerou, V., Amaral, L.A.N., Meyer, M. & Stanley, H.E. (1999).** *Scaling of the distributions of fluctuations of financial market indices.* Physical Review E, 60, 5305. `[BUSQ]`
- arXiv precursor: https://arxiv.org/pdf/cond-mat/9803374 (Inverse Cubic Law)
- La "ley cúbica inversa": P(|r|>x) ~ x^−3 — fuera del régimen Lévy (α<2) pero muy lejos de la gaussiana. Universal entre mercados.
- **Testeable**: D1 ajusta el exponente de cola de nuestras criptos con el método correcto (A6).

**A6. Clauset, A., Shalizi, C.R. & Newman, M.E.J. (2009).** *Power-law distributions in empirical data.* SIAM Review, 51(4), 661-703. DOI: 10.1137/070710111 · arXiv: 0706.1062. `[BUSQ]`
- Enlaces: https://aaronclauset.github.io/powerlaws/ (código del autor) · PDF: https://www.cs.cornell.edu/courses/cs6241/2019sp/readings/Clauset-2009-power-laws.pdf
- EL método estándar para ajustar leyes de potencia (MLE + Kolmogorov-Smirnov), demoliendo el error clásico de la regresión log-log visual.
- **Metodológico**: D1 usa este método, no el atajo.

## B. Burbujas y criticalidad (Sornette)

**B1. Sornette, D. (2003).** *Why Stock Markets Crash: Critical Events in Complex Financial Systems.* Princeton University Press. `[BUSQ]`
- Enlace: https://academic.oup.com/princeton-scholarship-online/book/14240 · reseña crítica: https://eh.net/book_reviews/why-stock-markets-crash-critical-events-in-complex-financial-systems/
- La teoría completa: burbuja = crecimiento súper-exponencial con oscilaciones log-periódicas hacia una singularidad de tiempo finito (t_c). Sornette dirige el Financial Crisis Observatory en ETH Zürich (fuente universitaria).
- **Caveat honesto de la propia reseña**: en tests retrospectivos, el modelo "predice" 1929/1987 solo después de ocurridos — la calibración prospectiva es lo difícil. Esto va DIRECTO al pre-registro de V62.

**B2. Filimonov, V. & Sornette, D. (2013).** *A stable and robust calibration scheme of the log-periodic power law model.* Physica A, 392(17), 3698-3707. arXiv: 1108.0099. `[WF ✓]`
- Enlace verificado: https://arxiv.org/abs/1108.0099
- Reduce el LPPL a 3 parámetros no lineales → calibración estable sin metaheurísticas. ES la receta canónica para implementar V62.
- **Testeable**: indicador de confianza LPPLS como gate direccional.

**B3. Gerlach, J.-C., Demos, G. & Sornette, D. (2019).** *Dissection of Bitcoin's multiscale bubble history from January 2012 to February 2018.* Royal Society Open Science, 6(7), 180643. DOI: 10.1098/rsos.180643 · arXiv: 1804.06261. `[BUSQ]`
- Enlace: https://royalsocietypublishing.org/rsos/article/6/7/180643/95246/
- Aplica LPPLS a Bitcoin: 3 burbujas largas + 10 picos menores identificados con drawup/drawdown automático. Peer-reviewed en Royal Society — el precedente directo cripto para V62.

## C. Multifractalidad

**C1. Kantelhardt, J.W., Zschiegner, S.A., Koscielny-Bunde, E., Havlin, S., Bunde, A. & Stanley, H.E. (2002).** *Multifractal detrended fluctuation analysis of nonstationary time series.* Physica A, 316(1-4), 87-114. arXiv: physics/0202070. `[BUSQ]`
- Enlace: https://oamonitor.ireland.openaire.eu/national/search/publication?pid=10.1016%2Fs0378-4371%2802%2901383-3
- EL método MF-DFA: generaliza DFA a espectro multifractal completo. Receta canónica para V61 (parámetros del paper: q ∈ [−5,5], escalas, detrending polinómico).

**C2. Grupo Drożdż/Kwapień/Wątorek (Cracovia, Instituto de Física Nuclear PAN).** Serie de papers sobre multifractalidad del mercado cripto. `[BUSQ]`
- *Multifractal cross-correlations of bitcoin and ether trading characteristics in the post-COVID-19 time* — arXiv: 2208.01445 (https://arxiv.org/pdf/2208.01445)
- *What is mature and what is still emerging in the cryptocurrency market?* — arXiv: 2305.05751
- *Multiscale characteristics of the emerging global cryptocurrency market* — arXiv: 2010.15403
- Hallazgo central del grupo: BTC/ETH desarrollaron multifractalidad genuina y se "maduraron" hacia características de mercados establecidos.
- **Testeable**: la anchura del espectro multifractal varía por régimen → V61.

**C3. Takaishi, T. (2018).** *Statistical properties and multifractality of Bitcoin.* Physica A, 506, 507-519. `[BUSQ]`
- Localizado vía las referencias de C2; multifractalidad de BTC confirmada con MF-DFA. Refuerzo independiente (Hiroshima University of Economics) para V61.

## D. Entropía y eficiencia de mercado

**D1. Bandt, C. & Pompe, B. (2002).** *Permutation entropy: a natural complexity measure for time series.* Physical Review Letters, 88, 174102. DOI: 10.1103/PhysRevLett.88.174102. `[BUSQ]`
- Enlace: https://www.semanticscholar.org/paper/b1ab25353d16bf639b1b53768374ee79065b5011 (4.000+ citas)
- Complejidad por patrones ordinales: robusta al ruido, sin supuestos de distribución, barata de computar. Parámetros canónicos: dimensión de embedding m=3..7, τ=1.
- **Receta para V60**: entropía de permutación normalizada en ventana rodante.

**D2. Sigaki, H.Y.D., Perc, M. & Ribeiro, H.V. (2019).** *Clustering patterns in efficiency and the coming-of-age of the cryptocurrency market.* Scientific Reports, 9, 1440. `[BUSQ]`
- Enlaces: https://www.nature.com/articles/s41598-018-37773-3 · arXiv: 1901.04967
- Aplica EXACTAMENTE la idea de V60: entropía de permutación + complejidad estadística en ventanas rodantes para medir eficiencia dinámica de 437 criptos. 37% eficientes >80% del tiempo; la eficiencia NO correlaciona con el market cap.
- **El precedente directo de V60** — publicado en Nature Scientific Reports.

**D3. Sensoy, A. (2019).** *The inefficiency of Bitcoin revisited: A high-frequency analysis with alternative currencies.* Finance Research Letters, 28, 68-73. `[BUSQ]`
- Enlace: https://ideas.repec.org/a/eee/finlet/v28y2019icp68-73.html
- BTCUSD/BTCEUR más eficientes intradía desde 2016; la volatilidad REDUCE la eficiencia informacional. Relevante para V60: la ineficiencia es variable en el tiempo (eso es lo que un gate explota).

## E. Flujo de información / lead-lag

**E1. Schreiber, T. (2000).** *Measuring information transfer.* Physical Review Letters, 85(2), 461-464. DOI: 10.1103/PhysRevLett.85.461. `[BUSQ]`
- Enlace: https://ui.adsabs.harvard.edu/abs/2000PhRvL..85..461S/abstract (4.400+ citas)
- Define transfer entropy: información direccional excluyendo la historia común — supera la causalidad de Granger para dependencias no lineales. Receta canónica para V63.

**E2. Dimpfl, T. & Peter, F.J. (2019).** *Group transfer entropy with an application to cryptocurrencies.* Physica A, 516, 543-551. `[BUSQ]`
- Enlace: https://www.sciencedirect.com/science/article/abs/pii/S0378437118313967 (base: Dimpfl & Peter 2013, Studies in Nonlinear Dynamics & Econometrics)
- **PRIOR HONESTO CLAVE para V63**: con group transfer entropy, Bitcoin NO es la cripto dominante que lidera el proceso de información. La hipótesis "BTC lidera, las alts siguen" podría estar invertida o ser inestable — el pre-registro de V63 debe ser bidireccional (medir TE en ambos sentidos), no asumir la dirección.

**E3. García-Medina, A. & colaboradores (2022).** *Using transfer entropy to measure information flows between cryptocurrencies.* Physica A, 586, 126484. `[BUSQ]`
- Enlace: https://ideas.repec.org/a/eee/phsmap/v586y2022ics0378437121007573.html
- TE aplicada al basket cripto moderno; refuerza que los flujos existen y cambian de dirección con el régimen (pandemia).

## F. Réplicas post-crash (ley de Omori)

**F1. Lillo, F. & Mantegna, R.N. (2003).** *Power-law relaxation in a complex system: Omori law after a financial market crash.* Physical Review E, 68, 016119. arXiv: cond-mat/0111257. `[WF ✓]`
- Enlace verificado: https://arxiv.org/abs/cond-mat/0111257 · publisher: https://journals.aps.org/pre/abstract/10.1103/PhysRevE.68.016119
- Tras un crash, la frecuencia de eventos |r|>umbral decae como ley de potencia (Omori, como terremotos): las "réplicas" financieras son reales y medibles.
- **Receta para V64**: ventana de réplicas post-shock como gate de entrada.

## G. Correlaciones y matrices aleatorias (RMT)

**G1. Laloux, L., Cizeau, P., Bouchaud, J.-P. & Potters, M. (1999).** *Noise dressing of financial correlation matrices.* Physical Review Letters, 83, 1467-1470. `[BUSQ]`
- Enlace: https://ui.adsabs.harvard.edu/abs/1999PhRvL..83.1467L/abstract
- La mayoría de los autovalores de una matriz de correlación financiera son indistinguibles de ruido (Marchenko-Pastur); los desviados (el "modo mercado") son la señal real.
- **Receta para V65** + caveat pre-declarado: con N=6-12 símbolos el espectro es pobre; el paper trabaja con N~400. Nuestra versión solo puede usar el autovalor máximo (modo mercado), no la estructura fina.

**G2. (Contexto cripto reciente)** *Detrended cross-correlations and their random matrix limit: an example from the cryptocurrency market* (2025). arXiv: 2512.06473 · Entropy 27(12), 1236, DOI: 10.3390/e27121236. `[BUSQ]`
- RMT aplicado específicamente a cripto por el grupo de Cracovia — precedente directo de que el enfoque se usa en nuestro universo de activos.

## H. Modelos de agentes / herding (contexto teórico)

**H1. Lux, T. & Marchesi, M. (1999).** *Scaling and criticality in a stochastic multi-agent model of a financial market.* Nature, 397, 498-500. DOI: 10.1038/17290. `[BUSQ]`
- Enlace: https://www.nature.com/articles/17290
- Agentes fundamentalistas/chartistas que cambian de bando reproducen los stylized facts. Explica POR QUÉ existen colas gordas y clustering sin necesitar noticias.
- **No testeable directamente** (modelo generativo) — contexto para el manual + motiva V66.

**H2. Cont, R. & Bouchaud, J.-P. (2000).** *Herd behavior and aggregate fluctuations in financial markets.* Macroeconomic Dynamics, 4(2), 170-196. `[BUSQ]`
- Enlaces: https://www.cambridge.org/core/journals/macroeconomic-dynamics/article/abs/51990E3780C6EBDA07A1753FC08E8453 · SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=58468
- Percolación: grupos de agentes imitándose → colas gordas exponencialmente truncadas. La imitación (herding) ES el mecanismo físico detrás del co-movimiento.
- **Traducción testeable → V66**: dispersión cross-sectional baja = manada operando junta.

## I. La crítica al campo (balance intelectual)

**I1. Gallegati, M., Keen, S., Lux, T. & Ormerod, P. (2006).** *Worrying trends in econophysics.* Physica A, 370(1), 1-6. `[BUSQ]`
- Enlaces: https://econpapers.repec.org/RePEc:eee:phsmap:v:370:y:2006:i:1:p:1-6 · respuesta de McCauley: https://arxiv.org/pdf/physics/0606002 · retrospectiva 10 años: https://d-nb.info/1125269812/34
- Cuatro críticas: ignorancia de la literatura económica, estadística poco rigurosa, universalidad asumida sin evidencia, y modelos sin mecanismo. **Firmada por dos econofísicos de primer nivel (Lux entre ellos)** — no es un ataque externo, es autocrítica del campo.
- **Para el manual y para nosotros**: nuestro estándar (pre-registro, null, OOB) responde exactamente a la crítica #2. Citarla nos protege de repetir los errores que el propio campo reconoce.

## J. "Quantum finance" — el tratamiento honesto

**J1. Baaquie, B.E. (2004).** *Quantum Finance: Path Integrals and Hamiltonians for Options and Interest Rates.* Cambridge University Press. ISBN 9780521840453. `[BUSQ]`
- Enlace: https://archive.org/details/liangzijinrongyi0000unse · AbeBooks/Amazon confirman edición
- Lo que la "física cuántica en finanzas" ES de verdad: formalismo matemático (path integrals, hamiltonianos) para VALUAR DERIVADOS — una técnica de cálculo, NO una señal de trading ni una afirmación de que el mercado "es cuántico".
- **No testeable como señal** — al manual: separa el uso legítimo del formalismo del humo retail ("trading cuántico").

**J2. NIST (agosto 2024).** *Post-Quantum Cryptography Standards* — FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA). `[BUSQ]`
- Enlaces: https://www.nist.gov/news-events/news/2024/08/nist-releases-first-3-finalized-post-quantum-encryption-standards · https://csrc.nist.gov/projects/post-quantum-cryptography · draft de transición: https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.IR.8547.ipd.pdf
- La amenaza real de Shor a ECDSA/Bitcoin y la respuesta (criptografía de retícula). Análisis técnico específico de Bitcoin: https://eprint.iacr.org/2021/967.pdf (IACR).
- **Sidebar del manual**: riesgo de SEGURIDAD de la cadena, no señal de trading. La parte verdadera del texto divulgativo.

## K. Universidades e institutos (anclas académicas del capítulo)

**K1. ETH Zürich — Financial Crisis Observatory** (cátedra de Didier Sornette): predicciones de burbujas en tiempo real con LPPLS. (Ver B1-B3.)
**K2. Boston University — grupo de H. Eugene Stanley**: origen del término "econofísica" (Stanley lo acuñó en 1995, Kolkata). (Ver A1, A5, C1.)
**K3. Oxford — Institute for New Economic Thinking (INET), Complexity Economics**: J. Doyne Farmer, físico (ex-Santa Fe Institute, ex-Prediction Company). `[BUSQ]`
- Enlaces: https://www.inet.ox.ac.uk/people/j-doyne-farmer · https://www.inet.ox.ac.uk/research/programmes/complexity-economics · https://www.santafe.edu/news-center/news/farmer-to-oxford
- La rama "complexity economics": agentes, redes, ecología de mercado. Farmer es el precedente de físicos que SÍ tradearon con esto (Prediction Company, años 90).
**K4. Santa Fe Institute**: cuna interdisciplinaria del enfoque de complejidad. https://santafe.edu/people/profile/j-doyne-farmer

## L. Crowding / reflexividad (traducción del "efecto observador") — literatura gris

**L1. Nota de honestidad**: la búsqueda de estudios ACADÉMICOS peer-reviewed sobre "funding rate extremo como señal contraria" devolvió principalmente literatura de industria/exchanges (Phemex, Altrady, CryptoRank, AInvest) con claims de exactitud no verificables (p.ej. "70-85% accuracy" sin paper citable). `[BUSQ]`
- Enlaces representativos (industria, NO academia): https://phemex.com/academy/what-is-funding-rate-in-crypto-futures · https://www.altrady.com/blog/crypto-trading-strategies/crypto-funding-rates-explained
- **Implicación para V67**: la hipótesis se apoya en el MECANISMO (posicionamiento apalancado extremo = combustible de squeeze — reflexividad clásica, Soros) y en NUESTROS datos de funding reales ya cacheados (V27-B/M3), no en una literatura académica sólida. Se pre-registra con esa etiqueta de honestidad: "mecanismo plausible + literatura gris", el estándar de evidencia más bajo de la tanda.

---

# Tabla de cierre — teoría → predicción testeable → hipótesis

| Teoría (fuente) | Predicción testeable | Hipótesis | Estado |
|---|---|---|---|
| Eficiencia variable medida con entropía de permutación (D1, D2, D3) | Ventanas "eficientes" (alta entropía) = sin señal explotable → chop | **V60** — gate de entrada por entropía | A pre-registrar |
| Multifractalidad por régimen (C1, C2, C3) | Espectro ancho ↔ estructura de tendencia; angosto ↔ ruido | **V61** — gate por anchura multifractal | A pre-registrar |
| Burbujas LPPLS (B1, B2, B3) | Burbuja madura → probabilidad elevada de cambio de régimen | **V62** — gate direccional LPPLS | A pre-registrar (con el caveat de B1) |
| Transfer entropy (E1, E2, E3) | Flujo de información direccional medible entre criptos | **V63** — señal lead-lag (BIDIRECCIONAL, prior de E2) | A pre-registrar |
| Ley de Omori (F1) | Réplicas post-shock siguen ley de potencia → periodo hostil para entradas | **V64** — gate post-shock | A pre-registrar |
| RMT modo-mercado (G1, G2) | Acoplamiento sistémico alto = una sola apuesta direccional | **V65** — gate/telemetría de acoplamiento | A pre-registrar (caveat N chico) |
| Herding/percolación (H1, H2) | Dispersión cross-sectional baja = manada | **V66** — filtro de dispersión | A pre-registrar |
| Reflexividad/crowding (L1 + mecanismo) | Funding extremo = posicionamiento crowded = riesgo de squeeze | **V67** — gate/señal contraria por funding | A pre-registrar (evidencia más débil de la tanda) |
| Colas de potencia (A2, A5, A6) | α ≈ 3 en cripto (¿o más pesadas?) | **D1** — diagnóstico info-only | A correr |
| Stylized facts (A4) | Clustering de vol., no-gaussianidad, sin autocorr. lineal | **D2** — diagnóstico info-only | A correr |
| Heisenberg / observador / entrelazamiento (texto fuente) | — (sin predicción falsable como física) | — | Al manual como desmontaje (ver TRIAGE.md) |
| Computación cuántica vs blockchain (J2) | — (seguridad, no trading) | — | Sidebar del manual |

**Priors honestos de la tanda** (de la propia literatura + historial del proyecto):
1. E2 invierte la dirección asumida de V63 → el pre-registro DEBE ser bidireccional.
2. B1 (reseña): LPPLS es célebre por "predecir" hacia atrás — V62 se evalúa solo con calibración causal (sin mirar el futuro), ventana por ventana.
3. El proyecto ya rechazó 12+ filtros de entrada; el prior general es rechazo. El valor garantizado es el capítulo del manual; un pase sería bonus.
