"""Servicio mock de 3 replicas. Lo unico que importa de la respuesta es cuanto tardo.

El JSON que devuelve es inventado y no lo mira nadie: este backend existe para
tener una distribucion de latencia realista (un cuerpo rapido y una cola larga)
contra la cual medir la politica de hedging del cliente.

No usa Flask, y es a proposito: el server de Werkzeug manda `Connection: close`
en TODAS las respuestas (werkzeug/serving.py:299, "Always close the connection"),
o sea un socket TCP nuevo por request. Los ~25.000 requests del demo agotaban los
16.384 puertos efimeros de macOS y la corrida se moria con Errno 49 a mitad de la
proyeccion. ThreadingHTTPServer con HTTP/1.1 si hace keep-alive.
"""

import json
import math
import random
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 5003: el 5000 lo usa 04-streaming-logs, el 5001 el 03-polling y el 5002 el
# 12-discord-chat-ws-api, asi que los cuatro pueden correr a la vez.
PUERTO = 5003

REPLICAS = 3

# Sembrar por (seq, replica) hace la corrida reproducible y le da a cada replica
# un sorteo INDEPENDIENTE, que es la unica razon por la que hedgear sirve de algo.
# Sembrar por thread id parece razonable y es catastrofico: macOS reusa los ids
# (40 hilos dieron 2 ids distintos) y la cola larga desaparece sin avisar.
SEMILLA = 20250817

# Cuerpo rapido: un lookup en memoria sano. sigma 0.70 es la dispersion tipica
# de un servicio real y deja el p95 del cuerpo en ~3.7x la mediana.
CUERPO_MEDIANA_MS = 22.0
CUERPO_SIGMA = 0.70

# Cola larga: 2 de cada 100 requests caen sobre un disco lento o un vecino
# ruidoso. Es un sorteo INDEPENDIENTE por (request, replica): NO es una pausa de
# GC, que congelaria la replica entera y haria salir los hedges en rafaga. El
# README explica por que esa diferencia importa.
STALL_PROBABILIDAD = 0.02
STALL_MEDIANA_MS = 500.0
STALL_SIGMA = 0.40

# Capacidad de cada replica. 48 alcanza para que los escenarios SANOS no hagan
# cola NUNCA: el peor de ellos (duplicar todos los requests) llega a 41 simultaneos
# por replica (medido), asi que la unica variable en juego es la politica del
# cliente y no una congestion que nadie pidio.
WORKERS_POR_REPLICA = 48

_estado = threading.Lock()
_workers = WORKERS_POR_REPLICA
# Un semaforo por replica: si no hay worker libre, el request espera ADENTRO del
# backend y esa espera se SUMA a su propio trabajo, que es como funciona una cola
# de verdad. La congestion emerge sola, sin formula ni constante magica.
_puestos = [threading.Semaphore(WORKERS_POR_REPLICA) for _ in range(REPLICAS)]
_en_vuelo = [0] * REPLICAS
_servidos = [0] * REPLICAS


def latencia_ms(seq: int, replica: int) -> float:
    """Cuanto TRABAJO tiene este request en esta replica, en ms (sin contar la cola).

    Determinista: el mismo (seq, replica) da siempre el mismo valor, y dos
    replicas distintas del mismo request sortean por separado.
    """
    sorteo = random.Random(SEMILLA + seq * 16 + replica)
    ms = sorteo.lognormvariate(math.log(CUERPO_MEDIANA_MS), CUERPO_SIGMA)
    if sorteo.random() < STALL_PROBABILIDAD:
        ms += sorteo.lognormvariate(math.log(STALL_MEDIANA_MS), STALL_SIGMA)
    return ms


def trabajo(replica: int, seq: int) -> dict[str, object]:
    """Hace cola si la replica esta llena, tarda lo suyo y devuelve un JSON cualquiera."""
    with _estado:
        _en_vuelo[replica] += 1
        puestos = _puestos[replica]
    with puestos:
        time.sleep(latencia_ms(seq, replica) / 1000)
    with _estado:
        _en_vuelo[replica] -= 1
        # Se cuenta al TERMINAR: este contador es el trabajo que el backend
        # realmente hizo, incluido el de las copias que el cliente ya descarto.
        _servidos[replica] += 1
    return {"sku": f"SKU-{seq:05d}", "stock": 42, "precio": 19.99}


def escenario(workers: int) -> dict[str, object]:
    """Arranca un escenario: contadores en cero y esta capacidad en TODAS las replicas.

    Que se sature parejo es el punto: no es una replica lenta al azar (contra eso
    el hedging gana), es un mal dia completo. Se llama con el backend vacio, asi
    que recrear los semaforos es seguro.
    """
    global _workers
    with _estado:
        _workers = max(1, workers)
        _puestos[:] = [threading.Semaphore(_workers) for _ in range(REPLICAS)]
        _servidos[:] = [0] * REPLICAS
    return {"workers": _workers}


class Mock(BaseHTTPRequestHandler):
    """GET /trabajo?replica=&seq= | GET /stats | POST /escenario?workers=."""

    # Sin esto se habla HTTP/1.0 y el socket se cierra en cada respuesta.
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        ruta, args = self._pedido()
        if ruta == "/stats":
            with _estado:
                self._json({"servidos": sum(_servidos), "en_vuelo": sum(_en_vuelo),
                            "workers": _workers})
        elif ruta == "/trabajo":
            self._json(trabajo(int(args["replica"]) % REPLICAS, int(args["seq"])))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        ruta, args = self._pedido()
        if ruta == "/escenario":
            self._json(escenario(int(args["workers"])))
        else:
            self.send_error(404)

    def _pedido(self) -> tuple[str, dict[str, str]]:
        ruta, _, query = self.path.partition("?")
        return ruta, dict(urllib.parse.parse_qsl(query))

    def _json(self, cuerpo: dict[str, object]) -> None:
        # Content-Length es obligatorio: sin el, el cliente no sabe donde termina
        # la respuesta y el keep-alive se cae.
        datos = json.dumps(cuerpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args: object) -> None:
        """Silencio: ~25.000 lineas de log ensucian la cola de latencia que medimos."""


if __name__ == "__main__":
    # El backlog default (5) rechaza conexiones cuando los 96 hilos del cliente
    # abren su socket todos juntos al arrancar.
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer.daemon_threads = True
    print(f"servicio mock en http://127.0.0.1:{PUERTO} ({REPLICAS} replicas)")
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Mock).serve_forever()
