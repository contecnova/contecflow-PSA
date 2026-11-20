"""Gestión de hallazgos: listado, triaje, remediación y excepciones.

Estados (`VulnerabilityFinding.status`) y transiciones manuales:

    open ──► triaged ──► in_progress ──► mitigated
      │         │             │              │
      └─────────┴─────────────┴──────────────┴──► false_positive
    accepted  ← solo por una excepción aprobada (y vuelve a open al caducar o revocarse)
    resolved  ← solo la reevaluación (el componente ya no está o ya no es vulnerable)

Remediación (el enlace queda en el hallazgo):

- **ticket**: incidente sobre el CI de la instancia (`build_internal_ticket`);
- **problema**: problema sobre el CI (`create_problem_record`);
- **cambio**: petición de cambio con los CIs afectados (`create_change_record`
  + `score_and_persist`, que calcula su impacto);
- **tarea**: en el proyecto del software (desarrollo propio; `create_task_record`).

Excepción (riesgo aceptado): motivo, controles compensatorios y caducidad
(`exception_max_days`). Si la empresa tiene un flujo de aprobación por defecto
para `vuln_exception`, la decide la bandeja de aprobaciones
(`approval_engine.fuentes`); si no, la decide quien tenga `software.aprobar`,
nunca quien la pidió. Aprobada → hallazgo `accepted`; caducada o revocada →
`open` (trabajo diario `caducar_excepciones`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.cmdb_software import (SoftwareInstance, SoftwareProduct, SoftwareVersion, Vulnerability,
                                      VulnerabilityException, VulnerabilityFinding)
from app.models.service_desk.cmdb import ConfigurationItem
from app.services.audit import audit_log
from app.services.cmdb_software import ajustes
from app.services.cmdb_software.correlacion import ABIERTOS, ORDEN_SEV, VIVOS

TRANSICIONES = {
    "open": ("triaged", "in_progress", "mitigated", "false_positive"),
    "triaged": ("open", "in_progress", "mitigated", "false_positive"),
    "in_progress": ("triaged", "mitigated", "false_positive"),
    "mitigated": ("in_progress", "false_positive"),
    "false_positive": ("open",),
}
PRIORIDAD_TICKET = {"critical": "p1_critical", "high": "p2_high", "medium": "p3_medium", "unknown": "p3_medium",
                    "low": "p4_low", "none": "p4_low"}


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def hallazgo(db, org, id_) -> VulnerabilityFinding:
    f = _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.id == id_).first() if id_ else None
    if f is None:
        raise error(404, "sw_hallazgo_no_encontrado")
    return f


def _dias_restantes(f: VulnerabilityFinding) -> Optional[float]:
    if not f.sla_due_at or f.status not in VIVOS:
        return None
    due = f.sla_due_at if f.sla_due_at.tzinfo else f.sla_due_at.replace(tzinfo=timezone.utc)
    return round((due - ahora()).total_seconds() / 86400, 1)


def serializar(db: Session, f: VulnerabilityFinding, v: Optional[Vulnerability] = None,
               p: Optional[SoftwareProduct] = None, i: Optional[SoftwareInstance] = None,
               host: Optional[ConfigurationItem] = None, padre: Optional[tuple] = None, org=None) -> dict:
    from app.core.umbrales import tono_de
    v = v or db.get(Vulnerability, f.vulnerability_id)
    p = p or db.get(SoftwareProduct, f.product_id)
    if i is None and f.instance_id:
        i = db.get(SoftwareInstance, f.instance_id)
    if host is None and i is not None and i.ci_id:
        host = db.get(ConfigurationItem, i.ci_id)
    if padre is None and f.parent_version_id:
        pv = db.get(SoftwareVersion, f.parent_version_id)
        pp = db.get(SoftwareProduct, pv.product_id) if pv else None
        padre = (pp.id if pp else None, pp.name if pp else None, pv.version if pv else None)
    restantes = _dias_restantes(f)
    tono = None
    if restantes is not None:
        try:
            tono = tono_de("vencimiento", restantes, db=db, org_id=org or f.organization_id)
        except Exception:  # noqa: BLE001 - el semáforo es informativo
            tono = "danger" if restantes < 0 else None
    return {
        "id": f.id, "status": f.status, "severity": f.severity, "priority_score": f.priority_score,
        "score_detail": json.loads(f.score_detail) if f.score_detail else None,
        # Versión desconocida: posible afectado (sin SLA hasta confirmarlo).
        "possible": bool(f.score_detail and json.loads(f.score_detail).get("possible")),
        "vulnerability_id": f.vulnerability_id, "vuln_id": v.vuln_id if v else None,
        "title": v.title if v else None, "cvss_score": v.cvss_score if v else None,
        "epss_score": v.epss_score if v else None, "kev": bool(v.kev) if v else False,
        "aliases": json.loads(v.aliases) if v and v.aliases else [],
        "product_id": f.product_id, "product_name": p.name if p else None, "affected_version": f.affected_version,
        "fixed_version": f.fixed_version, "instance_id": f.instance_id, "instance_name": i.name if i else None,
        "ci_id": host.id if host else None, "ci_name": host.name if host else None,
        "parent_version_id": f.parent_version_id, "parent_product_id": padre[0] if padre else None,
        "parent_product_name": padre[1] if padre else None, "parent_version": padre[2] if padre else None,
        "environment": f.environment, "exposure": f.exposure,
        "first_seen_at": f.first_seen_at.isoformat() if f.first_seen_at else None,
        "last_seen_at": f.last_seen_at.isoformat() if f.last_seen_at else None,
        "sla_due_at": f.sla_due_at.isoformat() if f.sla_due_at else None, "sla_days_left": restantes,
        "sla_tone": tono, "sla_breached": restantes is not None and restantes < 0,
        "assignee_user_id": f.assignee_user_id, "ticket_id": f.ticket_id, "change_id": f.change_id,
        "problem_id": f.problem_id, "task_id": f.task_id, "notes": f.notes, "resolution": f.resolution,
        "closed_at": f.closed_at.isoformat() if f.closed_at else None,
        "verified_at": f.verified_at.isoformat() if f.verified_at else None,
    }


def listar(db: Session, org, estado: Optional[str] = None, severidad: Optional[str] = None,
           producto_id: Optional[str] = None, ci_id: Optional[str] = None, kev: Optional[bool] = None,
           fuera_de_sla: Optional[bool] = None, q: Optional[str] = None, entorno: Optional[str] = None,
           pagina: int = 1, por_pagina: int = 50, posible: Optional[bool] = None) -> dict:
    consulta = _q(db, VulnerabilityFinding, org).join(Vulnerability,
                                                      Vulnerability.id == VulnerabilityFinding.vulnerability_id)
    if estado == "live":
        consulta = consulta.filter(VulnerabilityFinding.status.in_(VIVOS))
    elif estado == "open_all":
        consulta = consulta.filter(VulnerabilityFinding.status.in_(ABIERTOS))
    elif estado:
        consulta = consulta.filter(VulnerabilityFinding.status == estado)
    if severidad:
        consulta = consulta.filter(VulnerabilityFinding.severity.in_(severidad.split(",")))
    if producto_id:
        versiones = [x for (x,) in _q(db, SoftwareVersion, org).with_entities(SoftwareVersion.id)
                     .filter(SoftwareVersion.product_id == producto_id)]
        consulta = consulta.filter(or_(VulnerabilityFinding.product_id == producto_id,
                                       VulnerabilityFinding.parent_version_id.in_(versiones or [""])))
    if ci_id:
        instancias = [x for (x,) in _q(db, SoftwareInstance, org).with_entities(SoftwareInstance.id)
                      .filter(SoftwareInstance.ci_id == ci_id)]
        versiones = [x for (x,) in _q(db, SoftwareInstance, org).with_entities(SoftwareInstance.version_id)
                     .filter(SoftwareInstance.ci_id == ci_id, SoftwareInstance.version_id.isnot(None))]
        consulta = consulta.filter(or_(VulnerabilityFinding.instance_id.in_(instancias or [""]),
                                       VulnerabilityFinding.parent_version_id.in_(versiones or [""])))
    if kev is not None:
        consulta = consulta.filter(Vulnerability.kev.is_(bool(kev)))
    if fuera_de_sla:
        consulta = consulta.filter(VulnerabilityFinding.status.in_(VIVOS), VulnerabilityFinding.sla_due_at < ahora())
    if entorno:
        consulta = consulta.filter(VulnerabilityFinding.environment == entorno)
    if posible is not None:
        marca = VulnerabilityFinding.score_detail.like('%"possible": true%')
        consulta = consulta.filter(marca if posible else ~marca | VulnerabilityFinding.score_detail.is_(None))
    if q:
        patron = f"%{q.strip()}%"
        prods = [x for (x,) in _q(db, SoftwareProduct, org).with_entities(SoftwareProduct.id)
                 .filter(SoftwareProduct.name.ilike(patron))]
        consulta = consulta.filter(or_(Vulnerability.vuln_id.ilike(patron), Vulnerability.title.ilike(patron),
                                       Vulnerability.aliases.ilike(patron),
                                       VulnerabilityFinding.product_id.in_(prods or [""])))
    total = consulta.count()
    filas = (consulta.order_by(VulnerabilityFinding.priority_score.desc().nullslast(),
                               VulnerabilityFinding.sla_due_at.asc())
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all())
    return {"items": [serializar(db, f, org=org) for f in filas], "total": total, "page": pagina,
            "page_size": por_pagina}


def detalle(db: Session, org, f: VulnerabilityFinding) -> dict:
    from app.services.cmdb_software.analisis import impacto
    datos = serializar(db, f, org=org)
    v = db.get(Vulnerability, f.vulnerability_id)
    datos["vulnerability"] = {
        "description": v.description, "cvss_vector": v.cvss_vector, "cvss_version": v.cvss_version,
        "epss_percentile": v.epss_percentile, "kev_added": v.kev_added.isoformat() if v.kev_added else None,
        "cwe": json.loads(v.cwe) if v.cwe else [], "references": json.loads(v.references) if v.references else [],
        "published_at": v.published_at.isoformat() if v.published_at else None, "source": v.source}
    datos["impact"] = impacto(db, org, finding_id=f.id)
    datos["exceptions"] = [serializar_excepcion(e) for e in _q(db, VulnerabilityException, org)
                           .filter(VulnerabilityException.finding_id == f.id)
                           .order_by(VulnerabilityException.created_at.desc())]
    return datos


def cambiar(db: Session, org, f: VulnerabilityFinding, datos: dict, usuario) -> VulnerabilityFinding:
    antes = {"status": f.status, "assignee_user_id": f.assignee_user_id, "notes": f.notes}
    nuevo = datos.get("status")
    if nuevo and nuevo != f.status:
        if nuevo not in TRANSICIONES.get(f.status, ()):
            raise error(422, "sw_estado_no_valido", desde=f.status, hacia=nuevo)
        f.status = nuevo
        if nuevo == "false_positive":
            f.closed_at, f.resolution = ahora(), "not_affected"
        elif nuevo == "open":
            f.closed_at = None
        if nuevo == "mitigated":
            f.resolution = "mitigated"
    if "assignee_user_id" in datos:
        f.assignee_user_id = datos["assignee_user_id"] or None
    if "notes" in datos:
        f.notes = datos["notes"] or None
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_finding", f.id, f.finding_key[:80], old_values=antes,
              new_values={"status": f.status, "assignee_user_id": f.assignee_user_id, "notes": f.notes})
    return f


# ── Remediación ──────────────────────────────────────────────────────────────

def _contexto_texto(db, f: VulnerabilityFinding) -> tuple[str, str, list[str]]:
    datos = serializar(db, f)
    titulo = f"{datos['vuln_id']} en {datos['product_name']} {datos['affected_version'] or ''}".strip()
    cis = []
    if datos["ci_id"]:
        cis.append(datos["ci_id"])
    if f.parent_version_id:
        cis += [i.ci_id for i in db.query(SoftwareInstance).filter(
            SoftwareInstance.version_id == f.parent_version_id, SoftwareInstance.is_active.is_(True),
            SoftwareInstance.ci_id.isnot(None))]
    lineas = [datos.get("title") or "", "",
              f"Vulnerabilidad: {datos['vuln_id']} (severidad {datos['severity']}, CVSS {datos['cvss_score']}"
              f"{', KEV' if datos['kev'] else ''})",
              f"Afecta a: {datos['product_name']} {datos['affected_version'] or ''}",
              f"Corregida en: {datos['fixed_version'] or 'sin versión corregida conocida'}"]
    if datos["parent_product_name"]:
        lineas.append(f"Dentro de: {datos['parent_product_name']} {datos['parent_version'] or ''}")
    if datos["ci_name"]:
        lineas.append(f"Máquina: {datos['ci_name']}")
    if datos["sla_due_at"]:
        lineas.append(f"Plazo de remediación (SLA): {datos['sla_due_at'][:10]}")
    return titulo[:250], "\n".join(lineas), list(dict.fromkeys(cis))


def remediar(db: Session, org, f: VulnerabilityFinding, tipo: str, usuario, datos: Optional[dict] = None) -> dict:
    """Crea el ticket, problema, cambio o tarea de remediación y lo enlaza."""
    datos = datos or {}
    if f.status in ("resolved", "false_positive"):
        raise error(422, "sw_hallazgo_cerrado")
    campo = {"ticket": "ticket_id", "problem": "problem_id", "change": "change_id", "task": "task_id"}.get(tipo)
    if campo is None:
        raise error(422, "sw_valor_no_valido", campo="type", valor=tipo)
    if getattr(f, campo):
        raise error(409, "sw_remediacion_existente", tipo=tipo)
    titulo, descripcion, cis = _contexto_texto(db, f)
    prioridad = PRIORIDAD_TICKET.get(f.severity, "p3_medium")
    creado_id = None
    if tipo == "ticket":
        from app.schemas.service_desk import TicketCreateIn
        from app.services.service_desk.ticket_creation_service import build_internal_ticket
        t = build_internal_ticket(db, TicketCreateIn(title=titulo, description=descripcion, ticket_type="incident",
                                                     priority=prioridad, ci_id=cis[0] if cis else None,
                                                     tags="vulnerabilidad"), usuario.id)
        db.flush()
        creado_id = t.id
    elif tipo == "problem":
        from app.schemas.service_desk import ProblemIn
        from app.services.service_desk.problem_service import create_problem_record
        p = create_problem_record(db, usuario, ProblemIn(title=titulo, description=descripcion, priority=prioridad,
                                                         ci_id=cis[0] if cis else None,
                                                         owner_user_id=f.assignee_user_id))
        p.affected_services_json = json.dumps(cis) if cis else None
        db.flush()
        creado_id = p.id
    elif tipo == "change":
        from app.services.service_desk.change_service import create_change_record
        fixed = f.fixed_version or "la versión corregida"
        c = create_change_record(db, usuario, {
            "title": f"Actualizar {titulo}"[:250], "description": descripcion, "change_type": "normal",
            "risk": "high" if ORDEN_SEV.get(f.severity, 2) >= 3 else "medium", "priority": prioridad,
            "implementation_plan": datos.get("implementation_plan") or f"Actualizar a {fixed}.",
            "rollback_plan": datos.get("rollback_plan"), "business_justification": descripcion[:2000],
            "planned_start": datos.get("planned_start"), "planned_end": datos.get("planned_end")})
        c.affected_cis = json.dumps(cis) if cis else None
        db.flush()
        try:
            from app.services.service_desk.change_impact_service.cab import score_and_persist
            with db.begin_nested():
                score_and_persist(db, c.id)
        except Exception:  # noqa: BLE001 - el cambio queda creado aunque no se puntúe ahora
            pass
        creado_id = c.id
    else:
        from app.schemas import TaskCreate
        from app.services.task_service import create_task_record
        prod = db.get(SoftwareProduct, f.product_id)
        proyecto = datos.get("project_id")
        if not proyecto and f.parent_version_id:
            pv = db.get(SoftwareVersion, f.parent_version_id)
            padre = db.get(SoftwareProduct, pv.product_id) if pv else None
            proyecto = padre.project_id if padre else None
        proyecto = proyecto or (prod.project_id if prod else None)
        if not proyecto:
            raise error(422, "sw_sin_proyecto")
        t = create_task_record(db, TaskCreate(project_id=proyecto, title=titulo, description=descripcion,
                                              assignee_id=f.assignee_user_id), usuario)
        creado_id = t.id
    setattr(f, campo, creado_id)
    if f.status in ("open", "triaged"):
        f.status = "in_progress"
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_finding", f.id, f.finding_key[:80],
              new_values={campo: creado_id, "status": f.status}, metadata={"remediation": tipo})
    return {"type": tipo, "id": creado_id, "finding": serializar(db, f, org=org)}


# ── Excepciones ──────────────────────────────────────────────────────────────

def serializar_excepcion(e: VulnerabilityException) -> dict:
    return {"id": e.id, "finding_id": e.finding_id, "reason": e.reason,
            "compensating_controls": e.compensating_controls, "expires_at": e.expires_at.isoformat(),
            "status": e.status, "requested_by": e.requested_by, "decided_by": e.decided_by,
            "decided_at": e.decided_at.isoformat() if e.decided_at else None, "decision_note": e.decision_note,
            "approval_request_id": e.approval_request_id,
            "created_at": e.created_at.isoformat() if e.created_at else None}


def pedir_excepcion(db: Session, org, f: VulnerabilityFinding, datos: dict, usuario) -> VulnerabilityException:
    if f.status not in ABIERTOS:
        raise error(422, "sw_hallazgo_cerrado")
    motivo = (datos.get("reason") or "").strip()
    if len(motivo) < 10:
        raise error(422, "sw_excepcion_motivo")
    conf = ajustes.leer(db, org)
    maximo = int(conf.get("exception_max_days") or 180)
    try:
        caduca = date.fromisoformat(str(datos.get("expires_at"))[:10])
    except ValueError:
        raise error(422, "sw_excepcion_caducidad", max=maximo)
    hoy = date.today()
    if not (hoy < caduca <= hoy + timedelta(days=maximo)):
        raise error(422, "sw_excepcion_caducidad", max=maximo)
    if _q(db, VulnerabilityException, org).filter(VulnerabilityException.finding_id == f.id,
                                                  VulnerabilityException.status.in_(("pending", "approved"))).first():
        raise error(409, "sw_excepcion_ya_pendiente")
    e = VulnerabilityException(organization_id=org, finding_id=f.id, reason=motivo,
                               compensating_controls=(datos.get("compensating_controls") or "").strip() or None,
                               expires_at=caduca, status="pending", requested_by=usuario.id)
    db.add(e)
    db.flush()
    audit_log(db, usuario, "SUBMIT", "sw_vuln_exception", e.id, f.finding_key[:80],
              new_values=serializar_excepcion(e))
    # Bandeja de aprobaciones, si la empresa tiene flujo para este tipo.
    try:
        from app.services.approval_engine import fuentes
        v = db.get(Vulnerability, f.vulnerability_id)
        p = db.get(SoftwareProduct, f.product_id)
        fuentes.abrir(db, "vuln_exception", e.id, f"Excepción {v.vuln_id if v else ''} en {p.name if p else ''} "
                      f"{f.affected_version or ''} hasta {caduca.isoformat()}", usuario.id,
                      contexto={"severity": f.severity, "kev": bool(v and v.kev), "days": (caduca - hoy).days})
        from app.models.billing_reports import ApprovalRequest
        req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == "vuln_exception",
                                               ApprovalRequest.entity_id == e.id).first()
        if req is not None:
            e.approval_request_id = req.id
            db.flush()
    except Exception:  # noqa: BLE001 - sin flujo (o sin motor), la decide software.aprobar
        pass
    return e


def _aplicar_decision(db: Session, e: VulnerabilityException, aprobada: bool, usuario, nota: Optional[str]) -> None:
    f = db.get(VulnerabilityFinding, e.finding_id)
    e.status = "approved" if aprobada else "rejected"
    e.decided_by, e.decided_at, e.decision_note = getattr(usuario, "id", None), ahora(), nota
    if aprobada and f is not None and f.status in ABIERTOS:
        f.status = "accepted"
    db.flush()
    audit_log(db, usuario, "APPROVE" if aprobada else "REJECT", "sw_vuln_exception", e.id,
              f.finding_key[:80] if f else None, new_values=serializar_excepcion(e))


def decidir_excepcion(db: Session, org, e: VulnerabilityException, aprobada: bool, usuario,
                      nota: Optional[str] = None) -> VulnerabilityException:
    if e.status != "pending":
        raise error(422, "sw_excepcion_no_pendiente")
    if e.requested_by == usuario.id and not getattr(usuario, "is_superadmin", False):
        raise error(403, "sw_excepcion_propia")
    if e.approval_request_id:
        raise error(409, "sw_excepcion_en_bandeja")
    _aplicar_decision(db, e, aprobada, usuario, nota)
    return e


def aplicar_desde_bandeja(db: Session, excepcion_id: str, aprobada: bool, actor, nota: Optional[str]) -> None:
    """Decisión final del motor de aprobaciones (`approval_engine.fuentes.aplicar`)."""
    e = db.get(VulnerabilityException, excepcion_id)
    if e is not None and e.status == "pending":
        _aplicar_decision(db, e, aprobada, actor, nota)


def revocar_excepcion(db: Session, org, e: VulnerabilityException, usuario) -> VulnerabilityException:
    if e.status not in ("pending", "approved"):
        raise error(422, "sw_excepcion_no_pendiente")
    e.status = "revoked"
    e.decided_by, e.decided_at = usuario.id, ahora()
    f = db.get(VulnerabilityFinding, e.finding_id)
    if f is not None and f.status == "accepted":
        f.status = "open"
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_vuln_exception", e.id, None, new_values={"status": "revoked"})
    return e


def caducar_excepciones(db: Session, org) -> int:
    """Excepciones aprobadas vencidas → `expired` y su hallazgo vuelve a `open`."""
    hoy = date.today()
    n = 0
    for e in _q(db, VulnerabilityException, org).filter(VulnerabilityException.status == "approved",
                                                        VulnerabilityException.expires_at < hoy):
        e.status = "expired"
        f = db.get(VulnerabilityFinding, e.finding_id)
        if f is not None and f.status == "accepted":
            f.status = "open"
        audit_log(db, None, "UPDATE", "sw_vuln_exception", e.id, None, old_values={"status": "approved"},
                  new_values={"status": "expired"}, metadata={"reason": "expired"})
        n += 1
    db.flush()
    return n


def excepcion(db, org, id_) -> VulnerabilityException:
    e = _q(db, VulnerabilityException, org).filter(VulnerabilityException.id == id_).first() if id_ else None
    if e is None:
        raise error(404, "sw_excepcion_no_encontrada")
    return e


def listar_excepciones(db: Session, org, estado: Optional[str] = None) -> list[dict]:
    q = _q(db, VulnerabilityException, org)
    if estado:
        q = q.filter(VulnerabilityException.status == estado)
    salida = []
    for e in q.order_by(VulnerabilityException.created_at.desc()).limit(500):
        d = serializar_excepcion(e)
        f = db.get(VulnerabilityFinding, e.finding_id)
        if f is not None:
            d["finding"] = serializar(db, f, org=org)
        salida.append(d)
    return salida


# ── Ticket automático ────────────────────────────────────────────────────────

def tickets_automaticos(db: Session, org, ids_nuevos: list[str]) -> int:
    """Ticket para los hallazgos nuevos desde la severidad configurada (a nombre del propietario del producto)."""
    from app.models.user import User
    conf = ajustes.leer(db, org)
    minimo = conf.get("auto_ticket_min_severity")
    if not minimo or not ids_nuevos:
        return 0
    n = 0
    for f in _q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.id.in_(ids_nuevos)):
        if ORDEN_SEV.get(f.severity, 0) < ORDEN_SEV[minimo] or f.ticket_id:
            continue
        p = db.get(SoftwareProduct, f.product_id)
        dueno = db.get(User, p.owner_user_id) if p and p.owner_user_id else None
        if dueno is None or not dueno.is_active:
            continue
        try:
            with db.begin_nested():
                remediar(db, org, f, "ticket", dueno)
            n += 1
        except Exception:  # noqa: BLE001 - un ticket que no se puede abrir no para el resto
            continue
    return n
