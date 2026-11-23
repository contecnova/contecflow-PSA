"""«¿Olvidaste tu contraseña?» (operador y portal) y restablecimiento forzado (23-11-2026).

Incidencia de usuario: «No hay función de restablecer contraseña para los usuarios».
Detalle en docs/seguridad/politicas_de_cuenta.md §3 bis.
"""
import time
import uuid

import jwt
import pytest

from tests.conftest import auth


def _auditorias(db, accion):
    from app.models.enterprise import AuditLog
    return db.query(AuditLog).filter(AuditLog.action == accion).all()


# ── Comunes ───────────────────────────────────────────────────────────────────

def test_reclamar_jti_solo_vale_una_vez():
    from app.services.auth_service.estado_efimero import store_password_reset_jti
    from app.services.seguridad_de_cuentas.restablecimiento import reclamar_jti
    clave = f"prueba-{uuid.uuid4().hex}"
    store_password_reset_jti(clave, "jti-1", 60)
    assert reclamar_jti(clave, "otro") is False
    assert reclamar_jti(clave, "jti-1") is True
    assert reclamar_jti(clave, "jti-1") is False


def test_la_huella_no_guarda_el_correo():
    from app.services.seguridad_de_cuentas.restablecimiento import huella
    h = huella("Ana@Ejemplo.com ")
    assert "ana" not in h and h == huella("ana@ejemplo.com")


# ── Operador ──────────────────────────────────────────────────────────────────

def test_operador_el_enlace_es_de_un_solo_uso_y_audita(client, db):
    from app.models.user import User
    from app.services.auth_service import issue_password_reset_token
    admin = db.query(User).filter(User.username == "admin").first()
    token = issue_password_reset_token(admin)
    politica = client.post("/api/v1/auth/password/reset/policy", json={"token": token})
    assert politica.status_code == 200, politica.text
    assert politica.json()["MIN_PASSWORD_LENGTH"] >= 8
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Restablecida-2026-xyz!"})
    assert r.status_code == 200, r.text
    otra = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "Otra-distinta-2026-xyz!"})
    assert otra.status_code == 401 and otra.json().get("code") == "reset_token_no_valido"
    assert _auditorias(db, "PASSWORD_RESET_COMPLETE")


def test_operador_la_politica_se_aplica_al_restablecer(client, db):
    from app.models.user import User
    from app.services.auth_service import issue_password_reset_token
    admin = db.query(User).filter(User.username == "admin").first()
    token = issue_password_reset_token(admin)
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "corta"})
    assert r.status_code == 400 and r.json().get("code", "").startswith("contrasena_")
    # El token no se ha gastado: sigue valiendo para una contraseña buena.
    assert client.post("/api/v1/auth/password/reset/policy", json={"token": token}).status_code == 200


def test_operador_la_politica_exige_token_valido(client, db):
    r = client.post("/api/v1/auth/password/reset/policy", json={"token": "no-es-un-token"})
    assert r.status_code == 401


def test_operador_olvido_sin_cuenta_no_apunta_nada(client, db):
    antes = len(_auditorias(db, "PASSWORD_RESET_REQUEST"))
    r = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "nadie-existe@ejemplo.com"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(_auditorias(db, "PASSWORD_RESET_REQUEST")) == antes
    r = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "admin"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(_auditorias(db, "PASSWORD_RESET_REQUEST")) == antes + 1


def test_operador_forzar_restablecimiento(client, db, admin_token):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    r = client.post(f"/api/v1/security/users/{dev.id}/force-password-reset", headers=auth(admin_token),
                    json={"reason": "Sospecha de robo de credenciales", "send_link": True})
    assert r.status_code == 200, r.text
    db.refresh(dev)
    assert dev.password_must_change is True
    fila = _auditorias(db, "PASSWORD_RESET_FORCED")[-1]
    assert "Sospecha" in (fila.metadata_ or "")


def test_operador_forzar_exige_motivo_y_no_a_si_mismo(client, db, admin_token):
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    sin_motivo = client.post(f"/api/v1/security/users/{admin.id}/force-password-reset",
                             headers=auth(admin_token), json={})
    assert sin_motivo.status_code == 422
    propio = client.post(f"/api/v1/security/users/{admin.id}/force-password-reset",
                         headers=auth(admin_token), json={"reason": "prueba"})
    assert propio.status_code == 403


# ── Portal de clientes ────────────────────────────────────────────────────────

@pytest.fixture()
def contacto(db):
    from app.models.client_portal import ClientUser
    from app.services.client_portal_service import hash_password
    c = ClientUser(full_name="Berta Portal", email=f"berta-{uuid.uuid4().hex[:6]}@portal.com",
                   organization_id="1", is_active=True, hashed_password=hash_password("Clave-inicial-1"))
    db.add(c)
    db.commit()
    return c


def _token_del_portal_emitido_hace(client_id: str, segundos: int) -> str:
    from app.core.config import settings
    from app.services.client_portal_service import ALGORITHM, CLIENT_TOKEN_SECRET
    horas = float(getattr(settings, "CLIENT_TOKEN_EXPIRE_HOURS", 72) or 72)
    exp = int(time.time() + horas * 3600) - segundos
    return jwt.encode({"sub": client_id, "exp": exp, "type": "client", "jti": uuid.uuid4().hex},
                      CLIENT_TOKEN_SECRET, algorithm=ALGORITHM)


def test_portal_olvido_responde_igual_y_solo_audita_si_existe(client, db, contacto):
    antes = len(_auditorias(db, "PORTAL_PASSWORD_RESET_REQUEST"))
    a = client.post("/api/v1/portal/auth/password/forgot", json={"email": "nadie@portal.com"})
    b = client.post("/api/v1/portal/auth/password/forgot", json={"email": contacto.email})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert len(_auditorias(db, "PORTAL_PASSWORD_RESET_REQUEST")) == antes + 1


def test_portal_restablecer_aplica_politica_un_solo_uso_y_cierra_sesiones(client, db, contacto):
    from app.core.security import verify_client_token
    from app.services.seguridad_de_cuentas.restablecimiento import emitir_token_del_portal
    vieja = _token_del_portal_emitido_hace(contacto.id, 30)
    assert verify_client_token(vieja, db) is not None
    token = emitir_token_del_portal(contacto)

    p = client.post("/api/v1/portal/auth/password/policy", json={"token": token})
    assert p.status_code == 200, p.text
    assert p.json()["data"]["PASSWORD_HISTORY_COUNT"] == 0

    corta = client.post("/api/v1/portal/auth/password/reset", json={"token": token, "new_password": "abc"})
    assert corta.status_code == 400 and corta.json()["code"] == "contrasena_corta"
    igual = client.post("/api/v1/portal/auth/password/reset", json={"token": token, "new_password": "Clave-inicial-1"})
    assert igual.status_code == 400 and igual.json()["code"] == "portal_contrasena_igual_a_la_anterior"

    ok = client.post("/api/v1/portal/auth/password/reset", json={"token": token, "new_password": "Nueva-clave-portal-2026"})
    assert ok.status_code == 200, ok.text
    otra = client.post("/api/v1/portal/auth/password/reset", json={"token": token, "new_password": "Otra-clave-portal-2026"})
    assert otra.status_code == 401 and otra.json()["code"] == "portal_reset_token_no_valido"

    assert verify_client_token(vieja, db) is None   # la sesión anterior queda cerrada
    login = client.post("/api/v1/portal/auth/login", json={"email": contacto.email, "password": "Nueva-clave-portal-2026"})
    assert login.status_code == 200, login.text
    assert _auditorias(db, "PORTAL_PASSWORD_RESET_COMPLETE")


def test_portal_token_del_operador_no_vale_en_el_portal(client, db, contacto):
    from app.models.user import User
    from app.services.auth_service import issue_password_reset_token
    admin = db.query(User).filter(User.username == "admin").first()
    r = client.post("/api/v1/portal/auth/password/reset",
                    json={"token": issue_password_reset_token(admin), "new_password": "Nueva-clave-portal-2026"})
    assert r.status_code == 401 and r.json()["code"] == "portal_reset_token_no_valido"


def test_portal_el_corte_no_tumba_el_login_posterior(contacto):
    from app.services.seguridad_de_cuentas import restablecimiento as r
    r.cerrar_sesiones_del_portal(contacto.id)
    anterior = jwt.decode(_token_del_portal_emitido_hace(contacto.id, 30), options={"verify_signature": False})
    posterior = jwt.decode(_token_del_portal_emitido_hace(contacto.id, -2), options={"verify_signature": False})
    assert r.sesion_del_portal_cortada(anterior) is True
    assert r.sesion_del_portal_cortada(posterior) is False


def test_portal_forzar_restablecimiento(client, db, admin_token, contacto):
    from app.core.security import verify_client_token
    vieja = _token_del_portal_emitido_hace(contacto.id, 30)
    r = client.post(f"/api/v1/portal/clients/{contacto.id}/force-password-reset", headers=auth(admin_token),
                    json={"reason": "El cliente lo pide por teléfono"})
    assert r.status_code == 200, r.text
    db.refresh(contacto)
    assert contacto.must_change_password is True
    assert verify_client_token(vieja, db) is None
    fila = _auditorias(db, "PORTAL_PASSWORD_RESET_FORCED")[-1]
    assert "teléfono" in (fila.metadata_ or "") or "tel" in (fila.metadata_ or "")


def test_portal_forzar_exige_capacidad(client, db, dev_token, contacto):
    r = client.post(f"/api/v1/portal/clients/{contacto.id}/force-password-reset", headers=auth(dev_token),
                    json={"reason": "no debería poder"})
    assert r.status_code == 403
