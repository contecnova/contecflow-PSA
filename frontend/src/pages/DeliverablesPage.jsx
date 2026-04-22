import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, useSort, SortableTH } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Package } from 'lucide-react'
import { fmtDate, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const STATUS_CFG = {
  planned:     { label: 'Planificado', color: 'var(--text-2)', icon: '📋' },
  in_progress: { label: 'En curso',    color: 'var(--accent)', icon: '🔄' },
  in_review:   { label: 'En revisión', color: 'var(--warning)', icon: '👁' },
  delivered:   { label: 'Entregado',   color: 'var(--purple)', icon: '📤' },
  accepted:    { label: 'Aceptado',    color: 'var(--success)', icon: '✅' },
  rejected:    { label: 'Rechazado',   color: 'var(--danger)', icon: '❌' },
}

function StatusDropdown({ del, onUpdate }) {
  const [open, setOpen] = useState(false)
  const cfg = STATUS_CFG[del.status] || STATUS_CFG.planned
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        style={{ display: 'flex', alignItems: 'center', gap: 5, background: cfg.color + '15', border: `1px solid ${cfg.color}40`, borderRadius: 20, padding: '3px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 700, color: cfg.color, fontFamily: 'inherit', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {cfg.icon} {cfg.label} ▾
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 10 }} />
          <div style={{ position: 'absolute', top: '110%', left: 0, zIndex: 20, background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 10, padding: 6, minWidth: 160, boxShadow: '0 8px 24px #00000060' }}>
            {Object.entries(STATUS_CFG).map(([s, c]) => (
              <button key={s} onClick={() => { onUpdate(s); setOpen(false) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', background: del.status === s ? 'var(--accent-muted)' : 'transparent', border: 'none', borderRadius: 6, padding: '8px 12px', color: del.status === s ? 'var(--accent)' : 'var(--text-1)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
                {c.icon} {c.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function DeliverableFormModal({ del, projectId, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!del?.id
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const [form, setForm] = useState({
    name: del?.name || '',
    description: del?.description || '',
    format: del?.format || '',
    planned_date: del?.planned_date || '',
    owner_id: del?.owner_id || '',
    client_contact: del?.client_contact || '',
    acceptance_criteria: del?.acceptance_criteria || '',
    sort_order: del?.sort_order || 0,
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => isEdit ? api.patch(`/deliverables/${projectId}/${del.id}`, data) : api.post(`/deliverables/${projectId}`, data),
    onSuccess: () => { qc.invalidateQueries(['deliverables', projectId]); qc.invalidateQueries(['deliverables-overview']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title={isEdit ? `Editar entregable` : 'Nuevo Entregable'} onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Nombre *</label>
          <input value={form.name} onChange={set('name')} style={fs} placeholder="Nombre del entregable" aria-label="Nombre del entregable" />
        </div>
        <div>
          <label style={ls}>Formato</label>
          <input value={form.format} onChange={set('format')} style={fs} placeholder="Formato de entrega" aria-label="Formato de entrega" />
        </div>
        <div>
          <label style={ls}>Fecha planificada</label>
          <input type="date" value={form.planned_date} onChange={set('planned_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>Responsable</label>
          <select value={form.owner_id} onChange={set('owner_id')} style={fs}>
            <option value="">Sin asignar</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Contacto cliente</label>
          <input value={form.client_contact} onChange={set('client_contact')} style={fs} placeholder="Contacto del cliente" aria-label="Contacto del cliente" />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Descripción</label>
          <textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Criterios de aceptación</label>
          <textarea value={form.acceptance_criteria} onChange={set('acceptance_criteria')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder="Criterios de aceptacion" aria-label="Criterios de aceptacion" />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear entregable'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function DeliverablesPage() {
  const t = useAppT()
  const toast = useToast()
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [tab, setTab] = useState('project')

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })

  const { data: delivData, isLoading } = useQuery({
    queryKey: ['deliverables', selectedProject],
    queryFn: () => api.get(`/deliverables/${selectedProject}`).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: overview = [] } = useQuery({
    queryKey: ['deliverables-overview'],
    queryFn: () => api.get('/deliverables/all/overview').then(r => r.data),
    enabled: tab === 'overview',
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/deliverables/${selectedProject}/${id}`, { status }),
    onSuccess: () => { qc.invalidateQueries(['deliverables', selectedProject]); qc.invalidateQueries(['deliverables-overview']); qc.invalidateQueries(['deliverables-uat']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: accept } = useMutation({
    mutationFn: (id) => api.post(`/deliverables/${selectedProject}/${id}/accept`),
    onSuccess: () => { qc.invalidateQueries(['deliverables', selectedProject]); qc.invalidateQueries(['deliverables-overview']); qc.invalidateQueries(['deliverables-uat']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: reject } = useMutation({
    mutationFn: ({ id, reason }) => api.post(`/deliverables/${selectedProject}/${id}/reject?reason=${encodeURIComponent(reason)}`),
    onSuccess: () => { qc.invalidateQueries(['deliverables', selectedProject]); qc.invalidateQueries(['deliverables-overview']); qc.invalidateQueries(['deliverables-uat']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id) => api.delete(`/deliverables/${selectedProject}/${id}`),
    onSuccess: () => { qc.invalidateQueries(['deliverables', selectedProject]); qc.invalidateQueries(['deliverables-overview']); qc.invalidateQueries(['deliverables-uat']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const deliverables = delivData?.deliverables || []
  const summary = delivData?.summary || {}
  const { sort: ovSort, setSort: setOvSort, sortedData: sortedOverview } = useSort(overview, 'name')

  return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<Package size={18} />} title={t('deliverables.title')} subtitle={t('deliverables.subtitle')} />

      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        {[['project', '📁 Por proyecto'], ['overview', '🌐 Vista global']].map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 18px', borderRadius: 8, border: `1px solid ${tab === t ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t ? 'var(--accent-muted)' : 'transparent', color: tab === t ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'project' && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Seleccionar proyecto...</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && hasRole('admin', 'pm') && <Button onClick={() => setShowCreate(true)} icon="＋">Nuevo entregable</Button>}
          </div>

          {selectedProject && summary.total > 0 && (
            <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
              {[
                { label: 'Total', value: summary.total, color: 'var(--text-2)' },
                { label: 'Aceptados', value: summary.accepted, color: 'var(--success)' },
                { label: 'Entregados', value: summary.delivered, color: 'var(--purple)' },
                { label: 'En retraso', value: summary.overdue, color: 'var(--danger)' },
                { label: 'Completado', value: `${summary.completion_pct}%`, color: 'var(--accent)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '12px 16px', flex: 1 }}>
                  <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="📦" title="Selecciona un proyecto" description="Elige un proyecto para consultar sus entregables" />
          ) : isLoading ? <Spinner /> : deliverables.length === 0 ? (
            <EmptyState icon="📦" title="Sin entregables" description="Este proyecto todavia no tiene entregables definidos" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {deliverables.map(d => {
                const cfg = STATUS_CFG[d.status] || STATUS_CFG.planned
                return (
                  <div key={d.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${d.overdue ? 'var(--danger-border)' : cfg.color + '25'}`, borderRadius: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 6 }}>
                          <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{d.code}</span>
                          <span style={{ fontSize: 14, fontWeight: 700 }}>{d.name}</span>
                          {d.format && <span style={{ fontSize: 11, color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 20, padding: '1px 8px' }}>{d.format}</span>}
                          {d.overdue && <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700 }}>⚠ En retraso</span>}
                        </div>
                        {d.description && <p style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>{d.description}</p>}
                        <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                          {d.planned_date && <span style={{ color: d.overdue ? 'var(--danger)' : 'var(--text-2)' }}>📅 Planif: {fmtDate(d.planned_date)}</span>}
                          {d.delivered_date && <span style={{ color: 'var(--purple)' }}>📤 Entregado: {fmtDate(d.delivered_date)}</span>}
                          {d.accepted_date && <span style={{ color: 'var(--success)' }}>✅ Aceptado: {fmtDate(d.accepted_date)}</span>}
                          {d.owner_name && <span style={{ color: 'var(--text-2)' }}>👤 {d.owner_name}</span>}
                          {d.client_contact && <span style={{ color: 'var(--text-2)' }}>🏢 {d.client_contact}</span>}
                        </div>
                        {d.rejection_reason && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 6, padding: '4px 10px' }}>💬 {d.rejection_reason}</div>}
                        {d.acceptance_criteria && <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-2)' }}>✓ {d.acceptance_criteria}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                        <StatusDropdown del={d} onUpdate={(status) => updateStatus({ id: d.id, status })} />
                        <div style={{ display: 'flex', gap: 6 }}>
                          {d.status === 'delivered' && hasRole('admin', 'pm') && (
                            <>
                              <Button size="sm" onClick={() => accept(d.id)}>✓ Aceptar</Button>
                              <Button size="sm" variant="danger" onClick={() => { const r = prompt('Motivo del rechazo:'); if (r) reject({ id: d.id, reason: r }) }}>✕ Rechazar</Button>
                            </>
                          )}
                          {hasRole('admin', 'pm') && <button onClick={() => setEditing(d)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏️</button>}
                          {hasRole('admin', 'pm') && <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este entregable?', onConfirm: () => del(d.id), danger: true }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'overview' && (
        overview.length === 0 ? (
          <EmptyState icon="📦" title="Sin entregables en la vista global" description="No hay entregables registrados en ningun proyecto" />
        ) : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 120px', gap: 16, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
              <SortableTH col="name" sort={ovSort} onSort={setOvSort}>Entregable</SortableTH>
              <SortableTH col="project_code" sort={ovSort} onSort={setOvSort}>Proyecto</SortableTH>
              <SortableTH col="owner_name" sort={ovSort} onSort={setOvSort}>Responsable</SortableTH>
              <SortableTH col="planned_date" sort={ovSort} onSort={setOvSort}>Planificado</SortableTH>
              <SortableTH col="delivered_date" sort={ovSort} onSort={setOvSort}>Entregado</SortableTH>
              <SortableTH col="status" sort={ovSort} onSort={setOvSort}>Estado</SortableTH>
            </div>
            {sortedOverview.map(d => {
              const cfg = STATUS_CFG[d.status] || STATUS_CFG.planned
              return (
                <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 120px', gap: 16, padding: '12px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{d.name}</div>
                    {d.overdue && <span style={{ fontSize: 10, color: 'var(--danger)' }}>⚠ En retraso</span>}
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{d.project_code}</span>
                  <span style={{ fontSize: 12 }}>{d.owner_name || '—'}</span>
                  <span style={{ fontSize: 12, color: d.overdue ? 'var(--danger)' : 'var(--text-2)' }}>{d.planned_date ? fmtDate(d.planned_date) : '—'}</span>
                  <span style={{ fontSize: 12, color: 'var(--purple)' }}>{d.delivered_date ? fmtDate(d.delivered_date) : '—'}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: cfg.color }}>{cfg.icon} {cfg.label}</span>
                </div>
              )
            })}
          </div>
        )
      )}

      {showCreate && selectedProject && <DeliverableFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <DeliverableFormModal del={editing} projectId={editing.project_id || selectedProject} onClose={() => setEditing(null)} />}
    </div>
  )
}