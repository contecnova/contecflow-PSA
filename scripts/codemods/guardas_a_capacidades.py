"""Guardas de rol → capacidades del catálogo (auditoría 22-11-2026, informe 01, M9).

Pasa `Depends(require_admin)` y compañía (`require_admin_or_pm`,
`require_admin_or_hr`, `require_any_manager`, `require_internal_user`,
`require_worker`) de los endpoints de `app/api` a
`Depends(requiere_capacidad("<area>.<accion>"))`, con **la misma audiencia**:

- cada fichero de endpoints tiene un **área** (`AREA_DE_FICHERO`);
- cada guarda de rol es un **conjunto de roles** (`ROLES_DE_GUARDA`), y la
  capacidad elegida para (área, guarda) tiene exactamente esos roles;
- se reutiliza una capacidad del catálogo si ya existe con ese nombre, los
  mismos roles y sin `modulo` (o solo admin, a quien no se le cierra módulo);
  si el nombre está cogido con otros roles se prueba el siguiente de
  `ACCIONES`; si no existe, se crea (bloque generado de
  `app/core/capacidades.py`, `modulo=None`, así que no cierra más que la guarda
  de rol de antes: `RequiereCapacidad` solo añade el cierre por módulo, y una
  capacidad sin módulo no lo tiene).

El superadmin pasa igual con las dos guardas. El rol personalizado solo quita
por módulo, y eso lo sigue haciendo `modulos.comprobar` en `get_current_user`.

Modos:
    --plan            imprime (área, guarda) → capacidad y las capacidades nuevas.
    --aplicar         reescribe los endpoints, ajusta los imports y regenera el
                      bloque de capacidades nuevas (entre marcas) del catálogo.

Idempotente. Conserva CRLF/LF de cada fichero y hace `py_compile` de lo que toca.
"""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
API = RAIZ / "app" / "api"
CATALOGO = RAIZ / "app" / "core" / "capacidades.py"
FRONT = RAIZ / "frontend" / "src" / "permisos" / "capacidades.ts"

#: Guarda de rol → constante de roles de `app/core/capacidades.py`.
ROLES_DE_GUARDA = {
    "require_admin": "ADMIN",
    "require_admin_or_pm": "ADMIN_PM",
    "require_admin_or_hr": "ADMIN_RRHH",
    "require_any_manager": "GESTORES",
    "require_internal_user": "INTERNOS",
    "require_worker": "TODOS",
}
VALOR = {
    "ADMIN": ("admin",),
    "ADMIN_PM": ("admin", "pm"),
    "ADMIN_RRHH": ("admin", "hr"),
    "GESTORES": ("admin", "pm", "team_lead", "hr"),
    "INTERNOS": ("admin", "pm", "team_lead", "hr", "employee"),
    "TODOS": ("admin", "pm", "team_lead", "hr", "employee", "subcontractor"),
}

#: Acciones preferidas por guarda, en orden (si el nombre está cogido con otros roles, la siguiente).
ACCIONES = {
    "require_admin": ("administrar", "configurar", "admin"),
    "require_admin_or_pm": ("gestionar", "dirigir", "direccion_pm"),
    "require_admin_or_hr": ("rrhh", "personas_rrhh"),
    "require_any_manager": ("gestionar", "responsables", "gestores"),
    "require_internal_user": ("usar", "consultar", "internos"),
    "require_worker": ("trabajar", "trabajo_diario"),
}
QUIEN = {
    "require_admin": "dirección",
    "require_admin_or_pm": "dirección y PM",
    "require_admin_or_hr": "dirección y RRHH",
    "require_any_manager": "responsables: dirección, PM, jefes de equipo y RRHH",
    "require_internal_user": "personal interno",
    "require_worker": "internos y externos: trabajo diario, el servicio acota a lo suyo",
}
VERBO = {
    "require_admin": "administrar",
    "require_admin_or_pm": "gestionar",
    "require_admin_or_hr": "gestionar",
    "require_any_manager": "gestionar",
    "require_internal_user": "usar",
    "require_worker": "trabajar",
}

#: (área, guarda) → capacidad ya existente que es la misma decisión (mismos roles).
ELEGIDAS = {
    ("sd", "require_internal_user"): "sd.completo",
    ("alm", "require_any_manager"): "alm.gestionar",
}

#: Fichero (relativo a app/api/v1) → área de la capacidad.
AREA_DE_FICHERO = {
    "endpoints/abac.py": "gobierno", "endpoints/accounting_hub.py": "finanzas",
    "endpoints/activity.py": "colaboracion", "endpoints/advanced_config.py": "org",
    "endpoints/ai_chat.py": "ia", "endpoints/ai_governance.py": "ia", "endpoints/ai_modules.py": "ia",
    "endpoints/ai_planning.py": "ia", "endpoints/ai_providers.py": "ia", "endpoints/alerts.py": "alertas",
    "endpoints/alm_integracion.py": "alm", "endpoints/analytics.py": "analitica",
    "endpoints/analytics_extended.py": "analitica", "endpoints/approval_builder.py": "aprobaciones",
    "endpoints/approvals.py": "aprobaciones", "endpoints/ausencias.py": "ausencias",
    "endpoints/automations.py": "automatizacion", "endpoints/baselines.py": "proyectos",
    "endpoints/billing_reports.py": "facturacion", "endpoints/bookings.py": "reservas",
    "endpoints/bpmn_instances.py": "bpm", "endpoints/bpmn_processes.py": "bpm",
    "endpoints/branding.py": "org", "endpoints/budgets.py": "presupuestos", "endpoints/cab.py": "cab",
    "endpoints/capacity.py": "recursos", "endpoints/cartera_intake.py": "cartera",
    "endpoints/changes.py": "cambios", "endpoints/client_portal.py": "clientes",
    "endpoints/clients.py": "clientes", "endpoints/cmdb.py": "cmdb", "endpoints/cmdb_riesgo.py": "software",
    "endpoints/cmdb_software.py": "software", "endpoints/conectores.py": "integraciones",
    "endpoints/contracts.py": "contratos", "endpoints/currency_rates.py": "divisas",
    "endpoints/currency_sync.py": "divisas", "endpoints/custom_fields.py": "proyectos",
    "endpoints/dashboard.py": "panel", "endpoints/deliverables.py": "proyectos",
    "endpoints/documents_collab.py": "colaboracion", "endpoints/enterprise.py": "empresa",
    "endpoints/epics.py": "proyectos", "endpoints/esign.py": "firma", "endpoints/events.py": "org",
    "endpoints/expenses.py": "gastos", "endpoints/export_template.py": "exportar",
    "endpoints/git_integration.py": "integraciones", "endpoints/governance.py": "gobierno",
    "endpoints/grc.py": "gobierno", "endpoints/horas_extra.py": "horas_extra",
    "endpoints/imputations.py": "partes", "endpoints/integrations/__init__.py": "integraciones",
    "endpoints/integrations_hub.py": "integraciones", "endpoints/invoices.py": "facturacion",
    "endpoints/issue_types.py": "proyectos", "endpoints/jira.py": "integraciones",
    "endpoints/jira_integration.py": "integraciones", "endpoints/lecciones.py": "proyectos",
    "endpoints/m365.py": "integraciones", "endpoints/m365_bi.py": "integraciones", "endpoints/mcp.py": "ia",
    "endpoints/milestones.py": "proyectos", "endpoints/nps.py": "clientes", "endpoints/okrs.py": "okr",
    "endpoints/pdf_export.py": "exportar", "endpoints/performance.py": "evaluaciones",
    "endpoints/pipeline.py": "comercial", "endpoints/planificacion.py": "proyectos",
    "endpoints/politicas.py": "gobierno", "endpoints/portal_conversations.py": "clientes",
    "endpoints/portfolio.py": "cartera", "endpoints/predictions.py": "analitica",
    "endpoints/predictive_observability.py": "observabilidad",
    "endpoints/profitability.py": "finanzas", "endpoints/projects/__init__.py": "proyectos",
    "endpoints/raci.py": "proyectos", "endpoints/report_builder.py": "informes",
    "endpoints/resource_forecast.py": "recursos", "endpoints/resources.py": "recursos",
    "endpoints/revenue.py": "finanzas", "endpoints/risks.py": "proyectos", "routers/auth_saml.py": "org",
    "endpoints/salesforce_sync.py": "integraciones", "endpoints/scenarios.py": "recursos",
    "endpoints/security_observability.py": "soc", "endpoints/semantic_engine.py": "ia",
    "endpoints/skills.py": "competencias", "endpoints/slack.py": "integraciones",
    "endpoints/slack_block_kit.py": "integraciones", "endpoints/sprints.py": "proyectos",
    "endpoints/tasks.py": "tareas", "endpoints/templates.py": "proyectos", "endpoints/timesheets.py": "partes",
    "endpoints/traduccion.py": "traduccion", "endpoints/training.py": "formacion", "endpoints/users.py": "personas",
}

#: Prefijos de fichero → área (lo que no está arriba).
AREA_DE_CARPETA = (
    ("endpoints/bi_", "bi"),
    ("endpoints/collaboration/", "colaboracion"),
    ("endpoints/service_desk/cmdb", "cmdb"),
    ("endpoints/service_desk/", "sd"),
)

AREA_DESCRIPCION = {
    "gobierno": "Gobierno (ABAC, GRC, políticas, gobierno de IA y datos)", "finanzas": "Finanzas",
    "colaboracion": "Colaboración", "org": "Empresa (configuración avanzada, marca, eventos, SSO)",
    "ia": "IA (asistente, módulos, proveedores, planificación)", "alertas": "Alertas", "alm": "Licencias y activos",
    "analitica": "Analítica y predicciones", "aprobaciones": "Aprobaciones", "ausencias": "Ausencias",
    "automatizacion": "Automatizaciones", "proyectos": "Proyectos", "facturacion": "Facturación e informes de facturación",
    "reservas": "Reservas", "bpm": "Procesos BPM", "presupuestos": "Presupuestos", "cab": "CAB de cambios",
    "recursos": "Recursos y capacidad", "cartera": "Cartera", "cambios": "Cambios de proyecto",
    "clientes": "Clientes y su portal", "cmdb": "CMDB", "software": "Software de la CMDB",
    "integraciones": "Integraciones y conectores", "contratos": "Contratos", "divisas": "Tipos de cambio",
    "panel": "Paneles", "empresa": "Empresa extendida (externos, webhooks, subcontratas)", "firma": "Firma electrónica",
    "gastos": "Gastos", "exportar": "Exportaciones", "horas_extra": "Horas extra", "partes": "Imputaciones y partes",
    "okr": "OKR", "evaluaciones": "Evaluaciones", "comercial": "Pipeline comercial",
    "observabilidad": "Observabilidad predictiva", "informes": "Generador de informes",
    "soc": "Observabilidad de seguridad (SOC)", "competencias": "Competencias", "tareas": "Tareas", "traduccion": "Traducción",
    "formacion": "Formación", "personas": "Personas y usuarios", "bi": "BI", "sd": "Service desk",
}

GUARDA = re.compile(r"\bDepends\(\s*(require_(?:admin_or_pm|admin_or_hr|any_manager|internal_user|worker|admin))\s*\)")
INICIO = "    # >>> guardas_a_capacidades (generado: scripts/codemods/guardas_a_capacidades.py --aplicar)\n"
FIN = "    # <<< guardas_a_capacidades\n"
INICIO_TS = "  // >>> guardas_a_capacidades (generado: scripts/codemods/guardas_a_capacidades.py --aplicar)\n"
FIN_TS = "  // <<< guardas_a_capacidades\n"


def area_de(rel: str) -> str | None:
    if rel in AREA_DE_FICHERO:
        return AREA_DE_FICHERO[rel]
    for prefijo, area in AREA_DE_CARPETA:
        if rel.startswith(prefijo):
            return area
    return None


def _leer(p: Path) -> tuple[str, str]:
    crudo = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in crudo else "\n"
    return crudo.replace("\r\n", "\n"), nl


def _escribir(p: Path, texto: str, nl: str) -> None:
    p.write_bytes((texto.replace("\n", nl) if nl != "\n" else texto).encode("utf-8"))


def _catalogo_existente() -> dict[str, tuple[tuple[str, ...], bool]]:
    """nombre → (roles, tiene módulo), leído del fuente, sin el bloque generado."""
    texto, _ = _leer(CATALOGO)
    if INICIO in texto:
        texto = texto[:texto.index(INICIO)] + texto[texto.index(FIN) + len(FIN):]
    import ast
    constantes = dict(VALOR, ADMIN_PM_RRHH=("admin", "pm", "hr"), ADMIN_PM_JEFE=("admin", "pm", "team_lead"),
                      NADIE=())
    salida = {}
    for nodo in ast.walk(ast.parse(texto)):
        if isinstance(nodo, ast.AnnAssign) and getattr(nodo.target, "id", "") == "CAPACIDADES":
            for k, v in zip(nodo.value.keys, nodo.value.values):
                a = v.args[0]
                roles = constantes.get(a.id, ("?",)) if isinstance(a, ast.Name) else tuple(e.value for e in a.elts)
                modulo = v.args[2] if len(v.args) > 2 else next((kw.value for kw in v.keywords
                                                                 if kw.arg == "modulo"), None)
                con_modulo = modulo is not None and not (isinstance(modulo, ast.Constant) and modulo.value is None)
                salida[k.value] = (roles, con_modulo)
    return salida


def ficheros():
    for p in sorted((API / "v1").rglob("*.py")):
        rel = p.relative_to(API / "v1").as_posix()
        texto, _ = _leer(p)
        if GUARDA.search(texto) or rel == "endpoints/predictive_observability.py":
            yield p, rel, texto


def plan():
    existentes = _catalogo_existente()
    usos: dict[tuple[str, str], list[str]] = {}
    sin_area = []
    for p, rel, texto in ficheros():
        area = area_de(rel)
        guardas = set(GUARDA.findall(texto))
        if rel == "endpoints/predictive_observability.py":
            guardas.add("require_admin")
        if area is None:
            sin_area.append(rel)
            continue
        for g in guardas:
            usos.setdefault((area, g), []).append(rel)
    asignadas: dict[tuple[str, str], str] = {}
    nuevas: dict[str, tuple[str, str]] = {}
    for (area, g) in sorted(usos):
        roles = VALOR[ROLES_DE_GUARDA[g]]
        elegida = ELEGIDAS.get((area, g))
        if elegida:
            assert existentes[elegida][0] == roles, (elegida, roles)
            asignadas[(area, g)] = elegida
            continue
        for accion in ACCIONES[g]:
            nombre = f"{area}.{accion}"
            if nombre in nuevas:
                if nuevas[nombre][1] == g:
                    asignadas[(area, g)] = nombre
                    break
                continue
            if nombre in existentes:
                rs, con_modulo = existentes[nombre]
                if tuple(sorted(rs)) == tuple(sorted(roles)) and (not con_modulo or set(rs) <= {"admin"}):
                    asignadas[(area, g)] = nombre
                    break
                continue
            nuevas[nombre] = (area, g)
            asignadas[(area, g)] = nombre
            break
        else:
            raise SystemExit(f"sin nombre libre para {area} / {g}")
    return usos, asignadas, nuevas, sin_area


def _bloque_catalogo(nuevas) -> str:
    lineas = [INICIO,
              "    # Auditoría 22-11-2026 (M9): las guardas de rol de la API pasan a capacidades con\n",
              "    # EXACTAMENTE los roles de su `require_*` de antes y sin `modulo` (no cierran más).\n",
              "    # Nombre: <área del fichero>.<acción de la guarda>; ver el codemod.\n"]
    for nombre in sorted(nuevas):
        area, g = nuevas[nombre]
        desc = f"{AREA_DESCRIPCION.get(area, area)}: {VERBO[g]} ({QUIEN[g]})".replace('"', "'")
        lineas.append(f'    "{nombre}": _c({ROLES_DE_GUARDA[g]}, "{desc}"),\n')
    lineas.append(FIN)
    return "".join(lineas)


def _bloque_ts(nuevas) -> str:
    nombres = sorted(nuevas)
    filas = [INICIO_TS, "  // Auditoría 22-11-2026 (M9): capacidades de las guardas de la API que eran de rol.\n"]
    fila = "  "
    for n in nombres:
        trozo = f"'{n}', "
        if len(fila) + len(trozo) > 112:
            filas.append(fila.rstrip() + "\n")
            fila = "  "
        fila += trozo
    if fila.strip():
        filas.append(fila.rstrip() + "\n")
    filas.append(FIN_TS)
    return "".join(filas)


def _poner_bloque(texto: str, bloque: str, inicio: str, fin: str, ancla: str) -> str:
    if inicio in texto:
        return texto[:texto.index(inicio)] + bloque + texto[texto.index(fin) + len(fin):]
    i = texto.index(ancla)
    return texto[:i] + bloque + texto[i:]


_IMPORT = re.compile(r"^from app\.(?:core|api)\.deps import (\([^)]*\)|[^\n]*)\n", re.M)


def _arreglar_imports(texto: str) -> str:
    def sigue_usado(nombre: str, sin_imports: str) -> bool:
        return re.search(rf"\b{nombre}\b", sin_imports) is not None

    sin_imports = _IMPORT.sub("", texto)
    tiene_req = False

    def rehacer(m):
        nonlocal tiene_req
        cuerpo = m.group(1)
        parentesis = cuerpo.startswith("(")
        nombres = [n.strip() for n in re.sub(r"#[^\n]*", "", cuerpo.strip("()")).replace("\n", ",").split(",")]
        nombres = [n for n in nombres if n]
        quedan = []
        for n in nombres:
            base = n.split(" as ")[-1].strip()
            if base in ROLES_DE_GUARDA and not sigue_usado(base, sin_imports):
                continue
            quedan.append(n)
        if "requiere_capacidad" in sin_imports and not tiene_req and m.group(0).startswith("from app.core.deps"):
            if "requiere_capacidad" not in quedan:
                quedan.append("requiere_capacidad")
            tiene_req = True
        elif "requiere_capacidad" in quedan:
            tiene_req = True
        if quedan == nombres:
            return m.group(0)
        if not quedan:
            return ""
        if parentesis or len(", ".join(quedan)) > 90:
            return "from " + m.group(0).split(" ", 2)[1] + " import (\n" + "".join(f"    {n},\n" for n in quedan) + ")\n"
        return "from " + m.group(0).split(" ", 2)[1] + " import " + ", ".join(quedan) + "\n"

    nuevo = _IMPORT.sub(rehacer, texto)
    if "requiere_capacidad" in sin_imports and not tiene_req:
        # Sin import de app.core.deps (solo app.api.deps, o ninguno): se añade tras el primer import de deps
        # o tras el último `from app.` del principio.
        m = re.search(r"^from app\.api\.deps import (\([^)]*\)|[^\n]*)\n", nuevo, re.M) \
            or list(re.finditer(r"^from app\.[^\n]*\n", nuevo, re.M))[-1]
        nuevo = nuevo[:m.end()] + "from app.core.deps import requiere_capacidad\n" + nuevo[m.end():]
    return nuevo


def aplicar():
    usos, asignadas, nuevas, sin_area = plan()
    if len(usos) < 20:
        # Aplicado el 23-11-2026: ya no quedan guardas de rol que medir, y regenerar el
        # bloque desde aquí lo dejaría casi vacío. El bloque del catálogo es ya la fuente.
        raise SystemExit("ya aplicado: no quedan guardas de rol en app/api (el catálogo manda)")
    if sin_area:
        raise SystemExit(f"ficheros sin área: {sin_area}")
    # 1. Catálogo (backend y lista de tipos del frontend).
    texto, nl = _leer(CATALOGO)
    texto = _poner_bloque(texto, _bloque_catalogo(nuevas), INICIO, FIN, "}\n\n\ndef _valor")
    _escribir(CATALOGO, texto, nl)
    py_compile.compile(str(CATALOGO), doraise=True)
    texto, nl = _leer(FRONT)
    texto = _poner_bloque(texto, _bloque_ts(nuevas), INICIO_TS, FIN_TS, "] as const")
    _escribir(FRONT, texto, nl)
    # 2. Endpoints.
    tocados = 0
    for p, rel, texto in list(ficheros()):
        area = area_de(rel)
        _, nl = _leer(p)
        nuevo = GUARDA.sub(lambda m: f'Depends(requiere_capacidad("{asignadas[(area, m.group(1))]}"))', texto)
        nuevo = _arreglar_imports(nuevo)
        if nuevo != texto:
            _escribir(p, nuevo, nl)
            py_compile.compile(str(p), doraise=True)
            tocados += 1
    print(f"{tocados} ficheros; {len(nuevas)} capacidades nuevas; {len(asignadas)} pares (área, guarda)")


if __name__ == "__main__":
    if "--aplicar" in sys.argv:
        aplicar()
    else:
        usos, asignadas, nuevas, sin_area = plan()
        for k in sorted(asignadas):
            print(f"{k[0]:16} {k[1]:24} → {asignadas[k]}{'  (nueva)' if asignadas[k] in nuevas else ''}")
        print("sin área:", sin_area)
        print(len(nuevas), "nuevas")
