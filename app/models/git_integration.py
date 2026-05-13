"""Git integration models — PR/Deploy events linked to tasks."""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class PRStatus(str, enum.Enum):
    open      = "open"
    merged    = "merged"
    closed    = "closed"
    draft     = "draft"


class DeployStatus(str, enum.Enum):
    pending   = "pending"
    running   = "running"
    success   = "success"
    failure   = "failure"
    cancelled = "cancelled"


class GitProvider(str, enum.Enum):
    github = "github"
    gitlab = "gitlab"
    gitea  = "gitea"


class GitPullRequest(Base):
    __tablename__ = "git_pull_requests"

    id             = Column(Integer, primary_key=True, index=True)
    task_id        = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id     = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    provider       = Column(SAEnum(GitProvider), default=GitProvider.github)
    repo_full_name = Column(String(256), nullable=False)   # e.g. "org/repo"
    pr_number      = Column(Integer, nullable=False)
    pr_title       = Column(String(512))
    pr_url         = Column(String(1024))
    author_login   = Column(String(128))
    source_branch  = Column(String(256))
    target_branch  = Column(String(256))
    status         = Column(SAEnum(PRStatus), default=PRStatus.open)
    merged_at      = Column(DateTime(timezone=True), nullable=True)
    closed_at      = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at     = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    task    = relationship("Task",    back_populates=None, foreign_keys=[task_id])
    project = relationship("Project", back_populates=None, foreign_keys=[project_id])


class GitDeployment(Base):
    __tablename__ = "git_deployments"

    id             = Column(Integer, primary_key=True, index=True)
    task_id        = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id     = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    pr_id          = Column(Integer, ForeignKey("git_pull_requests.id", ondelete="SET NULL"), nullable=True)
    provider       = Column(SAEnum(GitProvider), default=GitProvider.github)
    repo_full_name = Column(String(256))
    environment    = Column(String(128), default="production")
    deploy_url     = Column(String(1024))
    status         = Column(SAEnum(DeployStatus), default=DeployStatus.pending)
    sha            = Column(String(64))
    deployed_at    = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at     = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    task    = relationship("Task",           back_populates=None, foreign_keys=[task_id])
    project = relationship("Project",        back_populates=None, foreign_keys=[project_id])
    pr      = relationship("GitPullRequest", back_populates=None, foreign_keys=[pr_id])
