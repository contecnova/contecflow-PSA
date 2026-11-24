"""Aislamiento entre empresas y autorización transversal (auditoría 22-11-2026).

Informe 01 (A1, A2, M1, M2, M3, M9) y la «causa de fondo» del informe 02:

- UPDATE/DELETE masivos acotados a la empresa (antes, sin filtro);
- sesión sin contexto: avisa o cierra, nunca en silencio; contexto de sistema
  declarado y `con_empresa` por iteración;
- RLS: el mismo estado que el ORM (usuario sin empresa ya no abre la base);
- `ServiceBase._scoped` falla en cerrado;
- claves de API y tokens OAuth pasan por la matriz GRC;
- el token OAuth trabaja en la empresa de su app;
- CSRF cubre la cookie del portal;
- las tareas de Celery declaran su contexto.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, update

from app.db import contexto_de_tenant as ctx
from app.db import rls
from app.db.session import TenantIsolationError, con_empresa, contexto_de_sistema
from app.models.mfa import Organization
from app.models.settings import Department
from tests.conftest import TestSession, auth


def _dos_empresas(db):
    db.add(Organization(id="org-b", name="B", slug="org-b", is_active=True))
    db.add_all([Department(name="dep-a", organization_id="1"), Department(name="dep-b", organization_id="org-b")])
    db.commit()


def _nombres(db):
    with contexto_de_sistema(db, "test"):
        return sorted((d.organization_id, d.name) for d in db.query(Department).all())


# ── UPDATE/DELETE masivos ─────────────────────────────────────────────────────

@pytest.mark.parametrize("forma", ["query", "orm", "core"])
def test_EL_HALLAZGO_update_masivo_solo_toca_su_empresa(db, forma):
    _dos_empresas(db)
    s = TestSession()
    try:
        with con_empresa(s, "1"):
            if forma == "query":
                s.query(Department).update({"name": "x"}, synchronize_session=False)
            elif forma == "orm":
                s.execute(update(Department).values(name="x"))
            else:
                s.execute(update(Department.__table__).values(name="x"))
            s.commit()
        assert _nombres(s) == [("1", "x"), ("org-b", "dep-b")]
    finally:
        s.close()


def test_delete_masivo_solo_borra_su_empresa(db):
    _dos_empresas(db)
    s = TestSession()
    try:
        with con_empresa(s, "1"):
            s.query(Department).delete(synchronize_session=False)
            s.execute(delete(Department))
            s.commit()
        assert _nombres(s) == [("org-b", "dep-b")]
    finally:
        s.close()


# ── Sesión sin contexto ───────────────────────────────────────────────────────

def test_sin_contexto_en_modo_cerrar_falla(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "TENANT_SESION_SIN_CONTEXTO", "cerrar")
    s = TestSession()
    try:
        with pytest.raises(TenantIsolationError):
            s.query(Department).all()
        with pytest.raises(TenantIsolationError):
            s.query(Department).update({"name": "x"}, synchronize_session=False)
        with contexto_de_sistema(s, "test: inventario entre empresas"):
            s.query(Department).all()  # declarado: pasa
        with ctx.trabajo_de_sistema("test: tarea"):
            s.query(Department).all()
    finally:
        s.close()


def test_sin_contexto_en_modo_avisar_deja_el_sitio(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "TENANT_SESION_SIN_CONTEXTO", "avisar")
    ctx.SITIOS_SIN_CONTEXTO.clear()
    s = TestSession()
    try:
        s.query(Department).all()
    finally:
        s.close()
    assert any("test_auditoria_2026_11_22_aislamiento.py" in k for k in ctx.SITIOS_SIN_CONTEXTO)


def test_con_empresa_no_abre_sin_empresa_y_restaura(db):
    s = TestSession()
    try:
        with pytest.raises(ValueError):
            with con_empresa(s, None):
                pass
        with con_empresa(s, "1"):
            assert ctx.estado(s.info) == ctx.EMPRESA
        assert "is_superadmin" not in s.info and "organization_id" not in s.info
    finally:
        s.close()


def test_rls_sigue_el_mismo_estado(monkeypatch):
    from app.core.config import settings
    assert rls.tenant_de({"is_superadmin": False, "organization_id": "1"}) == "1"
    assert rls.tenant_de({"is_superadmin": False, "organization_id": None}) == rls.NINGUNA
    assert rls.tenant_de({"is_superadmin": True}) == ""
    assert rls.tenant_de({ctx.CLAVE_SISTEMA: "x"}) == ""
    monkeypatch.setattr(settings, "TENANT_SESION_SIN_CONTEXTO", "cerrar")
    assert rls.tenant_de({}) == rls.NINGUNA
    monkeypatch.setattr(settings, "TENANT_SESION_SIN_CONTEXTO", "avisar")
    assert rls.tenant_de({}) == ""


def test_scoped_falla_en_cerrado_sin_empresa(db):
    from types import SimpleNamespace
    from app.services.base import ServiceBase
    _dos_empresas(db)
    sin_empresa = SimpleNamespace(organization_id=None, is_superadmin=False)
    assert ServiceBase(db, sin_empresa)._scoped(Department).all() == []
    con = SimpleNamespace(organization_id="org-b", is_superadmin=False)
    assert [d.name for d in ServiceBase(db, con)._scoped(Department).all()] == ["dep-b"]


# ── Credenciales delegadas: GRC y empresa ─────────────────────────────────────

def test_EL_HALLAZGO_una_clave_de_api_respeta_la_matriz_grc(client, pm_token, db):
    from app.services import grc_service
    r = client.post("/api/v1/bookings/api-keys", headers=auth(pm_token), json={"name": "i", "scopes": ["read"]})
    clave = r.json()["data"]["key"]
    client.cookies.clear()
    assert client.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 200
    grc_service.upsert_permission(db, "pm", "projects", "ver", allowed=False, updated_by=None)
    db.commit()
    r = client.get("/api/v1/projects", headers={"X-API-Key": clave})
    assert r.status_code == 403 and r.json().get("code") == "grc_politica_deniega", r.text


def test_EL_HALLAZGO_el_token_oauth_lleva_la_empresa_de_su_app(client, pm_token, db):
    from app.models.oauth_apps import OAuthApp, OAuthToken
    app = client.post("/api/v1/developer/apps", headers=auth(pm_token),
                      json={"name": "Integra", "scopes": ["read"]}).json()["data"]
    client.cookies.clear()
    r = client.post("/api/v1/developer/token", json={"grant_type": "client_credentials", "client_id": app["client_id"],
                                                      "client_secret": app["client_secret"], "scope": "read"})
    assert r.status_code == 200, r.text
    fila = db.query(OAuthApp).filter(OAuthApp.client_id == app["client_id"]).one()
    token = db.query(OAuthToken).filter(OAuthToken.app_id == fila.id).one()
    assert token.organization_id == fila.organization_id


def test_app_oauth_sin_empresa_no_emite_tokens(client, pm_token, db):
    # 24-11-2026 (migración 208, empresa obligatoria): ya no puede existir una app OAuth
    # sin empresa; la base lo rechaza (NOT NULL). Antes el test la dejaba sin empresa a
    # mano y comprobaba el 400 `oauth_app_sin_empresa` (que sigue en el código como
    # defensa); ahora comprueba que la base no deja quitarle la empresa y que la app,
    # intacta, sigue emitiendo tokens con la suya.
    from sqlalchemy.exc import IntegrityError
    from app.models.oauth_apps import OAuthApp
    app = client.post("/api/v1/developer/apps", headers=auth(pm_token),
                      json={"name": "Sin", "scopes": ["read"]}).json()["data"]
    with pytest.raises(IntegrityError):
        db.query(OAuthApp).filter(OAuthApp.client_id == app["client_id"]).update(
            {"organization_id": None}, synchronize_session=False)
        db.flush()
    db.rollback()
    client.cookies.clear()
    r = client.post("/api/v1/developer/token", json={"grant_type": "client_credentials", "client_id": app["client_id"],
                                                      "client_secret": app["client_secret"], "scope": "read"})
    assert r.status_code == 200, r.text


# ── CSRF del portal y tareas de Celery ────────────────────────────────────────

def test_la_cookie_del_portal_cuenta_como_autenticacion_por_cookie():
    from starlette.requests import Request
    from app.core.csrf import _uses_cookie_auth
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": [
        (b"cookie", b"portal_access_token=abc")]})
    assert _uses_cookie_auth(req)


def test_las_tareas_de_celery_declaran_su_contexto():
    from app.worker import celery_app

    @celery_app.task(name=f"tests.contexto_{uuid.uuid4().hex[:6]}")
    def _mirar():
        return ctx.motivo_de_sistema({})

    assert _mirar().startswith("tarea:tests.contexto_")
    assert ctx.motivo_de_sistema({}) is None


# ── A1: RLS desarmado ─────────────────────────────────────────────────────────

def test_rls_desarmado_no_arranca_en_produccion(monkeypatch):
    from app import main
    from app.core.config import settings
    monkeypatch.setattr(rls, "estado", lambda _c: {"armed": False, "reason": "conecta como superusuario"})
    monkeypatch.setattr(settings, "RLS_REQUIRED", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="RLS_REQUIRED"):
        main._avisar_si_rls_desarmada()
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    main._avisar_si_rls_desarmada()  # en desarrollo solo avisa
