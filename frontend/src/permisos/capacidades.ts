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
  'colaboracion.ver', 'tareas.editar', 'tareas.crear', 'tareas.gestionar', 'partes.equipo',
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
  // Proveedores y externalización (19-11-2026): ver (gestores y RRHH), gestionar y configurar (admin/PM).
  'proveedores.ver', 'proveedores.gestionar', 'proveedores.config',
  // Portal del proveedor (migración 191): solo externos marcados como contacto del portal de su proveedor.
  'proveedores.portal',
  'personas.config', 'costes.config', 'proyectos.config', 'tarifas.config', 'integraciones.desarrollo',
  'portal.formularios',
  // API de tarifas (escribir) e importación masiva: gestores (19-11-2026).
  'tarifas.gestionar', 'integraciones.importar',
] as const

export type Capacidad = typeof CAPACIDADES[number]

/** ¿Está la capacidad en la lista del usuario? (sin usuario, no). */
export function tieneCapacidad(capacidades: unknown, capacidad: Capacidad): boolean {
  return Array.isArray(capacidades) && capacidades.includes(capacidad)
}
