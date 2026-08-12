-- ---------------------------------------------------------------------------
-- Datos para demostrar el cache interno de PostgreSQL (shared_buffers).
--
-- Dimensionamiento (shared_buffers = 256MB):
--
--   * productos (~55 MB) entra COMODO en shared_buffers. Ademas se queda bajo
--     shared_buffers/4 (64 MB) a proposito: sobre ese umbral PostgreSQL escanea
--     con un "ring buffer" de 256 kB y la tabla NO se queda cacheada. Con 55 MB
--     el Seq Scan usa la estrategia normal y la tabla sube entera al cache.
--
--   * eventos (~1 GB) NO entra: casi 4x shared_buffers y mas grande que toda la
--     RAM del contenedor (mem_limit=1g). Existe solo para llenar los dos caches
--     con otra cosa y forzar la evicion de productos.
--
-- Las filas son anchas a proposito (~1.5 kB, 5 filas por pagina de 8 kB): asi el
-- costo de la consulta se lo lleva la LECTURA DE PAGINAS y no la CPU por fila,
-- que es justo el efecto que queremos medir.
--
-- Ninguna tabla lleva indices: la demo es sobre paginas de datos leidas por un
-- Seq Scan, no sobre busquedas por indice.
-- ---------------------------------------------------------------------------

-- Ver que paginas hay dentro de shared_buffers (fases 3 y 4 de la demo).
CREATE EXTENSION IF NOT EXISTS pg_buffercache;

-- Cargar una tabla entera a shared_buffers a la fuerza (fase 4 de la demo).
CREATE EXTENSION IF NOT EXISTS pg_prewarm;

-- Tabla CALIENTE: la que vamos a consultar una y otra vez.
CREATE TABLE productos AS
SELECT
    g                                                                          AS id,
    'Producto ' || g                                                           AS nombre,
    (ARRAY['electronica', 'hogar', 'ropa', 'juguetes', 'libros'])[1 + (g % 5)] AS categoria,
    ((g * 7919) % 100000) / 100.0                                              AS precio,
    (g * 13) % 500                                                             AS stock,
    repeat('descripcion larga del producto para el catalogo web. ', 28)        AS descripcion
FROM generate_series(1, 35200) AS g;

-- Tabla FRIA: gigante, solo existe para desalojar a productos de los caches.
CREATE TABLE eventos AS
SELECT
    g                                                                          AS id,
    1 + (g % 35200)                                                            AS producto_id,
    now() - ((g % 100000) * interval '1 second')                               AS creado_en,
    repeat('evento de navegacion registrado por el frontend web. ', 28)        AS payload
FROM generate_series(1, 650000) AS g;

ANALYZE productos;
ANALYZE eventos;

-- Bajar a disco lo recien escrito para que el estado inicial sea comparable.
CHECKPOINT;

SELECT
    relname                               AS tabla,
    pg_size_pretty(pg_relation_size(oid)) AS tamano,
    pg_relation_size(oid) / 8192          AS paginas
FROM pg_class
WHERE relname IN ('productos', 'eventos');
