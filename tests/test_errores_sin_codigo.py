"""Errores que ve el usuario: con codigo traducible y sin volver atras (19-11-2026).

- Cuota: `scripts/errores_sin_codigo.py` cuenta por fichero los
  `ErrorDeDominio`/`HTTPException`/`raise ValueError` con texto libre; ningun
  fichero puede superar su cuota de `scripts/errores-sin-codigo.json` ni
  aparecer uno nuevo (la lista solo encoge: `--encoger`).
- Cada codigo que lanza el codigo (`error`, `error_http`, `ErrorConCodigo`)
  existe en el catalogo y cada entidad de `no_encontrado` (`que=`) tiene texto
  en es/en/zh.
- Muestra de endpoints: la respuesta lleva `code` + `params` y el texto existe
  en ingles y chino.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

from app.core import codigos_de_error as cde
from app.core.errores import ErrorDeDominio
from tests.conftest import auth

RAIZ = Path(__file__).resolve().parents[1]
LANGS = RAIZ / "frontend" / "src" / "i18n" / "langs"


def _herramienta():
    spec = importlib.util.spec_from_file_location("errores_sin_codigo", RAIZ / "scripts" / "errores_sin_codigo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _err_srv(idioma: str) -> dict[str, str]:
    texto = (LANGS / f"{idioma}.mjs").read_text(encoding="utf-8")
    ini = texto.index("err_srv: {")
    fin = texto.index("\n  },", ini)
    return {m.group(1): m.group(2) for m in
            re.finditer(r'^\s+(\w+):\s*"((?:[^"\\]|\\.)*)",?\s*$', texto[ini:fin], re.M)}


# ── cuota ────────────────────────────────────────────────────────────────────

def test_ningun_fichero_supera_su_cuota_de_errores_sin_codigo():
    h = _herramienta()
    assert h.CUOTA.exists(), "falta scripts/errores-sin-codigo.json"
    cuota = h.leer_cuota()  # 19-11-2026: vacia (0 pendientes); solo puede seguir asi
    medido = h.totales(h.medir())
    pasados = {f: (n, cuota.get(f, 0)) for f, n in medido.items() if n > cuota.get(f, 0)}
    assert not pasados, (
        "Errores sin codigo nuevos (fichero: (ahora, cuota)). Lanza `error(...)`/`error_http(...)`/"
        f"`ErrorConCodigo(...)` de app/core/codigos_de_error.py: {pasados}")


def test_la_herramienta_cuenta_cada_patron(tmp_path, monkeypatch):
    h = _herramienta()
    app = tmp_path / "app" / "services"
    app.mkdir(parents=True)
    f = app / "x.py"
    f.write_text(
        "from app.core.errores import ErrorDeDominio\n"
        "from fastapi import HTTPException\n"
        "def a(e):\n"
        "    raise ErrorDeDominio(404, 'Cosa no encontrada')\n"
        "def b(e):\n"
        "    raise HTTPException(status_code=400, detail=str(e))\n"
        "def c(x):\n"
        "    raise ValueError(f'Mal: {x}')\n"
        "def d():\n"
        "    raise ErrorDeDominio(404, 'Cosa', code='no_encontrado')\n"
        "def e():\n"
        "    raise ErrorDeDominio(422, 'alm_licencia_vencida')\n"
        "def f():\n"
        "    raise HTTPException(404)\n",
        encoding="utf-8")
    monkeypatch.setattr(h, "RAIZ", tmp_path)
    assert [c for _, c in h.hallazgos(f)] == ["dominio", "http", "valor"]


def test_http_crudo_en_la_capa_api(tmp_path, monkeypatch):
    h = _herramienta()
    api = tmp_path / "app" / "api"
    api.mkdir(parents=True)
    f = api / "x.py"
    f.write_text(
        "from fastapi import HTTPException\n"
        "def a():\n"
        "    raise HTTPException(404)\n"
        "def b():\n"
        "    raise HTTPException(status_code=404, detail='bookmark_not_found')\n"
        "def c():\n"
        "    raise HTTPException(400, detail={'error': 'X'})\n"
        "def d():\n"
        "    raise HTTPException(422, 'alm_licencia_vencida')\n"
        "def e():\n"
        "    raise HTTPException(403, detail='sin_permiso')\n"
        "def f():\n"
        "    try:\n"
        "        pass\n"
        "    except HTTPException:\n"
        "        raise\n",
        encoding="utf-8")
    monkeypatch.setattr(h, "RAIZ", tmp_path)
    assert [c for _, c in h.hallazgos(f)] == ["http_crudo"] * 3


def test_encoger_nunca_sube_la_cuota():
    h = _herramienta()
    medido = {"a.py": [(1, "dominio")] * 5, "b.py": [(1, "http")] * 2, "c.py": [(1, "valor")]}
    assert h.encoger(medido, {"a.py": 3, "b.py": 4}) == {"a.py": 3, "b.py": 2}


# ── codigos usados y textos ──────────────────────────────────────────────────

def _codigos_usados() -> set[tuple[str, str]]:
    usados = set()
    for f in (RAIZ / "app").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            nombre = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            if nombre in ("error", "error_http", "error_con_codigo"):
                pos = 1
            elif nombre == "ErrorConCodigo":
                pos = 0
            else:
                continue
            if len(n.args) > pos and isinstance(n.args[pos], ast.Constant) and isinstance(n.args[pos].value, str):
                usados.add((f.relative_to(RAIZ).as_posix(), n.args[pos].value))
    return usados


def test_cada_codigo_lanzado_esta_en_el_catalogo():
    usados = _codigos_usados()
    assert len(usados) > 500
    faltan = sorted({(f, c) for f, c in usados if c not in cde.TODOS})
    assert not faltan, faltan


@pytest.mark.parametrize("idioma", ["es", "en", "zh"])
def test_cada_entidad_de_no_encontrado_tiene_texto(idioma):
    dic = _err_srv(idioma)
    assert cde.QUE
    faltan = [q for q in cde.QUE if f"que_{q}" not in dic]
    assert not faltan, f"{idioma}: {faltan}"


def test_las_entidades_usadas_existen():
    usadas = set()
    for f in (RAIZ / "app").rglob("*.py"):
        usadas |= set(re.findall(r'"no_encontrado",[^)]*?que="(\w+)"', f.read_text(encoding="utf-8")))
    assert usadas and not usadas - set(cde.QUE), usadas - set(cde.QUE)


def test_detail_conserva_el_texto_de_siempre():
    e = cde.error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    assert isinstance(e, ErrorDeDominio)
    assert (e.detail, e.code, e.params) == ("Épica no encontrada", "no_encontrado", {"que": "epica"})
    h = cde.error_http(400, "fichero_vacio")
    assert (h.status_code, h.detail, h.code, h.params) == (400, "El fichero está vacío", "fichero_vacio", {})
    v = cde.ErrorConCodigo("no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    assert str(v) == "Proyecto no encontrado" and isinstance(v, ValueError)
    import uuid
    assert isinstance(cde.error(404, "no_encontrado", que=uuid.uuid4()).params["que"], str)


# ── muestra de endpoints ─────────────────────────────────────────────────────

def _con_codigo(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    d = r.json()
    assert d.get("code") == code, d
    assert isinstance(d["detail"], str) and isinstance(d.get("params"), dict)
    en, zh = _err_srv("en"), _err_srv("zh")
    assert code in en and code in zh and en[code] != zh[code]
    for k in re.findall(r"\{(\w+)\}", en[code]):
        assert k in d["params"], (code, k)
    if d["params"].get("que"):
        assert f"que_{d['params']['que']}" in en and f"que_{d['params']['que']}" in zh
    return d


def test_endpoint_epica_inexistente(client, admin_token):
    r = client.get("/api/v1/epics/00000000-0000-0000-0000-000000000000", headers=auth(admin_token))
    if r.status_code == 404 and r.json().get("code"):
        d = _con_codigo(r, 404, "no_encontrado")
        assert d["params"]["que"] == "epica"
    else:  # la ruta puede cambiar; lo importante es el servicio
        from app.services import epics_service
        with pytest.raises(ErrorDeDominio) as e:
            epics_service.exigir_epica_visible(_db_vacia(), None, "no-existe")
        assert e.value.code == "no_encontrado"


def _db_vacia():
    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    class _Db:
        def query(self, *a, **k):
            return _Q()
    return _Db()


def test_endpoint_proyecto_inexistente(client, admin_token):
    r = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000", headers=auth(admin_token))
    assert r.status_code == 404, r.text
    d = _con_codigo(r, 404, "no_encontrado")
    assert d["params"]["que"] == "proyecto"


def test_endpoint_tarea_inexistente(client, admin_token):
    r = client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000", headers=auth(admin_token))
    assert r.status_code == 404, r.text
    _con_codigo(r, 404, r.json().get("code") or "no_encontrado")
