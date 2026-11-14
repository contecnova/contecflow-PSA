"""Catálogo tipado de campos que cada dominio registra (tarea #26).

El motor NO conoce ningún dominio. Un dominio (gastos, ausencias, compras…) se
registra con `registrar(Dominio(...))` y declara:

- sus campos, cada uno con tipo, operadores y de dónde salen sus valores
  (lista cerrada, selector de entidad, importe con moneda, fecha, número,
  texto, país, ciudad, sí/no);
- cómo convertir una entidad suya en un CONTEXTO (`contexto`): un diccionario
  con el valor de cada campo y los atributos del sujeto (quién pide) para el
  ámbito de la política;
- cómo cargar una entidad, listar las históricas (simulador), saber de quién
  es (explicación) y, opcionalmente, qué campos se pueden fijar
  (`set_field`) y cómo comprobar los requisitos (justificante, justificación).

Ver `dominios/gastos.py` como ejemplo completo, y DOCS.md («Motor de
políticas») para registrar un dominio nuevo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from app.core.errores import ErrorDeDominio

#: Tipos de campo y los operadores que admite cada uno (el primero es el de
#: por defecto en la pantalla). La lista es la que la pantalla ofrece; un campo
#: puede restringirla con `Campo.operadores`.
OPERADORES_POR_TIPO: dict[str, tuple[str, ...]] = {
    "importe": ("gt", "gte", "lt", "lte", "eq", "ne", "between", "pct_over"),
    "numero": ("gt", "gte", "lt", "lte", "eq", "ne", "between", "in", "not_in", "pct_over"),
    "texto": ("eq", "ne", "contains", "not_contains", "in", "not_in", "empty", "not_empty"),
    "enum": ("eq", "ne", "in", "not_in"),
    "entidad": ("eq", "ne", "in", "not_in", "empty", "not_empty"),
    "fecha": ("eq", "lt", "lte", "gt", "gte", "between", "weekday_in", "weekday_not_in"),
    "pais": ("eq", "ne", "in", "not_in", "empty", "not_empty"),
    "ciudad": ("eq", "ne", "in", "not_in", "empty", "not_empty"),
    "booleano": ("eq",),
}

#: Operadores que no llevan valor, y los que llevan dos.
SIN_VALOR = {"empty", "not_empty"}
DOS_VALORES = {"between"}
LISTA = {"in", "not_in", "weekday_in", "weekday_not_in"}

#: Clases de entidad que la pantalla sabe elegir con su selector.
ENTIDADES = ("usuario", "proyecto", "cliente", "rol", "departamento", "equipo", "grupo")


@dataclass(frozen=True)
class Opcion:
    valor: str
    etiqueta: str


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    tipo: str                                    # una clave de OPERADORES_POR_TIPO
    operadores: tuple[str, ...] = ()             # vacío: los del tipo
    opciones: tuple[Opcion, ...] = ()            # con tipo enum
    entidad: Optional[str] = None                # con tipo entidad: una de ENTIDADES
    ayuda: Optional[str] = None
    asignable: bool = False                      # lo puede fijar un resultado `set_field`
    categoria_de_tabla: bool = False             # su valor es la «categoría» al buscar en una tabla

    def __post_init__(self):
        if self.tipo not in OPERADORES_POR_TIPO:
            raise ValueError(f"tipo de campo desconocido: {self.tipo}")
        if self.tipo == "entidad" and self.entidad not in ENTIDADES:
            raise ValueError(f"campo {self.clave}: entidad desconocida {self.entidad}")

    @property
    def ops(self) -> tuple[str, ...]:
        return self.operadores or OPERADORES_POR_TIPO[self.tipo]

    def a_dict(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "tipo": self.tipo, "operadores": list(self.ops),
                "opciones": [{"valor": o.valor, "etiqueta": o.etiqueta} for o in self.opciones],
                "entidad": self.entidad, "ayuda": self.ayuda, "asignable": self.asignable}


@dataclass
class Dominio:
    """Lo que un dominio aporta al motor. Los `Callable` reciben `db` primero.

    - `contexto(db, entidad) -> dict`: {clave_de_campo: valor, …} más
      `_sujeto` ({usuario_id, rol, departamento, equipo, pais, ciudad}) y
      `_fecha` (la fecha de la entidad: vigencias y tipo de cambio).
      Un importe es {"cantidad": float, "moneda": "EUR"}.
    - `cargar(db, entidad_id) -> entidad | None` (ya acotada por empresa).
    - `historicos(db, desde, hasta, limite) -> list[entidad]` para el simulador.
    - `propietario(entidad) -> user_id` y `resumen(entidad) -> str`.
    - `cumple_requisito(db, entidad, resultado) -> bool` (opcional): si un
      `require_justification` / `require_attachment` ya se cumple.
    - `aplicar_campo(db, entidad, campo, valor)` (opcional): aplica `set_field`.
    """
    clave: str
    etiqueta: str
    campos: list[Campo]
    contexto: Callable[[Any, Any], dict]
    cargar: Callable[[Any, str], Any]
    historicos: Callable[[Any, Optional[date], Optional[date], int], list]
    propietario: Callable[[Any], Optional[str]]
    resumen: Callable[[Any], str]
    tipo_de_aprobacion: Optional[str] = None     # entity_type de approval_engine (expense, leave…)
    cumple_requisito: Optional[Callable[[Any, Any, dict], bool]] = None
    aplicar_campo: Optional[Callable[[Any, Any, str, Any], None]] = None
    _por_clave: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._por_clave = {c.clave: c for c in self.campos}
        if len(self._por_clave) != len(self.campos):
            raise ValueError(f"dominio {self.clave}: claves de campo repetidas")

    def campo(self, clave: str) -> Optional[Campo]:
        return self._por_clave.get(clave)

    def a_dict(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "tipo_de_aprobacion": self.tipo_de_aprobacion,
                "campos": [c.a_dict() for c in self.campos]}


_REGISTRO: dict[str, Dominio] = {}


def registrar(dominio: Dominio) -> Dominio:
    """Registra (o sustituye, al recargar) un dominio. Idempotente."""
    _REGISTRO[dominio.clave] = dominio
    return dominio


def _cargar_dominios_incluidos() -> None:
    # Los dominios del repositorio se registran al importarse. Uno nuevo se
    # añade a esta lista (y a DOCS.md); ver «Extension points» en el README.
    from app.services.politicas.dominios import gastos  # noqa: F401


def dominios() -> list[Dominio]:
    _cargar_dominios_incluidos()
    return sorted(_REGISTRO.values(), key=lambda d: d.clave)


def dominio(clave: str) -> Dominio:
    _cargar_dominios_incluidos()
    d = _REGISTRO.get(clave)
    if d is None:
        raise ErrorDeDominio(404, f"Dominio de políticas desconocido: {clave}")
    return d


def dominio_de_aprobacion(entity_type: str) -> Optional[Dominio]:
    """El dominio cuyo `tipo_de_aprobacion` es este entity_type de approval_engine."""
    _cargar_dominios_incluidos()
    return next((d for d in _REGISTRO.values() if d.tipo_de_aprobacion == entity_type), None)
