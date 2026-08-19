# Prototypes

Prototipos para la unidad de System Design. Cada carpeta numerada es un
proyecto independiente que se levanta y se corre por su cuenta.

# Instalación packages Python

```bash
pip3 install -r requirements.txt
```

# Puertos

Cada proyecto usa un puerto propio, así que se pueden levantar todos a la vez
sin pisarse. Importante: dos MySQL en el mismo puerto no dan error visible, el
script se conecta a la base equivocada y el demo miente.

Varios prototipos no abren ningún socket: son simulaciones que corren en la
terminal, imprimen y terminan. Esos van con `—`.

| Proyecto | Puerto(s) | Cómo se levanta |
|---|---|---|
| 01-reverse-proxy | — | `python3 reverse_proxy.py` |
| 02-load_balancer | — | `python3 <estrategia>_load_balancer.py` |
| 03-polling | 5001 | `python3 polling-ec2.py` |
| 04-streaming-logs | 5000 | `python3 streaming-logs.py` |
| 05-ws-chat-broadcasting | 8000 (web) + 8765 (ws) | `python3 ws-chat-server.py` |
| 06-db-connection-pool | 3307 (mysql) | `docker-compose up -d` + `python3 pool-counter.py` |
| 07-ecommerce-cache-redis | 3308 (mysql) + 6379 (redis) | `docker-compose up -d` + `python3 ecommerce_cache_storage_hot_cold.py` |
| 08-cache_debounce | — | `python3 cache_debounce.py` |
| 09-db-airline-booking-seats | 3306 (mysql) | `docker-compose up -d` + `python3 approach1_forupdate.py` |
| 10-indexes_ids_postgresql | 5432 (postgres) | `docker-compose up -d` + `python3 indexes_emp.py` |
| 11-db-buffer-cache-postgresql | 5433 (postgres) | `docker-compose up -d` + `python3 buffer_cache_demo.py` |
| 12-discord-chat-ws-api | 5002 (http + ws) | `python3 app.py` |
| 13-request-hedging | 5003 | `python3 backend.py` + `python3 hedging.py` |

Si un `docker-compose up` falla con `port is already allocated`, hay algo más
escuchando en ese puerto. Para ver qué es:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

Un PostgreSQL o un MySQL instalados en el sistema (no en Docker) son la causa
más común y hay que detenerlos antes de levantar los proyectos 10 y 11.

# Cómo se corre cada uno

Todos los comandos se corren **parado en la carpeta del proyecto**. Los que
sirven un `index.html` lo hacen desde el directorio de trabajo, así que correrlos
desde la raíz del repo rompe el frontend.

## 01-reverse-proxy

```bash
cd 01-reverse-proxy
python3 reverse_proxy.py
```

Sin Docker y sin servidor: no abre ningún puerto. Es una simulación de una sola
pasada que reescribe strings de request con una regex y los imprime.

Se espera ver 3 pares `Original request` / `Modified request` donde
`http://myblogs.com` quedó reemplazado por `http://192.168.0.10` y el path se
mantiene intacto. Termina solo.

## 02-load_balancer

```bash
cd 02-load_balancer
python3 round_robin_load_balancer.py
python3 hash_load_balancer.py
python3 range_load_balancer.py
```

Tampoco abre puertos: son tres simulaciones CLI de la misma idea (reescribir el
host del request) con tres estrategias distintas. Cada script corre solo y
termina.

- `round_robin_load_balancer.py`: rota los backends en orden. Se espera ver los
  requests cayendo en `192.168.0.10`, `.11`, `.12`, `.10`, `.11` — uno tras otro,
  sin mirar quién los hizo.
- `hash_load_balancer.py`: hashea la clave de ruteo e imprime `Routing key`. Lo
  que hay que ver es que **el mismo `user_id` va siempre al mismo backend**; el
  request sin `user_id` usa el request entero como clave.
- `range_load_balancer.py`: particiona por rango de `user_id` (1-10, 11-20,
  21-30). Se espera ver `user_id=25` en el tercer backend, `user_id=35` cayendo a
  `default.example.com` por quedar fuera de rango, y el request sin `user_id`
  saliendo **sin reescribir** con el mensaje `No user ID found in request`.

## 03-polling

```bash
cd 03-polling
python3 polling-ec2.py
```

Flask en el puerto **5001**, escuchando en `0.0.0.0`. No necesita Docker ni base
de datos. Abrir <http://localhost:5001> — el `index.html` lo sirve el mismo
Flask, así que no hay que abrir el archivo a mano.

Se espera ver: al pedir la instancia, el frontend hace polling y el estado queda
en `pending` unos 15 segundos hasta pasar a `running` con una IP inventada
(`192.168.0.x`). Los 15 segundos son a propósito: son 3 stages de 5 s.

Smoke test sin browser:

```bash
curl -s -X POST http://localhost:5001/launch_ec2      # devuelve {"instance_id": "..."}
curl -s http://localhost:5001/instance_status/<id>    # pending -> running
```

Se corta con Ctrl+C. Ojo que corre con `debug=True`, así que deja dos procesos
(el reloader y el hijo): si quedó colgado, `pkill -f polling-ec2.py`.

## 04-streaming-logs

```bash
cd 04-streaming-logs
python3 streaming-logs.py
```

Flask en el puerto **5000**, sólo en `127.0.0.1`. Sin Docker ni base. Abrir
<http://localhost:5000>.

Se espera ver eventos de CI/CD apareciendo **de a uno cada 3 segundos** sin que
el browser vuelva a pedir nada: la conexión a `/stream` queda abierta con
`Content-Type: text/event-stream`. Ese es todo el punto del demo — si los
eventos aparecen todos juntos de golpe, no está streameando.

Smoke test sin browser (se corta solo a los 10 s):

```bash
curl -s --max-time 10 http://localhost:5000/stream
```

Mismo detalle que el 03 con `debug=True`: `pkill -f streaming-logs.py` si queda
algo vivo.

## 05-ws-chat-broadcasting

```bash
cd 05-ws-chat-broadcasting
python3 ws-chat-server.py
```

Un solo proceso levanta **dos** cosas: un `SimpleHTTPRequestHandler` en el puerto
**8000** que sirve el `index.html`, y el servidor WebSocket en el **8765**. Sin
Docker ni base. Abrir <http://localhost:8000> en **dos pestañas** — el frontend
tiene `ws://localhost:8765` hardcodeado, así que sólo funciona en local.

Se espera ver: cada pestaña entra con un nombre y las dos reciben el mensaje
`<usuario> has joined the chat` del usuario `System`; lo que escribe una aparece
en la otra al instante. Al cerrar una pestaña, la otra recibe el `has left the
chat`. Eso es el broadcast: el servidor manda a todos los sockets del set, no
sólo al que escribió.

## 06-db-connection-pool

```bash
cd 06-db-connection-pool
docker-compose up -d          # levanta counter_mysql en el puerto 3307
python3 pool-counter.py
python3 non-pool-counter.py
```

Necesita Docker. El compose buildea un `mysql:8.0` propio (`Dockerfile` +
`init_db.sql` como seed) con `--max-connections=150`, contenedor `counter_mysql`,
base `counter_db`, `root`/`password`. Esperar unos segundos a que MySQL termine
de inicializar antes de correr los scripts.

Los dos scripts hacen exactamente lo mismo — 200 threads incrementando un
contador — y sólo cambian de dónde sacan la conexión:

- `pool-counter.py`: usa el pool de `utils.py` (`pool_size=32`). Se espera
  `Final counter value: 200` y ningún error.
- `non-pool-counter.py`: abre una conexión nueva por thread. Cuando el demo
  funciona, se ven varias líneas
  `Error for user N: 1040 (HY000): Too many connections` y el
  `Final counter value` queda **por debajo de 200** (o sea, hubo incrementos
  perdidos).

Aviso honesto: **el fallo del `non-pool` no es determinista**. En 4 corridas
medidas acá, 3 terminaron en 200/200 sin un solo error y sólo 1 falló (27
errores, contador en 173). Las conexiones se abren y cierran tan rápido que
muchas veces nunca hay 150 vivas a la vez. Si sale limpio, correrlo de nuevo o
subir `num_users` en el script.

Para bajar la base: `docker-compose down` (con `-v` si además querés borrar el
volumen `mysql_data`).

## 07-ecommerce-cache-redis

```bash
cd 07-ecommerce-cache-redis
docker-compose up -d          # mysql:8.0 en 3308 + redis:latest en 6379
python3 ecommerce_cache_storage_hot_cold.py
```

Necesita Docker y levanta **dos** contenedores: MySQL (base `ecommerce`,
`root`/`password`, seed `init_db.sql` con 5 productos) y Redis. Esperar a que
MySQL inicialice; se verifica con:

```bash
docker-compose exec mysql mysql -uroot -ppassword -e "SELECT COUNT(*) FROM ecommerce.products"
```

El script simula 10 vistas de producto con pesos (el producto 1 se pide mucho más
que el 5). Se espera ver la primera vista de cada producto como
`not in cache, fetching from database (cold storage - MySQL)` en el orden de los
**10-20 ms**, y las repeticiones como
`found in cache (hot storage - Redis)` en **menos de 1,5 ms**. Cierra con el
conteo de vistas por producto.

Detalle importante: el cache tiene TTL de 3600 s, así que **la segunda corrida
seguida no muestra ni un solo miss** y parece que el demo no hace nada. Para
volver a ver la parte fría hay que vaciar Redis:

```bash
docker-compose exec redis redis-cli FLUSHALL
```

Bajar todo con `docker-compose down`.

## 08-cache_debounce

```bash
cd 08-cache_debounce
python3 cache_debounce.py
```

No abre puertos ni necesita nada levantado: los "servidores" son strings. Tira
100.000 requests simulados y los rutea al azar con una probabilidad fija.

Se espera ver el resumen final con `Requests to Cache` cerca del **30 %** y
`Requests to Database` cerca del **70 %**, que es el `CACHE_PERCENTAGE = 30` del
script. Los porcentajes bailan un poco en cada corrida porque el seed está
comentado; si se quiere el mismo número siempre, descomentar `RANDOM_SEED` al
final del archivo.

## 09-db-airline-booking-seats

```bash
cd 09-db-airline-booking-seats
docker-compose up -d          # levanta flight_booking_mysql en el puerto 3306
python3 approach1_forupdate.py
python3 approach2_forupdate_skip_locked.py
python3 approach3_forupdate_nowait.py
```

Necesita Docker. Contenedor `flight_booking_mysql` (`mysql:8.0`), base
`flight_db`, `root`/`password`, seed `init_db.sql`. `utils.py` tiene el
`db_config` compartido y el `SEAT_LAYOUT` (24 filas x ABCDEF = **144 asientos**).
Ojo: el `db_config` no declara puerto, así que va al 3306 de `localhost`, sea el
contenedor o un MySQL del sistema — el aviso de arriba aplica acá más que en
ningún lado.

Los tres scripts lanzan **150 usuarios concurrentes contra 144 asientos** y sólo
cambian cómo bloquean la fila:

- `approach1_forupdate.py` (`SELECT ... FOR UPDATE`): se espera **144 asignados,
  6 sin asiento**, ~0,56 s. Cada transacción espera el lock, el avión se llena.
- `approach2_forupdate_skip_locked.py` (`FOR UPDATE SKIP LOCKED`): **mismo
  resultado, 144 y 6**, pero ~0,21 s. En vez de esperar, cada uno agarra el
  siguiente asiento libre: ~2,7x más rápido sin perder asientos.
- `approach3_forupdate_nowait.py` (`FOR UPDATE NOWAIT`): **sólo 6 asignados y 144
  fallos** `Seat was locked`. No es un bug: `NOWAIT` aborta en vez de esperar, y
  como el script no reintenta, el avión queda casi vacío. Ese contraste es el
  punto de la clase.

Bajar con `docker-compose down` (`-v` si además querés borrar `mysql_data` y
volver a sembrar desde cero).

## 10-indexes_ids_postgresql

```bash
cd 10-indexes_ids_postgresql
docker-compose up -d          # postgres:13 (contenedor postgres-demo) en 5432
python3 indexes_emp.py
python3 ids_emp.py
```

Necesita Docker: `postgres:13`, base `employee_db`, `postgres`/`password`,
volumen `postgres_data`. No tiene seed SQL — las tablas las crean los scripts.

- `indexes_emp.py`: dropea la tabla, inserta ~10.000 empleados y corre la misma
  consulta por `emp_dob_month` **antes y después** de crear el índice. Se espera
  ver dos bloques (`Query sin index` / `Query con index`) con la misma cantidad de
  registros y el segundo tiempo más bajo.
- `ids_emp.py`: es el pesado. Recrea la base, inserta **100.000 filas en tres
  tablas** (PK por RUT, PK `SERIAL`, PK `UUID`), corre `VACUUM ANALYZE` y compara
  tiempos de búsqueda y tamaños de tabla e índice de las tres.
- `README.md` de la carpeta: los comandos `psql` sueltos (`EXPLAIN ANALYZE`,
  `REINDEX`, `VACUUM`, tamaño de índices) para hacer la parte manual en clase.

Dos advertencias sobre este proyecto, las dos serias:

1. Es el único que pide el **5432 pelado**, que es justo donde escucha cualquier
   PostgreSQL instalado en el sistema. Hay que liberarlo antes (ver arriba).
2. Los scripts van a `localhost:5432` y **son destructivos**: `indexes_emp.py`
   hace `DROP TABLE employees` y `ids_emp.py` hace `DROP DATABASE employee_db`.
   Si el 5432 lo está atendiendo un PostgreSQL del sistema en vez del
   contenedor, el destrozo va contra esa base. Verificar con `lsof` **antes** de
   correrlos.

Bajar con `docker-compose down`.

## 11-db-buffer-cache-postgresql

```bash
cd 11-db-buffer-cache-postgresql
docker-compose up -d          # postgres:13 (postgres-buffer-cache-demo) en 5433
docker-compose logs -f db     # esperar a que termine de cargar (~10 s la 1ra vez)
python3 buffer_cache_demo.py
```

Necesita Docker. Base `buffer_cache_db`, `postgres`/`password`, puerto **5433**
en el host (el 5432 es del proyecto 10). El `init_db.sql` genera ~1 GB de datos y
el compose fuerza `shared_buffers=256MB`, `track_io_timing=on` y `mem_limit=1g`
para que la evicción se pueda demostrar en un notebook.

El script corre la misma consulta en 5 fases. Lo que hay que mirar no son los
milisegundos (dependen de la máquina) sino la columna de **páginas leídas**: pasa
de **7040 → 0 → 7040** cuando el cache se llena, se calienta y se desaloja. Una
corrida medida acá dio 32,8 ms en frío contra 5,3 ms en caliente (**x6,2**) y
volvió a 30,0 ms después de la evicción.

El `README.md` de la carpeta tiene el detalle largo: qué hace cada fase, los
`EXPLAIN (ANALYZE, BUFFERS)` sueltos para psql, y por qué
`database system is ready to accept connections` aparece dos veces en el log
(conectarse en la primera hace fallar el script).

Bajar con `docker-compose down`, o `docker-compose down -v` para volver a
arrancar con el cache y los datos realmente en frío.

## 12-discord-chat-ws-api

```bash
cd 12-discord-chat-ws-api
python3 app.py
```

Flask en el puerto **5002**, escuchando en `0.0.0.0`. Sin Docker y sin base
externa: usa un SQLite (`chat.db`) que se crea y se siembra solo en la primera
corrida. Un solo proceso sirve el `index.html`, la API REST y el WebSocket.

Abrir **dos pestañas ya bautizadas**: <http://localhost:5002/?user=ana> y
<http://localhost:5002/?user=beto>. Sin `?user=` la página pide el nombre con un
`prompt()` del browser.

Un chat de verdad necesita **dos** canales de datos: el historial viaja por
`fetch` (el socket no te puede dar lo que pasó antes de que te conectaras) y lo
que pasa ahora viaja por WebSocket. Lo que hay que ver: al recargar, el contador
*en vivo por WS* queda en **0** y todos los mensajes tienen badge naranja
**API**; los que llegan después tienen badge verde **WS**. Con `cortar WS` y
`reconectar` se ve el hueco recuperándose por REST con `?after=`, y con el
`modo ingenuo` se ve el hueco que **no** se recupera nunca.

El `README.md` de la carpeta tiene el detalle largo: el guión de clase paso a
paso, el contrato de los frames y las limitaciones del prototipo.

Para volver a arrancar de cero: Ctrl+C y `rm chat.db` (parado en la carpeta del
proyecto, como todos los comandos de esta sección).

## 13-request-hedging

```bash
python3 backend.py     # terminal 1: servicio mock en 127.0.0.1:5003
python3 hedging.py     # terminal 2: el experimento, ~90 s
```

Sin Docker y sin base: `backend.py` es un `ThreadingHTTPServer` que simula 3
réplicas durmiendo una latencia sorteada (cuerpo rápido + 2% de cola larga), y
`hedging.py` corre 7 escenarios de 2500 requests y termina imprimiendo una tabla
comparativa y un histograma. No hay nada que abrir en el browser: la salida es la
terminal.

Lo que hay que ver: el p50 queda en 26 ms y el p99 en 487 ms (**18x**), y
mandando una copia del request a otra réplica cuando pasan 81 ms (el p95 que el
propio script mide) el p99 baja a 112 ms pagando **+4%** de trabajo del backend.
Después la tabla muestra el otro lado: con el backend saturado, ese mismo umbral
hedgea el 96% de los requests y empeora todo, y un *hedge budget* del 5% lo
contiene.

El `README.md` de la carpeta tiene los números de las tres corridas, la cuenta de
Dean & Barroso sobre por qué la cola importa a escala, y por qué esto sólo se
puede hacer con operaciones idempotentes.
