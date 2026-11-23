"""Listados: paginacion comun y sin consultas por fila (segunda auditoria 2026-11).

Medido con un contador ``before_cursor_execute`` sobre el motor de la suite,
pidiendo cada listado con 2 y con 8 filas (consultas por peticion, autenticacion
incluida):

    endpoint                         antes (2 -> 8)   despues (2 -> 8)
    GET /imputations                 20 -> 26         18 -> 18
    GET /sd/tickets                  18 -> 30         15 -> 15
    GET /alm/vendors                 12 -> 18         12 -> 12
    GET /alm/contracts               18 -> 42         13 -> 13
    GET /alm/licenses                18 -> 42         13 -> 13
    GET /alm/assets                  15 -> 27         12 -> 12
    GET /invoices                    17 -> 35         13 -> 13
    GET /billing-reports/invoices    17 -> 35         13 -> 13
    GET /clients                     4 count + gestor por cliente -> 15 -> 15
    GET /clients/{cid}/invoices      500 (Invoice.total_amount no existe) -> 12 -> 12

Cada caso comprueba las dos cosas que importan: que el numero de consultas no
crece con las filas (2 y 8 dan lo mismo) y que no pasa de su techo medido.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, Integer, JSON, Numeric
from sqlalchemy import event as sa_event
from sqlalchemy import inspect as sa_inspect

from tests.conftest import auth, engine


# ── Semillas ─────────────────────────────────────────────────────────────────

def _nuevo(db, modelo, **campos):
    """Fila con las columnas obligatorias sin valor por defecto rellenas."""
    # Desde la revisión 186 (19-11-2026) tipo de proyecto, sector, categoría de
    # gasto... son claves VARCHAR validadas contra su catálogo en `before_flush`
    # (antes eran enums y aquí salía el primer miembro). Un texto al azar ya no
    # vale: se usa la primera clave del sistema de ese catálogo.
    from app.services.settings_service.catalogos_de_clave import CATALOGOS, _VIGILADOS
    claves_de_catalogo = {atr: CATALOGOS[cat][1][0][0] for _m, nombre, atr, cat in _VIGILADOS
                          if nombre == modelo.__name__}
    for col in sa_inspect(modelo).columns:
        if col.key in claves_de_catalogo and col.key not in campos and not col.nullable:
            campos[col.key] = claves_de_catalogo[col.key]
            continue
        if (col.key in campos or col.nullable or col.default is not None
                or col.server_default is not None or col.foreign_keys):
            continue
        if col.primary_key:
            if not isinstance(col.type, Integer):
                campos[col.key] = str(uuid.uuid4())
            continue
        t = col.type
        if isinstance(t, Enum):
            campos[col.key] = list(t.enum_class)[0] if t.enum_class else t.enums[0]
        elif isinstance(t, Boolean):
            campos[col.key] = False
        elif isinstance(t, Integer):
            campos[col.key] = 1
        elif isinstance(t, (Float, Numeric)):
            campos[col.key] = 1.0
        elif isinstance(t, DateTime):
            campos[col.key] = dt.datetime.now(dt.timezone.utc)
        elif isinstance(t, Date):
            campos[col.key] = dt.date.today()
        elif isinstance(t, JSON):
            campos[col.key] = {}
        else:
            campos[col.key] = uuid.uuid4().hex[:12]
    atributos = set(sa_inspect(modelo).attrs.keys())
    fila = modelo(**{k: v for k, v in campos.items() if k in atributos})
    db.add(fila)
    db.flush()
    return fila


def _cliente(db):
    from app.models.clients import Client
    return _nuevo(db, Client, name=f"C-{uuid.uuid4().hex[:6]}", created_by="admin-test-id", is_active=True)


def _proyecto(db, cliente=None):
    from app.models.project import Project
    return _nuevo(db, Project, name="P", code=f"P-{uuid.uuid4().hex[:6]}", owner_id="pm-test-id",
                  client_id=(cliente or _cliente(db)).id)


def _imputacion(db, ctx):
    from app.models.imputation import Imputation
    from app.models.task import Task
    p = _proyecto(db)
    t = _nuevo(db, Task, title="T", project_id=p.id, assignee_id="dev-test-id", reporter_id="pm-test-id")
    _nuevo(db, Imputation, user_id="dev-test-id", project_id=p.id, task_id=t.id, date=dt.date.today(), hours=1.0)


def _ticket(db, ctx):
    from app.models.service_desk.tickets import Ticket
    p = _proyecto(db)
    _nuevo(db, Ticket, title="Tk", project_id=p.id, client_id=p.client_id,
           requester_user_id="dev-test-id", assigned_to_user_id="pm-test-id")


def _proveedor(db, ctx=None):
    from app.models.alm import ALMVendor
    return _nuevo(db, ALMVendor, name=f"V-{uuid.uuid4().hex[:6]}")


def _contrato_alm(db, ctx):
    from app.models.alm import ALMContract
    from app.models.clients import ClientContractLink
    c = _nuevo(db, ALMContract, vendor_id=_proveedor(db).id, owner_id="pm-test-id")
    _nuevo(db, ClientContractLink, contract_id=c.id, client_id=_cliente(db).id)


def _licencia(db, ctx):
    from app.models.alm import ALMLicense
    from app.models.clients import ClientLicenseLink
    lic = _nuevo(db, ALMLicense, vendor_id=_proveedor(db).id)
    _nuevo(db, ClientLicenseLink, license_id=lic.id, client_id=_cliente(db).id)


def _activo(db, ctx):
    from app.models.alm import ALMAsset
    _nuevo(db, ALMAsset, vendor_id=_proveedor(db).id, assigned_to_id="dev-test-id")


def _factura(db, ctx):
    from app.models.billing_reports import Invoice
    cliente = ctx.setdefault("cliente", _cliente(db))
    p = _proyecto(db, cliente)
    _nuevo(db, Invoice, project_id=p.id, number=f"N-{uuid.uuid4().hex[:6]}", issue_date=dt.date.today())


def _cliente_suelto(db, ctx):
    _proyecto(db)  # el cliente y un proyecto suyo, para que los recuentos tengan algo


#: (ruta, semilla, techo de consultas con 8 filas)
CASOS = [
    ("/api/v1/imputations", _imputacion, 18),
    ("/api/v1/sd/tickets", _ticket, 15),
    ("/api/v1/alm/vendors", _proveedor, 12),
    ("/api/v1/alm/contracts", _contrato_alm, 13),
    ("/api/v1/alm/licenses", _licencia, 13),
    # Fase 1 ALM (16-11-2026): +1 consulta en lote, las asignaciones de la página (titular vigente).
    ("/api/v1/alm/assets", _activo, 13),
    ("/api/v1/invoices", _factura, 13),
    ("/api/v1/billing-reports/invoices", _factura, 13),
    ("/api/v1/clients", _cliente_suelto, 15),
    ("/api/v1/clients/{cliente}/invoices", _factura, 12),
]


def _consultas(client, ruta, cabeceras):
    cuenta = {"n": 0}

    def contar(*_a, **_k):
        cuenta["n"] += 1

    sa_event.listen(engine, "before_cursor_execute", contar)
    try:
        r = client.get(ruta, headers=cabeceras)
    finally:
        sa_event.remove(engine, "before_cursor_execute", contar)
    assert r.status_code == 200, r.text
    return cuenta["n"], r


@pytest.mark.parametrize("ruta,semilla,techo", CASOS, ids=[c[0] for c in CASOS])
def test_el_listado_no_hace_una_consulta_por_fila(ruta, semilla, techo, client, admin_token, db):
    cabeceras = auth(admin_token)
    ctx: dict = {}
    medidas = []
    hechas = 0
    for n in (2, 8):
        for _ in range(hechas, n):
            semilla(db, ctx)
        db.commit()
        hechas = n
        url = ruta.format(**{k: v.id for k, v in ctx.items()})
        client.get(url, headers=cabeceras)  # la primera calienta caches de ajustes
        consultas, r = _consultas(client, url, cabeceras)
        assert r.json()["meta"]["total"] >= n
        medidas.append(consultas)
    assert medidas[0] == medidas[1], f"{ruta}: {medidas[0]} consultas con 2 filas y {medidas[1]} con 8"
    assert medidas[1] <= techo, f"{ruta}: {medidas[1]} consultas, techo {techo}"


# ── Paginacion ───────────────────────────────────────────────────────────────

def test_sin_parametros_devuelve_todo_y_con_pagina_corta(client, admin_token, db):
    for _ in range(5):
        _proveedor(db)
    db.commit()
    h = auth(admin_token)

    todo = client.get("/api/v1/alm/vendors", headers=h)
    assert len(todo.json()["items"]) == 5
    assert todo.headers["X-Total-Count"] == "5"
    assert "X-Truncated" not in todo.headers

    pagina = client.get("/api/v1/alm/vendors", params={"page": 2, "page_size": 2}, headers=h)
    cuerpo = pagina.json()
    assert [v["id"] for v in cuerpo["items"]] == [v["id"] for v in todo.json()["items"][2:4]]
    meta = cuerpo["meta"]
    assert (meta["total"], meta["page"], meta["page_size"], meta["has_more"]) == (5, 2, 2, True)


def test_el_tope_del_servidor_avisa_en_vez_de_cortar_en_silencio(client, admin_token, db, monkeypatch):
    from app.core.config import settings
    for _ in range(3):
        _proveedor(db)
    db.commit()
    monkeypatch.setattr(settings, "LIST_MAX_ROWS", 2)

    r = client.get("/api/v1/alm/vendors", headers=auth(admin_token))
    assert len(r.json()["items"]) == 2
    assert r.headers["X-Total-Count"] == "3"
    assert r.headers["X-Truncated"] == "true"
    assert r.json()["meta"]["has_more"] is True


def test_los_totales_de_gastos_del_equipo_no_dependen_de_la_pagina(client, admin_token, db):
    from app.models.expenses import Expense
    for importe in (10.0, 20.0, 30.0):
        _nuevo(db, Expense, user_id="admin-test-id", project_id=_proyecto(db).id, amount=importe,
               is_billable=importe > 10, expense_date=dt.date.today())
    db.commit()
    r = client.get("/api/v1/expenses/team", params={"page": 1, "page_size": 1}, headers=auth(admin_token))
    datos = r.json()["data"]
    assert len(datos["expenses"]) == 1
    assert r.headers["X-Total-Count"] == "3"
    assert datos["total"] == 60.0 and datos["billable_total"] == 50.0
