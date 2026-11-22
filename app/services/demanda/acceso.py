"""Quién actúa sobre un expediente y qué puede hacer (responsables y segregación).

Un actor es un usuario interno (operador, cliente interno) o un usuario del
portal de clientes. La autorización de un paso por rol, grupo, persona o
departamento reutiliza la del motor de aprobaciones
(`approval_engine._base._is_authorized`, con la delegación por ausencia); un
comité es un grupo aprobador. No hay atajo para administradores: quien decide
tiene que estar configurado (igual que en la bandeja).

Segregación:
- `not_requester` (por defecto): quien pidió no decide ningún paso
  (`exigir_que_no_sea_suyo`, que registra la infracción en GRC);
- `not_actor_of_phases`: quien decidió algún paso de esas fases no decide en
  esta (quien estudió no vota en el CAB de su propio estudio).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error


@dataclass
class Actor:
    kind: str                      # user | client | system
    user: object = None
    client: object = None

    @property
    def id(self) -> Optional[str]:
        return getattr(self.user, "id", None) if self.kind == "user" else getattr(self.client, "id", None)

    @property
    def nombre(self) -> str:
        if self.kind == "user":
            return getattr(self.user, "full_name", None) or getattr(self.user, "email", "") or ""
        if self.kind == "client":
            return getattr(self.client, "full_name", None) or getattr(self.client, "email", "") or ""
        return "Sistema"

    @property
    def rol(self) -> Optional[str]:
        if self.kind == "user":
            r = getattr(self.user, "role", None)
            return getattr(r, "value", r)
        return "client" if self.kind == "client" else "system"

    @property
    def organization_id(self) -> Optional[str]:
        quien = self.user if self.kind == "user" else self.client
        return getattr(quien, "organization_id", None)


def de_usuario(usuario) -> Actor:
    return Actor("user", user=usuario)


def de_cliente(cliente) -> Actor:
    return Actor("client", client=cliente)


SISTEMA = Actor("system")


def puede_gestionar(actor: Actor) -> bool:
    """Capacidad `demanda.gestionar` (agendar comité, ejecutar, crear en nombre de otro)."""
    if actor.kind != "user":
        return False
    if getattr(actor.user, "is_superadmin", False):
        return True
    from app.core.capacidades import CAPACIDADES
    return actor.rol in CAPACIDADES["demanda.gestionar"].roles


def miembros_de_grupo(db: Session, grupo_id: Optional[str]) -> list[str]:
    from app.models.billing_reports import ApprovalGroup
    if not grupo_id:
        return []
    g = db.query(ApprovalGroup).filter(ApprovalGroup.id == grupo_id).first()
    try:
        return list(json.loads(g.member_ids or "[]")) if g else []
    except (TypeError, ValueError):
        return []


def _paso_del_motor(asignado: dict) -> SimpleNamespace:
    tipo = asignado.get("type")
    valor = asignado.get("value")
    return SimpleNamespace(
        approver_type={"role": "role", "group": "group", "committee": "group", "user": "user",
                       "department": "any_in_department"}.get(tipo, tipo),
        approver_role=valor if tipo == "role" else None,
        approver_user_id=valor if tipo == "user" else None,
        approver_group_id=valor if tipo in ("group", "committee") else None,
        approver_department=valor if tipo == "department" else None,
        approver_level=None, escalate_to_user_id=None,
    )


#: Responsables que salen del propio expediente (no de la configuración).
DINAMICOS = ("project_manager", "client_manager", "requester_manager", "department_head", "supplier")


def usuarios_dinamicos(db: Session, req, asignado: dict) -> list[str]:
    """Ids de usuario de un responsable dinámico: el PM del proyecto, el gestor de la
    cuenta del cliente, el responsable de quien pide, el jefe de su departamento o
    las personas del proveedor indicado."""
    from app.models.user import User
    tipo = asignado.get("type")
    uid = None
    if tipo == "project_manager" and req.project_id:
        from app.models.project import Project
        fila = db.query(Project.pm_id).filter(Project.id == req.project_id).first()
        uid = fila[0] if fila else None
    elif tipo == "client_manager" and req.client_id:
        from app.models.clients import Client
        fila = db.query(Client.account_manager_id).filter(Client.id == req.client_id).first()
        uid = fila[0] if fila else None
    elif tipo in ("requester_manager", "department_head") and req.requester_user_id:
        quien = db.query(User).filter(User.id == req.requester_user_id).first()
        if quien is not None and tipo == "requester_manager":
            uid = quien.manager_id
        elif quien is not None and quien.department:
            from app.models.settings import Department
            d = db.query(Department).filter(Department.name == quien.department,
                                            Department.organization_id == req.organization_id).first()
            uid = d.manager_id if d else None
    elif tipo == "supplier" and asignado.get("value"):
        from app.models.enterprise import SubcontractorWorker
        return [u for (u,) in db.query(SubcontractorWorker.user_id).filter(
            SubcontractorWorker.subcontractor_id == asignado["value"], SubcontractorWorker.user_id.isnot(None)).all()]
    return [uid] if uid else []


def _escalado(req, fase: Optional[dict]) -> Optional[dict]:
    """El responsable de escalado de la fase, si el plazo ya venció."""
    if not fase or not getattr(req, "sla_breached", False):
        return None
    return ((fase.get("escalation") or {}).get("to")) or None


def es_responsable(db: Session, actor: Actor, req, paso: dict, fase: Optional[dict] = None) -> bool:
    """Si el actor es responsable del paso (sin mirar la segregación).

    Con el plazo de la fase vencido, también lo es el responsable de escalado
    de la fase (`escalation.to`)."""
    escalado = _escalado(req, fase)
    if escalado and es_responsable(db, actor, req, {"assignee": escalado}):
        return True
    asignado = paso.get("assignee") or {}
    tipo = asignado.get("type")
    if tipo in DINAMICOS:
        return actor.kind == "user" and actor.id in usuarios_dinamicos(db, req, asignado)
    if tipo == "requester":
        if actor.kind == "client":
            return bool(req.client_user_id and req.client_user_id == actor.id)
        return actor.kind == "user" and bool(req.requester_user_id and req.requester_user_id == actor.id)
    if actor.kind != "user":
        return False
    if tipo == "approval_workflow":
        # Lo decide la bandeja; si no se pudo abrir solicitud, quien gestiona la demanda.
        return puede_gestionar(actor)
    from app.services.approval_engine._base import _is_authorized
    return bool(_is_authorized(_paso_del_motor(asignado), actor.user, req.requester_user_id or "", db))


def usuarios_responsables(db: Session, org_id: Optional[str], paso: dict, req=None) -> list[str]:
    """Ids de usuarios internos responsables del paso (para avisos y «pendientes para mí»)."""
    from app.models.user import User
    asignado = paso.get("assignee") or {}
    tipo, valor = asignado.get("type"), asignado.get("value")
    if tipo in DINAMICOS:
        return usuarios_dinamicos(db, req, asignado) if req is not None else []
    if tipo in ("group", "committee"):
        return miembros_de_grupo(db, valor)
    if tipo == "user":
        return [valor] if valor else []
    q = db.query(User.id).filter(User.is_active.is_(True))
    if org_id:
        q = q.filter(User.organization_id == org_id)
    if tipo == "role":
        return [u for (u,) in q.filter(User.role == valor).all()]
    if tipo == "department":
        return [u for (u,) in q.filter(User.department == valor).all()]
    return []


def exigir_segregacion(db: Session, actor: Actor, req, fase: dict) -> None:
    """Lanza 403 si el actor no puede decidir en esta fase por segregación."""
    if actor.kind != "user":
        return
    seg = fase.get("segregation") or {}
    if seg.get("not_requester", True) and req.requester_user_id:
        from app.services.approval_engine._base import exigir_que_no_sea_suyo
        exigir_que_no_sea_suyo(db, req.requester_user_id, actor.user, "demand_request", req.id)
    previas = seg.get("not_actor_of_phases") or []
    if not previas:
        return
    from app.models.demanda import DemandStepState
    for st in db.query(DemandStepState).filter(DemandStepState.request_id == req.id,
                                               DemandStepState.phase_key.in_(previas)).all():
        votos = []
        try:
            votos = json.loads(st.votes or "[]")
        except (TypeError, ValueError):
            pass
        if st.decided_by == actor.id or any(v.get("user_id") == actor.id for v in votos):
            from app.services.audit import audit_log
            audit_log(db, actor.user, "SOD_BLOCKED", "demand_request", req.id, req.code,
                      metadata={"phase": fase.get("key"), "previous_phase": st.phase_key})
            db.commit()
            raise error(403, "dem_sod_fase_previa", fase=st.phase_key)
