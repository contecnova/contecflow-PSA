/**
 * ClientPortalPage – Internal PM view for managing the client portal:
 * - Manage client users and their access
 * - Create/manage UAT sessions with test cases
 * - Send messages to clients
 * - Upload documents
 * - View portal stats
 */
import React, { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { fmtDate, fmtCurrency, extractErr} from '../utils/helpers'
import { STATUS_CFG, FR_STATUS_CFG } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


// STATUS_CFG y FR_STATUS_CFG centralizados en constants/sharedStatus.js

function StatusBadge({ status, cfg }) {
  const c = cfg[status] || { label: status, color: 'var(--text-2)' }
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: c.color + '20', color: c.color, border: `1px solid ${c.color}40`, textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{c.label}</span>
}

// ── Client Users Management ───────────────────────────────────────────────────
function ClientUsersTab({ projectId }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [editingClient, setEditingClient] = useState(null)
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['portal-clients', projectId],
    queryFn: () => api.get('/portal/clients', { params: { project_id: projectId } }).then(r => r.data),
    enabled: !!projectId,
  })
  const { mutate: deleteClient } = useMutation({
    mutationFn: (id) => api.delete(`/portal/clients/${id}`),
    onSuccess: () => qc.invalidateQueries(['portal-clients', projectId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggleActive } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/portal/clients/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['portal-clients', projectId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{clients.length} contacto(s) con acceso al portal</div>
        <Button onClick={() => setShowCreate(true)} icon="＋">Añadir contacto cliente</Button>
      </div>
      {isLoading ? <Spinner /> : clients.length === 0 ? (
        <EmptyState icon="👤" title="Sin contactos de cliente" description="Añade los contactos del cliente para que accedan al portal" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {clients.map(c => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', background: 'var(--surface-2)', border: `1px solid ${c.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, opacity: c.is_active ? 1 : 0.6 }}>
              <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'linear-gradient(135deg, #00d4ff, #7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                {c.full_name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{c.full_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{c.job_title || '—'} · {c.company || c.project_name} · {c.email}</div>
                <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: 11 }}>
                  {c.can_approve_deliverables && <span style={{ color: 'var(--success)' }}>✓ Puede aprobar entregables</span>}
                  {c.can_request_changes && <span style={{ color: 'var(--accent)' }}>✓ Puede solicitar cambios</span>}
                  {c.can_view_budget && <span style={{ color: 'var(--warning)' }}>✓ Ve el presupuesto</span>}
                </div>
              </div>
              {c.last_login && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>Último acceso: {fmtDate(c.last_login)}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setEditingClient(c)}
                  style={{ background: 'none', border: '1px solid var(--accent-glow)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                  ✏ Editar
                </button>
                <button onClick={() => toggleActive({ id: c.id, active: !c.is_active })}
                  style={{ background: 'none', border: `1px solid ${c.is_active ? 'var(--warning-border)' : 'var(--success-border)'}`, borderRadius: 6, padding: '4px 10px', color: c.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                  {c.is_active ? '⏸ Suspender' : '▶ Activar'}
                </button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este cliente del portal?', onConfirm: () => deleteClient(c.id), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-bg)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showCreate && projectId && <CreateClientModal projectId={projectId} onClose={() => setShowCreate(false)} />}
      {editingClient && <EditClientModal client={editingClient} onClose={() => setEditingClient(null)} onSaved={() => { qc.invalidateQueries(['portal-clients', projectId]); setEditingClient(null) }} />}
    </div>
  )
}

function CreateClientModal({ projectId, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ full_name: '', email: '', job_title: '', company: '', phone: '', password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: true, can_view_team: false })
  const [extraProjectIds, setExtraProjectIds] = useState([]) // additional projects beyond projectId
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => api.post('/portal/clients', data),
    onSuccess: () => { qc.invalidateQueries(['portal-clients', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const allProjectIds = [...new Set([projectId, ...extraProjectIds].filter(Boolean))]

  return (
    <Modal open title="Añadir contacto al portal" onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre completo *</label><input value={form.full_name} onChange={set('full_name')} style={fs} /></div>
        <div><label style={ls}>Email *</label><input type="email" value={form.email} onChange={set('email')} style={fs} /></div>
        <div><label style={ls}>Cargo</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder="Director de proyecto" /></div>
        <div><label style={ls}>Empresa</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>Teléfono</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Contraseña de acceso *</label><input type="password" value={form.password} onChange={set('password')} style={fs} placeholder="Mínimo 8 caracteres" /></div>
        {allProjects.length > 1 && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={{ ...ls, marginBottom: 10 }}>Acceso a proyectos adicionales</label>
            <div style={{ maxHeight: 140, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-2) var(--space-3)' }}>
              {allProjects.filter(p => p.id !== projectId).map(p => (
                <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={extraProjectIds.includes(p.id)}
                    onChange={e => setExtraProjectIds(prev => e.target.checked ? [...prev, p.id] : prev.filter(id => id !== p.id))} />
                  <span style={{ color: 'var(--text-1)', fontWeight: 500 }}>{p.code}</span>
                  <span style={{ color: 'var(--text-2)', fontSize: 12 }}>{p.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ ...ls, marginBottom: 10 }}>Permisos</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[['can_approve_deliverables','Puede aprobar entregables y UATs'],['can_request_changes','Puede solicitar nuevas funcionalidades y cambios'],['can_view_budget','Puede ver el consumo de presupuesto (horas)'],['can_view_team','Puede ver el equipo asignado']].map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate({ ...form, project_id: projectId, project_ids: allProjectIds })} disabled={isPending || !form.full_name || !form.email || !form.password} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear acceso'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── UAT Management ────────────────────────────────────────────────────────────
function EditClientModal({ client, onClose, onSaved }) {
  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data) => api.patch(`/portal/clients/${client.id}`, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const toast = useToast()
  const [form, setForm] = useState({
    full_name: client.full_name || '',
    email: client.email || '',
    job_title: client.job_title || '',
    company: client.company || '',
    phone: client.phone || '',
    password: '',
    project_ids: Array.isArray(client.project_ids) ? client.project_ids : (client.project_id ? [client.project_id] : []),
    can_approve_deliverables: client.can_approve_deliverables ?? true,
    can_request_changes: client.can_request_changes ?? true,
    can_view_budget: client.can_view_budget ?? true,
    can_view_team: client.can_view_team ?? false,
  })

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSave = () => {
    const data = { ...form }
    if (!data.password) delete data.password  // Only send password if changed
    mutate(data)
  }

  return (
    <Modal open title={`Editar contacto — ${client.full_name}`} onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre completo *</label><input value={form.full_name} onChange={set('full_name')} style={fs} /></div>
        <div><label style={ls}>Email *</label><input type="email" value={form.email} onChange={set('email')} style={fs} /></div>
        <div><label style={ls}>Cargo</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder="Director de proyecto" /></div>
        <div><label style={ls}>Empresa</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>Teléfono</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Proyectos con acceso</label>
          <select
            multiple
            value={form.project_ids}
            onChange={e => setForm(f => ({ ...f, project_ids: Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean) }))}
            style={{ ...fs, height: 38 + Math.min(allProjects.length, 5) * 28 }}>
            {allProjects.map(project => (
              <option key={project.id} value={project.id}>{project.code} — {project.name}</option>
            ))}
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Nueva contraseña</label>
          <input type="password" value={form.password} onChange={set('password')} style={fs} placeholder="Dejar vacío para no cambiarla" />
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>Si no quieres cambiar la contraseña, deja este campo vacío.</div>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ ...ls, marginBottom: 10 }}>Permisos</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              ['can_approve_deliverables', 'Puede aprobar entregables y UATs'],
              ['can_request_changes', 'Puede solicitar nuevas funcionalidades y cambios'],
              ['can_view_budget', 'Puede ver el consumo de presupuesto (horas)'],
              ['can_view_team', 'Puede ver el equipo asignado'],
            ].map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.full_name || !form.email}>
            {isPending ? 'Guardando...' : 'Guardar cambios'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}


function UATTab({ projectId }) {
  const [showCreate, setShowCreate] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['uat-team', projectId],
    queryFn: () => api.get('/portal/uat/team', { params: { project_id: projectId } }).then(r => r.data),
    enabled: !!projectId,
  })
  const { data: deliverables = [] } = useQuery({
    queryKey: ['deliverables-uat', projectId],
    queryFn: () => api.get(`/deliverables/${projectId}`).then(r => r.data.deliverables || []),
    enabled: !!projectId,
  })
  // Always read live data so UATDetailModal reflects updates without reopening
  const selectedSession = selectedId ? (sessions.find(s => s.id === selectedId) ?? null) : null

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{sessions.length} sesion(es) UAT</div>
        {projectId && <Button onClick={() => setShowCreate(true)} icon="＋">Nueva sesión UAT</Button>}
      </div>
      {isLoading ? <Spinner /> : sessions.length === 0 ? (
        <EmptyState icon="🧪" title="Sin sesiones UAT" description="Crea sesiones UAT para que el cliente valide los entregables" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {sessions.map(s => (
            <div key={s.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${STATUS_CFG[s.status]?.color + '40' || 'var(--surface-4)'}`, borderRadius: 12, cursor: 'pointer' }}
              onClick={() => setSelectedId(s.id)}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'var(--surface-2)'}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 3 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{s.code}</span>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{s.title}</span>
                    {s.overdue && <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700 }}>⚠ Vencido</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {s.deadline && `Plazo: ${fmtDate(s.deadline)} · `}
                    {s.stats.total} casos · {s.stats.passed} ✓ · {s.stats.failed} ✗
                  </div>
                </div>
                <StatusBadge status={s.status} cfg={STATUS_CFG} />
              </div>
              {s.stats.total > 0 && (
                <div style={{ height: 4, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(s.stats.passed / s.stats.total) * 100}%`, background: 'var(--success)', borderRadius: 4, transition: 'width 0.3s' }} />
                </div>
              )}
              {s.issues.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger)' }}>
                  🐛 {s.issues.filter(i => i.status === 'open').length} incidencia(s) abiertas
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {showCreate && projectId && <CreateUATModal projectId={projectId} deliverables={deliverables} onClose={() => setShowCreate(false)} />}
      {selectedSession && <UATDetailModal session={selectedSession} onClose={() => setSelectedId(null)} />}
    </div>
  )
}

function CreateUATModal({ projectId, deliverables, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ title: '', description: '', deliverable_id: '', test_environment: '', test_credentials: '', test_guide_url: '', available_from: '', deadline: '' })
  const [testCases, setTestCases] = useState([{ title: '', steps: '', expected_result: '' }])
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const { mutate, isPending } = useMutation({
    mutationFn: async (data) => {
      const res = await api.post(`/portal/uat/${projectId}`, data.form)
      for (const tc of data.testCases.filter(t => t.title)) {
        await api.post(`/portal/uat/${res.data.id}/test-cases`, { title: tc.title, steps: tc.steps, expected_result: tc.expected_result, order: data.testCases.indexOf(tc) })
      }
      return res
    },
    onSuccess: () => { qc.invalidateQueries(['uat-team', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title="Nueva sesión UAT" onClose={onClose} width={680}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div><label style={ls}>Título *</label><input value={form.title} onChange={set('title')} style={fs} placeholder="UAT Portal Cliente - Sprint 3" /></div>
          <div><label style={ls}>Entregable asociado</label>
            <select value={form.deliverable_id} onChange={set('deliverable_id')} style={fs}>
              <option value="">Sin vincular</option>
              {deliverables.map(d => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </select>
          </div>
        </div>
        <div><label style={ls}>Descripción</label><textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label style={ls}>URL entorno de pruebas</label><input value={form.test_environment} onChange={set('test_environment')} style={fs} placeholder="https://staging.cliente.com" /></div>
          <div><label style={ls}>Credenciales de acceso</label><input value={form.test_credentials} onChange={set('test_credentials')} style={fs} placeholder="user: demo / pass: ****" /></div>
          <div><label style={ls}>Disponible desde</label><input type="date" value={form.available_from} onChange={set('available_from')} style={fs} /></div>
          <div><label style={ls}>Fecha límite</label><input type="date" value={form.deadline} onChange={set('deadline')} style={fs} /></div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 10 }}>Casos de prueba</div>
          {testCases.map((tc, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 2fr 30px', gap: 8, marginBottom: 8, padding: 10, background: 'var(--surface-3)', borderRadius: 8 }}>
              <input value={tc.title} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, title: e.target.value } : t))} style={fs} placeholder={`Caso ${i + 1}: Título`} />
              <input value={tc.steps} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, steps: e.target.value } : t))} style={fs} placeholder="Pasos a seguir" />
              <input value={tc.expected_result} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, expected_result: e.target.value } : t))} style={fs} placeholder="Resultado esperado" />
              <button onClick={() => setTestCases(tcs => tcs.filter((_, j) => j !== i))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 16 }}>×</button>
            </div>
          ))}
          <button onClick={() => setTestCases(tcs => [...tcs, { title: '', steps: '', expected_result: '' }])}
            style={{ background: 'none', border: '1px dashed #1e2d45', borderRadius: 8, padding: '8px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', width: '100%' }}>
            ＋ Añadir caso de prueba
          </button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate({ form, testCases })} disabled={isPending || !form.title} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear sesión UAT'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function UATDetailModal({ session: initialSession, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: updateIssue } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/portal/uat/issues/${id}?status=${status}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['uat-team'], exact: false }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const SEV_COLORS = { low: 'var(--success)', medium: 'var(--accent)', high: 'var(--warning)', blocker: 'var(--danger)' }

  return (
    <Modal open title={`${initialSession.code} — ${initialSession.title}`} onClose={onClose} width={700}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <StatusBadge status={initialSession.status} cfg={STATUS_CFG} />
        {initialSession.test_environment && <a href={initialSession.test_environment} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none' }}>🔗 Entorno de pruebas</a>}
        {initialSession.deadline && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Plazo: {fmtDate(initialSession.deadline)}</span>}
      </div>

      {initialSession.client_notes && (
        <div style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase' }}>Notas del cliente</div>
          <p style={{ fontSize: 13, color: 'var(--text-1)' }}>{initialSession.client_notes}</p>
        </div>
      )}

      {/* Test cases */}
      {initialSession.test_cases.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            Casos de prueba ({initialSession.stats.passed}/{initialSession.stats.total} aprobados)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {initialSession.test_cases.map(tc => {
              const color = tc.status === 'passed' ? 'var(--success)' : tc.status === 'failed' ? 'var(--danger)' : 'var(--text-2)'
              return (
                <div key={tc.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${color}30`, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{tc.title}</div>
                      {tc.expected_result && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Esperado: {tc.expected_result}</div>}
                      {tc.actual_result && <div style={{ fontSize: 12, color: color, marginTop: 4 }}>Resultado: {tc.actual_result}</div>}
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color, background: color + '20', border: `1px solid ${color}40`, borderRadius: 20, padding: '2px 8px', textTransform: 'uppercase', flexShrink: 0 }}>
                      {tc.status === 'passed' ? '✓ OK' : tc.status === 'failed' ? '✗ KO' : '— Pendiente'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Issues */}
      {initialSession.issues.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            Incidencias ({initialSession.issues.filter(i => i.status === 'open').length} abiertas)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {initialSession.issues.map(issue => {
              const sevColor = SEV_COLORS[issue.severity] || 'var(--text-2)'
              return (
                <div key={issue.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${issue.status === 'open' ? sevColor + '40' : 'var(--surface-4)'}`, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: sevColor, background: sevColor + '20', borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{issue.severity}</span>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{issue.title}</span>
                      </div>
                      <p style={{ fontSize: 12, color: 'var(--text-2)', margin: 0 }}>{issue.description}</p>
                    </div>
                    {issue.status === 'open' && (
                      <select defaultValue={issue.status} onChange={e => updateIssue({ id: issue.id, status: e.target.value })}
                        style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: 'var(--space-2) var(--space-2)', color: 'var(--text-1)', fontSize: 11, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
                        <option value="open">Abierta</option>
                        <option value="fixed">Corregida</option>
                        <option value="deferred">Aplazada</option>
                        <option value="wontfix">No se corrige</option>
                      </select>
                    )}
                    {issue.status !== 'open' && <span style={{ fontSize: 11, color: 'var(--success)' }}>✓ {issue.status}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
      </div>
    </Modal>
  )
}

// ── Feature Requests Tab ──────────────────────────────────────────────────────
function FeatureRequestsTab({ projectId }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [responding, setResponding] = useState(null)
  const [responseForm, setResponseForm] = useState({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs', projectId],
    queryFn: () => api.get('/portal/feature-requests/team', { params: { project_id: projectId } }).then(r => Array.isArray(r.data) ? r.data : []),
    enabled: !!projectId,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }) => api.post(`/portal/feature-requests/${id}/respond`, data),
    onSuccess: () => { qc.invalidateQueries(['portal-frs', projectId]); setResponding(null) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.post(`/portal/feature-requests/${id}/respond`, { status }),
    onSuccess: () => qc.invalidateQueries(['portal-frs', projectId]),
    onError: e => toast.error(extractErr(e, 'Error al actualizar estado')),
  })

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  return (
    <div>
      {isLoading ? <Spinner /> : frs.length === 0 ? (
        <EmptyState icon="💡" title="Sin solicitudes de funcionalidad" description="El cliente no ha enviado ninguna solicitud aún" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {frs.map(fr => (
            <div key={fr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${fr.priority_color + '30'}`, borderRadius: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{fr.code}</span>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{fr.title}</span>
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 6px' }}>{fr.description}</p>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
                    <span style={{ color: fr.priority_color, fontWeight: 700 }}>⚡ {fr.priority_label}</span>
                    {fr.affected_area && <span style={{ color: 'var(--text-2)' }}>📋 {fr.affected_area}</span>}
                    {fr.client_name && <span style={{ color: 'var(--text-2)' }}>👤 {fr.client_name}</span>}
                    <span style={{ color: 'var(--text-2)' }}>{fmtDate(fr.submitted_at)}</span>
                  </div>
                  {fr.pm_response && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8, fontSize: 12 }}>
                      <span style={{ color: 'var(--text-2)' }}>Respuesta PM: </span>{fr.pm_response}
                      {fr.estimated_cost && <span style={{ color: 'var(--warning)', marginLeft: 12 }}>💶 {fmtCurrency(fr.estimated_cost)}</span>}
                      {fr.estimated_delivery_weeks && <span style={{ color: 'var(--accent)', marginLeft: 12 }}>📅 {fr.estimated_delivery_weeks} semanas</span>}
                    </div>
                  )}
                  {fr.client_approved === true && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--success)' }}>✓ Cliente aprobó el {fmtDate(fr.client_approved_at)}</div>}
                  {fr.client_approved === false && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>✗ Cliente rechazó</div>}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                  <StatusBadge status={fr.status} cfg={FR_STATUS_CFG} />
                  {['new', 'reviewing'].includes(fr.status) && (
                    <Button size="sm" onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                      💬 Responder
                    </Button>
                  )}
                  {fr.status === 'approved' && (
                    <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                      🚀 Iniciar desarrollo
                    </Button>
                  )}
                  {fr.status === 'in_development' && (
                    <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                      ✓ Completada
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {responding && (
        <Modal open title={`Responder a: ${responding.title}`} onClose={() => setResponding(null)} width={520}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>Respuesta / Análisis *</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical' }} placeholder="Describe el análisis y la solución propuesta..." /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div><label style={ls}>Horas estimadas</label><input type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>Coste estimado €</label><input type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>Semanas entrega</label><input type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={fs} placeholder="0" /></div>
            </div>
            <div><label style={ls}>Estado</label>
              <select value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} style={fs}>
                <option value="estimated">Presupuestada (pendiente aprobación cliente)</option>
                <option value="reviewing">En revisión interna</option>
                <option value="rejected">Rechazada (no factible)</option>
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setResponding(null)}>Cancelar</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>Enviar respuesta</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Messages Tab ──────────────────────────────────────────────────────────────
function MessagesTab({ projectId }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [replyTo, setReplyTo] = useState(null)
  const [newMsg, setNewMsg] = useState('')
  const [newSubject, setNewSubject] = useState('')
  const [showNew, setShowNew] = useState(false)

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['portal-messages', projectId],
    queryFn: () => api.get('/portal/messages/team', { params: { project_id: projectId } }).then(r => r.data),
    enabled: !!projectId,
    refetchInterval: 30000,
  })

  const { mutate: sendMsg } = useMutation({
    mutationFn: (data) => api.post('/portal/messages/team', data),
    onSuccess: () => { qc.invalidateQueries(['portal-messages', projectId]); setNewMsg(''); setNewSubject(''); setReplyTo(null); setShowNew(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const unread = messages.filter(m => !m.is_read_by_team && m.sender_type === 'client').length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
          {messages.length} conversacion(es)
          {unread > 0 && <span style={{ marginLeft: 8, background: 'var(--danger)', color: '#fff', borderRadius: 20, padding: '1px 8px', fontSize: 11, fontWeight: 700 }}>{unread} sin leer</span>}
        </div>
        <Button onClick={() => setShowNew(true)} icon="✉️">Nuevo mensaje</Button>
      </div>

      {isLoading ? <Spinner /> : messages.length === 0 ? (
        <EmptyState icon="💬" title="Sin mensajes" description="Inicia una conversación con el cliente" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {messages.map(thread => (
            <div key={thread.id} style={{ background: 'var(--surface-2)', border: `1px solid ${!thread.is_read_by_team && thread.sender_type === 'client' ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)'}`, borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ padding: '14px 18px', borderBottom: thread.replies?.length > 0 ? '1px solid #1e2d4530' : 'none' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    {thread.subject && <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{thread.subject}</div>}
                    <p style={{ fontSize: 13, color: 'var(--text-1)', margin: '0 0 6px' }}>{thread.body}</p>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                      {thread.sender_type === 'client' ? '👤' : '💼'} {thread.sender_name} · {thread.created_at}
                    </div>
                  </div>
                  {!thread.is_read_by_team && thread.sender_type === 'client' && (
                    <span style={{ fontSize: 10, background: 'var(--warning-bg)', color: 'var(--warning)', border: '1px solid #ffb80040', borderRadius: 20, padding: '2px 8px', flexShrink: 0 }}>Sin leer</span>
                  )}
                </div>
              </div>
              {thread.replies?.map(r => (
                <div key={r.id} style={{ padding: '10px 18px 10px 40px', borderBottom: '1px solid #1e2d4520', background: r.sender_type === 'team' ? 'var(--surface-1)' : 'transparent' }}>
                  <p style={{ fontSize: 13, color: 'var(--text-1)', margin: '0 0 4px' }}>{r.body}</p>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.sender_type === 'client' ? '👤' : '💼'} {r.sender_name} · {r.created_at}</div>
                </div>
              ))}
              <div style={{ padding: '10px 18px' }}>
                <button onClick={() => setReplyTo(thread)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '5px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                  ↩ Responder
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(showNew || replyTo) && (
        <Modal open title={replyTo ? `Responder a: ${replyTo.subject || replyTo.body.slice(0, 40)}` : 'Nuevo mensaje al cliente'} onClose={() => { setShowNew(false); setReplyTo(null) }} width={500}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {!replyTo && <div><label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }}>Asunto</label>
              <input value={newSubject} onChange={e => setNewSubject(e.target.value)} style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} /></div>}
            <textarea value={newMsg} onChange={e => setNewMsg(e.target.value)} rows={4} placeholder="Escribe tu mensaje..."
              style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box', width: '100%' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => { setShowNew(false); setReplyTo(null) }}>Cancelar</Button>
              <Button onClick={() => sendMsg({ project_id: projectId, body: newMsg, subject: newSubject || undefined, parent_id: replyTo?.id, thread_id: replyTo?.thread_id })} disabled={!newMsg}>Enviar</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────
function DocumentsTab({ projectId }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [docForm, setDocForm] = useState({ title: '', description: '', category: 'deliverable', file_url: '', file_name: '', requires_signature: false })
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs', projectId],
    queryFn: () => api.get('/portal/documents/team', { params: { project_id: projectId } }).then(r => r.data),
    enabled: !!projectId,
  })
  const { mutate: addDoc } = useMutation({
    mutationFn: (data) => api.post(`/portal/documents?project_id=${projectId}`, data),
    onSuccess: () => { qc.invalidateQueries(['portal-docs', projectId]); setShowAdd(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const CAT_LABELS = { contract: '📋 Contrato', deliverable: '📦 Entregable', meeting_notes: '📝 Acta reunión', report: '📊 Informe', other: '📄 Otro' }
  const CAT_COLORS = { contract: 'var(--purple)', deliverable: 'var(--success)', meeting_notes: 'var(--accent)', report: 'var(--warning)', other: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{docs.length} documento(s) compartidos</div>
        <Button onClick={() => setShowAdd(true)} icon="＋">Añadir documento</Button>
      </div>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState icon="📄" title="Sin documentos" description="Comparte documentos con el cliente: contratos, entregables, actas..." />
      ) : (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          {docs.map((doc, i) => {
            const color = CAT_COLORS[doc.category] || 'var(--text-2)'
            return (
              <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', borderBottom: i < docs.length - 1 ? '1px solid #1e2d4530' : 'none' }}>
                <span style={{ fontSize: 22, flexShrink: 0 }}>{CAT_LABELS[doc.category]?.split(' ')[0] || '📄'}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{doc.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                    <span style={{ color, fontWeight: 600 }}>{CAT_LABELS[doc.category]?.replace(/^\S+\s/, '') || doc.category}</span>
                    {doc.file_name && ` · ${doc.file_name}`}
                    {doc.created_at && ` · ${fmtDate(doc.created_at)}`}
                  </div>
                </div>
                {doc.requires_signature && (
                  <span style={{ fontSize: 11, color: doc.signed_by_client ? 'var(--success)' : 'var(--warning)', background: doc.signed_by_client ? 'var(--success-bg)' : 'var(--warning-bg)', border: `1px solid ${doc.signed_by_client ? 'var(--success-border)' : 'var(--warning-border)'}`, borderRadius: 20, padding: '2px 8px' }}>
                    {doc.signed_by_client ? '✓ Firmado' : '⏳ Pendiente firma'}
                  </span>
                )}
                {doc.file_url && (
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer" style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, textDecoration: 'none' }}>
                    ⬇ Descargar
                  </a>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showAdd && (
        <Modal open title="Añadir documento al portal" onClose={() => setShowAdd(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>Título *</label><input value={docForm.title} onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))} style={fs} /></div>
            <div><label style={ls}>Categoría</label>
              <select value={docForm.category} onChange={e => setDocForm(f => ({ ...f, category: e.target.value }))} style={fs}>
                {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div><label style={ls}>URL del archivo</label><input value={docForm.file_url} onChange={e => setDocForm(f => ({ ...f, file_url: e.target.value }))} style={fs} placeholder="https://..." /></div>
            <div><label style={ls}>Nombre del archivo</label><input value={docForm.file_name} onChange={e => setDocForm(f => ({ ...f, file_name: e.target.value }))} style={fs} placeholder="contrato_v1.pdf" /></div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={docForm.requires_signature} onChange={e => setDocForm(f => ({ ...f, requires_signature: e.target.checked }))} />
              Requiere firma del cliente
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancelar</Button>
              <Button onClick={() => addDoc(docForm)} disabled={!docForm.title}>Compartir</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}


// ── Wiki Portal Tab (operador: controla qué páginas wiki ve el cliente) ───────
function WikiPortalTab({ projectId }) {
  const { data: spaces = [] } = useQuery({
    queryKey: ['wiki-spaces-portal', projectId],
    queryFn: () => api.get('wiki/spaces').then(r => r.data.filter(s => !projectId || s.project_id === projectId || !s.project_id)),
  })
  const [selectedSpace, setSelectedSpace] = React.useState('')
  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['wiki-pages-portal-op', selectedSpace],
    queryFn: () => api.get(`wiki/spaces/${selectedSpace}/pages`).then(r => r.data),
    enabled: !!selectedSpace,
  })
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: setVis } = useMutation({
    mutationFn: ({ id, visibility }) => api.patch(`wiki/pages/${id}`, { visibility }),
    onSuccess: () => qc.invalidateQueries(['wiki-pages-portal-op', selectedSpace]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const VIS = {
    team:   { label: '🔒 Solo equipo', color: 'var(--text-2)' },
    portal: { label: '🌐 Portal cliente', color: 'var(--accent)' },
    public: { label: '🌍 Público', color: 'var(--success)' },
  }

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10, padding: 'var(--space-3) var(--space-4)', marginBottom: 20, fontSize: 13, color: 'var(--text-2)' }}>
        <strong style={{ color: 'var(--accent)' }}>ℹ Visibilidad wiki para el cliente</strong>
        {' '}— Aquí controlas qué páginas wiki son visibles en el Portal Cliente.
        Las páginas marcadas como <strong style={{ color: 'var(--accent)' }}>🌐 Portal cliente</strong> aparecerán
        en la sección «Base de conocimiento» del portal externo.
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select value={selectedSpace} onChange={e => setSelectedSpace(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', flex: 1 }}>
          <option value="">Selecciona un espacio wiki...</option>
          {spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      {isLoading && <Spinner />}
      {selectedSpace && !isLoading && pages.length === 0 && (
        <EmptyState icon="📚" title="Sin páginas" description="Este espacio wiki no tiene páginas aún" />
      )}
      {pages.length > 0 && (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          {pages.map((page, i) => (
            <div key={page.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 18px', borderBottom: i < pages.length - 1 ? '1px solid #1e2d4530' : 'none' }}>
              <span style={{ fontSize: 16 }}>📄</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{page.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{page.slug}</div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {Object.entries(VIS).map(([val, cfg]) => (
                  <button key={val} onClick={() => setVis({ id: page.id, visibility: val })}
                    style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${(page.visibility || 'team') === val ? cfg.color + '60' : 'var(--surface-4)'}`, background: (page.visibility || 'team') === val ? cfg.color + '15' : 'transparent', color: (page.visibility || 'team') === val ? cfg.color : 'var(--text-3)', fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {cfg.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stats panel ───────────────────────────────────────────────────────────────
function StatsPanel({ projectId }) {
  const { data: stats } = useQuery({
    queryKey: ['portal-stats', projectId],
    queryFn: () => api.get(`/portal/stats/${projectId}`).then(r => r.data),
    enabled: !!projectId,
    refetchInterval: 30000,
  })
  if (!stats) return null
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
      {[
        { label: 'Contactos cliente', value: stats.client_count, color: 'var(--text-2)', icon: '👤' },
        { label: 'Mensajes sin leer', value: stats.unread_messages, color: stats.unread_messages > 0 ? 'var(--warning)' : 'var(--text-2)', icon: '💬' },
        { label: 'FRs pendientes', value: stats.fr_pending_review, color: stats.fr_pending_review > 0 ? 'var(--danger)' : 'var(--text-2)', icon: '💡' },
        { label: 'UATs pendientes', value: stats.uat_pending, color: stats.uat_pending > 0 ? 'var(--accent)' : 'var(--text-2)', icon: '🧪' },
        { label: 'Satisfacción media', value: stats.avg_satisfaction ? `${stats.avg_satisfaction}/5` : '—', color: 'var(--success)', icon: '⭐' },
        { label: 'NPS medio', value: stats.avg_nps ?? '—', color: stats.avg_nps >= 8 ? 'var(--success)' : stats.avg_nps >= 6 ? 'var(--warning)' : 'var(--danger)', icon: '📊' },
      ].map(({ label, value, color, icon }) => (
        <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 'var(--space-3) var(--space-4)', flex: 1, minWidth: 120 }}>
          <div style={{ fontSize: 18, marginBottom: 4 }}>{icon}</div>
          <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Space Mono', monospace", color }}>{value}</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{label}</div>
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ClientPortalPage() {
  const _t = useAppT()
  const [tab, setTab] = useState('clients')
  const [selectedProject, setSelectedProject] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  const TABS = [
    { id: 'clients',  label: '👤 Contactos' },
    { id: 'uat',      label: '🧪 UAT' },
    { id: 'requests', label: '💡 Solicitudes' },
    { id: 'messages', label: '💬 Mensajes' },
    { id: 'documents',label: '📄 Documentos' },
    { id: 'wiki',     label: '📚 Wiki' },
  ]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title="Portal del Cliente"
        subtitle="Gestión del acceso externo, UATs, solicitudes y comunicación"
        actions={
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
            style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer', minWidth: 240 }}>
            <option value="">Seleccionar proyecto...</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        }
      />

      {selectedProject && <StatsPanel projectId={selectedProject} />}

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '8px 18px', borderRadius: 8, border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {!selectedProject ? (
        <EmptyState icon="🌐" title="Selecciona un proyecto" description="Elige un proyecto para gestionar su portal de cliente" />
      ) : (
        <>
          {tab === 'clients'   && <ClientUsersTab projectId={selectedProject} />}
          {tab === 'uat'       && <UATTab projectId={selectedProject} />}
          {tab === 'requests'  && <FeatureRequestsTab projectId={selectedProject} />}
          {tab === 'messages'  && <MessagesTab projectId={selectedProject} />}
          {tab === 'documents' && <DocumentsTab projectId={selectedProject} />}
          {tab === 'wiki'      && <WikiPortalTab projectId={selectedProject} />}
        </>
      )}
    </div>
  )
}