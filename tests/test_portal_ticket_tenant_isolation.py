"""Aislamiento multi-tenant de las rutas de ticket del PORTAL CLIENTE.

Auditoría de seguridad: las rutas de portal de `service_desk/tickets.py` autentican al
cliente con `require_portal_client(...)` dentro del cuerpo, pero algunas NO usan la
identidad del cliente para acotar el ticket:

- `POST /api/v1/sd/tickets/{id}/csat`            -> descarta el valor de retorno
- `POST /api/v1/sd/tickets/{id}/comments/client` -> usa get_ticket_or_404 (sin scoping)

Ambas resuelven el ticket solo por id, así que un cliente del portal podría actuar
sobre tickets de OTRO cliente. Estos tests fijan el comportamiento correcto: un
cliente no debe poder tocar un ticket cuyo requester_client_id no sea el suyo.

Contraste correcto en el mismo módulo: `client_ticket_detail_payload` filtra por
`Ticket.requester_client_id == client_id`.
"""

from tests.conftest import auth


def _create_project(client, token, code: str, name: str) -> str:
    res = client.post(
        "/api/v1/projects",
        json={
            "name": name,
            "code": code,
            "description": "Proyecto de auditoría",
            "status": "active",
            "billing_type": "time_material",
            "is_billable": True,
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


def _create_portal_client(client, token, project_ids, email: str, password: str) -> None:
    res = client.post(
        "/api/v1/portal/clients",
        json={
            "project_ids": project_ids,
            "full_name": f"Portal {email}",
            "email": email,
            "password": password,
            "can_request_changes": True,
            "language": "es",
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text


def _portal_login(client, email: str, password: str) -> None:
    res = client.post("/api/v1/portal/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def _setup_two_clients_and_victim_ticket(client, pm_token, db, resolve: bool = False):
    """Cliente A abre un ticket. Devuelve (ticket_id, creds del cliente B atacante).

    Si resolve=True, marca el ticket como resuelto directamente en la BD: el PATCH de
    agente interno acota por organización y no alcanza tickets creados desde el portal,
    y aquí lo que se audita son las rutas de portal, no ese scoping.
    """
    p_a = _create_project(client, pm_token, code="ISOA", name="Proyecto Cliente A")
    p_b = _create_project(client, pm_token, code="ISOB", name="Proyecto Cliente B")

    email_a, pwd_a = "iso.victim@test.com", "VictimPass123!"
    email_b, pwd_b = "iso.attacker@test.com", "AttackerPass123!"
    _create_portal_client(client, pm_token, [p_a], email_a, pwd_a)
    _create_portal_client(client, pm_token, [p_b], email_b, pwd_b)

    # Cliente A (víctima) abre un ticket desde su portal
    _portal_login(client, email_a, pwd_a)
    created = client.post(
        "/api/v1/sd/tickets/client",
        json={
            "title": "Incidencia del cliente A",
            "description": "Ticket que pertenece exclusivamente al cliente A",
            "ticket_type": "incident",
            "priority": "p3_medium",
        },
    )
    assert created.status_code in (200, 201), created.text
    ticket_id = created.json()["data"]["id"]

    if resolve:
        from app.models.service_desk import Ticket, TicketStatus

        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assert ticket is not None, "el ticket del cliente A no está en la BD de test"
        ticket.status = TicketStatus.resolved
        db.commit()

    return ticket_id, email_b, pwd_b


def test_portal_client_cannot_submit_csat_on_other_clients_ticket(client, pm_token, db):
    ticket_id, email_b, pwd_b = _setup_two_clients_and_victim_ticket(
        client, pm_token, db, resolve=True
    )

    # Cliente B (atacante) intenta puntuar el ticket del cliente A
    _portal_login(client, email_b, pwd_b)
    res = client.post(f"/api/v1/sd/tickets/{ticket_id}/csat", json={"score": 1, "comment": "sabotaje"})

    assert res.status_code in (403, 404), (
        "IDOR: un cliente del portal ha podido enviar CSAT sobre el ticket de otro "
        f"cliente (status={res.status_code}, body={res.text})"
    )


def test_portal_client_cannot_comment_on_other_clients_ticket(client, pm_token, db):
    ticket_id, email_b, pwd_b = _setup_two_clients_and_victim_ticket(
        client, pm_token, db
    )

    # Cliente B (atacante) intenta comentar públicamente en el ticket del cliente A
    _portal_login(client, email_b, pwd_b)
    res = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/comments/client",
        json={"body": "Comentario inyectado por otro cliente"},
    )

    assert res.status_code in (403, 404), (
        "IDOR: un cliente del portal ha podido comentar en el ticket de otro cliente "
        f"(status={res.status_code}, body={res.text})"
    )
