"""Reserva de documentos para editar: check-out / check-in (revisión 2026-11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.documents import Document, DocumentAccessLevel, DocumentPermission
from app.models.enterprise import AuditLog
from app.models.user import User
from tests.conftest import auth


def _u(db, username):
    return db.query(User).filter(User.username == username).first()


@pytest.fixture
def doc(db):
    """Un documento de la admin donde el PM y el empleado pueden editar."""
    admin = _u(db, "admin")
    d = Document(id="doc-res", title="Contrato", created_by=admin.id, organization_id=admin.organization_id)
    db.add(d)
    for nombre in ("pm_test", "dev_test"):
        db.add(DocumentPermission(document_id=d.id, user_id=_u(db, nombre).id, organization_id=admin.organization_id,
                                  access_level=DocumentAccessLevel.editor))
    db.commit()
    return d


def _reservar(client, token):
    return client.post("/api/v1/documents/doc-res/checkout", headers=auth(token))


def test_reservar_y_que_lo_vean_los_demas(client, db, doc, pm_token, dev_token):
    r = _reservar(client, pm_token)
    assert r.status_code == 200 and r.json()["data"]["mine"] is True
    caduca = datetime.fromisoformat(r.json()["data"]["expires_at"])
    assert timedelta(hours=23) < caduca - datetime.now(timezone.utc) <= timedelta(hours=24)
    visto = client.get("/api/v1/documents/doc-res", headers=auth(dev_token)).json()["data"]["checkout"]
    assert visto["mine"] is False and visto["user_name"] == _u(db, "pm_test").full_name
    lista = client.get("/api/v1/documents", headers=auth(dev_token)).json()
    filas = lista.get("items") or lista.get("data") or []
    assert next(f for f in filas if f["id"] == "doc-res")["checkout"]["user_id"] == _u(db, "pm_test").id


def test_EL_HALLAZGO_nadie_mas_escribe_mientras_esta_reservado(client, db, doc, pm_token, dev_token, admin_token):
    _reservar(client, pm_token)
    r = client.patch("/api/v1/documents/doc-res", json={"title": "Otro"}, headers=auth(dev_token))
    assert r.status_code == 423 and "reservado" in r.json()["detail"]["message"]
    r = client.post("/api/v1/documents/doc-res/versions", files={"file": ("a.txt", b"hola", "text/plain")},
                    headers=auth(dev_token))
    assert r.status_code == 423
    assert client.delete("/api/v1/documents/doc-res", headers=auth(admin_token)).status_code == 423
    assert _reservar(client, dev_token).status_code == 423
    # Quien lo tiene, sí.
    assert client.patch("/api/v1/documents/doc-res", json={"title": "Contrato v2"},
                        headers=auth(pm_token)).status_code == 200


def test_liberar_y_forzar(client, db, doc, pm_token, dev_token, admin_token):
    _reservar(client, pm_token)
    assert client.post("/api/v1/documents/doc-res/checkin", headers=auth(dev_token)).status_code == 409
    assert client.post("/api/v1/documents/doc-res/checkin", params={"force": True},
                       headers=auth(dev_token)).status_code == 403          # editor, no administra el documento
    assert client.post("/api/v1/documents/doc-res/checkin", params={"force": True},
                       headers=auth(admin_token)).status_code == 200
    forzada = db.query(AuditLog).filter(AuditLog.action == "CHECKIN_FORCED", AuditLog.resource_id == "doc-res").one()
    assert _u(db, "pm_test").id in forzada.metadata_
    assert client.patch("/api/v1/documents/doc-res", json={"title": "X"}, headers=auth(dev_token)).status_code == 200
    # El dueño la libera sin forzar.
    _reservar(client, dev_token)
    assert client.post("/api/v1/documents/doc-res/checkin", headers=auth(dev_token)).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "CHECKIN", AuditLog.resource_id == "doc-res").count() == 1


def test_una_reserva_caducada_no_bloquea(client, db, doc, pm_token, dev_token):
    _reservar(client, pm_token)
    db.expire_all()
    d = db.get(Document, "doc-res")
    d.checkout_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/v1/documents/doc-res", headers=auth(dev_token)).json()["data"]["checkout"] is None
    assert client.patch("/api/v1/documents/doc-res", json={"title": "Y"}, headers=auth(dev_token)).status_code == 200


def test_reservar_exige_poder_editar(client, db, doc, hr_token):
    assert client.post("/api/v1/documents/doc-res/checkout", headers=auth(hr_token)).status_code in (403, 404)


def test_la_edicion_colaborativa_respeta_permiso_y_reserva(client, db, doc, pm_token, dev_token, hr_token):
    url = "/api/v1/documents/doc-res/collab/snapshot"
    cuerpo = {"content": b"\x01\x02", "headers": {"Content-Type": "application/octet-stream"}}
    sin_permiso = client.post(url, content=cuerpo["content"], headers={**auth(hr_token), **cuerpo["headers"]})
    assert sin_permiso.status_code in (403, 404)                    # antes: 200
    assert client.get(url, headers=auth(hr_token)).status_code in (403, 404)
    _reservar(client, pm_token)
    assert client.post(url, content=cuerpo["content"],
                       headers={**auth(dev_token), **cuerpo["headers"]}).status_code == 423
    assert client.post(url, content=cuerpo["content"],
                       headers={**auth(pm_token), **cuerpo["headers"]}).status_code == 200
