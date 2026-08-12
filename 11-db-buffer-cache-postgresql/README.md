# Buffer cache de PostgreSQL

## Que demuestra

Que **la segunda consulta vuela sin que nadie programe un cache**. La misma
query, con los mismos parametros y el mismo plan, pasa de ~30 ms a ~4 ms solo
porque PostgreSQL fue dejando las paginas de datos en su cache interno
(`shared_buffers`) y el sistema operativo las dejo en el suyo (page cache).

Aca no hay Redis ni memcached ni un diccionario en memoria: **el cache ya venia
con la base de datos**.

El script corre un guion por fases:

| Fase | Que hace | Que se ve |
|---|---|---|
| 0 | Llena `shared_buffers` con la tabla fria | El cache queda sin `productos` |
| 1 | Ejecuta la consulta por primera vez | `shared read` = todas las paginas |
| 2 | Repite la MISMA consulta 10 veces | `shared read` cae a 0, `shared hit` domina |
| 3 | Mira `pg_buffercache` por dentro | `productos` quedo 100% residente |
| 4 | Fuerza la evicion con la tabla grande | Vuelve a degradarse: el cache es finito |

### Numeros de referencia

Medidos en un MacBook con Docker Desktop, tres corridas seguidas:

| | corrida 1 | corrida 2 | corrida 3 |
|---|---|---|---|
| Consulta en frio | 32.6 ms | 32.7 ms | 32.7 ms |
| Consulta en caliente (avg de 10) | 3.5 ms | 3.8 ms | 3.8 ms |
| **Speedup** | **x9.3** | **x8.6** | **x8.6** |
| Tras desalojar el cache | 29.3 ms | 30.1 ms | 31.6 ms |

En las tres, las paginas leidas pasan de **7040 a 0** y vuelven a **7040**
despues de la evicion. Los milisegundos dependen de la maquina; los contadores
de paginas, no.

## Como levantarlo

```bash
docker-compose up -d

# la carga inicial (~1 GB de datos) toma unos 10 s; esperar a que termine
docker-compose logs -f db

python3 buffer_cache_demo.py
```

Ojo con la espera: `database system is ready to accept connections` aparece
**dos veces** en el log. La primera es el servidor temporal que corre
`init_db.sql` y solo escucha por socket, asi que si te conectas ahi el script
falla con `server closed the connection unexpectedly`. La buena es la que viene
despues de `PostgreSQL init process complete; ready for start up.`

La base queda en el **puerto 5433** del host (el 5432 lo usa el proyecto 10).

Para bajar todo y borrar los datos:

```bash
docker-compose down -v
```

## Que hay adentro

| Tabla | Tamano | Rol |
|---|---|---|
| `productos` | 55 MB (7040 paginas) | **caliente**: entra comoda en `shared_buffers` |
| `eventos` | 1016 MB (130000 paginas) | **fria**: 4x el cache, sirve para desalojar |

Decisiones del `docker-compose.yml` que vale la pena mirar:

- `shared_buffers=256MB` — chico a proposito, para que la evicion se pueda
  demostrar en un notebook.
- `track_io_timing=on` — sin esto `EXPLAIN (ANALYZE, BUFFERS)` no muestra
  cuanto tiempo se fue esperando I/O.
- `max_parallel_workers_per_gather=0` — apaga el paralelismo para que el plan
  sea siempre el mismo y las mediciones se puedan comparar.
- `mem_limit: 1g` — acota la RAM del contenedor. Como el page cache del SO vive
  dentro de ese limite, tambien se vuelve finito y se puede demostrar que hay
  **dos** caches, no uno. Bajarlo (por ejemplo a `640m`) hace que la fase 4
  llegue al disco de verdad mas seguido, pero las latencias se vuelven ruidosas
  porque el contenedor pasa a estar bajo presion de memoria.

Las filas son anchas (~1.5 kB, 5 filas por pagina) y las tablas no tienen
indices: la demo es sobre **leer paginas**, no sobre buscar por indice. Asi el
costo de la consulta se lo lleva el I/O y no la CPU por fila.

## Los dos niveles de cache (importante)

```
consulta -> shared_buffers (cache de PostgreSQL, 256 MB)
              |  miss
              v
            page cache del SO (lo que sobre del 1 GB del contenedor)
              |  miss
              v
            disco
```

Un `shared read` en `EXPLAIN` significa "no estaba en `shared_buffers`", **no**
significa "vino del disco": pudo venir del page cache del SO. Se distinguen por
la velocidad, y el resumen del script la calcula:

- varios **GB/s** -> salio del page cache del SO
- cientos de **MB/s** -> salio del disco de verdad

Consecuencia practica para la clase:

- `docker-compose restart db` vacia `shared_buffers` pero **no** vacia el page
  cache del SO. Los contadores muestran la consulta totalmente fria
  (`shared read` = las 7040 paginas), pero el I/O sigue a velocidad de RAM
  (medido: ~40 ms para 55 MB, o sea ~1.4 GB/s) y no a velocidad de disco.
- El frio de verdad se ve tras `docker-compose down -v && docker-compose up -d`,
  que borra el volumen y arranca todo de cero.

## Comandos psql utiles

Entrar:

```bash
docker-compose exec db psql -U postgres -d buffer_cache_db
```

1. Cuanto cache tiene configurado:

```sql
SHOW shared_buffers;
```

2. La consulta de la demo, con paginas y tiempo de I/O (correrla dos veces
   seguidas y comparar `read` vs `hit`):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*), avg(precio) FROM productos WHERE categoria = 'electronica';
```

3. Que hay dentro de `shared_buffers` ahora mismo:

```sql
SELECT c.relname,
       pg_size_pretty(count(*)::bigint * 8192) AS residente,
       pg_size_pretty(pg_relation_size(c.oid)) AS tamano_tabla
FROM pg_buffercache b
JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
WHERE b.reldatabase = (SELECT oid FROM pg_database WHERE datname = current_database())
GROUP BY c.relname, c.oid
ORDER BY count(*) DESC
LIMIT 10;
```

4. Hit ratio acumulado por tabla (lo que mirarias en produccion):

```sql
SELECT relname,
       heap_blks_read  AS leidas_de_disco,
       heap_blks_hit   AS desde_cache,
       round(100.0 * heap_blks_hit / nullif(heap_blks_hit + heap_blks_read, 0), 2) AS hit_ratio
FROM pg_statio_user_tables
ORDER BY heap_blks_hit + heap_blks_read DESC;
```

5. Hit ratio de toda la base:

```sql
SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0), 2) AS hit_ratio
FROM pg_stat_database
WHERE datname = current_database();
```

6. Forzar la evicion a mano (llena el cache con la tabla grande):

```sql
SELECT pg_prewarm('eventos');
```

7. Reiniciar los contadores acumulados antes de un experimento:

```sql
SELECT pg_stat_reset();
```

## Como repetir el experimento en frio

```bash
# frio parcial: vacia shared_buffers, NO el page cache del SO
docker-compose restart db

# frio total: borra el volumen y vuelve a cargar todo (~15 s)
docker-compose down -v && docker-compose up -d
```

El script tambien se puede correr N veces seguidas sin reiniciar nada: su fase 0
deja el cache sin `productos` con `pg_prewarm('eventos')`, asi cada corrida
arranca del mismo estado y los numeros son comparables. Eso es lo que hace que
la demo se pueda repetir en clase sin bajar el contenedor.

## Relacion con el proyecto 07

- **07 (`07-ecommerce-cache-redis`)**: cache **externo**. Lo pones tu, lo llenas
  tu, lo invalidas tu, y guarda el **resultado** de la consulta (un producto ya
  serializado). Sirve para saltarse la base de datos entera.
- **11 (este)**: cache **interno**. Ya existe, se llena solo, se desaloja solo y
  guarda **paginas de datos** de 8 kB, no resultados. La consulta igual se
  ejecuta: lo que se ahorra es el I/O.

La conclusion de diseno: antes de meter un Redis, medir. Si el `hit ratio` de la
base ya es alto y la query sigue lenta, el problema no era el cache (era el plan,
un indice que falta, o CPU). Y si el `hit ratio` es bajo, a veces la solucion mas
barata es darle mas RAM a la base, no agregar otra pieza de infraestructura al
sistema.
