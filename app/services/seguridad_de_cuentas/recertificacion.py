"""Recertificación periódica de accesos (ISO 27001 A.5.18, SOC 2 CC6.2).

Una campaña fotografía el acceso de cada usuario activo (rol, rol personalizado,
capacidades, MFA, último acceso) y lo asigna a su responsable (`manager_id`; si
no tiene, a quien abre la campaña). El responsable decide mantener, revocar o
modificar con un comentario obligatorio: la evidencia. Al cerrar, los «revocar»
pueden desactivar la cuenta. Se exporta en CSV o JSON.
"""
from __future__ import annotations
import logging

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

from app.core.codigos_de_error import error

DECISIONES = ("keep", "revoke", "modify")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _foto(db, u) -> dict:
    from app.core.capacidades import capacidades_de
    from app.services.seguridad_de_cuentas.politica import CAPACIDADES_SENSIBLES
    try:
        caps = capacidades_de(db, u)
    except Exception:
        logging.getLogger(__name__).debug("_foto: excepcion ignorada", exc_info=True)
        caps = []
    return {"role": getattr(u.role, "value", u.role), "custom_role_id": u.custom_role_id,
            "is_superadmin": bool(u.is_superadmin), "mfa": bool(u.mfa_enabled),
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "department": u.department, "capabilities": caps,
            "sensitive_capabilities": sorted(set(caps) & set(CAPACIDADES_SENSIBLES))}


def abrir(db, org_id: str, actor, nombre: str, vence: Optional[datetime] = None):
    from app.db.session import _miembros_de
    from app.models.seguridad_de_cuentas import AccessReviewCampaign, AccessReviewItem
    from app.models.user import User
    if not (nombre or "").strip():
        raise error(422, "recertificacion_sin_nombre")
    c = AccessReviewCampaign(organization_id=org_id, name=nombre.strip()[:200], due_at=vence,
                             created_by=actor.id, status="open")
    db.add(c)
    db.flush()
    usuarios = db.query(User).filter(_miembros_de(User, org_id), User.is_active.is_(True),
                                     User.is_superadmin.isnot(True)).all()
    activos = {u.id for u in usuarios}
    for u in usuarios:
        revisor = u.manager_id if u.manager_id in activos and u.manager_id != u.id else actor.id
        db.add(AccessReviewItem(organization_id=org_id, campaign_id=c.id, user_id=u.id, reviewer_id=revisor,
                                snapshot=json.dumps(_foto(db, u), default=str)))
    db.flush()
    return c, len(usuarios)


def _campana(db, org_id: str, campana_id: str):
    from app.models.seguridad_de_cuentas import AccessReviewCampaign
    c = db.query(AccessReviewCampaign).filter(AccessReviewCampaign.id == campana_id,
                                              AccessReviewCampaign.organization_id == org_id).first()
    if c is None:
        raise error(404, "no_encontrado", que="campana")
    return c


def listar(db, org_id: str) -> list[dict]:
    from sqlalchemy import func
    from app.models.seguridad_de_cuentas import AccessReviewCampaign, AccessReviewItem
    filas = (db.query(AccessReviewCampaign).filter(AccessReviewCampaign.organization_id == org_id)
             .order_by(AccessReviewCampaign.created_at.desc()).limit(100).all())
    cuentas = dict(db.query(AccessReviewItem.campaign_id, func.count(AccessReviewItem.id))
                   .filter(AccessReviewItem.campaign_id.in_([c.id for c in filas] or [""]))
                   .group_by(AccessReviewItem.campaign_id).all())
    pendientes = dict(db.query(AccessReviewItem.campaign_id, func.count(AccessReviewItem.id))
                      .filter(AccessReviewItem.campaign_id.in_([c.id for c in filas] or [""]),
                              AccessReviewItem.decision == "pending")
                      .group_by(AccessReviewItem.campaign_id).all())
    return [{"id": c.id, "name": c.name, "status": c.status, "due_at": c.due_at, "created_at": c.created_at,
             "closed_at": c.closed_at, "items": cuentas.get(c.id, 0), "pending": pendientes.get(c.id, 0)}
            for c in filas]


def elementos(db, org_id: str, campana_id: str, revisor_id: Optional[str] = None) -> list[dict]:
    from app.models.seguridad_de_cuentas import AccessReviewItem
    from app.models.user import User
    _campana(db, org_id, campana_id)
    q = db.query(AccessReviewItem).filter(AccessReviewItem.campaign_id == campana_id)
    if revisor_id:
        q = q.filter(AccessReviewItem.reviewer_id == revisor_id)
    filas = q.all()
    ids = {x for f in filas for x in (f.user_id, f.reviewer_id, f.decided_by) if x}
    gente = {u.id: u for u in db.query(User).filter(User.id.in_(ids or {""}))}
    def nombre(i):
        u = gente.get(i)
        return u.full_name if u else None
    return [{"id": f.id, "user_id": f.user_id, "user": nombre(f.user_id),
             "email": getattr(gente.get(f.user_id), "email", None),
             "reviewer_id": f.reviewer_id, "reviewer": nombre(f.reviewer_id),
             "snapshot": json.loads(f.snapshot or "{}"), "decision": f.decision, "comment": f.comment,
             "decided_by": nombre(f.decided_by), "decided_at": f.decided_at, "applied_at": f.applied_at}
            for f in sorted(filas, key=lambda f: (nombre(f.user_id) or ""))]


def decidir(db, org_id: str, campana_id: str, elemento_id: str, actor, decision: str, comentario: str,
            es_admin: bool):
    from app.models.seguridad_de_cuentas import AccessReviewItem
    c = _campana(db, org_id, campana_id)
    if c.status != "open":
        raise error(409, "recertificacion_cerrada")
    if decision not in DECISIONES:
        raise error(422, "recertificacion_decision_no_valida", valor=decision)
    if not (comentario or "").strip():
        raise error(422, "recertificacion_sin_evidencia")
    e = db.query(AccessReviewItem).filter(AccessReviewItem.id == elemento_id,
                                          AccessReviewItem.campaign_id == campana_id).first()
    if e is None:
        raise error(404, "no_encontrado", que="elemento")
    if e.reviewer_id != actor.id and not es_admin:
        raise error(403, "recertificacion_no_eres_responsable")
    if e.user_id == actor.id:
        raise error(403, "separacion_de_funciones_misma_persona")
    antes = e.decision
    e.decision, e.comment = decision, comentario.strip()[:1000]
    e.decided_by, e.decided_at = actor.id, _ahora()
    return e, antes


def cerrar(db, org_id: str, campana_id: str, actor, aplicar_revocaciones: bool) -> dict:
    from app.models.seguridad_de_cuentas import AccessReviewItem
    from app.models.user import User
    c = _campana(db, org_id, campana_id)
    if c.status != "open":
        raise error(409, "recertificacion_cerrada")
    elementos_ = db.query(AccessReviewItem).filter(AccessReviewItem.campaign_id == campana_id).all()
    pendientes = sum(1 for e in elementos_ if e.decision == "pending")
    desactivados = []
    if aplicar_revocaciones:
        for e in elementos_:
            if e.decision == "revoke" and e.applied_at is None:
                u = db.get(User, e.user_id)
                if u is not None and u.is_active and not u.is_superadmin and u.id != actor.id:
                    u.is_active = False
                    desactivados.append(u.id)
                e.applied_at = _ahora()
    c.status, c.closed_by, c.closed_at = "closed", actor.id, _ahora()
    return {"pending_at_close": pendientes, "deactivated": desactivados}


def exportar(db, org_id: str, campana_id: str, formato: str) -> tuple[str, str]:
    """(contenido, tipo) de la campaña con todas sus decisiones."""
    c = _campana(db, org_id, campana_id)
    filas = elementos(db, org_id, campana_id)
    if formato == "json":
        return json.dumps({"campaign": {"id": c.id, "name": c.name, "status": c.status,
                                        "created_at": c.created_at, "closed_at": c.closed_at},
                           "items": filas}, default=str, ensure_ascii=False, indent=1), "application/json"
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["user", "email", "role", "sensitive_capabilities", "mfa", "last_login", "reviewer",
                "decision", "comment", "decided_by", "decided_at", "applied_at"])
    from app.core.celdas_seguras import fila_segura
    for f in filas:
        s = f["snapshot"]
        w.writerow(fila_segura((
            f["user"], f["email"], s.get("role"), " ".join(s.get("sensitive_capabilities") or []), s.get("mfa"),
            s.get("last_login"), f["reviewer"], f["decision"], f["comment"], f["decided_by"],
            f["decided_at"], f["applied_at"])))
    return salida.getvalue(), "text/csv"


def pendientes_de(db, revisor_id: str) -> int:
    from app.models.seguridad_de_cuentas import AccessReviewCampaign, AccessReviewItem
    return (db.query(AccessReviewItem).join(AccessReviewCampaign, AccessReviewCampaign.id == AccessReviewItem.campaign_id)
            .filter(AccessReviewItem.reviewer_id == revisor_id, AccessReviewItem.decision == "pending",
                    AccessReviewCampaign.status == "open").count())
