"""Turnos en el planificador y ausencias por horas (rev. 180).

Lo que se mide: la aritmética de tramos (partido, noche), el horario efectivo
de una persona en un día (cuadrante > jornada > empresa, festivos por sede,
ausencias por horas), los saldos en horas (un día = las horas de SU turno,
lotes con caducidad), pedir por horas, las reglas nuevas del motor (con la
vista previa y el simulador), la bolsa de horas desde lo imputado y el
planificador con turnos (calendario, carga).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.advanced_config import Office
from app.models.ausencias import TipoDeAusencia
from app.models.horario import MovimientoDeSaldo
from app.models.resources import AbsenceStatus
from app.models.settings import Holiday
from app.models.user import User, UserRole, UserStatus
from app.services.ausencias import bolsa, catalogo, saldos, solicitudes, turnos
from app.services.horario import efectivo as hor
from app.services.horario import jornadas
from app.services.horario import tramos as tr
from app.services.politicas import motor, servicio, simulador
from tests.conftest import HASH_DE_PRUEBA

ORG = "1"
LUNES = date(2026, 12, 7)


@pytest.fixture
def ctx(db):
    from app.db.session import publicar_contexto_de_tenant
    publicar_contexto_de_tenant(db, db.query(User).filter(User.id == "admin-test-id").first())
    return db


def _admin(db):
    return db.query(User).filter(User.id == "admin-test-id").first()


def _persona(db, uid, equipo="Planta", sede=None):
    u = User(id=uid, username=uid, email=f"{uid}@t.es", full_name=uid.title(), role=UserRole.employee,
             status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id=ORG,
             team=equipo, weekly_capacity_hours=40.0, office_id=sede)
    db.add(u)
    db.commit()
    return u


def _sede(db, nombre, pais="ES", ciudad="Madrid"):
    o = Office(id=str(uuid.uuid4()), organization_id=ORG, name=nombre, country=pais, city=ciudad)
    db.add(o)
    db.commit()
    return o


def _publicar(db, admin, reglas, nombre="Reglas"):
    doc = {"dominio": "ausencias", "nombre": nombre, "prioridad": 100, "activa": True, "ambito": {}, "reglas": reglas}
    p = servicio.crear(db, admin, doc)
    servicio.publicar(db, admin, p["id"])
    motor.invalidar(ORG)
    return doc


def _cond(*hijos):
    return {"tipo": "grupo", "op": "and", "hijos": list(hijos)}


def _c(campo, operador, valor=None, valor2=None):
    return {"tipo": "condicion", "campo": campo, "operador": operador, "valor": valor, "valor2": valor2}


def _tipo_horas(db, admin, clave="asuntos_horas", **extra):
    datos = {"clave": clave, "nombre": "Asuntos propios por horas", "unidad": "horas", "modos": ["horas"],
             "descuenta_saldo": True, "saldo": "propio", "cupo_anual": 16, **extra}
    return catalogo.tipo(db, catalogo.guardar_tipo(db, admin, datos)["id"])


# ── Tramos (puro) ────────────────────────────────────────────────────────────

def test_tramos_partido_noche_y_franjas():
    partido = tr.de_lista([["09:00", "14:00"], ["16:00", "19:00"]])
    assert tr.total_horas(partido) == 8
    assert tr.total_horas(tr.restar(partido, [tr.desde_texto("13:00", "17:00")])) == 6
    noche = (tr.desde_texto("22:00", "06:00"),)
    assert noche[0].fin == 30 * 60
    # 02:00–04:00 cae en la madrugada del turno que empezó el día anterior.
    assert tr.total_horas(tr.franja_en_dia("02:00", "04:00", noche)) == 2
    assert tr.mitad(partido, "primera") == (tr.Tramo(540, 780),)
    assert tr.franjas([tr.desde_texto("09:30", "11:00")], 60) == [540, 600]
    with pytest.raises(ValueError):
        tr.de_lista([["09:00", "12:00"], ["11:00", "13:00"]])


# ── Horario efectivo ─────────────────────────────────────────────────────────

def test_horario_efectivo_turno_partido_jornada_de_verano_y_festivo_de_sede(ctx):
    db, admin = ctx, _admin(ctx)
    madrid, bcn = _sede(db, "Madrid"), _sede(db, "Barcelona", ciudad="Barcelona")
    ana, beto = _persona(db, "ana", sede=madrid.id), _persona(db, "beto", sede=bcn.id)
    t = turnos.guardar_turno(db, admin, {"nombre": "Partido", "tramos": [["08:00", "13:00"], ["15:00", "18:00"]],
                                         "pausa_minutos": 0})
    assert t["partido"] and t["duracion_horas"] == 8
    turnos.asignar(db, admin, [{"user_id": ana.id, "fecha": LUNES, "turno_id": t["id"]}])
    # Jornada de verano cada año (diciembre en el ejemplo) para la sede de Barcelona: 6 h de lunes a viernes.
    j = jornadas.guardar_jornada(db, admin, {"nombre": "Intensiva", "semana": {str(d): [["08:00", "14:00"]] for d in range(1, 6)}})
    jornadas.guardar_asignacion(db, admin, {"jornada_id": j["id"], "ambito": "sede", "valor": bcn.id,
                                            "desde": date(2020, 12, 1), "hasta": date(2020, 12, 31),
                                            "recurrente_anual": True})
    # Festivo solo de la sede de Madrid el martes.
    db.add(Holiday(id=str(uuid.uuid4()), organization_id=ORG, name="San Fulano", date=LUNES + timedelta(days=1),
                   office_id=madrid.id))
    db.commit()
    plan = hor.horarios(db, [ana.id, beto.id], LUNES, LUNES + timedelta(days=6))
    assert plan[ana.id][LUNES].origen == "cambio" and plan[ana.id][LUNES].horas == 8
    assert plan[ana.id][LUNES + timedelta(days=1)].festivo == "San Fulano"
    assert plan[ana.id][LUNES + timedelta(days=1)].horas == 0
    assert plan[beto.id][LUNES + timedelta(days=1)].festivo is None
    assert plan[beto.id][LUNES].origen == "jornada" and plan[beto.id][LUNES].horas == 6
    assert plan[beto.id][LUNES + timedelta(days=5)].horas == 0      # sábado
    # Fuera de diciembre, la jornada de la empresa (40 h / 5 días).
    assert hor.dia(db, beto.id, date(2027, 1, 4)).horas == 8


def test_ausencia_por_horas_quita_su_franja_del_horario(ctx):
    db, admin = ctx, _admin(ctx)
    ana = _persona(db, "ana")
    tipo = _tipo_horas(db, admin)
    a = solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                        "modo": "horas", "start_time": "10:00", "end_time": "12:00"})
    assert a.status == AbsenceStatus.pending
    assert a.scheduled_hours == 2 and a.working_days == 0.25 and a.amount == 2
    solicitudes.aplicar_decision(db, a, True, admin, None)
    d = hor.dia(db, ana.id, LUNES)
    assert d.horas_teoricas == 8 and d.horas == 6
    assert tr.a_lista(d.libres) == [["09:00", "10:00"], ["12:00", "17:00"]]
    # Otra petición el mismo día en otra franja no se solapa; en la misma, sí.
    solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                    "modo": "horas", "start_time": "15:00", "end_time": "16:00"})
    with pytest.raises(Exception):
        solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                        "modo": "horas", "start_time": "11:00", "end_time": "11:30"})
    # Un tipo solo por horas no se pide por días.
    with pytest.raises(Exception):
        solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES + timedelta(days=2),
                                        "end_date": LUNES + timedelta(days=2), "modo": "dias"})


# ── Saldos en horas ──────────────────────────────────────────────────────────

def test_lotes_caducan_y_se_gasta_primero_lo_que_antes_caduca():
    lotes = [saldos.Lote(date(2026, 1, 1), 10, date(2026, 12, 31), "derecho"),
             saldos.Lote(date(2026, 1, 1), 3, date(2026, 3, 31), "arrastre")]
    descubierto = saldos.repartir(lotes, [saldos.Consumo(date(2026, 2, 10), 2), saldos.Consumo(date(2026, 6, 1), 9)])
    assert descubierto == 0
    restante, caducado = saldos.restante_en(lotes, descubierto, date(2026, 7, 1))
    assert (restante, caducado) == (1, 1)     # el arrastre sobrante (1) caducó en marzo
    assert saldos.periodo(TipoDeAusencia(periodo_saldo="anual", inicio_periodo_mes=4), date(2026, 2, 1))[:2] == \
        (date(2025, 4, 1), date(2026, 3, 31))


def test_vacaciones_en_horas_un_dia_son_las_horas_de_su_turno(ctx):
    db, admin = ctx, _admin(ctx)
    ana = _persona(db, "ana")
    vac = catalogo.tipo_por_clave(db, "vacation")
    datos = {**catalogo.tipo_dict(vac), "unidad": "horas", "modos": ["dias", "horas"], "requisitos": None}
    catalogo.guardar_tipo(db, admin, datos, vac.id)
    largo = turnos.guardar_turno(db, admin, {"nombre": "Largo", "hora_inicio": "07:00", "hora_fin": "17:00"})
    turnos.asignar(db, admin, [{"user_id": ana.id, "fecha": LUNES, "turno_id": largo["id"]}])
    s0 = saldos.de_tipo(db, ana.id, LUNES, vac)
    # Su jornada media (casi toda de 8 h, un día de 10) convierte los 23 días de derecho en horas.
    assert s0["unidad"] == "horas" and s0["media_diaria_horas"] == pytest.approx(8, abs=0.05)
    assert s0["derecho"] == pytest.approx(23 * s0["media_diaria_horas"], rel=1e-3)
    previa = solicitudes.vista_previa(db, ana, {"type": "vacation", "start_date": LUNES, "end_date": LUNES})
    assert previa["horas"] == 10 and previa["dias_laborables"] == 1
    assert previa["saldo_restante"] == pytest.approx(s0["restante"] - 10)
    # Un ajuste de RRHH suma al saldo.
    from app.services.ausencias import movimientos
    movimientos.crear(db, admin, {"user_id": ana.id, "saldo_clave": "vacaciones", "cantidad": 4, "fecha": LUNES,
                                  "nota": "Compensación"})
    assert saldos.de_tipo(db, ana.id, LUNES, vac)["restante"] == pytest.approx(s0["restante"] + 4)


# ── Reglas nuevas del motor ──────────────────────────────────────────────────

def test_reglas_por_horas_minimo_redondeo_negativo_y_dependencias(ctx):
    db, admin = ctx, _admin(ctx)
    ana = _persona(db, "ana")
    tipo = _tipo_horas(db, admin, cupo_anual=2)
    _publicar(db, admin, [
        {"nombre": "Mínimo media hora", "activa": True, "detener": False, "exceso": None,
         "condicion": _cond(_c("modo", "eq", "horas"), _c("horas", "lt", 0.5)),
         "resultados": [{"tipo": "block", "mensaje": "Mínimo media hora"}]},
        {"nombre": "Redondeo y negativo", "activa": True, "detener": False, "exceso": None,
         "condicion": _cond(_c("tipo", "eq", tipo.clave)),
         "resultados": [{"tipo": "redondeo", "minutos": "60", "modo": "arriba"},
                        {"tipo": "saldo_negativo", "hasta": 1}]},
        {"nombre": "No tras una baja", "activa": True, "detener": False, "exceso": None,
         "condicion": _cond(_c("tipos_contiguos", "in", ["sick"])),
         "resultados": [{"tipo": "block", "mensaje": "No pegado a una baja"}]},
        {"nombre": "Tarde", "activa": True, "detener": False, "exceso": None,
         "condicion": _cond(_c("hora_inicio", "gte", "14:00")),
         "resultados": [{"tipo": "warn", "mensaje": "Por la tarde"}]},
    ])
    base = {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES, "modo": "horas"}
    corta = solicitudes.vista_previa(db, ana, {**base, "start_time": "10:00", "end_time": "10:15"})
    assert corta["decision"] == "block" and "Mínimo media hora" in corta["bloqueos"]
    # 14:00–16:30 (2 h 30) → 3 h por el redondeo; el cupo es 2 h y se permite quedar en −1.
    p = solicitudes.vista_previa(db, ana, {**base, "start_time": "14:00", "end_time": "16:30"})
    assert p["redondeo"]["despues"] == 3 and p["horas"] == 3
    assert p["negativo_permitido"] == 1 and p["saldo_restante"] == -1 and not p["bloqueos"]
    assert "Por la tarde" in p["avisos"]
    a = solicitudes.solicitar(db, ana, {**base, "start_time": "14:00", "end_time": "16:30"})
    assert a.scheduled_hours == 3
    # 3 h más dejarían −4: no se permite.
    p2 = solicitudes.vista_previa(db, ana, {**base, "start_date": LUNES + timedelta(days=1),
                                            "end_date": LUNES + timedelta(days=1), "start_time": "10:00",
                                            "end_time": "13:00"})
    assert p2["bloqueos"]
    # Dependencia: pegada a una baja (viernes anterior) no se puede.
    solicitudes.solicitar(db, ana, {"type": "sick", "start_date": LUNES - timedelta(days=3),
                                    "end_date": LUNES - timedelta(days=3)})
    p3 = solicitudes.vista_previa(db, ana, {**base, "start_time": "09:00", "end_time": "10:00"})
    assert "No pegado a una baja" in p3["bloqueos"]


def test_simulador_ve_las_reglas_nuevas_sobre_lo_ya_pedido(ctx):
    db, admin = ctx, _admin(ctx)
    ana, beto = _persona(db, "ana"), _persona(db, "beto")
    tipo = _tipo_horas(db, admin)
    solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                    "modo": "horas", "start_time": "09:00", "end_time": "13:00"})
    solicitudes.solicitar(db, beto, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                     "modo": "horas", "start_time": "09:00", "end_time": "10:00"})
    doc = {"dominio": "ausencias", "nombre": "Máximo 2 h al día", "prioridad": 100, "activa": True, "ambito": {},
           "reglas": [{"nombre": "Máx", "activa": True, "detener": False, "exceso": None,
                       "condicion": _cond(_c("horas_max_dia", "gt", 2)),
                       "resultados": [{"tipo": "block", "mensaje": "Más de 2 h en un día"}]}]}
    r = simulador.simular(db, admin, documento=doc, ultimos=10)
    assert r["evaluadas"] >= 2 and r["cambian"] == 1 and r["resumen_de_cambios"]["nuevos_bloqueos"] == 1
    # Excepción en el ámbito: ana queda fuera.
    doc["ambito"] = {"excepto_personas": [ana.id]}
    assert simulador.simular(db, admin, documento=doc, ultimos=10)["cambian"] == 0


# ── Bolsa de horas ───────────────────────────────────────────────────────────

def test_bolsa_de_horas_desde_el_exceso_imputado(ctx):
    from app.models.imputation import Imputation
    from app.models.project import Project, ProjectType
    db, admin = ctx, _admin(ctx)
    ana = _persona(db, "ana")
    assert bolsa.horas_de_bolsa(10, 8, "laborable", {"factor": 1.5, "umbral_minutos": 30}) == 2.25
    assert bolsa.horas_de_bolsa(4, 0, "festivo", {"factor": 1, "factor_festivo": 2, "tope_diario": 6}) == 6
    tipo = catalogo.tipo(db, catalogo.guardar_tipo(db, admin, {
        "clave": "compensacion", "nombre": "Compensación", "unidad": "horas", "modos": ["horas", "dias"],
        "descuenta_saldo": True, "saldo": "bolsa", "caduca_meses": 6,
        "bolsa": {"factor": 1.0, "factor_festivo": 2.0, "umbral_minutos": 0}})["id"])
    p = Project(id=str(uuid.uuid4()), organization_id=ORG, code="BOL-1", name="Bolsa",
                project_type=ProjectType.development)
    db.add(p)
    viernes = LUNES - timedelta(days=3)
    sabado = LUNES - timedelta(days=2)
    for d, h in ((viernes, 10), (sabado, 3)):
        db.add(Imputation(id=str(uuid.uuid4()), organization_id=ORG, user_id=ana.id, project_id=p.id, date=d, hours=h))
    db.commit()
    r = bolsa.recalcular(db, viernes, sabado)
    assert r["creados"] == 2
    assert bolsa.recalcular(db, viernes, sabado)["creados"] == 0      # idempotente
    movs = {m.fecha: m for m in db.query(MovimientoDeSaldo).filter_by(user_id=ana.id, saldo_clave=tipo.id).all()}
    assert movs[viernes].cantidad == 2 and movs[sabado].cantidad == 3       # sábado: día libre, factor 1
    assert movs[viernes].caduca == date(2027, 6, 4)
    s = saldos.de_tipo(db, ana.id, LUNES, tipo)
    assert s["saldo"] == "bolsa" and s["restante"] == 5
    a = solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES, "end_date": LUNES,
                                        "modo": "horas", "start_time": "09:00", "end_time": "13:00"})
    assert a.scheduled_hours == 4
    assert saldos.de_tipo(db, ana.id, LUNES, tipo)["restante"] == 1


# ── Planificador con turnos ──────────────────────────────────────────────────

def test_planificador_usa_el_horario_efectivo(ctx):
    from app.services.planificador.calendario import cargar_calendarios
    from app.services.resource_analytics import capacidad_de_semana, get_user_week_hours
    db, admin = ctx, _admin(ctx)
    ana = _persona(db, "ana")
    finde = turnos.guardar_turno(db, admin, {"nombre": "Finde", "hora_inicio": "08:00", "hora_fin": "20:00",
                                             "trabaja_festivos": True})
    sabado = LUNES + timedelta(days=5)
    turnos.asignar(db, admin, [{"user_id": ana.id, "fecha": sabado, "turno_id": finde["id"]},
                               {"user_id": ana.id, "fecha": LUNES, "turno_id": None}])
    _empresa, cals = cargar_calendarios(db, ORG, [ana.id], LUNES)
    c = cals[ana.id]
    assert not c.es_laborable(LUNES) and c.es_laborable(sabado) and c.horas(sabado) == 12
    assert c.horas(LUNES + timedelta(days=1)) == 8
    assert c.horas_en(LUNES, LUNES + timedelta(days=6)) == 4 * 8 + 12
    assert c.fin_desde(LUNES + timedelta(days=4), 2) == sabado
    hw = get_user_week_hours(db, ana.id, LUNES)
    assert hw["scheduled_hours"] == 44 and capacidad_de_semana(hw) == 44
    # Una ausencia aprobada de 2 h el martes quita 2 h de la capacidad.
    tipo = _tipo_horas(db, admin)
    a = solicitudes.solicitar(db, ana, {"absence_type_id": tipo.id, "start_date": LUNES + timedelta(days=1),
                                        "end_date": LUNES + timedelta(days=1), "modo": "horas",
                                        "start_time": "09:00", "end_time": "11:00"})
    solicitudes.aplicar_decision(db, a, True, admin, None)
    assert capacidad_de_semana(get_user_week_hours(db, ana.id, LUNES)) == 42
    _e, cals = cargar_calendarios(db, ORG, [ana.id], LUNES)
    assert cals[ana.id].horas(LUNES + timedelta(days=1)) == 6
