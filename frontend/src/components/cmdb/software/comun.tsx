/**
 * Piezas comunes de la CMDB de software y vulnerabilidades (19-11-2026):
 * etiquetas de severidad y ciclo de vida, botón de subir fichero, descargas,
 * listas de valores del servidor (`/cmdb/software/meta`) y el aviso de error.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md (sección 8).
 */
import { useRef } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, StatusBadge } from '../../ui'
import type { StatusBadgeKind } from '../../ui'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { downloadBlob, extractErr, fmtDate } from '../../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../../constants/errors'
import { STALE_DEFAULT_MS } from '../../../constants/timings'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { CicloDeVidaEstado, Hallazgo, ResultadoDeImportacion, Severidad } from '../../../services/api/cmdbSoftware'

export const SEV_KIND: Record<string, StatusBadgeKind> = {
  critical: 'danger', high: 'orange', medium: 'warning', low: 'info', none: 'neutral', unknown: 'neutral',
}
export const CICLO_KIND: Record<string, StatusBadgeKind> = { eol: 'danger', unsupported: 'orange', soon: 'warning' }
export const ESTADO_KIND: Record<string, StatusBadgeKind> = {
  open: 'danger', triaged: 'warning', in_progress: 'info', mitigated: 'accent', resolved: 'success',
  false_positive: 'neutral', accepted: 'purple',
}
export const EXCEPCION_KIND: Record<string, StatusBadgeKind> = {
  pending: 'warning', approved: 'success', rejected: 'danger', expired: 'neutral', revoked: 'neutral',
}
/** Transiciones de estado de un hallazgo (las mismas que `gestion.TRANSICIONES` del servidor). */
export const TRANSICIONES: Record<string, string[]> = {
  open: ['triaged', 'in_progress', 'mitigated', 'false_positive'],
  triaged: ['open', 'in_progress', 'mitigated', 'false_positive'],
  in_progress: ['triaged', 'mitigated', 'false_positive'],
  mitigated: ['in_progress', 'false_positive'],
  false_positive: ['open'],
}
export const ORDEN_SEV: Severidad[] = ['critical', 'high', 'medium', 'low', 'none', 'unknown']

export function useErr() {
  const toast = useToast()
  return (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
}

/** Valores permitidos (categorías, entornos, relaciones…): el servidor manda. */
export function useMetaSw() {
  return useQuery({ queryKey: ['sw-meta'], queryFn: cmdbSoftwareApi.meta, staleTime: STALE_DEFAULT_MS })
}

/** Texto traducido de un código del servidor: `sw.v_<catalogo>.<codigo>` (si falta, el código). */
export function useEtiquetaSw() {
  const t = useAppT()
  return (catalogo: string, codigo: string | null | undefined) => (codigo ? etiquetaCodigo(t, `sw.v_${catalogo}`, codigo) : '—')
}

export function SeveridadBadge({ s }: { s: Severidad | string | null | undefined }) {
  const e = useEtiquetaSw()
  if (!s) return <span className="u-text3-xs">—</span>
  return <StatusBadge kind={SEV_KIND[s] ?? 'neutral'} caps={false}>{e('sev', s)}</StatusBadge>
}

export function CicloBadge({ c, fecha }: { c: CicloDeVidaEstado | undefined; fecha?: string | null }) {
  const e = useEtiquetaSw()
  if (!c) return null
  return <StatusBadge kind={CICLO_KIND[c] ?? 'neutral'} caps={false} title={fecha ?? undefined}>{e('vida', c)}</StatusBadge>
}

/** Opciones de un `<Select>` a partir de una lista de códigos. */
export function Opciones({ valores, catalogo, todos }: { valores: readonly string[] | undefined; catalogo: string; todos?: string }) {
  const e = useEtiquetaSw()
  return (
    <>
      {todos !== undefined && <option value="">{todos}</option>}
      {(valores ?? []).map(v => <option key={v} value={v}>{e(catalogo, v)}</option>)}
    </>
  )
}

/** Botón que abre el selector de ficheros y entrega el elegido. */
export function BotonFichero({ children, onFichero, onFicheros, multiple, accept, loading, icon, variant = 'secondary', size = 'sm', disabled }: {
  children: ReactNode; onFichero?: (f: File) => void; onFicheros?: (f: File[]) => void; multiple?: boolean; accept?: string; loading?: boolean; icon?: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost'; size?: 'xs' | 'sm' | 'md'; disabled?: boolean
}) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <>
      <input ref={ref} type="file" hidden accept={accept} multiple={multiple} aria-hidden="true" tabIndex={-1}
        onChange={e => {
          const lista = Array.from(e.target.files ?? [])
          if (lista.length) { onFicheros?.(lista); onFichero?.(lista[0]) }
          e.target.value = ''
        }} />
      <Button size={size} variant={variant} icon={icon} loading={loading} disabled={disabled} onClick={() => ref.current?.click()}>{children}</Button>
    </>
  )
}

/** Descarga un CSV que el servidor devuelve como blob. */
export async function descargar(peticion: Promise<{ data: unknown }>, nombre: string) {
  const r = await peticion
  downloadBlob(r.data as Blob, nombre)
}

/** Resumen legible de una importación (lo que se creó, cambió o quitó). */
export function useAvisoDeImportacion() {
  const t = useAppT()
  const toast = useToast()
  return (r: ResultadoDeImportacion | Record<string, unknown>) => {
    const n = (k: string) => Number((r as Record<string, unknown>)[k] ?? 0) || 0
    toast.success(t('sw.importado', { creados: n('created') + n('new_products'), actualizados: n('updated'), quitados: n('removed') }))
    // Composición (19-11-2026): ficheros que no se han podido leer y componentes sin versión.
    const ignorados = (r as Record<string, unknown>).ignored
    if (Array.isArray(ignorados) && ignorados.length) toast.warning(t('sw.importado_ignorados', { ficheros: ignorados.join(', ') }))
    if (n('unknown_version')) toast.warning(t('sw.importado_sin_version', { n: n('unknown_version') }))
  }
}

/** Lista clave → valor (dl con las clases sdm-kv). */
export function ListaKv({ filas }: { filas: [ReactNode, ReactNode][] }) {
  return (
    <dl className="sdm-kv">
      {filas.map(([k, v], i) => <div key={i} className="sw-kv-fila"><dt>{k}</dt><dd>{v ?? '—'}</dd></div>)}
    </dl>
  )
}

/** Valor de configuración legible (los secretos ya llegan enmascarados del servidor). */
export function valorLegible(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** Semáforo del plazo de remediación (`sla_tone` del servidor). */
export function Semaforo({ h }: { h: Pick<Hallazgo, 'sla_tone' | 'sla_days_left' | 'sla_due_at' | 'sla_breached'> }) {
  const t = useAppT()
  if (!h.sla_due_at) return <span className="u-text3-xs">—</span>
  const n = h.sla_days_left ?? 0
  return (
    <StatusBadge kind={h.sla_tone ?? 'neutral'} caps={false} dot title={fmtDate(h.sla_due_at)}>
      {h.sla_breached ? t('sw.sla_vencido', { n: Math.abs(n) }) : t('sw.sla_quedan', { n })}
    </StatusBadge>
  )
}

/** «Posible afectado»: no se conoce la versión exacta (prioridad a la mitad y sin plazo). */
export function PosibleBadge({ posible }: { posible?: boolean }) {
  const t = useAppT()
  if (!posible) return null
  return <StatusBadge kind="info" caps={false} title={t('sw.posible_ayuda')}>{t('sw.posible')}</StatusBadge>
}

/** Una versión; `null` se lee «versión desconocida». */
export function VersionTexto({ v }: { v: string | null | undefined }) {
  const t = useAppT()
  return v ? <span className="u-mono">{v}</span> : <span className="sw-version-desconocida">{t('sw.version_desconocida')}</span>
}
