"""Plantillas de proyecto: la guarda que faltaba, y el enum que no cabía.

Auditoría 2026-08 (P3-22).

## La guarda

`endpoints/templates.py` tenía su propio `_get_template_or_404` que buscaba la
plantilla por id **sin ningún filtro de organización**, y de él colgaban las dos
altas: añadir un documento o un rol a la plantilla de otro cliente era una
escritura cruzada. Y las dos funciones de servicio que usa —`get_full_template`
y `export_project_as_template`— **no recibían al sujeto**, así que no podían
comprobar nada aunque quisieran: la misma forma que el endpoint de coste activo,
que sí lo recibía y lo descartaba con `_: User = Depends(...)`.

## El defecto que salió al arreglarla

`export_project_as_template` escribía la probabilidad de cada riesgo así:

    probability=str(getattr(r, "probability", "medium"))

Y `Risk.probability` es un `Enum(RiskProbability)` **NOT NULL**, así que `str()`
no da `"medium"`: da `"RiskProbability.medium"`. Medido sobre los diez valores:

    str(RiskProbability.very_low)  -> 'RiskProbability.very_low'   24 chars
    str(RiskProbability.medium)    -> 'RiskProbability.medium'     22 chars
    str(RiskProbability.very_high) -> 'RiskProbability.very_high'  25 chars
    str(RiskImpact.negligible)     -> 'RiskImpact.negligible'      21 chars

Y `template_risks.probability` es **VARCHAR(20)**. Dos defectos:

1. **siempre** se guardaba un texto que ningún lector puede comparar contra el
   enum, así que la plantilla salía con la probabilidad ilegible;
2. y en **cuatro de los diez valores** —entre ellos `medium`, el valor por
   defecto y el más frecuente— el texto **no cabe en la columna**: en PostgreSQL
   eso es `value too long for type character varying(20)` y la exportación
   entera revienta con un 500. En SQLite se guarda truncado y en silencio, que
   es por lo que la suite no lo veía. **Estos tests comprueban la longitud
   explícitamente**, porque sobre SQLite la aserción de tipo no basta.

## Y dos funciones muertas

`add_template_document` y `add_template_role` ya existían en el servicio, **no
las llamaba nadie** —comprobado en `app/` y en `tests/`— y tampoco filtraban por
organización: el endpoint había reimplementado lo mismo a mano. Se deja una sola
implementación.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio

ORG = "org-tpl-mia"
OTRA = "org-tpl-ajena"

#: El límite real de `template_risks.probability` y `.impact`.
LARGO_DE_COLUMNA = 20


class _Usuario:
    def __init__(self, organization_id, uid="u-tpl"):
        self.id = uid
        self.organization_id = organization_id
        self.is_superadmin = False


@pytest.fixture()
def plantillas(db):
    """Una plantilla en cada organización."""
    from app.models.advanced_config import ProjectTemplate

    creadas = {}
    for org in (ORG, OTRA):
        t = ProjectTemplate(
            id=f"tpl-{org}", name=f"Plantilla de {org}", organization_id=org)
        db.add(t)
        db.flush()
        creadas[org] = t
    db.commit()
    return creadas


# -- La guarda ---------------------------------------------------------------

def test_EL_HALLAZGO_no_se_anade_un_documento_a_la_plantilla_de_otro(db, plantillas):
    from app.services import advanced_config_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.agregar_documento_a_plantilla(
            db, _Usuario(ORG), plantillas[OTRA].id, {"name": "Colado"})
    assert exc.value.status_code == 404

    doc = svc.agregar_documento_a_plantilla(
        db, _Usuario(ORG), plantillas[ORG].id, {"name": "Especificacion"})
    db.commit()
    assert doc.name == "Especificacion"
    assert doc.organization_id == ORG


def test_EL_HALLAZGO_no_se_anade_un_rol_a_la_plantilla_de_otro(db, plantillas):
    from app.services import advanced_config_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.agregar_rol_a_plantilla(
            db, _Usuario(ORG), plantillas[OTRA].id, {"role_name": "Colado"})
    assert exc.value.status_code == 404

    rol = svc.agregar_rol_a_plantilla(
        db, _Usuario(ORG), plantillas[ORG].id, {"role_name": "Arquitecto"})
    db.commit()
    assert rol.role_name == "Arquitecto"
    assert rol.organization_id == ORG


def test_el_nombre_del_rol_acepta_las_dos_claves(db, plantillas):
    """El endpoint aceptaba `role_name` o `name`; se conserva."""
    from app.services import advanced_config_service as svc

    rol = svc.agregar_rol_a_plantilla(
        db, _Usuario(ORG), plantillas[ORG].id, {"name": "Analista"})
    db.commit()
    assert rol.role_name == "Analista"


def test_la_plantilla_completa_de_otro_cliente_da_404(db, plantillas):
    from app.services import advanced_config_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.get_full_template(plantillas[OTRA].id, db, _Usuario(ORG))
    assert exc.value.status_code == 404

    datos = svc.get_full_template(plantillas[ORG].id, db, _Usuario(ORG))
    assert datos["id"] == plantillas[ORG].id


def test_sin_sujeto_la_plantilla_completa_sigue_funcionando(db, plantillas):
    """El parámetro es opcional para los llamadores internos sin sujeto.

    Queda medido a propósito: si alguien lo hace obligatorio, este test dirá
    dónde estaba el compromiso.
    """
    from app.services import advanced_config_service as svc

    datos = svc.get_full_template(plantillas[OTRA].id, db)
    assert datos["id"] == plantillas[OTRA].id


def test_EL_ESTRUCTURAL_las_dos_funciones_muertas_ya_no_estan():
    """Dos implementaciones de la misma cosa es como aparecen las dos puertas."""
    from app.services import advanced_config_service as svc

    assert not hasattr(svc, "add_template_document")
    assert not hasattr(svc, "add_template_role")


# -- La exportación ----------------------------------------------------------

@pytest.fixture()
def proyectos_con_riesgo(db):
    """Un proyecto con un riesgo en cada organización.

    La probabilidad es `medium`, que es la que revienta la columna: 22 caracteres
    con `str()` contra un VARCHAR(20).
    """
    from app.models.pipeline import Risk, RiskImpact, RiskProbability
    from app.models.project import Project, ProjectType

    creados = {}
    for i, org in enumerate((ORG, OTRA)):
        p = Project(
            id=f"proy-{org}", name=f"Proyecto de {org}", code=f"PT{i}",
            project_type=ProjectType.development, organization_id=org,
            description=f"Descripcion de {org}")
        db.add(p)
        db.flush()
        # `code` es NOT NULL en `risks`.
        db.add(Risk(
            id=f"riesgo-{org}", code=f"R-{i}", project_id=p.id,
            title=f"Riesgo de {org}",
            category="tecnico", probability=RiskProbability.medium,
            impact=RiskImpact.moderate,
            mitigation_plan="Plan de mitigacion", organization_id=org))
        creados[org] = p
    db.commit()
    return creados


def test_EL_HALLAZGO_no_se_exporta_el_proyecto_de_otro_cliente(
    db, proyectos_con_riesgo
):
    """Se quedaba con los títulos de sus tareas y sus riesgos."""
    from app.services import advanced_config_service as svc

    with pytest.raises((HTTPException, ErrorDeDominio)) as exc:
        svc.export_project_as_template(
            project_id=proyectos_con_riesgo[OTRA].id, name=None,
            description=None, user_id="u-tpl", db=db,
            current_user=_Usuario(ORG))
    assert exc.value.status_code == 404


def test_EL_HALLAZGO_la_probabilidad_exportada_es_el_valor_y_cabe_en_la_columna(
    db, proyectos_con_riesgo
):
    """El defecto de verdad: `str()` sobre un enum en un VARCHAR(20)."""
    from app.models.advanced_config import TemplateRisk
    from app.services import advanced_config_service as svc

    datos = svc.export_project_as_template(
        project_id=proyectos_con_riesgo[ORG].id, name="Exportada",
        description=None, user_id="u-tpl", db=db,
        current_user=_Usuario(ORG))

    assert datos["risks_exported"] == 1
    riesgo = (
        db.query(TemplateRisk)
        .filter(TemplateRisk.template_id == datos["template_id"])
        .first()
    )
    assert riesgo.probability == "medium", (
        f"se ha guardado {riesgo.probability!r} en vez de 'medium'")
    assert riesgo.impact == "moderate"
    # Y la comprobación que SQLite no hace por su cuenta.
    assert len(riesgo.probability) <= LARGO_DE_COLUMNA
    assert len(riesgo.impact) <= LARGO_DE_COLUMNA
    # El resto del riesgo, que iba detrás de `hasattr` muertos.
    assert riesgo.category == "tecnico"
    assert riesgo.mitigation_plan == "Plan de mitigacion"


def test_EL_ESCENARIO_lo_que_escribia_antes_no_cabia(db):
    """Que el defecto era real: se mide el texto que producía `str()`.

    Cuatro de los diez valores de los dos enums pasan de 20 caracteres, así que
    en PostgreSQL la exportación reventaba con un 500.
    """
    from app.models.pipeline import RiskImpact, RiskProbability

    demasiado_largos = [
        str(m) for m in list(RiskProbability) + list(RiskImpact)
        if len(str(m)) > LARGO_DE_COLUMNA
    ]
    assert len(demasiado_largos) == 4, (
        f"esperaba 4 valores que no caben, hay {len(demasiado_largos)}: "
        f"{demasiado_largos}")
    assert "RiskProbability.medium" in demasiado_largos, (
        "el valor por defecto ya cabe: revisar si este test sigue midiendo lo "
        "que dice")

    # Y todos los `.value` sí caben, que es lo que ahora se guarda.
    assert all(
        len(m.value) <= LARGO_DE_COLUMNA
        for m in list(RiskProbability) + list(RiskImpact))


def test_el_ayudante_del_enum_tambien_admite_una_cadena_y_un_nulo():
    from app.services import advanced_config_service as svc

    from app.models.pipeline import RiskProbability

    assert svc._valor_de_enum(RiskProbability.very_high, "medium") == "very_high"
    assert svc._valor_de_enum("high", "medium") == "high"
    assert svc._valor_de_enum(None, "medium") == "medium"


def test_la_plantilla_exportada_lleva_la_organizacion(db, proyectos_con_riesgo):
    """Sin esto la plantilla nace invisible para su propio cliente (§3.quater)."""
    from app.models.advanced_config import ProjectTemplate, TemplateTask
    from app.services import advanced_config_service as svc

    datos = svc.export_project_as_template(
        project_id=proyectos_con_riesgo[ORG].id, name=None, description=None,
        user_id="u-tpl", db=db, current_user=_Usuario(ORG))

    tmpl = db.query(ProjectTemplate).filter(
        ProjectTemplate.id == datos["template_id"]).first()
    assert tmpl.organization_id == ORG
    assert tmpl.name == f"Template from Proyecto de {ORG}"
    # Y el `project_type`, que iba detrás de un `hasattr` muerto.
    assert tmpl.project_type is not None

    # Las hijas también, para que no queden invisibles.
    tareas = db.query(TemplateTask).all()
    assert all(t.organization_id == ORG for t in tareas)
