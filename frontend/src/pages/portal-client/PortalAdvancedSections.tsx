/**
 * PortalAdvancedSections — todas las páginas internas del portal cliente
 * con el lenguaje visual del backoffice (PortalUI).
 *
 * Exports:
 *   PortalUAT, PortalFeatureRequests, PortalMessages,
 *   PortalInvoices, PortalRoadmap, PortalDocuments, PortalWiki
 */
import { useEffect, useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FlaskConical, Lightbulb, Map, BookOpen, FileText, Receipt,
  MessageSquare, Plus, Search, ArrowLeft, Bug, FileSignature,
  Download, CheckCircle2, XCircle, Clock,
  ExternalLink, Key, Package,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconCR } from '../../components/ui/FRCRIcons'
import { ClientGovernedConversationInbox } from '../../components/portal/GovernedConversations'
import { CLIENT_API, useLang, useClientAuth } from './portalClientContext'
import type { ApiError } from '../../services/api'
import PortalKbArticulo from './PortalKbArticulo'
import {
  PortalPageHeader, PortalCard, PortalSection, PortalEmpty,
  PortalBadge, PortalButton, PortalModal, PortalField, PortalInput,
  PortalSelect, PortalTextarea, PortalProgress, PortalBanner,
  formatMoney, metaItems, MONEDA_PORTAL_POR_DEFECTO,
} from './PortalUI'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { useTabListKeys } from '../../components/ui/Tabs'
import { POLL_FAST_MS, POLL_FREQUENT_MS } from '../../constants/timings'
import './PortalAdvancedSections.css'

// ── Status helpers ───────────────────────────────────────────────────────────
const STATUS_TONE: Record<string, string> = {
  pending: 'warning', new: 'default', reviewing: 'accent', estimated: 'warning',
  approved: 'success', rejected: 'danger', passed: 'success', conditional: 'success',
  failed: 'danger', in_progress: 'accent', planned: 'default', delivered: 'accent',
  accepted: 'success', closed: 'default', resolved: 'success', cancelled: 'default',
  paid: 'success', overdue: 'danger', sent: 'warning', draft: 'default',
}

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null
  return <PortalBadge tone={STATUS_TONE[status] || 'default'}>{String(status).replace(/_/g, ' ')}</PortalBadge>
}

// ── Respuestas del portal ────────────────────────────────────────────────────
// Campos según los serializadores de app/services/client_portal_service
// (serializacion.py, facturas.py, panel.py, wiki_y_encuestas.py).

/** `_uat_test_cases_out`. */
interface UatTestCase {
  id: string
  title: string
  steps?: string | null
  expected_result?: string | null
  actual_result?: string | null
  status: string
  notes?: string | null
  order?: number
}

/** `_uat_issues_out`. */
interface UatIssue {
  id: string
  title: string
  description?: string | null
  severity?: string
  status: string
  steps_to_reproduce?: string | null
}

/** `uat_out`. */
interface UatSession {
  id: string
  code?: string
  title: string
  description?: string | null
  test_environment?: string | null
  test_credentials?: string | null
  status: string
  deadline?: string | null
  overdue?: boolean | null
  test_cases?: UatTestCase[]
  issues?: UatIssue[]
  stats?: { total: number; passed: number; failed: number; pending: number }
}

/** `fr_out` (+ `can_edit_by_client` que añade el listado). */
interface FeatureRequest {
  id: string
  code?: string
  project_id?: string | null
  project_name?: string
  title: string
  description?: string | null
  business_justification?: string | null
  affected_area?: string | null
  priority?: string
  status: string
  pm_response?: string | null
  estimated_hours?: number | null
  estimated_cost?: number | null
  estimated_delivery_weeks?: number | null
  client_approved?: boolean | null
  client_approved_at?: string | null
  submitted_at?: string | null
  can_edit_by_client?: boolean
  cr_status?: string | null
  cr_status_label?: string | null
  cr_status_color?: string | null
}

/** Formulario de alta/edición de una solicitud. */
interface FeatureRequestForm {
  title: string
  description: string
  business_justification: string
  affected_area: string
  priority: string
  project_id: string
}

/** Proyecto tal como viene en la sesión del cliente (`client.projects`). */
interface ClientProject {
  id: string
  name?: string
  code?: string
}

/** Conversación de `/portal/collaboration/conversations`. */
interface CollabConversation {
  id: string
  title?: string
}

/** Mensaje de `/portal/collaboration/conversations/{id}/messages`. */
interface CollabMessage {
  id: string
  body: string
  author_name?: string | null
  client_user_id?: string | number | null
  sent_at: string
}

/** Factura de `list_client_invoices` (facturas.py). */
interface ClientInvoice {
  id: string
  number?: string | null
  client_name?: string | null
  status: string
  subtotal?: number | null
  tax_amount?: number | null
  total?: number | null
  currency?: string | null
  issue_date?: string | null
  due_date?: string | null
  client_approval_status?: string | null
}

interface RoadmapMilestone {
  id: string
  name: string
  due_date?: string | null
  is_completed?: boolean
  billing_pct?: number | null
}

interface RoadmapDeliverable {
  id: string
  name: string
  format?: string | null
  status: string
  planned_date?: string | null
}

/** `GET /portal/project` (panel.py), lo que pinta el roadmap. */
interface ClientProjectDetail {
  milestones?: RoadmapMilestone[]
  deliverables?: RoadmapDeliverable[]
}

/** `doc_out`. */
interface ClientDocument {
  id: string
  title: string
  description?: string | null
  category?: string | null
  file_url?: string | null
  file_name?: string | null
  requires_signature?: boolean
  signed_by_client?: boolean
  signed_at?: string | null
  created_at?: string
}

interface WikiPageSummary {
  id: string
  title: string
  updated_at?: string | null
}

interface WikiBlock {
  type?: string
  content?: string
}

interface WikiPageDetail extends WikiPageSummary {
  content?: WikiBlock[]
}

interface KbArticle {
  id: string
  title: string
  summary?: string | null
  tags?: string | null
  view_count?: number
  helpful_count?: number
}

// ════════════════════════════════════════════════════════════════════════════
// PortalUAT
// ════════════════════════════════════════════════════════════════════════════
export function PortalUAT() {
  const { t: traducir } = useAppLang()
  const t = useLang()
  const qc = useQueryClient()
  const toast = useToast()
  const issueIdPrefix = useId()
  const [selected, setSelected] = useState<UatSession | null>(null)
  const [testResults, setTestResults] = useState<Record<string, string>>({})
  const [globalNotes, setGlobalNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [reportingIssue, setReportingIssue] = useState(false)
  const [issueForm, setIssueForm] = useState({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })

  const { data: sessions = [], isLoading } = useQuery<UatSession[]>({
    queryKey: ['portal-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data),
  })

  const submitResult = async (sessionId: string, result: string) => {
    setSubmitting(true)
    try {
      const testCases = selected?.test_cases?.map(tc => ({
        id: tc.id, status: testResults[tc.id] || 'pending', actual_result: '', notes: '',
      })) || []
      await CLIENT_API.post(`/portal/uat/${sessionId}/submit-result`, { result, notes: globalNotes, test_cases: testCases })
      qc.invalidateQueries({ queryKey: ['portal-uat'] })
      toast.success(traducir('portaladvanced.resultado_enviado'))
      setSelected(null)
    } catch (e) {
      toast.error(extractErr(e, 'Error al enviar resultado'))
    } finally { setSubmitting(false) }
  }

  const submitIssue = async () => {
    try {
      await CLIENT_API.post(`/portal/uat/${selected?.id}/issues`, issueForm)
      qc.invalidateQueries({ queryKey: ['portal-uat'] })
      toast.success(traducir('portaladvanced.incidencia_reportada'))
      setReportingIssue(false)
      setIssueForm({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })
    } catch (e) {
      toast.error(extractErr(e, 'Error al reportar incidencia'))
    }
  }

  // ── Detail view ────────────────────────────────────────────────────────────
  if (selected) {
    const hasFailure = Object.values(testResults).includes('failed')
    return (
      <div>
        <PortalPageHeader
          title={selected.title}
          subtitle={selected.description}
          icon={FlaskConical}
          breadcrumb={[
            { label: t('nav_uat') || 'UAT', onClick: () => setSelected(null) },
            { label: selected.title },
          ]}
          actions={
            <PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />}
              onClick={() => setSelected(null)}>{traducir('chat.back')}</PortalButton>
          }
        />

        {(selected.test_environment || selected.test_credentials) && (
          <PortalCard className="portalad-sx1">
            <PortalSection title={traducir('portaladvanced.entorno_de_pruebas')}>
              <div className="poadse-row-1">
                {selected.test_environment && (
                  <a href={selected.test_environment} target="_blank" rel="noopener noreferrer" className="poadse-row-2">
                    <ExternalLink size={13} /> {traducir('portaladvanced.abrir_entorno')}
                  </a>
                )}
                {selected.test_credentials && (
                  <div className="poadse-row-3">
                    <Key size={13} /> {selected.test_credentials}
                  </div>
                )}
              </div>
            </PortalSection>
          </PortalCard>
        )}

        {selected.test_cases?.length > 0 && (
          <div className="u-mb-16">
            <div className="poadse-box-1">{traducir('portaladvanced.casos_de_prueba')}</div>
            <div className="u-stack-10">
              {selected.test_cases.map(tc => (
                <PortalCard key={tc.id}>
                  <div className="u-mb-10">
                    <div className="poadse-box-2">{tc.title}</div>
                    {tc.steps && <div className="poadse-box-3">📋 {tc.steps}</div>}
                    {tc.expected_result && <div className="poadse-txt-1">✓ {tc.expected_result}</div>}
                  </div>
                  <div className="u-row-8">
                    {[
                      { val: 'passed', label: 'Pasado', color: 'var(--success)', icon: <CheckCircle2 size={14} /> },
                      { val: 'failed', label: 'Fallado', color: 'var(--danger)',  icon: <XCircle size={14} /> },
                    ].map(opt => (
                      <button className="poadse-row-29 portalad-sx2" key={opt.val} onClick={() => setTestResults(r => ({ ...r, [tc.id]: opt.val }))} style={{ border: `1px solid ${testResults[tc.id] === opt.val ? opt.color : 'var(--surface-4)'}`, background: testResults[tc.id] === opt.val ? alpha(opt.color, '1a') : 'var(--surface-3)', color: testResults[tc.id] === opt.val ? opt.color : 'var(--text-2)' }}>{opt.icon} {opt.label}</button>
                    ))}
                  </div>
                </PortalCard>
              ))}
            </div>
          </div>
        )}

        {selected.issues?.length > 0 && (
          <div className="u-mb-16">
            <div className="poadse-box-1">{traducir('client_portal.uat_issues_title')}</div>
            <div className="u-stack-8">
              {selected.issues.map(issue => (
                <PortalCard key={issue.id} padding={14}>
                  <div className="poadse-row-4">
                    <div>
                      <div className="u-sm-700">{issue.title}</div>
                      <p className="poadse-box-4">{issue.description}</p>
                    </div>
                    <PortalBadge tone={issue.status === 'fixed' ? 'success' : 'danger'}>{issue.status === 'fixed' ? 'Corregido' : 'Abierto'}</PortalBadge>
                  </div>
                </PortalCard>
              ))}
            </div>
          </div>
        )}

        <PortalCard className="portalad-sx1">
          <PortalField label={traducir('portaladvanced.notas_para_el_equipo')}>
            <PortalTextarea rows={3} value={globalNotes} onChange={e => setGlobalNotes(e.target.value)} placeholder={traducir('portaladvanced.comentarios_generales_de_la_sesion')} />
          </PortalField>
        </PortalCard>

        <div className="u-wrap-10">
          <PortalButton variant="secondary" icon={<Bug size={14} />} onClick={() => setReportingIssue(true)}>
            {traducir('portaladvanced.reportar_incidencia')}
          </PortalButton>
          {selected.status !== 'passed' && selected.status !== 'failed' && (
            <>
              <PortalButton variant="danger" icon={<XCircle size={14} />}
                onClick={() => submitResult(selected.id, 'failed')} loading={submitting}>
                {traducir('aus.rechazar')}
              </PortalButton>
              <PortalButton variant="primary" icon={<CheckCircle2 size={14} />}
                onClick={() => submitResult(selected.id, hasFailure ? 'conditional' : 'passed')}
                loading={submitting}>
                {hasFailure ? 'Aprobar con observaciones' : 'Aprobar'}
              </PortalButton>
            </>
          )}
        </div>

        <PortalModal
          open={reportingIssue}
          onClose={() => setReportingIssue(false)}
          title={traducir('portaladvanced.reportar_incidencia')}
          subtitle={traducir('portaladvanced.describe_el_problema_encontrado_durante_la_prueba')}
          footer={
            <>
              <PortalButton variant="secondary" onClick={() => setReportingIssue(false)}>{traducir('common.cancel')}</PortalButton>
              <PortalButton onClick={submitIssue} disabled={!issueForm.title || !issueForm.description}>{traducir('chat.send')}</PortalButton>
            </>
          }
        >
          <div className="u-stack-14">
            <PortalField label={traducir('portaladvanced.titulo')} required>
              <PortalInput id={`${issueIdPrefix}-title`} value={issueForm.title} onChange={e => setIssueForm(f => ({ ...f, title: e.target.value }))} />
            </PortalField>
            <PortalField label={traducir('portaladvanced.descripcion')} required>
              <PortalTextarea rows={3} value={issueForm.description} onChange={e => setIssueForm(f => ({ ...f, description: e.target.value }))} />
            </PortalField>
            <PortalField label={traducir('lec.severidad')}>
              <PortalSelect value={issueForm.severity} onChange={e => setIssueForm(f => ({ ...f, severity: e.target.value }))}>
                <option value="low">{traducir('lec.sev_baja')}</option>
                <option value="medium">{traducir('lec.sev_media')}</option>
                <option value="high">{traducir('lec.sev_alta')}</option>
                <option value="blocker">{traducir('clientportalpage.sev_blocker')}</option>
              </PortalSelect>
            </PortalField>
            <PortalField label={traducir('portaladvanced.pasos_para_reproducir')}>
              <PortalTextarea rows={2} value={issueForm.steps_to_reproduce} onChange={e => setIssueForm(f => ({ ...f, steps_to_reproduce: e.target.value }))} />
            </PortalField>
          </div>
        </PortalModal>
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div>
      <PortalPageHeader
        title="UAT"
        subtitle={traducir('portaladvanced.sesiones_de_aceptacion_de_usuario_donde_validas')}
        icon={FlaskConical}
        meta={[
          { value: sessions.length, label: 'sesiones' },
          { value: sessions.filter(s => ['pending', 'in_progress'].includes(s.status)).length, label: 'pendientes', color: 'var(--warning)' },
          { value: sessions.filter(s => ['passed', 'conditional'].includes(s.status)).length, label: 'aprobadas', color: 'var(--success)' },
        ]}
      />

      {isLoading ? (
        <div className="poadse-box-5">{traducir('common.loading')}</div>
      ) : sessions.length === 0 ? (
        <PortalEmpty icon={FlaskConical}
          title={traducir('portaladvanced.no_hay_sesiones_uat')}
          description={traducir('portaladvanced.cuando_el_equipo_prepare_una_entrega_para')}
        />
      ) : (
        <div className="u-stack-12">
          {sessions.map(s => (
            <PortalCard key={s.id} onClick={() => { setSelected(s); setTestResults({}); setGlobalNotes('') }}>
              <div className="poadse-row-5">
                <div className="u-flex1-min0">
                  <div className="poadse-row-6">
                    <FlaskConical size={16} className="portalad-sx3" />
                    <div className="poadse-txt-2">{s.title}</div>
                  </div>
                  <div className="poadse-box-6">
                    {s.deadline && (
                      <span className="poadse-row-30" style={{ color: s.overdue ? 'var(--danger)' : 'var(--text-2)' }}>
                        <Clock size={12} /> {s.overdue ? 'Vencido: ' : 'Plazo: '}{s.deadline}
                      </span>
                    )}
                  </div>
                  {s.stats?.total > 0 && (
                    <div className="poadse-row-7">
                      <span>{s.stats.total} {traducir('client_portal.uat_cases')}</span>
                      <span className="u-success">✓ {s.stats.passed}</span>
                      <span className="u-danger">✗ {s.stats.failed}</span>
                    </div>
                  )}
                </div>
                <StatusBadge status={s.status} />
              </div>
            </PortalCard>
          ))}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalFeatureRequests
// ════════════════════════════════════════════════════════════════════════════
export function PortalFeatureRequests() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const formIdPrefix = useId()
  const { client } = useClientAuth()
  // `projects` llega sin tipar en la sesión; aquí se usan id, nombre y código.
  const clientProjects = (client?.projects || []) as ClientProject[]
  const [showNew, setShowNew] = useState(false)
  const [editingFr, setEditingFr] = useState<FeatureRequest | null>(null)
  const [form, setForm] = useState<FeatureRequestForm>({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })

  const { data: frs = [], isLoading } = useQuery<FeatureRequest[]>({
    queryKey: ['portal-frs-client'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data),
  })

  const resetForm = () => setForm({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })

  const { mutate: createFR } = useMutation({
    mutationFn: (d: FeatureRequestForm) => CLIENT_API.post('/portal/feature-requests', d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); setShowNew(false); resetForm(); toast.success(traducir('intake_form.success_title')) },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al enviar')),
  })
  const { mutate: updateFR, isPending: updatingFr } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FeatureRequestForm }) => CLIENT_API.patch(`/portal/feature-requests/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); setEditingFr(null); setShowNew(false); resetForm(); toast.success(traducir('portaladvanced.actualizada')) },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al actualizar')),
  })
  const { mutate: withdrawFR, isPending: withdrawingFr } = useMutation({
    mutationFn: ({ id }: { id: string }) => CLIENT_API.post(`/portal/feature-requests/${id}/withdraw`, {}),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); toast.success(traducir('portaladvanced.solicitud_retirada')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: decide } = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) => CLIENT_API.post(`/portal/feature-requests/${id}/decide`, { approved, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); toast.success(traducir('chat.decision_registrada')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const openEdit = (fr: FeatureRequest) => {
    setEditingFr(fr); setShowNew(true)
    setForm({
      title: fr.title || '', description: fr.description || '',
      business_justification: fr.business_justification || '',
      affected_area: fr.affected_area || '', priority: fr.priority || 'medium',
      project_id: fr.project_id || '',
    })
  }

  const totalProjects = client?.projects?.length || client?.project_ids?.length || 0
  const requiresProject = totalProjects > 1

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.solicitudes_y_cambios')}
        subtitle={traducir('portaladvanced.tus_peticiones_de_nuevas_funcionalidades_y_cambios')}
        icon={Lightbulb}
        meta={[
          { value: frs.length, label: 'totales' },
          { value: frs.filter(f => f.status === 'estimated' && f.client_approved == null).length, label: 'esperan tu decisión', color: 'var(--warning)' },
          { value: frs.filter(f => f.status === 'approved').length, label: 'aprobadas', color: 'var(--success)' },
        ]}
        actions={
          client?.can_request_changes ? (
            <PortalButton icon={<Plus size={14} />} onClick={() => { resetForm(); setEditingFr(null); setShowNew(true) }}>
              {traducir('portaladvanced.nueva_solicitud')}
            </PortalButton>
          ) : null
        }
      />

      {isLoading ? null : frs.length === 0 ? (
        <PortalEmpty icon={Lightbulb}
          title={traducir('portaladvanced.sin_solicitudes')}
          description={client?.can_request_changes ? '¿Necesitas algo nuevo? Crea tu primera solicitud y el equipo te enviará una estimación.' : 'No tienes permiso para solicitar cambios. Contacta con tu PM para ello.'}
          action={client?.can_request_changes ? (
            <PortalButton icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{traducir('portaladvanced.nueva_solicitud')}</PortalButton>
          ) : null}
        />
      ) : (
        <div className="u-stack-12">
          {frs.map(fr => (
            <PortalCard key={fr.id}>
              <div className="poadse-row-8">
                <div className="u-flex1-min0">
                  <div className="poadse-row-9">
                    <span className="u-text3-mono-xs">{fr.code}</span>
                    <span className="poadse-txt-2">{fr.title}</span>
                  </div>
                  <div className="poadse-row-10">
                    {fr.project_name && <span>📁 {fr.project_name}</span>}
                    {fr.submitted_at && <span>{traducir('portaladvanced.creada')} {fr.submitted_at}</span>}
                    {fr.affected_area && <span>{traducir('portaladvanced.area')} {fr.affected_area}</span>}
                  </div>
                  <p className="poadse-box-7">{fr.description}</p>
                  {fr.pm_response && (
                    <div className="poadse-box-8">
                      <div className="poadse-box-9">
                        {traducir('portaladvanced.respuesta_del_pm')}
                      </div>
                      <p className="poadse-box-10">{fr.pm_response}</p>
                      <div className="poadse-row-11">
                        {fr.estimated_cost && <span className="poadse-txt-3">💶 {formatMoney(fr.estimated_cost)}</span>}
                        {fr.estimated_hours && <span className="u-accent">⏱ {fr.estimated_hours}h</span>}
                        {fr.estimated_delivery_weeks && <span className="u-text2">📅 ~{fr.estimated_delivery_weeks} {traducir('bi.weeks')}</span>}
                      </div>
                    </div>
                  )}
                  {fr.status === 'estimated' && fr.client_approved == null && (
                    <div className="poadse-row-12">
                      <PortalButton variant="danger" size="sm" icon={<XCircle size={13} />}
                        onClick={() => decide({ id: fr.id, approved: false })}>{traducir('aus.rechazar')}</PortalButton>
                      <PortalButton size="sm" icon={<CheckCircle2 size={13} />}
                        onClick={() => decide({ id: fr.id, approved: true })}>{traducir('portaladvanced.aprobar_presupuesto')}</PortalButton>
                    </div>
                  )}
                  {fr.client_approved === true && (
                    <div className="poadse-box-11">
                      {traducir('portaladvanced.aprobado_por_ti_el')} {fr.client_approved_at}
                    </div>
                  )}
                  {fr.client_approved === false && (
                    <div className="poadse-box-12">{traducir('portaladvanced.rechazado_por_ti')}</div>
                  )}
                  {fr.can_edit_by_client && (
                    <div className="poadse-row-13">
                      <PortalButton variant="secondary" size="sm" onClick={() => openEdit(fr)}>{traducir('common.edit')}</PortalButton>
                      <PortalButton variant="danger" size="sm" loading={withdrawingFr}
                        onClick={() => withdrawFR({ id: fr.id })}>{traducir('pol.retirar')}</PortalButton>
                    </div>
                  )}
                </div>
                <div className="poadse-stack-1">
                  <StatusBadge status={fr.status} />
                  {fr.cr_status ? (
                    <BadgeWithTooltip
                      label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                      color={fr.cr_status_color || 'var(--text-3)'}
                      tooltip={traducir('portaladvanced.estado_de_la_change_request_vinculada')}
                      icon={<IconCR />}
                    />
                  ) : (
                    <BadgeWithTooltip
                      label={traducir('portaladvanced.sin_cr')}
                      color="var(--text-3)"
                      tooltip={traducir('portaladvanced.se_generara_change_request_al_aprobar_la')}
                      icon={<IconCR />}
                    />
                  )}
                </div>
              </div>
            </PortalCard>
          ))}
        </div>
      )}

      <PortalModal
        open={showNew}
        onClose={() => { setShowNew(false); setEditingFr(null); resetForm() }}
        title={editingFr ? 'Editar solicitud' : 'Nueva solicitud'}
        subtitle={traducir('portaladvanced.describe_lo_que_necesitas_con_el_mayor')}
        width={620}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => { setShowNew(false); setEditingFr(null); resetForm() }}>{traducir('common.cancel')}</PortalButton>
            <PortalButton
              loading={updatingFr}
              disabled={!form.title || !form.description || (requiresProject && !form.project_id)}
              onClick={() => editingFr ? updateFR({ id: editingFr.id, data: form }) : createFR(form)}
            >{editingFr ? 'Guardar cambios' : 'Enviar solicitud'}</PortalButton>
          </>
        }
      >
        <div className="u-stack-14">
          {requiresProject && (
            <PortalField label={traducir('gas.proyecto')} required>
              <PortalSelect id={`${formIdPrefix}-project`} value={form.project_id}
                onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))}>
                <option value="">{traducir('invoices.select')}</option>
                {clientProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </PortalSelect>
            </PortalField>
          )}
          <PortalField label={traducir('portaladvanced.titulo')} required>
            <PortalInput value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder={traducir('portaladvanced.resumen_breve')} />
          </PortalField>
          <PortalField label={traducir('portaladvanced.descripcion')} required>
            <PortalTextarea rows={3} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder={traducir('portaladvanced.que_necesitas')} />
          </PortalField>
          <PortalField label={traducir('portaladvanced.justificacion_de_negocio')} hint="Por qué es importante para ti">
            <PortalTextarea rows={2} value={form.business_justification} onChange={e => setForm(f => ({ ...f, business_justification: e.target.value }))} />
          </PortalField>
          <div className="u-grid2-12">
            <PortalField label={traducir('portaladvanced.area_afectada')}>
              <PortalInput value={form.affected_area} onChange={e => setForm(f => ({ ...f, affected_area: e.target.value }))} placeholder={traducir('portaladvanced.ej_reporting_login')} />
            </PortalField>
            <PortalField label={traducir('common.priority')}>
              <PortalSelect value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                <option value="low">{traducir('lec.sev_baja')}</option>
                <option value="medium">{traducir('lec.sev_media')}</option>
                <option value="high">{traducir('lec.sev_alta')}</option>
                <option value="critical">{traducir('portaladvanced.critica')}</option>
              </PortalSelect>
            </PortalField>
          </div>
        </div>
      </PortalModal>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalMessages — usa el nuevo dominio collaboration via /portal/collaboration/*
// (sustituye al inbox antiguo, manteniendo el componente gobernado como
// segunda pestaña para compatibilidad con conversaciones legacy).
// ════════════════════════════════════════════════════════════════════════════
export function PortalMessages() {
  const { t: traducir } = useAppLang()
  const t = useLang()
  const { client } = useClientAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState('chat')
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  const { data: conversations = [], isLoading } = useQuery<CollabConversation[]>({
    queryKey: ['portal-collab-conversations'],
    queryFn: () => CLIENT_API.get('/portal/collaboration/conversations').then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: messages = [] } = useQuery<CollabMessage[]>({
    queryKey: ['portal-collab-messages', activeConvId],
    queryFn: () => CLIENT_API.get(`/portal/collaboration/conversations/${activeConvId}/messages`).then(r => r.data),
    enabled: !!activeConvId,
    refetchInterval: POLL_FAST_MS,
  })

  const send = useMutation({
    mutationFn: () => CLIENT_API.post('/portal/collaboration/messages', { conversation_id: activeConvId, body: draft }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-collab-messages', activeConvId] })
      qc.invalidateQueries({ queryKey: ['portal-collab-conversations'] })
      setDraft('')
    },
  })

  useEffect(() => {
    if (!activeConvId && conversations.length > 0) setActiveConvId(conversations[0].id)
  }, [conversations, activeConvId])

  const projectOptions = Array.isArray(client?.projects)
    ? (client.projects as ClientProject[]).map(p => ({ id: p.id, name: p.name || p.code || p.id, code: p.code || '' }))
    : []
  // La sesión tipa `project_id` como `string | number`; el backend lo da como UUID (texto).
  const proyectoDeSesion = client?.project_id as string | null | undefined
  const fallbackProject = proyectoDeSesion ? [{ id: proyectoDeSesion, name: proyectoDeSesion, code: '' }] : []

  const tabs = [
    { id: 'chat', label: 'Chat unificado' },
    { id: 'governed', label: 'Solicitudes formales' },
  ]
  const teclas = useTabListKeys(tabs.map(x => x.id), tab, setTab)

  return (
    <div>
      <PortalPageHeader
        title={traducir('chat.messages')}
        subtitle={traducir('portaladvanced.chat_unificado_con_el_equipo_del_proyecto')}
        icon={MessageSquare}
      />

      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" className="poadse-row-14">
        {tabs.map(tb => (
          <button className="poadse-box-28" key={tb.id} type="button" role="tab" data-tab-id={tb.id}
            tabIndex={tb.id === teclas.focusId ? 0 : -1} aria-selected={tab === tb.id}
            onClick={() => setTab(tb.id)}
            style={{ borderBottom: `2px solid ${tab === tb.id ? 'var(--accent)' : 'transparent'}`, fontWeight: tab === tb.id ? 700 : 500, color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)' }}>{tb.label}</button>
        ))}
      </div>

      {tab === 'chat' && (
        isLoading ? <div className="poadse-box-13">{traducir('common.loading')}</div> :
        conversations.length === 0 ? (
          <PortalEmpty icon={MessageSquare} title={traducir('portaladvanced.aun_no_tienes_conversaciones')}
            description={traducir('portaladvanced.cuando_el_equipo_te_invite_a_un')} />
        ) : (
          <div className="poadse-grid-1">
            <PortalCard padding={10} className="portalad-sx4">
              {conversations.map(c => (
                <button className="poadse-box-29" key={c.id} onClick={() => setActiveConvId(c.id)}
                  style={{ background: activeConvId === c.id ? 'var(--accent-muted)' : 'transparent', color: activeConvId === c.id ? 'var(--accent)' : 'var(--text-1)' }}>{c.title}</button>
              ))}
            </PortalCard>
            <PortalCard padding={0} className="portalad-sx5">
              <div className="poadse-box-14">
                {messages.map(m => (
                  <div key={m.id} className="u-mb-10">
                    <div className="u-text3-xs">
                      {m.author_name || (m.client_user_id === client?.id ? 'Tú' : 'Equipo')} · {new Date(m.sent_at).toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div className="poadse-txt-4">{m.body}</div>
                  </div>
                ))}
              </div>
              <div className="poadse-row-15">
                <textarea aria-label={traducir('portaladvanced.escribe_un_mensaje')} value={draft} onChange={e => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (draft.trim()) send.mutate() } }}
                  placeholder={traducir('portaladvanced.escribe_un_mensaje')} rows={1}
                  className="poadse-box-15" />
                <PortalButton size="sm" onClick={() => draft.trim() && send.mutate()} disabled={!draft.trim()}>{traducir('chat.send')}</PortalButton>
              </div>
            </PortalCard>
          </div>
        )
      )}

      {tab === 'governed' && (
        <ClientGovernedConversationInbox
          title={t('messages_team_title')}
          emptyTitle={t('messages_empty')}
          emptyDescription={t('messages_empty')}
          projectOptions={projectOptions.length ? projectOptions : fallbackProject}
          initialProjectId={proyectoDeSesion || ''}
        />
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalInvoices
// ════════════════════════════════════════════════════════════════════════════
export function PortalInvoices() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [reasonByInvoice, setReasonByInvoice] = useState<Record<string, string>>({})
  const defaultCurrency = MONEDA_PORTAL_POR_DEFECTO

  const { data: invoices = [], isLoading } = useQuery<ClientInvoice[]>({
    queryKey: ['portal-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
  })

  const { mutate: approveInvoice, isPending } = useMutation({
    mutationFn: ({ invoiceId, approved, reason }: { invoiceId: string; approved: boolean; reason?: string }) => CLIENT_API.post(`/portal/invoices/${invoiceId}/approve`, { approved, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-invoices'] })
      qc.invalidateQueries({ queryKey: ['portal-dashboard'] })
      toast.success(traducir('chat.decision_registrada'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al actualizar la factura')),
  })

  const totals = invoices.reduce((acc: { total: number; paid: number; overdue: number; pending: number }, i) => {
    const v = Number(i.total || 0)
    acc.total += v
    if (i.status === 'paid') acc.paid += v
    if (i.status === 'overdue') acc.overdue += v
    if (['sent', 'submitted', 'pending'].includes(i.status)) acc.pending += v
    return acc
  }, { total: 0, paid: 0, overdue: 0, pending: 0 })
  const currency = invoices[0]?.currency || defaultCurrency

  return (
    <div>
      <PortalPageHeader
        title={traducir('nav.invoices')}
        subtitle={traducir('portaladvanced.aprueba_o_rechaza_las_facturas_pendientes_y')}
        icon={Receipt}
        meta={metaItems([
          { value: invoices.length, label: 'facturas' },
          { value: formatMoney(totals.paid, currency), label: 'cobrado', color: 'var(--success)' },
          { value: formatMoney(totals.pending, currency), label: 'pendiente', color: 'var(--warning)' },
          totals.overdue > 0 && { value: formatMoney(totals.overdue, currency), label: 'vencido', color: 'var(--danger)' },
        ])}
      />

      {isLoading ? (
        <div className="poadse-box-5">{traducir('common.loading')}</div>
      ) : invoices.length === 0 ? (
        <PortalEmpty icon={Receipt} title={traducir('portaladvanced.sin_facturas')} description={traducir('portaladvanced.cuando_se_emitan_facturas_en_este_proyecto')} />
      ) : (
        <div className="u-stack-12">
          {invoices.map(inv => {
            const cur = inv.currency || defaultCurrency
            const reason = reasonByInvoice[inv.id] || ''
            return (
              <PortalCard key={inv.id}>
                <div className="poadse-row-16">
                  <div className="u-flex1-min0">
                    <div className="u-text3-mono-xs">#{inv.number || inv.id}</div>
                    <div className="poadse-txt-2">{inv.client_name || 'Factura'}</div>
                    <div className="poadse-row-17">
                      <span>{traducir('portaladvanced.emitida')} {inv.issue_date || '—'}</span>
                      <span>{traducir('portaladvanced.vence')} {inv.due_date || '—'}</span>
                    </div>
                  </div>
                  <div className="poadse-txt-5">
                    <div className="poadse-txt-6">{formatMoney(inv.total, cur)}</div>
                    <StatusBadge status={inv.status} />
                  </div>
                </div>
                <div className="poadse-box-16">
                  {traducir('portaladvanced.base_iva', { base: formatMoney(inv.subtotal, cur), iva: formatMoney(inv.tax_amount, cur) })}
                </div>
                {inv.client_approval_status === 'pending' && (
                  <>
                    <PortalField label={traducir('portaladvanced.comentario_opcional')}>
                      <PortalTextarea rows={2}
                        value={reason}
                        onChange={e => setReasonByInvoice(prev => ({ ...prev, [inv.id]: e.target.value }))}
                        placeholder={traducir('portaladvanced.motivo_si_rechazas_observaciones')}
                      />
                    </PortalField>
                    <div className="poadse-row-18">
                      <PortalButton variant="danger" size="sm" loading={isPending}
                        onClick={() => approveInvoice({ invoiceId: inv.id, approved: false, reason })}>{traducir('aus.rechazar')}</PortalButton>
                      <PortalButton size="sm" icon={<CheckCircle2 size={13} />} loading={isPending}
                        onClick={() => approveInvoice({ invoiceId: inv.id, approved: true, reason })}>{traducir('aus.aprobar')}</PortalButton>
                    </div>
                  </>
                )}
              </PortalCard>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalRoadmap
// ════════════════════════════════════════════════════════════════════════════
export function PortalRoadmap() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const { data, isLoading, error } = useQuery<ClientProjectDetail | null>({
    queryKey: ['portal-project'],
    queryFn: () => CLIENT_API.get('/portal/project').then(r => r.data).catch((e: ApiError) => {
      if (e?.response?.status === 404 || e?.response?.status === 403) return null
      throw e
    }),
  })

  const milestones: RoadmapMilestone[] = data?.milestones || []
  const deliverables: RoadmapDeliverable[] = data?.deliverables || []
  const completedMs = milestones.filter(m => m.is_completed).length
  const completedDel = deliverables.filter(d => d.status === 'accepted').length

  if (isLoading) return (
    <div>
      <PortalPageHeader title="Roadmap" icon={Map} />
      <div className="poadse-box-5">{traducir('common.loading')}</div>
    </div>
  )
  if (!data || error) return (
    <div>
      <PortalPageHeader title="Roadmap" icon={Map} />
      <PortalEmpty icon={Map} title={traducir('portaladvanced.sin_proyecto_asignado')} description={traducir('portaladvanced.cuando_tengas_un_proyecto_activo_veras_aqui')} />
    </div>
  )

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.roadmap_del_proyecto')}
        subtitle={traducir('portaladvanced.hitos_planificados_y_entregables_del_proyecto')}
        icon={Map}
        meta={[
          { value: `${completedMs}/${milestones.length}`, label: 'hitos completados', color: 'var(--accent)' },
          { value: `${completedDel}/${deliverables.length}`, label: 'entregables aceptados', color: 'var(--success)' },
        ]}
      />

      {milestones.length === 0 && deliverables.length === 0 ? (
        <PortalEmpty icon={Map} title={traducir('portaladvanced.aun_sin_plan_publicado')}
          description={traducir('portaladvanced.el_equipo_todavia_no_ha_publicado_hitos')} />
      ) : (
        <div className="poadse-grid-2">
          <PortalCard>
            <PortalSection title={traducir('pres.tipo_hitos')} hint={`${completedMs} de ${milestones.length} completados`}>
              {milestones.length === 0 ? (
                <div className="u-text3-sm">{traducir('portaladvanced.sin_hitos_planificados')}</div>
              ) : (
                <div className="u-stack-10">
                  <PortalProgress value={milestones.length ? (completedMs / milestones.length) * 100 : 0} color="var(--success)" />
                  {milestones.map((m, i) => (
                    <div key={m.id} className="poadse-row-19">
                      <div className="poadse-stack-2">
                        <div className="poadse-row-31 portalad-sx6" style={{ background: m.is_completed ? 'var(--success)' : 'var(--surface-3)', border: `2px solid ${m.is_completed ? 'var(--success)' : 'var(--surface-4)'}`, color: m.is_completed ? '#fff' : 'var(--text-2)' }}>
                          {m.is_completed ? <CheckCircle2 size={14} /> : i + 1}
                        </div>
                        {i < milestones.length - 1 && (
                          <div className="poadse-box-30" style={{ background: m.is_completed ? 'var(--success-border, rgba(16,185,129,0.3))' : 'var(--surface-4)' }} />
                        )}
                      </div>
                      <div className="poadse-box-17">
                        <div className="poadse-txt-8" style={{ color: m.is_completed ? 'var(--text-2)' : 'var(--text-1)', textDecoration: m.is_completed ? 'line-through' : 'none' }}>{m.name}</div>
                        <div className="poadse-row-20">
                          {m.due_date && <span>📅 {m.due_date}</span>}
                          {m.billing_pct && <span className="u-warning">💶 {m.billing_pct}%</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </PortalSection>
          </PortalCard>

          <PortalCard>
            <PortalSection title={traducir('nav.deliverables')} hint={`${completedDel} de ${deliverables.length} aceptados`}>
              {deliverables.length === 0 ? (
                <div className="u-text3-sm">{traducir('portaladvanced.sin_entregables_planificados')}</div>
              ) : (
                <div className="u-stack-8">
                  {deliverables.map(d => (
                    <div key={d.id} className="poadse-row-21">
                      <Package size={15} className="portalad-sx7" />
                      <div className="u-flex1-min0">
                        <div className="poadse-box-18">{d.name}</div>
                        <div className="u-text3-xs">
                          {d.format && `${d.format} · `}{d.planned_date || '—'}
                        </div>
                      </div>
                      <StatusBadge status={d.status} />
                    </div>
                  ))}
                </div>
              )}
            </PortalSection>
          </PortalCard>
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalDocuments
// ════════════════════════════════════════════════════════════════════════════
export function PortalDocuments() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [signModal, setSignModal] = useState<{ id: string; title: string } | null>(null)
  const [signJobTitle, setSignJobTitle] = useState('')
  const [signedPdfB64, setSignedPdfB64] = useState<{ b64: string; title: string } | null>(null)

  const { data: docs = [] } = useQuery<ClientDocument[]>({
    queryKey: ['portal-docs-client'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data),
  })

  const { mutate: sign, isPending: signing } = useMutation({
    mutationFn: ({ id, job_title }: { id: string; job_title: string }) => CLIENT_API.post(`/portal/documents/${id}/sign`, { job_title }).then(r => r.data),
    onSuccess: (data: { pdf_b64?: string | null } | null) => {
      qc.invalidateQueries({ queryKey: ['portal-docs-client'] })
      setSignModal(null)
      setSignJobTitle('')
      if (data?.pdf_b64) {
        setSignedPdfB64({ b64: data.pdf_b64, title: signModal?.title || 'documento' })
      } else toast.success(traducir('portaladvanced.documento_firmado_correctamente'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al firmar')),
  })

  useEffect(() => {
    if (!signedPdfB64) return
    const bytes = atob(signedPdfB64.b64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Firmado_${signedPdfB64.title.replace(/\s+/g, '_').slice(0, 40)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
    setSignedPdfB64(null)
    toast.success(traducir('portaladvanced.certificado_de_firma_descargado'))
  }, [signedPdfB64, toast, traducir])

  const pendingSign = docs.filter(d => d.requires_signature && !d.signed_by_client).length

  return (
    <div>
      <PortalPageHeader
        title={traducir('docs.titulo')}
        subtitle={traducir('portaladvanced.documentacion_compartida_del_proyecto_contratos_actas_informes')}
        icon={FileText}
        meta={[
          { value: docs.length, label: 'documentos' },
          { value: pendingSign, label: 'por firmar', color: pendingSign ? 'var(--warning)' : 'var(--text-3)' },
        ]}
      />

      {docs.length === 0 ? (
        <PortalEmpty icon={FileText} title={traducir('portaladvanced.sin_documentos')} description={traducir('portaladvanced.aqui_apareceran_contratos_informes_y_entregables_compartidos')} />
      ) : (
        <div className="u-stack-10">
          {docs.map(doc => (
            <PortalCard key={doc.id}>
              <div className="poadse-row-22">
                <div className="poadse-row-23"><FileText size={18} /></div>
                <div className="u-flex1-min0">
                  <div className="u-sm-700">{doc.title}</div>
                  {doc.description && <div className="u-text2-xs-mt2">{doc.description}</div>}
                  <div className="u-hint">
                    {doc.file_name || doc.category} · {doc.created_at}
                  </div>
                </div>
                <div className="poadse-row-24">
                  {doc.requires_signature && !doc.signed_by_client && (
                    <PortalButton size="sm" icon={<FileSignature size={13} />}
                      onClick={() => { setSignModal({ id: doc.id, title: doc.title }); setSignJobTitle('') }}>
                      {traducir('portaladvanced.firmar')}
                    </PortalButton>
                  )}
                  {doc.signed_by_client && (
                    <PortalBadge tone="success" icon={<CheckCircle2 size={11} />}>
                      {traducir('client_portal.docs_signed')} {doc.signed_at?.slice(0, 10) || ''}
                    </PortalBadge>
                  )}
                  {doc.file_url && (
                    <a href={doc.file_url} target="_blank" rel="noopener noreferrer"
                      className="poadse-row-25"><Download size={13} /> {traducir('aus.descargar')}</a>
                  )}
                </div>
              </div>
            </PortalCard>
          ))}
        </div>
      )}

      <PortalModal
        open={!!signModal}
        onClose={() => setSignModal(null)}
        title={traducir('portaladvanced.firmar_documento')}
        subtitle={signModal?.title || ''}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => setSignModal(null)}>{traducir('common.cancel')}</PortalButton>
            <PortalButton loading={signing} icon={<FileSignature size={13} />}
              onClick={() => { if (signModal) sign({ id: signModal.id, job_title: signJobTitle }) }}>
              {traducir('portaladvanced.firmar')}
            </PortalButton>
          </>
        }
      >
        <div className="u-stack-12">
          <PortalField label={traducir('portaladvanced.cargo_funcion')} hint="Aparecerá en el certificado de firma">
            <PortalInput value={signJobTitle} onChange={e => setSignJobTitle(e.target.value)} placeholder={traducir('portaladvanced.ej_director_de_operaciones')} />
          </PortalField>
          <PortalBanner tone="info" icon={<FileSignature size={16} />} title={traducir('portaladvanced.firma_con_certificado_pdf')} body="Se generará un PDF certificado con tus datos, fecha y hora. Se descargará automáticamente al firmar." />
        </div>
      </PortalModal>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalWiki
// ════════════════════════════════════════════════════════════════════════════
export function PortalWiki() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState('docs')
  const [searchKB, setSearchKB] = useState('')
  // Revisión 2026-11: el artículo se listaba y no se podía abrir.
  const [articuloAbierto, setArticuloAbierto] = useState<string | null>(null)

  const { data: pages = [], isLoading } = useQuery<WikiPageSummary[]>({
    queryKey: ['portal-wiki-pages'],
    queryFn: () => CLIENT_API.get('/portal/wiki/pages').then(r => r.data),
  })
  const { data: pageDetail } = useQuery<WikiPageDetail | null>({
    queryKey: ['portal-wiki-page', selected],
    queryFn: () => CLIENT_API.get(`/portal/wiki/pages/${selected}`).then(r => r.data),
    enabled: !!selected,
  })
  const { data: kbArticles = [], isLoading: loadingKB } = useQuery<KbArticle[]>({
    queryKey: ['portal-wiki-kb', searchKB],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined } }).then(r => r.data),
    enabled: tab === 'kb',
  })

  const tabs = [
    { id: 'docs', label: 'Documentación' },
    { id: 'kb',   label: 'Base de conocimiento' },
  ]
  // Antes del return del detalle: un hook no puede quedar detrás de un return.
  const teclas = useTabListKeys(tabs.map(x => x.id), tab, id => { setTab(id); setSelected(null) })

  if (articuloAbierto) {
    return <PortalKbArticulo id={articuloAbierto} onVolver={() => setArticuloAbierto(null)} migas={traducir('portalkb.migas_wiki')} />
  }
  if (selected && pageDetail) {
    return (
      <div>
        <PortalPageHeader
          title={pageDetail.title}
          icon={BookOpen}
          breadcrumb={[{ label: 'Wiki', onClick: () => setSelected(null) }, { label: pageDetail.title }]}
          actions={<PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={() => setSelected(null)}>{traducir('chat.back')}</PortalButton>}
        />
        <PortalCard>
          <div className="poadse-txt-7">
            {(pageDetail.content || []).map((block, i) => {
              if (block.type === 'heading1') return <h1 key={i} className="poadse-box-19">{block.content}</h1>
              if (block.type === 'heading2') return <h2 key={i} className="poadse-box-20">{block.content}</h2>
              if (block.type === 'heading3') return <h3 key={i} className="poadse-box-21">{block.content}</h3>
              if (block.type === 'bullet') return <li key={i} className="poadse-sp-1">{block.content}</li>
              if (block.type === 'code') return <pre key={i} className="poadse-box-22">{block.content}</pre>
              if (block.type === 'callout') return <div key={i} className="poadse-box-23">{block.content}</div>
              if (block.type === 'separator') return <hr key={i} className="poadse-box-24" />
              return <p key={i} className="u-mb-10">{block.content}</p>
            })}
          </div>
          <div className="poadse-box-25">
            {traducir('portaladvanced.ultima_actualizacion')} {pageDetail.updated_at ? new Date(pageDetail.updated_at).toLocaleDateString(localeActivo()) : '—'}
          </div>
        </PortalCard>
      </div>
    )
  }

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.wiki_y_conocimiento')}
        subtitle={traducir('portaladvanced.documentacion_interna_del_proyecto_y_base_de')}
        icon={BookOpen}
        meta={[
          { value: pages.length, label: 'documentos' },
          { value: kbArticles.length, label: 'artículos KB' },
        ]}
      />

      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" aria-label="Wiki" className="poadse-row-26">
        {tabs.map(tb => (
          <button className="poadse-box-28" key={tb.id} type="button" role="tab" data-tab-id={tb.id}
            tabIndex={tb.id === teclas.focusId ? 0 : -1} aria-selected={tab === tb.id}
            onClick={() => { setTab(tb.id); setSelected(null) }}
            style={{ borderBottom: `2px solid ${tab === tb.id ? 'var(--accent)' : 'transparent'}`, fontWeight: tab === tb.id ? 700 : 500, color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)' }}>{tb.label}</button>
        ))}
      </div>

      {tab === 'docs' && (
        <>
          {isLoading ? (
            <div className="poadse-box-5">{traducir('common.loading')}</div>
          ) : pages.length === 0 ? (
            <PortalEmpty icon={BookOpen} title={traducir('portaladvanced.sin_paginas')} description={traducir('portaladvanced.cuando_el_equipo_publique_documentacion_interna_la')} />
          ) : (
            <div className="poadse-grid-3">
              {pages.map(p => (
                <PortalCard key={p.id} onClick={() => setSelected(p.id)}>
                  <div className="poadse-row-19">
                    <div className="poadse-row-27">
                      <FileText size={16} />
                    </div>
                    <div className="u-flex1-min0">
                      <div className="poadse-box-2">{p.title}</div>
                      <div className="u-text3-xs">
                        {p.updated_at ? new Date(p.updated_at).toLocaleDateString(localeActivo()) : '—'}
                      </div>
                    </div>
                  </div>
                </PortalCard>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'kb' && (
        <>
          <div className="poadse-box-26">
            <Search size={14} className="portalad-sx8" />
            <PortalInput value={searchKB} onChange={e => setSearchKB(e.target.value)}
              placeholder={traducir('portaladvanced.buscar_en_la_base_de_conocimiento')}
              style={{ paddingLeft: 34, fontSize: 'var(--text-md)', padding: '11px 12px 11px 34px' }} />
          </div>
          {loadingKB ? (
            <div className="poadse-box-5">{traducir('common.loading')}</div>
          ) : kbArticles.length === 0 ? (
            <PortalEmpty icon={Search} title={searchKB ? `Sin resultados para "${searchKB}"` : 'Base de conocimiento vacía'} />
          ) : (
            <div className="u-stack-10">
              {kbArticles.map(a => (
                <PortalCard key={a.id} onClick={() => setArticuloAbierto(a.id)}>
                  <div className="poadse-row-28">
                    <div className="u-sm-700">{a.title}</div>
                    <div className="u-text3-xs">👁 {a.view_count} · ✓ {a.helpful_count}</div>
                  </div>
                  {a.summary && <p className="poadse-box-27">{a.summary}</p>}
                  {a.tags && <div className="u-text3-xs">🏷 {a.tags}</div>}
                </PortalCard>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
