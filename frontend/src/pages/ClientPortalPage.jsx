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
import { z } from 'zod'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { fmtDate, fmtCurrency, extractErr} from '../utils/helpers'
import { STATUS_CFG, FR_STATUS_CFG } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const uatSessionSchema = z.object({
  title: z.string().trim().min(1, 'El titulo es obligatorio'),
  description: z.string().optional(),
  deliverable_id: z.string().optional(),
  test_environment: z.string().optional(),
  test_credentials: z.string().optional(),
  test_guide_url: z.string().optional(),
  available_from: z.string().optional(),
  deadline: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.available_from && values.deadline && values.deadline < values.available_from) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['deadline'],
      message: 'La fecha limite no puede ser anterior a la fecha disponible desde',
    })
  }
})

const portalClientCreateSchema = z.object({
  full_name: z.string().trim().min(1, 'El nombre es obligatorio'),
  email: z.string().trim().email('Email invalido'),
  job_title: z.string().optional(),
  company: z.string().optional(),
  phone: z.string().optional(),
  password: z.string().min(1, 'La contrasena es obligatoria'),
  can_approve_deliverables: z.boolean(),
  can_request_changes: z.boolean(),
  can_view_budget: z.boolean(),
  can_view_team: z.boolean(),
})

const portalClientEditSchema = z.object({
  full_name: z.string().trim().min(1, 'El nombre es obligatorio'),
  email: z.string().trim().email('Email invalido'),
  job_title: z.string().optional(),
  company: z.string().optional(),
  phone: z.string().optional(),
  password: z.string().optional(),
  project_ids: z.array(z.union([z.string(), z.number()])),
  can_approve_deliverables: z.boolean(),
  can_request_changes: z.boolean(),
  can_view_budget: z.boolean(),
  can_view_team: z.boolean(),
})


// STATUS_CFG y FR_STATUS_CFG centralizados en constants/sharedStatus.js

function StatusBadge({ status, cfg }) {
  const c = cfg[status] || { label: status, color: 'var(--text-2)' }
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: c.color + '20', color: c.color, border: `1px solid ${c.color}40`, textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{c.label}</span>
}

// ── Client Users Management ───────────────────────────────────────────────────
function ClientUsersTab({ projectId }) {
  const t = useAppT()
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
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const { mutate: toggleActive } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/portal/clients/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['portal-clients', projectId]),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{clients.length} {t('client_portal.contacts_count')}</div>
        <Button onClick={() => setShowCreate(true)} icon="＋">{t('client_portal.add_contact')}</Button>
      </div>
      {isLoading ? <Spinner /> : clients.length === 0 ? (
        <EmptyState icon="👤" title={t('client_portal.empty_contacts_title')} description={t('client_portal.empty_contacts_desc')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {clients.map(c => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', background: 'var(--surface-2)', border: `1px solid ${c.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, opacity: c.is_active ? 1 : 0.6 }}>
              <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'linear-gradient(135deg, #00d4ff, #7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                {c.full_name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{c.full_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{c.job_title || t('client_portal.role_unknown')} · {c.company || c.project_name} · {c.email}</div>
                <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: 11 }}>
                  {c.can_approve_deliverables && <span style={{ color: 'var(--success)' }}>{`✓ ${t('client_portal.perm_approve')}`}</span>}
                  {c.can_request_changes && <span style={{ color: 'var(--accent)' }}>{`✓ ${t('client_portal.perm_request')}`}</span>}
                  {c.can_view_budget && <span style={{ color: 'var(--warning)' }}>{`✓ ${t('client_portal.perm_view_budget')}`}</span>}
                </div>
              </div>
              {c.last_login && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{`${t('client_portal.last_access')}: ${fmtDate(c.last_login)}`}</div>}
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setEditingClient(c)}
                  style={{ background: 'none', border: '1px solid var(--accent-glow)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                  {`✏ ${t('client_portal.edit')}`}
                </button>
                <button onClick={() => toggleActive({ id: c.id, active: !c.is_active })}
                  style={{ background: 'none', border: `1px solid ${c.is_active ? 'var(--warning-border)' : 'var(--success-border)'}`, borderRadius: 6, padding: '4px 10px', color: c.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                  {c.is_active ? `⏸ ${t('client_portal.suspend')}` : `▶ ${t('client_portal.activate')}`}
                </button>
                <button onClick={() => { openConfirmGlobal({ message: t('client_portal.delete_contact_confirm'), onConfirm: () => deleteClient(c.id), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-bg)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
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
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ full_name: '', email: '', job_title: '', company: '', phone: '', password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: true, can_view_team: false })
  const [extraProjectIds, setExtraProjectIds] = useState([]) // additional projects beyond projectId
  const validation = useFormValidation(portalClientCreateSchema)
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => api.post('/portal/clients', data),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries(['portal-clients', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const allProjectIds = [...new Set([projectId, ...extraProjectIds].filter(Boolean))]

  const handleSubmit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ ...result.data, project_id: projectId, project_ids: allProjectIds })
  }

  return (
    <Modal open title={t('client_portal.create_contact_title')} onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('client_portal.label_full_name')} *</label>
          <input value={form.full_name} onChange={set('full_name')} style={validation.inputStyle(fs, 'full_name')} />
          {validation.errors.full_name && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.full_name}</p>}
        </div>
        <div>
          <label style={ls}>{t('client_portal.label_email')} *</label>
          <input type="email" value={form.email} onChange={set('email')} style={validation.inputStyle(fs, 'email')} />
          {validation.errors.email && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.email}</p>}
        </div>
        <div><label style={ls}>{t('client_portal.label_job_title')}</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder={t('client_portal.label_job_title')} /></div>
        <div><label style={ls}>{t('client_portal.label_company')}</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>{t('client_portal.label_phone')}</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('client_portal.label_password')} *</label>
          <input type="password" value={form.password} onChange={set('password')} style={validation.inputStyle(fs, 'password')} placeholder={t('client_portal.password_placeholder')} />
          {validation.errors.password && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.password}</p>}
        </div>
        {allProjects.length > 1 && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.additional_projects_access')}</label>
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
          <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.permissions')}</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[['can_approve_deliverables', t('client_portal.perm_approve_desc')],['can_request_changes', t('client_portal.perm_request_desc')],['can_view_budget', t('client_portal.perm_budget_desc')],['can_view_team', t('client_portal.perm_team_desc')]].map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={isPending} loading={isPending}>
            {isPending ? t('client_portal.creating') : t('client_portal.create_access')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── UAT Management ────────────────────────────────────────────────────────────
function EditClientModal({ client, onClose, onSaved }) {
  const t = useAppT()
  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data) => api.patch(`/portal/clients/${client.id}`, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
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
  const validation = useFormValidation(portalClientEditSchema)

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const handleSave = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    const data = { ...result.data }
    if (!data.password) delete data.password  // Only send password if changed
    mutate(data)
  }

  return (
    <Modal open title={`${t('client_portal.edit')} — ${client.full_name}`} onClose={onClose} width={560}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('client_portal.label_full_name')} *</label>
          <input value={form.full_name} onChange={set('full_name')} style={validation.inputStyle(fs, 'full_name')} />
          {validation.errors.full_name && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.full_name}</p>}
        </div>
        <div>
          <label style={ls}>{t('client_portal.label_email')} *</label>
          <input type="email" value={form.email} onChange={set('email')} style={validation.inputStyle(fs, 'email')} />
          {validation.errors.email && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.email}</p>}
        </div>
        <div><label style={ls}>{t('client_portal.label_job_title')}</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder={t('client_portal.label_job_title')} /></div>
        <div><label style={ls}>{t('client_portal.label_company')}</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>{t('client_portal.label_phone')}</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('client_portal.additional_projects_access')}</label>
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
          <label style={ls}>{t('client_portal.label_password')}</label>
          <input type="password" value={form.password} onChange={set('password')} style={fs} placeholder={t('client_portal.password_placeholder')} />
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{t('client_portal.password_placeholder')}</div>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.permissions')}</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              ['can_approve_deliverables', t('client_portal.perm_approve_desc')],
              ['can_request_changes', t('client_portal.perm_request_desc')],
              ['can_view_budget', t('client_portal.perm_budget_desc')],
              ['can_view_team', t('client_portal.perm_team_desc')],
            ].map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.full_name || !form.email}>
            {isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}


function UATTab({ projectId }) {
  const t = useAppT()
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
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{sessions.length} {t('client_portal.uat_sessions_count')}</div>
        {projectId && <Button onClick={() => setShowCreate(true)} icon="＋">{t('client_portal.uat_new_session')}</Button>}
      </div>
      {isLoading ? <Spinner /> : sessions.length === 0 ? (
        <EmptyState icon="🧪" title={t('client_portal.uat_empty_title')} description={t('client_portal.uat_empty_desc')} />
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
                    {s.overdue && <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700 }}>{`⚠ ${t('client_portal.uat_overdue')}`}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {s.deadline && `${t('client_portal.uat_deadline')}: ${fmtDate(s.deadline)} · `}
                    {s.stats.total} {t('client_portal.uat_cases')} · {s.stats.passed} ✓ · {s.stats.failed} ✗
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
                  {`🐛 ${s.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open_issues')}`}
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
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ title: '', description: '', deliverable_id: '', test_environment: '', test_credentials: '', test_guide_url: '', available_from: '', deadline: '' })
  const [testCases, setTestCases] = useState([{ title: '', steps: '', expected_result: '' }])
  const validation = useFormValidation(uatSessionSchema)
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: async (data) => {
      const res = await api.post(`/portal/uat/${projectId}`, data.form)
      for (const tc of data.testCases.filter(t => t.title)) {
        await api.post(`/portal/uat/${res.data.id}/test-cases`, { title: tc.title, steps: tc.steps, expected_result: tc.expected_result, order: data.testCases.indexOf(tc) })
      }
      return res
    },
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries(['uat-team', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ form: result.data, testCases })
  }

  return (
    <Modal open title={t('client_portal.uat_modal_new_title')} onClose={onClose} width={680}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div>
            <label style={ls}>{t('client_portal.uat_label_title')} *</label>
            <input value={form.title} onChange={set('title')} style={validation.inputStyle(fs, 'title')} placeholder={t('client_portal.uat_placeholder_title')} />
            {validation.errors.title && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.title}</p>}
          </div>
          <div><label style={ls}>{t('client_portal.uat_label_deliverable')}</label>
            <select value={form.deliverable_id} onChange={set('deliverable_id')} style={fs}>
              <option value="">{t('client_portal.uat_unlinked')}</option>
              {deliverables.map(d => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </select>
          </div>
        </div>
        <div><label style={ls}>{t('client_portal.uat_label_description')}</label><textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label style={ls}>{t('client_portal.uat_label_test_env_url')}</label><input value={form.test_environment} onChange={set('test_environment')} style={fs} placeholder={t('client_portal.uat_placeholder_test_env_url')} /></div>
          <div><label style={ls}>{t('client_portal.uat_label_test_credentials')}</label><input value={form.test_credentials} onChange={set('test_credentials')} style={fs} placeholder={t('client_portal.uat_placeholder_test_credentials')} /></div>
          <div><label style={ls}>{t('client_portal.uat_label_available_from')}</label><input type="date" value={form.available_from} onChange={set('available_from')} style={validation.inputStyle(fs, 'available_from')} /></div>
          <div>
            <label style={ls}>{t('client_portal.uat_label_deadline')}</label>
            <input type="date" value={form.deadline} onChange={set('deadline')} style={validation.inputStyle(fs, 'deadline')} />
            {validation.errors.deadline && <p style={{ marginTop: 4, fontSize: 11, color: 'var(--danger)' }}>{validation.errors.deadline}</p>}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 10 }}>{t('client_portal.uat_test_cases')}</div>
          {testCases.map((tc, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 2fr 30px', gap: 8, marginBottom: 8, padding: 10, background: 'var(--surface-3)', borderRadius: 8 }}>
              <input value={tc.title} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, title: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_title_placeholder').replace('{index}', String(i + 1))} />
              <input value={tc.steps} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, steps: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_steps_placeholder')} />
              <input value={tc.expected_result} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, expected_result: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_expected_placeholder')} />
              <button onClick={() => setTestCases(tcs => tcs.filter((_, j) => j !== i))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 16 }}>×</button>
            </div>
          ))}
          <button onClick={() => setTestCases(tcs => [...tcs, { title: '', steps: '', expected_result: '' }])}
            style={{ background: 'none', border: '1px dashed #1e2d45', borderRadius: 8, padding: '8px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', width: '100%' }}>
            {`＋ ${t('client_portal.uat_add_test_case')}`}
          </button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('client_portal.uat_creating_session') : t('client_portal.uat_create_session')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function UATDetailModal({ session: initialSession, onClose }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: updateIssue } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/portal/uat/issues/${id}?status=${status}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['uat-team'], exact: false }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const SEV_COLORS = { low: 'var(--success)', medium: 'var(--accent)', high: 'var(--warning)', blocker: 'var(--danger)' }

  return (
    <Modal open title={`${initialSession.code} — ${initialSession.title}`} onClose={onClose} width={700}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <StatusBadge status={initialSession.status} cfg={STATUS_CFG} />
        {initialSession.test_environment && <a href={initialSession.test_environment} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none' }}>{`🔗 ${t('client_portal.uat_detail_test_env')}`}</a>}
        {initialSession.deadline && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{`${t('client_portal.uat_deadline')}: ${fmtDate(initialSession.deadline)}`}</span>}
      </div>

      {initialSession.client_notes && (
        <div style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase' }}>{t('client_portal.uat_detail_client_notes')}</div>
          <p style={{ fontSize: 13, color: 'var(--text-1)' }}>{initialSession.client_notes}</p>
        </div>
      )}

      {/* Test cases */}
      {initialSession.test_cases.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            {`${t('client_portal.uat_detail_cases_title')} (${initialSession.stats.passed}/${initialSession.stats.total} ${t('client_portal.uat_detail_approved')})`}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {initialSession.test_cases.map(tc => {
              const color = tc.status === 'passed' ? 'var(--success)' : tc.status === 'failed' ? 'var(--danger)' : 'var(--text-2)'
              return (
                <div key={tc.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${color}30`, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{tc.title}</div>
                      {tc.expected_result && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{`${t('client_portal.uat_expected')}: ${tc.expected_result}`}</div>}
                      {tc.actual_result && <div style={{ fontSize: 12, color: color, marginTop: 4 }}>{`${t('client_portal.uat_result')}: ${tc.actual_result}`}</div>}
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color, background: color + '20', border: `1px solid ${color}40`, borderRadius: 20, padding: '2px 8px', textTransform: 'uppercase', flexShrink: 0 }}>
                      {tc.status === 'passed' ? '✓ OK' : tc.status === 'failed' ? '✗ KO' : `— ${t('client_portal.uat_pending')}`}
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
            {`${t('client_portal.uat_issues_title')} (${initialSession.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open')})`}
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
                        <option value="open">{t('client_portal.uat_issue_open')}</option>
                        <option value="fixed">{t('client_portal.uat_issue_fixed')}</option>
                        <option value="deferred">{t('client_portal.uat_issue_deferred')}</option>
                        <option value="wontfix">{t('client_portal.uat_issue_wontfix')}</option>
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
        <Button variant="secondary" onClick={onClose}>{t('client_portal.close')}</Button>
      </div>
    </Modal>
  )
}

// ── Feature Requests Tab ──────────────────────────────────────────────────────
function FeatureRequestsTab({ projectId }) {
  const t = useAppT()
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
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.post(`/portal/feature-requests/${id}/respond`, { status }),
    onSuccess: () => qc.invalidateQueries(['portal-frs', projectId]),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  return (
    <div>
      {isLoading ? <Spinner /> : frs.length === 0 ? (
        <EmptyState icon="💡" title={t('client_portal.fr_empty_title')} description={t('client_portal.fr_empty_desc')} />
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
                      <span style={{ color: 'var(--text-2)' }}>{`${t('client_portal.fr_pm_response')}: `}</span>{fr.pm_response}
                      {fr.estimated_cost && <span style={{ color: 'var(--warning)', marginLeft: 12 }}>💶 {fmtCurrency(fr.estimated_cost)}</span>}
                      {fr.estimated_delivery_weeks && <span style={{ color: 'var(--accent)', marginLeft: 12 }}>📅 {fr.estimated_delivery_weeks} semanas</span>}
                    </div>
                  )}
                  {fr.client_approved === true && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--success)' }}>{`✓ ${t('client_portal.fr_client_approved')} ${fmtDate(fr.client_approved_at)}`}</div>}
                  {fr.client_approved === false && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>{`✗ ${t('client_portal.fr_client_rejected')}`}</div>}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                  <StatusBadge status={fr.status} cfg={FR_STATUS_CFG} />
                  {['new', 'reviewing'].includes(fr.status) && (
                    <Button size="sm" onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                      {`💬 ${t('client_portal.fr_respond')}`}
                    </Button>
                  )}
                  {fr.status === 'approved' && (
                    <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                      {`🚀 ${t('client_portal.fr_start_dev')}`}
                    </Button>
                  )}
                  {fr.status === 'in_development' && (
                    <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                      {`✓ ${t('client_portal.fr_completed')}`}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {responding && (
        <Modal open title={`${t('client_portal.fr_modal_title')}: ${responding.title}`} onClose={() => setResponding(null)} width={520}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>{t('client_portal.fr_label_response')} *</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical' }} placeholder={t('client_portal.fr_response_placeholder')} /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div><label style={ls}>{t('client_portal.fr_label_hours')}</label><input type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>{t('client_portal.fr_label_cost')} €</label><input type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>{t('client_portal.fr_label_weeks')}</label><input type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={fs} placeholder="0" /></div>
            </div>
            <div><label style={ls}>{t('client_portal.fr_label_status')}</label>
              <select value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} style={fs}>
                <option value="estimated">{t('client_portal.fr_status_estimated')}</option>
                <option value="reviewing">{t('client_portal.fr_status_reviewing')}</option>
                <option value="rejected">{t('client_portal.fr_status_rejected')}</option>
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setResponding(null)}>{t('common.cancel')}</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>{t('client_portal.fr_send_response')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Messages Tab ──────────────────────────────────────────────────────────────
function MessagesTab({ projectId }) {
  const t = useAppT()
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
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const unread = messages.filter(m => !m.is_read_by_team && m.sender_type === 'client').length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
          {messages.length} {t('client_portal.messages_count')}
          {unread > 0 && <span style={{ marginLeft: 8, background: 'var(--danger)', color: '#fff', borderRadius: 20, padding: '1px 8px', fontSize: 11, fontWeight: 700 }}>{unread} {t('client_portal.messages_unread')}</span>}
        </div>
        <Button onClick={() => setShowNew(true)} icon="✉️">{t('client_portal.messages_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : messages.length === 0 ? (
        <EmptyState icon="💬" title={t('client_portal.messages_empty_title')} description={t('client_portal.messages_empty_desc')} />
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
                    <span style={{ fontSize: 10, background: 'var(--warning-bg)', color: 'var(--warning)', border: '1px solid #ffb80040', borderRadius: 20, padding: '2px 8px', flexShrink: 0 }}>{t('client_portal.messages_badge_unread')}</span>
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
                  {`↩ ${t('client_portal.messages_reply')}`}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(showNew || replyTo) && (
        <Modal open title={replyTo ? `${t('client_portal.messages_modal_reply_to')}: ${replyTo.subject || replyTo.body.slice(0, 40)}` : t('client_portal.messages_modal_new_to_client')} onClose={() => { setShowNew(false); setReplyTo(null) }} width={500}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {!replyTo && <div><label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }}>{t('client_portal.messages_subject')}</label>
              <input value={newSubject} onChange={e => setNewSubject(e.target.value)} style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }} /></div>}
            <textarea value={newMsg} onChange={e => setNewMsg(e.target.value)} rows={4} placeholder={t('client_portal.messages_body_placeholder')}
              style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box', width: '100%' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => { setShowNew(false); setReplyTo(null) }}>{t('common.cancel')}</Button>
              <Button onClick={() => sendMsg({ project_id: projectId, body: newMsg, subject: newSubject || undefined, parent_id: replyTo?.id, thread_id: replyTo?.thread_id })} disabled={!newMsg}>{t('client_portal.send')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────
function DocumentsTab({ projectId }) {
  const t = useAppT()
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
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const CAT_LABELS = {
    contract: `📋 ${t('client_portal.docs_contract')}`,
    deliverable: `📦 ${t('client_portal.docs_deliverable')}`,
    meeting_notes: `📝 ${t('client_portal.docs_meeting_notes')}`,
    report: `📊 ${t('client_portal.docs_report')}`,
    other: `📄 ${t('client_portal.docs_other')}`,
  }
  const CAT_COLORS = { contract: 'var(--purple)', deliverable: 'var(--success)', meeting_notes: 'var(--accent)', report: 'var(--warning)', other: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{docs.length} {t('client_portal.docs_count')}</div>
        <Button onClick={() => setShowAdd(true)} icon="＋">{t('client_portal.docs_add')}</Button>
      </div>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState icon="📄" title={t('client_portal.docs_empty_title')} description={t('client_portal.docs_empty_desc')} />
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
                    {doc.signed_by_client ? `✓ ${t('client_portal.docs_signed')}` : `⏳ ${t('client_portal.docs_pending_signature')}`}
                  </span>
                )}
                {doc.file_url && (
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer" style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, textDecoration: 'none' }}>
                    {`⬇ ${t('client_portal.docs_download')}`}
                  </a>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showAdd && (
        <Modal open title={t('client_portal.docs_modal_title')} onClose={() => setShowAdd(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>{t('client_portal.docs_label_title')} *</label><input value={docForm.title} onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))} style={fs} /></div>
            <div><label style={ls}>{t('client_portal.docs_label_category')}</label>
              <select value={docForm.category} onChange={e => setDocForm(f => ({ ...f, category: e.target.value }))} style={fs}>
                {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div><label style={ls}>{t('client_portal.docs_label_file_url')}</label><input value={docForm.file_url} onChange={e => setDocForm(f => ({ ...f, file_url: e.target.value }))} style={fs} placeholder="https://..." /></div>
            <div><label style={ls}>{t('client_portal.docs_label_file_name')}</label><input value={docForm.file_name} onChange={e => setDocForm(f => ({ ...f, file_name: e.target.value }))} style={fs} placeholder={t('client_portal.docs_placeholder_file_name')} /></div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={docForm.requires_signature} onChange={e => setDocForm(f => ({ ...f, requires_signature: e.target.checked }))} />
              {t('client_portal.docs_requires_signature')}
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setShowAdd(false)}>{t('common.cancel')}</Button>
              <Button onClick={() => addDoc(docForm)} disabled={!docForm.title}>{t('client_portal.docs_share')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}


// ── Wiki Portal Tab (operador: controla qué páginas wiki ve el cliente) ───────
function WikiPortalTab({ projectId }) {
  const t = useAppT()
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
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const VIS = {
    team:   { label: `🔒 ${t('client_portal.wiki_vis_team')}`, color: 'var(--text-2)' },
    portal: { label: `🌐 ${t('client_portal.wiki_vis_portal')}`, color: 'var(--accent)' },
    public: { label: `🌍 ${t('client_portal.wiki_vis_public')}`, color: 'var(--success)' },
  }

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10, padding: 'var(--space-3) var(--space-4)', marginBottom: 20, fontSize: 13, color: 'var(--text-2)' }}>
        <strong style={{ color: 'var(--accent)' }}>{`ℹ ${t('client_portal.wiki_info_title')}`}</strong>
        {' '}— {t('client_portal.wiki_info_desc')}
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select value={selectedSpace} onChange={e => setSelectedSpace(e.target.value)}
          style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', flex: 1 }}>
          <option value="">{t('client_portal.wiki_select_space')}</option>
          {spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      {isLoading && <Spinner />}
      {selectedSpace && !isLoading && pages.length === 0 && (
        <EmptyState icon="📚" title={t('client_portal.wiki_empty_title')} description={t('client_portal.wiki_empty_desc')} />
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
  const t = useAppT()
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
        { label: t('client_portal.stat_contacts'), value: stats.client_count, color: 'var(--text-2)', icon: '👤' },
        { label: t('client_portal.stat_unread_messages'), value: stats.unread_messages, color: stats.unread_messages > 0 ? 'var(--warning)' : 'var(--text-2)', icon: '💬' },
        { label: t('client_portal.stat_pending_requests'), value: stats.fr_pending_review, color: stats.fr_pending_review > 0 ? 'var(--danger)' : 'var(--text-2)', icon: '💡' },
        { label: t('client_portal.stat_pending_uat'), value: stats.uat_pending, color: stats.uat_pending > 0 ? 'var(--accent)' : 'var(--text-2)', icon: '🧪' },
        { label: t('client_portal.stat_avg_satisfaction'), value: stats.avg_satisfaction ? `${stats.avg_satisfaction}/5` : '—', color: 'var(--success)', icon: '⭐' },
        { label: t('client_portal.stat_avg_nps'), value: stats.avg_nps ?? '—', color: stats.avg_nps >= 8 ? 'var(--success)' : stats.avg_nps >= 6 ? 'var(--warning)' : 'var(--danger)', icon: '📊' },
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
  const t = useAppT()
  const [tab, setTab] = useState('clients')
  const [selectedProject, setSelectedProject] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects', { params: { page_size: 200 } }).then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])),
  })

  const TABS = [
    { id: 'clients',  label: `👤 ${t('client_portal.tab_contacts')}` },
    { id: 'uat',      label: `🧪 ${t('client_portal.tab_uat')}` },
    { id: 'requests', label: `💡 ${t('client_portal.tab_requests')}` },
    { id: 'messages', label: `💬 ${t('client_portal.tab_messages')}` },
    { id: 'documents',label: `📄 ${t('client_portal.tab_documents')}` },
    { id: 'wiki',     label: `📚 ${t('client_portal.tab_wiki')}` },
  ]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={t('client_portal.title')}
        subtitle={t('client_portal.subtitle')}
        actions={
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
            style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer', minWidth: 240 }}>
            <option value="">{t('client_portal.select_project')}</option>
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
        <EmptyState icon="🌐" title={t('client_portal.empty_select_title')} description={t('client_portal.empty_select_desc')} />
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