"""PATCH de un proveedor de IA: sólo sus campos editables (revisión 2026-11).

Medido antes: escribía cualquier atributo (`organization_id`, `total_cost_usd`,
`created_by`…): un administrador podía mover el proveedor a otra empresa o
falsear su gasto acumulado.
"""
from __future__ import annotations

from tests.conftest import auth


def test_EL_HALLAZGO_no_se_mueve_de_empresa_ni_se_falsea_el_gasto(client, admin_token):
    r = client.post("/api/v1/ai-providers", headers=auth(admin_token),
                    json={"name": "Gem", "provider": "gemini", "api_key": "k", "default_model": "gemini-2.5-flash"})
    assert r.status_code in (200, 201), r.text
    pid = (r.json().get("data") or r.json())["id"]
    for malo in ({"organization_id": "otra"}, {"total_cost_usd": 0}, {"created_by": "x"}):
        r = client.patch(f"/api/v1/ai-providers/{pid}", headers=auth(admin_token), json=malo)
        assert r.status_code == 400 and list(malo)[0] in r.json()["detail"]
    r = client.patch(f"/api/v1/ai-providers/{pid}", headers=auth(admin_token), json={"name": "Gemini", "max_tokens": 4000})
    assert r.status_code == 200
