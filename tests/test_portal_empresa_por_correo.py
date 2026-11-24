"""Portal: correo único POR EMPRESA y elección de empresa en el login (migración 208, 24-11-2026).

Docs: README §«Portal de clientes» y docs/seguridad/politicas_de_cuenta.md §«Varias empresas con el mismo correo».
"""
import uuid

import pytest

CLAVE = "Clave-del-portal-208"
OTRA = "Otra-clave-portal-208"
SEGUNDA = "org-portal-208"


def _auditorias(db, accion):
    from app.models.enterprise import AuditLog
    return db.query(AuditLog).filter(AuditLog.action == accion).all()


@pytest.fixture()
def dos_cuentas(db):
    """El mismo correo en la empresa de pruebas («1») y en una segunda."""
    from app.models.client_portal import ClientUser
    from app.models.mfa import Organization
    from app.services.client_portal_service import hash_password
    db.add(Organization(id=SEGUNDA, name="Segunda SA", slug="segunda-sa", is_active=True))
    correo = f"varias-{uuid.uuid4().hex[:6]}@portal.com"
    a = ClientUser(full_name="Vera Uno", email=correo, organization_id="1", is_active=True,
                   hashed_password=hash_password(CLAVE))
    b = ClientUser(full_name="Vera Dos", email=correo.upper(), organization_id=SEGUNDA, is_active=True,
                   hashed_password=hash_password(CLAVE))
    db.add_all([a, b])
    db.commit()
    return correo, a, b


def _login(client, correo, clave, **extra):
    return client.post("/api/v1/portal/auth/login", json={"email": correo, "password": clave, **extra})


def test_con_varias_empresas_pide_elegir_sin_token(client, db, dos_cuentas):
    correo, a, b = dos_cuentas
    r = _login(client, correo, CLAVE)
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["choose_organization"] is True
    assert {e["id"] for e in datos["organizations"]} == {"1", SEGUNDA}
    assert "portal_access_token" not in r.cookies


def test_elegir_empresa_entra_en_esa_y_queda_auditado(client, db, dos_cuentas):
    correo, a, b = dos_cuentas
    r = _login(client, correo, CLAVE, organization_id=SEGUNDA)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["client"]["id"] == b.id
    fila = _auditorias(db, "PORTAL_LOGIN_EMPRESA_ELEGIDA")[-1]
    assert fila.organization_id == SEGUNDA and "eleccion" in (fila.metadata_ or "")


def test_no_revela_empresas_donde_la_contrasena_no_vale(client, db, dos_cuentas):
    from app.services.client_portal_service import hash_password
    correo, a, b = dos_cuentas
    b.hashed_password = hash_password(OTRA)
    db.commit()
    r = _login(client, correo, CLAVE)
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert not datos.get("choose_organization") and datos["client"]["id"] == a.id


def test_una_empresa_elegida_donde_la_contrasena_no_vale_es_401(client, db, dos_cuentas):
    from app.services.client_portal_service import hash_password
    correo, a, b = dos_cuentas
    b.hashed_password = hash_password(OTRA)
    db.commit()
    r = _login(client, correo, CLAVE, organization_id=SEGUNDA)
    assert r.status_code == 401 and r.json()["code"] == "credenciales_incorrectas"


def test_el_codigo_de_acceso_resuelve_la_empresa_sin_preguntar(client, db, dos_cuentas):
    correo, a, b = dos_cuentas
    r = _login(client, correo, CLAVE, organization_code="segunda-sa")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["client"]["id"] == b.id
    assert "codigo" in (_auditorias(db, "PORTAL_LOGIN_EMPRESA_ELEGIDA")[-1].metadata_ or "")


def test_un_codigo_que_no_existe_se_ignora(client, db, dos_cuentas):
    correo, a, b = dos_cuentas
    r = _login(client, correo, CLAVE, organization_code="no-existe")
    assert r.json()["data"]["choose_organization"] is True


def test_el_mismo_correo_dos_veces_en_una_empresa_no_se_puede(db, dos_cuentas):
    from sqlalchemy.exc import IntegrityError
    from app.models.client_portal import ClientUser
    correo, a, b = dos_cuentas
    db.add(ClientUser(full_name="Copia", email=correo.title(), organization_id="1", is_active=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_olvido_envia_un_enlace_por_empresa_o_solo_el_del_codigo(client, db, dos_cuentas, monkeypatch):
    from app.services.seguridad_de_cuentas import restablecimiento
    correo, a, b = dos_cuentas
    enviados = []
    monkeypatch.setattr(restablecimiento, "enviar_enlace_al_cliente",
                        lambda _db, cliente, **_k: enviados.append(cliente.organization_id) or True)
    r = client.post("/api/v1/portal/auth/password/forgot", json={"email": correo})
    assert r.status_code == 200
    assert sorted(enviados) == sorted(["1", SEGUNDA])
    enviados.clear()
    r = client.post("/api/v1/portal/auth/password/forgot", json={"email": correo, "organization_code": "segunda-sa"})
    assert r.status_code == 200 and enviados == [SEGUNDA]


def test_la_pantalla_de_restablecer_nombra_la_empresa(client, db, dos_cuentas):
    from app.services.seguridad_de_cuentas.restablecimiento import emitir_token_del_portal
    correo, a, b = dos_cuentas
    p = client.post("/api/v1/portal/auth/password/policy", json={"token": emitir_token_del_portal(b)})
    assert p.status_code == 200, p.text
    assert p.json()["data"]["organization_name"] == "Segunda SA"
