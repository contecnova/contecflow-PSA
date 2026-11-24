/**
 * Piezas comunes del cuaderno: colores, iconos de etiqueta, nombres traducidos
 * y descarga de exportaciones.
 */
import {
  AlertTriangle, Bookmark, Calendar, CheckCircle, CircleDot, Flag, HelpCircle, Lightbulb, Mail, Phone, Star, User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Etiqueta, Formato, TipoExportable } from '../../services/api/cuaderno'
import { cuadernoApi } from '../../services/api/cuaderno'
import { downloadBlob } from '../../utils/helpers'

export const COLORES = ['blue', 'green', 'amber', 'red', 'purple', 'teal', 'pink', 'gray', 'orange'] as const
export const ICONOS_DE_ETIQUETA = ['circle-dot', 'star', 'help-circle', 'lightbulb', 'phone', 'flag', 'bookmark',
  'alert-triangle', 'check-circle', 'calendar', 'mail', 'user'] as const
const ICONOS: Record<string, LucideIcon> = {
  'circle-dot': CircleDot, star: Star, 'help-circle': HelpCircle, lightbulb: Lightbulb, phone: Phone, flag: Flag,
  bookmark: Bookmark, 'alert-triangle': AlertTriangle, 'check-circle': CheckCircle, calendar: Calendar, mail: Mail, user: User,
}
/** Claves de las etiquetas de fábrica (traducidas en la interfaz). */
export const ETIQUETAS_DE_FABRICA = ['todo', 'important', 'question', 'idea', 'call', 'critical']

type T = (k: string, v?: Record<string, unknown>) => string

export function IconoDeEtiqueta({ icono, size = 12 }: { icono?: string | null; size?: number }) {
  const Icono = ICONOS[icono || ''] || CircleDot
  return <Icono size={size} aria-hidden />
}

/** Nombre visible: las de fábrica sin cambiar, traducidas; el resto, como se escribió. */
export function nombreDeEtiqueta(t: T, e: Etiqueta | undefined, clave: string): string {
  if (e && e.scope === 'org' && ETIQUETAS_DE_FABRICA.includes(e.key)) {
    const fabrica = { todo: 'Pendiente', important: 'Importante', question: 'Pregunta', idea: 'Idea', call: 'Llamar a…', critical: 'Crítico' }[e.key]
    if (e.label === fabrica) return t(`cuaderno.tag_${e.key}`)
  }
  return e?.label || (ETIQUETAS_DE_FABRICA.includes(clave) ? t(`cuaderno.tag_${clave}`) : clave)
}

export async function descargarExportacion(kind: TipoExportable, id: string, formato: Formato, nombre: string): Promise<void> {
  const blob = await cuadernoApi.exportar(kind, id, formato)
  const limpio = (nombre || 'cuaderno').replace(/[\\/:*?"<>|]+/g, ' ').trim() || 'cuaderno'
  downloadBlob(blob, `${limpio}.${formato}`)
}

/** ¿Puede escribir con este permiso? */
export const puedeEscribir = (p?: string | null) => p === 'owner' || p === 'edit'
