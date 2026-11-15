"""Gastos sobre el motor de políticas, con aprobación graduada (tarea #27, rev. 166).

Lo que se mide: dentro de la política (responsable / auto-aprobado), +10 % → un
nivel más, +30 % → dos, bloqueo explícito → 422, conversión PLN→EUR, comidas
por asistente, tipo de documento exigido, sin flujo los niveles se abren igual
y no se saltan desde la pantalla de gastos, migración de `expense_policies`
con el mismo comportamiento, ejemplos como borrador y aislamiento por empresa.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.billing_reports import ApprovalRequest, ApprovalRequestStep
from app.models.bookings import ExchangeRate
from app.models.expenses import Expense, ExpenseAttachment, ExpenseStatus
from app.models.politicas import FilaDeTablaDeReferencia, Politica, ReglaDePolitica, TablaDeReferencia
from app.models.user import User
from app.services.politicas import motor
from tests.conftest import auth
from tests.test_approvals import create_workflow

ORG = "1"
DIA = "2026-10-07"   # miércoles


def _cond(campo, op, valor=None, **extra):
    return {"tipo": "condicion", "campo": campo, "operador": op, "valor": valor, **extra}


def _y(*hijos):
    return {"tipo": "grupo", "op": "and", "hijos": list(hijos)}


def _politica(db, reglas, *, org=ORG, nombre="P", prioridad=100):
    pid = str(uuid.uuid4())
    p = Politica(id=pid, familia_id=pid, version=1, estado="publicada", dominio="gastos", nombre=nombre,
                 prioridad=prioridad, activa=True, organization_id=org)
    for i, r in enumerate(reglas):
        p.reglas.append(ReglaDePolitica(
            id=str(uuid.uuid4()), organization_id=org, orden=i + 1, nombre=r.get("nombre", f"R{i + 1}"), activa=True,
            detener=False, condicion=json.dumps(r["condicion"]) if r.get("condicion") else None,
            resultados=json.dumps(r.get("resultados", [])), exceso=json.dumps(r["exceso"]) if r.get("exceso") else None))
    db.add(p)
    db.commit()
    motor.invalidar(org)
    return p


def _tabla_de_comidas(db):
    t = TablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, nombre="Comidas", dominio="gastos",
                          tipo_de_valor="importe", moneda="PLN")
    t.filas += [FilaDeTablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, pais="PL", valor=120, moneda="PLN"),
                FilaDeTablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, valor=40, moneda="EUR")]
    db.add(t)
    db.commit()
    return {"tipo": "tabla", "tabla_id": t.id}


def _politica_de_comidas(db):
    """Comida en Polonia ≤ tabla por asistente; ≤ 20 % → +1 nivel; > 20 % → +2."""
    ref = _tabla_de_comidas(db)
    return _politica(db, [{"nombre": "Comida", "condicion": _y(
        _cond("categoria", "eq", "meals"), _cond("importe_por_asistente", "pct_over", 0, referencia=ref)),
        "exceso": {"campo": "importe_por_asistente", "referencia": ref, "bandas": [
            {"desde": 0, "hasta": 20, "resultados": [{"tipo": "add_approval_levels", "niveles": 1}]},
            {"desde": 20, "hasta": None, "resultados": [{"tipo": "add_approval_levels", "niveles": 2}]}]}}])


def _jerarquia(db):
    db.query(User).filter(User.id == "dev-test-id").update({"manager_id": "pm-test-id"})
    db.query(User).filter(User.id == "pm-test-id").update({"manager_id": "admin-test-id"})
    db.commit()


def _flujo_con_responsable(client, admin_token):
    wf = create_workflow(client, admin_token)
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token), json={
        "step_order": 1, "name": "Responsable", "approver_type": "manager", "timeout_hours": 48})
    assert r.status_code == 200, r.text
    return wf


def _crear(client, token, importe, moneda="PLN", categoria="meals", pais="PL", ciudad="Krakow", **extra):
    r = client.post("/api/v1/expenses", headers=auth(token), json={
        "category": categoria, "description": "Comida con cliente", "amount": importe, "currency": moneda,
        "expense_date": DIA, "country": pais, "city": ciudad, "is_billable": False, **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _enviar(client, token, gid):
    return client.post(f"/api/v1/expenses/my/{gid}/submit", headers=auth(token))


def _solicitud(db, gid):
    db.expire_all()
    return db.query(ApprovalRequest).filter(ApprovalRequest.entity_id == gid).one()


def _anadidos(db, req):
    return sorted((s.approver_type, s.approver_level) for s in
                  db.query(ApprovalRequestStep).filter(ApprovalRequestStep.request_id == req.id).all())


# ── Aprobación graduada ──────────────────────────────────────────────────────

@pytest.mark.parametrize("importe,niveles", [(120, []), (132, [("manager_level", 2)]),
                                             (156, [("manager_level", 2), ("manager_level", 3)])])
def test_dentro_10_y_30_por_ciento_por_encima(client, admin_token, dev_token, db, importe, niveles):
    """En la tabla: solo el responsable del flujo. +10 %: un nivel más; +30 %: dos."""
    _jerarquia(db)
    _flujo_con_responsable(client, admin_token)
    _politica_de_comidas(db)
    g = _crear(client, dev_token, importe)
    r = _enviar(client, dev_token, g["id"])
    assert r.status_code == 200, r.text
    req = _solicitud(db, g["id"])
    assert req.status == "pending" and _anadidos(db, req) == niveles
    if niveles:
        assert json.loads(req.contexto)["_politica"]["exceso_pct"] == pytest.approx(importe / 1.2 - 100, abs=0.01)


def test_auto_aprobado_dentro_de_la_politica(client, admin_token, dev_token, db):
    _flujo_con_responsable(client, admin_token)
    _politica(db, [{"nombre": "Pequeño", "condicion": _cond("importe", "lte", {"cantidad": 50, "moneda": "PLN"}),
                    "resultados": [{"tipo": "auto_approve"}]}])
    g = _crear(client, dev_token, 40)
    assert _enviar(client, dev_token, g["id"]).status_code == 200
    req = _solicitud(db, g["id"])
    assert req.status == "approved" and db.get(Expense, g["id"]).status == ExpenseStatus.approved


def test_bloqueo_explicito_422_y_un_exceso_no_bloquea(client, admin_token, pm_token, dev_token, db):
    _politica_de_comidas(db)
    _politica(db, [{"nombre": "Alcohol", "condicion": _cond("descripcion", "contains", "alcohol"),
                    "resultados": [{"tipo": "block", "mensaje": "El alcohol no se reembolsa"}]}], nombre="Bloqueo")
    g = _crear(client, dev_token, 50, description="Cena con alcohol")
    r = _enviar(client, dev_token, g["id"])
    assert r.status_code == 422 and "El alcohol no se reembolsa" in r.text
    assert db.get(Expense, g["id"]).status == ExpenseStatus.draft
    # Un 200 % por encima de la tabla no bloquea: sin flujo se abre la solicitud solo con los niveles.
    _jerarquia(db)
    g = _crear(client, dev_token, 360)
    assert _enviar(client, dev_token, g["id"]).status_code == 200
    req = _solicitud(db, g["id"])
    assert req.workflow_id is None and _anadidos(db, req) == [("manager_level", 1), ("manager_level", 2)]
    # Revisar desde la pantalla de gastos saltaría los niveles: 409.
    r = client.post(f"/api/v1/expenses/{g['id']}/review", headers=auth(admin_token), json={"approved": True})
    assert r.status_code == 409, r.text
    # En la bandeja del responsable (nivel 1) aparece con el indicador de exceso y el origen del paso.
    bandeja = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(pm_token)).json()
    item = next(x for x in bandeja.get("items", bandeja.get("data", [])) if x["id"] == req.id)
    assert item["politica"]["exceso_pct"] == 200.0 and item["politica"]["niveles"] == 2
    assert item["step_origin"].startswith("P ·")


def test_conversion_pln_a_eur(client, dev_token, db):
    db.add(ExchangeRate(id=str(uuid.uuid4()), from_currency="PLN", to_currency="EUR", rate=0.23,
                        effective_date=date(2026, 10, 1), organization_id=ORG))
    db.commit()
    _politica(db, [{"nombre": "Más de 200 €", "condicion": _cond("importe", "gt", {"cantidad": 200, "moneda": "EUR"}),
                    "resultados": [{"tipo": "warn", "mensaje": "caro"}]}])
    caro = _crear(client, dev_token, 1000)         # 230 EUR
    barato = _crear(client, dev_token, 800)        # 184 EUR
    pre = client.get(f"/api/v1/expenses/{caro['id']}/policy-preview", headers=auth(dev_token)).json()["data"]
    assert pre["decision"] == "review" and pre["avisos"][0]["mensaje"] == "caro"
    traza = pre["explicacion"][0]["reglas"][0]["traza"][0]
    assert traza["convertido"] == {"cantidad": 230.0, "moneda": "EUR"}
    pre = client.get(f"/api/v1/expenses/{barato['id']}/policy-preview", headers=auth(dev_token)).json()["data"]
    assert pre["decision"] == "allow" and pre["puede_enviar"]
    assert _enviar(client, dev_token, caro["id"]).status_code == 200
    gasto = client.get("/api/v1/expenses/my", headers=auth(dev_token)).json()
    fila = next(x for x in gasto.get("items", gasto.get("data", [])) if x["id"] == caro["id"])
    assert fila["policy_flags"][0]["mensaje"] == "caro" and fila["policy_summary"]["decision"] == "review"


@pytest.mark.parametrize("asistentes,niveles,pct", [(3, 0, None), (2, 2, 25.0), (None, 2, 150.0)])
def test_comidas_por_asistente(client, dev_token, db, asistentes, niveles, pct):
    """300 PLN: con 3 asistentes son 100 por persona (≤ 120); con 2, 150 (+25 % → +2); sin dato, 1 (+150 %)."""
    _politica_de_comidas(db)
    g = _crear(client, dev_token, 300, attendees=asistentes)
    pre = client.get(f"/api/v1/expenses/{g['id']}/policy-preview", headers=auth(dev_token)).json()["data"]
    assert pre["niveles"] == niveles, pre
    if niveles:
        assert pre["excesos"][0]["exceso_pct"] == pct and pre["aprobacion"]["niveles_anadidos"] == [1, 2]


def test_tipo_de_documento_exigido(client, dev_token, db):
    _politica(db, [{"nombre": "Factura", "condicion": _cond("importe", "gt", {"cantidad": 100, "moneda": "PLN"}),
                    "resultados": [{"tipo": "require_attachment", "tipos_de_documento": ["invoice"],
                                    "mensaje": "Adjunta la factura"}]}])
    g = _crear(client, dev_token, 200)
    r = _enviar(client, dev_token, g["id"])
    assert r.status_code == 422 and r.json()["detail"]["requisitos"][0]["tipos_de_documento"] == ["invoice"]
    a = ExpenseAttachment(id=str(uuid.uuid4()), organization_id=ORG, expense_id=g["id"], filename="t.jpg",
                          storage_key="k", document_type="receipt")
    db.add(a)
    db.commit()
    assert _enviar(client, dev_token, g["id"]).status_code == 422          # un ticket no es la factura
    assert client.patch(f"/api/v1/expenses/attachments/{a.id}", headers=auth(dev_token),
                        json={"document_type": "factura-inventada"}).status_code == 422
    r = client.patch(f"/api/v1/expenses/attachments/{a.id}", headers=auth(dev_token), json={"document_type": "invoice"})
    assert r.status_code == 200 and r.json()["data"]["document_type"] == "invoice"
    assert _enviar(client, dev_token, g["id"]).status_code == 200


# ── Migración de expense_policies ────────────────────────────────────────────

def _migracion():
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "166_gastos_sobre_el_motor_de_politicas.py"
    spec = importlib.util.spec_from_file_location("m166", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_migracion_de_politicas_antiguas_conserva_el_comportamiento(client, dev_token, db):
    m = _migracion()
    conn = db.connection()
    conn.execute(sa.text(
        "CREATE TABLE expense_policies (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), nombre VARCHAR(200),"
        " categoria VARCHAR(30), limite_por_gasto FLOAT, limite_diario FLOAT, justificante_desde FLOAT,"
        " justificacion_desde FLOAT, accion VARCHAR(10), activa BOOLEAN, created_by VARCHAR(36), created_at TIMESTAMP)"))
    filas = [("p-bloq", "Comidas", "meals", 100, None, 50, None, "bloquear"),
             ("p-avisa", "Diario", None, None, 300, None, 20, "avisar")]
    for i, nombre, cat, tope, diario, just, expl, accion in filas:
        conn.execute(sa.text("INSERT INTO expense_policies VALUES (:i, :o, :n, :c, :t, :d, :j, :x, :a, 1, NULL, NULL)"),
                     dict(i=i, o=ORG, n=nombre, c=cat, t=tope, d=diario, j=just, x=expl, a=accion))
    assert m._datos(conn) == 2 and m._datos(conn) == 0          # idempotente
    db.commit()
    motor.invalidar(ORG)
    eur = dict(moneda="EUR", pais="ES", ciudad="Madrid")
    # bloquear + tope por gasto → 422 como antes
    g = _crear(client, dev_token, 120, **eur)
    r = _enviar(client, dev_token, g["id"])
    assert r.status_code == 422 and "tope de 100.00" in r.text
    # bloquear + justificante desde 50 → requisito: sin justificante no se envía
    g = _crear(client, dev_token, 60, **eur)
    assert _enviar(client, dev_token, g["id"]).status_code == 422
    db.add(ExpenseAttachment(id=str(uuid.uuid4()), organization_id=ORG, expense_id=g["id"], filename="t", storage_key="k"))
    db.commit()
    assert _enviar(client, dev_token, g["id"]).status_code == 200
    # avisar + tope diario 300 (todas las categorías) + justificación desde 20 → se envía marcado
    g = _crear(client, dev_token, 250, categoria="travel", notes=None, **eur)
    assert _enviar(client, dev_token, g["id"]).status_code == 200
    db.expire_all()
    mensajes = {x["mensaje"] for x in json.loads(db.get(Expense, g["id"]).policy_flags)["avisos_detalle"]}
    assert any("tope diario" in x for x in mensajes) and any("explicar" in x for x in mensajes)
    # downgrade: se rehace la fila con sus valores
    conn = db.connection()
    assert m._deshacer(conn) == 2
    vuelta = conn.execute(sa.text("SELECT limite_por_gasto, justificante_desde, accion, categoria FROM expense_policies "
                                  "WHERE id = 'p-bloq'")).one()
    assert tuple(vuelta) == (100.0, 50.0, "bloquear", "meals")
    conn.execute(sa.text("DROP TABLE expense_policies"))
    db.commit()


# ── Ejemplos, vista previa y empresa ─────────────────────────────────────────

def test_ejemplos_se_cargan_como_borrador_y_no_se_aplican(client, admin_token, dev_token, db):
    r = client.post("/api/v1/policies/examples/gastos", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["politicas_creadas"] == 4
    assert {p.estado for p in db.query(Politica).filter(Politica.dominio == "gastos").all()} == {"borrador"}
    assert client.post("/api/v1/policies/examples/gastos", headers=auth(admin_token)).json()["data"]["politicas_creadas"] == 0
    assert client.post("/api/v1/policies/examples/gastos", headers=auth(dev_token)).status_code == 403
    g = _crear(client, dev_token, 900)
    assert client.get(f"/api/v1/expenses/{g['id']}/policy-preview", headers=auth(dev_token)).json()["data"]["decision"] == "allow"


def test_aislamiento_por_empresa(client, dev_token, db, seed_multitenant):
    _politica(db, [{"nombre": "Todo", "resultados": [{"tipo": "block", "mensaje": "ajena"}]}], org="org-b-test")
    g = _crear(client, dev_token, 50)
    assert _enviar(client, dev_token, g["id"]).status_code == 200   # la de la otra empresa no aplica
    otro = Expense(id=str(uuid.uuid4()), organization_id="org-b-test", code="EXP-B", user_id="dev-test-id",
                   category="meals", description="x", amount=1, currency="EUR", expense_date=date(2026, 10, 7))
    db.add(otro)
    db.commit()
    assert client.get(f"/api/v1/expenses/{otro.id}/policy-preview", headers=auth(dev_token)).status_code == 404
