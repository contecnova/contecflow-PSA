"""Flujo de demanda configurable (migración 195, 22-11-2026).

Ver docs/FLUJO_DE_DEMANDA.md. Ocho tablas:

- `demand_request_types`: tipos de solicitud por empresa (cambio en proyecto,
  nueva funcionalidad, servicio…), con sus canales y su flujo.
- `demand_flows`: definición JSON versionada del flujo (fases, pasos, decisiones,
  puertas, plazos, avisos, bloqueo de campos).
- `demand_requests`: el expediente único vivo de cada solicitud.
- `demand_step_states`: estado de cada paso por fase y ronda (votos incluidos).
- `demand_transitions`: log INMUTABLE de transiciones (hash encadenado; el ORM
  rechaza UPDATE y DELETE).
- `demand_field_versions`: versiones de los campos críticos (append-only).
- `demand_documents`: repositorio documental etiquetado por fase.
- `demand_comments`: comentarios (internos o visibles para el cliente).
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, event, func

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DemandRequestType(Base):
    __tablename__ = "demand_request_types"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    key = Column(String(60), nullable=False)
    name = Column(String(200), nullable=False)
    name_i18n = Column(Text, nullable=True)           # JSON {es, en, zh, …}
    channels = Column(Text, nullable=True)            # JSON ["client_portal", "internal_portal", "operator", "supplier_portal"]
    scopes = Column(Text, nullable=True)              # JSON ["project", "service", "asset", "none"]: sobre qué se pide
    description = Column(Text, nullable=True)
    requires_project = Column(Boolean, nullable=False, default=False)
    allows_standalone = Column(Boolean, nullable=False, default=True)
    flow_id = Column(String(36), ForeignKey("demand_flows.id", ondelete="SET NULL"), nullable=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DemandFlow(Base):
    __tablename__ = "demand_flows"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    key = Column(String(60), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    definition = Column(Text, nullable=False)         # JSON (ver docs/FLUJO_DE_DEMANDA.md)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DemandRequest(Base):
    __tablename__ = "demand_requests"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    code = Column(String(30), nullable=False, index=True)
    type_id = Column(String(36), ForeignKey("demand_request_types.id", ondelete="SET NULL"), nullable=True, index=True)
    type_key = Column(String(60), nullable=False)
    flow_id = Column(String(36), ForeignKey("demand_flows.id", ondelete="SET NULL"), nullable=True, index=True)
    flow_version = Column(Integer, nullable=False, default=1)
    flow_snapshot = Column(Text, nullable=False)      # foto JSON del flujo con el que nació
    origin = Column(String(30), nullable=False, default="operator")  # client_portal | internal_portal | operator
    title = Column(String(255), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    standalone = Column(Boolean, nullable=False, default=False)
    scope_kind = Column(String(20), nullable=True)    # project | service | asset | none
    scope_ref_id = Column(String(36), nullable=True, index=True)  # elemento del catálogo o CI
    executed_actions = Column(Text, nullable=True)    # JSON [{action, id, ok, at}] de las acciones al cerrar
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    client_user_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True, index=True)
    requester_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    current_phase_key = Column(String(60), nullable=True, index=True)
    phase_round = Column(Integer, nullable=False, default=0)
    phase_entered_at = Column(DateTime(timezone=True), nullable=True)
    sla_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    sla_warned = Column(Boolean, nullable=False, default=False)
    sla_breached = Column(Boolean, nullable=False, default=False)
    paused_since = Column(DateTime(timezone=True), nullable=True)
    paused_seconds = Column(Float, nullable=False, default=0.0)
    data = Column(Text, nullable=True)                # JSON {campo: valor} vigente
    client_locked = Column(Boolean, nullable=False, default=False)
    committee_required = Column(Boolean, nullable=True)
    committee_reasons = Column(Text, nullable=True)   # JSON [texto]
    committee_date = Column(DateTime(timezone=True), nullable=True)
    result_kind = Column(String(20), nullable=True)   # backlog | new_project | portfolio
    result_project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    result_change_request_id = Column(String(36), ForeignKey("change_requests.id", ondelete="SET NULL"), nullable=True)
    result_proposal_id = Column(String(36), ForeignKey("portfolio_proposals.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DemandStepState(Base):
    __tablename__ = "demand_step_states"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("demand_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_key = Column(String(60), nullable=False)
    round = Column(Integer, nullable=False, default=1)
    step_key = Column(String(60), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | approved | rejected | done | skipped
    votes = Column(Text, nullable=True)               # JSON [{user_id, decision, note, at}]
    decided_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    approval_request_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DemandTransition(Base):
    """Log inmutable. No se actualiza ni se borra (ver eventos al final)."""
    __tablename__ = "demand_transitions"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("demand_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False, default=1)
    from_phase = Column(String(60), nullable=True)
    to_phase = Column(String(60), nullable=True)
    step_key = Column(String(60), nullable=True)
    decision = Column(String(30), nullable=False, index=True)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String(255), nullable=True)
    actor_role = Column(String(60), nullable=True)
    justification = Column(Text, nullable=True)
    is_bypass = Column(Boolean, nullable=False, default=False)
    payload = Column(Text, nullable=True)             # JSON (motivos de la puerta, campos que faltaban…)
    prev_hash = Column(String(64), nullable=True)
    hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class DemandFieldVersion(Base):
    __tablename__ = "demand_field_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("demand_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    field = Column(String(60), nullable=False)
    value = Column(Text, nullable=True)               # JSON del valor
    source = Column(String(20), nullable=False)       # client | internal
    phase_key = Column(String(60), nullable=True)
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DemandDocument(Base):
    __tablename__ = "demand_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("demand_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    file_key = Column(String(500), nullable=True)
    phase_key = Column(String(60), nullable=True)
    tag = Column(String(40), nullable=False, default="other")
    file_name = Column(String(255), nullable=False)
    mime = Column(String(120), nullable=True)
    size = Column(Integer, nullable=True)
    is_annex = Column(Boolean, nullable=False, default=False)
    personal_data = Column(Boolean, nullable=False, default=False)
    internal = Column(Boolean, nullable=False, default=False)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DemandComment(Base):
    __tablename__ = "demand_comments"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), ForeignKey("demand_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_key = Column(String(60), nullable=True)
    body = Column(Text, nullable=False)
    internal = Column(Boolean, nullable=False, default=False)
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_client_id = Column(String(36), ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RegistroInmutable(Exception):
    """Se intentó cambiar o borrar una fila del log de transiciones o de versiones."""


def _rechazar(mapper, connection, target):  # noqa: ARG001
    raise RegistroInmutable(f"{target.__tablename__} es de solo añadir: no se modifica ni se borra")


for _modelo in (DemandTransition, DemandFieldVersion):
    event.listen(_modelo, "before_update", _rechazar)
    event.listen(_modelo, "before_delete", _rechazar)
