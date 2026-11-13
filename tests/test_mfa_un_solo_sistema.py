"""Un solo sistema TOTP: el que exige el login (auditoria 2026-11).

Habia dos: `users.mfa_secret`/`users.mfa_enabled` (`/api/v1/auth/mfa/*`, el
que mira el login) y `mfa_configs` (`/api/v1/mfa/*`, el de la pantalla /mfa).
Quien activaba el 2FA en la pantalla creia estar protegido y entraba sin
codigo, y el informe de cumplimiento contaba esa tabla.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pyotp
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.user import User
from app.services import informe_de_cumplimiento as informe
from tests.conftest import _TEST_PASSWORD, auth

RAIZ = Path(__file__).resolve().parents[1]


def _entrar(client):
    return client.post("/api/v1/auth/login", json={"username": "admin", "password": _TEST_PASSWORD})


def _activar_como_la_pantalla(client, token):
    """Las llamadas de `mfaApi` (frontend/src/services/api/_core.ts)."""
    assert client.get("/api/v1/auth/mfa/status", headers=auth(token)).json()["enabled"] is False
    alta = client.post("/api/v1/auth/mfa/setup", headers=auth(token), json={})
    assert alta.status_code == 200, alta.text
    datos = alta.json()
    assert datos["qr_url"].startswith("data:image/png;base64,")
    ok = client.post("/api/v1/auth/mfa/verify-setup", headers=auth(token),
                     json={"code": pyotp.TOTP(datos["secret"]).now()})
    assert ok.status_code == 200, ok.text
    codigos = ok.json()["backup_codes"]
    assert len(codigos) == 8
    estado = client.get("/api/v1/auth/mfa/status", headers=auth(token)).json()
    assert estado["enabled"] is True and estado["backup_codes_remaining"] == 8 and estado["verified_at"]
    return datos["secret"], codigos


def test_EL_HALLAZGO_activar_en_la_pantalla_exige_el_segundo_factor_al_entrar(client, admin_token):
    secreto, respaldo = _activar_como_la_pantalla(client, admin_token)

    reto = _entrar(client).json()
    assert reto.get("mfa_required") is True and not reto.get("access_token"), reto
    malo = client.post("/api/v1/auth/mfa/validate",
                       json={"mfa_challenge_token": reto["mfa_challenge_token"], "code": "000000"})
    assert malo.status_code == 401
    bueno = client.post("/api/v1/auth/mfa/validate",
                        json={"mfa_challenge_token": _entrar(client).json()["mfa_challenge_token"],
                              "code": pyotp.TOTP(secreto).now()})
    assert bueno.status_code == 200, bueno.text

    # Un codigo de respaldo vale una sola vez.
    r = client.post("/api/v1/auth/mfa/validate",
                    json={"mfa_challenge_token": _entrar(client).json()["mfa_challenge_token"], "code": respaldo[0]})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/mfa/validate",
                    json={"mfa_challenge_token": _entrar(client).json()["mfa_challenge_token"], "code": respaldo[0]})
    assert r.status_code == 401


def test_desactivar_en_la_pantalla_deja_entrar_sin_codigo_y_borra_los_de_respaldo(client, admin_token):
    secreto, _ = _activar_como_la_pantalla(client, admin_token)
    r = client.post("/api/v1/auth/mfa/disable", headers=auth(admin_token),
                    json={"code": pyotp.TOTP(secreto).now()})
    assert r.status_code == 200, r.text
    assert not _entrar(client).json().get("mfa_required")
    estado = client.get("/api/v1/auth/mfa/status", headers=auth(admin_token)).json()
    assert (estado["enabled"], estado["backup_codes_remaining"]) == (False, 0)


def test_con_el_2fa_activo_reconfigurar_pide_reautenticacion(client, admin_token):
    _activar_como_la_pantalla(client, admin_token)
    assert client.get("/api/v1/auth/mfa/status", headers=auth(admin_token)).json()["reauth_required"] is True
    assert client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token), json={}).status_code == 401
    r = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token), json={"password": _TEST_PASSWORD})
    assert r.status_code == 200, r.text


def test_no_queda_ninguna_ruta_bajo_api_v1_mfa_ni_un_segundo_almacen(client, admin_token):
    from app.db.base import Base
    from app.main import app
    import app.models.mfa as modelos

    rutas = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in rutas if p.startswith(("/api/v1/mfa", "/api/v2/mfa"))]
    assert client.post("/api/v1/mfa/setup", headers=auth(admin_token)).status_code in (404, 405)
    assert "mfa_configs" not in Base.metadata.tables and not hasattr(modelos, "MFAConfig")
    assert not (RAIZ / "app" / "services" / "mfa_service.py").exists()
    cliente = (RAIZ / "frontend" / "src" / "services" / "api" / "_core.ts").read_text(encoding="utf-8")
    assert "'/mfa/" not in cliente and "'/auth/mfa/verify-setup'" in cliente


def test_el_informe_de_cumplimiento_cuenta_lo_que_exige_el_login(client, admin_token, db):
    def totp():
        return next(c for c in informe.generar(db, "1")["controls"] if c["id"] == "mfa_coverage")["measured"]["totp"]

    antes = totp()
    _activar_como_la_pantalla(client, admin_token)
    db.expire_all()
    assert totp() == antes + 1


# ── La revision 160 ──────────────────────────────────────────────────────────

def _revision_160():
    ruta = RAIZ / "alembic" / "versions" / "160_mfa_un_solo_sistema.py"
    spec = importlib.util.spec_from_file_location("rev160", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_antigua(con):
    for sql in (
        "CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)",
        "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, mfa_enabled BOOLEAN, mfa_secret VARCHAR(512))",
        "CREATE TABLE mfa_configs (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
        "user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id), totp_secret VARCHAR(512) NOT NULL, "
        "is_enabled BOOLEAN, verified_at DATETIME, last_used_at DATETIME, created_at DATETIME)",
        "CREATE TABLE mfa_backup_codes (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
        "mfa_id VARCHAR(36) NOT NULL REFERENCES mfa_configs(id), code_hash VARCHAR(128) NOT NULL, "
        "used_at DATETIME, created_at DATETIME)",
        "CREATE INDEX ix_mfa_backup_codes_mfa_id ON mfa_backup_codes (mfa_id)",
    ):
        con.execute(sa.text(sql))
    filas = {
        # solo en la pantalla: el login no le pedia codigo
        "u-pantalla": (False, None, "v2:pantalla", True),
        # alta pendiente en /auth/mfa (sin verificar): manda la pantalla, que si estaba activa
        "u-pendiente": (False, "v2:pendiente", "v2:pantalla2", True),
        # ya tenia TOTP canonico (distinto): no se toca
        "u-canonico": (True, "v2:canonico", "v2:viejo", True),
        # pantalla sin verificar: no se copia
        "u-sin-verificar": (False, None, "v2:a-medias", False),
        # solo passkeys (mfa_enabled sin secreto): se le anade el TOTP de la pantalla
        "u-passkey": (True, None, "v2:pantalla3", True),
    }
    for uid, (enabled, secreto, legado, activo) in filas.items():
        con.execute(sa.text("INSERT INTO users VALUES (:i, :e, :s)"), {"i": uid, "e": enabled, "s": secreto})
        con.execute(sa.text("INSERT INTO mfa_configs (id, user_id, totp_secret, is_enabled, verified_at) "
                            "VALUES (:c, :i, :t, :a, '2026-05-01 10:00:00')"),
                    {"c": f"c-{uid}", "i": uid, "t": legado, "a": activo})
    con.execute(sa.text("INSERT INTO mfa_backup_codes (id, mfa_id, code_hash) VALUES "
                        "('b1', 'c-u-pantalla', 'h1'), ('b3', 'c-u-sin-verificar', 'h3')"))
    con.execute(sa.text("INSERT INTO mfa_backup_codes (id, mfa_id, code_hash, used_at) VALUES "
                        "('b2', 'c-u-pantalla', 'h2', '2026-05-02 10:00:00')"))


def _subir(con, rev):
    ctx = MigrationContext.configure(con)
    with Operations.context(ctx):
        rev.upgrade()


def test_la_revision_160_copia_los_secretos_de_la_pantalla_y_es_idempotente():
    rev = _revision_160()
    motor = sa.create_engine("sqlite://")
    with motor.begin() as con:
        _base_antigua(con)
        _subir(con, rev)
        _subir(con, rev)   # idempotente
        usuarios = {f.id: (bool(f.mfa_enabled), f.mfa_secret, f.mfa_verified_at is not None)
                    for f in con.execute(sa.text("SELECT * FROM users"))}
        assert usuarios == {
            "u-pantalla": (True, "v2:pantalla", True),
            "u-pendiente": (True, "v2:pantalla2", True),
            "u-canonico": (True, "v2:canonico", False),
            "u-sin-verificar": (False, None, False),
            "u-passkey": (True, "v2:pantalla3", True),
        }
        tablas = set(sa.inspect(con).get_table_names())
        assert "mfa_configs" not in tablas
        cols = {c["name"] for c in sa.inspect(con).get_columns("mfa_backup_codes")}
        assert "user_id" in cols and "mfa_id" not in cols
        # Solo los que valian al entrar: sin usar y de una configuracion activa.
        codigos = con.execute(sa.text("SELECT id, user_id FROM mfa_backup_codes")).fetchall()
        assert [tuple(c) for c in codigos] == [("b1", "u-pantalla")]
    motor.dispose()


def test_tras_la_revision_el_login_exige_el_codigo_al_usuario_de_la_pantalla(client, db):
    """El secreto copiado tal cual vale para `/auth/mfa/validate` (mismo cifrado)."""
    from app.core.encryption import encrypt_value

    secreto = pyotp.random_base32()
    admin = db.query(User).filter(User.username == "admin").one()
    # Lo que deja la revision: el valor de `mfa_configs.totp_secret` sin tocar.
    admin.mfa_secret, admin.mfa_enabled = encrypt_value(secreto), True
    db.commit()
    reto = _entrar(client).json()
    assert reto.get("mfa_required") is True
    r = client.post("/api/v1/auth/mfa/validate",
                    json={"mfa_challenge_token": reto["mfa_challenge_token"], "code": pyotp.TOTP(secreto).now()})
    assert r.status_code == 200, r.text
