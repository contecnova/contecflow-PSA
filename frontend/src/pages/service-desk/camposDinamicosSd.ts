/**
 * Textos legibles de los campos dinámicos del alta de ticket (incidencia 3 de
 * usuarios, 23-11-2026).
 *
 * Las reglas (`/sd/dynamic-forms`) guardan identificadores y valores: el campo
 * `affected_environment` con opciones `produccion`/`preproduccion`/`desarrollo`
 * y pistas de enrutado como `{queue: "incident_l1"}`. Se guardan así en el
 * ticket (son datos), pero en pantalla salían en crudo y con la etiqueta en
 * castellano fijo. Aquí se traducen con `sd_campos_dinamicos.*`; lo que no
 * tenga clave (campos creados por el administrador) se muestra con su etiqueta
 * o, si es un valor, legible (sin guiones bajos y con mayúscula inicial).
 */

/** El traductor del operador: `t('mod.clave', 'respaldo')` devuelve el respaldo si falta. */
export type TraductorConRespaldo = (clave: string, respaldo?: string) => string

const AUSENTE = '\u0000'

function traducida(t: TraductorConRespaldo, clave: string): string | null {
  const v = t(clave, AUSENTE)
  return v && v !== AUSENTE && v !== clave ? v : null
}

/** `incident_l1` → «Incident l1»: nunca la clave cruda con guiones bajos. */
export function legible(valor: string): string {
  const texto = valor.replace(/[_-]+/g, ' ').trim()
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : valor
}

/** Etiqueta de un campo dinámico: la traducción de los campos de serie o la del administrador. */
export function etiquetaDeCampoDinamico(t: TraductorConRespaldo, campo: { id?: string; label?: string }): string {
  const deSerie = campo.id ? traducida(t, `sd_campos_dinamicos.campo_${campo.id}`) : null
  return deSerie ?? campo.label ?? legible(campo.id ?? '')
}

/** Texto de una opción de un desplegable dinámico (el valor que se guarda no cambia). */
export function etiquetaDeOpcionDinamica(t: TraductorConRespaldo, opcion: string): string {
  return traducida(t, `sd_campos_dinamicos.opcion_${opcion}`) ?? opcion
}

/**
 * Valor de una pista de enrutado: la cola por su nombre, prioridad y tipo por
 * su etiqueta y el resto legible.
 */
export function valorDePistaDeEnrutado(
  t: TraductorConRespaldo, campo: string, valor: unknown, etiquetas: Record<string, Record<string, string>> = {},
): string {
  if (valor == null || valor === '') return '—'
  const v = String(valor)
  if (campo === 'queue') return traducida(t, `sd_campos_dinamicos.cola_${v}`) ?? legible(v)
  const conocida = etiquetas[campo]?.[v]
  if (conocida) return conocida
  return traducida(t, `sd_campos_dinamicos.opcion_${v}`) ?? legible(v)
}
