"""El panel de sesiones activas estaba vacío para todo el mundo.

Auditoría 2026-08. `user_sessions.organization_id` existe —la puso la auditoría
#7— y **nadie la rellenaba**: `register_or_rotate_user_session` construye la
fila con `user_id`, `refresh_token_jti`, `auth_method` y `created_at`, y nada
más. Así que toda sesión nacía con `organization_id` NULL.

El filtro de tenant es `organization_id == org`, y una fila con NULL **no la ve
su propia organización**. Consecuencia medida:

    GET  /auth/sessions/active     → 0 sesiones, siempre, para cualquier usuario
    DELETE /auth/sessions/{id}     → no encuentra ninguna que revocar

Es el defecto de §3.quater otra vez, y otra vez sin un error en los registros:
una lista vacía, que es exactamente lo que no se investiga. «Revocar este
dispositivo» es además un control de seguridad: no poder usarlo importa.

Por qué no lo veía nada: el sellado automático tampoco lo salva, y no es un
descuido del sellado. El inicio de sesión es **anónimo por definición** —el
usuario todavía no está autenticado cuando se crea la fila—, así que la sesión
de base de datos no tiene contexto publicado y `_sellar_organizacion` sale por
la puerta de atrás. La organización hay que ponerla a mano, y es lo que se hace.

Y por qué no lo veía la suite: hasta esta auditoría `tests/conftest.py` usaba
una factoría sin los escuchadores de producción, así que el filtro no corría en
ningún test. Este fichero salió al registrarlos.
"""
from datetime import datetime, timedelta, timezone

from app.models.sessions import UserSession
from app.models.user import User
from tests.conftest import TEST_PASSWORD, auth


def test_la_fila_de_sesion_lleva_organizacion(client, db):
    """La causa, medida en la fila."""
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text

    admin = db.query(User).filter(User.id == "admin-test-id").first()
    filas = db.query(UserSession).filter(UserSession.user_id == admin.id).all()
    assert filas, "el login no dejó ninguna fila de sesión"

    for fila in filas:
        assert fila.organization_id is not None, (
            "`register_or_rotate_user_session` ha vuelto a crear la sesión sin "
            "organización: el panel de sesiones activas se queda vacío y "
            "«revocar dispositivo» deja de encontrar nada"
        )
        assert str(fila.organization_id) == str(admin.organization_id)


def test_el_panel_de_sesiones_activas_no_esta_vacio(client, admin_token, db):
    """El síntoma, por la puerta de la API y con el filtro puesto."""
    res = client.get("/api/v1/auth/sessions/active", headers=auth(admin_token))
    assert res.status_code == 200, res.text
    sesiones = res.json().get("items")
    assert sesiones, "el panel de sesiones activas está vacío"
    assert "device_name" in sesiones[0]


def test_se_puede_revocar_el_dispositivo(client, admin_token, db):
    """Y el botón de revocar, que es la parte que es un control de seguridad."""
    res = client.get("/api/v1/auth/sessions/active", headers=auth(admin_token))
    sesiones = res.json()["items"]
    assert sesiones

    borrado = client.delete(
        f"/api/v1/auth/sessions/{sesiones[0]['id']}", headers=auth(admin_token))
    assert borrado.status_code == 200, borrado.text
    assert borrado.json().get("ok") is True

    db.expire_all()
    fila = db.query(UserSession).filter(UserSession.id == sesiones[0]["id"]).first()
    assert fila.revoked_at is not None


def test_una_sesion_ajena_no_se_puede_revocar(client, admin_token, db):
    """El filtro tiene que seguir tapando lo que no es tuyo.

    Rellenar `organization_id` no puede convertirse en «ahora se ven todas»: la
    fila de otra organización sigue estando fuera de alcance, y además
    `revoke_one_session` acota por `user_id`. Dos capas, y las dos importan.
    """
    ajena = UserSession(
        user_id="usuario-de-otra-org",
        organization_id="org-ajena",
        refresh_token_jti="jti-ajeno",
        auth_method="password",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(ajena)
    db.commit()

    res = client.get("/api/v1/auth/sessions/active", headers=auth(admin_token))
    assert res.status_code == 200
    assert all(s["id"] != ajena.id for s in res.json()["items"])

    borrado = client.delete(
        f"/api/v1/auth/sessions/{ajena.id}", headers=auth(admin_token))
    assert borrado.status_code in (403, 404), borrado.text

    db.expire_all()
    assert db.query(UserSession).filter(
        UserSession.id == ajena.id).first().revoked_at is None
