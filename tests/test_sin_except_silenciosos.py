"""Auditoria 2026-11 (#25): ningun `except Exception` se traga el error sin rastro.

Habia 207. Se corrigieron con scripts/codemods/except_silenciosos.py (log con la
traza: warning si el try hace E/S, debug si no). Esto impide que vuelvan.
"""
import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "app"
LOG = {"debug", "info", "warning", "error", "exception", "critical", "log", "print_exc", "capture_exception", "warn"}


def _amplio(t):
    if t is None:
        return True
    n = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else None)
    return n in ("Exception", "BaseException")


def _deja_rastro(body):
    for nodo in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(nodo, ast.Raise):
            return True
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in LOG:
                return True
    return False


def test_ningun_except_amplio_silencioso():
    fuera = []
    for f in RAIZ.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ExceptHandler) and _amplio(n.type) and not _deja_rastro(n.body):
                fuera.append(f"{f.relative_to(RAIZ).as_posix()}:{n.lineno}")
    assert fuera == [], "except Exception sin log ni raise:\n" + "\n".join(fuera)
