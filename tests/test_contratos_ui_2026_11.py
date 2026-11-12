"""Auditoria 2026-11 (#25, segunda pasada): contratos entre pantallas y API.

Cada test cubre un desajuste que la pasada de tipos encontro en el frontend:

- TaskUpdate descartaba `start_date` (la columna existia y el alta la aceptaba).
- Ajustes > Usuarios: el alta descartaba tarifa, rol personalizado y zona
  horaria; el listado no mandaba la zona horaria.
- DocumentListOut filtraba `tags` y `version_count`.
- Ingresos (ASC 606): crear una obligacion con `method`/`standalone_price`/
  `notes` era un 500; el diario no decia si una entrada estaba revertida y se
  podia revertir dos veces.
- Chat: `_serialize_message` no mandaba `linked_deliverable_id`/`linked_risk_id`.
- Portal (equipo): `uat_out` no mandaba `issues_count` y el listado de FR no
  traia los datos de la CR que pinta el modal.
"""
import uuid

import pytest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from tests.conftest import auth


def _proyecto(client, token, code="CUI"):
    res = client.post("/api/v1/projects", json={
        "name": f"Contrato UI {code}", "code": f"{code}{uuid.uuid4().hex[:4].upper()}",
        "status": "active", "billing_type": "time_material",
    }, headers=auth(token))
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


# ── Tareas ────────────────────────────────────────────────────────────────────

def test_editar_tarea_guarda_start_date(client, pm_token, db):
    pid = _proyecto(client, pm_token, "TSD")
    tarea = client.post("/api/v1/tasks", json={
        "title": "Con inicio", "project_id": pid, "status": "todo", "priority": "medium",
    }, headers=auth(pm_token)).json()["data"]

    res = client.patch(f"/api/v1/tasks/{tarea['id']}", json={"start_date": "2026-12-01"},
                       headers=auth(pm_token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["start_date"] == "2026-12-01"

    # Y se puede borrar: el frontend manda null cuando el campo queda vacio.
    res = client.patch(f"/api/v1/tasks/{tarea['id']}", json={"start_date": None, "estimated_hours": None},
                       headers=auth(pm_token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["start_date"] is None


def test_tarea_con_cadena_vacia_en_horas_es_422(client, pm_token, db):
    """Lo que mandaba TasksPage antes de limpiar el cuerpo: el servidor no lo acepta."""
    pid = _proyecto(client, pm_token, "TVC")
    res = client.post("/api/v1/tasks", json={
        "title": "Vacia", "project_id": pid, "estimated_hours": "", "due_date": "",
    }, headers=auth(pm_token))
    assert res.status_code == 422


# ── Usuarios ──────────────────────────────────────────────────────────────────

def _rol_personalizado(db, organization_id):
    from app.models.advanced_config import CustomRole

    rol = CustomRole(id=str(uuid.uuid4()), organization_id=organization_id,
                     name=f"Rol {uuid.uuid4().hex[:6]}", is_active=True, is_system=False)
    db.add(rol)
    db.commit()
    return rol


def test_alta_de_usuario_guarda_tarifa_rol_y_zona(client, admin_token, db):
    from app.models.user import User

    admin = db.query(User).filter(User.username == "admin").first()
    rol = _rol_personalizado(db, admin.organization_id)
    res = client.post("/api/v1/users", json={
        "username": "alta.completa", "email": "alta.completa@test.com",
        "full_name": "Alta Completa", "password": "Sup3r-Segura!2026",
        "hourly_rate": "55.5", "timezone": "Europe/Madrid", "custom_role_id": rol.id,
    }, headers=auth(admin_token))
    assert res.status_code == 200, res.text
    creado = res.json()["data"]
    assert creado["custom_role_id"] == rol.id
    assert creado["timezone"] == "Europe/Madrid"
    # La tarifa no viaja en UserPublic: se lee del detalle (UserWithRate).
    assert "hourly_rate" not in creado

    detalle = client.get(f"/api/v1/users/{creado['id']}", headers=auth(admin_token)).json()["data"]
    assert detalle["hourly_rate"] == 55.5

    listado = client.get("/api/v1/users", params={"search": "alta.completa"},
                         headers=auth(admin_token)).json()
    filas = listado if isinstance(listado, list) else listado.get("items", listado.get("data", []))
    fila = next(u for u in filas if u["id"] == creado["id"])
    assert fila["timezone"] == "Europe/Madrid"


def test_alta_de_usuario_con_rol_de_otra_organizacion_es_422(client, admin_token, db):
    from app.models.mfa import Organization

    otra = Organization(id=str(uuid.uuid4()), name="Otra", slug=f"otra-{uuid.uuid4().hex[:6]}")
    db.add(otra)
    db.commit()
    rol = _rol_personalizado(db, otra.id)
    res = client.post("/api/v1/users", json={
        "username": "rol.ajeno", "email": "rol.ajeno@test.com", "full_name": "Rol Ajeno",
        "password": "Sup3r-Segura!2026", "custom_role_id": rol.id,
    }, headers=auth(admin_token))
    assert res.status_code == 422, res.text


def test_tarifa_vacia_es_422_y_null_la_borra(client, admin_token, db):
    res = client.post("/api/v1/users", json={
        "username": "tarifa.null", "email": "tarifa.null@test.com", "full_name": "Tarifa Null",
        "password": "Sup3r-Segura!2026", "hourly_rate": 40,
    }, headers=auth(admin_token))
    assert res.status_code == 200, res.text
    uid = res.json()["data"]["id"]

    # Lo que mandaba la pantalla antes: un '' en un numero.
    assert client.patch(f"/api/v1/users/{uid}", json={"hourly_rate": ""},
                        headers=auth(admin_token)).status_code == 422
    # Lo que manda ahora.
    res = client.patch(f"/api/v1/users/{uid}", json={"hourly_rate": None, "timezone": None},
                       headers=auth(admin_token))
    assert res.status_code == 200, res.text
    assert client.get(f"/api/v1/users/{uid}", headers=auth(admin_token)).json()["data"]["hourly_rate"] is None


def test_solo_admin_da_de_alta_con_tarifa(client, pm_token, db):
    res = client.post("/api/v1/users", json={
        "username": "pm.alta", "email": "pm.alta@test.com", "full_name": "PM Alta",
        "password": "Sup3r-Segura!2026", "hourly_rate": 10,
    }, headers=auth(pm_token))
    assert res.status_code == 403


# ── Documentos ────────────────────────────────────────────────────────────────

def test_listado_de_documentos_trae_etiquetas_y_numero_de_versiones(client, admin_token, db):
    doc = client.post("/api/v1/documents", json={"title": "Con etiquetas", "category": "proposal"},
                      headers=auth(admin_token)).json()["data"]
    assert client.post(f"/api/v1/documents/{doc['id']}/tags", json={"tag": "Legal"},
                       headers=auth(admin_token)).status_code == 200

    res = client.get("/api/v1/documents", headers=auth(admin_token))
    assert res.status_code == 200, res.text
    body = res.json()
    filas = body if isinstance(body, list) else body.get("items", body.get("data", []))
    fila = next(d for d in filas if d["id"] == doc["id"])
    assert fila["tags"] == ["legal"]
    assert fila["version_count"] == 0


# ── Ingresos ASC 606 ──────────────────────────────────────────────────────────

def _contrato(client, token, pid):
    res = client.post("/api/v1/revenue-recognition/contracts", json={
        "project_id": pid, "name": "Contrato ASC", "contract_value": 10000, "method": "milestone",
    }, headers=auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_obligacion_guarda_metodo_precio_y_notas(client, pm_token, db):
    contrato = _contrato(client, pm_token, _proyecto(client, pm_token, "OBL"))
    res = client.post(f"/api/v1/revenue-recognition/contracts/{contrato['id']}/obligations", json={
        "name": "Licencia", "method": "milestone", "standalone_price": 2500, "notes": "Paso 4",
        # Claves que no son del cliente: se ignoran en vez de dar 500.
        "organization_id": "otra", "id": "fijado-por-el-cliente", "inventado": 1,
    }, headers=auth(pm_token))
    assert res.status_code == 200, res.text
    ob = res.json()["data"]
    assert ob["method"] == "milestone"
    assert ob["standalone_price"] == 2500
    assert ob["notes"] == "Paso 4"
    assert ob["id"] != "fijado-por-el-cliente"

    res = client.patch(f"/api/v1/revenue-recognition/obligations/{ob['id']}",
                       json={"standalone_price": 3000, "notes": "Revisada"}, headers=auth(pm_token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["standalone_price"] == 3000
    assert res.json()["data"]["notes"] == "Revisada"


def test_obligacion_con_metodo_desconocido_es_422(client, pm_token, db):
    contrato = _contrato(client, pm_token, _proyecto(client, pm_token, "OBM"))
    res = client.post(f"/api/v1/revenue-recognition/contracts/{contrato['id']}/obligations",
                      json={"name": "Mal", "method": "magia"}, headers=auth(pm_token))
    assert res.status_code == 422


def test_diario_marca_revertidas_y_no_revierte_dos_veces(client, pm_token, db):
    from app.models.revenue import EntryType, RevenueContract, RevenueEntry

    contrato = _contrato(client, pm_token, _proyecto(client, pm_token, "REV"))
    org_id = db.query(RevenueContract.organization_id).filter(RevenueContract.id == contrato["id"]).scalar()
    entrada = RevenueEntry(
        id=str(uuid.uuid4()), organization_id=org_id,
        rev_contract_id=contrato["id"], entry_type=EntryType.recognized, amount=1000.0,
        currency="EUR", period_year=2026, period_month=10, milestone_id=None,
    )
    db.add(entrada)
    db.commit()

    res = client.post(f"/api/v1/revenue-recognition/entries/{entrada.id}/reverse", headers=auth(pm_token))
    assert res.status_code == 200, res.text

    filas = client.get("/api/v1/revenue-recognition/entries", params={"contract_id": contrato["id"]},
                       headers=auth(pm_token)).json()
    filas = filas if isinstance(filas, list) else filas.get("items", filas.get("data", []))
    original = next(f for f in filas if f["id"] == entrada.id)
    assert original["is_reversed"] is True
    assert original["contract_name"] == "Contrato ASC"
    assert original["method"] == "milestone"
    reversion = next(f for f in filas if f["reverses_entry_id"] == entrada.id)
    assert reversion["is_reversed"] is False

    res = client.post(f"/api/v1/revenue-recognition/entries/{entrada.id}/reverse", headers=auth(pm_token))
    assert res.status_code == 400


# ── Chat ──────────────────────────────────────────────────────────────────────

def test_mensaje_serializado_trae_entregable_y_riesgo(db):
    from app.models.collaboration import CollaborationMessage
    from app.schemas.collaboration import MessageOut
    from app.services.collaboration.messages import _serialize_message

    msg = CollaborationMessage(
        id=str(uuid.uuid4()), organization_id="org", conversation_id="conv",
        type="text", status="visible", body="hola", metadata_json={},
        has_attachments=False, is_pinned=False, is_redacted=False,
        sent_at=datetime.now(timezone.utc),
        linked_deliverable_id="del-1", linked_risk_id="risk-1",
    )
    salida = MessageOut(**_serialize_message(db, msg)).model_dump()
    assert salida["linked_deliverable_id"] == "del-1"
    assert salida["linked_risk_id"] == "risk-1"


# ── Portal (vista del equipo) ─────────────────────────────────────────────────

def test_uat_out_trae_issues_count():
    from app.services.client_portal_service.serializacion import uat_out

    sesion = SimpleNamespace(
        id="u1", code="UAT-1", project_id="p", deliverable_id=None, title="UAT", description=None,
        test_environment=None, test_credentials=None, test_guide_url=None, status="pending",
        available_from=None, deadline=None, completed_at=None, client_result=None, client_notes=None,
        test_cases=[],
        issues=[SimpleNamespace(id=f"i{n}", title="Fallo", description=None, severity="high",
                                status="open", steps_to_reproduce=None) for n in range(2)],
    )
    assert uat_out(sesion)["issues_count"] == 2


def test_listado_de_fr_del_equipo_trae_datos_de_la_cr(client, pm_token, db):
    from app.models.resources import ChangeRequest, ChangeRequestImpact
    from app.services.client_portal_service.peticiones import _detalle_de_cr, _peticiones_de_cambio

    pid = _proyecto(client, pm_token, "FRC")
    cr = ChangeRequest(
        id=str(uuid.uuid4()), code="CR-900", project_id=pid, title="Cambio", description="d",
        impact=ChangeRequestImpact.high, cost_impact=1200.0, schedule_impact_days=5,
        resolution_notes="ok", approved_at=date(2026, 11, 2),
    )
    db.add(cr)
    db.commit()

    crs = _peticiones_de_cambio(db, [SimpleNamespace(change_request_id=cr.id),
                                     SimpleNamespace(change_request_id=None)])
    detalle = _detalle_de_cr(crs.get(cr.id))
    assert detalle == {
        "impact": "high", "impact_label": "Alto", "cost_impact": 1200.0,
        "schedule_impact_days": 5, "resolution_notes": "ok",
        "approved_at": "2026-11-02", "implemented_at": None,
    }
    assert _detalle_de_cr(None) == {}


def test_filtro_por_etiqueta_en_el_servidor(client, admin_token, db):
    """El parametro `tags` se aceptaba y se ignoraba (auditoria 2026-11)."""
    con = client.post("/api/v1/documents", json={"title": "Etiquetado", "category": "proposal"},
                      headers=auth(admin_token)).json()["data"]
    sin = client.post("/api/v1/documents", json={"title": "Sin etiqueta", "category": "proposal"},
                      headers=auth(admin_token)).json()["data"]
    client.post(f"/api/v1/documents/{con['id']}/tags", json={"tag": "Contrato"}, headers=auth(admin_token))
    body = client.get("/api/v1/documents", params={"tags": "contrato"}, headers=auth(admin_token)).json()
    ids = {d["id"] for d in (body if isinstance(body, list) else body.get("items", body.get("data", [])))}
    assert con["id"] in ids and sin["id"] not in ids


def test_enlace_de_mensaje_a_otra_organizacion_es_422(db):
    from app.core.errores import ErrorDeDominio
    from app.services.collaboration.messages import _exigir_enlaces_de_la_org
    with pytest.raises(ErrorDeDominio) as e:
        _exigir_enlaces_de_la_org(db, "org-x", None, None, "no-existe", None)
    assert e.value.status_code == 422
    _exigir_enlaces_de_la_org(db, "org-x", None, None, None, None)  # sin enlaces: nada que comprobar
