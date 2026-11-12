from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text, Integer, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class TenantPolicyPack(Base):
    __tablename__ = "tenant_policy_packs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_key = Column(String(80), nullable=False, index=True)  # access_baseline | password_strict | data_retention
    pack_version = Column(String(20), nullable=False, default="1.0")
    is_enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(Text, nullable=True)  # JSON overrides
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", foreign_keys=[organization_id])
    updater = relationship("User", foreign_keys=[updated_by])


class ComplianceEvidence(Base):
    __tablename__ = "compliance_evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    framework = Column(String(30), nullable=False, index=True)  # SOC2 | ISO27001
    control_id = Column(String(50), nullable=False, index=True)
    evidence_type = Column(String(30), nullable=False)  # policy | screenshot | report | ticket | audit_log
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    artifact_uri = Column(String(1000), nullable=True)
    artifact_hash = Column(String(128), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization = relationship("Organization", foreign_keys=[organization_id])
    creator = relationship("User", foreign_keys=[created_by])


class RetentionPolicy(Base):
    """Cuánto se guarda cada tipo de registro de una empresa (revisión 2026-11).

    Ver app/services/retencion.py. Nacen apagadas: primero se mira la vista
    previa y luego se activan.
    """
    __tablename__ = "retention_policies"
    __table_args__ = (Index("uq_retention_policies_org_entity", "organization_id", "entity", unique=True),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    entity = Column(String(40), nullable=False)
    keep_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_deleted = Column(Integer, nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LegalHold(Base):
    """Bloqueo legal: lo que coincide no se borra, ni por retención ni a mano (revisión 2026-11).

    Coincide un registro del tipo `entity` (o de cualquiera, `*`) cuyo campo
    `field` vale `value` (p. ej. `client_id` = el cliente del litigio).
    """
    __tablename__ = "legal_holds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    case_reference = Column(String(120), nullable=False)
    reason = Column(Text, nullable=True)
    entity = Column(String(40), nullable=False, default="*")
    field = Column(String(60), nullable=False)
    value = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    released_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)


# El bloqueo legal también frena el borrado manual (ver app/db/bloqueo_legal.py).
from sqlalchemy import event as _sa_event  # noqa: E402
from sqlalchemy.orm import Session as _SesionBase  # noqa: E402


@_sa_event.listens_for(_SesionBase, "before_flush")
def _bloqueo_legal_antes_de_borrar(session, flush_context, instances) -> None:
    if session.deleted:
        from app.db.bloqueo_legal import comprobar_borrados
        comprobar_borrados(session)
