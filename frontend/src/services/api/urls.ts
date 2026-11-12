/**
 * URLs de la API. Única fuente del prefijo (`VITE_API_URL` o `/api/v1`).
 *
 * Auditoría 2026-11: había ~30 `/api/v1` escritos a mano en componentes
 * (WebSockets, enlaces de descarga, URLs de webhook que se enseñan al usuario,
 * `sendBeacon`…). Con `VITE_API_URL` apuntando a otro host todos fallaban o
 * enseñaban una URL equivocada. Para peticiones normales usa el cliente
 * (`services/api`); esto es sólo para lo que no puede pasar por él.
 */

const VITE_API_URL = (import.meta as unknown as { env?: { VITE_API_URL?: string; VITE_WS_URL?: string } }).env?.VITE_API_URL

/** Base de la API tal como la usa el cliente axios (relativa o absoluta). */
export const API_BASE_URL: string = (VITE_API_URL || '/api/v1').replace(/\/+$/, '')

/** URL de un endpoint (`/x/y`) para `href`, `src`, `sendBeacon`, `EventSource`… */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

/** URL absoluta, con origen: para enseñarla o copiarla (webhooks, OAuth…). */
export function apiUrlAbsoluta(path: string): string {
  return new URL(apiUrl(path), window.location.origin).href
}

/** Base ws(s)://host[:puerto] del servidor de la API (o `VITE_WS_URL`). */
export function wsBase(): string {
  const envWs = (import.meta as unknown as { env?: { VITE_WS_URL?: string } }).env?.VITE_WS_URL
  if (envWs) return envWs.replace(/\/+$/, '')
  const api = new URL(API_BASE_URL, window.location.origin)
  const proto = api.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${api.host}`
}

/** URL ws(s):// de un endpoint WebSocket de la API (`/ws/notifications`…). */
export function apiWsUrl(path: string): string {
  const prefijo = new URL(API_BASE_URL, window.location.origin).pathname.replace(/\/+$/, '')
  return `${wsBase()}${prefijo}${path.startsWith('/') ? path : `/${path}`}`
}
