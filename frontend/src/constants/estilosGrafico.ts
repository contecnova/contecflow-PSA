import type { CSSProperties } from 'react'

/**
 * Objetos de estilo para las props de Recharts que solo admiten un objeto
 * (`contentStyle`, `labelStyle`, `wrapperStyle`): no aceptan `className`. Son
 * constantes de módulo —misma referencia en cada render— y solo usan
 * `var(--token)`, así que siguen al tema y al acento.
 */

/** Tooltip sobre superficie 2 (el más habitual). */
export const TOOLTIP_SUPERFICIE_2: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)' }
/** Tooltip sobre superficie 2 con borde más marcado y esquinas redondeadas. */
export const TOOLTIP_SUPERFICIE_2_BORDE_5: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8 }
/** Tooltip sobre superficie 3, texto pequeño. */
export const TOOLTIP_SUPERFICIE_3_SM: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', fontSize: 'var(--text-sm)' }
/** Tooltip sobre superficie 3 redondeado, texto pequeño. */
export const TOOLTIP_SUPERFICIE_3_REDONDO_SM: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: 'var(--text-sm)' }
/** Tooltip sobre superficie 3 redondeado, texto muy pequeño. */
export const TOOLTIP_SUPERFICIE_3_REDONDO_XS: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: 'var(--text-xs)' }
/** Etiqueta del tooltip en texto principal. */
export const ETIQUETA_TEXTO_1: CSSProperties = { color: 'var(--text-1)' }
/** Leyenda pequeña en texto secundario. */
export const LEYENDA_SM: CSSProperties = { fontSize: 'var(--text-sm)', color: 'var(--text-2)' }
/** Leyenda muy pequeña en texto secundario. */
export const LEYENDA_XS: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-2)' }
/** Leyenda pequeña separada del gráfico. */
export const LEYENDA_SM_SEPARADA: CSSProperties = { fontSize: 'var(--text-sm)', color: 'var(--text-2)', paddingTop: 8 }
