/**
 * Refresco tras escritura (18-11-2026).
 *
 * Antes cada pantalla decidía a mano qué consultas invalidar después de crear,
 * editar o borrar, y muchas se olvidaban de alguna: al crear un cliente o
 * cambiar su contacto principal, la lista de contactos no cambiaba hasta
 * recargar. Ahora, tras cualquier escritura con éxito (POST/PUT/PATCH/DELETE)
 * que pasa por el cliente HTTP común, se invalidan TODAS las consultas: las que
 * están en pantalla se vuelven a pedir al momento y las demás quedan obsoletas
 * y se piden al volver a mostrarse. Varias escrituras seguidas se agrupan en
 * un solo refresco.
 *
 * Fuera quedan las peticiones que usan POST para leer o que no cambian datos
 * de nadie (vistas previas, simuladores, búsquedas, traducción bajo demanda,
 * «escribiendo…», latidos, sesión): refrescarlo todo con ellas sería ruido.
 */
import type { QueryClient } from '@tanstack/react-query'

let cliente: QueryClient | null = null
let pendiente: ReturnType<typeof setTimeout> | null = null

/** Milisegundos para agrupar escrituras seguidas en un solo refresco. */
export const AGRUPAR_ESCRITURAS_MS = 60

const ESCRITURAS = new Set(['post', 'put', 'patch', 'delete'])

/** Rutas que escriben sin cambiar datos visibles (o que leen con POST). */
export const SIN_REFRESCO: RegExp[] = [
  /\/auth\//,
  /\/ws-ticket\b/,
  /\/preview\b/,
  /\/previa\b/,
  /\/simulat/,
  /\/search\b/,
  /\/query\b/,
  /\/ask\b/,
  /\/translation\/(messages|text|outbound\/preview|test)\b/,
  /\/typing\b/,
  /\/presence\b/,
  /\/heartbeat\b/,
  /\/ai\/(texto|chat)\b/,
  /\/estimate\b/,
  /\/validation\b/,
  // «Mi cuaderno» (migración 202): el guardado automático y el estado de los chips
  // no cambian lo que se ve en otras pantallas (y refrescar con cada guardado sobra).
  /\/notebook\/pages\/[^/]+\/content\b/,
  /\/notebook\/chips\/resolve\b/,
  // 23-11-2026: las predicciones se piden con POST desde useQuery (ProjectRiskBadge en
  // cada tarjeta). Refrescar tras ellas volvía a pedirlas: bucle de cientos de
  // peticiones por minuto que agotó el pool de conexiones del backend.
  /\/predictions\//,
]

/**
 * Freno general contra bucles: una petición hecha DURANTE un refresco (las
 * consultas que se vuelven a pedir) no dispara otro. Una lectura con POST que
 * no esté en `SIN_REFRESCO` ya no puede encadenar refrescos sin fin.
 */
export const VENTANA_TRAS_REFRESCO_MS = 1500
let refrescandoHasta = 0

/** Lo registra main.tsx con el QueryClient de la aplicación. */
export function registrarClienteDeConsultas(qc: QueryClient): void {
  cliente = qc
}

/** ¿Esta respuesta debe refrescar las consultas? */
export function debeRefrescar(metodo: string | undefined, url: string | undefined): boolean {
  if (!metodo || !ESCRITURAS.has(metodo.toLowerCase())) return false
  const ruta = url || ''
  return !SIN_REFRESCO.some(r => r.test(ruta))
}

/** Llamado por el interceptor tras una respuesta 2xx. */
export function trasEscritura(metodo: string | undefined, url: string | undefined): void {
  if (!cliente || !debeRefrescar(metodo, url)) return
  if (Date.now() < refrescandoHasta) return
  if (pendiente) clearTimeout(pendiente)
  pendiente = setTimeout(() => {
    pendiente = null
    refrescandoHasta = Date.now() + VENTANA_TRAS_REFRESCO_MS
    // `active`: solo se vuelve a pedir lo que está en pantalla; el resto queda obsoleto.
    void cliente?.invalidateQueries({ refetchType: 'active' })
  }, AGRUPAR_ESCRITURAS_MS)
}
