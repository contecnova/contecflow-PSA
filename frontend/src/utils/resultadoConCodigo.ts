/**
 * Texto de un resultado del servidor que trae `code` (+ `params`) además de un
 * `detail`/`error` de respaldo (incidencia 10 de usuarios, 23-11-2026): «probar
 * conexión» de las integraciones y del buzón del Service Desk salían con textos
 * fijos en castellano o en inglés («no test probe defined for sd_mailbox»).
 *
 * El código se traduce con el catálogo de errores del operador (`err_srv.*`,
 * generado por `scripts/codemods/errores_con_codigo.py --sincronizar`); si no
 * hay traducción, se muestra el texto de respaldo.
 */
export type ResultadoConCodigo = {
  code?: string | null
  params?: Record<string, unknown> | null
  detail?: string | null
  error?: string | null
}

export type Traducir = (clave: string, params?: Record<string, unknown>) => string

export function textoDeResultado(t: Traducir, r: ResultadoConCodigo | null | undefined, respaldo = ''): string {
  if (!r) return respaldo
  if (r.code) {
    const clave = `err_srv.${r.code}`
    const texto = t(clave, { ...(r.params ?? {}) })
    if (texto && texto !== clave && texto !== r.code) return texto
  }
  return r.detail || r.error || respaldo
}
