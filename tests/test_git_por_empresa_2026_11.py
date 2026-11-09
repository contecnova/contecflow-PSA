"""Webhooks de Git por empresa (revisión 2026-11).

Medido antes: un secreto y una dirección para toda la instalación; el evento
no decía de qué empresa era y el código de la tarea se buscaba en todas, así
que un PR fusionado en una empresa cerraba la tarea homónima de otra.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from app.models.git_integration import GitPullRequest
from app.models.task import Task
from app.services.integration_credentials_service import set_credential


def _pr_fusionado(codigo: str) -> bytes:
    return json.dumps({"action": "closed", "repository": {"full_name": "acme/web"},
                       "pull_request": {"number": 7, "title": f"{codigo} arreglo", "merged": True,
                                        "head": {"ref": f"feature/{codigo}"}, "base": {"ref": "main"},
                                        "merged_at": "2026-11-09T10:00:00Z"}}).encode()


def _firma(cuerpo: bytes, secreto: str) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def test_EL_HALLAZGO_el_pr_solo_cierra_la_tarea_de_su_empresa(client, db, seed_multitenant):
    a, b = db.get(Task, "task-a-test"), db.get(Task, "task-b-test")
    a.code = b.code = "TSK-00042"
    db.commit()
    set_credential(db, "webhooks", "github_secret", "secreto-de-a", "org-a-test")
    cuerpo = _pr_fusionado("TSK-00042")
    r = client.post("/api/v1/git/webhooks/github/org-a", content=cuerpo,
                    headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _firma(cuerpo, "secreto-de-a"),
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert str(getattr(db.get(Task, "task-a-test").status, "value", db.get(Task, "task-a-test").status)) == "done"
    assert str(getattr(db.get(Task, "task-b-test").status, "value", db.get(Task, "task-b-test").status)) != "done"
    pr = db.query(GitPullRequest).filter(GitPullRequest.pr_number == 7).one()
    assert pr.organization_id == "org-a-test" and pr.task_id == "task-a-test"


def test_cada_empresa_necesita_su_secreto(client, db, seed_multitenant):
    cuerpo = _pr_fusionado("TSK-TB001")
    set_credential(db, "webhooks", "github_secret", "secreto-de-a", "org-a-test")
    # La de B no tiene secreto propio: no vale el de A ni el global.
    r = client.post("/api/v1/git/webhooks/github/org-b", content=cuerpo,
                    headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _firma(cuerpo, "secreto-de-a")})
    assert r.status_code == 403
    # Con la firma equivocada para A, tampoco.
    r = client.post("/api/v1/git/webhooks/github/org-a", content=cuerpo,
                    headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _firma(cuerpo, "otro")})
    assert r.status_code == 403


def test_la_direccion_sin_empresa_solo_si_hay_una(client, db, seed_multitenant):
    r = client.post("/api/v1/git/webhooks/github", content=b"{}", headers={"X-GitHub-Event": "ping"})
    assert r.status_code == 409 and "varias empresas" in r.json()["detail"]
