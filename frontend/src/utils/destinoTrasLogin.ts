/**
 * Enlace profundo tras el login (auditoría 22-11-2026, M1 del 04).
 *
 * Un enlace (correo, aviso, marcador a `/projects/123`) sin sesión acababa en la
 * página de inicio. `ProtectedRoute` guarda aquí la ruta pedida y, al entrar, se
 * vuelve a ella. Va en sessionStorage (no en el estado del router) porque el SSO
 * sale al proveedor de identidad y vuelve con una carga completa.
 *
 * Solo rutas internas: empiezan por `/`, no por `//` ni `/\` (redirección abierta),
 * y no son `/login`.
 */
const CLAVE = 'cf_volver_a'

export function esRutaInterna(ruta: unknown): ruta is string {
  return typeof ruta === 'string' && ruta.startsWith('/') && !ruta.startsWith('//') && !ruta.startsWith('/\\')
    && !/^\/login(\/|\?|#|$)/.test(ruta)
}

export function guardarDestinoTrasLogin(ruta: string): void {
  if (!esRutaInterna(ruta) || ruta === '/') return
  try { sessionStorage.setItem(CLAVE, ruta) } catch { /* accesorio: almacenamiento bloqueado */ }
}

/** Devuelve y borra el destino guardado (o null). */
export function tomarDestinoTrasLogin(): string | null {
  try {
    const ruta = sessionStorage.getItem(CLAVE)
    sessionStorage.removeItem(CLAVE)
    return esRutaInterna(ruta) ? ruta : null
  } catch {
    return null
  }
}

/** Consulta el destino sin borrarlo. */
export function verDestinoTrasLogin(): string | null {
  try {
    const ruta = sessionStorage.getItem(CLAVE)
    return esRutaInterna(ruta) ? ruta : null
  } catch {
    return null
  }
}
