"""Paginacion de listados: un solo mecanismo (segunda auditoria 2026-11).

Medido con un barrido AST de `app/services`: 163 funciones `list_*` hacian
`.all()` sin `limit`, asi que un listado devolvia la tabla entera de la empresa
por grande que fuera. Este modulo es la pieza comun para cerrarlo sin romper a
quien ya consume esos listados.

Sigue la convencion que ya tenia la API (contratos, imputaciones, tickets,
documentos, facturas): ``page``/``page_size``, el total en la cabecera
``X-Total-Count`` (con ``X-Page``/``X-Page-Size``) y en ``meta.total`` del sobre
``APIListResponse``. Es la que recorre ``todasLasPaginas`` en el frontend.

Contrato:

* El endpoint declara ``pagina: Paginacion = Depends(paginacion)``.
* El servicio aplica ``paginar(query, pagina)`` a su consulta y devuelve la
  ``Pagina``: los elementos, el total real y si se ha cortado.
* El endpoint publica el total con ``exponer(response, pagina)`` o, si responde
  con el sobre, con ``lista_paginada(response, pagina)``.

Compatibilidad: sin ``page``/``page_size`` la respuesta tiene la misma forma y
los mismos elementos que antes, salvo que pase de ``LIST_MAX_ROWS`` filas. En
ese caso no se corta en silencio: ``X-Truncated: true``, ``meta.has_more`` y un
aviso en el log con el listado y el total.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Generic, Iterable, List, Optional, TypeVar

from fastapi import Query, Response

from app.core.config import settings
from app.core.constantes import MAX_TAMANO_DE_PAGINA

logger = logging.getLogger(__name__)

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class Paginacion:
    """Lo que pidio el cliente. ``page_size`` None = no pagina (se aplica el tope)."""

    page: int = 1
    page_size: Optional[int] = None

    @property
    def pide_pagina(self) -> bool:
        return self.page_size is not None

    @property
    def tope(self) -> int:
        return self.page_size if self.page_size is not None else settings.LIST_MAX_ROWS

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size if self.page_size is not None else 0


#: Para llamadas internas (exportaciones, otros servicios) que no vienen de HTTP.
SIN_PAGINAR = Paginacion()


def paginacion(
    page: Optional[int] = Query(None, ge=1, description="Pagina (desde 1). Sin page_size se ignora."),
    page_size: Optional[int] = Query(
        None, ge=1, le=MAX_TAMANO_DE_PAGINA,
        description="Filas por pagina. Sin el, el listado entero hasta el tope del servidor (LIST_MAX_ROWS).",
    ),
) -> Paginacion:
    """Dependencia FastAPI con los parametros de paginacion de un listado."""
    return Paginacion(page=page or 1, page_size=page_size)


@dataclass
class Pagina(Generic[T]):
    items: List[T]
    total: int
    pagina: Paginacion = field(default_factory=Paginacion)

    @property
    def hay_mas(self) -> bool:
        return self.pagina.offset + len(self.items) < self.total

    @property
    def truncada(self) -> bool:
        """Cortada por el tope del servidor, no porque el cliente pidiera una pagina."""
        return not self.pagina.pide_pagina and self.hay_mas

    def mapear(self, fn: Callable[[T], U]) -> "Pagina[U]":
        return Pagina(items=[fn(x) for x in self.items], total=self.total, pagina=self.pagina)


def _avisar_si_truncada(pagina: Pagina, origen: str) -> None:
    if pagina.truncada:
        logger.warning(
            "listado truncado por LIST_MAX_ROWS=%s: %s devuelve %s de %s filas",
            settings.LIST_MAX_ROWS, origen, len(pagina.items), pagina.total,
        )


def paginar(query, pagina: Optional[Paginacion] = None, origen: str = "") -> Pagina:
    """Aplica la pagina a una ``Query`` ORM ya filtrada y ordenada.

    El total sale de ``Query.count()``, que desactiva la carga ansiosa (un
    ``joinedload`` de colecciones no infla el recuento); los elementos, de
    ``offset``/``limit`` sobre la misma consulta.
    """
    pagina = pagina or SIN_PAGINAR
    total = query.order_by(None).count()
    items = query.offset(pagina.offset).limit(pagina.tope).all() if total > pagina.offset else []
    resultado = Pagina(items=items, total=total, pagina=pagina)
    _avisar_si_truncada(resultado, origen or "consulta")
    return resultado


def paginar_lista(elementos: Iterable[T], pagina: Optional[Paginacion] = None, origen: str = "") -> Pagina[T]:
    """La misma pagina sobre una lista ya calculada (filtros que no son SQL)."""
    pagina = pagina or SIN_PAGINAR
    todos = list(elementos)
    resultado = Pagina(items=todos[pagina.offset:pagina.offset + pagina.tope], total=len(todos), pagina=pagina)
    _avisar_si_truncada(resultado, origen or "lista")
    return resultado


def exponer(response: Optional[Response], pagina: Pagina) -> None:
    """Cabeceras con el total, las mismas que ya ponen los listados paginados."""
    if response is None:
        return
    response.headers["X-Total-Count"] = str(pagina.total)
    response.headers["X-Page"] = str(pagina.pagina.page)
    response.headers["X-Page-Size"] = str(pagina.pagina.tope)
    if pagina.truncada:
        response.headers["X-Truncated"] = "true"


def lista_paginada(response: Optional[Response], pagina: Pagina):
    """Atajo para endpoints con el sobre ``APIListResponse``: cabeceras + meta."""
    from app.core.responses import APIListResponse

    exponer(response, pagina)
    return APIListResponse.ok(
        items=pagina.items, total=pagina.total,
        page=pagina.pagina.page, page_size=pagina.pagina.tope, has_more=pagina.hay_mas,
    )
