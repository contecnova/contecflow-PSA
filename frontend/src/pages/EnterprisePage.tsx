/**
 * EnterprisePage v14 — Webhooks, GDPR, Email, Integraciones, SSO, Audit, API Keys
 */
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, downloadBlob } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, webhooksApi, autoWorkflowsApi, gdprApi, emailApi, oauthIntegrationsApi, integrationsHubApi, enterpriseApi, apiKeysApi, apiUrl } from '../services/api'
import type { ClaveDeApi, ClaveDeApiCreada, ConfigSso, EventoDeAuditoria, IntegracionOAuth, VerificacionDeCadena } from '../services/api/tipos'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'

import { useAppT } from '../i18n/AppLangContext'
import { INTEGRATION_CATALOG } from '../constants/api'
import { Building2 } from 'lucide-react'
import useMediaQuery from '../hooks/useMediaQuery'
import { AUDIT_LOG_PAGE_SIZE, AUDIT_LOG_SMALL_PAGE_SIZE } from '../constants/pagination'

const fs: CSSProperties = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

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

function WebhooksTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
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
      <div style={{ background:'var(--accent-muted)', border:'.5px solid rgba(0,212,255,0.25)', borderRadius:'var(--radius-md)', padding:'12px 16px', marginBottom:20, fontSize: "var(--text-base)", color:'var(--accent)' }}>
        {traducir('enterprise.los_webhooks_entrantes_permiten_que_sistemas_externos')}
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>{traducir('enterprise.nuevo_webhook')}</Button>
      </div>
      {isLoading ? <Spinner /> : triggers.length === 0 ? (
        <EmptyState icon="🔗" title={traducir('enterprise.sin_webhooks')} description="Crea el primer webhook entrante para automatizaciones" />
      ) : triggers.map(t => (
        <div key={t.id} style={{ ...card, padding:'14px 18px', marginBottom:10 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 }}>
            <div className="u-min0">
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:4 }}>{t.name}</div>
              <code style={{ fontSize: "var(--text-xs)", background:'var(--surface-2)', padding:'2px 8px', borderRadius:4, color:'var(--text-2)' }}>POST {apiUrl(t.endpoint)}</code>
              <span style={{ marginLeft:12, fontSize: "var(--text-xs)", color:'var(--text-2)' }}>{t.fire_count} disparos</span>
            </div>
            <div className="u-row-8">
              <button onClick={() => setShowLogs(showLogs === t.id ? null : t.id)} style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:'var(--radius-sm)', padding:'4px 10px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-xs)", fontFamily:'inherit' }}>
                {showLogs === t.id ? 'Ocultar' : 'Logs'}
              </button>
              <button onClick={() => { openConfirmGlobal({ message: 'Eliminar?', onConfirm: () => del(t.id), danger: true }) }} style={{ background:'transparent', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:'var(--radius-sm)', padding:'4px 8px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
            </div>
          </div>
          {showLogs === t.id && (
            <div style={{ marginTop:10, borderTop:'.5px solid var(--surface-4)', paddingTop:8 }}>
              {logs.length === 0 ? <div className="u-text3-sm">{traducir('enterprise.sin_llamadas_aun')}</div> :
                logs.slice(0,5).map(l => (
                  <div key={l.id} style={{ fontSize: "var(--text-xs)", padding:'3px 0', borderBottom:'.5px solid var(--surface-4)', display:'flex', gap:10 }}>
                    <span style={{ color: l.status === 'ok' ? 'var(--success)' : 'var(--danger)' }}>{l.status}</span>
                    <span className="u-text2">{l.received_at}</span>
                    <span style={{ color:'var(--text-3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>{l.payload_preview}</span>
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
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} style={fs} /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Slug (URL)</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.slug} onChange={e => setForm(f => ({...f, slug:e.target.value.toLowerCase().replace(/\s+/g,'-')}))} style={fs} placeholder="mi-webhook" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Workflow</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.workflow_id} onChange={e => setForm(f => ({...f, workflow_id:e.target.value}))} style={fs}>
                <option value="">{traducir('enterprise.sin_workflow')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <div style={{ background:'var(--surface-2)', borderRadius:8, padding:'8px 12px', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
              URL: <code>POST {apiUrl(`/webhooks/fire/${form.slug || 'tu-slug'}`)}</code>
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => create(form)} disabled={isPending || !form.name || !form.slug}>Crear</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function GDPRTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<GdprForm>({ request_type:'erasure', subject_user_id:'', subject_email:'', notes:'' })

  const { data: requests = [], isLoading } = useQuery({ queryKey:['gdpr'], queryFn:() => gdprApi.list().then(r => r.data) })
  const { data: usersRaw = [] } = useQuery({ queryKey:['users'], queryFn:() => usersApi.list().then(r => r.data) })
  const users = Array.isArray(usersRaw) ? usersRaw : []

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: GdprForm) => gdprApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['gdpr'] }); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: process } = useMutation({
    mutationFn: (id: string) => gdprApi.process(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gdpr'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const TYPE_LABELS: Record<string,string> = { erasure:'Derecho al olvido', portability:'Portabilidad', access:'Acceso', rectification:'Rectificación' }
  const STATUS_COLORS: Record<string,string> = { pending:'var(--warning)', processing:'var(--accent)', completed:'var(--success)', rejected:'var(--danger)' }

  return (
    <div>
      <div style={{ background:'var(--warning-bg)', border:'.5px solid rgba(251,191,36,0.25)', borderRadius:'var(--radius-md)', padding:'12px 16px', marginBottom:20, fontSize: "var(--text-base)", color:'var(--warning)' }}>
        {traducir('enterprise.gestion_de_solicitudes_rgpd_plazo_maximo_de')}
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_solicitud')}</Button>
      </div>
      {isLoading ? <Spinner /> : requests.length === 0 ? (
        <EmptyState icon="🔒" title={traducir('enterprise.sin_solicitudes_rgpd')} description="No hay solicitudes de privacidad registradas" />
      ) : (
        <div style={{ ...card, overflowX:'auto' }}>
          {requests.map(r => (
            <div key={r.id} style={{ display:'grid', gridTemplateColumns:'150px 120px 1fr 100px auto', gap:12, minWidth:640, padding:'12px 18px', borderBottom:'.5px solid var(--surface-4)', alignItems:'center' }}>
              <span style={{ fontSize: "var(--text-sm)", fontWeight:500 }}>{TYPE_LABELS[r.request_type] || r.request_type}</span>
              <span style={{ fontSize: "var(--text-sm)", fontWeight:500, color:STATUS_COLORS[r.status] || 'var(--text-2)' }}>{r.status}</span>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{r.subject_name}</div>
                {r.subject_email && <div className="u-text2-xs">{r.subject_email}</div>}
                {r.notes && <div className="u-text2-xs">{r.notes}</div>}
              </div>
              <span className="u-text2-sm">{r.deadline}</span>
              {r.status === 'pending' && <Button onClick={() => process(r.id)}>Procesar</Button>}
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_solicitud_rgpd')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Tipo</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.request_type} onChange={e => setForm(f => ({...f, request_type:e.target.value}))} style={fs}>
                <option value="erasure">{traducir('enterprise.derecho_al_olvido_art_17')}</option>
                <option value="portability">Portabilidad (Art. 20)</option>
                <option value="access">Acceso (Art. 15)</option>
                <option value="rectification">{traducir('enterprise.rectificacion_art_16')}</option>
              </select>
            </div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Usuario</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.subject_user_id} onChange={e => setForm(f => ({...f, subject_user_id:e.target.value}))} style={fs}>
                <option value="">Seleccionar...</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.full_name} — {u.email}</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{traducir('enterprise.email_si_ya_no_existe')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.subject_email} onChange={e => setForm(f => ({...f, subject_email:e.target.value}))} style={fs} />
            </div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Notas</label>
              <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.notes} onChange={e => setForm(f => ({...f, notes:e.target.value}))} rows={3} style={{...fs, resize:'vertical'}} />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => create(form)} disabled={isPending || (!form.subject_user_id && !form.subject_email)}>Crear</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function EmailTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showSend, setShowSend] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
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
      <div style={{ display:'flex', flexWrap:'wrap', gap:10, justifyContent:'flex-end', marginBottom:20 }}>
        <button onClick={() => setShowCreate(true)} style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'8px 14px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
          + Plantilla
        </button>
        <Button onClick={() => setShowSend(true)}>✉ Enviar email</Button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(320px, 100%), 1fr))', gap:20 }}>
        <div className="u-min0">
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:12 }}>Plantillas ({allTpl.length})</div>
          {allTpl.map(t => (
            <div key={t.id} style={{ ...card, padding:'12px 14px', marginBottom:8 }}>
              <div style={{ display:'flex', gap:6, marginBottom:4 }}>
                <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>{t.category}</span>
                {t.is_system && <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-2)', color:'var(--text-3)' }}>sistema</span>}
              </div>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{t.name}</div>
              <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:2, fontFamily:'var(--font-mono)' }}>{t.subject}</div>
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:12 }}>{traducir('enterprise.historial_de_envios')}</div>
          {logs.length === 0 ? <EmptyState icon="✉" title={traducir('enterprise.sin_historial_de_envios')} description="Todavia no se han enviado correos desde este modulo" /> : (
            <div style={{ ...card, overflow:'hidden' }}>
              {logs.slice(0,15).map(l => (
                <div key={l.id} style={{ display:'grid', gridTemplateColumns:'50px 1fr auto', gap:8, padding:'8px 14px', borderBottom:'.5px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                  <span style={{ fontWeight:500, color: l.status === 'sent' ? 'var(--success)' : 'var(--danger)' }}>{l.status}</span>
                  <div>
                    <div style={{ fontWeight:500 }}>{l.to}</div>
                    <div className="u-text2-xs">{l.subject}</div>
                  </div>
                  <span style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', whiteSpace:'nowrap' }}>{(l.sent_at || l.created_at || '').slice(0,16)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {showSend && (
        <Modal open title="Enviar email" onClose={() => setShowSend(false)} width={500}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>{traducir('enterprise.para')}</label><input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={sendForm.to} onChange={e => setSendForm(f => ({...f, to:e.target.value}))} style={fs} placeholder="destinatario@empresa.com" /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Plantilla</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={sendForm.template_id} onChange={e => setSendForm(f => ({...f, template_id:e.target.value}))} style={fs}>
                <option value="">{traducir('enterprise.sin_plantilla')}</option>
                {allTpl.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            {!sendForm.template_id && <>
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Asunto</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sendForm.subject} onChange={e => setSendForm(f => ({...f, subject:e.target.value}))} style={fs} /></div>
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>HTML</label><textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={sendForm.body_html} onChange={e => setSendForm(f => ({...f, body_html:e.target.value}))} rows={4} style={{...fs, resize:'vertical'}} /></div>
            </>}
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowSend(false)}>Cancelar</Button>
              <Button onClick={() => send(sendForm)} disabled={sending || !sendForm.to}>{sending ? 'Enviando...' : 'Enviar'}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_plantilla_de_email')} onClose={() => setShowCreate(false)} width={560}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Nombre</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={newTpl.name} onChange={e => setNewTpl(f => ({...f, name:e.target.value}))} style={fs} /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>Asunto (usa {'{{variable}}'})</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={newTpl.subject} onChange={e => setNewTpl(f => ({...f, subject:e.target.value}))} style={fs} /></div>
            <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{traducir('enterprise.categoria')}</label>
              <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={newTpl.category} onChange={e => setNewTpl(f => ({...f, category:e.target.value}))} style={fs}>
                {['automation','alert','report','invoice'].map((c: string) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{traducir('enterprise.html_del_cuerpo')}</label><textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={newTpl.body_html} onChange={e => setNewTpl(f => ({...f, body_html:e.target.value}))} rows={5} style={{...fs, resize:'vertical'}} /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => createTpl(newTpl)} disabled={!newTpl.name || !newTpl.subject || !newTpl.body_html}>Crear</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function IntegrationsTab() {
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
    onSuccess: () => { invalidar(); setConfiguring(null); toast.success('Integración guardada') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.deleteJiraConfig() : oauthIntegrationsApi.delete(id),
    onSuccess: () => { invalidar(); toast.success('Integración eliminada') },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: sync } = useMutation({
    mutationFn: (id: string) => id === JIRA_ID ? integrationsHubApi.syncJira() : oauthIntegrationsApi.sync(id, {}),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['integrations'] }); toast.success(`Sincronizados: ${r?.data?.synced ?? 0} elementos${r?.data?.errors?.length ? ` · ${r.data.errors.length} con error` : ''}`) },
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
        setTestResult({ ok: true, message: `Conectado: ${res.data.total} proyectos Jira disponibles` })
      } else {
        const res = await oauthIntegrationsApi.sync(integ.id, {})
        setTestResult({ ok: true, message: `Sincronizados: ${res.data.synced} elementos` })
      }
    } catch (e: unknown) {
      const _raw1 = (e as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
      setTestResult({ ok: false, message: Array.isArray(_raw1) ? _raw1.map((d: ValidationDetail) => d.msg).join(', ') : ((_raw1 as string) || 'Error de conexión') })
    } finally {
      setTesting(null)
    }
  }


  // El catálogo viene de la configuración de negocio sin tipar (`unknown`).
  const CATALOG = INTEGRATION_CATALOG as IntegrationCatalogEntry[]

  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }
  const is: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 11px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

  return (
    <div>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>Integraciones nativas</div>
      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16 }}>{traducir('enterprise.conecta_contecflow_con_tus_herramientas_de_trabajo')}</div>

      {/* Integraciones activas */}
      {integrations.length > 0 && (
        <div className="u-mb-20">
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Configuradas</div>
          {integrations.map(integ => {
            const cat = CATALOG.find((c) => c.type === integ.integration_type) || { icon: '🔗', label: integ.integration_type }
            return (
              <div key={integ.id} style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', minWidth: 0 }}>
                  <span style={{ fontSize: "var(--text-xl-em)" }}>{cat.icon}</span>
                  <div>
                    <div className="u-base-700">{integ.name || cat.label}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: integ.is_active ? 'var(--success)' : 'var(--danger)' }}>
                      {integ.is_active ? '● Activa' : '● Inactiva'}
                      {integ.last_sync_at && ` · Último sync: ${integ.last_sync_at.slice(0,10)}`}
                    </div>
                  </div>
                </div>
                <div className="u-row-6">
                  <button onClick={() => testIntegration(integ)} disabled={testing === integ.id}
                    style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                    {testing === integ.id ? '⟳' : '🔧 Probar'}
                  </button>
                  <button onClick={() => sync(integ.id)}
                    style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                    ↺ Sync
                  </button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${integ.name}?`, onConfirm: () => del(integ.id), danger: true }) }}
                    style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              </div>
            )
          })}

          {/* Test result */}
          {testResult && (
            <div style={{ background: testResult.ok ? 'var(--success-bg)' : 'var(--danger-bg)', border: `1px solid ${testResult.ok ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8, padding: '8px 14px', marginTop: 8, fontSize: "var(--text-sm)", color: testResult.ok ? 'var(--success)' : 'var(--danger)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {testResult.ok ? '✅' : '✗'} {testResult.message}
              <button onClick={() => setTestResult(null)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✕</button>
            </div>
          )}
        </div>
      )}

      {/* Catálogo para añadir */}
      <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
        {integrations.length === 0 ? 'Disponibles' : 'Añadir otra'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))', gap: 10 }}>
        {CATALOG.map((cat) => (
          <button key={cat.type} onClick={() => {
            setConfiguring(cat)
            // Jira: se precarga la conexión guardada; el token vacío conserva el actual.
            const previa = cat.type === 'jira' && jira?.configured
              ? { base_url: jira.base_url || '', email: jira.email || '', project_key: jira.project_key || '' } : {}
            setForm({ name: (cat.type === 'jira' && jira?.configured && jira.name) || cat.label, integration_type: cat.type, config: previa })
          }}
            type="button"
            style={{ background: 'var(--surface-1)', border: `1px solid ${configuring?.type === cat.type ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 'var(--radius-md)', padding: '14px 16px', cursor: 'pointer', transition: 'border-color 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = configuring?.type === cat.type ? 'var(--accent)' : 'var(--surface-4)'}
          >
            <div style={{ fontSize: "var(--text-2xl)", marginBottom: 6 }}>{cat.icon}</div>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 3 }}>{cat.label}</div>
            <div className="u-text2-xs">{cat.desc}</div>
          </button>
        ))}
      </div>

      {/* Formulario de configuración */}
      {configuring && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--accent-border)', borderRadius: 12, padding: '18px 20px', marginTop: 16 }}>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--accent)', marginBottom: 14 }}>
            {configuring.icon} Configurar {configuring.label}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10, marginBottom: 14 }}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{traducir('enterprise.nombre_de_la_integracion')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={is} />
            </div>
            {configuring.fields?.map(field => (
              <div key={field.key}>
                <label id={`${idCampo}-et-${field.key}`} htmlFor={`${idCampo}-${field.key}`} style={ls}>{field.label}</label>
                <input id={`${idCampo}-${field.key}`} aria-labelledby={`${idCampo}-et-${field.key}`}
                  type={field.type || 'text'}
                  value={form.config?.[field.key] || ''}
                  onChange={e => setForm(f => ({ ...f, config: { ...f.config, [field.key]: e.target.value } }))}
                  style={is}
                  placeholder={field.placeholder || ''}
                />
              </div>
            ))}
          </div>
          <div className="u-actions-8">
            <button onClick={() => setConfiguring(null)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <button onClick={() => create({ ...form, integration_type: configuring.type, config: JSON.stringify(form.config) })}
              disabled={isPending}
              style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-border-strong)', borderRadius: 8, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
              {isPending ? '⟳ Guardando...' : '✓ Guardar integración'}
            </button>
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
    <div style={{ ...card, padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div className="u-md-700">{t('enterprise.cadena_titulo')}</div>
          <div className="u-text2-sm-mt2">{t('enterprise.cadena_ayuda')}</div>
        </div>
        <Button size="sm" onClick={() => verificar()} disabled={!!ocupado}>{ocupado === 'verificar' ? '…' : t('enterprise.cadena_verificar')}</Button>
        <Button size="sm" variant="secondary" onClick={exportar} disabled={!!ocupado}>{ocupado === 'exportar' ? '…' : t('enterprise.cadena_exportar')}</Button>
        <label style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', cursor: 'pointer' }}>
          {t('enterprise.cadena_comparar')}
          <input type="file" accept="application/json,.json" style={{ display: 'none' }} aria-label={t('enterprise.cadena_comparar')}
            onChange={e => { comparar(e.target.files?.[0]); e.target.value = '' }} />
        </label>
      </div>
      {resultado && (
        <div role="status" style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8, border: `1px solid ${color}`, background: 'var(--surface-1)' }}>
          <div style={{ fontWeight: 700, color }}>
            {resultado.ok ? t('enterprise.cadena_ok') : resultado.breaks_total > 0 ? t('enterprise.cadena_rota', { n: resultado.breaks_total }) : t('enterprise.cadena_no_casa')}
          </div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>
            {t('enterprise.cadena_recorridas', { n: resultado.rows_checked })}
            {resultado.head.entry_hash && <> · {t('enterprise.cadena_cabeza')} #{resultado.head.seq} <code className="u-mono">{resultado.head.entry_hash.slice(0, 16)}…</code></>}
          </div>
          {resultado.expected_head && (
            <div style={{ fontSize: "var(--text-sm)", marginTop: 4, color: resultado.expected_head.found ? 'var(--success)' : 'var(--danger)' }}>
              {t(resultado.expected_head.found ? 'enterprise.cadena_cabeza_sigue' : 'enterprise.cadena_cabeza_falta', { seq: resultado.expected_head.seq })}
            </div>
          )}
          {resultado.breaks.length > 0 && (
            <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: "var(--text-sm)" }}>
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
    <div style={{ display: 'grid', gap: 14 }}>
      <CadenaDeAuditoria />
      <div style={{ ...card, padding: '12px 14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 12 }}>
          <div style={{ background: 'var(--surface-2)', border: '.5px solid var(--surface-4)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Total eventos</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, marginTop: 4 }}>{logs.length}</div>
          </div>
          <div style={{ background: 'var(--surface-2)', border: '.5px solid var(--surface-4)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Reset solicitados</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, marginTop: 4 }}>{resetRequestLogs.length}</div>
          </div>
          <div style={{ background: 'var(--surface-2)', border: '.5px solid var(--surface-4)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Reset completados</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, marginTop: 4 }}>{resetCompleteLogs.length}</div>
          </div>
        </div>
      </div>

      <div style={{ ...card, overflowX:'auto' }}>
        <div style={{ padding: '10px 16px', fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', borderBottom: '.5px solid var(--surface-4)' }}>
          {traducir('enterprise.eventos_de_recuperacion_de_contrasena')}
        </div>
        {passwordResetLogs.length === 0 ? <div style={{ padding:18, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-sm)" }}>{traducir('enterprise.sin_eventos_de_recuperacion')}</div> :
          passwordResetLogs.map((l, i) => (
            <div key={l.id||i} style={{ display:'grid', gridTemplateColumns:'140px 220px 1fr 140px', gap:12, minWidth:700, padding:'9px 16px', borderBottom:'.5px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
              <span style={{ color:'var(--text-2)', fontFamily:'var(--font-mono)' }}>{(l.created_at||'').slice(0,16)}</span>
              <span style={{ fontWeight:600, color: l.action === 'PASSWORD_RESET_COMPLETE' ? 'var(--success)' : 'var(--accent)' }}>{l.action}</span>
              <span className="u-text2">{l.resource_name || l.resource || '-'}</span>
              <span className="u-text3">{l.user_name||''}</span>
            </div>
          ))
        }
      </div>

      <div style={{ ...card, overflowX:'auto' }}>
        <div style={{ padding: '10px 16px', fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', borderBottom: '.5px solid var(--surface-4)' }}>
          Audit log general (ultimos 30)
        </div>
      {logs.length === 0 ? <div style={{ padding:18, textAlign:'center', color:'var(--text-3)', fontSize: "var(--text-sm)" }}>{traducir('enterprise.sin_entradas_en_el_audit_log')}</div> :
        logs.slice(0,30).map((l, i) => (
          <div key={l.id||i} style={{ display:'grid', gridTemplateColumns:'140px 220px 1fr 140px', gap:12, minWidth:700, padding:'9px 16px', borderBottom:'.5px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
            <span style={{ color:'var(--text-2)', fontFamily:'var(--font-mono)' }}>{(l.created_at||'').slice(0,16)}</span>
            <span style={{ fontWeight:500 }}>{l.action}</span>
            <span className="u-text2">{l.resource} {l.resource_name||''}</span>
            <span className="u-text3">{l.user_name||''}</span>
          </div>
        ))
      }
      </div>
    </div>
  )
}

function APIKeysTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
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
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_api_key')}</Button>
      </div>
      {newKey && (
        <div style={{ background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)', borderRadius:'var(--radius-md)', padding:'14px 18px', marginBottom:20 }}>
          <div style={{ fontWeight:500, color:'var(--success)', marginBottom:6 }}>{traducir('enterprise.copiala_ahora_no_se_mostrara_de_nuevo')}</div>
          <code style={{ fontSize: "var(--text-base)", background:'var(--surface-1)', padding:'8px 12px', borderRadius:'var(--radius-sm)', display:'block', wordBreak:'break-all' }}>{newKey.key}</code>
          <button onClick={() => setNewKey(null)} style={{ marginTop:8, background:'transparent', border:'none', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>Cerrar</button>
        </div>
      )}
      {keys.length === 0 ? <EmptyState icon="🗝" title={traducir('enterprise.sin_api_keys')} description="Genera una clave para integraciones externas" /> : (
        <div style={{ ...card, overflowX:'auto' }}>
          {keys.map(k => (
            <div key={k.id} style={{ display:'grid', gridTemplateColumns:'1fr 80px 130px 110px auto', gap:12, minWidth:620, padding:'12px 18px', borderBottom:'.5px solid var(--surface-4)', alignItems:'center', fontSize: "var(--text-sm)" }}>
              <div>
                <div style={{ fontWeight:500 }}>{k.name}</div>
                <code className="u-text2-xs">{k.key_prefix}...</code>
              </div>
              <span className="u-text2">{(k.scopes||[]).join(', ')}</span>
              <span className="u-text2">{k.requests_today||0}/{k.rate_limit_per_day} hoy</span>
              <span className="u-text3">{k.last_used_at || 'Nunca usado'}</span>
              <button onClick={() => { openConfirmGlobal({ message: 'Revocar clave?', onConfirm: () => revoke(k.id), danger: true }) }} style={{ background:'transparent', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:'var(--radius-sm)', padding:'3px 10px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-xs)", fontFamily:'inherit' }}>Revocar</button>
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_api_key_2')} onClose={() => setShowCreate(false)} width={420}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Nombre</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} style={fs} placeholder={traducir('enterprise.nombre_de_la_clave')} /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{traducir('enterprise.limite_por_hora')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={form.rate_limit_per_hour} onChange={e => setForm(f => ({...f, rate_limit_per_hour:+e.target.value}))} style={fs} /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => create(form)} disabled={!form.name}>Crear</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function SSOTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); setShowCreate(false); setEditId(null); setForm(VACIO); toast.success('SSO guardado') },
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sso-cfg'] }); toast.success('SSO eliminado') },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const testSSO = async (id: string) => {
    try {
      const res = await enterpriseApi.ssoTest(id)
      setTestResult(res.data)
    } catch (e: unknown) {
      const _raw2 = (e as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
      const _msg2 = Array.isArray(_raw2) ? _raw2.map((d: ValidationDetail) => d.msg).join(', ') : ((_raw2 as string) || 'Error de conexión')
      setTestResult({ valid: false, issues: [_msg2] })
    }
  }

  const PROVIDER_INFO: Record<string, { label:string; icon:string; discovery:string }> = {
    azure_ad: { label: 'Azure AD / Entra ID', icon: '🔵', discovery: 'https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration' },
    okta:     { label: 'Okta',                icon: '🟠', discovery: 'https://{your-domain}.okta.com/.well-known/openid-configuration' },
    google:   { label: 'Google Workspace',    icon: '🔴', discovery: 'https://accounts.google.com/.well-known/openid-configuration' },
    oidc:     { label: 'OIDC Genérico',       icon: '🔑', discovery: 'https://your-idp.com/.well-known/openid-configuration' },
  }

  const cardStyle: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 18px', marginBottom: 10 }
  const inputStyle: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 11px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
  const labelStyle: CSSProperties = { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <div className="u-min0">
          <div className="u-md-700">Single Sign-On (SSO)</div>
          <div className="u-text2-sm">Configura Azure AD / Entra ID, Okta, Google o cualquier proveedor OpenID Connect</div>
        </div>
        <button onClick={() => { setShowCreate(s => !s); setEditId(null); setForm(VACIO) }} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
          {showCreate ? '✕ Cancelar' : '+ Añadir proveedor'}
        </button>
      </div>

      {/* Información de integración */}
      <div style={{ ...cardStyle, background: 'var(--purple-bg)', borderColor: 'var(--purple-bg)', marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--purple)', marginBottom: 8 }}>{traducir('enterprise.como_integrar_sso')}</div>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', lineHeight: 1.7 }}>
          {traducir('enterprise.1_registra_contecflow_como_aplicacion_en_tu')}<br/>
          {traducir('enterprise.2_configura_el')} <strong className="u-text1">Redirect URI</strong>: <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4 }}>{window.location.origin}/login</code><br/>
          {traducir('enterprise.3_copia_el_client_id_y_client')}<br/>
          {traducir('enterprise.4_anade_el_boton_de_login_sso')} <strong className="u-text1">Ajustes {'>'} Seguridad</strong>.
        </div>
      </div>

      {/* Formulario de creación */}
      {showCreate && (
        <div style={{ ...cardStyle, borderColor: 'var(--accent-glow)' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)', marginBottom: 14 }}>{editId ? traducir('enterprise.sso_editar') : traducir('enterprise.nuevo_proveedor_sso')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Proveedor</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.provider} disabled={!!editId} onChange={e => {
                const info: { label?: string; icon?: string; discovery?: string } = PROVIDER_INFO[e.target.value] || {}
                setForm(f => ({ ...f, provider: e.target.value, oidc_discovery_url: info.discovery || '' }))
              }} style={inputStyle}>
                {Object.entries(PROVIDER_INFO).map(([k, v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={labelStyle}>{traducir('enterprise.nombre_para_mostrar_en_login')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inputStyle} placeholder={PROVIDER_INFO[form.provider]?.label} />
            </div>
            <div>
              <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={labelStyle}>Client ID *</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.oidc_client_id} onChange={e => setForm(f=>({...f,oidc_client_id:e.target.value}))} style={inputStyle} placeholder={traducir('enterprise.client_id_del_proveedor')} />
            </div>
            <div>
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={labelStyle}>Client Secret *</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="password" value={form.oidc_client_secret} onChange={e => setForm(f=>({...f,oidc_client_secret:e.target.value}))} style={inputStyle} />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={labelStyle}>Discovery URL (OpenID Connect)</label>
              <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.oidc_discovery_url} onChange={e => setForm(f=>({...f,oidc_discovery_url:e.target.value}))} style={inputStyle} placeholder={PROVIDER_INFO[form.provider]?.discovery} />
            </div>
            <div>
              <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={labelStyle}>{traducir('enterprise.sso_scopes')}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.oidc_scopes} onChange={e => setForm(f=>({...f,oidc_scopes:e.target.value}))} style={inputStyle} />
            </div>
            <div>
              <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={labelStyle}>{traducir('enterprise.sso_dominios')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.allowed_domains} onChange={e => setForm(f=>({...f,allowed_domains:e.target.value}))} style={inputStyle} placeholder="empresa.com, filial.es" />
            </div>
            <div>
              <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={labelStyle}>{traducir('enterprise.sso_rol_defecto')}</label>
              <select id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.default_role} onChange={e => setForm(f=>({...f,default_role:e.target.value}))} style={inputStyle}>
                {['employee','team_lead','pm','hr','admin','subcontractor'].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={labelStyle}>{traducir('enterprise.sso_claim_grupos')}</label>
              <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.groups_claim} onChange={e => setForm(f=>({...f,groups_claim:e.target.value}))} style={inputStyle} />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={labelStyle}>{traducir('enterprise.sso_mapeo')}</label>
              <textarea id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} rows={3} value={form.role_mapping_text} onChange={e => setForm(f=>({...f,role_mapping_text:e.target.value}))} style={{ ...inputStyle, fontFamily: 'var(--font-mono)' }} placeholder={'Contecflow-Admins=admin\nContecflow-PM=pm'} />
            </div>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-sm)' }}>
              <input type="checkbox" aria-label={traducir('enterprise.sso_autocrear')} checked={form.auto_create_users} onChange={e => setForm(f=>({...f,auto_create_users:e.target.checked}))} />
              {traducir('enterprise.sso_autocrear')}
            </label>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-sm)' }}>
              <input type="checkbox" aria-label={traducir('enterprise.sso_activo')} checked={form.is_active} onChange={e => setForm(f=>({...f,is_active:e.target.checked}))} />
              {traducir('enterprise.sso_activo')}
            </label>
          </div>
          <div className="u-actions-8">
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
            <button onClick={() => create(aPayload(form))} disabled={creating || !form.oidc_client_id} style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-border-strong)', borderRadius: 7, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
              {creating ? '⟳ Guardando...' : '✓ Guardar SSO'}
            </button>
          </div>
        </div>
      )}

      {/* Lista de proveedores */}
      {configs.length === 0 && !showCreate ? (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: "var(--text-4xl)", marginBottom: 10 }}>🔑</div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 4 }}>{traducir('enterprise.sin_sso_configurado')}</div>
          <div className="u-sm">{traducir('enterprise.anade_azure_ad_okta_o_google_para')}</div>
        </div>
      ) : (
        configs.map(c => {
          const info = PROVIDER_INFO[c.provider] || { icon: '🔑', label: c.provider }
          return (
            <div key={c.id} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', minWidth: 0 }}>
                  <span style={{ fontSize: "var(--text-2xl)" }}>{info.icon}</span>
                  <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                    <div className="u-md-700">{c.name || info.label}</div>
                    <div className="u-text2-xs">
                      Client ID: {c.oidc_client_id?.slice(0,8)}...
                      {c.is_active
                        ? <span style={{ marginLeft: 8, color: 'var(--success)' }}>● Activo</span>
                        : <span style={{ marginLeft: 8, color: 'var(--danger)' }}>● Inactivo</span>}
                    </div>
                    {c.oidc_discovery_url && (
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>{c.oidc_discovery_url.slice(0, 60)}...</div>
                    )}
                  </div>
                </div>
                <div className="u-wrap-6">
                  <button onClick={() => toggle(c)} aria-pressed={!!c.is_active} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: c.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                    {c.is_active ? traducir('enterprise.sso_desactivar') : traducir('enterprise.sso_activar')}
                  </button>
                  <button onClick={() => editar(c)} aria-label={`${traducir('enterprise.sso_editar')} ${c.name || c.provider}`} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                  <button onClick={() => testSSO(c.id)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                    🔧 Verificar config
                  </button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${c.name || c.provider}?`, onConfirm: () => del(c.id), danger: true }) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* Resultado del test */}
      {testResult && (
        <div style={{ ...cardStyle, borderColor: testResult.valid ? 'var(--success-border)' : 'var(--danger-border)', background: testResult.valid ? 'var(--success-bg)' : 'var(--danger-bg)' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: testResult.valid ? 'var(--success)' : 'var(--danger)', marginBottom: 8 }}>
            {testResult.valid ? '✅ Configuración válida' : '✗ Configuración incompleta'}
          </div>
          {(testResult.issues?.length ?? 0) > 0 && (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {testResult.issues!.map((i: string, idx: number) => <li key={idx} style={{ fontSize: "var(--text-sm)", color: 'var(--danger)', marginBottom: 4 }}>{i}</li>)}
            </ul>
          )}
          <button onClick={() => setTestResult(null)} style={{ marginTop: 8, background: 'transparent', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>Cerrar</button>
        </div>
      )}
    </div>
  )
}


// ── Componente principal ───────────────────────────────────────────────────────
export default function EnterprisePage(): JSX.Element {
  const _t = useAppT()
  // `?tab=<id>` abre esa pestaña (la lista de puesta en marcha enlaza a SSO).
  const [tab, setTab] = useState(() => new URLSearchParams(window.location.search).get('tab') || 'webhooks')

  const TABS = [
    { id: 'webhooks',     label: 'Webhooks' },
    { id: 'gdpr',         label: 'GDPR' },
    { id: 'email',        label: 'Email' },
    { id: 'integrations', label: 'Integraciones' },
    { id: 'sso',          label: 'SSO' },
    { id: 'audit',        label: 'Auditoría' },
    { id: 'apikeys',      label: 'API Keys' },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Building2 size={18} />}
        title={_t('enterprise.title')}
        subtitle={_t('enterprise.subtitle')}
      showListExport={false}
      />

      {/* Tabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 24, borderBottom: '1px solid var(--surface-4)', paddingBottom: 0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '7px 16px', border: 'none', cursor: 'pointer',
            background: 'transparent', fontFamily: 'inherit', fontSize: "var(--text-sm)",
            borderRadius: '8px 8px 0 0',
            fontWeight: 600,
            color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
            borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            marginBottom: -1, transition: 'all 0.15s',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Contenido */}
      {tab === 'webhooks'     && <WebhooksTab />}
      {tab === 'gdpr'         && <GDPRTab />}
      {tab === 'email'        && <EmailTab />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'sso'          && <SSOTab />}
      {tab === 'audit'        && <AuditTab />}
      {tab === 'apikeys'      && <APIKeysTab />}
    </PageShell>
  )
}
