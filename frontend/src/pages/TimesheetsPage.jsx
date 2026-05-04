import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { timesheetsApi, imputationsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Clock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { fmtHours, fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_CFG = {
  draft:     { label: 'Borrador',  color: 'var(--text-2)', bg: 'rgba(120,138,170,0.09)', border: 'rgba(122,138,170,0.19)' },
  submitted: { label: 'Enviado',   color: 'var(--warning)', bg: 'var(--warning-bg)', border: 'var(--warning-border)' },
  approved:  { label: 'Aprobado',  color: 'var(--success)', bg: 'var(--success-bg)', border: 'var(--success-border)' },
  rejected:  { label: 'Rechazado', color: 'var(--danger)', bg: 'var(--danger-bg)', border: 'var(--danger-border)' },
}

function onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft
  return (
    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
      {cfg.label}
    </span>
  )
}

function WeekLines({ weekStart, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ hours: 0, description: '' })

  const { data: lines = [], isLoading } = useQuery({
    queryKey: ['timesheet-lines', weekStart],
    queryFn: () => timesheetsApi.weekLines(weekStart).then(r => r.data),
  })

  const { mutate: updateLine, isPending: updating } = useMutation({
    mutationFn: ({ id, data }) => imputationsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['timesheet-lines', weekStart] }); setEditingId(null) },
    onError: e => toast.error(e?.response?.data?.detail || 'Error al actualizar'),
  })

  const { mutate: deleteLine } = useMutation({
    mutationFn: (id) => imputationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timesheet-lines', weekStart] }),
    onError: e => toast.error(e?.response?.data?.detail || 'Error al eliminar'),
  })

  const byDay = lines.reduce((a, l) => { const d = l.date; if (!a[d]) a[d] = []; a[d].push(l); return a }, {})
  const IS = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 6,
    padding: '5px 9px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }

  return (
    <Modal open title={`Semana ${weekStart}`} onClose={onClose} width={660}>
      {isLoading ? <Spinner /> : lines.length === 0 ? (
        <EmptyState icon="⏱️" title="Sin imputaciones" description="No hay lineas registradas para esta semana" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Object.entries(byDay).sort().map(([day, dayLines]) => (
            <div key={day}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase',
                letterSpacing: '0.06em', marginBottom: 6, paddingBottom: 4,
                borderBottom: '1px solid var(--surface-4)' }}>{fmtDate(day)}</div>
              {dayLines.map(l => (
                <div key={l.id} style={{ marginBottom: 4 }}>
                  {editingId === l.id ? (
                    /* ── Modo edición inline ── */
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                      background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
                      borderRadius: 8 }}>
                      <input type="number" min="0.25" max="24" step="0.25"
                        value={editForm.hours}
                        onChange={e => setEditForm(f => ({ ...f, hours: parseFloat(e.target.value) || 0 }))}
                        style={{ ...IS, width: 65 }} />
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>h</span>
                      <input value={editForm.description}
                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                        placeholder="Descripcion del trabajo"
                        aria-label="Descripcion del trabajo"
                        style={{ ...IS, flex: 1 }} />
                      <button onClick={() => updateLine({ id: l.id, data: { hours: editForm.hours, description: editForm.description } })}
                        disabled={updating || editForm.hours <= 0}
                        style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '5px 12px',
                          color: '#fff', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        {updating ? '...' : '✓ Guardar'}
                      </button>
                      <button onClick={() => setEditingId(null)}
                        style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6,
                          padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                        Cancelar
                      </button>
                    </div>
                  ) : (
                    /* ── Vista normal ── */
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px',
                      background: 'var(--surface-3)', borderRadius: 8 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)',
                        fontWeight: 700, width: 38, flexShrink: 0 }}>{l.hours}h</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{l.project_name}</div>
                        {l.description && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.description}</div>}
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
                        {l.is_billable && <span style={{ fontSize: "var(--text-2xs)", background: 'var(--success-bg)', color: 'var(--success)',
                          border: '1px solid var(--success-border)', borderRadius: 20, padding: '1px 7px' }}>Facturable</span>}
                        {l.is_approved && <span style={{ fontSize: "var(--text-2xs)", background: 'var(--accent-muted)', color: 'var(--accent)',
                          border: '1px solid var(--accent-border)', borderRadius: 20, padding: '1px 7px' }}>✓ Aprobado</span>}
                        {!l.is_approved && (
                          <>
                            <button onClick={() => { setEditingId(l.id); setEditForm({ hours: l.hours, description: l.description || '' }) }}
                              style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5,
                                padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                              ✏
                            </button>
                            <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta imputación?', onConfirm: () => deleteLine(l.id), danger: true }) }}
                              style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 5,
                                padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                              🗑
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
          <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12,
            display: 'flex', justifyContent: 'flex-end', fontSize: "var(--text-md)", fontWeight: 700 }}>
            Total: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginLeft: 8 }}>
              {lines.reduce((s, l) => s + l.hours, 0).toFixed(1)}h</span>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ReviewModal({ timesheet, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const [notes, setNotes] = useState('')
  const { mutate: review, isPending } = useMutation({
    mutationFn: ({ approved }) => timesheetsApi.review(timesheet.id, { approved, notes }),
    onSuccess: () => { qc.invalidateQueries(['timesheets-pending']); qc.invalidateQueries(['timesheets-team']); qc.invalidateQueries(['timesheets-mine']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open title={`Revisar: ${timesheet.user_name} · semana ${timesheet.week_start}`} onClose={onClose} width={480}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
          {[
            { label: 'Horas totales', value: fmtHours(timesheet.total_hours) },
            { label: 'H. facturables', value: fmtHours(timesheet.billable_hours) },
            { label: 'Coste', value: fmtCurrency(timesheet.total_cost) },
          ].map(({ label, value }) => (
            <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{value}</div>
            </div>
          ))}
        </div>
        <label style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Notas (opcional)</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder="Notas de revision" aria-label="Notas de revision"
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button variant="danger" onClick={() => review({ approved: false })} loading={isPending} disabled={isPending}>✕ Rechazar</Button>
        <Button onClick={() => review({ approved: true })} loading={isPending} disabled={isPending}>✓ Aprobar</Button>
      </div>
    </Modal>
  )
}

export default function TimesheetsPage() {
  const t = useAppT()
  const toast = useToast()
  const { _user, hasRole } = useAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState(hasRole('admin', 'pm', 'hr') ? 'team' : 'mine')
  const [viewLines, setViewLines] = useState(null)
  const [reviewing, setReviewing] = useState(null)
  const [teamSortKey, setTeamSortKey] = useState('week_start')
  const [teamSortDir, setTeamSortDir] = useState('desc')
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

  const toggleTeamSort = (key) => {
    if (teamSortKey === key) setTeamSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setTeamSortKey(key); setTeamSortDir('asc') }
  }
  const teamSortIcon = (key) => teamSortKey === key ? (teamSortDir === 'asc' ? ' ↑' : ' ↓') : ''

  const { data: mySheets = [], isLoading: loadingMine } = useQuery({
    queryKey: ['timesheets-mine'],
    queryFn: () => timesheetsApi.my().then(r => r.data),
  })

  const { data: pending = [], isLoading: loadingPending } = useQuery({
    queryKey: ['timesheets-pending'],
    queryFn: () => timesheetsApi.pending().then(r => r.data),
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  const { data: teamSheets = [], isLoading: loadingTeam } = useQuery({
    queryKey: ['timesheets-team'],
    queryFn: () => timesheetsApi.team().then(r => r.data),
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  const { mutate: submit, isPending: submitting } = useMutation({
    mutationFn: (weekStart) => timesheetsApi.submit(weekStart),
    onSuccess: () => { qc.invalidateQueries(['timesheets-mine']); qc.invalidateQueries(['timesheets-pending']); qc.invalidateQueries(['dash-hours-week']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const dateInRange = (value, from, to) => {
    if (!value) return true
    if (from && value < from) return false
    if (to && value > to) return false
    return true
  }

  const filteredMine = mySheets.filter(ts => {
    if (mineStatusFilter && ts.status !== mineStatusFilter) return false
    if (!dateInRange(ts.week_start, mineFrom, mineTo)) return false
    return true
  })

  const filteredPending = pending.filter(ts => {
    if (pendingSearch) {
      const q = pendingSearch.toLowerCase()
      const haystack = `${ts.user_name || ''} ${ts.week_start || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    if (!dateInRange(ts.week_start, pendingFrom, pendingTo)) return false
    return true
  })

  const filteredTeam = teamSheets.filter(ts => {
    if (teamSearch) {
      const q = teamSearch.toLowerCase()
      const haystack = `${ts.user_name || ''} ${ts.week_start || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    if (teamStatusFilter && ts.status !== teamStatusFilter) return false
    if (!dateInRange(ts.week_start, teamFrom, teamTo)) return false
    return true
  })

  const tabs = [
    { id: 'mine', label: 'Mis timesheets' },
    ...(hasRole('admin', 'pm', 'hr') ? [
      { id: 'pending', label: `⏳ Pendientes (${pending.length})` },
      { id: 'team', label: 'Equipo' },
    ] : []),
  ]

  return (
    <PageShell>
      <PageHeader icon={<Clock size={18} />} title={t('timesheets.title')} subtitle={t('timesheets.subtitle')} />

      <Tabs
        items={tabs}
        active={tab}
        onChange={setTab}
        style={{ marginBottom: 20, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />

      {tab === 'mine' && (
        <div>
          {loadingMine ? <Spinner /> : mySheets.length === 0 ? (
            <EmptyState icon="📋" title="Sin timesheets" description="Aun no has generado ningun parte semanal" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <select value={mineStatusFilter} onChange={e => setMineStatusFilter(e.target.value)} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }}>
                  <option value="">Estado: todos</option>
                  <option value="draft">Borrador</option>
                  <option value="submitted">Enviado</option>
                  <option value="approved">Aprobado</option>
                  <option value="rejected">Rechazado</option>
                </select>
                <input type="date" value={mineFrom} onChange={e => setMineFrom(e.target.value)} aria-label="Semana desde" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                <span style={{ color: 'var(--text-3)' }}>—</span>
                <input type="date" value={mineTo} onChange={e => setMineTo(e.target.value)} aria-label="Semana hasta" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                {(mineStatusFilter || mineFrom || mineTo) && (
                  <button onClick={() => { setMineStatusFilter(''); setMineFrom(''); setMineTo('') }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                    Limpiar
                  </button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{filteredMine.length} / {mySheets.length}</span>
              </div>
              {filteredMine.length === 0 ? (
                <EmptyState icon="🔍" title="Sin resultados" description="No hay timesheets que coincidan con los filtros" />
              ) : filteredMine.map(ts => (
                <div key={ts.week_start} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${ts.status === 'rejected' ? 'var(--danger-border)' : ts.status === 'approved' ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>
                      Semana del {fmtDate(ts.week_start)} al {fmtDate(ts.week_end)}
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                      <span>Total: <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>{fmtHours(ts.total_hours)}</span></span>
                      <span>Facturables: <span style={{ color: 'var(--accent)' }}>{fmtHours(ts.billable_hours)}</span></span>
                      {ts.total_cost > 0 && <span>Coste: <span style={{ color: 'var(--warning)' }}>{fmtCurrency(ts.total_cost)}</span></span>}
                    </div>
                    {ts.review_notes && ts.status === 'rejected' && (
                      <div style={{ marginTop: 6, fontSize: "var(--text-sm)", color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 6, padding: '4px 10px' }}>
                        💬 {ts.review_notes}
                      </div>
                    )}
                  </div>
                  <StatusBadge status={ts.status} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => setViewLines(ts.week_start)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '5px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Ver líneas</button>
                    {(ts.status === 'draft' || ts.status === 'rejected') && ts.total_hours > 0 && (
                      <Button size="sm" onClick={() => submit(ts.week_start)} loading={submitting}>Enviar</Button>
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
          {loadingPending ? <Spinner /> : pending.length === 0 ? (
            <EmptyState icon="✅" title="Sin pendientes" description="No hay timesheets pendientes de revision" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input value={pendingSearch} onChange={e => setPendingSearch(e.target.value)} placeholder="Buscar persona o semana..." aria-label="Buscar pendientes" style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 340, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                <input type="date" value={pendingFrom} onChange={e => setPendingFrom(e.target.value)} aria-label="Pendientes desde" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                <span style={{ color: 'var(--text-3)' }}>—</span>
                <input type="date" value={pendingTo} onChange={e => setPendingTo(e.target.value)} aria-label="Pendientes hasta" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                {(pendingSearch || pendingFrom || pendingTo) && (
                  <button onClick={() => { setPendingSearch(''); setPendingFrom(''); setPendingTo('') }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                    Limpiar
                  </button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{filteredPending.length} / {pending.length}</span>
              </div>
              {filteredPending.length === 0 ? (
                <EmptyState icon="🔍" title="Sin resultados" description="No hay timesheets pendientes que coincidan con los filtros" />
              ) : filteredPending.map(ts => (
                <div key={ts.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', background: 'var(--surface-2)', border: '1px solid var(--warning-border)', borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{ts.user_name}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>
                      Semana del {fmtDate(ts.week_start)} · {fmtHours(ts.total_hours)} · {fmtHours(ts.billable_hours)} facturables
                    </div>
                  </div>
                  <StatusBadge status={ts.status} />
                  <Button size="sm" onClick={() => setReviewing(ts)}>Revisar</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'team' && (
        <div>
          {loadingTeam ? <Spinner /> : teamSheets.length === 0 ? (
            <EmptyState icon="👥" title="Sin timesheets de equipo" description="Todavia no hay partes semanales del equipo" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input value={teamSearch} onChange={e => setTeamSearch(e.target.value)} placeholder="Buscar persona o semana..." aria-label="Buscar equipo" style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 340, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                <select value={teamStatusFilter} onChange={e => setTeamStatusFilter(e.target.value)} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }}>
                  <option value="">Estado: todos</option>
                  <option value="draft">Borrador</option>
                  <option value="submitted">Enviado</option>
                  <option value="approved">Aprobado</option>
                  <option value="rejected">Rechazado</option>
                </select>
                <input type="date" value={teamFrom} onChange={e => setTeamFrom(e.target.value)} aria-label="Equipo desde" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                <span style={{ color: 'var(--text-3)' }}>—</span>
                <input type="date" value={teamTo} onChange={e => setTeamTo(e.target.value)} aria-label="Equipo hasta" style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }} />
                {(teamSearch || teamStatusFilter || teamFrom || teamTo) && (
                  <button onClick={() => { setTeamSearch(''); setTeamStatusFilter(''); setTeamFrom(''); setTeamTo('') }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>
                    Limpiar
                  </button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{filteredTeam.length} / {teamSheets.length}</span>
              </div>
              {filteredTeam.length === 0 ? (
                <EmptyState icon="🔍" title="Sin resultados" description="No hay timesheets de equipo que coincidan con los filtros" />
              ) : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 80px 80px 80px 100px 80px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                {[['user_name','Persona'],['week_start','Semana'],['total_hours','Total'],['billable_hours','Fact.'],['total_cost','Coste'],['status','Estado']].map(([key, label]) => (
                  <button key={key} type="button" onClick={() => toggleTeamSort(key)}
                    onKeyDown={e => onKeyboardActivate(e, () => toggleTeamSort(key))}
                    style={{ background: 'transparent', border: 'none', textAlign: 'left', padding: 0,
                      cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
                      color: teamSortKey === key ? 'var(--accent)' : 'var(--text-2)' }}>
                    {label}{teamSortIcon(key)}
                  </button>
                ))}
                <span></span>
              </div>
              {[...filteredTeam].sort((a, b) => {
                const va = a[teamSortKey] ?? ''
                const vb = b[teamSortKey] ?? ''
                const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb))
                return teamSortDir === 'asc' ? cmp : -cmp
              }).map(ts => (
                <div key={ts.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 80px 80px 80px 100px 80px', gap: 16, padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center' }}>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{ts.user_name}</span>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{fmtDate(ts.week_start)}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)' }}>{fmtHours(ts.total_hours)}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{fmtHours(ts.billable_hours)}</span>
                  <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{fmtCurrency(ts.total_cost)}</span>
                  <StatusBadge status={ts.status} />
                  {ts.status === 'submitted' && <Button size="sm" onClick={() => setReviewing(ts)}>Revisar</Button>}
                </div>
              ))}
            </div>
              )}
            </div>
          )}
        </div>
      )}

      {viewLines && <WeekLines weekStart={viewLines} onClose={() => setViewLines(null)} />}
      {reviewing && <ReviewModal timesheet={reviewing} onClose={() => setReviewing(null)} />}
    </PageShell>
  )
}
