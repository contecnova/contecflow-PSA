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
    # 23-11-2026 (docs/seguridad/politicas_de_cuenta.md): políticas de cuenta de la
    # empresa (contraseñas, MFA, sesiones, acceso), usuarios y sesiones, aprobaciones.
    "seguridad.administrar": _c(ADMIN, "Seguridad de cuentas: políticas, bloqueos, MFA y sesiones de los usuarios",
                                sonda=_get("/api/v1/security/policy", True)),
    # Recertificación de accesos: cada responsable revisa a su gente.
    "seguridad.recertificar": _c(GESTORES, "Revisar los accesos de mi equipo (recertificación)",
                                 sonda=_get("/api/v1/security/access-reviews/mine", True)),
    # Migración 206 (docs/PIR.md): revisión posterior a la implantación de cambios y proyectos.
    "pir.ver": _c(INTERNOS, "PIR: ver y rellenar las revisiones en las que participo (el servicio acota)",
                  sonda=_get("/api/v1/pir/mias", True)),
    "pir.gestionar": _c(GESTORES, "PIR: programar, reasignar, descartar las opcionales, acciones e informes"),
    "pir.aprobar": _c(ADMIN_PM_JEFE, "PIR: aprobar, devolver, cerrar y reabrir (con segregación si la empresa la exige)"),
    "pir.administrar": _c(ADMIN, "PIR: configuración, plantillas y borrado",
                          sonda=_get("/api/v1/pir/config", True)),

    # ── Trabajo diario ───────────────────────────────────────────────────────
    "colaboracion.ver": _c(INTERNOS, "Chat, calendario, documentos, wiki, búsqueda, aprobaciones, informes",
                           sonda=_get("/api/v1/conectores/contecmind/disponible", True)),
    "tareas.editar": _c(("admin", "pm", "team_lead", "employee"), "Editar tareas en las vistas de trabajo", "tasks"),
    "tareas.crear": _c(ADMIN_PM_JEFE, "Crear tareas", "tasks"),
    "tareas.gestionar": _c(ADMIN_PM, "Borrar tareas y configurar el tablero", "tasks"),
    # 23-11-2026 (M9): crear tareas desde el asistente de IA (herramienta `create_task`,
    # `tool_execution/politica.py`); antes `require_internal_user`, mismos roles.
    "tareas.usar": _c(INTERNOS, "Tareas: crear desde el asistente de IA (personal interno)"),
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
    "sd.gestionar": _c(GESTORES, "Service desk: gestionar (responsables: análisis de cambios ITSM, colas, escalados, guardias y operación; antes require_any_manager)"),
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
    # «Mi cuaderno» (migración 202, docs/CUADERNO.md): notas personales de cada persona con
    # acceso a gestión (internos y externos; el portal de clientes no). Privado por defecto:
    # ninguna capacidad deja leer cuadernos ajenos salvo `cuaderno.acceso_excepcional`, que
    # exige además un bloqueo legal activo o una solicitud RGPD en curso (auditado).
    "cuaderno.usar": _c(TODOS, "Mi cuaderno: mis cuadernos, notas rápidas y lo compartido conmigo",
                        sonda=_get("/api/v1/notebook/tags", True)),
    "cuaderno.config": _c(ADMIN, "Configurar Mi cuaderno: etiquetas por defecto, plantillas, baja, papelera, IA y voz",
                          sonda=_get("/api/v1/notebook/config", True)),
    "cuaderno.acceso_excepcional": _c(ADMIN, "Acceso excepcional a los cuadernos de una persona con bloqueo legal "
                                      "o solicitud RGPD en curso (auditado)"),
    # Agentes de código por MCP (23-11-2026, docs/integraciones/MCP.md): conectar OpenCode, Claude
    # Code… al servidor MCP (`POST /api/v1/mcp`) y generar sus credenciales. Cada herramienta pide
    # además la MISMA capacidad que su ruta REST; la empresa lo enciende en Configuración.
    "mcp.usar": _c(TODOS, "Agentes de código (MCP): conectar el editor o el terminal y generar sus credenciales",
                   sonda=_get("/api/v1/mcp/estado")),
    # «Del ticket al PR» (migración 203, docs/integraciones/TICKET_A_PR.md): módulo opcional por
    # empresa (apagado). Ver las ejecuciones del ticket o tarea que ya se ve; lanzar el agente;
    # aprobar o rechazar su plan; configurar (repositorios, límites, credenciales Git, motor).
    "ticket_pr.ver": _c(INTERNOS, "Del ticket al PR: ver las ejecuciones del agente de código en tickets y tareas",
                        sonda=_get("/api/v1/ticket-pr/estado", True)),
    "ticket_pr.lanzar": _c(ADMIN_PM_JEFE, "Del ticket al PR: lanzar el agente de código desde un ticket o una tarea"),
    "ticket_pr.aprobar_plan": _c(ADMIN_PM_JEFE, "Del ticket al PR: aprobar o rechazar el plan del agente de código"),
    "ticket_pr.config": _c(ADMIN, "Del ticket al PR: configurar el módulo, repositorios, límites y credenciales Git",
                           sonda=_get("/api/v1/ticket-pr/config", True)),

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
    # >>> guardas_a_capacidades (generado: scripts/codemods/guardas_a_capacidades.py --aplicar)
    # Auditoría 22-11-2026 (M9): las guardas de rol de la API pasan a capacidades con
    # EXACTAMENTE los roles de su `require_*` de antes y sin `modulo` (no cierran más).
    # Nombre: <área del fichero>.<acción de la guarda>; ver el codemod.
    "alertas.administrar": _c(ADMIN, "Alertas: administrar (dirección)"),
    "alertas.gestionar": _c(GESTORES, "Alertas: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "alertas.usar": _c(INTERNOS, "Alertas: usar (personal interno)"),
    "alm.administrar": _c(ADMIN, "Licencias y activos: administrar (dirección)"),
    "analitica.gestionar": _c(ADMIN_PM, "Analítica y predicciones: gestionar (dirección y PM)"),
    "analitica.responsables": _c(GESTORES, "Analítica y predicciones: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "analitica.usar": _c(INTERNOS, "Analítica y predicciones: usar (personal interno)"),
    "aprobaciones.administrar": _c(ADMIN, "Aprobaciones: administrar (dirección)"),
    "aprobaciones.gestionar": _c(GESTORES, "Aprobaciones: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "ausencias.administrar": _c(ADMIN, "Ausencias: administrar (dirección)"),
    "ausencias.responsables": _c(GESTORES, "Ausencias: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "ausencias.trabajar": _c(TODOS, "Ausencias: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "ausencias.usar": _c(INTERNOS, "Ausencias: usar (personal interno)"),
    "automatizacion.administrar": _c(ADMIN, "Automatizaciones: administrar (dirección)"),
    "automatizacion.gestionar": _c(GESTORES, "Automatizaciones: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "bi.administrar": _c(ADMIN, "BI: administrar (dirección)"),
    "bi.gestionar": _c(ADMIN_PM, "BI: gestionar (dirección y PM)"),
    "bi.usar": _c(INTERNOS, "BI: usar (personal interno)"),
    "bpm.gestionar": _c(ADMIN_PM, "Procesos BPM: gestionar (dirección y PM)"),
    "bpm.usar": _c(INTERNOS, "Procesos BPM: usar (personal interno)"),
    "cab.administrar": _c(ADMIN, "CAB de cambios: administrar (dirección)"),
    "cab.gestionar": _c(GESTORES, "CAB de cambios: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "cambios.responsables": _c(GESTORES, "Cambios de proyecto: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "cartera.usar": _c(INTERNOS, "Cartera: usar (personal interno)"),
    "clientes.dirigir": _c(ADMIN_PM, "Clientes: salud del cliente (fotos y cálculo; antes guarda a mano en el cuerpo, admin y PM)"),
    "clientes.gestionar": _c(GESTORES, "Clientes y su portal: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "cmdb.administrar": _c(ADMIN, "CMDB: administrar (dirección)"),
    "cmdb.gestionar": _c(ADMIN_PM, "CMDB: gestionar (dirección y PM)"),
    "cmdb.usar": _c(INTERNOS, "CMDB: usar (personal interno)"),
    "colaboracion.administrar": _c(ADMIN, "Colaboración: administrar (dirección)"),
    "colaboracion.gestionar": _c(GESTORES, "Colaboración: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "colaboracion.trabajar": _c(TODOS, "Colaboración: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "colaboracion.usar": _c(INTERNOS, "Colaboración: usar (personal interno)"),
    "comercial.administrar": _c(ADMIN, "Pipeline comercial: administrar (dirección)"),
    "comercial.gestionar": _c(GESTORES, "Pipeline comercial: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "comercial.usar": _c(INTERNOS, "Pipeline comercial: usar (personal interno)"),
    "competencias.usar": _c(INTERNOS, "Competencias: usar (personal interno)"),
    "contratos.administrar": _c(ADMIN, "Contratos: administrar (dirección)"),
    "contratos.gestionar": _c(GESTORES, "Contratos: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "divisas.administrar": _c(ADMIN, "Tipos de cambio: administrar (dirección)"),
    "divisas.gestionar": _c(GESTORES, "Tipos de cambio: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "divisas.usar": _c(INTERNOS, "Tipos de cambio: usar (personal interno)"),
    "empresa.administrar": _c(ADMIN, "Empresa extendida (externos, webhooks, subcontratas): administrar (dirección)"),
    "empresa.gestionar": _c(GESTORES, "Empresa extendida (externos, webhooks, subcontratas): gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "evaluaciones.responsables": _c(GESTORES, "Evaluaciones: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "exportar.gestionar": _c(ADMIN_PM, "Exportaciones: gestionar (dirección y PM)"),
    "exportar.usar": _c(INTERNOS, "Exportaciones: usar (personal interno)"),
    "facturacion.gestionar": _c(GESTORES, "Facturación e informes de facturación: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "facturacion.usar": _c(INTERNOS, "Facturación e informes de facturación: usar (personal interno)"),
    "finanzas.gestionar": _c(ADMIN_PM, "Finanzas: gestionar (dirección y PM)"),
    "finanzas.responsables": _c(GESTORES, "Finanzas: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "firma.administrar": _c(ADMIN, "Firma electrónica: administrar (dirección)"),
    "formacion.responsables": _c(GESTORES, "Formación: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "formacion.usar": _c(INTERNOS, "Formación: usar (personal interno)"),
    "gastos.dirigir": _c(ADMIN_PM, "Gastos: gestionar (dirección y PM)"),
    "gastos.responsables": _c(GESTORES, "Gastos: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "gastos.trabajar": _c(TODOS, "Gastos: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "gastos.usar": _c(INTERNOS, "Gastos: usar (personal interno)"),
    "gobierno.administrar": _c(ADMIN, "Gobierno (ABAC, GRC, políticas, gobierno de IA y datos): administrar (dirección)"),
    "gobierno.gestionar": _c(GESTORES, "Gobierno (ABAC, GRC, políticas, gobierno de IA y datos): gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "gobierno.usar": _c(INTERNOS, "Gobierno (ABAC, GRC, políticas, gobierno de IA y datos): usar (personal interno)"),
    "horas_extra.trabajar": _c(TODOS, "Horas extra: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "ia.administrar": _c(ADMIN, "IA (asistente, módulos, proveedores, planificación): administrar (dirección)"),
    "ia.gestionar": _c(GESTORES, "IA (asistente, módulos, proveedores, planificación): gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "ia.rrhh": _c(ADMIN_RRHH, "IA (asistente, módulos, proveedores, planificación): gestionar (dirección y RRHH)"),
    "ia.usar": _c(INTERNOS, "IA (asistente, módulos, proveedores, planificación): usar (personal interno)"),
    "informes.gestionar": _c(ADMIN_PM, "Generador de informes: gestionar (dirección y PM)"),
    "informes.usar": _c(INTERNOS, "Generador de informes: usar (personal interno)"),
    "integraciones.administrar": _c(ADMIN, "Integraciones y conectores: administrar (dirección)"),
    "integraciones.gestionar": _c(ADMIN_PM, "Integraciones y conectores: gestionar (dirección y PM)"),
    "integraciones.responsables": _c(GESTORES, "Integraciones y conectores: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "integraciones.usar": _c(INTERNOS, "Integraciones y conectores: usar (personal interno)"),
    "observabilidad.administrar": _c(ADMIN, "Observabilidad predictiva: administrar (dirección)"),
    "okr.gestionar": _c(GESTORES, "OKR: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "okr.usar": _c(INTERNOS, "OKR: usar (personal interno)"),
    "org.rrhh": _c(ADMIN_RRHH, "Empresa (configuración avanzada, marca, eventos, SSO): gestionar (dirección y RRHH)"),
    "panel.administrar": _c(ADMIN, "Paneles: administrar (dirección)"),
    "panel.gestionar": _c(GESTORES, "Paneles: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "partes.gestionar": _c(GESTORES, "Imputaciones y partes: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "personas.administrar": _c(ADMIN, "Personas y usuarios: administrar (dirección)"),
    "personas.gestionar": _c(GESTORES, "Personas y usuarios: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "personas.rrhh": _c(ADMIN_RRHH, "Personas y usuarios: gestionar (dirección y RRHH)"),
    "personas.usar": _c(INTERNOS, "Personas y usuarios: usar (personal interno)"),
    "presupuestos.gestionar": _c(GESTORES, "Presupuestos: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "proyectos.administrar": _c(ADMIN, "Proyectos: administrar (dirección)"),
    "proyectos.dirigir": _c(ADMIN_PM, "Proyectos: gestionar (dirección y PM)"),
    "proyectos.responsables": _c(GESTORES, "Proyectos: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "proyectos.usar": _c(INTERNOS, "Proyectos: usar (personal interno)"),
    "recursos.gestionar": _c(GESTORES, "Recursos y capacidad: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "recursos.usar": _c(INTERNOS, "Recursos y capacidad: usar (personal interno)"),
    "reservas.administrar": _c(ADMIN, "Reservas: administrar (dirección)"),
    "reservas.gestionar": _c(GESTORES, "Reservas: gestionar (responsables: dirección, PM, jefes de equipo y RRHH)"),
    "reservas.usar": _c(INTERNOS, "Reservas: usar (personal interno)"),
    "sd.trabajar": _c(TODOS, "Service desk: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "soc.administrar": _c(ADMIN, "Observabilidad de seguridad (SOC): administrar (dirección)"),
    "software.administrar": _c(ADMIN, "Software de la CMDB: administrar (dirección)"),
    "tareas.dirigir": _c(ADMIN_PM, "Tareas: gestionar (dirección y PM)"),
    "tareas.trabajar": _c(TODOS, "Tareas: trabajar (internos y externos: trabajo diario, el servicio acota a lo suyo)"),
    "traduccion.administrar": _c(ADMIN, "Traducción: administrar (dirección)"),
    "traduccion.usar": _c(INTERNOS, "Traducción: usar (personal interno)"),
    # <<< guardas_a_capacidades
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
