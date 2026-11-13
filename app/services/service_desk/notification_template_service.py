"""Plantillas de los avisos del Service Desk, vistas por la organizacion.

El texto por defecto vive en `plantillas_aviso.POR_DEFECTO`; la organizacion
lo personaliza o lo apaga con una fila de `email_templates` con el mismo
`code` e idioma. Aqui se listan las dos cosas juntas y se escribe la fila.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cab import EmailTemplate
from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.services.service_desk.plantillas_aviso import IDIOMAS, POR_DEFECTO, VARIABLES
from app.services.service_desk.ticket_event_processor import renderizar
from app.core.errores import ErrorDeDominio

#: Valores de ejemplo para la vista previa.
EJEMPLO = {
    "ticket_number": "INC-0042", "ticket_title": "La VPN no conecta desde casa",
    "ticket_status": "En curso", "ticket_priority": "P2 alta",
    "requester_name": "Ana Cliente", "assignee_name": "Luis Agente", "group_name": "Soporte N1",
    "comment_author": "Luis Agente", "comment_body": "Hemos reiniciado el concentrador; prueba ahora.",
    "resolution": "Certificado renovado", "sla_due": "16/03/2026 12:30",
    "link": "https://ejemplo/service-desk?ticket=…", "org_name": "",
}


def _fila(db: Session, code: str, idioma: str, org_id: Optional[str]) -> Optional[EmailTemplate]:
    return db.query(EmailTemplate).filter(
        EmailTemplate.code == code,
        EmailTemplate.language == idioma,
        EmailTemplate.organization_id.is_(None) if org_id is None else EmailTemplate.organization_id == org_id,
    ).first()


def _exigir(code: str, idioma: str) -> None:
    if code not in POR_DEFECTO:
        raise ErrorDeDominio(404, "Aviso desconocido")
    if idioma not in IDIOMAS:
        raise ErrorDeDominio(422, f"Idioma sin textos: {idioma}")


def listar(db: Session, org_id: Optional[str]) -> list[dict]:
    salida = []
    for code, textos in POR_DEFECTO.items():
        idiomas = {}
        for idioma in IDIOMAS:
            fila = _fila(db, code, idioma, org_id)
            asunto, cuerpo = textos.get(idioma) or textos[IDIOMA_DE_RESPALDO]
            idiomas[idioma] = {
                "subject": fila.subject if fila else asunto,
                "body_html": fila.body_html if fila else cuerpo,
                "is_active": fila.is_active if fila else True,
                "customized": fila is not None,
                "default_subject": asunto,
                "default_body_html": cuerpo,
            }
        _, evento, papel = code.split(".")  # sd.<evento>.<papel>
        salida.append({"code": code, "event": evento, "role": papel, "languages": idiomas})
    return salida


def guardar(db: Session, org_id: Optional[str], user_id: Optional[str], code: str, idioma: str,
            subject: str, body_html: str, is_active: bool) -> dict:
    _exigir(code, idioma)
    if not subject.strip() or not body_html.strip():
        raise ErrorDeDominio(422, "El asunto y el texto no pueden quedar vacíos")
    fila = _fila(db, code, idioma, org_id)
    if fila is None:
        fila = EmailTemplate(
            organization_id=org_id, code=code, language=idioma, category="service_desk",
            name=f"Service Desk — {code} ({idioma})", created_by=user_id,
            variables=json.dumps(list(VARIABLES)), is_system=False,
        )
        db.add(fila)
    fila.subject, fila.body_html, fila.is_active = subject, body_html, is_active
    return {"code": code, "language": idioma, "customized": True, "is_active": is_active}


def restaurar(db: Session, org_id: Optional[str], code: str, idioma: str) -> dict:
    _exigir(code, idioma)
    fila = _fila(db, code, idioma, org_id)
    if fila is not None:
        db.delete(fila)
    return {"code": code, "language": idioma, "customized": False}


def vista_previa(subject: str, body_html: str) -> dict:
    return {"subject": renderizar(subject, EJEMPLO, escapar=False),
            "body_html": renderizar(body_html, EJEMPLO, escapar=True)}
