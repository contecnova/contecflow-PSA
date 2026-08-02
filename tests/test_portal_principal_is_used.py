"""Guardrail: si un endpoint declara el principal del portal, tiene que USARLO.

Por qué existe (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §1):

El wiki del portal tenía la dependencia de autenticación puesta correctamente...

    def portal_wiki_pages(db=Depends(get_db), current_client=Depends(get_current_client)):
        return APIListResponse.ok(items=_svc.portal_wiki_pages(db))   # <- current_client ignorado

...y aun así filtraba cross-tenant, porque el servicio nunca recibía el cliente.
Autenticar no acota: si declaras el principal y no lo pasas aguas abajo, la
comprobación de tenencia sencillamente no ocurre.

El mismo olvido causó el IDOR de CSAT en la primera auditoría, donde el valor de
retorno de `require_portal_client(...)` se descartaba.

Este test recorre el AST de todos los endpoints y exige que cualquier parámetro
inyectado con `Depends(get_current_client)` / `Depends(get_current_portal_client)`
aparezca en el cuerpo de la función.

**Cómo declarar una excepción legítima:** si un endpoint solo necesita *autenticar*
(no autorizar por ese principal — p. ej. devuelve configuración global idéntica para
todos los clientes), nombra el parámetro con guion bajo inicial: `_client`. Eso lo
hace explícito y revisable en el diff, en lugar de silencioso.
"""

from __future__ import annotations

import ast
import pathlib

ENDPOINTS_DIR = pathlib.Path("app/api")

PORTAL_PRINCIPAL_DEPS = {
    "get_current_client",
    "get_current_portal_client",
}


def _depends_target(default_node) -> str | None:
    """Si el default es `Depends(x)`, devuelve el nombre de `x`."""
    if not isinstance(default_node, ast.Call):
        return None
    func = default_node.func
    if not (isinstance(func, ast.Name) and func.id == "Depends"):
        return None
    if not default_node.args:
        return None
    arg = default_node.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    return None


def _names_used(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _principal_params(fn: ast.FunctionDef) -> list[str]:
    """Parámetros del endpoint inyectados con una dependencia de principal de portal."""
    args = fn.args
    positional = args.posonlyargs + args.args
    # los defaults alinean por la derecha
    paired = list(zip(
        positional[len(positional) - len(args.defaults):], args.defaults, strict=True,
    ))
    paired += [
        (a, d)
        for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True)
        if d is not None
    ]
    return [
        a.arg for a, d in paired
        if _depends_target(d) in PORTAL_PRINCIPAL_DEPS
    ]


def test_portal_principal_is_used_when_declared() -> None:
    violations: list[str] = []

    for path in sorted(ENDPOINTS_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # pragma: no cover - no debería ocurrir
            continue

        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for param in _principal_params(fn):
                if param.startswith("_"):
                    continue  # opt-out explícito y visible en el diff
                body_names: set[str] = set()
                for stmt in fn.body:
                    body_names |= _names_used(stmt)
                if param not in body_names:
                    rel = str(path).replace("\\", "/")
                    violations.append(f"{rel}:{fn.lineno}  {fn.name}() ignora '{param}'")

    assert not violations, (
        "Endpoints que inyectan el principal del portal y no lo usan. Autenticar no "
        "acota: si no pasas el cliente al servicio, no hay comprobación de tenencia "
        "(así se filtró el wiki del portal). Úsalo, o renómbralo con guion bajo si "
        "de verdad solo necesitas autenticar:\n  - " + "\n  - ".join(violations)
    )
