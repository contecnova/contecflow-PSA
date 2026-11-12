/**
 * ClientPortalPage – Internal PM view for managing the client portal:
 * - Manage client users and their access
 * - Create/manage UAT sessions with test cases
 * - Send messages to clients
 * - Upload documents
 * - View portal stats
 */
import React, { useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { portalApi, projectsApi, deliverablesApi, wikiApi, type PathId } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Page } from '../components/ui'
import { useTabListKeys } from '../components/ui/Tabs'
import {
  Globe, Users, FlaskConical, Lightbulb, FileText, BookOpen,
} from 'lucide-react'
import { fmtDate, fmtCurrency, extractErr} from '../utils/helpers'
import { STATUS_CFG, FR_STATUS_CFG, type StatusConfig } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { LARGE_PAGE_SIZE, NOTIFICATIONS_POLL_MS } from '../constants/timings'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../components/portal/GovernedConversations'
import { alpha } from '../constants/theme'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

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

// ── Tipos de las respuestas del portal (los campos que usa esta pantalla) ─────
interface ClientePortal {
  id: string
  full_name: string
  email: string
  job_title?: string | null
  company?: string | null
  phone?: string | null
  project_id?: string | null
  project_ids?: string[]
  project_name?: string | null
  is_active: boolean
  can_approve_deliverables?: boolean
  can_request_changes?: boolean
  can_view_budget?: boolean
  can_view_team?: boolean
  last_login?: string | null
}
type PermisoCliente = 'can_approve_deliverables' | 'can_request_changes' | 'can_view_budget' | 'can_view_team'
type FormCliente = {
  full_name: string; email: string; job_title: string; company: string; phone: string; password: string
} & Record<PermisoCliente, boolean>
type FormEdicionCliente = FormCliente & { project_ids: string[] }
type EventoDeCampo = ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>

interface CasoDePrueba { id: string; title: string; status: string; expected_result?: string | null; actual_result?: string | null }
interface IncidenciaUat { id: string; title: string; description?: string | null; severity: string; status: string }
interface SesionUat {
  id: string
  code: string
  title: string
  status: string
  overdue?: boolean
  deadline?: string | null
  test_environment?: string | null
  client_notes?: string | null
  stats: { total: number; passed: number; failed: number }
  test_cases: CasoDePrueba[]
  issues: IncidenciaUat[]
}
interface Entregable { id: string; code: string; name: string }
type FormUat = z.infer<typeof uatSessionSchema>
type CasoNuevo = { title: string; steps: string; expected_result: string }

interface PeticionDeCambio {
  id: string
  code: string
  title: string
  description?: string | null
  status: string
  priority_color: string
  priority_label: string
  affected_area?: string | null
  client_name?: string | null
  submitted_at?: string | null
  pm_response?: string | null
  estimated_cost?: number | null
  estimated_delivery_weeks?: number | null
  client_approved?: boolean | null
  client_approved_at?: string | null
}
type RespuestaPeticion = { pm_response: string; estimated_hours: string; estimated_cost: string; estimated_delivery_weeks: string; status: string }

interface DocumentoPortal {
  id: string
  title: string
  category: string
  file_name?: string | null
  file_url?: string | null
  created_at?: string | null
  requires_signature?: boolean
  signed_by_client?: boolean
}
type FormDocumento = { title: string; description: string; category: string; file_url: string; file_name: string; requires_signature: boolean }

interface EspacioWiki { id: string; name: string; project_id?: string | null }
interface PaginaWiki { id: string; title: string; slug: string; visibility?: string | null }

interface EstadisticasPortal {
  client_count: number
  unread_messages: number
  fr_pending_review: number
  uat_pending: number
  avg_satisfaction: number | null
  avg_nps: number | null
}

function StatusBadge({ status, cfg }: { status: string; cfg: Record<string, StatusConfig> }) {
  const t = useAppT()
  const c = cfg[status] || { label: t('client_portal.unknown_status'), color: 'var(--text-2)' }
  return <DsBadge color={c.color}>{c.label}</DsBadge>
}

// ── Client Users Management ───────────────────────────────────────────────────
function ClientUsersTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [editingClient, setEditingClient] = useState<ClientePortal | null>(null)
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['portal-clients', projectId],
    queryFn: () => portalApi.clients({ project_id: projectId }).then((r): ClientePortal[] => r.data),
    enabled: !!projectId,
  })
  const { mutate: deleteClient } = useMutation({
    mutationFn: (id: PathId) => portalApi.deleteClient(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const { mutate: toggleActive } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => portalApi.updateClient(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div className="u-text2-base">{clients.length} {t('client_portal.contacts_count')}</div>
        <Button onClick={() => setShowCreate(true)} icon="＋">{t('client_portal.add_contact')}</Button>
      </div>
      {isLoading ? <Spinner /> : clients.length === 0 ? (
        <EmptyState svgIcon={<Users size={36} />} title={t('client_portal.empty_contacts_title')} description={t('client_portal.empty_contacts_desc')} />
      ) : (
        <div className="u-stack-10">
          {clients.map(c => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', background: 'var(--surface-2)', border: `1px solid ${c.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, opacity: c.is_active ? 1 : 0.6 }}>
              <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--purple))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 700, flexShrink: 0 }}>
                {c.full_name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div className="u-flex1">
                <div className="u-md-700">{c.full_name}</div>
                <div className="u-text2-sm">{c.job_title || t('client_portal.role_unknown')} · {c.company || c.project_name} · {c.email}</div>
                <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: "var(--text-xs)" }}>
                  {c.can_approve_deliverables && <span style={{ color: 'var(--success)' }}>{`✓ ${t('client_portal.perm_approve')}`}</span>}
                  {c.can_request_changes && <span style={{ color: 'var(--accent)' }}>{`✓ ${t('client_portal.perm_request')}`}</span>}
                  {c.can_view_budget && <span className="u-warning">{`✓ ${t('client_portal.perm_view_budget')}`}</span>}
                </div>
              </div>
              {c.last_login && <div className="u-text2-xs">{`${t('client_portal.last_access')}: ${fmtDate(c.last_login)}`}</div>}
              <div className="u-row-8">
                <button onClick={() => setEditingClient(c)}
                  style={{ background: 'none', border: '1px solid var(--accent-glow)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                  {`✏ ${t('client_portal.edit')}`}
                </button>
                <button onClick={() => toggleActive({ id: c.id, active: !c.is_active })}
                  style={{ background: 'none', border: `1px solid ${c.is_active ? 'var(--warning-border)' : 'var(--success-border)'}`, borderRadius: 6, padding: '4px 10px', color: c.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                  {c.is_active ? `⏸ ${t('client_portal.suspend')}` : `▶ ${t('client_portal.activate')}`}
                </button>
                <button onClick={() => { openConfirmGlobal({ message: t('client_portal.delete_contact_confirm'), onConfirm: () => deleteClient(c.id), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-bg)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showCreate && projectId && <CreateClientModal projectId={projectId} onClose={() => setShowCreate(false)} />}
      {editingClient && <EditClientModal client={editingClient} onClose={() => setEditingClient(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }); setEditingClient(null) }} />}
    </div>
  )
}

function CreateClientModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<FormCliente>({ full_name: '', email: '', job_title: '', company: '', phone: '', password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: true, can_view_team: false })
  const [extraProjectIds, setExtraProjectIds] = useState<string[]>([]) // additional projects beyond projectId
  const validation = useFormValidation(portalClientCreateSchema)
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k: keyof FormCliente) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data: z.infer<typeof portalClientCreateSchema> & { project_id: string; project_ids: string[] }) => portalApi.createClient(data),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }); onClose() },
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
        <div className="u-col-full">
          <label style={ls}>{t('client_portal.label_full_name')} *</label>
          <input value={form.full_name} onChange={set('full_name')} style={validation.inputStyle(fs, 'full_name')} />
          {validation.errors.full_name && <p className="u-field-error">{validation.errors.full_name}</p>}
        </div>
        <div>
          <label style={ls}>{t('client_portal.label_email')} *</label>
          <input type="email" value={form.email} onChange={set('email')} style={validation.inputStyle(fs, 'email')} />
          {validation.errors.email && <p className="u-field-error">{validation.errors.email}</p>}
        </div>
        <div><label style={ls}>{t('client_portal.label_job_title')}</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder={t('client_portal.label_job_title')} /></div>
        <div><label style={ls}>{t('client_portal.label_company')}</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>{t('client_portal.label_phone')}</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div className="u-col-full">
          <label style={ls}>{t('client_portal.label_password')} *</label>
          <input type="password" value={form.password} onChange={set('password')} style={validation.inputStyle(fs, 'password')} placeholder={t('client_portal.password_placeholder')} />
          {validation.errors.password && <p className="u-field-error">{validation.errors.password}</p>}
        </div>
        {allProjects.length > 1 && (
          <div className="u-col-full">
            <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.additional_projects_access')}</label>
            <div style={{ maxHeight: 140, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-2) var(--space-3)' }}>
              {allProjects.filter(p => p.id !== projectId).map(p => (
                <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
                  <input type="checkbox" checked={extraProjectIds.includes(p.id)}
                    onChange={e => setExtraProjectIds(prev => e.target.checked ? [...prev, p.id] : prev.filter(id => id !== p.id))} />
                  <span style={{ color: 'var(--text-1)', fontWeight: 500 }}>{p.code}</span>
                  <span className="u-text2-sm">{p.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="u-col-full">
          <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.permissions')}</label>
          <div className="u-stack-8">
            {([['can_approve_deliverables', t('client_portal.perm_approve_desc')],['can_request_changes', t('client_portal.perm_request_desc')],['can_view_budget', t('client_portal.perm_budget_desc')],['can_view_team', t('client_portal.perm_team_desc')]] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: "var(--text-base)" }}>
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
function EditClientModal({ client, onClose, onSaved }: { client: ClientePortal; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: z.infer<typeof portalClientEditSchema>) => portalApi.updateClient(client.id, data),
    onSuccess: onSaved,
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const toast = useToast()
  const [form, setForm] = useState<FormEdicionCliente>({
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

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k: keyof FormEdicionCliente) => (e: EventoDeCampo) => {
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
        <div className="u-col-full">
          <label style={ls}>{t('client_portal.label_full_name')} *</label>
          <input value={form.full_name} onChange={set('full_name')} style={validation.inputStyle(fs, 'full_name')} />
          {validation.errors.full_name && <p className="u-field-error">{validation.errors.full_name}</p>}
        </div>
        <div>
          <label style={ls}>{t('client_portal.label_email')} *</label>
          <input type="email" value={form.email} onChange={set('email')} style={validation.inputStyle(fs, 'email')} />
          {validation.errors.email && <p className="u-field-error">{validation.errors.email}</p>}
        </div>
        <div><label style={ls}>{t('client_portal.label_job_title')}</label><input value={form.job_title} onChange={set('job_title')} style={fs} placeholder={t('client_portal.label_job_title')} /></div>
        <div><label style={ls}>{t('client_portal.label_company')}</label><input value={form.company} onChange={set('company')} style={fs} /></div>
        <div><label style={ls}>{t('client_portal.label_phone')}</label><input value={form.phone} onChange={set('phone')} style={fs} /></div>
        <div className="u-col-full">
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
        <div className="u-col-full">
          <label style={ls}>{t('client_portal.label_password')}</label>
          <input type="password" value={form.password} onChange={set('password')} style={fs} placeholder={t('client_portal.password_placeholder')} />
          <div className="u-hint">{t('client_portal.password_placeholder')}</div>
        </div>
        <div className="u-col-full">
          <label style={{ ...ls, marginBottom: 10 }}>{t('client_portal.permissions')}</label>
          <div className="u-stack-8">
            {([
              ['can_approve_deliverables', t('client_portal.perm_approve_desc')],
              ['can_request_changes', t('client_portal.perm_request_desc')],
              ['can_view_budget', t('client_portal.perm_budget_desc')],
              ['can_view_team', t('client_portal.perm_team_desc')],
            ] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: "var(--text-base)" }}>
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


function UATTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const [showCreate, setShowCreate] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['uat-team', projectId],
    queryFn: () => portalApi.uat({ project_id: projectId }).then((r): SesionUat[] => r.data),
    enabled: !!projectId,
  })
  const { data: deliverables = [] } = useQuery({
    queryKey: ['deliverables-uat', projectId],
    queryFn: () => deliverablesApi.get(projectId).then((r): Entregable[] => r.data.deliverables || []),
    enabled: !!projectId,
  })
  // Always read live data so UATDetailModal reflects updates without reopening
  const selectedSession = selectedId ? (sessions.find(s => s.id === selectedId) ?? null) : null

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div className="u-text2-base">{sessions.length} {t('client_portal.uat_sessions_count')}</div>
        {projectId && <Button onClick={() => setShowCreate(true)} icon="＋">{t('client_portal.uat_new_session')}</Button>}
      </div>
      {isLoading ? <Spinner /> : sessions.length === 0 ? (
        <EmptyState svgIcon={<FlaskConical size={36} />} title={t('client_portal.uat_empty_title')} description={t('client_portal.uat_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {sessions.map(s => (
            <button key={s.id} type="button" style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${alpha(STATUS_CFG[s.status]?.color, '40') || 'var(--surface-4)'}`, borderRadius: 12, cursor: 'pointer', width:'100%', textAlign:'left', fontFamily:'inherit' }}
              onClick={() => setSelectedId(s.id)}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'var(--surface-2)'}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 3 }}>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{s.code}</span>
                    <span className="u-md-700">{s.title}</span>
                    {s.overdue && <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', fontWeight: 700 }}>{`⚠ ${t('client_portal.uat_overdue')}`}</span>}
                  </div>
                  <div className="u-text2-sm">
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
                <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--danger)' }}>
                  {`🐛 ${s.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open_issues')}`}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
      {showCreate && projectId && <CreateUATModal projectId={projectId} deliverables={deliverables} onClose={() => setShowCreate(false)} />}
      {selectedSession && <UATDetailModal session={selectedSession} onClose={() => setSelectedId(null)} />}
    </div>
  )
}

function CreateUATModal({ projectId, deliverables, onClose }: { projectId: string; deliverables: Entregable[]; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<Required<FormUat>>({ title: '', description: '', deliverable_id: '', test_environment: '', test_credentials: '', test_guide_url: '', available_from: '', deadline: '' })
  const [testCases, setTestCases] = useState<CasoNuevo[]>([{ title: '', steps: '', expected_result: '' }])
  const validation = useFormValidation(uatSessionSchema)
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const set = (k: keyof FormUat) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: async (data: { form: FormUat; testCases: CasoNuevo[] }) => {
      const res = await portalApi.createUat(projectId, data.form)
      for (const tc of data.testCases.filter(t => t.title)) {
        await portalApi.addTestCase(res.data.id, { title: tc.title, steps: tc.steps, expected_result: tc.expected_result, order: data.testCases.indexOf(tc) })
      }
      return res
    },
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['uat-team', projectId] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ form: result.data, testCases })
  }

  return (
    <Modal open title={t('client_portal.uat_modal_new_title')} onClose={onClose} width={680}>
      <div className="u-stack-14">
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div>
            <label style={ls}>{t('client_portal.uat_label_title')} *</label>
            <input value={form.title} onChange={set('title')} style={validation.inputStyle(fs, 'title')} placeholder={t('client_portal.uat_placeholder_title')} />
            {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
          </div>
          <div><label style={ls}>{t('client_portal.uat_label_deliverable')}</label>
            <select value={form.deliverable_id} onChange={set('deliverable_id')} style={fs}>
              <option value="">{t('client_portal.uat_unlinked')}</option>
              {deliverables.map(d => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </select>
          </div>
        </div>
        <div><label style={ls}>{t('client_portal.uat_label_description')}</label><textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>
        <div className="u-grid2-12">
          <div><label style={ls}>{t('client_portal.uat_label_test_env_url')}</label><input value={form.test_environment} onChange={set('test_environment')} style={fs} placeholder={t('client_portal.uat_placeholder_test_env_url')} /></div>
          <div><label style={ls}>{t('client_portal.uat_label_test_credentials')}</label><input value={form.test_credentials} onChange={set('test_credentials')} style={fs} placeholder={t('client_portal.uat_placeholder_test_credentials')} /></div>
          <div><label style={ls}>{t('client_portal.uat_label_available_from')}</label><DateInput value={form.available_from} onChange={set('available_from')} style={validation.inputStyle(fs, 'available_from')} /></div>
          <div>
            <label style={ls}>{t('client_portal.uat_label_deadline')}</label>
            <DateInput value={form.deadline} onChange={set('deadline')} style={validation.inputStyle(fs, 'deadline')} />
            {validation.errors.deadline && <p className="u-field-error">{validation.errors.deadline}</p>}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 10 }}>{t('client_portal.uat_test_cases')}</div>
          {testCases.map((tc, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 2fr 30px', gap: 8, marginBottom: 8, padding: 10, background: 'var(--surface-3)', borderRadius: 8 }}>
              <input value={tc.title} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, title: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_title_placeholder').replace('{index}', String(i + 1))} />
              <input value={tc.steps} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, steps: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_steps_placeholder')} />
              <input value={tc.expected_result} onChange={e => setTestCases(tcs => tcs.map((t, j) => j === i ? { ...t, expected_result: e.target.value } : t))} style={fs} placeholder={t('client_portal.uat_test_case_expected_placeholder')} />
              <button onClick={() => setTestCases(tcs => tcs.filter((_, j) => j !== i))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-lg)" }}>×</button>
            </div>
          ))}
          <button onClick={() => setTestCases(tcs => [...tcs, { title: '', steps: '', expected_result: '' }])}
            style={{ background: 'none', border: '1px dashed var(--surface-4)', borderRadius: 8, padding: '8px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', width: '100%' }}>
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

function UATDetailModal({ session: initialSession, onClose }: { session: SesionUat; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: updateIssue } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.updateUatStatus(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['uat-team'], exact: false }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const SEV_COLORS: Record<string, string> = { low: 'var(--success)', medium: 'var(--accent)', high: 'var(--warning)', blocker: 'var(--danger)' }

  return (
    <Modal open title={`${initialSession.code} — ${initialSession.title}`} onClose={onClose} width={700}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <StatusBadge status={initialSession.status} cfg={STATUS_CFG} />
        {initialSession.test_environment && <a href={initialSession.test_environment} target="_blank" rel="noopener noreferrer" style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', textDecoration: 'none' }}>{`🔗 ${t('client_portal.uat_detail_test_env')}`}</a>}
        {initialSession.deadline && <span className="u-text2-sm">{`${t('client_portal.uat_deadline')}: ${fmtDate(initialSession.deadline)}`}</span>}
      </div>

      {initialSession.client_notes && (
        <div style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase' }}>{t('client_portal.uat_detail_client_notes')}</div>
          <p style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{initialSession.client_notes}</p>
        </div>
      )}

      {/* Test cases */}
      {initialSession.test_cases.length > 0 && (
        <div className="u-mb-16">
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            {`${t('client_portal.uat_detail_cases_title')} (${initialSession.stats.passed}/${initialSession.stats.total} ${t('client_portal.uat_detail_approved')})`}
          </div>
          <div className="u-stack-8">
            {initialSession.test_cases.map(tc => {
              const color = tc.status === 'passed' ? 'var(--success)' : tc.status === 'failed' ? 'var(--danger)' : 'var(--text-2)'
              return (
                <div key={tc.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${alpha(color, '30')}`, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div className="u-flex1">
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 4 }}>{tc.title}</div>
                      {tc.expected_result && <div className="u-text2-sm">{`${t('client_portal.uat_expected')}: ${tc.expected_result}`}</div>}
                      {tc.actual_result && <div style={{ fontSize: "var(--text-sm)", color: color, marginTop: 4 }}>{`${t('client_portal.uat_result')}: ${tc.actual_result}`}</div>}
                    </div>
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color, background: alpha(color, '20'), border: `1px solid ${alpha(color, '40')}`, borderRadius: 20, padding: '2px 8px', textTransform: 'uppercase', flexShrink: 0 }}>
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
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            {`${t('client_portal.uat_issues_title')} (${initialSession.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open')})`}
          </div>
          <div className="u-stack-8">
            {initialSession.issues.map(issue => {
              const sevColor = SEV_COLORS[issue.severity] || 'var(--text-2)'
              return (
                <div key={issue.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${issue.status === 'open' ? alpha(sevColor, '40') : 'var(--surface-4)'}`, borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div className="u-flex1">
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: sevColor, background: alpha(sevColor, '20'), borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{issue.severity}</span>
                        <span className="u-base-600">{issue.title}</span>
                      </div>
                      <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', margin: 0 }}>{issue.description}</p>
                    </div>
                    {issue.status === 'open' && (
                      <select defaultValue={issue.status} onChange={e => updateIssue({ id: issue.id, status: e.target.value })}
                        style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: 'var(--space-2) var(--space-2)', color: 'var(--text-1)', fontSize: "var(--text-xs)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
                        <option value="open">{t('client_portal.uat_issue_open')}</option>
                        <option value="fixed">{t('client_portal.uat_issue_fixed')}</option>
                        <option value="deferred">{t('client_portal.uat_issue_deferred')}</option>
                        <option value="wontfix">{t('client_portal.uat_issue_wontfix')}</option>
                      </select>
                    )}
                    {issue.status !== 'open' && <span style={{ fontSize: "var(--text-xs)", color: 'var(--success)' }}>✓ {issue.status}</span>}
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
function FeatureRequestsTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [responding, setResponding] = useState<PeticionDeCambio | null>(null)
  const [responseForm, setResponseForm] = useState<RespuestaPeticion>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs', projectId],
    queryFn: () => portalApi.featureRequests({ project_id: projectId }).then((r): PeticionDeCambio[] => Array.isArray(r.data) ? r.data : []),
    enabled: !!projectId,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RespuestaPeticion }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs', projectId] }); setResponding(null) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.respondFeatureRequest(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-frs', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  return (
    <div>
      {isLoading ? <Spinner /> : frs.length === 0 ? (
        <EmptyState svgIcon={<Lightbulb size={36} />} title={t('client_portal.fr_empty_title')} description={t('client_portal.fr_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {frs.map(fr => (
            <div key={fr.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${alpha(fr.priority_color, '30')}`, borderRadius: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div className="u-flex1">
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{fr.code}</span>
                    <span className="u-md-700">{fr.title}</span>
                  </div>
                  <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '0 0 6px' }}>{fr.description}</p>
                  <div style={{ display: 'flex', gap: 12, fontSize: "var(--text-sm)" }}>
                    <span style={{ color: fr.priority_color, fontWeight: 700 }}>⚡ {fr.priority_label}</span>
                    {fr.affected_area && <span className="u-text2">📋 {fr.affected_area}</span>}
                    {fr.client_name && <span className="u-text2">👤 {fr.client_name}</span>}
                    <span className="u-text2">{fmtDate(fr.submitted_at)}</span>
                  </div>
                  {fr.pm_response && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8, fontSize: "var(--text-sm)" }}>
                      <span className="u-text2">{`${t('client_portal.fr_pm_response')}: `}</span>{fr.pm_response}
                      {fr.estimated_cost && <span style={{ color: 'var(--warning)', marginLeft: 12 }}>💶 {fmtCurrency(fr.estimated_cost)}</span>}
                      {fr.estimated_delivery_weeks && <span style={{ color: 'var(--accent)', marginLeft: 12 }}>📅 {fr.estimated_delivery_weeks} semanas</span>}
                    </div>
                  )}
                  {fr.client_approved === true && <div style={{ marginTop: 6, fontSize: "var(--text-sm)", color: 'var(--success)' }}>{`✓ ${t('client_portal.fr_client_approved')} ${fmtDate(fr.client_approved_at)}`}</div>}
                  {fr.client_approved === false && <div style={{ marginTop: 6, fontSize: "var(--text-sm)", color: 'var(--danger)' }}>{`✗ ${t('client_portal.fr_client_rejected')}`}</div>}
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
          <div className="u-stack-14">
            <div><label style={ls}>{t('client_portal.fr_label_response')} *</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical' }} placeholder={t('client_portal.fr_response_placeholder')} /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div><label style={ls}>{t('client_portal.fr_label_hours')}</label><input type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Ej: 8" /></div>
              <div><label style={ls}>{t('client_portal.fr_label_cost')} €</label><input type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} style={fs} placeholder="Ej: 1200" /></div>
              <div><label style={ls}>{t('client_portal.fr_label_weeks')}</label><input type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={fs} placeholder="Ej: 4" /></div>
            </div>
            <div><label style={ls}>{t('client_portal.fr_label_status')}</label>
              <select value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} style={fs}>
                <option value="estimated">{t('client_portal.fr_status_estimated')}</option>
                <option value="reviewing">{t('client_portal.fr_status_reviewing')}</option>
                <option value="rejected">{t('client_portal.fr_status_rejected')}</option>
              </select>
            </div>
            <div className="u-actions-10">
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
function MessagesTab({ projectId }: { projectId: string }) {
  const traducir = useAppT()
  return (
    <div className="u-stack-16">
      <TeamGovernedConversationInbox
        title={traducir('clientportal.conversaciones_del_portal')}
        emptyTitle="Sin conversaciones"
        emptyDescription="No hay conversaciones para este proyecto. Crea una conversación gobernada para empezar."
        projectOptions={projectId ? [{ id: projectId, name: projectId, code: '' }] : []}
        initialProjectId={projectId || ''}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────
function DocumentsTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [docForm, setDocForm] = useState<FormDocumento>({ title: '', description: '', category: 'deliverable', file_url: '', file_name: '', requires_signature: false })
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs', projectId],
    queryFn: () => portalApi.documents({ project_id: projectId }).then((r): DocumentoPortal[] => r.data),
    enabled: !!projectId,
  })
  const { mutate: addDoc } = useMutation({
    mutationFn: (data: FormDocumento) => portalApi.createDocument(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-docs', projectId] }); setShowAdd(false) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const CAT_LABELS: Record<string, string> = {
    contract: `📋 ${t('client_portal.docs_contract')}`,
    deliverable: `📦 ${t('client_portal.docs_deliverable')}`,
    meeting_notes: `📝 ${t('client_portal.docs_meeting_notes')}`,
    report: `📊 ${t('client_portal.docs_report')}`,
    other: `📄 ${t('client_portal.docs_other')}`,
  }
  const CAT_COLORS: Record<string, string> = { contract: 'var(--purple)', deliverable: 'var(--success)', meeting_notes: 'var(--accent)', report: 'var(--warning)', other: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div className="u-text2-base">{docs.length} {t('client_portal.docs_count')}</div>
        <Button onClick={() => setShowAdd(true)} icon="＋">{t('client_portal.docs_add')}</Button>
      </div>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState svgIcon={<FileText size={36} />} title={t('client_portal.docs_empty_title')} description={t('client_portal.docs_empty_desc')} />
      ) : (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          {docs.map((doc, i) => {
            const color = CAT_COLORS[doc.category] || 'var(--text-2)'
            return (
              <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', borderBottom: i < docs.length - 1 ? '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' : 'none' }}>
                <span style={{ fontSize: "var(--text-xl-em)", flexShrink: 0 }}>{CAT_LABELS[doc.category]?.split(' ')[0] || '📄'}</span>
                <div className="u-flex1">
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{doc.title}</div>
                  <div className="u-text2-xs">
                    <span style={{ color, fontWeight: 600 }}>{CAT_LABELS[doc.category]?.replace(/^\S+\s/, '') || doc.category}</span>
                    {doc.file_name && ` · ${doc.file_name}`}
                    {doc.created_at && ` · ${fmtDate(doc.created_at)}`}
                  </div>
                </div>
                {doc.requires_signature && (
                  <span style={{ fontSize: "var(--text-xs)", color: doc.signed_by_client ? 'var(--success)' : 'var(--warning)', background: doc.signed_by_client ? 'var(--success-bg)' : 'var(--warning-bg)', border: `1px solid ${doc.signed_by_client ? 'var(--success-border)' : 'var(--warning-border)'}`, borderRadius: 20, padding: '2px 8px' }}>
                    {doc.signed_by_client ? `✓ ${t('client_portal.docs_signed')}` : `⏳ ${t('client_portal.docs_pending_signature')}`}
                  </span>
                )}
                {doc.file_url && (
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer" style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: 'var(--space-2) var(--space-3)', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", textDecoration: 'none' }}>
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
          <div className="u-stack-14">
            <div><label style={ls}>{t('client_portal.docs_label_title')} *</label><input value={docForm.title} onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))} style={fs} /></div>
            <div><label style={ls}>{t('client_portal.docs_label_category')}</label>
              <select value={docForm.category} onChange={e => setDocForm(f => ({ ...f, category: e.target.value }))} style={fs}>
                {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div><label style={ls}>{t('client_portal.docs_label_file_url')}</label><input value={docForm.file_url} onChange={e => setDocForm(f => ({ ...f, file_url: e.target.value }))} style={fs} placeholder="https://..." /></div>
            <div><label style={ls}>{t('client_portal.docs_label_file_name')}</label><input value={docForm.file_name} onChange={e => setDocForm(f => ({ ...f, file_name: e.target.value }))} style={fs} placeholder={t('client_portal.docs_placeholder_file_name')} /></div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
              <input type="checkbox" checked={docForm.requires_signature} onChange={e => setDocForm(f => ({ ...f, requires_signature: e.target.checked }))} />
              {t('client_portal.docs_requires_signature')}
            </label>
            <div className="u-actions-10">
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
function WikiPortalTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const { data: spaces = [] } = useQuery({
    queryKey: ['wiki-spaces-portal', projectId],
    queryFn: () => wikiApi.portalSpaces().then((r): EspacioWiki[] => r.data.filter((s: EspacioWiki) => !projectId || s.project_id === projectId || !s.project_id)),
  })
  const [selectedSpace, setSelectedSpace] = React.useState('')
  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['wiki-pages-portal-op', selectedSpace],
    queryFn: () => wikiApi.portalPages(selectedSpace).then((r): PaginaWiki[] => r.data),
    enabled: !!selectedSpace,
  })
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: setVis } = useMutation({
    mutationFn: ({ id, visibility }: { id: string; visibility: string }) => wikiApi.portalUpdatePage(id, { visibility }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wiki-pages-portal-op', selectedSpace] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const VIS = {
    team:   { label: `${t('client_portal.wiki_vis_team')}`, color: 'var(--text-2)' },
    portal: { label: `${t('client_portal.wiki_vis_portal')}`, color: 'var(--accent)' },
    public: { label: `${t('client_portal.wiki_vis_public')}`, color: 'var(--success)' },
  }

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10, padding: 'var(--space-3) var(--space-4)', marginBottom: 20, fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
        <strong style={{ color: 'var(--accent)' }}>{`ℹ ${t('client_portal.wiki_info_title')}`}</strong>
        {' '}— {t('client_portal.wiki_info_desc')}
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select value={selectedSpace} onChange={e => setSelectedSpace(e.target.value)}
          style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', flex: 1 }}>
          <option value="">{t('client_portal.wiki_select_space')}</option>
          {spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      {isLoading && <Spinner />}
      {selectedSpace && !isLoading && pages.length === 0 && (
        <EmptyState svgIcon={<BookOpen size={36} />} title={t('client_portal.wiki_empty_title')} description={t('client_portal.wiki_empty_desc')} />
      )}
      {pages.length > 0 && (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          {pages.map((page, i) => (
            <div key={page.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 18px', borderBottom: i < pages.length - 1 ? '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' : 'none' }}>
              <span style={{ fontSize: "var(--text-lg)" }}>📄</span>
              <div className="u-flex1">
                <div className="u-base-600">{page.title}</div>
                <div className="u-text2-xs">{page.slug}</div>
              </div>
              <div className="u-row-6">
                {Object.entries(VIS).map(([val, cfg]) => (
                  <button key={val} onClick={() => setVis({ id: page.id, visibility: val })}
                    style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${(page.visibility || 'team') === val ? alpha(cfg.color, '60') : 'var(--surface-4)'}`, background: (page.visibility || 'team') === val ? alpha(cfg.color, '15') : 'transparent', color: (page.visibility || 'team') === val ? cfg.color : 'var(--text-3)', fontSize: "var(--text-xs)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
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
function StatsPanel({ projectId }: { projectId: string }) {
  const t = useAppT()
  const { data: stats } = useQuery({
    queryKey: ['portal-stats', projectId],
    queryFn: () => portalApi.stats(projectId).then((r): EstadisticasPortal => r.data),
    enabled: !!projectId,
    refetchInterval: NOTIFICATIONS_POLL_MS,
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
          <div style={{ fontSize: "var(--text-lg-em)", marginBottom: 4 }}>{icon}</div>
          <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{label}</div>
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ClientPortalPage(): JSX.Element {
  const traducir = useAppT()
  const t = useAppT()
  const [tab, setTab] = useState('clients')
  const [selectedProject, setSelectedProject] = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })

  const TABS = [
    { id: 'clients',  label: `${t('client_portal.tab_contacts')}` },
    { id: 'uat',      label: `${t('client_portal.tab_uat')}` },
    { id: 'requests', label: `${t('client_portal.tab_requests')}` },
    { id: 'messages', label: `${t('client_portal.tab_messages')}` },
    { id: 'documents',label: `${t('client_portal.tab_documents')}` },
    { id: 'wiki',     label: `${t('client_portal.tab_wiki')}` },
  ]
  const teclas = useTabListKeys(TABS.map(x => x.id), tab, setTab)

  return (
    <Page
      icon={<Globe size={18} />}
      title={t('client_portal.title')}
      subtitle={t('client_portal.subtitle')}
      rightActions={
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          className="ds-input"
          style={{ minWidth: 240 }}>
          <option value="">{t('client_portal.select_project')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
      }
    >
      {selectedProject && <StatsPanel projectId={selectedProject} />}

      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} className="ds-segmented" role="tablist" aria-label={traducir('clientportal.secciones_del_portal_cliente')}
        style={{ alignSelf: 'flex-start' }}>
        {TABS.map(t => (
          <button key={t.id} type="button" role="tab" data-tab-id={t.id}
            tabIndex={t.id === teclas.focusId ? 0 : -1}
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {!selectedProject ? (
        <EmptyState svgIcon={<Globe size={36} />} title={t('client_portal.empty_select_title')} description={t('client_portal.empty_select_desc')} />
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
    </Page>
  )
}