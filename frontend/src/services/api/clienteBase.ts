/**
 * Cliente HTTP común (19-11-2026).
 *
 * Auditoría de hardcodeados: el cliente de la app (`_core.ts`), el portal de
 * clientes, la vista pública por enlace y el formulario público creaban cada uno
 * su `axios.create` con `timeout: 30000` escrito a mano (y el formulario usaba
 * `axios` sin límite). Ahora todos salen de aquí: misma base (`API_BASE_URL`)
 * y mismo límite (`TIMEOUT_API_MS`). Cada uno sigue con su sesión propia: el
 * portal y las vistas públicas NO deben disparar el refresco de la sesión de
 * empleado, por eso no reutilizan la instancia de `_core`.
 */
import axios, { type AxiosInstance, type AxiosResponse, type CreateAxiosDefaults } from 'axios'
import { API_BASE_URL } from './urls'

/** Límite de espera de una petición normal (las de IA lo amplían en `_core`). */
export const TIMEOUT_API_MS = 30_000

function leerCookie(nombre: string): string | null {
  if (typeof document === 'undefined') return null
  const par = document.cookie.split('; ').find(c => c.startsWith(`${nombre}=`))
  return par ? decodeURIComponent(par.slice(nombre.length + 1)) : null
}

/**
 * Instancia con la base y el límite comunes; `extra` añade cabeceras, credenciales…
 *
 * Incidencia 7 de usuarios (23-11-2026): las instancias con cookies
 * (`withCredentials`, el portal de clientes) devuelven el testigo CSRF en
 * `X-CSRF-Token` en las peticiones que escriben, como `_core.ts`. Sin él, con
 * `CSRF_DOUBLE_SUBMIT=1` el portal no podía guardar nada tras entrar (ni el
 * cambio de contraseña obligatorio del primer acceso): 403 «missing csrf token».
 */
/**
 * Idioma de la interfaz de operador (24-11-2026, barrido de traducciones). Va en la
 * cabecera `X-Idioma` de cada petición para que el servidor devuelva en ese idioma
 * el contenido que traduce él (biblioteca de Certificaciones: marcos, controles,
 * plantillas). Se lee de `localStorage` (misma clave que `AppLangContext.STORAGE_KEY`,
 * sin importarlo para no meter el contexto de React en el cliente HTTP).
 */
export function idiomaDeLaInterfaz(): string {
  try {
    return (typeof localStorage !== 'undefined' && localStorage.getItem('contecflow_operator_lang')) || 'es'
  } catch {
    return 'es'
  }
}

export function crearClienteDeApi(extra: CreateAxiosDefaults = {}): AxiosInstance {
  const instancia = axios.create({ baseURL: API_BASE_URL, timeout: TIMEOUT_API_MS, ...extra })
  instancia.interceptors.request.use((config) => {
    config.headers.set('X-Idioma', idiomaDeLaInterfaz())
    return config
  })
  if (extra.withCredentials) {
    instancia.interceptors.request.use((config) => {
      const metodo = (config.method || 'get').toUpperCase()
      if (metodo !== 'GET' && metodo !== 'HEAD' && metodo !== 'OPTIONS') {
        const csrf = leerCookie('csrf_token')
        if (csrf) config.headers.set('X-CSRF-Token', csrf)
      }
      return config
    })
  }
  return instancia
}

/** Cliente sin sesión para páginas públicas (enlace compartido, formularios públicos). */
export const apiPublica: AxiosInstance = crearClienteDeApi()

/**
 * Desenvuelve los dos sobres del servidor en la respuesta (23-11-2026,
 * auditoría 05 A.3: antes estaba copiado en `_core.ts` y en el portal):
 *
 * - lista (`APIListResponse`): exactamente `{ items, meta }` → `res.data` es el
 *   array y `res.meta` la paginación;
 * - objeto (`APIResponse`): exactamente `{ data, meta }` → `res.data` es el
 *   contenido y `res.meta` la meta.
 *
 * Guardas estrictas (dos claves exactas) para no tocar un payload que tenga por
 * casualidad una clave `data` o `items`. Modifica y devuelve la misma respuesta.
 */
export function desenvolverSobre<R extends AxiosResponse<unknown>>(res: R): R & { meta?: Record<string, unknown> } {
  const body = res?.data as Record<string, unknown> | null | undefined
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const claves = Object.keys(body)
    if (claves.length === 2 && Array.isArray(body.items) && body.meta && typeof body.meta === 'object') {
      ;(res as { meta?: unknown }).meta = body.meta
      ;(res as { data: unknown }).data = body.items
    } else if (claves.length === 2 && 'data' in body && 'meta' in body) {
      ;(res as { meta?: unknown }).meta = body.meta
      ;(res as { data: unknown }).data = body.data
    }
  }
  return res as R & { meta?: Record<string, unknown> }
}
