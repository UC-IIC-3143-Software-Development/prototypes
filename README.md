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

| Proyecto | Puerto(s) | Cómo se levanta |
|---|---|---|
| 01-reverse-proxy | 8080 + backends | `python3 reverse_proxy.py` |
| 02-load_balancer | 8080 + backends | `python3 <estrategia>_load_balancer.py` |
| 03-polling | 5001 | `python3 polling-ec2.py` |
| 04-streaming-logs | 5000 | `python3 streaming-logs.py` |
| 05-ws-chat-broadcasting | 8000 (web) + 8765 (ws) | `python3 ws-chat-server.py` |
| 06-db-connection-pool | 3307 (mysql) | `docker-compose up -d` + `python3 pool-counter.py` |
| 07-ecommerce-cache-redis | 3308 (mysql) + 6379 (redis) | `docker-compose up -d` + `python3 ecommerce_cache_storage_hot_cold.py` |
| 08-cache_debounce | — | `python3 cache_debounce.py` |
| 09-db-airline-booking-seats | 3306 (mysql) | `docker-compose up -d` + `python3 approach1_forupdate.py` |
| 10-indexes_ids_postgresql | 5432 (postgres) | `docker-compose up -d` + `python3 indexes_emp.py` |
| 11-db-buffer-cache-postgresql | 5433 (postgres) | `docker-compose up -d` + `python3 buffer_cache_demo.py` |

Si un `docker-compose up` falla con `port is already allocated`, hay algo más
escuchando en ese puerto. Para ver qué es:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

Un PostgreSQL o un MySQL instalados en el sistema (no en Docker) son la causa
más común y hay que detenerlos antes de levantar los proyectos 10 y 11.
