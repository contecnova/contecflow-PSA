/**
 * Resolves the WebSocket base URL based on environment variables or current origin.
 * Priority: VITE_WS_URL env var → derived from VITE_API_URL → fallback to hostname:8000
 */
export function resolveWsBase() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const apiUrl = import.meta.env.VITE_API_URL || '/api/v1'
  try {
    const url = new URL(apiUrl, window.location.origin)
    return `${proto}://${url.hostname}:${url.port || (proto === 'wss' ? '443' : '80')}`
  } catch {
    return `${proto}://${window.location.hostname}:8000`
  }
}
