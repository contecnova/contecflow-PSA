"""
test_platform_flows.py — Pruebas de flujo completo de la plataforma.

Estos tests cubren ciclos de vida completos extremo-a-extremo para garantizar
que los distintos módulos del sistema interactúan correctamente entre sí.
No son pruebas unitarias: cada test atraviesa múltiples endpoints y verifica
que el estado del sistema es consistente en cada paso del flujo.

Flujos cubiertos:
  1. Ciclo completo de gasto (borrador → envío → aprobación → reembolso)
  2. Ciclo completo de ticket de service desk (crear → comentar → escalar → resolver → CSAT)
  3. Solicitud de cambio completa (borrador → envío → aprobación → implementación)
  4. Entrega de proyecto y rentabilidad (proyecto → tarea → horas → dashboard KPI)
  5. Ciclo de vida de riesgo (identificar → escalar → mitigar → cerrar)
  6. Portal de cliente: solicitud de funcionalidad (FR) → respuesta PM → decisión cliente

Notas sobre las rutas reales:
  - Service Desk: /api/v1/sd/tickets  (prefix="/sd")
  - Client Portal: /api/v1/portal/...  (prefix="/portal")
  - Deliverables: /api/v1/deliverables/{project_id}  (no /project/ prefix)
  - Risks: probability/impact son strings ("low","medium","high","very_high","critical")
  - Changes /implement returns {"message":...}, check via GET
  - Expenses /submit returns {"ok": True}, check via /my list
  - OKRs: POST /okrs  (create objective), POST /okrs/key-results  (add KR)
"""
from datetime import date, timedelta

from tests.conftest import auth


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_project(client, token, code, billing_type="time_material", billing_rate=100):
    res = client.post(
        "/api/v1/projects",
        json={
            "name": f"Flow {code}",
            "code": code,
            "status": "active",
            "billing_type": billing_type,
            "billing_rate": billing_rate,
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _make_task(client, token, project_id, title="Tarea test"):
    res = client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": project_id, "status": "todo", "priority": "medium"},
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


# ── 1. Ciclo completo de gasto ────────────────────────────────────────────────

def test_expense_full_lifecycle(client, admin_token, pm_token, dev_token, db):
    """Borrador → envío → aprobación por PM → reembolso."""
    project_id = _make_project(client, pm_token, "EXP-FLOW-01")

    # El desarrollador crea un gasto en borrador
    create = client.post(
        "/api/v1/expenses",
        json={
            "project_id": project_id,
            "description": "Hotel cliente",
            "amount": 185.50,
            "category": "travel",
            "expense_date": str(date.today()),
            "is_billable": True,
        },
        headers=auth(dev_token),
    )
    assert create.status_code in (200, 201), create.text
    exp_id = create.json()["id"]
    assert create.json()["status"] == "draft"

    # Envío para aprobación (returns {"ok": True})
    submit = client.post(f"/api/v1/expenses/my/{exp_id}/submit", headers=auth(dev_token))
    assert submit.status_code == 200, submit.text
    assert submit.json().get("ok") is True

    # Verificar que el estado cambió a 'submitted' vía listado
    my_expenses = client.get("/api/v1/expenses/my", headers=auth(dev_token))
    assert my_expenses.status_code == 200
    _my_body = my_expenses.json()
    _my_items = _my_body if isinstance(_my_body, list) else _my_body.get("items", [])
    exp_data = next(e for e in _my_items if e["id"] == exp_id)
    assert exp_data["status"] == "submitted"

    # El PM ve el gasto en la cola de pendientes
    pending = client.get("/api/v1/expenses/pending", headers=auth(pm_token))
    assert pending.status_code == 200
    ids = [e["id"] for e in pending.json()]
    assert exp_id in ids

    # PM aprueba el gasto
    review = client.post(
        f"/api/v1/expenses/{exp_id}/review",
        json={"approved": True, "notes": "Justificado"},
        headers=auth(pm_token),
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "approved"

    # Marcar como reembolsado
    reimburse = client.post(f"/api/v1/expenses/{exp_id}/reimburse", headers=auth(pm_token))
    assert reimburse.status_code == 200, reimburse.text
    # Verify final status via list
    my_expenses_after = client.get("/api/v1/expenses/my", headers=auth(dev_token))
    _after_body = my_expenses_after.json()
    _after_items = _after_body if isinstance(_after_body, list) else _after_body.get("items", [])
    exp_final = next(e for e in _after_items if e["id"] == exp_id)
    assert exp_final["status"] == "reimbursed"

    # El resumen del proyecto refleja el gasto
    summary = client.get(f"/api/v1/expenses/summary/{project_id}", headers=auth(pm_token))
    assert summary.status_code == 200
    data = summary.json()
    assert data["total"] >= 185.50
    assert data["count"] >= 1


def test_expense_rejected_can_be_recalled(client, pm_token, dev_token, db):
    """El empleado puede retirar un gasto enviado antes de que sea revisado."""
    project_id = _make_project(client, pm_token, "EXP-FLOW-02")

    create = client.post(
        "/api/v1/expenses",
        json={
            "project_id": project_id,
            "description": "Taxi reunión",
            "amount": 22.00,
            "category": "travel",
            "expense_date": str(date.today()),
        },
        headers=auth(dev_token),
    )
    assert create.status_code in (200, 201), create.text
    exp_id = create.json()["id"]

    # Enviar
    submit = client.post(f"/api/v1/expenses/my/{exp_id}/submit", headers=auth(dev_token))
    assert submit.status_code == 200
    assert submit.json().get("ok") is True

    # Retirar (recall — returns {"ok": True})
    recall = client.post(f"/api/v1/expenses/my/{exp_id}/recall", headers=auth(dev_token))
    assert recall.status_code == 200, recall.text
    assert recall.json().get("ok") is True

    # Verify status reverted to draft
    my_exp = client.get("/api/v1/expenses/my", headers=auth(dev_token))
    recalled = next(e for e in my_exp.json() if e["id"] == exp_id)
    assert recalled["status"] == "draft"


# ── 2. Ciclo completo de ticket de Service Desk ───────────────────────────────

def test_service_desk_ticket_full_lifecycle(client, admin_token, pm_token, db):
    """Crear → comentar → escalar → resolver → cerrar → CSAT."""
    # Crear ticket
    create = client.post(
        "/api/v1/sd/tickets",
        json={
            "title": "Error en integración de facturación",
            "description": "El módulo de facturación no genera el PDF correctamente",
            "ticket_type": "incident",
            "priority": "p2_high",
        },
        headers=auth(admin_token),
    )
    assert create.status_code in (200, 201), create.text
    ticket = create.json()
    ticket_id = ticket["id"]
    assert ticket["status"] in ("open", "new")

    # Asignar agente
    assign = client.patch(
        f"/api/v1/sd/tickets/{ticket_id}",
        json={"assigned_to_user_id": "admin-test-id"},
        headers=auth(admin_token),
    )
    assert assign.status_code == 200, assign.text

    # Añadir comentario interno
    comment = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/comments",
        json={"body": "Revisando logs del sistema", "is_internal": True},
        headers=auth(admin_token),
    )
    assert comment.status_code in (200, 201), comment.text

    # Registrar tiempo trabajado
    time_log = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/time-log",
        json={"minutes": 45, "description": "Diagnóstico inicial"},
        headers=auth(admin_token),
    )
    assert time_log.status_code in (200, 201), time_log.text

    # Escalar ticket (to_level son niveles de soporte: l1/l2/l3 — query params)
    escalate = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/escalate",
        params={"to_level": "l2", "reason": "Requiere revisión de arquitectura"},
        headers=auth(admin_token),
    )
    assert escalate.status_code in (200, 201), escalate.text

    # Resolver ticket
    resolve = client.patch(
        f"/api/v1/sd/tickets/{ticket_id}",
        json={"status": "resolved", "resolution_notes": "PDF regenerado tras reinicio del servicio"},
        headers=auth(admin_token),
    )
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["status"] == "resolved"

    # Cerrar ticket
    close = client.patch(
        f"/api/v1/sd/tickets/{ticket_id}",
        json={"status": "closed"},
        headers=auth(admin_token),
    )
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"
    # CSAT (client-side) is tested in portal flow tests


def test_service_desk_ticket_appears_in_my_queue(client, admin_token, db):
    """Un ticket asignado aparece en la cola personal del agente."""
    create = client.post(
        "/api/v1/sd/tickets",
        json={
            "title": "Problema de acceso",
            "description": "El usuario no puede iniciar sesión en el módulo de informes",
            "ticket_type": "incident",
            "priority": "p3_medium",
            "assigned_to_user_id": "admin-test-id",
        },
        headers=auth(admin_token),
    )
    assert create.status_code in (200, 201), create.text
    ticket_id = create.json()["id"]

    queue = client.get("/api/v1/sd/tickets/my-queue", headers=auth(admin_token))
    assert queue.status_code == 200
    ids = [t["id"] for t in queue.json()]
    assert ticket_id in ids


# ── 3. Solicitud de cambio — ciclo completo ───────────────────────────────────

def test_change_request_full_lifecycle(client, pm_token, admin_token, db):
    """Borrador → envío → aprobación PM → implementación → estado final."""
    project_id = _make_project(client, pm_token, "CR-FLOW-01")

    # Crear CR en borrador
    cr = client.post(
        f"/api/v1/changes/{project_id}",
        json={
            "title": "Ampliar scope de integración Jira",
            "description": "Añadir sincronización bidireccional de comentarios",
            "impact": "medium",
            "estimated_hours": 16,
        },
        headers=auth(pm_token),
    )
    assert cr.status_code in (200, 201), cr.text
    cr_id = cr.json()["id"]
    assert cr.json()["status"] == "draft"

    # Enviar para revisión
    submit = client.post(
        f"/api/v1/changes/{project_id}/{cr_id}/submit",
        headers=auth(pm_token),
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "submitted"

    # Aparece en la lista de pendientes globales
    pending = client.get("/api/v1/changes/all/pending", headers=auth(admin_token))
    assert pending.status_code == 200
    ids = [c["id"] for c in pending.json()]
    assert cr_id in ids

    # Admin aprueba la CR
    review = client.post(
        f"/api/v1/changes/{project_id}/{cr_id}/review",
        json={"approved": True, "resolution_notes": "Aprobado en reunión de comité"},
        headers=auth(admin_token),
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "approved"

    # Marcar como implementada (returns {"message": "CR marcada como implementada"})
    implement = client.post(
        f"/api/v1/changes/{project_id}/{cr_id}/implement",
        headers=auth(admin_token),
    )
    assert implement.status_code == 200, implement.text
    assert "implementada" in implement.json().get("message", "").lower()


def test_change_request_rejection_flow(client, pm_token, admin_token, db):
    """Una CR rechazada queda en estado 'rejected' y no puede implementarse."""
    project_id = _make_project(client, pm_token, "CR-FLOW-02")

    cr = client.post(
        f"/api/v1/changes/{project_id}",
        json={
            "title": "Rediseño completo de UI",
            "description": "Cambio estético sin valor de negocio claro",
        },
        headers=auth(pm_token),
    )
    cr_id = cr.json()["id"]

    client.post(f"/api/v1/changes/{project_id}/{cr_id}/submit", headers=auth(pm_token))

    review = client.post(
        f"/api/v1/changes/{project_id}/{cr_id}/review",
        json={"approved": False, "resolution_notes": "No alineado con objetivos del proyecto"},
        headers=auth(admin_token),
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "rejected"

    # Intentar implementar una CR rechazada debe fallar
    implement = client.post(
        f"/api/v1/changes/{project_id}/{cr_id}/implement",
        headers=auth(admin_token),
    )
    assert implement.status_code in (400, 409, 422), \
        f"Implementar CR rechazada debería fallar, recibido: {implement.status_code}"


# ── 4. Entrega de proyecto y rentabilidad ─────────────────────────────────────

def test_project_delivery_and_profitability_flow(client, pm_token, dev_token, db):
    """Proyecto → tarea → imputaciones → rentabilidad → dashboard KPI."""
    project_id = _make_project(client, pm_token, "PROF-FLOW-01")

    # Añadir miembro al proyecto
    client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": "dev-test-id", "role": "developer"},
        headers=auth(pm_token),
    )

    # Crear tarea
    task_id = _make_task(client, pm_token, project_id, "Desarrollo módulo de pagos")

    # Desarrollador registra horas durante 3 días
    today = date.today()
    for i in range(3):
        work_day = today - timedelta(days=i)
        imp = client.post(
            "/api/v1/imputations",
            json={
                "project_id": project_id,
                "task_id": task_id,
                "date": str(work_day),
                "hours": 8,
                "description": f"Trabajo día {i+1}",
                "is_billable": True,
            },
            headers=auth(dev_token),
        )
        assert imp.status_code in (200, 201), f"Día {i+1}: {imp.text}"

    # Verificar rentabilidad del proyecto
    profitability = client.get(
        f"/api/v1/profitability/{project_id}",
        headers=auth(pm_token),
    )
    assert profitability.status_code == 200, profitability.text
    data = profitability.json()
    assert data["total_hours"] >= 24
    assert data["billable_hours"] >= 24

    # Verificar dashboard global (projects-health es accesible a PMs)
    dashboard = client.get("/api/v1/dashboard/projects-health", headers=auth(pm_token))
    assert dashboard.status_code == 200
    assert isinstance(dashboard.json(), list)


def test_project_full_crud_lifecycle(client, pm_token, admin_token, db):
    """Crear → actualizar → verificar miembros → cerrar proyecto."""
    # Crear
    create = client.post(
        "/api/v1/projects",
        json={
            "name": "Proyecto ciclo completo",
            "code": "CRUD-FLOW-01",
            "status": "active",
            "billing_type": "fixed_price",
            "contract_amount": 25000,
        },
        headers=auth(pm_token),
    )
    assert create.status_code in (200, 201), create.text
    pid = create.json()["id"]

    # Actualizar descripción y fechas
    update = client.patch(
        f"/api/v1/projects/{pid}",
        json={"description": "Descripción actualizada", "start_date": str(date.today())},
        headers=auth(pm_token),
    )
    assert update.status_code == 200, update.text

    # Listar proyectos — debe aparecer
    lst = client.get("/api/v1/projects", headers=auth(pm_token))
    assert lst.status_code == 200
    _lst_body = lst.json()
    _lst_items = _lst_body if isinstance(_lst_body, list) else _lst_body.get("items", [])
    ids = [p["id"] for p in _lst_items]
    assert pid in ids

    # Añadir miembro
    add_member = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": "dev-test-id", "role": "developer"},
        headers=auth(pm_token),
    )
    assert add_member.status_code in (200, 201), add_member.text

    # Cerrar proyecto
    close_res = client.patch(
        f"/api/v1/projects/{pid}",
        json={"status": "completed"},
        headers=auth(pm_token),
    )
    assert close_res.status_code == 200, close_res.text
    assert close_res.json()["status"] == "completed"


# ── 5. Ciclo de vida de riesgo ────────────────────────────────────────────────

def test_risk_lifecycle_identify_mitigate_close(client, pm_token, admin_token, db):
    """Identificar riesgo crítico → actualizar mitigación → cerrar."""
    project_id = _make_project(client, pm_token, "RISK-FLOW-01")

    # Crear riesgo alto — probability/impact son strings
    # score = PROB_SCORE["high"] * IMPACT_SCORE["critical"] = 0.7 * 5 = 3.5
    create = client.post(
        f"/api/v1/risks/{project_id}",
        json={
            "title": "Dependencia de proveedor externo sin SLA garantizado",
            "description": "El proveedor no tiene SLA formal y puede causar retrasos",
            "category": "external",
            "probability": "high",
            "impact": "critical",
            "mitigation_plan": "Negociar SLA formal antes de fin de mes",
        },
        headers=auth(pm_token),
    )
    assert create.status_code in (200, 201), create.text
    risk = create.json()
    risk_id = risk["id"]
    # score es float: 0.7 × 5 = 3.5
    assert risk["risk_score"] == 3.5

    # Actualizar plan de mitigación (RiskStatus: mitigating, not mitigated)
    update = client.patch(
        f"/api/v1/risks/{project_id}/{risk_id}",
        json={
            "mitigation_plan": "SLA firmado. Añadir proveedor de respaldo.",
            "status": "mitigating",
        },
        headers=auth(pm_token),
    )
    assert update.status_code == 200, update.text
    assert update.json()["status"] == "mitigating"

    # Verificar que el riesgo aparece en el portafolio
    portfolio = client.get("/api/v1/risks/all/portfolio", headers=auth(admin_token))
    assert portfolio.status_code == 200
    risk_ids = [r["id"] for r in portfolio.json()]
    assert risk_id in risk_ids

    # Cerrar riesgo
    close = client.patch(
        f"/api/v1/risks/{project_id}/{risk_id}",
        json={"status": "closed"},
        headers=auth(pm_token),
    )
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"


def test_multiple_risks_scored_and_sorted(client, pm_token, db):
    """Múltiples riesgos tienen puntuaciones float distintas calculadas correctamente."""
    # PROB_SCORE: very_low=0.05, low=0.2, medium=0.5, high=0.7, very_high=0.9
    # IMPACT_SCORE: negligible=1, minor=2, moderate=3, major=4, critical=5
    project_id = _make_project(client, pm_token, "RISK-FLOW-02")

    risk_configs = [
        # low(0.2) × minor(2) = 0.4
        {"title": "Riesgo bajo", "probability": "low", "impact": "minor", "expected_score": 0.4},
        # medium(0.5) × moderate(3) = 1.5
        {"title": "Riesgo medio", "probability": "medium", "impact": "moderate", "expected_score": 1.5},
        # very_high(0.9) × critical(5) = 4.5
        {"title": "Riesgo crítico", "probability": "very_high", "impact": "critical", "expected_score": 4.5},
    ]

    for cfg in risk_configs:
        res = client.post(
            f"/api/v1/risks/{project_id}",
            json={
                "title": cfg["title"],
                "description": f"Descripción de {cfg['title']}",
                "probability": cfg["probability"],
                "impact": cfg["impact"],
            },
            headers=auth(pm_token),
        )
        assert res.status_code in (200, 201), res.text
        assert res.json()["risk_score"] == cfg["expected_score"]

    # Listar todos los riesgos del proyecto (returns {"risks": [...], "summary": {...}})
    lst = client.get(f"/api/v1/risks/{project_id}", headers=auth(pm_token))
    assert lst.status_code == 200
    assert len(lst.json()["risks"]) >= 3


# ── 6. Portal de cliente — Solicitud de Funcionalidad completa ────────────────

def test_client_portal_fr_lifecycle(client, pm_token, admin_token, db):
    """
    Flujo completo del portal de cliente:
    PM crea acceso de cliente → cliente envía FR → PM responde con estimación
    → cliente aprueba la propuesta.

    NOTA: Login del portal establece cookie portal_access_token en el TestClient.
    Los endpoints de portal usan get_current_client que acepta esa cookie.
    """
    project_id = _make_project(client, pm_token, "PORTAL-FLOW-01")

    # PM crea acceso para el cliente en el portal
    portal_client_resp = client.post(
        "/api/v1/portal/clients",
        json={
            "full_name": "Ana García",
            "email": "ana.garcia.portal@cliente.com",
            "password": "SecurePass123!",
            "project_id": project_id,
            "can_approve_deliverables": True,
            "can_request_changes": True,
            "can_view_budget": False,
        },
        headers=auth(pm_token),
    )
    assert portal_client_resp.status_code in (200, 201), portal_client_resp.text

    # Cliente se autentica — responde {"ok": True, "client": {...}} y setea cookie
    login = client.post(
        "/api/v1/portal/auth/login",
        json={"email": "ana.garcia.portal@cliente.com", "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    # Cookie portal_access_token es seteada automáticamente por TestClient

    # Cliente envía una Feature Request (sin header extra, usa cookie)
    fr = client.post(
        "/api/v1/portal/feature-requests",
        json={
            "title": "Añadir exportación a Excel del dashboard",
            "description": "Necesitamos poder exportar los datos del dashboard de proyectos a Excel para presentaciones directivas",
            "business_justification": "Agiliza los reportes mensuales al comité de dirección",
            "priority": "high",
            "project_id": project_id,
        },
    )
    assert fr.status_code in (200, 201), fr.text
    fr_data = fr.json()
    fr_id = fr_data["id"]
    assert fr_data["status"] in ("pending", "new", "submitted")

    # El equipo interno ve las FRs pendientes
    team_frs = client.get("/api/v1/portal/feature-requests/team", headers=auth(pm_token))
    assert team_frs.status_code == 200
    fr_ids = [f["id"] for f in team_frs.json()]
    assert fr_id in fr_ids

    # PM responde con estimación
    response = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={
            "pm_response": "Factible en el sprint Q2. Estimamos 20h de desarrollo.",
            "estimated_hours": 20,
            "estimated_cost": 2000,
            "estimated_delivery_weeks": 4,
            "status": "estimated",
        },
        headers=auth(pm_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "estimated"

    # Cliente aprueba la propuesta (usa cookie)
    decision = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/decide",
        json={"approved": True, "reason": "Excelente propuesta, procedemos"},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"


def test_client_portal_fr_rejected_by_client(client, pm_token, db):
    """El cliente puede rechazar una propuesta de FR con motivo."""
    project_id = _make_project(client, pm_token, "PORTAL-FLOW-02")

    # Crear cliente de portal
    portal_client_resp = client.post(
        "/api/v1/portal/clients",
        json={
            "full_name": "Carlos López",
            "email": "carlos.lopez.portal@empresa.com",
            "password": "SecurePass456!",
            "project_id": project_id,
        },
        headers=auth(pm_token),
    )
    assert portal_client_resp.status_code in (200, 201), portal_client_resp.text

    login = client.post(
        "/api/v1/portal/auth/login",
        json={"email": "carlos.lopez.portal@empresa.com", "password": "SecurePass456!"},
    )
    assert login.status_code == 200, login.text
    # Cookie seteada automáticamente

    fr = client.post(
        "/api/v1/portal/feature-requests",
        json={
            "title": "Cambio de colores corporativos en todos los módulos",
            "description": "Actualizar paleta de colores a los nuevos estándares de marca",
            "priority": "medium",
            "project_id": project_id,
        },
    )
    assert fr.status_code in (200, 201), fr.text
    fr_id = fr.json()["id"]

    # PM responde
    client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={
            "pm_response": "Implementable pero costoso: 80h de diseño.",
            "estimated_hours": 80,
            "estimated_cost": 8000,
            "status": "estimated",
        },
        headers=auth(pm_token),
    )

    # Cliente rechaza por coste (usa cookie)
    decision = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/decide",
        json={"approved": False, "reason": "El coste supera el presupuesto disponible"},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "rejected"


# ── 7. Flujo de entrega con entregable y aprobación cliente ───────────────────

def test_deliverable_client_approval_flow(client, pm_token, db):
    """Crear entregable → marcar como listo → verificar en lista del proyecto."""
    project_id = _make_project(client, pm_token, "DELIV-FLOW-01")

    # Crear entregable — POST /{project_id}, sin project_id ni due_date en body
    deliv = client.post(
        f"/api/v1/deliverables/{project_id}",
        json={
            "name": "Documento de requisitos v1.0",
            "description": "Especificación funcional completa del módulo de pagos",
            "planned_date": str(date.today() + timedelta(days=14)),
        },
        headers=auth(pm_token),
    )
    assert deliv.status_code in (200, 201), deliv.text
    deliv_id = deliv.json()["id"]

    # Marcar como listo para revisión — PATCH /{project_id}/{del_id}
    ready = client.patch(
        f"/api/v1/deliverables/{project_id}/{deliv_id}",
        json={"status": "in_review"},  # DeliverableStatus enum: in_review not review
        headers=auth(pm_token),
    )
    assert ready.status_code == 200, ready.text

    # Listar entregables del proyecto — GET /{project_id} returns {"deliverables": [...]}
    lst = client.get(f"/api/v1/deliverables/{project_id}", headers=auth(pm_token))
    assert lst.status_code == 200
    ids = [d["id"] for d in lst.json()["deliverables"]]
    assert deliv_id in ids


# ── 8. Flujo de OKR con progreso ──────────────────────────────────────────────

def test_okr_full_progress_flow(client, admin_token, db):
    """Crear objetivo → añadir key result → actualizar progreso → verificar completion."""
    # Crear objetivo — POST /api/v1/okrs  (status_code=201, returns {id, title})
    obj = client.post(
        "/api/v1/okrs",
        json={
            "title": "Alcanzar 95% de satisfacción de clientes en Q2",
            "description": "Mejorar NPS y CSAT en todos los proyectos activos",
            "period": "Q2",
            "year": 2025,  # list endpoint defaults to year=2025
            "owner_id": "admin-test-id",
        },
        headers=auth(admin_token),
    )
    assert obj.status_code == 201, obj.text
    obj_id = obj.json()["id"]

    # Añadir key result — POST /api/v1/okrs/key-results con objective_id en body
    kr = client.post(
        "/api/v1/okrs/key-results",
        json={
            "objective_id": obj_id,
            "title": "CSAT promedio >= 4.5/5",
            "target_value": 4.5,
            "current_value": 3.8,
            "unit": "score",
        },
        headers=auth(admin_token),
    )
    assert kr.status_code == 201, kr.text
    kr_id = kr.json()["id"]

    # Registrar progreso — {"value": ..., "note": ...}  (status_code=201)
    checkin = client.post(
        f"/api/v1/okrs/key-results/{kr_id}/checkin",
        json={"value": 4.2, "note": "Mejora tras nuevo proceso de onboarding"},
        headers=auth(admin_token),
    )
    assert checkin.status_code == 201, checkin.text
    assert checkin.json()["current_value"] == 4.2

    # Verificar objetivo aparece en la lista (year=2025 is the default)
    obj_list = client.get("/api/v1/okrs?year=2025", headers=auth(admin_token))
    assert obj_list.status_code == 200
    obj_ids = [o["id"] for o in obj_list.json()]
    assert obj_id in obj_ids


# ── 9. Flujo de aprobación de ausencia y conflicto de planificación ───────────

def test_absence_approved_blocks_capacity_planning(client, pm_token, dev_token, db):
    """Ausencia aprobada bloquea la planificación de capacidad para ese usuario y semana."""
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7)

    # Dev solicita vacaciones
    absence = client.post(
        "/api/v1/absences/my",
        json={
            "type": "vacation",
            "start_date": str(monday),
            "end_date": str(monday + timedelta(days=4)),
            "reason": "Vacaciones de verano",
        },
        headers=auth(dev_token),
    )
    assert absence.status_code in (200, 201), absence.text
    absence_id = absence.json()["id"]

    # PM aprueba la ausencia
    approve = client.post(
        f"/api/v1/absences/{absence_id}/review",
        json={"approved": True},
        headers=auth(pm_token),
    )
    assert approve.status_code in (200, 201), approve.text

    # Intentar planificar capacidad del dev en esa semana debe fallar
    blocked = client.post(
        "/api/v1/capacity/plans",
        json={
            "user_id": "dev-test-id",
            "week_start": str(monday),
            "planned_hours": 40,
        },
        headers=auth(pm_token),
    )
    assert blocked.status_code in (409, 422), \
        f"Planificar capacidad con ausencia aprobada debería fallar: {blocked.status_code}"


# ── 10. Verificación de acceso y seguridad básica ────────────────────────────

def test_unauthenticated_access_denied_across_modules(client, db):
    """Todos los módulos críticos requieren autenticación."""
    protected_endpoints = [
        ("GET", "/api/v1/projects"),
        ("GET", "/api/v1/tasks"),
        ("GET", "/api/v1/imputations"),
        ("GET", "/api/v1/timesheets/pending"),
        ("GET", "/api/v1/expenses/pending"),
        ("GET", "/api/v1/risks/all/portfolio"),
        ("GET", "/api/v1/sd/tickets"),
        ("GET", "/api/v1/milestones/dashboard/pending"),
        ("GET", "/api/v1/changes/all/pending"),
        ("GET", "/api/v1/okrs"),
        ("GET", "/api/v1/dashboard/kpis"),
    ]

    for method, endpoint in protected_endpoints:
        if method == "GET":
            res = client.get(endpoint)
        else:
            res = client.post(endpoint)
        assert res.status_code in (401, 403), \
            f"{method} {endpoint} debería requerir auth, recibido: {res.status_code}"


def test_employee_cannot_access_admin_endpoints(client, dev_token, db):
    """Un empleado no puede acceder a endpoints de administración."""
    # GET /api/v1/users is accessible to all internal users (require_internal_user)
    # Only truly admin-only endpoints should be tested here
    admin_only_endpoints = [
        ("GET", "/api/v1/settings/log-level"),  # requires require_admin
        ("GET", "/api/v1/dashboard/kpis"),      # requires require_admin
    ]

    for method, endpoint in admin_only_endpoints:
        res = client.get(endpoint, headers=auth(dev_token))
        assert res.status_code in (403, 401), \
            f"{endpoint}: employee no debería poder acceder, recibido: {res.status_code}"
