"""Motor común de políticas, reglas y flujos (tarea #26).

Lo que se mide: condiciones con conversión de moneda y bandas de exceso,
combinación determinista de resultados, niveles de aprobación añadidos a la
solicitud, pasos informar y ramas en paralelo del diseñador, simulador sin
efectos, aislamiento por empresa y guardas.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.billing_reports import ApprovalRequest, ApprovalRequestStep
from app.models.bookings import ExchangeRate
from app.models.enterprise import Notification
from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
from app.models.politicas import EvaluacionDePolitica, FilaDeTablaDeReferencia, Politica, TablaDeReferencia
from app.models.user import User
from app.services.politicas import motor, resultados as res
from tests.conftest import auth
from tests.test_approvals import create_workflow

ORG = "1"
DIA = date(2026, 10, 7)   # miércoles


def _gasto(db, importe, moneda="EUR", categoria=ExpenseCategory.meals, pais="ES", ciudad="Madrid",
           usuario="dev-test-id", estado=ExpenseStatus.submitted):
    e = Expense(id=str(uuid.uuid4()), organization_id=ORG, code=f"EXP-{uuid.uuid4().hex[:4]}", user_id=usuario,
                category=categoria, description="Comida", amount=importe, currency=moneda, expense_date=DIA,
                country=pais, city=ciudad, status=estado)
    db.add(e)
    db.commit()
    return e


def _cond(campo, op, valor=None, **extra):
    return {"tipo": "condicion", "campo": campo, "operador": op, "valor": valor, **extra}


def _politica(db, reglas, *, prioridad=100, estado="publicada", org=ORG, ambito=None, nombre="P"):
    import json
    from app.models.politicas import ReglaDePolitica
    pid = str(uuid.uuid4())
    p = Politica(id=pid, familia_id=pid, version=1, estado=estado, dominio="gastos", nombre=nombre,
                 prioridad=prioridad, activa=True, organization_id=org, ambito=json.dumps(ambito or {}))
    for i, r in enumerate(reglas):
        p.reglas.append(ReglaDePolitica(id=str(uuid.uuid4()), organization_id=org, orden=i + 1,
                                        nombre=r.get("nombre", f"R{i + 1}"), activa=True, detener=False,
                                        condicion=json.dumps(r.get("condicion")) if r.get("condicion") else None,
                                        resultados=json.dumps(r.get("resultados", [])),
                                        exceso=json.dumps(r["exceso"]) if r.get("exceso") else None))
    db.add(p)
    db.commit()
    motor.invalidar(org)
    return p


# ── Condiciones ──────────────────────────────────────────────────────────────

def test_importe_se_compara_tras_convertir_la_moneda_y_sin_tipo_queda_indeterminado(db):
    db.add(ExchangeRate(id=str(uuid.uuid4()), from_currency="USD", to_currency="EUR", rate=0.9,
                        effective_date=date(2026, 10, 1), organization_id=ORG))
    db.commit()
    _politica(db, [{"nombre": "Comida cara", "condicion": _cond("importe", "gt", {"cantidad": 150, "moneda": "EUR"}),
                    "resultados": [{"tipo": "warn", "mensaje": "cara"}]}])
    ev = motor.evaluar(db, "gastos", _gasto(db, 200, "USD"))       # 180 EUR > 150
    paso = ev["explicacion"][0]["reglas"][0]["traza"][0]
    assert ev["decision"] == "review" and paso["cumple"] is True
    assert paso["convertido"] == {"cantidad": 180.0, "moneda": "EUR"}
    assert motor.evaluar(db, "gastos", _gasto(db, 160, "USD"))["decision"] == "allow"   # 144 EUR
    # Sin tipo GBP→EUR: no se inventa 1:1; queda indeterminada y avisa (revisión humana).
    ev = motor.evaluar(db, "gastos", _gasto(db, 100, "GBP"))
    assert ev["explicacion"][0]["reglas"][0]["cumple"] is None
    assert ev["decision"] == "review" and "No se pudo evaluar" in ev["resultado"]["avisos"][0]["mensaje"]


def test_bandas_de_exceso_sobre_la_tabla_por_ciudad(db):
    t = TablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, nombre="Dietas", tipo_de_valor="importe",
                          moneda="EUR")
    t.filas += [FilaDeTablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, pais="ES", valor=40, moneda="EUR"),
                FilaDeTablaDeReferencia(id=str(uuid.uuid4()), organization_id=ORG, pais="ES", ciudad="Madrid",
                                        categoria="meals", valor=50, moneda="EUR")]
    db.add(t)
    db.commit()
    ref = {"tipo": "tabla", "tabla_id": t.id}
    _politica(db, [{"nombre": "Dieta", "condicion": _cond("importe", "pct_over", 0, referencia=ref),
                    "exceso": {"campo": "importe", "referencia": ref, "bandas": [
                        {"desde": 0, "hasta": 20, "resultados": [{"tipo": "add_approval_levels", "niveles": 1}]},
                        {"desde": 20, "hasta": None, "resultados": [{"tipo": "add_approval_levels", "niveles": 2}]}]}}])
    assert motor.evaluar(db, "gastos", _gasto(db, 50))["decision"] == "allow"          # en el tope
    ev = motor.evaluar(db, "gastos", _gasto(db, 60))                                   # +20 % -> banda 1
    assert ev["resultado"]["niveles"] == 1
    assert ev["explicacion"][0]["reglas"][0]["exceso"]["exceso_pct"] == 20.0
    assert motor.evaluar(db, "gastos", _gasto(db, 70))["resultado"]["niveles"] == 2    # +40 %
    # Barcelona usa la fila del país (40): 50 es +25 % -> banda 2.
    assert motor.evaluar(db, "gastos", _gasto(db, 50, ciudad="Barcelona"))["resultado"]["niveles"] == 2


def test_operadores_de_fecha_y_grupos_o_negados(db):
    arbol = {"tipo": "grupo", "op": "or", "hijos": [
        _cond("fecha", "weekday_in", [6, 7]),
        {"tipo": "grupo", "op": "and", "negar": True, "hijos": [_cond("categoria", "in", ["meals", "travel"])]}]}
    _politica(db, [{"condicion": arbol, "resultados": [{"tipo": "tag", "etiqueta": "revisar"}]}])
    assert motor.evaluar(db, "gastos", _gasto(db, 10))["resultado"]["etiquetas"] == []          # miércoles, comida
    assert motor.evaluar(db, "gastos", _gasto(db, 10, categoria=ExpenseCategory.software))["resultado"]["etiquetas"] == ["revisar"]


# ── Combinación ──────────────────────────────────────────────────────────────

def test_resolucion_de_conflictos_determinista():
    o1 = {"politica_id": "a", "politica": "A", "regla_id": "r1", "regla": "R1"}
    o2 = {"politica_id": "b", "politica": "B", "regla_id": "r2", "regla": "R2"}
    c = res.combinar([(o1, {"tipo": "add_approval_levels", "niveles": 1}),
                      (o2, {"tipo": "add_approval_levels", "niveles": 2}),
                      (o1, {"tipo": "set_field", "campo": "facturable", "valor": False}),
                      (o2, {"tipo": "set_field", "campo": "facturable", "valor": True}),
                      (o2, {"tipo": "auto_approve"})])
    assert (c["decision"], c["niveles"], c["campos"]["facturable"]["valor"]) == ("review", 2, False)
    assert res.combinar([(o1, {"tipo": "warn", "mensaje": "x"}), (o2, {"tipo": "auto_approve"})])["decision"] == "review"
    assert res.combinar([(o1, {"tipo": "auto_approve"})])["decision"] == "auto_approve"
    bloqueo = res.combinar([(o1, {"tipo": "add_approval_levels", "niveles": 3}), (o2, {"tipo": "block", "mensaje": "no"})])
    assert bloqueo["decision"] == "block"


# ── Integración con el motor de aprobaciones ─────────────────────────────────

def test_los_niveles_se_anaden_a_la_solicitud_y_los_decide_el_siguiente_responsable(client, admin_token, pm_token, db):
    db.query(User).filter(User.id == "dev-test-id").update({"manager_id": "pm-test-id"})
    db.query(User).filter(User.id == "pm-test-id").update({"manager_id": "admin-test-id"})
    db.commit()
    wf = create_workflow(client, admin_token)
    r = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", headers=auth(admin_token), json={
        "step_order": 1, "name": "Responsable", "approver_type": "manager", "timeout_hours": 48})
    assert r.status_code == 200, r.text
    from app.services.approval_engine import fuentes
    e = _gasto(db, 300)
    ev = {"decision": "review", "contexto": {"importe": {"cantidad": 300, "moneda": "EUR"}},
          "resultado": res.combinar([({"politica": "Dietas", "regla": "Exceso"},
                                      {"tipo": "add_approval_levels", "niveles": 1})])}
    fuentes.abrir(db, "expense", e.id, "Gasto", "dev-test-id", {"amount": 300}, evaluacion=ev)
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_id == e.id).one()
    extra = db.query(ApprovalRequestStep).filter(ApprovalRequestStep.request_id == req.id).one()
    assert (extra.approver_type, extra.approver_level, extra.step_order) == ("manager_level", 2, 2)
    assert "importe" in req.contexto
    # El responsable directo aprueba su paso; el siguiente (nivel 2 = admin) recibe el añadido.
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", headers=auth(pm_token), json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["data"]["current_step"] == 2, r.text
    bandeja = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(admin_token)).json()
    assert req.id in [x["id"] for x in bandeja.get("items", bandeja.get("data", []))]
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", headers=auth(admin_token), json={"decision": "approved"})
    assert r.json()["data"]["status"] == "approved", r.text


def test_disenador_paralelo_e_informar(client, admin_token, pm_token, db):
    wf = create_workflow(client, admin_token)
    paso = lambda nid, t, **d: {"id": nid, "type": t, "position": {"x": 0, "y": 0}, "data": d}  # noqa: E731
    diagrama = {"nodos": [paso("i", "start"), paso("aviso", "inform", nombre="RRHH", approver_type="role", approver_role="hr"),
                          paso("d", "split"),
                          paso("a", "approve", nombre="Admin", approver_type="role", approver_role="admin"),
                          paso("b", "approve", nombre="PM", approver_type="role", approver_role="pm"),
                          paso("u", "join"), paso("f", "end")],
                "aristas": [{"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(
                    [("i", "aviso"), ("aviso", "d"), ("d", "a"), ("d", "b"), ("a", "u"), ("b", "u"), ("u", "f")])]}
    r = client.put(f"/api/v1/approvals/workflows/{wf['id']}/diagram", headers=auth(admin_token), json=diagrama)
    assert r.status_code == 200 and r.json()["data"]["pasos"] == 3, r.text
    from app.services.approval_engine import fuentes
    fuentes.abrir(db, "expense", "g-1", "Gasto", "dev-test-id", {})
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_id == "g-1").one()
    assert req.current_step == 2   # la etapa 1 solo informa: se avisa y se pasa
    assert db.query(Notification).filter(Notification.user_id == "hr-test-id",
                                         Notification.resource_id == req.id).count() == 1
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", headers=auth(admin_token), json={"decision": "approved"})
    assert r.json()["data"]["status"] == "pending"     # falta la otra rama
    r = client.post(f"/api/v1/approvals/requests/{req.id}/decide", headers=auth(pm_token), json={"decision": "approved"})
    assert r.json()["data"]["status"] == "approved", r.text
    # Un diagrama roto no se guarda y dice qué nodo falla.
    diagrama["aristas"] = diagrama["aristas"][:-1]
    r = client.put(f"/api/v1/approvals/workflows/{wf['id']}/diagram", headers=auth(admin_token), json=diagrama)
    assert r.status_code == 422 and any(e["nodo"] == "u" for e in r.json()["detail"]["errors"])


# ── Simulador ────────────────────────────────────────────────────────────────

def test_el_simulador_no_tiene_efectos_y_dice_que_cambia(client, admin_token, db):
    for importe in (30, 80, 200):
        _gasto(db, importe)
    _politica(db, [{"condicion": _cond("importe", "gt", {"cantidad": 150, "moneda": "EUR"}),
                    "resultados": [{"tipo": "warn", "mensaje": "alto"}]}])
    r = client.post("/api/v1/policies", headers=auth(admin_token), json={
        "dominio": "gastos", "nombre": "Más estricta", "prioridad": 50, "reglas": [
            {"nombre": "Más de 50", "condicion": _cond("importe", "gt", {"cantidad": 50, "moneda": "EUR"}),
             "resultados": [{"tipo": "add_approval_levels", "niveles": 1}]}]})
    assert r.status_code == 200, r.text
    antes = [db.query(m).count() for m in (EvaluacionDePolitica, ApprovalRequestStep, Notification, ApprovalRequest)]
    r = client.post("/api/v1/policies/simulate", headers=auth(admin_token),
                    json={"politica_id": r.json()["data"]["id"], "ultimos": 10})
    assert r.status_code == 200, r.text
    sim = r.json()["data"]
    assert (sim["evaluadas"], sim["cambian"], sim["resumen_de_cambios"]["mas_aprobacion"]) == (3, 2, 2)
    db.expire_all()
    assert [db.query(m).count() for m in (EvaluacionDePolitica, ApprovalRequestStep, Notification, ApprovalRequest)] == antes


# ── Empresa, versiones y guardas ─────────────────────────────────────────────

def test_aislamiento_por_empresa(client, admin_token, db, seed_multitenant):
    ajena = _politica(db, [{"resultados": [{"tipo": "block", "mensaje": "no"}]}], org="org-b-test", nombre="Ajena")
    assert all(p["id"] != ajena.id for p in client.get("/api/v1/policies", headers=auth(admin_token)).json()["data"])
    assert client.get(f"/api/v1/policies/{ajena.id}", headers=auth(admin_token)).status_code == 404
    e = _gasto(db, 10)
    e.organization_id = "org-a-test"
    db.commit()
    assert motor.evaluar(db, "gastos", e)["decision"] == "allow"   # la de org B no aplica a org A


def test_versiones_publicar_retira_la_anterior_y_guardas(client, admin_token, dev_token, db):
    doc = {"dominio": "gastos", "nombre": "Viajes", "reglas": [
        {"nombre": "Todo", "resultados": [{"tipo": "tag", "etiqueta": "viaje"}]}]}
    v1 = client.post("/api/v1/policies", headers=auth(admin_token), json=doc).json()["data"]
    assert client.post(f"/api/v1/policies/{v1['id']}/publish", headers=auth(admin_token)).status_code == 200
    assert client.put(f"/api/v1/policies/{v1['id']}", headers=auth(admin_token), json=doc).status_code == 409
    v2 = client.post(f"/api/v1/policies/{v1['id']}/new-version", headers=auth(admin_token)).json()["data"]
    assert (v2["version"], v2["estado"]) == (2, "borrador")
    client.post(f"/api/v1/policies/{v2['id']}/publish", headers=auth(admin_token))
    historial = client.get(f"/api/v1/policies/{v2['id']}/history", headers=auth(admin_token)).json()["data"]
    assert [(h["version"], h["estado"]) for h in historial] == [(2, "publicada"), (1, "retirada")]
    malo = {**doc, "reglas": [{"nombre": "", "resultados": [{"tipo": "block"}]}]}
    r = client.post("/api/v1/policies/validate", headers=auth(admin_token), json=malo).json()["data"]
    assert not r["valida"] and {e["ruta"] for e in r["errores"]} >= {"reglas[0].nombre", "reglas[0].resultados[0]"}
    for metodo, url in (("post", "/api/v1/policies"), ("get", "/api/v1/policies"),
                        ("post", "/api/v1/policies/simulate"), ("put", f"/api/v1/policies/tables/{v1['id']}/rows")):
        assert getattr(client, metodo)(url, headers=auth(dev_token), **({"json": {}} if metodo != "get" else {})).status_code == 403
    e = _gasto(db, 10, usuario="pm-test-id")
    assert client.get(f"/api/v1/policies/explanations/gastos/{e.id}", headers=auth(dev_token)).status_code == 403


@pytest.mark.parametrize("pct,banda", [(0, None), (10, (0, 20)), (20, (0, 20)), (25, (20, None))])
def test_banda_limites(pct, banda):
    b = motor._banda([{"desde": 0, "hasta": 20}, {"desde": 20, "hasta": None}], pct)
    assert (None if b is None else (b["desde"], b["hasta"])) == banda
