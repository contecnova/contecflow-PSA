/**
 * services/api/politicas.ts — motor de políticas, reglas y flujos (tarea #26).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'
import type {
  CatalogoDePoliticas, ComprobacionDeDiagrama, DiagramaDeFlujo, DocumentoDePolitica, ErrorDeValidacion,
  Explicaciones, FilaDeTabla, OpcionesDePoliticas, Politica, PoliticaEnLista, Regla, Simulacion, TablaDeReferencia,
} from './tipos-politicas'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export interface ParametrosDeSimulacion {
  politica_id?: string; documento?: DocumentoDePolitica; ultimos?: number; desde?: string; hasta?: string
}

export const politicasApi = {
  catalogo: () => D<CatalogoDePoliticas>(api.get('/policies/catalog')),
  opciones: () => D<OpcionesDePoliticas>(api.get('/policies/options')),
  listar: (dominio?: string) => D<PoliticaEnLista[]>(api.get('/policies', { params: dominio ? { dominio } : {} })),
  detalle: (id: string) => D<Politica>(api.get(`/policies/${id}`)),
  crear: (doc: DocumentoDePolitica) => D<Politica>(api.post('/policies', doc)),
  guardar: (id: string, doc: DocumentoDePolitica) => D<Politica>(api.put(`/policies/${id}`, doc)),
  borrar: (id: string) => D<{ eliminada?: boolean; retirada?: boolean }>(api.delete(`/policies/${id}`)),
  publicar: (id: string) => D<Politica>(api.post(`/policies/${id}/publish`)),
  nuevaVersion: (id: string) => D<Politica>(api.post(`/policies/${id}/new-version`)),
  activar: (id: string, activa: boolean) => D<Politica>(api.post(`/policies/${id}/activation`, { activa })),
  historial: (id: string) => D<Politica[]>(api.get(`/policies/${id}/history`)),
  crearRegla: (id: string, regla: Regla) => D<Politica>(api.post(`/policies/${id}/rules`, regla)),
  validar: (doc: DocumentoDePolitica) => D<{ valida: boolean; errores: ErrorDeValidacion[] }>(api.post('/policies/validate', doc)),
  simular: (p: ParametrosDeSimulacion) => D<Simulacion>(api.post('/policies/simulate', p)),
  explicaciones: (dominio: string, entidadId: string) => D<Explicaciones>(api.get(`/policies/explanations/${dominio}/${entidadId}`)),
  tablas: () => D<TablaDeReferencia[]>(api.get('/policies/tables')),
  tabla: (id: string) => D<TablaDeReferencia>(api.get(`/policies/tables/${id}`)),
  crearTabla: (t: Partial<TablaDeReferencia>) => D<TablaDeReferencia>(api.post('/policies/tables', t)),
  editarTabla: (id: string, t: Partial<TablaDeReferencia>) => D<TablaDeReferencia>(api.patch(`/policies/tables/${id}`, t)),
  borrarTabla: (id: string) => D<{ ok: boolean }>(api.delete(`/policies/tables/${id}`)),
  guardarFilas: (id: string, filas: FilaDeTabla[]) => D<TablaDeReferencia>(api.put(`/policies/tables/${id}/rows`, { filas })),
  importar: (id: string, fichero: File) => {
    const fd = new FormData()
    fd.append('file', fichero)
    return D<{ filas: FilaDeTabla[]; errores: { fila: number | null; mensaje: string }[] }>(api.post(`/policies/tables/${id}/import`, fd))
  },
  // Diseñador gráfico de flujos de aprobación (vive en /approvals: no hay un segundo motor).
  diagrama: (workflowId: string) => D<DiagramaDeFlujo>(api.get(`/approvals/workflows/${workflowId}/diagram`)),
  comprobarDiagrama: (workflowId: string, d: Pick<DiagramaDeFlujo, 'nodos' | 'aristas'>) =>
    D<ComprobacionDeDiagrama>(api.post(`/approvals/workflows/${workflowId}/diagram/check`, d)),
  guardarDiagrama: (workflowId: string, d: Pick<DiagramaDeFlujo, 'nodos' | 'aristas'>) =>
    D<DiagramaDeFlujo>(api.put(`/approvals/workflows/${workflowId}/diagram`, d)),
}
