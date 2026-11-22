"""Índice de riesgo y gestión de vulnerabilidades (22-11-2026, rev. 194).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`, §11. Lógica:
`app/services/cmdb_software/riesgo/`.

- `sw_risk_snapshots`: histórico diario del índice por ámbito.
- `sw_compensating_controls`: controles compensatorios sobre hallazgos.
- `sw_exploit_events`: intentos de explotación importados (SIEM/EDR/IPS).
- `sw_saved_views`: vistas guardadas de la lista de vulnerabilidades.
- `sw_risk_alert_log`: avisos ya mandados (sin repetir).

Columnas nuevas en tablas de la rev. 190 (en `app/models/cmdb_software.py`):
`sw_config.risk_settings`, `sw_findings.detected_by`, `exploit_attempts`,
`last_exploit_at`, `risk_points` y `sw_instances.exposure_source`.
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


def _usuario():
    return Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class RiskSnapshot(Base):
    """Foto diaria del índice de un ámbito (recalcular el mismo día sustituye)."""
    __tablename__ = "sw_risk_snapshots"
    __table_args__ = (UniqueConstraint("organization_id", "scope_type", "scope_id", "day",
                                       name="uq_sw_risk_snapshots_scope_day"),)

    id = _id()
    organization_id = _org()
    #: org | client | service | machine | application
    scope_type = Column(String(12), nullable=False, index=True)
    scope_id = Column(String(36), nullable=False, default="", server_default="", index=True)   # "" en org
    day = Column(Date, nullable=False, index=True)
    score = Column(Float, nullable=False, default=0)
    accepted_score = Column(Float, nullable=False, default=0)
    factors = Column(Text, nullable=True)     # JSON {factor: {score, points}}
    counts = Column(Text, nullable=True)      # JSON
    computed_at = Column(DateTime(timezone=True), server_default=func.now())


class CompensatingControl(Base):
    """Control que mitiga un hallazgo sin cerrarlo (baja su riesgo y su prioridad)."""
    __tablename__ = "sw_compensating_controls"

    id = _id()
    organization_id = _org()
    finding_id = Column(String(36), ForeignKey("sw_findings.id", ondelete="CASCADE"), nullable=False, index=True)
    #: waf | ips | virtual_patch | isolation | edr | segmentation | other
    control_type = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)
    reduction = Column(Float, nullable=False, default=0.5)
    expires_at = Column(Date, nullable=False, index=True)
    status = Column(String(10), nullable=False, default="active", index=True)   # active | expired | revoked
    created_by = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_by = _usuario()
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExploitEvent(Base):
    """Intento de explotación visto por un SIEM, EDR o IPS."""
    __tablename__ = "sw_exploit_events"
    __table_args__ = (UniqueConstraint("organization_id", "source", "external_id", name="uq_sw_exploit_events_ext"),)

    id = _id()
    organization_id = _org()
    source = Column(String(30), nullable=False, default="file")
    external_id = Column(String(200), nullable=False)
    vuln_id = Column(String(80), nullable=True, index=True)
    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="SET NULL"), nullable=True, index=True)
    host = Column(String(255), nullable=True)
    ip = Column(String(45), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    action = Column(String(10), nullable=False, default="detected")   # blocked | detected | allowed
    count = Column(Integer, nullable=False, default=1)
    finding_id = Column(String(36), ForeignKey("sw_findings.id", ondelete="SET NULL"), nullable=True, index=True)
    details = Column(Text, nullable=True)
    created_by = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedVulnView(Base):
    """Vista guardada de la lista de vulnerabilidades (filtros y columnas)."""
    __tablename__ = "sw_saved_views"

    id = _id()
    organization_id = _org()
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    surface = Column(String(15), nullable=True)
    group_by = Column(String(10), nullable=True)      # cve | asset | vacío
    filters = Column(Text, nullable=True)             # JSON
    columns = Column(Text, nullable=True)             # JSON lista
    shared = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RiskAlertLog(Base):
    """Aviso de riesgo ya mandado: no se repite el mismo (`kind` + `key`)."""
    __tablename__ = "sw_risk_alert_log"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "alert_key", name="uq_sw_risk_alert_log"),)

    id = _id()
    organization_id = _org()
    kind = Column(String(20), nullable=False)
    alert_key = Column(String(200), nullable=False)
    recipients = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
