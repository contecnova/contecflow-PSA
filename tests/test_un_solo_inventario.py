"""Un solo inventario de activos: ALM, con CI, historial y renovacion.

Auditoria 2026-11: habia dos. ALM tenia pantalla; los activos del Service Desk
(`sd_assets`) eran los unicos con CI, historial y fechas de ciclo de vida, y no
se veian en ninguna parte. La migracion 111 los fundio en ALM.
"""
from __future__ import annotations

from datetime import timedelta

from app.core import timeutil
from tests.conftest import auth

BASE = "/api/v1/alm/assets"


def _activo(client, token, **datos):
    r = client.post(BASE, headers=auth(token), json={"name": "Portatil", "type": "laptop", **datos})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_cada_cambio_queda_en_el_historial(client, admin_token):
    h = auth(admin_token)
    aid = _activo(client, admin_token, location="Madrid")
    client.patch(f"{BASE}/{aid}", headers=h, json={"location": "Barcelona", "eol_date": "2027-01-31"})
    client.post(f"{BASE}/{aid}/assign", headers=h, json={"user_id": "admin-test-id"})

    filas = client.get(f"{BASE}/{aid}/history", headers=h).json()["items"]
    # Una lista y no un dict: el estado tiene dos filas (alta y asignacion) que
    # pueden llevar la misma marca de tiempo, y su orden no esta garantizado.
    cambios = {(f["field"], f["old_value"], f["new_value"]) for f in filas}
    assert ("location", "Madrid", "Barcelona") in cambios
    assert ("eol_date", None, "2027-01-31") in cambios
    assert ("assigned_to_id", None, "admin-test-id") in cambios
    assert ("status", "available", "in_use") in cambios

    detalle = client.get(f"{BASE}/{aid}", headers=h).json()["data"]
    assert detalle["eol_date"] == "2027-01-31"


def test_los_vencimientos_salen_por_la_fecha_mas_cercana(client, admin_token):
    hoy = timeutil.today()
    _activo(client, admin_token, name="lejos", warranty_expiry=(hoy + timedelta(days=200)).isoformat())
    _activo(client, admin_token, name="cerca", lease_expiry=(hoy + timedelta(days=3)).isoformat(),
            eol_date=(hoy + timedelta(days=20)).isoformat())
    _activo(client, admin_token, name="retirado", status="retired", warranty_expiry=hoy.isoformat())

    filas = client.get(f"{BASE}/expiring", headers=auth(admin_token), params={"days": 30}).json()["items"]
    assert [(f["name"], f["expiry_type"]) for f in filas] == [("cerca", "lease_expiry"), ("cerca", "eol_date")]


def test_el_escaneo_abre_un_solo_ticket_por_activo_y_en_su_organizacion(db, client, admin_token):
    from app.models.alm import ALMAsset
    from app.models.service_desk import Ticket, TicketStatus
    from app.services.alm_ciclo_de_vida import escanear_vencimientos

    hoy = timeutil.today()
    aid = _activo(client, admin_token, warranty_expiry=(hoy + timedelta(days=2)).isoformat())
    _activo(client, admin_token, name="fuera", warranty_expiry=(hoy + timedelta(days=40)).isoformat())
    # Otra organizacion que la que la sesion de pruebas pone por defecto: asi
    # se ve si el ticket hereda la del activo o la de la sesion (el worker no
    # tiene ninguna).
    db.get(ALMAsset, aid).organization_id = "org-renovacion"
    db.commit()

    assert escanear_vencimientos(db) == {"vencen": 1, "tickets_creados": 1, "ya_abiertos": 0}
    db.commit()
    assert escanear_vencimientos(db)["tickets_creados"] == 0, "abre otro cada dia"

    activo = db.get(ALMAsset, aid)
    ticket = db.get(Ticket, activo.refresh_ticket_id)
    assert ticket.organization_id == "org-renovacion"

    # Cerrado el ticket, el siguiente vencimiento abre uno nuevo.
    ticket.status = TicketStatus.closed
    db.commit()
    assert escanear_vencimientos(db)["tickets_creados"] == 1


def test_con_el_ajuste_a_cero_el_escaneo_no_abre_nada(db, client, admin_token):
    from app.models.alm import ALMAsset
    from app.services import settings_service as ss
    from app.services.alm_ciclo_de_vida import escanear_vencimientos

    aid = _activo(client, admin_token, warranty_expiry=timeutil.today().isoformat())
    ss.set_runtime_value(db, "service_desk", "SD_ASSET_REFRESH_DAYS", 0, db.get(ALMAsset, aid).organization_id)
    db.commit()
    assert escanear_vencimientos(db)["tickets_creados"] == 0


def test_el_boton_de_renovacion_no_duplica(client, admin_token):
    h = auth(admin_token)
    aid = _activo(client, admin_token)
    a = client.post(f"{BASE}/{aid}/refresh-ticket", headers=h).json()["data"]
    b = client.post(f"{BASE}/{aid}/refresh-ticket", headers=h).json()["data"]
    assert a["created"] and not b["created"] and a["ticket_id"] == b["ticket_id"]
