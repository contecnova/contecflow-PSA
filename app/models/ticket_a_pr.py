"""«Del ticket al PR» (migración 203, 23-11-2026, docs/integraciones/TICKET_A_PR.md).

Dos tablas, las dos con `organization_id` (TenantSession y RLS las acotan por empresa):

- `ticket_pr_repos`: repositorios permitidos por proyecto (proveedor GitHub o
  GitLab, `owner/repo` o ruta del proyecto de GitLab, rama base por defecto,
  orden de tests). Solo desde aquí se puede lanzar un agente: un repositorio
  que no está en la lista no existe para el módulo.
- `ticket_pr_runs`: cada ejecución (plan y build) lanzada desde un ticket o una
  tarea, con su estado, la instrucción y el plan (con los datos personales
  ocultos), el resultado del diff, el PR, el cambio ITSM vinculado, las horas del
  agente, los tokens y el coste de IA (imputado al proyecto) y el log del
  contenedor (oculto y recortado). Retención y bloqueo legal: tipo `ticket_pr_runs`.

Ninguna credencial se guarda aquí: las de Git y del modelo viven cifradas en el
almacén de integraciones (proveedor `ticket_pr`) y en el proveedor de IA.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.db.base import Base
from app.models.money import Rate


def _uuid() -> str:
    return str(uuid.uuid4())


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


def _usuario():
    return Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


#: Estados de una ejecución (en este orden avanza el flujo normal).
ESTADOS = (
    "queued_plan",        # en cola para la fase PLAN
    "planning",           # el agente de solo lectura está proponiendo
    "awaiting_approval",  # plan listo: una persona lo aprueba o lo rechaza
    "rejected",           # plan rechazado (fin)
    "queued_build",       # plan aprobado, en cola para BUILD
    "building",           # el agente aplica los cambios en el contenedor
    "blocked",            # el diff tocaba ficheros protegidos, añadía secretos o pasaba límites (fin)
    "failed",             # error del motor, de Docker o de Git (fin)
    "cancelled",          # cancelada por una persona (fin)
    "awaiting_cab",       # PR abierto y cambio en el CAB: merge bloqueado
    "cab_approved",       # cambio aprobado: el estado del PR pasa a éxito (merge lo hace una persona)
    "cab_rejected",       # cambio rechazado o cancelado: el estado del PR pasa a fallo (fin)
    "merged",             # PR fusionado por una persona (fin)
    "closed",             # PR cerrado sin fusionar (fin)
)
FINALES = frozenset({"rejected", "blocked", "failed", "cancelled", "cab_rejected", "merged", "closed"})
ACTIVOS = frozenset({"queued_plan", "planning", "queued_build", "building"})


class TicketPrRepo(Base):
    """Repositorio permitido para un proyecto."""
    __tablename__ = "ticket_pr_repos"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)               # github | gitlab
    repo_full_name = Column(String(256), nullable=False)        # owner/repo o grupo/subgrupo/proyecto
    default_branch = Column(String(200), nullable=False, default="main")
    test_command = Column(String(500), nullable=True)           # p. ej. «npm ci && npm test»; vacío: sin tests
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class TicketPrRun(Base):
    """Una ejecución del agente de código desde un ticket o una tarea."""
    __tablename__ = "ticket_pr_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = _org()
    source_type = Column(String(10), nullable=False)            # ticket | task
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    source_ref = Column(String(40), nullable=True)              # número del ticket o código de la tarea
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    repo_id = Column(String(36), ForeignKey("ticket_pr_repos.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(20), nullable=False)
    repo_full_name = Column(String(256), nullable=False)
    base_branch = Column(String(200), nullable=False)
    base_sha = Column(String(64), nullable=True)                # fijado en PLAN; BUILD parte del mismo
    branch_name = Column(String(255), nullable=True)            # contecflow/<ticket>-<id>
    engine = Column(String(30), nullable=False, default="opencode")
    engine_image = Column(String(300), nullable=True)           # imagen:versión fijada que se usó
    ai_provider_id = Column(String(36), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True)
    model = Column(String(120), nullable=True)
    instruction = Column(Text, nullable=False)                  # con los datos personales ocultos
    plan_text = Column(Text, nullable=True)
    plan_files = Column(Text, nullable=True)                    # JSON: ficheros que el plan dice tocar
    status = Column(String(30), nullable=False, default="queued_plan", index=True)
    status_code = Column(String(80), nullable=True)             # código del catálogo del motivo (bloqueo, fallo)
    status_params = Column(Text, nullable=True)                 # JSON con sus parámetros
    launched_by = _usuario()
    plan_decided_by = _usuario()
    plan_decided_at = Column(DateTime(timezone=True), nullable=True)
    plan_decision_note = Column(String(1000), nullable=True)
    cancelled_by = _usuario()
    diff_summary = Column(Text, nullable=True)                  # JSON: ficheros, líneas añadidas y quitadas
    tests_ran = Column(Boolean, nullable=False, default=False)
    tests_passed = Column(Boolean, nullable=True)
    reasoning_summary = Column(Text, nullable=True)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String(1024), nullable=True)
    head_sha = Column(String(64), nullable=True)
    pr_status_state = Column(String(20), nullable=True)         # último estado publicado: pending | success | failure
    change_id = Column(String(36), ForeignKey("sd_change_requests.id", ondelete="SET NULL"), nullable=True,
                       index=True)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Rate, nullable=False, default=0)
    agent_seconds = Column(Integer, nullable=False, default=0)  # tiempo de contenedor del agente (plan + build + tests)
    log_redacted = Column(Text, nullable=True)                  # log del contenedor, oculto y recortado
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    __table_args__ = (Index("ix_ticket_pr_runs_org_created", "organization_id", "created_at"),)
