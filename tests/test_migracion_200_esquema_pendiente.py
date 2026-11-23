"""Migracion 200: esquema pendiente de la auditoria 2026-11-22 (23-11-2026).

Sube una base SQLite vacia hasta la 199, siembra los blobs de `AppSetting` que
la 200 mueve a tablas propias, sube a la 200, baja a la 199 y vuelve a subir:
los datos van y vuelven, el numero de filas por tabla se conserva y las FK
quedan con la accion que dicen los modelos.
"""
import json
import os
import sqlite3
import uuid

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
def base_199(tmp_path, monkeypatch):
    from alembic import command
    from app.core.config import settings
    ruta = str(tmp_path / "m200.db")
    url = "sqlite:///" + ruta.replace("\\", "/")
    monkeypatch.setattr(settings, "DATABASE_URL", url, raising=False)
    monkeypatch.setattr(settings, "DATABASE_MIGRATIONS_URL", url, raising=False)
    command.upgrade(_cfg(url), "199_seguridad_de_cuentas")
    return ruta, url


def _sembrar(ruta):
    c = sqlite3.connect(ruta)
    org = str(uuid.uuid4())
    c.execute("INSERT INTO organizations (id, name, slug, is_active) VALUES (?, 'M200', ?, 1)", (org, "m200-" + org[:8]))
    sesiones = {"s-1": {"id": "s-1", "caller_id": "+34 600 111 222", "status": "closed", "intent": "incident",
                        "entities": {}, "transcript": [{"speaker": "user", "text": "no va"}],
                        "created_at": "2026-11-20T10:00:00+00:00", "closed_at": "2026-11-20T10:05:00+00:00"}}
    ins = 'INSERT INTO app_settings (id, "key", organization_id, value) VALUES (?, ?, ?, ?)'
    c.execute(ins, (str(uuid.uuid4()), "sd.voice_agent.sessions", org, json.dumps(sesiones)))
    c.execute(ins, (str(uuid.uuid4()), "sd.dynamic_forms.rules", org, json.dumps({"version": 2, "fields": []})))
    c.execute(ins, (str(uuid.uuid4()), "sd.dynamic_forms.history", org,
                    json.dumps([{"snapshot_id": "h-1", "created_at": "2026-11-19T10:00:00+00:00", "rules": {}}])))
    c.commit()
    return org


def test_la_200_sube_baja_y_vuelve_a_subir_sin_perder_datos(base_199):
    from alembic import command
    ruta, url = base_199
    org = _sembrar(ruta)
    antes = _conteo(ruta)

    command.upgrade(_cfg(url), "200_esquema_pendiente_auditoria")
    c = sqlite3.connect(ruta)
    assert c.execute("SELECT count(*) FROM sd_voice_sessions WHERE organization_id = ?", (org,)).fetchone()[0] == 1
    fila = c.execute("SELECT caller_id_last4, caller_id_enc, caller_id_hash FROM sd_voice_sessions").fetchone()
    assert fila[0] == "1222" and fila[1].startswith(("v2:", "kmsv1:")) and "600" not in fila[1] and fila[2]
    assert c.execute("SELECT count(*) FROM sd_dynamic_form_rule_history").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM app_settings WHERE \"key\" LIKE 'sd.%'").fetchone()[0] == 0
    # A-MOD1: hacia organizations, CASCADE; B-MOD1: ya no hay columnas org_id.
    acciones = {r[3]: r[6] for r in c.execute("PRAGMA foreign_key_list('alerts')")}
    assert acciones["organization_id"] == "CASCADE"
    assert "org_id" not in {r[1] for r in c.execute("PRAGMA table_info('security_events')")}
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.close()

    command.downgrade(_cfg(url), "199_seguridad_de_cuentas")
    assert _conteo(ruta) == antes
    c = sqlite3.connect(ruta)
    valor = c.execute("SELECT value FROM app_settings WHERE \"key\" = 'sd.voice_agent.sessions'").fetchone()[0]
    assert json.loads(valor)["s-1"]["caller_id"] == "+34 600 111 222"
    assert "org_id" in {r[1] for r in c.execute("PRAGMA table_info('security_events')")}
    c.close()

    command.upgrade(_cfg(url), "200_esquema_pendiente_auditoria")
    assert sqlite3.connect(ruta).execute("SELECT count(*) FROM sd_voice_sessions").fetchone()[0] == 1


def test_una_sola_cabeza():
    # La cabeza concreta la comprueba el test de la última migración (201).
    from alembic.script import ScriptDirectory
    from alembic.config import Config
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


def test_los_modelos_no_tienen_fk_sin_ondelete():
    import app.models  # noqa: F401
    from app.db.base import Base
    sin = [f"{t.name}.{fk.parent.name}" for t in Base.metadata.tables.values() for fk in t.foreign_keys
           if not fk.ondelete]
    assert sin == []
