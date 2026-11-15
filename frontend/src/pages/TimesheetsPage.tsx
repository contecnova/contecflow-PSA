import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { timesheetsApi, imputationsApi } from '../services/api'
import type { FiltroDeTimesheets, FiltroDeTimesheetsDelEquipo } from '../services/api'
import type { EstadoDeTimesheet, LineaDeTimesheet, Timesheet } from '../services/api/tipos-personas'
import { Button, Modal, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Clock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fmtHours, fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import Pagination from '../components/ui/Pagination'
import { DEFAULT_PAGE_SIZE } from '../constants/pagination'
import { useValorConRetardo } from '../hooks/useValorConRetardo'
import './TimesheetsPage.css'

type TimesheetStatus = EstadoDeTimesheet
type TimesheetItem = Timesheet
type TimesheetLine = LineaDeTimesheet

type TeamSortKey = 'user_name' | 'week_start' | 'total_hours' | 'billable_hours' | 'total_cost' | 'status'

type RoleAuth = {
  hasRole: (...roles: string[]) => boolean
}

type T = (key: string, params?: Record<string, string | number>) => string

const STATUS_CFG: Record<string, { labelKey: string; color: string }> = {
  draft:     { labelKey: 'timesheets.estado_borrador',  color: 'var(--text-2)' },
  submitted: { labelKey: 'timesheets.submitted', color: 'var(--warning)' },
  approved:  { labelKey: 'timesheets.approved',  color: 'var(--success)' },
  rejected:  { labelKey: 'timesheets.rejected', color: 'var(--danger)' },
}
const STATUS_IDS = ['draft', 'submitted', 'approved', 'rejected'] as const

function onKeyboardActivate(event: { key: string; preventDefault: () => void }, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function StatusBadge({ status }: { status: TimesheetStatus }) {
  const t = useAppT() as T
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft
  return (
    <DsBadge color={cfg.color}>{t(cfg.labelKey)}</DsBadge>
  )
}

function WeekLines({ weekStart, onClose }: { weekStart: string; onClose: () => void }) {
  const t = useAppT() as T
  const toast = useToast()
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState<string | number | null>(null)
  const [editForm, setEditForm] = useState({ hours: 0, description: '' })

  const { data: lines = [], isLoading } = useQuery<TimesheetLine[]>({
    queryKey: ['timesheet-lines', weekStart],
    queryFn: () => timesheetsApi.weekLines(weekStart).then(r => r.data),
  })

  const { mutate: updateLine, isPending: updating } = useMutation({
    mutationFn: ({ id, data }: { id: string | number; data: { hours: number; description: string } }) => imputationsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['timesheet-lines', weekStart] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
      setEditingId(null)
    },
    onError: e => toast.error(extractErr(e, t('timesheets.error_actualizar'))),
  })

  const { mutate: deleteLine } = useMutation({
    mutationFn: (id: string | number) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['timesheet-lines', weekStart] })
      qc.invalidateQueries({ queryKey: ['timesheets-mine'] })
      qc.invalidateQueries({ queryKey: ['timesheets-pending'] })
      qc.invalidateQueries({ queryKey: ['timesheets-team'] })
    },
    onError: e => toast.error(extractErr(e, t('timesheets.error_eliminar'))),
  })

  const byDay: Record<string, TimesheetLine[]> = lines.reduce((a, l) => {
    const d = l.date
    if (!a[d]) a[d] = []
    a[d].push(l)
    return a
  }, {} as Record<string, TimesheetLine[]>)

  return (
    <Modal open title={t('timesheets.modal_semana', { semana: weekStart })} onClose={onClose} width={660}>
      {isLoading ? <Spinner /> : lines.length === 0 ? (
        <EmptyState icon="⏱️" title={t('timesheets.sin_imputaciones')} description={t('timesheets.sin_lineas_semana')} />
      ) : (
        <div className="u-stack-12">
          {(Object.entries(byDay) as Array<[string, TimesheetLine[]]>).sort().map(([day, dayLines]) => (
            <div key={day}>
              <div className="ts-day-head">{fmtDate(day)}</div>
              {dayLines.map(l => (
                <div key={l.id} className="ts-line">
                  {editingId === l.id ? (
                    /* ── Modo edición inline ── */
                    <div className="ts-line-edit">
                      <input type="number" min="0.25" max="24" step="0.25"
                        aria-label={t('timesheets.horas')}
                        value={editForm.hours}
                        onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                        className="ts-line-input ts-line-input--hours" />
                      <span className="u-text2-sm">h</span>
                      <input value={editForm.description}
                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                        placeholder={t('timesheets.descripcion_del_trabajo')}
                        aria-label={t('timesheets.descripcion_del_trabajo')}
                        className="ts-line-input ts-line-input--desc" />
                      <button type="button" onClick={() => updateLine({ id: l.id, data: { hours: editForm.hours, description: editForm.description } })}
                        disabled={updating || editForm.hours <= 0}
                        className="ts-line-save">
                        {updating ? '...' : `✓ ${t('timesheets.guardar')}`}
                      </button>
                      <button type="button" onClick={() => setEditingId(null)} className="ts-line-cancel">
                        {t('timesheets.cancelar')}
                      </button>
                    </div>
                  ) : (
                    /* ── Vista normal ── */
                    <div className="ts-line-view">
                      <span className="ts-line-hours">{l.hours}h</span>
                      <div className="u-flex1-min0">
                        <div className="u-base-600">{l.project_name}</div>
                        {l.description && <div className="ts-line-desc">{l.description}</div>}
                      </div>
                      <div className="ts-line-actions">
                        {l.billable && <span className="ts-tag ts-tag--billable">{t('timesheets.facturable')}</span>}
                        {l.is_approved && <span className="ts-tag ts-tag--approved">✓ {t('timesheets.approved')}</span>}
                        {!l.is_approved && (
                          <>
                            <button type="button"
                              onClick={() => { setEditingId(l.id); setEditForm({ hours: l.hours, description: l.description || '' }) }}
                              aria-label={t('timesheets.editar_linea')} title={t('timesheets.editar_linea')}
                              className="ts-icon-btn">
                              <span aria-hidden="true">✏</span>
                            </button>
                            <button type="button"
                              onClick={() => { openConfirmGlobal({ message: t('timesheets.confirmar_eliminar'), onConfirm: () => deleteLine(l.id), danger: true }) }}
                              aria-label={t('timesheets.eliminar_linea')} title={t('timesheets.eliminar_linea')}
                              className="ts-icon-btn ts-icon-btn--danger">
                              <span aria-hidden="true">🗑</span>
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
          <div className="ts-lines-total">
            {t('timesheets.total')}: <span className="ts-lines-total-value">
              {lines.reduce((s, l) => s + l.hours, 0).toFixed(1)}h</span>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ReviewModal({ timesheet, onClose }: { timesheet: TimesheetItem; onClose: () => void }) {
  const t = useAppT() as T
  const idCampo = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const [notes, setNotes] = useState('')
  const { mutate: review, isPending } = useMutation({
    mutationFn: ({ approved }: { approved: boolean }) => timesheetsApi.review(timesheet.id, { approved, notes }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['timesheets-pending'] }); qc.invalidateQueries({ queryKey: ['timesheets-team'] }); qc.invalidateQueries({ queryKey: ['timesheets-mine'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={t('timesheets.modal_revisar', { persona: timesheet.user_name ?? '', semana: timesheet.week_start })} onClose={onClose} width={480}>
      <div className="u-mb-16">
        <div className="ts-review-kpis">
          {[
            { label: t('timesheets.horas_totales'), value: fmtHours(timesheet.total_hours) },
            { label: t('timesheets.horas_facturables_corto'), value: fmtHours(timesheet.billable_hours) },
            { label: t('timesheets.coste'), value: fmtCurrency(timesheet.total_cost) },
          ].map(({ label, value }) => (
            <div key={label} className="ts-review-kpi">
              <div className="u-text2-xs-mb4">{label}</div>
              <div className="ts-review-kpi-value">{value}</div>
            </div>
          ))}
        </div>
        <label id={`${idCampo}-etnotas`} htmlFor={`${idCampo}-notas`} className="ts-label">{t('timesheets.notas_opcional')}</label>
        <textarea id={`${idCampo}-notas`} aria-labelledby={`${idCampo}-etnotas`} value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder={t('timesheets.notas_de_revision')}
          className="ts-textarea" />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('timesheets.cancelar')}</Button>
        <Button variant="danger" onClick={() => review({ approved: false })} loading={isPending} disabled={isPending}>✕ {t('timesheets.rechazar')}</Button>
        <Button onClick={() => review({ approved: true })} loading={isPending} disabled={isPending}>✓ {t('timesheets.approve')}</Button>
      </div>
    </Modal>
  )
}

const SHEET_BORDER: Record<string, string> = {
  rejected: 'ts-sheet--rejected',
  approved: 'ts-sheet--approved',
}

export default function TimesheetsPage() {
  const t = useAppT() as T
  const toast = useToast()
  const { hasRole } = useAuth() as RoleAuth
  const qc = useQueryClient()
  const [tab, setTab] = useState<'mine' | 'pending' | 'team'>(hasRole('admin', 'pm', 'hr') ? 'team' : 'mine')
  const [viewLines, setViewLines] = useState<string | null>(null)
  const [reviewing, setReviewing] = useState<TimesheetItem | null>(null)
  const [teamSortKey, setTeamSortKey] = useState<TeamSortKey>('week_start')
  const [teamSortDir, setTeamSortDir] = useState<'asc' | 'desc'>('desc')
  const [mineStatusFilter, setMineStatusFilter] = useState('')
  const [mineFrom, setMineFrom] = useState('')
  const [mineTo, setMineTo] = useState('')
  const [pendingSearch, setPendingSearch] = useState('')
  const [pendingFrom, setPendingFrom] = useState('')
  const [pendingTo, setPendingTo] = useState('')
  const [teamSearch, setTeamSearch] = useState('')
  const [teamStatusFilter, setTeamStatusFilter] = useState('')
  const [teamFrom, setTeamFrom] = useState('')
  const [teamTo, setTeamTo] = useState('')
  const [pendingPage, setPendingPage] = useState(1)
  const [teamPage, setTeamPage] = useState(1)
  // El texto va al servidor: se espera a que se deje de escribir.
  const pendingQ = useValorConRetardo(pendingSearch.trim())
  const teamQ = useValorConRetardo(teamSearch.trim())

  const toggleTeamSort = (key: TeamSortKey) => {
    if (teamSortKey === key) setTeamSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setTeamSortKey(key); setTeamSortDir('asc') }
    setTeamPage(1)
  }
  const teamSortIcon = (key: TeamSortKey) => teamSortKey === key ? (teamSortDir === 'asc' ? ' ↑' : ' ↓') : ''

  const { data: mySheets = [], isLoading: loadingMine } = useQuery<TimesheetItem[]>({
    queryKey: ['timesheets-mine'],
    queryFn: () => timesheetsApi.my().then(r => r.data),
  })

  // Pendientes y equipo se filtran, ordenan y paginan en el servidor: el total es el de todo
  // lo filtrado, no el de la pagina.
  const pendingParams: FiltroDeTimesheets = {
    q: pendingQ || undefined, date_from: pendingFrom || undefined, date_to: pendingTo || undefined,
    page: pendingPage, page_size: DEFAULT_PAGE_SIZE,
  }
  const { data: pendingData, isLoading: loadingPending } = useQuery({
    queryKey: ['timesheets-pending', pendingParams],
    queryFn: () => timesheetsApi.pending(pendingParams).then(r => ({ items: r.data ?? [], total: r.meta?.total ?? r.data?.length ?? 0 })),
    enabled: hasRole('admin', 'pm', 'hr'),
    placeholderData: keepPreviousData,
  })
  const pending: TimesheetItem[] = pendingData?.items ?? []
  const pendingTotal = pendingData?.total ?? 0
  const pendingFiltered = !!(pendingQ || pendingFrom || pendingTo)

  const teamParams: FiltroDeTimesheetsDelEquipo = {
    q: teamQ || undefined, status: teamStatusFilter || undefined,
    date_from: teamFrom || undefined, date_to: teamTo || undefined,
    sort: teamSortKey, direction: teamSortDir,
    page: teamPage, page_size: DEFAULT_PAGE_SIZE,
  }
  const { data: teamData, isLoading: loadingTeam } = useQuery({
    queryKey: ['timesheets-team', teamParams],
    queryFn: () => timesheetsApi.team(teamParams).then(r => ({ items: r.data ?? [], total: r.meta?.total ?? r.data?.length ?? 0 })),
    enabled: hasRole('admin', 'pm', 'hr'),
    placeholderData: keepPreviousData,
  })
  const teamSheets: TimesheetItem[] = teamData?.items ?? []
  const teamTotal = teamData?.total ?? 0
  const teamFiltered = !!(teamQ || teamStatusFilter || teamFrom || teamTo)
  const totalPaginas = (total: number) => Math.max(1, Math.ceil(total / DEFAULT_PAGE_SIZE))

  const { mutate: submit, isPending: submitting } = useMutation({
    mutationFn: (weekStart: string) => timesheetsApi.submit(weekStart),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['timesheets-mine'] }); qc.invalidateQueries({ queryKey: ['timesheets-pending'] }); qc.invalidateQueries({ queryKey: ['dash-hours-week'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const dateInRange = (value?: string, from?: string, to?: string) => {
    if (!value) return true
    if (from && value < from) return false
    if (to && value > to) return false
    return true
  }

  const filteredMine = mySheets.filter((ts) => {
    if (mineStatusFilter && ts.status !== mineStatusFilter) return false
    if (!dateInRange(ts.week_start, mineFrom, mineTo)) return false
    return true
  })

  const tabs = [
    { id: 'mine', label: t('timesheets.tab_mios') },
    ...(hasRole('admin', 'pm', 'hr') ? [
      { id: 'pending', label: `⏳ ${t('timesheets.tab_pendientes', { n: pendingTotal })}` },
      { id: 'team', label: t('timesheets.tab_equipo') },
    ] : []),
  ]

  const statusOptions = STATUS_IDS.map(id => <option key={id} value={id}>{t(STATUS_CFG[id].labelKey)}</option>)

  const teamColumns: Array<[TeamSortKey, string]> = [
    ['user_name', t('timesheets.col_persona')],
    ['week_start', t('timesheets.col_semana')],
    ['total_hours', t('timesheets.total')],
    ['billable_hours', t('timesheets.col_facturables')],
    ['total_cost', t('timesheets.coste')],
    ['status', t('timesheets.status')],
  ]

  return (
    <PageShell>
      <PageHeader icon={<Clock size={18} />} title={t('timesheets.title')} subtitle={t('timesheets.subtitle')} showListExport={true} exportTargetSelector='[data-export-table="timesheets-list"]' exportFilePrefix="timesheets" />

      <Tabs
        items={tabs}
        active={tab}
        onChange={(id: string) => setTab(id as 'mine' | 'pending' | 'team')}
        className="ts-tabs"
      />

      {tab === 'mine' && (
        <div>
          {loadingMine ? <Spinner /> : mySheets.length === 0 ? (
            <EmptyState icon="📋" title={t('timesheets.no_timesheets')} description={t('timesheets.vacio_mios')} />
          ) : (
            <div data-export-table="timesheets-list" className="u-stack-10">
              <div className="u-wrap-center-8">
                <select value={mineStatusFilter} onChange={e => setMineStatusFilter(e.target.value)} aria-label={t('timesheets.status')} className="ts-control">
                  <option value="">{t('timesheets.estado_todos')}</option>
                  {statusOptions}
                </select>
                <DateInput value={mineFrom} onChange={e => setMineFrom(e.target.value)} aria-label={t('timesheets.semana_desde')} className="ts-control" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={mineTo} onChange={e => setMineTo(e.target.value)} aria-label={t('timesheets.semana_hasta')} className="ts-control" />
                {(mineStatusFilter || mineFrom || mineTo) && (
                  <button type="button" onClick={() => { setMineStatusFilter(''); setMineFrom(''); setMineTo('') }} className="ts-clear">
                    {t('timesheets.limpiar')}
                  </button>
                )}
                <span className="ts-count">{filteredMine.length} / {mySheets.length}</span>
              </div>
              {filteredMine.length === 0 ? (
                <EmptyState icon="🔍" title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_mios')} />
              ) : filteredMine.map(ts => (
                <div key={ts.week_start} className={`ts-sheet ${SHEET_BORDER[ts.status] ?? ''}`}>
                  <div className="u-flex1">
                    <div className="ts-sheet-title">
                      {t('timesheets.semana_rango', { desde: fmtDate(ts.week_start), hasta: fmtDate(ts.week_end) })}
                    </div>
                    <div className="ts-sheet-meta">
                      <span>{t('timesheets.total')}: <span className="ts-strong">{fmtHours(ts.total_hours)}</span></span>
                      <span>{t('timesheets.facturables')}: <span className="u-accent">{fmtHours(ts.billable_hours)}</span></span>
                      {(ts.total_cost ?? 0) > 0 && <span>{t('timesheets.coste')}: <span className="u-warning">{fmtCurrency(ts.total_cost)}</span></span>}
                    </div>
                    {ts.review_notes && ts.status === 'rejected' && (
                      <div className="ts-reject-note">
                        💬 {ts.review_notes}
                      </div>
                    )}
                  </div>
                  <StatusBadge status={ts.status} />
                  <div className="u-row-8">
                    <button type="button" onClick={() => setViewLines(ts.week_start)} className="ts-btn-ghost">{t('timesheets.ver_lineas')}</button>
                    {(ts.status === 'draft' || ts.status === 'rejected') && (ts.total_hours ?? 0) > 0 && (
                      <Button size="sm" onClick={() => submit(ts.week_start)} loading={submitting}>{t('timesheets.enviar')}</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'pending' && (
        <div>
          {loadingPending ? <Spinner /> : pendingTotal === 0 && !pendingFiltered ? (
            <EmptyState icon="✅" title={t('timesheets.sin_pendientes')} description={t('timesheets.vacio_pendientes')} />
          ) : (
            <div className="u-stack-10">
              <div className="u-wrap-center-8">
                <input value={pendingSearch} onChange={e => { setPendingSearch(e.target.value); setPendingPage(1) }} placeholder={t('timesheets.buscar_placeholder')} aria-label={t('timesheets.buscar_pendientes')} className="ts-control ts-search" />
                <DateInput value={pendingFrom} onChange={e => { setPendingFrom(e.target.value); setPendingPage(1) }} aria-label={t('timesheets.pendientes_desde')} className="ts-control" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={pendingTo} onChange={e => { setPendingTo(e.target.value); setPendingPage(1) }} aria-label={t('timesheets.pendientes_hasta')} className="ts-control" />
                {(pendingSearch || pendingFrom || pendingTo) && (
                  <button type="button" onClick={() => { setPendingSearch(''); setPendingFrom(''); setPendingTo(''); setPendingPage(1) }} className="ts-clear">
                    {t('timesheets.limpiar')}
                  </button>
                )}
                <span className="ts-count" role="status">{t('timesheets.n_registros', { n: pendingTotal })}</span>
              </div>
              {pending.length === 0 ? (
                <EmptyState icon="🔍" title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_pendientes')} />
              ) : pending.map(ts => (
                <div key={ts.id} className="ts-sheet ts-sheet--pending-review">
                  <div className="u-flex1">
                    <div className="u-md-700">{ts.user_name}</div>
                    <div className="u-text2-sm-mt2">
                      {t('timesheets.semana_del_fecha', { fecha: fmtDate(ts.week_start) })} · {fmtHours(ts.total_hours)} · {t('timesheets.n_facturables', { horas: fmtHours(ts.billable_hours) })}
                    </div>
                  </div>
                  <StatusBadge status={ts.status} />
                  <Button size="sm" onClick={() => setReviewing(ts)}>{t('timesheets.revisar')}</Button>
                </div>
              ))}
              <Pagination page={pendingPage} totalPages={totalPaginas(pendingTotal)} onChange={setPendingPage}
                total={pendingTotal} pageSize={DEFAULT_PAGE_SIZE} />
            </div>
          )}
        </div>
      )}

      {tab === 'team' && (
        <div>
          {loadingTeam ? <Spinner /> : teamTotal === 0 && !teamFiltered ? (
            <EmptyState icon="👥" title={t('timesheets.sin_timesheets_de_equipo')} description={t('timesheets.vacio_equipo')} />
          ) : (
            <div className="u-stack-10">
              <div className="u-wrap-center-8">
                <input value={teamSearch} onChange={e => { setTeamSearch(e.target.value); setTeamPage(1) }} placeholder={t('timesheets.buscar_placeholder')} aria-label={t('timesheets.buscar_equipo')} className="ts-control ts-search" />
                <select value={teamStatusFilter} onChange={e => { setTeamStatusFilter(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.status')} className="ts-control">
                  <option value="">{t('timesheets.estado_todos')}</option>
                  {statusOptions}
                </select>
                <DateInput value={teamFrom} onChange={e => { setTeamFrom(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.equipo_desde')} className="ts-control" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={teamTo} onChange={e => { setTeamTo(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.equipo_hasta')} className="ts-control" />
                {(teamSearch || teamStatusFilter || teamFrom || teamTo) && (
                  <button type="button" onClick={() => { setTeamSearch(''); setTeamStatusFilter(''); setTeamFrom(''); setTeamTo(''); setTeamPage(1) }} className="ts-clear">
                    {t('timesheets.limpiar')}
                  </button>
                )}
                <span className="ts-count" role="status">{t('timesheets.n_registros', { n: teamTotal })}</span>
              </div>
              {teamSheets.length === 0 ? (
                <EmptyState icon="🔍" title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_equipo')} />
              ) : (
            <div className="ds-card ds-card--plano">
              <div className="ts-team-grid ts-team-head">
                {teamColumns.map(([key, label]) => (
                  <button key={key} type="button" onClick={() => toggleTeamSort(key)}
                    onKeyDown={e => onKeyboardActivate(e, () => toggleTeamSort(key))}
                    aria-pressed={teamSortKey === key}
                    className={`ts-sort${teamSortKey === key ? ' ts-sort--active' : ''}`}>
                    {label}{teamSortIcon(key)}
                  </button>
                ))}
                <span></span>
              </div>
              {teamSheets.map(ts => (
                <div key={ts.id} className="ts-team-grid">
                  <span className="u-base-600">{ts.user_name}</span>
                  <span className="u-text2-sm">{fmtDate(ts.week_start)}</span>
                  <span className="ts-num">{fmtHours(ts.total_hours)}</span>
                  <span className="ts-num ts-num--accent">{fmtHours(ts.billable_hours)}</span>
                  <span className="ts-num ts-num--warning">{fmtCurrency(ts.total_cost)}</span>
                  <StatusBadge status={ts.status} />
                  {ts.status === 'submitted' && <Button size="sm" onClick={() => setReviewing(ts)}>{t('timesheets.revisar')}</Button>}
                </div>
              ))}
            </div>
              )}
              <Pagination page={teamPage} totalPages={totalPaginas(teamTotal)} onChange={setTeamPage}
                total={teamTotal} pageSize={DEFAULT_PAGE_SIZE} />
            </div>
          )}
        </div>
      )}

      {viewLines && <WeekLines weekStart={viewLines} onClose={() => setViewLines(null)} />}
      {reviewing && <ReviewModal timesheet={reviewing} onClose={() => setReviewing(null)} />}
    </PageShell>
  )
}
