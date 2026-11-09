"""La IA usa el proveedor de la empresa de quien llama, también sin filtro de empresa (revisión 2026-11).

Medido antes: `call_ai` tomaba `is_superadmin=True` por defecto y elegía con el
`organization_id` que le pasaran (casi nunca). Desde un trabajo de fondo —sin
filtro de empresa en la sesión— el proveedor «por defecto» era el más antiguo de
cualquier empresa: se usaba la clave de otra.
"""
from __future__ import annotations

from app.models.ai_providers import AIProvider, AIProviderType
from app.models.mfa import Organization
from app.models.user import User, UserRole
from app.services import ai_provider_service as s


def test_EL_HALLAZGO_sin_filtro_de_empresa_usa_el_proveedor_de_la_suya(db, monkeypatch):
    db.add(Organization(id="org-ia-b", name="Otra", slug="otra-ia"))
    db.add(User(id="u-ia-b", username="u_ia_b", email="u-ia-b@example.com", full_name="B", role=UserRole.employee,
                organization_id="org-ia-b", hashed_password="x"))
    db.add(AIProvider(id="prov-a", name="De la empresa 1", provider=AIProviderType.anthropic, organization_id="1",
                      is_active=True, is_default=True, api_key="x"))
    db.add(AIProvider(id="prov-b", name="De la otra", provider=AIProviderType.anthropic, organization_id="org-ia-b",
                      is_active=True, is_default=True, api_key="x"))
    db.commit()
    usado = {}

    def llamar(db_, p, *a, **k):
        usado["id"] = p.id if p else None
        return p, {"text": "ok", "tokens_in": 0, "tokens_out": 0, "cost": 0}, None
    monkeypatch.setattr(s, "_llamar_con_respaldo", llamar)
    monkeypatch.setattr(s, "_registrar_uso", lambda *a, **k: None)
    monkeypatch.setattr(s, "_exigir_presupuesto", lambda *a, **k: None)
    monkeypatch.setitem(db.info, "organization_id", None)     # como un trabajo de fondo: la sesión sin empresa
    s.call_ai(db, [{"role": "user", "content": "hola"}], user_id="u-ia-b", skip_guardrails=True)
    assert usado["id"] == "prov-b"


def test_un_proveedor_pedido_por_id_es_de_su_empresa_o_global(db):
    db.add(AIProvider(id="prov-otra", name="Ajena", provider=AIProviderType.anthropic, organization_id="org-ajena-x",
                      is_active=True, api_key="x"))
    db.add(AIProvider(id="prov-global", name="Global", provider=AIProviderType.anthropic, organization_id=None,
                      is_active=True, api_key="x"))
    db.commit()
    assert s._seleccionar_proveedor(db, "prov-otra", False, "1") is None
    assert s._seleccionar_proveedor(db, "prov-global", False, "1").id == "prov-global"
