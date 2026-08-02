"""Aislamiento multi-tenant del wiki expuesto al PORTAL DE CLIENTE.

Auditoría de seguridad (2ª pasada): `GET /api/v1/portal/wiki/pages` y
`GET /api/v1/portal/wiki/pages/{page_id}` autentican correctamente al cliente vía
`Depends(get_current_client)`, pero las funciones de servicio que hay detrás
—`portal_wiki_pages(db)` y `portal_wiki_page_detail(page_id, db)`— **ni siquiera
reciben el cliente**. Filtran solo por `visibility == "portal"`.

`WikiPage` y `WikiSpace` tienen `organization_id` y `project_id`, así que el wiki es
un recurso con tenencia. Sin acotarlo, cualquier cliente del portal puede enumerar y
leer el wiki de portal de CUALQUIER otra organización: el listado le entrega los ids
y el detalle le entrega el contenido.

Es la misma clase de fallo que los IDOR de CSAT y comentarios (auditoría 1), pero de
lectura y sin necesidad de adivinar ningún identificador.
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


def _seed_victim_wiki_page(db, project_id: str) -> tuple[str, str]:
    """Página wiki visible en portal que pertenece SOLO al proyecto de la víctima."""
    from app.models.epics import WikiPage, WikiSpace

    space = WikiSpace(
        project_id=project_id,
        name="Espacio Cliente A",
        slug="espacio-cliente-a-iso",
        is_active=True,
    )
    db.add(space)
    db.flush()

    page = WikiPage(
        space_id=space.id,
        title="Runbook confidencial del cliente A",
        slug="runbook-confidencial-a",
        content="Credenciales y procedimientos internos del cliente A",
        content_text="Credenciales y procedimientos internos del cliente A",
        visibility="portal",
        is_published=True,
        is_active=True,
    )
    db.add(page)
    db.commit()
    return page.id, page.title


def _setup(client, pm_token, db):
    p_a = _create_project(client, pm_token, code="WIKA", name="Proyecto Cliente A")
    p_b = _create_project(client, pm_token, code="WIKB", name="Proyecto Cliente B")

    email_a, pwd_a = "wiki.victim@test.com", "VictimPass123!"
    email_b, pwd_b = "wiki.attacker@test.com", "AttackerPass123!"
    _create_portal_client(client, pm_token, [p_a], email_a, pwd_a)
    _create_portal_client(client, pm_token, [p_b], email_b, pwd_b)

    page_id, page_title = _seed_victim_wiki_page(db, p_a)
    return page_id, page_title, (email_a, pwd_a), (email_b, pwd_b)


def test_portal_client_still_sees_own_wiki_page(client, pm_token, db):
    """Contrapeso: acotar por tenencia no debe romper el caso legítimo.

    Sin este test, "arreglar" la fuga devolviendo siempre vacío también pasaría.
    """
    page_id, page_title, (email_a, pwd_a), _ = _setup(client, pm_token, db)

    _portal_login(client, email_a, pwd_a)

    listed = client.get("/api/v1/portal/wiki/pages")
    assert listed.status_code == 200, listed.text
    assert page_id in [p["id"] for p in listed.json()["items"]], (
        "El cliente propietario ha dejado de ver su propia página de wiki"
    )

    detail = client.get(f"/api/v1/portal/wiki/pages/{page_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["title"] == page_title


def test_portal_client_cannot_list_other_clients_wiki_pages(client, pm_token, db):
    page_id, page_title, _, (email_b, pwd_b) = _setup(client, pm_token, db)

    _portal_login(client, email_b, pwd_b)
    res = client.get("/api/v1/portal/wiki/pages")
    assert res.status_code == 200, res.text

    ids = [p["id"] for p in res.json()["items"]]
    assert page_id not in ids, (
        "Fuga cross-tenant: el listado de wiki del portal expone la página de otro "
        f"cliente ({page_title!r}). Devuelto: {res.json()['items']}"
    )


def test_portal_client_cannot_read_other_clients_wiki_page(client, pm_token, db):
    page_id, page_title, _, (email_b, pwd_b) = _setup(client, pm_token, db)

    _portal_login(client, email_b, pwd_b)
    res = client.get(f"/api/v1/portal/wiki/pages/{page_id}")

    assert res.status_code in (403, 404), (
        "Fuga cross-tenant: un cliente del portal ha leído el contenido de la página "
        f"wiki de otro cliente (status={res.status_code}, body={res.text})"
    )
