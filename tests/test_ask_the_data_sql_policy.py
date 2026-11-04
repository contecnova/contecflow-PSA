"""La política de SQL de «pregúntale a los datos», que no tenía ni un test.

Auditoría 2026-09 (hallazgo 18). `validate_sql` es lo único que separa el SQL
que escribe un modelo de lenguaje —a partir de texto libre del usuario— de la
base de datos de producción. Al bajar su complejidad se descubrió que **no
tenía ninguna prueba**, así que la única forma de saber si el refactor
cambiaba algo era compararlo con la versión anterior a mano.

Estos casos son esa comparación, convertida en guardián. Cubren las tres cosas
que la función hace y que, si se rompen, no se notan hasta que ya ha pasado
algo:

  1. **Sólo SELECT, sólo tablas permitidas.** Una lista blanca, no una negra.
  2. **Siempre hay LIMIT.** Una consulta sin él puede traerse la tabla entera.
  3. **El acotado por organización se inyecta, no se confía.** Es lo que más
     importa: el modelo puede escribir su propio `organization_id = '...'`, y
     ese valor lo controla él. El filtro de verdad se añade aparte, con el
     `org_id` como parámetro enlazado.
"""
import pytest

from app.services.ask_the_data import (
    MAX_ROWS,
    SQLValidationError,
    validate_sql,
)


# ── Lo que se rechaza ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "DELETE FROM dim_project",
    "UPDATE dim_project SET status = 'x'",
    "INSERT INTO dim_project (id) VALUES ('x')",
    "DROP TABLE dim_project",
])
def test_solo_se_permiten_consultas_de_lectura(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql, "org-1")


def test_una_tabla_no_permitida_se_rechaza():
    with pytest.raises(SQLValidationError, match="Unauthorized tables"):
        validate_sql("SELECT * FROM users_secretos", "org-1")


def test_una_consulta_sin_tabla_se_rechaza():
    # `SELECT 1` no toca datos, pero tampoco tiene sentido aquí y abre la
    # puerta a expresiones que el resto de comprobaciones no miran.
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT 1", "org-1")


def test_el_punto_y_coma_no_permite_encadenar_una_segunda_sentencia():
    # El `rstrip(";")` sólo quita el final; una segunda sentencia queda dentro
    # y la caza la lista de palabras prohibidas.
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM dim_project; DROP TABLE dim_project", "org-1")


# ── El límite ─────────────────────────────────────────────────────────────────

def test_se_anade_limite_cuando_no_lo_hay():
    sql, _ = validate_sql("SELECT * FROM dim_project", None)
    assert f"LIMIT {MAX_ROWS}" in sql


def test_un_limite_mayor_se_acota():
    sql, _ = validate_sql("SELECT * FROM dim_project LIMIT 999999", None)
    assert f"LIMIT {MAX_ROWS}" in sql
    assert "999999" not in sql


def test_un_limite_menor_se_respeta():
    sql, _ = validate_sql("SELECT * FROM dim_project LIMIT 5", None)
    assert "LIMIT 5" in sql


# ── El acotado por organización ───────────────────────────────────────────────

def test_sin_org_no_se_inyecta_nada():
    sql, params = validate_sql("SELECT * FROM dim_project", None)
    assert params == {}
    assert "organization_id" not in sql


def test_el_org_id_viaja_como_parametro_enlazado_y_nunca_interpolado():
    sql, params = validate_sql("SELECT * FROM dim_project", "org-1")
    assert params == {"org_id": "org-1"}
    assert "$org_id" in sql
    # El valor en sí NO puede aparecer en el texto de la consulta.
    assert "org-1" not in sql


def test_se_inyecta_en_el_where_existente():
    sql, _ = validate_sql("SELECT * FROM dim_project WHERE status = 'active'", "org-1")
    assert "WHERE dim_project.organization_id = $org_id AND status = 'active'" in sql


def test_se_inyecta_antes_del_group_by_en_una_agregada():
    sql, _ = validate_sql("SELECT status, COUNT(*) FROM fact_imputations GROUP BY status", "org-1")
    # El filtro tiene que quedar ANTES del GROUP BY: si quedara fuera, la
    # agregación ya habría mezclado filas de otras organizaciones.
    assert sql.index("organization_id = $org_id") < sql.index("GROUP BY")


def test_se_inyecta_antes_del_order_by():
    sql, _ = validate_sql("SELECT * FROM fact_imputations ORDER BY created_at DESC", "org-1")
    assert sql.index("organization_id = $org_id") < sql.index("ORDER BY")


def test_el_filtro_propio_se_anade_aunque_el_modelo_escriba_el_suyo():
    """El caso que da sentido a todo lo demás.

    Si el modelo escribe `WHERE organization_id = 'otra-org'`, ese valor lo
    controla él. El filtro de verdad se añade **además**, encadenado con AND,
    de forma que la consulta no puede devolver filas de otra organización por
    mucho que el modelo lo pida.
    """
    sql, params = validate_sql(
        "SELECT * FROM dim_project WHERE organization_id = 'otra-org'", "org-1",
    )
    assert params == {"org_id": "org-1"}
    assert "organization_id = $org_id AND" in sql
    # La condición del modelo sigue ahí, pero ahora está en conjunción con la
    # nuestra: `org_id = $org_id AND org_id = 'otra-org'` no devuelve nada.
    assert "'otra-org'" in sql


# ── Higiene de entrada ────────────────────────────────────────────────────────

def test_se_quitan_las_vallas_de_markdown_que_pone_el_modelo():
    sql, _ = validate_sql("```sql\nSELECT * FROM dim_project;\n```", None)
    assert "```" not in sql
    assert sql.lstrip().upper().startswith("SELECT")



def test_con_join_el_filtro_va_por_cada_tabla_y_no_es_ambiguo():
    """Auditoria 2026-11: `organization_id` sin calificar era ambiguo con JOIN
    (DuckDB: «Ambiguous reference») y toda consulta de dos tablas fallaba."""
    from app.services.ask_the_data import validate_sql
    sql, params = validate_sql(
        "SELECT p.name, SUM(i.hours) FROM fact_imputations i JOIN dim_project p ON p.project_id = i.project_id "
        "GROUP BY p.name", org_id="org-1")
    assert "i.organization_id = $org_id" in sql and "p.organization_id = $org_id" in sql
    assert params["org_id"] == "org-1"


def test_el_calendario_comun_no_se_filtra():
    from app.services.ask_the_data import _inyectar_filtro_de_tenant
    assert "organization_id" not in _inyectar_filtro_de_tenant("SELECT year FROM dim_date LIMIT 5")
