from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


class AlertType(str, enum.Enum):
    overload = "overload"              # Person >100% capacity
    burnout_risk = "burnout_risk"      # 3+ weeks at high load
    budget_exceeded = "budget_exceeded"  # Project >90% budget
    budget_critical = "budget_critical"  # Project >100% budget
    deadline_risk = "deadline_risk"    # Project behind schedule
    task_blocked = "task_blocked"      # Task blocked for >2 days
    hours_deviation = "hours_deviation"  # Task >50% over estimate
    no_imputation = "no_imputation"    # Person hasn't logged for 2+ days


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(Enum(AlertType), nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False)

    # Who it's about
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(Text)
    value = Column(Float, nullable=True)    # e.g. 110 (% load) or 92000 (€ spent)
    threshold = Column(Float, nullable=True)  # e.g. 100 (% limit)
    dedup_key = Column(String(200), nullable=True, index=True)  # Prevents DB-level duplicates

    is_read = Column(Boolean, default=False)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Notification sent
    email_sent = Column(Boolean, default=False)
    slack_sent = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="alerts", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[project_id])
    task = relationship("Task", foreign_keys=[task_id])

    def __repr__(self):
        return f"<Alert {self.alert_type} severity={self.severity}>"

