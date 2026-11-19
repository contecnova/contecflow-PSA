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
  'analitica.ver', 'informes.programar', 'alertas.ver', 'exportar.ver', 'exportar.todo', 'exportar.proyectos',
  'datos.plataforma',
  'ia.ver', 'ia.asignacion', 'ia.asignacion_config',
  'personas.config', 'costes.config', 'proyectos.config', 'tarifas.config', 'integraciones.desarrollo',
  'portal.formularios',
] as const

export type Capacidad = typeof CAPACIDADES[number]

/** ¿Está la capacidad en la lista del usuario? (sin usuario, no). */
export function tieneCapacidad(capacidades: unknown, capacidad: Capacidad): boolean {
  return Array.isArray(capacidades) && capacidades.includes(capacidad)
}
