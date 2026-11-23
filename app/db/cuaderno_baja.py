"""Baja de una persona: qué pasa con sus cuadernos (migración 202, docs/CUADERNO.md §GRC).

Al desactivar a un usuario (venga de la ficha, SCIM, la recertificación o las
cuentas inactivas), un `before_flush` aplica la política de la empresa
(Configuración › Mi cuaderno, `cuaderno.config` → `offboarding`):

- `transfer` (por defecto): pasan a su responsable (`users.manager_id`), que los
  ve como propios con la marca «transferido de». Sin responsable, se conservan
  y queda anotado en la auditoría para que dirección decida.
- `trash`: van a la papelera (`deleted_at`); la purga de la papelera los borra
  pasado el plazo, salvo bloqueo legal.
- `keep`: no se tocan (nadie los lee: el dueño está de baja).

Cada caso queda en `audit_logs` (`NOTEBOOK_OFFBOARDING`). Las comparticiones
hacia la persona de baja se quitan siempre. Solo depende de modelos y de `app.db`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import event, inspect, update
from sqlalchemy.orm import Session

POLITICAS = ("transfer", "trash", "keep")


def _desactivados(session) -> list:
    from app.models.user import User
    salida = []
    for obj in session.dirty:
        if not isinstance(obj, User) or obj.is_active is not False:
            continue
        hist = inspect(obj).attrs.is_active.history
        if hist.deleted and any(v is True for v in hist.deleted):
            salida.append(obj)
    return salida


def politica_de(session, org) -> str:
    """La política de baja de la empresa (`transfer` si no hay configuración)."""
    from app.models.settings import AppSetting
    fila = session.query(AppSetting.value).filter(AppSetting.key == "cuaderno.config",
                                                   AppSetting.organization_id == org).first()
    try:
        valor = (json.loads(fila[0]) if fila and fila[0] else {}).get("offboarding") or "transfer"
    except (TypeError, ValueError):
        valor = "transfer"
    return valor if valor in POLITICAS else "transfer"


def aplicar_baja(session, usuario, ahora=None) -> dict:
    """Aplica la política a los cuadernos de `usuario`. Devuelve lo hecho. No confirma."""
    from app.models.cuaderno import (Notebook, NotebookAttachment, NotebookItem, NotebookPage, NotebookSection,
                                     NotebookShare, NotebookTag)
    from app.models.enterprise import AuditLog
    ahora = ahora or datetime.now(timezone.utc)
    org = usuario.organization_id
    uid = usuario.id
    ids = [i for (i,) in session.query(Notebook.id).filter(Notebook.owner_id == uid, Notebook.organization_id == org)]
    politica = politica_de(session, org)
    informe = {"user_id": uid, "policy": politica, "notebooks": len(ids), "to": None}
    # Las comparticiones hacia la persona de baja se quitan siempre.
    session.execute(update(NotebookShare).where(NotebookShare.target_type == "user", NotebookShare.target_id == uid)
                    .values(target_id="__baja__" + uid[:20]).execution_options(synchronize_session=False))
    if ids and politica == "transfer":
        destino = getattr(usuario, "manager_id", None)
        if destino and destino != uid:
            for M in (NotebookSection, NotebookPage, NotebookItem):
                session.execute(update(M).where(M.notebook_id.in_(ids))
                                .values(owner_id=destino).execution_options(synchronize_session=False))
            session.execute(update(Notebook).where(Notebook.id.in_(ids)).values(
                owner_id=destino, transferred_from=uid, transferred_at=ahora, is_quick=False)
                .execution_options(synchronize_session=False))
            session.execute(update(NotebookAttachment).where(NotebookAttachment.owner_id == uid)
                            .values(owner_id=destino).execution_options(synchronize_session=False))
            informe["to"] = destino
        else:
            informe["policy"] = "keep_without_manager"
    elif ids and politica == "trash":
        session.execute(update(Notebook).where(Notebook.id.in_(ids), Notebook.deleted_at.is_(None))
                        .values(deleted_at=ahora, deleted_by="offboarding")
                        .execution_options(synchronize_session=False))
    # Sus etiquetas propias no sirven a nadie más.
    session.execute(NotebookTag.__table__.delete().where(NotebookTag.owner_id == uid))
    if ids or politica != "keep":
        session.add(AuditLog(user_id=None, user_name="System", action="NOTEBOOK_OFFBOARDING",
                             resource="notebook", resource_id=uid, resource_name="offboarding",
                             new_values=json.dumps(informe), organization_id=org))
    return informe


def al_desactivar(session, flush_context=None, instances=None) -> None:
    usuarios = _desactivados(session)
    if not usuarios:
        return
    from app.db.session import sin_filtro_de_tenant
    with session.no_autoflush, sin_filtro_de_tenant(session):
        for u in usuarios:
            aplicar_baja(session, u)


def registrar() -> None:
    if not event.contains(Session, "before_flush", al_desactivar):
        event.listen(Session, "before_flush", al_desactivar)
