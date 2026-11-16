"""Licencias y hardware — fase 4: integración en toda la plataforma (16-11-2026).

Bajas (manual, SCIM, fin de contrato, programada; regla de licencias y
política de equipo sin devolver), devoluciones hasta el acta, kit de alta,
autoservicio («Mis equipos y licencias»), catálogo (pedir licencia o equipo,
pasos assign/revoke_license), ticket ↔ recurso, recursos técnicos del
proyecto, permisos y la migración.

Las actas de la fase 1 se apagan en estas pruebas (`actas_activadas` → False):
lo que se prueba aquí es la integración, no el PDF ni la firma.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.alm import ALMAsignacion, ALMAsset, ALMLicense, LicenseType
from app.models.alm_integracion import (
    ALMBaja, ALMDevolucion, ALMItemDeCatalogo, ALMKit, ALMKitElemento, ALMPeticion, ALMPropuestaDeKit,
)
from app.models.service_desk import ServiceCategory, ServiceItem, Ticket
from app.models.user import User, UserStatus
from tests.conftest import auth

ORG = "1"


def _tipo_de_proyecto():
    from app.models.project import ProjectType
    return list(ProjectType)[0]


_TIPO = _tipo_de_proyecto()


# ── Preparación ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _sin_actas(monkeypatch):
    from app.services import alm_actas
    monkeypatch.setattr(alm_actas, "actas_activadas", lambda db, org: False)


def _ajustes(monkeypatch, **valores):
    """Fija ajustes de `licencias_integracion` sin tocar la base."""
    from app.services.alm_integracion import _comun as c
    originales = (c.ajuste_int, c.ajuste_str, c.ajuste_bool)

    def leer(original):
        def _leer(db, clave, org):
            return valores[clave] if clave in valores else original(db, clave, org)
        return _leer
    monkeypatch.setattr(c, "ajuste_int", leer(originales[0]))
    monkeypatch.setattr(c, "ajuste_str", leer(originales[1]))
    monkeypatch.setattr(c, "ajuste_bool", leer(originales[2]))


def _licencia(db, nombre="Office E3", asientos=5, coste=1200.0, **kw):
    lic = ALMLicense(id=str(uuid.uuid4()), organization_id=ORG, name=nombre, product_name=nombre,
                     type=LicenseType.subscription, total_seats=asientos, annual_cost=coste, **kw)
    db.add(lic)
    db.flush()
    return lic


def _activo(db, nombre="Portátil 1", tipo="laptop"):
    a = ALMAsset(id=str(uuid.uuid4()), organization_id=ORG, name=nombre, type=tipo, status="available",
                 asset_tag=f"TAG-{uuid.uuid4().hex[:6]}", purchase_price=1000.0)
    db.add(a)
    db.flush()
    return a


def _asignar(db, user_id, *, license_id=None, asset_id=None, **kw):
    from app.services import alm_asignaciones
    return alm_asignaciones.asignar(db, actor=None, holder_type="user", holder_id=user_id,
                                    license_id=license_id, asset_id=asset_id, **kw)


def _usuario(db, uid="dev-test-id"):
    return db.query(User).filter(User.id == uid).first()


# ── Bajas ─────────────────────────────────────────────────────────────────────

def test_baja_manual_libera_licencias_y_abre_devolucion_con_ticket(db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=0, ALM_OFFBOARDING_PENDING_ASSETS="avisar",
             ALM_RETURN_DUE_DAYS=7, ALM_RETURN_GROUP_ID="")
    from app.services.user_service import deactivate_user_record
    lic = _licencia(db)
    activo = _activo(db)
    _asignar(db, "dev-test-id", license_id=lic.id)
    _asignar(db, "dev-test-id", asset_id=activo.id)

    resumen = deactivate_user_record(_usuario(db), db, None)

    assert resumen and resumen["motivo"] == "manual"
    assert resumen["licencias_liberadas"] == 1
    assert db.query(ALMAsignacion).filter(ALMAsignacion.license_id == lic.id,
                                          ALMAsignacion.status == "active").count() == 0
    dev = db.query(ALMDevolucion).filter(ALMDevolucion.asset_id == activo.id).one()
    assert dev.estado == "pendiente" and dev.fecha_limite == date.today() + timedelta(days=7)
    ticket = db.get(Ticket, dev.ticket_id)
    assert (ticket.linked_resource_type, ticket.linked_resource_id) == ("asset", activo.id)
    baja = db.query(ALMBaja).filter(ALMBaja.user_id == "dev-test-id").one()
    assert baja.estado == "pendiente_devolucion"


def test_regla_de_n_dias_aplaza_la_liberacion_hasta_la_pasada_diaria(db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=30, ALM_OFFBOARDING_PENDING_ASSETS="avisar",
             ALM_CONTRACT_END_OFFBOARDING=False)
    from app.services.alm_integracion import bajas
    lic = _licencia(db)
    _asignar(db, "dev-test-id", license_id=lic.id)
    user = _usuario(db)
    user.is_active = False
    baja = bajas.al_dar_de_baja(db, user, "manual")
    db.commit()
    assert baja.licencias_liberadas_en is None
    assert baja.licencias_liberar_en == date.today() + timedelta(days=30)
    assert db.query(ALMAsignacion).filter(ALMAsignacion.license_id == lic.id, ALMAsignacion.status == "active").count() == 1

    baja.licencias_liberar_en = date.today() - timedelta(days=1)
    db.commit()
    r = bajas.pasada_diaria(db, ORG)
    assert r["licencias_liberadas"] == 1
    db.refresh(baja)
    assert baja.estado == "cerrada"  # sin equipos: no queda nada pendiente


def test_politica_bloquear_rechaza_la_desactivacion_manual(client, admin_token, db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_PENDING_ASSETS="bloquear")
    _asignar(db, "dev-test-id", asset_id=_activo(db).id)
    db.commit()
    r = client.delete("/api/v1/users/dev-test-id", headers=auth(admin_token))
    assert r.status_code == 409 and "almint_baja_bloqueada" in r.text
    assert _usuario(db).is_active is True


def test_politica_confirmar_exige_confirmacion_y_queda_anotada(client, admin_token, db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_PENDING_ASSETS="confirmar", ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=0)
    _asignar(db, "dev-test-id", asset_id=_activo(db).id)
    db.commit()
    r = client.delete("/api/v1/users/dev-test-id", headers=auth(admin_token))
    assert r.status_code == 409 and "almint_baja_requiere_confirmacion" in r.text
    r = client.delete("/api/v1/users/dev-test-id?confirmar_equipos=true", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["alm_baja"]["confirmada_con_pendientes"] is True


def test_scim_nunca_se_bloquea_y_abre_la_baja(db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_PENDING_ASSETS="bloquear", ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=0)
    from app.services.scim_service import deactivate_scim_user, update_scim_user
    _asignar(db, "dev-test-id", asset_id=_activo(db).id)
    deactivate_scim_user(_usuario(db), db)
    db.commit()
    baja = db.query(ALMBaja).filter(ALMBaja.user_id == "dev-test-id").one()
    assert baja.motivo == "scim" and baja.estado == "pendiente_devolucion"
    # Un PATCH active=false sobre otra persona también abre su baja.
    update_scim_user(_usuario(db, "hr-test-id"), {"Operations": [{"op": "replace", "path": "active", "value": False}]},
                     "PATCH", db)
    db.commit()
    assert db.query(ALMBaja).filter(ALMBaja.user_id == "hr-test-id", ALMBaja.motivo == "scim").count() == 1


def test_un_fallo_de_alm_no_corta_la_desactivacion_por_scim(db, monkeypatch):
    from app.services.alm_integracion import bajas
    from app.services.scim_service import deactivate_scim_user

    def roto(*a, **k):
        raise RuntimeError("ALM caído")
    monkeypatch.setattr(bajas, "al_dar_de_baja", roto)
    user = _usuario(db)
    deactivate_scim_user(user, db)
    db.commit()
    assert user.is_active is False and user.status == UserStatus.inactive


def test_fin_de_contrato_de_subcontratado_abre_la_baja(db, monkeypatch):
    _ajustes(monkeypatch, ALM_CONTRACT_END_OFFBOARDING=True, ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=0,
             ALM_OFFBOARDING_PENDING_ASSETS="avisar")
    from app.models.enterprise import Subcontractor, SubcontractorWorker
    from app.services.alm_integracion import bajas
    s = Subcontractor(id=str(uuid.uuid4()), organization_id=ORG, code="SUB-001", name="Subcontrata SL")
    db.add(s)
    db.flush()
    db.add(SubcontractorWorker(id=str(uuid.uuid4()), organization_id=ORG, subcontractor_id=s.id, user_id="sub-test-id",
                               name="Sub", available_until=date.today() - timedelta(days=1)))
    db.commit()
    r = bajas.pasada_diaria(db, ORG)
    assert r["fines_de_contrato"] == 1
    assert _usuario(db, "sub-test-id").is_active is False
    assert db.query(ALMBaja).filter(ALMBaja.user_id == "sub-test-id", ALMBaja.motivo == "fin_contrato").count() == 1


def test_baja_programada_se_ejecuta_el_dia_y_se_puede_anular_antes(db):
    from app.services.alm_integracion import bajas
    admin = _usuario(db, "admin-test-id")
    b = bajas.programar_baja(db, "dev-test-id", date.today().isoformat(), admin)
    assert b["estado"] == "programada"
    bajas.pasada_diaria(db, ORG)
    assert _usuario(db).is_active is False
    b2 = bajas.programar_baja(db, "hr-test-id", (date.today() + timedelta(days=10)).isoformat(), admin)
    assert bajas.anular_baja(db, b2["id"], admin)["estado"] == "anulada"


def test_recepcion_cierra_la_devolucion_y_resuelve_el_ticket(db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_LICENSE_RELEASE_DAYS=0, ALM_OFFBOARDING_PENDING_ASSETS="avisar")
    from app.services.alm_integracion import bajas
    activo = _activo(db)
    _asignar(db, "dev-test-id", asset_id=activo.id)
    user = _usuario(db)
    user.is_active = False
    baja = bajas.al_dar_de_baja(db, user, "manual")
    db.commit()
    dev = db.query(ALMDevolucion).filter(ALMDevolucion.baja_id == baja.id).one()
    out = bajas.registrar_recepcion(db, dev.id, _usuario(db, "admin-test-id"), condition="good")
    # Sin actas (apagadas): no hay nada que firmar y la devolución se cierra.
    assert out["estado"] == "cerrada"
    estado = db.get(ALMAsset, activo.id).status
    assert getattr(estado, "value", estado) == "available"
    assert db.get(Ticket, dev.ticket_id).status.value == "resolved"
    db.refresh(baja)
    assert baja.estado == "cerrada"


def test_devolucion_hecha_desde_alm_se_detecta_al_sincronizar(db, monkeypatch):
    _ajustes(monkeypatch, ALM_OFFBOARDING_PENDING_ASSETS="avisar")
    from app.services import alm_asignaciones
    from app.services.alm_integracion import bajas
    activo = _activo(db)
    a = _asignar(db, "dev-test-id", asset_id=activo.id)
    dev = bajas.abrir_devolucion(db, a, origen="autoservicio")
    db.commit()
    alm_asignaciones.devolver(db, a.id, actor=None)
    assert bajas.sincronizar(db, dev) is True
    assert dev.estado == "cerrada"


# ── Kit de alta ───────────────────────────────────────────────────────────────

def _kit(db, lic, criterio="puesto", valor="Consultor", tipo_equipo="laptop"):
    k = ALMKit(id=str(uuid.uuid4()), organization_id=ORG, nombre="Consultoría", criterio=criterio, valor=valor)
    db.add(k)
    db.flush()
    db.add(ALMKitElemento(organization_id=ORG, kit_id=k.id, tipo="licencia", license_id=lic.id, cantidad=1))
    db.add(ALMKitElemento(organization_id=ORG, kit_id=k.id, tipo="equipo", asset_type=tipo_equipo, cantidad=1))
    db.commit()
    return k


def test_alta_propone_kit_y_un_clic_reserva_o_pide_compra(client, admin_token, db, monkeypatch):
    _ajustes(monkeypatch, ALM_KIT_ON_HIRE=True, ALM_PURCHASE_GROUP_ID="")
    lic = _licencia(db, asientos=1)
    _kit(db, lic)
    r = client.post("/api/v1/users", headers=auth(admin_token), json={
        "username": "nuevo", "email": "nuevo@contecflow.com", "full_name": "Nuevo Consultor",
        "job_title": "Consultor", "role": "employee", "password": "Contecflow!2026-ok", "manager_id": "pm-test-id"})
    assert r.status_code in (200, 201), r.text
    nuevo_id = r.json()["data"]["id"] if "data" in r.json() else r.json()["id"]
    p = db.query(ALMPropuestaDeKit).filter(ALMPropuestaDeKit.user_id == nuevo_id).one()
    assert p.responsable_id == "pm-test-id"

    from app.services.alm_integracion import kits
    # Sin portátiles en el almacén: la licencia se asigna y el equipo se pide.
    out = kits.confirmar(db, p.id, _usuario(db, "pm-test-id"))
    resultados = {e["tipo"]: e["resultado"] for e in out["resultado"]}
    assert resultados == {"licencia": "asignada", "equipo": "compra"}
    compra = [e for e in out["resultado"] if e["tipo"] == "equipo"][0]
    assert db.get(Ticket, compra["ticket_id"]) is not None


def test_kit_sin_permiso_y_sin_asientos(db, monkeypatch):
    _ajustes(monkeypatch, ALM_KIT_ON_HIRE=True, ALM_KIT_FALLBACK_ROLES="admin")
    from app.core.errores import ErrorDeDominio
    from app.services.alm_integracion import kits
    lic = _licencia(db, asientos=0)
    _activo(db)
    _kit(db, lic, criterio="todos", valor=None)
    p = kits.proponer(db, _usuario(db, "hr-test-id"), forzar=True)
    db.commit()
    with pytest.raises(ErrorDeDominio):
        kits.confirmar(db, p.id, _usuario(db))           # un empleado cualquiera no decide
    out = kits.confirmar(db, p.id, _usuario(db, "admin-test-id"))
    r = {e["tipo"]: e["resultado"] for e in out["resultado"]}
    assert r == {"licencia": "compra", "equipo": "asignado"}


# ── Autoservicio ──────────────────────────────────────────────────────────────

def test_mis_equipos_solo_lo_propio_y_acciones(client, dev_token, sub_token, db, monkeypatch):
    _ajustes(monkeypatch, ALM_BREAKDOWN_GROUP_ID="", ALM_RETURN_GROUP_ID="", ALM_RETURN_DUE_DAYS=0)
    lic = _licencia(db)
    mio = _asignar(db, "dev-test-id", asset_id=_activo(db, "Mío").id, mode="loan",
                   valid_to=date.today() + timedelta(days=3))
    _asignar(db, "dev-test-id", license_id=lic.id)
    ajeno = _asignar(db, "sub-test-id", asset_id=_activo(db, "Ajeno").id)
    db.commit()

    d = client.get("/api/v1/alm/integracion/mio", headers=auth(dev_token)).json()["data"]
    assert [e["name"] for e in d["equipos"]] == ["Mío"] and d["equipos"][0]["mode"] == "loan"
    assert len(d["licencias"]) == 1
    s = client.get("/api/v1/alm/integracion/mio", headers=auth(sub_token)).json()["data"]
    assert [e["name"] for e in s["equipos"]] == ["Ajeno"]

    r = client.post(f"/api/v1/alm/integracion/mio/asignaciones/{ajeno.id}/averia", headers=auth(dev_token),
                    json={"descripcion": "No arranca"})
    assert r.status_code == 404
    r = client.post(f"/api/v1/alm/integracion/mio/asignaciones/{mio.id}/averia", headers=auth(dev_token),
                    json={"descripcion": "No arranca", "urgencia": "high"})
    assert r.status_code == 200, r.text
    t = db.get(Ticket, r.json()["data"]["id"])
    assert t.ticket_type.value == "incident" and t.linked_resource_id == mio.asset_id
    r = client.post(f"/api/v1/alm/integracion/mio/asignaciones/{mio.id}/devolver", headers=auth(dev_token), json={})
    assert r.status_code == 200 and r.json()["data"]["origen"] == "autoservicio"
    tickets = client.get(f"/api/v1/alm/integracion/recursos/asset/{mio.asset_id}/tickets",
                         headers=auth(dev_token))
    assert tickets.status_code == 403  # el listado por recurso es de gestión


# ── Catálogo ──────────────────────────────────────────────────────────────────

def _item_de_alm(db, tipo="licencia", **kw):
    cat = ServiceCategory(id=str(uuid.uuid4()), organization_id=ORG, name="Puesto de trabajo")
    db.add(cat)
    db.flush()
    item = ServiceItem(id=str(uuid.uuid4()), organization_id=ORG, category_id=cat.id,
                       name="Pedir licencia" if tipo == "licencia" else "Pedir equipo", requires_approval=False)
    db.add(item)
    db.flush()
    db.add(ALMItemDeCatalogo(organization_id=ORG, service_item_id=item.id, tipo=tipo, **kw))
    db.commit()
    return item


def test_pedir_licencia_sin_aprobacion_se_da_de_alta_y_enlaza(client, dev_token, db):
    lic = _licencia(db, asientos=2)
    _item_de_alm(db)
    r = client.post("/api/v1/alm/integracion/mio/peticiones", headers=auth(dev_token),
                    json={"tipo": "licencia", "license_id": lic.id, "motivo": "Proyecto X"})
    assert r.status_code == 200, r.text
    p = db.query(ALMPeticion).one()
    assert p.estado == "cumplida" and p.beneficiario_id == "dev-test-id"
    t = db.get(Ticket, p.ticket_id)
    assert (t.linked_resource_type, t.linked_resource_id) == ("license", lic.id)
    assert t.status.value == "resolved"


def test_pedir_equipo_sin_existencias_pide_compra_y_se_reintenta(client, dev_token, db, monkeypatch):
    _ajustes(monkeypatch, ALM_PURCHASE_GROUP_ID="")
    from app.services.alm_integracion import catalogo
    _item_de_alm(db, tipo="equipo")
    r = client.post("/api/v1/alm/integracion/mio/peticiones", headers=auth(dev_token),
                    json={"tipo": "equipo", "asset_type": "laptop"})
    assert r.status_code == 200, r.text
    p = db.query(ALMPeticion).one()
    assert p.estado == "en_compra" and p.compra_ticket_id
    activo = _activo(db)
    db.commit()
    out = catalogo.reintentar(db, p.id, _usuario(db, "admin-test-id"))
    assert out["estado"] == "cumplida" and out["asset_id"] == activo.id


def test_sin_item_de_catalogo_no_se_puede_pedir(client, dev_token, db):
    lic = _licencia(db)
    db.commit()
    r = client.post("/api/v1/alm/integracion/mio/peticiones", headers=auth(dev_token),
                    json={"tipo": "licencia", "license_id": lic.id})
    assert r.status_code == 409 and "almint_catalogo_sin_item" in r.text


def test_pasos_assign_y_revoke_license_actualizan_alm(db):
    from app.services.alm_integracion.catalogo import paso_de_catalogo
    lic = _licencia(db)
    item = _item_de_alm(db)
    t = Ticket(id=str(uuid.uuid4()), organization_id=ORG, number="SR-9001", ticket_type="service_request",
               title="Licencia", description="", requester_user_id="dev-test-id", service_item_id=item.id)
    db.add(t)
    db.flush()
    admin = _usuario(db, "admin-test-id")
    r = paso_de_catalogo(db, {"type": "assign_license", "license_id": lic.id}, t, admin)
    assert r["ok"] and r["alm"]["resultado"] == "asignada"
    assert db.query(ALMAsignacion).filter(ALMAsignacion.license_id == lic.id,
                                          ALMAsignacion.holder_user_id == "dev-test-id",
                                          ALMAsignacion.status == "active").count() == 1
    r = paso_de_catalogo(db, {"type": "revoke_license", "license_id": lic.id}, t, admin)
    assert r["ok"] and r["alm"]["n"] == 1
    assert db.query(ALMAsignacion).filter(ALMAsignacion.license_id == lic.id,
                                          ALMAsignacion.status == "active").count() == 0


def test_paso_con_url_tambien_llama_al_sistema_externo(db, monkeypatch):
    from app.services import bookings_service
    from app.services.alm_integracion.catalogo import paso_de_catalogo
    llamadas = []
    monkeypatch.setattr(bookings_service, "_execute_provision_action",
                        lambda cfg, ctx: llamadas.append(cfg["operation"]) or {"ok": True, "status_code": 200,
                                                                                 "operation": cfg["operation"]})
    lic = _licencia(db)
    t = Ticket(id=str(uuid.uuid4()), organization_id=ORG, number="SR-9002", ticket_type="service_request",
               title="Licencia", description="", requester_user_id="dev-test-id")
    db.add(t)
    db.flush()
    r = paso_de_catalogo(db, {"type": "assign_license", "license_id": lic.id, "url": "https://idm.example.com/x"},
                         t, _usuario(db, "admin-test-id"))
    assert llamadas == ["assign_license"] and r["ok"] and r["external"]["ok"]


# ── Ficha de proyecto ─────────────────────────────────────────────────────────

def test_recursos_del_proyecto_permisos_y_bolsa(client, pm_token, sub_token, db):
    from app.models.project import Project
    from app.services import alm_asignaciones
    p = Project(id=str(uuid.uuid4()), organization_id=ORG, name="Proyecto ALM", code=f"P{uuid.uuid4().hex[:5]}", project_type=_TIPO,
                pm_id="pm-test-id")
    db.add(p)
    db.flush()
    lic = _licencia(db, asientos=10)
    alm_asignaciones.asignar(db, actor=None, holder_type="project", holder_id=p.id, license_id=lic.id, quantity=3)
    db.commit()
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["puedo_gestionar"] is True and d["bolsas"][0]["quantity"] == 3
    assert d["coste"] is not None
    # El subcontratado no ve un proyecto que no es suyo: 404.
    r = client.get(f"/api/v1/alm/integracion/proyectos/{p.id}/recursos", headers=auth(sub_token))
    assert r.status_code == 404


def test_solo_el_pm_o_admin_asigna_en_el_proyecto(client, dev_token, pm_token, db):
    from app.models.project import Project, ProjectMember
    p = Project(id=str(uuid.uuid4()), organization_id=ORG, name="Proyecto B", code=f"P{uuid.uuid4().hex[:5]}", project_type=_TIPO,
                pm_id="pm-test-id")
    db.add(p)
    db.flush()
    db.add(ProjectMember(organization_id=ORG, project_id=p.id, user_id="dev-test-id", is_active=True))
    lic = _licencia(db, asientos=10)
    db.commit()
    datos = {"holder_type": "user", "holder_id": "dev-test-id", "license_id": lic.id}
    r = client.post(f"/api/v1/alm/integracion/proyectos/{p.id}/asignar", headers=auth(dev_token), json=datos)
    assert r.status_code == 403
    r = client.post(f"/api/v1/alm/integracion/proyectos/{p.id}/asignar", headers=auth(pm_token), json=datos)
    assert r.status_code == 200, r.text
    aid = r.json()["data"]["id"]
    r = client.post(f"/api/v1/alm/integracion/proyectos/{p.id}/asignaciones/{aid}/liberar", headers=auth(pm_token), json={})
    assert r.status_code == 200 and r.json()["data"]["status"] == "ended"


# ── Permisos de gestión ───────────────────────────────────────────────────────

def test_bajas_y_kits_no_son_para_empleados(client, dev_token, hr_token):
    assert client.get("/api/v1/alm/integracion/bajas", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/alm/integracion/bajas", headers=auth(hr_token)).status_code == 200
    assert client.post("/api/v1/alm/integracion/kits", headers=auth(dev_token), json={}).status_code == 403


# ── Migración ─────────────────────────────────────────────────────────────────

def test_migracion_172_encadenada_y_con_downgrade():
    import importlib.util
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "172_alm_altas_bajas_y_autoservicio.py"
    spec = importlib.util.spec_from_file_location("m172", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "172_alm_altas_bajas_y_autoservicio" and m.down_revision == "171_alm_uso_real"
    assert callable(m.upgrade) and callable(m.downgrade)
    from app.db.base import Base
    import app.models  # noqa: F401  (registra los modelos)
    assert set(m.TABLAS) <= set(Base.metadata.tables)
