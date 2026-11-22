/**
 * Piezas comunes del flujo de demanda del operador (22-11-2026): catálogo del
 * configurador, textos en tres idiomas, insignias de estado y de plazo.
 */
import { useQuery } from '@tanstack/react-query'
import { Input, StatusBadge, Textarea } from '../ui'
import { demandaApi, type CatalogoDeDemanda, type EstadoDeDemanda, type EstadoSla, type TextoI18n } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import './demanda.css'

type T = ReturnType<typeof useAppT>

export const CATALOGO_VACIO: CatalogoDeDemanda = {
  assignee_types: [], decisions: [], phase_kinds: [], field_types: [], document_tags: [], notify_events: [], condition_ops: [],
  roles: [], groups: [], users: [], approval_workflows: [], execution_modes: [], channels: [],
}

/** `GET /demand/catalog` (opciones de los desplegables); con fallo, listas vacías. */
export function useCatalogoDemanda(): CatalogoDeDemanda {
  const { data } = useQuery({ queryKey: ['demand-catalog'], queryFn: demandaApi.catalogo, staleTime: 60_000 })
  return { ...CATALOGO_VACIO, ...(data || {}) }
}

/** Texto traducido de `clave`; si no existe, el valor técnico tal cual. */
export function etiquetaDe(t: T, prefijo: string, valor: string): string {
  const clave = `demanda.${prefijo}_${valor}`
  const v = t(clave)
  return v === clave ? valor : v
}

export const opcionesDe = (t: T, prefijo: string, valores: string[]) => valores.map(v => ({ value: v, label: etiquetaDe(t, prefijo, v) }))

const TONO_ESTADO: Record<EstadoDeDemanda, 'neutral' | 'warning' | 'info' | 'success' | 'danger' | 'accent'> = {
  draft: 'neutral', in_progress: 'info', pending_info: 'warning', on_hold: 'neutral', approved: 'success', rejected: 'danger', withdrawn: 'neutral', done: 'accent',
}

export function EstadoDeDemandaBadge({ estado }: { estado: EstadoDeDemanda }) {
  const t = useAppT()
  return <StatusBadge kind={TONO_ESTADO[estado] ?? 'neutral'}>{etiquetaDe(t, 'estado', estado)}</StatusBadge>
}

const TONO_SLA: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = { ok: 'success', warning: 'warning', breached: 'danger', paused: 'neutral' }

export function SlaBadge({ estado }: { estado: EstadoSla | undefined }) {
  const t = useAppT()
  if (!estado) return null
  return <StatusBadge kind={TONO_SLA[estado] ?? 'neutral'}>{etiquetaDe(t, 'sla', estado)}</StatusBadge>
}

const IDIOMAS: Array<keyof TextoI18n> = ['es', 'en', 'zh']

/** Tres cajas (es / en / zh) para un nombre traducible. */
export function CamposI18n({ etiqueta, valor, onChange, multilinea, requeridoEs }: {
  etiqueta: string; valor: TextoI18n | undefined; onChange: (v: TextoI18n) => void; multilinea?: boolean; requeridoEs?: boolean
}) {
  const v = valor || {}
  return (
    <div className="dem-rejilla dem-rejilla--i18n">
      {IDIOMAS.map(l => multilinea ? (
        <Textarea key={l} label={`${etiqueta} (${l})`} required={requeridoEs && l === 'es'} rows={2} value={v[l] ?? ''} onChange={e => onChange({ ...v, [l]: e.target.value })} />
      ) : (
        <Input key={l} label={`${etiqueta} (${l})`} required={requeridoEs && l === 'es'} value={v[l] ?? ''} onChange={e => onChange({ ...v, [l]: e.target.value })} />
      ))}
    </div>
  )
}
