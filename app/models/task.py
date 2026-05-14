from sqlalchemy import Column, String, Float, Integer, DateTime, Enum, Text, ForeignKey, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


class TaskStatus(str, enum.Enum):
    backlog = "backlog"
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    in_review = "in_review"
    review = "review"          # legacy alias kept for backward compat
    done = "done"
    cancelled = "cancelled"


class TaskPriority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete
    code = Column(String(30), nullable=False, index=True)  # e.g. TSK-001 (unique per-tenant — ver __table_args__)

    # Hierarchy
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id = Column(String(36), ForeignKey("project_phases.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)

    # Content
    title = Column(String(500), nullable=False)
    description = Column(Text)
    acceptance_criteria = Column(Text)
    tags = Column(String(500))

    # Assignment
    assignee_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reporter_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Status and priority
    status = Column(Enum(TaskStatus), default=TaskStatus.todo, nullable=False, index=True)
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium, nullable=False)

    # Time tracking
    estimated_hours = Column(Float, nullable=True)
    story_points = Column(Integer, nullable=True)
    issue_type   = Column(String(50), nullable=True, index=True)  # IssueType.value v20

    # Dates
    start_date = Column(Date, nullable=True)
    due_date   = Column(Date, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Jira sync
    jira_issue_key = Column(String(50), nullable=True, index=True)
    jira_issue_id = Column(String(50), nullable=True)
    jira_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Blocker info
    blocked_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    # Optimistic locking (P1-5)
    version = Column(Integer, default=1, nullable=False)

    # audit #38: unique per-tenant (no global) — preserva semántica multi-tenant.
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_task_code_per_org"),
    )

    # Relationships
    project = relationship("Project", back_populates="tasks")
    phase = relationship("ProjectPhase", back_populates="tasks")
    assignee = relationship("User", back_populates="task_assignments", foreign_keys=[assignee_id])
    reporter = relationship("User", foreign_keys=[reporter_id])
    creator = relationship("User", foreign_keys=[created_by])
    subtasks = relationship("Task", backref="parent", remote_side=[id])
    # audit #56-57: selectin eager-loading evita N+1 cuando TaskOut serializa real_hours
    # (que itera self.imputations) en list_tasks. Un único IN-load reemplaza N queries.
    imputations = relationship("Imputation", back_populates="task", lazy="selectin")
    # audit #56-57: comments también se serializa en TaskOut → mismo patrón N+1 en listados.
    comments = relationship(
        "TaskComment",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskComment.created_at",
        lazy="selectin",
    )

    @property
    def real_hours(self):
        return sum(i.hours for i in self.imputations)

    @property
    def efficiency_ratio(self):
        if self.estimated_hours and self.real_hours:
            return round(self.estimated_hours / self.real_hours, 2)
        return None

    def __repr__(self):
        return f"<Task {self.code}: {self.title[:40]}>"


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    is_active = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    task = relationship("Task", back_populates="comments")
    author = relationship("User")
