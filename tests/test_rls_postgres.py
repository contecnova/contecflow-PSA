"""Aislamiento entre empresas en la base (RLS), contra Postgres de verdad (revisión 2026-11).

SQLite no tiene RLS: esta prueba solo corre con
`RLS_TEST_OWNER_URL` (dueño del esquema, con las políticas aplicadas) y
`RLS_TEST_APP_URL` (rol de aplicación sin BYPASSRLS). Sin ellas se salta, y lo
dice. Medido antes: la aplicación conectaba como superusuario y había 0 políticas.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

OWNER, APP = os.getenv("RLS_TEST_OWNER_URL"), os.getenv("RLS_TEST_APP_URL")
pytestmark = pytest.mark.skipif(not (OWNER and APP), reason="sin RLS_TEST_OWNER_URL / RLS_TEST_APP_URL (Postgres)")

A, B = "rls-prueba-a", "rls-prueba-b"


@pytest.fixture
def app_session():
    from app.db.session import TenantSession
    from app.models.mfa import Organization
    from app.models.project import Project, ProjectStatus, ProjectType
    dueno = create_engine(OWNER)
    with Session(dueno) as s:
        for org in (A, B):
            s.add(Organization(id=org, name=org, slug=org))
        s.flush()
        for org in (A, B):
            s.add(Project(id=f"{org}-p", code=f"R{org[-1].upper()}1", name=f"Proyecto {org}",
                          status=ProjectStatus.active, project_type=ProjectType.development, organization_id=org))
        s.commit()
    motor = create_engine(APP)
    sesion = sessionmaker(bind=motor, class_=TenantSession)()
    sesion.info.update(organization_id=A, is_superadmin=False)
    yield sesion
    sesion.close()
    with dueno.begin() as c:
        c.execute(text("DELETE FROM projects WHERE organization_id IN (:a, :b)"), {"a": A, "b": B})
        c.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": A, "b": B})


def _cuantos(s):
    return s.execute(text("SELECT count(*) FROM projects WHERE organization_id IN (:a, :b)"), {"a": A, "b": B}).scalar()


def test_EL_HALLAZGO_el_sql_a_mano_no_ve_otra_empresa(app_session):
    assert _cuantos(app_session) == 1, "el SQL escrito a mano no pasa por el filtro del ORM: lo para la base"


def test_sin_filtro_y_superadmin_ven_todo(app_session):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(app_session):
        assert _cuantos(app_session) == 2
    app_session.info["is_superadmin"] = True
    assert _cuantos(app_session) == 2


def test_no_se_inserta_en_otra_empresa(app_session):
    from sqlalchemy.exc import ProgrammingError
    with pytest.raises(ProgrammingError, match="row-level security"):
        app_session.execute(text("INSERT INTO projects (id, code, name, status, project_type, organization_id) "
                                 "VALUES ('rls-x', 'RX1', 'x', 'active', 'development', :b)"), {"b": B})
    app_session.rollback()


def test_releer_lo_de_otra_empresa_dentro_de_sin_filtro_sigue_valiendo(app_session):
    """El uso documentado de `sin_filtro_de_tenant` (releer una fila que uno ha movido) no lo rompe RLS."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.project import Project
    with sin_filtro_de_tenant(app_session):
        ajeno = app_session.get(Project, f"{B}-p")
        app_session.expire(ajeno)
        assert ajeno.name == f"Proyecto {B}"


def test_la_red_esta_armada_con_el_rol_de_aplicacion(app_session):
    from app.db import rls
    estado = rls.estado(app_session.connection())
    assert estado["armed"] is True, estado
