"""Baja definitiva de una empresa y «entrar como» (revisión multitenant 2026-11)."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

from app.models.mfa import Organization
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User, UserOrganizationMembership, UserRole
from tests.conftest import HASH_DE_PRUEBA, auth


def _empresa(db, org_id="org-baja", con_usuario_compartido=False):
    db.add(Organization(id=org_id, name="Empresa Baja", slug=org_id))
    db.flush()
    db.add(User(id="u-baja", username="u_baja", email="u@baja.com", full_name="U Baja", role=UserRole.admin,
                is_active=True, organization_id=org_id, hashed_password=HASH_DE_PRUEBA))
    db.add(Project(code="BAJ1", name="Proyecto Baja", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id=org_id))
    if con_usuario_compartido:
        db.add(User(id="u-mixto", username="u_mixto", email="mixto@baja.com", full_name="Mixto", role=UserRole.pm,
                    is_active=True, organization_id=org_id, hashed_password=HASH_DE_PRUEBA))
        db.flush()
        db.add(UserOrganizationMembership(user_id="u-mixto", organization_id="1"))
    db.commit()


def test_pedir_la_baja_suspende_y_abre_la_cuarentena_y_se_puede_deshacer(client, superadmin_token, db):
    _empresa(db)
    h = auth(superadmin_token)
    assert client.post("/api/v1/organizations/org-baja/deletion", headers=h, json={"reason": ""}).status_code == 422
    r = client.post("/api/v1/organizations/org-baja/deletion", headers=h, json={"reason": "Fin de contrato"})
    assert r.status_code == 200, r.text
    db.expire_all()
    org = db.get(Organization, "org-baja")
    assert org.is_active is False and org.deletion_purge_after is not None
    assert (org.deletion_purge_after - org.deletion_requested_at).days == 30
    assert client.delete("/api/v1/organizations/org-baja/deletion", headers=h).status_code == 200
    db.expire_all()
    assert db.get(Organization, "org-baja").deletion_purge_after is None


def test_la_exportacion_trae_todo_lo_suyo_y_nada_ajeno(client, superadmin_token, db):
    _empresa(db)
    r = client.get("/api/v1/organizations/org-baja/export", headers=auth(superadmin_token))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    proyectos = json.loads(zf.read("projects.json"))
    assert [p["code"] for p in proyectos] == ["BAJ1"]
    usuarios = json.loads(zf.read("users.json"))
    assert [u["email"] for u in usuarios] == ["u@baja.com"] and "hashed_password" not in usuarios[0]


def test_EL_HALLAZGO_al_vencer_la_cuarentena_se_borra_todo_lo_suyo(db):
    from app.services.baja_de_empresa_service import purgar_caducadas
    _empresa(db, con_usuario_compartido=True)
    otro = Project(code="UNO9", name="De la 1", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id="1")
    db.add(otro)
    org = db.get(Organization, "org-baja")
    org.is_active = False
    org.deletion_purge_after = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    hechas = purgar_caducadas(db)
    assert [h["organization_id"] for h in hechas] == ["org-baja"]
    db.expire_all()
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        assert db.get(Organization, "org-baja") is None
        assert db.query(Project).filter(Project.organization_id == "org-baja").count() == 0
        assert db.get(User, "u-baja") is None
        mixto = db.get(User, "u-mixto")
        assert mixto is not None and mixto.organization_id == "1", "pertenece a otra: se queda en ella"
        assert db.get(Project, otro.id) is not None, "lo de otras empresas no se toca"


def test_una_baja_sin_vencer_no_se_borra(db):
    from app.services.baja_de_empresa_service import purgar_caducadas
    _empresa(db)
    db.get(Organization, "org-baja").deletion_purge_after = datetime.now(timezone.utc) + timedelta(days=3)
    db.commit()
    assert purgar_caducadas(db) == []


# ── Entrar como ──────────────────────────────────────────────────────────────

def test_entrar_como_pide_motivo_queda_auditado_y_veda_credenciales(client, superadmin_token, db):
    from app.models.enterprise import AuditLog
    h = auth(superadmin_token)
    r = client.post("/api/v1/organizations/1/impersonate", headers=h, json={"user_id": "pm-test-id", "reason": ""})
    assert r.status_code == 422
    r = client.post("/api/v1/organizations/1/impersonate", headers=h,
                    json={"user_id": "pm-test-id", "reason": "Ticket de soporte 123"})
    assert r.status_code == 200, r.text
    token = r.cookies.get("access_token")
    me = client.get("/api/v1/auth/me", headers=auth(token)).json()
    assert me["id"] == "pm-test-id" and me["impersonated_by"]
    assert client.post("/api/v1/auth/change-password", headers=auth(token),
                       json={"current_password": "x", "new_password": "y"}).status_code == 403
    assert client.get("/api/v1/projects", headers=auth(token)).status_code == 200
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        fila = db.query(AuditLog).filter(AuditLog.action == "IMPERSONATION_START").one()
    assert fila.organization_id == "1"


def test_entrar_como_se_puede_desactivar(client, superadmin_token, db):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "tenants", "IMPERSONATION_ENABLED", False, None)
    db.commit()
    settings_service.invalidate_cache()
    r = client.post("/api/v1/organizations/1/impersonate", headers=auth(superadmin_token),
                    json={"user_id": "pm-test-id", "reason": "x"})
    assert r.status_code == 403
