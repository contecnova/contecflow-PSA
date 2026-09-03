"""Los filtros del constructor de informes, y las dos formas de no filtrar.

Auditoría 2026-08 (P3-18). `apply_filter` era complejidad 15 —doce `elif` sobre
el mismo `operator` en treinta líneas— y traía dos caminos por los que un filtro
podía **no filtrar**.

## 1. Un `in` con un valor que no es lista devolvía TODAS las filas

```python
elif operator == "in":
    if isinstance(value, list):
        query = query.filter(col.in_(value))
```

Sin rama alternativa, así que la consulta salía **sin filtrar**. Y pasaba las dos
validaciones del llamador —que sí existen y sí devuelven 400— porque lo que
fallaba era el *tipo* del valor, y `value` está declarado `Any`. Quien pedía
«estado está en […]» no recibía un error: recibía el informe completo con cifras
plausibles.

## 2. Una columna del catálogo que el modelo no tiene

`if not hasattr(model, column): return query`. Hoy es inalcanzable —las 243
columnas que `ENTITIES` declara existen todas en su modelo— y el test estructural
del final de este fichero es lo que lo mantiene así.

## 3. Y la entidad «Riesgos», que salió de escribir ese test estructural

`get_model_class()` buscaba `Risk` en `app.models.resources` cuando está en
`app.models.pipeline`. El `getattr(mod, clase, None)` devolvía `None`, el
`except` no se enteraba, y **todo informe sobre riesgos respondía 400** mientras
el catálogo ofrecía sus 16 columnas en la interfaz.

La invariante que fijan estos tests: **ningún operador puede dejar la consulta
sin filtrar.** Cada uno produce una cláusula, siempre.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.project import Project
from app.services.report_builder_service import (
    ENTITIES,
    OPERADORES_SOPORTADOS,
    OPERATORS,
    apply_filter,
    get_model_class,
)


class _ConsultaFalsa:
    """Registra las cláusulas que se le añaden en vez de hablar con la base."""

    def __init__(self):
        self.clausulas = []

    def filter(self, clausula):
        self.clausulas.append(clausula)
        return self


def _clausula(operator, value, column="name"):
    """La cláusula que produce un filtro, o el fallo de no producir ninguna."""
    q = _ConsultaFalsa()
    devuelto = apply_filter(q, Project, column, operator, value)
    assert devuelto is q, "apply_filter debe devolver la consulta encadenable"
    assert len(q.clausulas) == 1, (
        f"'{operator}' con {value!r} ha dejado la consulta SIN FILTRAR"
    )
    return q.clausulas[0]


# ── La invariante: todo operador produce cláusula ────────────────────────────

@pytest.mark.parametrize("operator", sorted(OPERADORES_SOPORTADOS))
def test_LA_INVARIANTE_ningun_operador_deja_la_consulta_sin_filtrar(operator):
    """El defecto original en su forma general: si un operador puede salir sin
    añadir cláusula, el informe devuelve más filas de las pedidas y nadie se
    entera. Se prueba cada uno con un valor de lista y con uno escalar, que son
    los dos que llegan de verdad."""
    for valor in (["a", "b"], "a"):
        _clausula(operator, valor)


def test_los_operadores_de_la_interfaz_y_los_de_sql_son_los_mismos():
    """`OPERATORS` es lo que la interfaz ofrece y lo que la validación acepta;
    la tabla de cláusulas es lo que se sabe traducir a SQL. Si divergen, un
    operador aceptado y no implementado vuelve a devolver todo sin filtrar —
    esta vez por la otra puerta."""
    assert set(OPERATORS) == set(OPERADORES_SOPORTADOS), (
        "operadores sólo en la interfaz: %s | sólo en SQL: %s" % (
            sorted(set(OPERATORS) - set(OPERADORES_SOPORTADOS)),
            sorted(set(OPERADORES_SOPORTADOS) - set(OPERATORS)),
        )
    )


# ── El defecto nº 1: el `in` mal tipado ─────────────────────────────────────

def test_EL_HALLAZGO_un_in_con_valor_escalar_si_filtra():
    """Antes salía sin filtrar: todas las filas. Ahora un escalar se interpreta
    como lista de uno, que es lo que la persona quería decir."""
    c = _clausula("in", "activo")
    assert "IN" in str(c).upper()


@pytest.mark.parametrize("valor", [
    "activo",            # cadena — el caso que rompía
    42,                  # número
    None,                # nulo
    ("a", "b"),          # tupla
    {"a", "b"},          # conjunto
    frozenset({"a"}),
])
def test_un_in_filtra_con_cualquier_tipo_de_valor(valor):
    _clausula("in", valor)


def test_un_in_con_lista_vacia_no_devuelve_filas_y_eso_es_lo_correcto():
    """«Está en el conjunto vacío» son cero filas. Devolverlo todo, que es lo
    que hacía cuando el valor no era lista, es lo contrario de lo pedido."""
    c = _clausula("in", [])
    assert "IN" in str(c).upper()


@pytest.mark.parametrize("entrada,esperado", [
    (["a", "b", "c"], ["a", "b", "c"]),
    (("a", "b"),      ["a", "b"]),
    ({"a"},           ["a"]),
    ("sola",          ["sola"]),      # el escalar, como lista de uno
    (42,              [42]),
    ([],              []),
])
def test_un_in_conserva_exactamente_los_elementos_que_se_le_dan(entrada, esperado):
    """SQLAlchemy renderiza `IN` con un parámetro expandible, así que los valores
    se comprueban en el `BindParameter` y no en el texto del SQL."""
    valores = _clausula("in", entrada).right.value
    assert sorted(map(repr, valores)) == sorted(map(repr, esperado))


def test_un_in_con_none_filtra_y_no_casa_con_nada():
    """`None` dentro de un `IN` se renderiza *inline* como `NULL` y no por
    parámetro expandible, así que la comprobación va sobre el SQL.

    Lo que importa es la propiedad, no la forma: `IN (NULL)` no casa con ninguna
    fila —ni con las que tienen la columna a nulo, porque en SQL nada es igual a
    NULL— así que un valor nulo devuelve **cero filas**. Es lo contrario de lo
    que hacía antes, que era devolverlas todas.
    """
    assert "IN (NULL)" in str(_clausula("in", None))


# ── Los doce operadores, uno a uno ──────────────────────────────────────────

@pytest.mark.parametrize("operator,fragmento", [
    ("eq",           "="),
    ("neq",          "!="),
    ("gt",           ">"),
    ("lt",           "<"),
    ("gte",          ">="),
    ("lte",          "<="),
    ("contains",     "LIKE"),
    ("not_contains", "LIKE"),
    ("starts_with",  "LIKE"),
    ("in",           "IN"),
    ("is_null",      "IS NULL"),
    ("is_not_null",  "IS NOT NULL"),
])
def test_cada_operador_genera_su_sql(operator, fragmento):
    assert fragmento in str(_clausula(operator, "x")).upper()


def test_contains_y_not_contains_son_opuestos():
    """Los dos usan `LIKE`, así que la comprobación de arriba no los distingue.
    Lo que los distingue es la negación, y eso sí importa: confundirlos devuelve
    exactamente las filas que no se piden."""
    assert "NOT" not in str(_clausula("contains", "x")).upper()
    assert "NOT" in str(_clausula("not_contains", "x")).upper()


@pytest.mark.parametrize("operator,plantilla", [
    ("contains",    "%x%"),
    ("starts_with", "x%"),
])
def test_los_comodines_van_donde_deben(operator, plantilla):
    """`starts_with` con `%x%` sería `contains` con otro nombre."""
    c = _clausula(operator, "x")
    assert c.right.value == plantilla


@pytest.mark.parametrize("operator", ["is_null", "is_not_null"])
@pytest.mark.parametrize("valor", [None, "", "cualquier cosa", 0, []])
def test_los_de_nulidad_ignoran_el_valor(operator, valor):
    """«Está vacío» no lleva operando y la interfaz no manda ninguno. Que el
    valor que llegue no cambie la cláusula evita que un `is_null` con valor se
    comporte de dos formas."""
    assert str(_clausula(operator, valor)) == str(_clausula(operator, None))


def test_is_null_no_se_confunde_con_igual_a_none():
    """`col == None` y `col IS NULL` son lo mismo en SQLAlchemy, pero
    `col != None` y `col IS NOT NULL` no siempre se leen igual: conviene que
    cada operador use su forma explícita."""
    assert "IS NULL" in str(_clausula("is_null", None)).upper()
    assert "IS NOT NULL" in str(_clausula("is_not_null", None)).upper()


# ── El defecto nº 2: una columna que el modelo no tiene ─────────────────────

def test_EL_HALLAZGO_una_columna_inexistente_ya_no_devuelve_todo_sin_filtrar():
    """Antes `return query`: el informe salía completo. Ahora es un 500, porque
    el error es del catálogo del servidor y no de quien pide el informe — y un
    500 se ve en los logs mientras que un informe con filas de más no se ve en
    ningún sitio."""
    with pytest.raises(HTTPException) as e:
        apply_filter(_ConsultaFalsa(), Project, "columna_que_no_existe", "eq", "x")
    assert e.value.status_code == 500
    assert "columna_que_no_existe" in str(e.value.detail)


def test_un_operador_sin_traduccion_tambien_lanza():
    with pytest.raises(HTTPException) as e:
        apply_filter(_ConsultaFalsa(), Project, "name", "operador_inventado", "x")
    assert e.value.status_code == 500


# ── El test estructural: catálogo contra modelos ────────────────────────────

def test_todas_las_columnas_del_catalogo_existen_en_su_modelo():
    """Esto es lo que mantiene inalcanzable la rama de arriba.

    `allowed_cols` sale de `ENTITIES[entidad]["columns"]`, un catálogo escrito a
    mano, no derivado del modelo. Una columna que el catálogo declare y el modelo
    no tenga se ofrece en la interfaz, pasa la validación de `allowed_cols` y
    llega a `apply_filter`.
    """
    fallos = []
    for entidad, definicion in ENTITIES.items():
        modelo = get_model_class(entidad)
        if modelo is None:
            continue          # entidades opcionales: el test de abajo las cubre
        for columna in definicion.get("columns", {}):
            if not hasattr(modelo, columna):
                fallos.append(f"{entidad}.{columna}")
    assert not fallos, "columnas del catálogo que no existen en su modelo: %s" % fallos


def test_EL_HALLAZGO_todas_las_entidades_del_catalogo_resuelven_su_modelo():
    """De aquí salió el hallazgo de «Riesgos».

    `get_model_class()` resuelve 16 entidades opcionales por ruta de módulo, con
    un `getattr(mod, clase, None)` y un `except (ImportError, AttributeError):
    pass`. Riesgos buscaba `Risk` en `app.models.resources` cuando está en
    `app.models.pipeline`, así que devolvía `None` y **todo informe sobre riesgos
    respondía 400 «entidad no soportada en este entorno»** — mientras el catálogo
    ofrecía sus 16 columnas en la interfaz.

    Si este test falla, alguna entidad que la interfaz ofrece no se puede
    consultar. Los `except` que se lo tragan siguen ahí a propósito, porque las
    entidades opcionales son opcionales de verdad en algunos despliegues; lo que
    no puede pasar es que se lo traguen **en el entorno de tests**, donde todos
    los módulos están.
    """
    sin_modelo = [e for e in ENTITIES if get_model_class(e) is None]
    assert not sin_modelo, (
        "entidades ofrecidas en el catálogo que no resuelven su modelo: %s"
        % sin_modelo
    )


def test_riesgos_resuelve_y_trae_lo_que_el_catalogo_promete():
    """El caso concreto, fijado: no vale con que resuelva algo, tiene que
    resolver un modelo con las 16 columnas del catálogo y con las dos que
    necesita el acotado por tenant de `execute_report`."""
    modelo = get_model_class("risks")
    assert modelo is not None, "la entidad «Riesgos» ha vuelto a no resolver"
    assert modelo.__tablename__ == "risks"
    for columna in ENTITIES["risks"]["columns"]:
        assert hasattr(modelo, columna), columna
    assert hasattr(modelo, "organization_id")
    assert hasattr(modelo, "project_id")


# ── De extremo a extremo, por el endpoint real ───────────────────────────────

class TestInformeDeRiesgosPorElEndpoint:
    """Que la clase resuelva no basta: hay que ver el 200.

    El endpoint es lo que usa la interfaz, y es donde se veía el 400. Estos dos
    tests son los que habrían cazado el hallazgo desde el principio — no había
    ninguno que pidiera un informe de riesgos.
    """

    def test_EL_HALLAZGO_un_informe_de_riesgos_ya_no_devuelve_400(
            self, client, admin_token, db):
        from tests.conftest import auth
        res = client.post(
            "/api/v1/reports/preview",
            json={"entity": "risks", "columns": ["code", "title", "status"]},
            headers=auth(admin_token),
        )
        assert res.status_code == 200, (
            "la entidad «Riesgos» vuelve a no resolver su modelo: %s" % res.text
        )

    def test_un_informe_de_riesgos_acepta_filtros(self, client, admin_token, db):
        from tests.conftest import auth
        res = client.post(
            "/api/v1/reports/preview",
            json={
                "entity": "risks",
                "columns": ["code", "title", "risk_score"],
                "filters": [
                    {"column": "status", "operator": "eq", "value": "open"},
                    {"column": "impact", "operator": "in", "value": ["high", "medium"]},
                ],
            },
            headers=auth(admin_token),
        )
        assert res.status_code == 200, res.text

    def test_EL_DEFECTO_medido_por_su_efecto_un_in_escalar_no_devuelve_todo(
            self, client, admin_token, db):
        """El defecto, medido por su efecto y con datos propios.

        Antes, `in` con una cadena no filtraba: el informe salía con TODAS las
        filas. La comprobación que lo caza es que `in` con un escalar devuelva
        **lo mismo que `eq`** con ese escalar, y estrictamente menos que sin
        filtro.

        Los datos los crea el test —tres proyectos, dos con el mismo estado— para
        que las cifras estén calculadas a mano y el test **no pueda pasar en
        vacío**: si la base estuviera vacía, «in devuelve lo mismo que eq» sería
        `0 == 0` y no verificaría nada. Ése es el modo en que un test así deja de
        verificar sin que nadie lo note.
        """
        from tests.conftest import auth
        from app.models.project import Project, ProjectStatus, ProjectType
        from app.models.user import User

        # La organización se toma del propio administrador que va a pedir el
        # informe: si se cogiera otra, el acotado por tenant de `execute_report`
        # dejaría las filas fuera y el test pasaría en vacío.
        org_id = db.query(User.organization_id).filter(
            User.username == "admin").scalar()
        assert org_id, "el administrador de los tests no tiene organización"

        for codigo, estado in (("AUD-IN-1", ProjectStatus.planning),
                               ("AUD-IN-2", ProjectStatus.planning),
                               ("AUD-IN-3", ProjectStatus.completed)):
            db.add(Project(organization_id=org_id, code=codigo, name=codigo,
                           project_type=ProjectType.development, status=estado,
                           is_billable=False))
        db.commit()

        def filas(operador, valor):
            res = client.post(
                "/api/v1/reports/preview",
                json={
                    "entity": "projects",
                    "columns": ["code", "status"],
                    "filters": [{"column": "status", "operator": operador,
                                 "value": valor}],
                },
                headers=auth(admin_token),
            )
            assert res.status_code == 200, res.text
            # La respuesta es {"data": {"rows": [...], "count": N}, "meta": ...}.
            # Leerla mal es como se puede creer que hay filas donde no hay: un
            # `.get("rows", cuerpo)` sobre el diccionario exterior devuelve el
            # propio diccionario, y contar sus claves da 2 sin ninguna fila.
            crudas = res.json()["data"]["rows"]
            return [f for f in crudas if (f.get("code") or "").startswith("AUD-IN-")]

        con_eq = filas("eq", "planning")
        con_in = filas("in", "planning")
        todas = filas("is_not_null", None)

        assert len(todas) == 3, "los tres proyectos del test no están: %s" % todas
        assert len(con_eq) == 2, "«eq planning» debería dar 2, ha dado %d" % len(con_eq)
        assert len(con_in) == 2, (
            "«in» con un escalar ha devuelto %d de 3 en vez de 2: el filtro no "
            "está filtrando" % len(con_in)
        )
