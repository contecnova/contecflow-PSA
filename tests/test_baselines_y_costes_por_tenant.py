"""Dos anclas de tenencia que nadie comprobaba: el proyecto y la persona.

Auditoría 2026-08 (P3-22).

**`baselines.py`** — los cuatro endpoints anclan en `project_id` y **ninguno
comprobaba de quién es el proyecto**. Todo lo demás cuelga de ahí: las líneas
base se buscan por `project_id`, las tareas también. Así que el proyecto era el
único punto donde la tenencia se podía verificar, y era el que faltaba. Un
cronograma congelado guarda el presupuesto del proyecto en ese momento
(`budget_at_freeze`) y las horas estimadas de cada tarea.

**`user_costs.py`** — más cuidadoso que la media (los presets de país y el
`/summary` sí comprobaban la organización), pero cuatro sitios buscaban por id
a secas, y aquí lo que se expone son **salarios**:

* `GET /users/{id}/active` devolvía el perfil de coste y el
  `legacy_hourly_rate` de cualquier usuario por id;
* `GET /users/{id}/profiles`, el histórico salarial completo;
* `update_profile` y `delete_profile` buscaban el perfil por id.

Y una señal que merece quedar escrita: el endpoint de `/active` recibía el
sujeto y **lo descartaba con `_: User = Depends(...)`**. Tenía delante lo que
hacía falta para comprobar y lo tiraba; por eso la comprobación nunca se
escribió.

Estos tests van contra los servicios, donde el filtro implícito de
`TenantSession` no actúa (la suite usa otra factoría), así que lo que prueban es
la guarda explícita: **antes del arreglo devolverían la fila ajena**.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

ORG = "org-mia-bl"
OTRA = "org-ajena-bl"


class _Usuario:
    def __init__(self, organization_id, uid=None):
        self.id = uid or f"u-{organization_id}"
        self.organization_id = organization_id


# ── Líneas base del Gantt ───────────────────────────────────────────────────

@pytest.fixture()
def proyectos(db):
    """Un proyecto con una tarea en cada organización."""
    from app.models.project import Project, ProjectType
    from app.models.task import Task

    creados = {}
    for i, org in enumerate((ORG, OTRA)):
        p = Project(
            # `project_type` es NOT NULL en el modelo.
            organization_id=org, name=f"Proyecto de {org}", code=f"P{i}",
            project_type=ProjectType.development, budget_amount=100000.0,
        )
        db.add(p)
        db.flush()
        # `code` es NOT NULL en `tasks`.
        t = Task(project_id=p.id, code=f"T{i}", title=f"Tarea de {org}",
                 estimated_hours=10.0)
        db.add(t)
        db.flush()
        creados[org] = {"proyecto": p, "tarea": t}
    db.commit()
    return creados


def test_EL_HALLAZGO_el_proyecto_de_otro_cliente_da_404(db, proyectos):
    """Es la guarda que faltaba, y la única posible en este módulo."""
    from app.services import baselines_service as svc

    ajeno = proyectos[OTRA]["proyecto"]
    with pytest.raises(HTTPException) as exc:
        svc.proyecto_propio(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404

    mio = proyectos[ORG]["proyecto"]
    assert svc.proyecto_propio(db, _Usuario(ORG), mio.id).id == mio.id


def test_no_se_listan_las_lineas_base_de_un_proyecto_ajeno(db, proyectos):
    from app.services import baselines_service as svc

    ajeno = proyectos[OTRA]["proyecto"]
    with pytest.raises(HTTPException) as exc:
        svc.list_baselines(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404


def test_congelar_un_cronograma_guarda_la_foto_y_la_organizacion(db, proyectos):
    from app.services import baselines_service as svc

    mio = proyectos[ORG]["proyecto"]
    linea = svc.crear_linea_base(
        db, _Usuario(ORG), mio.id,
        name="Inicial", description="al arrancar", is_initial=True)

    assert linea.organization_id == ORG
    assert linea.total_tasks == 1
    assert linea.total_hours == 10.0
    # El presupuesto congelado: antes era SIEMPRE None porque se leia
    # `proj.budget` tras un `hasattr`, y la columna se llama `budget_amount`.
    assert linea.budget_at_freeze == 100000.0
    # La foto lleva la tarea con sus fechas y horas.
    import json
    foto = json.loads(linea.schedule_snapshot)
    assert len(foto["tasks"]) == 1
    assert foto["tasks"][0]["estimated_hours"] == 10.0


def test_no_se_puede_congelar_el_cronograma_de_otro_cliente(db, proyectos):
    from app.services import baselines_service as svc

    ajeno = proyectos[OTRA]["proyecto"]
    with pytest.raises(HTTPException) as exc:
        svc.crear_linea_base(
            db, _Usuario(ORG), ajeno.id, name="X", description=None,
            is_initial=False)
    assert exc.value.status_code == 404


def test_la_linea_base_de_otro_proyecto_no_se_compara_ni_se_borra(db, proyectos):
    from app.services import baselines_service as svc

    ajeno = proyectos[OTRA]["proyecto"]
    linea_ajena = svc.crear_linea_base(
        db, _Usuario(OTRA), ajeno.id, name="Suya", description=None,
        is_initial=False)

    mio = proyectos[ORG]["proyecto"]
    # Ni pasando el proyecto propio con la linea ajena...
    with pytest.raises(HTTPException) as exc:
        svc.comparar_con_linea_base(db, _Usuario(ORG), mio.id, linea_ajena.id)
    assert exc.value.status_code == 404
    # ...ni pasando el proyecto ajeno.
    with pytest.raises(HTTPException) as exc:
        svc.borrar_linea_base(db, _Usuario(ORG), ajeno.id, linea_ajena.id)
    assert exc.value.status_code == 404


def test_una_fecha_ilegible_en_la_foto_no_rompe_la_comparacion(db, proyectos):
    """La línea base es un histórico y puede traer datos de versiones viejas."""
    from app.services import baselines_service as svc

    assert svc._dias_de_desvio("2026-01-10", "2026-01-01") == 9
    assert svc._dias_de_desvio("no-es-fecha", "2026-01-01") is None
    assert svc._dias_de_desvio(None, "2026-01-01") is None


# ── Costes por persona: son salarios ────────────────────────────────────────

@pytest.fixture()
def personas(db):
    """Un usuario con perfil de coste en cada organización."""
    from app.models.user import User, UserRole, UserStatus
    from app.services import cost_service as svc

    creados = {}
    for org in (ORG, OTRA):
        u = User(
            id=f"persona-{org}", username=f"persona-{org}",
            email=f"persona-{org}@example.com", full_name=f"Persona {org}",
            role=UserRole.employee, status=UserStatus.active,
            hashed_password="x", organization_id=org, hourly_rate=42.0,
        )
        db.add(u)
        db.flush()
        from datetime import date as _Date
        perfil = svc.create_profile(
            db, user_id=u.id, valid_from=_Date(2026, 1, 1),
            gross_annual_salary=50000.0, employer_cost_pct=30.0,
            extra_annual_costs=0.0, productive_hours_year=1600,
            country_code="ES", currency="EUR", notes=None,
            organization_id=org, created_by_user_id=u.id,
        )
        creados[org] = {"usuario": u, "perfil": perfil}
    db.commit()
    return creados


def test_EL_HALLAZGO_no_se_lee_el_coste_de_una_persona_de_otro_cliente(db, personas):
    """`/users/{id}/active` devolvía el perfil y el `hourly_rate` de cualquiera."""
    from app.services import cost_service as svc

    ajena = personas[OTRA]["usuario"]
    with pytest.raises(HTTPException) as exc:
        svc.usuario_propio(db, _Usuario(ORG), ajena.id)
    assert exc.value.status_code == 404

    mia = personas[ORG]["usuario"]
    assert svc.usuario_propio(db, _Usuario(ORG), mia.id).id == mia.id


def test_EL_HALLAZGO_no_se_edita_el_perfil_de_coste_de_otro_cliente(db, personas):
    from app.services import cost_service as svc

    ajeno = personas[OTRA]["perfil"]
    with pytest.raises(HTTPException) as exc:
        svc.perfil_propio(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404

    mio = personas[ORG]["perfil"]
    assert svc.perfil_propio(db, _Usuario(ORG), mio.id).id == mio.id


def test_el_resumen_de_costes_no_lista_a_los_de_otro_cliente(db, personas):
    from app.services import cost_service as svc

    filas = svc.usuarios_activos_de_la_organizacion(
        db, _Usuario(ORG), tope=100)
    orgs = {u.organization_id for u in filas}
    assert orgs == {ORG}, f"el resumen incluye otras organizaciones: {orgs}"


def test_EL_HALLAZGO_el_filtro_del_resumen_ya_no_es_condicional(db, personas):
    """Era `if org_id: q = q.filter(...)`.

    Con un sujeto sin organización eso listaba a los usuarios de **todos** los
    clientes; ahora lista los que no tienen organización, que es lo que dice.
    """
    from app.services import cost_service as svc

    filas = svc.usuarios_activos_de_la_organizacion(
        db, _Usuario(None), tope=100)
    assert all(u.organization_id is None for u in filas), (
        "un sujeto sin organización está viendo usuarios de otros clientes")


def test_un_preset_global_de_pais_se_puede_leer_pero_no_borrar(db):
    """Los globales son los valores que trae el producto: se sobrescriben."""
    from app.models.user_cost import CountryEmployerCost
    from app.services import cost_service as svc

    from tests.conftest import fila_global

    # `fila_global` porque el sellado del `flush` rellenaria la organizacion de
    # la sesion, y un preset de pais con organizacion ya no es el global que
    # trae el producto: es el de un cliente.
    with fila_global(db):
        global_ = CountryEmployerCost(
            organization_id=None, country_code="PT", country_name="Portugal",
            currency="EUR", employer_cost_pct=25.0, productive_hours_year=1600)
        db.add(global_)
        db.commit()

    assert svc.preset_propio_o_global(db, _Usuario(ORG), global_.id).id == global_.id
    with pytest.raises(HTTPException) as exc:
        svc.borrar_preset_de_pais(db, _Usuario(ORG), global_.id)
    assert exc.value.status_code == 400


def test_el_preset_de_otro_cliente_no_se_ve(db):
    from app.models.user_cost import CountryEmployerCost
    from app.services import cost_service as svc

    ajeno = CountryEmployerCost(
        organization_id=OTRA, country_code="IT", country_name="Italia",
        currency="EUR", employer_cost_pct=28.0, productive_hours_year=1600)
    db.add(ajeno)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        svc.preset_propio_o_global(db, _Usuario(ORG), ajeno.id)
    assert exc.value.status_code == 404


def test_el_codigo_de_pais_se_normaliza_a_mayusculas(db):
    """La unicidad es por `(country_code, organization_id)`: sin normalizar,
    «es» y «ES» serían dos presets del mismo país."""
    from app.services import cost_service as svc

    primero = svc.guardar_preset_de_pais(db, _Usuario(ORG), {
        "country_code": "fr", "country_name": "Francia", "currency": "EUR",
        "employer_cost_pct": 40.0, "productive_hours_year": 1600, "notes": None,
    })
    assert primero.country_code == "FR"

    segundo = svc.guardar_preset_de_pais(db, _Usuario(ORG), {
        "country_code": "FR", "country_name": "Francia (revisado)",
        "currency": "EUR", "employer_cost_pct": 42.0,
        "productive_hours_year": 1600, "notes": None,
    })
    assert segundo.id == primero.id, "se creó un segundo preset del mismo país"
    assert segundo.employer_cost_pct == 42.0
