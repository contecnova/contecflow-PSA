"""Horas extra y trabajo fuera de horario aprobados por flujos (18-11-2026, rev. 184).

Lo que se mide:
- sin configuración el módulo está ACTIVO (por defecto) con control «avisar»;
- desactivado, no se pide nada y la imputación no cambia;
- registro de jornada coherente (franja dentro de horario, tipo de día);
- ciclo sin flujo (decide su responsable) con línea de tiempo y auditoría;
- segregación: ni lo propio ni lo pedido para otro, también en la bandeja;
- con flujo `overtime`: se decide en la bandeja de aprobaciones;
- reglas sin código: el máximo legal de 80 h/año pagadas como regla publicada
  (bloquea el pago, no la bolsa) y su lectura como límite en el resumen;
- control al imputar: bloquear sin autorización, regularizar (declaración
  posterior que se recalcula y se anula);
- bolsa `solo_horas_extra`: solo el exceso cubierto por lo aprobado en bolsa;
- GRC: retención, RGPD y los dos controles del informe de cumplimiento.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.horas_extra import EventoDeHorasExtra, PeticionDeHorasExtra
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from app.services.horario import efectivo as hor
from app.services.horario import tramos as tr
from app.services.horas_extra import calculo, control
from app.services.politicas import motor, servicio
from tests.conftest import auth

ORG = "1"
LUNES = date(2026, 12, 7)          # lunes laborable sin festivos en la base de pruebas
SABADO = LUNES + timedelta(days=5)


@pytest.fixture
def ctx(db):
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, db.query(User).filter(User.id == "admin-test-id").first())
    dev = db.query(User).filter(User.id == "dev-test-id").first()
    dev.manager_id = "pm-test-id"
    db.commit()
    return db


def _activar(client, token, **extra):
    datos = {"activo": True, "control_imputacion": "avisar", "tolerancia_minutos": 15,
             "compensaciones": ["pago", "bolsa", "ninguna"], "compensacion_por_defecto": "bolsa",
             "workflow_id": None, "tipo_bolsa_id": None, "pedir_en_nombre": True, "exigir_motivo": True, **extra}
    r = client.put("/api/v1/overtime/config", json=datos, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fin_de_horario(db, uid, d) -> str:
    x = hor.dia(db, uid, d)
    return tr.hhmm(max(t.fin for t in x.libres))


def _franja_tras_horario(db, uid, d, horas=2):
    fin = tr.minutos(_fin_de_horario(db, uid, d))
    return tr.hhmm(fin), tr.hhmm(fin + horas * 60)


def _pedir(client, token, **datos):
    return client.post("/api/v1/overtime", json={"motivo": "Cierre de mes", **datos}, headers=auth(token))


def _publicar(db, reglas, nombre="Horas extra"):
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    p = servicio.crear(db, admin, {"dominio": "horas_extra", "nombre": nombre, "prioridad": 100, "activa": True,
                                   "ambito": {}, "reglas": reglas})
    servicio.publicar(db, admin, p["id"])
    motor.invalidar(ORG)


def _c(campo, operador, valor=None):
    return {"tipo": "condicion", "campo": campo, "operador": operador, "valor": valor, "valor2": None}


def _regla(nombre, condicion, *resultados):
    return {"nombre": nombre, "activa": True, "detener": False, "exceso": None,
            "condicion": {"tipo": "grupo", "op": "and", "hijos": [condicion]}, "resultados": list(resultados)}


# ── Desactivado ──────────────────────────────────────────────────────────────

def test_por_defecto_esta_activo_con_aviso(client, dev_token):
    r = client.get("/api/v1/overtime/config", headers=auth(dev_token))
    d = r.json()["data"]
    assert r.status_code == 200 and d["activo"] is True and d["control_imputacion"] == "avisar"


def test_desactivado_no_toca_la_imputacion(client, dev_token, hr_token, ctx):
    assert _activar(client, hr_token, activo=False)["activo"] is False
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="laborable", horas=2)
    assert r.status_code == 409 and r.json()["code"] == "horas_extra_desactivadas"
    assert control.capacidad_semanal_extra(ctx, "dev-test-id", LUNES) == 0.0
    assert control.comprobar(ctx, "dev-test-id", SABADO, 8)["accion"] == "nada"


def test_solo_admin_o_rrhh_configura_y_queda_auditado(client, dev_token, hr_token, ctx):
    r = client.put("/api/v1/overtime/config", headers=auth(dev_token), json={
        "activo": True, "control_imputacion": "avisar", "compensaciones": ["pago"], "compensacion_por_defecto": "pago"})
    assert r.status_code == 403
    _activar(client, hr_token)
    from app.models.enterprise import AuditLog as Audit
    assert ctx.query(Audit).filter(Audit.resource == "overtime_config").count() == 1


# ── Coherencia con el horario ────────────────────────────────────────────────

def test_registro_de_jornada_coherente(client, admin_token, dev_token, ctx):
    _activar(client, admin_token)
    fin = _fin_de_horario(ctx, "dev-test-id", LUNES)
    dentro = tr.hhmm(tr.minutos(fin) - 60)
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="fuera_de_franja", hora_inicio=dentro, hora_fin=tr.hhmm(tr.minutos(fin) + 60))
    assert r.status_code == 422 and r.json()["code"] == "horas_extra_franja_dentro_de_horario"
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="festivo", horas=2)
    assert r.status_code == 422 and r.json()["code"] == "horas_extra_tipo_no_coincide"
    ini, fin2 = _franja_tras_horario(ctx, "dev-test-id", LUNES, 1)
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="laborable", hora_inicio=ini, hora_fin=fin2, horas=3)
    assert r.status_code == 422 and r.json()["code"] == "horas_extra_horas_mayor_que_franja"
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="laborable", horas=2, motivo="")
    assert r.status_code == 422 and r.json()["code"] == "horas_extra_motivo_obligatorio"


# ── Ciclo sin flujo, segregación ─────────────────────────────────────────────

def test_ciclo_sin_flujo_decide_su_responsable_y_nadie_aprueba_lo_suyo(client, admin_token, dev_token, pm_token, ctx):
    _activar(client, admin_token)
    ini, fin = _franja_tras_horario(ctx, "dev-test-id", LUNES)
    previa = client.post("/api/v1/overtime/preview", headers=auth(dev_token), json={
        "fecha": str(LUNES), "tipo": "laborable", "hora_inicio": ini, "hora_fin": fin, "motivo": "x"}).json()["data"]
    assert previa["horas"] == 2 and previa["clase_dia"] == "laborable" and previa["errores"] == []
    assert previa["aprobaciones"][0]["origen"] == "responsable"
    r = _pedir(client, dev_token, fecha=str(LUNES), tipo="laborable", hora_inicio=ini, hora_fin=fin)
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert p["estado"] == "pendiente" and p["horas"] == 2 and p["en_aprobacion"] is False

    r = client.post(f"/api/v1/overtime/{p['id']}/review", headers=auth(dev_token), json={"aprobado": True})
    assert r.status_code == 403                       # SoD: lo suyo no
    bandeja = client.get("/api/v1/overtime/inbox", headers=auth(pm_token)).json()["data"]
    assert [b["peticion"]["id"] for b in bandeja] == [p["id"]] and bandeja[0]["sin_flujo"] is True
    r = client.post(f"/api/v1/overtime/{p['id']}/review", headers=auth(pm_token),
                    json={"aprobado": True, "nota": "OK", "horas_autorizadas": 1.5})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["estado"] == "aprobada" and r.json()["data"]["horas_autorizadas"] == 1.5

    ciclo = client.get(f"/api/v1/overtime/{p['id']}", headers=auth(dev_token)).json()["data"]
    assert [e["tipo"] for e in ciclo["linea_de_tiempo"]] == ["creada", "en_revision", "aprobada"]
    assert ciclo["evaluaciones"][0]["momento"] == "solicitud"
    from app.models.enterprise import AuditLog as Audit
    acciones = {a.action for a in ctx.query(Audit).filter(Audit.resource == "overtime_request",
                                                          Audit.resource_id == p["id"]).all()}
    assert acciones == {"CREATE", "APPROVE"}
    # Otro empleado no la ve (404, no se confirma que existe).
    r = client.get(f"/api/v1/overtime/{p['id']}", headers=auth(client_token_de(client, ctx)))
    assert r.status_code == 404


def client_token_de(client, db):
    """Un segundo empleado sin relación con dev (para la visibilidad)."""
    from tests.conftest import HASH_DE_PRUEBA, TEST_PASSWORD
    from app.models.user import UserRole, UserStatus
    if db.query(User).filter(User.id == "otro-he").first() is None:
        db.add(User(id="otro-he", username="otro_he", email="otro_he@t.es", full_name="Otro", role=UserRole.employee,
                    status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id=ORG,
                    weekly_capacity_hours=40.0))
        db.commit()
    r = client.post("/api/v1/auth/login", json={"username": "otro_he", "password": TEST_PASSWORD})
    return r.cookies.get("access_token")


def test_quien_pide_por_otro_no_aprueba_tampoco_en_la_bandeja(client, admin_token, pm_token, hr_token, ctx):
    from tests.test_approvals import add_step, create_workflow
    wf = create_workflow(client, admin_token, entity_type="overtime", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="hr")
    _activar(client, admin_token, workflow_id=wf["id"])
    r = _pedir(client, pm_token, user_id="dev-test-id", fecha=str(SABADO), tipo="no_laborable", horas=4,
               compensacion="pago")
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert p["en_aprobacion"] is True and p["solicitante_id"] == "pm-test-id"
    from app.models.billing_reports import ApprovalRequest
    req = ctx.query(ApprovalRequest).filter(ApprovalRequest.entity_type == "overtime",
                                            ApprovalRequest.entity_id == p["id"]).one()
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", json={"decision": "approved"},
                    headers=auth(pm_token))
    assert r.status_code == 403                       # la pidió él para otro
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", json={"decision": "approved"},
                    headers=auth(hr_token))
    assert r.status_code == 200, r.text
    ctx.expire_all()
    fila = ctx.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == p["id"]).one()
    assert fila.estado == "aprobada" and fila.horas_autorizadas == 4
    # Liquidar el pago: RRHH, con referencia, una sola vez.
    r = client.post(f"/api/v1/overtime/{p['id']}/settle", json={"referencia": "NOM-2026-12"}, headers=auth(hr_token))
    assert r.status_code == 200 and r.json()["data"]["liquidacion"]["referencia"] == "NOM-2026-12"
    r = client.post(f"/api/v1/overtime/{p['id']}/settle", json={"referencia": "otra"}, headers=auth(hr_token))
    assert r.status_code == 409 and r.json()["code"] == "horas_extra_ya_liquidada"


# ── Reglas sin código: el máximo legal ───────────────────────────────────────

def test_maximo_legal_de_80_horas_pagadas_es_una_regla_editable(client, admin_token, dev_token, pm_token, ctx):
    _activar(client, admin_token)
    _publicar(ctx, [_regla("80 h/año pagadas", _c("horas_en_anio_pago", "gt", 80),
                           {"tipo": "block", "mensaje": "Máximo legal de 80 h/año"})])
    for i in range(20):                               # 79 h pagadas ya aprobadas en el año
        ctx.add(PeticionDeHorasExtra(id=str(uuid.uuid4()), organization_id=ORG, user_id="dev-test-id",
                                     origen="previa", tipo="no_laborable", fecha=date(2026, 3, 7) + timedelta(days=7 * i),
                                     horas=3.95, horas_autorizadas=3.95, compensacion="pago", factor=1.0,
                                     estado="aprobada"))
    ctx.commit()
    r = _pedir(client, dev_token, fecha=str(SABADO), tipo="no_laborable", horas=2, compensacion="pago")
    assert r.status_code == 422 and r.json()["code"] == "horas_extra_bloqueada"
    assert "80" in r.json()["detail"]
    r = _pedir(client, dev_token, fecha=str(SABADO), tipo="no_laborable", horas=2, compensacion="bolsa")
    assert r.status_code == 200, r.text            # compensadas con descanso: no cuentan
    res = client.get("/api/v1/overtime/summary", params={"desde": "2026-01-01", "hasta": "2026-12-31"},
                     headers=auth(pm_token)).json()["data"]
    assert res["limites_publicados"][0]["campo"] == "horas_en_anio_pago"
    fila = next(f for f in res["filas"] if f["clave"] == "dev-test-id")
    lim = fila["limites"][0]
    assert lim["umbral"] == 80 and lim["consumo"] == 79.0 and lim["efecto"] == "block"


def test_los_ejemplos_se_cargan_como_borradores(client, admin_token, ctx):
    r = client.post("/api/v1/policies/examples/horas_extra", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["politicas_creadas"] == 2
    from app.models.politicas import Politica
    estados = {p.estado for p in ctx.query(Politica).filter(Politica.dominio == "horas_extra").all()}
    assert "publicada" not in estados


# ── Control al imputar ───────────────────────────────────────────────────────

def _imputar(db, uid, d, h, pid="p-he"):
    if db.query(Project.id).filter(Project.id == pid).first() is None:
        db.add(Project(id=pid, code=pid.upper(), name="HE", status=ProjectStatus.active,
                       project_type=ProjectType.consulting, organization_id=ORG))
    i = Imputation(id=str(uuid.uuid4()), user_id=uid, project_id=pid, date=d, hours=h, organization_id=ORG,
                   description="x")
    db.add(i)
    db.commit()
    return i


def test_bloquear_sin_autorizacion_y_permitir_lo_aprobado(client, admin_token, pm_token, dev_token, ctx):
    _activar(client, admin_token, control_imputacion="bloquear")
    from app.core.errores import ErrorDeDominio
    with pytest.raises(ErrorDeDominio) as e:
        control.antes_de_imputar(ctx, "dev-test-id", SABADO, 3)
    assert e.value.code == "horas_extra_sin_autorizar"
    assert control.antes_de_imputar(ctx, "dev-test-id", SABADO, 0.2) is None      # dentro de la tolerancia
    p = _pedir(client, dev_token, fecha=str(SABADO), tipo="no_laborable", horas=3).json()["data"]
    client.post(f"/api/v1/overtime/{p['id']}/review", headers=auth(pm_token), json={"aprobado": True})
    assert control.antes_de_imputar(ctx, "dev-test-id", SABADO, 3) is None
    assert control.capacidad_semanal_extra(ctx, "dev-test-id", SABADO) == 3
    r = client.get("/api/v1/overtime/check", params={"fecha": str(SABADO), "horas": 5}, headers=auth(dev_token))
    assert r.json()["data"]["accion"] == "bloquear" and r.json()["data"]["sin_autorizar"] == 2


def test_regularizar_crea_recalcula_y_anula_la_declaracion(client, admin_token, ctx):
    _activar(client, admin_token, control_imputacion="regularizar")
    i = _imputar(ctx, "dev-test-id", SABADO, 3)
    r = control.despues_de_imputar(ctx, "dev-test-id", SABADO, "dev-test-id")
    assert r["accion"] == "creada"
    p = ctx.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == r["peticion_id"]).one()
    assert (p.origen, p.estado, p.horas, p.tipo) == ("posterior", "pendiente", 3, "no_laborable")
    i.hours = 5
    ctx.commit()
    assert control.despues_de_imputar(ctx, "dev-test-id", SABADO, "dev-test-id")["accion"] == "actualizada"
    ctx.refresh(p)
    assert p.horas == 5
    i.is_active = False
    ctx.commit()
    assert control.despues_de_imputar(ctx, "dev-test-id", SABADO, None)["accion"] == "anulada"
    ctx.refresh(p)
    assert p.estado == "cancelada"
    tipos = [e.tipo for e in ctx.query(EventoDeHorasExtra).filter(EventoDeHorasExtra.peticion_id == p.id)
             .order_by(EventoDeHorasExtra.created_at, EventoDeHorasExtra.id).all()]
    assert tipos[0] == "declarada" and "recalculada" in tipos and tipos[-1] == "anulada"


def test_sin_autorizar_con_tolerancia():
    assert calculo.sin_autorizar(8.2, 8, 0, 15) == 0.0
    assert calculo.sin_autorizar(9.5, 8, 1, 15) == 0.5
    assert calculo.sin_autorizar(4, 0, 4, 0) == 0.0


# ── Bolsa de horas solo con lo aprobado ──────────────────────────────────────

def test_bolsa_solo_horas_extra_aprobadas(client, admin_token, ctx):
    from app.models.horario import MovimientoDeSaldo
    from app.services.ausencias import bolsa, catalogo
    admin = ctx.query(User).filter(User.id == "admin-test-id").first()
    tipo_id = catalogo.guardar_tipo(ctx, admin, {
        "clave": "bolsa_he", "nombre": "Compensación de horas extra", "unidad": "horas", "modos": ["horas"],
        "descuenta_saldo": True, "saldo": "bolsa", "bolsa": {"factor": 1.0, "solo_horas_extra": True}})["id"]
    _activar(client, admin_token, tipo_bolsa_id=tipo_id)
    _imputar(ctx, "dev-test-id", SABADO, 5)
    bolsa.recalcular(ctx, SABADO, SABADO, ["dev-test-id"])
    assert ctx.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.saldo_clave == tipo_id).count() == 0
    ctx.add(PeticionDeHorasExtra(id=str(uuid.uuid4()), organization_id=ORG, user_id="dev-test-id", origen="previa",
                                 tipo="no_laborable", fecha=SABADO, horas=3, horas_autorizadas=3,
                                 compensacion="bolsa", factor=1.0, estado="aprobada"))
    ctx.commit()
    bolsa.recalcular(ctx, SABADO, SABADO, ["dev-test-id"])
    m = ctx.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.saldo_clave == tipo_id).one()
    assert m.cantidad == 3


# ── GRC ──────────────────────────────────────────────────────────────────────

def test_grc_retencion_rgpd_e_informe(client, admin_token, dev_token, ctx):
    from app.db.bloqueo_legal import TIPOS
    from app.services import informe_de_cumplimiento
    from app.services.cab_service.gdpr import _gdpr_portability_export
    assert "overtime_requests" in TIPOS
    _activar(client, admin_token)
    _pedir(client, dev_token, fecha=str(SABADO), tipo="no_laborable", horas=2)
    dev = ctx.query(User).filter(User.id == "dev-test-id").first()
    copia = _gdpr_portability_export(ctx, dev)
    assert copia["data_summary"]["overtime_requests"] == 1 and copia["overtime_requests"][0]["horas"] == 2
    ids = {c["id"] for c in informe_de_cumplimiento.generar(ctx, ORG)["controls"]}
    assert {"overtime_limits", "overtime_unauthorized"} <= ids


# ── Vista previa con datos a medias (19-11-2026) ────────────────────────────

def test_vista_previa_a_medias_no_da_422(client, dev_token):
    """Mientras se escribe, sin horas ni franja: lo que falta como error a enseñar, sin 422."""
    r = client.post("/api/v1/overtime/preview", headers=auth(dev_token),
                    json={"fecha": str(LUNES), "tipo": "laborable"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["decision"] == "incompleta" and d["errores"] and d["codigo_error"] == "horas_extra_sin_franja_ni_horas"
    # Pedir de verdad sigue rechazándolo.
    assert _pedir(client, dev_token, fecha=str(LUNES), tipo="laborable").status_code == 422
