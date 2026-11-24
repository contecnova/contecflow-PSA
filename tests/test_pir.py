"""PIR común a cambios y proyectos (migración 206, 23-11-2026, docs/PIR.md).

Lo crítico: programación automática (cambio implantado/cerrado, puesta en marcha
y cierre del proyecto), obligatoriedad (por defecto y por plantilla),
segregación al aprobar, efecto de una PIR «fallo» en el catálogo de cambios
estándar (y su vuelta atrás al reabrir), acciones → tareas, lecciones,
aislamiento por empresa, trabajo de fondo de vencidas, bloqueo legal, la
migración y las guardas de la API.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import auth

REPO = Path(__file__).resolve().parents[1]
BASE = "/api/v1/pir"


# ── Ayudas ───────────────────────────────────────────────────────────────────

def _usuario(db, uid):
    from app.models.user import User
    u = db.get(User, uid)
    if u.organization_id is None:
        u.organization_id = "1"
        db.commit()
    return u


def _cambio(db, tipo="normal", estado="in_progress", org="1", **extra):
    from app.models.service_desk import ITSMChangeRequest
    import uuid
    ch = ITSMChangeRequest(number=f"CHG-{uuid.uuid4().hex[:6]}", title="Cambio de prueba", description="d",
                           change_type=tipo, status=estado, organization_id=org, owner_id="pm-test-id",
                           requester_id="pm-test-id", **extra)
    db.add(ch)
    db.commit()
    return ch


def _proyecto(db, org="1", tipo="development"):
    from app.models.project import Project
    import uuid
    p = Project(code=f"PRJ-{uuid.uuid4().hex[:5]}", name="Proyecto PIR", project_type=tipo, organization_id=org,
                pm_id="pm-test-id")
    db.add(p)
    db.commit()
    return p


def _config(db, org="1", **campos):
    from app.models.pir import PirConfiguracion
    c = db.query(PirConfiguracion).filter(PirConfiguracion.organization_id == org).first()
    if c is None:
        from app.services.pir.plantillas import config
        c = config(db, org)
        db.add(c)
    for k, v in campos.items():
        setattr(c, k, v)
    db.commit()
    return c


def _pirs(db, **filtro):
    from app.models.pir import PirRevision
    q = db.query(PirRevision)
    for k, v in filtro.items():
        q = q.filter(getattr(PirRevision, k) == v)
    return q.all()


def _rellenar_y_enviar(db, usuario, pir, resultado="exito"):
    from app.services.pir import servicio
    criterios = [{**c, "resultado": "si"} for c in servicio._json(pir.criterios, [])]
    servicio.guardar(db, usuario, pir.id, {"criterios": criterios, "resultado": resultado,
                                           "objetivos_cumplidos": "si", "hubo_marcha_atras": False})
    return servicio.enviar(db, usuario, pir.id)


# ── Programación automática y obligatoriedad ─────────────────────────────────

def test_cambio_normal_implantado_programa_pir_obligatoria_hoy_mas_n(db):
    from app.services.pir.programacion import al_cambiar_estado_de_cambio
    _config(db, dias_cambio=10)
    ch = _cambio(db, "normal")
    al_cambiar_estado_de_cambio(db, ch, "implemented")
    db.commit()
    [pir] = _pirs(db, change_id=ch.id)
    assert pir.obligatorio and pir.motivo == "implantacion" and pir.estado == "programado"
    assert pir.fecha_prevista == date.today() + timedelta(days=10)
    assert pir.responsable_id == "pm-test-id", "el dueño del cambio"
    assert pir.criterios and pir.preguntas, "cuestionario de fábrica (ITIL 4)"


def test_repetir_la_transicion_no_duplica(db):
    from app.services.pir.programacion import al_cambiar_estado_de_cambio
    ch = _cambio(db, "emergency")
    al_cambiar_estado_de_cambio(db, ch, "implemented")
    al_cambiar_estado_de_cambio(db, ch, "closed_success")
    db.commit()
    assert len(_pirs(db, change_id=ch.id)) == 1


def test_estandar_por_defecto_no_programa_pir(db):
    from app.services.pir.programacion import al_cambiar_estado_de_cambio
    ch = _cambio(db, "standard")
    al_cambiar_estado_de_cambio(db, ch, "implemented")
    db.commit()
    assert _pirs(db, change_id=ch.id) == []


def test_momento_cierre_solo_programa_al_cerrar(db):
    from app.services.pir.programacion import al_cambiar_estado_de_cambio
    _config(db, momento_cambio="cierre")
    ch = _cambio(db, "normal")
    al_cambiar_estado_de_cambio(db, ch, "implemented")
    db.commit()
    assert _pirs(db, change_id=ch.id) == []
    al_cambiar_estado_de_cambio(db, ch, "closed_failed")
    db.commit()
    assert [p.motivo for p in _pirs(db, change_id=ch.id)] == ["cierre"]


def test_la_plantilla_del_tipo_manda_sobre_la_configuracion(db):
    from app.models.pir import PirPlantilla
    from app.services.pir.programacion import al_cambiar_estado_de_cambio
    db.add(PirPlantilla(organization_id="1", nombre="Estándar", ambito="change", tipo="standard", obligatorio=True,
                        dias=3, criterios='[{"clave": "ok", "texto": "Funciona"}]', activo=True))
    db.commit()
    ch = _cambio(db, "standard")
    al_cambiar_estado_de_cambio(db, ch, "implemented")
    db.commit()
    [pir] = _pirs(db, change_id=ch.id)
    assert pir.obligatorio and pir.fecha_prevista == date.today() + timedelta(days=3)
    assert '"ok"' in pir.criterios


def test_transicion_por_la_api_programa_la_pir(client, admin_token, db):
    ch = _cambio(db, "normal", estado="in_progress")
    r = client.patch(f"/api/v1/sd/changes/{ch.id}", headers=auth(admin_token), json={"status": "implemented"})
    assert r.status_code == 200, r.text
    assert len(_pirs(db, change_id=ch.id)) == 1


def test_proyecto_go_live_y_cierre_segun_obligatoriedad(db):
    from app.models.financial import ProjectMilestone
    from app.services.pir.programacion import al_cerrar_proyecto, al_completar_hito
    p = _proyecto(db)
    hito = ProjectMilestone(project_id=p.id, organization_id="1", name="Go-live", is_go_live=True)
    db.add(hito)
    db.commit()
    al_completar_hito(db, hito)
    db.commit()
    assert _pirs(db, project_id=p.id) == [], "por defecto opcional en proyectos"
    _config(db, obligatorio_proyecto=True)
    al_completar_hito(db, hito)
    al_cerrar_proyecto(db, p)
    db.commit()
    assert sorted(x.motivo for x in _pirs(db, project_id=p.id)) == ["cierre", "go_live"]


def test_cerrar_proyecto_por_la_api_programa_la_pir(client, admin_token, db):
    _config(db, obligatorio_proyecto=True)
    p = _proyecto(db)
    r = client.patch(f"/api/v1/projects/{p.id}", headers=auth(admin_token), json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert [x.motivo for x in _pirs(db, project_id=p.id)] == ["cierre"]


# ── Flujo y segregación ──────────────────────────────────────────────────────

def test_no_se_envia_incompleta(db):
    from app.core.errores import ErrorDeDominio
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", _cambio(db).id)
    db.commit()
    with pytest.raises(ErrorDeDominio) as e:
        servicio.enviar(db, admin, pir.id)
    assert e.value.status_code == 422


def test_quien_gestiono_el_cambio_no_aprueba_su_pir(db):
    from app.core.errores import ErrorDeDominio
    from app.services.pir import servicio
    pm = _usuario(db, "pm-test-id")
    admin = _usuario(db, "admin-test-id")
    ch = _cambio(db)   # dueño: el PM
    pir = servicio.crear(db, admin, "change", ch.id, responsable_id="admin-test-id")
    db.commit()
    _rellenar_y_enviar(db, admin, pir)
    with pytest.raises(ErrorDeDominio) as e:
        servicio.aprobar(db, pm, pir.id)
    assert e.value.status_code == 403
    with pytest.raises(ErrorDeDominio):
        servicio.aprobar(db, admin, pir.id)   # responsable de la PIR: tampoco


def test_sin_segregacion_el_implicado_si_aprueba(db):
    from app.services.pir import servicio
    _config(db, segregacion=False)
    pm = _usuario(db, "pm-test-id")
    pir = servicio.crear(db, pm, "change", _cambio(db).id)
    db.commit()
    _rellenar_y_enviar(db, pm, pir)
    assert servicio.aprobar(db, pm, pir.id)["estado"] == "aprobado"


def test_obligatoria_no_se_descarta_y_opcional_si(db):
    from app.core.errores import ErrorDeDominio
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    obligatoria = servicio.crear(db, admin, "change", _cambio(db, "normal").id)
    opcional = servicio.crear(db, admin, "change", _cambio(db, "standard").id)
    db.commit()
    with pytest.raises(ErrorDeDominio):
        servicio.descartar(db, admin, obligatoria.id, "no aplica")
    assert servicio.descartar(db, admin, opcional.id, "no aplica")["estado"] == "descartado"


def test_auditoria_de_crear_enviar_aprobar_reabrir_borrar(db):
    from app.models.enterprise import AuditLog
    from app.services.pir import servicio
    _config(db, segregacion=False)
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", _cambio(db).id)
    db.commit()
    _rellenar_y_enviar(db, admin, pir)
    servicio.aprobar(db, admin, pir.id)
    servicio.reabrir(db, admin, pir.id, "faltaba un KPI")
    servicio.borrar(db, admin, pir.id)
    acciones = {a.action for a in db.query(AuditLog).filter(AuditLog.resource == "pir").all()}
    assert {"CREATE", "SUBMIT", "APPROVE", "REOPEN", "DELETE"} <= acciones


# ── Catálogo de cambios estándar ─────────────────────────────────────────────

def _modelo_estandar(db, **extra):
    from app.models.service_desk import StandardChangeModel
    m = StandardChangeModel(organization_id="1", name="Reinicio", procedure="p", max_risk="medium", status="approved",
                            is_active=True, proposed_by="pm-test-id",
                            next_review_at=datetime.now(timezone.utc) + timedelta(days=30), **extra)
    db.add(m)
    db.commit()
    return m


def test_pir_fallo_cuenta_como_fallo_del_modelo_y_lo_suspende(db, monkeypatch):
    from app.models.service_desk import StandardChangeModel
    from app.services.pir import servicio
    from app.services.service_desk import cambios_estandar_service as cat
    monkeypatch.setattr(cat, "_ajuste_int", lambda db, clave, org: {"SD_STANDARD_CHANGE_MIN_CLOSURES": 2,
                                                                    "SD_STANDARD_CHANGE_MAX_FAILURE_PCT": 40}[clave])
    _config(db, segregacion=False)
    m = _modelo_estandar(db, success_count=2)
    ch = _cambio(db, "standard", estado="closed_success", standard_model_id=m.id)
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", ch.id)
    db.commit()
    _rellenar_y_enviar(db, admin, pir, resultado="fallo")
    servicio.aprobar(db, admin, pir.id)
    m = db.get(StandardChangeModel, m.id)
    assert (m.success_count, m.failure_count) == (1, 1), "el éxito del cierre pasa a ser fallo"
    assert m.status == "suspended", "50 % > 40 % con 2 cierres"
    servicio.reabrir(db, admin, pir.id, "mal evaluada")
    m = db.get(StandardChangeModel, m.id)
    assert (m.success_count, m.failure_count) == (2, 0), "reabrir deshace el efecto"


def test_pir_fallo_antes_del_cierre_no_cuenta_dos_veces(db):
    from app.models.service_desk import StandardChangeModel
    from app.services.pir import servicio
    from app.services.service_desk import cambios_estandar_service as cat
    _config(db, segregacion=False)
    m = _modelo_estandar(db)
    ch = _cambio(db, "standard", estado="implemented", standard_model_id=m.id)
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", ch.id)
    db.commit()
    _rellenar_y_enviar(db, admin, pir, resultado="fallo")
    servicio.aprobar(db, admin, pir.id)
    cat.anotar_cierre(db, ch, exito=True, usuario=admin)
    m = db.get(StandardChangeModel, m.id)
    assert (m.success_count, m.failure_count) == (0, 1)


# ── Acciones, lecciones, beneficios ──────────────────────────────────────────

def test_accion_de_mejora_nace_como_tarea_del_proyecto(db):
    from app.models.task import Task
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    p = _proyecto(db)
    pir = servicio.crear(db, admin, "project", p.id)
    db.commit()
    r = servicio.crear_accion(db, admin, pir.id, {"descripcion": "Automatizar el despliegue",
                                                  "responsable_id": "dev-test-id", "fecha_limite": "2026-12-31"})
    assert not r["sin_tarea"]
    t = db.get(Task, r["accion"]["task_id"])
    assert t.project_id == p.id and t.assignee_id == "dev-test-id" and t.due_date == date(2026, 12, 31)
    assert pir.codigo in t.title


def test_accion_de_cambio_sin_proyecto_va_al_de_mejora_continua_o_sin_tarea(db):
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", _cambio(db).id)
    db.commit()
    assert servicio.crear_accion(db, admin, pir.id, {"descripcion": "Revisar el runbook"})["sin_tarea"]
    mejora = _proyecto(db)
    _config(db, proyecto_acciones_id=mejora.id)
    r = servicio.crear_accion(db, admin, pir.id, {"descripcion": "Revisar el runbook otra vez"})
    assert not r["sin_tarea"] and r["accion"]["project_id"] == mejora.id


def test_leccion_aprendida_va_al_modulo_de_lecciones(db):
    from app.models.lecciones import Leccion
    from app.services import lecciones
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", _cambio(db).id)
    db.commit()
    cat = lecciones.categorias(db, "1")[0]
    servicio.crear_leccion(db, admin, pir.id, {"titulo": "Probar en preproducción", "categoria": cat,
                                               "que_paso": "Faltó probar", "recomendacion": "Probar antes"})
    [l] = db.query(Leccion).filter(Leccion.origen_tipo == "pir", Leccion.origen_id == pir.id).all()
    assert l.origen_ref == pir.codigo
    assert servicio.detalle(db, admin, pir.id)["lecciones"][0]["codigo"] == l.codigo


def test_beneficios_del_proyecto_se_copian_y_se_actualizan(db):
    from app.models.clientes_internos import ProjectBenefit
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    p = _proyecto(db)
    b = ProjectBenefit(organization_id="1", project_id=p.id, name="Ahorro", target=100.0)
    db.add(b)
    db.commit()
    pir = servicio.crear(db, admin, "project", p.id)
    db.commit()
    d = servicio.detalle(db, admin, pir.id)
    assert d["beneficios"][0]["previsto"] == 100.0
    servicio.guardar(db, admin, pir.id, {"beneficios": [{"benefit_id": b.id, "conseguido": 80, "actualizar": True}]})
    assert db.get(ProjectBenefit, b.id).actual == 80


# ── Aislamiento, CAB, vencidas, GRC ──────────────────────────────────────────

def test_otra_empresa_no_ve_la_pir(client, admin_token, db):
    from app.services.pir import servicio
    ch = _cambio(db, org="2")
    pir = servicio.crear(db, None, "change", ch.id)
    db.commit()
    assert client.get(f"{BASE}/{pir.id}", headers=auth(admin_token)).status_code == 404
    ids = [x["id"] for x in client.get(BASE, headers=auth(admin_token)).json()["data"]["items"]]
    assert pir.id not in ids


def test_empleado_solo_ve_las_suyas(db):
    from app.services.pir import servicio
    admin = _usuario(db, "admin-test-id")
    dev = _usuario(db, "dev-test-id")
    ajena = servicio.crear(db, admin, "change", _cambio(db).id)
    suya = servicio.crear(db, admin, "change", _cambio(db).id, responsable_id="dev-test-id")
    db.commit()
    ids = {x["id"] for x in servicio.listar(db, dev)["items"]}
    assert suya.id in ids and ajena.id not in ids


def test_cab_cerrado_con_pir_pendiente_no_cuenta_como_cerrado_del_todo(db):
    from app.services.pir import informes, servicio
    admin = _usuario(db, "admin-test-id")
    ch = _cambio(db, estado="closed_success")
    servicio.crear(db, admin, "change", ch.id)
    db.commit()
    assert informes.cerrado_del_todo(db, ch) is False
    v = informes.vista_del_cab(db, admin)
    assert v["cerrados_con_pir_pendiente"] >= 1 and v["pir_pendientes"] >= 1


def test_trabajo_de_fondo_avisa_una_vez_de_las_vencidas(db):
    from app.services.pir import programacion, servicio
    admin = _usuario(db, "admin-test-id")
    pir = servicio.crear(db, admin, "change", _cambio(db).id, fecha_prevista=date.today() - timedelta(days=1))
    db.commit()
    assert programacion.revisar_vencidas(db, "1")["pir_vencidas_avisadas"] == 1
    db.commit()
    assert programacion.revisar_vencidas(db, "1")["pir_vencidas_avisadas"] == 0
    assert servicio.detalle(db, admin, pir.id)["vencida"] is True
    assert {"pir-vencidas"} <= set(__import__("app.worker", fromlist=["x"]).celery_app.conf.beat_schedule)


def test_bloqueo_legal_tiene_el_tipo_pir():
    from app.db.bloqueo_legal import TIPOS
    tipo = TIPOS["pir_reviews"]
    assert tipo.modelo().__tablename__ == "pir_revisiones" and "change_id" in tipo.campos


def test_capacidades_y_guardas(client, admin_token, sub_token):
    from app.core.capacidades import CAPACIDADES
    assert {"pir.ver", "pir.gestionar", "pir.aprobar", "pir.administrar"} <= set(CAPACIDADES)
    assert client.get(f"{BASE}/mias", headers=auth(admin_token)).status_code == 200
    assert client.get(f"{BASE}/mias", headers=auth(sub_token)).status_code == 403
    assert client.get(f"{BASE}/config", headers=auth(admin_token)).status_code == 200


def test_la_ficha_del_cambio_mantiene_los_campos_pir_compatibles(client, admin_token, db):
    ch = _cambio(db)
    d = client.get(f"/api/v1/sd/changes/{ch.id}", headers=auth(admin_token)).json()["data"]
    assert {"pir_success", "pir_date", "pir_notes", "pir_obligatoria_pendiente"} <= set(d)


# ── Migración ────────────────────────────────────────────────────────────────

def test_la_migracion_206_declara_lo_mismo_que_los_modelos():
    spec = importlib.util.spec_from_file_location("m206", REPO / "alembic" / "versions" / "206_pir.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "206_pir" and m.down_revision == "205_portal_usuarios"
    from app.models.pir import PirAccion, PirConfiguracion, PirPlantilla, PirRevision
    definicion = m._definicion()
    for modelo in (PirRevision, PirAccion, PirPlantilla, PirConfiguracion):
        cols = {c.name for c in definicion[modelo.__tablename__] if hasattr(c, "name")}
        assert cols == {c.name for c in modelo.__table__.columns}, modelo.__tablename__
    from app.models.service_desk import ITSMChangeRequest
    assert not {"pir_notes", "pir_success", "pir_date"} & {c.name for c in ITSMChangeRequest.__table__.columns}
