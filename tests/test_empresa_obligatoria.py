"""`organization_id` obligatorio (migración 208, 24-11-2026).

Docs: docs/seguridad/empresa_obligatoria.md. Vigila:

- que la lista `TABLAS_SIN_EMPRESA_PERMITIDA` y los modelos casen (toda tabla con
  `organization_id` nulable está en la lista con motivo, y ninguna de la lista es
  NOT NULL), y que la copia congelada de la migración sea la misma;
- que el sellado deduce la empresa del padre y corta lo que quede sin empresa;
- el relleno y la reconstrucción de la migración sobre una base SQLite en memoria.
"""
import importlib.util

import pytest
import sqlalchemy as sa


def _migracion():
    ruta = "alembic/versions/208_empresa_obligatoria_y_portal.py"
    spec = importlib.util.spec_from_file_location("mig208_test", ruta)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


def _tablas_con_empresa():
    import app.models  # noqa: F401
    from app.db.base import Base
    return {n: t for n, t in Base.metadata.tables.items() if "organization_id" in t.c}


# ── La lista y los modelos ────────────────────────────────────────────────────

def test_solo_las_tablas_exceptuadas_admiten_empresa_vacia():
    from app.db.empresa_obligatoria import TABLAS_SIN_EMPRESA_PERMITIDA as EXC
    tablas = _tablas_con_empresa()
    nulables = {n for n, t in tablas.items() if t.c.organization_id.nullable}
    assert nulables - set(EXC) == set(), "organization_id nulable sin estar en TABLAS_SIN_EMPRESA_PERMITIDA"
    assert set(EXC) - nulables == set(), "tabla exceptuada que ya es NOT NULL (o no existe): sácala de la lista"


def test_cada_excepcion_tiene_motivo():
    from app.db.empresa_obligatoria import TABLAS_SIN_EMPRESA_PERMITIDA as EXC
    for tabla, motivo in EXC.items():
        assert motivo and len(motivo.strip()) >= 20, tabla


def test_los_catalogos_con_valor_global_estan_exceptuados():
    """Una tabla que lee `org == X OR org IS NULL` necesita poder guardar el NULL."""
    import app.models  # noqa: F401
    from app.db.base import Base
    from app.db.empresa_obligatoria import TABLAS_SIN_EMPRESA_PERMITIDA as EXC
    globales = {m.class_.__tablename__ for m in Base.registry.mappers
                if getattr(m.class_, "_tenant_filter_include_global", False)}
    assert globales <= set(EXC), globales - set(EXC)


def test_la_migracion_208_usa_la_misma_lista():
    from app.db.empresa_obligatoria import TABLAS_SIN_EMPRESA_PERMITIDA as EXC
    assert _migracion().EXCEPTUADAS == frozenset(EXC)


def test_el_correo_del_portal_es_unico_por_empresa_en_el_modelo():
    from app.models.client_portal import ClientUser
    indices = {i.name: i for i in ClientUser.__table__.indexes}
    assert indices["uq_client_users_org_email"].unique
    assert not ClientUser.__table__.c.email.unique


# ── Sellado al insertar ───────────────────────────────────────────────────────

def test_la_empresa_se_deduce_del_proyecto(db):
    from app.db.empresa_obligatoria import empresa_deducida
    from app.models.project import Project, ProjectType
    from app.models.task import Task
    p = Project(name="Deducir", code="DED-208", project_type=ProjectType.development, organization_id="1")
    db.add(p)
    db.commit()
    assert empresa_deducida(db, Task(title="hija", project_id=p.id)) == "1"


def test_una_fila_sin_empresa_corta_el_flush_con_codigo(db):
    from app.core.errores import ErrorDeDominio
    from app.models.settings import Department
    from tests.conftest import fila_global
    with fila_global(db):
        db.add(Department(name="Sin empresa"))
        with pytest.raises(ErrorDeDominio) as exc:
            db.commit()
    db.rollback()
    assert exc.value.code == "fila_sin_empresa"
    assert exc.value.params["tabla"] == "departments"


def test_una_tabla_exceptuada_admite_la_fila_global(db):
    from app.models.settings import AppSetting
    from tests.conftest import fila_global
    with fila_global(db):
        db.add(AppSetting(key="prueba.208.global", value="x", organization_id=None))
        db.commit()
    assert db.query(AppSetting).filter(AppSetting.key == "prueba.208.global").one().organization_id is None


# ── La migración sobre una base en memoria ───────────────────────────────────

def _base_pequena(conn, empresas=("e1",)):
    for sql in (
        "CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY, name VARCHAR(50))",
        "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36) NOT NULL)",
        "CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36))",
        "CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
        "project_id VARCHAR(36) REFERENCES projects (id), FOREIGN KEY(organization_id) REFERENCES organizations (id))",
        "CREATE TABLE departments (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), name VARCHAR(50))",
        "CREATE TABLE client_users (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), email VARCHAR(255))",
        "CREATE INDEX ix_departments_nombre ON departments (lower(name))",
    ):
        conn.exec_driver_sql(sql)
    for e in empresas:
        conn.exec_driver_sql(f"INSERT INTO organizations VALUES ('{e}', 'Empresa {e}')")
    conn.exec_driver_sql("INSERT INTO projects VALUES ('p1', 'e1')")
    conn.exec_driver_sql("INSERT INTO tasks VALUES ('t1', NULL, 'p1')")
    conn.exec_driver_sql("INSERT INTO departments VALUES ('d1', NULL, 'Ventas')")


def test_rellena_por_el_padre_y_por_la_empresa_unica(monkeypatch):
    mig = _migracion()
    monkeypatch.delenv(mig.VARIABLE_EMPRESA, raising=False)
    motor = sa.create_engine("sqlite://")
    with motor.begin() as conn:
        _base_pequena(conn)
        cuenta = mig.rellenar(conn, ["departments", "projects", "tasks"])
        assert cuenta["tasks"] == {"deducidas": 1, "respaldo": 0}
        assert cuenta["departments"] == {"deducidas": 0, "respaldo": 1}
        mig.poner_restriccion(conn, ["departments", "tasks"], True)
        cols = {c["name"]: c for c in sa.inspect(conn).get_columns("departments")}
        assert cols["organization_id"]["nullable"] is False
        indices = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_departments_nombre'").scalar()
        assert "lower(name)" in indices, "la reconstrucción perdió el índice de expresión"
        assert conn.exec_driver_sql("SELECT organization_id FROM departments").scalar() == "e1"
        mig.poner_restriccion(conn, ["departments"], False)
        cols = {c["name"]: c for c in sa.inspect(conn).get_columns("departments")}
        assert cols["organization_id"]["nullable"] is True


def test_con_varias_empresas_y_filas_sin_deducir_para(monkeypatch):
    mig = _migracion()
    monkeypatch.delenv(mig.VARIABLE_EMPRESA, raising=False)
    motor = sa.create_engine("sqlite://")
    with motor.begin() as conn:
        _base_pequena(conn, empresas=("e1", "e2"))
        with pytest.raises(mig.MigracionParada) as exc:
            mig.rellenar(conn, ["departments", "tasks"])
        assert "departments: 1 filas" in str(exc.value)
        monkeypatch.setenv(mig.VARIABLE_EMPRESA, "e2")
        mig.rellenar(conn, ["departments"])
        assert conn.exec_driver_sql("SELECT organization_id FROM departments").scalar() == "e2"


def test_duplicados_de_correo_en_una_empresa_paran_sin_borrar():
    mig = _migracion()
    motor = sa.create_engine("sqlite://")
    with motor.begin() as conn:
        _base_pequena(conn)
        conn.exec_driver_sql("INSERT INTO client_users VALUES ('c1', 'e1', 'Ana@X.com')")
        conn.exec_driver_sql("INSERT INTO client_users VALUES ('c2', 'e1', 'ana@x.com')")
        conn.exec_driver_sql("INSERT INTO client_users VALUES ('c3', 'e2', 'ana@x.com')")
        assert mig.duplicados_del_portal(conn) == [("e1", "ana@x.com", 2)]
        with pytest.raises(mig.MigracionParada) as exc:
            mig._exigir_sin_duplicados(conn)
        assert "a***@x.com" in str(exc.value) and "ana@x.com" not in str(exc.value)
        assert conn.exec_driver_sql("SELECT count(*) FROM client_users").scalar() == 3


def test_la_restriccion_se_pone_y_se_quita_en_el_create_table():
    mig = _migracion()
    sql = 'CREATE TABLE "x" (\n\tid VARCHAR(36) NOT NULL, \n\torganization_id VARCHAR(36), \n\t' \
          'group_organization_id VARCHAR(36), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id)\n)'
    con = mig.sql_con_restriccion(sql, True)
    assert "organization_id VARCHAR(36) NOT NULL," in con and "group_organization_id VARCHAR(36)," in con
    assert mig.sql_con_restriccion(con, False) == sql
