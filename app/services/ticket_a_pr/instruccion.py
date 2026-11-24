"""La instrucción del agente a partir del ticket o la tarea, con los datos personales ocultos.

Lo que sale de contecflow hacia el modelo (y queda en el registro de la
ejecución) pasa SIEMPRE por aquí:

1. Solo el título, la descripción, el tipo y el código del ticket o la tarea.
   Nunca el solicitante, su correo, su teléfono, el cliente ni los comentarios.
2. `ocultar`: el detector de datos personales de la gobernanza de IA
   (`ai_governance.redact_pii`: correos, teléfonos, DNI/NIE, IBAN, tarjetas,
   IP, nombres…) y, encima, la redacción de las políticas de la empresa
   (`redactar_contexto`, módulo `ticket_pr`).
3. La instrucción que la persona revisa o edita se vuelve a ocultar al
   lanzar: lo que se escriba a mano tampoco se escapa.

Lo mismo para el plan, el resumen y el log del contenedor antes de guardarlos.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.services.ticket_a_pr import config as _config

logger = logging.getLogger(__name__)

MAX_INSTRUCCION = 12000


def ocultar(texto: Optional[str], db: Optional[Session] = None, usuario=None) -> str:
    """El texto con los datos personales ocultos (nunca lanza: sin detector, el texto vacío)."""
    if not texto:
        return ""
    try:
        from app.services.ai_governance import redact_pii
        texto, _ = redact_pii(texto, strategy="mask")
    except Exception:
        # Si el detector falla no se manda nada personal por error: se corta.
        logger.warning("ticket_pr: fallo del detector de datos personales; se descarta el texto", exc_info=True)
        return ""
    if db is not None and usuario is not None:
        from app.services.ai_provider_service.gobernanza import redactar_contexto
        texto = redactar_contexto(db, texto, usuario, _config.MODULO) or texto
    return texto


def datos_del_origen(origen) -> dict:
    """Título, descripción, tipo y código (lo único que se usa del ticket o la tarea)."""
    from app.models.task import Task
    if isinstance(origen, Task):
        return {"tipo": "tarea", "codigo": origen.code or "", "titulo": origen.title or "",
                "descripcion": origen.description or ""}
    tipo = getattr(getattr(origen, "ticket_type", None), "value", getattr(origen, "ticket_type", "")) or "ticket"
    return {"tipo": f"ticket ({tipo})", "codigo": origen.number or "", "titulo": origen.title or "",
            "descripcion": origen.description or ""}


class _Seguro(dict):
    """`format_map` que deja intactos los marcadores desconocidos (plantilla de la empresa)."""

    def __missing__(self, clave):
        return "{" + clave + "}"


def componer(plantilla: str, **valores) -> str:
    try:
        return plantilla.format_map(_Seguro(**{k: (v if v is not None else "") for k, v in valores.items()}))
    except (ValueError, IndexError):
        # Una plantilla con llaves sueltas: se sustituye a mano lo conocido.
        texto = plantilla
        for k, v in valores.items():
            texto = texto.replace("{" + k + "}", str(v or ""))
        return texto


def instruccion_de_plan(db: Session, usuario, origen, repo: str, rama: str, cfg: dict) -> str:
    """La propuesta inicial (la persona la puede editar antes de lanzar)."""
    d = datos_del_origen(origen)
    texto = componer((cfg.get("templates") or {}).get("plan") or _config.PLANTILLA_PLAN, repo=repo, rama=rama,
                     tipo=d["tipo"], codigo=d["codigo"], titulo=d["titulo"], descripcion=d["descripcion"])
    return ocultar(texto, db, usuario)[:MAX_INSTRUCCION]


def instruccion_de_build(db: Session, usuario, instruccion: str, repo: str, rama: str, plan: str, cfg: dict) -> str:
    """BUILD parte del encargo revisado (ya oculto) y del plan aprobado."""
    texto = componer((cfg.get("templates") or {}).get("build") or _config.PLANTILLA_BUILD, repo=repo, rama=rama,
                     instruccion=instruccion or "", plan=plan or "")
    return ocultar(texto, db, usuario)[:MAX_INSTRUCCION * 2]
