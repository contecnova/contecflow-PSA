"""19-11-2026: la configuración de Voz, Autorresolución e informes de Microsoft 365
pasa a Configuración (`/settings/sd-voz`, `/settings/sd-autorresolucion`,
`/settings/m365-informes`). Sus guardados no dejaban rastro: ahora quedan en la
auditoría con antes y después, y el secreto de Graph nunca aparece en ella.
"""
from tests.conftest import auth


def _ultima(db, recurso):
    from app.models.enterprise import AuditLog
    return (db.query(AuditLog).filter(AuditLog.resource == recurso)
            .order_by(AuditLog.created_at.desc()).first())


def test_guardar_config_de_voz_queda_auditado(client, admin_token, db):
    r = client.put("/api/v1/sd/voice/config", json={"greeting": "Hola auditada"}, headers=auth(admin_token))
    assert r.status_code == 200
    fila = _ultima(db, "sd_voice_config")
    assert fila is not None and fila.action == "UPDATE"
    assert "Hola auditada" in str(fila.new_values)


def test_guardar_config_de_autorresolucion_queda_auditado(client, admin_token, db):
    r = client.patch("/api/v1/sd/auto-resolution/config", json={"default_job_limit": 31}, headers=auth(admin_token))
    assert r.status_code == 200
    fila = _ultima(db, "sd_auto_resolution_config")
    assert fila is not None and fila.action == "UPDATE"
    assert "31" in str(fila.new_values)


def test_guardar_config_o365_queda_auditado_sin_el_secreto(client, admin_token, db):
    r = client.put("/api/v1/bi/o365/config", headers=auth(admin_token),
                   json={"tenant_id": "t-aud", "client_id": "c-aud", "client_secret": "SECRETO-NO-VISIBLE", "enabled": True})
    assert r.status_code == 200
    fila = _ultima(db, "bi_o365_config")
    assert fila is not None and fila.action == "UPDATE"
    todo = f"{fila.old_values} {fila.new_values} {getattr(fila, 'metadata_', '')} {getattr(fila, 'extra', '')}"
    assert "SECRETO-NO-VISIBLE" not in todo
    assert "t-aud" in str(fila.new_values)


def test_pm_no_guarda_ninguna_de_las_tres(client, pm_token):
    assert client.put("/api/v1/sd/voice/config", json={"greeting": "x"}, headers=auth(pm_token)).status_code == 403
    assert client.patch("/api/v1/sd/auto-resolution/config", json={"default_job_limit": 3}, headers=auth(pm_token)).status_code == 403
    assert client.put("/api/v1/bi/o365/config", json={"tenant_id": "x"}, headers=auth(pm_token)).status_code == 403
