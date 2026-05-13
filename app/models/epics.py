"""
Contecflow v19 — 5 módulos del roadmap:
  1. Wiki / Editor de documentos
  2. Épicas y Roadmap visual
  3. Búsqueda avanzada NQL
  4. Cumulative Flow Diagram
  5. @Menciones y comentarios threaded
"""
import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


# ─── 1. WIKI ──────────────────────────────────────────────────────────────────

class WikiSpace(Base):
    __tablename__ = "wiki_spaces"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    name        = Column(String(200), nullable=False)
    slug        = Column(String(100), nullable=False, unique=True, index=True)
    is_active   = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    is_public   = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    pages       = relationship("WikiPage", back_populates="space", cascade="all, delete-orphan")


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    space_id     = Column(String(36), ForeignKey("wiki_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id    = Column(String(36), ForeignKey("wiki_pages.id",  ondelete="SET NULL"),  nullable=True,  index=True)
    title        = Column(String(500), nullable=False)
    slug         = Column(String(200), nullable=False)
    is_active    = Column(Boolean, default=True)
    content      = Column(Text, nullable=True)       # JSON blocks
    visibility   = Column(String(20), default='team')   # team | portal | public (client-visible)
    content_text = Column(Text, nullable=True)       # texto plano para búsqueda
    is_published = Column(Boolean, default=True)
    sort_order   = Column(Integer, default=0)
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    space    = relationship("WikiSpace",   back_populates="pages")
    children = relationship("WikiPage",    foreign_keys=[parent_id])
    versions = relationship("WikiVersion", back_populates="page", cascade="all, delete-orphan")
    wiki_comments = relationship("WikiComment", back_populates="page", cascade="all, delete-orphan")


class WikiVersion(Base):
    __tablename__ = "wiki_versions"
    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    page_id      = Column(String(36), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    version_num  = Column(Integer, nullable=False, default=1)
    title        = Column(String(500), nullable=False)
    content      = Column(Text, nullable=True)
    content_text = Column(Text, nullable=True)
    change_note  = Column(String(500), nullable=True)
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    page         = relationship("WikiPage", back_populates="versions")


class WikiTemplate(Base):
    __tablename__ = "wiki_templates"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    icon        = Column(String(10),  nullable=True)
    content     = Column(Text, nullable=True)   # JSON blocks de la plantilla
    is_system   = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class WikiComment(Base):
    __tablename__ = "wiki_comments"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    page_id     = Column(String(36), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id   = Column(String(36), ForeignKey("wiki_comments.id", ondelete="CASCADE"), nullable=True)
    content     = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    page    = relationship("WikiPage",    back_populates="wiki_comments")
    replies = relationship("WikiComment", foreign_keys=[parent_id])


# ─── 2. ÉPICAS Y ROADMAP ──────────────────────────────────────────────────────

class Epic(Base):
    __tablename__ = "epics"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id  = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title       = Column(String(500), nullable=False)
    is_active   = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    color       = Column(String(20), default="#7c3aed")
    status      = Column(String(30), default="open")    # open, in_progress, done, cancelled
    priority    = Column(String(20), default="medium")  # low, medium, high, critical
    start_date  = Column(String(10), nullable=True)
    end_date    = Column(String(10), nullable=True)
    sort_order  = Column(Integer, default=0)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    epic_tasks  = relationship("EpicTask",       back_populates="epic", cascade="all, delete-orphan")
    dependencies= relationship("EpicDependency", foreign_keys="EpicDependency.epic_id",
                               back_populates="epic", cascade="all, delete-orphan")


class EpicTask(Base):
    __tablename__ = "epic_tasks"
    id       = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    epic_id  = Column(String(36), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id  = Column(String(36), ForeignKey("tasks.id",     ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    epic     = relationship("Epic", back_populates="epic_tasks")


class EpicDependency(Base):
    __tablename__ = "epic_dependencies"
    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    epic_id       = Column(String(36), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False, index=True)
    depends_on_id = Column(String(36), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False)
    is_active     = Column(Boolean, default=True)
    epic          = relationship("Epic", foreign_keys=[epic_id],       back_populates="dependencies")
    depends_on    = relationship("Epic", foreign_keys=[depends_on_id])


# ─── 3. BÚSQUEDA NQL ──────────────────────────────────────────────────────────

class SavedFilter(Base):
    __tablename__ = "saved_filters"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(200), nullable=False)
    entity_type = Column(String(30), nullable=False, index=True)  # task, ticket, project, epic
    nql_query   = Column(Text, nullable=False)
    is_active   = Column(Boolean, default=True)
    is_shared   = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ─── 4. CUMULATIVE FLOW DIAGRAM ───────────────────────────────────────────────

class TaskStateSnapshot(Base):
    __tablename__ = "task_state_snapshots"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    sprint_id  = Column(String(36), ForeignKey("sprints.id",  ondelete="CASCADE"), nullable=True,  index=True)
    snap_date  = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD
    status     = Column(String(50), nullable=False)
    count      = Column(Integer,    default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── 5. MENCIONES Y COMENTARIOS THREADED ─────────────────────────────────────

class Mention(Base):
    __tablename__ = "mentions"
    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    mentioned_user = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mentioned_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    entity_type    = Column(String(30), nullable=False)   # task, ticket, wiki_page, comment
    entity_id      = Column(String(36), nullable=False, index=True)
    context_text   = Column(String(500), nullable=True)
    is_read        = Column(Boolean, default=False, index=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class ThreadedComment(Base):
    __tablename__ = "threaded_comments"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    entity_type = Column(String(30), nullable=False, index=True)  # task, ticket
    entity_id   = Column(String(36), nullable=False, index=True)
    parent_id   = Column(String(36), ForeignKey("threaded_comments.id", ondelete="CASCADE"), nullable=True)
    content     = Column(Text, nullable=False)
    is_active   = Column(Boolean, default=True)
    is_resolved = Column(Boolean, default=False)
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    replies     = relationship("ThreadedComment", foreign_keys=[parent_id])
