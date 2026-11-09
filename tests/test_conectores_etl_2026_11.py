"""Conectores ETL de BI: una lista, resultados reales y secretos que se usan (revisión 2026-11).

Medido antes, en la pantalla Plataforma de datos:
- tres listas de conectores que no coincidían (20, 5 y 29 nombres);
- «Sync» inventaba el número de registros (`random.randint(25, 450)`);
- «Sincronizar» mandaba la tarea a la cola `etl_{id}`, que nadie escucha;
- los extractores capturaban el error y devolvían `[]`: «OK, 0 registros»;
- la entidad por defecto era `"default"`, que HubSpot, Stripe y Xero no reconocen;
- los secretos se guardaban cifrados y se pasaban cifrados al proveedor.
"""
from __future__ import annotations

import json

import pytest

from app.integrations import bi_etl_connectors as etl
from app.models.settings import AppSetting
from app.services import bi_etl_service as svc
from tests.conftest import auth

URL = "/api/v1/bi/etl"


def _lista(client, token):
    r = client.get(f"{URL}/connectors", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_una_sola_lista_con_campos_y_entidades(client, admin_token):
    d = _lista(client, admin_token)
    ids = [c["connector_id"] for c in d["connectors"]]
    assert ids == etl.SUPPORTED_CONNECTORS and len(ids) == 21
    hub = next(c for c in d["connectors"] if c["connector_id"] == "hubspot")
    assert (hub["nombre"], hub["entity"], hub["entidades"]) == ("HubSpot", "deals", ["deals", "contacts"])
    assert hub["campos"] == [{"clave": "access_token", "secreto": True}]
    assert {c["clave"] for c in d["generico"]["campos"]} >= {"endpoint_url", "data_path", "header_value"}


def test_EL_HALLAZGO_el_error_del_proveedor_queda_y_no_es_ok_con_cero(client, admin_token, monkeypatch):
    def falla(url, headers=None, timeout=None):
        raise RuntimeError("401 Unauthorized")
    monkeypatch.setattr(etl, "_http_get", falla)
    client.patch(f"{URL}/connectors/github", headers=auth(admin_token), json={"enabled": True, "config": {"repo": "a/b", "token": "x"}})
    r = client.post(f"{URL}/connectors/github/sync", headers=auth(admin_token)).json()["data"]
    assert r["ok"] is False and "401" in r["error"]
    gh = next(c for c in _lista(client, admin_token)["connectors"] if c["connector_id"] == "github")
    assert gh["status"] == "error" and "401" in gh["last_error"] and gh["last_records"] == 0
    log = client.get(f"{URL}/connectors/github/log", headers=auth(admin_token)).json()["data"]["entries"]
    assert log[0]["ok"] is False and "401" in log[0]["error"]


def test_sincronizar_trae_guarda_y_lo_cuenta(client, admin_token, monkeypatch):
    monkeypatch.setattr(etl, "_http_get", lambda url, headers=None, timeout=None: [{"id": 1}, {"id": 2}, {"id": 3}])
    client.patch(f"{URL}/connectors/github", headers=auth(admin_token), json={"enabled": True, "config": {"repo": "a/b", "token": "x"}})
    r = client.post(f"{URL}/connectors/github/sync", headers=auth(admin_token)).json()["data"]
    assert (r["ok"], r["records_ingested"], r["entity"]) == (True, 3, "issues")
    datos = client.get(f"{URL}/data/github", headers=auth(admin_token)).json()["data"]["data"]
    assert datos["count"] == 3


def test_desactivado_no_sincroniza(client, admin_token):
    r = client.post(f"{URL}/connectors/github/sync", headers=auth(admin_token))
    assert r.status_code == 400 and "desactivado" in r.json()["detail"]


def test_EL_HALLAZGO_el_secreto_se_guarda_cifrado_no_vuelve_y_llega_descifrado(client, db, admin_token, monkeypatch):
    client.patch(f"{URL}/connectors/hubspot", headers=auth(admin_token), json={"config": {"access_token": "pat-claro-123"}})
    crudo = db.query(AppSetting).filter(AppSetting.key == svc.CLAVE_CONFIG).one().value
    assert "pat-claro-123" not in crudo
    hub = next(c for c in _lista(client, admin_token)["connectors"] if c["connector_id"] == "hubspot")
    assert hub["config"] == {} and hub["secretos_puestos"] == ["access_token"]
    # vacío = no cambia
    client.patch(f"{URL}/connectors/hubspot", headers=auth(admin_token), json={"config": {"access_token": ""}})
    visto = {}
    monkeypatch.setattr(etl.HubSpotConnector, "connect", lambda self, cfg: visto.update(cfg) or object())
    monkeypatch.setattr(etl.HubSpotConnector, "extract", lambda self, c, entity, filters=None: [])
    assert client.post(f"{URL}/connectors/hubspot/test", headers=auth(admin_token)).json()["data"]["ok"] is True
    assert visto["access_token"] == "pat-claro-123"


def test_entidad_y_campos_se_validan(client, admin_token):
    r = client.patch(f"{URL}/connectors/hubspot", headers=auth(admin_token), json={"entity": "default"})
    assert r.status_code == 400 and "deals" in r.json()["detail"]
    r = client.patch(f"{URL}/connectors/hubspot", headers=auth(admin_token), json={"config": {"inventado": "1"}})
    assert r.status_code == 400 and "inventado" in r.json()["detail"]
    assert client.patch(f"{URL}/connectors/no-existe", headers=auth(admin_token), json={}).status_code == 404


def test_EL_HALLAZGO_la_fuente_rest_generica_extrae_por_data_path(client, admin_token, monkeypatch):
    pedidas = []

    def get(url, headers=None, timeout=None):
        pedidas.append((url, headers))
        return {"data": {"items": [{"a": 1}, {"a": 2}]}}
    monkeypatch.setattr(etl, "_http_get", get)
    r = client.post(f"{URL}/sources", headers=auth(admin_token), json={"nombre": "Mi ERP", "config": {
        "endpoint_url": "https://erp.example.com/api/pedidos", "data_path": "data.items",
        "header_name": "X-Api-Key", "header_value": "clave-secreta"}})
    assert r.status_code == 200, r.text
    f = r.json()["data"]
    assert (f["connector_id"], f["nombre"], f["personalizado"]) == ("rest.mi-erp", "Mi ERP", True)
    p = client.post(f"{URL}/connectors/rest.mi-erp/test", headers=auth(admin_token)).json()["data"]
    assert p == {"ok": True, "records": 2}
    assert pedidas[-1][1] == {"X-Api-Key": "clave-secreta"}
    client.patch(f"{URL}/connectors/rest.mi-erp", headers=auth(admin_token), json={"config": {"data_path": "data.filas"}})
    p = client.post(f"{URL}/connectors/rest.mi-erp/test", headers=auth(admin_token)).json()["data"]
    assert p["ok"] is False and "filas" in p["error"]
    assert client.post(f"{URL}/sources", headers=auth(admin_token), json={"nombre": "Mi ERP", "config": {"endpoint_url": "https://x.example.com"}}).status_code == 400
    assert client.delete(f"{URL}/sources/rest.mi-erp", headers=auth(admin_token)).status_code == 200
    assert "rest.mi-erp" not in [c["connector_id"] for c in _lista(client, admin_token)["connectors"]]
    assert client.delete(f"{URL}/sources/github", headers=auth(admin_token)).status_code == 404


def test_una_url_interna_no_se_pide(client, admin_token):
    client.post(f"{URL}/sources", headers=auth(admin_token), json={"nombre": "Interna", "config": {"endpoint_url": "https://127.0.0.1/admin"}})
    p = client.post(f"{URL}/connectors/rest.interna/test", headers=auth(admin_token)).json()["data"]
    assert p["ok"] is False and "private" in p["error"]


def test_cada_organizacion_ve_sus_fuentes(db):
    svc.crear_fuente(db, "1", "Solo de la uno", {"endpoint_url": "https://a.example.com"})
    assert "rest.solo-de-la-uno" in [c["connector_id"] for c in svc.listar(db, "1")]
    assert "rest.solo-de-la-uno" not in [c["connector_id"] for c in svc.listar(db, "2")]


def test_la_pasada_periodica_lanza_solo_lo_activo(db, monkeypatch):
    from contextlib import contextmanager

    import app.db.session as sesion
    import app.worker as w

    @contextmanager
    def la_de_pruebas():
        yield db
    monkeypatch.setattr(sesion, "worker_db_session", la_de_pruebas)
    svc.configurar(db, "1", "github", enabled=True)
    svc.configurar(db, "1", "jira", enabled=False)
    lanzadas = []
    monkeypatch.setattr(w.sync_connector_data, "delay", lambda cid, org: lanzadas.append((org, cid)))
    assert w.sincronizar_conectores_etl() == {"lanzadas": 1}
    assert lanzadas == [("1", "github")]
    entradas = [k for k, v in w.celery_app.conf.beat_schedule.items() if "connector" in v["task"] or "conectores_etl" in v["task"]]
    assert entradas == ["bi-connector-sync"]


@pytest.mark.parametrize("tipo", sorted(etl.SUPPORTED_CONNECTORS))
def test_ningun_extractor_se_traga_el_error(tipo, monkeypatch):
    """Cada conector con API HTTP propaga el fallo (antes 17 de 21 devolvían `[]`)."""
    def falla(*a, **kw):
        raise RuntimeError("caída")
    monkeypatch.setattr(etl, "_http_get", falla)
    monkeypatch.setattr(etl, "_http_post", falla)
    c = etl.get_connector(tipo)
    cfg = {k: "x" for k, _ in c.campos}
    if tipo == "google_analytics":
        cfg["credentials_json"] = json.dumps({})
    with pytest.raises(Exception):
        c.extract(c.connect(cfg), entity=c.entidades[0], filters={})


def test_el_registro_respeta_el_tope_de_admin(db, monkeypatch):
    from app.services import settings_service
    monkeypatch.setattr(settings_service, "get_runtime_int", lambda db, k, org=None: 3 if k == "BI_ETL_LOG_MAX_ENTRIES" else 100)
    monkeypatch.setattr(etl, "_http_get", lambda url, headers=None, timeout=None: [])
    svc.configurar(db, "1", "github", enabled=True, config={"repo": "a/b", "token": "x"})
    for _ in range(5):
        svc.sincronizar(db, "1", "github")
    assert len(svc.registro(db, "1", "github", 100)) == 3


def test_sin_su_paquete_no_se_activa_y_lo_dice(client, admin_token):
    """Seis conectores usan un SDK opcional; sin él, la lista lo dice y no se activan."""
    sf = next(c for c in _lista(client, admin_token)["connectors"] if c["connector_id"] == "salesforce")
    if not sf["falta"]:
        pytest.skip("simple-salesforce está instalado aquí")
    assert sf["falta"] == "pip install simple-salesforce"
    r = client.patch(f"{URL}/connectors/salesforce", headers=auth(admin_token), json={"enabled": True})
    assert r.status_code == 400 and "simple-salesforce" in r.json()["detail"]
