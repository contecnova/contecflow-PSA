"""Políticas de cuenta (23-11-2026, docs/seguridad/politicas_de_cuenta.md).

Lo crítico: caducidad y cambio forzado, historial, comunes y datos personales,
bloqueo persistente y desbloqueo, MFA obligatorio con gracia, cierre de sesión
inmediato (`sid`), desactivar revoca, IP permitidas, separación de funciones,
el editor genérico no toca la política y el registro de auditoría inmutable.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import _TEST_PASSWORD, auth

ORG = "1"


@pytest.fixture(autouse=True)
def _sin_cache_de_ajustes():
    from app.services.settings_service.runtime import invalidate_cache
    from app.services.seguridad_de_cuentas.politica import olvidar_cache
    invalidate_cache(None)
    olvidar_cache()
    yield
    invalidate_cache(None)
    olvidar_cache()


def _politica(db, **cambios):
    from app.services.seguridad_de_cuentas import politica
    politica.escribir(db, ORG, politica.validar(cambios, politica.leer(db, ORG)))
    db.commit()


def _login(client, usuario="dev_test", clave=_TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": usuario, "password": clave})


def _token(res):
    assert res.status_code == 200, res.text
    return res.cookies.get("access_token")


def _codigo(res):
    try:
        return res.json().get("code")
    except ValueError:
        return None


def _usuario(db, username="dev_test"):
    from app.models.user import User
    db.expire_all()
    return db.query(User).filter(User.username == username).first()


# ── Contraseñas ─────────────────────────────────────────────────────────────

def test_caducidad_obliga_a_cambiar_y_solo_deja_cambiarla(client, db):
    _politica(db, PASSWORD_EXPIRY_DAYS=30, PASSWORD_EXPIRY_WARNING_DAYS=7)
    u = _usuario(db)
    u.password_changed_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()

    res = _login(client)
    token = _token(res)
    assert res.json()["user"]["account_security"]["password_change_required"] is True

    bloqueada = client.get("/api/v1/projects", headers=auth(token))
    assert bloqueada.status_code == 403 and _codigo(bloqueada) == "contrasena_cambio_obligatorio"
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 200

    cambio = client.post("/api/v1/auth/change-password", headers=auth(token),
                         json={"current_password": _TEST_PASSWORD, "new_password": "Zorro-Azul#Monta2026"})
    assert cambio.status_code == 200, cambio.text
    assert _codigo(client.get("/api/v1/projects", headers=auth(token))) != "contrasena_cambio_obligatorio"

    from app.models.enterprise import AuditLog
    assert db.query(AuditLog).filter(AuditLog.action == "PASSWORD_CHANGED").count() == 1


def test_historial_impide_reutilizar(client, db):
    token = _token(_login(client))
    nueva = "Zorro-Azul#Monta2026"
    assert client.post("/api/v1/auth/change-password", headers=auth(token),
                       json={"current_password": _TEST_PASSWORD, "new_password": nueva}).status_code == 200
    vuelta = client.post("/api/v1/auth/change-password", headers=auth(token),
                         json={"current_password": nueva, "new_password": _TEST_PASSWORD})
    assert vuelta.status_code == 400 and _codigo(vuelta) == "contrasena_reutilizada"
    from app.models.seguridad_de_cuentas import PasswordHistory
    assert db.query(PasswordHistory).filter(PasswordHistory.user_id == _usuario(db).id).count() == 1


def test_comunes_y_datos_personales_sin_red():
    from app.core.errores import ErrorDeDominio
    from app.services.seguridad_de_cuentas.contrasenas import comprobar_reglas, es_comun
    from app.services.seguridad_de_cuentas.politica import Politica
    assert es_comun("Password2024!") and es_comun("qwerty123") and es_comun("aaaaaaaa")
    assert not es_comun("Zorro-Azul#Monta2026")
    with pytest.raises(ErrorDeDominio) as e:
        comprobar_reglas("Password2024!", Politica())
    assert e.value.code == "contrasena_comun"
    with pytest.raises(ErrorDeDominio) as e:
        comprobar_reglas("Marta-Gomez#2026x", Politica(), ("mgomez", "marta@empresa.es", "Marta Gómez"))
    assert e.value.code == "contrasena_con_datos_personales"
    with pytest.raises(ErrorDeDominio) as e:
        comprobar_reglas("Ab1!" + "x" * 200, Politica())
    assert e.value.code == "contrasena_max_caracteres"


# ── Bloqueo ─────────────────────────────────────────────────────────────────

def test_bloqueo_persistente_aviso_y_desbloqueo_por_admin(client, db, admin_token):
    from app.models.enterprise import AuditLog, Notification
    from app.services.seguridad_de_cuentas.bloqueo import al_bloquearse
    al_bloquearse(db, _usuario(db), 600)

    res = _login(client)
    assert res.status_code == 429 and _codigo(res) == "login_bloqueado"
    assert db.query(Notification).filter(Notification.user_id == _usuario(db).id,
                                         Notification.type == "security_alert").count() >= 1

    ok = client.post(f"/api/v1/security/users/{_usuario(db).id}/unlock", headers=auth(admin_token))
    assert ok.status_code == 200, ok.text
    assert _login(client).status_code == 200
    acciones = {a for (a,) in db.query(AuditLog.action)}
    assert {"ACCOUNT_LOCKED", "ACCOUNT_UNLOCKED"} <= acciones


# ── MFA ─────────────────────────────────────────────────────────────────────

def test_mfa_obligatorio_por_rol_pasada_la_gracia_solo_deja_configurarlo(client, db):
    _politica(db, MFA_REQUIRED_ROLES="admin,employee", MFA_GRACE_DAYS=0)
    res = _login(client)
    token = _token(res)
    marcas = res.json()["user"]["account_security"]
    assert marcas["mfa_required"] is True and marcas["mfa_required_by"] == "rol"
    assert _usuario(db).mfa_grace_started_at is not None

    bloqueada = client.get("/api/v1/projects", headers=auth(token))
    assert bloqueada.status_code == 403 and _codigo(bloqueada) == "mfa_configuracion_obligatoria"
    assert client.get("/api/v1/auth/mfa/status", headers=auth(token)).status_code == 200


def test_mfa_con_gracia_deja_entrar(client, db):
    _politica(db, MFA_REQUIRED_ROLES="employee", MFA_GRACE_DAYS=7)
    token = _token(_login(client))
    assert client.get("/api/v1/auth/me", headers=auth(token)).json()["account_security"]["mfa_grace_until"]
    assert _codigo(client.get("/api/v1/projects", headers=auth(token))) != "mfa_configuracion_obligatoria"


# ── Sesiones ────────────────────────────────────────────────────────────────

def test_cerrar_una_sesion_corta_el_token_en_el_acto(client, db, admin_token):
    token = _token(_login(client))
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 200
    sesiones = client.get("/api/v1/security/sessions", headers=auth(admin_token)).json()["items"]
    de_dev = [s for s in sesiones if s["user_id"] == _usuario(db).id]
    assert de_dev
    for s in de_dev:
        assert client.delete(f"/api/v1/security/sessions/{s['id']}", headers=auth(admin_token)).status_code == 200
    res = client.get("/api/v1/auth/me", headers=auth(token))
    assert res.status_code == 401 and _codigo(res) == "sesion_revocada"


def test_desactivar_revoca_sus_sesiones(client, db):
    from app.models.sessions import UserSession
    _token(_login(client))
    u = _usuario(db)
    u.is_active = False
    db.commit()
    vivas = db.query(UserSession).filter(UserSession.user_id == u.id, UserSession.revoked_at.is_(None)).count()
    assert vivas == 0


def test_maximo_de_sesiones_concurrentes(client, db):
    from app.models.sessions import UserSession
    _politica(db, SESSION_MAX_CONCURRENT=1)
    _token(_login(client))
    _token(_login(client))
    vivas = db.query(UserSession).filter(UserSession.user_id == _usuario(db).id,
                                         UserSession.revoked_at.is_(None)).count()
    assert vivas == 1


# ── Acceso ──────────────────────────────────────────────────────────────────

def test_ip_fuera_de_la_lista_no_entra_y_el_superadmin_si(client, db, superadmin_token):
    _politica(db, ACCESS_IP_ALLOWLIST="10.0.0.0/8")
    res = _login(client)
    assert res.status_code == 403 and _codigo(res) == "acceso_ip_no_permitida"
    assert client.get("/api/v1/auth/me", headers=auth(superadmin_token)).status_code == 200


def test_validacion_de_la_politica():
    from app.core.errores import ErrorDeDominio
    from app.services.seguridad_de_cuentas.politica import Politica, validar
    for cambio in ({"ACCESS_IP_ALLOWLIST": "10.0.0.0/33"}, {"ACCESS_HOURS": "25:00-26:00"},
                   {"MFA_ALLOWED_METHODS": "sms"}, {"PASSWORD_HISTORY_COUNT": 99}, {"NO_EXISTE": 1}):
        with pytest.raises(ErrorDeDominio):
            validar(cambio, Politica())


# ── Gobierno ────────────────────────────────────────────────────────────────

def test_separacion_de_funciones_necesita_otro_admin(client, db, admin_token):
    from tests.conftest import HASH_DE_PRUEBA
    from app.models.user import User, UserRole, UserStatus
    from app.services.seguridad_de_cuentas.politica import leer
    _politica(db, SECURITY_SOD_TWO_ADMINS=True)
    pedida = client.put("/api/v1/security/policy", headers=auth(admin_token),
                        json={"changes": {"PASSWORD_HISTORY_COUNT": 7}, "reason": "ISO A.5.17"})
    assert pedida.status_code == 200, pedida.text
    assert pedida.json()["applied"] is False
    sid = pedida.json()["pending_request_id"]

    propia = client.post(f"/api/v1/security/change-requests/{sid}/approve", headers=auth(admin_token), json={})
    assert propia.status_code == 403 and _codigo(propia) == "separacion_de_funciones_misma_persona"

    db.add(User(id="admin2-test-id", username="admin2_test", email="admin2@example.org", full_name="Segundo Admin",
                role=UserRole.admin, status=UserStatus.active, is_active=True, organization_id=ORG,
                hashed_password=HASH_DE_PRUEBA, weekly_capacity_hours=40.0, currency="EUR"))
    db.commit()
    otro = _token(_login(client, "admin2_test"))
    ok = client.post(f"/api/v1/security/change-requests/{sid}/approve", headers=auth(otro), json={})
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert leer(db, ORG).PASSWORD_HISTORY_COUNT == 7


def test_el_editor_generico_no_toca_la_politica(client, admin_token):
    res = client.put("/api/v1/settings/runtime/password_policy/MIN_PASSWORD_LENGTH",
                     headers=auth(admin_token), json={"value": "4"})
    assert res.status_code == 409 and _codigo(res) == "ajuste_grupo_de_seguridad"


def test_el_informe_mide_las_politicas_de_cuenta(db):
    from app.services.informe_de_cumplimiento import generar
    ids = {c["id"] for c in generar(db, ORG)["controls"]}
    assert {"mfa_policy", "passwords_expired", "privileged_accounts", "access_review",
            "superadmin_bypass", "audit_log_immutable"} <= ids


# ── Registro de auditoría inmutable ─────────────────────────────────────────

def test_audit_logs_no_admite_update_ni_delete(tmp_path):
    from app.db import auditoria_inmutable
    motor = create_engine(f"sqlite:///{tmp_path / 'aud.db'}")
    columnas = ", ".join(f'"{c}" TEXT' for c in auditoria_inmutable.COLUMNAS_PROTEGIDAS if c != "seq")
    with motor.begin() as c:
        c.execute(text(f"CREATE TABLE audit_logs ({columnas}, seq INTEGER, user_id TEXT)"))
        c.execute(text("CREATE TABLE audit_log_purge_permits (organization_id TEXT PRIMARY KEY, reason TEXT, "
                       "created_at TEXT, uses INTEGER, active BOOLEAN)"))
        auditoria_inmutable.instalar(c)
        assert auditoria_inmutable.instalados(c)
        c.execute(text("INSERT INTO audit_logs (id, organization_id, action, seq, user_id) "
                       "VALUES ('a', 'o1', 'LOGIN', 1, 'u1'), ('b', 'o1', 'LOGIN', NULL, 'u1')"))
    for sql in ("UPDATE audit_logs SET action = 'X' WHERE id = 'a'", "DELETE FROM audit_logs WHERE id = 'a'"):
        with pytest.raises(Exception, match="solo anadir"):
            with motor.begin() as c:
                c.execute(text(sql))
    with motor.begin() as c:
        c.execute(text("UPDATE audit_logs SET user_id = NULL WHERE id = 'a'"))     # ON DELETE SET NULL
        c.execute(text("UPDATE audit_logs SET seq = 2 WHERE id = 'b'"))           # encadenar filas antiguas
        auditoria_inmutable.abrir_permiso_de_purga(c, "o1")
        c.execute(text("DELETE FROM audit_logs WHERE organization_id = 'o1'"))     # purga de la empresa
        auditoria_inmutable.cerrar_permiso_de_purga(c, "o1")
        assert c.execute(text("SELECT count(*) FROM audit_logs")).scalar() == 0
