"""Ronda 2 de la auditoría 2026-11-22 (23-11-2026), migración 198.

- A-SD19: catálogo de cambios estándar. El tipo lo fija el servidor; un
  estándar necesita un modelo aprobado, vigente y que cubra el cambio; SoD al
  aprobar el modelo; suspensión por tasa de fallo.
- Portal: cambio de contraseña obligatorio con la contraseña generada.
- Proyectos: `contract_amount` en el alta y la edición.
- Migración 198: lo que declara cuadra con los modelos.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import auth

BASE = "/api/v1/sd"
REPO = Path(__file__).resolve().parents[1]


def _modelo(db, **extra):
    from app.models.service_desk import StandardChangeModel
    datos = dict(organization_id="1", name="Reinicio de servicio", procedure="1. Parar 2. Arrancar",
                 max_risk="medium", status="approved", is_active=True, proposed_by="pm-test-id",
                 next_review_at=datetime.now(timezone.utc) + timedelta(days=30))
    datos.update(extra)
    m = StandardChangeModel(**datos)
    db.add(m)
    db.commit()
    return m


def _crear(client, token, **extra):
    datos = {"title": "Reinicio", "description": "Reiniciar el servicio", **extra}
    return client.post(f"{BASE}/changes", headers=auth(token), json=datos)


# ── A-SD19 ───────────────────────────────────────────────────────────────────

def test_declarar_estandar_sin_modelo_no_vale(client, admin_token):
    r = _crear(client, admin_token, change_type="standard")
    assert r.status_code == 422 and r.json().get("code") == "cambio_estandar_sin_modelo", r.text


@pytest.mark.parametrize("extra,motivo", [
    ({"status": "proposed"}, "sin_aprobar"),
    ({"status": "suspended"}, "suspendido"),
    ({"next_review_at": datetime.now(timezone.utc) - timedelta(days=1)}, "caducado"),
    ({"max_risk": "low"}, "riesgo"),
    ({"applies_to_ci_types": json.dumps(["database"])}, "fuera_de_alcance"),
])
def test_un_modelo_que_no_encaja_no_hace_estandar_el_cambio(client, admin_token, db, extra, motivo):
    m = _modelo(db, **extra)
    r = _crear(client, admin_token, change_type="standard", standard_model_id=m.id, risk="medium")
    assert r.status_code == 409, r.text
    assert r.json().get("params", {}).get("motivo") == motivo


def test_el_modelo_de_otra_empresa_no_existe_para_el(client, admin_token, db):
    m = _modelo(db, organization_id="2")
    assert _crear(client, admin_token, change_type="standard", standard_model_id=m.id).status_code == 404


def test_con_modelo_vigente_se_aprueba_solo_y_cuenta_el_uso(client, admin_token, db, monkeypatch):
    from app.models.service_desk import ITSMChangeRequest, StandardChangeModel
    from app.services.service_desk import change_service
    monkeypatch.setattr(change_service, "_auto_score_change", lambda db, ch: setattr(ch, "auto_risk_score", 5.0))
    m = _modelo(db)
    r = _crear(client, admin_token, change_type="standard", standard_model_id=m.id)
    assert r.status_code == 200, r.text
    ch = db.get(ITSMChangeRequest, r.json()["data"]["id"])
    assert ch.status.value == "approved" and ch.standard_model_id == m.id
    assert ch.implementation_plan == m.procedure, "la plantilla rellena el plan vacío"
    assert db.get(StandardChangeModel, m.id).use_count == 1


def test_si_el_modelo_caduca_antes_de_enviar_va_al_cab_como_normal(client, admin_token, db, monkeypatch):
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk import change_service
    monkeypatch.setattr(change_service, "_auto_score_change", lambda db, ch: setattr(ch, "auto_risk_score", 99.0))
    m = _modelo(db)
    cid = _crear(client, admin_token, change_type="standard", standard_model_id=m.id).json()["data"]["id"]
    ch = db.get(ITSMChangeRequest, cid)
    assert ch.status.value == "draft"
    m.next_review_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    change_service._maybe_auto_approve(db, ch)
    assert getattr(ch.change_type, "value", ch.change_type) == "normal"


def test_quien_propone_el_modelo_no_lo_aprueba(client, admin_token, db):
    r = client.post(f"{BASE}/standard-changes", headers=auth(admin_token),
                    json={"name": "Alta de usuario", "procedure": "Pasos del alta"})
    assert r.status_code == 201, r.text
    mid = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "proposed"
    r = client.post(f"{BASE}/standard-changes/{mid}/approve", headers=auth(admin_token))
    assert r.status_code == 403 and r.json().get("code") == "sod_no_puedes_aprobar_lo_tuyo", r.text


def test_la_tasa_de_fallo_suspende_el_modelo(db, monkeypatch):
    from app.models.service_desk import ITSMChangeRequest, StandardChangeModel
    from app.services.service_desk import cambios_estandar_service as svc
    monkeypatch.setattr(svc, "_ajuste_int", lambda db, clave, org: {"SD_STANDARD_CHANGE_MIN_CLOSURES": 2,
                                                                    "SD_STANDARD_CHANGE_MAX_FAILURE_PCT": 40}[clave])
    m = _modelo(db, success_count=1)
    ch = ITSMChangeRequest(number="CHG-T1", title="t", description="d", change_type="standard",
                           standard_model_id=m.id, organization_id="1")
    db.add(ch)
    db.flush()
    svc.anotar_cierre(db, ch, exito=False, usuario=None)
    m = db.get(StandardChangeModel, m.id)
    assert m.failure_count == 1 and m.status == "suspended" and m.suspended_reason.startswith("tasa_de_fallo")


def test_editar_lo_aprobado_lo_devuelve_al_cab(db):
    from app.models.user import User
    from app.services.service_desk import cambios_estandar_service as svc
    admin = db.get(User, "admin-test-id")
    m = _modelo(db, organization_id=admin.organization_id)
    svc.editar_modelo(db, admin, m.id, {"procedure": "Otros pasos"})
    assert m.status == "proposed" and m.approved_at is None


# ── Portal: contraseña generada ──────────────────────────────────────────────

def test_la_contrasena_generada_obliga_a_cambiarla(client, pm_token, db):
    from app.models.client_portal import ClientUser
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Portal", "code": "PCC1", "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    r = client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
        "project_ids": [pid], "full_name": "Cliente", "email": "cambio@ejemplo.com", "language": "es"})
    assert r.status_code == 200, r.text
    cli = db.query(ClientUser).filter(ClientUser.email == "cambio@ejemplo.com").first()
    assert cli.must_change_password is True


def test_el_portal_bloquea_hasta_cambiar_la_contrasena(db):
    from app.core.errores import ErrorDeDominio
    from app.services.client_portal_service.autenticacion import exigir_contrasena_cambiada

    class _C:
        must_change_password = True

    with pytest.raises(ErrorDeDominio) as e:
        exigir_contrasena_cambiada(_C(), "/api/v1/portal/dashboard")
    assert e.value.status_code == 403
    for libre in ("/api/v1/portal/auth/me", "/api/v1/portal/branding", "/api/v1/portal/auth/session-config"):
        exigir_contrasena_cambiada(_C(), libre)


def test_cambiarla_quita_la_marca(db):
    from app.models.client_portal import ClientUser
    from app.services.client_portal_service import hash_password
    from app.services.client_portal_service.clientes import update_my_profile
    cli = ClientUser(organization_id="1", full_name="C", email="marca@ejemplo.com", is_active=True,
                     hashed_password=hash_password("Temporal-123"), must_change_password=True)
    db.add(cli)
    db.commit()
    update_my_profile({"password": "Nueva-clave-456", "current_password": "Temporal-123"}, cli, db)
    assert cli.must_change_password is False


# ── Proyectos: contract_amount ───────────────────────────────────────────────

def test_contract_amount_en_alta_y_edicion(client, pm_token):
    r = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Contrato", "code": "CTR1", "status": "active", "contract_amount": 12000})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["data"]["id"]
    assert r.json()["data"]["contract_amount"] == 12000
    r = client.patch(f"/api/v1/projects/{pid}", headers=auth(pm_token), json={"contract_amount": 15000.5})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).json()["data"]["contract_amount"] == 15000.5


# ── Migración 198 ────────────────────────────────────────────────────────────

def test_198_cuadra_con_los_modelos():
    import app.models  # noqa: F401
    from app.db.base import Base
    spec = importlib.util.spec_from_file_location("m198", REPO / "alembic" / "versions" / "198_cambios_estandar_y_portal.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "197_dinero_numeric"
    md = Base.metadata.tables
    assert mig.MODELOS in md
    assert "standard_model_id" in md[mig.CAMBIOS].c
    assert "must_change_password" in md["client_users"].c
    unicas = {c.name for c in md[mig.PREFS].constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert mig.UQ_PREFS_AHORA in unicas and mig.UQ_PREFS_ANTES not in unicas
