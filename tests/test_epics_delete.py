"""
test_epics_delete.py — DELETE endpoint tests for the epics router (audit #93).

Cubre los endpoints DELETE de /api/v1/epics/* que carecían de cobertura:
  - /api/v1/epics/wiki/spaces/{space_id}
  - /api/v1/epics/wiki/pages/{page_id}
  - /api/v1/epics/filters/{filter_id}
  - /api/v1/epics/comments/{comment_id}        (threaded comments)
  - /api/v1/epics/{epic_id}

Patrón ABAC + concealment: cada test crea el recurso vía POST, lo elimina vía
DELETE y verifica que (a) la respuesta es 200, y (b) el recurso ya no aparece
en el listado correspondiente (soft-delete con is_active=False).
"""
from tests.conftest import auth


def _create_project(client, token, name="Epics Test Project"):
    res = client.post(
        "/api/v1/projects",
        json={
            "name": name,
            "code": "ETP",
            "status": "active",
            "project_type": "development",
            "billing_type": "time_material",
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]  # /projects no migrado: dict crudo


def _create_wiki_space(client, token, slug="ws-delete-test"):
    res = client.post(
        "/api/v1/epics/wiki/spaces",
        json={
            "name": "Wiki Space Delete Test",
            "slug": slug,
            "description": "Espacio para test de borrado",
            "is_public": False,
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


# ── 1. DELETE /wiki/spaces/{space_id} ──────────────────────────────────────────

def test_delete_wiki_space_hides_from_listing(client, admin_token, db):
    space_id = _create_wiki_space(client, admin_token)

    deleted = client.delete(
        f"/api/v1/epics/wiki/spaces/{space_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["ok"] is True

    # Concealment: ya no debe aparecer en el listado de espacios.
    listed = client.get("/api/v1/epics/wiki/spaces", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(s["id"] != space_id for s in listed.json()["items"])

    # Soft-delete: la fila sigue en BD pero con is_active=False.
    from app.models.epics import WikiSpace
    row = db.query(WikiSpace).filter(WikiSpace.id == space_id).first()
    assert row is not None
    assert row.is_active is False


# ── 2. DELETE /wiki/pages/{page_id} ────────────────────────────────────────────

def test_delete_wiki_page_hides_from_listing(client, admin_token, db):
    space_id = _create_wiki_space(client, admin_token, slug="ws-page-delete")

    created = client.post(
        f"/api/v1/epics/wiki/spaces/{space_id}/pages",
        json={
            "title": "Página a borrar",
            "slug": "pagina-borrar",
            "content": [],
            "is_published": True,
            "sort_order": 0,
        },
        headers=auth(admin_token),
    )
    assert created.status_code in (200, 201), created.text
    page_id = created.json()["data"]["id"]

    deleted = client.delete(
        f"/api/v1/epics/wiki/pages/{page_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["ok"] is True

    # Concealment: la página no debe aparecer en el árbol de páginas del espacio.
    listed = client.get(
        f"/api/v1/epics/wiki/spaces/{space_id}/pages",
        headers=auth(admin_token),
    )
    assert listed.status_code == 200

    def _ids_in_tree(nodes):
        out = []
        for n in nodes:
            out.append(n["id"])
            out.extend(_ids_in_tree(n.get("children") or []))
        return out

    assert page_id not in _ids_in_tree(listed.json()["items"])

    # Soft-delete: is_active=False
    from app.models.epics import WikiPage
    row = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    assert row is not None
    assert row.is_active is False


# ── 3. DELETE /filters/{filter_id} ─────────────────────────────────────────────

def test_delete_saved_filter_hides_from_listing(client, admin_token, db):
    created = client.post(
        "/api/v1/epics/filters",
        json={
            "name": "Filtro a borrar",
            "entity_type": "task",
            "nql_query": "status = open",
            "is_shared": False,
        },
        headers=auth(admin_token),
    )
    assert created.status_code in (200, 201), created.text
    filter_id = created.json()["data"]["id"]

    deleted = client.delete(
        f"/api/v1/epics/filters/{filter_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["ok"] is True

    # Concealment: no aparece en el listado de filtros del usuario.
    listed = client.get("/api/v1/epics/filters", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(f["id"] != filter_id for f in listed.json()["items"])

    # Soft-delete: is_active=False
    from app.models.epics import SavedFilter
    row = db.query(SavedFilter).filter(SavedFilter.id == filter_id).first()
    assert row is not None
    assert row.is_active is False


# ── 4. DELETE /comments/{comment_id}  (threaded) ───────────────────────────────

def test_delete_threaded_comment_hides_from_listing(client, admin_token, db):
    # entity_type="epic" evita la resolución por código de task/ticket en el
    # servicio: cualquier UUID arbitrario es válido como entity_id en ese caso.
    entity_id = "epic-fixture-for-comments"

    created = client.post(
        "/api/v1/epics/comments",
        params={"entity_type": "epic", "entity_id": entity_id},
        json={"content": "Comentario a borrar", "parent_id": None},
        headers=auth(admin_token),
    )
    assert created.status_code in (200, 201), created.text
    comment_id = created.json()["data"]["id"]

    deleted = client.delete(
        f"/api/v1/epics/comments/{comment_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["ok"] is True

    # Concealment: no aparece en el listado para esa entidad.
    listed = client.get(
        "/api/v1/epics/comments",
        params={"entity_type": "epic", "entity_id": entity_id},
        headers=auth(admin_token),
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert all(c.get("id") != comment_id for c in items)

    # Soft-delete: is_active=False
    from app.models.epics import ThreadedComment
    row = db.query(ThreadedComment).filter(ThreadedComment.id == comment_id).first()
    assert row is not None
    assert row.is_active is False


# ── 5. DELETE /{epic_id} ───────────────────────────────────────────────────────

def test_delete_epic_hides_from_listing(client, admin_token, db):
    project_id = _create_project(client, admin_token)

    created = client.post(
        "/api/v1/epics",
        params={"project_id": project_id},
        json={
            "title": "Épica a borrar",
            "description": "Test de borrado",
            "color": "#7c3aed",
            "status": "open",
            "priority": "medium",
            "sort_order": 0,
        },
        headers=auth(admin_token),
    )
    assert created.status_code in (200, 201), created.text
    epic_id = created.json()["data"]["id"]

    deleted = client.delete(
        f"/api/v1/epics/{epic_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["ok"] is True

    # Concealment: la épica no aparece en el listado del proyecto.
    listed = client.get(
        "/api/v1/epics",
        params={"project_id": project_id},
        headers=auth(admin_token),
    )
    assert listed.status_code == 200
    assert all(e["id"] != epic_id for e in listed.json()["items"])

    # Soft-delete: is_active=False
    from app.models.epics import Epic
    row = db.query(Epic).filter(Epic.id == epic_id).first()
    assert row is not None
    assert row.is_active is False
