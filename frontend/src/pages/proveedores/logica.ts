/**
 * Proveedores y externalización (19-11-2026): reglas de pantalla sin React.
 *
 * Las listas repiten los `Literal` de `app/schemas/proveedores.py` (orden de
 * pantalla); `/suppliers/meta` es la fuente y, si llega, manda. Las reglas de
 * asignación son el reflejo en pantalla de `app/services/proveedores/asignabilidad.py`
 * (el backend las vuelve a comprobar con 422).
 */
import type {
  AlcanceDePaquete, AQuienSeAsigna, CicloDeVida, CriterioDeRiesgo, EstadoDeContratoProveedor, EstadoDeCuentaProveedor,
  EstadoDeCumplimiento, EstadoDePaquete, ModeloDeCobro, ModoDeRelacion, NivelDeAcceso,
  NivelDeRiesgoProveedor, PeriodoDeCobro, TipoDeContratoProveedor, TipoDeDocumentoProveedor, TipoDeProveedor,
  AgregacionDeMedicion, CuentaDeMedicion, FuenteDeMedicion, TipoDeInforme,
} from '../../services/api/tipos-proveedores'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'

export const TIPOS: TipoDeProveedor[] = ['freelance', 'company']
export const MODOS: ModoDeRelacion[] = ['staff_augmentation', 'outsourcing', 'managed_services']
export const MODELOS: ModeloDeCobro[] = ['per_resource', 'fixed_price', 'per_unit', 'subscription', 'expense', 'bonus']
export const PERIODOS: PeriodoDeCobro[] = ['monthly', 'quarterly', 'annual', 'one_time']
export const TIPOS_DE_CONTRATO: TipoDeContratoProveedor[] = ['msa', 'sow', 'service', 'framework', 'freelance']
export const ALCANCES: AlcanceDePaquete[] = ['project', 'phase', 'milestone', 'deliverable', 'tasks']
export const TIPOS_DE_DOCUMENTO: TipoDeDocumentoProveedor[] = [
  'dpa_art28', 'nda', 'iso27001', 'soc2', 'ens', 'insurance_liability', 'insurance_cyber',
  'security_questionnaire', 'due_diligence', 'tax_certificate', 'social_security_certificate', 'other',
]
export const NIVELES_DE_ACCESO: NivelDeAcceso[] = ['read', 'write', 'admin']
export const CRITERIOS: CriterioDeRiesgo[] = ['data_access', 'criticality', 'dependency', 'financial', 'location', 'security']
export const FRECUENCIAS = ['weekly', 'monthly', 'quarterly'] as const

// ── Migración 191 ────────────────────────────────────────────────────────────
/** Tipos de informe: avance (paquete) y periódico, parte de servicio y evidencia de SLA (servicio). */
export const TIPOS_DE_INFORME: TipoDeInforme[] = ['progress', 'periodic', 'service_log', 'sla_evidence']
export const TIPOS_DE_INFORME_DE_SERVICIO: TipoDeInforme[] = ['periodic', 'service_log', 'sla_evidence']
export const FUENTES_DE_MEDICION: FuenteDeMedicion[] = ['manual', 'cmdb', 'external']
export const AGREGACIONES: AgregacionDeMedicion[] = ['last', 'max', 'average']
export const CUENTAS_DE_MEDICION: CuentaDeMedicion[] = ['devices', 'owners']
/** Unidades por dispositivo/usuario: las únicas que admiten fuente de medición automática o externa. */
export const UNIDADES_DE_RECUENTO = ['device_month', 'user_month']

/** ¿Puede el servicio tener una fuente de medición distinta de la manual? (backend: 422 `proveedor_medicion_sin_unidad`). */
export const admiteMedicion = (unidad: string | null | undefined) => !!unidad && UNIDADES_DE_RECUENTO.includes(unidad)

/** ¿El estado de cuenta está esperando en la bandeja de aprobaciones? */
export const enBandeja = (estado: EstadoDeCuentaProveedor) => estado === 'pending_approval'

/** ¿Qué acciones admite un estado de cuenta? (mismo criterio que `facturacion`). */
export function accionesDeEstado(estado: EstadoDeCuentaProveedor, tieneFactura: boolean): Array<'reconcile' | 'approve' | 'dispute'> {
  if (estado === 'approved' || estado === 'pending_approval') return estado === 'pending_approval' ? ['dispute'] : []
  const res: Array<'reconcile' | 'approve' | 'dispute'> = ['reconcile']
  if (tieneFactura && estado === 'reconciled') res.push('approve')
  if (estado !== 'disputed') res.push('dispute')
  return res
}

/**
 * Filas de recuento pegadas desde un CSV o la exportación de un SIEM:
 * `servicio;fecha;cantidad[;sistema]` (o con comas o tabuladores). El servicio
 * es su id o su nombre (`servicios`). Devuelve las filas válidas y los números
 * de línea que no se entienden.
 */
export function filasDeRecuento(textoPegado: string, servicios: { id: string; name: string }[]): {
  filas: { service_id: string; as_of: string | null; quantity: number; system: string | null }[]; malas: number[]
} {
  const filas: { service_id: string; as_of: string | null; quantity: number; system: string | null }[] = []
  const malas: number[] = []
  const porNombre = new Map(servicios.map(s => [s.name.trim().toLowerCase(), s.id]))
  const ids = new Set(servicios.map(s => s.id))
  textoPegado.split(/\r?\n/).forEach((linea, i) => {
    const l = linea.trim()
    if (!l) return
    // Con `;` o tabuladores, la coma puede ser decimal; si no, la coma separa.
    const partes = (/[;\t]/.test(l) ? l.split(/[;\t]/) : l.split(',')).map(x => x.trim())
    if (i === 0 && partes.some(p => /^(servic|service|服务)/i.test(p))) return  // cabecera
    const [servicio, fecha, cantidad, sistema] = partes
    const id = ids.has(servicio) ? servicio : porNombre.get((servicio || '').toLowerCase())
    const n = Number((cantidad || '').replace(',', '.'))
    const fechaOk = !fecha || /^\d{4}-\d{2}-\d{2}$/.test(fecha)
    if (!id || !Number.isFinite(n) || n < 0 || !fechaOk) { malas.push(i + 1); return }
    filas.push({ service_id: id, as_of: fecha || null, quantity: n, system: sistema || null })
  })
  return { filas, malas }
}

// 23-11-2026: fuera `META_POR_DEFECTO` (sin uso desde que se quitó `useMetaProveedores`; auditoría 04b).

// ── Tonos de las insignias ───────────────────────────────────────────────────
export const TONO_CICLO: Record<CicloDeVida, StatusBadgeKind> = { onboarding: 'info', active: 'success', suspended: 'warning', offboarded: 'neutral' }
export const TONO_RIESGO: Record<NivelDeRiesgoProveedor, StatusBadgeKind> = { low: 'success', medium: 'info', high: 'warning', critical: 'danger' }
export const TONO_CONTRATO: Record<EstadoDeContratoProveedor, StatusBadgeKind> = { draft: 'neutral', active: 'success', suspended: 'warning', expired: 'neutral', terminated: 'danger' }
export const TONO_PAQUETE: Record<EstadoDePaquete, StatusBadgeKind> = { planned: 'neutral', in_progress: 'info', delivered: 'accent', accepted: 'success', rejected: 'danger', cancelled: 'neutral' }
export const TONO_CUENTA: Record<EstadoDeCuentaProveedor, StatusBadgeKind> = { closed: 'info', reconciled: 'accent', pending_approval: 'warning', disputed: 'danger', approved: 'success' }
export const TONO_CUMPLIMIENTO: Record<EstadoDeCumplimiento, StatusBadgeKind> = { ok: 'success', attention: 'warning', blocked: 'danger' }
/** Estado de documento de `grc.estado_de_documento` (supuesto: valid | expiring | expired). */
export const TONO_DOCUMENTO: Record<string, StatusBadgeKind> = { valid: 'success', expiring: 'warning', expired: 'danger' }
/** Tono de la puntuación (umbral `sla` de la empresa, `app/core/umbrales.py`). */
export const tonoDePuntuacion = (tono: string | null | undefined): StatusBadgeKind =>
  tono === 'ok' || tono === 'success' ? 'success' : tono === 'warning' ? 'warning' : tono === 'critical' || tono === 'danger' ? 'danger' : 'neutral'

/** Pasos posibles de un paquete según su estado (mismo ciclo que el backend). */
export function pasosDePaquete(estado: EstadoDePaquete): Array<'start' | 'deliver' | 'accept' | 'reject' | 'cancel'> {
  switch (estado) {
    case 'planned': return ['start', 'cancel']
    case 'in_progress': return ['deliver', 'cancel']
    case 'delivered': return ['accept', 'reject']
    case 'rejected': return ['start', 'cancel']
    default: return []
  }
}

/** Datos mínimos de la ficha para decidir qué se ve. */
export type ProveedorClasificado = { kind?: TipoDeProveedor | null; engagement_modes?: ModoDeRelacion[] | null; lifecycle_status?: CicloDeVida | null }

export const esFreelance = (p: ProveedorClasificado) => p.kind === 'freelance'
export const tieneModo = (p: ProveedorClasificado, m: ModoDeRelacion) => (p.engagement_modes || []).includes(m)
export const estaActivo = (p: ProveedorClasificado) => !p.lifecycle_status || p.lifecycle_status === 'active' || p.lifecycle_status === 'onboarding'

/**
 * ¿A quién se asigna el trabajo? (lo mismo que `assign_to` de la ficha).
 * Freelance: a su persona. Empresa: a sus personas con staff augmentation y a
 * la empresa (paquetes) con outsourcing; servicios gestionados no se asignan.
 */
export function aQuienSeAsigna(p: ProveedorClasificado): AQuienSeAsigna {
  if (!estaActivo(p)) return 'none'
  if (esFreelance(p)) return 'person'
  const personas = tieneModo(p, 'staff_augmentation')
  const empresa = tieneModo(p, 'outsourcing')
  if (personas && empresa) return 'person_and_supplier'
  if (personas) return 'person'
  if (empresa) return 'supplier'
  return 'none'
}

/** ¿Tiene personas? Freelance siempre (la suya); empresa solo con staff augmentation. */
export const tienePersonas = (p: ProveedorClasificado) => esFreelance(p) || tieneModo(p, 'staff_augmentation')

export type PestanaDeFicha =
  | 'summary' | 'workers' | 'assignments' | 'timelogs' | 'contracts' | 'services' | 'packages' | 'billing' | 'performance' | 'compliance'

/**
 * Pestañas de la ficha. Personas, asignaciones y partes solo si tiene personas
 * (no en outsourcing ni servicios puros); servicios con su modo; paquetes con
 * outsourcing (también freelance con outsourcing: el paquete va a su persona).
 * Una empresa sin modos (recién migrada o mal clasificada) ve todo para poder arreglarla.
 */
export function pestanasDeLaFicha(p: ProveedorClasificado): PestanaDeFicha[] {
  const sinModos = !esFreelance(p) && !(p.engagement_modes || []).length
  const personas = sinModos || tienePersonas(p)
  const res: PestanaDeFicha[] = ['summary']
  if (personas) res.push('workers', 'assignments', 'timelogs')
  res.push('contracts')
  if (sinModos || tieneModo(p, 'managed_services')) res.push('services')
  if (sinModos || tieneModo(p, 'outsourcing')) res.push('packages')
  res.push('billing', 'performance', 'compliance')
  return res
}

/** Campos de asignación de una tarea: persona o proveedor (excluyentes). */
export type AsignacionDeTarea = { assignee_id: string; supplier_id: string; supplier_work_package_id: string }

/**
 * Cambia un campo de asignación respetando la exclusión (422
 * `proveedor_asignacion_exclusiva`): elegir persona vacía proveedor y paquete;
 * elegir proveedor vacía la persona; cambiar de proveedor vacía el paquete.
 */
export function asignacionExclusiva<T extends AsignacionDeTarea>(actual: T, campo: keyof AsignacionDeTarea, valor: string): T {
  if (campo === 'assignee_id') {
    return valor ? { ...actual, assignee_id: valor, supplier_id: '', supplier_work_package_id: '' } : { ...actual, assignee_id: '' }
  }
  if (campo === 'supplier_id') {
    const paquete = valor && valor === actual.supplier_id ? actual.supplier_work_package_id : ''
    return { ...actual, supplier_id: valor, supplier_work_package_id: paquete, assignee_id: valor ? '' : actual.assignee_id }
  }
  return { ...actual, supplier_work_package_id: valor, assignee_id: valor ? '' : actual.assignee_id }
}

// ── Formularios ──────────────────────────────────────────────────────────────
export const numeroONull = (v: string | number | null | undefined): number | null => {
  if (v === null || v === undefined) return null
  const s = String(v).trim()
  if (!s) return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}
export const textoONull = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null)
export const texto = (v: unknown) => (v === null || v === undefined ? '' : String(v))

/** Primer y último día del mes de `hoy` (YYYY-MM-DD), periodo por defecto de previsión y cierre. */
export function mesDe(hoy: Date = new Date()): { desde: string; hasta: string } {
  const y = hoy.getFullYear()
  const m = hoy.getMonth()
  const dos = (n: number) => String(n).padStart(2, '0')
  const ultimo = new Date(y, m + 1, 0).getDate()
  return { desde: `${y}-${dos(m + 1)}-01`, hasta: `${y}-${dos(m + 1)}-${dos(ultimo)}` }
}

/** Traductor con respaldo (clave sin traducir → texto del servidor). */
export type Traductor = (clave: string, p?: Record<string, unknown>) => string
export function conRespaldo(t: Traductor, clave: string, respaldo: string): string {
  const r = t(clave)
  return r === clave ? respaldo : r
}
