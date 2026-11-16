/**
 * EnterprisePage v14 — Webhooks, GDPR, Email, Integraciones, SSO, Audit, API Keys
 */
import { useAppLang } from '../i18n/AppLangContext'
import { useState, useId, useRef } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { extractErr, downloadBlob, fmtDate, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, esFichaCompleta, webhooksApi, autoWorkflowsApi, gdprApi, emailApi, oauthIntegrationsApi, integrationsHubApi, enterpriseApi, apiKeysApi, apiUrl } from '../services/api'
import type { ClaveDeApi, ClaveDeApiCreada, ConfigSso, EventoDeAuditoria, IntegracionOAuth, SolicitudRgpd, VerificacionDeCadena } from '../services/api/tipos'
import { Button, Modal, Spinner, EmptyState, Tabs, KpiCard, IconButton, StatusBadge } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import type { AxiosResponse } from 'axios'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'

import { useAppT } from '../i18n/AppLangContext'
import { INTEGRATION_CATALOG } from '../constants/api'
import { Building2, CalendarDays, CheckCircle2, FileUp, Github, History, Key, KeyRound, KanbanSquare, Mail, MessageSquare, Pencil, Plug, Plus, Receipt, RefreshCw, ScrollText, Send, ShieldCheck, Trash2, Users, Webhook, X, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import useMediaQuery from '../hooks/useMediaQuery'
import { AUDIT_LOG_PAGE_SIZE, AUDIT_LOG_SMALL_PAGE_SIZE, SMALL_PAGE_SIZE } from '../constants/pagination'
import './EnterprisePage.css'

const GDPR_POR_PAGINA = SMALL_PAGE_SIZE


// ── Formularios (las respuestas van tipadas en services/api/tipos.ts) ───────
interface WebhookForm { name: string; slug: string; workflow_id: string }

interface GdprForm { request_type: string; subject_user_id: string; subject_email: string; notes: string }

interface SendEmailForm { to: string; subject: string; body_html: string; template_id: string }
interface NewTemplateForm { name: string; subject: string; body_html: string; category: string }

interface IntegrationField { key: string; label: string; type?: string; placeholder?: string }
interface IntegrationCatalogEntry { type: string; label: string; icon: string; desc?: string; fields?: IntegrationField[] }
/** Fila de la lista: las de `integration_configs` y la conexión Jira de la empresa (sin `config`). */
type OAuthIntegration = Pick<IntegracionOAuth, 'id' | 'name' | 'integration_type' | 'is_active' | 'last_sync_at'> & { config?: IntegracionOAuth['config'] }
interface IntegrationForm { name: string; access_token?: string; config: Record<string, string>; integration_type?: string }
const JIRA_ID = 'jira-config'

/** Detalle de error de FastAPI cuando es una lista de validación. */
interface ValidationDetail { msg?: string }

interface ApiKeyForm { name: string; rate_limit_per_hour: number }

/** El formulario de alta de cada pestaña se abre desde la cabecera de la página. */
interface AltaProps { showCreate: boolean; setShowCreate: (v: boolean) => void }

/** Icono de cada integración del catálogo (el catálogo trae emojis: no se pintan). */
const ICONO_INTEGRACION: Record<string, LucideIcon> = {
  slack: MessageSquare, teams: Users, jira: KanbanSquare, github: Github,
  google_calendar: CalendarDays, xero: Receipt, quickbooks: Receipt,
}
const iconoIntegracion = (tipo?: string) => ICONO_INTEGRACION[tipo || ''] || Plug

/** Etiqueta de un código (`<prefijo>_<codigo>`); si no hay clave, el código tal cual. */
const etiq = (t: (k: string, f?: string) => string, prefijo: string, codigo?: string | null) =>
  codigo ? t(`${prefijo}_${String(codigo).toLowerCase()}`, String(codigo)) : '—'
const ROLES_SSO = ['employee', 'team_lead', 'pm', 'hr', 'admin', 'subcontractor']

function WebhooksTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showLogs, setShowLogs] = useState<string|null>(null)
  const [form, setForm] = useState({ name:'', slug:'', workflow_id:'' })

  const { data: triggers = [], isLoading } = useQuery({ queryKey:['wh-triggers'], queryFn:() => webhooksApi.list().then(r => r.data) })
  const { data: workflows = [] } = useQuery({ queryKey:['workflows-ent'], queryFn:() => autoWorkflowsApi.list().then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['wh-logs', showLogs], queryFn:() => webhooksApi.logs(showLogs).then(r => r.data), enabled:!!showLogs })

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: WebhookForm) => webhooksApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wh-triggers'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => webhooksApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wh-triggers'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="ent-card">
        {traducir('enterprise.los_webhooks_entrantes_permiten_que_sistemas_externos')}
      </div>
      {isLoading ? <Spinner /> : triggers.length === 0 ? (
        <EmptyState icon={<Webhook size={28} />} title={traducir('enterprise.sin_webhooks')} description={t('pagina_ent.crea_el_primer_webhook_entrante_para')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nuevo_webhook')}</Button>} />
      ) : triggers.map(trg => (
        <div key={trg.id} className="enterprise-page-e1">
          <div className="ent-row-2">
            <div className="u-min0">
              <div className="ent-box">{trg.name}</div>
              <code className="ent-card-2">POST {apiUrl(trg.endpoint)}</code>
              <span className="ent-label">{t('pagina_ent.disparos', { n: trg.fire_count })}</span>
            </div>
            <div className="u-row-8">
              <Button size="sm" variant="secondary" icon={<History size={14} />} onClick={() => setShowLogs(showLogs === trg.id ? null : trg.id)}>
                {showLogs === trg.id ? t('pagina_ent.ocultar') : t('pagina_ent.logs')}
              </Button>
              <IconButton className="ent-borrar" onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar_webhook'), confirmLabel: t('pagina_ent.eliminar_boton'), onConfirm: () => del(trg.id), danger: true }) }} ariaLabel={t('pagina_ent.eliminar_webhook_aria', { name: trg.name })}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          </div>
          {showLogs === trg.id && (
            <div className="ent-box-2">
              {logs.length === 0 ? <div className="u-text3-sm">{traducir('enterprise.sin_llamadas_aun')}</div> :
                logs.slice(0,5).map(l => (
                  <div key={l.id} className="ent-row-3">
                    <span className={`${l.status === 'ok' ? 'enterpri-sx1' : 'enterpri-sx2'}`}>{l.status === 'ok' ? t('pagina_ent.llamada_ok') : t('pagina_ent.llamada_error')}</span>
                    <span className="u-text2">{fmtDateTime(l.received_at)}</span>
                    <span className="ent-label-2">{l.payload_preview}</span>
                  </div>
                ))
              }
            </div>
          )}
        </div>
      ))}
      {showCreate && (
        <Modal open title={traducir('enterprise.nuevo_webhook_2')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} className="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">{t('pagina_ent.slug_url')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.slug} onChange={e => setForm(f => ({...f, slug:e.target.value.toLowerCase().replace(/\s+/g,'-')}))} className="enterprise-page-e17" placeholder="mi-webhook" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.workflow')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.workflow_id} onChange={e => setForm(f => ({...f, workflow_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{traducir('enterprise.sin_workflow')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <div className="ent-card-3">
              {t('pagina_ent.url')}{' '}<code>POST {apiUrl(`/webhooks/fire/${form.slug || 'tu-slug'}`)}</code>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={isPending || !form.name || !form.slug}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function GDPRTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<GdprForm>({ request_type:'erasure', subject_user_id:'', subject_email:'', notes:'' })

  const [page, setPage] = useState(1)
  // Paginado en el servidor: el interceptor deja la lista en `data` y el total en `meta.total`.
  const { data: pagina, isLoading } = useQuery<{ items: SolicitudRgpd[]; total: number }>({
    queryKey: ['gdpr', page],
    queryFn: () => gdprApi.list({ page, page_size: GDPR_POR_PAGINA }).then((r: AxiosResponse<SolicitudRgpd[]> & { meta?: { total?: number } }) =>
      ({ items: r.data, total: Number(r.meta?.total ?? r.data.length) })),
  })
  const requests = pagina?.items ?? []
  const paginas = Math.max(1, Math.ceil((pagina?.total ?? 0) / GDPR_POR_PAGINA))
  const { data: usersRaw = [] } = useQuery({ queryKey:['users'], queryFn:() => usersApi.list().then(r => r.data) })
  const users = Array.isArray(usersRaw) ? usersRaw : []

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: GdprForm) => gdprApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['gdpr'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: process } = useMutation({
    mutationFn: (id: string) => gdprApi.process(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['gdpr'] }); toast.success(t('pagina_ent.rgpd_procesada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  // Revisión GRC 16-11-2026: rechazo motivado (el estado existía y nada lo ponía)
  // y descarga de la copia de acceso/portabilidad (se generaba y no se veía).
  const { mutate: reject } = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => gdprApi.reject(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gdpr'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const rechazar = async (id: string) => {
    const reason = await pedirTexto({ title: t('pagina_ent.rgpd_rechazar'), message: t('pagina_ent.rgpd_motivo_rechazo'), label: t('pagina_ent.rgpd_motivo_rechazo'), multiline: true, confirmLabel: t('pagina_ent.rgpd_rechazar') })
    if (reason && reason.trim().length >= 3) reject({ id, reason: reason.trim() })
  }
  const descargar = async (id: string) => {
    try { downloadBlob((await gdprApi.exportFile(id)).data, `gdpr-${id}.json`) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const TYPE_LABELS: Record<string,string> = { erasure:t('pagina_ent.derecho_al_olvido'), portability:t('pagina_ent.portabilidad'), access:t('pagina_ent.acceso'), rectification:t('pagina_ent.rectificacion') }
  const STATUS_COLORS: Record<string,string> = { pending:'var(--warning)', processing:'var(--accent)', completed:'var(--success)', rejected:'var(--danger)' }

  return (
    <div>
      <div className="ent-card-4">
        {traducir('enterprise.gestion_de_solicitudes_rgpd_plazo_maximo_de')}
      </div>
      {isLoading ? <Spinner /> : requests.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={traducir('enterprise.sin_solicitudes_rgpd')} description={t('pagina_ent.no_hay_solicitudes_de_privacidad_registradas')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_solicitud')}</Button>} />
      ) : (
        <div className="enterprise-page-e2">
          {requests.map(r => (
            <div key={r.id} className="ent-grid">
              <span className="ent-label-3">{TYPE_LABELS[r.request_type] || r.request_type}</span>
              <span className="ent-label-3 enterprise-page-e3" style={{ '--enterprise-page-color': STATUS_COLORS[r.status] || 'var(--text-2)' } as CSSProperties}>{t(`pagina_ent.rgpd_estado_${r.status}`)}</span>
              <div>
                <div className="ent-box-3">{r.subject_deleted ? t('pagina_ent.rgpd_persona_eliminada') : r.subject_name}</div>
                {r.subject_email && <div className="u-text2-xs">{r.subject_email}</div>}
                {r.notes && <div className="u-text2-xs">{r.notes}</div>}
              </div>
              <span className="u-text2-sm">{fmtDate(r.deadline)}</span>
              {(r.status === 'pending' || r.status === 'processing') && (
                <div className="u-row-6">
                  <Button onClick={() => openConfirmGlobal({ message: t('pagina_ent.rgpd_confirmar_procesar'), onConfirm: () => process(r.id), danger: r.request_type === 'erasure' })}>{t('pagina_ent.procesar')}</Button>
                  <Button variant="secondary" onClick={() => rechazar(r.id)}>{t('pagina_ent.rgpd_rechazar')}</Button>
                </div>
              )}
              {r.has_export && <Button variant="secondary" onClick={() => descargar(r.id)}>{t('pagina_ent.rgpd_descargar')}</Button>}
            </div>
          ))}
        </div>
      )}
      {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} />}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_solicitud_rgpd')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.tipo')}</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.request_type} onChange={e => setForm(f => ({...f, request_type:e.target.value}))} className="enterprise-page-e17">
                <option value="erasure">{traducir('enterprise.derecho_al_olvido_art_17')}</option>
                <option value="portability">{t('pagina_ent.portabilidad_art_20')}</option>
                <option value="access">{t('pagina_ent.acceso_art_15')}</option>
                <option value="rectification">{traducir('enterprise.rectificacion_art_16')}</option>
              </select>
            </div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.usuario')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.subject_user_id} onChange={e => setForm(f => ({...f, subject_user_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{t('pagina_ent.seleccionar')}</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{esFichaCompleta(u) ? ` — ${u.email}` : ''}</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">{traducir('enterprise.email_si_ya_no_existe')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.subject_email} onChange={e => setForm(f => ({...f, subject_email:e.target.value}))} className="enterprise-page-e17" />
            </div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e16">{t('pagina_ent.notas')}</label>
              <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.notes} onChange={e => setForm(f => ({...f, notes:e.target.value}))} rows={3} className="enterprise-page-e4" />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={isPending || (!form.subject_user_id && !form.subject_email)}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function EmailTab({ showSend, setShowSend, showCreate, setShowCreate }: AltaProps & { showSend: boolean; setShowSend: (v: boolean) => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [sendForm, setSendForm] = useState<SendEmailForm>({ to:'', subject:'', body_html:'', template_id:'' })
  const [newTpl, setNewTpl] = useState<NewTemplateForm>({ name:'', subject:'', body_html:'', category:'automation' })

  const { data: catalog } = useQuery({ queryKey:['email-tpl'], queryFn:() => emailApi.catalog().then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['email-logs'], queryFn:() => emailApi.logs().then(r => r.data) })

  const { mutate: send, isPending:sending } = useMutation({
    mutationFn: (d: SendEmailForm) => emailApi.send({...d, to:[d.to]}),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['email-logs'] }); setShowSend(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: createTpl } = useMutation({
    mutationFn: (d: NewTemplateForm) => emailApi.createTemplate(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['email-tpl'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const allTpl = [...(catalog?.system || []), ...(catalog?.custom || [])]

  return (
    <div>
      <div className="ent-grid-2">
        <div className="u-min0">
          <div className="ent-box-4">{t('pagina_ent.plantillas')}{allTpl.length})</div>
          {allTpl.map(tpl => (
            <div key={tpl.id} className="enterprise-page-e5">
              <div className="ent-row-5">
                <span className="ent-card-5">{etiq(t, 'pagina_ent.tpl_cat', tpl.category)}</span>
                {tpl.is_system && <span className="ent-card-6">{t('pagina_ent.sistema')}</span>}
              </div>
              <div className="ent-box-3">{tpl.name}</div>
              <div className="ent-box-5">{tpl.subject}</div>
            </div>
          ))}
        </div>
        <div>
          <div className="ent-box-4">{traducir('enterprise.historial_de_envios')}</div>
          {logs.length === 0 ? <EmptyState icon={<Mail size={28} />} title={traducir('enterprise.sin_historial_de_envios')} description={t('pagina_ent.todavia_no_se_han_enviado_correos')} /> : (
            <div className="enterprise-page-e6">
              {logs.slice(0,15).map(l => (
                <div key={l.id} className="ent-grid-3">
                  <span className={`ent-label-4 ${l.status === 'sent' ? 'enterpri-sx3' : 'enterpri-sx4'}`}>{etiq(t, 'pagina_ent.envio', l.status)}</span>
                  <div>
                    <div className="ent-label-4">{l.to}</div>
                    <div className="u-text2-xs">{l.subject}</div>
                  </div>
                  <span className="ent-label-5">{fmtDateTime(l.sent_at || l.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {showSend && (
        <Modal open title={t('pagina_ent.enviar_email_2')} onClose={() => setShowSend(false)} width={500}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="enterprise-page-e16">{traducir('enterprise.para')}</label><input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={sendForm.to} onChange={e => setSendForm(f => ({...f, to:e.target.value}))} className="enterprise-page-e17" placeholder={t('pagina_ent.destinatario_empresa_com')} /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{t('pagina_ent.plantilla_2')}</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={sendForm.template_id} onChange={e => setSendForm(f => ({...f, template_id:e.target.value}))} className="enterprise-page-e17">
                <option value="">{traducir('enterprise.sin_plantilla')}</option>
                {allTpl.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            {!sendForm.template_id && <>
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.asunto')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sendForm.subject} onChange={e => setSendForm(f => ({...f, subject:e.target.value}))} className="enterprise-page-e17" /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e16">HTML</label><textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={sendForm.body_html} onChange={e => setSendForm(f => ({...f, body_html:e.target.value}))} rows={4} className="enterprise-page-e4" /></div>
            </>}
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowSend(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => send(sendForm)} disabled={sending || !sendForm.to}>{sending ? t('pagina_ent.enviando') : t('pagina_ent.enviar')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_plantilla_de_email')} onClose={() => setShowCreate(false)} width={560}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={newTpl.name} onChange={e => setNewTpl(f => ({...f, name:e.target.value}))} className="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="enterprise-page-e16">{t('pagina_ent.asunto_usa')}{' '}{'{{variable}}'})</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newTpl.subject} onChange={e => setNewTpl(f => ({...f, subject:e.target.value}))} className="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="enterprise-page-e16">{traducir('enterprise.categoria')}</label>
              <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={newTpl.category} onChange={e => setNewTpl(f => ({...f, category:e.target.value}))} className="enterprise-page-e17">
                {['automation','alert','report','invoice'].map((c: string) => <option key={c} value={c}>{t(`pagina_ent.tpl_cat_${c}`)}</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="enterprise-page-e16">{traducir('enterprise.html_del_cuerpo')}</label><textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={newTpl.body_html} onChange={e => setNewTpl(f => ({...f, body_html:e.target.value}))} rows={5} className="enterprise-page-e4" /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={!newTpl.name || !newTpl.subject || !newTpl.body_html}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function IntegrationsTab() {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [configuring, setConfiguring] = useState<IntegrationCatalogEntry | null>(null)
  const [testing, setTesting]         = useState<string|null>(null)
  const [testResult, setTestResult]   = useState<{ok:boolean;message:string}|null>(null)
  const [form, setForm] = useState<IntegrationForm>({ name:'', access_token:'', config:{} })

  const { data: otras = [] } = useQuery({
    queryKey: ['integrations'],
    queryFn: () => oauthIntegrationsApi.list().then(r => r.data),
  })

  // Segunda auditoría 2026-11 (#23): Jira es la conexión única de la organización
  // (`/integrations-hub/jira/config`), no una fila de `integration_configs`.
  const { data: jira } = useQuery({
    queryKey: ['jira-hub-config'],
    queryFn: () => integrationsHubApi.jiraConfig().then(r => r.data),
  })
  const integrations: OAuthIntegration[] = [
    ...otras.filter(i => i.integration_type !== 'jira'),
    ...(jira?.configured && jira.is_active ? [{
      id: JIRA_ID, name: jira.name, integration_type: 'jira', is_active: true,
      last_sync_at: jira.last_sync_at ?? null,
    }] : []),
  ]
  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ['integrations'] })
    qc.invalidateQueries({ queryKey: ['jira-hub-config'] })
  }

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Omit<IntegrationForm, 'config'> & { config: string }): Promise<unknown> => {
      if (d.integration_type === 'jira') {
        const cfg = JSON.parse(d.config || '{}') as Record<string, string>
        return integrationsHubApi.saveJiraConfig({
          name: d.name, base_url: cfg.base_url || '', email: cfg.email || '',
          api_token: cfg.api_token || undefined, project_key: cfg.project_key ?? undefined,
        })
      }
      return oauthIntegrationsApi.create(d)
    },
    onSuccess: () => { invalidar(); setConfiguring(null); toast.success(t('pagina_ent.integracion_guardada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.deleteJiraConfig() : oauthIntegrationsApi.delete(id),
    onSuccess: () => { invalidar(); toast.success(t('pagina_ent.integracion_eliminada')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: sync } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.syncJira() : oauthIntegrationsApi.sync(id, {}),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['integrations'] }); toast.success(r?.data?.errors?.length
        ? t('pagina_ent.sincronizados_con_error', { synced: r?.data?.synced ?? 0, length: r.data.errors.length })
        : t('pagina_ent.sincronizados_elementos', { synced: r?.data?.synced ?? 0 })) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const testIntegration = async (integ: OAuthIntegration) => {
    setTesting(integ.id)
    setTestResult(null)
    try {
      const cfg = integ.config || {}
      if (integ.integration_type === 'slack') {
        const res = await integrationsHubApi.testSlack({ webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'teams') {
        const res = await integrationsHubApi.testTeams({ webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'jira') {
        // Sin datos: el servidor prueba la conexión guardada (el token no viaja al navegador).
        const res = await integrationsHubApi.testJira({})
        setTestResult({ ok: true, message: t('pagina_ent.conectado_proyectos_jira_disponibles', { total: res.data.total }) })
      } else {
        const res = await oauthIntegrationsApi.sync(integ.id, {})
        setTestResult({ ok: true, message: t('pagina_ent.sincronizados_elementos', { synced: res.data.synced }) })
      }
    } catch (e: unknown) {
      const _raw1 = (e as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
      setTestResult({ ok: false, message: Array.isArray(_raw1) ? _raw1.map((d: ValidationDetail) => d.msg).join(', ') : ((_raw1 as string) || t('pagina_ent.error_de_conexion')) })
    } finally {
      setTesting(null)
    }
  }

  // El catálogo viene de la configuración de negocio sin tipar (`unknown`).
  const CATALOG = INTEGRATION_CATALOG as IntegrationCatalogEntry[]

  return (
    <div>
      <div className="ent-box-6">{t('pagina_ent.integraciones_nativas')}</div>
      <div className="ent-box-7">{traducir('enterprise.conecta_contecflow_con_tus_herramientas_de_trabajo')}</div>

      {/* Integraciones activas */}
      {integrations.length > 0 && (
        <div className="u-mb-20">
          <div className="ent-box-8">{t('pagina_ent.configuradas')}</div>
          {integrations.map(integ => {
            const cat = CATALOG.find((c) => c.type === integ.integration_type) || { label: integ.integration_type }
            const Icono = iconoIntegracion(integ.integration_type)
            return (
              <div key={integ.id} className="ent-row-6">
                <div className="ent-row-7">
                  <span className="ent-label-6" aria-hidden><Icono size={20} /></span>
                  <div>
                    <div className="u-base-700">{integ.name || cat.label}</div>
                    <div className={`u-xs ${integ.is_active ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
                      {integ.is_active ? t('pagina_ent.activa') : t('pagina_ent.inactiva')}
                      {integ.last_sync_at && t('pagina_ent.ultimo_sync', { v1: fmtDate(integ.last_sync_at) })}
                    </div>
                  </div>
                </div>
                <div className="u-row-6">
                  <Button size="sm" variant="secondary" onClick={() => testIntegration(integ)} loading={testing === integ.id}>
                    {t('pagina_ent.probar')}
                  </Button>
                  <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => sync(integ.id)}>
                    {t('pagina_ent.sync')}
                  </Button>
                  <IconButton className="ent-borrar" ariaLabel={t('pagina_ent.eliminar', { name: integ.name || cat.label })}
                    onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar', { name: integ.name }), onConfirm: () => del(integ.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )
          })}

          {/* Test result */}
          {testResult && (
            <div className={`ent-row-8 enterpri-sx5 ${testResult.ok ? 'enterpri-sx6' : 'enterpri-sx7'} enterprise-page-e7`} style={{ '--enterprise-page-border': `1px solid ${testResult.ok ? 'var(--success-border)' : 'var(--danger-border)'}` } as CSSProperties}>
              <span className="ent-resultado">{testResult.ok ? <CheckCircle2 size={14} aria-hidden /> : <XCircle size={14} aria-hidden />} {testResult.message}</span>
              <IconButton ariaLabel={t('pagina_ent.cerrar')} onClick={() => setTestResult(null)}><X size={14} aria-hidden /></IconButton>
            </div>
          )}
        </div>
      )}

      {/* Catálogo para añadir */}
      <div className="ent-box-8">
        {integrations.length === 0 ? t('pagina_ent.disponibles') : t('pagina_ent.anadir_otra')}
      </div>
      <div className="ent-grid-4">
        {CATALOG.map((cat) => { const Icono = iconoIntegracion(cat.type); return (
          <button key={cat.type} aria-pressed={configuring?.type === cat.type} onClick={() => {
            setConfiguring(cat)
            // Jira: se precarga la conexión guardada; el token vacío conserva el actual.
            const previa = cat.type === 'jira' && jira?.configured
              ? { base_url: jira.base_url || '', email: jira.email || '', project_key: jira.project_key || '' } : {}
            setForm({ name: (cat.type === 'jira' && jira?.configured && jira.name) || cat.label, integration_type: cat.type, config: previa })
          }}
            type="button"
            className="ent-btn-8 enterpri-sx8 ent-catalogo"
          >
            <div className="ent-box-9" aria-hidden><Icono size={22} /></div>
            <div className="ent-box-10">{cat.label}</div>
            <div className="u-text2-xs">{t(`pagina_ent.int_desc_${cat.type}`, cat.desc)}</div>
          </button>
        ) })}
      </div>

      {/* Formulario de configuración */}
      {configuring && (
        <div className="ent-card-7">
          <div className="ent-box-11">
            {t('pagina_ent.configurar')}{' '}{configuring.label}
          </div>
          <div className="ent-grid-5">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e18">{traducir('enterprise.nombre_de_la_integracion')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} className="enterprise-page-e19" />
            </div>
            {configuring.fields?.map(field => (
              <div key={field.key}>
                <label id={`${idCampo}-et-${field.key}`} htmlFor={`${idCampo}-${field.key}`} className="enterprise-page-e18">{field.label}</label>
                <input id={`${idCampo}-${field.key}`} aria-labelledby={`${idCampo}-et-${field.key}`}
                  type={field.type || 'text'}
                  value={form.config?.[field.key] || ''}
                  onChange={e => setForm(f => ({ ...f, config: { ...f.config, [field.key]: e.target.value } }))}
                  className="enterprise-page-e19"
                  placeholder={field.placeholder || ''}
                />
              </div>
            ))}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setConfiguring(null)}>{t('pagina_ent.cancelar')}</Button>
            <Button onClick={() => create({ ...form, integration_type: configuring.type, config: JSON.stringify(form.config) })}
              loading={isPending}>
              {isPending ? t('pagina_ent.guardando') : t('pagina_ent.guardar_integracion')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Cadena a prueba de manipulación del registro (revisión 2026-11). */
function CadenaDeAuditoria() {
  const t = useAppT()
  const toast = useToast()
  const [resultado, setResultado] = useState<VerificacionDeCadena | null>(null)
  const [ocupado, setOcupado] = useState<'' | 'verificar' | 'exportar'>('')
  const ficheroRef = useRef<HTMLInputElement | null>(null)
  const verificar = async (esperada?: { seq: number; entry_hash: string }) => {
    setOcupado('verificar')
    try {
      const params = esperada ? { expected_seq: esperada.seq, expected_hash: esperada.entry_hash } : undefined
      const r = await enterpriseApi.verifyAuditChain(params)
      setResultado(r.data)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado('') }
  }
  const exportar = async () => {
    setOcupado('exportar')
    try {
      const r = await enterpriseApi.exportAuditChain()
      downloadBlob(r.data, `audit-chain-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.json`)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado('') }
  }
  const comparar = async (fichero?: File) => {
    if (!fichero) return
    try {
      const head = JSON.parse(await fichero.text())?.head
      if (!head?.seq || !head?.entry_hash) { toast.error(t('enterprise.cadena_fichero_sin_cabeza')); return }
      await verificar(head)
    } catch { toast.error(t('enterprise.cadena_fichero_sin_cabeza')) }
  }
  const color = resultado ? (resultado.ok ? 'var(--success)' : 'var(--danger)') : 'var(--text-3)'
  return (
    <div className="enterprise-page-e8">
      <div className="ent-row-9">
        <div className="ent-box-12">
          <div className="u-md-700">{t('enterprise.cadena_titulo')}</div>
          <div className="u-text2-sm-mt2">{t('enterprise.cadena_ayuda')}</div>
        </div>
        <Button size="sm" icon={<ShieldCheck size={14} />} onClick={() => verificar()} disabled={!!ocupado && ocupado !== 'verificar'} loading={ocupado === 'verificar'}>{t('enterprise.cadena_verificar')}</Button>
        <Button size="sm" variant="secondary" onClick={exportar} disabled={!!ocupado && ocupado !== 'exportar'} loading={ocupado === 'exportar'}>{t('enterprise.cadena_exportar')}</Button>
        <Button size="sm" variant="ghost" icon={<FileUp size={14} />} onClick={() => ficheroRef.current?.click()} disabled={!!ocupado}>{t('enterprise.cadena_comparar')}</Button>
        <input ref={ficheroRef} type="file" accept="application/json,.json" className="ent-input" aria-label={t('enterprise.cadena_comparar')}
          onChange={e => { comparar(e.target.files?.[0]); e.target.value = '' }} />
      </div>
      {resultado && (
        <div role="status" className="ent-box-13 enterpri-sx5 enterprise-page-e7" style={{ '--enterprise-page-border': `1px solid ${color}` } as CSSProperties}>
          <div className="ent-box-14 enterprise-page-e3" style={{ '--enterprise-page-color': color } as CSSProperties}>
            {resultado.ok ? t('enterprise.cadena_ok') : resultado.breaks_total > 0 ? t('enterprise.cadena_rota', { n: resultado.breaks_total }) : t('enterprise.cadena_no_casa')}
          </div>
          <div className="ent-box-15">
            {t('enterprise.cadena_recorridas', { n: resultado.rows_checked })}
            {resultado.head.entry_hash && <> · {t('enterprise.cadena_cabeza')} #{resultado.head.seq} <code className="u-mono">{resultado.head.entry_hash.slice(0, 16)}…</code></>}
          </div>
          {resultado.expected_head && (
            <div className={`ent-box-16 ${resultado.expected_head.found ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
              {t(resultado.expected_head.found ? 'enterprise.cadena_cabeza_sigue' : 'enterprise.cadena_cabeza_falta', { seq: resultado.expected_head.seq })}
            </div>
          )}
          {resultado.breaks.length > 0 && (
            <ul className="ent-box-17">
              {resultado.breaks.slice(0, 20).map((b, i) => (
                <li key={i}>#{b.seq ?? '—'} · {t(`enterprise.cadena_razon_${b.reason}`)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function AuditTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: logs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_PAGE_SIZE}).then(r => r.data?.logs || []).catch(() => []),
  })
  const { data: resetRequestLogs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent-reset-request'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_SMALL_PAGE_SIZE,action:'PASSWORD_RESET_REQUEST'}).then(r => r.data?.logs || []).catch(() => []),
  })
  const { data: resetCompleteLogs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent-reset-complete'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_SMALL_PAGE_SIZE,action:'PASSWORD_RESET_COMPLETE'}).then(r => r.data?.logs || []).catch(() => []),
  })

  const passwordResetLogs = [...resetCompleteLogs, ...resetRequestLogs]
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 20)

  return (
    <div className="ent-grid-6">
      <CadenaDeAuditoria />
      <div className="ds-grid-stats">
        <KpiCard icon={<ScrollText size={16} />} label={t('pagina_ent.total_eventos')} value={logs.length} />
        <KpiCard icon={<KeyRound size={16} />} label={t('pagina_ent.reset_solicitados')} value={resetRequestLogs.length} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('pagina_ent.reset_completados')} value={resetCompleteLogs.length} />
      </div>

      <div className="enterprise-page-e2">
        <div className="ent-box-20">
          {traducir('enterprise.eventos_de_recuperacion_de_contrasena')}
        </div>
        {passwordResetLogs.length === 0 ? <EmptyState icon={<KeyRound size={28} />} title={traducir('enterprise.sin_eventos_de_recuperacion')} /> :
          passwordResetLogs.map((l, i) => (
            <div key={l.id||i} className="ent-grid-8">
              <span className="ent-label-8">{fmtDateTime(l.created_at)}</span>
              <span className={`u-600 ${l.action === 'PASSWORD_RESET_COMPLETE' ? 'enterpri-sx3' : 'enterpri-sx9'}`}>{etiq(t, 'pagina_ent.accion', l.action)}</span>
              <span className="u-text2">{l.resource_name || l.resource || '-'}</span>
              <span className="u-text3">{l.user_name||''}</span>
            </div>
          ))
        }
      </div>

      <div className="enterprise-page-e2">
        <div className="ent-box-20">
          {t('pagina_ent.audit_log_general_ultimos_30')}
        </div>
      {logs.length === 0 ? <EmptyState icon={<ScrollText size={28} />} title={traducir('enterprise.sin_entradas_en_el_audit_log')} /> :
        logs.slice(0,30).map((l, i) => (
          <div key={l.id||i} className="ent-grid-8">
            <span className="ent-label-8">{fmtDateTime(l.created_at)}</span>
            <span className="ent-label-4">{l.action}</span>
            <span className="u-text2">{l.resource} {l.resource_name||''}</span>
            <span className="u-text3">{l.user_name||''}</span>
          </div>
        ))
      }
      </div>
    </div>
  )
}

function APIKeysTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [newKey, setNewKey] = useState<ClaveDeApiCreada | null>(null)
  const [form, setForm] = useState<ApiKeyForm>({ name:'', rate_limit_per_hour:1000 })

  const { data: keys = [] } = useQuery<ClaveDeApi[]>({ queryKey:['api-keys'], queryFn:() => apiKeysApi.list().then(r => r.data) })
  const { mutate: create } = useMutation({
    mutationFn: (d: ApiKeyForm) => apiKeysApi.create({ ...d, scopes:['read'] }).then(r => r.data),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ['api-keys'] }); setNewKey(data); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: revoke } = useMutation({
    mutationFn: (id: string) => apiKeysApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      {newKey && (
        <div className="ent-card-9">
          <div className="ent-box-22">{traducir('enterprise.copiala_ahora_no_se_mostrara_de_nuevo')}</div>
          <code className="ent-card-10">{newKey.key}</code>
          <div className="ent-cerrar-clave"><Button size="sm" variant="secondary" onClick={() => setNewKey(null)}>{t('pagina_ent.cerrar')}</Button></div>
        </div>
      )}
      {keys.length === 0 ? <EmptyState icon={<Key size={28} />} title={traducir('enterprise.sin_api_keys')} description={t('pagina_ent.genera_una_clave_para_integraciones_externas')}
        action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_api_key')}</Button>} /> : (
        <div className="enterprise-page-e2">
          {keys.map(k => (
            <div key={k.id} className="ent-grid-9">
              <div>
                <div className="ent-label-4">{k.name}</div>
                <code className="u-text2-xs">{k.key_prefix}...</code>
              </div>
              <span className="u-text2">{(k.scopes||[]).map(s => etiq(t, 'developer.scope', s)).join(', ')}</span>
              <span className="u-text2">{t('pagina_ent.peticiones_hoy', { usadas: k.requests_today || 0, limite: k.rate_limit_per_day })}</span>
              <span className="u-text3">{k.last_used_at ? fmtDateTime(k.last_used_at) : t('pagina_ent.nunca_usado')}</span>
              <Button size="sm" variant="danger" onClick={() => { openConfirmGlobal({ message: t('pagina_ent.revocar_clave'), onConfirm: () => revoke(k.id), danger: true }) }}>{t('pagina_ent.revocar')}</Button>
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_api_key_2')} onClose={() => setShowCreate(false)} width={420}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} className="enterprise-page-e17" placeholder={traducir('enterprise.nombre_de_la_clave')} /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{traducir('enterprise.limite_por_hora')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={form.rate_limit_per_hour} onChange={e => setForm(f => ({...f, rate_limit_per_hour:+e.target.value}))} className="enterprise-page-e17" /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={!form.name}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function SSOTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const toast = useToast()
  const qc = useQueryClient()
  const [testResult, setTestResult] = useState<{valid?:boolean; issues?:string[]}|null>(null)
  // Auditoría 2026-11: el formulario solo tenía cliente y discovery; no se
  // podía activar (el PATCH no existía en el cliente), ni elegir rol por
  // defecto, mapear grupos a roles o limitar dominios.
  const VACIO = {
    provider: 'azure_ad', name: '',
    oidc_client_id: '', oidc_client_secret: '',
    oidc_discovery_url: '', oidc_scopes: 'openid email profile', is_active: true,
    default_role: 'employee', auto_create_users: true, allowed_domains: '',
    groups_claim: 'groups', role_mapping_text: '',
  }
  const [form, setForm] = useState(VACIO)
  const [editId, setEditId] = useState<string | null>(null)
  const aPayload = (f: typeof VACIO) => {
    const role_mapping: Record<string, string> = {}
    f.role_mapping_text.split('\n').map(l => l.trim()).filter(Boolean).forEach(l => {
      const i = l.lastIndexOf('=')
      if (i > 0) role_mapping[l.slice(0, i).trim()] = l.slice(i + 1).trim()
    })
    const { role_mapping_text: _omit, ...resto } = f
    const datos: Record<string, unknown> = { ...resto, role_mapping }
    if (editId) { delete datos.provider; if (!f.oidc_client_secret) delete datos.oidc_client_secret }
    return datos
  }

  const { data: configs = [] } = useQuery<ConfigSso[]>({
    queryKey: ['sso-cfg'],
    queryFn: () => enterpriseApi.ssoList().then(r => r.data).catch(() => []),
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: Record<string, unknown>) => (editId ? enterpriseApi.ssoUpdate(editId, d) : enterpriseApi.ssoCreate(d)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); setShowCreate(false); setEditId(null); setForm(VACIO); toast.success(t('pagina_ent.sso_guardado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: (c: ConfigSso) => enterpriseApi.ssoUpdate(c.id, { is_active: !c.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sso-cfg'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const editar = (c: ConfigSso) => {
    setEditId(c.id)
    setForm({
      ...VACIO, provider: c.provider, name: c.name || '', oidc_client_id: c.oidc_client_id || '',
      oidc_discovery_url: c.oidc_discovery_url || '', oidc_scopes: c.oidc_scopes || VACIO.oidc_scopes,
      is_active: !!c.is_active, default_role: c.default_role || 'employee', auto_create_users: c.auto_create_users !== false,
      allowed_domains: c.allowed_domains || '', groups_claim: c.groups_claim || 'groups',
      role_mapping_text: Object.entries(c.role_mapping || {}).map(([g, r]) => `${g}=${r}`).join('\n'),
    })
    setShowCreate(true)
  }

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => enterpriseApi.ssoDelete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); toast.success(t('pagina_ent.sso_eliminado')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const testSSO = async (id: string) => {
    try {
      const res = await enterpriseApi.ssoTest(id)
      setTestResult(res.data)
    } catch (e: unknown) {
      const _raw2 = (e as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
      const _msg2 = Array.isArray(_raw2) ? _raw2.map((d: ValidationDetail) => d.msg).join(', ') : ((_raw2 as string) || t('pagina_ent.error_de_conexion'))
      setTestResult({ valid: false, issues: [_msg2] })
    }
  }

  const PROVIDER_INFO: Record<string, { label:string; discovery:string }> = {
    azure_ad: { label: t('pagina_ent.azure_ad_entra_id'), discovery: 'https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration' },
    okta:     { label: 'Okta',                discovery: 'https://{your-domain}.okta.com/.well-known/openid-configuration' },
    google:   { label: 'Google Workspace',    discovery: 'https://accounts.google.com/.well-known/openid-configuration' },
    oidc:     { label: t('pagina_ent.oidc_generico'), discovery: 'https://your-idp.com/.well-known/openid-configuration' },
  }
  const cerrarFormulario = () => { setShowCreate(false); setEditId(null); setForm(VACIO) }


  return (
    <div>
      <div className="ent-row-10">
        <div className="u-min0">
          <div className="u-md-700">{t('pagina_ent.single_sign_on_sso')}</div>
          <div className="u-text2-sm">{t('pagina_ent.configura_azure_ad_entra_id_okta')}</div>
        </div>
      </div>

      {/* Información de integración */}
      <div className="enterprise-page-e10">
        <div className="ent-box-23">{traducir('enterprise.como_integrar_sso')}</div>
        <div className="ent-box-24">
          {traducir('enterprise.1_registra_contecflow_como_aplicacion_en_tu')}<br/>
          {traducir('enterprise.2_configura_el')} <strong className="u-text1">{t('pagina_ent.redirect_uri')}</strong>: <code className="ent-card-11">{window.location.origin}/login</code><br/>
          {traducir('enterprise.3_copia_el_client_id_y_client')}<br/>
          {traducir('enterprise.4_anade_el_boton_de_login_sso')} <strong className="u-text1">{t('pagina_ent.ajustes')}{' '}{'>'}{' '}{t('pagina_ent.seguridad')}</strong>.
        </div>
      </div>

      {/* Formulario de creación */}
      {showCreate && (
        <div className="enterprise-page-e11">
          <div className="ent-box-25">{editId ? traducir('enterprise.sso_editar') : traducir('enterprise.nuevo_proveedor_sso')}</div>
          <div className={`ent-grid-10 ${isNarrow ? 'enterpri-sx10' : 'enterpri-sx11'}`}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e20">{t('pagina_ent.proveedor')}</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.provider} disabled={!!editId} onChange={e => {
                const info: { label?: string; discovery?: string } = PROVIDER_INFO[e.target.value] || {}
                setForm(f => ({ ...f, provider: e.target.value, oidc_discovery_url: info.discovery || '' }))
              }} className="enterprise-page-e19">
                {Object.entries(PROVIDER_INFO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e20">{traducir('enterprise.nombre_para_mostrar_en_login')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} className="enterprise-page-e19" placeholder={PROVIDER_INFO[form.provider]?.label} />
            </div>
            <div>
              <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="enterprise-page-e20">{t('pagina_ent.client_id')}</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.oidc_client_id} onChange={e => setForm(f=>({...f,oidc_client_id:e.target.value}))} className="enterprise-page-e19" placeholder={traducir('enterprise.client_id_del_proveedor')} />
            </div>
            <div>
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="enterprise-page-e20">{t('pagina_ent.client_secret')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="password" value={form.oidc_client_secret} onChange={e => setForm(f=>({...f,oidc_client_secret:e.target.value}))} className="enterprise-page-e19" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="enterprise-page-e20">{t('pagina_ent.discovery_url_openid_connect')}</label>
              <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.oidc_discovery_url} onChange={e => setForm(f=>({...f,oidc_discovery_url:e.target.value}))} className="enterprise-page-e19" placeholder={PROVIDER_INFO[form.provider]?.discovery} />
            </div>
            <div>
              <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="enterprise-page-e20">{traducir('enterprise.sso_scopes')}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.oidc_scopes} onChange={e => setForm(f=>({...f,oidc_scopes:e.target.value}))} className="enterprise-page-e19" />
            </div>
            <div>
              <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="enterprise-page-e20">{traducir('enterprise.sso_dominios')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.allowed_domains} onChange={e => setForm(f=>({...f,allowed_domains:e.target.value}))} className="enterprise-page-e19" placeholder={t('pagina_ent.empresa_com_filial_es')} />
            </div>
            <div>
              <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="enterprise-page-e20">{traducir('enterprise.sso_rol_defecto')}</label>
              <select id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.default_role} onChange={e => setForm(f=>({...f,default_role:e.target.value}))} className="enterprise-page-e19">
                {ROLES_SSO.map(r => <option key={r} value={r}>{etiquetaCodigo(t, 'rol_usuario', r)}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="enterprise-page-e20">{traducir('enterprise.sso_claim_grupos')}</label>
              <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.groups_claim} onChange={e => setForm(f=>({...f,groups_claim:e.target.value}))} className="enterprise-page-e19" />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="enterprise-page-e20">{traducir('enterprise.sso_mapeo')}</label>
              <textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} rows={3} value={form.role_mapping_text} onChange={e => setForm(f=>({...f,role_mapping_text:e.target.value}))} className="enterprise-page-e12" placeholder={'Contecflow-Admins=admin\nContecflow-PM=pm'} />
            </div>
            <label className="ent-label-9">
              <input type="checkbox" aria-label={traducir('enterprise.sso_autocrear')} checked={form.auto_create_users} onChange={e => setForm(f=>({...f,auto_create_users:e.target.checked}))} />
              {traducir('enterprise.sso_autocrear')}
            </label>
            <label className="ent-label-9">
              <input type="checkbox" aria-label={traducir('enterprise.sso_activo')} checked={form.is_active} onChange={e => setForm(f=>({...f,is_active:e.target.checked}))} />
              {traducir('enterprise.sso_activo')}
            </label>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={cerrarFormulario}>{t('pagina_ent.cancelar')}</Button>
            <Button onClick={() => create(aPayload(form))} disabled={!form.oidc_client_id} loading={creating}>
              {creating ? t('pagina_ent.guardando') : t('pagina_ent.guardar_sso')}
            </Button>
          </div>
        </div>
      )}

      {/* Lista de proveedores */}
      {configs.length === 0 && !showCreate ? (
        <EmptyState icon={<KeyRound size={28} />} title={traducir('enterprise.sin_sso_configurado')} description={traducir('enterprise.anade_azure_ad_okta_o_google_para')}
          action={<Button icon={<Plus size={14} />} onClick={() => { setEditId(null); setForm(VACIO); setShowCreate(true) }}>{t('pagina_ent.anadir_proveedor')}</Button>} />
      ) : (
        configs.map(c => {
          const info = PROVIDER_INFO[c.provider] || { label: c.provider }
          return (
            <div key={c.id} className="enterprise-page-e13">
              <div className="ent-row-11">
                <div className="ent-row-7">
                  <span className="ent-label-10" aria-hidden><KeyRound size={20} /></span>
                  <div className="ent-box-29">
                    <div className="u-md-700">{c.name || info.label}</div>
                    <div className="u-text2-xs">
                      {t('pagina_ent.client_id_2')}{' '}{c.oidc_client_id?.slice(0,8)}...
                      {' '}<StatusBadge kind={c.is_active ? 'success' : 'neutral'}>{c.is_active ? t('pagina_ent.activo') : t('pagina_ent.inactivo')}</StatusBadge>
                    </div>
                    {c.oidc_discovery_url && (
                      <div className="ent-box-30">{c.oidc_discovery_url.slice(0, 60)}...</div>
                    )}
                  </div>
                </div>
                <div className="u-wrap-6">
                  <Button size="sm" variant="secondary" onClick={() => toggle(c)}>
                    {c.is_active ? traducir('enterprise.sso_desactivar') : traducir('enterprise.sso_activar')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => testSSO(c.id)}>
                    {t('pagina_ent.verificar_config')}
                  </Button>
                  <IconButton onClick={() => editar(c)} ariaLabel={`${traducir('enterprise.sso_editar')} ${c.name || c.provider}`}><Pencil size={14} aria-hidden /></IconButton>
                  <IconButton className="ent-borrar" ariaLabel={t('pagina_ent.eliminar_2', { v1: c.name || c.provider })} onClick={() => { openConfirmGlobal({ message: t('pagina_ent.eliminar_2', { v1: c.name || c.provider }), onConfirm: () => del(c.id), danger: true }) }}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* Resultado del test */}
      {testResult && (
        <div className={`enterprise-page-e13 ${testResult.valid ? 'enterprise-page-m14' : 'enterprise-page-m15'}`}>
          <div className={`ent-box-31 ent-resultado ${testResult.valid ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
            {testResult.valid ? <CheckCircle2 size={14} aria-hidden /> : <XCircle size={14} aria-hidden />}
            {testResult.valid ? t('pagina_ent.configuracion_valida') : t('pagina_ent.configuracion_incompleta')}
          </div>
          {(testResult.issues?.length ?? 0) > 0 && (
            <ul className="ent-box-32">
              {testResult.issues!.map((i: string, idx: number) => <li key={idx} className="ent-box-33">{i}</li>)}
            </ul>
          )}
          <div className="ent-cerrar-clave"><Button size="sm" variant="secondary" onClick={() => setTestResult(null)}>{t('pagina_ent.cerrar')}</Button></div>
        </div>
      )}
    </div>
  )
}

// ── Componente principal ───────────────────────────────────────────────────────
export default function EnterprisePage(): JSX.Element {
  const { t } = useAppLang()
  const _t = useAppT()
  // `?tab=<id>` abre esa pestaña (la lista de puesta en marcha enlaza a SSO).
  const [tab, setTabState] = useState(() => new URLSearchParams(window.location.search).get('tab') || 'webhooks')
  // El alta de cada pestaña se abre desde la cabecera: `alta` dice cuál está abierta.
  const [alta, setAlta] = useState<string | null>(null)
  const setTab = (id: string) => { setTabState(id); setAlta(null) }
  const fijarAlta = (id: string) => (v: boolean) => setAlta(v ? id : null)

  const TABS = [
    { id: 'webhooks',     label: t('pagina_ent.webhooks'), icon: <Webhook size={14} /> },
    { id: 'gdpr',         label: t('pagina_ent.rgpd'), icon: <ShieldCheck size={14} /> },
    { id: 'email',        label: t('pagina_ent.email'), icon: <Mail size={14} /> },
    { id: 'integrations', label: t('pagina_ent.integraciones'), icon: <Plug size={14} /> },
    { id: 'sso',          label: 'SSO', icon: <KeyRound size={14} /> },
    { id: 'audit',        label: t('pagina_ent.auditoria'), icon: <ScrollText size={14} /> },
    { id: 'apikeys',      label: t('pagina_ent.api_keys'), icon: <Key size={14} /> },
  ]

  const accion = (id: string, texto: string) => (
    <Button icon={<Plus size={14} />} onClick={() => setAlta(id)}>{texto}</Button>
  )
  const acciones = tab === 'webhooks' ? accion('webhooks', _t('enterprise.nuevo_webhook'))
    : tab === 'gdpr' ? accion('gdpr', _t('enterprise.nueva_solicitud'))
    : tab === 'email' ? (
      <>
        <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setAlta('email-plantilla')}>{t('pagina_ent.plantilla')}</Button>
        <Button icon={<Send size={14} />} onClick={() => setAlta('email-envio')}>{t('pagina_ent.enviar_email')}</Button>
      </>
    )
    : tab === 'sso' ? accion('sso', t('pagina_ent.anadir_proveedor'))
    : tab === 'apikeys' ? accion('apikeys', _t('enterprise.nueva_api_key'))
    : undefined

  return (
    <PageShell>
      <PageHeader
        icon={<Building2 size={18} />}
        title={_t('nav.enterprise')}
        subtitle={_t('enterprise.subtitle')}
        actions={acciones}
        showListExport={false}
      />

      <Tabs items={TABS} active={tab} onChange={setTab} className="ent-tabs" />

      {/* Contenido */}
      {tab === 'webhooks'     && <WebhooksTab showCreate={alta === 'webhooks'} setShowCreate={fijarAlta('webhooks')} />}
      {tab === 'gdpr'         && <GDPRTab showCreate={alta === 'gdpr'} setShowCreate={fijarAlta('gdpr')} />}
      {tab === 'email'        && <EmailTab showCreate={alta === 'email-plantilla'} setShowCreate={fijarAlta('email-plantilla')}
                                   showSend={alta === 'email-envio'} setShowSend={fijarAlta('email-envio')} />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'sso'          && <SSOTab showCreate={alta === 'sso'} setShowCreate={fijarAlta('sso')} />}
      {tab === 'audit'        && <AuditTab />}
      {tab === 'apikeys'      && <APIKeysTab showCreate={alta === 'apikeys'} setShowCreate={fijarAlta('apikeys')} />}
    </PageShell>
  )
}
