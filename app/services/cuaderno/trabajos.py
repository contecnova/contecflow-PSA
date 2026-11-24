"""Trabajos de fondo de «Mi cuaderno», por empresa (app/worker.py).

- `avisos` (cada 5 min): las casillas con aviso vencido y sin marcar avisan a
  su dueño en la campana (una vez por aviso: `reminded_at`).
- `papelera` (diario): borra lo que lleva en la papelera más de `trash_days`
  (configuración de la empresa). Lo que está bajo bloqueo legal se queda
  (el `before_flush` de `app/db/bloqueo_legal.py` lo impide) y se cuenta.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def avisos(db: Session, org_id) -> dict:
    from app.models.cuaderno import NotebookItem, NotebookPage
    from app.services.notifications import notify_user
    ahora = datetime.now(timezone.utc)
    filas = db.query(NotebookItem, NotebookPage.title, NotebookPage.deleted_at).join(
        NotebookPage, NotebookPage.id == NotebookItem.page_id).filter(
        NotebookItem.organization_id == org_id, NotebookItem.kind == "todo", NotebookItem.checked.is_(False),
        NotebookItem.remind_at.isnot(None), NotebookItem.remind_at <= ahora, NotebookItem.reminded_at.is_(None)
    ).limit(500).all()
    enviados = 0
    for item, titulo, borrada in filas:
        item.reminded_at = ahora
        if borrada is not None:
            continue
        try:
            notify_user(db, item.owner_id, "system", f"Recordatorio: {item.text[:200]}", titulo,
                        resource="notebook_page", resource_id=item.page_id,
                        action_url=f"/notebook?page={item.page_id}",
                        aviso={"titulo": "cuaderno.recordatorio", "cuerpo": "cuaderno.recordatorio_cuerpo",
                               "params": {"texto": item.text[:200], "pagina": titulo or "—"}})
            enviados += 1
        except Exception:  # noqa: BLE001 - un aviso fallido no para el resto
            logger.warning("cuaderno: aviso no enviado %s", item.id, exc_info=True)
    db.commit()
    return {"reminders": enviados}


def papelera(db: Session, org_id) -> dict:
    from app.db.bloqueo_legal import BloqueoLegalActivo
    from app.models.cuaderno import Notebook, NotebookPage, NotebookSection
    from app.services.cuaderno import config
    dias = int(config.leer(db, org_id).get("trash_days") or 30)
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    informe = {"deleted": 0, "held": 0, "failed": 0, "days": dias}
    for M in (Notebook, NotebookSection, NotebookPage):
        ids = [i for (i,) in db.query(M.id).filter(M.organization_id == org_id, M.deleted_at.isnot(None),
                                                   M.deleted_at < corte).limit(2000)]
        for oid in ids:
            try:
                with db.begin_nested():
                    o = db.get(M, oid)
                    if o is not None:
                        db.delete(o)
                        db.flush()
                informe["deleted"] += 1
            except BloqueoLegalActivo:
                informe["held"] += 1
            except Exception:  # noqa: BLE001
                informe["failed"] += 1
                logger.warning("cuaderno: no se pudo purgar %s %s", M.__tablename__, oid, exc_info=True)
    if informe["deleted"] or informe["held"]:
        from app.services.audit import audit_log
        audit_log(db, None, "RETENTION_PURGE", "notebook_trash", None, "notebook trash",
                  metadata={"organization_id": org_id, **informe})
    db.commit()
    return informe
