/**
 * Clientes internos (22-11-2026): lógica pura compartida por la gestión
 * (`/internal-clients`), el portal (`/mi-departamento`), la ficha del cliente y
 * Configuración. Sin React, para poder probarla sin montar pantallas.
 * Ver docs/CLIENTES_INTERNOS.md.
 */
import type {
  AvisoInterno, CriterioDeReparto, EstadoDeAdopcion, EstadoDeCargo, FuenteDeCoste, MetodoDeCoste, ModoFinanciero,
  RolDesignable, SubtipoInterno, TipoDeAdopcion, TipoDeBeneficio,
} from '../../services/api/clientesInternos'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'

export type Traductor = (clave: string, p?: Record<string, unknown>) => string

export const SUBTIPOS: SubtipoInterno[] = ['departamento', 'unidad_negocio', 'filial', 'centro_coste']
export const MODOS_FINANCIEROS: ModoFinanciero[] = ['showback', 'chargeback', 'intercompania']
export const METODOS_DE_COSTE: MetodoDeCoste[] = ['horas_coste', 'tarifa_interna', 'precio_cerrado', 'catalogo']
export const FUENTES_DE_COSTE: FuenteDeCoste[] = ['horas', 'precio_cerrado', 'catalogo', 'licencias', 'activos', 'software', 'reparto']
export const ESTADOS_DE_CARGO: EstadoDeCargo[] = ['borrador', 'por_aprobar', 'emitido', 'exportado', 'anulado']
export const ROLES_DESIGNABLES: RolDesignable[] = ['usuario_clave', 'finanzas', 'delegado']
export const TIPOS_DE_ADOPCION: TipoDeAdopcion[] = ['formacion', 'comunicacion', 'soporte', 'hito']
export const ESTADOS_DE_ADOPCION: EstadoDeAdopcion[] = ['pendiente', 'en_curso', 'hecho']
export const TIPOS_DE_BENEFICIO: TipoDeBeneficio[] = ['ahorro', 'ingreso', 'riesgo', 'intangible']
export const CRITERIOS_DE_REPARTO: CriterioDeReparto[] = ['usuarios', 'tickets', 'licencias', 'software', 'fijo']

export const TONO_CARGO: Record<EstadoDeCargo, StatusBadgeKind> = {
  borrador: 'neutral', por_aprobar: 'warning', emitido: 'success', exportado: 'info', anulado: 'danger',
}
export const TONO_ADOPCION: Record<EstadoDeAdopcion, StatusBadgeKind> = { pendiente: 'neutral', en_curso: 'warning', hecho: 'success' }

/**
 * Dónde se arregla cada aviso de configuración que devuelve el backend
 * (`warnings`). Configuración única: el aviso enlaza a la pantalla, no hay
 * botones «Configurar» en el módulo.
 */
export const DESTINO_DE_AVISO: Record<string, string> = {
  interno_sin_responsable: '/clients',
  interno_sin_presupuesto: '/budgets',
  interno_sin_tarifa: '/settings/rates',
  interno_sin_cuenta_erp: '/clients',
  interno_sin_estructura: '/clients',
  interno_sin_cuenta_ti: '/settings/clientes-internos',
}
export const destinoDeAviso = (aviso: AvisoInterno): string => DESTINO_DE_AVISO[aviso] || '/clients'

export type AccionDeCargo = 'issue' | 'approve' | 'reject' | 'cancel'

/**
 * Acciones posibles sobre un cargo según su estado, la capacidad
 * `interno.cargos` (emitir y anular) y `can_approve` (responsable de la
 * unidad, nunca quien lo generó o emitió: lo decide el backend).
 */
export function accionesDeCargo(estado: EstadoDeCargo, puedeCargos: boolean, puedeAprobar: boolean): AccionDeCargo[] {
  const r: AccionDeCargo[] = []
  if (estado === 'borrador' && puedeCargos) r.push('issue')
  if (estado === 'por_aprobar' && puedeAprobar) r.push('approve', 'reject')
  if ((estado === 'borrador' || estado === 'por_aprobar' || estado === 'emitido') && puedeCargos) r.push('cancel')
  return r
}

/** Mes actual `YYYY-MM` (periodo de cargos y repartos). */
export function mesActual(hoy: Date = new Date()): string {
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`
}

/** Texto de un número opcional del formulario: '' → null; si no, número (o null si no lo es). */
export function numeroONull(v: string | number | null | undefined): number | null {
  if (v === '' || v == null) return null
  const n = typeof v === 'number' ? v : Number(String(v).replace(',', '.'))
  return Number.isFinite(n) ? n : null
}
export const textoONull = (v: string | null | undefined): string | null => (v && v.trim() ? v.trim() : null)

/** Etiqueta de una clave de enumeración `internos.<prefijo><clave>` con la clave de respaldo. */
export function etiquetaInterna(t: Traductor, prefijo: string, clave: string | null | undefined): string {
  if (!clave) return '—'
  const k = `internos.${prefijo}${clave}`
  const r = t(k)
  return r === k ? clave : r
}

/** Campos internos del formulario del cliente (texto) → carga útil de `/clients`. */
export const CAMPOS_INTERNOS = [
  'internal_type', 'department_id', 'area_id', 'cost_center_id', 'group_organization_id', 'business_owner_id',
  'finance_mode', 'cost_method', 'internal_rate_table_id', 'transfer_markup_pct', 'erp_account',
] as const

export const FORM_INTERNO_VACIO: Record<string, string> = {
  kind: 'externo', internal_type: 'departamento', department_id: '', area_id: '', cost_center_id: '', group_organization_id: '',
  business_owner_id: '', finance_mode: 'showback', cost_method: 'horas_coste', internal_rate_table_id: '', transfer_markup_pct: '', erp_account: '',
}

/** Del cliente (detalle o lista) a los textos del formulario. */
export function formInternoDe(c: Record<string, unknown>): Record<string, string> {
  const r: Record<string, string> = { ...FORM_INTERNO_VACIO }
  r.kind = c.kind === 'interno' ? 'interno' : 'externo'
  for (const k of CAMPOS_INTERNOS) {
    const v = c[k]
    if (v != null && v !== '') r[k] = String(v)
  }
  return r
}

/**
 * Del formulario a la carga útil: externo → solo `kind`; interno → los campos
 * con '' como null y el margen como número (solo en intercompañía).
 */
export function datosInternos(form: Record<string, string>): Record<string, unknown> {
  if (form.kind !== 'interno') return { kind: 'externo' }
  const r: Record<string, unknown> = { kind: 'interno' }
  for (const k of CAMPOS_INTERNOS) r[k] = textoONull(form[k])
  r.transfer_markup_pct = form.finance_mode === 'intercompania' ? numeroONull(form.transfer_markup_pct) : null
  if (form.cost_method !== 'tarifa_interna') r.internal_rate_table_id = null
  return r
}

/** Quita del formulario plano los campos internos (para mezclarlos aparte con `datosInternos`). */
export function sinCamposInternos(form: Record<string, string>): Record<string, string> {
  const r = { ...form }
  delete r.kind
  for (const k of CAMPOS_INTERNOS) delete r[k]
  return r
}
