"""Dependencias: un solo vocabulario y sin ciclos (revisión 2026-11)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.task import Task, TaskStatus
from app.services.task_service import create_task_dependency
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1)
from app.core.errores import ErrorDeDominio


def test_EL_HALLAZGO_bloqueada_por_se_guarda_como_fs_y_un_ciclo_se_rechaza(db, proyecto):
    for i in ("a", "b", "c"):
        db.add(Task(id=f"td-{i}", code=f"TD-{i}", project_id="p-b1", title=i, status=TaskStatus.todo))
    db.commit()
    d = create_task_dependency(db, "td-b", "td-a", "blocked_by", 0, "admin-test-id")      # b bloqueada por a
    assert (d["predecessor_id"], d["successor_id"], d["dependency_type"]) == ("td-a", "td-b", "FS")
    create_task_dependency(db, "td-b", "td-c", "blocks", 0, "admin-test-id")              # a → b → c
    with pytest.raises((HTTPException, ErrorDeDominio)) as e:
        create_task_dependency(db, "td-c", "td-a", "FS", 0, "admin-test-id")              # c → a cerraría el ciclo
    assert e.value.status_code == 400
    with pytest.raises((HTTPException, ErrorDeDominio)):
        create_task_dependency(db, "td-a", "td-c", "inventado", 0, "admin-test-id")
