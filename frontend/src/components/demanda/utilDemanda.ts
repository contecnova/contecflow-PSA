/**
 * Funciones puras del flujo de demanda (22-11-2026): decisiones que exigen
 * justificación, ayudas de edición de la definición y validación local previa
 * a la del servidor (`POST /demand/flows/validate`, que es la que manda).
 * Probadas en `__tests__/demanda.test.ts`.
 */
import type { CampoDeFlujo, DefinicionDeFlujo, ErrorDeDefinicion, FaseDeFlujo, PasoDeFlujo, TextoI18n } from '../../services/api/demanda'

/** Decisiones cuya justificación es obligatoria siempre. */
export const DECISIONES_CON_JUSTIFICACION = ['reject', 'return', 'request_info', 'skip', 'hold'] as const

/**
 * ¿Exige justificación esta decisión? La vía rápida solo la exige cuando el
 * expediente superaba los umbrales del comité (`committee.required`): es el bypass.
 */
export function justificacionObligatoria(decision: string, comiteRequerido: boolean): boolean {
  if ((DECISIONES_CON_JUSTIFICACION as readonly string[]).includes(decision)) return true
  return decision === 'fast_track' && comiteRequerido
}

/** Decisiones que piden elegir fase de destino. */
export const decisionConDestino = (decision: string) => decision === 'return'

const CLAVE = /^[a-z][a-z0-9_]*$/

export const claveValida = (k: string) => CLAVE.test(k)

/** Convierte un texto libre en una clave técnica (minúsculas, guiones bajos). */
export function claveDesdeTexto(texto: string): string {
  const base = texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return /^[a-z]/.test(base) ? base : base ? `x_${base}` : ''
}

/** Mueve el elemento `i` una posición (`-1` arriba, `1` abajo); no sale del rango. */
export function mover<T>(lista: T[], i: number, dir: -1 | 1): T[] {
  const j = i + dir
  if (j < 0 || j >= lista.length) return lista
  const copia = lista.slice()
  ;[copia[i], copia[j]] = [copia[j], copia[i]]
  return copia
}

export const textoVacio = (): TextoI18n => ({ es: '', en: '', zh: '' })

export function pasoNuevo(n: number): PasoDeFlujo {
  return { key: `paso_${n}`, name: textoVacio(), mode: 'task', assignee: { type: 'role', value: '', label: '' }, quorum: 'any', optional: false }
}

export function faseNueva(n: number): FaseDeFlujo {
  return {
    key: `fase_${n}`, name: textoVacio(), kind: 'work', parallel: false, steps: [pasoNuevo(1)],
    decisions: ['approve', 'reject', 'return'], on_approve: 'next', on_reject: 'end:rejected', return_targets: [],
    required_fields: [], client_editable: false, lock_client_from_here: false, sla_hours: null, sla_warn_pct: 80,
    pause_on_info: true, segregation: { not_requester: true, not_actor_of_phases: [] }, documents_tag: null, notify: [],
  }
}

export function campoNuevo(n: number): CampoDeFlujo {
  return { key: `campo_${n}`, label: textoVacio(), type: 'text', options: [], critical: false, owner: 'client', client_visible: true, policy_field: null }
}

export function definicionVacia(): DefinicionDeFlujo {
  return { fields: [], submit_required: [], phases: [], execution: ['backlog'], notify: [] }
}

/** Siguiente número libre para una clave `prefijo_N`. */
export function siguienteClave(prefijo: string, existentes: string[]): number {
  let n = existentes.length + 1
  while (existentes.includes(`${prefijo}_${n}`)) n += 1
  return n
}

/** Destinos válidos de `on_approve`/`on_reject`/`return_targets` además de las fases. */
export function destinosDeSalida(fases: FaseDeFlujo[], extra: string[]): string[] {
  return [...extra, ...fases.map(f => f.key)]
}

/** Quita de la definición las referencias a una fase borrada o renombrada. */
export function renombrarFase(def: DefinicionDeFlujo, de: string, a: string | null): DefinicionDeFlujo {
  const cambia = (v: string) => (v === de ? (a ?? '') : v)
  return {
    ...def,
    phases: def.phases.map(f => ({
      ...f,
      key: f.key === de && a ? a : f.key,
      on_approve: a === null && f.on_approve === de ? 'next' : cambia(f.on_approve) || 'next',
      on_reject: a === null && f.on_reject === de ? 'end:rejected' : cambia(f.on_reject) || 'end:rejected',
      return_targets: (f.return_targets || []).map(cambia).filter(Boolean),
      segregation: f.segregation ? { ...f.segregation, not_actor_of_phases: (f.segregation.not_actor_of_phases || []).map(cambia).filter(Boolean) } : f.segregation,
      gate: f.gate ? { ...f.gate, if_true: cambia(f.gate.if_true) || 'next', if_false: cambia(f.gate.if_false) || 'next' } : f.gate,
    })).filter(f => !(a === null && f.key === de)),
  }
}

/**
 * Validación local de la definición: claves únicas y bien formadas, nombres en
 * castellano y referencias existentes. Es una ayuda: el servidor valida de verdad.
 */
export function validarLocal(def: DefinicionDeFlujo): ErrorDeDefinicion[] {
  const errores: ErrorDeDefinicion[] = []
  const claves = new Set<string>()
  def.phases.forEach((f, i) => {
    const p = `phases[${i}]`
    if (!claveValida(f.key)) errores.push({ path: `${p}.key`, code: 'clave_invalida' })
    else if (claves.has(f.key)) errores.push({ path: `${p}.key`, code: 'clave_duplicada' })
    claves.add(f.key)
    if (!f.name?.es?.trim()) errores.push({ path: `${p}.name`, code: 'nombre_obligatorio' })
    if (!f.steps?.length && f.kind !== 'gate') errores.push({ path: `${p}.steps`, code: 'sin_pasos' })
    const pasos = new Set<string>()
    f.steps?.forEach((s, j) => {
      if (!claveValida(s.key)) errores.push({ path: `${p}.steps[${j}].key`, code: 'clave_invalida' })
      else if (pasos.has(s.key)) errores.push({ path: `${p}.steps[${j}].key`, code: 'clave_duplicada' })
      pasos.add(s.key)
    })
  })
  const campos = new Set<string>()
  def.fields.forEach((c, i) => {
    if (!claveValida(c.key)) errores.push({ path: `fields[${i}].key`, code: 'clave_invalida' })
    else if (campos.has(c.key)) errores.push({ path: `fields[${i}].key`, code: 'clave_duplicada' })
    campos.add(c.key)
    if (!c.label?.es?.trim()) errores.push({ path: `fields[${i}].label`, code: 'nombre_obligatorio' })
  })
  const destinoOk = (v: string) => !v || v === 'next' || v.startsWith('end:') || claves.has(v)
  def.phases.forEach((f, i) => {
    if (!destinoOk(f.on_approve)) errores.push({ path: `phases[${i}].on_approve`, code: 'fase_inexistente' })
    if (!destinoOk(f.on_reject)) errores.push({ path: `phases[${i}].on_reject`, code: 'fase_inexistente' })
    f.return_targets?.forEach((r, j) => { if (!claves.has(r)) errores.push({ path: `phases[${i}].return_targets[${j}]`, code: 'fase_inexistente' }) })
    f.required_fields?.forEach((r, j) => { if (!campos.has(r)) errores.push({ path: `phases[${i}].required_fields[${j}]`, code: 'campo_inexistente' }) })
  })
  def.submit_required.forEach((r, j) => { if (!campos.has(r) && r !== 'title') errores.push({ path: `submit_required[${j}]`, code: 'campo_inexistente' }) })
  return errores
}

/** Lee un JSON de definición; devuelve la definición o el mensaje del fallo de sintaxis. */
export function leerDefinicion(texto: string): { def?: DefinicionDeFlujo; error?: string } {
  try {
    const v = JSON.parse(texto) as unknown
    if (!v || typeof v !== 'object' || Array.isArray(v)) return { error: 'object' }
    const o = v as Partial<DefinicionDeFlujo>
    return { def: { ...definicionVacia(), ...o, fields: o.fields ?? [], phases: o.phases ?? [], submit_required: o.submit_required ?? [], execution: o.execution ?? [] } }
  } catch (e) {
    return { error: (e as Error).message }
  }
}

/** Valor de un campo del expediente en la caja de edición (todo texto). */
export function valorDeCampo(tipo: string, v: unknown): string {
  if (v === null || v === undefined) return ''
  if (tipo === 'boolean') return v ? 'true' : 'false'
  return String(v)
}

/** Texto de la caja → valor que se guarda. */
export function valorParaGuardar(tipo: string, texto: string): unknown {
  if (tipo === 'boolean') return texto === 'true'
  if (tipo === 'number' || tipo === 'money') return texto.trim() === '' ? null : Number(texto)
  return texto
}

/** Campos del expediente que han cambiado respecto de `data`. */
export function camposCambiados(datos: Record<string, unknown>, editado: Record<string, string>, tipos: Record<string, string>): Record<string, unknown> {
  const salida: Record<string, unknown> = {}
  for (const [k, texto] of Object.entries(editado)) {
    const tipo = tipos[k] || 'text'
    if (valorDeCampo(tipo, datos[k]) !== texto) salida[k] = valorParaGuardar(tipo, texto)
  }
  return salida
}
