"""La «categoría» de un ticket, en un solo sitio.

Auditoría 2026-09. Este accesor estaba escrito **dos veces**
—`alert_correlation_service._ticket_category` e
`incident_intelligence_service._ticket_category_value`—, idénticas salvo el
nombre, y **las dos llevaban la misma nota de `FIX:`** explicando el mismo
defecto: alguien asumió que `Ticket` tenía una columna `category` y no la tiene,
así que el clustering y las estadísticas reventaban con `AttributeError`.

Que el mismo arreglo esté escrito dos veces es el aviso, no la anécdota: la
próxima vez que la fuente de la categoría cambie —un `category_id` propio en
`Ticket`, por ejemplo— habrá que acordarse de los dos sitios, y el que se olvide
no fallará a gritos: devolverá un discriminador distinto y los grupos saldrán
mal. Lo encontró `scripts/audit_funciones_duplicadas.py`.

Vive en su propio módulo y no en uno de los dos servicios para no crear una
dependencia entre ellos: correlación de alertas e inteligencia de incidentes son
dominios hermanos, y hacer que uno importe del otro por un accesor de doce
líneas sería peor que la copia.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def ticket_category(t) -> Optional[str]:
    """Un identificador estable de «categoría» para un `Ticket`.

    Usa la mejor fuente disponible: `service_item.category_id` si el ticket está
    enlazado a un elemento de catálogo, y si no el `ticket_type`.

    `Ticket` **no** expone una columna `category` directa. Lo que necesitan tanto
    el clustering de alertas como las estadísticas de incidentes es sólo un
    discriminador estable, y cualquiera de las dos fuentes sirve para eso.

    El `except` ancho es a propósito: esto es best-effort sobre una relación que
    puede no estar cargada, y un fallo aquí no debe tumbar un cálculo de
    agrupación. Se registra en `debug` porque a nivel `warning` sería ruido en
    cada ticket sin elemento de catálogo, que es el caso normal.
    """
    if t is None:
        return None
    try:
        si = getattr(t, "service_item", None)
        cat_id = getattr(si, "category_id", None) if si is not None else None
        if cat_id:
            return str(cat_id)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("ticket_category: fallo best-effort ignorado", exc_info=True)
    tt = getattr(t, "ticket_type", None)
    if tt is None:
        return None
    return str(getattr(tt, "value", tt))
