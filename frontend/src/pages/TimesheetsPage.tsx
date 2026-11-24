import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { timesheetsApi, imputationsApi } from '../services/api'
import type { FiltroDeTimesheets, FiltroDeTimesheetsDelEquipo } from '../services/api'
import type { EstadoDeTimesheet, LineaDeTimesheet, Timesheet } from '../services/api/tipos-personas'
import { Buscador, Button, IconButton, Modal, Spinner, EmptyState, Tabs, SortableTH, ariaSort, Select, TablaSimple, Textarea, Input } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Clock, Hourglass, ClipboardList, Search, CircleCheck, Users, Pencil, Trash2, Check, X, MessageSquare } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fmtHours, fmtCurrency, fmtDate, extractErr } from '../utils/helpers'
import { HORAS_MAXIMAS_POR_DIA } from '../utils/umbrales'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import DsBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import Pagination from '../components/ui/Pagination'
import { DEFAULT_PAGE_SIZE } from '../constants/pagination'
import { useValorConRetardo } from '../hooks/useValorConRetardo'
import './TimesheetsPage.css'

type TimesheetStatus = EstadoDeTimesheet
type TimesheetItem = Timesheet
type TimesheetLine = LineaDeTimesheet

type TeamSortKey = 'user_name' | 'week_start' | 'total_hours' | 'billable_hours' | 'total_cost' | 'status'

type T = (key: string, params?: Record<string, string | number>) => string

const STATUS_CFG: Record<string, { labelKey: string; kind: StatusBadgeKind }> = {
  draft:     { labelKey: 'timesheets.estado_borrador', kind: 'neutral' },
  submitted: { labelKey: 'timesheets.submitted', kind: 'warning' },
  approved:  { labelKey: 'timesheets.approved', kind: 'success' },
  rejected:  { labelKey: 'timesheets.rejected', kind: 'danger' },
}
const TEAM_NUM = new Set<string>(['total_hours', 'billable_hours', 'total_cost'])
const STATUS_IDS = ['draft', 'submitted', 'approved', 'rejected'] as const

function StatusBadge({ status }: { status: TimesheetStatus }) {
  const t = useAppT() as T
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft
  return (
    <DsBadge kind={cfg.kind} caps={false} className="ts-status">{t(cfg.labelKey)}</DsBadge>
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
        <EmptyState icon={<Clock size={28} />} title={t('timesheets.sin_imputaciones')} description={t('timesheets.sin_lineas_semana')} />
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
                      <Input type="number" min="0.25" max={HORAS_MAXIMAS_POR_DIA} step="0.25"
                        aria-label={t('timesheets.horas')}
                        value={editForm.hours}
                        onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                        inputClassName="ts-line-input--hours" />
                      <span className="u-text2-sm">h</span>
                      <Input value={editForm.description}
                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                        placeholder={t('timesheets.descripcion_del_trabajo')}
                        aria-label={t('timesheets.descripcion_del_trabajo')} inputClassName="ts-line-input--desc" />
                      <Button size="sm" icon={<Check size={14} />} onClick={() => updateLine({ id: l.id, data: { hours: editForm.hours, description: editForm.description } })}
                        loading={updating} disabled={updating || editForm.hours <= 0}>
                        {t('timesheets.guardar')}
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setEditingId(null)}>
                        {t('timesheets.cancelar')}
                      </Button>
                    </div>
                  ) : (
                    /* ── Vista normal ── */
                    <div className="ts-line-view">
                      <span className="ts-line-hours">{fmtHours(l.hours)}</span>
                      <div className="u-flex1-min0">
                        <div className="u-base-600">{l.project_name}</div>
                        {l.description && <div className="ts-line-desc">{l.description}</div>}
                      </div>
                      <div className="ts-line-actions">
                        {l.billable && <span className="ts-tag ts-tag--billable">{t('timesheets.facturable')}</span>}
                        {l.is_approved && <span className="ts-tag ts-tag--approved"><Check size={12} aria-hidden="true" /> {t('timesheets.approved')}</span>}
                        {!l.is_approved && (
                          <>
                            <IconButton variante="caja" ariaLabel={t('timesheets.editar_linea')}
                              onClick={() => { setEditingId(l.id); setEditForm({ hours: l.hours, description: l.description || '' }) }}>
                              <Pencil size={14} />
                            </IconButton>
                            <IconButton variante="caja" tono="peligro" ariaLabel={t('timesheets.eliminar_linea')}
                              onClick={() => { openConfirmGlobal({ message: t('timesheets.confirmar_eliminar'), onConfirm: () => deleteLine(l.id), danger: true }) }}>
                              <Trash2 size={14} />
                            </IconButton>
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
              {fmtHours(lines.reduce((s, l) => s + l.hours, 0))}</span>
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
        <Textarea label={t('timesheets.notas_opcional')} id={`${idCampo}-notas`} value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder={t('timesheets.notas_de_revision')} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('timesheets.cancelar')}</Button>
        <Button variant="danger" onClick={() => review({ approved: false })} icon={<X size={14} />} loading={isPending} disabled={isPending}>{t('timesheets.rechazar')}</Button>
        <Button onClick={() => review({ approved: true })} icon={<Check size={14} />} loading={isPending} disabled={isPending}>{t('timesheets.approve')}</Button>
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
  const { puede } = useAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'mine' | 'pending' | 'team'>(puede('partes.equipo') ? 'team' : 'mine')
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

  const toggleTeamSort = (key: string) => {
    if (teamSortKey === key) setTeamSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setTeamSortKey(key as TeamSortKey); setTeamSortDir('asc') }
    setTeamPage(1)
  }
  const teamSort = { key: teamSortKey, dir: teamSortDir }

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
    enabled: puede('partes.equipo'),
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
    enabled: puede('partes.equipo'),
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
    ...(puede('partes.equipo') ? [
      { id: 'pending', label: t('timesheets.tab_pendientes', { n: pendingTotal }), icon: <Hourglass size={14} /> },
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
            <EmptyState icon={<ClipboardList size={28} />} title={t('timesheets.no_timesheets')} description={t('timesheets.vacio_mios')} />
          ) : (
            <div data-export-table="timesheets-list" className="u-stack-10">
              <div className="ds-toolbar ts-toolbar">
                <Select suelto placeholder={false} value={mineStatusFilter} onChange={e => setMineStatusFilter(e.target.value)} aria-label={t('timesheets.status')}>
                  <option value="">{t('timesheets.estado_todos')}</option>
                  {statusOptions}
                </Select>
                <DateInput value={mineFrom} onChange={e => setMineFrom(e.target.value)} aria-label={t('timesheets.semana_desde')} className="ds-input" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={mineTo} onChange={e => setMineTo(e.target.value)} aria-label={t('timesheets.semana_hasta')} className="ds-input" />
                {(mineStatusFilter || mineFrom || mineTo) && (
                  <Button variant="ghost" size="md" onClick={() => { setMineStatusFilter(''); setMineFrom(''); setMineTo('') }}>{t('timesheets.limpiar')}</Button>
                )}
                <span className="ts-count">{filteredMine.length} / {mySheets.length}</span>
              </div>
              {filteredMine.length === 0 ? (
                <EmptyState icon={<Search size={28} />} title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_mios')} />
              ) : filteredMine.map(ts => (
                <div key={ts.week_start} className={`ts-sheet ${SHEET_BORDER[ts.status] ?? ''}`}>
                  <div className="u-flex1">
                    <div className="ts-sheet-title">
                      {t('timesheets.semana_rango', { desde: fmtDate(ts.week_start), hasta: fmtDate(ts.week_end) })}
                    </div>
                    <div className="ts-sheet-meta">
                      <span>{t('timesheets.total')}: <span className="ts-strong">{fmtHours(ts.total_hours)}</span></span>
                      <span>{t('timesheets.facturables')}: <span className="ts-strong">{fmtHours(ts.billable_hours)}</span></span>
                      {(ts.total_cost ?? 0) > 0 && <span>{t('timesheets.coste')}: <span className="ts-strong">{fmtCurrency(ts.total_cost)}</span></span>}
                    </div>
                    {ts.review_notes && ts.status === 'rejected' && (
                      <div className="ts-reject-note">
                        <MessageSquare size={14} aria-hidden="true" /> {ts.review_notes}
                      </div>
                    )}
                  </div>
                  <StatusBadge status={ts.status} />
                  <div className="u-row-8">
                    <Button variant="ghost" size="sm" onClick={() => setViewLines(ts.week_start)}>{t('timesheets.ver_lineas')}</Button>
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
            <EmptyState icon={<CircleCheck size={28} />} title={t('timesheets.sin_pendientes')} description={t('timesheets.vacio_pendientes')} />
          ) : (
            <div className="u-stack-10">
              <div className="ds-toolbar ts-toolbar">
                <Buscador value={pendingSearch} onChange={v => { setPendingSearch(v); setPendingPage(1) }} placeholder={t('timesheets.buscar_placeholder')} aria-label={t('timesheets.buscar_pendientes')} className="ts-search" />
                <DateInput value={pendingFrom} onChange={e => { setPendingFrom(e.target.value); setPendingPage(1) }} aria-label={t('timesheets.pendientes_desde')} className="ds-input" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={pendingTo} onChange={e => { setPendingTo(e.target.value); setPendingPage(1) }} aria-label={t('timesheets.pendientes_hasta')} className="ds-input" />
                {(pendingSearch || pendingFrom || pendingTo) && (
                  <Button variant="ghost" size="md" onClick={() => { setPendingSearch(''); setPendingFrom(''); setPendingTo(''); setPendingPage(1) }}>{t('timesheets.limpiar')}</Button>
                )}
                <span className="ts-count" role="status">{t('timesheets.n_registros', { n: pendingTotal })}</span>
              </div>
              {pending.length === 0 ? (
                <EmptyState icon={<Search size={28} />} title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_pendientes')} />
              ) : (
                <div className="ds-card ds-card--plano ts-table-wrap">
                  <TablaSimple claseTabla="ts-table">
                    <thead>
                      <tr>
                        <th>{t('timesheets.col_persona')}</th>
                        <th>{t('timesheets.col_semana')}</th>
                        <th className="ts-th-num">{t('timesheets.total')}</th>
                        <th className="ts-th-num">{t('timesheets.col_facturables')}</th>
                        <th>{t('timesheets.status')}</th>
                        <th><span className="ts-sr-only">{t('timesheets.revisar')}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {pending.map(ts => (
                        <tr key={ts.id}>
                          <td className="ts-strong">{ts.user_name}</td>
                          <td>{fmtDate(ts.week_start)}</td>
                          <td className="ts-num">{fmtHours(ts.total_hours)}</td>
                          <td className="ts-num">{fmtHours(ts.billable_hours)}</td>
                          <td><StatusBadge status={ts.status} /></td>
                          <td className="ts-td-action"><Button size="sm" onClick={() => setReviewing(ts)}>{t('timesheets.revisar')}</Button></td>
                        </tr>
                      ))}
                    </tbody>
                  </TablaSimple>
                </div>
              )}
              <Pagination page={pendingPage} totalPages={totalPaginas(pendingTotal)} onChange={setPendingPage}
                total={pendingTotal} pageSize={DEFAULT_PAGE_SIZE} />
            </div>
          )}
        </div>
      )}

      {tab === 'team' && (
        <div>
          {loadingTeam ? <Spinner /> : teamTotal === 0 && !teamFiltered ? (
            <EmptyState icon={<Users size={28} />} title={t('timesheets.sin_timesheets_de_equipo')} description={t('timesheets.vacio_equipo')} />
          ) : (
            <div className="u-stack-10">
              <div className="ds-toolbar ts-toolbar">
                <Buscador value={teamSearch} onChange={v => { setTeamSearch(v); setTeamPage(1) }} placeholder={t('timesheets.buscar_placeholder')} aria-label={t('timesheets.buscar_equipo')} className="ts-search" />
                <Select suelto placeholder={false} value={teamStatusFilter} onChange={e => { setTeamStatusFilter(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.status')}>
                  <option value="">{t('timesheets.estado_todos')}</option>
                  {statusOptions}
                </Select>
                <DateInput value={teamFrom} onChange={e => { setTeamFrom(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.equipo_desde')} className="ds-input" />
                <span className="u-text3" aria-hidden="true">—</span>
                <DateInput value={teamTo} onChange={e => { setTeamTo(e.target.value); setTeamPage(1) }} aria-label={t('timesheets.equipo_hasta')} className="ds-input" />
                {(teamSearch || teamStatusFilter || teamFrom || teamTo) && (
                  <Button variant="ghost" size="md" onClick={() => { setTeamSearch(''); setTeamStatusFilter(''); setTeamFrom(''); setTeamTo(''); setTeamPage(1) }}>{t('timesheets.limpiar')}</Button>
                )}
                <span className="ts-count" role="status">{t('timesheets.n_registros', { n: teamTotal })}</span>
              </div>
              {teamSheets.length === 0 ? (
                <EmptyState icon={<Search size={28} />} title={t('timesheets.sin_resultados')} description={t('timesheets.sin_coincidencias_equipo')} />
              ) : (
                <div className="ds-card ds-card--plano ts-table-wrap">
                  <TablaSimple claseTabla="ts-table">
                    <thead>
                      <tr>
                        {teamColumns.map(([key, label]) => (
                          <th key={key} aria-sort={ariaSort(teamSort, key)} className={TEAM_NUM.has(key) ? 'ts-th-num' : undefined}>
                            <SortableTH col={key} sort={teamSort} onSort={toggleTeamSort} align={TEAM_NUM.has(key) ? 'right' : 'left'}>{label}</SortableTH>
                          </th>
                        ))}
                        <th><span className="ts-sr-only">{t('timesheets.revisar')}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {teamSheets.map(ts => (
                        <tr key={ts.id}>
                          <td className="ts-strong">{ts.user_name}</td>
                          <td>{fmtDate(ts.week_start)}</td>
                          <td className="ts-num">{fmtHours(ts.total_hours)}</td>
                          <td className="ts-num">{fmtHours(ts.billable_hours)}</td>
                          <td className="ts-num">{fmtCurrency(ts.total_cost)}</td>
                          <td><StatusBadge status={ts.status} /></td>
                          <td className="ts-td-action">
                            {ts.status === 'submitted' && <Button size="sm" onClick={() => setReviewing(ts)}>{t('timesheets.revisar')}</Button>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </TablaSimple>
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
