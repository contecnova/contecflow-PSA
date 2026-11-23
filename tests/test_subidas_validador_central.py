"""Los endpoints de subida leen con tope y validan por app/core/uploads.py (auditoria 2026-11, M4 / A-SD8)."""
import ast
from pathlib import Path

import pytest

from app.core.errores import ErrorDeDominio
from app.core.uploads import UploadProfile, validate_upload

RAIZ = Path(__file__).resolve().parent.parent / "app" / "api"
# Los endpoints donde el .read() sobre un UploadFile queda a la vista.
FICHEROS = [p for p in RAIZ.rglob("*.py") if "UploadFile" in p.read_text(encoding="utf-8")]


def _lecturas_directas(arbol):
    """`x.read(...)` o `x.file.read(...)` sobre un parametro UploadFile."""
    subidas = set()
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for a in f.args.args + f.args.kwonlyargs:
                anot = ast.unparse(a.annotation) if a.annotation else ""
                if "UploadFile" in anot:
                    subidas.add(a.arg)
    malas = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "read":
            dueño = n.func.value
            if isinstance(dueño, ast.Attribute) and dueño.attr == "file":
                dueño = dueño.value
            if isinstance(dueño, ast.Name) and dueño.id in subidas:
                malas.append(n.lineno)
    return malas


def test_hay_endpoints_de_subida():
    assert len(FICHEROS) >= 10


@pytest.mark.parametrize("ruta", FICHEROS, ids=lambda p: p.name)
def test_ningun_endpoint_lee_el_fichero_sin_tope(ruta):
    fuente = ruta.read_text(encoding="utf-8")
    malas = _lecturas_directas(ast.parse(fuente))
    assert not malas, f"{ruta.name}: lectura directa de UploadFile en las lineas {malas}; usa app/core/uploads.py"


def test_portal_de_proveedores_usa_el_validador_central():
    fuente = (RAIZ / "v1" / "endpoints" / "proveedores_portal.py").read_text(encoding="utf-8")
    assert "read_and_validate_upload_sync(file, UploadProfile.DOCUMENT)" in fuente


@pytest.mark.parametrize("perfil", [UploadProfile.DOCUMENT, UploadProfile.CHANNEL])
def test_un_exe_se_rechaza(perfil):
    with pytest.raises(ErrorDeDominio) as e:
        validate_upload("evidencia.exe", "application/octet-stream", b"MZ\x90\x00", perfil)
    assert e.value.status_code == 415
    with pytest.raises(ErrorDeDominio):  # renombrado a pdf: lo delatan los bytes
        validate_upload("evidencia.pdf", "application/pdf", b"MZ\x90\x00", perfil)
