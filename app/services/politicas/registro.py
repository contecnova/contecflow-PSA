"""Tipos del catálogo de dominios y su registro (hoja: no importa ningún dominio).

Salió de `catalogo.py` (rev. 167) para que los dominios importen de aquí y
`catalogo._cargar_dominios_incluidos` (que importa los dominios) no cierre un
ciclo. `catalogo` lo reexporta todo: nadie más tiene que cambiar.
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
    # Un periodo (desde, hasta) del contexto contra el periodo de la condición:
    # «solapa con» un cierre de vacaciones, «no solapa con» (tarea #25).
    "periodo": ("overlaps", "not_overlaps"),
    # Una hora del día «HH:MM» (rev. 180: franja de una ausencia por horas).
    "hora": ("eq", "ne", "lt", "lte", "gt", "gte", "between"),
}

#: Operadores que no llevan valor, y los que llevan dos.
SIN_VALOR = {"empty", "not_empty"}
DOS_VALORES = {"between", "overlaps", "not_overlaps"}
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


#: Tipos de parámetro de un resultado propio de un dominio (la pantalla pinta
#: cada uno con su control: número, lista cerrada, sí/no, entidad, texto,
#: resultados anidados del motor, destinatarios de aviso, canales, o una clave
#: interna que la pantalla genera sola).
TIPOS_DE_PARAMETRO = ("numero", "enum", "booleano", "entidad", "texto", "resultados", "destinatarios", "canales",
                      "clave")


@dataclass(frozen=True)
class Parametro:
    clave: str
    etiqueta: str
    tipo: str                                    # uno de TIPOS_DE_PARAMETRO
    opciones: tuple[Opcion, ...] = ()            # con tipo enum
    entidad: Optional[str] = None                # con tipo entidad
    defecto: Any = None
    minimo: Optional[float] = None
    obligatorio: bool = True
    ayuda: Optional[str] = None
    visible_si: Optional[tuple[str, tuple]] = None   # (parámetro, valores): solo se pide si ese vale uno de ellos

    def a_dict(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "tipo": self.tipo,
                "opciones": [{"valor": o.valor, "etiqueta": o.etiqueta} for o in self.opciones],
                "entidad": self.entidad, "defecto": self.defecto, "minimo": self.minimo,
                "obligatorio": self.obligatorio, "ayuda": self.ayuda,
                "visible_si": {"parametro": self.visible_si[0], "valores": list(self.visible_si[1])}
                if self.visible_si else None}


@dataclass(frozen=True)
class ResultadoPropio:
    """Un resultado que solo tiene sentido en un dominio (p. ej. el cupo de
    ausencias). Se guarda como cualquier otro (`{"tipo": clave, …parámetros}`),
    se valida con sus `parametros` y lo resuelve el gancho `resolver_propio`
    del dominio al evaluar (ver `motor.evaluar_con`)."""
    clave: str
    etiqueta: str
    parametros: tuple[Parametro, ...]
    ayuda: Optional[str] = None

    def a_dict(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "ayuda": self.ayuda,
                "parametros": [p.a_dict() for p in self.parametros]}


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
    - `usos_de_tabla`: para qué más puede usar el dominio una tabla de
      referencia (p. ej. gastos `kilometraje`); la pantalla lo elige en la tabla.
    - `ejemplos(db, usuario) -> {"tablas": [...], "politicas": [...]}`
      (opcional): políticas de ejemplo que un administrador carga a mano
      («Cargar ejemplos»); se crean como BORRADOR, nunca se aplican solas.
    - `resultados_propios` + `resolver_propio(db, ctx, resultado) -> (resultados, detalle)`
      (opcional, tarea #25): resultados que solo entiende este dominio. Al
      evaluar, el motor pide al dominio qué resultados del motor salen de cada
      uno ahora (p. ej. cupo lleno → lista de espera) y guarda `detalle` en la
      explicación. Solo lee: evaluar sigue sin efectos.
    - `admite_lista_de_espera`: el resultado `waitlist` tiene sentido en él.
    - `tipos_de_documento(db) -> [Opcion]` (opcional): los tipos de documento
      del dominio (en vez de `POLICY_DOCUMENT_TYPES`).
    - `opciones_dinamicas(db) -> {clave_de_campo: [Opcion]}` (opcional): las
      opciones de un campo `enum` que dependen de la empresa (tipos, turnos).
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
    usos_de_tabla: tuple[Opcion, ...] = ()
    ejemplos: Optional[Callable[[Any, Any], dict]] = None
    resultados_propios: tuple[ResultadoPropio, ...] = ()
    resolver_propio: Optional[Callable[[Any, dict, dict], tuple]] = None
    admite_lista_de_espera: bool = False
    tipos_de_documento: Optional[Callable[[Any], list]] = None
    opciones_dinamicas: Optional[Callable[[Any], dict]] = None
    # Rev. 167: al publicar una versión, el dominio pone al día lo que dependa de ella
    # (ausencias: cuenta en los cupos nuevos las ausencias que ya existían).
    al_publicar: Optional[Callable[[Any, dict], None]] = None
    _por_clave: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._por_clave = {c.clave: c for c in self.campos}
        if len(self._por_clave) != len(self.campos):
            raise ValueError(f"dominio {self.clave}: claves de campo repetidas")

    def campo(self, clave: str) -> Optional[Campo]:
        return self._por_clave.get(clave)

    def resultado_propio(self, clave: str) -> Optional[ResultadoPropio]:
        return next((r for r in self.resultados_propios if r.clave == clave), None)

    def a_dict(self) -> dict:
        return {"clave": self.clave, "etiqueta": self.etiqueta, "tipo_de_aprobacion": self.tipo_de_aprobacion,
                "campos": [c.a_dict() for c in self.campos],
                "usos_de_tabla": [{"valor": o.valor, "etiqueta": o.etiqueta} for o in self.usos_de_tabla],
                "tiene_ejemplos": self.ejemplos is not None,
                "resultados_propios": [r.a_dict() for r in self.resultados_propios],
                "admite_lista_de_espera": self.admite_lista_de_espera}


_REGISTRO: dict[str, Dominio] = {}


def registrar(dominio: Dominio) -> Dominio:
    """Registra (o sustituye, al recargar) un dominio. Idempotente."""
    _REGISTRO[dominio.clave] = dominio
    return dominio


