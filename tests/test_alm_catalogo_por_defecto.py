"""Catálogo de equipos y licencias por defecto (19-11-2026, `alm_integracion.catalogo.asegurar_items`)."""
from app.models.alm_integracion import ALMItemDeCatalogo
from app.models.service_desk import ServiceItem
from app.services.alm_integracion import catalogo
from tests.conftest import auth


def _vaciar(db):
    db.query(ALMItemDeCatalogo).filter(ALMItemDeCatalogo.organization_id == "1").delete()
    db.commit()


def test_se_crea_una_vez_interno_y_auditado(db):
    _vaciar(db)
    assert catalogo.asegurar_items(db, "1") is True
    assert catalogo.asegurar_items(db, "1") is False          # idempotente
    filas = db.query(ALMItemDeCatalogo).filter(ALMItemDeCatalogo.organization_id == "1").all()
    assert sorted(f.tipo for f in filas) == ["equipo", "licencia"]
    for f in filas:
        item = db.get(ServiceItem, f.service_item_id)
        assert item.is_visible_to_clients is False and item.requires_approval and item.approval_mode == "engine"
    from app.models.enterprise import AuditLog
    assert db.query(AuditLog).filter(AuditLog.resource == "alm_item_de_catalogo").count() >= 1


def test_mis_equipos_siempre_permite_pedir(client, dev_token, db):
    _vaciar(db)
    r = client.get("/api/v1/alm/integracion/mio/opciones", headers=auth(dev_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["puede_pedir_equipo"] and d["puede_pedir_licencia"]
