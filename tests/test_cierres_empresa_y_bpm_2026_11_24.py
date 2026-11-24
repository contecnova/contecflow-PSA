"""24-11-2026: superadmin sin empresa al encolar trabajo, y catálogo BPM sembrado al día."""
from types import SimpleNamespace

import pytest


def test_superadmin_sin_empresa_no_puede_encolar():
    from app.core import segundo_plano

    sesion = SimpleNamespace(info={"organization_id": None,
                                   "current_user": SimpleNamespace(is_superadmin=True, organization_id=None)})
    with pytest.raises(Exception) as exc:
        segundo_plano.encolar(test_superadmin_sin_empresa_no_puede_encolar, _sesion=sesion)
    assert getattr(exc.value, "status_code", None) == 409
    assert getattr(exc.value, "code", None) == "empresa_requerida"


def test_usuario_con_empresa_sigue_encolando(monkeypatch):
    from app.core import segundo_plano

    llamadas = []
    monkeypatch.setattr(segundo_plano, "_llamar", lambda f, org, a, k, sesion=None: llamadas.append(org) or "ok")
    monkeypatch.setattr(segundo_plano, "_hay_cola", lambda: False)
    sesion = SimpleNamespace(info={"organization_id": "org-1",
                                   "current_user": SimpleNamespace(is_superadmin=True, organization_id=None)})
    assert segundo_plano.encolar(test_usuario_con_empresa_sigue_encolando, _sesion=sesion) == "ok"
    assert llamadas == ["org-1"]


def test_catalogo_sembrado_se_pone_al_dia_solo_si_nadie_lo_edito():
    from app.services import bpmn_process_service as svc

    class _Q:
        def __init__(self, v): self.v = v
        def filter(self, *a): return self
        def order_by(self, *a): return self
        def first(self): return self.v

    proc = SimpleNamespace(id="p1")
    sin_autor = SimpleNamespace(created_by_user_id=None, bpmn_xml="<viejo/>")
    con_autor = SimpleNamespace(created_by_user_id="u1", bpmn_xml="<viejo/>")
    igual = SimpleNamespace(created_by_user_id=None, bpmn_xml="<nuevo/>")
    assert svc._sin_tocar_y_desfasado(SimpleNamespace(query=lambda *a: _Q(sin_autor)), proc, "<nuevo/>")
    assert not svc._sin_tocar_y_desfasado(SimpleNamespace(query=lambda *a: _Q(con_autor)), proc, "<nuevo/>")
    assert not svc._sin_tocar_y_desfasado(SimpleNamespace(query=lambda *a: _Q(igual)), proc, "<nuevo/>")


def test_el_arranque_sincroniza_el_catalogo_bpm():
    import inspect
    import app.main as m

    assert "_sincronizar_catalogo_bpm(_is_testing)" in inspect.getsource(m.lifespan)


def test_el_arranque_siembra_los_roles_de_sistema_de_todas_las_empresas():
    """24-11-2026: el superadmin (sin empresa activa) veía «Roles y permisos» vacío."""
    import inspect
    import app.main as m
    from app.services.advanced_config_service import semillas

    assert "sembrar_roles_de_sistema_en_todas(db)" in inspect.getsource(m._sincronizar_catalogo_bpm)
    fuente = inspect.getsource(semillas.sembrar_roles_de_sistema_en_todas)
    assert "con_empresa" in fuente and "seed_system_roles(db, org)" in fuente
