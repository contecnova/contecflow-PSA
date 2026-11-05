"""Políticas RLS generadas desde los modelos: misma semántica que el filtro del ORM (revisión 2026-11).

Corre sin Postgres; la prueba contra la base de verdad es `test_rls_postgres.py`.
"""
from __future__ import annotations

from app.db import rls
from app.db.base import Base


def test_toda_tabla_con_empresa_tiene_politica():
    con_empresa = {t.name for t in Base.metadata.sorted_tables if {"organization_id", "org_id"} & set(t.c.keys())}
    assert set(rls.politicas()) == con_empresa and len(con_empresa) > 300


def test_la_semantica_es_la_del_orm():
    p = rls.politicas()
    assert "IS NULL" not in p["projects"][0].split(" OR ", 1)[1], "estricta: sin filas globales"
    assert "organization_id IS NULL" in p["app_settings"][0], "AppSetting incluye las globales"
    assert "user_organization_memberships" in p["users"][0], "usuarios: ficha o pertenencia"


def test_el_contexto_es_el_que_decide_el_orm():
    assert rls.tenant_de({"organization_id": "o1", "is_superadmin": False}) == "o1"
    assert rls.tenant_de({"organization_id": "o1", "is_superadmin": True}) == ""
    assert rls.tenant_de({"organization_id": "o1"}) == "", "sesión sin inicializar (trabajos de fondo): no filtra"
    assert rls.tenant_de({"organization_id": "o1", "is_superadmin": False, "bypass_tenant_filter": True}) == ""
