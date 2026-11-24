"""RGPD y acceso excepcional de «Mi cuaderno» (docs/CUADERNO.md §GRC).

- `copia`: los cuadernos de una persona (también los de la papelera), con cada
  página en Markdown (acceso art. 15 y portabilidad art. 20). La engancha
  `cab_service/gdpr.py` en la copia de las solicitudes RGPD.
- `suprimir`: borra sus cuadernos (con secciones, páginas, adjuntos, dibujos,
  audios e instantáneas de colaboración), sus etiquetas y lo compartido con
  ella. Lo engancha `supresion_service.suprimir_persona` (que antes comprueba
  el bloqueo legal de la persona: 409 sin tocar nada).
- `acceso_excepcional`: la ÚNICA forma de que alguien que no es el dueño lea un
  cuaderno sin que se lo hayan compartido. Exige la capacidad
  `cuaderno.acceso_excepcional` y un motivo verificable de la empresa: un
  bloqueo legal ACTIVO que identifique a la persona (su id, correo o usuario,
  entidad `*`, `notebooks` o `notebook_pages`) o una solicitud RGPD de esa
  persona en curso (`pending`/`processing`). Cada acceso queda en
  `audit_logs` (`NOTEBOOK_EXCEPTIONAL_ACCESS`, con el caso o la solicitud).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error


def _cuadernos(db: Session, org: Optional[str], user_id: str):
    from app.models.cuaderno import Notebook
    q = db.query(Notebook).filter(Notebook.owner_id == user_id)
    if org:
        q = q.filter(Notebook.organization_id == org)
    return q.order_by(Notebook.sort_order, Notebook.created_at).all()


def hay_datos(db: Session, org: Optional[str], user_id: str) -> bool:
    return bool(_cuadernos(db, org, user_id))


def copia(db: Session, org: Optional[str], user_id: str) -> dict:
    from app.models.cuaderno import NotebookAttachment, NotebookPage, NotebookSection, NotebookShare, NotebookTag
    from app.services.cuaderno import contenido
    salida = []
    total = 0
    for nb in _cuadernos(db, org, user_id):
        secciones = []
        for s in db.query(NotebookSection).filter(NotebookSection.notebook_id == nb.id).order_by(NotebookSection.sort_order):
            paginas = []
            for p in db.query(NotebookPage).filter(NotebookPage.section_id == s.id).order_by(NotebookPage.sort_order):
                adj = db.query(NotebookAttachment).filter(NotebookAttachment.page_id == p.id).all()
                paginas.append({"title": p.title, "created_at": str(p.created_at)[:19] if p.created_at else None,
                                "updated_at": str(p.updated_at)[:19] if p.updated_at else None,
                                "in_trash": p.deleted_at is not None,
                                "markdown": contenido.a_markdown(contenido.cargar(p.content)),
                                "attachments": [{"file_name": a.file_name, "kind": a.kind, "size_bytes": a.size_bytes}
                                                for a in adj]})
                total += 1
            secciones.append({"title": s.title, "in_trash": s.deleted_at is not None, "pages": paginas})
        compartido = [{"target_type": x.target_type, "permission": x.permission, "section_id": x.section_id}
                      for x in db.query(NotebookShare).filter(NotebookShare.notebook_id == nb.id)]
        salida.append({"title": nb.title, "in_trash": nb.deleted_at is not None,
                       "transferred_from": nb.transferred_from, "shared_with": compartido, "sections": secciones})
    etiquetas = [{"key": t.key, "label": t.label} for t in db.query(NotebookTag).filter(NotebookTag.owner_id == user_id)]
    return {"notebooks": salida, "notebook_pages_count": total, "notebook_tags": etiquetas}


def suprimir(db: Session, org: Optional[str], user_id: str) -> dict:
    """Borra lo suyo del cuaderno. No confirma. Un bloqueo legal sobre un cuaderno lo impide (409)."""
    from app.models.cuaderno import NotebookPage, NotebookShare, NotebookTag
    informe = {"notebooks": 0, "shares_removed": 0, "tags": 0}
    for nb in _cuadernos(db, org, user_id):
        db.delete(nb)
        informe["notebooks"] += 1
    q = db.query(NotebookShare).filter(NotebookShare.target_type == "user", NotebookShare.target_id == user_id)
    if org:
        q = q.filter(NotebookShare.organization_id == org)
    informe["shares_removed"] = q.delete(synchronize_session=False)
    informe["tags"] = db.query(NotebookTag).filter(NotebookTag.owner_id == user_id).delete(synchronize_session=False)
    # Lo que escribió en cuadernos ajenos (compartidos) es del cuaderno ajeno: se queda sin autor.
    for campo in ("created_by", "updated_by"):
        db.query(NotebookPage).filter(getattr(NotebookPage, campo) == user_id).update(
            {campo: None}, synchronize_session=False)
    db.flush()
    return informe


def motivo_valido(db: Session, org: str, persona, legal_hold_id: Optional[str] = None,
                  gdpr_request_id: Optional[str] = None) -> dict:
    """El motivo del acceso excepcional, comprobado (o 403 `cuaderno_acceso_sin_motivo`)."""
    from app.models.cab import GDPRRequest, GDPRRequestStatus
    from app.models.governance import LegalHold
    if legal_hold_id:
        b = db.get(LegalHold, legal_hold_id)
        identifica = {str(v) for v in (persona.id, persona.email, persona.username) if v}
        if b is not None and b.organization_id == org and b.is_active \
                and b.entity in ("*", "notebooks", "notebook_pages") and b.value in identifica:
            return {"kind": "legal_hold", "id": b.id, "case_reference": b.case_reference}
    if gdpr_request_id:
        r = db.get(GDPRRequest, gdpr_request_id)
        if r is not None and r.organization_id == org and r.subject_user_id == persona.id \
                and r.status in (GDPRRequestStatus.pending, GDPRRequestStatus.processing):
            return {"kind": "gdpr_request", "id": r.id,
                    "request_type": getattr(r.request_type, "value", r.request_type)}
    raise error(403, "cuaderno_acceso_sin_motivo")


def acceso_excepcional(db: Session, actor, persona_id: str, datos: dict, ip: Optional[str] = None) -> tuple:
    """(bytes, nombre, mime) de los cuadernos de `persona_id`, auditado. No confirma."""
    from app.models.cuaderno import NotebookPage
    from app.models.user import User
    from app.services.audit import audit_log
    from app.services.cuaderno import exportar
    org = getattr(actor, "organization_id", None)
    persona = db.get(User, persona_id)
    if persona is None or persona.organization_id != org:
        raise error(404, "no_encontrado", que="usuario")
    motivo = motivo_valido(db, org, persona, datos.get("legal_hold_id"), datos.get("gdpr_request_id"))
    justificacion = str(datos.get("justification") or "").strip()
    if len(justificacion) < 10:
        raise error(422, "cuaderno_acceso_sin_justificacion")
    formato = datos.get("format") or "md"
    if formato not in exportar.FORMATOS:
        raise error(422, "cuaderno_formato_no_valido")
    paginas = []
    for nb in _cuadernos(db, org, persona.id):
        filas = db.query(NotebookPage).filter(NotebookPage.notebook_id == nb.id).all()
        paginas.extend(exportar._en_orden(filas))
    titulo = f"{persona.full_name} — cuadernos"
    contenido_ = exportar.generar(paginas, titulo, formato)
    audit_log(db, actor, "NOTEBOOK_EXCEPTIONAL_ACCESS", "notebook", persona.id, persona.full_name,
              new_values={"reason": motivo, "justification": justificacion[:1000], "format": formato,
                          "pages": len(paginas)}, ip_address=ip)
    return contenido_, f"cuadernos_{persona.id[:8]}.{formato}", exportar.FORMATOS[formato]
