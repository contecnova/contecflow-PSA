/**
 * services/api/gastos.ts — justificantes (con tipo de documento), reparto entre proyectos y la
 * vista previa de las políticas al enviar (rev. 166, tarea #27). Las políticas de gasto son del
 * motor común: `politicasApi` (`/policies`, dominio `gastos`).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'
import type { Gasto } from './tipos-finanzas'
import type { ExplicacionDePolitica, ResumenDePolitica } from './tipos-politicas'

export interface Justificante {
  id: string; filename: string; content_type?: string; size_bytes?: number; document_type?: string | null; created_at?: string
}
export interface Parte { project_id: string; project_name?: string | null; percentage: number }
/** Un aviso con el que se envió el gasto (`gastos_politicas.avisos_guardados`). */
export interface Incumplimiento { politica?: string | null; regla?: string | null; mensaje: string | null }

/** El gasto con lo que añade la rev. 166: dónde, asistentes, viaje y el resumen de sus políticas. */
export type GastoConPoliticas = Gasto & {
  country?: string | null; city?: string | null; attendees?: number | null; trip?: string | null
  policy_summary?: (ResumenDePolitica & { avisos_detalle?: Incumplimiento[] }) | null
}

interface Origen { politica?: string | null; regla?: string | null; mensaje?: string | null }
export interface RequisitoPrevisto extends Origen {
  tipo: 'require_attachment' | 'require_justification'; tipos_de_documento: string[]; cumplido: boolean
}
/** GET /expenses/{id}/policy-preview: qué pasará al enviar (sin efectos). */
export interface VistaPreviaDeEnvio {
  decision: 'block' | 'review' | 'auto_approve' | 'allow'
  puede_enviar: boolean
  bloqueos: Origen[]; avisos: Origen[]; requisitos: RequisitoPrevisto[]
  niveles: number
  avisar: { politica?: string | null; mensaje?: string | null; canales: string[]; destinatarios: { tipo: string; valor?: string | null }[] }[]
  etiquetas: string[]; campos: Record<string, unknown>; auto_aprobar: boolean
  excesos: { politica: string; regla: string; exceso_pct: number; valor?: number; referencia?: number; moneda?: string }[]
  aprobacion: {
    flujo: { id: string; nombre: string } | null
    pasos_del_flujo: { nombre: string; informar: boolean }[]
    niveles_anadidos: number[]
    pasos_anadidos: { nombre?: string | null; approver_type?: string; informar: boolean; politica?: string | null }[]
  }
  politicas_que_aplican: string[]
  explicacion: ExplicacionDePolitica[]
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

/** Filtros y orden de las listas de gastos (todo en el servidor: la lista va paginada). */
export interface FiltrosDeGastos {
  status?: string; category?: string; q?: string; date_from?: string; date_to?: string; project_id?: string
  sort?: string; direction?: 'asc' | 'desc'; page: number; page_size: number
}
export interface PaginaDeGastos { items: GastoConPoliticas[]; total: number }
export interface TotalesDeGastos { count: number; total_amount: number; submitted_count: number }
export interface PaginaDelEquipo extends PaginaDeGastos {
  importe_total: number; facturable_total: number; por_categoria: Record<string, number>
}

/** Quita los filtros vacíos (el servidor los toma como «sin filtro», pero no ensucian la URL). */
const limpio = (f: Partial<FiltrosDeGastos>) =>
  Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '' && v !== undefined && v !== null))

const pagina = (r: { data: unknown; meta?: unknown }): PaginaDeGastos => {
  const items = (Array.isArray(r.data) ? r.data : []) as GastoConPoliticas[]
  const meta = r.meta as { total?: number | null } | undefined
  return { items, total: meta?.total ?? items.length }
}

export const gastosApi = {
  justificantes: (id: string) => D<{ items: Justificante[] }>(api.get(`/expenses/${id}/attachments`)),
  subir: (id: string, file: File, tipoDeDocumento?: string | null) => {
    const fd = new FormData()
    fd.append('file', file)
    if (tipoDeDocumento) fd.append('document_type', tipoDeDocumento)
    return D<Justificante>(api.post(`/expenses/${id}/attachments`, fd))
  },
  tipar: (aid: string, tipoDeDocumento: string | null) =>
    D<Justificante>(api.patch(`/expenses/attachments/${aid}`, { document_type: tipoDeDocumento })),
  urlJustificante: (aid: string) => D<{ url: string }>(api.get(`/expenses/attachments/${aid}/url`)),
  quitarJustificante: (aid: string) => api.delete(`/expenses/attachments/${aid}`),
  reparto: (id: string) => D<{ items: Parte[] }>(api.get(`/expenses/${id}/allocations`)),
  repartir: (id: string, partes: { project_id: string; percentage: number }[]) =>
    D<{ items: Parte[] }>(api.put(`/expenses/${id}/allocations`, partes)),
  vistaPrevia: (id: string) => D<VistaPreviaDeEnvio>(api.get(`/expenses/${id}/policy-preview`)),
  // Listas paginadas (page/page_size; total en meta.total o X-Total-Count).
  mios: (f: FiltrosDeGastos) => api.get('/expenses/my', { params: limpio(f) }).then(pagina),
  totalesMios: (f: Partial<FiltrosDeGastos>) => D<TotalesDeGastos>(api.get('/expenses/my/totals', { params: limpio(f) })),
  pendientes: (f: FiltrosDeGastos) => api.get('/expenses/pending', { params: limpio(f) }).then(pagina),
  totalesPendientes: (f: Partial<FiltrosDeGastos>) => D<TotalesDeGastos>(api.get('/expenses/pending/totals', { params: limpio(f) })),
  equipo: (f: FiltrosDeGastos) => api.get('/expenses/team', { params: limpio(f) }).then((r): PaginaDelEquipo => {
    const d = r.data as { expenses?: GastoConPoliticas[]; total?: number; billable_total?: number; by_category?: Record<string, number> }
    const items = d.expenses ?? []
    const cabecera = Number(r.headers?.['x-total-count'])
    return { items, total: Number.isFinite(cabecera) ? cabecera : items.length, importe_total: d.total ?? 0,
      facturable_total: d.billable_total ?? 0, por_categoria: d.by_category ?? {} }
  }),
}
