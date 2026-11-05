"""NexusAgent en segundo plano corre en la empresa de quien lo pidió (revisión 2026-11).

`run_agent_task` abría su propia sesión sin empresa (las herramientas leían y
escribían de todas) y elegía el proveedor como superadmin.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.models.ai_chat import AIAgentExecution
from app.models.user import User


def test_EL_HALLAZGO_el_trabajo_publica_la_empresa_y_elige_su_proveedor(db, monkeypatch):
    pm = db.query(User).filter(User.username == "pm_test").one()
    ejecucion = AIAgentExecution(user_id=pm.id, instruction="lista proyectos", status="pending",
                                 organization_id=pm.organization_id)
    db.add(ejecucion)
    db.commit()

    @contextmanager
    def sesion_de_pruebas():
        yield db
    monkeypatch.setattr("app.db.session.worker_db_session", sesion_de_pruebas)
    vistos = {}

    def proveedor(db_, **k):
        vistos.update(k, sesion=db_.info.get("organization_id"), superadmin=db_.info.get("is_superadmin"))
        raise RuntimeError("parar aquí")
    monkeypatch.setattr("app.services.ai_provider_service.get_default_provider", proveedor)

    from app.worker import run_agent_task
    with pytest.raises(RuntimeError, match="parar aquí"):
        run_agent_task.run(ejecucion.id, "lista proyectos", pm.id)
    assert vistos == {"is_superadmin": False, "organization_id": pm.organization_id,
                      "sesion": pm.organization_id, "superadmin": False}
