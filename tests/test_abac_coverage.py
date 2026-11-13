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
import io
import tokenize
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
    r"\.id\s*==\s*current_user\.id|,\s*current_user\.id\s*\)|"
    # La misma comprobacion cuando el servicio llama `user` a su parametro, que
    # es como esta escrito medio `app/services/collaboration/`:
    #   `CollaborationSavedMessage.user_id == user.id`
    #   `if msg.user_id != user.id and not ...: raise HTTPException(403, ...)`
    r"\.user_id\s*[=!]=\s*\w+\.id|\w+\.id\s*[=!]=\s*\w+\.user_id|"
    # Y el acotado por ORGANIZACION del usuario autenticado, que el docstring
    # de este test ya nombraba como control valido y la expresion no reconocia.
    # El valor sale del sujeto autenticado, no de un parametro de la peticion:
    # por eso se exige que aparezca junto a `current_user`.
    r'getattr\(\s*current_user\s*,\s*["\']organization_id["\']|'
    r"current_user\.organization_id",
    re.IGNORECASE,
)


#: El endpoint entrega la identidad de QUIEN LLAMA hacia abajo.
#:
#: No vale cualquier id: tiene que salir del sujeto autenticado. Un `user_id`
#: que viene en el cuerpo de la peticion no acota nada.
#:
#: Se acepta tanto el id suelto —`delete_saved_filter(filter_id, cu.id, db)`—
#: como el objeto entero: `run_in_threadpool(svc.abortar, uid, current_user)`,
#: que es como esta escrito `collaboration/tus.py` y es igual de valido, porque
#: el servicio saca de ahi el `user.id` contra el que compara.
_ENTREGA_EL_ID_DEL_LLAMANTE = re.compile(
    r"\b(current_user|cu|user)\.id\b|\(\s*[^)]*\bcurrent_user\b\s*[,)]"
)

#: Aguas abajo se compara una columna de propiedad.
#:
#: Dos formas, las dos vistas en este proyecto:
#:   `SavedFilter.created_by == user_id`   -> atributo de modelo
#:   `meta.get("user_id") == user.id`      -> diccionario (subidas tus)
#: Auditoria 2026-09: esta expresion exige que el lado derecho de la
#: comparacion sea la identidad del llamante, no un valor cualquiera. Sin eso,
#: un filtro de busqueda corriente —`Comment.author_id == author_id`, donde
#: `author_id` llega en la query— pasaria por control de autorizacion. Es la
#: mitad que aprieta, y es lo que permite que la otra acepte tanto el id suelto
#: como el objeto usuario entero sin abrir la mano de verdad.
#: Las alternativas largas van primero: `user_id` no debe comerse el principio
#: de `current_user_id`, que es como se llama el parametro en `cab_service`.
_ID_DEL_LLAMANTE = (
    r"(?:current_user_id|usuario_id|_user_id|user_id"
    r"|current_user\.id|usuario\.id|user\.id|cu\.id)"
)

_COLUMNA_DE_PROPIEDAD = re.compile(
    r"\.(user_id|created_by|created_by_id|owner_id|author_id)\s*[=!]=\s*" + _ID_DEL_LLAMANTE + "|"
    r"""(?:\[|\.get\(\s*)["'](user_id|created_by|created_by_id|owner_id|author_id)["']"""
    r"\s*(?:\]|\))\s*[=!]=\s*" + _ID_DEL_LLAMANTE + "|"
    # Y la propiedad escrita en la CLAVE en vez de en una columna. Auditoria
    # 2026-09: `DELETE /reports/templates/{id}` aparecia «sin control» aunque
    # las plantillas son estrictamente por usuario, porque el acotado es
    #
    #     AppSetting.key == f"{_TEMPLATE_KEY_PREFIX}{user_id}"
    #
    # No hay columna de propiedad que comparar: el id del usuario ES parte de
    # la clave, asi que un usuario no puede nombrar la fila de otro. Se exige
    # que el id interpolado venga del sujeto autenticado —lo garantiza la otra
    # mitad de `_acota_por_propiedad`— y que forme parte de un valor comparado.
    r"[=!]=\s*f[\"\'][^\"\']*\{(user_id|current_user\.id|cu\.id|user\.id)\}"
)


def _acota_por_propiedad(endpoint) -> bool:
    """Control de propiedad reconocido exigiendo las DOS mitades a la vez.

    Auditoria 2026-09. `SERVICE_AUTHZ_SIGNALS` solo sabia de un puñado de
    formas literales (`.user_id == current_user.id` y parecidas) y marcaba como
    "sin control" rutas que si lo tenian, escrito con otro nombre de columna:

        delete_saved_filter(filter_id, cu.id, db)   # el endpoint
        ... SavedFilter.created_by == user_id ...   # el servicio, y 404 si no

    Eso es exactamente el control que hace falta. Ampliar la lista de nombres a
    secas seria demasiado laxo —`Task.assignee_id == assignee_id` es un filtro
    de busqueda, no una autorizacion—, asi que se exigen las dos mitades:

    1. el endpoint entrega el id del usuario autenticado hacia abajo, y
    2. aguas abajo ese valor se compara contra una columna de propiedad.

    Una sola de las dos no basta, y es justo esa conjuncion la que distingue
    "acotado a quien pregunta" de "filtrado por un parametro cualquiera".
    """
    if not _ENTREGA_EL_ID_DEL_LLAMANTE.search(_source(endpoint)):
        return False
    return bool(_COLUMNA_DE_PROPIEDAD.search(_called_service_sources(endpoint)))


def _sin_prosa(src: str) -> str:
    """El codigo sin comentarios ni docstrings.

    Auditoria 2026-09, y el guardian se volvio a satisfacer solo. Al documentar
    en `uninstall_integration` **por que** no lleva guarda, el docstring decia
    la frase «colgarle un `require_admin` haria pasar el test»... y la hizo
    pasar: `SERVICE_AUTHZ_SIGNALS` busca `require_` sobre el fuente en crudo,
    sin distinguir codigo de prosa.

    Es la misma familia que `NO_CUENTAN_COMO_CONTROL`: el detector creyendose
    una senal que no era una comprobacion. Y era mas grave de lo que parecia,
    porque valia para cualquier endpoint — bastaba un comentario que nombrase
    `is_superadmin`, `require_admin` o un 403 para que el barrido lo diera por
    protegido. Lo caza la segunda regla del trinquete, la que exige que una
    ruta que ya no aparece salga de la lista: sin ella el arreglo habria
    entrado en verde.

    Se quitan los comentarios y las cadenas de triple comilla. Las cadenas
    normales se quedan: hacen falta para `meta.get("user_id") == user.id` y
    para la clave `f"{_TEMPLATE_KEY_PREFIX}{user_id}"`, que si son codigo.
    """
    try:
        lineas = src.splitlines(keepends=True)
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            comilla = tok.string.lstrip("rbfuRBFU")[:3]
            prosa = tok.type == tokenize.COMMENT or (
                tok.type == tokenize.STRING and comilla in (chr(34) * 3, chr(39) * 3)
            )
            if not prosa:
                continue
            # Se blanquea EN SITIO, sin recomponer el fuente a partir de los
            # tokens: unirlos con un separador rompe la adyacencia y
            # `enforce_abac(` deja de encontrarse, que es la primera cosa que
            # este barrido necesita ver.
            (f0, c0), (f1, c1) = tok.start, tok.end
            for f in range(f0, f1 + 1):
                linea = lineas[f - 1]
                desde = c0 if f == f0 else 0
                hasta = c1 if f == f1 else len(linea)
                lineas[f - 1] = linea[:desde] + " " * (hasta - desde) + linea[hasta:]
        return "".join(lineas)
    except Exception:
        # Un fuente que no tokeniza (indentacion de `inspect.getsource` sobre un
        # metodo, por ejemplo) se devuelve tal cual: peor medido, nunca ciego.
        return src


def _source(fn) -> str:
    try:
        return _sin_prosa(inspect.getsource(fn))
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


#: Cuántos saltos de llamada se siguen desde el endpoint. Dos alcanza el patrón
#: de este proyecto —endpoint → servicio → ayudante—, que es donde vive la
#: comprobación en la mitad de los casos.
PROFUNDIDAD = 2


def _caminos_llamados(src: str) -> set[tuple[str, ...]]:
    """Los caminos de las llamadas del código: `('msg_svc', 'delete_message')`.

    Auditoría 2026-09: antes se guardaba **sólo el último nombre**
    (`delete_message`) y luego se buscaba ese nombre suelto por todo el módulo,
    quedándose con el primer objeto que lo tuviera. Con eso se resolvía a una
    función **distinta** de la que el endpoint llama —hay muchos
    `delete_message` en un proyecto— y la comprobación real no se veía: así se
    colaban 29 rutas en la lista de «sin control» teniéndolo.

    Guardar el camino y seguirlo entero resuelve la función correcta.
    """
    try:
        arbol = ast.parse(src.lstrip())
    except Exception:
        return set()

    caminos: set[tuple[str, ...]] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        fn = nodo.func
        caminos |= _caminos_de_trampolin(nodo, fn)
        if isinstance(fn, ast.Name):
            caminos.add((fn.id,))
        elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            caminos.add((fn.value.id, fn.attr))
        elif isinstance(fn, ast.Attribute):
            caminos.add((fn.attr,))
    return {c for c in caminos if c[-1] not in NO_CUENTAN_COMO_CONTROL}


#: Funciones que reciben OTRA funcion y la ejecutan por ti.
#:
#: Auditoria 2026-09: `DELETE /collaboration/tus/{uid}` aparecia «sin control»
#: teniendolo. Su cuerpo es:
#:
#:     await run_in_threadpool(svc.abortar, uid, current_user)
#:
#: y `svc.abortar` comprueba `meta.get("user_id") == user.id`. Pero para el AST
#: la unica llamada ahi es `run_in_threadpool`: `svc.abortar` es un *argumento*,
#: no un `Call`, asi que el barrido nunca llegaba a leer su codigo.
#:
#: La lista es cerrada a proposito. Seguir cualquier funcion pasada como
#: argumento a cualquier sitio haria el detector mas permisivo de lo que se
#: puede justificar; estos tres nombres si ejecutan lo que reciben, siempre.
TRAMPOLINES = {"run_in_threadpool", "add_task", "enqueue"}


def _caminos_de_trampolin(nodo: "ast.Call", fn) -> set[tuple[str, ...]]:
    """La funcion que se le pasa a un trampolin, como si se hubiera llamado."""
    nombre = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
    if nombre not in TRAMPOLINES:
        return set()
    caminos: set[tuple[str, ...]] = set()
    for arg in nodo.args:
        if isinstance(arg, ast.Name):
            caminos.add((arg.id,))
        elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
            caminos.add((arg.value.id, arg.attr))
    return caminos


def _resolver_camino(camino: tuple[str, ...], modulo):
    """Sigue el camino desde el módulo del endpoint. `None` si no lleva a nada."""
    objetivo = modulo
    for paso in camino:
        objetivo = getattr(objetivo, paso, None)
        if objetivo is None:
            return None
    return objetivo if callable(objetivo) else None


def _called_service_sources(endpoint) -> str:
    """Código del endpoint más el de las funciones que invoca en su módulo.

    Un nivel de profundidad: alcanza para ver el `_svc.delete_client(...)` típico
    de este proyecto, donde la comprobación de rol vive en el servicio.

    `enforce_abac` se excluye a propósito: ver `NO_CUENTAN_COMO_CONTROL`.
    """
    blobs = [_source(endpoint)]
    frontera = [(endpoint, blobs[0])]

    # Dos niveles: el endpoint llama al servicio, y el servicio suele delegar
    # en un ayudante que es donde de verdad está la comprobación.
    for _ in range(PROFUNDIDAD):
        siguiente = []
        for fn, src in frontera:
            modulo = inspect.getmodule(fn)
            for camino in _caminos_llamados(src):
                destino = _resolver_camino(camino, modulo)
                if destino is None:
                    continue
                fuente = _source(destino)
                if fuente:
                    blobs.append(fuente)
                    siguiente.append((destino, fuente))
        frontera = siguiente
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
#: Empezaron siendo 54. **Veintinueve eran falsos positivos del detector**, no
#: rutas sin control, y arreglarlo fue la mitad del trabajo:
#:
#:  · Resolvía los nombres llamados **sueltos** —`delete_message`— y se quedaba
#:    con el primer objeto del módulo que tuviera uno igual. En un proyecto con
#:    varios `delete_message` eso resuelve a **otra** función, y la comprobación
#:    real no se ve. Ahora sigue el camino entero (`msg_svc.delete_message`).
#:  · Miraba **un solo salto**. El patrón de aquí es endpoint → servicio →
#:    ayudante, y la comprobación vive en el tercero la mitad de las veces.
#:  · No reconocía dos idiomas de control que este proyecto usa a diario: la
#:    propiedad escrita como `fila.user_id == user.id` —cuando el servicio
#:    llama `user` a su parámetro— y el acotado por organización
#:    `organization_id=getattr(current_user, "organization_id", None)`, que el
#:    propio docstring de este test ya nombraba como control válido.
#:
#: Cada ampliación se añadió **después de leer el código** que la justifica, no
#: para poner el test en verde. Las 25 que quedan se comprobaron a mano: no
#: tienen guarda de rol, ni comprobación de propiedad, ni acotado explícito por
#: organización en ninguno de los dos saltos.
#:
#: **Las 25 son DELETE salvo ninguna**: borrados de objetos de negocio de la
#: organización —clientes, planes de capacidad, activos, cambios, plantillas,
#: claves de API—. El filtrado automático de `TenantSession` impide que un
#: cliente toque los de otro; lo que NO hay es control de quién, dentro de la
#: misma organización, puede borrarlos. Hoy puede cualquier empleado.
#:
#: Cada una necesita una decisión propia: guarda de rol en la ruta, o
#: comprobación de propiedad o de organización en el servicio. No se arreglan
#: en un barrido, y forzar uno sería justo lo contrario de lo que este test
#: existe para evitar.
#:
#: La regla del trinquete es la de siempre en este repo: **la lista sólo puede
#: encoger**. Una ruta nueva en esta situación rompe el test; una que se arregle
#: y no se quite de aquí, también.
ABAC_UNICO_CONTROL_CONOCIDAS: set[str] = set()
# Auditoria 2026-09, segunda pasada: de 24 rutas a 1.
#
# De las 24, **ocho no tenian el problema**: el control existia y el
# detector no sabia leerlo. Cada limite esta arreglado y documentado donde
# vive: `_acota_por_propiedad` (el id del llamante baja y se compara contra
# una columna de propiedad), `TRAMPOLINES` (funciones que se pasan a
# `run_in_threadpool` en vez de llamarse) y la propiedad escrita en la
# clave de `AppSetting` en vez de en una columna.
#
# Las otras quince llevan ya una guarda de rol, con el motivo escrito junto
# a cada una. El criterio, para que se pueda discutir: **borrar no puede
# ser mas facil que crear**. Donde crear ya exigia gestor (ALM) la guarda
# es la misma; donde crear esta abierto y la operacion es la inversa exacta
# y reversible (vinculos entre tickets, etiquetas de wiki) se excluye solo
# al subcontratista; y donde la operacion es de gestion por naturaleza
# (capacidad, clientes, activos, cambios) se exige gestor. `esign` es el
# unico con control de propiedad y no de rol, porque crear la solicitud
# esta abierto y un `require_any_manager` habria atrapado al solicitante.
#
# Quedaba una, `DELETE /api/v1/marketplace/uninstall`: no hacia nada (todo el
# router de marketplace era una fachada). Segunda auditoria 2026-11: el modulo
# se borro entero, sin llamadas desde el frontend ni documentacion.



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
        if _acota_por_propiedad(endpoint):
            continue  # el id del llamante baja y se compara contra su columna
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
