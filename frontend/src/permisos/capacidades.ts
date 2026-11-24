/**
 * Matriz de permisos (19-11-2026): nombres de las capacidades.
 *
 * La fuente es el backend (`app/core/capacidades.py`): ahí se decide qué roles
 * tienen cada una, coincidiendo con las guardas de los endpoints, y el
 * superadmin y los roles personalizados. La pantalla recibe las efectivas en
 * `/auth/me` (`user.capacidades`) y solo pregunta `puede('x')`.
 *
 * Esta lista solo da tipos (que un nombre mal escrito no compile);
 * `permisos/__tests__/permisos.test.ts` comprueba que coincide con el backend.
 */
export const CAPACIDADES = [
  'plataforma.empresas', 'org.administrar',
  'colaboracion.ver', 'tareas.editar', 'tareas.crear', 'tareas.gestionar', 'tareas.usar','partes.equipo',
  'gastos.ver', 'gastos.gestionar', 'procesos.bandeja',
  'proyectos.ver', 'proyectos.trabajo', 'proyectos.panel', 'proyectos.gestionar', 'proyectos.lineas_base',
  'proyectos.gobierno', 'cambios.gestionar', 'cartera.gestionar', 'bpm.editar',
  'equipo.ver', 'recursos.ver', 'recursos.prevision', 'externos.alta', 'costes.ver',
  'ausencias.gestionar', 'ausencias.config', 'horas_extra.gestionar', 'horas_extra.config',
  'competencias.gestionar', 'formacion.gestionar', 'evaluaciones.gestionar', 'alm.personas', 'alm.configurar',
  'finanzas.ver',
  'sd.ver', 'sd.completo', 'soporte.panel', 'sd.config', 'sd.administrar', 'sd.gestionar', 'sd.disenar_flujos',
  'cmdb.ver', 'alm.ver',
  // API de /alm por capacidad (19-11-2026): gestionar (gestores), consultar catálogos (internos), conexiones (admin).
  'alm.gestionar', 'alm.consultar', 'alm.conexiones',
  // CMDB de software y vulnerabilidades (19-11-2026): ver, gestionar (catálogo, instancias, triaje),
  // aprobar (excepciones y líneas base) y configurar (fuentes de avisos, credenciales, plazos).
  'software.ver', 'software.gestionar', 'software.aprobar', 'software.config',
  'analitica.ver', 'informes.programar', 'alertas.ver', 'exportar.ver', 'exportar.todo', 'exportar.proyectos',
  'datos.plataforma',
  'ia.ver', 'ia.asignacion', 'ia.asignacion_config',
  // Asistente de reuniones (19-11-2026): usar (internos), ver todas (supervisión) y configurar.
  'reuniones.usar', 'reuniones.ver_todas', 'reuniones.config',
  // Mi cuaderno (migración 202): usar (todos los de gestión), configurar y acceso excepcional (admin, auditado).
  'cuaderno.usar', 'cuaderno.config', 'cuaderno.acceso_excepcional',
  // Agentes de código por MCP (23-11-2026): conectar el editor o el terminal y generar credenciales.
  'mcp.usar',
  // Del ticket al PR (migración 203): ver ejecuciones, lanzar el agente, aprobar su plan y configurar.
  'ticket_pr.ver', 'ticket_pr.lanzar', 'ticket_pr.aprobar_plan', 'ticket_pr.config',
  // Proveedores y externalización (19-11-2026): ver (gestores y RRHH), gestionar y configurar (admin/PM).
  'proveedores.ver', 'proveedores.gestionar', 'proveedores.config',
  // Portal del proveedor (migración 191): solo externos marcados como contacto del portal de su proveedor.
  'proveedores.portal',
  'personas.config', 'costes.config', 'proyectos.config', 'tarifas.config', 'integraciones.desarrollo',
  'portal.formularios',
  // API de tarifas (escribir) e importación masiva: gestores (19-11-2026).
  'tarifas.gestionar', 'integraciones.importar',
  // Flujo de demanda (22-11-2026): ver expedientes, gestionarlos (decidir, adjuntar, ejecutar) y configurar tipos y flujos.
  'demanda.ver', 'demanda.gestionar', 'demanda.config',
  // Clientes internos (22-11-2026): portal de la unidad (internos), gestión (admin, PM) y cargos/servicios compartidos (admin).
  'interno.portal', 'interno.gestionar', 'interno.cargos',
  // Seguridad de cuentas (23-11-2026): administrar políticas (admin) y recertificar accesos (responsables).
  'seguridad.administrar', 'seguridad.recertificar',
  // PIR (migración 206, docs/PIR.md): ver y rellenar las propias, gestionar, aprobar (con segregación) y administrar.
  'pir.ver', 'pir.gestionar', 'pir.aprobar', 'pir.administrar',
  // Certificaciones (migración 212, docs/CERTIFICACIONES.md): ver, gestionar, auditar (con SoD) y administrar.
  'certificaciones.ver', 'certificaciones.gestionar', 'certificaciones.auditar', 'certificaciones.administrar',
  // Chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md): llamar y videollamar a clientes.
  'clientes.llamar',
  // >>> guardas_a_capacidades (generado: scripts/codemods/guardas_a_capacidades.py --aplicar)
  // Auditoría 22-11-2026 (M9): capacidades de las guardas de la API que eran de rol.
  'alertas.administrar', 'alertas.gestionar', 'alertas.usar', 'alm.administrar', 'analitica.gestionar',
  'analitica.responsables', 'analitica.usar', 'aprobaciones.administrar', 'aprobaciones.gestionar',
  'ausencias.administrar', 'ausencias.responsables', 'ausencias.trabajar', 'ausencias.usar',
  'automatizacion.administrar', 'automatizacion.gestionar', 'bi.administrar', 'bi.gestionar', 'bi.usar',
  'bpm.gestionar', 'bpm.usar', 'cab.administrar', 'cab.gestionar', 'cambios.responsables', 'cartera.usar',
  'clientes.dirigir', 'clientes.gestionar', 'cmdb.administrar', 'cmdb.gestionar', 'cmdb.usar', 'colaboracion.administrar',
  'colaboracion.gestionar', 'colaboracion.trabajar', 'colaboracion.usar', 'comercial.administrar',
  'comercial.gestionar', 'comercial.usar', 'competencias.usar', 'contratos.administrar', 'contratos.gestionar',
  'divisas.administrar', 'divisas.gestionar', 'divisas.usar', 'empresa.administrar', 'empresa.gestionar',
  'evaluaciones.responsables', 'exportar.gestionar', 'exportar.usar', 'facturacion.gestionar',
  'facturacion.usar', 'finanzas.gestionar', 'finanzas.responsables', 'firma.administrar',
  'formacion.responsables', 'formacion.usar', 'gastos.dirigir', 'gastos.responsables', 'gastos.trabajar',
  'gastos.usar', 'gobierno.administrar', 'gobierno.gestionar', 'gobierno.usar', 'horas_extra.trabajar',
  'ia.administrar', 'ia.gestionar', 'ia.rrhh', 'ia.usar', 'informes.gestionar', 'informes.usar',
  'integraciones.administrar', 'integraciones.gestionar', 'integraciones.responsables', 'integraciones.usar',
  'observabilidad.administrar', 'okr.gestionar', 'okr.usar', 'org.rrhh', 'panel.administrar',
  'panel.gestionar', 'partes.gestionar', 'personas.administrar', 'personas.gestionar', 'personas.rrhh',
  'personas.usar', 'presupuestos.gestionar', 'proyectos.administrar', 'proyectos.dirigir',
  'proyectos.responsables', 'proyectos.usar', 'recursos.gestionar', 'recursos.usar', 'reservas.administrar',
  'reservas.gestionar', 'reservas.usar', 'sd.trabajar', 'soc.administrar', 'software.administrar',
  'tareas.dirigir', 'tareas.trabajar', 'traduccion.administrar', 'traduccion.usar',
  // <<< guardas_a_capacidades
] as const

export type Capacidad = typeof CAPACIDADES[number]

/** ¿Está la capacidad en la lista del usuario? (sin usuario, no). */
export function tieneCapacidad(capacidades: unknown, capacidad: Capacidad): boolean {
  return Array.isArray(capacidades) && capacidades.includes(capacidad)
}
