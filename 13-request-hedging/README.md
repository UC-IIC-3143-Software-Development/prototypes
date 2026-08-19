# Request hedging

## Que demuestra

Que **el promedio miente y la cola es el problema**. El servicio de este demo esta
sano: el 50% de los requests contesta en **26 ms**. El mismo servicio, medido en
el percentil 99, contesta en **487 ms**: casi **19x peor**. Nadie lo nota mirando
el promedio, y sin embargo hay usuarios reales esperando medio segundo por un
lookup que "tarda 26 ms".

La tecnica que ataca eso es *request hedging* ("The Tail at Scale", Dean y
Barroso, CACM 2013): si a los X ms la replica no contesto, se manda una **copia
del request a otra replica** y se usa la primera respuesta que llegue. Calibrando
X en el **p95 medido** (80 ms aca), el p99 pasa de **487 ms a 110 ms** (4.4x
mejor) y el backend hace apenas **+4.7% de trabajo**, porque solo se duplica el
4.7% de los requests: justo el 4.7% que estaba por caer en la cola larga. La cola
de requests por encima de 200 ms baja de **47 a 1** sobre 2500. El p50 no se mueve
ni un milisegundo: el 95% de los requests nunca llega al umbral.

## La matematica que hace que esto importe

Con fan-out 1, el p99 le arruina el dia al 1% de los usuarios. Pero a escala los
requests se abren en abanico: una pantalla de busqueda consulta 100 shards en
paralelo y **no puede contestar hasta que vuelve el ultimo**. Si cada shard tiene
1% de chance de caer en su cola larga, la probabilidad de que *ninguno* de los 100
se pase es:

```
0.99 ^ 100 = 0.366        ->  1 - 0.366 = 63.4%
```

**El 63% de los requests de usuario pega en la cola.** El p99 de las partes se
convirtio en el caso *tipico* del todo. Ese es el numero que da vuelta la
intuicion: "1% es poquito" es verdad para un componente y es falso para el
sistema.

Corolario de diseno: a escala, bajar el promedio de los componentes casi no mueve
la aguja, y una tecnica que solo toca al 5% mas lento vale muchisimo. La cola no
es un detalle de medicion, es el comportamiento que ve el usuario.

## Como correrlo

Dos terminales, sin Docker y sin base de datos.

```bash
# terminal 1: el servicio mock (queda escuchando en 127.0.0.1:5003)
cd 13-request-hedging
python3 backend.py
```

```bash
# terminal 2: el experimento
cd 13-request-hedging
python3 hedging.py
```

Tarda **~90 s** (medido: 92 / 93 s) e imprime todo al final: la
cabecera con el modelo, la tabla de los 7 escenarios y el histograma. Si la
maquina esta ocupada con otra cosa pesada, los escenarios saturados se estiran
(una corrida con el equipo cargado tardo 320 s); los numeros de las filas 1-4
igual quedan iguales.

El backend se puede dejar levantado entre corridas: cada escenario le postea su
capacidad y le pone los contadores en cero antes de empezar. Si `hedging.py`
arranca y no encuentra a nadie en el 5003, lo dice y se va.

Si `backend.py` corta con `OSError: [Errno 48] Address already in use`, quedo un
backend de una corrida anterior escuchando en el 5003:

```bash
lsof -ti tcp:5003 | xargs kill
```

## Los numeros

Medido en un MacBook Pro (Apple M2 Max, 12 cores, macOS 15.7) con Python 3.11.7.
Los milisegundos dependen de la maquina; los **ratios** y las columnas del
backend, no. Esta es la corrida 3 tal cual sale por pantalla:

```
umbral de hedge = p95 MEDIDO en el escenario 1 = 80 ms (no esta hardcodeado)
=============================================================================================
                                latencia que ve el CLIENTE (ms) | trabajo del BACKEND (requests)
ESCENARIO                        p50   p95    p99  p99.9    max |   total extra  hedge   gano
---------------------------------------------------------------------------------------------
1  sin hedging (baseline)         26    80    487   1052   1080 |    2500   +0%   0.0%   0.0%
2  hedge @ p95 (80 ms)            26    80    110    182    680 |    2617   +5%   4.7%   2.6%
3  hedge @ p50 (26 ms)            26    57     73    150    678 |    3557  +42%  42.3%  12.5%
4  hedge @ 0 ms (duplicar)        24    48     66    128    684 |    5000 +100% 100.0%  47.0%
---------------------------------------------------------------------------------------------
5  SATURADO sin hedging          165   689   1112   1341   1502 |    2500   +0%   0.0%   0.0%
6  SATURADO hedge @ 80 ms        394   920   1424   1753   1814 |    4933  +97%  97.3%  41.8%
7  SATURADO hedge + budget 5%    173   758   1257   1558   2149 |    2625   +5%   5.0%   3.1%
=============================================================================================
```

La columna `extra` esta redondeada a entero: el `+5%` de la fila 2 es `2617/2500`,
o sea +4.7%, y segun la corrida se ve `+4%` o `+5%`.

Los 7 escenarios mandan **los mismos 2500 requests de cliente**: la demanda no
cambia nunca, lo unico que cambia es que hace el cliente con ella y cuanta
capacidad tiene el backend. `total` no se infiere: se lee de `GET /stats`, un
contador que el backend incrementa cuando **termina** de ejecutar el request,
incluidas las copias que el cliente ya descarto.

Las tres corridas seguidas, para ver que esto se reproduce:

| | corrida 1 | corrida 2 | corrida 3 |
|---|---|---|---|
| Umbral auto-calculado (p95 del esc. 1) | 80 ms | 80 ms | 80 ms |
| p99 sin hedging | 493 ms | 490 ms | 487 ms |
| p99 con hedge @p95 | 112 ms | 112 ms | 110 ms |
| **Mejora del p99** | **4.40x** | **4.38x** | **4.43x** |
| Trabajo extra del backend | +4.5% | +4.7% | +4.7% |
| Requests hedgeados | 4.5% | 4.7% | 4.7% |
| Cola > 200 ms (de 2500) | 47 -> 1 | 46 -> 1 | 47 -> 1 |

Como el umbral se mide en cada corrida, cae en **80 u 81 ms** segun el dia; todo
lo demas de las filas 1-4 se mueve uno o dos milisegundos y nada mas.

El umbral **no esta hardcodeado**: el escenario 1 mide su propio p95 y los
escenarios 2, 6 y 7 usan ese valor. Es exactamente lo que hace Cassandra con
`speculative_retry = 99PERCENTILE`.

Que fila mirar:

- **Fila 1 vs 2** es la tesis entera. `p50 26 -> 26` (el caso comun no se toca),
  `p99 487 -> 110`, `total 2500 -> 2617`. Cuatro veces mejor la cola por menos de
  5% de trabajo.
- **La columna `gano`** es la honestidad del demo: de ese 4.7% hedgeado, la copia
  llego primero solo en el 2.6%. **El otro 45% de los hedges fue trabajo tirado a
  la basura** — el backend lo ejecuto entero para nadie.
- **La raya del medio** separa backend sano de backend roto. Todo lo que pasa
  abajo pasa con el mismo codigo de cliente y el mismo umbral.

El histograma que imprime abajo de la tabla dice lo mismo sin percentiles:

```
      0-25 ms | 1183    ->  1189
     25-50 ms |  942    ->   940
    50-100 ms |  300    ->   318
   100-200 ms |   28    ->    52
   200-400 ms |   15    ->     0
   400-800 ms |   23    ->     1
      >800 ms |    9    ->     0
```

Las tres primeras filas son practicamente identicas: el hedging **no acelero
nada**, solo evito que un punado de requests se cayera en el pozo. La barra esta
en escala log a proposito — en escala lineal la cola no se ve, que es justamente
por lo que existen los percentiles.

## El trade-off

El umbral del hedge es la unica perilla, y la tabla muestra la curva completa:

| Umbral | p95 | p99 | Trabajo del backend | Hedgeados |
|---|---|---|---|---|
| sin hedging | 80 ms | 487 ms | 2500 (+0%) | 0% |
| **p95 (80 ms)** | **80 ms** | **110 ms** | **2617 (+4.7%)** | **4.7%** |
| p50 (26 ms) | 57 ms | 73 ms | 3557 (+42%) | 42.3% |
| 0 ms (duplicar todo) | 48 ms | 66 ms | 5000 (+100%) | 100% |

Leido de arriba hacia abajo: los primeros **377 ms de p99** cuestan **+4.7%** de
infraestructura. Los **37 ms** siguientes (110 -> 73) cuestan **+37%** mas. Los
**7 ms** que quedan (73 -> 66) cuestan **otro +58%**. Rendimientos decrecientes
brutales, y no hace falta explicarlos: estan en la tabla.

Por que el p95 y no el p50: el umbral define, por definicion, **que fraccion de
los requests se duplica**. Hedgear al p95 duplica ~5%; hedgear al p50 duplica
~42% (no 50%, porque el reloj del cliente y el round-trip HTTP corren unos
milisegundos a favor). Ese 42% de copias es capacidad que le estas sacando al
backend para servir requests que **ya estaban bien** — en un backend con
headroom se nota poco, y en uno sin headroom es el escenario 6.

El caso `0 ms` es la reduccion al absurdo y vale como ancla: si duplicas la flota
entera, si, mejora todo, incluso el p50. **Duplicaste la flota.** Y solo se ve
tan lindo porque este backend tiene 48 workers por replica y le sobra el doble de
capacidad. La columna `gano` da 47.0%, casi el 50% exacto que se espera cuando
las dos copias salen juntas y son simetricas.

## Cuando el hedging EMPEORA las cosas

**La precondicion del hedging es la independencia entre replicas.** La copia sirve
porque la segunda replica sortea su suerte por separado: si la primera cayo en un
disco lento, es improbable que la segunda tambien. En `backend.py` eso es
literal — la latencia se siembra con `(seq, replica)`, asi que dos replicas del
mismo request son dos sorteos distintos.

Cuando la lentitud **no es aleatoria sino sistemica** (se cayeron replicas, un
deploy se llevo capacidad puesta, el cluster entero esta al limite), esa
independencia desaparece: no hay ninguna replica sana adonde escapar, y la copia
solo agrega carga. Los escenarios 5-7 bajan la capacidad de **48 a 2 workers por
replica** sin tocar nada mas: mismo cliente, mismos 2500 requests, mismo umbral
de 80 ms.

| | 5. saturado, sin hedging | 6. saturado, hedge @80 ms | 7. saturado, hedge + budget 5% |
|---|---|---|---|
| p50 | 165 ms | **394 ms** (2.4x peor) | 173 ms |
| p95 | 689 ms | **920 ms** (1.3x peor) | 758 ms |
| p99 | 1112 ms | **1424 ms** | 1257 ms |
| Trabajo del backend | 2500 | **4933 (+97%)** | 2625 (+5%) |
| Requests hedgeados | 0% | **97.3%** | 5.0% |

El numero que grita es el **97.3%**. El mismo umbral que en el dia sano se
disparaba en el 4.7% de los requests, con el backend caido se dispara en casi
todos: **el hedging degenero en "duplicar todo" sin que nadie cambiara la
configuracion**. Y le pide +97% de trabajo al backend exactamente el dia que no
tiene nada para dar.

Las columnas que hay que mirar son el **p50 y la carga**, porque son las que se
repiten corrida a corrida: el p50 empeora 2.4x (382 / 411 / 394 ms contra 163 /
151 / 165) y el trabajo del backend sube ~+96% siempre. El **p99 tambien empeora
casi siempre** (1424 vs 1112 aca), pero es la columna mas ruidosa de la tabla:
bajo saturacion el p99 se apoya en 25 muestras cuya latencia depende de la cola
real y del scheduler del SO, y en una de cada tres corridas puede salir parecido
o incluso mejor que sin hedgear. Si en clase sale asi, ese es el numero honesto:
la tesis del escenario 6 **no** es "el p99 empeora", es que el sistema paga el
doble de carga para no comprar nada.

El mecanismo es un lazo de realimentacion positiva:

```
mas lento  ->  vence el umbral mas seguido  ->  mas copias  ->  mas carga  ->  mas lento
```

Un umbral calibrado contra un percentil es una **constante que se vuelve mentira
apenas cambia la distribucion**, y el sistema no se entera.

La mitigacion es el **hedge budget**: un contador que se niega a hedgear mas del
5% de los requests vistos. Son literalmente tres lineas
(`PresupuestoDeHedge.conceder`), y la columna 7 muestra que alcanzan: los hedges
vuelven de 97.3% a 5.0% clavado, el trabajo extra de +97% a +5%, y el p50 vuelve
al del baseline saturado (173 vs 165 ms; el p95 queda cerca, 758 vs 689). El
budget **devuelve el sistema al estado en que estaba antes de "ayudar"**.

Lo honesto de la fila 7: el p99 **no mejora** respecto de no hedgear (1164, 1106 y
1257 ms en las tres corridas, contra 1296, 889 y 1112 sin hedging: ruido). Y esta
bien que sea asi. Con todas las replicas igual de mal no hay adonde escapar, asi
que el budget no compra latencia — **compra que el hedging no te empeore el dia**.
La leccion de produccion es esa: cualquier mecanismo que responde a la lentitud
generando **mas trabajo** necesita un tope, siempre. Es la misma idea que el
*retry budget* / retry throttling de gRPC y los service meshes.

## Cuando NO se puede hedgear

El hedging manda copias **sin esperar a que la primera falle**. Por definicion hay
copias que se ejecutan enteras y cuyo resultado se descarta: en este demo, el
escenario 2 tira a la basura ~40% de los hedges y el escenario 4 tira 2500
requests completos. Si la operacion tiene efecto de lado, **el efecto ocurre igual
N veces**.

Hedgear un `POST /cobrar` cobra la tarjeta dos veces, y el cliente ni se entera:
se quedo con la primera respuesta y la otra se ejecuto igual del lado del
servidor.

| Hedgeable | No hedgeable |
|---|---|
| `GET` de un producto, lookup, lectura de una replica | Cobro, "enviar mail", `INSERT` sin clave |
| Busqueda, render, cualquier consulta pura | Cualquier cosa que mute estado |

Por eso gRPC obliga a configurar el hedging **por metodo** y no globalmente: la
decision es por operacion y solo la conoce quien escribio esa operacion. La
salida estandar cuando igual hace falta reintentar algo con efecto es una
**idempotency key** que el servidor deduplica (Stripe es el ejemplo canonico): el
request pasa a ser idempotente *por construccion*, y recien ahi se puede hedgear
o reintentar sin miedo.

## Como lo hacen los sistemas de verdad

- **gRPC** — `hedgingPolicy` en el service config, con `maxAttempts`,
  `hedgingDelay` y `nonFatalStatusCodes` (definido en el gRFC A6, *client
  retries*). El `hedgingDelay` es exactamente el umbral X de este demo, y la
  recomendacion de la doc es ponerlo en un percentil alto de la latencia
  observada. Es el ejemplo mas limpio para mostrar en clase.
- **Envoy** — tiene una *hedge policy* con `hedge_on_per_try_timeout`, que
  dispara la copia cuando se vence el timeout por intento en vez de a un delay
  configurado aparte *(detalle aproximado: conviene chequear la doc de la version
  antes de afirmarlo)*.
- **Cassandra** — `speculative_retry` como opcion por tabla, que acepta
  `99PERCENTILE`, `ALWAYS`, `NONE` o un valor fijo en ms. Es esta misma tecnica
  con otro nombre, y el default en percentil confirma que calibrar el umbral
  contra la propia distribucion medida es practica estandar, no una idea de
  paper. Varios drivers de bases distribuidas traen ademas una *speculative
  execution policy* del lado del cliente.

**La variante del paper: tied requests.** El hedging clasico **espera** X ms antes
de mandar la copia, y esa espera es la que mantiene el costo en ~5%. Los *tied
requests* hacen otra cosa: mandan el request a **dos replicas de entrada**, pero
cada copia lleva la identidad de la otra (van "atadas"); cuando una replica saca
el request de su cola y **empieza** a ejecutarlo, le manda un mensaje de
cancelacion a la otra.

| | Hedging | Tied requests |
|---|---|---|
| Cuando sale la copia | despues de X ms | de entrada, a las dos |
| Donde se deduplica | en el cliente, esperando | en el servidor, al desencolar |
| Que ataca | la cola de ejecucion | tambien la cola de **encolado** |
| Que necesita el servidor | nada | cancelacion cooperativa entre replicas |

Los tied requests desperdician mucho menos trabajo y arrancan en la replica que
tenga la cola mas corta sin tener que adivinar cual es; a cambio necesitan
protocolo entre replicas, mientras que el hedging funciona contra un servidor que
no sabe nada. El paper sugiere ademas un delay chico antes de la segunda copia
(del orden del doble del round-trip de red) para que la cancelacion llegue a
tiempo.

## Que NO tiene

Cada limite es la puerta a otra clase:

- **El backend no es un servicio: duerme.** `time.sleep()` con una latencia
  sorteada de una lognormal. Lo que se mide es la **politica del cliente**, no la
  performance de un servidor real. El modelo de latencia es sintetico: cuerpo
  lognormal(mediana 22 ms, sigma 0.70) + un 2% con un stall extra de
  lognormal(mediana 500 ms, sigma 0.40).
- **Un solo proceso simula las 3 replicas** y no hay red real. La varianza de red
  (retransmisiones TCP, un switch congestionado, un pod que migro de nodo) es
  otra fuente de cola gorda que este demo no toca, y en produccion suele ser la
  principal.
- **Sin cancelacion del lado del servidor.** La copia perdedora corre hasta el
  final: es a proposito, porque ese trabajo tirado **es** el costo que el demo
  quiere mostrar. Implementarlo bien es la variante de tied requests de arriba.
- **La cola es un semaforo, no un scheduler.** Hay N workers por replica y el que
  no entra espera; no hay prioridades, ni load shedding, ni timeouts del lado del
  servidor. Un backend real se defiende, y esa defensa cambia la forma de la cola.
- **Lazo cerrado.** Los 32 drivers mandan el request siguiente recien cuando
  volvio el anterior, asi que la tasa la fija la latencia y no al reves. Es
  *coordinated omission*: con trafico que llega a tasa fija (usuarios de verdad)
  la cola creceria sin techo y todos los numeros de cola serian **peores**. Estos
  son la version optimista.
- **El harness suma ~4 ms parejos** a toda la tabla (sesgo de `time.sleep` en
  macOS + round-trip HTTP), por eso el p50 medido da 26 y no los 22 del modelo.
  El sesgo es identico en los 7 escenarios, asi que no altera ninguna
  comparacion.
- **2500 muestras por escenario** dejan el p99 apoyado en 25 requests y el p99.9
  en 3. El p99.9 hay que leerlo como "el peor punado", no como una medicion. El
  modelo es determinista (la latencia se siembra por `(seq, replica)`), asi que
  los escenarios sanos dan lo mismo en cada corrida; los saturados varian porque
  ahi la latencia depende de la cola real y esa depende del scheduler del SO.
- **Sin descubrimiento de replicas ni health checks.** El cliente elige por
  round-robin (`seq % 3`) y la copia va a la siguiente. Un cliente real evita las
  replicas que sabe enfermas, que es la otra mitad del problema.

## Detalles de implementacion que valen la pena mirar

- `con_hedge()` en `hedging.py` es la tecnica entera en ocho lineas. Tres
  sutilezas: el reloj **no** se reinicia cuando sale la copia (el usuario empezo a
  esperar cuando salio la primera), la copia perdedora **no** se cancela, y hay
  que **leer** el resultado de la ganadora — si no, un request que fallo entra en
  la tabla como una muestra rapida y perfecta.
- `backend.py` **no usa Flask**, y es a proposito: el server de Werkzeug manda
  `Connection: close` en todas las respuestas, o sea un socket TCP nuevo por
  request. Los ~25.000 requests del demo agotaban los 16.384 puertos efimeros de
  macOS (TIME_WAIT dura 30 s) y la corrida se moria con `Errno 49` a mitad de la
  proyeccion, 8 de cada 11 veces. Con `ThreadingHTTPServer` en HTTP/1.1 y una
  conexion por hilo de envio son 96 sockets reusados de punta a punta.
- La cola del backend es un **semaforo por replica**, no una formula: si no hay
  worker libre el request espera adentro y esa espera se suma a su propio
  trabajo. La congestion del escenario 6 emerge sola, sin ninguna constante
  magica que la fabrique.
