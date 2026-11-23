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
        """Consulta acotada a la empresa del usuario; sin empresa, ninguna fila.

        Auditoria 22-11-2026 (informe 02, «causa de fondo»): sin `org_id` no
        filtraba (fallo en abierto). Ahora solo pasa sin filtro el superadmin
        explicito o una sesion en contexto de sistema declarado
        (`contexto_de_tenant`); cualquier otro caso sin empresa no ve nada.
        """
        q = self.db.query(model_cls)
        columna = getattr(model_cls, "organization_id", None)
        if columna is None and getattr(model_cls, "_tenant_exempt", False) is not True:
            columna = getattr(model_cls, "org_id", None)
        if columna is not None:
            org = self._org_id or (self.db.info.get("organization_id") if self.current_user is None else None)
            if org:
                q = q.filter(columna == org)
            elif not self._sin_restriccion():
                from sqlalchemy import false
                q = q.filter(false())
        if extra_filters:
            for f in extra_filters:
                q = q.filter(f)
        return q

    def _sin_restriccion(self) -> bool:
        """Superadmin explicito o contexto libre declarado en la sesion."""
        if self.current_user is not None:
            return bool(getattr(self.current_user, "is_superadmin", False))
        from app.db import contexto_de_tenant as ctx
        return ctx.estado(getattr(self.db, "info", {}) or {}) == ctx.LIBRE
