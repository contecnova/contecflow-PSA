"""service_desk.changes models — split from the former 1385-LOC god-file."""

from sqlalchemy import Index, Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import ChangeRisk, ChangeStatus, ChangeType, TicketPriority

class ITSMChangeRequest(Base):
    """Change Management ITIL completo — separado del ChangeRequest de proyectos."""
    __tablename__ = "sd_change_requests"
    # Unico por organizacion (revision multitenant 2026-11): antes era global y
    # una segunda empresa no podia repetir el codigo/nombre de otra.
    __table_args__ = (Index("uq_sd_change_requests_org_number", "organization_id", "number", unique=True),)

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # audit #7
    number      = Column(String(20), nullable=False, index=True, default=lambda: f"CHG-{uuid.uuid4().hex[:8].upper()}")
    title       = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    change_type  = Column(Enum(ChangeType), nullable=False, default=ChangeType.normal)
    status       = Column(Enum(ChangeStatus), nullable=False, default=ChangeStatus.draft, index=True)
    risk         = Column(Enum(ChangeRisk), default=ChangeRisk.medium)
    priority     = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)

    # Planificación
    planned_start    = Column(DateTime(timezone=True), nullable=True)
    planned_end      = Column(DateTime(timezone=True), nullable=True)
    actual_start     = Column(DateTime(timezone=True), nullable=True)
    actual_end       = Column(DateTime(timezone=True), nullable=True)

    # Plan
    implementation_plan = Column(Text, nullable=True)
    rollback_plan       = Column(Text, nullable=True)
    test_plan           = Column(Text, nullable=True)
    business_justification = Column(Text, nullable=True)

    # Impacto
    impact_description = Column(Text, nullable=True)
    affected_cis       = Column(Text, nullable=True)  # JSON: lista de CI IDs
    downtime_minutes   = Column(Integer, default=0)

    # Post-Implementation Review
    pir_notes    = Column(Text, nullable=True)
    pir_success  = Column(Boolean, nullable=True)
    pir_date     = Column(DateTime(timezone=True), nullable=True)

    # Relaciones
    requester_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approver_id  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at  = Column(DateTime(timezone=True), nullable=True)
    approved_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    rejected_reason = Column(Text, nullable=True)

    # Phase 2 — Change Impact Analysis
    auto_risk_score = Column(Float, nullable=True)
    impact_analysis_json = Column(Text, nullable=True)
    suggested_window_json = Column(Text, nullable=True)

    related_ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Comite de cambios (CAB): sus votos viven en `sd_change_approvals`. Antes
    # el CAB era un JSON en `app_settings`, sin pantalla.
    cab_quorum     = Column(Integer, nullable=True)
    cab_meeting_at = Column(DateTime(timezone=True), nullable=True)
    cab_agenda     = Column(Text, nullable=True)
    implementer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    release_id     = Column(String(36), ForeignKey("sd_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    # 23-11-2026 (A-SD19): el modelo preaprobado del catalogo de cambios
    # estandar. Sin el, el servidor no deja que el cambio sea `standard`.
    standard_model_id = Column(String(36), ForeignKey("sd_standard_change_models.id", ondelete="SET NULL"),
                               nullable=True, index=True)
    related_problem_id = Column(String(36), ForeignKey("sd_problems.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requester = relationship("User", foreign_keys=[requester_id])
    owner     = relationship("User", foreign_keys=[owner_id])
    approver  = relationship("User", foreign_keys=[approver_id])
    approver_user = relationship("User", foreign_keys=[approved_by])
    standard_model = relationship("StandardChangeModel", foreign_keys=[standard_model_id])

    requester_user_id = synonym("requester_id")

    def __init__(self, **kwargs):
        legacy_priority = kwargs.get("priority")
        if isinstance(legacy_priority, str):
            priority_map = {
                "critical": TicketPriority.p1_critical,
                "high": TicketPriority.p2_high,
                "medium": TicketPriority.p3_medium,
                "low": TicketPriority.p4_low,
            }
            kwargs["priority"] = priority_map.get(legacy_priority, legacy_priority)
        super().__init__(**kwargs)

ChangeRequest = ITSMChangeRequest


class ChangeApproval(Base):
    """El voto de un miembro del comite sobre un cambio."""
    __tablename__ = "sd_change_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    change_id = Column(String(36), ForeignKey("sd_change_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(20), default="pending", nullable=False)  # pending | approved | rejected
    note = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    approver = relationship("User", foreign_keys=[approver_user_id])


class ChangeBlackout(Base):
    """Ventana de congelacion: en ella no se programan cambios salvo de emergencia."""
    __tablename__ = "sd_change_blackouts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    reason = Column(Text, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Release(Base):
    """Una version que agrupa cambios que salen juntos."""
    __tablename__ = "sd_releases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    version = Column(String(50), nullable=True)
    status = Column(String(20), default="planned", nullable=False)  # planned | in_progress | released | cancelled
    planned_date = Column(DateTime(timezone=True), nullable=True, index=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", foreign_keys=[owner_id])


class StandardChangeModel(Base):
    """Modelo de cambio estandar (ITIL 4): un procedimiento preaprobado por el CAB.

    23-11-2026, auditoria 2026-11-22 (A-SD19). Antes un cambio se aprobaba solo
    porque el solicitante declaraba el tipo `standard`. Ahora un cambio solo es
    estandar si referencia un modelo de su empresa que:

    - esta aprobado (`status` = `ESTADO_MODELO_APROBADO`) y activo;
    - no ha caducado (`next_review_at` futura: revision periodica);
    - cubre su alcance (CIs, tipos de CI o servicios) y su riesgo (`max_risk`).

    Si su tasa de fallo (`failure_count` / cierres) supera
    `SD_STANDARD_CHANGE_MAX_FAILURE_PCT` se suspende y sus cambios vuelven al CAB.
    Logica: `app/services/service_desk/cambios_estandar_service.py`.
    """
    __tablename__ = "sd_standard_change_models"
    __table_args__ = (Index("ix_sd_standard_change_models_org_status", "organization_id", "status"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # Procedimiento: pasos de implantacion, vuelta atras y prueba (plantilla del cambio).
    procedure = Column(Text, nullable=False)
    rollback_plan = Column(Text, nullable=True)
    test_plan = Column(Text, nullable=True)
    max_risk = Column(String(20), nullable=False, default="low")       # ChangeRisk
    # Alcance (JSON, listas de ids o claves). Vacio en los tres: cualquier CI.
    applies_to_ci_ids = Column(Text, nullable=True)
    applies_to_ci_types = Column(Text, nullable=True)
    applies_to_service_ids = Column(Text, nullable=True)
    # Ciclo de vida: proposed -> approved -> (suspended -> proposed) / retired.
    status = Column(String(20), nullable=False, default="proposed")
    is_active = Column(Boolean, nullable=False, default=True)
    proposed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    review_interval_days = Column(Integer, nullable=True)
    next_review_at = Column(DateTime(timezone=True), nullable=True, index=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_reason = Column(Text, nullable=True)
    # Uso: cambios aprobados con el modelo y sus cierres.
    use_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    proposer = relationship("User", foreign_keys=[proposed_by])
    approver = relationship("User", foreign_keys=[approved_by])
