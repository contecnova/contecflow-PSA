"""Interfaz del «motor de agente de código» y su registro (TICKET_A_PR.md §Diseño).

Un motor sabe hacer tres cosas sobre un árbol de ficheros, siempre dentro del
contenedor aislado (`sandbox`) y nunca en el host:

- `planificar`: agente de SOLO LECTURA; devuelve el plan (texto).
- `construir`: agente que edita; devuelve el árbol resultante y un resumen.
- `ejecutar_tests`: la orden de tests del repositorio sobre el árbol resultante.

El resto (Git, diff, PR, CAB, límites, auditoría) no depende del motor. OpenCode
es el primero (`opencode.py`); `MotorSimulado` es el de los tests (sin Docker ni
modelo). Cambiar de motor = registrar otra clase en `MOTORES`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.services.ticket_a_pr.diff import Arbol, Fichero
from app.services.ticket_a_pr.sandbox import Limites


@dataclass
class Modelo:
    """El modelo de la empresa (de su proveedor de IA). La clave solo viaja al contenedor."""
    proveedor: str                     # anthropic | openai | gemini | deepseek | groq | mistral | azure | ollama
    modelo: str
    api_key: str = ""
    base_url: str = ""
    provider_id: Optional[str] = None

    def __repr__(self) -> str:         # la clave nunca sale en un log
        return f"Modelo({self.proveedor}/{self.modelo})"


@dataclass
class Contexto:
    run_id: str
    instruccion: str
    arbol: Arbol
    modelo: Modelo
    imagen: str
    limites: Limites
    hosts_extra: list[tuple[str, int]] = field(default_factory=list)
    bash_permitido: list[str] = field(default_factory=list)
    max_bytes: int = 200 * 1024 * 1024          # tamaño máximo del árbol que devuelve el contenedor


@dataclass
class ResultadoMotor:
    ok: bool
    texto: str = ""
    arbol: Optional[Arbol] = None
    tokens_in: int = 0
    tokens_out: int = 0
    coste_usd: float = 0.0
    segundos: int = 0
    log: str = ""
    codigo: Optional[str] = None       # código del catálogo si falla
    params: dict = field(default_factory=dict)


class MotorDeAgente(ABC):
    nombre: str = ""

    @abstractmethod
    def planificar(self, ctx: Contexto) -> ResultadoMotor: ...

    @abstractmethod
    def construir(self, ctx: Contexto) -> ResultadoMotor: ...

    @abstractmethod
    def ejecutar_tests(self, ctx: Contexto, orden: str) -> ResultadoMotor: ...

    def hosts_propios(self) -> list[tuple[str, int]]:
        """Hosts que el motor necesita además del modelo (p. ej. su catálogo de modelos)."""
        return []


class MotorSimulado(MotorDeAgente):
    """Motor para los tests: no hay contenedor ni modelo.

    `cambios`: `{ruta: contenido | None}` que el «agente» aplica en BUILD
    (`None` borra). `plan`: el texto del plan. `fallo`: código para simular un error.
    Registra cada llamada en `llamadas` (fase, instrucción, imagen, solo lectura).
    """
    nombre = "simulado"

    def __init__(self, plan: str = "Cambiar app.py\nFICHEROS:\napp.py", cambios: Optional[dict] = None,
                 tests_ok: bool = True, fallo: Optional[str] = None, coste: float = 0.01, tokens=(1000, 200)):
        self.plan, self.cambios = plan, cambios if cambios is not None else {"app.py": b"print('arreglado')\n"}
        self.tests_ok, self.fallo, self.coste, self.tokens = tests_ok, fallo, coste, tokens
        self.llamadas: list[dict] = []

    def _base(self, ctx: Contexto, fase: str) -> Optional[ResultadoMotor]:
        self.llamadas.append({"fase": fase, "instruccion": ctx.instruccion, "imagen": ctx.imagen,
                              "ficheros": sorted(ctx.arbol.ficheros), "modelo": ctx.modelo.modelo})
        if self.fallo:
            return ResultadoMotor(False, codigo=self.fallo, log=f"fallo simulado en {fase}")
        return None

    def planificar(self, ctx: Contexto) -> ResultadoMotor:
        return self._base(ctx, "plan") or ResultadoMotor(
            True, texto=self.plan, tokens_in=self.tokens[0], tokens_out=self.tokens[1], coste_usd=self.coste,
            segundos=30, log="plan simulado")

    def construir(self, ctx: Contexto) -> ResultadoMotor:
        error = self._base(ctx, "build")
        if error:
            return error
        nuevo = Arbol(dict(ctx.arbol.ficheros))
        for ruta, contenido in self.cambios.items():
            if contenido is None:
                nuevo.ficheros.pop(ruta, None)
            elif isinstance(contenido, tuple):          # ("enlace", destino): simula un symlink
                nuevo.rechazados[ruta] = contenido[0]
            else:
                nuevo.ficheros[ruta] = Fichero(contenido if isinstance(contenido, bytes) else str(contenido).encode())
        return ResultadoMotor(True, texto="He cambiado lo que decía el plan.", arbol=nuevo,
                              tokens_in=self.tokens[0], tokens_out=self.tokens[1], coste_usd=self.coste,
                              segundos=120, log="build simulado")

    def ejecutar_tests(self, ctx: Contexto, orden: str) -> ResultadoMotor:
        self.llamadas.append({"fase": "tests", "orden": orden})
        return ResultadoMotor(self.tests_ok, texto="tests simulados", segundos=60, log="tests simulados")


def _opencode() -> MotorDeAgente:
    from app.services.ticket_a_pr.opencode import MotorOpenCode
    return MotorOpenCode()


#: Motores disponibles (nombre de la configuración → fábrica).
MOTORES: dict[str, Callable[[], MotorDeAgente]] = {"opencode": _opencode}

#: Los tests lo fijan (`forzar_motor`) para no depender de Docker ni del modelo.
_forzado: Optional[MotorDeAgente] = None


def forzar_motor(motor: Optional[MotorDeAgente]) -> None:
    global _forzado
    _forzado = motor


def obtener_motor(nombre: str) -> MotorDeAgente:
    if _forzado is not None:
        return _forzado
    fabrica = MOTORES.get(nombre)
    if fabrica is None:
        from app.core.codigos_de_error import ErrorConCodigo
        raise ErrorConCodigo("ticket_pr_motor_desconocido", motor=nombre[:40])
    return fabrica()


def motor_forzado() -> bool:
    return _forzado is not None
