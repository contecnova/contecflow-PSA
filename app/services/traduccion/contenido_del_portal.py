"""Contenido de operadores que lee el cliente del portal, en su idioma (16-11-2026).

Avisos (`/sd/announcements`), paginas de la wiki del portal
(`/portal/wiki/pages`) y nombres y descripciones del catalogo de servicios
(`/sd/catalog`) los escribe un operador en su idioma. Al servirlos a un cliente
del portal se traducen al idioma de su pantalla con el servicio de siempre
(`servicio.traducir`, canal `portal`):

- solo si la empresa traduce y tiene el canal `portal` activo
  (`TRANSLATION_ENABLED` + `TRANSLATION_CHANNELS`); si no, el original;
- cache por (texto, origen, destino, glosario): cada texto se paga una vez por
  idioma y empresa; el resto de lecturas salen de la cache;
- tope de gasto de IA de la empresa: agotado, el original;
- un fallo del proveedor nunca rompe la lectura: el original.

Cada elemento traducido lleva `translated_from` (idioma de origen) para que la
pantalla pueda decir que es una traduccion automatica, y `original` (`{campo:
texto}`) para que el cliente pueda ver el texto original. Lo que no se pudo
traducir sale tal cual, sin marca.

Acotado: `org_id` es siempre la organizacion del cliente que lee; la cache y el
gasto son de esa empresa.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL, normalizar
from app.services.traduccion.servicio import TRADUCIDO, traducir

logger = logging.getLogger(__name__)

CANAL = "portal"
#: Clave de cada elemento traducido con sus textos originales (`{campo: texto}`):
#: la marca «Traducido automáticamente» del portal permite ver el original.
CAMPO_ORIGINAL = "original"


def idioma_del_lector(cliente, pedido: Optional[str] = None) -> Optional[str]:
    """Idioma al que se traduce: el de la pantalla del portal (`?lang=`) si es
    uno de los 8 del portal; si no, el de la ficha del cliente."""
    for candidato in (pedido, getattr(cliente, "language", None)):
        idioma = normalizar(candidato)
        if idioma in IDIOMAS_DEL_PORTAL:
            return idioma
    return None


def localizar(db: Session, org_id: Optional[str], elementos: list[dict], campos: Iterable[str],
              idioma: Optional[str], *, hijos: Optional[str] = None,
              campos_hijos: Iterable[str] = ()) -> list[dict]:
    """Traduce en sitio `campos` de cada elemento (y `campos_hijos` de la lista
    `hijos` de cada uno, p. ej. los servicios de una categoria) a `idioma`.
    Una sola llamada al servicio para todos los textos. Nunca lanza."""
    destino = normalizar(idioma)
    if not destino or not org_id or not elementos:
        return elementos
    campos, campos_hijos = tuple(campos), tuple(campos_hijos)
    huecos: list[tuple[dict, str]] = []
    for e in elementos:
        huecos += [(e, c) for c in campos if isinstance(e.get(c), str) and e[c].strip()]
        if hijos:
            for h in e.get(hijos) or []:
                huecos += [(h, c) for c in campos_hijos if isinstance(h.get(c), str) and h[c].strip()]
    if not huecos:
        return elementos
    try:
        resultados = traducir(db, org_id, [d[c] for d, c in huecos], destino, canal=CANAL)
    except Exception:
        logger.exception("contenido del portal: no se pudo traducir; se sirve el original")
        db.rollback()
        return elementos
    for (d, c), r in zip(huecos, resultados):
        if r.estado == TRADUCIDO and r.texto:
            # El original se conserva para que el portal ofrezca «Ver original».
            d.setdefault(CAMPO_ORIGINAL, {})[c] = d[c]
            d[c] = r.texto
            d["translated_from"] = r.origen
            d["language"] = destino
    # La cache es de la empresa y se guarda aunque la peticion sea de lectura:
    # sin esto, cada visita volveria a pagar al proveedor.
    try:
        db.commit()
    except Exception:
        logger.warning("contenido del portal: no se pudo guardar la cache", exc_info=True)
        db.rollback()
    return elementos
