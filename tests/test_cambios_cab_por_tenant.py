"""El estado `in_approval` no existe, y por eso el scoring del CAB no corría.

Auditoría 2026-08 (P3-22). Salió de mover a servicio los dos puntos de acceso de
`change_impact.py`, y lo que había detrás es más grande que el movimiento.

## Dos enums llamados `ChangeStatus`

* `app/models/service_desk/_enums.py` — draft, submitted, **cab_review**,
  approved, scheduled, in_progress, implemented, post_review, closed_success,
  closed_failed, cancelled. Es el que usa la **columna**.
* `app/services/service_desk/change_management_service.py` — draft, submitted,
  **in_approval**, approved, ... Un enum local, y **no lo usaba nadie**: las
  funciones de su propio módulo importan el del modelo. Era el único sitio del
  repositorio donde `in_approval` existía.

Tres consumidores importaban el del modelo y escribían
`ChangeStatus.in_approval`. Medido:

1. **`POST /batch-score`**: la referencia era incondicional, así que respondía
   **500 siempre** —`AttributeError: type object 'ChangeStatus' has no attribute
   'in_approval'`— y **nunca puntuó un solo cambio**.
2. **`GET /cab-dashboard`**: el valor por defecto del parámetro era
   `"submitted,in_approval"`, e `in_approval` se caía del filtro por no estar en
   el enum. El panel listaba **sólo `submitted`** y no mostraba **ninguno** de
   los cambios que están de verdad en revisión del CAB, que es `cab_review`. Y
   con un estado inexistente en la petición se llegaba a la rama de respaldo y
   devolvía 500.
3. **La tarea de Celery `change_impact_batch_score`**, cada 10 minutos: mismo
   `AttributeError`, atrapado por su `except` exterior — una línea de log y
   nada. **La pasada programada llevaba fallando en cada tic**, así que
   `auto_risk_score` sólo se rellenaba en la transición a `submitted` y la
   auto-aprobación de cambios estándar de bajo riesgo no corría nunca.

## Corrección de mi primer diagnóstico

Escribí que `/batch-score` «auto-aprobaba las solicitudes de cambio de todos los
clientes», porque su consulta no filtraba por organización y el bucle escribe.
**El filtro faltaba de verdad, pero esa escritura cruzada nunca fue
alcanzable**: el endpoint reventaba con el `AttributeError` antes de llegar a la
consulta. Era un defecto **latente**, no un incidente. La guarda hace falta
igual —ahora que el endpoint funciona, sin ella sí lo sería— pero decirlo de la
otra manera sería exagerar lo que pasaba.

## Y lo que sí era un problema de escala

Sin tope. Cada cambio cuesta un `score_and_persist` —que consulta elementos de
configuración, sus dependencias, los tickets abiertos sobre ellos y el historial
de incidencias— **más un `commit`**. La tarea de Celery sí tenía `limit(50)`; el
endpoint no tenía ninguno.
"""
from __future__ import annotations

import pytest

ORG = "org-cab-mia"
OTRA = "org-cab-ajena"


class _Usuario:
    def __init__(self, organization_id, superadmin=False):
        self.id = "u-cab"
        self.organization_id = organization_id
        self.is_superadmin = superadmin


def _cambio(db, org, i, *, score=None, estado="submitted"):
    from app.models.service_desk import ITSMChangeRequest

    fila = ITSMChangeRequest(
        id=f"chg-{org}-{i}", number=f"CHG-{org[-3:]}{i}",
        title=f"Cambio {i} de {org}", description="x",
        status=estado, auto_risk_score=score, organization_id=org,
    )
    db.add(fila)
    return fila


@pytest.fixture()
def cambios(db):
    """Dos cambios pendientes sin puntuar en cada organización."""
    for org in (ORG, OTRA):
        for i in range(2):
            _cambio(db, org, i)
    db.commit()


# -- El panel ----------------------------------------------------------------

def test_EL_HALLAZGO_el_panel_no_lista_los_cambios_de_otro_cliente(db, cambios):
    from app.services.service_desk import change_impact_service as svc

    datos = svc.panel_del_cab(
        db, _Usuario(ORG), estados=svc.ESTADOS_PENDIENTES_DE_CAB,
        min_risk_score=0, page=1, page_size=25)

    assert datos["total"] == 2, (
        f"el panel lista cambios de otras organizaciones: {datos['total']}")
    assert all(i["id"].startswith(f"chg-{ORG}") for i in datos["items"])


def test_EL_ESCENARIO_la_consulta_de_antes_alcanzaba_las_dos(db, cambios):
    from app.models.service_desk import ITSMChangeRequest

    filas = db.query(ITSMChangeRequest).all()
    assert {f.organization_id for f in filas} == {ORG, OTRA}, (
        "la consulta sin ámbito ya no alcanza las dos organizaciones; "
        "revisar si estos tests siguen midiendo lo que dicen")


def test_el_panel_cuenta_los_que_no_tienen_score(db):
    from app.services.service_desk import change_impact_service as svc

    _cambio(db, ORG, 0, score=None)
    _cambio(db, ORG, 1, score=55)
    db.commit()

    datos = svc.panel_del_cab(
        db, _Usuario(ORG), estados=svc.ESTADOS_PENDIENTES_DE_CAB,
        min_risk_score=0, page=1, page_size=25)
    assert datos["total"] == 2
    assert datos["unscored"] == 1


def test_el_filtro_de_riesgo_minimo_deja_pasar_los_sin_puntuar(db):
    """Comportamiento del original, conservado: un cambio sin score todavía no
    se puede descartar por riesgo, así que pasa el filtro."""
    from app.services.service_desk import change_impact_service as svc

    _cambio(db, ORG, 0, score=None)
    _cambio(db, ORG, 1, score=10)
    _cambio(db, ORG, 2, score=80)
    db.commit()

    datos = svc.panel_del_cab(
        db, _Usuario(ORG), estados=svc.ESTADOS_PENDIENTES_DE_CAB,
        min_risk_score=50, page=1, page_size=25)
    ids = {i["id"] for i in datos["items"]}
    assert ids == {f"chg-{ORG}-0", f"chg-{ORG}-2"}


def test_un_sujeto_sin_organizacion_no_ve_el_panel_de_todos(db, cambios):
    from app.services.service_desk import change_impact_service as svc

    datos = svc.panel_del_cab(
        db, _Usuario(None), estados=svc.ESTADOS_PENDIENTES_DE_CAB,
        min_risk_score=0, page=1, page_size=25)
    assert datos["total"] == 0


# -- La pasada de scoring: aquí se escribe ----------------------------------

def test_la_pasada_no_toca_los_cambios_de_otro_cliente(db, cambios):
    """La guarda que faltaba. Era latente, no un incidente: ver el docstring.

    Importa ahora precisamente porque el endpoint ya funciona.
    """
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk import change_impact_service as svc

    datos = svc.puntuar_cambios_pendientes(db, _Usuario(ORG))

    assert datos["total_pending"] == 2, (
        f"la pasada ha encontrado {datos['total_pending']} cambios pendientes "
        "en vez de 2: está alcanzando los de otras organizaciones")

    # Los del otro cliente siguen sin puntuar y sin aprobar.
    ajenos = (
        db.query(ITSMChangeRequest)
        .filter(ITSMChangeRequest.organization_id == OTRA)
        .all()
    )
    assert all(c.auto_risk_score is None for c in ajenos), (
        "se han puntuado cambios de otro cliente")
    assert all(c.status == "submitted" for c in ajenos), (
        "se ha cambiado el estado de una solicitud de otro cliente")


def test_la_pasada_puntua_los_propios(db, cambios):
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk import change_impact_service as svc

    datos = svc.puntuar_cambios_pendientes(db, _Usuario(ORG))
    assert datos["ok"] is True
    assert datos["scored"] + datos["errors"] == 2

    mios = (
        db.query(ITSMChangeRequest)
        .filter(ITSMChangeRequest.organization_id == ORG)
        .all()
    )
    if datos["errors"] == 0:
        assert all(c.auto_risk_score is not None for c in mios)


def test_el_tope_acota_la_pasada_y_lo_dice(db, monkeypatch):
    from app.services.service_desk import change_impact_service as svc

    for i in range(5):
        _cambio(db, ORG, i)
    db.commit()

    # El tope se lee en el submodulo del CAB (auditoria 2026-11, #24).
    monkeypatch.setattr(svc.cab, "TOPE_DE_CAMBIOS_POR_PASADA", 2)
    datos = svc.puntuar_cambios_pendientes(db, _Usuario(ORG))

    assert datos["total_pending"] == 5, (
        "el total de pendientes debe seguir siendo el total, no lo analizado")
    assert datos["scored"] + datos["errors"] == 2
    assert datos["truncated"] is True


def test_sin_truncamiento_no_se_marca(db, cambios):
    from app.services.service_desk import change_impact_service as svc

    datos = svc.puntuar_cambios_pendientes(db, _Usuario(ORG))
    assert datos["truncated"] is False


def test_el_tope_se_configura_por_entorno_y_no_esta_en_duro():
    from app.services.service_desk import change_impact_service as svc

    assert isinstance(svc.TOPE_DE_CAMBIOS_POR_PASADA, int)
    assert svc.TOPE_DE_CAMBIOS_POR_PASADA > 0

    entorno = open(".env.example", encoding="utf-8").read()
    assert "CHANGE_BATCH_SCORE_MAX" in entorno, (
        "la perilla no está declarada en .env.example: el código la lee y la "
        "configuración no la ofrece")


def test_EL_HALLAZGO_los_estados_pendientes_existen_en_el_enum_del_modelo():
    """El defecto de verdad: `in_approval` no es un valor de esa columna.

    La constante sale del enum, así que un renombrado revienta aquí y no en un
    `AttributeError` a mitad de una petición.
    """
    from app.models.service_desk import ChangeStatus
    from app.services.service_desk import change_impact_service as svc

    valores = {m.value for m in ChangeStatus}
    assert "in_approval" not in valores, (
        "`in_approval` ha aparecido en el enum del modelo: revisar si estos "
        "tests siguen midiendo lo que dicen")
    assert svc.ESTADOS_PENDIENTES_DE_CAB == [
        ChangeStatus.submitted.value, ChangeStatus.cab_review.value]
    assert set(svc.ESTADOS_PENDIENTES_DE_CAB) <= valores


def test_EL_ESTRUCTURAL_no_queda_un_segundo_enum_ChangeStatus():
    """Dos enums con el mismo nombre y valores distintos es una trampa.

    Se importa el que no toca y el intérprete no se queja hasta que se accede
    al miembro que falta — que es exactamente lo que pasó tres veces.
    """
    from app.services.service_desk import change_management_service as cms

    assert not hasattr(cms, "ChangeStatus"), (
        "ha vuelto el segundo enum ChangeStatus en change_management_service")


def test_EL_ESTRUCTURAL_ningun_sitio_usa_un_miembro_que_el_enum_no_tiene():
    """El guardián de la clase entera de defecto, por AST.

    Recorre `app/` buscando `ChangeStatus.<algo>` y comprueba que `<algo>` es un
    miembro real del enum del modelo. Habría cazado los tres sitios.
    """
    import ast
    import io as _io
    from pathlib import Path

    from app.models.service_desk import ChangeStatus

    miembros = {m.name for m in ChangeStatus}
    culpables = []
    for ruta in Path("app").rglob("*.py"):
        if "__pycache__" in ruta.parts:
            continue
        try:
            arbol = ast.parse(_io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Name)
                    and nodo.value.id == "ChangeStatus"
                    and nodo.attr not in miembros
                    and not nodo.attr.startswith("_")):
                culpables.append(
                    f"{ruta.as_posix()}:{nodo.lineno} -> ChangeStatus.{nodo.attr}")

    assert not culpables, (
        "estos sitios usan un miembro que el enum del modelo no tiene, así que "
        "revientan con AttributeError al ejecutarse: " + "; ".join(culpables))


def test_los_campos_de_la_respuesta_siguen_estando(db, cambios):
    """No se cambia el contrato: sólo se añade `truncated`."""
    from app.services.service_desk import change_impact_service as svc

    datos = svc.puntuar_cambios_pendientes(db, _Usuario(ORG))
    for campo in ("ok", "total_pending", "scored", "auto_approved", "errors"):
        assert campo in datos, f"falta {campo}, que ya devolvía antes"
