/**
 * Estado del almacén analítico (DuckDB) que usan Ask the Data y los informes
 * (revisión 2026-11). Antes una carga fallida sólo iba al log y el almacén podía
 * estar vacío sin que nadie lo supiera.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'

type Carga = { run_at: string; status: string; detail: Record<string, unknown> } | null
type Estado = { last_run: Carga; last_ok: Carga; company_rows: Record<string, number> }

export default function EstadoDelAlmacen() {
  const { t } = useAppLang()
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<Estado>({ queryKey: ['olap-status'], queryFn: () => analyticsApi.olapStatus().then(r => r.data) })
  const cargar = useMutation({
    mutationFn: () => analyticsApi.olapRefresh(),
    onSuccess: () => { toast.success(t('dataexplorer.almacen_cargado')); qc.invalidateQueries({ queryKey: ['olap-status'] }) },
    onError: (e: unknown) => { toast.error(extractErr(e, 'Error')); qc.invalidateQueries({ queryKey: ['olap-status'] }) },
  })
  if (!data) return null
  const filas = data.company_rows
  const fallo = data.last_run?.status === 'error'
  const vacio = !data.last_ok
  const color = fallo || vacio ? 'var(--warning)' : 'var(--text-3)'
  return (
    <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 'var(--text-xs)', color }}>
      <span>
        {vacio ? t('dataexplorer.almacen_vacio')
          : t('dataexplorer.almacen_estado', {
            fecha: new Date(data.last_ok!.run_at + 'Z').toLocaleString(),
            imputaciones: filas.fact_imputations ?? 0, proyectos: filas.fact_projects ?? 0,
            tickets: filas.fact_tickets ?? 0, oportunidades: filas.fact_pipeline ?? 0,
          })}
        {fallo && ` · ${t('dataexplorer.almacen_fallo', { error: String(data.last_run?.detail?.error ?? '') })}`}
      </span>
      {/* 2026-11: la recarga es global (todas las empresas): solo superadmin. */}
      {user?.is_superadmin && (
        <button type="button" onClick={() => cargar.mutate()} disabled={cargar.isPending}
          style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '2px 8px', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-xs)' }}>
          {cargar.isPending ? '…' : t('dataexplorer.almacen_cargar')}
        </button>
      )}
    </div>
  )
}
