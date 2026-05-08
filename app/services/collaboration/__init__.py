"""Collaboration domain services.

Modules:
  _bus        — async event bus (in-memory now, Redis/NATS-ready)
  _search     — full-text search (Postgres tsvector / SQLite LIKE; OpenSearch-ready)
  _storage    — file storage (local now; S3/MinIO-ready)
  _queue      — background tasks (FastAPI BackgroundTasks now; NATS-ready)
  _audit      — append-only audit log writer with integrity hash
  _permissions — role checks for workspace/team/channel/conversation
"""
from app.services.collaboration._bus import bus, EventBus  # noqa: F401
from app.services.collaboration._search import search_engine, MessageSearch  # noqa: F401
from app.services.collaboration._storage import storage, FileStorage  # noqa: F401
from app.services.collaboration._queue import task_queue, TaskQueue  # noqa: F401
from app.services.collaboration._audit import audit_log  # noqa: F401
