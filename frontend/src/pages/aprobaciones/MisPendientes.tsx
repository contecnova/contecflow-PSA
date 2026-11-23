/**
 * Pestaña de aprobaciones pendientes del usuario y aviso de fuera de la oficina.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import PoliticaDeLaSolicitud from '../../components/politicas/PoliticaDeLaSolicitud'
import { useId, useState } from 'react'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { CheckCircle2, Clock as ClockIcon, Check, X } from 'lucide-react'
import { Button, EmptyState, KpiCard, Select, Checkbox } from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { UserSelect } from '../../components/ui/EntitySelect'
import DateInput from '../../components/ui/DateInput'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import { color, entityLabels, ICONO_ENTIDAD_DESCONOCIDA, type PendingRequest } from './compartido'

// ── Fuera de la oficina (revisión 2026-11) ───────────────────────────────────
// Mientras dura, los avisos de mis aprobaciones llegan también al delegado y
// este puede decidir los pasos que me tocarían.
function FueraDeLaOficina() {
  const t = useAppT()
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ delegate_id?: string | null; away_from?: string | null; away_until?: string | null }>({
    queryKey: ['approvals-ooo'], queryFn: () => approvalsApi.getOutOfOffice().then(r => r.data),
  })
  const [form, setForm] = useState<{ delegate_id: string; away_from: string; away_until: string } | null>(null)
  const actual = form ?? { delegate_id: data?.delegate_id ?? '', away_from: data?.away_from ?? '', away_until: data?.away_until ?? '' }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: (d: typeof actual) => approvalsApi.setOutOfOffice({ delegate_id: d.delegate_id || null, away_from: d.away_from || null, away_until: d.away_until || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approvals-ooo'] }); setForm(null); toast.success(t('approvals.guardado')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_guardar'))),
  })
  return (
    <details className="ds-card apv-ooo" open={Boolean(data?.delegate_id)}>
      <summary>
        {t('approvals.fuera_de_la_oficina')}{data?.delegate_id && data.away_until ? ` · ${t('approvals.delegado_hasta', { fecha: fmtDate(data.away_until) })}` : ''}
      </summary>
      <div className="apv-ooo__fila">
        <div className="apv-ooo__delegado">
          <div className="u-text3-xs" id={`${idCampo}-delegar`}>{t('approvals.delegar_en')}</div>
          <span aria-labelledby={`${idCampo}-delegar`}>
            <UserSelect value={actual.delegate_id} onChange={id => setForm({ ...actual, delegate_id: id })} placeholder={t('approvals.elige_a_quien')} />
          </span>
        </div>
        <label htmlFor={`${idCampo}-desde`} className="u-text3-xs">{t('approvals.desde')}<br />
          <DateInput id={`${idCampo}-desde`} value={actual.away_from} onChange={e => setForm({ ...actual, away_from: e.target.value })} className="apv-ooo__fecha" /></label>
        <label htmlFor={`${idCampo}-hasta`} className="u-text3-xs">{t('approvals.hasta')}<br />
          <DateInput id={`${idCampo}-hasta`} value={actual.away_until} onChange={e => setForm({ ...actual, away_until: e.target.value })} className="apv-ooo__fecha" /></label>
        <Button size="sm" disabled={isPending || !actual.delegate_id || !actual.away_from || !actual.away_until} onClick={() => guardar(actual)}>{t('approvals.guardar')}</Button>
        {data?.delegate_id && <Button size="sm" variant="secondary" disabled={isPending} onClick={() => guardar({ delegate_id: '', away_from: '', away_until: '' })}>{t('approvals.quitar')}</Button>}
      </div>
    </details>
  )
}

// ── Tab de mis solicitudes pendientes ─────────────────────────────────────────
export function MyPendingTab() {
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [entityFilter, setEntityFilter] = useState('all')
  const [sortMode, setSortMode] = useState('oldest') // oldest | newest

  const { data: pending = [], isLoading } = useQuery<PendingRequest[]>({
    queryKey: ['approvals-pending-me'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
    enabled: !loading && !!user,
  })

  const refrescar = () => {
    // Cascade to the affected entity caches (approval could be for timesheets, expenses, or absences)
    for (const k of ['approvals-pending-me', 'timesheets-pending', 'timesheets-mine', 'expenses-pending', 'expenses-my', 'absences-pending', 'team-absences']) {
      qc.invalidateQueries({ queryKey: [k] })
    }
  }
  const { mutate: decide, isPending: deciding } = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: string; note?: string }) => approvalsApi.decide(id, { decision, note }),
    onSuccess: () => { refrescar(); toast.success(t('approvals.decision_registered')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const [bulkApproving, setBulkApproving] = useState(false)

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return
    setBulkApproving(true)
    try {
      await Promise.all(Array.from(selectedIds).map(id => approvalsApi.decide(id, { decision: 'approved' })))
      toast.success(t('approvals.approve_selected', { count: selectedIds.size }))
      setSelectedIds(new Set())
      refrescar()
    } catch (e) {
      toast.error(extractErr(e, t('approvals.bulk_approval_error')))
    } finally {
      setBulkApproving(false)
    }
  }

  const toggleSelect = (id: string) => setSelectedIds(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const queue = pending
    .filter(r => entityFilter === 'all' ? true : r.entity_type === entityFilter)
    .sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime()
      const tb = new Date(b.created_at || 0).getTime()
      return sortMode === 'oldest' ? ta - tb : tb - ta
    })

  const toggleAll = () => setSelectedIds(prev =>
    prev.size === queue.length ? new Set() : new Set(queue.map(r => r.id))
  )

  const statsByEntity: Record<string, number> = pending.reduce((acc: Record<string, number>, r) => {
    acc[r.entity_type] = (acc[r.entity_type] || 0) + 1
    return acc
  }, {})

  if (isLoading) return <div className="apv-cargando" role="status">{t('approvals.loading')}</div>

  if (pending.length === 0) return (
    <div className="ds-stack-lg">
      <FueraDeLaOficina />
      <div className="ds-card">
        <EmptyState icon={<CheckCircle2 size={28} />} title={t('approvals.no_pending_title')} description={t('approvals.no_pending_desc')} />
      </div>
    </div>
  )

  return (
    <div className="ds-stack-lg">
      <FueraDeLaOficina />
      <div className="ds-grid-stats">
        <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.total_pending')} value={pending.length} warning={pending.length > 0} />
        {Object.entries(statsByEntity).slice(0, 3).map(([k, count]) => {
          const entity = entityLabels(t)[k] || { label: k, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }
          return <KpiCard key={k} icon={entity.icon} label={entity.label} value={count} />
        })}
      </div>

      <div className="ds-toolbar">
        <Select suelto placeholder={false} aria-label={t('approvals.filter_by_entity')} value={entityFilter} onChange={e => setEntityFilter(e.target.value)} className="ds-input apv-input--auto">
          <option value="all">{t('approvals.all_entities')}</option>
          {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('approvals.sort_requests')} value={sortMode} onChange={e => setSortMode(e.target.value)} className="ds-input apv-input--auto">
          <option value="oldest">{t('approvals.sort_oldest')}</option>
          <option value="newest">{t('approvals.sort_newest')}</option>
        </Select>
      </div>

      <div className="ds-row-between">
        <label htmlFor="approvals-select-all" className="apv-seleccion">
          <Checkbox id="approvals-select-all" className="apv-casilla"
            checked={queue.length > 0 && selectedIds.size === queue.length} onChange={toggleAll} />
          {selectedIds.size === 0
            ? t('approvals.queue_for_approval', { count: queue.length })
            : t('approvals.selected_of_total', { selected: selectedIds.size, total: queue.length })}
        </label>
        {selectedIds.size > 0 && (
          <Button size="sm" icon={<Check size={14} />} onClick={handleBulkApprove} loading={bulkApproving}>
            {t('approvals.approve_selected', { count: selectedIds.size })}
          </Button>
        )}
      </div>
      <div data-export-table="approvals-export" className="ds-stack-sm">
        {queue.map(req => {
          const entity = entityLabels(t)[req.entity_type] || { label: req.entity_type, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }
          const ageHours = Math.max(0, Math.floor((Date.now() - new Date(req.created_at || Date.now()).getTime()) / 3600000))
          const isUrgent = ageHours >= 24
          const marcada = selectedIds.has(req.id)
          return (
            <div key={req.id} className={`ds-card apv-solicitud${marcada ? ' apv-solicitud--marcada' : isUrgent ? ' apv-solicitud--urgente' : ''}`}>
              <div className="apv-solicitud__fila">
                <Checkbox className="apv-casilla apv-casilla--arriba"
                  aria-label={t('approvals.select_request_aria', { name: req.entity_summary || req.entity_id })}
                  checked={marcada} onChange={() => toggleSelect(req.id)} />
                <div className="u-flex1-min0">
                  <div className="ds-row-wrap apv-solicitud__chips">
                    <span className="ds-pill apv-entidad apv-icono-texto" style={color(entity.color)}>{entity.icon} {entity.label}</span>
                    {req.step_name && (
                      <span className="ds-muted u-xs">{t('approvals.step_n', { order: req.step_order })}: {req.step_name}</span>
                    )}
                  </div>
                  <div className="apv-solicitud__titulo">{req.entity_summary || req.entity_id}</div>
                  <div className="ds-muted">{t('approvals.request_by')}: {req.requester_name} · {fmtDateTime(req.created_at)}</div>
                  <PoliticaDeLaSolicitud resumen={req.politica} entidadId={req.entity_id} origenDelPaso={req.step_origin} />
                  {isUrgent && (
                    <div className="apv-solicitud__urgente">
                      <ClockIcon size={11} aria-hidden />
                      {t('approvals.pending_since', { hours: ageHours })}
                    </div>
                  )}
                </div>
                <div className="apv-solicitud__botones">
                  <Button size="sm" variant="secondary" icon={<X size={14} />}
                    title={t('approvals.reject_request_aria', { name: req.entity_summary || req.entity_id })}
                    onClick={() => decide({ id: req.id, decision: 'rejected', note: '' })}
                    disabled={deciding}>
                    {t('approvals.reject_action')}
                  </Button>
                  <Button size="sm" icon={<Check size={14} />} onClick={() => decide({ id: req.id, decision: 'approved' })} loading={deciding}>
                    {t('approvals.approve_action')}
                  </Button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
