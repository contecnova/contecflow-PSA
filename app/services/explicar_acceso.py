"""Explicador de accesos: ¿puede este usuario hacer esto, y qué capa lo decide? (revisión 2026-11).

Contecflow apila varias capas de permiso y, hasta ahora, un admin sólo veía un
403 sin saber de dónde venía. Esto recorre las capas **en el orden en que se
aplican** a una petición y dice qué responde cada una:

1. ABAC (políticas de la empresa; dependencia del router),
2. matriz GRC (rol × módulo × acción; dependencia del router),
3. cuenta y empresa (usuario activo, empresa no desactivada),
4. módulos del rol (`custom_roles.module_access`),
5. permisos por proyecto (si la ruta lleva `{project_id}`),
6. rol que exige el endpoint (`require_admin` y compañía).

Cada capa usa la MISMA función de decisión que la que deniega de verdad
(`modulos.modulo_cerrado`, `permisos_de_proyecto.decidir`, `grc_enforce.decidir`,
`abac_enforce.evaluar`), así que lo que se explica es lo que pasa. Gana la
primera que deniega.

Lo que no ve: las comprobaciones que un endpoint hace DENTRO de su servicio
(algunas rutas comprueban el rol ahí, no en la firma) y el aislamiento entre
empresas, que no deniega sino que esconde las filas ajenas (404). Se dice.
"""
from __future__ import annotations

import inspect
import re
from typing import Optional

from starlette.routing import Match

PERMITE, DENIEGA, NO_APLICA, NO_SE_SABE = "allow", "deny", "not_applicable", "unknown"


def _capa(id_: str, veredicto: str, detalle: str, **datos) -> dict:
    return {"layer": id_, "verdict": veredicto, "detail": detalle, **datos}


def _ruta(app, metodo: str, camino: str):
    """(ruta, parámetros) que contestaría: la primera coincidencia completa, como Starlette."""
    alcance = {"type": "http", "path": camino, "method": metodo, "root_path": ""}
    parcial = None
    for r in app.routes:
        if not hasattr(r, "matches") or getattr(r, "dependant", None) is None:
            continue
        coincide, hijo = r.matches(alcance)
        if coincide == Match.FULL:
            return r, hijo.get("path_params", {}), None
        if coincide == Match.PARTIAL and parcial is None:
            parcial = r
    return None, {}, parcial


def _guardas(dependant) -> dict:
    """Qué exige la firma del endpoint, recorriendo su árbol de dependencias."""
    from app.core import deps
    conocidas = (deps.get_current_user, deps.get_current_active_user)
    roles: set[str] = set()
    propias: set[str] = set()
    salida = {"superadmin": False, "user": False, "client": False}
    pendientes = [dependant]
    while pendientes:
        d = pendientes.pop()
        llamada = getattr(d, "call", None)
        hijas = getattr(d, "dependencies", []) or []
        if isinstance(llamada, deps.RequireRole):
            roles |= {getattr(r, "value", r) for r in llamada.roles}
        elif llamada is deps.require_superadmin:
            salida["superadmin"] = True
        elif llamada in conocidas:
            salida["user"] = True
        elif llamada is getattr(deps, "get_current_client", None):
            salida["client"] = True
        elif d is not dependant and any(getattr(h, "call", None) in conocidas for h in hijas):
            # Una guarda del propio módulo (p. ej. `_require_admin`) que recibe al
            # usuario: casi siempre mira el rol, pero aquí no se puede evaluar.
            propias.add(getattr(llamada, "__name__", type(llamada).__name__))
        pendientes.extend(hijas)
    salida["roles"] = sorted(roles)
    salida["custom"] = sorted(propias)
    return salida


#: Señales de que el cuerpo del endpoint decide por su cuenta (rol o 403 propio).
_EN_EL_CUERPO = re.compile(r"\bverify_\w+\(|\brequire_\w+\(|HTTPException\(\s*(?:status_code\s*=\s*)?403"
                           r"|status\.HTTP_403_FORBIDDEN|\.role\s*(?:!=|==|not in|in)\b")


def _comprueba_en_el_cuerpo(endpoint) -> bool:
    try:
        fuente = inspect.getsource(inspect.unwrap(endpoint))
    except (OSError, TypeError):
        return False
    cuerpo = fuente.split(":\n", 1)[-1]          # sin la firma, donde ya están las guardas
    return bool(_EN_EL_CUERPO.search(cuerpo))


def rutas(app) -> list[dict]:
    """Las operaciones de la API (método y plantilla), para elegir en la pantalla."""
    vistas, salida = set(), []
    for r in app.routes:
        camino = getattr(r, "path", "")
        if not camino.startswith("/api/v1/") or getattr(r, "dependant", None) is None:
            continue
        for m in sorted((getattr(r, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            if (m, camino) not in vistas:
                vistas.add((m, camino))
                salida.append({"method": m, "path": camino})
    return salida


def explicar(db, app, usuario, metodo: str, camino: str) -> dict:
    from app.core import abac_enforce, grc_enforce, modulos, permisos_de_proyecto
    from app.core.abac_dependency import _resolve_coverage
    from app.core.grc_catalog import action_for, module_for_path
    from app.models.mfa import Organization

    metodo = (metodo or "GET").upper()
    camino = "/" + (camino or "").strip().lstrip("/")
    if not camino.startswith("/api/"):
        camino = "/api/v1" + camino
    camino = camino.split("?", 1)[0]
    rol = getattr(usuario.role, "value", usuario.role)
    capas: list[dict] = []

    ruta, parametros, parcial = _ruta(app, metodo, camino)
    if ruta is None:
        if parcial is not None:
            capas.append(_capa("route", DENIEGA, "method_not_allowed",
                               allowed_methods=sorted((parcial.methods or set()) - {"HEAD", "OPTIONS"})))
        else:
            capas.append(_capa("route", DENIEGA, "not_found"))
        return _resumen(usuario, metodo, camino, None, capas)
    capas.append(_capa("route", PERMITE, "found", template=ruta.path))
    guardas = _guardas(ruta.dependant)

    # 1. ABAC (dependencia del router): sólo si el prefijo está cubierto y la empresa tiene políticas.
    cobertura = _resolve_coverage(camino)
    if cobertura is None or abac_enforce._abac_no_aplica(usuario, cobertura[0]):
        capas.append(_capa("abac", NO_APLICA, "not_covered" if cobertura is None else "exempt_user"))
    else:
        tipo, accion = cobertura
        try:
            permitido, aplicadas, _ = abac_enforce.evaluar(db, usuario, usuario.organization_id, tipo, None, accion,
                                                          auditar=False)
        except Exception:
            capas.append(_capa("abac", DENIEGA, "evaluation_error", resource_type=tipo, action=accion))
        else:
            if not aplicadas:
                capas.append(_capa("abac", NO_APLICA, "no_matching_policy", resource_type=tipo, action=accion))
            else:
                capas.append(_capa("abac", PERMITE if permitido else DENIEGA, "policies",
                                   resource_type=tipo, action=accion, policies=[str(p) for p in aplicadas]))

    # 2. Matriz GRC (dependencia del router).
    modulo, accion = module_for_path(camino), action_for(metodo, camino)
    if modulo is None or accion is None:
        capas.append(_capa("grc", NO_APLICA, "exempt_path"))
    else:
        d = grc_enforce.decidir(db, usuario, modulo, accion, usuario.organization_id)
        veredicto = DENIEGA if d["denied"] else (PERMITE if d["reason"] == "allowed" else NO_APLICA)
        capas.append(_capa("grc", veredicto, d["reason"], module=modulo, action=accion, role=d["role"],
                           company_row=d.get("company_row")))

    # 3. Cuenta y empresa (dentro de get_current_user).
    if guardas["client"] and not guardas["user"]:
        capas.append(_capa("account", DENIEGA, "portal_route"))
    elif not getattr(usuario, "is_active", True):
        capas.append(_capa("account", DENIEGA, "user_inactive"))
    else:
        empresa = db.get(Organization, usuario.organization_id) if usuario.organization_id else None
        if empresa is not None and not empresa.is_active and not usuario.is_superadmin:
            capas.append(_capa("account", DENIEGA, "company_inactive"))
        else:
            capas.append(_capa("account", PERMITE, "active"))

    # 4 y 5. Módulos del rol y permisos por proyecto (también dentro de get_current_user).
    if guardas["user"] or guardas["roles"] or guardas["superadmin"]:
        cerrado = modulos.modulo_cerrado(db, usuario, camino)
        capas.append(_capa("modules", DENIEGA, "module_closed", module=cerrado) if cerrado
                     else _capa("modules", NO_APLICA if not modulos.vetados(db, usuario) else PERMITE,
                                "no_closed_modules" if not modulos.vetados(db, usuario) else "route_not_in_closed"))
        proyecto = parametros.get("project_id")
        nivel, motivo = permisos_de_proyecto.decidir(db, usuario, metodo, camino, proyecto)
        if not proyecto:
            capas.append(_capa("project", NO_APLICA, "no_project_in_route"))
        elif motivo:
            capas.append(_capa("project", DENIEGA, motivo, level=nivel, project_id=proyecto))
        else:
            capas.append(_capa("project", PERMITE if nivel else NO_APLICA,
                               "level_allows" if nivel else "no_row_for_user", level=nivel, project_id=proyecto))
    else:
        capas.append(_capa("modules", NO_APLICA, "no_user_guard"))
        capas.append(_capa("project", NO_APLICA, "no_user_guard"))

    # 6. Rol que exige la firma del endpoint.
    if guardas["superadmin"]:
        capas.append(_capa("role", PERMITE if usuario.is_superadmin else DENIEGA, "requires_superadmin", role=rol))
    elif guardas["roles"] and not (usuario.is_superadmin or rol in guardas["roles"]):
        capas.append(_capa("role", DENIEGA, "requires_roles", required=guardas["roles"], role=rol))
    elif _comprueba_en_el_cuerpo(ruta.endpoint):
        # La firma deja pasar (o no pide rol), pero el cuerpo decide por su cuenta.
        capas.append(_capa("role", NO_SE_SABE, "in_body_check", role=rol, required=guardas["roles"] or None))
    elif guardas["roles"]:
        capas.append(_capa("role", PERMITE, "requires_roles", required=guardas["roles"], role=rol))
    elif guardas["custom"]:
        capas.append(_capa("role", NO_SE_SABE, "custom_guard", guards=guardas["custom"], role=rol))
    elif guardas["user"]:
        capas.append(_capa("role", PERMITE, "any_signed_in_user", role=rol))
    else:
        capas.append(_capa("role", NO_SE_SABE, "no_guard_in_signature"))

    # Lo que no se ve desde fuera.
    capas.append(_capa("service", NO_SE_SABE, "service_checks_not_visible"))
    capas.append(_capa("tenant", NO_APLICA, "other_company_rows_hidden"))
    return _resumen(usuario, metodo, camino, ruta.path, capas)


#: El orden en que las capas actúan en una petición real.
ORDEN = ("route", "abac", "grc", "account", "modules", "project", "role", "service", "tenant")


def _resumen(usuario, metodo: str, camino: str, plantilla: Optional[str], capas: list[dict]) -> dict:
    capas.sort(key=lambda c: ORDEN.index(c["layer"]))
    primera = next((c for c in capas if c["verdict"] == DENIEGA), None)
    rol = next((c for c in capas if c["layer"] == "role"), None)
    # Sin una capa que deniegue, «permite» sólo si el rol del endpoint lo deja
    # claro; una guarda propia o una ruta sin usuario quedan en «no se sabe».
    veredicto = DENIEGA if primera else (PERMITE if rol and rol["verdict"] == PERMITE else NO_SE_SABE)
    return {"user": {"id": usuario.id, "name": getattr(usuario, "full_name", None),
                     "role": getattr(usuario.role, "value", usuario.role),
                     "is_superadmin": bool(usuario.is_superadmin)},
            "method": metodo, "path": camino, "template": plantilla,
            "verdict": veredicto,
            "decided_by": primera["layer"] if primera else None,
            "layers": capas}
