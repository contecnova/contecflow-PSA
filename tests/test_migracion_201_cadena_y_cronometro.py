"""Migración 201: HMAC de la cadena de colaboración y un solo cronómetro abierto (23-11-2026).

- La migración sube desde la 200 cerrando los cronómetros abiertos duplicados,
  baja a la 200 y vuelve a subir sin perder filas.
- La cadena de colaboración firma las filas nuevas con la clave activa del
  llavero (`hmac` + `key_id`), detecta un HMAC cambiado, informa como
  «sin clave» (no rotura) una fila cuyo `kid` ya no está, y sigue validando las
  filas antiguas sin HMAC.
- El servicio del cronómetro traduce el choque con el índice único a 409 con
  código `cronometro_ya_activo` (nunca 500).
"""
import os
import sqlite3
import uuid

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IX = "uq_timer_sessions_un_activo_por_usuario"


def _cfg(url):
    from alembic.config import Config
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _conteo(ruta):
    c = sqlite3.connect(ruta)
    tablas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tablas}


@pytest.fixture
def base_200(tmp_path, monkeypatch):
    from alembic import command
    from app.core.config import settings
    ruta = str(tmp_path / "m201.db")
    url = "sqlite:///" + ruta.replace("\\", "/")
    monkeypatch.setattr(settings, "DATABASE_URL", url, raising=False)
    monkeypatch.setattr(settings, "DATABASE_MIGRATIONS_URL", url, raising=False)
    command.upgrade(_cfg(url), "200_esquema_pendiente_auditoria")
    return ruta, url


def test_la_201_cierra_duplicados_y_va_y_vuelve(base_200):
    from alembic import command
    ruta, url = base_200
    c = sqlite3.connect(ruta)   # sin PRAGMA foreign_keys: basta con ids sueltos
    for tid, usuario, inicio in [("t0", "u1", "2026-11-20 10:00:00"), ("t1", "u1", "2026-11-21 10:00:00"),
                                 ("t2", "u1", "2026-11-22 10:00:00"), ("t3", "u2", "2026-11-22 10:00:00")]:
        c.execute("INSERT INTO timer_sessions (id, user_id, project_id, started_at, paused_duration_secs) "
                  "VALUES (?, ?, 'p', ?, 0)", (tid, usuario, inicio))
    c.commit()
    c.close()
    antes = _conteo(ruta)

    command.upgrade(_cfg(url), "201_cadena_colaboracion_y_cronometro")
    c = sqlite3.connect(ruta)
    abiertos = dict(c.execute("SELECT id, ended_at IS NULL FROM timer_sessions").fetchall())
    assert abiertos == {"t0": 0, "t1": 0, "t2": 1, "t3": 1}   # queda el más reciente de u1
    assert _IX in {r[1] for r in c.execute("PRAGMA index_list('timer_sessions')")}
    cols = {r[1] for r in c.execute("PRAGMA table_info('collaboration_audit_events')")}
    assert {"hmac", "key_id"} <= cols
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO timer_sessions (id, user_id, project_id, started_at, paused_duration_secs) "
                  "VALUES ('t9', 'u1', 'p', '2026-11-23 10:00:00', 0)")
    c.close()
    assert _conteo(ruta) == antes

    command.downgrade(_cfg(url), "200_esquema_pendiente_auditoria")
    c = sqlite3.connect(ruta)
    assert _IX not in {r[1] for r in c.execute("PRAGMA index_list('timer_sessions')")}
    assert not {"hmac", "key_id"} & {r[1] for r in c.execute("PRAGMA table_info('collaboration_audit_events')")}
    c.close()
    assert _conteo(ruta) == antes

    command.upgrade(_cfg(url), "201_cadena_colaboracion_y_cronometro")
    assert _conteo(ruta) == antes


def test_una_sola_cabeza_y_es_la_201():
    from alembic.script import ScriptDirectory
    from alembic.config import Config
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["201_cadena_colaboracion_y_cronometro"]


# ── C5 · HMAC con el llavero ─────────────────────────────────────────────────

def _escribir(db, n, org="1"):
    from app.services.collaboration import _audit
    filas = []
    for i in range(n):
        filas.append(_audit.write(db, organization_id=org, actor_user_id="admin-test-id", actor_client_id=None,
                                  action=f"h.{i}", entity_type="x", entity_id=str(i), payload={"i": i}))
    db.commit()
    return filas


def test_c5_filas_nuevas_llevan_hmac_y_kid_activo(db):
    from app.services.collaboration import _audit
    from app.services.key_management import get_jwt_signing_key
    filas = _escribir(db, 3)
    kid, _ = get_jwt_signing_key()
    assert all(f.hmac and len(f.hmac) == 64 and f.key_id == kid for f in filas)
    r = _audit.verify_chain(db, "1")
    assert r["is_valid"], r["breaks"]
    assert r["unverifiable"] == []


def test_c5_hmac_cambiado_es_rotura(db):
    from app.services.collaboration import _audit
    filas = _escribir(db, 2)
    filas[1].hmac = "0" * 64
    db.commit()
    r = _audit.verify_chain(db, "1")
    assert not r["is_valid"]
    assert any(b.get("hmac") == "no_cuadra" and b["id"] == filas[1].id for b in r["breaks"])


def test_c5_kid_podado_no_es_rotura(db):
    from app.services.collaboration import _audit
    filas = _escribir(db, 2)
    filas[0].key_id = "k-ya-no-existe"
    db.commit()
    r = _audit.verify_chain(db, "1")
    assert r["is_valid"], r["breaks"]
    assert r["unverifiable"] == [filas[0].id]


def test_c5_filas_antiguas_sin_hmac_se_verifican_como_antes(db):
    from app.services.collaboration import _audit
    filas = _escribir(db, 2)
    for f in filas:
        f.hmac = None
        f.key_id = None
    db.commit()
    r = _audit.verify_chain(db, "1")
    assert r["is_valid"], r["breaks"]
    assert r["unverifiable"] == []


# ── M31 · un solo cronómetro abierto ─────────────────────────────────────────

def test_segundo_cronometro_en_carrera_da_409_con_codigo(db, monkeypatch):
    """El índice gana la carrera que la comprobación previa no ve: 409, no 500."""
    from types import SimpleNamespace
    from app.core.errores import ErrorDeDominio
    from app.models.imputation import TimerSession
    from app.models.project import Project, ProjectMember, ProjectStatus, ProjectType
    from app.models.user import User
    from app.services.imputation_service import cronometro

    dev = db.query(User).filter(User.id == "dev-test-id").first()
    proyecto = Project(code="TMR-201-" + uuid.uuid4().hex[:6], name="Cronómetro 201",
                       project_type=ProjectType.development, status=ProjectStatus.active,
                       organization_id=dev.organization_id, pm_id="pm-test-id")
    db.add(proyecto)
    db.flush()
    db.add(ProjectMember(project_id=proyecto.id, user_id=dev.id, is_active=True))
    db.add(TimerSession(user_id=dev.id, project_id=proyecto.id))   # el «otro» clic, ya guardado
    db.commit()

    # La comprobación previa no lo ve (como si el otro proceso aún no hubiera confirmado).
    real = db.query
    vista = {"hecha": False}

    class _Vacia:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    def _query(*entidades, **kw):
        if entidades and entidades[0] is TimerSession and not vista["hecha"]:
            vista["hecha"] = True
            return _Vacia()
        return real(*entidades, **kw)

    monkeypatch.setattr(db, "query", _query)
    with pytest.raises(ErrorDeDominio) as e:
        cronometro.start_timer_session(SimpleNamespace(project_id=proyecto.id, task_id=None), dev, db)
    assert e.value.status_code == 409
    assert e.value.code == "cronometro_ya_activo"
