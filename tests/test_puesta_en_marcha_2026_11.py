"""Lista de puesta en marcha de una empresa (revisión 2026-11, lo que contecmind tenía).

Cada punto se mide sobre los datos de la empresa, no se marca a mano: estas
pruebas crean el dato y comprueban que el punto cambia, y que el dato de OTRA
empresa no cuenta.
"""
from __future__ import annotations

from app.models.billing_reports import ApprovalWorkflow
from app.models.clients import Client
from app.models.mfa import Organization
from app.services import settings_service
from tests.conftest import auth

URL = "/api/v1/settings/setup-checklist"


def _lista(client, token) -> dict:
    r = client.get(URL, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _punto(lista, id_):
    return next(p for p in lista["items"] if p["id"] == id_)


def _otra_empresa(db):
    db.add(Organization(id="org-pm", name="Otra", slug="org-pm"))
    db.commit()
    return "org-pm"


def test_once_puntos_medidos_y_los_totales_cuadran(client, admin_token):
    lista = _lista(client, admin_token)
    ids = [p["id"] for p in lista["items"]]
    assert ids == ["ai_provider", "email", "support_inbox", "users", "clients", "approval_workflows", "sla",
                   "sso", "mfa", "branding", "ai_budget", "db_isolation"]
    assert all(isinstance(p["measured"], dict) and p["measured"] for p in lista["items"])
    necesarios = [p for p in lista["items"] if p["required"]]
    assert lista["required_total"] == len(necesarios) == 7
    assert lista["required_done"] == sum(p["done"] for p in necesarios)
    assert lista["recommended_done"] == sum(p["done"] for p in lista["items"] if not p["required"])


def test_EL_HALLAZGO_un_flujo_de_aprobacion_activo_cierra_el_punto_y_el_de_otra_empresa_no(client, db, admin_token):
    otra = _otra_empresa(db)
    db.add(ApprovalWorkflow(name="Ajeno", entity_type="expense", is_active=True, organization_id=otra))
    db.add(ApprovalWorkflow(name="Apagado", entity_type="expense", is_active=False, organization_id="1"))
    db.commit()
    assert _punto(_lista(client, admin_token), "approval_workflows")["done"] is False

    db.add(ApprovalWorkflow(name="Gastos", entity_type="expense", is_active=True, organization_id="1"))
    db.commit()
    punto = _punto(_lista(client, admin_token), "approval_workflows")
    assert punto["done"] is True and punto["measured"] == {"workflows": 1}


def test_clientes_cuentan_solo_los_de_la_empresa(client, db, admin_token):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        propios = db.query(Client).filter(Client.organization_id == "1").count()
    otra = _otra_empresa(db)
    db.add(Client(name="Cliente ajeno", organization_id=otra))
    db.commit()
    assert _punto(_lista(client, admin_token), "clients")["measured"] == {"clients": propios}

    db.add(Client(name="Cliente propio", organization_id="1"))
    db.commit()
    punto = _punto(_lista(client, admin_token), "clients")
    assert punto["done"] is True and punto["measured"] == {"clients": propios + 1}


def test_el_tope_de_gasto_se_lee_del_ajuste_de_la_empresa(client, db, admin_token):
    assert _punto(_lista(client, admin_token), "ai_budget")["done"] is False
    settings_service.set_runtime_value(db, "ai", "AI_DAILY_BUDGET_USD", 5.0, "1")
    db.commit()
    settings_service.invalidate_cache()
    punto = _punto(_lista(client, admin_token), "ai_budget")
    assert punto["done"] is True and punto["measured"] == {"daily_budget_usd": 5.0}


def test_la_mfa_va_sin_enlace_porque_no_tiene_pantalla(client, admin_token):
    assert _punto(_lista(client, admin_token), "mfa")["link"] is None


def test_solo_el_admin(client, pm_token, dev_token):
    assert client.get(URL, headers=auth(pm_token)).status_code == 403
    assert client.get(URL, headers=auth(dev_token)).status_code == 403
