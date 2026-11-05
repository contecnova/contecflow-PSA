"""Políticas de retención generales y bloqueo legal (revisión 2026-11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enterprise import AuditLog, Notification
from app.models.governance import LegalHold
from app.models.mfa import Organization
from app.models.service_desk.tickets import Ticket
from app.services import retencion
from tests.conftest import auth

HACE = lambda dias: datetime.now(timezone.utc) - timedelta(days=dias)  # noqa: E731
URL = "/api/v1/governance"


def _ticket(db, id_, *, cerrado_hace=None, cliente=None, org="1"):
    db.add(Ticket(id=id_, number=f"INC-{id_}", ticket_type="incident", title=id_, description="x",
                  organization_id=org, client_id=cliente,
                  closed_at=HACE(cerrado_hace) if cerrado_hace is not None else None))


@pytest.fixture
def tickets(db):
    from app.models.clients import Client
    db.add(Client(id="cli-litigio", name="Litigio SA", organization_id="1"))
    _ticket(db, "viejo-1", cerrado_hace=400)
    _ticket(db, "viejo-2", cerrado_hace=500)
    _ticket(db, "viejo-litigio", cerrado_hace=400, cliente="cli-litigio")
    _ticket(db, "reciente", cerrado_hace=10)
    _ticket(db, "abierto")                         # sin cerrar: nunca vence
    db.commit()


def _bloquear(db, campo="client_id", valor="cli-litigio", entidad="*", org="1"):
    db.add(LegalHold(organization_id=org, case_reference="CASO-7", entity=entidad, field=campo, value=valor))
    db.commit()


def _ids(db):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return {t.id for t in db.query(Ticket)}


def test_vista_previa_cuenta_vencidos_y_bloqueados(db, tickets):
    _bloquear(db)
    assert retencion.vista_previa(db, "1", "tickets", 365) | {"cutoff": None} == {
        "entity": "tickets", "keep_days": 365, "expired": 3, "held": 1, "would_delete": 2, "cutoff": None}


def test_EL_HALLAZGO_aplica_y_respeta_el_bloqueo(client, db, tickets, admin_token):
    _bloquear(db)
    r = client.put(f"{URL}/retention/policies/tickets", json={"keep_days": 365, "is_active": True},
                   headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["data"]["is_active"] is True
    r = client.post(f"{URL}/retention/run", headers=auth(admin_token))
    assert r.json()["data"] == {"tickets": {"deleted": 2, "failed": 0, "keep_days": 365}}
    db.expire_all()
    assert _ids(db) == {"viejo-litigio", "reciente", "abierto"}
    purga = db.query(AuditLog).filter(AuditLog.action == "RETENTION_PURGE").one()
    assert '"deleted": 2' in purga.metadata_


def test_apagada_no_borra_nada(db, tickets):
    retencion.guardar_politica(db, "1", db.query(__import__("app.models.user", fromlist=["User"]).User).first(),
                               "tickets", 365, False)
    assert retencion.aplicar(db, "1") == {} and len(_ids(db)) == 5


def test_el_borrado_manual_de_algo_bloqueado_se_rechaza(db, tickets):
    _bloquear(db)
    db.delete(db.get(Ticket, "viejo-litigio"))
    with pytest.raises(retencion.BloqueoLegalActivo):
        db.commit()
    db.rollback()
    # Levantado el bloqueo, sí.
    db.query(LegalHold).update({"is_active": False})
    db.commit()
    db.delete(db.get(Ticket, "viejo-litigio"))
    db.commit()
    assert "viejo-litigio" not in _ids(db)


def test_el_bloqueo_de_otra_empresa_no_cuenta(db, tickets):
    db.add(Organization(id="org-ret", name="Otra", slug="org-ret"))
    db.commit()
    _bloquear(db, org="org-ret")
    assert retencion.vista_previa(db, "1", "tickets", 365)["held"] == 0


def test_bloqueo_por_tipo_y_por_persona_en_avisos(db):
    from app.models.user import User
    u = db.query(User).filter(User.username == "pm_test").one()
    otro = db.query(User).filter(User.username == "dev_test").one()
    for usuario in (u, otro):
        db.add(Notification(user_id=usuario.id, type="task_assigned", title="viejo", organization_id="1",
                            created_at=HACE(100)))
    db.commit()
    _bloquear(db, campo="user_id", valor=u.id, entidad="notifications")
    assert retencion.vista_previa(db, "1", "notifications", 60) | {"cutoff": None} == {
        "entity": "notifications", "keep_days": 60, "expired": 2, "held": 1, "would_delete": 1, "cutoff": None}


def test_minimo_de_dias_campos_validos_y_solo_admin(client, db, admin_token, pm_token):
    assert client.put(f"{URL}/retention/policies/tickets", json={"keep_days": 5},
                      headers=auth(admin_token)).status_code == 422
    assert client.put(f"{URL}/retention/policies/audit_logs", json={"keep_days": 400},
                      headers=auth(admin_token)).status_code == 422       # el registro de auditoría no se retiene
    assert client.post(f"{URL}/legal-holds", json={"case_reference": "X", "field": "password", "value": "1"},
                       headers=auth(admin_token)).status_code == 422
    r = client.post(f"{URL}/legal-holds", json={"case_reference": "CASO-9", "field": "client_id", "value": "c1"},
                    headers=auth(admin_token))
    assert r.status_code == 200
    lista = client.get(f"{URL}/legal-holds", headers=auth(admin_token)).json()["data"]
    assert lista[0]["case_reference"] == "CASO-9" and lista[0]["is_active"] is True
    assert client.post(f"{URL}/legal-holds/{lista[0]['id']}/release", headers=auth(admin_token)).status_code == 200
    for metodo, url in (("get", "/retention/policies"), ("post", "/retention/run"), ("get", "/legal-holds")):
        assert getattr(client, metodo)(URL + url, headers=auth(pm_token)).status_code == 403


def test_la_baja_de_una_empresa_no_borra_mientras_tenga_un_bloqueo(db):
    """La purga de la baja borra todas sus tablas: con un bloqueo legal activo se niega."""
    from app.services.baja_de_empresa_service import purgar_caducadas
    from tests.test_baja_y_entrar_como import _empresa
    _empresa(db)
    org = db.get(Organization, "org-baja")
    org.is_active, org.deletion_purge_after = False, HACE(1)
    db.commit()
    _bloquear(db, campo="user_id", valor="u-baja", org="org-baja")
    assert purgar_caducadas(db) == []
    assert db.get(Organization, "org-baja") is not None
    db.query(LegalHold).update({"is_active": False})
    db.commit()
    assert [h["organization_id"] for h in purgar_caducadas(db)] == ["org-baja"]
