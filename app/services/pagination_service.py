import math
from collections.abc import MutableMapping
from typing import Any, Optional, Protocol, Tuple

import logging

logger = logging.getLogger(__name__)


class ConCabeceras(Protocol):
    """Algo con `headers` escribibles: la `Response` de FastAPI que pasa el endpoint.

    Auditoria 2026-11 (item 36): el servicio no importa FastAPI; solo escribe
    las cabeceras de paginacion en lo que le den.
    """
    headers: MutableMapping[str, str]


def paginate_query(query: Any, page: int, page_size: int, response: Optional[ConCabeceras] = None) -> Tuple[list, int, int]:
    """Paginate a SQLAlchemy query and optionally expose pagination headers.

    Returns (items, total, pages). Keeps endpoint payload backward-compatible when
    the endpoint historically returned a plain list.
    """
    total = query.order_by(None).count()
    pages = math.ceil(total / page_size) if total > 0 else 0
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(pages)

    return items, total, pages
