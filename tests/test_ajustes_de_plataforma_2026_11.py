"""Un ajuste leído sólo en su fila global es de plataforma (revisión 2026-11).

Medido: 30 claves se leían sin empresa; un admin de empresa las «cambiaba» para
la suya y no pasaba nada. O la clave es de plataforma (y sólo la cambia el
superadmin), o su lectura pasa la empresa.
"""
from __future__ import annotations

import pathlib
import re

from app.services.settings_service import AJUSTES_DE_PLATAFORMA, RUNTIME_FLAG_GROUPS
from tests.conftest import auth

_LECTURA = re.compile(r'get_runtime_(?:str|int|float|bool)\(\s*[^,]+,\s*["\']([A-Z0-9_]+)["\']\s*(\)|,\s*([^)]*)\))')


def _lecturas():
    lecturas: dict[str, set] = {}
    for f in pathlib.Path("app").rglob("*.py"):
        for m in _LECTURA.finditer(f.read_text(errors="ignore")):
            resto = (m.group(3) or "").strip()
            con_empresa = bool(resto) and not resto.startswith("default")
            lecturas.setdefault(m.group(1), set()).add("empresa" if con_empresa else "global")
    return lecturas


def test_toda_clave_leida_solo_en_global_es_de_plataforma():
    claves = {k[0] for grupo in RUNTIME_FLAG_GROUPS.values() for k in grupo}
    lecturas = _lecturas()
    assert len(lecturas) > 100, f"la sonda sólo vio {len(lecturas)} claves leídas: no está mirando"
    solo_global = {k for k, v in lecturas.items() if v == {"global"} and k in claves}
    assert solo_global - AJUSTES_DE_PLATAFORMA == set(), (
        "Se leen sólo en global y no son de plataforma: pasa la empresa al leerlas o decláralas: "
        f"{sorted(solo_global - AJUSTES_DE_PLATAFORMA)}")


def test_EL_HALLAZGO_un_admin_de_empresa_no_cambia_un_ajuste_de_plataforma(client, admin_token, superadmin_token):
    r = client.put("/api/v1/settings/runtime/timeouts/OUTBOUND_HTTP_TIMEOUT_SECONDS",
                   headers=auth(admin_token), json={"value": "5"})
    assert r.status_code == 403, r.text
    r = client.put("/api/v1/settings/runtime/timeouts/OUTBOUND_HTTP_TIMEOUT_SECONDS",
                   headers=auth(superadmin_token), json={"value": "5"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["organization_id"] is None
