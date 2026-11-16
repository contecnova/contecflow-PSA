/**
 * MarcaExterno — «Externo · <proveedor>» junto al nombre de una persona.
 *
 * Un recurso externo es un usuario con rol `subcontractor` (persona de un
 * proveedor `Subcontractor`). En el trabajo diario se le trata como interno,
 * pero en cualquier lista o selector de personas tiene que verse que es de
 * fuera y de qué proveedor. El servidor añade `external_company` (nombre del
 * proveedor o null) a los usuarios de ese rol en `/users`, `/users/directory`
 * y los miembros de proyecto.
 *
 * - `esExterno(p)` y `textoMarcaExterno(t, p)`: puras, para `<option>` y textos.
 * - `etiquetaDePersona(t, p)`: «Nombre · Externo · Proveedor» o solo el nombre.
 * - `<MarcaExterno persona={p} />`: la pastilla (nada si la persona es interna).
 */
import { Building2 } from 'lucide-react'
import { useTextoUi } from './useTextoUi'
import './MarcaExterno.css'

type Traducir = (clave: string, params?: Record<string, string | number>) => string

export interface PersonaConEmpresa {
  role?: string | null
  external_company?: string | null
  full_name?: string | null
  name?: string | null
}

export const ROL_EXTERNO = 'subcontractor'

/** La persona es un recurso externo (rol `subcontractor` o con proveedor informado). */
export function esExterno(p: PersonaConEmpresa | null | undefined): boolean {
  if (!p) return false
  return p.role === ROL_EXTERNO || !!(p.external_company && p.external_company.trim())
}

/** «Externo · Proveedor» (o «Externo» sin proveedor); null si es interna. */
export function textoMarcaExterno(t: Traducir, p: PersonaConEmpresa | null | undefined): string | null {
  if (!esExterno(p)) return null
  const empresa = p?.external_company?.trim()
  return empresa ? t('uikit.externo_de', { empresa }) : t('uikit.externo')
}

/** Nombre de la persona con la marca de externo detrás si lo es. */
export function etiquetaDePersona(t: Traducir, p: PersonaConEmpresa | null | undefined): string {
  const nombre = p?.full_name || p?.name || ''
  const marca = textoMarcaExterno(t, p)
  return marca ? (nombre ? `${nombre} · ${marca}` : marca) : nombre
}

export interface MarcaExternoProps {
  persona: PersonaConEmpresa | null | undefined
  className?: string
}

/** Pastilla «Externo · Proveedor»; no pinta nada para una persona interna. */
export default function MarcaExterno({ persona, className }: MarcaExternoProps) {
  const t = useTextoUi()
  const texto = textoMarcaExterno(t, persona)
  if (!texto) return null
  return (
    <span className={`ui-marca-externo${className ? ` ${className}` : ''}`} title={texto}>
      <Building2 size={11} aria-hidden />
      <span>{texto}</span>
    </span>
  )
}
