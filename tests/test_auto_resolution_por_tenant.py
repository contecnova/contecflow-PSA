"""La auto-resolución de IA no era por organización: ni su estado ni su alcance.

Auditoría 2026-08 (P3-22, tanda 2 · `service_desk`). Al mirar los 17 puntos de
acceso a base de `endpoints/service_desk/ai_auto_resolution.py` salieron cuatro
cosas, todas de la misma familia: **algo que debería ser por cliente y no lo
era**.

1. **El trabajo procesaba tickets de TODAS las organizaciones.**
   `run_daily_auto_resolution_job` acepta `organization_id` y su propio docstring
   dice que sin él «procesa todos». El endpoint no lo pasaba. Y en el camino
   asíncrono la sesión es un `SessionLocal()` recién creado —sin
   `is_superadmin` ni `organization_id` en `info`—, así que el filtro de tenant
   se salta por diseño. Resultado: **un administrador de un cliente lanzaba la
   auto-resolución sobre los tickets de todos los demás**, resolviéndolos y
   comentándolos. No es una lectura cruzada: es una escritura cruzada.

2. **La configuración era global.** `get/save_auto_resolution_config` usan una
   clave de `AppSetting` sin organización y la escriben con
   `organization_id=NULL`. Cualquier administrador cambiaba los umbrales de
   confianza, el auto-cierre y el tope del trabajo **para todos los clientes**.
   Y el comentario de cabecera del propio servicio ya decía que esa config es
   «por organización»: la intención estaba escrita y el código no la cumplía.
   El contador de feedback sí se arregló en su día —`feedback_stats::{org}`—, así
   que la convención de clave por organización ya existe en este módulo y es la
   que se sigue aquí, en vez de inventar otra.

3. **El estado y el historial del trabajo eran globales.** Mismas claves
   desnudas: un cliente veía el `job_id`, las marcas de tiempo, las estadísticas
   y los errores de los trabajos de otro.

4. **El cerrojo era uno para todos.** `_AUTO_RES_JOB_LOCK = Lock()` a nivel de
   módulo: con el trabajo de un cliente en marcha, el de otro recibía
   `already_running` y no podía ejecutar el suyo.

`AppSetting` ya está diseñado para esto —su docstring dice que las filas con
`organization_id` son «tenant-specific overrides» y que las consultas devuelven
las del tenant *y* las globales para que quien llama prefiera la del tenant—, así
que el arreglo usa el contrato que ya había en vez de inventar otro.
"""
from __future__ import annotations

import pytest


#: Dos identificadores de organizacion. No hacen falta filas de `organizations`:
#: lo que se prueba es el acotado de los `AppSetting` y del cerrojo, y ambos
#: trabajan con el identificador, no con la entidad.
ORG_A = "org-auto-res-a"
ORG_B = "org-auto-res-b"


# ── 2. La configuración es por organización ─────────────────────────────────

def test_EL_HALLAZGO_la_configuracion_no_se_comparte_entre_organizaciones(db):
    """Lo que ajusta un cliente no puede cambiarle los umbrales a otro."""
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a, org_b = ORG_A, ORG_B

    svc.save_auto_resolution_config(db, {"threshold_auto": 0.95}, organization_id=org_a)
    db.commit()

    cfg_a = svc.get_auto_resolution_config(db, organization_id=org_a)
    cfg_b = svc.get_auto_resolution_config(db, organization_id=org_b)

    assert cfg_a["threshold_auto"] == pytest.approx(0.95)
    assert cfg_b["threshold_auto"] != pytest.approx(0.95), (
        "la organización B heredó el umbral que puso A: la configuración es global")


def test_la_configuracion_de_un_tenant_respalda_en_la_global(db):
    """Sin fila propia se usa la global, que es el contrato de `AppSetting`."""
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a = ORG_A

    svc.save_auto_resolution_config(db, {"threshold_auto": 0.80}, organization_id=None)
    db.commit()

    cfg = svc.get_auto_resolution_config(db, organization_id=org_a)
    assert cfg["threshold_auto"] == pytest.approx(0.80)

    # Y en cuanto el tenant pone la suya, gana sobre la global.
    svc.save_auto_resolution_config(db, {"threshold_auto": 0.90}, organization_id=org_a)
    db.commit()
    assert svc.get_auto_resolution_config(db, organization_id=org_a)["threshold_auto"] == pytest.approx(0.90)
    assert svc.get_auto_resolution_config(db, organization_id=None)["threshold_auto"] == pytest.approx(0.80)


# ── 3. El estado y el historial son por organización ───────────────────────

def test_EL_HALLAZGO_el_estado_del_trabajo_no_se_comparte(db):
    """Un cliente no puede ver el `job_id` ni los errores del trabajo de otro."""
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a, org_b = ORG_A, ORG_B

    svc.guardar_estado_del_trabajo(
        db, {"running": True, "status": "running", "last_job_id": "trabajo-de-A"},
        organization_id=org_a)
    db.commit()

    assert svc.estado_del_trabajo(db, organization_id=org_a)["last_job_id"] == "trabajo-de-A"
    estado_b = svc.estado_del_trabajo(db, organization_id=org_b)
    assert estado_b["last_job_id"] != "trabajo-de-A", (
        "la organización B ve el trabajo de A: el estado es global")
    assert estado_b["status"] == "never_run"
    assert estado_b["running"] is False


def test_EL_HALLAZGO_el_historial_del_trabajo_no_se_comparte(db):
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a, org_b = ORG_A, ORG_B

    svc.anotar_en_el_historial(
        db, {"status": "completed", "stats": {"processed": 7}}, organization_id=org_a)
    db.commit()

    assert len(svc.historial_del_trabajo(db, organization_id=org_a)) == 1
    assert svc.historial_del_trabajo(db, organization_id=org_b) == [], (
        "la organización B ve el historial de A")


def test_el_historial_esta_acotado_y_no_crece_sin_freno(db):
    """El historial se recorta: es un `AppSetting`, no una tabla de eventos."""
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a = ORG_A
    for i in range(svc.MAX_HISTORIAL_DEL_TRABAJO + 5):
        svc.anotar_en_el_historial(db, {"status": "completed", "n": i}, organization_id=org_a)
    db.commit()

    historial = svc.historial_del_trabajo(db, organization_id=org_a)
    assert len(historial) == svc.MAX_HISTORIAL_DEL_TRABAJO
    # Se conservan los más recientes.
    assert historial[0]["n"] == svc.MAX_HISTORIAL_DEL_TRABAJO + 4


# ── 4. El cerrojo es por organización ───────────────────────────────────────

def test_EL_HALLAZGO_el_trabajo_de_una_organizacion_no_bloquea_a_otra(db):
    """Con el trabajo de A en marcha, B tiene que poder lanzar el suyo.

    El cerrojo estaba a nivel de módulo, uno para todo el proceso.
    """
    from app.services.service_desk import ai_auto_resolution_service as svc

    org_a, org_b = ORG_A, ORG_B

    cerrojo_a = svc.cerrojo_del_trabajo(org_a)
    assert cerrojo_a.acquire(blocking=False)
    try:
        assert svc.cerrojo_del_trabajo(org_b).acquire(blocking=False), (
            "el trabajo de A bloquea a B: el cerrojo es uno para todo el proceso")
        svc.cerrojo_del_trabajo(org_b).release()
        # Y el de A sigue tomado: dos llamadas devuelven el MISMO cerrojo.
        assert not svc.cerrojo_del_trabajo(org_a).acquire(blocking=False)
    finally:
        cerrojo_a.release()


# ── 1. El alcance del trabajo ───────────────────────────────────────────────

def test_EL_HALLAZGO_el_endpoint_acota_el_trabajo_a_su_organizacion(
    client, admin_token, db, monkeypatch
):
    """El endpoint tiene que pasar `organization_id` al trabajo.

    Es el defecto más serio de los cuatro: sin él el trabajo recorre y
    **auto-resuelve** los tickets de todas las organizaciones. Se comprueba
    interceptando la función del trabajo y mirando con qué la llaman, que es
    exactamente lo que estaba mal.
    """
    from tests.conftest import auth
    from app.models.user import User
    import app.api.v1.endpoints.service_desk.ai_auto_resolution as ep

    recibido: dict = {}

    def trabajo_falso(session, *, limit=None, organization_id=None):
        recibido["limit"] = limit
        recibido["organization_id"] = organization_id
        return {"processed": 0, "auto_resolved": 0, "suggested": 0, "failed": 0}

    monkeypatch.setattr(ep, "run_daily_auto_resolution_job", trabajo_falso)

    r = client.post(
        "/api/v1/sd/auto-resolution/run-job?run_async=false&limit=5",
        headers=auth(admin_token))
    assert r.status_code == 200, r.text

    org_del_admin = db.query(User.organization_id).filter(User.username == "admin").scalar()
    assert recibido["limit"] == 5
    assert recibido["organization_id"] == org_del_admin, (
        "el endpoint no acotó el trabajo a la organización de quien lo lanza: "
        "procesaría tickets de todos los clientes")
