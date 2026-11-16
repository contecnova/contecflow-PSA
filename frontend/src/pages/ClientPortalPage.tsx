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
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { z } from 'zod'
import { portalApi, portalClientsApi, projectsApi, deliverablesApi, wikiApi, type PathId } from '../services/api'
import type { Entregable, PortalPeticion, PortalSesionUat, PortalUsuario, VisibilidadDeWiki, WikiPaginaEnArbol } from '../services/api/tipos-alm'
import { Button, Modal, Spinner, EmptyState, Page, KpiCard, Tabs } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import { SMALL_PAGE_SIZE } from '../constants/pagination'
import {
  Globe, Users, FlaskConical, Lightbulb, FileText, BookOpen, Plus, Check, Pencil,
  Pause, Play, Trash2, AlertTriangle, CheckCircle2, XCircle, Bug, X, Link2, Minus,
  Zap, ClipboardList, User, Wallet, CalendarDays, MessageSquare, Rocket, Package,
  NotebookPen, BarChart3, Hourglass, Download, Info, MessageCircle, Star, Gauge,
  FileSignature,
} from 'lucide-react'
import { fmtDate, extractErr } from '../utils/helpers'
import { STATUS_CFG, FR_STATUS_CFG, type StatusConfig } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { LARGE_PAGE_SIZE, NOTIFICATIONS_POLL_MS } from '../constants/timings'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../components/portal/GovernedConversations'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './ClientPortalPage.css'

type Traductor = ReturnType<typeof useAppT>

/** Color de datos (estado, severidad, prioridad...) → custom property que consumen las clases `.cpp-*`. */
const colorVar = (color: string | undefined): CSSProperties => ({ '--cpp-color': color || 'var(--text-2)' } as CSSProperties)

/** Props de un campo con error: aria-invalid (lo pinta `.cpp-input`) + enlace al mensaje. */
function propsDeError(errors: Record<string, string | undefined>, key: string, idBase: string) {
  return errors[key] ? { 'aria-invalid': true as const, 'aria-describedby': `${idBase}-err-${key}` } : {}
}
function MensajeError({ errors, campo, idBase }: { errors: Record<string, string | undefined>; campo: string; idBase: string }) {
  return errors[campo] ? <p id={`${idBase}-err-${campo}`} className="u-field-error">{errors[campo]}</p> : null
}

// Esquemas construidos con el traductor activo: los mensajes salen en el idioma del usuario.
function crearEsquemaUat(t: Traductor) {
  return z.object({
    title: z.string().trim().min(1, t('clientportalpage.err_titulo')),
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
        code: 'custom',
        path: ['deadline'],
        message: t('clientportalpage.err_fecha_limite'),
      })
    }
  })
}

function crearEsquemaAltaCliente(t: Traductor) {
  return z.object({
    full_name: z.string().trim().min(1, t('clientportalpage.err_nombre')),
    email: z.string().trim().pipe(z.email(t('clientportalpage.err_email'))),
    job_title: z.string().optional(),
    company: z.string().optional(),
    phone: z.string().optional(),
    password: z.string().min(1, t('clientportalpage.err_contrasena')),
    can_approve_deliverables: z.boolean(),
    can_request_changes: z.boolean(),
    can_view_budget: z.boolean(),
    can_view_team: z.boolean(),
  })
}

function crearEsquemaEdicionCliente(t: Traductor) {
  return z.object({
    full_name: z.string().trim().min(1, t('clientportalpage.err_nombre')),
    email: z.string().trim().pipe(z.email(t('clientportalpage.err_email'))),
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
}
type DatosAltaCliente = z.infer<ReturnType<typeof crearEsquemaAltaCliente>>
type DatosEdicionCliente = z.infer<ReturnType<typeof crearEsquemaEdicionCliente>>


// STATUS_CFG y FR_STATUS_CFG centralizados en constants/sharedStatus.js

// ── Tipos de las respuestas del portal: services/api/tipos-alm ───────────────
type ClientePortal = PortalUsuario
type PermisoCliente = 'can_approve_deliverables' | 'can_request_changes' | 'can_view_budget' | 'can_view_team'
type FormCliente = {
  full_name: string; email: string; job_title: string; company: string; phone: string; password: string
} & Record<PermisoCliente, boolean>
type FormEdicionCliente = FormCliente & { project_ids: string[] }
type EventoDeCampo = ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>

type SesionUat = PortalSesionUat
type FormUat = z.infer<ReturnType<typeof crearEsquemaUat>>
type CasoNuevo = { title: string; steps: string; expected_result: string }

type PeticionDeCambio = PortalPeticion
type RespuestaPeticion = { pm_response: string; estimated_hours: string; estimated_cost: string; estimated_delivery_weeks: string; status: string }

type FormDocumento = { title: string; description: string; category: string; file_url: string; file_name: string; requires_signature: boolean }

/** epics_service.serialize_page: el backend NO envía `visibility` ni tiene ruta para cambiarla
 *  (WikiPageIn no la acepta); el selector de visibilidad no puede funcionar sin ese cambio. */
/** El árbol de páginas en una lista (con su profundidad): la visibilidad se fija por página. */
function aplanarPaginas(paginas: WikiPaginaEnArbol[], nivel = 0): Array<WikiPaginaEnArbol & { nivel: number }> {
  return paginas.flatMap(p => [{ ...p, nivel }, ...aplanarPaginas(p.children, nivel + 1)])
}

function StatusBadge({ status, cfg }: { status: string; cfg: Record<string, StatusConfig> }) {
  const t = useAppT()
  const c = cfg[status]
  // La etiqueta sale de i18n (`clientportalpage.estado_<estado>`); sharedStatus solo aporta el color.
  if (!c) return <DsBadge color="var(--text-2)">{t('client_portal.unknown_status')}</DsBadge>
  return <DsBadge color={c.color}>{t(`clientportalpage.estado_${status}`)}</DsBadge>
}

// ── Client Users Management ───────────────────────────────────────────────────
/** Contactos del portal por página (#22: /portal/clients pagina con page/page_size). */
const CONTACTOS_POR_PAGINA = SMALL_PAGE_SIZE

function ClientUsersTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [editingClient, setEditingClient] = useState<ClientePortal | null>(null)
  const [page, setPage] = useState(1)
  // Paginada en el servidor (#22): total en meta.total / X-Total-Count.
  const { data: pagina, isLoading } = useQuery({
    queryKey: ['portal-clients', projectId, 'pagina', page],
    queryFn: () => portalClientsApi.list({ project_id: projectId, page, page_size: CONTACTOS_POR_PAGINA }).then(r => ({
      items: r.data,
      total: r.meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length),
    })),
    enabled: !!projectId,
    placeholderData: keepPreviousData,
  })
  const clients = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / CONTACTOS_POR_PAGINA))
  // Al borrar el último de la última página, o al cambiar de proyecto, no quedarse en una página vacía.
  React.useEffect(() => { if (pagina && page > totalPages) setPage(totalPages) }, [pagina, page, totalPages])
  React.useEffect(() => { setPage(1) }, [projectId])
  const { mutate: deleteClient } = useMutation({
    mutationFn: (id: PathId) => portalApi.deleteClient(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const { mutate: toggleActive } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => portalClientsApi.update(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div className="u-row-between-mb16">
        <div className="u-text2-base">{total} {t('client_portal.contacts_count')}</div>
        <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>{t('client_portal.add_contact')}</Button>
      </div>
      {isLoading ? <Spinner /> : clients.length === 0 ? (
        <EmptyState svgIcon={<Users size={36} />} title={t('client_portal.empty_contacts_title')} description={t('client_portal.empty_contacts_desc')} />
      ) : (
        <div className="u-stack-10">
          {clients.map(c => (
            <div key={c.id} className={c.is_active ? 'cpp-user' : 'cpp-user is-inactive'}>
              <div className="cpp-avatar" aria-hidden="true">
                {c.full_name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div className="u-flex1">
                <div className="u-md-700">{c.full_name}</div>
                <div className="u-text2-sm">{c.job_title || t('client_portal.role_unknown')} · {c.company || c.project_name} · {c.email}</div>
                <div className="cpp-perms">
                  {c.can_approve_deliverables && <span className="u-success cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_approve')}</span>}
                  {c.can_request_changes && <span className="u-accent cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_request')}</span>}
                  {c.can_view_budget && <span className="u-warning cpp-con-icono"><Check size={12} aria-hidden="true" />{t('client_portal.perm_view_budget')}</span>}
                </div>
              </div>
              {c.last_login && <div className="u-text2-xs">{`${t('client_portal.last_access')}: ${fmtDate(c.last_login)}`}</div>}
              <div className="u-row-8">
                <Button variant="secondary" size="sm" icon={<Pencil size={13} />} onClick={() => setEditingClient(c)}>
                  {t('client_portal.edit')}
                </Button>
                <Button variant="secondary" size="sm" icon={c.is_active ? <Pause size={13} /> : <Play size={13} />}
                  onClick={() => toggleActive({ id: c.id, active: !c.is_active })}>
                  {c.is_active ? t('client_portal.suspend') : t('client_portal.activate')}
                </Button>
                <Button variant="danger" size="sm" icon={<Trash2 size={13} />}
                  title={t('clientportalpage.eliminar_contacto', { name: c.full_name })}
                  onClick={() => { openConfirmGlobal({ message: t('client_portal.delete_contact_confirm'), onConfirm: () => deleteClient(c.id), danger: true }) }}>
                  <span className="u-sr-only">{t('clientportalpage.eliminar_contacto', { name: c.full_name })}</span>
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={CONTACTOS_POR_PAGINA} maxVisible={5} />
      {showCreate && projectId && <CreateClientModal projectId={projectId} onClose={() => setShowCreate(false)} />}
      {editingClient && <EditClientModal client={editingClient} onClose={() => setEditingClient(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['portal-clients', projectId] }); setEditingClient(null) }} />}
    </div>
  )
}

function CreateClientModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<FormCliente>({ full_name: '', email: '', job_title: '', company: '', phone: '', password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: true, can_view_team: false })
  const [extraProjectIds, setExtraProjectIds] = useState<string[]>([]) // additional projects beyond projectId
  const esquema = React.useMemo(() => crearEsquemaAltaCliente(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
  const set = (k: keyof FormCliente) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (data: DatosAltaCliente & { project_id: string; project_ids: string[] }) => portalClientsApi.create(data),
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
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.label_full_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={set('full_name')} className="cpp-input cpp-input--roomy" {...err('full_name')} />
          {msg('full_name')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.label_email')} *</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={form.email} onChange={set('email')} className="cpp-input cpp-input--roomy" {...err('email')} />
          {msg('email')}
        </div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.label_job_title')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.job_title} onChange={set('job_title')} className="cpp-input cpp-input--roomy" placeholder={t('client_portal.label_job_title')} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.label_company')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.company} onChange={set('company')} className="cpp-input cpp-input--roomy" /></div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.label_phone')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.phone} onChange={set('phone')} className="cpp-input cpp-input--roomy" /></div>
        <div className="u-col-full">
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="cpp-label">{t('client_portal.label_password')} *</label>
          <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="password" value={form.password} onChange={set('password')} className="cpp-input cpp-input--roomy" placeholder={t('client_portal.password_placeholder')} {...err('password')} />
          {msg('password')}
        </div>
        {allProjects.length > 1 && (
          <fieldset className="u-col-full cpp-fieldset">
            <legend className="cpp-label cpp-label--group">{t('client_portal.additional_projects_access')}</legend>
            <div className="cpp-projects-box">
              {allProjects.filter(p => p.id !== projectId).map(p => (
                <label key={p.id} className="u-row-center-8-pointer">
                  <input type="checkbox" aria-label={`${p.code} ${p.name}`} checked={extraProjectIds.includes(p.id)}
                    onChange={e => setExtraProjectIds(prev => e.target.checked ? [...prev, p.id] : prev.filter(id => id !== p.id))} />
                  <span className="cpp-project-code">{p.code}</span>
                  <span className="u-text2-sm">{p.name}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <fieldset className="u-col-full cpp-fieldset">
          <legend className="cpp-label cpp-label--group">{t('client_portal.permissions')}</legend>
          <div className="u-stack-8">
            {([['can_approve_deliverables', t('client_portal.perm_approve_desc')],['can_request_changes', t('client_portal.perm_request_desc')],['can_view_budget', t('client_portal.perm_budget_desc')],['can_view_team', t('client_portal.perm_team_desc')]] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <label key={k} className="cpp-check">
                <input type="checkbox" aria-label={label} checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="cpp-actions">
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
  const idCampo = React.useId()
  const t = useAppT()
  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => r.data),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: DatosEdicionCliente) => portalClientsApi.update(client.id, data),
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
  const esquema = React.useMemo(() => crearEsquemaEdicionCliente(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
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
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.label_full_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={set('full_name')} className="cpp-input" {...err('full_name')} />
          {msg('full_name')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.label_email')} *</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="email" value={form.email} onChange={set('email')} className="cpp-input" {...err('email')} />
          {msg('email')}
        </div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.label_job_title')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.job_title} onChange={set('job_title')} className="cpp-input" placeholder={t('client_portal.label_job_title')} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.label_company')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.company} onChange={set('company')} className="cpp-input" /></div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.label_phone')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.phone} onChange={set('phone')} className="cpp-input" /></div>
        <div className="u-col-full">
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="cpp-label">{t('client_portal.additional_projects_access')}</label>
          <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`}
            multiple
            value={form.project_ids}
            onChange={e => setForm(f => ({ ...f, project_ids: Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean) }))}
            className="cpp-input cpp-input--multi"
            style={{ '--cpp-h': `${38 + Math.min(allProjects.length, 5) * 28}px` } as CSSProperties}>
            {allProjects.map(project => (
              <option key={project.id} value={project.id}>{project.code} — {project.name}</option>
            ))}
          </select>
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="cpp-label">{t('client_portal.label_password')}</label>
          <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} type="password" value={form.password} onChange={set('password')} className="cpp-input" placeholder={t('client_portal.password_placeholder')} />
          <div className="u-hint">{t('client_portal.password_placeholder')}</div>
        </div>
        <fieldset className="u-col-full cpp-fieldset">
          <legend className="cpp-label cpp-label--group">{t('client_portal.permissions')}</legend>
          <div className="u-stack-8">
            {([
              ['can_approve_deliverables', t('client_portal.perm_approve_desc')],
              ['can_request_changes', t('client_portal.perm_request_desc')],
              ['can_view_budget', t('client_portal.perm_budget_desc')],
              ['can_view_team', t('client_portal.perm_team_desc')],
            ] as Array<[PermisoCliente, string]>).map(([k, label]) => (
              <label key={k} className="cpp-check">
                <input type="checkbox" aria-label={label} checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="cpp-actions">
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
    queryFn: () => portalApi.uat({ project_id: projectId }).then(r => r.data),
    enabled: !!projectId,
  })
  const { data: deliverables = [] } = useQuery({
    queryKey: ['deliverables-uat', projectId],
    queryFn: () => deliverablesApi.listByProject(projectId).then(r => r.data.deliverables || []),
    enabled: !!projectId,
  })
  // Always read live data so UATDetailModal reflects updates without reopening
  const selectedSession = selectedId ? (sessions.find(s => s.id === selectedId) ?? null) : null

  return (
    <div>
      <div className="cpp-tab-head">
        <div className="u-text2-base">{sessions.length} {t('client_portal.uat_sessions_count')}</div>
        {projectId && <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>{t('client_portal.uat_new_session')}</Button>}
      </div>
      {isLoading ? <Spinner /> : sessions.length === 0 ? (
        <EmptyState svgIcon={<FlaskConical size={36} />} title={t('client_portal.uat_empty_title')} description={t('client_portal.uat_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {sessions.map(s => (
            <button key={s.id} type="button"
              className={STATUS_CFG[s.status] ? 'cpp-uat has-color' : 'cpp-uat'}
              style={STATUS_CFG[s.status] ? colorVar(STATUS_CFG[s.status].color) : undefined}
              onClick={() => setSelectedId(s.id)}>
              <div className="cpp-row-top cpp-row-top--mb">
                <div>
                  <div className="cpp-title-row">
                    <span className="u-text2-mono-xs">{s.code}</span>
                    <span className="u-md-700">{s.title}</span>
                    {s.overdue && <span className="cpp-overdue cpp-con-icono"><AlertTriangle size={12} aria-hidden="true" />{t('client_portal.uat_overdue')}</span>}
                  </div>
                  <div className="u-text2-sm cpp-con-icono">
                    {s.deadline && `${t('client_portal.uat_deadline')}: ${fmtDate(s.deadline)} · `}
                    {s.stats.total} {t('client_portal.uat_cases')} ·
                    <CheckCircle2 size={12} className="u-success" aria-label={t('clientportalpage.estado_passed')} />{s.stats.passed} ·
                    <XCircle size={12} className="u-danger" aria-label={t('clientportalpage.estado_failed')} />{s.stats.failed}
                  </div>
                </div>
                <StatusBadge status={s.status} cfg={STATUS_CFG} />
              </div>
              {s.stats.total > 0 && (
                <div className="cpp-progress" aria-hidden="true">
                  <div className="cpp-progress__bar" style={{ '--cpp-pct': `${(s.stats.passed / s.stats.total) * 100}%` } as CSSProperties} />
                </div>
              )}
              {s.issues.length > 0 && (
                <div className="cpp-uat__issues cpp-con-icono">
                  <Bug size={12} aria-hidden="true" />{`${s.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open_issues')}`}
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
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<Required<FormUat>>({ title: '', description: '', deliverable_id: '', test_environment: '', test_credentials: '', test_guide_url: '', available_from: '', deadline: '' })
  const [testCases, setTestCases] = useState<CasoNuevo[]>([{ title: '', steps: '', expected_result: '' }])
  const esquema = React.useMemo(() => crearEsquemaUat(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
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
        <div className="cpp-grid-2-1">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.uat_label_title')} *</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} className="cpp-input" placeholder={t('client_portal.uat_placeholder_title')} {...err('title')} />
            {msg('title')}
          </div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.uat_label_deliverable')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.deliverable_id} onChange={set('deliverable_id')} className="cpp-input">
              <option value="">{t('client_portal.uat_unlinked')}</option>
              {deliverables.map(d => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </select>
          </div>
        </div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.uat_label_description')}</label><textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.description} onChange={set('description')} rows={2} className="cpp-input" /></div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.uat_label_test_env_url')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.test_environment} onChange={set('test_environment')} className="cpp-input" placeholder={t('client_portal.uat_placeholder_test_env_url')} /></div>
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.uat_label_test_credentials')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.test_credentials} onChange={set('test_credentials')} className="cpp-input" placeholder={t('client_portal.uat_placeholder_test_credentials')} /></div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="cpp-label">{t('client_portal.uat_label_available_from')}</label><DateInput id={`${idCampo}-6`} value={form.available_from} onChange={set('available_from')} className="cpp-input" {...err('available_from')} /></div>
          <div>
            <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="cpp-label">{t('client_portal.uat_label_deadline')}</label>
            <DateInput id={`${idCampo}-7`} value={form.deadline} onChange={set('deadline')} className="cpp-input" {...err('deadline')} />
            {msg('deadline')}
          </div>
        </div>

        <div>
          <div className="cpp-subtitle-accent">{t('client_portal.uat_test_cases')}</div>
          {testCases.map((tc, i) => (
            <div key={i} className="cpp-case">
              <input aria-label={t('client_portal.uat_test_case_title_placeholder', { index: i + 1 })} value={tc.title} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, title: e.target.value } : c))} className="cpp-input" placeholder={t('client_portal.uat_test_case_title_placeholder', { index: i + 1 })} />
              <input aria-label={t('client_portal.uat_test_case_steps_placeholder')} value={tc.steps} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, steps: e.target.value } : c))} className="cpp-input" placeholder={t('client_portal.uat_test_case_steps_placeholder')} />
              <input aria-label={t('client_portal.uat_test_case_expected_placeholder')} value={tc.expected_result} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, expected_result: e.target.value } : c))} className="cpp-input" placeholder={t('client_portal.uat_test_case_expected_placeholder')} />
              <button type="button" onClick={() => setTestCases(tcs => tcs.filter((_, j) => j !== i))} className="cpp-case__remove"
                aria-label={t('clientportalpage.quitar_caso', { index: i + 1 })} title={t('clientportalpage.quitar_caso', { index: i + 1 })}><X size={14} aria-hidden="true" /></button>
            </div>
          ))}
          <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setTestCases(tcs => [...tcs, { title: '', steps: '', expected_result: '' }])}>
            {t('client_portal.uat_add_test_case')}
          </Button>
        </div>

        <div className="cpp-actions">
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
  const ISSUE_STATUS = ['open', 'fixed', 'deferred', 'wontfix']

  return (
    <Modal open title={`${initialSession.code} — ${initialSession.title}`} onClose={onClose} width={700}>
      <div className="cpp-detail-head">
        <StatusBadge status={initialSession.status} cfg={STATUS_CFG} />
        {initialSession.test_environment && <a href={initialSession.test_environment} target="_blank" rel="noopener noreferrer" className="cpp-link cpp-con-icono"><Link2 size={13} aria-hidden="true" />{t('client_portal.uat_detail_test_env')}</a>}
        {initialSession.deadline && <span className="u-text2-sm">{`${t('client_portal.uat_deadline')}: ${fmtDate(initialSession.deadline)}`}</span>}
      </div>

      {initialSession.client_notes && (
        <div className="cpp-notes">
          <div className="cpp-notes__title">{t('client_portal.uat_detail_client_notes')}</div>
          <p className="cpp-notes__text">{initialSession.client_notes}</p>
        </div>
      )}

      {/* Test cases */}
      {initialSession.test_cases.length > 0 && (
        <div className="u-mb-16">
          <div className="cpp-section-title">
            {t('client_portal.uat_detail_cases_summary', { passed: initialSession.stats.passed, total: initialSession.stats.total })}
          </div>
          <div className="u-stack-8">
            {initialSession.test_cases.map(tc => {
              const color = tc.status === 'passed' ? 'var(--success)' : tc.status === 'failed' ? 'var(--danger)' : 'var(--text-2)'
              return (
                <div key={tc.id} className="cpp-item cpp-item--case" style={colorVar(color)}>
                  <div className="cpp-row-top">
                    <div className="u-flex1">
                      <div className="cpp-item__title">{tc.title}</div>
                      {tc.expected_result && <div className="u-text2-sm">{`${t('client_portal.uat_expected')}: ${tc.expected_result}`}</div>}
                      {tc.actual_result && <div className="cpp-item__result">{`${t('client_portal.uat_result')}: ${tc.actual_result}`}</div>}
                    </div>
                    <span className="cpp-chip cpp-con-icono">
                      {tc.status === 'passed' ? <><CheckCircle2 size={12} aria-hidden="true" />{t('clientportalpage.estado_passed')}</>
                        : tc.status === 'failed' ? <><XCircle size={12} aria-hidden="true" />{t('clientportalpage.estado_failed')}</>
                        : <><Minus size={12} aria-hidden="true" />{t('client_portal.uat_pending')}</>}
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
          <div className="cpp-section-title">
            {t('client_portal.uat_issues_summary', { n: initialSession.issues.filter(i => i.status === 'open').length })}
          </div>
          <div className="u-stack-8">
            {initialSession.issues.map(issue => {
              const sevColor = SEV_COLORS[issue.severity] || 'var(--text-2)'
              return (
                <div key={issue.id} className={issue.status === 'open' ? 'cpp-item cpp-item--issue-open' : 'cpp-item'} style={colorVar(sevColor)}>
                  <div className="cpp-row-top cpp-row-top--gap">
                    <div className="u-flex1">
                      <div className="cpp-title-row cpp-title-row--sm">
                        <span className="cpp-sev">{SEV_COLORS[issue.severity] ? t(`clientportalpage.sev_${issue.severity}`) : issue.severity}</span>
                        <span className="u-base-600">{issue.title}</span>
                      </div>
                      <p className="cpp-issue__desc">{issue.description}</p>
                    </div>
                    {issue.status === 'open' && (
                      <select defaultValue={issue.status} onChange={e => updateIssue({ id: issue.id, status: e.target.value })}
                        aria-label={t('clientportalpage.estado_incidencia', { title: issue.title })}
                        className="cpp-select-sm">
                        <option value="open">{t('client_portal.uat_issue_open')}</option>
                        <option value="fixed">{t('client_portal.uat_issue_fixed')}</option>
                        <option value="deferred">{t('client_portal.uat_issue_deferred')}</option>
                        <option value="wontfix">{t('client_portal.uat_issue_wontfix')}</option>
                      </select>
                    )}
                    {issue.status !== 'open' && <span className="cpp-resolved cpp-con-icono"><Check size={12} aria-hidden="true" />{ISSUE_STATUS.includes(issue.status) ? t(`client_portal.uat_issue_${issue.status}`) : issue.status}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="cpp-footer">
        <Button variant="secondary" onClick={onClose}>{t('client_portal.close')}</Button>
      </div>
    </Modal>
  )
}

// ── Feature Requests Tab ──────────────────────────────────────────────────────
function FeatureRequestsTab({ projectId }: { projectId: string }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [responding, setResponding] = useState<PeticionDeCambio | null>(null)
  const [responseForm, setResponseForm] = useState<RespuestaPeticion>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs', projectId],
    queryFn: () => portalApi.featureRequests({ project_id: projectId }).then(r => r.data),
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

  return (
    <div>
      {isLoading ? <Spinner /> : frs.length === 0 ? (
        <EmptyState svgIcon={<Lightbulb size={36} />} title={t('client_portal.fr_empty_title')} description={t('client_portal.fr_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {frs.map(fr => (
            <div key={fr.id} className="cpp-fr" style={colorVar(fr.priority_color)}>
              <div className="cpp-row-top cpp-row-top--mb">
                <div className="u-flex1">
                  <div className="cpp-title-row cpp-title-row--sm">
                    <span className="u-text2-mono-xs">{fr.code}</span>
                    <span className="u-md-700">{fr.title}</span>
                  </div>
                  <p className="cpp-fr__desc">{fr.description}</p>
                  <div className="cpp-fr__meta">
                    <span className="cpp-fr__prio cpp-con-icono"><Zap size={12} aria-hidden="true" />{fr.priority_label}</span>
                    {fr.affected_area && <span className="u-text2 cpp-con-icono"><ClipboardList size={12} aria-hidden="true" />{fr.affected_area}</span>}
                    {fr.client_name && <span className="u-text2 cpp-con-icono"><User size={12} aria-hidden="true" />{fr.client_name}</span>}
                    <span className="u-text2">{fmtDate(fr.submitted_at)}</span>
                  </div>
                  {fr.pm_response && (
                    <div className="cpp-fr__response">
                      <span className="u-text2">{`${t('client_portal.fr_pm_response')}: `}</span>{fr.pm_response}
                      {fr.estimated_cost && <span className="cpp-fr__cost cpp-con-icono"><Wallet size={12} aria-hidden="true" />{fmtMoneda(fr.estimated_cost, { decimales: 0 })}</span>}
                      {fr.estimated_delivery_weeks && <span className="cpp-fr__weeks cpp-con-icono"><CalendarDays size={12} aria-hidden="true" />{t('clientportalpage.n_semanas', { count: fr.estimated_delivery_weeks })}</span>}
                    </div>
                  )}
                  {fr.client_approved === true && <div className="cpp-fr__approved cpp-con-icono"><CheckCircle2 size={13} aria-hidden="true" />{`${t('client_portal.fr_client_approved')} ${fmtDate(fr.client_approved_at)}`}</div>}
                  {fr.client_approved === false && <div className="cpp-fr__rejected cpp-con-icono"><XCircle size={13} aria-hidden="true" />{t('client_portal.fr_client_rejected')}</div>}
                </div>
                <div className="cpp-fr__side">
                  <StatusBadge status={fr.status} cfg={FR_STATUS_CFG} />
                  {['new', 'reviewing'].includes(fr.status) && (
                    <Button size="sm" icon={<MessageSquare size={13} />} onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                      {t('client_portal.fr_respond')}
                    </Button>
                  )}
                  {fr.status === 'approved' && (
                    <Button size="sm" variant="secondary" icon={<Rocket size={13} />} onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                      {t('client_portal.fr_start_dev')}
                    </Button>
                  )}
                  {fr.status === 'in_development' && (
                    <Button size="sm" variant="secondary" icon={<CheckCircle2 size={13} />} onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                      {t('client_portal.fr_completed')}
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
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.fr_label_response')} *</label><textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} className="cpp-input" placeholder={t('client_portal.fr_response_placeholder')} /></div>
            <div className="cpp-grid-3">
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.fr_label_hours')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} className="cpp-input" placeholder={t('clientportalpage.ejemplo', { valor: 8 })} /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.fr_label_cost')} ({fmtMoneda.simbolo})</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} className="cpp-input" placeholder={t('clientportalpage.ejemplo', { valor: 1200 })} /></div>
              <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.fr_label_weeks')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} className="cpp-input" placeholder={t('clientportalpage.ejemplo', { valor: 4 })} /></div>
            </div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.fr_label_status')}</label>
              <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} className="cpp-input">
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
        emptyTitle={traducir('clientportalpage.sin_conversaciones')}
        emptyDescription={traducir('clientportalpage.sin_conversaciones_desc')}
        projectOptions={projectId ? [{ id: projectId, name: projectId, code: '' }] : []}
        initialProjectId={projectId || ''}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

// ── Documents Tab ─────────────────────────────────────────────────────────────
function DocumentsTab({ projectId }: { projectId: string }) {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [docForm, setDocForm] = useState<FormDocumento>({ title: '', description: '', category: 'deliverable', file_url: '', file_name: '', requires_signature: false })

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs', projectId],
    queryFn: () => portalApi.documents({ project_id: projectId }).then(r => r.data),
    enabled: !!projectId,
  })
  const { mutate: addDoc } = useMutation({
    mutationFn: (data: FormDocumento) => portalApi.createDocument(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-docs', projectId] }); setShowAdd(false) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const CAT_LABELS: Record<string, string> = {
    contract: t('client_portal.docs_contract'),
    deliverable: t('client_portal.docs_deliverable'),
    meeting_notes: t('client_portal.docs_meeting_notes'),
    report: t('client_portal.docs_report'),
    other: t('client_portal.docs_other'),
  }
  const CAT_ICONS: Record<string, React.ReactNode> = {
    contract: <FileSignature size={16} />, deliverable: <Package size={16} />, meeting_notes: <NotebookPen size={16} />,
    report: <BarChart3 size={16} />, other: <FileText size={16} />,
  }
  const CAT_COLORS: Record<string, string> = { contract: 'var(--purple)', deliverable: 'var(--success)', meeting_notes: 'var(--accent)', report: 'var(--warning)', other: 'var(--text-2)' }

  return (
    <div>
      <div className="cpp-tab-head">
        <div className="u-text2-base">{docs.length} {t('client_portal.docs_count')}</div>
        <Button onClick={() => setShowAdd(true)} icon={<Plus size={14} />}>{t('client_portal.docs_add')}</Button>
      </div>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState svgIcon={<FileText size={36} />} title={t('client_portal.docs_empty_title')} description={t('client_portal.docs_empty_desc')} />
      ) : (
        <div className="ds-card ds-card--plano">
          {docs.map(doc => {
            const color = CAT_COLORS[doc.category] || 'var(--text-2)'
            return (
              <div key={doc.id} className="cpp-row">
                <span className="cpp-doc__icon" aria-hidden="true">{CAT_ICONS[doc.category] || <FileText size={16} />}</span>
                <div className="u-flex1">
                  <div className="u-base-700">{doc.title}</div>
                  <div className="u-text2-xs">
                    <span className="cpp-doc__cat" style={colorVar(color)}>{CAT_LABELS[doc.category] || t('client_portal.docs_other')}</span>
                    {doc.file_name && ` · ${doc.file_name}`}
                    {doc.created_at && ` · ${fmtDate(doc.created_at)}`}
                  </div>
                </div>
                {doc.requires_signature && (
                  <span className={doc.signed_by_client ? 'cpp-sign is-signed cpp-con-icono' : 'cpp-sign cpp-con-icono'}>
                    {doc.signed_by_client ? <Check size={12} aria-hidden="true" /> : <Hourglass size={12} aria-hidden="true" />}
                    {doc.signed_by_client ? t('client_portal.docs_signed') : t('client_portal.docs_pending_signature')}
                  </span>
                )}
                {doc.file_url && (
                  <a href={doc.file_url} target="_blank" rel="noopener noreferrer" className="cpp-btn cpp-con-icono">
                    <Download size={13} aria-hidden="true" />{t('client_portal.docs_download')}
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
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.docs_label_title')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={docForm.title} onChange={e => setDocForm(f => ({ ...f, title: e.target.value }))} className="cpp-input" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.docs_label_category')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={docForm.category} onChange={e => setDocForm(f => ({ ...f, category: e.target.value }))} className="cpp-input">
                {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.docs_label_file_url')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="url" value={docForm.file_url} onChange={e => setDocForm(f => ({ ...f, file_url: e.target.value }))} className="cpp-input" placeholder="https://..." /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.docs_label_file_name')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={docForm.file_name} onChange={e => setDocForm(f => ({ ...f, file_name: e.target.value }))} className="cpp-input" placeholder={t('client_portal.docs_placeholder_file_name')} /></div>
            <label className="u-row-center-8-pointer">
              <input type="checkbox" aria-label={t('client_portal.docs_requires_signature')} checked={docForm.requires_signature} onChange={e => setDocForm(f => ({ ...f, requires_signature: e.target.checked }))} />
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
    queryFn: () => wikiApi.portalSpaces().then(r => r.data.filter(s => !projectId || s.project_id === projectId || !s.project_id)),
  })
  const [selectedSpace, setSelectedSpace] = React.useState('')
  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['wiki-pages-portal-op', selectedSpace],
    // Antes solo salían las páginas raíz: las subpáginas no se podían publicar.
    queryFn: () => wikiApi.portalPages(selectedSpace).then(r => aplanarPaginas(r.data)),
    enabled: !!selectedSpace,
  })
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: setVis } = useMutation({
    mutationFn: ({ id, visibility }: { id: string; visibility: VisibilidadDeWiki }) => wikiApi.portalUpdatePage(id, { visibility }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wiki-pages-portal-op', selectedSpace] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const VIS: Record<VisibilidadDeWiki, { label: string; color: string }> = {
    team:   { label: `${t('client_portal.wiki_vis_team')}`, color: 'var(--text-2)' },
    portal: { label: `${t('client_portal.wiki_vis_portal')}`, color: 'var(--accent)' },
    public: { label: `${t('client_portal.wiki_vis_public')}`, color: 'var(--success)' },
  }

  return (
    <div>
      <div className="cpp-info">
        <strong className="u-accent cpp-con-icono"><Info size={14} aria-hidden="true" />{t('client_portal.wiki_info_title')}</strong>
        {' '}— {t('client_portal.wiki_info_desc')}
      </div>
      <div className="cpp-wiki-filter">
        <select value={selectedSpace} onChange={e => setSelectedSpace(e.target.value)}
          aria-label={t('client_portal.wiki_select_space')}
          className="cpp-input cpp-input--roomy u-flex1">
          <option value="">{t('client_portal.wiki_select_space')}</option>
          {spaces.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      {isLoading && <Spinner />}
      {selectedSpace && !isLoading && pages.length === 0 && (
        <EmptyState svgIcon={<BookOpen size={36} />} title={t('client_portal.wiki_empty_title')} description={t('client_portal.wiki_empty_desc')} />
      )}
      {pages.length > 0 && (
        <div className="ds-card ds-card--plano">
          {pages.map(page => (
            <div key={page.id} className="cpp-row cpp-row--wiki">
              <span className="cpp-wiki-icon" aria-hidden="true" style={{ '--cpp-nivel': page.nivel } as CSSProperties}><FileText size={14} /></span>
              <div className="u-flex1">
                <div className="u-base-600">{page.title}</div>
                <div className="u-text2-xs">{page.slug}</div>
              </div>
              <div className="u-row-6" role="group" aria-label={t('clientportalpage.visibilidad_de', { title: page.title })}>
                {(Object.entries(VIS) as Array<[VisibilidadDeWiki, { label: string; color: string }]>).map(([val, cfg]) => (
                  <button key={val} type="button" onClick={() => setVis({ id: page.id, visibility: val })}
                    aria-pressed={page.visibility === val}
                    className="cpp-vis" style={colorVar(cfg.color)}>
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
    queryFn: () => portalApi.stats(projectId).then(r => r.data),
    enabled: !!projectId,
    refetchInterval: NOTIFICATIONS_POLL_MS,
  })
  if (!stats) return null
  return (
    <div className="ds-grid-stats cpp-stats-kpi">
      <KpiCard icon={<Users size={16} />} label={t('client_portal.stat_contacts')} value={stats.client_count} />
      <KpiCard icon={<MessageCircle size={16} />} label={t('client_portal.stat_unread_messages')} value={stats.unread_messages} warning={stats.unread_messages > 0} />
      <KpiCard icon={<Lightbulb size={16} />} label={t('client_portal.stat_pending_requests')} value={stats.fr_pending_review} danger={stats.fr_pending_review > 0} />
      <KpiCard icon={<FlaskConical size={16} />} label={t('client_portal.stat_pending_uat')} value={stats.uat_pending} accent={stats.uat_pending > 0} />
      <KpiCard icon={<Star size={16} />} label={t('client_portal.stat_avg_satisfaction')} value={stats.avg_satisfaction ? `${stats.avg_satisfaction}/5` : '—'} />
      <KpiCard icon={<Gauge size={16} />} label={t('client_portal.stat_avg_nps')} value={stats.avg_nps ?? '—'}
        danger={stats.avg_nps != null && stats.avg_nps < 6} warning={stats.avg_nps != null && stats.avg_nps >= 6 && stats.avg_nps < 8} />
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
    { id: 'clients',  label: t('client_portal.tab_contacts'), icon: <Users size={14} /> },
    { id: 'uat',      label: t('client_portal.tab_uat'), icon: <FlaskConical size={14} /> },
    { id: 'requests', label: t('client_portal.tab_requests'), icon: <Lightbulb size={14} /> },
    { id: 'messages', label: t('client_portal.tab_messages'), icon: <MessageSquare size={14} /> },
    { id: 'documents',label: t('client_portal.tab_documents'), icon: <FileText size={14} /> },
    { id: 'wiki',     label: t('client_portal.tab_wiki'), icon: <BookOpen size={14} /> },
  ]

  return (
    <Page
      icon={<Globe size={18} />}
      title={t('client_portal.title')}
      subtitle={t('client_portal.subtitle')}
    >
      {/* 16-11-2026 (pasada de diseño): el selector de proyecto es un filtro y va
          en la barra de filtros, no en la cabecera. */}
      <div className="ds-toolbar">
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          aria-label={t('client_portal.select_project')}
          className="ds-input cpp-project-select">
          <option value="">{t('client_portal.select_project')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
      </div>

      {selectedProject && <StatsPanel projectId={selectedProject} />}

      <Tabs className="cpp-tabs" items={TABS} active={tab} onChange={setTab} ariaLabel={traducir('clientportal.secciones_del_portal_cliente')} />

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