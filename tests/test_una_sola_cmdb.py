"""Una sola CMDB: lo que se descubre se puede elegir en un ticket.

Auditoria 2026-11: habia dos. El descubrimiento y la pantalla CMDB escribian en
`cmdb_items`; los tickets, problemas, cambios y el analisis de impacto leian
`sd_configuration_items`. La migracion 110 las fundio en la segunda.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from tests.conftest import auth

BASE = "/api/v1/sd/cmdb"


def _aws(org="1", pid="prov-aws"):
    return SimpleNamespace(id=pid, organization_id=org)


def _vm(ext, **extra):
    return {"external_id": ext, "name": ext, "ci_type": "virtual_machine", "status": "active",
            "attributes": json.dumps({"size": "t3"}), **extra}


def test_lo_descubierto_vive_en_la_cmdb_de_los_tickets(db, client, admin_token):
    from app.models.service_desk import CIType, ConfigurationItem, Ticket, TicketType
    from app.services.cmdb.models import reconcile_cis

    r = reconcile_cis(db, [_vm("i-1", ip_address="10.0.0.9")], "aws", provider=_aws())
    db.commit()
    assert r == {"created": 1, "updated": 0, "deactivated": 0}
    ci = db.query(ConfigurationItem).filter_by(external_id="i-1").one()
    assert ci.ci_type == CIType.virtual_machine and ci.code.startswith("CI-")
    assert ci.organization_id == "1" and ci.discovery_provider_id == "prov-aws"

    # Lo ve la organizacion en la pantalla, aunque no tenga responsable ni proyecto.
    filas = client.get(BASE, headers=auth(admin_token), params={"q": "10.0.0.9"}).json()["items"]
    assert [f["id"] for f in filas] == [ci.id] and filas[0]["is_discovered"]

    # Y se puede citar en un ticket: la clave ajena es la misma tabla.
    t = Ticket(number="INC-0900", ticket_type=TicketType.incident, title="t", description="d", ci_id=ci.id)
    db.add(t)
    db.commit()
    assert t.ci_id == ci.id


def test_EL_HALLAZGO_el_check_in_de_un_agente_no_retira_a_los_demas(db):
    """Se reconciliaba un solo host con el tipo `agent`: todos los demas, retirados."""
    from app.models.service_desk import CIStatus, ConfigurationItem
    from app.services.cmdb.models import reconcile_cis

    reconcile_cis(db, [_vm("agent:a1")], "agent", organization_id="1", retirar_ausentes=False)
    reconcile_cis(db, [_vm("agent:a2")], "agent", organization_id="1", retirar_ausentes=False)
    db.commit()
    estados = {c.external_id: c.status for c in db.query(ConfigurationItem).filter_by(discovery_provider="agent")}
    assert estados == {"agent:a1": CIStatus.operational, "agent:a2": CIStatus.operational}

    # El escaneo completo de un proveedor si retira lo que ya no aparece.
    reconcile_cis(db, [_vm("i-1"), _vm("i-2")], "aws", provider=_aws())
    r = reconcile_cis(db, [_vm("i-1")], "aws", provider=_aws())
    assert r["deactivated"] == 1
    assert db.query(ConfigurationItem).filter_by(external_id="i-2").one().status == CIStatus.retired


def test_dos_proveedores_del_mismo_tipo_no_se_retiran_entre_si(db):
    from app.models.service_desk import CIStatus, ConfigurationItem
    from app.services.cmdb.models import reconcile_cis

    reconcile_cis(db, [_vm("i-a")], "aws", provider=_aws(pid="cuenta-a"))
    r = reconcile_cis(db, [_vm("i-b")], "aws", provider=_aws(pid="cuenta-b"))
    assert r["deactivated"] == 0
    assert db.query(ConfigurationItem).filter_by(external_id="i-a").one().status == CIStatus.operational


def test_la_deriva_y_el_historial_siguen_funcionando(db):
    from app.models.cmdb import CMDBChangelog
    from app.models.service_desk import ConfigurationItem
    from app.services.cmdb.models import reconcile_cis

    reconcile_cis(db, [_vm("i-1")], "aws", provider=_aws())
    reconcile_cis(db, [_vm("i-1", attributes=json.dumps({"size": "t3.large"}))], "aws", provider=_aws())
    ci = db.query(ConfigurationItem).filter_by(external_id="i-1").one()
    assert ci.drift_detected_at is not None
    assert {h.action for h in db.query(CMDBChangelog).filter_by(item_id=ci.id)} == {"created", "updated"}


def test_la_deduplicacion_no_cruza_organizaciones(db):
    from app.services.cmdb.models import deduplicate_candidates, reconcile_cis

    reconcile_cis(db, [_vm("x-1", hostname="web01", ip_address="10.0.0.1")], "aws", provider=_aws(org="1", pid="p1"))
    reconcile_cis(db, [_vm("x-2", name="x-1", hostname="web01", ip_address="10.0.0.1")], "aws",
                  provider=_aws(org="2", pid="p2"))
    assert deduplicate_candidates(db, min_confidence=0.5) == []


def test_alta_cambio_historial_relacion_y_baja_desde_la_pantalla(client, admin_token):
    h = auth(admin_token)
    crear = lambda nombre, tipo: client.post(BASE, headers=h, json={  # noqa: E731
        "name": nombre, "ci_type": tipo, "ip_address": "10.1.1.1", "attributes": {"os": "Linux"}}).json()["data"]["id"]
    srv, app_ = crear("srv-1", "server"), crear("app-1", "application")

    cuerpo = {"name": "srv-1", "ci_type": "server", "status": "maintenance", "ip_address": "10.1.1.2",
              "attributes": {"os": "Linux"}}
    assert client.patch(f"{BASE}/{srv}", headers=h, json=cuerpo).status_code == 200
    campos = {c["field"] for c in client.get(f"{BASE}/{srv}/changelog", headers=h).json()["items"]}
    assert {"status", "ip_address"} <= campos and "attributes" not in campos, campos

    fila = next(f for f in client.get(BASE, headers=h).json()["items"] if f["id"] == srv)
    assert fila["attributes"] == {"os": "Linux"} and fila["status"] == "maintenance"

    assert client.post(f"{BASE}/relations", headers=h, json={
        "source_ci_id": srv, "target_ci_id": app_, "relation_type": "runs_on"}).status_code == 422
    rel = client.post(f"{BASE}/relations", headers=h, json={
        "source_ci_id": srv, "target_ci_id": app_, "relation_type": "hosts"}).json()["data"]["id"]
    assert client.delete(f"{BASE}/relations/{rel}", headers=h).status_code == 200
    assert client.get(f"{BASE}/{srv}/relations", headers=h).json()["items"] == []

    assert client.delete(f"{BASE}/{srv}", headers=h).status_code == 200
    assert srv not in {f["id"] for f in client.get(BASE, headers=h).json()["items"]}


def test_EL_HALLAZGO_la_correlacion_de_alertas_encuentra_la_raiz(db):
    """Leia `cmdb_relations` con ids de la otra CMDB: no casaba nunca."""
    from app.models.service_desk import CIRelation, CIRelationType, CIType, ConfigurationItem
    from app.services.service_desk.alert_correlation_service import _expand_ci_dependencies

    for i, t in (("app", CIType.application), ("db", CIType.database), ("host", CIType.server)):
        db.add(ConfigurationItem(id=i, code=f"CI-{i}", name=i, ci_type=t))
    db.add(CIRelation(source_ci_id="app", target_ci_id="db", relation_type=CIRelationType.depends_on))
    db.add(CIRelation(source_ci_id="host", target_ci_id="app", relation_type=CIRelationType.hosts))
    db.commit()
    assert set(_expand_ci_dependencies(db, ["app"])) == {"db", "host"}


# -- Clases de CI configurables ---------------------------------------------

def test_sin_configurar_salen_los_de_fabrica_y_lo_dice(client, admin_token):
    datos = client.get(f"{BASE}/class-fields", headers=auth(admin_token)).json()["data"]
    assert datos["por_defecto"] is True
    assert [c["key"] for c in datos["clases"]["database"]] == ["db_engine", "port", "size_gb", "backup_schedule"]


def test_al_guardar_una_clase_la_organizacion_pasa_a_tener_las_suyas(client, admin_token):
    h = auth(admin_token)
    nuevos = [{"key": "motor", "label": "Motor", "field_type": "text"}, {"key": "puerto", "field_type": "number"}]
    datos = client.put(f"{BASE}/class-fields/database", headers=h, json=nuevos).json()["data"]
    assert datos["por_defecto"] is False
    assert [c["key"] for c in datos["clases"]["database"]] == ["motor", "puerto"]
    # Las demas clases se copiaron de fabrica: no se pierden ni las tapa nada.
    assert [c["key"] for c in datos["clases"]["server"]][:2] == ["os", "cpu_cores"]
    vacia = client.put(f"{BASE}/class-fields/storage", headers=h, json=[]).json()["data"]
    assert vacia["clases"]["storage"] == [], "vaciar una clase la deja sin campos; no vuelve a los de fabrica"


def test_los_campos_de_clase_se_validan(client, admin_token):
    h = auth(admin_token)
    for malo in ([{"key": "Con Espacios"}], [{"key": "a"}, {"key": "a"}], [{"key": "hostname"}],
                 [{"key": "x", "field_type": "json"}]):
        assert client.put(f"{BASE}/class-fields/server", headers=h, json=malo).status_code == 422, malo
    assert client.put(f"{BASE}/class-fields/nave_espacial", headers=h, json=[]).status_code == 422


def test_un_pm_edita_cis_como_en_la_pantalla_pero_no_configura_clases(client, pm_token):
    """La pantalla CMDB la ven administradores y PM; la CMDB vieja dejaba editar a los dos."""
    h = auth(pm_token)
    r = client.post(BASE, headers=h, json={"name": "srv-pm", "ci_type": "server"})
    assert r.status_code == 200, r.text
    assert client.put(f"{BASE}/class-fields/server", headers=h, json=[]).status_code == 403

