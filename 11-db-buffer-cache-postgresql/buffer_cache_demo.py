"""Demo: la segunda consulta vuela porque la base de datos ya tiene un cache.

Sin Redis, sin memcached, sin cache aplicativo. La MISMA consulta se ejecuta
varias veces y se vuelve mucho mas rapida sola, porque PostgreSQL va dejando las
paginas de datos en su cache interno (shared_buffers) y el SO las deja en su
page cache. El script mide la latencia y, sobre todo, cuenta PAGINAS: cuantas
vinieron del cache ('shared hit') y cuantas hubo que ir a buscar ('shared read').
"""

import time
from typing import NamedTuple

import psycopg2
from psycopg2.extensions import cursor as Cursor

DB_NAME = "buffer_cache_db"
DB_USER = "postgres"
DB_PASSWORD = "password"
DB_HOST = "localhost"
DB_PORT = "5433"

# La misma consulta y los mismos parametros en todas las fases: asi el plan de
# ejecucion no cambia y la unica variable es de donde salen las paginas.
CONSULTA = "SELECT count(*), avg(precio) FROM productos WHERE categoria = 'electronica'"

REPETICIONES = 10

# Tabla enorme que no cabe en shared_buffers. Solo existe para llenar el cache
# con otra cosa y dejar a 'productos' afuera.
TABLA_FRIA = "eventos"

ANCHO = 74


class Medicion(NamedTuple):
    """Resultado de una ejecucion de CONSULTA.

    ms_cliente incluye el viaje de ida y vuelta; ms_servidor es lo que reporta
    el propio PostgreSQL. paginas_hit son las que estaban en shared_buffers y
    paginas_read las que hubo que pedirle al SO (page cache o disco).
    """

    ms_cliente: float
    ms_servidor: float
    paginas_hit: int
    paginas_read: int
    ms_io: float


def medir(cursor: Cursor) -> Medicion:
    """Ejecuta CONSULTA una vez y devuelve latencia y contadores de paginas.

    Se mide con EXPLAIN (ANALYZE, BUFFERS) para que la latencia y el conteo de
    paginas vengan de la MISMA ejecucion. TIMING OFF evita el costo de medir
    cada fila, que distorsionaria la comparacion.
    """
    inicio = time.perf_counter()
    cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) {CONSULTA}")
    ms_cliente = (time.perf_counter() - inicio) * 1000
    plan = cursor.fetchone()[0][0]
    nodo = plan["Plan"]
    return Medicion(
        ms_cliente=ms_cliente,
        ms_servidor=plan["Execution Time"],
        paginas_hit=nodo["Shared Hit Blocks"],
        paginas_read=nodo["Shared Read Blocks"],
        # Solo aparece con track_io_timing=on (ver docker-compose.yml).
        ms_io=nodo.get("I/O Read Time", 0.0),
    )


def mb_por_segundo(m: Medicion) -> float:
    """Velocidad a la que llegaron las paginas que no estaban en shared_buffers.

    Delata de donde salieron: varios GB/s solo se explican por el page cache del
    SO; cientos de MB/s ya es el disco de verdad.
    """
    if not m.paginas_read or not m.ms_io:
        return 0.0
    return (m.paginas_read * 8192 / 1048576) / (m.ms_io / 1000)


def ocupacion_cache(cursor: Cursor) -> list[tuple[str, float, float]]:
    """(tabla, MB residentes en shared_buffers, MB totales de la tabla)."""
    cursor.execute(
        """
        SELECT c.relname,
               count(b.bufferid) * 8192 / 1048576.0,
               pg_relation_size(c.oid) / 1048576.0
        FROM pg_class c
        LEFT JOIN pg_buffercache b
               ON b.relfilenode = pg_relation_filenode(c.oid)
              AND b.reldatabase = (
                    SELECT oid FROM pg_database WHERE datname = current_database()
                  )
        WHERE c.relname IN ('productos', %s)
        GROUP BY c.relname, c.oid
        ORDER BY 2 DESC
        """,
        (TABLA_FRIA,),
    )
    return [(n, float(mb), float(tot)) for n, mb, tot in cursor.fetchall()]


def desalojar_productos_del_cache(cursor: Cursor) -> None:
    """Deja shared_buffers sin paginas de 'productos'.

    Carga la tabla fria entera con pg_prewarm: como no cabe, el algoritmo de
    reemplazo de PostgreSQL va botando lo que habia, incluido 'productos'.
    """
    cursor.execute(f"SELECT pg_prewarm('{TABLA_FRIA}')")
    cursor.fetchone()


def titulo(texto: str) -> None:
    print("\n" + "-" * ANCHO)
    print(f" {texto}")
    print("-" * ANCHO)


def encabezado_tabla() -> None:
    print(
        f"{'':22} {'latencia':>10} {'servidor':>10} "
        f"{'hit':>8} {'leidas':>8} {'I/O':>9}"
    )


def fila(etiqueta: str, m: Medicion, extra: str = "") -> None:
    print(
        f"{etiqueta:22} {m.ms_cliente:>7.1f} ms {m.ms_servidor:>7.1f} ms "
        f"{m.paginas_hit:>8} {m.paginas_read:>8} {m.ms_io:>6.1f} ms{extra}"
    )


def mostrar_ocupacion(cursor: Cursor) -> None:
    for nombre, mb, total in ocupacion_cache(cursor):
        pct = 100.0 * mb / total if total else 0.0
        print(f"  {nombre:12} {mb:7.1f} MB en cache  de {total:7.1f} MB  ({pct:5.1f}%)")


def contexto(cursor: Cursor) -> None:
    cursor.execute("SHOW shared_buffers")
    buffers = cursor.fetchone()[0]
    cursor.execute("SELECT current_setting('server_version')")
    version = cursor.fetchone()[0]

    print("=" * ANCHO)
    print(" El cache no siempre lo pones tu: la base de datos ya trae uno")
    print("=" * ANCHO)
    print(f"PostgreSQL     : {version}")
    print(f"shared_buffers : {buffers}   (cache interno de la BD)")
    for nombre, _, total in sorted(ocupacion_cache(cursor)):
        paginas = int(total * 1048576 / 8192)
        print(f"tabla {nombre:9}: {total:7.1f} MB  ({paginas} paginas de 8 kB)")
    print(f"consulta       : {CONSULTA}")


def fase_1_frio(cursor: Cursor) -> Medicion:
    titulo("FASE 1 - En frio: nadie ha consultado 'productos' todavia")
    print("Primera ejecucion. PostgreSQL no tiene ni una pagina de la tabla en")
    print("shared_buffers, asi que tiene que pedirlas todas afuera.\n")
    encabezado_tabla()
    m = medir(cursor)
    fila("1a ejecucion", m)
    print(f"\n=> {m.paginas_read} paginas de afuera, {m.paginas_hit} desde el cache.")
    print(f"=> {m.ms_io:.1f} de los {m.ms_servidor:.1f} ms se fueron esperando I/O.")
    return m


def fase_2_caliente(cursor: Cursor, frio: Medicion) -> list[Medicion]:
    titulo(f"FASE 2 - En caliente: la MISMA consulta, {REPETICIONES} veces mas")
    print("No cambiamos nada: misma query, mismos parametros, mismo plan.")
    print("Lo unico que cambio es que las paginas ya estan en shared_buffers.\n")
    encabezado_tabla()
    mediciones = []
    for i in range(1, REPETICIONES + 1):
        m = medir(cursor)
        mediciones.append(m)
        fila(f"repeticion {i}", m, extra=f"   x{frio.ms_cliente / m.ms_cliente:.1f}")
    print("\n=> 'leidas' cayo a 0 y ahora todas las paginas son 'hit'.")
    print("=> Nadie escribio una linea de cache: lo hizo la base de datos sola.")
    return mediciones


def fase_3_ocupacion(cursor: Cursor) -> None:
    titulo("FASE 3 - Que hay realmente dentro de shared_buffers")
    print("pg_buffercache deja mirar el cache por dentro, pagina por pagina.\n")
    mostrar_ocupacion(cursor)
    print("\n=> 'productos' fue subiendo al cache sola, a medida que la consultamos.")


def fase_4_eviccion(cursor: Cursor) -> Medicion:
    titulo("FASE 4 - El cache es finito: forzamos la evicion")

    print(f"4a) Primero un Seq Scan completo de '{TABLA_FRIA}' (la tabla gigante).\n")
    cursor.execute(f"SELECT count(*) FROM {TABLA_FRIA}")
    cursor.fetchone()
    mostrar_ocupacion(cursor)
    encabezado_tabla()
    fila("tras el Seq Scan", medir(cursor))
    print("\n=> Sorpresa: leer 1 GB no desalojo nada. 'productos' sigue 100% en el")
    print("   cache y sus paginas siguen siendo todas 'hit'. PostgreSQL escanea las")
    print("   tablas grandes con un 'ring buffer' de 256 kB justamente para que un")
    print("   reporte pesado no le tire el cache al resto del sistema.")
    print("   Ojo: la LATENCIA de esta fila no es comparable con las demas (el")
    print("   servidor viene de mover 1 GB); aca lo que vale son los contadores.")

    print(f"\n4b) Ahora forzamos: cargamos '{TABLA_FRIA}' entera a shared_buffers.\n")
    desalojar_productos_del_cache(cursor)
    mostrar_ocupacion(cursor)
    encabezado_tabla()
    tras_eviccion = medir(cursor)
    fila("tras la evicion", tras_eviccion)
    leidas = tras_eviccion.paginas_read
    print(f"\n=> 'productos' quedo en 0 MB y volvieron las {leidas} paginas leidas.")
    print("   La consulta se degrado de nuevo: el cache no es infinito, lo que")
    print("   entra bota a lo que estaba.")

    print("\n4c) Y si la volvemos a consultar, se vuelve a calentar sola.\n")
    encabezado_tabla()
    fila("recalentada", medir(cursor))
    return tras_eviccion


def resumen(frio: Medicion, calientes: list[Medicion], tras_eviccion: Medicion) -> None:
    promedio = sum(m.ms_cliente for m in calientes) / len(calientes)
    total_paginas = calientes[0].paginas_hit + calientes[0].paginas_read
    hit_ratio = 100.0 * calientes[0].paginas_hit / total_paginas

    titulo("RESUMEN")
    print(
        f"  Consulta en frio          : {frio.ms_cliente:7.1f} ms  "
        f"({frio.paginas_read} paginas leidas de afuera)"
    )
    print(
        f"  Consulta en caliente (avg): {promedio:7.1f} ms  "
        f"(0 paginas leidas, {hit_ratio:.0f}% hit ratio)"
    )
    print(f"  Speedup                   : x{frio.ms_cliente / promedio:.1f}")
    print(
        f"  Tras desalojar el cache   : {tras_eviccion.ms_cliente:7.1f} ms  "
        f"({tras_eviccion.paginas_read} paginas leidas de afuera)"
    )

    mb = frio.paginas_read * 8192 / 1048576
    print()
    print(
        f"  Las dos lecturas 'en frio' leyeron las mismas {frio.paginas_read} paginas "
        f"({mb:.0f} MB),"
    )
    print("  pero a distinta velocidad segun donde estaban:")
    print(
        f"    fase 1 (primera consulta) : {frio.ms_io:6.1f} ms de I/O "
        f"-> {mb_por_segundo(frio):6.0f} MB/s"
    )
    print(
        f"    fase 4 (tras la evicion)  : {tras_eviccion.ms_io:6.1f} ms de I/O "
        f"-> {mb_por_segundo(tras_eviccion):6.0f} MB/s"
    )
    print("  Varios GB/s = las paginas seguian en el page cache del SO. Cientos de")
    print("  MB/s = hubo que ir al disco de verdad. Mismo 'shared read', origenes")
    print("  distintos: abajo de shared_buffers hay OTRO cache.")
    print()
    print("  Por que pasa esto:")
    print("  1. PostgreSQL nunca lee del disco directo: copia cada pagina de 8 kB")
    print("     a shared_buffers y trabaja ahi. Si la pagina ya esta, es un 'hit'")
    print("     y se ahorra el viaje completo.")
    print("  2. Debajo hay un segundo cache, el page cache del SO, que tambien")
    print("     guarda esas paginas. Por eso un 'miss' de la BD no siempre llega")
    print("     al disco: shared_buffers -> page cache del SO -> disco.")
    print("  3. Los dos son finitos y de reemplazo automatico: lo que se consulta")
    print("     seguido se queda, lo que no, se va. Nadie invalida nada a mano.")
    print("  4. Moraleja: antes de montar un Redis, medi. Puede que el 'cache que")
    print("     te falta' ya lo tengas y lo que falte sea RAM o una mejor query.")


def main() -> None:
    conexion = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    )
    conexion.autocommit = True
    try:
        cursor = conexion.cursor()
        contexto(cursor)

        titulo("FASE 0 - Dejamos el cache realmente frio")
        print(f"Llenamos shared_buffers con '{TABLA_FRIA}' para que no quede ni una")
        print("pagina de 'productos'. Sin esto, la segunda corrida del script ya")
        print("arrancaria con el cache caliente y la fase 1 mentiria.")
        # Calienta el catalogo y el plan sin tocar las paginas de datos, para que
        # la medicion en frio mida solo la lectura de la tabla.
        cursor.execute(f"EXPLAIN {CONSULTA}")
        cursor.fetchall()
        desalojar_productos_del_cache(cursor)
        print()
        mostrar_ocupacion(cursor)

        frio = fase_1_frio(cursor)
        calientes = fase_2_caliente(cursor, frio)
        fase_3_ocupacion(cursor)
        tras_eviccion = fase_4_eviccion(cursor)
        resumen(frio, calientes, tras_eviccion)
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
