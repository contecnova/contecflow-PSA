// Tipos, colores y hooks compartidos por las pestañas y modales de la CMDB. 23-11-2026: troceado de CMDBPage sin cambio de comportamiento.
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../constants/timings'

// Auditoría 2026-11: esta pantalla editaba `cmdb_items`, una segunda CMDB que
// los tickets no veían. Ahora trabaja sobre `/sd/cmdb`, la misma que eligen
// tickets, problemas y cambios, y que alimenta el descubrimiento.

/** Color de la etiqueta (dato): lo consume `.cmdb-chip` vía `--cmdb-chip`. */
export const chip = (color: string): CSSProperties => ({ '--cmdb-chip': color } as CSSProperties)

export type CI = {
  id: string; code?: string; name?: string; ci_type?: string; status?: string
  environment?: string; description?: string; hostname?: string; ip_address?: string; version?: string
  criticality?: string; attributes?: Record<string, unknown>; is_discovered?: boolean
  discovery_provider?: string; drift_detected_at?: string
}

// Las clases de `CIType` en el servidor (app/models/service_desk/_enums.py).
export const CI_TYPES = ['server','virtual_machine','application','database','network','service','container','cloud','endpoint','storage','module','integration','other']

// Atributos propios de cada clase; se guardan en `attributes`. Host, IP y
// versión son columnas comunes a todas y van aparte. Auditoría 2026-11:
// estaban escritos aquí; ahora los configura cada organización (pestaña
// «Clases») y los de fábrica viven en el servidor (cmdb_clases.py).
export type Campo = { key: string; label?: string | null; field_type: string }

type CamposDeClase = { por_defecto: boolean; clases: Record<string, Campo[]> }

export function useCamposDeClase() {
  return useQuery<CamposDeClase>({
    queryKey: ['cmdb-class-fields'],
    queryFn: () => cmdbApi.classFields().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
}

/** La etiqueta escrita por la organización o, si no hay, la traducida de fábrica. */
export function useEtiquetaDeCampo() {
  const t = useAppT()
  return (c: Campo) => {
    if (c.label) return c.label
    const texto = t(`cmdb.f_${c.key}`)
    return texto === `cmdb.f_${c.key}` ? c.key : texto
  }
}

export const STATUS_COLOR: Record<string, string> = { operational:'var(--success)', degraded:'var(--orange)', maintenance:'var(--warning)', retired:'var(--text-2)' }

export const ENV_COLOR: Record<string, string> = { production:'var(--danger)', staging:'var(--warning)', test:'var(--purple)', development:'var(--accent)' }

export const CRITICALITIES = ['low','medium','high','critical']

export const REL_TYPES = ['depends_on','hosts','connects_to','backed_up_by','monitored_by','part_of']

/** Una clave de i18n que puede no existir: si no, el valor tal cual. */
export function useEtiqueta() {
  const t = useAppT()
  return (prefijo: string, valor?: string) => {
    if (!valor) return '—'
    const clave = `cmdb.${prefijo}${valor}`
    const texto = t(clave)
    return texto === clave ? valor : texto
  }
}
