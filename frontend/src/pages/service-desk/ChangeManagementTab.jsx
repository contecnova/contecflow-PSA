import { useId, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import api from '../../services/api'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH } from '../../components/ui'
import { COLOR } from '../../constants/theme'

const CHANGE_STATUS_COLOR = {
  draft: COLOR.text2,
  submitted: COLOR.accent,
  cab_review: COLOR.warning,
  approved: COLOR.success,
  scheduled: 'var(--sky-blue)',
  in_progress: COLOR.accent,
  implemented: COLOR.success,
  post_review: COLOR.warning,
  closed_success: COLOR.success,
  closed_failed: COLOR.danger,
  cancelled: COLOR.text3,
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function ChangeDetailPanel({ change, onClose, onEdit, onAction, statusActions }) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ['sd-change-detail', change.id],
    queryFn: () => api.get(`/sd/changes/${change.id}`).then(r => r.data),
  })

  const c = detail || change
  const sc = CHANGE_STATUS_COLOR[c.status] || COLOR.text2
  const rc = c.risk === 'critical' ? COLOR.danger : c.risk === 'high' ? 'var(--orange)' : c.risk === 'medium' ? COLOR.warning : COLOR.success

  const Section = ({ title, content: text }) => text ? (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', lineHeight: 1.6, whiteSpace: 'pre-wrap', background: 'var(--surface-1)', borderRadius: 8, padding: '10px 14px' }}>{text}</div>
    </div>
  ) : null

  const actions = statusActions[c.status] || []

  return (
    <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 560, background: 'var(--surface-0)', borderLeft: '1px solid var(--surface-4)', zIndex: 200, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 32px rgba(0,0,0,0.25)' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-1)', position: 'sticky', top: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, marginRight: 12 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 700 }}>{c.number}</span>
              <span style={{ fontSize: "var(--text-xs)", background: `${sc}15`, color: sc, padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{c.status?.replace(/_/g, ' ')}</span>
              <span style={{ fontSize: "var(--text-xs)", color: rc, fontWeight: 600 }}>⚠ {c.risk}</span>
              <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{c.change_type?.replace(/_/g, ' ')}</span>
            </div>
            <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.3 }}>{c.title}</div>
          </div>
          <button onClick={onClose} aria-label="Cerrar detalle" style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: "var(--text-xl)", cursor: 'pointer', lineHeight: 1, padding: '0 4px' }}>×</button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button onClick={onEdit} style={{ padding: '5px 14px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
          {actions.map(a => (
            <button key={a.label} onClick={() => { onAction(c, a); onClose() }} style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${a.color}40`, background: `${a.color}10`, color: a.color, fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>{a.label}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        {isLoading ? <Spinner /> : <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 20 }}>
            {[
              ['Solicitante', c.requester || '—'],
              ['Owner', c.owner || '—'],
              ['Inicio planif.', fmtDate(c.planned_start)],
              ['Fin planif.', fmtDate(c.planned_end)],
              ['Inicio real', fmtDate(c.actual_start)],
              ['Fin real', fmtDate(c.actual_end)],
              ['Downtime', c.downtime_minutes ? `${c.downtime_minutes} min` : '—'],
              ['Aprobado', c.approved_at ? fmtDate(c.approved_at) : '—'],
            ].map(([label, val]) => (
              <div key={label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 500 }}>{val}</div>
              </div>
            ))}
          </div>
          <Section title="Descripción" content={c.description} />
          <Section title="Justificación de negocio" content={c.business_justification} />
          <Section title="Plan de implementación" content={c.implementation_plan} />
          <Section title="Plan de rollback" content={c.rollback_plan} />
          <Section title="Plan de pruebas" content={c.test_plan} />
          <Section title="Descripción de impacto" content={c.impact_description} />
        </>}
      </div>
    </div>
  )
}

function ChangeEditModal({ change, onClose, onSaved }) {
  const idPrefix = useId()
  const toast = useToast()
  const [form, setForm] = useState({
    title: change.title || '',
    description: change.description || '',
    change_type: change.change_type || 'normal',
    risk: change.risk || 'medium',
    priority: change.priority || 'p3_medium',
    business_justification: change.business_justification || '',
    implementation_plan: change.implementation_plan || '',
    rollback_plan: change.rollback_plan || '',
    test_plan: change.test_plan || '',
    impact_description: change.impact_description || '',
    planned_start: change.planned_start ? change.planned_start.replace(' ', 'T').slice(0, 16) : '',
    planned_end: change.planned_end ? change.planned_end.replace(' ', 'T').slice(0, 16) : '',
    downtime_minutes: change.downtime_minutes || 0,
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => api.patch(`/sd/changes/${change.id}`, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={`Editar ${change.number}`} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, maxHeight: '70vh', overflowY: 'auto', paddingRight: 4 }}>
        <div style={{ gridColumn: '1/-1' }}><label htmlFor={`${idPrefix}-title`} style={LS}>Título *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-change-type`} style={LS}>Tipo de cambio</label><select id={`${idPrefix}-change-type`} value={form.change_type} onChange={set('change_type')} style={IS}><option value="standard">Standard — pre-aprobado</option><option value="normal">Normal — requiere CAB</option><option value="emergency">Emergency — ECAB</option></select></div>
        <div><label htmlFor={`${idPrefix}-risk`} style={LS}>Riesgo</label><select id={`${idPrefix}-risk`} value={form.risk} onChange={set('risk')} style={IS}>{[['low', 'Bajo'], ['medium', 'Medio'], ['high', 'Alto'], ['critical', 'Crítico']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div><label htmlFor={`${idPrefix}-planned-start`} style={LS}>Inicio planificado</label><input id={`${idPrefix}-planned-start`} type="datetime-local" value={form.planned_start} onChange={set('planned_start')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-planned-end`} style={LS}>Fin planificado</label><input id={`${idPrefix}-planned-end`} type="datetime-local" value={form.planned_end} onChange={set('planned_end')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-downtime`} style={LS}>Downtime estimado (min)</label><input id={`${idPrefix}-downtime`} type="number" value={form.downtime_minutes} onChange={set('downtime_minutes')} style={IS} min="0" /></div>
        <div style={{ gridColumn: '1/-1' }}><label htmlFor={`${idPrefix}-description`} style={LS}>Descripción *</label><textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1' }}><label htmlFor={`${idPrefix}-business-justification`} style={LS}>Justificación de negocio</label><textarea id={`${idPrefix}-business-justification`} value={form.business_justification} onChange={set('business_justification')} rows={2} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label htmlFor={`${idPrefix}-implementation-plan`} style={LS}>Plan de implementación</label><textarea id={`${idPrefix}-implementation-plan`} value={form.implementation_plan} onChange={set('implementation_plan')} rows={4} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label htmlFor={`${idPrefix}-rollback-plan`} style={LS}>Plan de rollback</label><textarea id={`${idPrefix}-rollback-plan`} value={form.rollback_plan} onChange={set('rollback_plan')} rows={4} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label htmlFor={`${idPrefix}-test-plan`} style={LS}>Plan de pruebas</label><textarea id={`${idPrefix}-test-plan`} value={form.test_plan} onChange={set('test_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label htmlFor={`${idPrefix}-impact-description`} style={LS}>Descripción de impacto</label><textarea id={`${idPrefix}-impact-description`} value={form.impact_description} onChange={set('impact_description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10 }}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>Guardar cambios</Button></div>
      </div>
    </Modal>
  )
}

function NewChangeModal({ onClose, onSaved }) {
  const idPrefix = useId()
  const toast = useToast()
  const [form, setForm] = useState({
    title: '', description: '', change_type: 'normal', risk: 'medium', priority: 'p3_medium', business_justification: '', implementation_plan: '', rollback_plan: '', test_plan: '', planned_start: '', planned_end: '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => api.post('/sd/changes', data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title="Nuevo Change Request" onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={{ gridColumn: '1/-1' }}><label htmlFor={`${idPrefix}-title`} style={LS}>Título *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} placeholder="Título del cambio" /></div>
        <div><label style={LS}>Tipo de cambio</label><select value={form.change_type} onChange={set('change_type')} style={IS}><option value="standard">Standard — pre-aprobado</option><option value="normal">Normal — requiere CAB</option><option value="emergency">Emergency — ECAB</option></select></div>
        <div><label style={LS}>Riesgo</label><select value={form.risk} onChange={set('risk')} style={IS}><option value="low">Bajo</option><option value="medium">Medio</option><option value="high">Alto</option><option value="critical">Crítico</option></select></div>
        <div><label style={LS}>Inicio planificado</label><input type="datetime-local" value={form.planned_start} onChange={set('planned_start')} style={IS} /></div>
        <div><label style={LS}>Fin planificado</label><input type="datetime-local" value={form.planned_end} onChange={set('planned_end')} style={IS} /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={LS}>Descripción *</label><textarea value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={LS}>Justificación de negocio</label><textarea value={form.business_justification} onChange={set('business_justification')} rows={2} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label style={LS}>Plan de implementación</label><textarea value={form.implementation_plan} onChange={set('implementation_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label style={LS}>Plan de rollback</label><textarea value={form.rollback_plan} onChange={set('rollback_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.description} loading={isPending}>Crear Change Request</Button></div>
      </div>
    </Modal>
  )
}

export default function ChangeManagementTab() {
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState(null)
  const [detail, setDetail] = useState(null)
  const [filterStatus, setFilterStatus] = useState('')

  const { data: changes = [], isLoading } = useQuery({
    queryKey: ['sd-changes', filterStatus],
    queryFn: () => api.get('/sd/changes', { params: { status: filterStatus || undefined } }).then(r => r.data),
  })

  const { mutate: approve } = useMutation({
    mutationFn: ({ id, approved }) => api.post(`/sd/changes/${id}/approve`, { approved }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success('Change actualizado') },
    onError: e => toast.error(extractErr(e, 'Error al actualizar')),
  })

  const { sort: changeSort, setSort: setChangeSort, sortedData: sortedChanges } = useSort(changes, 'number')

  const IS = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }

  const STATUS_ACTIONS = {
    draft: [{ label: 'Enviar a revisión', next: 'submitted', color: COLOR.accent }],
    submitted: [{ label: 'Enviar a CAB', next: 'cab_review', color: COLOR.warning }],
    cab_review: [{ label: 'Aprobar', action: 'approve', color: COLOR.success }, { label: 'Rechazar', action: 'reject', color: COLOR.danger }],
    approved: [{ label: 'Programar', next: 'scheduled', color: COLOR.accent }],
    scheduled: [{ label: 'Iniciar', next: 'in_progress', color: COLOR.accent }],
    in_progress: [{ label: 'Implementado', next: 'implemented', color: COLOR.success }],
    implemented: [{ label: 'Cerrar éxito', next: 'closed_success', color: COLOR.success }, { label: 'Cerrar fallo', next: 'closed_failed', color: COLOR.danger }],
  }

  const handleAction = (c, action) => {
    if (action.action === 'approve') { approve({ id: c.id, approved: true }); return }
    if (action.action === 'reject') { approve({ id: c.id, approved: false }); return }
    api.patch(`/sd/changes/${c.id}`, { status: action.next })
      .then(() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success('Estado actualizado') })
      .catch(e => toast.error(extractErr(e, 'Error')))
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10 }}><select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={IS}><option value="">Todos los estados</option>{['draft', 'submitted', 'cab_review', 'approved', 'scheduled', 'in_progress', 'implemented', 'post_review', 'closed_success', 'closed_failed'].map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}</select></div>
        <Button onClick={() => setShowNew(true)}>+ Nuevo Change Request</Button>
      </div>

      {isLoading ? <Spinner /> : changes.length === 0 ? <EmptyState icon="🔄" title="Sin cambios registrados" description="Crea el primer change request para iniciar el flujo de gestión de cambios." /> :
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr style={{ borderBottom: '2px solid var(--surface-4)' }}><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="number" sort={changeSort} onSort={setChangeSort}>Nº</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="title" sort={changeSort} onSort={setChangeSort}>Título</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="change_type" sort={changeSort} onSort={setChangeSort}>Tipo</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="risk" sort={changeSort} onSort={setChangeSort}>Riesgo</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="status" sort={changeSort} onSort={setChangeSort}>Estado</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="planned_start" sort={changeSort} onSort={setChangeSort}>Inicio planif.</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap' }}><SortableTH col="owner" sort={changeSort} onSort={setChangeSort}>Owner</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap', fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase' }}>Acciones</th></tr></thead>
            <tbody>
              {sortedChanges.map(c => {
                const sc = CHANGE_STATUS_COLOR[c.status] || COLOR.text2
                const rc = c.risk === 'critical' ? COLOR.danger : c.risk === 'high' ? 'var(--orange)' : c.risk === 'medium' ? COLOR.warning : COLOR.success
                const actions = STATUS_ACTIONS[c.status] || []
                return (
                  <tr key={c.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600 }}>{c.number}</td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-base)", color: 'var(--text-1)', maxWidth: 220 }}><button onClick={() => setDetail(c)} style={{ background: 'none', border: 'none', color: 'var(--text-1)', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', fontSize: "var(--text-base)", padding: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 220 }}>{c.title}</button></td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{c.change_type?.replace(/_/g, ' ')}</td>
                    <td style={{ padding: '10px 8px' }}><span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: rc }}>{c.risk}</span></td>
                    <td style={{ padding: '10px 8px' }}><span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: sc, background: `${sc}15`, padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap' }}>{c.status?.replace(/_/g, ' ')}</span></td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{fmtDate(c.planned_start)}</td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{c.owner || '—'}</td>
                    <td style={{ padding: '10px 8px' }}><div style={{ display: 'flex', gap: 4, flexWrap: 'nowrap' }}><button onClick={() => setEditing(c)} style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>✏ Editar</button>{actions.map(a => <button key={a.label} onClick={() => handleAction(c, a)} style={{ padding: '3px 8px', borderRadius: 5, border: `1px solid ${a.color}40`, background: `${a.color}10`, color: a.color, fontSize: "var(--text-2xs)", cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{a.label}</button>)}</div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>}

      {showNew && <NewChangeModal onClose={() => setShowNew(false)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setShowNew(false); toast.success('Change request creado') }} />}
      {editing && <ChangeEditModal change={editing} onClose={() => setEditing(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setEditing(null); toast.success('Change request actualizado') }} />}
      {detail && <ChangeDetailPanel change={detail} onClose={() => setDetail(null)} onEdit={() => { setEditing(detail); setDetail(null) }} onAction={handleAction} statusActions={STATUS_ACTIONS} />}
    </div>
  )
}
