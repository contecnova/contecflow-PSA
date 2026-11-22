"""Matriz de permisos: catálogo de capacidades y roles reales (19-11-2026).

Antes los permisos de la pantalla estaban escritos a mano en ~300 sitios del
frontend (`roles={[...]}` en las rutas, `roles: [...]` en el menú, `hasRole`,
comparaciones directas de rol), con el menú y las rutas en desacuerdo y al menos seis
listas de roles distintas (algunas con roles que no existen: designer,
finance, developer). Ahora:

- **Una capacidad** es un permiso con nombre (`proyectos.ver`,
  `sd.config`, `gastos.gestionar`…) y los roles base que la tienen por defecto.
  La pantalla solo pregunta por capacidades (`usePermiso('x')` / `puede('x')`).
- **Las capacidades coinciden con las guardas del backend**: cada una que
  abre una pantalla o una acción declara una `sonda` (una llamada real de esa
  pantalla). `tests/test_capacidades.py` comprueba que quien tiene la
  capacidad no recibe 403 en su sonda y, si la sonda es `estricta`, que quien
  no la tiene sí lo recibe. Lo que se muestra no da 403.
- **Superadmin** las tiene todas (incluida `plataforma.empresas`, que nadie
  más tiene).
- **Rol personalizado** (`users.custom_role_id`, o la fila de sistema de su
  rol base): solo restringe. Una capacidad con `modulo` desaparece si ese
  módulo está cerrado para la persona (`app.core.modulos.vetados`), igual que
  la API devuelve 403 en sus rutas. Nunca da algo que el rol base no tenga.
- Las capacidades llegan en `/auth/me` y en el login (`UserPublic.capacidades`,
  puestas por `app.core.modulos.con_rutas_cerradas`). Los roles reales, con
  sus etiquetas en es/en/zh, en `GET /auth/roles`.

Documentado en DOCS.md («Matriz de permisos»). La declaración de rutas y menú
del frontend está en `frontend/src/permisos/navegacion.tsx`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.user import UserRole

# ── Roles base reales ────────────────────────────────────────────────────────

#: Roles de `users.role`, en el orden en que se ofrecen en los selectores.
ROLES: tuple[str, ...] = tuple(r.value for r in UserRole)

#: Etiquetas de los roles (las mismas que `rol_usuario` en i18n/langs/*.mjs).
ETIQUETAS_DE_ROL: dict[str, dict[str, str]] = {
    "admin":         {"es": "Dirección", "en": "Management", "zh": "管理层"},
    "pm":            {"es": "Project Manager", "en": "Project Manager", "zh": "项目经理"},
    "team_lead":     {"es": "Team Lead", "en": "Team Lead", "zh": "团队负责人"},
    "hr":            {"es": "RRHH", "en": "HR", "zh": "人力资源"},
    "employee":      {"es": "Empleado", "en": "Employee", "zh": "员工"},
    "subcontractor": {"es": "Externo", "en": "External", "zh": "外部人员"},
}

TODOS = ROLES
INTERNOS = ("admin", "pm", "team_lead", "hr", "employee")          # require_internal_user
GESTORES = ("admin", "pm", "team_lead", "hr")                      # require_any_manager
ADMIN_PM = ("admin", "pm")                                         # require_admin_or_pm
ADMIN_RRHH = ("admin", "hr")                                       # require_admin_or_hr
ADMIN_PM_RRHH = ("admin", "pm", "hr")
ADMIN_PM_JEFE = ("admin", "pm", "team_lead")
ADMIN = ("admin",)                                                 # require_admin
NADIE: tuple[str, ...] = ()                                        # solo superadmin


@dataclass(frozen=True)
class Sonda:
    """Llamada real de la pantalla o acción que abre la capacidad.

    `estricta`: la guarda del endpoint es exactamente ese conjunto de roles
    (quien no tiene la capacidad recibe 403). Si no lo es, la API sirve a
    más roles (acotando datos) y la capacidad es una decisión de pantalla.
    """
    metodo: str
    ruta: str
    estricta: bool = False


@dataclass(frozen=True)
class Capacidad:
    roles: tuple[str, ...]
    descripcion: str
    #: Módulo de `app.core.modulos.MODULOS` que, cerrado por el rol, la quita.
    modulo: Optional[str] = None
    sonda: Optional[Sonda] = None


def _c(roles, descripcion, modulo=None, sonda=None) -> Capacidad:
    return Capacidad(tuple(roles), descripcion, modulo, sonda)


def _get(ruta: str, estricta: bool = False) -> Sonda:
    return Sonda("GET", ruta, estricta)


CAPACIDADES: dict[str, Capacidad] = {
    # ── Plataforma y empresa ─────────────────────────────────────────────────
    "plataforma.empresas": _c(NADIE, "Gestionar las empresas de la plataforma (superadmin)",
                              sonda=_get("/api/v1/organizations", True)),
    "org.administrar": _c(ADMIN, "Administrar la empresa (ajustes de administración, acciones de admin)",
                          "settings", _get("/api/v1/settings/setup-checklist", True)),

    # ── Trabajo diario ───────────────────────────────────────────────────────
    "colaboracion.ver": _c(INTERNOS, "Chat, calendario, documentos, wiki, búsqueda, aprobaciones, informes",
                           sonda=_get("/api/v1/conectores/contecmind/disponible", True)),
    "tareas.editar": _c(("admin", "pm", "team_lead", "employee"), "Editar tareas en las vistas de trabajo", "tasks"),
    "tareas.crear": _c(ADMIN_PM_JEFE, "Crear tareas", "tasks"),
    "tareas.gestionar": _c(ADMIN_PM, "Borrar tareas y configurar el tablero", "tasks"),
    "partes.equipo": _c(ADMIN_PM_RRHH, "Partes de horas del equipo y pendientes de aprobar", "timesheets",
                        _get("/api/v1/timesheets/pending")),
    "gastos.ver": _c(INTERNOS, "Gastos propios", sonda=_get("/api/v1/expenses/my")),
    "gastos.gestionar": _c(ADMIN_PM_RRHH, "Gastos del equipo y pendientes de aprobar",
                           sonda=_get("/api/v1/expenses/pending")),
    "procesos.bandeja": _c(INTERNOS, "Bandeja de procesos BPM", sonda=_get("/api/v1/bpmn-instances/inbox", True)),

    # ── Proyectos ────────────────────────────────────────────────────────────
    "proyectos.ver": _c(TODOS, "Proyectos (cada uno los suyos)", "projects", _get("/api/v1/projects")),
    "proyectos.trabajo": _c(INTERNOS, "Sprints, RACI, cambios, UAT, Gantt, épicas, dependencias, wiki, lecciones",
                            "projects", _get("/api/v1/lessons/indicadores", True)),
    "proyectos.panel": _c(ADMIN_PM_JEFE, "Salud del portfolio", "dashboard", _get("/api/v1/dashboard/projects-health")),
    "proyectos.gestionar": _c(ADMIN_PM, "Gestionar proyectos, plan, épicas, entregables y valor ganado", "projects",
                              _get("/api/v1/projects/evm/portfolio", True)),
    "proyectos.lineas_base": _c(GESTORES, "Líneas base del plan", "projects"),
    "proyectos.gobierno": _c(ADMIN_PM, "Riesgos, cambios, entregables, Git y firma electrónica",
                             sonda=_get("/api/v1/deliverables/all/overview")),
    "cambios.gestionar": _c(ADMIN_PM, "Aprobar cambios de proyecto pendientes", "changes",
                            _get("/api/v1/changes/all/pending")),
    "cartera.gestionar": _c(ADMIN_PM, "Gestionar la entrada de propuestas a la cartera"),
    # Flujo de demanda (migración 195, docs/FLUJO_DE_DEMANDA.md): ver y decidir los pasos
    # de los que se es responsable (internos), gestionar (comité, ejecución, crear en nombre
    # de otro) y configurar tipos, flujos y plantillas.
    "demanda.ver": _c(INTERNOS, "Flujo de demanda: solicitudes y decisiones de las que se es responsable",
                      sonda=_get("/api/v1/demand/requests", True)),
    "demanda.gestionar": _c(ADMIN_PM, "Flujo de demanda: agendar comités, ejecutar y crear en nombre de otro"),
    "demanda.config": _c(ADMIN, "Configurar el flujo de demanda: tipos, flujos, plantillas",
                         sonda=_get("/api/v1/demand/flows", True)),
    "bpm.editar": _c(ADMIN_PM, "Editar y parar procesos BPM"),

    # ── Equipo y personas ────────────────────────────────────────────────────
    "equipo.ver": _c(GESTORES, "Capacidad del equipo, planificación y altas/bajas",
                     sonda=_get("/api/v1/resources/u/skill-gaps")),
    "recursos.ver": _c(ADMIN_PM_RRHH, "Recursos, capacidad, organigrama, OKR y evaluaciones", "resources",
                       _get("/api/v1/users/load")),
    "recursos.prevision": _c(ADMIN_PM_JEFE, "Previsión y planificador de recursos, procesos BPM", "resources",
                             _get("/api/v1/resource-forecast/weeks")),
    "externos.alta": _c(ADMIN_PM, "Dar de alta a un externo"),
    # Proveedores y externalización (19-11-2026, docs/PROVEEDORES_Y_EXTERNALIZACION.md).
    "proveedores.ver": _c(GESTORES, "Proveedores: ficha, contratos, servicios, paquetes, rendimiento y cumplimiento",
                          sonda=_get("/api/v1/suppliers/overview", True)),
    "proveedores.gestionar": _c(ADMIN_PM, "Gestionar proveedores: contratos, precios, consumo, facturación y GRC"),
    "proveedores.config": _c(ADMIN_PM, "Configurar proveedores: plantillas de contrato, catálogos y umbrales"),
    # Migración 191: portal del proveedor. Solo externos; además hace falta ser contacto
    # del portal de su proveedor (`subcontractor_workers.supplier_portal`): sin la marca,
    # la pantalla muestra que no tiene acceso y la API responde 403 (salvo `/me`, que
    # responde `enabled: false`). La guarda de `/api/v1/supplier-portal` es esta capacidad.
    "proveedores.portal": _c(("subcontractor",), "Portal del proveedor: informes, evidencias, paquetes, consumo "
                             "y estado de cuenta de su proveedor", sonda=_get("/api/v1/supplier-portal/me", True)),
    "costes.ver": _c(ADMIN_RRHH, "Ver costes y tarifas de las personas"),
    "ausencias.gestionar": _c(GESTORES, "Gestionar las ausencias del equipo", "absences"),
    "ausencias.config": _c(ADMIN_RRHH, "Configurar ausencias y planificar vacaciones", "absences"),
    "horas_extra.gestionar": _c(GESTORES, "Gestionar horas extra del equipo y pedirlas en nombre de otro",
                                sonda=_get("/api/v1/overtime/summary")),
    "horas_extra.config": _c(ADMIN_RRHH, "Configurar y liquidar horas extra"),
    "competencias.gestionar": _c(ADMIN_RRHH, "Matriz de competencias", "skills", _get("/api/v1/skills/matrix", True)),
    "formacion.gestionar": _c(ADMIN_RRHH, "Gestionar cursos y certificaciones"),
    "evaluaciones.gestionar": _c(ADMIN_RRHH, "Gestionar ciclos de evaluación"),
    "alm.personas": _c(ADMIN_PM_RRHH, "Altas y bajas de equipos (kits, bajas)",
                       sonda=_get("/api/v1/alm/integracion/bajas", True)),
    "alm.configurar": _c(ADMIN_RRHH, "Configurar altas y bajas de equipos"),
    # Guardas de /alm por capacidad (19-11-2026). `alm.ver` decide la pantalla
    # (/alm, dirección y PM); la API sirve a más roles y se desdobla con los
    # mismos roles que tenían sus `require_*`:
    "alm.gestionar": _c(GESTORES, "Licencias y activos: escribir y leer lo económico (API de /alm y /alm/uso)",
                        sonda=_get("/api/v1/alm/dashboard", True)),
    "alm.consultar": _c(INTERNOS, "Licencias y activos: catálogos de los selectores (proveedores, licencias, activos)",
                        sonda=_get("/api/v1/alm/config", True)),
    "alm.conexiones": _c(ADMIN, "Fuentes de uso real de licencias y equipos (conexiones y sincronización)",
                         sonda=_get("/api/v1/alm/uso/conexiones", True)),

    # ── Clientes y finanzas ──────────────────────────────────────────────────
    "finanzas.ver": _c(ADMIN_PM, "Clientes, pipeline, contratos, facturación, rentabilidad, presupuestos",
                       sonda=_get("/api/v1/profitability/summary", True)),
    # Clientes internos (rev. 193, docs/CLIENTES_INTERNOS.md): unidades de la propia
    # compañía con showback/chargeback. El portal interno acota a las unidades de
    # cada persona (`clientes_internos.unidades`); dirección y finanzas ven todas.
    "interno.portal": _c(INTERNOS, "Portal interno: proyectos, UAT, hitos, peticiones, SLA y coste de mis unidades",
                         sonda=_get("/api/v1/internal-portal/me", True)),
    "interno.gestionar": _c(ADMIN_PM, "Clientes internos: cuadro de dirección, costes, borradores de cargo, "
                            "beneficios, adopción y designaciones", sonda=_get("/api/v1/internal-clients/overview", True)),
    "interno.cargos": _c(ADMIN, "Emitir, exportar y anular cargos internos; servicios compartidos y su reparto",
                         sonda=_get("/api/v1/internal-clients/shared-costs", True)),

    # ── Soporte e ITSM ───────────────────────────────────────────────────────
    "sd.ver": _c(TODOS, "Service desk (el externo, solo sus tickets)", sonda=_get("/api/v1/sd/tickets/my-queue")),
    "sd.completo": _c(INTERNOS, "Service desk completo (aprobaciones, todas las pestañas)",
                      sonda=_get("/api/v1/sd/approvals/mine", True)),
    "soporte.panel": _c(INTERNOS, "Estado del soporte", sonda=_get("/api/v1/sd/metrics/itil")),
    "sd.config": _c(GESTORES, "Configuración del service desk (respuestas rápidas y lectura)",
                    sonda=_get("/api/v1/sd/workflow-designer/blueprints", True)),
    "sd.administrar": _c(ADMIN, "Administrar el service desk (canales, SLA, plantillas, agente)"),
    "sd.gestionar": _c(GESTORES, "Responsable del análisis de cambios ITSM"),
    # Pantalla: diseñador de flujos y calendarios SLA. API: escribir calendarios SLA
    # (`/cmdb/sla-calendars`, antes `require_admin_or_pm`). El diseñador en sí lo
    # guarda `sd.config` (gestores), como antes.
    "sd.disenar_flujos": _c(ADMIN_PM, "Diseñador de flujos del service desk y calendarios SLA"),
    "cmdb.ver": _c(ADMIN_PM, "CMDB y panel de agentes", sonda=_get("/api/v1/sd/cmdb")),
    "alm.ver": _c(ADMIN_PM, "Licencias y activos", sonda=_get("/api/v1/alm/dashboard")),
    # CMDB de software y vulnerabilidades (19-11-2026, docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md).
    "software.ver": _c(ADMIN_PM, "Software de la CMDB: catálogo, composición, dónde se usa, vulnerabilidades",
                       sonda=_get("/api/v1/cmdb/software/dashboard", True)),
    "software.gestionar": _c(ADMIN_PM, "Gestionar software: catálogo, instancias, importaciones, triaje y remediación",
                             sonda=_get("/api/v1/cmdb/software/products", True)),
    "software.aprobar": _c(ADMIN, "Aprobar excepciones de vulnerabilidad y líneas base de configuración"),
    "software.config": _c(ADMIN, "Configurar fuentes de avisos, credenciales y SLA de remediación",
                          sonda=_get("/api/v1/cmdb/software/config", True)),

    # ── Análisis ─────────────────────────────────────────────────────────────
    "analitica.ver": _c(ADMIN_PM, "Panel ejecutivo, explorador, generador de informes, predicciones, EVM",
                        "reports", _get("/api/v1/reports/schema", True)),
    "informes.programar": _c(GESTORES, "Informes programados", "reports"),
    "alertas.ver": _c(ADMIN_PM_RRHH, "Alertas", "alerts", _get("/api/v1/alerts")),
    "exportar.ver": _c(ADMIN_PM_RRHH, "Exportación de datos", "exports"),
    "exportar.todo": _c(ADMIN_RRHH, "Exportar las horas de todos", "exports"),
    "exportar.proyectos": _c(ADMIN_PM, "Exportar proyectos", "exports"),
    "datos.plataforma": _c(ADMIN, "Plataforma y gobierno de datos",
                           sonda=_get("/api/v1/bi/governance/overview", True)),

    # ── IA y automatización ──────────────────────────────────────────────────
    "ia.ver": _c(ADMIN_PM, "NexusAgent, NexusOracle, automatizaciones, contratos IA, sprint planning IA",
                 sonda=_get("/api/v1/automations")),
    "ia.asignacion": _c(ADMIN_PM_RRHH, "Asignación por IA", sonda=_get("/api/v1/semantic/config")),
    "ia.asignacion_config": _c(ADMIN_RRHH, "Configurar la asignación por IA"),
    # Asistente de reuniones (19-11-2026, docs/ASISTENTE_DE_REUNIONES.md).
    "reuniones.usar": _c(INTERNOS, "Asistente de reuniones: grabar, invitar el bot, traer reuniones, ver las suyas",
                         sonda=_get("/api/v1/meeting-assistant/meetings", True)),
    "reuniones.ver_todas": _c(ADMIN, "Ver y escuchar todas las reuniones de la empresa"),
    "reuniones.config": _c(ADMIN, "Configurar el asistente de reuniones y el RGPD por persona",
                           sonda=_get("/api/v1/meeting-assistant/config", True)),

    # ── Configuración (secciones de /settings) ───────────────────────────────
    "personas.config": _c(ADMIN_RRHH, "Departamentos, usuarios y vacaciones", "settings"),
    # 19-11-2026 (guardas por capacidad): `costes.config`, `integraciones.desarrollo`
    # y `portal.formularios` guardan rutas fuera de /settings (/user-costs,
    # /developer, /forms), así que van sin `modulo` (un rol personalizado que
    # cierra Ajustes no perdía esas rutas). La sección sigue oculta igual: la
    # pantalla la tapa por la ruta /settings/<sección> (`puedeVerSeccion`).
    "costes.config": _c(ADMIN_RRHH, "Costes de las personas", sonda=_get("/api/v1/user-costs/summary", True)),
    "proyectos.config": _c(ADMIN_PM, "Plantillas, tipos, flujos, campos y permisos de proyecto", "settings"),
    "tarifas.config": _c(ADMIN_PM, "Tarifas", "settings"),
    # API de tarifas (`/rate-cards`, escribir): gestores, como su `require_any_manager`.
    "tarifas.gestionar": _c(GESTORES, "Crear y cambiar tablas de tarifas, entradas y excepciones"),
    "integraciones.desarrollo": _c(ADMIN_PM, "Portal de desarrolladores e importación"),
    # API de importación masiva (`/billing-reports/import/*`): gestores.
    "integraciones.importar": _c(GESTORES, "Importación masiva de datos (plantillas, validar, ejecutar, historial)",
                                 sonda=_get("/api/v1/billing-reports/import/jobs", True)),
    "portal.formularios": _c(ADMIN_PM, "Formularios públicos"),
}


def _valor(rol) -> str:
    return getattr(rol, "value", rol) or ""


def capacidades_de(db, user) -> list[str]:
    """Capacidades efectivas de `user`, ordenadas.

    Superadmin: todas. Si no, las de su rol base menos las de módulos cerrados
    por su rol personalizado (o la fila de sistema de su rol).
    """
    if getattr(user, "is_superadmin", False):
        return sorted(CAPACIDADES)
    rol = _valor(user.role)
    propias = {n for n, c in CAPACIDADES.items() if rol in c.roles}
    if db is not None:
        from app.core.modulos import vetados
        cerrados = vetados(db, user)
        if cerrados:
            propias = {n for n in propias if CAPACIDADES[n].modulo not in cerrados}
    return sorted(propias)


def tiene(db, user, capacidad: str) -> bool:
    """¿Tiene `user` la capacidad? (desconocida → KeyError, para no escribirla mal)."""
    if capacidad not in CAPACIDADES:
        raise KeyError(capacidad)
    return capacidad in capacidades_de(db, user)


def roles_publicos() -> list[dict]:
    """Roles base reales con sus etiquetas, para los selectores."""
    return [{"id": r, "etiquetas": ETIQUETAS_DE_ROL.get(r, {"es": r, "en": r, "zh": r}),
             "interno": r != UserRole.subcontractor.value} for r in ROLES]
