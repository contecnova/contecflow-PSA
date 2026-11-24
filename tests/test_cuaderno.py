"""«Mi cuaderno» (migración 202, docs/CUADERNO.md): privacidad, compartir, nota→acción,
exportación, RGPD, baja, acceso excepcional y aislamiento por empresa.

Escritos el 23-11-2026 sin ejecutar (regla de ahorro del encargo): ejecutar con
`pytest tests/test_cuaderno.py`.
"""
from __future__ import annotations

import json

import pytest

from app.models.user import User
from tests.conftest import auth

ORG = "1"
B = "/api/v1/notebook"


def _u(db, uid) -> User:
    return db.get(User, uid)


def _pagina(client, token, titulo="Nota", contenido=None) -> dict:
    arbol = client.get(f"{B}/tree", headers=auth(token)).json()["data"]
    nb = next(n for n in arbol["notebooks"] if not n["is_quick"])
    sec = nb["sections"][0]
    r = client.post(f"{B}/sections/{sec['id']}/pages", headers=auth(token),
                    json={"title": titulo, **({"content": contenido} if contenido else {})})
    assert r.status_code == 200, r.text
    return {**r.json()["data"], "notebook": nb}


def _doc(*bloques) -> dict:
    return {"type": "doc", "content": list(bloques)}


def _p(texto) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": texto}]}


# ── Privado por defecto ──────────────────────────────────────────────────────

def test_privado_por_defecto_ni_el_admin_ni_el_superadmin_lo_leen(client, pm_token, admin_token, superadmin_token):
    p = _pagina(client, pm_token, "Secreto", _doc(_p("contraseña del wifi")))
    for token in (admin_token, superadmin_token):
        assert client.get(f"{B}/pages/{p['id']}", headers=auth(token)).status_code == 404
        assert client.put(f"{B}/pages/{p['id']}/content", headers=auth(token), json={"title": "x"}).status_code == 404
        assert client.get(f"{B}/search", params={"q": "wifi"}, headers=auth(token)).json()["data"] == []
        assert client.get(f"{B}/export/page/{p['id']}", headers=auth(token)).status_code == 404
    # La búsqueda global (⌘K) tampoco la enseña a otros…
    g = client.get("/api/v1/global-search", params={"q": "Secreto"}, headers=auth(admin_token)).json()["data"]
    assert not g["grouped"].get("notes")
    # …pero sí a su dueño.
    g = client.get("/api/v1/global-search", params={"q": "Secreto"}, headers=auth(pm_token)).json()["data"]
    assert [n["id"] for n in g["grouped"]["notes"]] == [p["id"]]


def test_el_portal_de_clientes_no_entra(client):
    assert client.get(f"{B}/tree").status_code in (401, 403)


def test_config_y_acceso_excepcional_solo_con_su_capacidad(client, pm_token, admin_token):
    assert client.get(f"{B}/config", headers=auth(pm_token)).status_code == 403
    assert client.get(f"{B}/config", headers=auth(admin_token)).status_code == 200
    r = client.post(f"{B}/admin/exceptional-access/admin-test-id", headers=auth(pm_token),
                    json={"justification": "x" * 20, "legal_hold_id": "y"})
    assert r.status_code == 403


# ── Compartir ────────────────────────────────────────────────────────────────

def test_compartir_en_lectura_y_luego_en_edicion_y_quitar(client, db, pm_token, dev_token):
    from app.models.enterprise import AuditLog
    p = _pagina(client, pm_token, "Compartida")
    nb = p["notebook"]
    assert client.get(f"{B}/pages/{p['id']}", headers=auth(dev_token)).status_code == 404
    r = client.post(f"{B}/notebooks/{nb['id']}/shares", headers=auth(pm_token),
                    json={"target_type": "user", "target_id": "dev-test-id", "permission": "read"})
    assert r.status_code == 200, r.text
    share = r.json()["data"]
    d = client.get(f"{B}/pages/{p['id']}", headers=auth(dev_token))
    assert d.status_code == 200 and d.json()["data"]["permission"] == "read"
    assert client.put(f"{B}/pages/{p['id']}/content", headers=auth(dev_token), json={"title": "no"}).status_code == 403
    # Solo el dueño comparte o cambia permisos. El invitado VE el cuaderno (lectura),
    # así que la respuesta honesta es 403 (sin permiso), no 404 (`acceso._exigir`:
    # 404 sólo si no lo ve; 403 si lo ve sin el permiso mínimo, como el PUT de arriba).
    assert client.patch(f"{B}/shares/{share['id']}", headers=auth(dev_token), json={"permission": "edit"}).status_code == 403
    assert client.patch(f"{B}/shares/{share['id']}", headers=auth(pm_token), json={"permission": "edit"}).status_code == 200
    assert client.put(f"{B}/pages/{p['id']}/content", headers=auth(dev_token),
                      json={"title": "Sí", "content": _doc(_p("hola")), "collab": True}).status_code == 200
    assert client.delete(f"{B}/shares/{share['id']}", headers=auth(pm_token)).status_code == 200
    assert client.get(f"{B}/pages/{p['id']}", headers=auth(dev_token)).status_code == 404
    acciones = {a.action for a in db.query(AuditLog).filter(AuditLog.resource.in_(("notebook", "notebook_share")))}
    assert {"SHARE", "UPDATE", "UNSHARE"} <= acciones


def test_compartir_con_un_equipo_y_solo_una_seccion(client, db, pm_token, dev_token):
    dev = _u(db, "dev-test-id")
    dev.team = "Equipo Azul"
    db.commit()
    p1 = _pagina(client, pm_token, "En la sección compartida")
    nb = p1["notebook"]
    s2 = client.post(f"{B}/notebooks/{nb['id']}/sections", headers=auth(pm_token), json={"title": "Privada"}).json()["data"]
    p2 = client.post(f"{B}/sections/{s2['id']}/pages", headers=auth(pm_token), json={"title": "Fuera"}).json()["data"]
    r = client.post(f"{B}/notebooks/{nb['id']}/shares", headers=auth(pm_token),
                    json={"target_type": "team", "target_id": "Equipo Azul", "permission": "read",
                          "section_id": p1["section_id"]})
    assert r.status_code == 200, r.text
    assert client.get(f"{B}/pages/{p1['id']}", headers=auth(dev_token)).status_code == 200
    assert client.get(f"{B}/pages/{p2['id']}", headers=auth(dev_token)).status_code == 404


def test_las_notas_rapidas_no_se_comparten(client, pm_token):
    nb = client.get(f"{B}/quick", headers=auth(pm_token)).json()["data"]["notebook_id"]
    r = client.post(f"{B}/notebooks/{nb}/shares", headers=auth(pm_token),
                    json={"target_type": "user", "target_id": "dev-test-id", "permission": "read"})
    assert r.status_code == 422


# ── Contenido ────────────────────────────────────────────────────────────────

def test_el_contenido_se_valida_en_el_servidor(client, pm_token):
    p = _pagina(client, pm_token)
    malo = _doc(
        {"type": "paragraph", "content": [{"type": "text", "text": "clic", "marks": [
            {"type": "link", "attrs": {"href": "javascript:alert(1)"}}]}]},
        {"type": "script", "content": [{"type": "text", "text": "x"}]},
        {"type": "image", "attrs": {"src": "https://evil.example/x.png"}},
    )
    assert client.put(f"{B}/pages/{p['id']}/content", headers=auth(pm_token), json={"content": malo}).status_code == 200
    doc = client.get(f"{B}/pages/{p['id']}", headers=auth(pm_token)).json()["data"]["content"]
    texto = json.dumps(doc)
    assert "javascript" not in texto and "script" not in texto and "evil.example" not in texto


def test_casillas_y_etiquetas_en_la_vista_agregada(client, pm_token):
    contenido = _doc(
        {"type": "taskList", "content": [{"type": "taskItem", "attrs": {"checked": False, "bid": "b1", "due": "2026-12-01"},
                                          "content": [_p("Llamar al proveedor")]}]},
        {"type": "paragraph", "content": [{"type": "noteTag", "attrs": {"key": "idea"}}, {"type": "text", "text": " Mejorar el alta"}]},
    )
    p = _pagina(client, pm_token, "Con tareas", contenido)
    items = client.get(f"{B}/items", params={"status": "all"}, headers=auth(pm_token)).json()["data"]
    todo = next(i for i in items if i["kind"] == "todo")
    assert todo["text"] == "Llamar al proveedor" and todo["due_date"] == "2026-12-01"
    assert any(i["kind"] == "tag" and i["tag_key"] == "idea" and "Mejorar" in i["text"] for i in items)
    assert client.patch(f"{B}/items/{todo['id']}", headers=auth(pm_token), json={"checked": True}).status_code == 200
    doc = client.get(f"{B}/pages/{p['id']}", headers=auth(pm_token)).json()["data"]["content"]
    assert doc["content"][0]["content"][0]["attrs"]["checked"] is True


def test_conflicto_de_version_sin_red(client, pm_token):
    p = _pagina(client, pm_token)
    assert client.put(f"{B}/pages/{p['id']}/content", headers=auth(pm_token),
                      json={"title": "a", "base_version": p["version"]}).status_code == 200
    r = client.put(f"{B}/pages/{p['id']}/content", headers=auth(pm_token), json={"title": "b", "base_version": p["version"]})
    assert r.status_code == 409 and r.json().get("code") == "cuaderno_conflicto_de_version"


# ── De nota a acción y chips ─────────────────────────────────────────────────

@pytest.fixture
def proyecto(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    p = Project(code="CDN", name="Cuaderno", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id=ORG, pm_id="pm-test-id", created_by="pm-test-id")
    db.add(p)
    db.commit()
    return p


def test_nota_a_tarea_con_vinculo_en_los_dos_sentidos(client, db, pm_token, proyecto):
    from app.models.task import Task
    p = _pagina(client, pm_token, "Reunión con cliente")
    r = client.post(f"{B}/pages/{p['id']}/actions", headers=auth(pm_token),
                    json={"kind": "task", "text": "Preparar la oferta", "project_id": proyecto.id})
    assert r.status_code == 200, r.text
    chip = r.json()["data"]
    tarea = db.get(Task, chip["id"])
    assert tarea.title == "Preparar la oferta" and f"/notebook?page={p['id']}" in tarea.description
    vuelta = client.get(f"{B}/backlinks", params={"type": "task", "id": tarea.id}, headers=auth(pm_token)).json()["data"]
    assert vuelta and vuelta[0]["page_id"] == p["id"] and vuelta[0]["relation"] == "created"
    estado = client.post(f"{B}/chips/resolve", headers=auth(pm_token), json={"refs": [{"type": "task", "id": tarea.id}]}).json()["data"]
    assert estado[0]["hidden"] is False and estado[0]["status"]


def test_la_tarea_exige_un_proyecto_visible(client, pm_token, seed_multitenant):
    p = _pagina(client, pm_token)
    r = client.post(f"{B}/pages/{p['id']}/actions", headers=auth(pm_token), json={"kind": "task", "text": "x"})
    assert r.status_code == 422
    r = client.post(f"{B}/pages/{p['id']}/actions", headers=auth(pm_token),
                    json={"kind": "task", "text": "x", "project_id": "project-b-test"})
    assert r.status_code == 404


def test_un_chip_que_el_lector_no_ve_sale_oculto_y_sin_titulo(client, db, pm_token, dev_token, proyecto):
    from app.models.task import Task
    t = Task(code="TSK-CDN1", project_id=proyecto.id, title="Despido confidencial", organization_id=ORG,
             created_by="pm-test-id", reporter_id="pm-test-id", status="todo", priority="medium")
    db.add(t)
    db.commit()
    contenido = _doc({"type": "paragraph", "content": [{"type": "objectRef", "attrs": {"type": "task", "id": t.id, "label": "Despido confidencial"}}]})
    p = _pagina(client, pm_token, "Con chip", contenido)
    client.post(f"{B}/notebooks/{p['notebook']['id']}/shares", headers=auth(pm_token),
                json={"target_type": "user", "target_id": "dev-test-id", "permission": "read"})
    datos = client.get(f"{B}/pages/{p['id']}", headers=auth(dev_token)).json()["data"]
    assert "Despido" not in json.dumps(datos["content"])
    estado = client.post(f"{B}/chips/resolve", headers=auth(dev_token), json={"refs": [{"type": "task", "id": t.id}]}).json()["data"]
    assert estado[0]["hidden"] is True and "label" not in estado[0]


# ── Exportación ──────────────────────────────────────────────────────────────

def test_exportar_pagina_seccion_y_cuaderno_a_markdown_y_pdf(client, db, pm_token):
    from app.models.enterprise import AuditLog
    p = _pagina(client, pm_token, "Exportable", _doc({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Título"}]}, _p("cuerpo")))
    md = client.get(f"{B}/export/page/{p['id']}", params={"format": "md"}, headers=auth(pm_token))
    assert md.status_code == 200 and "## Título" in md.text and "cuerpo" in md.text
    pdf = client.get(f"{B}/export/section/{p['section_id']}", params={"format": "pdf"}, headers=auth(pm_token))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"{B}/export/notebook/{p['notebook_id']}", params={"format": "md"}, headers=auth(pm_token)).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "EXPORT", AuditLog.resource.like("notebook%")).count() >= 3


# ── RGPD, bloqueo legal, baja y acceso excepcional ───────────────────────────

def test_rgpd_copia_y_supresion_incluyen_los_cuadernos(client, db, pm_token):
    from app.models.cuaderno import Notebook
    from app.services.cab_service.gdpr import _gdpr_portability_export
    from app.services.cuaderno import rgpd
    _pagina(client, pm_token, "Mis datos", _doc(_p("dato personal")))
    pm = _u(db, "pm-test-id")
    copia = _gdpr_portability_export(db, pm)
    assert any("dato personal" in pg["markdown"] for nb in copia["notebooks"] for s in nb["sections"] for pg in s["pages"])
    informe = rgpd.suprimir(db, None, pm.id)
    db.commit()
    assert informe["notebooks"] >= 1
    assert db.query(Notebook).filter(Notebook.owner_id == pm.id).count() == 0


def test_el_bloqueo_legal_impide_purgar_y_habilita_el_acceso_excepcional(client, db, pm_token, admin_token):
    from app.models.enterprise import AuditLog
    from app.models.governance import LegalHold
    p = _pagina(client, pm_token, "Bajo bloqueo", _doc(_p("prueba")))
    h = LegalHold(organization_id=ORG, case_reference="CASO-1", entity="notebook_pages", field="owner_id",
                  value="pm-test-id", is_active=True)
    db.add(h)
    db.commit()
    assert client.delete(f"{B}/pages/{p['id']}", headers=auth(pm_token)).status_code == 200
    assert client.delete(f"{B}/trash/page/{p['id']}", headers=auth(pm_token)).status_code == 409
    # Sin motivo: no.
    r = client.post(f"{B}/admin/exceptional-access/pm-test-id", headers=auth(admin_token),
                    json={"justification": "requerimiento judicial", "format": "md"})
    assert r.status_code == 403
    r = client.post(f"{B}/admin/exceptional-access/pm-test-id", headers=auth(admin_token),
                    json={"justification": "requerimiento judicial", "legal_hold_id": h.id, "format": "md"})
    assert r.status_code == 200 and "prueba" in r.text
    assert db.query(AuditLog).filter(AuditLog.action == "NOTEBOOK_EXCEPTIONAL_ACCESS").count() == 1


def test_baja_transfiere_los_cuadernos_al_responsable(client, db, pm_token):
    from app.models.cuaderno import Notebook, NotebookPage
    p = _pagina(client, pm_token, "Para el jefe")
    pm = _u(db, "pm-test-id")
    pm.manager_id = "admin-test-id"
    db.commit()
    pm.is_active = False
    db.commit()
    nb = db.get(Notebook, p["notebook_id"])
    assert nb.owner_id == "admin-test-id" and nb.transferred_from == "pm-test-id"
    assert db.get(NotebookPage, p["id"]).owner_id == "admin-test-id"


def test_baja_a_la_papelera_segun_la_politica(client, db, admin_token, pm_token):
    from app.models.cuaderno import Notebook
    assert client.put(f"{B}/config", headers=auth(admin_token), json={"offboarding": "trash"}).status_code == 200
    p = _pagina(client, pm_token)
    pm = _u(db, "pm-test-id")
    pm.is_active = False
    db.commit()
    assert db.get(Notebook, p["notebook_id"]).deleted_at is not None


# ── Aislamiento por empresa ──────────────────────────────────────────────────

def test_aislamiento_por_empresa(client, db, seed_multitenant):
    from tests.conftest import TEST_PASSWORD
    tok_a = client.post("/api/v1/auth/login", json={"username": "pm_test", "password": TEST_PASSWORD}).cookies.get("access_token")
    p = _pagina(client, tok_a, "Empresa A", _doc(_p("solo de A")))
    tok_b = client.post("/api/v1/auth/login", json={"username": "outsider", "password": TEST_PASSWORD}).cookies.get("access_token")
    assert client.get(f"{B}/pages/{p['id']}", headers=auth(tok_b)).status_code == 404
    assert client.get(f"{B}/search", params={"q": "solo de"}, headers=auth(tok_b)).json()["data"] == []
    # No se puede compartir con alguien de otra empresa.
    r = client.post(f"{B}/notebooks/{p['notebook_id']}/shares", headers=auth(tok_a),
                    json={"target_type": "user", "target_id": "outsider-test-id", "permission": "read"})
    assert r.status_code == 404


# ── Papelera ─────────────────────────────────────────────────────────────────

def test_papelera_y_restaurar(client, pm_token):
    p = _pagina(client, pm_token, "Ir y volver")
    assert client.delete(f"{B}/pages/{p['id']}", headers=auth(pm_token)).status_code == 200
    papelera = client.get(f"{B}/trash", headers=auth(pm_token)).json()["data"]
    assert any(x["id"] == p["id"] for x in papelera)
    assert client.post(f"{B}/trash/page/{p['id']}/restore", headers=auth(pm_token)).status_code == 200
    assert client.get(f"{B}/pages/{p['id']}", headers=auth(pm_token)).status_code == 200
