"""Tests de Service Desk — tickets, SLA, categorías."""
from jose import jwt
from tests.conftest import auth
from app.core.config import settings
from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.service_desk import SLAPolicy, Ticket
from app.services.sla_service import get_client_from_token as _get_client_from_token


def test_get_client_from_token_valid(db):
    user = ClientUser(full_name="Cliente Prueba", email="cliente@test.com", is_active=True)
    db.add(user)
    db.commit()

    token = jwt.encode({"sub": user.id, "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")
    client_obj = _get_client_from_token(f"Bearer {token}", db)
    assert client_obj is not None
    assert client_obj.id == user.id


def test_get_client_from_token_invalid_token(db):
    client_obj = _get_client_from_token("Bearer invalid.token.value", db)
    assert client_obj is None


def test_get_client_from_token_wrong_claim_type(db):
    user = ClientUser(full_name="Cliente Prueba 2", email="cliente2@test.com", is_active=True)
    db.add(user)
    db.commit()

    token = jwt.encode({"sub": user.id, "type": "admin"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")
    client_obj = _get_client_from_token(f"Bearer {token}", db)
    assert client_obj is None


def test_list_tickets_requires_auth(client, db):
    res = client.get("/api/v1/sd/tickets")
    assert res.status_code in (401, 403)


def test_create_ticket(client, admin_token, db):
    res = client.post("/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Error en producción",
            "description": "El sistema se cae al guardar",
            "priority": "p2_high",
            "ticket_type": "incident"
        })
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data


def test_list_tickets(client, admin_token, db):
    res = client.get("/api/v1/sd/tickets", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    items = data if isinstance(data, list) else data.get("items", data.get("tickets", []))
    assert isinstance(items, list)


def test_ticket_detail(client, admin_token, db):
    create = client.post("/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={"title": "Test ticket", "description": "Detalle de test", "priority": "p4_low", "ticket_type": "incident"})
    assert create.status_code in (200, 201)
    tid = create.json()["data"]["id"]
    res = client.get(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["id"] == tid


def test_update_ticket_status(client, admin_token, db):
    create = client.post("/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={"title": "Ticket estado", "description": "Estado a actualizar", "priority": "p3_medium", "ticket_type": "incident"})
    assert create.status_code in (200, 201)
    tid = create.json()["data"]["id"]
    res = client.patch(f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={"status": "in_progress"})
    assert res.status_code == 200


def test_ticket_dynamic_fields_roundtrip(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Ticket con campos dinámicos",
            "description": "Prueba dinámica",
            "ticket_type": "incident",
            "dynamic_fields": {
                "affected_environment": "produccion",
                "business_impact_details": "caida parcial",
            },
        },
    )
    assert created.status_code in (200, 201)
    tid = created.json()["data"]["id"]

    detail = client.get(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token))
    assert detail.status_code == 200
    assert detail.json()["data"].get("dynamic_fields", {}).get("affected_environment") == "produccion"

    updated = client.patch(
        f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={
            "dynamic_fields": {
                "affected_environment": "preproduccion",
                "requested_due_date": "2026-06-01",
            },
        },
    )
    assert updated.status_code == 200

    detail_after = client.get(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token))
    assert detail_after.status_code == 200
    dyn = detail_after.json()["data"].get("dynamic_fields", {})
    assert dyn.get("affected_environment") == "preproduccion"
    assert dyn.get("requested_due_date") == "2026-06-01"


def test_update_ticket_status_legacy_waiting_client_maps_to_pending_client(client, admin_token, db):
    create = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={"title": "Ticket legacy waiting", "description": "legacy", "priority": "p3_medium", "ticket_type": "incident"},
    )
    assert create.status_code in (200, 201)
    tid = create.json()["data"]["id"]

    res = client.patch(
        f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={"status": "waiting_client"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "pending_client"


def test_update_ticket_status_legacy_pending_change_maps_to_pending_third(client, admin_token, db):
    create = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={"title": "Ticket legacy change", "description": "legacy", "priority": "p3_medium", "ticket_type": "incident"},
    )
    assert create.status_code in (200, 201)
    tid = create.json()["data"]["id"]

    res = client.patch(
        f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={"status": "pending_change"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "pending_third"


def test_add_comment_to_ticket(client, admin_token, db):
    create = client.post("/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={"title": "Ticket comentarios", "description": "Comentario test", "priority": "p4_low", "ticket_type": "incident"})
    tid = create.json()["data"]["id"]
    res = client.post(f"/api/v1/sd/tickets/{tid}/comments",
        headers=auth(admin_token),
        json={"body": "Investigando el problema"})
    assert res.status_code in (200, 201)


def test_list_categories(client, admin_token, db):
    res = client.get("/api/v1/sd/catalog", headers=auth(admin_token))
    assert res.status_code == 200


def test_list_sla_policies(client, admin_token, db):
    res = client.get("/api/v1/sd/sla-policies", headers=auth(admin_token))
    assert res.status_code == 200


def test_ai_suggest_response_endpoint(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "No puedo entrar al portal",
            "description": "Al iniciar sesión recibo error 500",
            "ticket_type": "incident",
        },
    )
    assert created.status_code in (200, 201)
    tid = created.json()["data"]["id"]

    res = client.post(
        f"/api/v1/sd/tickets/{tid}/ai-suggest",
        headers=auth(admin_token),
        json={"content": "cliente bloqueado, pedir logs y pasos de reproducción"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["ticket_id"] == tid
    # Sin proveedor de IA (la suite no tiene ninguno) el aviso ya no se entrega
    # como si fuera el borrador: llega aparte, en `ai_error` (revision 2026-11).
    assert data.get("draft") is None and data["ai_error"]


def test_split_ticket_creates_child_and_link(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Dos incidencias distintas",
            "description": "Problema A y B",
            "ticket_type": "incident",
        },
    )
    tid = created.json()["data"]["id"]

    split = client.post(
        f"/api/v1/sd/tickets/{tid}/split",
        headers=auth(admin_token),
        json={"title": "Incidencia B separada", "description": "Solo problema B"},
    )
    assert split.status_code in (200, 201)
    out = split.json()["data"]
    assert out["ok"] is True
    assert out.get("child_id")

    links = client.get(f"/api/v1/sd/tickets/{tid}/links", headers=auth(admin_token))
    assert links.status_code == 200
    assert any(l.get("ticket_id") == out["child_id"] for l in links.json()["items"])


def test_client_ticket_uses_client_sla_policy(client, admin_token, db):
    policy = SLAPolicy(name="Enterprise 4h", is_default=False, p1_response_hours=1, p1_resolution_hours=4)
    db.add(policy)
    db.flush()

    cli = Client(name="Acme", sla_policy_id=policy.id)
    db.add(cli)
    db.flush()

    cuser = ClientUser(
        full_name="Cliente Acme",
        email="cliente.acme@test.com",
        is_active=True,
        client_org_id=cli.id,
    )
    db.add(cuser)
    db.commit()

    client_token = jwt.encode({"sub": cuser.id, "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")

    created = client.post(
        "/api/v1/sd/tickets/client",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"title": "Ticket cliente", "description": "desc", "ticket_type": "incident"},
    )
    assert created.status_code in (200, 201)
    tid = created.json()["data"]["id"]

    t = db.query(Ticket).filter(Ticket.id == tid).first()
    assert t is not None
    assert t.sla_policy_id == policy.id


def test_portal_dynamic_forms_public_endpoint(client, db):
    cuser = ClientUser(
        full_name="Portal Dynamic User",
        email="portal.dynamic@test.com",
        is_active=True,
    )
    db.add(cuser)
    db.commit()

    client_token = jwt.encode({"sub": cuser.id, "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")
    res = client.get(
        "/api/v1/sd/dynamic-forms/public",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert isinstance(data.get("fields", []), list)


def test_client_ticket_dynamic_fields_roundtrip(client, db):
    cuser = ClientUser(
        full_name="Portal Dynamic Ticket",
        email="portal.dynamic.ticket@test.com",
        is_active=True,
    )
    db.add(cuser)
    db.commit()

    client_token = jwt.encode({"sub": cuser.id, "type": "client"}, settings.CLIENT_PORTAL_SECRET, algorithm="HS256")

    created = client.post(
        "/api/v1/sd/tickets/client",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "title": "Portal ticket con dynamic fields",
            "description": "Roundtrip portal",
            "ticket_type": "incident",
            "dynamic_fields": {
                "affected_environment": "produccion",
                "business_impact_details": "impacto portal",
            },
        },
    )
    assert created.status_code in (200, 201)
    tid = created.json()["data"]["id"]

    detail = client.get(
        f"/api/v1/sd/tickets/client/{tid}",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert detail.status_code == 200
    dyn = detail.json()["data"].get("dynamic_fields", {})
    assert dyn.get("affected_environment") == "produccion"
    assert dyn.get("business_impact_details") == "impacto portal"


def test_dynamic_forms_diff_and_context_options(client, admin_token, db):
    ctx = client.get(
        "/api/v1/sd/dynamic-forms/context-options",
        headers=auth(admin_token),
    )
    assert ctx.status_code == 200
    payload = ctx.json()["data"]
    assert "clients" in payload
    assert "services" in payload
    assert "cis" in payload

    diff = client.post(
        "/api/v1/sd/dynamic-forms/diff",
        headers=auth(admin_token),
        json={},
    )
    assert diff.status_code == 200
    out = diff.json()["data"]
    assert "summary" in out
    assert "fields" in out


def test_ticket_restore_pending_and_time_unit_dropdown_backend(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Ticket restore pending",
            "description": "Prueba restore pending + timelog unit",
            "ticket_type": "incident",
        },
    )
    assert created.status_code in (200, 201)
    tid = created.json()["data"]["id"]

    to_progress = client.patch(
        f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={"status": "in_progress"},
    )
    assert to_progress.status_code == 200

    to_pending = client.patch(
        f"/api/v1/sd/tickets/{tid}",
        headers=auth(admin_token),
        json={"status": "pending_client"},
    )
    assert to_pending.status_code == 200

    restored = client.post(
        f"/api/v1/sd/tickets/{tid}/restore-pending",
        headers=auth(admin_token),
    )
    assert restored.status_code == 200
    assert restored.json()["data"].get("restored") is True

    timelog = client.post(
        f"/api/v1/sd/tickets/{tid}/time-log",
        headers=auth(admin_token),
        json={"minutes": 2, "unit": "hours"},
    )
    assert timelog.status_code == 200
    assert timelog.json()["data"].get("logged_minutes") == 120


def test_public_status_and_embed_routes(client, db):
    res_status = client.get("/status")
    assert res_status.status_code == 200
    # Revisión 2026-11: la página va en el idioma de la empresa y se pinta con
    # su script, servido aparte por la CSP.
    assert "Estado del servicio" in res_status.text and "/status/page.js" in res_status.text
    assert client.get("/status/page.js").status_code == 200

    res_embed = client.get("/status/embed.js")
    assert res_embed.status_code == 200
    assert "Estado del servicio" in res_embed.text

    res_widget = client.get("/widget/ticket.js")
    assert res_widget.status_code == 200
    # Revisión 2026-11: el widget usa el token del formulario público (`data-form`).
    assert "data-form" in res_widget.text
