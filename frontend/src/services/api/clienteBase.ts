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
import axios, { type AxiosInstance, type CreateAxiosDefaults } from 'axios'
import { API_BASE_URL } from './urls'

/** Límite de espera de una petición normal (las de IA lo amplían en `_core`). */
export const TIMEOUT_API_MS = 30_000

/** Instancia con la base y el límite comunes; `extra` añade cabeceras, credenciales… */
export function crearClienteDeApi(extra: CreateAxiosDefaults = {}): AxiosInstance {
  return axios.create({ baseURL: API_BASE_URL, timeout: TIMEOUT_API_MS, ...extra })
}

/** Cliente sin sesión para páginas públicas (enlace compartido, formularios públicos). */
export const apiPublica: AxiosInstance = crearClienteDeApi()
