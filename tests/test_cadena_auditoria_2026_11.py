"""Registro de auditoría a prueba de manipulación (revisión 2026-11).

Cada prueba manipula la tabla como lo haría alguien con acceso a la base (SQL
directo, sin la clave) y comprueba que la verificación lo encuentra y dice
dónde, y cuántas filas miró.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.models.enterprise import AuditLog
from app.models.mfa import Organization
from app.models.user import User
from app.services import cadena_auditoria as cadena
from app.services.audit import audit_log
from tests.conftest import auth


def _admin(db):
    return db.query(User).filter(User.username == "admin").first()


def _escribir(db, n, org="1"):
    for i in range(n):
        db.add(AuditLog(action="UPDATE", resource="projects", resource_id=f"p{i}", resource_name=f"P{i}",
                        user_name="Ana", new_values='{"status": "active"}', organization_id=org))
        db.commit()


def _filas(db, org="1"):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return db.query(AuditLog).filter(AuditLog.organization_id == org).order_by(AuditLog.seq).all()


def test_cada_fila_se_encadena_con_la_anterior_y_la_verificacion_dice_cuantas_mira(db):
    _escribir(db, 3)
    audit_log(db, _admin(db), "CREATE", "tasks", "t1", "Tarea")   # el servicio de siempre
    db.commit()
    filas = _filas(db)
    assert [f.seq for f in filas] == list(range(1, len(filas) + 1))
    assert filas[0].prev_hash == cadena.CERO
    assert all(b.prev_hash == a.entry_hash for a, b in zip(filas, filas[1:], strict=False))
    r = cadena.verificar(db, "1")
    assert r["ok"] and r["rows_checked"] == len(filas) >= 4
    assert r["head"] == {"seq": filas[-1].seq, "entry_hash": filas[-1].entry_hash}


def test_varias_filas_en_el_mismo_flush(db):
    for i in range(3):
        db.add(AuditLog(action="DELETE", resource="tasks", resource_id=f"t{i}", organization_id="1"))
    db.commit()
    assert cadena.verificar(db, "1")["ok"]


def test_EL_HALLAZGO_una_fila_cambiada_por_sql_se_detecta(db):
    _escribir(db, 4)
    victima = _filas(db)[1]
    db.execute(text("UPDATE audit_logs SET new_values = '{\"status\": \"closed\"}' WHERE id = :i"), {"i": victima.id})
    db.commit()
    db.expire_all()
    r = cadena.verificar(db, "1")
    assert not r["ok"] and r["rows_checked"] == 4
    assert {"id": victima.id, "seq": victima.seq, "reason": "hash_mismatch"} in r["breaks"]


def test_recalcular_la_huella_sin_la_clave_tampoco_sirve(db):
    import hashlib
    _escribir(db, 2)
    f = _filas(db)[0]
    otra = hashlib.sha256(b"inventada").digest()
    falsa = cadena.huella(otra, {**cadena._fila_de(f), "new_values": "{}"}, f.seq, f.prev_hash)
    db.execute(text("UPDATE audit_logs SET new_values = '{}', entry_hash = :h WHERE id = :i"), {"h": falsa, "i": f.id})
    db.commit()
    db.expire_all()
    razones = {b["reason"] for b in cadena.verificar(db, "1")["breaks"]}
    assert "hash_mismatch" in razones and "prev_mismatch" in razones   # y la siguiente ya no casa


def test_borrar_una_del_medio_deja_un_hueco(db):
    _escribir(db, 4)
    db.execute(text("DELETE FROM audit_logs WHERE id = :i"), {"i": _filas(db)[1].id})
    db.commit()
    db.expire_all()
    r = cadena.verificar(db, "1")
    assert not r["ok"] and r["breaks"][0]["reason"] == "seq_gap" and r["breaks"][0]["expected_seq"] == 2


def test_borrar_las_ultimas_solo_se_ve_contra_una_cabeza_guardada(db):
    _escribir(db, 3)
    cabeza = cadena.verificar(db, "1")["head"]
    db.execute(text("DELETE FROM audit_logs WHERE id = :i"), {"i": _filas(db)[-1].id})
    db.commit()
    db.expire_all()
    assert cadena.verificar(db, "1")["ok"]          # la cadena que queda está entera…
    r = cadena.verificar(db, "1", cabeza)            # …pero la cabeza exportada ya no está
    assert not r["ok"] and r["expected_head"] == {"seq": cabeza["seq"], "found": False}


def test_cada_empresa_tiene_su_cadena(db):
    db.add(Organization(id="org-cad", name="Otra", slug="org-cad"))
    db.commit()
    _escribir(db, 2, "org-cad")
    _escribir(db, 1)
    assert [f.seq for f in _filas(db, "org-cad")] == [1, 2]
    db.execute(text("UPDATE audit_logs SET action = 'X' WHERE organization_id = 'org-cad'"))
    db.commit()
    db.expire_all()
    assert cadena.verificar(db, "1")["ok"] and not cadena.verificar(db, "org-cad")["ok"]


def test_borrar_un_usuario_no_rompe_la_cadena(db):
    _escribir(db, 1)
    audit_log(db, _admin(db), "UPDATE", "projects", "p9", "P9")
    db.commit()
    db.execute(text("UPDATE audit_logs SET user_id = NULL"))   # lo que hace ON DELETE SET NULL
    db.commit()
    db.expire_all()
    assert cadena.verificar(db, "1")["ok"]


def test_rotar_secret_key_con_la_anterior_declarada(db, monkeypatch):
    _escribir(db, 2)
    viejo = settings.SECRET_KEY
    monkeypatch.setattr(settings, "SECRET_KEY", viejo + "-nuevo")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    assert {b["reason"] for b in cadena.verificar(db, "1")["breaks"]} == {"unknown_key"}
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", viejo)
    _escribir(db, 1)                                   # la nueva fila, con la clave nueva
    assert cadena.verificar(db, "1")["ok"]


def test_la_exportacion_va_firmada_y_un_cambio_la_invalida(db):
    _escribir(db, 3)
    doc = cadena.exportar(db, "1", limite=2)
    assert cadena.comprobar_firma(doc)
    assert doc["truncated"] and [e["seq"] for e in doc["entries"]] == [2, 3]
    assert doc["head"]["seq"] == 3 and doc["verification"]["ok"]
    doc["entries"][0]["new_values"] = "{}"
    assert not cadena.comprobar_firma(doc)


def test_endpoints_solo_admin_y_la_exportacion_queda_auditada(client, db, admin_token, pm_token):
    _escribir(db, 2)
    r = client.get("/api/v1/enterprise/audit-log/chain/verify", headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["data"]["ok"]
    r = client.get("/api/v1/enterprise/audit-log/chain/export", headers=auth(admin_token))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert cadena.comprobar_firma(r.json())
    db.expire_all()
    assert _filas(db)[-1].resource == "audit_chain" and _filas(db)[-1].action == "EXPORT"
    assert cadena.verificar(db, "1")["ok"]
    pem = client.get("/api/v1/enterprise/audit-log/chain/public-key", headers=auth(admin_token)).json()["data"]
    assert pem["public_key_pem"] == r.json()["public_key_pem"]
    for url in ("verify", "export", "public-key"):
        assert client.get(f"/api/v1/enterprise/audit-log/chain/{url}", headers=auth(pm_token)).status_code == 403


@pytest.mark.parametrize("cambio", ["action", "created_at"])
def test_cualquier_campo_de_la_huella_cuenta(db, cambio):
    _escribir(db, 1)
    f = _filas(db)[0]
    valor = "'BORRADO'" if cambio == "action" else "'2020-01-01 00:00:00'"
    db.execute(text(f"UPDATE audit_logs SET {cambio} = {valor} WHERE id = :i"), {"i": f.id})  # noqa: S608 — parametrizado en la prueba
    db.commit()
    db.expire_all()
    assert cadena.verificar(db, "1")["breaks"][0]["reason"] == "hash_mismatch"
