"""Ausencias gobernadas por reglas (tarea #25, revisión 167).

Lo que se mide: cupo por día y turno con orden de llegada al pedir y al
aprobar, promoción de la lista de espera al cancelar y al rechazar, la carrera
por la última plaza, el documento exigido con su recordatorio, el acceso y la
auditoría de un parte médico, la migración de tipos, el flujo multinivel y el
aislamiento por empresa.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.ausencias import RequisitoDeAusencia, ReservaDeCupo
from app.models.resources import Absence, AbsenceStatus
from app.models.user import User, UserRole, UserStatus
from app.services.ausencias import catalogo, cupos, documentos, solicitudes, turnos
from app.services.politicas import motor, servicio
from tests.conftest import HASH_DE_PRUEBA, auth

ORG = "1"
LUNES = date(2026, 12, 7)


@pytest.fixture
def ctx(db):
    """La sesión con el contexto de la empresa (como una petición autenticada)."""
    from app.db.session import publicar_contexto_de_tenant
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    publicar_contexto_de_tenant(db, admin)
    return db


def _persona(db, uid, rol=UserRole.employee, jefe=None, equipo="Soporte"):
    u = User(id=uid, username=uid, email=f"{uid}@t.es", full_name=uid.title(), role=rol, status=UserStatus.active,
             is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id=ORG, team=equipo, manager_id=jefe,
             weekly_capacity_hours=40.0)
    db.add(u)
    db.commit()
    return u


def _turnos_y_cuadrante(db, admin, personas, dias=3):
    m = turnos.guardar_turno(db, admin, {"nombre": "Mañana", "hora_inicio": "06:00", "hora_fin": "14:00",
                                         "personas_requeridas": 1, "trabaja_festivos": True})
    n = turnos.guardar_turno(db, admin, {"nombre": "Noche", "hora_inicio": "22:00", "hora_fin": "06:00",
                                         "trabaja_festivos": True})
    turnos.asignar(db, admin, [{"user_id": p.id, "fecha": LUNES + timedelta(days=i), "turno_id": m["id"]}
                               for p in personas for i in range(dias)])
    return m, n


def _politica_de_cupo(db, admin, momento="solicitud", si_lleno=None, maximo=2):
    doc = {"dominio": "ausencias", "nombre": f"Cupo {momento}", "prioridad": 100, "activa": True, "ambito": {},
           "reglas": [{"nombre": "Cupo", "activa": True, "detener": False, "exceso": None,
                       "condicion": {"tipo": "grupo", "op": "and", "hijos": [
                           {"tipo": "condicion", "campo": "tipo", "operador": "eq", "valor": "vacation"}]},
                       "resultados": [{"tipo": "cupo", "clave": str(uuid.uuid4()), "maximo": maximo,
                                       "agrupar_por": "empresa", "por_turno": True, "momento": momento,
                                       "si_lleno": si_lleno if si_lleno is not None else [{"tipo": "waitlist"}],
                                       "avisar_al_promover": [{"tipo": "solicitante"}], "canales": ["app"]}]}]}
    p = servicio.crear(db, admin, doc)
    servicio.publicar(db, admin, p["id"])
    motor.invalidar(ORG)


def _pedir(db, u, dia=LUNES, hasta=None, tipo="vacation", **extra):
    return solicitudes.solicitar(db, u, {"type": tipo, "start_date": dia, "end_date": hasta or dia, **extra})


def _admin(db):
    return db.query(User).filter(User.id == "admin-test-id").first()


# ── Cupo por día y turno ─────────────────────────────────────────────────────

def test_cupo_por_turno_y_dia_al_pedir_por_orden_de_llegada(ctx):
    db, admin = ctx, _admin(ctx)
    a, b, c = (_persona(db, x) for x in ("ana", "beto", "carla"))
    _turnos_y_cuadrante(db, admin, [a, b, c])
    _politica_de_cupo(db, admin)
    x, y, z = _pedir(db, a), _pedir(db, b), _pedir(db, c)
    assert (x.status, y.status, z.status) == (AbsenceStatus.pending, AbsenceStatus.pending, AbsenceStatus.waitlisted)
    assert cupos.posicion(db, z.id) == 1
    # Otro día del mismo turno tiene sus dos plazas.
    assert _pedir(db, c, LUNES + timedelta(days=1)).status == AbsenceStatus.pending
    # La vista previa enseña la lista de espera y el cupo lleno.
    d = _persona(db, "dani")
    turnos.asignar(db, admin, [{"user_id": d.id, "fecha": LUNES, "turno_id": turnos.turnos(db)[0].id}])
    previa = solicitudes.vista_previa(db, d, {"type": "vacation", "start_date": LUNES, "end_date": LUNES})
    assert previa["lista_de_espera"] and previa["cupos"][0]["lleno"] and previa["cupos"][0]["huecos"][0]["ocupadas"] == 2


def test_cupo_al_aprobar_gana_quien_se_aprueba_antes(ctx):
    db, admin = ctx, _admin(ctx)
    a, b, c = (_persona(db, x) for x in ("ana", "beto", "carla"))
    _turnos_y_cuadrante(db, admin, [a, b, c])
    _politica_de_cupo(db, admin, momento="aprobacion")
    x, y, z = _pedir(db, a), _pedir(db, b), _pedir(db, c)
    assert {x.status, y.status, z.status} == {AbsenceStatus.pending}
    solicitudes.aplicar_decision(db, z, True, admin, None)
    solicitudes.aplicar_decision(db, y, True, admin, None)
    solicitudes.aplicar_decision(db, x, True, admin, None)
    assert (z.status, y.status, x.status) == (AbsenceStatus.approved, AbsenceStatus.approved, AbsenceStatus.waitlisted)
    # Al rechazar una aprobada no: al cancelar la de beto, ana pasa (ya estaba aprobada).
    solicitudes.cancelar(db, b, db.get(Absence, y.id))
    db.refresh(x)
    assert x.status == AbsenceStatus.approved


def test_lista_de_espera_promueve_al_cancelar_y_al_rechazar(ctx):
    db, admin = ctx, _admin(ctx)
    a, b, c, d = (_persona(db, x) for x in ("ana", "beto", "carla", "dani"))
    _turnos_y_cuadrante(db, admin, [a, b, c, d])
    _politica_de_cupo(db, admin)
    x, y, z, w = _pedir(db, a), _pedir(db, b), _pedir(db, c), _pedir(db, d)
    assert (z.status, w.status) == (AbsenceStatus.waitlisted, AbsenceStatus.waitlisted)
    assert (cupos.posicion(db, z.id), cupos.posicion(db, w.id)) == (1, 2)
    solicitudes.cancelar(db, a, x)
    db.refresh(z), db.refresh(w)
    assert z.status == AbsenceStatus.pending and w.status == AbsenceStatus.waitlisted
    solicitudes.aplicar_decision(db, y, False, admin, "No")
    db.refresh(w)
    assert w.status == AbsenceStatus.pending
    from app.models.enterprise import Notification
    assert db.query(Notification).filter(Notification.user_id == "carla", Notification.resource_id == z.id).count() >= 1
    tipos = [e.tipo for e in db.query(__import__("app.models.ausencias", fromlist=["x"]).EventoDeAusencia)
             .filter_by(absence_id=z.id).all()]
    assert tipos[:3] == ["pedida", "en_espera", "promovida"]


def test_bloquear_si_lleno_rechaza_y_no_guarda_plaza(ctx):
    db, admin = ctx, _admin(ctx)
    a, b = _persona(db, "ana"), _persona(db, "beto")
    _turnos_y_cuadrante(db, admin, [a, b])
    _politica_de_cupo(db, admin, maximo=1, si_lleno=[{"tipo": "block", "mensaje": "Sin plaza"}])
    _pedir(db, a)
    from app.core.errores import ErrorDeDominio
    with pytest.raises(ErrorDeDominio) as e:
        _pedir(db, b)
    assert e.value.status_code == 422  # la evaluación ya lo ve lleno: bloqueo de política
    assert db.query(ReservaDeCupo).count() == 1


def test_el_cupo_cuenta_las_ausencias_que_ya_existian_y_es_idempotente(ctx):
    db, admin = ctx, _admin(ctx)
    a, b, c = (_persona(db, x) for x in ("ana", "beto", "carla"))
    _turnos_y_cuadrante(db, admin, [a, b, c])
    tipo = catalogo.tipo_por_clave(db, "vacation")
    previas = [Absence(id=str(uuid.uuid4()), organization_id=ORG, user_id=u.id, type="vacation", absence_type_id=tipo.id,
                       start_date=d, end_date=d, working_days=1, amount=1, unit="dias", status=AbsenceStatus.approved,
                       is_active=True, requested_at=cupos.ahora())
               for u, d in ((a, LUNES), (a, LUNES + timedelta(days=1)))]
    db.add_all(previas)
    db.commit()
    # Al publicar: la ausencia de ana del lunes (anterior a la política) ocupa su plaza.
    _politica_de_cupo(db, admin, maximo=1)
    assert db.query(ReservaDeCupo).filter_by(absence_id=previas[0].id, estado="ocupa").count() == 1
    from app.models.politicas import Politica
    pub = db.query(Politica).filter_by(dominio="ausencias", estado="publicada").one()
    assert cupos.sembrar_politica(db, servicio.politica_dict(pub)) == 0          # idempotente
    assert _pedir(db, b).status == AbsenceStatus.waitlisted
    # Al crear una plaza nueva: una aprobada que aún no contaba (la de ana el martes) cuenta.
    db.query(ReservaDeCupo).filter_by(absence_id=previas[1].id).delete()
    from app.models.ausencias import HuecoDeCupo
    db.query(HuecoDeCupo).filter(HuecoDeCupo.fecha == LUNES + timedelta(days=1)).delete()
    db.commit()
    assert _pedir(db, c, LUNES + timedelta(days=1)).status == AbsenceStatus.waitlisted
    assert db.query(ReservaDeCupo).filter_by(absence_id=previas[1].id, estado="ocupa").count() == 1


def test_ampliar_reevalua_reserva_y_vuelve_a_aprobacion_y_si_se_rechaza_vuelve_atras(ctx):
    from app.models.billing_reports import ApprovalRequest, ApprovalStep, ApprovalWorkflow
    from app.models.ausencias import EventoDeAusencia
    db, admin = ctx, _admin(ctx)
    a, b = _persona(db, "ana", jefe="pm-test-id"), _persona(db, "beto")
    _turnos_y_cuadrante(db, admin, [a, b], dias=5)
    _politica_de_cupo(db, admin, maximo=1)
    x = _pedir(db, a)                                   # sin flujo: decide el responsable
    solicitudes.aplicar_decision(db, x, True, admin, None)
    assert x.status == AbsenceStatus.approved
    # Ahora hay flujo para ausencias: la ampliación vuelve a aprobación.
    wf = ApprovalWorkflow(id=str(uuid.uuid4()), organization_id=ORG, name="WF", entity_type="leave", is_active=True,
                          is_default=True, trigger_conditions="{}")
    db.add(wf)
    db.add(ApprovalStep(id=str(uuid.uuid4()), organization_id=ORG, workflow_id=wf.id, step_order=1, name="Responsable",
                        approver_type="manager", kind="approve", required_approvals=1))
    db.commit()
    hr, pm = db.get(User, "hr-test-id"), db.get(User, "pm-test-id")
    solicitudes.ampliar(db, hr, x, LUNES + timedelta(days=2))
    assert x.status == AbsenceStatus.pending and x.end_date == LUNES + timedelta(days=2)
    assert db.query(ApprovalRequest).filter_by(entity_id=x.id, status="pending").count() == 1
    assert {r["fecha"] for r in cupos.reservas_de(db, x.id)} == {(LUNES + timedelta(days=i)).isoformat() for i in range(3)}
    solicitudes.revisar(db, pm, x, False, "No")         # rechazada: vuelve al fin anterior, sigue aprobada
    assert (x.status, x.end_date) == (AbsenceStatus.approved, LUNES)
    assert [r["fecha"] for r in cupos.reservas_de(db, x.id)] == [LUNES.isoformat()]
    # Beto toma el miércoles; ampliar hasta el miércoles deja la ampliación en espera.
    assert _pedir(db, b, LUNES + timedelta(days=2)).status == AbsenceStatus.pending
    solicitudes.ampliar(db, hr, x, LUNES + timedelta(days=2))
    assert x.status == AbsenceStatus.waitlisted
    tipos = [e.tipo for e in db.query(EventoDeAusencia).filter_by(absence_id=x.id).order_by(EventoDeAusencia.created_at)]
    assert {"ampliada", "ampliacion_rechazada", "en_espera"} <= set(tipos)


# ── La carrera por la última plaza ───────────────────────────────────────────

def test_dos_peticiones_a_la_vez_por_la_ultima_plaza(tmp_path):
    """Base en fichero y dos hilos con su propia sesión: solo uno ocupa."""
    from sqlalchemy.orm import sessionmaker
    from app.models.ausencias import HuecoDeCupo, TipoDeAusencia
    from app.models.ausencias import ReservaDeCupo as R
    motor_ = sa.create_engine(f"sqlite:///{tmp_path / 'carrera.db'}", connect_args={"timeout": 30})
    HuecoDeCupo.__table__.create(motor_)
    Absence.__table__.create(motor_)   # vacía: la siembra de una plaza nueva no encuentra ausencias previas
    with motor_.begin() as c:
        c.exec_driver_sql("CREATE TABLE organizations (id TEXT PRIMARY KEY)")
    # La siembra consulta `absences`, que carga su tipo (`absence_type`, lazy="joined",
    # revisión 167): sin `tipos_de_ausencia` la primera petición fallaba con la
    # escritura a medias y las otras siete acababan en «database is locked».
    TipoDeAusencia.__table__.create(motor_)
    R.__table__.create(motor_)
    Sesion = sessionmaker(bind=motor_)
    cupo = {"clave": "k", "maximo": 1, "si_lleno": [{"tipo": "waitlist"}]}
    huecos = [(LUNES, "t1", "")]
    salida, barrera = {}, threading.Barrier(8)

    def pedir(i):
        s = Sesion()
        barrera.wait()
        try:
            salida[i] = cupos.reservar(s, f"a{i}", cupos.ahora(), [{"cupo": cupo, "huecos": huecos}], ORG)["resultado"]
        finally:
            s.close()

    hilos = [threading.Thread(target=pedir, args=(i,)) for i in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(salida.values()) == ["espera"] * 7 + ["ocupa"]
    with motor_.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM reservas_de_cupo WHERE estado='ocupa'").scalar() == 1
        assert c.exec_driver_sql("SELECT ocupadas FROM huecos_de_cupo").scalar() == 1


# ── Documentos ───────────────────────────────────────────────────────────────

def _baja_con_parte(db, admin, escalar=0):
    tipo = catalogo.tipo_por_clave(db, "sick")
    parte = next(d for d in catalogo.documentos(db) if d.clave == "parte_de_baja")
    catalogo.guardar_tipo(db, admin, {**catalogo.tipo_dict(tipo), "requisitos": [
        {"tipo_de_documento_id": parte.id, "plazo_dias": 3, "plazo_desde": "inicio", "recordar_dias_antes": 1,
         "escalar_dias_despues": escalar, "escalar_a": [{"tipo": "rol", "valor": "hr"}]}]}, tipo.id)
    return parte


def test_documento_exigido_con_plazo_recordatorio_y_escalado(ctx):
    db, admin = ctx, _admin(ctx)
    a = _persona(db, "ana")
    _baja_con_parte(db, admin)
    ausencia = _pedir(db, a, tipo="sick")
    req = db.query(RequisitoDeAusencia).filter_by(absence_id=ausencia.id).one()
    assert req.vence == LUNES + timedelta(days=3) and req.estado == "pendiente"
    assert documentos.pasada(db, LUNES)["recordados"] == 0
    assert documentos.pasada(db, req.vence - timedelta(days=1))["recordados"] == 1
    assert documentos.pasada(db, req.vence - timedelta(days=1))["recordados"] == 0   # una vez
    informe = documentos.pasada(db, req.vence + timedelta(days=1))
    db.refresh(req)
    assert informe["vencidos"] == 1 and informe["escalados"] == 1 and req.escalado_en is not None
    from app.models.enterprise import Notification
    assert db.query(Notification).filter(Notification.user_id == "hr-test-id", Notification.resource_id == ausencia.id).count() == 1


@pytest.fixture
def almacen(monkeypatch):
    from app.services import s3_service
    guardados = {}

    def subir(file_content, file_name, document_id, version_num, content_type="x"):
        clave = f"documents/{document_id}/v{version_num}/{file_name}"
        guardados[clave] = file_content
        return clave, len(file_content)
    monkeypatch.setattr(s3_service.file_storage, "upload_file", subir)
    monkeypatch.setattr(s3_service.file_storage, "generate_presigned_url", lambda k, expiration_hours=None: f"/firmada/{k}")
    return guardados


def test_parte_medico_solo_persona_rrhh_y_acceso_especial_y_todo_auditado(ctx, almacen):
    from app.core.errores import ErrorDeDominio
    from app.models.documents import DocumentAccessLog
    from app.models.enterprise import AuditLog
    from app.services import documents_service
    db, admin = ctx, _admin(ctx)
    a = _persona(db, "ana", jefe="pm-test-id")
    parte = _baja_con_parte(db, admin)
    ausencia = _pedir(db, a, tipo="sick")
    d = documentos.subir(db, a, ausencia, tipo_id=parte.id, nombre="parte.pdf", content_type="application/pdf",
                         contenido=b"%PDF-1.4 parte")
    assert d["especial"] and db.query(RequisitoDeAusencia).filter_by(absence_id=ausencia.id).one().estado == "entregado"
    hr = db.get(User, "hr-test-id")
    pm = db.get(User, "pm-test-id")
    assert documentos.abrir(db, a, ausencia, d["id"], "view", None)["url"].startswith("/firmada/")
    assert documentos.abrir(db, hr, ausencia, d["id"], "download", None)["accion"] == "download"
    for quien in (admin, pm):   # ni el administrador ni el responsable sin acceso especial
        with pytest.raises(ErrorDeDominio):
            documentos.abrir(db, quien, ausencia, d["id"], "view", None)
    from app.models.ausencias import DocumentoDeAusencia
    fila = db.get(DocumentoDeAusencia, d["id"])
    with pytest.raises(ErrorDeDominio):     # tampoco por /documents
        documents_service.check_document_access(fila.documento, admin)
    assert all(x.id != fila.document_id for x in documents_service.query_documents(db, admin)[0].all())
    catalogo.conceder_acceso(db, admin, admin.id)
    assert documentos.abrir(db, admin, ausencia, d["id"], "view", None)["accion"] == "view"
    acciones = [x.action for x in db.query(AuditLog).filter(AuditLog.resource == "absence_document").all()]
    assert acciones.count("ACCESS_DENIED") == 2 and "VIEW" in acciones and "DOWNLOAD" in acciones
    assert db.query(DocumentAccessLog).filter_by(document_id=fila.document_id).count() == 3
    # Sustituir crea la versión 2 y deja la 1 «sustituida».
    d2 = documentos.subir(db, hr, ausencia, tipo_id=parte.id, nombre="parte2.pdf", content_type="application/pdf",
                          contenido=b"%PDF-1.4 v2", sustituye_a=d["id"])
    assert d2["version"] == 2 and db.get(type(fila), d["id"]).estado == "sustituido"


def test_documentos_de_ausencia_entran_en_retencion_y_bloqueo_legal():
    from app.db.bloqueo_legal import TIPOS
    assert TIPOS["absence_documents"].campos == ("id", "absence_id", "user_id")


# ── Migración de tipos ───────────────────────────────────────────────────────

def test_migracion_167_crea_tipos_y_conserva_las_ausencias(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    ruta = Path(__file__).resolve().parents[1] / "alembic/versions/167_ausencias_reglas_turnos_y_documentos.py"
    spec = importlib.util.spec_from_file_location("m167", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    motor_ = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with motor_.begin() as c:
        for t in ("organizations", "approval_workflows", "offices", "documents"):
            c.exec_driver_sql(f"CREATE TABLE {t} (id TEXT PRIMARY KEY)")
        c.exec_driver_sql("CREATE TABLE users (id TEXT PRIMARY KEY, organization_id TEXT)")
        c.exec_driver_sql("CREATE TABLE absences (id TEXT PRIMARY KEY, organization_id TEXT, user_id TEXT, "
                          "type VARCHAR(9) NOT NULL, status VARCHAR(9) NOT NULL, working_days FLOAT, created_at DATETIME)")
        c.exec_driver_sql("INSERT INTO organizations VALUES ('o1'), ('o2')")
        c.exec_driver_sql("INSERT INTO users VALUES ('u1', 'o1'), ('u2', 'o2')")
        c.exec_driver_sql("INSERT INTO absences VALUES ('a1', 'o1', 'u1', 'vacation', 'approved', 5, '2026-01-01'),"
                          " ('a2', NULL, 'u2', 'sick', 'pending', 2, '2026-02-01')")
    for _ in range(2):   # idempotente
        with motor_.connect() as c:
            ctx_ = MigrationContext.configure(c)
            ctx_.autocommit_block = contextlib.nullcontext
            with Operations.context(ctx_):
                m.upgrade()
            c.commit()
    with motor_.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM tipos_de_ausencia").scalar() == 14
        filas = c.exec_driver_sql(
            "SELECT a.id, a.type, a.status, a.amount, a.unit, t.clave, t.organization_id FROM absences a "
            "JOIN tipos_de_ausencia t ON t.id = a.absence_type_id ORDER BY a.id").all()
    assert [tuple(f) for f in filas] == [("a1", "vacation", "approved", 5.0, "dias", "vacation", "o1"),
                                         ("a2", "sick", "pending", 2.0, "dias", "sick", "o2")]


def test_api_antiguo_con_type_sigue_valiendo(client, dev_token):
    r = client.post("/api/v1/absences/my", headers=auth(dev_token),
                    json={"type": "personal", "start_date": "2026-12-09", "end_date": "2026-12-09"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["type"] == "personal" and d["absence_type_id"] and d["working_days"] == 1


# ── Flujo multinivel ─────────────────────────────────────────────────────────

def test_flujo_multinivel_responsable_luego_rrhh_e_informa(ctx, client, admin_token, pm_token, hr_token):
    from tests.test_approvals import add_step, create_workflow
    db = ctx
    wf = create_workflow(client, admin_token, entity_type="leave")
    add_step(client, admin_token, wf["id"], 1, approver_type="manager", approver_role=None)
    add_step(client, admin_token, wf["id"], 2, approver_type="role", approver_role="hr")
    dev = db.get(User, "dev-test-id")
    dev.manager_id = "pm-test-id"
    db.commit()
    a = _pedir(db, dev, LUNES + timedelta(days=1))
    assert a.status == AbsenceStatus.pending
    r = client.post(f"/api/v1/absences/{a.id}/review", headers=auth(pm_token), json={"approved": True})
    assert r.status_code == 200 and r.json()["data"]["status"] == "pending", r.text
    r = client.post(f"/api/v1/absences/{a.id}/review", headers=auth(hr_token), json={"approved": True})
    assert r.json()["data"]["status"] == "approved", r.text
    det = client.get(f"/api/v1/absences/{a.id}/detail", headers=auth(hr_token)).json()["data"]
    assert [x["decision"] for x in det["aprobacion"]["decisiones"]] == ["approved", "approved"]
    assert det["ausencia"]["approved_by"] == db.get(User, "hr-test-id").full_name
    assert [e["tipo"] for e in det["linea_de_tiempo"]][-1] == "aprobada"


# ── Aislamiento por empresa ──────────────────────────────────────────────────

def test_aislamiento_por_empresa(client, dev_token, seed_multitenant, db):
    from app.core.security import create_access_token
    r = client.post("/api/v1/absences/my", headers=auth(dev_token),
                    json={"type": "vacation", "start_date": "2026-12-10", "end_date": "2026-12-10"})
    assert r.status_code == 200, r.text
    aid = r.json()["data"]["id"]
    fuera = create_access_token(subject="outsider-test-id")
    assert client.get(f"/api/v1/absences/{aid}/detail", headers=auth(fuera)).status_code == 404
    tipos_b = client.get("/api/v1/absences/types", headers=auth(fuera)).json()["data"]
    tipos_a = client.get("/api/v1/absences/types", headers=auth(dev_token)).json()["data"]
    assert {t["clave"] for t in tipos_b} == {t["clave"] for t in tipos_a}
    assert not {t["id"] for t in tipos_b} & {t["id"] for t in tipos_a}


def test_cargar_ejemplos_no_aplica_nada(ctx, client, admin_token):
    r = client.post("/api/v1/absences/examples", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert len(d["turnos"]) == 3 and d["flujo_activo"] is False and d["politica"]
    p = client.get(f"/api/v1/policies/{d['politica']}", headers=auth(admin_token)).json()["data"]
    assert p["estado"] == "borrador" and p["reglas"][0]["resultados"][0]["tipo"] == "cupo"
    again = client.post("/api/v1/absences/examples", headers=auth(admin_token)).json()["data"]
    assert again["turnos"] == [] and again["politica"] is None
    json.dumps(d)
