"""Base service class. All new services should extend this."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.user import User


class ServiceBase:
    """
    Base class for all service-layer classes.

    Usage:
        class ProjectService(ServiceBase):
            def get_active(self):
                return self.db.query(Project).filter(...).all()
    """

    def __init__(self, db: Session, current_user: Optional["User"] = None):
        self.db = db
        self.current_user = current_user
        self._org_id: Optional[str] = (
            getattr(current_user, "organization_id", None)
            if current_user else None
        )

    @property
    def org_id(self) -> Optional[str]:
        return self._org_id

    def _scoped(self, model_cls, extra_filters=None):
        """Return a query scoped to current org (if not superadmin)."""
        q = self.db.query(model_cls)
        if self._org_id and hasattr(model_cls, "organization_id"):
            q = q.filter(model_cls.organization_id == self._org_id)
        if extra_filters:
            for f in extra_filters:
                q = q.filter(f)
        return q
