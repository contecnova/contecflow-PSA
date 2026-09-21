"""Cobertura ABAC verificada contra el mecanismo REAL (auditoría 2026-08, P1-5 y P1-25).

Sustituye a `tests/test_abac_registry_completeness.py`, que verificaba con mucho
cuidado que `ABAC_ROUTE_REGISTRY` estuviera completo... siendo ese registro
consumido únicamente por `ABACMiddleware`, un no-op absoluto: se saltaba el
chequeo cuando `request.state.user` era None y nada en el proyecto asignaba ese
atributo jamás. Seis tests en verde dando garantía sobre código inerte. Es el
patrón más peligroso de toda la auditoría, porque un control ausente se nota y
uno que informa «OK» se cree.

Este fichero mide la realidad:

1. Que cada prefijo declarado en el mapa de cobertura tenga de verdad rutas que
   llamen a `enforce_abac()`.
2. Que el mapa no acumule prefijos de rutas que ya no existen.
3. Que ninguna ruta dependa de `enforce_abac()` como único control — es fail-open
   por diseño, así que sería un control imaginario. Este es el inventario que
   mantiene deliberado el reparto entre RBAC de ruta y RBAC de servicio.
"""
from __future__ import annotations

import ast
import inspect
import re

from app.core.abac_registry import ABAC_COVERED_PREFIXES, ABAC_EXEMPT_PREFIXES
from app.core.deps import (
    require_admin,
    require_admin_or_hr,
    require_admin_or_pm,
    require_any_manager,
    require_internal_user,
    require_superadmin,
)
from app.main import app

ROUTE_ROLE_GUARDS = {
    require_admin,
    require_admin_or_hr,
    require_admin_or_pm,
    require_any_manager,
    require_internal_user,
    require_superadmin,
}

# Señales de control de autorización en la capa de servicio. Es deliberadamente
# amplio: el objetivo es detectar la AUSENCIA TOTAL de control, no auditar que
# cada comprobación concreta sea la correcta (eso no es decidible estáticamente).
SERVICE_AUTHZ_SIGNALS = re.compile(
    # Guardas de rol y de organizacion.
    r"current_user\.role|cu\.role|user\.role|is_superadmin|"
    r"_scoped_\w*or_404|org_scoped_or_404|assert_same_org|assert_org_id_is_own|"
    r"verify_admin_or_governance_role|require_|"
    r"HTTPException\(\s*403|status\.HTTP_403|"
    # Comprobacion de PROPIEDAD, que en este proyecto es tan control como las
    # anteriores: una busqueda acotada al usuario que pregunta, que devuelve
    # 404 si la fila no es suya. Auditoria 2026-09: faltaba, y por eso el
    # listado de rutas "sin control" incluia sitios como
    # `get_absence_for_user(db, absence_id, current_user.id)`, que es
    # exactamente el control que hace falta ahi.
    r"for_user\(|owner_id|"
    r"user_id\s*==\s*current_user\.id|user_id\s*=\s*current_user\.id|"
    r"\.id\s*==\s*current_user\.id|,\s*current_user\.id\s*\)",
    re.IGNORECASE,
)


def _source(fn) -> str:
    try:
        return inspect.getsource(fn)
    except Exception:
        return ""


def _calls_enforce_abac(src: str) -> bool:
    return "enforce_abac(" in src


def _api_routes():
    for route in app.routes:
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        endpoint = getattr(route, "endpoint", None)
        if not path.startswith("/api/v") or dependant is None or endpoint is None:
            continue
        methods = (getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}
        yield route, path, methods, dependant, endpoint


def _first_level_prefixes() -> set[str]:
    out: set[str] = set()
    for _route, path, _m, _d, _e in _api_routes():
        parts = path.split("/")
        if len(parts) >= 4 and parts[3]:
            out.add("/".join(parts[:4]))
    return out


# ── 1. El mapa de cobertura describe la realidad ──────────────────────────────

def test_every_api_prefix_is_covered_or_exempt():
    """Un dominio nuevo no puede nacer sin una decisión sobre ABAC."""
    undecided = sorted(
        p
        for p in _first_level_prefixes()
        if p not in ABAC_COVERED_PREFIXES and p not in ABAC_EXEMPT_PREFIXES
    )
    assert not undecided, (
        "Prefijos de API sin decisión sobre ABAC. Añade cada uno a "
        "ABAC_COVERED_PREFIXES (con su resource_type) o a ABAC_EXEMPT_PREFIXES "
        "(con el motivo):\n  - " + "\n  - ".join(undecided)
    )


def test_covered_prefixes_are_reachable_by_the_abac_dependency():
    """Cada prefijo declarado cubierto tiene rutas vivas que la dependencia alcanza.

    Antes de la auditoría 2026-08 la cobertura era ASPIRACIONAL: de los 110
    prefijos declarados, 45 (261 rutas) no tenían ni un endpoint que llamase a
    `enforce_abac()`. Una política ABAC sobre facturas, por ejemplo, no se
    aplicaba en /api/v1/invoices: existía en la interfaz y no hacía nada.

    Ahora `apply_abac_for_route` cuelga de los routers v1 y v2 completos, así que
    basta con que el prefijo resuelva contra rutas reales. Este test comprueba
    las dos mitades: que el prefijo tiene rutas, y que el resolvedor de la
    dependencia las asocia a un resource_type.
    """
    from app.core.abac_dependency import _resolve_coverage

    live_paths = [path for _r, path, _m, _d, _e in _api_routes()]

    sin_rutas: list[str] = []
    sin_resolver: list[str] = []
    for prefix in ABAC_COVERED_PREFIXES:
        matching = [p for p in live_paths if p == prefix or p.startswith(prefix + "/")]
        if not matching:
            sin_rutas.append(prefix)
            continue
        # El prefijo más específico gana; para una ruta bajo este prefijo, el
        # resolvedor debe devolver algo (puede ser un prefijo más específico).
        if _resolve_coverage(matching[0]) is None:
            sin_resolver.append(prefix)

    assert not sin_rutas, (
        "Prefijos declarados cubiertos que no tienen ninguna ruta viva:\n  - "
        + "\n  - ".join(sorted(sin_rutas))
    )
    assert not sin_resolver, (
        "Prefijos cuyas rutas la dependencia ABAC no resuelve:\n  - "
        + "\n  - ".join(sorted(sin_resolver))
    )


def test_abac_dependency_is_registered_on_both_api_routers():
    """La cobertura entera depende de este registro: si desaparece, vuelve a ser ficción."""
    from app.core.abac_dependency import apply_abac_for_route

    covered = 0
    for _route, _path, _m, dependant, _e in _api_routes():
        if any(d.call is apply_abac_for_route for d in dependant.dependencies):
            covered += 1
    total = sum(1 for _ in _api_routes())
    assert covered == total, (
        f"apply_abac_for_route sólo cuelga de {covered} de {total} rutas de /api/v*. "
        "Debe registrarse en los include_router de v1 y v2 en app/main.py."
    )


def test_no_prefix_is_both_covered_and_exempt():
    overlap = sorted(set(ABAC_COVERED_PREFIXES) & set(ABAC_EXEMPT_PREFIXES))
    assert not overlap, f"Prefijos declarados a la vez cubiertos y exentos: {overlap}"


def test_maps_have_no_stale_prefixes():
    live = _first_level_prefixes()
    stale_covered = sorted(
        p for p in ABAC_COVERED_PREFIXES if "/".join(p.split("/")[:4]) not in live
    )
    stale_exempt = sorted(p for p in ABAC_EXEMPT_PREFIXES if p not in live)
    assert not stale_covered, f"Prefijos cubiertos que ya no existen: {stale_covered}"
    assert not stale_exempt, f"Prefijos exentos que ya no existen: {stale_exempt}"


def test_exemptions_document_a_reason():
    empty = sorted(p for p, reason in ABAC_EXEMPT_PREFIXES.items() if not (reason or "").strip())
    assert not empty, f"Exenciones sin motivo escrito: {empty}"


# ── 2. enforce_abac nunca es el único control ─────────────────────────────────

#: Nombres cuyo código NO cuenta como «otro control».
#:
#: Auditoría 2026-09. Esto faltaba, y sin ello **este test no podía fallar
#: nunca por el motivo que existe para detectar**. El barrido resolvía cada
#: nombre llamado por el endpoint —incluido `enforce_abac`— y concatenaba su
#: código fuente al blob donde busca señales de autorización. Y el cuerpo de
#: `enforce_abac` contiene `is_superadmin` y `user.role`, que son dos de esas
#: señales.
#:
#: Es decir: una ruta cuyo único control fuera `enforce_abac` pasaba el test
#: porque el propio `enforce_abac` «tenía señales de control». El guardián se
#: satisfacía a sí mismo con la función que está investigando.
#:
#: Salió al bajar la complejidad de `enforce_abac` (hallazgo 18): al mover el
#: corte de superadmin y el 403 a dos ayudantes, las señales desaparecieron de
#: su cuerpo y el test se puso rojo de golpe. No era una regresión — era la
#: primera vez que medía.
NO_CUENTAN_COMO_CONTROL = {"enforce_abac"}


def _called_service_sources(endpoint) -> str:
    """Código del endpoint más el de las funciones que invoca en su módulo.

    Un nivel de profundidad: alcanza para ver el `_svc.delete_client(...)` típico
    de este proyecto, donde la comprobación de rol vive en el servicio.

    `enforce_abac` se excluye a propósito: ver `NO_CUENTAN_COMO_CONTROL`.
    """
    src = _source(endpoint)
    blobs = [src]
    module = inspect.getmodule(endpoint)
    try:
        tree = ast.parse(src.lstrip())
    except Exception:
        return "\n".join(blobs)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name:
                names.add(name)

    for name in names - NO_CUENTAN_COMO_CONTROL:
        target = getattr(module, name, None)
        if target is None and module is not None:
            for attr in dir(module):
                holder = getattr(module, attr, None)
                candidate = getattr(holder, name, None)
                if callable(candidate):
                    target = candidate
                    break
        if callable(target):
            blobs.append(_source(target))
    return "\n".join(blobs)


#: Rutas cuyo ÚNICO control aparente es `enforce_abac()`, que es fail-open.
#:
#: ══ Esto es deuda medida, no una lista de exenciones ══
#:
#: Auditoría 2026-09. Hasta hoy este test pasaba **en verde con cero rutas**, y
#: era mentira: `_called_service_sources` resolvía cada nombre llamado por el
#: endpoint —incluido `enforce_abac`— y concatenaba su código al blob donde
#: busca señales de autorización. Como el cuerpo de `enforce_abac` contiene
#: `is_superadmin` y `user.role`, **toda** ruta cuyo único control fuera
#: `enforce_abac` quedaba tapada por el propio `enforce_abac`. El guardián se
#: satisfacía a sí mismo con la función que investiga.
#:
#: Salió al bajar la complejidad de `enforce_abac` (hallazgo 18): al mover el
#: corte de superadmin y el 403 a dos ayudantes, las señales desaparecieron de
#: su cuerpo y el test se puso rojo de golpe sobre 65 rutas. Once de ellas eran
#: ruido de la heurística —usaban la comprobación de propiedad
#: `..._for_user(db, id, current_user.id)`, que es un control legítimo y no
#: estaba en la lista de señales—, así que se añadió. Quedan éstas.
#:
#: **49 de las 54 son DELETE.** Es lo que hay que mirar primero: un borrado
#: cuyo único guardia no comprueba nada mientras la organización no tenga
#: políticas ABAC activas —que es el caso por defecto—.
#:
#: Cada una necesita una decisión propia: guarda de rol en la ruta, o
#: comprobación de propiedad o de organización en el servicio. No se arreglan
#: en un barrido, y forzar uno sería justo lo contrario de lo que este test
#: existe para evitar.
#:
#: La regla del trinquete es la de siempre en este repo: **la lista sólo puede
#: encoger**. Una ruta nueva en esta situación rompe el test; una que se arregle
#: y no se quite de aquí, también.
ABAC_UNICO_CONTROL_CONOCIDAS = {
    "DELETE /api/v1/alm/assets/{aid}/installs/{iid}",
    "DELETE /api/v1/alm/licenses/{lid}/assignments/{aid}",
    "DELETE /api/v1/bi/alerts/custom-metrics/{key}",
    "DELETE /api/v1/bi/alerts/rules/{rule_id}",
    "DELETE /api/v1/bi/bookmarks/{bookmark_id}",
    "DELETE /api/v1/bi/collaboration/dashboards/{dashboard_key}/shares/{share_id}",
    "DELETE /api/v1/bi/delivery/rules/{rule_id}",
    "DELETE /api/v1/bi/delivery/schedules/{schedule_id}",
    "DELETE /api/v1/bi/embed/token/{jti}",
    "DELETE /api/v1/bi/intelligence/query-builder/templates/{template_id}",
    "DELETE /api/v1/bi/platform/connectors/custom/{connector_id}",
    "DELETE /api/v1/bi/platform/governance/field-sensitivity/{sensitivity_id}",
    "DELETE /api/v1/bi/query-builder/queries/{query_id}",
    "DELETE /api/v1/bi/reports/v2/presets/{preset_id}/customize",
    "DELETE /api/v1/bi/reports/v2/templates/{template_id}",
    "DELETE /api/v1/bookings/api-keys/{key_id}",
    "DELETE /api/v1/capacity/plans/{plan_id}",
    "DELETE /api/v1/clients/{cid}",
    "DELETE /api/v1/clients/{cid}/contacts/{contact_id}",
    "DELETE /api/v1/clients/{cid}/contracts/{link_id}",
    "DELETE /api/v1/clients/{cid}/licenses/{link_id}",
    "DELETE /api/v1/clients/{cid}/projects/{project_id}/link",
    "DELETE /api/v1/cmdb/wiki-pages/{page_id}/tags/{tag_id}",
    "DELETE /api/v1/collaboration/conversations/{conversation_id}/members/{user_id}",
    "DELETE /api/v1/collaboration/conversations/{conversation_id}/pins/{message_id}",
    "DELETE /api/v1/collaboration/integrations/{integration_id}",
    "DELETE /api/v1/collaboration/messages/{message_id}",
    "DELETE /api/v1/collaboration/push/unsubscribe",
    "DELETE /api/v1/collaboration/saved/{message_id}",
    "DELETE /api/v1/collaboration/search/saved/{saved_id}",
    "DELETE /api/v1/collaboration/teams/{team_id}/members/{user_id}",
    "DELETE /api/v1/collaboration/tus/{uid}",
    "DELETE /api/v1/dashboard-widgets/reset",
    "DELETE /api/v1/enterprise/notifications/clear-old",
    "DELETE /api/v1/epics/comments/{comment_id}",
    "DELETE /api/v1/epics/filters/{filter_id}",
    "DELETE /api/v1/epics/{epic_id}/tasks/{task_id}",
    "DELETE /api/v1/esign/{envelope_id}",
    "DELETE /api/v1/marketplace/uninstall",
    "DELETE /api/v1/mfa/disable",
    "DELETE /api/v1/reports/templates/{template_id}",
    "DELETE /api/v1/sd/assets/{asset_id}",
    "DELETE /api/v1/sd/autonomous/playbooks/{playbook_id}",
    "DELETE /api/v1/sd/changes/{change_id}",
    "DELETE /api/v1/sd/rca/templates/{template_id}",
    "DELETE /api/v1/sd/tickets/{ticket_id}/internal-comments/{comment_id}",
    "DELETE /api/v1/sd/tickets/{ticket_id}/links/{link_id}",
    "DELETE /api/v1/task-dependencies/{dep_id}",
    "DELETE /api/v1/tasks/dependencies/{dep_id}",
    "GET /api/v1/users/org-chart",
    "PATCH /api/v1/alerts/{alert_id}/read",
    "PATCH /api/v1/users/{user_id}",
    "POST /api/v1/documents",
    "POST /api/v1/documents/upload",
}


def test_enforce_abac_is_never_the_only_authorization_control():
    """`enforce_abac()` es fail-open: sin políticas activas no comprueba nada.

    Toda ruta que lo llame necesita ADEMÁS un control real: una guarda de rol en
    la firma del endpoint, o una comprobación de rol, propiedad u organización
    en la capa de servicio.

    Heurística por diseño: detecta la ausencia total de control, no valida que
    cada comprobación concreta sea la adecuada. Descarta el fallo catastrófico
    («no hay nada»), no sustituye a una revisión de autorización por endpoint.

    Dos reglas, no una:

    1. Una ruta que **no esté** en `ABAC_UNICO_CONTROL_CONOCIDAS` no puede
       quedarse sin control. Es la que importa: el código nuevo nace guardado.
    2. Una ruta que **sí esté** y se haya arreglado tiene que salir de la lista.
       Si no, el test falla y pide que se quite. Es a propósito: mantiene la
       foto honesta y hace visible cada mejora.
    """
    sin_control: set[str] = set()
    for _route, path, methods, dependant, endpoint in _api_routes():
        if not _calls_enforce_abac(_source(endpoint)):
            continue
        if {d.call for d in dependant.dependencies} & ROUTE_ROLE_GUARDS:
            continue  # guarda de rol en la ruta
        if SERVICE_AUTHZ_SIGNALS.search(_called_service_sources(endpoint)):
            continue  # control en la capa de servicio
        sin_control.add(f"{','.join(sorted(methods)) or '?'} {path}")

    nuevas = sin_control - ABAC_UNICO_CONTROL_CONOCIDAS
    assert not nuevas, (
        "Rutas NUEVAS cuyo único control aparente es enforce_abac(), que es "
        "fail-open. Añade una guarda de rol en la ruta o una comprobación en el "
        "servicio:\n  - " + "\n  - ".join(sorted(nuevas))
    )

    arregladas = ABAC_UNICO_CONTROL_CONOCIDAS - sin_control
    assert not arregladas, (
        "Estas rutas YA tienen control y siguen en ABAC_UNICO_CONTROL_CONOCIDAS. "
        "Quítalas de la lista — el trinquete sólo sirve si la foto es honesta:"
        "\n  - " + "\n  - ".join(sorted(arregladas))
    )


def test_abac_middleware_stays_deleted():
    """El middleware ABAC era un no-op; no debe volver sin cablear la auth.

    Si alguien lo reintroduce, tiene que resolver antes las dos razones por las
    que se borró: `request.state.user` no lo puebla nadie (habría que decodificar
    el JWT en middleware, creando una segunda vía de autenticación), y el mapa de
    prefijos usa action="read" para todo, así que un DELETE se comprobaría como
    lectura.
    """
    import importlib

    try:
        importlib.import_module("app.core.abac_middleware")
    except ModuleNotFoundError:
        return
    raise AssertionError(
        "app/core/abac_middleware.py ha vuelto. Antes de reintroducirlo hay que "
        "poblar request.state.user y dar a cada prefijo su action real; si no, es "
        "otra vez un no-op que aparenta proteger."
    )
