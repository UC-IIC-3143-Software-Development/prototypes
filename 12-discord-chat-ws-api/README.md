# Chat tipo Discord: historial por API + tiempo real por WebSocket

## Que demuestra

Que un chat necesita **dos canales de datos** y que ninguno reemplaza al otro. El
WebSocket **no te puede dar el pasado**: cuando se abre, empieza a contarte lo
que pasa desde ese instante, y todo lo anterior no existe para el. El REST **no
te puede dar el presente**: contesta lo que habia en la base cuando corrio el
`SELECT` y despues se calla; para enterarte de lo siguiente tenes que volver a
preguntar. Por eso toda app de chat real usa los dos: `fetch` para "que paso" y
un socket para "que esta pasando".

Y la parte fina, que es lo que hace valioso al demo: **el bug clasico no esta en
ninguno de los dos, esta en la costura**. Entre "pido el historial" y "me
suscribo al socket" hay una ventana, y lo que se escriba ahi adentro puede no
quedar en ninguno de los dos lados: es un **hueco**, y es invisible hasta que
alguien recarga la pagina. El arreglo es contraintuitivo: hay que abrir el WS
**primero**, bufferear lo que llegue, recien despues pedir el historial y
reconciliar por id. Eso no elimina el solapamiento entre los dos canales, lo
**garantiza** — y un solapamiento se deduplica por id, mientras que un hueco no
se puede inventar.

| Canal | Contesta | Propiedades que solo tiene el | Lo que no puede |
|---|---|---|---|
| REST (`fetch`) | **que paso** | consultable, paginable, cacheable, reintentable, con status code | avisarte de algo nuevo |
| WebSocket | **que esta pasando** | push sin preguntar, latencia de milisegundos, presencia | contarte lo de antes de conectarse |

La pantalla lo hace visible con un badge por mensaje: **API** (naranja) si vino
por `fetch`, **WS** (verde) si vino por el socket. Es el **mismo objeto con los
mismos campos** en los dos casos; lo unico que cambia es **cuando** lo pediste.

## Como levantarlo

`flask-sock` es una dependencia nueva de este proyecto, asi que si el repo ya
estaba instalado hay que volver a correr el install (desde la **raiz** del repo):

```bash
pip3 install -r requirements.txt
```

```bash
cd 12-discord-chat-ws-api
python3 app.py
```

Flask en el puerto **5002**, escuchando en `0.0.0.0`. Sin Docker, sin base
externa y sin build step: un solo proceso sirve el `index.html`, la API REST y el
WebSocket, y la base es un `chat.db` de SQLite que se crea y se siembra sola en
la primera corrida (**77 mensajes**: 55 en `#general`, 12 en `#random`, 10 en
`#dev`).

Abrir **dos ventanas ya bautizadas** — asi se demuestra esto, con una sola no se
ve nada:

- <http://localhost:5002/?user=ana>
- <http://localhost:5002/?user=beto>

Sin `?user=` la pagina pregunta el nombre con un `prompt()` del browser, que
frena el arranque y deja dos `anon` iguales si te olvidas de uno.

Para volver al estado inicial: Ctrl+C, `rm chat.db` y levantar de nuevo.
Si el puerto esta ocupado: `lsof -nP -iTCP:5002 -sTCP:LISTEN`.

## El guion de la clase

La pantalla tiene tres cosas que valen: el **badge** de cada mensaje, el contador
*en vivo por WS en este canal* (se resetea al abrir cada canal), y el **panel de
eventos** de la derecha, que loguea cada `GET`, cada frame y cada merge. Los
pasos van en orden y cada uno deja la pantalla lista para el siguiente.

| # | Que hace el profesor | Que se ve en pantalla | Que queda demostrado |
|---|---|---|---|
| 1 | Dos ventanas (`ana` y `beto`), las dos en `#general`. Beto escribe | El mensaje aparece en **las dos** al instante, con badge verde **WS**. Tambien en la de beto: no se pinta local, vuelve por el socket | Push de verdad, sin polling y sin recargar. El `id` lo puso el servidor, por eso el emisor tiene que esperar el round-trip |
| 2 | F5 en la ventana de ana | La **misma** conversacion, mensaje por mensaje, pero **todos los badges naranjas (API)** y el contador de WS en **0** | *El WebSocket no te puede dar lo que paso antes de que te conectaras.* Es la justificacion entera del REST en una tecla |
| 3 | Abrir en otra pestana <http://localhost:5002/api/channels/general/messages?limit=5> | El JSON crudo: `messages` ascendente, `has_more: true`, y objetos con los mismos `id, channel_id, author, text, ts` que muestra el panel para los frames WS | Misma forma, dos transportes. El cliente tiene **una sola** funcion de render |
| 4 | Click en **cargar mas (?before=)**, arriba de todo | En el panel: `GET .../messages?before=6&limit=50 -> 5 mensajes, has_more=false`. Se prependen 5 mensajes naranjas, el scroll **no salta** y el boton pasa a *no hay mas historial* | Paginacion por **cursor**, no por `OFFSET`: se pide "lo anterior a este id", no "salteame 50" |
| 5 | En ana: **cortar WS**. Beto escribe 3 mensajes | Banner rojo en ana. Ana **no muestra nada** y sigue tan campante; si intenta escribir, el panel dice `no se envia: el WS no esta conectado` | La pantalla **miente en silencio**: es exactamente lo que pasa con el wifi cortado |
| 6 | En ana: **reconectar** | En orden: `subscribed latest_id=` mayor que lo ultimo visto, `hueco: me perdi 3 ids mientras estuve caido`, el `GET ...?after=<ultimo id visto>`, y los 3 mensajes entrando con badge **naranja**. Beto manda un cuarto: entra **verde** | El replay del hueco lo hace el **REST**, no el socket. En pantalla queda API-API-API-WS: **ese borde de color es el instante de la reconexion** |
| 7 | Tildar **modo ingenuo (REST primero, WS despues)**, ir a `#random` y volver a `#general`. Mientras el panel dice `ventana de 800 ms`, beto escribe | Ese mensaje **no aparece nunca** en ana: ni por WS ni por REST, y ana no tiene forma de saberlo. F5 y ahi si aparece, naranja | El mensaje siempre estuvo en la base: lo que fallo fue el **orden del cliente**. Destildar y repetir: mismos clicks, misma gente, un flag de diferencia |
| 8 | Al abrir cualquier canal, leer la linea `merge:` del panel | `merge: subscribed latest_id=55 \| REST llego hasta 55 \| buffer arranca en - \| solapados descartados 0 -> 50 en pantalla`. Si beto escribe justo durante la carga: `solapados descartados 1` y **una sola** burbuja | La prueba de que no hay ni hueco ni duplicado. *Suscribirse primero no elimina el solapamiento, lo garantiza; y un solapamiento se deduplica por id* |
| 9 | Cerrar la ventana de beto entera | En ana la lista *En este canal* baja a 1 y el panel escribe `beto salio`, **sin ningun request HTTP** | La presencia solo tiene sentido **ahora**: por eso no hay endpoint REST de presencia y no hace falta |
| 10 | Tercera ventana (`caro`) en `#random`. Beto escribe en `#general` | Caro no recibe **ningun** frame: su contador no se mueve | El filtro por canal esta en el **servidor**; el broadcast ni siquiera sale hacia esa conexion |

Dos avisos para no pelearse con el demo en vivo:

- El paso 7 se hace **de a dos manos**: el mensaje de beto tiene que salir
  mientras la ventana de ana esta en la ventana de 800 ms.
- Entre el click a `#random` y el click de vuelta a `#general`, **esperar a que
  termine la apertura**. Si los dos clicks van juntos, el segundo se ignora a
  proposito y el panel lo dice: `#general: ignorado, hay una apertura en curso`.

## La API REST

| Metodo y ruta | Params | Respuesta |
|---|---|---|
| `GET /` | — | El `index.html` (lo sirve el mismo proceso) |
| `GET /api/channels` | — | `{"channels": [{"id": "general", "name": "general"}, ...]}` |
| `GET /api/channels/<channel_id>/messages` | `before`, `after`, `limit` | `{"channel_id": "general", "messages": [...], "has_more": true}` |

El objeto mensaje es **el mismo** que viaja adentro del frame WS `message`:

```json
{ "id": 56, "channel_id": "general", "author": "beto", "text": "hola", "ts": "2026-08-17T12:54:09Z" }
```

`id` es un `INTEGER PRIMARY KEY AUTOINCREMENT` de SQLite, monotono y **global, no
por canal**: por eso `#random` arranca en el id 56 y por eso dentro de un canal
quedan huecos de numeracion. Esta bien: es un **token de orden**, no un contador.
`ts` es solo para mostrar — nunca se ordena ni se reconcilia por tiempo, porque
dos mensajes del mismo segundo (o dos relojes desincronizados) rompen el merge.

Un solo endpoint de mensajes, con tres modos mutuamente excluyentes:

| Modo | Query | Que devuelve | Quien lo usa |
|---|---|---|---|
| inicial | *(sin cursor)* | los `limit` mensajes **mas nuevos** del canal | abrir el canal |
| hacia atras | `?before=6` | los `limit` inmediatamente **mas viejos** que el 6, sin incluirlo | boton *cargar mas* |
| hacia adelante | `?after=55` | los `limit` inmediatamente **mas nuevos** que el 55, sin incluirlo | rellenar el hueco al reconectar |

Detalles del contrato que le sacan trabajo al cliente:

- `messages` viene **siempre ascendente por id**, en los tres modos, asi el
  frontend no tiene ni un `.reverse()` y los tres modos comparten el mismo
  render. Los modos "hacia atras" el servidor los resuelve con `ORDER BY id DESC`
  y los invierte por dentro. (Trampa clasica: `ORDER BY id ASC LIMIT 50` con
  `?before=` devuelve los 50 mas viejos **del canal**, no los 50 pegados al
  cursor.)
- `has_more` siempre se refiere a **la direccion que pediste**, y sale de pedirle
  a SQLite `limit + 1` filas y tirar la sobrante.
- `limit` se **clampea** a 1..100 (default 50): `?limit=0` y `?limit=9999` no son
  errores, se acomodan. Un error menos que manejar en cada llamada.
- Solo hay dos errores, a proposito: `404 {"error": "canal desconocido"}` y
  `400 {"error": "cursor invalido"}` (cursor no entero, los dos cursores juntos,
  o un numero que no entra en 64 bits).
- **No existe** un endpoint REST de presencia. Es informacion del presente: es
  trabajo del socket, y esa division es justamente lo que ensena el proyecto.

## El protocolo WebSocket

Endpoint: `ws://localhost:5002/ws?user=<nombre>`. **Una conexion por pestana**, y
el canal no va en la URL: una conexion esta suscripta a **exactamente un canal a
la vez** y un `subscribe` nuevo reemplaza al anterior (por eso no hay
`unsubscribe`, y por eso la presencia es por canal). Todos los frames son JSON
con campo `type`: dos del cliente, cuatro del servidor.

| Dir | Frame | Campos | Cuando |
|---|---|---|---|
| C -> S | `subscribe` | `channel_id` | Al abrir un canal o al reconectar |
| C -> S | `send` | `channel_id`, `text` | Al mandar un mensaje (max 500 chars, no vacio) |
| S -> C | `subscribed` | `channel_id`, `latest_id`, `members` | Ack del `subscribe`. **El frame mas importante** |
| S -> C | `message` | `message` *(el objeto entero)* | Broadcast a los suscriptos del canal, **incluido el emisor** |
| S -> C | `presence` | `channel_id`, `event` (`join`/`leave`), `user`, `members` | Alguien entro, cambio de canal o se desconecto |
| S -> C | `error` | `detail` | Frame ilegible o de `type` desconocido, canal desconocido, `send` sin suscripcion, texto vacio o muy largo |

`latest_id` es el `MAX(id)` del canal leido **en el mismo instante** en que la
conexion entra al set de suscriptos (dentro del lock, ni antes ni despues). Ese
es el contrato que convierte el merge de heuristica en garantia:

> todo id **&le; `latest_id`** te lo tenes que traer por REST; todo id **&gt;
> `latest_id`** te va a llegar por este socket.

`presence` manda el **roster completo** ademas del evento: el roster para
repintar la lista sin que el cliente diffee nada, y el `event` + `user` para
poder escribir "beto salio" en el panel.

Dos ausencias deliberadas: **no hay heartbeat** de aplicacion (el browser y el
protocolo ya hacen ping/pong) y **no hay frame `resume`** — el hueco se recupera
por REST con `?after=`, que es el punto del proyecto. Las dos se comparan con
Discord mas abajo.

Del lado del servidor hay **un solo `threading.Lock` global** que serializa dos
secuencias: `[insertar -> leer el id -> difundir]` y `[suscribir -> leer
latest_id]`. Sin el, dos `send` concurrentes pueden salir por el socket en orden
invertido (el 130 antes que el 129) y el merge por id del cliente deja de ser
correcto.

## El orden correcto (y el bug clasico)

El orden intuitivo es "cargo la pantalla y despues me engancho a lo nuevo". Es el
que pierde mensajes:

```
INGENUO: REST primero, subscribe despues        (checkbox "modo ingenuo")

  cliente                                  servidor
     |--- GET .../messages ---------------->|  SELECT: llega hasta el id 55
     |<-------------- [6..55] --------------|
     |                                      |  <-- beto escribe: id 56
     |                                      |      nadie suscripto: el frame no sale
     |--- subscribe ----------------------->|  ahora si entra al set
     |<-- subscribed latest_id=56 ----------|
     |                                      |  <-- beto escribe: id 57
     |<-- message id=57 --------------------|
     |
     pantalla: 6..55 y 57.   El 56 NO ESTA y no hay forma de saberlo.
     No esta en el historial (el SELECT ya habia pasado)
     ni en el socket   (todavia no habia suscripcion).          <-- HUECO
```

El correcto invierte los dos pasos y agrega un buffer:

```
CORRECTO: subscribe -> esperar el ack -> bufferear -> REST -> merge -> pintar

  cliente                                  servidor
     |--- subscribe ----------------------->|  entra al set de suscriptos
     |<-- subscribed latest_id=55 ----------|  MAX(id) leido en ese mismo instante
     |                                      |  <-- beto escribe: id 56
     |<-- message id=56 --------------------|  --> al BUFFER, no se pinta
     |--- GET .../messages ---------------->|  SELECT: llega hasta el id 56
     |<-------------- [7..56] --------------|
     |
     merge por id:  histMax = 56
                    del buffer entra solo lo que tenga id > 56  -> nada
                    el 56 estaba en los DOS lados -> se descarta uno
     pantalla: 7..56, sin huecos y sin repetidos.               <-- SOLAPAMIENTO
```

Tres decisiones, y las tres importan:

1. **Suscribirse antes del fetch.** Convierte un posible hueco en un posible
   solapamiento. Un mensaje repetido se tira por id; uno que nunca llego no se
   puede inventar.
2. **Esperar el ack `subscribed`, no solo mandar el frame.** `ws.send()` es
   fire-and-forget: no garantiza que el servidor ya te haya metido en el set. Sin
   el ack queda la misma ventana de antes, solo que de microsegundos — o sea que
   no se reproduce en clase pero rompe en produccion.
3. **Bufferear en vez de pintar mientras carga.** Si no, los mensajes nuevos
   aparecen arriba de un historial que todavia no llego, y el orden final lo
   decide quien gano la carrera.

Al reconectar es el mismo baile, con un paso mas al principio: suscribirse,
comparar `latest_id` contra el ultimo id que viste **sin pegarle a la base**, y
solo si hay diferencia pedir `?after=<lastSeenId>` en loop hasta que `has_more`
sea `false`. Recargar la pagina entera en vez de rellenar seria peor: se rebaja
lo que ya estaba, el scroll salta al fondo y, si el hueco fue de mas de 50
mensajes, **queda un agujero silencioso en el medio de la conversacion**.

(El panel dice `me perdi N ids`, no "N mensajes", a proposito: el id es global,
asi que si en el medio alguien escribio en otro canal el numero es mas grande que
la cantidad de burbujas que vas a ver aparecer.)

## Como lo hacen los sistemas de verdad

Discord es **asimetrico a proposito**: los mensajes se **mandan por REST** (`POST
/api/v10/channels/{channel.id}/messages`) y se **reciben por el gateway
WebSocket** (evento `MESSAGE_CREATE`). No es una inconsistencia historica:
escribir y leer tienen requisitos distintos.

Por que mandar por HTTP y no por el socket:

1. **Rate limits.** Discord devuelve buckets por ruta en los headers
   `X-RateLimit-Bucket`, `X-RateLimit-Remaining`, `X-RateLimit-Reset-After`, y un
   `429` con `Retry-After`. Un frame WebSocket no tiene respuesta ni headers
   donde colgar nada de eso.
2. **Un status code por request.** El cliente sabe si su mensaje entro (200), si
   fue rechazado (400), si no tiene permiso (403) o si tiene que esperar (429).
   Por el socket es fire-and-forget: hay que inventarse un protocolo de acks
   encima.
3. **Auth y reintentos con semantica HTTP**, que ya entienden todos los proxies,
   CDNs y librerias del camino.
4. **Idempotencia.** El `POST` acepta un `nonce` que genera el cliente y que el
   gateway devuelve dentro del `MESSAGE_CREATE`. Eso permite el **echo optimista**
   sin duplicar (pintas la burbuja local y la reemplazas cuando vuelve la
   autoritativa) y cubre el reintento despues de un timeout.

El handshake del gateway, por opcodes: el servidor abre con **op 10 HELLO**
(trae `heartbeat_interval`), el cliente responde **op 2 IDENTIFY** (token,
intents) y el servidor manda el dispatch **READY**, con `session_id` y
`resume_gateway_url`. Desde ahi cada dispatch (**op 0**) viene numerado con un
sequence `s` que el cliente guarda: **ese `s` es el equivalente conceptual de
nuestro `lastSeenId`**. Si la conexion se cae, el cliente abre el
`resume_gateway_url` y manda **op 6 RESUME** con token + `session_id` + el ultimo
`s`; el gateway le **repite** lo que se perdio y cierra con `RESUMED`. Si la
sesion es demasiado vieja, contesta **op 9 INVALID SESSION** y el cliente tiene
que volver a IDENTIFY y rebajarse el estado completo. Esas dos ramas — replay
barato o refetch completo — son exactamente las dos ramas de nuestra reconexion.

Los **heartbeats** (op 1 del cliente, op 11 ACK del servidor) existen porque una
conexion TCP puede estar muerta mientras el sistema operativo la sigue creyendo
abierta: timeout de NAT, cambio de red, tapa del notebook. La leccion:
*"el socket esta abierto" no es lo mismo que "estoy recibiendo eventos"*, y un
cliente serio tiene que detectar el **silencio**, no solo el `onclose`.

Los ids son **snowflakes** de 64 bits: 42 bits de milisegundos desde la epoca de
Discord (`1420070400000`, o sea 2015-01-01) + 5 de worker + 5 de proceso + 12 de
incremento dentro del mismo ms. Consecuencias: ordenar por id ordena por tiempo,
cada worker genera los suyos **sin un contador central** y no colisionan, y del
id se saca el timestamp sin ir a la base.

Y la paginacion es **siempre por cursor** (`before`, `after`, `around`, mas
`limit` de 1..100 con default 50), nunca por `OFFSET`. Dos razones distintas y
las dos importan:

| | Cursor sobre el id | `OFFSET n` |
|---|---|---|
| **Correccion** | El id es inmutable: la pagina 2 es la pagina 2 aunque entren mensajes mientras paginas | Se corre bajo tus pies: repite filas o se saltea otras |
| **Costo** | Seek por indice, O(log n): la pagina 200 cuesta lo mismo que la 1 | La base recorre y descarta n filas: la pagina 200 cuesta 200 veces la 1 |

**La simplificacion principal de este prototipo, declarada:** aca el mensaje se
manda **por el WebSocket** (`{"type": "send"}`), no por `POST`. Esta bien para
una clase porque el argumento del proyecto es sobre **leer** — el historial
necesita REST, lo que pasa ahora necesita WS — y ese argumento no se toca
cambiando por donde se escribe; a cambio, todo entra en un archivo y en un solo
modelo mental. Lo que se pierde y **no** hay que copiar a produccion: no hay
status code por mensaje, no hay headers de rate limit, no hay `nonce` ni
reintentos idempotentes. Si esto fuera real, el send seria
`POST /api/channels/<id>/messages` y el WS quedaria de **solo lectura**.

Otras simplificaciones, todas conscientes: los ids son un `AUTOINCREMENT` de
SQLite en vez de snowflakes distribuidos (con **un** proceso un contador central
es perfecto; deja de serlo en el instante en que hay dos servidores escribiendo);
no hay autenticacion; la presencia es el set de conexiones vivas de este proceso;
los timestamps no participan del orden.

Ultima diferencia deliberada: Discord devuelve los mensajes **newest-first** y
cada cliente tiene que invertir el array. Aca se devuelve siempre ascendente, en
los tres modos, para que el frontend no tenga ni un `.reverse()`: el servidor se
come el `ORDER BY DESC` + invertir por dentro.

## Relacion con el proyecto 05

- **05 (`05-ws-chat-broadcasting`)**: WebSocket **puro**, y ademas en un servidor
  aparte (8000 para la web, 8765 para el socket). Entras y ves lo que se escribe
  **desde ese momento**; si recargas la pagina, la conversacion arranca vacia,
  porque el historial nunca existio para vos.
- **12 (este)**: agrega la mitad que falta. Al recargar, la conversacion sigue
  ahi — pero vino por HTTP, y el contador de WS en **0** lo demuestra.

Este proyecto ademas **fusiona** los dos servidores en un proceso y un puerto a
proposito, para que la discusion sea sobre los dos canales de datos y no sobre el
deployment. En produccion casi siempre estan separados: Discord usa dos hostnames
distintos, `discord.com/api` y `gateway.discord.gg`, porque escalan distinto —
la API es stateless y se replica sin pensar, mientras que el gateway sostiene
millones de conexiones largas y con estado (`session_id`, buffer de replay,
presencia).

## Que NO tiene

Cada limite de esta lista es la puerta a otra clase:

- **Sin autenticacion.** El usuario es un query param: `?user=ana` te hace ana.
  Un gateway real manda un frame IDENTIFY con un token; aca no hay nada que
  identificar.
- **Estado en memoria de un solo proceso.** Las suscripciones son un `dict` en
  este proceso. Con dos procesos detras de un balanceador, ana y beto pueden caer
  en procesos distintos y **no verse**: el broadcast solo alcanza a las
  conexiones locales. La solucion real es un bus de pub/sub entre procesos
  (Redis, NATS) — el mismo Redis del **proyecto 07**, usado para otra cosa. El
  contrato del cliente no cambiaria en nada.
- **Sin rate limit.** Se puede tirar mensajes en loop desde la consola del
  browser y el servidor los escribe todos. Es lo que los buckets de Discord
  existen para frenar, y es una de las razones por las que el send real va por
  HTTP.
- **Sin entrega garantizada.** No hay ack por mensaje ni reintento: si el socket
  muere justo despues del `send`, el mensaje puede estar escrito sin que vos lo
  hayas visto. Se arregla solo al reconectar, porque el `?after=` te lo trae —
  que es precisamente por que el prototipo puede darse el lujo de no tener acks.
- **Sin deteccion de silencio.** Se detecta el `onclose`, pero no la conexion que
  quedo abierta y muda (el caso del heartbeat op 1/11).
- **Ids centralizados.** Un `AUTOINCREMENT` deja de servir con dos escritores; de
  ahi salen los snowflakes, y de ahi sale la discusion de ids del **proyecto 10**.
- **Servidor de desarrollo de Flask, un thread por conexion.** Para una clase con
  veinte pestanas sobra; para produccion, ni cerca.
