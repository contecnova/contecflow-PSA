/**
 * Servicios tipados de las pantallas que llamaban a `api.*` directamente
 * (auditoría 04, M15; 23-11-2026). Antes las rutas y los tipos estaban
 * repartidos por las páginas (ESign, planificador de recursos, mapa de calor,
 * changelog, RACI, puntuaciones de riesgo, aprobación por correo, preferencias
 * de avisos y traducciones de la app): el C1 de ESign (id con `Number()`) habría
 * salido al tipar el servicio. Ahora cada ruta vive aquí una sola vez.
 *
 * Las funciones de lectura son genéricas en el tipo de la respuesta: la página
 * declara la forma que pinta (`reservasApi.listar<Reserva[]>()`), y el
 * desenvoltorio de sobres ya lo hace el interceptor (`desenvolverSobre`).
 */
import type { AxiosResponse } from 'axios'
import api, { type PathId, type QueryParams } from './_core'

// ── Firma electrónica: solicitudes (sobres) ──────────────────────────────────
export const solicitudesDeFirmaApi = {
  crear: <T>(datos: Record<string, unknown>): Promise<AxiosResponse<T>> => api.post('/esign', datos),
  estadisticas: <T>(): Promise<AxiosResponse<T>> => api.get('/esign/summary/stats'),
  listar: <T>(): Promise<AxiosResponse<T>> => api.get('/esign'),
  anular: (id: string): Promise<AxiosResponse<unknown>> => api.delete(`/esign/${id}`),
  marcarFirmado: (sobreId: string, firmanteId: string): Promise<AxiosResponse<unknown>> =>
    api.patch(`/esign/${sobreId}/signers/${firmanteId}/signed`),
}

// ── Reservas de recursos y previsión por semanas ─────────────────────────────
export const reservasApi = {
  previsionPorSemanas: <T>(params: QueryParams): Promise<AxiosResponse<T>> => api.get('/resource-forecast/weeks', { params }),
  listar: <T>(params?: QueryParams): Promise<AxiosResponse<T>> => api.get('/bookings', { params }),
  mapaDeCalor: <T>(params?: QueryParams): Promise<AxiosResponse<T>> => api.get('/bookings/heatmap', { params }),
  crear: (datos: unknown): Promise<AxiosResponse<unknown>> => api.post('/bookings', datos),
  editar: (id: PathId, datos: unknown): Promise<AxiosResponse<unknown>> => api.patch(`/bookings/${id}`, datos),
  borrar: (id: PathId): Promise<AxiosResponse<unknown>> => api.delete(`/bookings/${id}`),
}

// ── Changelog del proyecto ───────────────────────────────────────────────────
export const changelogApi = {
  listar: <T>(proyecto: PathId): Promise<AxiosResponse<T>> => api.get(`/projects/${proyecto}/changelog`),
  crear: (proyecto: PathId, datos: unknown): Promise<AxiosResponse<unknown>> => api.post(`/projects/${proyecto}/changelog`, datos),
  generar: (proyecto: PathId, datos: { weeks: number; version_tag: string | null }): Promise<AxiosResponse<unknown>> =>
    api.post(`/projects/${proyecto}/changelog/generate`, datos),
  borrar: (proyecto: PathId, id: PathId): Promise<AxiosResponse<unknown>> => api.delete(`/projects/${proyecto}/changelog/${id}`),
}

// ── Matriz RACI ──────────────────────────────────────────────────────────────
export const raciApi = {
  obtener: <T>(proyecto: PathId): Promise<AxiosResponse<T>> => api.get(`/projects/${proyecto}/raci`),
  guardar: (proyecto: PathId, datos: unknown): Promise<AxiosResponse<unknown>> => api.put(`/projects/${proyecto}/raci`, datos),
  borrar: (proyecto: PathId, entrada: PathId): Promise<AxiosResponse<unknown>> => api.delete(`/projects/${proyecto}/raci/${entrada}`),
}

// ── Puntuaciones de riesgo por proyecto ──────────────────────────────────────
export const puntuacionesDeRiesgoApi = {
  listar: <T>(params?: { refresh?: boolean }): Promise<AxiosResponse<T>> => api.get('/risk-scores', { params }),
  detalle: <T>(proyecto: PathId): Promise<AxiosResponse<T>> => api.get(`/risk-scores/${proyecto}`),
}

// ── Aprobar o rechazar desde el enlace del correo (token firmado) ────────────
export const aprobacionPorCorreoApi = {
  leer: <T>(token: string): Promise<AxiosResponse<T>> => api.get('/approvals/email-decision', { params: { token } }),
  decidir: (datos: { token: string; decision: string; note: string | null }): Promise<AxiosResponse<unknown>> =>
    api.post('/approvals/email-decision', datos),
}

// ── Preferencias de avisos de la persona ─────────────────────────────────────
export const preferenciasDeAvisosApi = {
  leer: <T>(): Promise<AxiosResponse<T>> => api.get('/users/me/notification-preferences'),
  guardar: (datos: { preferences: unknown; digest: unknown }): Promise<AxiosResponse<unknown>> =>
    api.put('/users/me/notification-preferences', datos),
}

// ── Armazón: traducciones personalizadas y renovación de sesión ──────────────
export const armazonApi = {
  traduccionesDeLaApp: (): Promise<AxiosResponse<Record<string, Record<string, unknown>>>> => api.get('/settings/app-translations'),
  /** Renueva la sesión (al salir de la suplantación cambia de empresa). */
  renovarSesion: (): Promise<AxiosResponse<unknown>> => api.post('/auth/refresh'),
}

// ── Menú lateral por defecto de cada rol (23-11-2026, «menú personalizable») ──
// La preferencia de cada persona va en `/users/me/preferences` (`extra.menu`).
export const menuPorDefectoApi = {
  /** El de mi rol en mi empresa (`null`: el orden del código). */
  mio: (): Promise<AxiosResponse<unknown>> => api.get('/settings/menu-default/mine'),
  /** El de cada rol (`org.administrar`). */
  porRol: (): Promise<AxiosResponse<{ version: number; roles: Record<string, unknown> }>> => api.get('/settings/menu-default'),
  guardar: (datos: { version: number; roles: Record<string, unknown> }): Promise<AxiosResponse<unknown>> =>
    api.put('/settings/menu-default', datos),
}
