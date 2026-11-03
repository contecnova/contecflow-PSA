"""El usuario del portal y su organizacion (auditoria 2026-11)."""
from __future__ import annotations


def test_el_usuario_del_portal_nace_en_la_organizacion_de_su_cliente(db):
    """Sin ella, el filtro de organizacion del portal dejaba fuera sus proyectos."""
    from types import SimpleNamespace

    from app.models.client_portal import ClientUser
    from app.models.clients import Client
    from app.services.client_service import create_portal_user

    db.add(Client(id="cli-org", name="Acme", organization_id="org-del-cliente"))
    db.commit()
    datos = create_portal_user("cli-org", {"full_name": "Laura", "email": "laura@acme.test"},
                               SimpleNamespace(id="u", organization_id="1", is_superadmin=False), db)
    assert db.get(ClientUser, datos["id"]).organization_id == "org-del-cliente"
