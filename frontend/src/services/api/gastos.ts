/**
 * services/api/gastos.ts — justificantes, reparto entre proyectos y políticas de gasto (revisión 2026-11).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'

export interface Justificante { id: string; filename: string; content_type?: string; size_bytes?: number; created_at?: string }
export interface Parte { project_id: string; project_name?: string | null; percentage: number }
export interface Politica {
  id: string; nombre: string; categoria?: string | null; limite_por_gasto?: number | null; limite_diario?: number | null
  justificante_desde?: number | null; justificacion_desde?: number | null; accion: 'bloquear' | 'avisar'; activa: boolean
}
export interface Incumplimiento { politica_id: string; politica: string; regla: string; accion: 'bloquear' | 'avisar'; mensaje: string }

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const gastosApi = {
  justificantes: (id: string) => D<{ items: Justificante[] }>(api.get(`/expenses/${id}/attachments`)),
  subir: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return D<Justificante>(api.post(`/expenses/${id}/attachments`, fd))
  },
  urlJustificante: (aid: string) => D<{ url: string }>(api.get(`/expenses/attachments/${aid}/url`)),
  quitarJustificante: (aid: string) => api.delete(`/expenses/attachments/${aid}`),
  reparto: (id: string) => D<{ items: Parte[] }>(api.get(`/expenses/${id}/allocations`)),
  repartir: (id: string, partes: { project_id: string; percentage: number }[]) =>
    D<{ items: Parte[] }>(api.put(`/expenses/${id}/allocations`, partes)),
  comprobar: (id: string) => D<{ incumplimientos: Incumplimiento[]; bloquea: boolean }>(api.get(`/expenses/${id}/policy-check`)),
  politicas: () => D<{ items: Politica[] }>(api.get('/expenses/policies')),
  crearPolitica: (body: Partial<Politica>) => D<Politica>(api.post('/expenses/policies', body)),
  editarPolitica: (id: string, body: Partial<Politica>) => D<Politica>(api.patch(`/expenses/policies/${id}`, body)),
  borrarPolitica: (id: string) => api.delete(`/expenses/policies/${id}`),
}
