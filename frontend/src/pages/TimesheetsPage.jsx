import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { timesheetsApi, imputationsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
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
    <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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
    padding: '5px 9px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }

  return (
    <Modal open title={`Semana ${weekStart}`} onClose={onClose} width={660}>
      {isLoading ? <Spinner /> : lines.length === 0 ? (
        <EmptyState icon="⏱️" title="Sin imputaciones" description="No hay lineas registradas para esta semana" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Object.entries(byDay).sort().map(([day, dayLines]) => (
            <div key={day}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase',
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
                      <span style={{ fontSize: 12, color: 'var(--text-2)' }}>h</span>
                      <input value={editForm.description}
                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                        placeholder="Descripcion del trabajo"
                        aria-label="Descripcion del trabajo"
                        style={{ ...IS, flex: 1 }} />
                      <button onClick={() => updateLine({ id: l.id, data: { hours: editForm.hours, description: editForm.description } })}
                        disabled={updating || editForm.hours <= 0}
                        style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '5px 12px',
                          color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                        {updating ? '...' : '✓ Guardar'}
                      </button>
                      <button onClick={() => setEditingId(null)}
                        style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6,
                          padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>
                        Cancelar
                      </button>
                    </div>
                  ) : (
                    /* ── Vista normal ── */
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px',
                      background: 'var(--surface-3)', borderRadius: 8 }}>
                      <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--accent)',
                        fontWeight: 700, width: 38, flexShrink: 0 }}>{l.hours}h</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{l.project_name}</div>
                        {l.description && <div style={{ fontSize: 11, color: 'var(--text-2)',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.description}</div>}
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
                        {l.is_billable && <span style={{ fontSize: 10, background: 'var(--success-bg)', color: 'var(--success)',
                          border: '1px solid #00e5a030', borderRadius: 20, padding: '1px 7px' }}>Facturable</span>}
                        {l.is_approved && <span style={{ fontSize: 10, background: 'var(--accent-muted)', color: 'var(--accent)',
                          border: '1px solid #00d4ff30', borderRadius: 20, padding: '1px 7px' }}>✓ Aprobado</span>}
                        {!l.is_approved && (
                          <>
                            <button onClick={() => { setEditingId(l.id); setEditForm({ hours: l.hours, description: l.description || '' }) }}
                              style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5,
                                padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                              ✏
                            </button>
                            <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta imputación?', onConfirm: () => deleteLine(l.id), danger: true }) }}
                              style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 5,
                                padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
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
            display: 'flex', justifyContent: 'flex-end', fontSize: 14, fontWeight: 700 }}>
            Total: <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--accent)', marginLeft: 8 }}>
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
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{value}</div>
            </div>
          ))}
        </div>
        <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }}>Notas (opcional)</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder="Notas de revision" aria-label="Notas de revision"
          style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }} />
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

  const tabs = [
    { id: 'mine', label: 'Mis timesheets' },
    ...(hasRole('admin', 'pm', 'hr') ? [
      { id: 'pending', label: `⏳ Pendientes (${pending.length})` },
      { id: 'team', label: 'Equipo' },
    ] : []),
  ]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<Clock size={18} />} title={t('timesheets.title')} subtitle={t('timesheets.subtitle')} />

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'mine' && (
        <div>
          {loadingMine ? <Spinner /> : mySheets.length === 0 ? (
            <EmptyState icon="📋" title="Sin timesheets" description="Aun no has generado ningun parte semanal" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {mySheets.map(ts => (
                <div key={ts.week_start} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${ts.status === 'rejected' ? 'var(--danger-border)' : ts.status === 'approved' ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>
                      Semana del {fmtDate(ts.week_start)} al {fmtDate(ts.week_end)}
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-2)' }}>
                      <span>Total: <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>{fmtHours(ts.total_hours)}</span></span>
                      <span>Facturables: <span style={{ color: 'var(--accent)' }}>{fmtHours(ts.billable_hours)}</span></span>
                      {ts.total_cost > 0 && <span>Coste: <span style={{ color: 'var(--warning)' }}>{fmtCurrency(ts.total_cost)}</span></span>}
                    </div>
                    {ts.review_notes && ts.status === 'rejected' && (
                      <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 6, padding: '4px 10px' }}>
                        💬 {ts.review_notes}
                      </div>
                    )}
                  </div>
                  <StatusBadge status={ts.status} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => setViewLines(ts.week_start)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '5px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Ver líneas</button>
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
              {pending.map(ts => (
                <div key={ts.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', background: 'var(--surface-2)', border: '1px solid #ffb80030', borderRadius: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{ts.user_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>
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
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 80px 80px 80px 100px 80px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
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
              {[...teamSheets].sort((a, b) => {
                const va = a[teamSortKey] ?? ''
                const vb = b[teamSortKey] ?? ''
                const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb))
                return teamSortDir === 'asc' ? cmp : -cmp
              }).map(ts => (
                <div key={ts.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 80px 80px 80px 100px 80px', gap: 16, padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{ts.user_name}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{fmtDate(ts.week_start)}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{fmtHours(ts.total_hours)}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--accent)' }}>{fmtHours(ts.billable_hours)}</span>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--warning)' }}>{fmtCurrency(ts.total_cost)}</span>
                  <StatusBadge status={ts.status} />
                  {ts.status === 'submitted' && <Button size="sm" onClick={() => setReviewing(ts)}>Revisar</Button>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {viewLines && <WeekLines weekStart={viewLines} onClose={() => setViewLines(null)} />}
      {reviewing && <ReviewModal timesheet={reviewing} onClose={() => setReviewing(null)} />}
    </div>
  )
}
