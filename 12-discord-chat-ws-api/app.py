"""Chat tipo Discord: el historial viaja por REST y el tiempo real por WebSocket.

Los dos canales de datos contestan preguntas distintas: REST contesta "que paso"
(es consultable, paginable, reintentable) y el WebSocket contesta "que esta
pasando" (solo sabe del presente). El bug clasico no esta en ninguno de los dos
sino en la COSTURA: si el cliente pide el historial antes de suscribirse, todo lo
que se escriba en el medio no queda ni en el historial ni en el socket. El
frontend hace el orden correcto y deja ver la diferencia.

Un solo proceso y un solo puerto sirven HTTP y WS (el proyecto 05 ya muestra el
WS en un server aparte; aca el punto son los dos canales, no el deployment).
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_sock import ConnectionClosed, Sock

# Rutas atadas al archivo y no al cwd: si no, correr esto desde la raiz del repo
# crea el chat.db en el lugar equivocado y el index.html da 404.
HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "chat.db"

CHANNELS = [{"id": name, "name": name} for name in ("general", "random", "dev")]
CHANNEL_IDS = {c["id"] for c in CHANNELS}

FIELDS = "id, channel_id, author, text, ts"
DEFAULT_LIMIT, MAX_LIMIT, MAX_TEXT = 50, 100, 500

app = Flask(__name__, static_folder=None)
# Sin ordenar las claves alfabeticamente: el JSON crudo en el browser se lee en
# el orden del contrato (id, channel_id, author, text, ts).
app.json.sort_keys = False
sock = Sock(app)

# Cada conexion WS corre en su propio thread, asi que este dict lo tocan N
# threads a la vez. Un unico lock global serializa las dos secuencias que
# sostienen el demo: [insertar -> leer el id -> difundir] y [suscribir -> leer
# latest_id]. Sin eso dos mensajes concurrentes pueden salir en orden invertido
# (el 130 antes que el 129) y el merge por id del cliente deja de ser correcto.
_lock = threading.Lock()
_subs: dict[Any, tuple[str, str]] = {}  # ws -> (usuario, canal suscripto)


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """Conexion sqlite de un solo uso, ya commiteada al salir.

    Una por operacion a proposito: las conexiones de sqlite no se pueden
    compartir entre threads y aca cada request y cada WS es un thread distinto.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _iso(moment: datetime) -> str:
    """ISO-8601 UTC con Z. El ts es solo para mostrar: el orden lo da el id."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db() -> None:
    """Crea el schema y siembra la conversacion si la base esta vacia.

    Idempotente: el server se puede levantar dos veces sin duplicar nada.
    """
    with _db() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " channel_id TEXT NOT NULL, author TEXT NOT NULL,"
            " text TEXT NOT NULL, ts TEXT NOT NULL)"
        )
        # La paginacion por cursor es un seek por este indice: cuesta lo mismo
        # la pagina 1 que la pagina 200, al reves que un OFFSET.
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_id ON messages(channel_id, id)"
        )
        if con.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0:
            _seed(con)


def _seed(con: sqlite3.Connection) -> None:
    """Inserta la conversacion inicial del modulo SEED, canal por canal.

    Textos, orden e ids son fijos para que la demo de lo mismo en toda maquina.
    Los ts se escalonan hacia atras desde el arranque para que el historial se
    lea como una charla reciente; nada del protocolo depende de ellos.
    """
    rows = [
        (channel, author, text) for channel in SEED for author, text in SEED[channel]
    ]
    start = datetime.now(timezone.utc) - timedelta(seconds=90 * len(rows))
    con.executemany(
        "INSERT INTO messages (channel_id, author, text, ts) VALUES (?, ?, ?, ?)",
        [
            (channel, author, text, _iso(start + timedelta(seconds=90 * i)))
            for i, (channel, author, text) in enumerate(rows)
        ],
    )


def _page(
    channel_id: str, before: int | None, after: int | None, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    """Devuelve (mensajes, has_more) SIEMPRE en orden ascendente por id.

    `after` recupera hacia adelante (el hueco de una reconexion); `before`
    recupera hacia atras (scroll); sin cursor son los mas nuevos del canal.
    El servidor se come el ORDER BY DESC + invertir para que el cliente reciba
    siempre ascendente y los tres modos compartan el mismo render.
    """
    select = f"SELECT {FIELDS} FROM messages WHERE channel_id=?"
    with _db() as con:
        if after is not None:
            sql = f"{select} AND id>? ORDER BY id ASC LIMIT ?"
            rows = con.execute(sql, (channel_id, after, limit + 1)).fetchall()
        elif before is not None:
            # OJO: aca ORDER BY id ASC devolveria los mas viejos DEL CANAL, no
            # los mas cercanos al cursor. Por eso DESC y despues se invierte.
            sql = f"{select} AND id<? ORDER BY id DESC LIMIT ?"
            rows = con.execute(sql, (channel_id, before, limit + 1)).fetchall()[::-1]
        else:
            sql = f"{select} ORDER BY id DESC LIMIT ?"
            rows = con.execute(sql, (channel_id, limit + 1)).fetchall()[::-1]
    has_more = len(rows) > limit
    if has_more:  # se pidio uno de mas justo para saberlo; la sobrante se tira
        rows = rows[1:] if after is None else rows[:-1]
    return [dict(r) for r in rows], has_more


def _latest_id(channel_id: str) -> int | None:
    """Id del ultimo mensaje del canal, o None si esta vacio."""
    with _db() as con:
        sql = "SELECT MAX(id) FROM messages WHERE channel_id=?"
        latest: int | None = con.execute(sql, (channel_id,)).fetchone()[0]
        return latest


def _insert(channel_id: str, author: str, text: str) -> dict[str, Any]:
    """Persiste el mensaje y lo devuelve ya con el id que le puso el servidor."""
    ts = _iso(datetime.now(timezone.utc))
    with _db() as con:
        cur = con.execute(
            "INSERT INTO messages (channel_id, author, text, ts) VALUES (?, ?, ?, ?)",
            (channel_id, author, text, ts),
        )
        return {
            "id": cur.lastrowid,
            "channel_id": channel_id,
            "author": author,
            "text": text,
            "ts": ts,
        }


@app.get("/")
def index() -> Any:
    return send_from_directory(HERE, "index.html")


@app.get("/api/channels")
def channels() -> Any:
    """Lista de canales. Sin contadores ni ultimo mensaje: no hacen al punto."""
    return jsonify(channels=CHANNELS)


def _limit() -> int:
    """`limit` del querystring, clampeado a 1..100 (default 50).

    Nunca falla: un limit ilegible o fuera de rango se acomoda en vez de ser un
    error mas que el cliente tenga que manejar.
    """
    try:
        wanted = int(request.args.get("limit", DEFAULT_LIMIT))
    except ValueError:
        wanted = DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, wanted))


@app.get("/api/channels/<channel_id>/messages")
def messages(channel_id: str) -> Any:
    """Historial paginado por cursor: ?before=<id>, ?after=<id> o sin cursor.

    Responde {channel_id, messages (ascendente), has_more}. Solo hay dos
    errores, a proposito: canal inexistente (404) y cursor no entero o los dos
    cursores en el mismo request (400).
    """
    if channel_id not in CHANNEL_IDS:
        return jsonify(error="canal desconocido"), 404
    raw_before, raw_after = request.args.get("before"), request.args.get("after")
    if raw_before is not None and raw_after is not None:
        return jsonify(error="cursor invalido"), 400
    try:
        before = int(raw_before) if raw_before is not None else None
        after = int(raw_after) if raw_after is not None else None
    except ValueError:
        return jsonify(error="cursor invalido"), 400
    # int() acepta enteros de cualquier tamano, sqlite solo de 64 bits: sin este
    # corte un cursor gigante sale por OverflowError (500) en vez de este 400.
    if any(c is not None and abs(c) >= 2**63 for c in (before, after)):
        return jsonify(error="cursor invalido"), 400
    found, has_more = _page(channel_id, before, after, _limit())
    return jsonify(channel_id=channel_id, messages=found, has_more=has_more)


def _deliver(ws: Any, frame: dict[str, Any]) -> bool:
    """Manda un frame a una conexion. False si ya estaba muerta."""
    try:
        ws.send(json.dumps(frame))
        return True
    except (ConnectionClosed, OSError):
        # OSError (BrokenPipeError) cae en la ventana entre que el peer manda RST
        # y la libreria marca la conexion cerrada. Si se escapara de aca subiria
        # por _broadcast hasta el loop del que ESCRIBIO, o sea que cerrar una
        # pestana en el momento justo desconectaria a otro.
        return False


def _members(channel_id: str) -> list[str]:
    """Roster del canal. Se llama con _lock tomado."""
    return sorted({user for user, channel in _subs.values() if channel == channel_id})


def _broadcast(channel_id: str, frame: dict[str, Any]) -> None:
    """Difunde a los suscriptos del canal. Se llama con _lock tomado.

    El filtro por canal esta aca y no en el cliente: a una conexion que mira
    otro canal el frame ni siquiera le sale.
    """
    dead = []
    for ws, (_, channel) in _subs.items():
        if channel == channel_id and not _deliver(ws, frame):
            dead.append(ws)
    for ws in dead:
        _subs.pop(ws, None)


def _presence(channel_id: str, event: str, user: str) -> dict[str, Any]:
    """Frame de presencia con el roster completo. Se llama con _lock tomado.

    Va el roster entero ademas del evento para que el cliente repinte la lista
    sin diffear nada, y el evento para poder escribir "beto salio" en el log.
    """
    return {
        "type": "presence",
        "channel_id": channel_id,
        "event": event,
        "user": user,
        "members": _members(channel_id),
    }


def _subscribe(ws: Any, user: str, channel_id: str) -> None:
    """Mueve la conexion al canal y le contesta `subscribed` con latest_id.

    latest_id se lee DENTRO del lock, en el mismo instante en que la conexion
    entra al set de suscriptos. Ese es el contrato que le permite al cliente
    mergear sin adivinar: todo id <= latest_id lo tiene que pedir por REST,
    todo id mayor le va a llegar por este socket.
    """
    if channel_id not in CHANNEL_IDS:
        _deliver(ws, {"type": "error", "detail": "canal desconocido"})
        return
    with _lock:
        previous = _subs.get(ws, ("", ""))[1]
        _subs[ws] = (user, channel_id)
        _deliver(
            ws,
            {
                "type": "subscribed",
                "channel_id": channel_id,
                "latest_id": _latest_id(channel_id),
                "members": _members(channel_id),
            },
        )
        if previous and previous != channel_id:
            _broadcast(previous, _presence(previous, "leave", user))
        _broadcast(channel_id, _presence(channel_id, "join", user))


def _send_message(ws: Any, user: str, frame: dict[str, Any]) -> None:
    """Escribe el mensaje del frame `send` y lo difunde al canal.

    El emisor tambien lo recibe por el socket (no se pinta local): asi se ve que
    el id lo pone el servidor y que el mensaje propio volvio por el mismo camino
    que el de los demas.
    """
    text = str(frame.get("text") or "").strip()
    if not text or len(text) > MAX_TEXT:
        detail = f"mensaje vacio o de mas de {MAX_TEXT} caracteres"
        _deliver(ws, {"type": "error", "detail": detail})
        return
    with _lock:
        # El canal viaja en el frame aunque el server ya lo sepa: si el usuario
        # cambio de canal justo antes, el mensaje se rechaza en vez de publicarse
        # en el canal equivocado. Canal vacio = todavia no se suscribio, y ahi el
        # mensaje no tiene donde ir (escribirlo dejaria filas que ningun GET ve).
        channel_id = _subs.get(ws, ("", ""))[1]
        if not channel_id or frame.get("channel_id") != channel_id:
            _deliver(ws, {"type": "error", "detail": "no estas suscripto a ese canal"})
            return
        message = _insert(channel_id, user, text)
        _broadcast(channel_id, {"type": "message", "message": message})


def _read(ws: Any) -> dict[str, Any] | None:
    """Bloquea hasta el proximo frame y lo devuelve como dict, o None si es basura.

    Un frame ilegible tiene que costar un `error` y no la conexion: en clase el
    primer `ws.send("hola")` desde la consola del browser seria tambien el
    ultimo, porque la excepcion mata el thread de esa conexion.
    """
    try:
        frame = json.loads(ws.receive())
    except json.JSONDecodeError:
        return None
    return frame if isinstance(frame, dict) else None


def _leave(ws: Any) -> None:
    """Saca la conexion y avisa al canal que el usuario se fue."""
    with _lock:
        user, channel_id = _subs.pop(ws, ("", ""))
        if channel_id:
            _broadcast(channel_id, _presence(channel_id, "leave", user))


@sock.route("/ws")
def gateway(ws: Any) -> None:
    """Gateway del chat en ws://.../ws?user=<nombre>.

    Una conexion esta suscripta a exactamente un canal a la vez: un `subscribe`
    nuevo reemplaza al anterior, por eso no hay frame `unsubscribe` y por eso la
    presencia es por canal. No hay heartbeat propio (el browser y el protocolo
    ya lo hacen) ni frame de resume: el hueco se recupera por REST con ?after=,
    que es justamente el punto del proyecto.
    """
    user = (request.args.get("user") or "").strip()[:20] or "anon"
    with _lock:
        _subs[ws] = (user, "")
    try:
        while True:
            frame = _read(ws)
            if frame is None:
                _deliver(ws, {"type": "error", "detail": "frame ilegible"})
            elif frame.get("type") == "subscribe":
                _subscribe(ws, user, str(frame.get("channel_id") or ""))
            elif frame.get("type") == "send":
                _send_message(ws, user, frame)
            else:
                # En una demo en vivo el silencio es peor que un error.
                _deliver(ws, {"type": "error", "detail": "frame desconocido"})
    except ConnectionClosed:
        pass  # el cliente se fue; limpia el finally
    finally:
        _leave(ws)


SEED: dict[str, list[tuple[str, str]]] = {
    "general": [
        ("ana", "buenas, abro el hilo para organizar la entrega"),
        ("beto", "hola ana"),
        ("caro", "buenas gente"),
        ("dami", "presente"),
        ("ana", "la idea es cerrar el alcance hoy y no llegar al viernes corriendo"),
        ("beto", "de acuerdo, ya perdimos una semana"),
        ("caro", "yo arranque con el diagrama de componentes"),
        ("ana", "pasalo cuando lo tengas asi lo miramos entre todos"),
        ("dami", "consulta, entra el tema de caches en la entrega?"),
        ("euge", "entra, lo vimos la clase pasada"),
        ("dami", "uf, justo me la perdi"),
        ("euge", "te paso los apuntes, no es tanto"),
        ("ana", "punto 1: que guardamos en la base y que en memoria"),
        ("beto", "todo lo que se lee mucho y cambia poco va a cache"),
        ("caro", "el catalogo de productos entonces"),
        ("beto", "exacto, y el carrito no"),
        ("dami", "por que el carrito no?"),
        ("beto", "porque cambia todo el tiempo y es distinto para cada usuario"),
        ("dami", "ah cierto, no lo habia pensado asi"),
        ("ana", "lo anoto"),
        ("euge", "ojo que si cachean mal despues aparecen precios viejos"),
        ("caro", "eso nos paso en el tp anterior jaja"),
        ("beto", "no me lo recuerdes"),
        ("ana", "punto 2: cuantos usuarios asumimos"),
        ("caro", "pongamos mil concurrentes"),
        ("euge", "mil es mucho para una demo"),
        ("caro", "pero para el calculo sirve"),
        ("ana", "ponemos mil en el informe y aclaramos que la demo corre con dos"),
        ("beto", "me parece bien"),
        ("dami", "y la base? una sola?"),
        ("ana", "una sola, con replica de lectura si llegamos"),
        ("euge", "la replica es media hora, yo la haria"),
        ("beto", "media hora tuya o media hora nuestra"),
        ("euge", "jaja"),
        ("caro", "subo el diagrama en un rato, me falta la parte de colas"),
        ("ana", "genial"),
        ("dami", "alguien esta mirando lo del websocket?"),
        ("beto", "yo, es para las notificaciones"),
        ("dami", "y no alcanza con preguntar cada 5 segundos?"),
        ("beto", "alcanza, pero le pegas a la api todo el tiempo al pedo"),
        ("euge", "con mil usuarios son 200 requests por segundo de nada"),
        ("dami", "ok ok, me convencieron"),
        ("ana", "igual el historial lo seguis pidiendo por http eh"),
        ("dami", "por que?"),
        ("ana", "el socket te da lo de ahora, no lo que paso antes de conectarte"),
        ("beto", "esa es la parte que siempre se olvida"),
        ("caro", "literal, el bug del tp pasado fue ese"),
        ("euge", "y no se nota hasta que recargas la pagina"),
        ("dami", "buenisimo, ahora si lo entendi"),
        ("ana", "punto 3: quien escribe cada parte del informe"),
        ("caro", "yo hago los diagramas"),
        ("beto", "yo la parte de datos"),
        ("euge", "yo reviso todo al final"),
        ("dami", "yo armo las conclusiones"),
        ("ana", "perfecto, junto todo el jueves"),
    ],
    "random": [
        ("caro", "alguien vio que el ascensor sigue roto"),
        ("dami", "hace tres semanas ya"),
        ("beto", "es un sistema distribuido, esta eventualmente arreglado"),
        ("caro", "jajaja"),
        ("euge", "hoy hay feria de comida en el patio"),
        ("ana", "voy"),
        ("dami", "yo tambien"),
        ("beto", "avisen y bajo"),
        ("euge", "arranca 12 y media"),
        ("caro", "dale"),
        ("dami", "lleven efectivo que no hay senal para pagar"),
        ("ana", "clasico"),
    ],
    "dev": [
        ("beto", "me tira error cuando levanto el server"),
        ("euge", "que dice exacto"),
        ("beto", "address already in use"),
        ("euge", "tenes otra cosa escuchando en ese puerto"),
        ("euge", "fijate con lsof -nP -iTCP:5002 -sTCP:LISTEN"),
        ("beto", "era el server de ayer que quedo colgado"),
        ("euge", "clasico"),
        ("caro", "a mi sqlite me tiraba que no lo puedo usar desde otro thread"),
        ("euge", "cada conexion corre en su propio thread, abri la conexion adentro"),
        ("caro", "listo, ahora anda"),
    ],
}


if __name__ == "__main__":
    init_db()
    # 5002: el 5000 lo usa 04-streaming-logs y el 5001 el 03-polling, asi que
    # los tres pueden correr a la vez. Ver la tabla de puertos del README raiz.
    #
    # use_reloader=False aunque haya debug: al guardar este archivo el reloader
    # reinicia y patea TODAS las conexiones WS abiertas, o sea que el chat se
    # muere en el medio de la clase sin explicacion.
    app.run(host="0.0.0.0", port=5002, debug=True, use_reloader=False, threaded=True)
