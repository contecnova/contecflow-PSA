"""Licencias y hardware, fases 1 y 3 (16-11-2026).

Fase 1: asignación universal (persona, proyecto, departamento, cliente,
equipo) con historial inmutable; métricas de licencia y bolsas; ciclo de vida
del hardware con préstamo, devolución y baja; clave cifrada; panel sin doble
conteo; métricas filtradas.

Fase 3: coste por titular y día e imputación al proyecto; renovaciones con
preaviso, decisión y renovación automática; conciliación contrato ↔ factura ↔
gasto sin contar dos veces en la rentabilidad.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from tests.conftest import auth


# ── Utilidades ────────────────────────────────────────────────────────────────

def _u(db, nombre="admin"):
    from app.models.user import User
    return db.query(User).filter(User.username == nombre).first()


def _sufijo():
    return uuid.uuid4().hex[:6]


def _licencia(db, **kw):
    from app.models.alm import ALMLicense
    datos = dict(name=f"Lic-{_sufijo()}", type="subscription", status="active", organization_id="1",
                 metric="named_user")
    datos.update(kw)
    lic = ALMLicense(**datos)
    db.add(lic)
    db.flush()
    return lic


def _activo(db, **kw):
    from app.models.alm import ALMAsset
    datos = dict(name=f"Portátil-{_sufijo()}", type="laptop", status="available", organization_id="1",
                 asset_tag=f"T-{_sufijo()}", serial_number=f"S-{_sufijo()}")
    datos.update(kw)
    a = ALMAsset(**datos)
    db.add(a)
    db.flush()
    return a


def _proyecto(db):
    from app.models.project import Project
    from tests.test_listados_paginados_y_sin_n_mas_1_2026_11 import _nuevo
    return _nuevo(db, Project, name=f"P-{_sufijo()}", code=f"P{_sufijo()}", organization_id="1")


def _sin_actas(monkeypatch):
    """Sin acta: estas pruebas no miran el PDF ni el almacén de ficheros."""
    from app.services import alm_actas
    monkeypatch.setattr(alm_actas, "actas_activadas", lambda db, org: False)


# ── Fase 1: asignación universal ──────────────────────────────────────────────

def test_asignar_licencia_a_persona_ocupa_asiento_y_deja_historial(db, monkeypatch):
    from app.core.errores import ErrorDeDominio
    from app.models.alm import ALMEvento
    from app.services import alm_asignaciones as asig
    admin, dev = _u(db), _u(db, "dev_test")
    lic = _licencia(db, total_seats=1)
    a = asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=dev.id, reason="Alta en el equipo")
    assert a.status == "active" and a.holder_user_id == dev.id and a.resource_type == "license"
    assert asig.asientos_usados(db, lic) == 1
    # sin asientos libres
    with pytest.raises(ErrorDeDominio) as e:
        asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=admin.id)
    assert e.value.detail == "alm_sin_asientos"
    # la misma persona dos veces
    lic.total_seats = 5
    with pytest.raises(ErrorDeDominio) as e:
        asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=dev.id)
    assert e.value.detail == "alm_ya_asignada"
    # revocar exige motivo; con motivo cierra y libera el asiento
    with pytest.raises(ErrorDeDominio):
        asig.liberar(db, a.id, actor=admin, tipo="revoked")
    asig.liberar(db, a.id, actor=admin, tipo="revoked", motivo="Cambio de puesto")
    assert a.status == "ended" and a.end_kind == "revoked" and a.ended_on == dt.date.today()
    assert asig.asientos_usados(db, lic) == 0
    eventos = [e.event for e in db.query(ALMEvento).filter(ALMEvento.assignment_id == a.id)]
    assert {"assigned", "revoked"} <= set(eventos)
    # quién tuvo qué: el historial por titular lo encuentra
    pagina = asig.historial(db, holder_type="user", holder_id=dev.id)
    assert any(f["event"] == "revoked" and f["reason"] == "Cambio de puesto" for f in pagina.items)


def test_el_historial_es_inmutable(db):
    from app.models.alm import ALMEvento
    ev = ALMEvento(resource_type="license", event="assigned", organization_id="1")
    db.add(ev)
    db.flush()
    ev.reason = "cambio"
    with pytest.raises(ValueError):
        db.flush()
    db.rollback()


def test_bolsa_de_proyecto_se_reparte_sin_pasarse(db):
    from app.core.errores import ErrorDeDominio
    from app.services import alm_asignaciones as asig
    admin, dev = _u(db), _u(db, "dev_test")
    proyecto = _proyecto(db)
    lic = _licencia(db, total_seats=10)
    bolsa = asig.asignar(db, actor=admin, license_id=lic.id, holder_type="project", holder_id=proyecto.id, quantity=2)
    assert bolsa.mode == "pool" and asig.asientos_usados(db, lic) == 2
    hija = asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=dev.id, parent_id=bolsa.id)
    assert hija.parent_id == bolsa.id
    assert asig.asientos_usados(db, lic) == 2           # la hija consume de la bolsa, no de la licencia
    asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=admin.id, parent_id=bolsa.id)
    pm = _u(db, "pm_test")
    with pytest.raises(ErrorDeDominio) as e:
        asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=pm.id, parent_id=bolsa.id)
    assert e.value.detail == "alm_bolsa_sin_asientos"
    # cerrar la bolsa cierra sus hijas
    asig.liberar(db, bolsa.id, actor=admin)
    db.refresh(hija)
    assert hija.status == "ended"


def test_metricas_de_licencia(db):
    from app.core.errores import ErrorDeDominio
    from app.services import alm_asignaciones as asig
    admin = _u(db)
    por_equipo = _licencia(db, metric="device", total_seats=1)
    with pytest.raises(ErrorDeDominio) as e:
        asig.asignar(db, actor=admin, license_id=por_equipo.id, holder_type="user", holder_id=admin.id)
    assert e.value.detail == "alm_metrica_dispositivo_sin_personas"
    equipo = _activo(db)
    asig.asignar(db, actor=admin, license_id=por_equipo.id, holder_type="asset", holder_id=equipo.id)
    # concurrente: las asignaciones no consumen asientos; manda el pico
    concurrente = _licencia(db, metric="concurrent", total_seats=1, is_compliance_req=True)
    for u in (admin, _u(db, "dev_test"), _u(db, "pm_test")):
        asig.asignar(db, actor=admin, license_id=concurrente.id, holder_type="user", holder_id=u.id)
    asig.registrar_pico(db, concurrente.id, 3, fuente="manual")
    db.refresh(concurrente)
    assert concurrente.concurrent_peak == 3
    from app.services.alm_service import get_compliance_report
    problemas = {(i["license_id"], i["issue"]) for i in get_compliance_report(db)["issues"]}
    assert (concurrente.id, "OVER_PEAK") in problemas


def test_asignacion_con_flujo_queda_pendiente_y_la_bandeja_la_activa(db, monkeypatch):
    from app.services import alm_asignaciones as asig
    from app.services.approval_engine import fuentes
    admin, dev = _u(db), _u(db, "dev_test")
    lic = _licencia(db, total_seats=3)
    monkeypatch.setattr(asig, "_hay_flujo", lambda *a, **k: True)
    abiertas = []
    monkeypatch.setattr(fuentes, "abrir", lambda db, tipo, eid, *a, **k: abiertas.append((tipo, eid)))
    monkeypatch.setattr(fuentes, "estado", lambda db, tipo, eid: "pending")
    a = asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=dev.id)
    assert a.status == "pending" and abiertas == [("alm_assignment", a.id)]
    assert asig.asientos_usados(db, lic) == 1          # la pendiente reserva su asiento
    asig.aplicar_decision(db, a.id, True, admin, None)
    db.refresh(a)
    assert a.status == "active" and a.approved_by == admin.id


# ── Fase 1: hardware ──────────────────────────────────────────────────────────

def test_ciclo_de_vida_prestamo_devolucion_y_baja(db, monkeypatch):
    from app.core.errores import ErrorDeDominio
    from app.services import alm_asignaciones as asig
    from app.services.alm_ciclo_de_vida import acciones_posibles, transicion
    _sin_actas(monkeypatch)
    admin, dev = _u(db), _u(db, "dev_test")
    a = _activo(db, status="ordered")
    assert "receive" in acciones_posibles(a)
    transicion(db, a.id, "receive", admin)
    assert a.status.value == "available"
    with pytest.raises(ErrorDeDominio) as e:
        asig.prestar(db, actor=admin, asset_id=a.id, holder_type="user", holder_id=dev.id, valid_to=None)
    assert e.value.detail == "alm_prestamo_sin_devolucion"
    p = asig.prestar(db, actor=admin, asset_id=a.id, holder_type="user", holder_id=dev.id,
                     valid_to=dt.date.today() + dt.timedelta(days=7))
    db.refresh(a)
    assert a.status.value == "on_loan" and a.assigned_to_id == dev.id
    with pytest.raises(ErrorDeDominio):     # no se da de baja con titular
        transicion(db, a.id, "retired", admin, datos={"reason": "obsolete"})
    asig.devolver(db, p.id, actor=admin, condition="fair")
    db.refresh(a)
    assert a.status.value == "available" and a.assigned_to_id is None and a.condition.value == "fair"
    transicion(db, a.id, "retired", admin, datos={"reason": "obsolete"})
    transicion(db, a.id, "disposed", admin, datos={"method": "recycle", "value": "20"})
    db.refresh(a)
    assert a.status.value == "disposed" and a.disposal_method == "recycle" and a.disposal_value == 20.0


def test_el_estado_del_activo_no_se_cambia_editando(client, db, admin_token, monkeypatch):
    _sin_actas(monkeypatch)
    a = _activo(db)
    db.commit()
    r = client.patch(f"/api/v1/alm/assets/{a.id}", json={"status": "in_use"}, headers=auth(admin_token))
    assert r.status_code == 409 and "alm_estado_por_accion" in r.text


def test_alta_de_activo_con_persona_crea_su_asignacion(client, db, admin_token, monkeypatch):
    _sin_actas(monkeypatch)
    dev = _u(db, "dev_test")
    r = client.post("/api/v1/alm/assets", json={"name": f"Equipo-{_sufijo()}", "type": "laptop",
                                                "assigned_to_id": dev.id}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "in_use" and d["holder_type"] == "user" and d["holder_id"] == dev.id
    assert "return" in d["actions"]


def test_actas_entrega_y_firma_en_la_aplicacion(db, monkeypatch):
    """El acta se emite al asignar a una persona; solo esa persona la firma."""
    from app.core.errores import ErrorDeDominio
    from app.models.alm import ALMActa
    from app.services import alm_actas, alm_asignaciones as asig
    monkeypatch.setattr(alm_actas, "guardar_documento", lambda *a, **k: None)   # sin almacén de ficheros
    admin, dev = _u(db), _u(db, "dev_test")
    activo = _activo(db)
    a = asig.asignar(db, actor=admin, asset_id=activo.id, holder_type="user", holder_id=dev.id,
                     checklist=[{"item": "charger", "ok": True}])
    acta = db.query(ALMActa).filter(ALMActa.assignment_id == a.id).first()
    assert acta is not None and acta.kind == "delivery" and acta.signer_user_id == dev.id
    with pytest.raises(ErrorDeDominio):
        alm_actas.firmar(db, acta.id, admin)
    datos = alm_actas.serializar(db, acta, con_url=False)
    assert datos["checklist"][0] == {"item": "charger", "ok": True, "note": ""}


# ── Fase 1: clave cifrada, panel y métricas ───────────────────────────────────

def test_la_clave_se_guarda_cifrada_y_solo_sale_por_su_endpoint(client, db, admin_token):
    r = client.post("/api/v1/alm/licenses", json={"name": f"Lic-{_sufijo()}", "type": "subscription",
                                                  "license_key": "AAAA-BBBB-CCCC-1234"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["has_key"] and d["license_key_hint"] == "1234" and "license_key" not in d
    from app.models.alm import ALMLicense
    lic = db.query(ALMLicense).filter(ALMLicense.id == d["id"]).first()
    assert lic._license_key.startswith(("v2:", "kmsv1:"))
    assert client.get(f"/api/v1/alm/licenses/{lic.id}/key", headers=auth(admin_token)).json()["data"]["license_key"] \
        == "AAAA-BBBB-CCCC-1234"
    # editar sin clave no la borra
    client.patch(f"/api/v1/alm/licenses/{lic.id}", json={"license_key": "", "notes": "x"}, headers=auth(admin_token))
    db.refresh(lic)
    assert lic.license_key == "AAAA-BBBB-CCCC-1234"


def test_panel_sin_doble_conteo_ni_canceladas(db):
    from app.models.alm import ALMContract
    from app.services.alm_service import coste_anual_vigente
    antes = coste_anual_vigente(db)
    c = ALMContract(title=f"C-{_sufijo()}", type="subscription", status="active", annual_value=1000, organization_id="1")
    db.add(c)
    db.flush()
    _licencia(db, contract_id=c.id, annual_cost=400)              # dentro del contrato
    _licencia(db, annual_cost=300)                                  # suelta
    _licencia(db, annual_cost=999, status="cancelled")               # no cuenta
    _licencia(db, annual_cost=999, is_active=False)                 # borrada: no cuenta
    lic, con = coste_anual_vigente(db)
    assert round(lic - antes[0], 2) == 300 and round(con - antes[1], 2) == 1000


def test_metricas_de_activos_por_tipo_usan_el_codigo_y_filtran_borrados(db):
    from app.services.metrics.alm import metric_assets_by_type
    _activo(db, type="mobile")
    _activo(db, type="mobile", is_active=False)
    filas, _ = metric_assets_by_type(db, dt.date.today(), dt.date.today(), 10)
    movil = next(f for f in filas if f["code"] == "mobile")
    from app.models.alm import ALMAsset
    esperados = db.query(ALMAsset).filter(ALMAsset.type == "mobile", ALMAsset.is_active.is_(True),
                                          ALMAsset.status.notin_(("retired", "disposed"))).count()
    assert movil["value"] == esperados


# ── Fase 3: costes ────────────────────────────────────────────────────────────

def test_coste_por_titular_y_dia_con_ocioso(db):
    from app.services import alm_asignaciones as asig
    from app.services.alm_costes import lineas
    admin = _u(db)
    hoy = dt.date.today()
    inicio = hoy - dt.timedelta(days=9)
    lic = _licencia(db, total_seats=2, annual_cost=730.0, purchase_date=inicio - dt.timedelta(days=100))
    asig.asignar(db, actor=admin, license_id=lic.id, holder_type="user", holder_id=admin.id, valid_from=inicio)
    filas = [li for li in lineas(db, inicio, hoy) if li.resource_id == lic.id]
    persona = next(li for li in filas if li.kind == "license")
    ocioso = next(li for li in filas if li.kind == "idle")
    # 730/365 = 2 al día; medio para la persona (1 de 2 asientos), 10 días
    assert round(persona.amount, 2) == 10.0 and persona.days == 10
    assert round(ocioso.amount, 2) == 10.0


def test_coste_de_alm_entra_en_la_rentabilidad_del_proyecto(db):
    from app.services import alm_asignaciones as asig
    from app.services.costes_de_proyecto import costes_externos
    admin = _u(db)
    proyecto = _proyecto(db)
    hoy = dt.date.today()
    lic = _licencia(db, total_seats=1, annual_cost=365.0, purchase_date=hoy - dt.timedelta(days=50))
    asig.asignar(db, actor=admin, license_id=lic.id, holder_type="project", holder_id=proyecto.id,
                 valid_from=hoy - dt.timedelta(days=4))
    externos = costes_externos(db, proyecto.id, "EUR", hoy - dt.timedelta(days=4), hoy)
    assert round(externos["alm"], 2) == 5.0


def test_amortizacion_de_un_equipo_al_titular(db, monkeypatch):
    from app.services import alm_asignaciones as asig
    from app.services.alm_costes import lineas
    _sin_actas(monkeypatch)
    admin = _u(db)
    hoy = dt.date.today()
    a = _activo(db, purchase_price=1095.0, residual_value=0, depreciation_years=1, purchase_date=hoy - dt.timedelta(days=30))
    asig.asignar(db, actor=admin, asset_id=a.id, holder_type="user", holder_id=admin.id, valid_from=hoy - dt.timedelta(days=1))
    filas = [li for li in lineas(db, hoy - dt.timedelta(days=4), hoy) if li.resource_id == a.id]
    al_titular = sum(li.amount for li in filas if li.kind == "asset")
    en_almacen = sum(li.amount for li in filas if li.kind == "idle")
    assert round(al_titular, 2) == 6.0 and round(en_almacen, 2) == 9.0      # 3 €/día


# ── Fase 3: renovaciones ──────────────────────────────────────────────────────

def test_renovacion_automatica_y_decision_de_cancelar(db):
    from app.core.errores import ErrorDeDominio
    from app.models.alm import ALMContract
    from app.services import alm_renovaciones as ren
    admin = _u(db)
    hoy = dt.date.today()
    auto = ALMContract(title=f"Auto-{_sufijo()}", type="subscription", status="active", auto_renew=True,
                       renewal_date=hoy, billing_cycle="annual", organization_id="1")
    db.add(auto)
    db.flush()
    assert ren.aplicar_al_vencer(db, "contract", auto, hoy) == "auto_renewed"
    assert auto.renewal_date == ren.sumar_meses(hoy, 12)

    corte = ALMContract(title=f"Cancelar-{_sufijo()}", type="subscription", status="active", auto_renew=True,
                        renewal_date=hoy + dt.timedelta(days=20), notice_days=30, organization_id="1")
    db.add(corte)
    db.commit()
    with pytest.raises(ErrorDeDominio):
        ren.decidir(db, admin, "contract", corte.id, "cancel")            # sin motivo
    fila = ren.decidir(db, admin, "contract", corte.id, "cancel", reason="No se usa")
    assert fila["decision"]["decision"] == "cancel" and corte.auto_renew is False
    assert ren.aplicar_al_vencer(db, "contract", corte, hoy + dt.timedelta(days=20)) == "cancelled_at_term"
    assert corte.status == "cancelled"


def test_aviso_de_preaviso_una_sola_vez(db, monkeypatch):
    from app.models.alm import ALMContract, ALMRenewalAlert
    from app.services import alm_renovaciones as ren
    hoy = dt.date.today()
    avisos = []
    monkeypatch.setattr("app.services.notifications.notify_user", lambda *a, **k: avisos.append(a))
    c = ALMContract(title=f"Aviso-{_sufijo()}", type="support", status="active", renewal_date=hoy + dt.timedelta(days=40),
                    notice_days=30, owner_id=_u(db).id, organization_id="1")
    db.add(c)
    db.flush()
    assert ren._avisos_de_renovacion(db, "contract", c, hoy) == 1      # faltan 10 días para el fin del preaviso
    assert ren._avisos_de_renovacion(db, "contract", c, hoy) == 0
    assert db.query(ALMRenewalAlert).filter(ALMRenewalAlert.entity_id == c.id, ALMRenewalAlert.kind == "notice").count() == 1


def test_aviso_de_prestamo_vencido(db, monkeypatch):
    from app.services import alm_asignaciones as asig, alm_renovaciones as ren
    _sin_actas(monkeypatch)
    avisos = []
    monkeypatch.setattr("app.services.notifications.notify_user", lambda *a, **k: avisos.append(a))
    admin, dev = _u(db), _u(db, "dev_test")
    a = _activo(db)
    hoy = dt.date.today()
    asig.prestar(db, actor=admin, asset_id=a.id, holder_type="user", holder_id=dev.id,
                 valid_from=hoy - dt.timedelta(days=10), valid_to=hoy - dt.timedelta(days=2))
    assert ren._avisos_de_prestamos(db, hoy) >= 1
    assert any(x[1] == dev.id for x in avisos)


# ── Fase 3: conciliación ──────────────────────────────────────────────────────

def _gasto(db, importe, categoria="software", estado="approved", proyecto=None):
    from app.models.expenses import Expense
    g = Expense(code=f"EXP-{_sufijo()}", user_id=_u(db).id, category=categoria, description="Licencias",
                amount=importe, currency="EUR", expense_date=dt.date.today(), status=estado, project_id=proyecto,
                organization_id="1")
    db.add(g)
    db.flush()
    return g


def test_conciliacion_contrato_factura_gasto(db):
    from app.models.alm import ALMContract
    from app.services import alm_conciliacion as conc
    admin = _u(db)
    c = ALMContract(title=f"Mensual-{_sufijo()}", type="subscription", status="active", annual_value=1200,
                    billing_cycle="monthly", currency="EUR", start_date=dt.date(2026, 1, 1), organization_id="1")
    db.add(c)
    db.flush()
    f = conc.crear(db, admin, {"number": f"F-{_sufijo()}", "contract_id": c.id, "issue_date": "2026-10-31",
                               "period_from": "2026-10-01", "period_to": "2026-10-31", "amount": 100})
    assert f["expected_amount"] == 100.0 and f["issues"] == ["no_expense"] and f["status"] == "discrepancy"
    g = _gasto(db, 100)
    f = conc.vincular_gasto(db, admin, f["id"], g.id)
    assert f["status"] == "matched" and f["issues"] == []
    # un importe que no cuadra
    mal = conc.crear(db, admin, {"number": f"F-{_sufijo()}", "contract_id": c.id, "issue_date": "2026-11-30",
                                 "period_from": "2026-11-01", "period_to": "2026-11-30", "amount": 150})
    assert "amount_mismatch" in mal["issues"]
    aceptada = conc.aceptar(db, admin, mal["id"], "Subida de precio pactada")
    assert aceptada["status"] == "accepted"


def test_un_gasto_conciliado_no_cuenta_dos_veces_en_el_proyecto(db):
    from app.models.alm import ALMContract
    from app.services import alm_conciliacion as conc
    from app.services.costes_de_proyecto import costes_externos
    admin = _u(db)
    proyecto = _proyecto(db)
    g = _gasto(db, 50, proyecto=proyecto.id)
    antes = costes_externos(db, proyecto.id, "EUR")["gastos"]
    c = ALMContract(title=f"C-{_sufijo()}", type="subscription", status="active", annual_value=600, organization_id="1")
    db.add(c)
    db.flush()
    f = conc.crear(db, admin, {"number": f"F-{_sufijo()}", "contract_id": c.id, "issue_date": dt.date.today().isoformat(),
                               "amount": 50})
    conc.vincular_gasto(db, admin, f["id"], g.id)
    assert round(antes - costes_externos(db, proyecto.id, "EUR")["gastos"], 2) == 50.0


# ── Permisos ──────────────────────────────────────────────────────────────────

def test_permisos_minimos(client, dev_token, sub_token):
    assert client.get("/api/v1/alm/costs", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/alm/history", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/alm/invoices", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/alm/assets", headers=auth(sub_token)).status_code == 403
    # sus propias actas sí
    assert client.get("/api/v1/alm/me/acts", headers=auth(dev_token)).status_code == 200
