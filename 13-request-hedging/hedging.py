"""Request hedging: si la replica no contesto a los X ms, mandamos una copia a otra.

Tecnica de "The Tail at Scale" (Dean y Barroso, CACM 2013). El experimento corre
7 escenarios contra backend.py, mide la latencia que ve el CLIENTE y la compara
con el trabajo que el backend tuvo que hacer de verdad.

Se corre con el backend ya levantado:  python3 backend.py  &&  python3 hedging.py
"""

import http.client
import json
import math
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import NamedTuple

# Las constantes del modelo se importan del backend para que la cabecera que se
# proyecta en clase no mienta si alguien las toca.
from backend import (CUERPO_MEDIANA_MS, CUERPO_SIGMA, PUERTO, REPLICAS,
                     STALL_MEDIANA_MS, STALL_PROBABILIDAD, STALL_SIGMA,
                     WORKERS_POR_REPLICA)

BASE = f"http://127.0.0.1:{PUERTO}"

# Con 2500 muestras el p99 se apoya en 25 requests y el p99.9 en 3. Es el minimo
# defendible; subirla a 20000 da una corrida seria de ~6 minutos.
REQUESTS = 2500

# 32 requests logicos en vuelo. Hedgeando, cada uno puede tener 2 pedidos abiertos,
# y la copia perdedora sigue abierta mientras el driver ya arranco el siguiente:
# por eso el pool de envio tiene 3x. Con keep-alive son 96 conexiones TCP reusadas
# de punta a punta, no las ~25.000 que abria urllib.
CONCURRENCIA = 32
HILOS_DE_ENVIO = 3 * CONCURRENCIA

WARMUP = 200

# El mal dia: 2 workers por replica contra los 48 sanos. No es una replica lenta
# al azar (contra eso el hedging gana), es que TODAS estan mal a la vez.
WORKERS_SATURADO = 2

# Un plazo que no vence nunca: es como se expresa "sin hedging" sin agregar un if
# al corazon del demo.
SIN_HEDGE_MS = 3_600_000.0

# Los dos pools se crean UNA vez y se reusan en los 7 escenarios: un pool por
# request bloquearia al salir del `with` esperando a la copia perdedora (+2.8 s
# medidos) y se comeria entera la ganancia del hedging.
DRIVERS = ThreadPoolExecutor(CONCURRENCIA)
ENVIOS = ThreadPoolExecutor(HILOS_DE_ENVIO)

# Una conexion TCP por hilo de envio, reusada (keep-alive), que es lo que hace
# cualquier cliente HTTP real. urllib abre un socket NUEVO por request: con eso el
# demo agotaba los 16.384 puertos efimeros de macOS (TIME_WAIT dura 30 s) y moria
# con Errno 49 antes de imprimir la tabla, 8 de cada 11 corridas.
_conexiones = threading.local()


def pedir(seq: int, replica: int) -> None:
    """Un GET al backend. La respuesta se descarta: lo unico que importa es el tiempo."""
    con = getattr(_conexiones, "http", None)
    if con is None:
        con = _conexiones.http = http.client.HTTPConnection("127.0.0.1", PUERTO, timeout=60)
    try:
        con.request("GET", f"/trabajo?replica={replica}&seq={seq}")
        con.getresponse().read()
    except (http.client.HTTPException, OSError):
        # Una conexion rota no se reusa: se tira y que reviente arriba.
        con.close()
        _conexiones.http = None
        raise


class PresupuestoDeHedge:
    """Tope de hedges: no concede mas que `frac` de los requests vistos.

    Contrato: registrar() una vez por request (se hedgee o no) y conceder() solo
    cuando el hedge esta por dispararse.

    Es el freno de un lazo de realimentacion positiva: mas lento -> mas hedges ->
    mas carga -> mas lento. Sin tope ese lazo no converge.
    """

    def __init__(self, frac: float) -> None:
        self.frac = frac
        self.vistos = 0
        self.usados = 0
        self._lock = threading.Lock()

    def registrar(self) -> None:
        with self._lock:
            self.vistos += 1

    def conceder(self) -> bool:
        with self._lock:
            if self.usados < self.frac * self.vistos:
                self.usados += 1
                return True
            return False


def con_hedge(seq: int, delay_ms: float, tope: PresupuestoDeHedge) -> tuple[float, int, bool]:
    """Manda el request y devuelve (latencia_ms, pedidos_enviados, gano_la_copia).

    La tecnica entera son estas ocho lineas: si a los delay_ms la primera replica
    no contesto, sale una copia a OTRA replica y nos quedamos con la respuesta que
    llegue primero.

    Tres detalles que son la mitad de la clase:
    - el reloj NO se reinicia cuando sale la copia: el usuario empezo a esperar
      cuando salio la primera;
    - la copia perdedora NO se cancela. El backend ya la esta ejecutando y no se
      entera de que nos fuimos: la termina entera y la tira. Ese es el costo;
    - hay que LEER el resultado de la ganadora. Si no, un request que fallo entra
      en la tabla como una muestra rapida y perfecta, y nadie se entera.
    """
    replica = seq % REPLICAS  # round-robin: reparte parejo y la copia va a otra
    tope.registrar()
    t0 = time.perf_counter()
    primera = ENVIOS.submit(pedir, seq, replica)
    listas, _ = wait([primera], timeout=delay_ms / 1000)
    if listas or not tope.conceder():
        primera.result()
        return (time.perf_counter() - t0) * 1000, 1, False
    copia = ENVIOS.submit(pedir, seq, (replica + 1) % REPLICAS)
    listas, _ = wait([primera, copia], return_when=FIRST_COMPLETED)
    gano_copia = primera not in listas
    (copia if gano_copia else primera).result()
    (primera if gano_copia else copia).add_done_callback(lambda f: f.exception())
    return (time.perf_counter() - t0) * 1000, 2, gano_copia


class Escenario(NamedTuple):
    """Resultado de un escenario. `lat` viene ordenada de menor a mayor."""

    nombre: str
    lat: list[float]
    servidos: int
    hedgeados: int
    ganados: int
    saturado: bool


def correr(nombre: str, delay_ms: float, workers: int, frac: float) -> Escenario:
    """Corre REQUESTS requests con esa politica y devuelve lo medido.

    `workers` es la capacidad por replica del backend y `frac` el tope de hedges
    (1.0 = sin tope). El backend arranca el escenario en cero, asi que los
    contadores de trabajo servido son de este escenario solo.
    """
    print(f"  corriendo {nombre} ...", flush=True)
    postear(f"/escenario?workers={workers}")
    tope = PresupuestoDeHedge(frac)
    por_driver: list[list[tuple[float, int, bool]]] = [[] for _ in range(CONCURRENCIA)]

    def driver(d: int) -> None:
        # Lazo cerrado: cada driver manda el request siguiente recien cuando volvio
        # el anterior. Subestima la cola frente al trafico real (coordinated
        # omission) y lo decimos abajo de la tabla; a cambio la carga ofrecida no
        # se dispara sola y los 7 escenarios son comparables entre si.
        for seq in range(d, REQUESTS, CONCURRENCIA):
            por_driver[d].append(con_hedge(seq, delay_ms, tope))

    for f in [DRIVERS.submit(driver, d) for d in range(CONCURRENCIA)]:
        f.result()

    # Las copias perdedoras siguen corriendo del lado del backend: si leemos los
    # contadores antes de que terminen, subcontamos justo el trabajo desperdiciado
    # que el demo quiere mostrar. Con tope, por si alguna quedo colgada.
    limite = time.perf_counter() + 30
    while leer("/stats")["en_vuelo"] > 0 and time.perf_counter() < limite:
        time.sleep(0.05)

    medidas = [m for lista in por_driver for m in lista]
    return Escenario(
        nombre=nombre,
        lat=sorted(m[0] for m in medidas),
        servidos=leer("/stats")["servidos"],
        hedgeados=sum(1 for m in medidas if m[1] == 2),
        ganados=sum(1 for m in medidas if m[2]),
        saturado=workers < WORKERS_POR_REPLICA,
    )


def leer(ruta: str) -> dict[str, int]:
    """GET de un endpoint JSON del backend."""
    with urllib.request.urlopen(BASE + ruta, timeout=30) as r:
        stats: dict[str, int] = json.load(r)
    return stats


def postear(ruta: str) -> None:
    """POST a un endpoint de control del backend."""
    with urllib.request.urlopen(urllib.request.Request(BASE + ruta, data=b""), timeout=30) as r:
        r.read()


def pct(lat: list[float], q: float) -> float:
    """Percentil nearest-rank (sin interpolar) sobre una lista YA ordenada."""
    return lat[min(len(lat) - 1, int(q * len(lat)))]


ANCHO = 93
FILA = ("{n:<30}{p50:>6}{p95:>6}{p99:>7}{p999:>7}{mx:>7} | "
        "{backend:>7}{extra:>6}{hedge:>7}{gano:>7}")


def fila(e: Escenario) -> str:
    """Formatea un escenario como fila de la tabla."""
    n0 = "{:.0f}".format
    return FILA.format(
        n=e.nombre,
        p50=n0(pct(e.lat, 0.50)), p95=n0(pct(e.lat, 0.95)), p99=n0(pct(e.lat, 0.99)),
        p999=n0(pct(e.lat, 0.999)), mx=n0(e.lat[-1]), backend=e.servidos,
        extra=f"{(e.servidos / REQUESTS - 1) * 100:+.0f}%",
        hedge=f"{e.hedgeados / REQUESTS * 100:.1f}%",
        gano=f"{e.ganados / REQUESTS * 100:.1f}%")


def tabla(escenarios: list[Escenario], umbral: float) -> None:
    """Imprime los 7 escenarios, con una raya separando backend sano de backend roto."""
    rotos = [e for e in escenarios if e.saturado]
    print(f"\numbral de hedge = p95 MEDIDO en el escenario 1 = {umbral:.0f} ms (no esta hardcodeado)")
    print("=" * ANCHO)
    print(f"{'latencia que ve el CLIENTE (ms)':>63} | {'trabajo del BACKEND (requests)'}")
    print(FILA.format(n="ESCENARIO", p50="p50", p95="p95", p99="p99", p999="p99.9", mx="max",
                      backend="total", extra="extra", hedge="hedge", gano="gano"))
    print("-" * ANCHO)
    for e in escenarios:
        if e is rotos[0]:
            print("-" * ANCHO)
        print(fila(e))
    print("=" * ANCHO)
    print(f"""  total = requests que el backend EJECUTO entero. La copia perdedora no se cancela: es trabajo tirado.
  hedge = % de requests que mandaron copia; gano = % en que la copia llego primero (el resto se tiro).
  esc 5-7: mismo cliente, backend con la capacidad caida de {WORKERS_POR_REPLICA} a {WORKERS_SATURADO} workers por replica.
  El umbral de 5-7 sigue siendo {umbral:.0f} ms, el p95 del dia SANO. Bajo saturacion el p95 real es
    {pct(rotos[0].lat, 0.95):.0f} ms, o sea que ese umbral viejo hedgea el {rotos[1].hedgeados / REQUESTS * 100:.0f}%: es duplicar todo con otro nombre.
  El budget (esc 7) frena la espiral: p50 y carga vuelven a los de 5. Pero el p99 NO mejora, queda
    igual o peor que sin hedgear: con TODAS las replicas mal no hay adonde escapar. Ahi no se hedgea.
  lazo cerrado ({CONCURRENCIA} drivers): la tasa la fija la latencia, no al reves. Con trafico a tasa fija la
    cola seria PEOR (coordinated omission): estos numeros son la version OPTIMISTA.
  modelo determinista: las mismas {REQUESTS} latencias en cada corrida. p99 = 25 muestras, p99.9 = 3.
  PRECONDICION: solo se hedgea lo IDEMPOTENTE. Hedgear un POST que cobra una tarjeta la cobra dos veces.""")


CORTES = [25.0, 50.0, 100.0, 200.0, 400.0, 800.0]


def histograma(sin_hedge: Escenario, con: Escenario) -> None:
    """Imprime las dos distribuciones lado a lado, en escala log."""
    def contar(lat: list[float]) -> list[int]:
        bordes = [0.0, *CORTES, float("inf")]
        return [sum(1 for x in lat if a <= x < b) for a, b in zip(bordes, bordes[1:])]

    def barra(c: int) -> str:
        # Escala log: en lineal la cola es invisible, que es justamente por lo que
        # existen los percentiles.
        return "█" * round(34 * math.log10(c + 1) / math.log10(REQUESTS + 1))

    etiquetas = [f"{a:.0f}-{b:.0f} ms" for a, b in zip([0, *CORTES], CORTES)] + [f">{CORTES[-1]:.0f} ms"]
    izq, der = contar(sin_hedge.lat), contar(con.lat)
    print(f"\n  Distribucion de {REQUESTS} requests  (barra en escala LOG: en lineal la cola no se veria)\n")
    print(f"{'rango':>13}   {sin_hedge.nombre[3:]:<40}{con.nombre[3:]}")
    for etq, a, b in zip(etiquetas, izq, der):
        print(f"{etq:>13} |{barra(a):<34}| {a:>4}   |{barra(b):<34}| {b:>4}")
    cola = sum(izq[CORTES.index(200.0) + 1:]), sum(der[CORTES.index(200.0) + 1:])
    print(f"\n   cola (>200 ms):  SIN = {cola[0]} requests      CON = {cola[1]} requests\n")


def cabecera() -> None:
    """Imprime el modelo del servicio antes de los numeros."""
    print(f"""
modelo: {REPLICAS} replicas x {WORKERS_POR_REPLICA} workers. Cada replica sortea su latencia por separado (por eso
hedgear sirve) y la cola sale de un semaforo por replica, o sea que la espera se SUMA:
  {100 - STALL_PROBABILIDAD * 100:.0f}%  lognormal(mediana {CUERPO_MEDIANA_MS:.0f} ms, sigma {CUERPO_SIGMA})      <- cuerpo sano
   {STALL_PROBABILIDAD * 100:.0f}%  + lognormal(mediana {STALL_MEDIANA_MS:.0f} ms, sigma {STALL_SIGMA})  <- disco lento / vecino ruidoso
cliente: {REQUESTS} requests por escenario, {CONCURRENCIA} en vuelo (lazo cerrado)
medido aparte: el harness (sesgo de time.sleep + round-trip HTTP) suma ~4 ms parejos a TODA la
tabla, por eso el p50 que se ve abajo da 26 y no los 22 del modelo. No cambia ninguna comparacion.""")


def main() -> None:
    # Se pide levantar el backend aparte (y no lanzarlo como subproceso) porque en
    # clase se muestran las dos mitades: la politica del cliente y el servicio.
    try:
        leer("/stats")
    except urllib.error.URLError:
        print(f"No hay nadie escuchando en {BASE}. Levantalo primero:  python3 backend.py")
        return

    cabecera()
    # Warmup descartado: abrir las 96 conexiones y arrancar los hilos ensucia el p99.
    postear(f"/escenario?workers={WORKERS_POR_REPLICA}")
    for f in [ENVIOS.submit(pedir, s, s % REPLICAS) for s in range(REQUESTS, REQUESTS + WARMUP)]:
        f.result()

    sano, roto = WORKERS_POR_REPLICA, WORKERS_SATURADO
    base = correr("1  sin hedging (baseline)", SIN_HEDGE_MS, sano, 1.0)
    p95, p50 = pct(base.lat, 0.95), pct(base.lat, 0.50)
    escenarios = [
        base,
        correr(f"2  hedge @ p95 ({p95:.0f} ms)", p95, sano, 1.0),
        correr(f"3  hedge @ p50 ({p50:.0f} ms)", p50, sano, 1.0),
        correr("4  hedge @ 0 ms (duplicar)", 0.0, sano, 1.0),
        correr("5  SATURADO sin hedging", SIN_HEDGE_MS, roto, 1.0),
        correr(f"6  SATURADO hedge @ {p95:.0f} ms", p95, roto, 1.0),
        correr("7  SATURADO hedge + budget 5%", p95, roto, 0.05),
    ]
    postear(f"/escenario?workers={sano}")  # que no quede saturado despues del demo
    tabla(escenarios, p95)
    histograma(escenarios[0], escenarios[1])


if __name__ == "__main__":
    main()
