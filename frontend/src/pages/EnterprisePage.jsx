/**
 * EnterprisePage v14 — Webhooks, GDPR, Email, Integraciones, SSO, Audit, API Keys
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import _PageHeader from '../components/layout/PageHeader'

import { useAppT } from '../i18n/AppLangContext'
import { INTEGRATION_CATALOG } from '../constants/api'

const fs = { width:'100%', background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'9px 12px', color:'var(--color-text-primary)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--color-text-secondary)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--color-background-primary)', border:'.5px solid var(--color-border-tertiary)', borderRadius:12 }

function WebhooksTab() {
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [showLogs, setShowLogs] = useState(null)
  const [form, setForm] = useState({ name:'', slug:'', workflow_id:'' })

  const { data: triggers = [], isLoading } = useQuery({ queryKey:['wh-triggers'], queryFn:() => api.get('/webhooks').then(r => r.data) })
  const { data: workflows = [] } = useQuery({ queryKey:['workflows-ent'], queryFn:() => api.get('/automation-workflows').then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['wh-logs', showLogs], queryFn:() => api.get(`/webhooks/${showLogs}/logs`).then(r => r.data), enabled:!!showLogs })

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/webhooks', d),
    onSuccess: () => { qc.invalidateQueries(['wh-triggers']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/webhooks/${id}`),
    onSuccess: () => qc.invalidateQueries(['wh-triggers']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ background:'var(--color-background-info)', border:'.5px solid var(--color-border-info)', borderRadius:10, padding:'12px 16px', marginBottom:20, fontSize:13, color:'var(--color-text-info)' }}>
        Los webhooks entrantes permiten que sistemas externos disparen automatizaciones en Clarive mediante un simple HTTP POST a la URL configurada.
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nuevo webhook</Button>
      </div>
      {isLoading ? <Spinner /> : triggers.length === 0 ? (
        <EmptyState icon="🔗" title="Sin webhooks" description="Crea el primer webhook entrante para automatizaciones" />
      ) : triggers.map(t => (
        <div key={t.id} style={{ ...card, padding:'14px 18px', marginBottom:10 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div>
              <div style={{ fontSize:13, fontWeight:500, marginBottom:4 }}>{t.name}</div>
              <code style={{ fontSize:11, background:'var(--color-background-secondary)', padding:'2px 8px', borderRadius:4, color:'var(--color-text-secondary)' }}>POST /api/v1{t.endpoint}</code>
              <span style={{ marginLeft:12, fontSize:11, color:'var(--color-text-secondary)' }}>{t.fire_count} disparos</span>
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <button onClick={() => setShowLogs(showLogs === t.id ? null : t.id)} style={{ background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:6, padding:'4px 10px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
                {showLogs === t.id ? 'Ocultar' : 'Logs'}
              </button>
              <button onClick={() => { openConfirmGlobal({ message: 'Eliminar?', onConfirm: () => del(t.id), danger: true }) }} style={{ background:'transparent', border:'.5px solid var(--color-border-danger)', borderRadius:6, padding:'4px 8px', color:'var(--color-text-danger)', cursor:'pointer', fontSize:12 }}>🗑</button>
            </div>
          </div>
          {showLogs === t.id && (
            <div style={{ marginTop:10, borderTop:'.5px solid var(--color-border-tertiary)', paddingTop:8 }}>
              {logs.length === 0 ? <div style={{ fontSize:12, color:'var(--color-text-tertiary)' }}>Sin llamadas aún</div> :
                logs.slice(0,5).map(l => (
                  <div key={l.id} style={{ fontSize:11, padding:'3px 0', borderBottom:'.5px solid var(--color-border-tertiary)', display:'flex', gap:10 }}>
                    <span style={{ color: l.status === 'ok' ? 'var(--color-text-success)' : 'var(--color-text-danger)' }}>{l.status}</span>
                    <span style={{ color:'var(--color-text-secondary)' }}>{l.received_at}</span>
                    <span style={{ color:'var(--color-text-tertiary)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>{l.payload_preview}</span>
                  </div>
                ))
              }
            </div>
          )}
        </div>
      ))}
      {showCreate && (
        <Modal open title="Nuevo webhook" onClose={() => setShowCreate(false)} width={480}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Nombre</label><input value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Slug (URL)</label><input value={form.slug} onChange={e => setForm(f => ({...f, slug:e.target.value.toLowerCase().replace(/\s+/g,'-')}))} style={fs} placeholder="mi-webhook" aria-label="Slug del webhook" /></div>
            <div><label style={ls}>Workflow</label>
              <select value={form.workflow_id} onChange={e => setForm(f => ({...f, workflow_id:e.target.value}))} style={fs}>
                <option value="">Sin workflow</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <div style={{ background:'var(--color-background-secondary)', borderRadius:8, padding:'8px 12px', fontSize:12, color:'var(--color-text-secondary)' }}>
              URL: <code>POST /api/v1/webhooks/fire/{form.slug || 'tu-slug'}</code>
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ request_type:'erasure', subject_user_id:'', subject_email:'', notes:'' })

  const { data: requests = [], isLoading } = useQuery({ queryKey:['gdpr'], queryFn:() => api.get('/gdpr/requests').then(r => r.data) })
  const { data: usersRaw = [] } = useQuery({ queryKey:['users'], queryFn:() => usersApi.list().then(r => r.data) })
  const users = Array.isArray(usersRaw) ? usersRaw : []

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/gdpr/requests', d),
    onSuccess: () => { qc.invalidateQueries(['gdpr']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: process } = useMutation({
    mutationFn: id => api.post(`/gdpr/requests/${id}/process`),
    onSuccess: () => qc.invalidateQueries(['gdpr']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const TYPE_LABELS = { erasure:'Derecho al olvido', portability:'Portabilidad', access:'Acceso', rectification:'Rectificación' }
  const STATUS_COLORS = { pending:'var(--color-text-warning)', processing:'var(--color-text-info)', completed:'var(--color-text-success)', rejected:'var(--color-text-danger)' }

  return (
    <div>
      <div style={{ background:'var(--color-background-warning)', border:'.5px solid var(--color-border-warning)', borderRadius:10, padding:'12px 16px', marginBottom:20, fontSize:13, color:'var(--color-text-warning)' }}>
        Gestión de solicitudes RGPD. Plazo máximo de respuesta: 30 días (Art. 12 RGPD).
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva solicitud</Button>
      </div>
      {isLoading ? <Spinner /> : requests.length === 0 ? (
        <EmptyState icon="🔒" title="Sin solicitudes RGPD" description="No hay solicitudes de privacidad registradas" />
      ) : (
        <div style={{ ...card, overflow:'hidden' }}>
          {requests.map(r => (
            <div key={r.id} style={{ display:'grid', gridTemplateColumns:'150px 120px 1fr 100px auto', gap:12, padding:'12px 18px', borderBottom:'.5px solid var(--color-border-tertiary)', alignItems:'center' }}>
              <span style={{ fontSize:12, fontWeight:500 }}>{TYPE_LABELS[r.request_type] || r.request_type}</span>
              <span style={{ fontSize:12, fontWeight:500, color:STATUS_COLORS[r.status] || 'var(--color-text-secondary)' }}>{r.status}</span>
              <div>
                <div style={{ fontSize:13, fontWeight:500 }}>{r.subject_name || r.subject_email || 'Sin identificar'}</div>
                {r.notes && <div style={{ fontSize:11, color:'var(--color-text-secondary)' }}>{r.notes}</div>}
              </div>
              <span style={{ fontSize:12, color:'var(--color-text-secondary)' }}>{r.deadline}</span>
              {r.status === 'pending' && <Button onClick={() => process(r.id)}>Procesar</Button>}
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title="Nueva solicitud RGPD" onClose={() => setShowCreate(false)} width={480}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Tipo</label>
              <select value={form.request_type} onChange={e => setForm(f => ({...f, request_type:e.target.value}))} style={fs}>
                <option value="erasure">Derecho al olvido (Art. 17)</option>
                <option value="portability">Portabilidad (Art. 20)</option>
                <option value="access">Acceso (Art. 15)</option>
                <option value="rectification">Rectificación (Art. 16)</option>
              </select>
            </div>
            <div><label style={ls}>Usuario</label>
              <select value={form.subject_user_id} onChange={e => setForm(f => ({...f, subject_user_id:e.target.value}))} style={fs}>
                <option value="">Seleccionar...</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.full_name} — {u.email}</option>)}
              </select>
            </div>
            <div><label style={ls}>Email (si ya no existe)</label>
              <input value={form.subject_email} onChange={e => setForm(f => ({...f, subject_email:e.target.value}))} style={fs} />
            </div>
            <div><label style={ls}>Notas</label>
              <textarea value={form.notes} onChange={e => setForm(f => ({...f, notes:e.target.value}))} rows={3} style={{...fs, resize:'vertical'}} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [showSend, setShowSend] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [sendForm, setSendForm] = useState({ to:'', subject:'', body_html:'', template_id:'' })
  const [newTpl, setNewTpl] = useState({ name:'', subject:'', body_html:'', category:'automation' })

  const { data: catalog } = useQuery({ queryKey:['email-tpl'], queryFn:() => api.get('/email/templates').then(r => r.data) })
  const { data: logs = [] } = useQuery({ queryKey:['email-logs'], queryFn:() => api.get('/email/logs').then(r => r.data) })

  const { mutate: send, isPending:sending } = useMutation({
    mutationFn: d => api.post('/email/send', {...d, to:[d.to]}),
    onSuccess: () => { qc.invalidateQueries(['email-logs']); setShowSend(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: createTpl } = useMutation({
    mutationFn: d => api.post('/email/templates', d),
    onSuccess: () => { qc.invalidateQueries(['email-tpl']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const allTpl = [...(catalog?.system || []), ...(catalog?.custom || [])]

  return (
    <div>
      <div style={{ display:'flex', gap:10, justifyContent:'flex-end', marginBottom:20 }}>
        <button onClick={() => setShowCreate(true)} style={{ background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'8px 14px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
          + Plantilla
        </button>
        <Button onClick={() => setShowSend(true)}>✉ Enviar email</Button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
        <div>
          <div style={{ fontSize:13, fontWeight:500, marginBottom:12 }}>Plantillas ({allTpl.length})</div>
          {allTpl.map(t => (
            <div key={t.id} style={{ ...card, padding:'12px 14px', marginBottom:8 }}>
              <div style={{ display:'flex', gap:6, marginBottom:4 }}>
                <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-info)', color:'var(--color-text-info)' }}>{t.category}</span>
                {t.is_system && <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-secondary)', color:'var(--color-text-tertiary)' }}>sistema</span>}
              </div>
              <div style={{ fontSize:13, fontWeight:500 }}>{t.name}</div>
              <div style={{ fontSize:11, color:'var(--color-text-secondary)', marginTop:2, fontFamily:'monospace' }}>{t.subject}</div>
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontSize:13, fontWeight:500, marginBottom:12 }}>Historial de envíos</div>
          {logs.length === 0 ? <EmptyState icon="✉" title="Sin historial de envios" description="Todavia no se han enviado correos desde este modulo" /> : (
            <div style={{ ...card, overflow:'hidden' }}>
              {logs.slice(0,15).map(l => (
                <div key={l.id} style={{ display:'grid', gridTemplateColumns:'50px 1fr auto', gap:8, padding:'8px 14px', borderBottom:'.5px solid var(--color-border-tertiary)', fontSize:12 }}>
                  <span style={{ fontWeight:500, color: l.status === 'sent' ? 'var(--color-text-success)' : 'var(--color-text-danger)' }}>{l.status}</span>
                  <div>
                    <div style={{ fontWeight:500 }}>{l.to}</div>
                    <div style={{ fontSize:11, color:'var(--color-text-secondary)' }}>{l.subject}</div>
                  </div>
                  <span style={{ fontSize:11, color:'var(--color-text-tertiary)', whiteSpace:'nowrap' }}>{(l.sent_at || l.created_at || '').slice(0,16)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {showSend && (
        <Modal open title="Enviar email" onClose={() => setShowSend(false)} width={500}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Para</label><input value={sendForm.to} onChange={e => setSendForm(f => ({...f, to:e.target.value}))} style={fs} placeholder="destinatario@empresa.com" aria-label="Destinatario" /></div>
            <div><label style={ls}>Plantilla</label>
              <select value={sendForm.template_id} onChange={e => setSendForm(f => ({...f, template_id:e.target.value}))} style={fs}>
                <option value="">Sin plantilla</option>
                {allTpl.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            {!sendForm.template_id && <>
              <div><label style={ls}>Asunto</label><input value={sendForm.subject} onChange={e => setSendForm(f => ({...f, subject:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>HTML</label><textarea value={sendForm.body_html} onChange={e => setSendForm(f => ({...f, body_html:e.target.value}))} rows={4} style={{...fs, resize:'vertical'}} /></div>
            </>}
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowSend(false)}>Cancelar</Button>
              <Button onClick={() => send(sendForm)} disabled={sending || !sendForm.to}>{sending ? 'Enviando...' : 'Enviar'}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showCreate && (
        <Modal open title="Nueva plantilla de email" onClose={() => setShowCreate(false)} width={560}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Nombre</label><input value={newTpl.name} onChange={e => setNewTpl(f => ({...f, name:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Asunto (usa {'{{variable}}'})</label><input value={newTpl.subject} onChange={e => setNewTpl(f => ({...f, subject:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Categoría</label>
              <select value={newTpl.category} onChange={e => setNewTpl(f => ({...f, category:e.target.value}))} style={fs}>
                {['automation','alert','report','invoice'].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div><label style={ls}>HTML del cuerpo</label><textarea value={newTpl.body_html} onChange={e => setNewTpl(f => ({...f, body_html:e.target.value}))} rows={5} style={{...fs, resize:'vertical'}} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [configuring, setConfiguring] = useState(null)
  const [testing, setTesting]         = useState(null)
  const [testResult, setTestResult]   = useState(null)
  const [form, setForm] = useState({ name:'', access_token:'', config:{} })

  const { data: integrations = [] } = useQuery({
    queryKey: ['integrations'],
    queryFn: () => api.get('/oauth-integrations').then(r => r.data),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/oauth-integrations', d),
    onSuccess: () => { qc.invalidateQueries(['integrations']); setConfiguring(null); toast.success('Integración guardada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/oauth-integrations/${id}`),
    onSuccess: () => { qc.invalidateQueries(['integrations']); toast.success('Integración eliminada') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const { mutate: sync } = useMutation({
    mutationFn: id => api.post(`/oauth-integrations/${id}/sync`, {}),
    onSuccess: () => { qc.invalidateQueries(['integrations']); toast.success('Sincronización completada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const testIntegration = async (integ) => {
    setTesting(integ.id)
    setTestResult(null)
    try {
      const cfg = typeof integ.config === 'string' ? JSON.parse(integ.config || '{}') : (integ.config || {})
      if (integ.integration_type === 'slack') {
        const res = await api.post('/integrations-hub/slack/test', { webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'teams') {
        const res = await api.post('/integrations-hub/teams/test', { webhook_url: cfg.webhook_url || '' })
        setTestResult({ ok: true, message: res.data.message })
      } else if (integ.integration_type === 'jira') {
        const res = await api.post('/integrations-hub/jira/test', {
          base_url: cfg.base_url || '', email: cfg.email || '', api_token: cfg.api_token || ''
        })
        setTestResult({ ok: true, message: `Conectado: ${res.data.total} proyectos Jira disponibles` })
      } else {
        const res = await api.post(`/oauth-integrations/${integ.id}/sync`, {})
        setTestResult({ ok: true, message: `Sincronizados: ${res.data.synced} elementos` })
      }
    } catch (e) {
      const _raw1 = e?.response?.data?.detail
      setTestResult({ ok: false, message: Array.isArray(_raw1) ? _raw1.map(d => d.msg).join(', ') : (_raw1 || 'Error de conexión') })
    } finally {
      setTesting(null)
    }
  }


  const CATALOG = INTEGRATION_CATALOG

  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }
  const is = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 7, padding: '7px 11px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Integraciones nativas</div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>Conecta Clarive con tus herramientas de trabajo</div>

      {/* Integraciones activas */}
      {integrations.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Configuradas</div>
          {integrations.map(integ => {
            const cat = CATALOG.find(c => c.type === integ.integration_type) || { icon: '🔗', label: integ.integration_type }
            return (
              <div key={integ.id} style={{ background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 10, padding: '12px 16px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ fontSize: 22 }}>{cat.icon}</span>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{integ.name || cat.label}</div>
                    <div style={{ fontSize: 11, color: integ.is_active ? 'var(--success)' : 'var(--danger)' }}>
                      {integ.is_active ? '● Activa' : '● Inactiva'}
                      {integ.last_sync_at && ` · Último sync: ${integ.last_sync_at.slice(0,10)}`}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => testIntegration(integ)} disabled={testing === integ.id}
                    style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                    {testing === integ.id ? '⟳' : '🔧 Probar'}
                  </button>
                  <button onClick={() => sync(integ.id)}
                    style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                    ↺ Sync
                  </button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${integ.name}?`, onConfirm: () => del(integ.id), danger: true }) }}
                    style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                </div>
              </div>
            )
          })}

          {/* Test result */}
          {testResult && (
            <div style={{ background: testResult.ok ? 'var(--success-bg)' : 'var(--danger-bg)', border: `1px solid ${testResult.ok ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8, padding: '8px 14px', marginTop: 8, fontSize: 12, color: testResult.ok ? 'var(--success)' : 'var(--danger)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {testResult.ok ? '✅' : '✗'} {testResult.message}
              <button onClick={() => setTestResult(null)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✕</button>
            </div>
          )}
        </div>
      )}

      {/* Catálogo para añadir */}
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
        {integrations.length === 0 ? 'Disponibles' : 'Añadir otra'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
        {CATALOG.map(cat => (
          <button key={cat.type} onClick={() => { setConfiguring(cat); setForm({ name: cat.label, integration_type: cat.type, config: {} }) }}
            type="button"
            style={{ background: 'var(--surface-1)', border: `1px solid ${configuring?.type === cat.type ? 'var(--accent-glow)' : 'var(--surface-4)'}`, borderRadius: 10, padding: '14px 16px', cursor: 'pointer', transition: 'border-color 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = configuring?.type === cat.type ? 'var(--accent-glow)' : 'var(--surface-4)'}
          >
            <div style={{ fontSize: 24, marginBottom: 6 }}>{cat.icon}</div>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 3 }}>{cat.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{cat.desc}</div>
          </button>
        ))}
      </div>

      {/* Formulario de configuración */}
      {configuring && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid #00d4ff30', borderRadius: 12, padding: '18px 20px', marginTop: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent)', marginBottom: 14 }}>
            {configuring.icon} Configurar {configuring.label}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10, marginBottom: 14 }}>
            <div>
              <label style={ls}>Nombre de la integración</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={is} />
            </div>
            {configuring.fields?.map(field => (
              <div key={field.key}>
                <label style={ls}>{field.label}</label>
                <input
                  type={field.type || 'text'}
                  value={form.config?.[field.key] || ''}
                  onChange={e => setForm(f => ({ ...f, config: { ...f.config, [field.key]: e.target.value } }))}
                  style={is}
                  placeholder={field.placeholder || ''}
                />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setConfiguring(null)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <button onClick={() => create({ ...form, integration_type: configuring.type, config: JSON.stringify(form.config) })}
              disabled={isPending}
              style={{ background: 'var(--accent-glow)', border: '1px solid #00d4ff40', borderRadius: 8, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600 }}>
              {isPending ? '⟳ Guardando...' : '✓ Guardar integración'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


function AuditTab() {
  const { data: logs = [] } = useQuery({
    queryKey: ['audit-ent'],
    queryFn: () => api.get('/enterprise/audit-log?page=1&page_size=50').then(r => r.data?.logs || []).catch(() => []),
  })
  const { data: resetRequestLogs = [] } = useQuery({
    queryKey: ['audit-ent-reset-request'],
    queryFn: () => api.get('/enterprise/audit-log?page=1&page_size=20&action=PASSWORD_RESET_REQUEST').then(r => r.data?.logs || []).catch(() => []),
  })
  const { data: resetCompleteLogs = [] } = useQuery({
    queryKey: ['audit-ent-reset-complete'],
    queryFn: () => api.get('/enterprise/audit-log?page=1&page_size=20&action=PASSWORD_RESET_COMPLETE').then(r => r.data?.logs || []).catch(() => []),
  })

  const passwordResetLogs = [...resetCompleteLogs, ...resetRequestLogs]
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 20)

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div style={{ ...card, padding: '12px 14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
          <div style={{ background: 'var(--color-background-secondary)', border: '.5px solid var(--color-border-tertiary)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Total eventos</div>
            <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>{logs.length}</div>
          </div>
          <div style={{ background: 'var(--color-background-secondary)', border: '.5px solid var(--color-border-tertiary)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Reset solicitados</div>
            <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>{resetRequestLogs.length}</div>
          </div>
          <div style={{ background: 'var(--color-background-secondary)', border: '.5px solid var(--color-border-tertiary)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Reset completados</div>
            <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>{resetCompleteLogs.length}</div>
          </div>
        </div>
      </div>

      <div style={{ ...card, overflow:'hidden' }}>
        <div style={{ padding: '10px 16px', fontSize: 12, fontWeight: 700, color: 'var(--color-text-secondary)', borderBottom: '.5px solid var(--color-border-tertiary)' }}>
          Eventos de recuperacion de contrasena
        </div>
        {passwordResetLogs.length === 0 ? <div style={{ padding:18, textAlign:'center', color:'var(--color-text-tertiary)', fontSize: 12 }}>Sin eventos de recuperacion</div> :
          passwordResetLogs.map((l, i) => (
            <div key={l.id||i} style={{ display:'grid', gridTemplateColumns:'140px 220px 1fr 140px', gap:12, padding:'9px 16px', borderBottom:'.5px solid var(--color-border-tertiary)', fontSize:12 }}>
              <span style={{ color:'var(--color-text-secondary)', fontFamily:'monospace' }}>{(l.created_at||'').slice(0,16)}</span>
              <span style={{ fontWeight:600, color: l.action === 'PASSWORD_RESET_COMPLETE' ? 'var(--color-text-success)' : 'var(--color-text-info)' }}>{l.action}</span>
              <span style={{ color:'var(--color-text-secondary)' }}>{l.resource_name || l.resource || '-'}</span>
              <span style={{ color:'var(--color-text-tertiary)' }}>{l.user_name||''}</span>
            </div>
          ))
        }
      </div>

      <div style={{ ...card, overflow:'hidden' }}>
        <div style={{ padding: '10px 16px', fontSize: 12, fontWeight: 700, color: 'var(--color-text-secondary)', borderBottom: '.5px solid var(--color-border-tertiary)' }}>
          Audit log general (ultimos 30)
        </div>
      {logs.length === 0 ? <div style={{ padding:18, textAlign:'center', color:'var(--color-text-tertiary)', fontSize: 12 }}>Sin entradas en el audit log</div> :
        logs.slice(0,30).map((l, i) => (
          <div key={l.id||i} style={{ display:'grid', gridTemplateColumns:'140px 220px 1fr 140px', gap:12, padding:'9px 16px', borderBottom:'.5px solid var(--color-border-tertiary)', fontSize:12 }}>
            <span style={{ color:'var(--color-text-secondary)', fontFamily:'monospace' }}>{(l.created_at||'').slice(0,16)}</span>
            <span style={{ fontWeight:500 }}>{l.action}</span>
            <span style={{ color:'var(--color-text-secondary)' }}>{l.resource} {l.resource_name||''}</span>
            <span style={{ color:'var(--color-text-tertiary)' }}>{l.user_name||''}</span>
          </div>
        ))
      }
      </div>
    </div>
  )
}

function APIKeysTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [newKey, setNewKey] = useState(null)
  const [form, setForm] = useState({ name:'', rate_limit_per_hour:1000 })

  const { data: keys = [] } = useQuery({ queryKey:['api-keys'], queryFn:() => api.get('/api-keys').then(r => r.data) })
  const { mutate: create } = useMutation({
    mutationFn: d => api.post('/api-keys', { ...d, scopes:['read'] }).then(r => r.data),
    onSuccess: data => { qc.invalidateQueries(['api-keys']); setNewKey(data); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: revoke } = useMutation({
    mutationFn: id => api.delete(`/api-keys/${id}`),
    onSuccess: () => qc.invalidateQueries(['api-keys']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva API key</Button>
      </div>
      {newKey && (
        <div style={{ background:'var(--color-background-success)', border:'.5px solid var(--color-border-success)', borderRadius:10, padding:'14px 18px', marginBottom:20 }}>
          <div style={{ fontWeight:500, color:'var(--color-text-success)', marginBottom:6 }}>Cópiala ahora — no se mostrará de nuevo</div>
          <code style={{ fontSize:13, background:'var(--color-background-primary)', padding:'8px 12px', borderRadius:6, display:'block', wordBreak:'break-all' }}>{newKey.key}</code>
          <button onClick={() => setNewKey(null)} style={{ marginTop:8, background:'transparent', border:'none', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>Cerrar</button>
        </div>
      )}
      {keys.length === 0 ? <EmptyState icon="🗝" title="Sin API keys" description="Genera una clave para integraciones externas" /> : (
        <div style={{ ...card, overflow:'hidden' }}>
          {keys.map(k => (
            <div key={k.id} style={{ display:'grid', gridTemplateColumns:'1fr 80px 130px 110px auto', gap:12, padding:'12px 18px', borderBottom:'.5px solid var(--color-border-tertiary)', alignItems:'center', fontSize:12 }}>
              <div>
                <div style={{ fontWeight:500 }}>{k.name}</div>
                <code style={{ fontSize:11, color:'var(--color-text-secondary)' }}>{k.key_prefix}...</code>
              </div>
              <span style={{ color:'var(--color-text-secondary)' }}>{(k.scopes||[]).join(', ')}</span>
              <span style={{ color:'var(--color-text-secondary)' }}>{k.requests_today||0}/{k.rate_limit_per_day} hoy</span>
              <span style={{ color:'var(--color-text-tertiary)' }}>{k.last_used_at || 'Nunca usado'}</span>
              <button onClick={() => { openConfirmGlobal({ message: 'Revocar clave?', onConfirm: () => revoke(k.id), danger: true }) }} style={{ background:'transparent', border:'.5px solid var(--color-border-danger)', borderRadius:6, padding:'3px 10px', color:'var(--color-text-danger)', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>Revocar</button>
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title="Nueva API key" onClose={() => setShowCreate(false)} width={420}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Nombre</label><input value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} style={fs} placeholder="Nombre de la clave" aria-label="Nombre de la clave" /></div>
            <div><label style={ls}>Límite por hora</label><input type="number" value={form.rate_limit_per_hour} onChange={e => setForm(f => ({...f, rate_limit_per_hour:+e.target.value}))} style={fs} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [form, setForm] = useState({
    provider: 'azure_ad', name: '',
    oidc_client_id: '', oidc_client_secret: '',
    oidc_discovery_url: '', is_active: true,
  })

  const { data: configs = [], _isLoading } = useQuery({
    queryKey: ['sso-cfg'],
    queryFn: () => api.get('/enterprise/sso').then(r => r.data).catch(() => []),
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => api.post('/enterprise/sso', d),
    onSuccess: () => { qc.invalidateQueries(['sso-cfg']); setShowCreate(false); toast.success('SSO creado') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/enterprise/sso/${id}`),
    onSuccess: () => { qc.invalidateQueries(['sso-cfg']); toast.success('SSO eliminado') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const testSSO = async (id) => {
    try {
      const res = await api.post(`/enterprise/sso/${id}/test`)
      setTestResult(res.data)
    } catch (e) {
      const _raw2 = e?.response?.data?.detail
      const _msg2 = Array.isArray(_raw2) ? _raw2.map(d => d.msg).join(', ') : (_raw2 || 'Error de conexión')
      setTestResult({ valid: false, issues: [_msg2] })
    }
  }

  const PROVIDER_INFO = {
    azure_ad: { label: 'Azure AD / Entra ID', icon: '🔵', discovery: 'https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration' },
    okta:     { label: 'Okta',                icon: '🟠', discovery: 'https://{your-domain}.okta.com/.well-known/openid-configuration' },
    google:   { label: 'Google Workspace',    icon: '🔴', discovery: 'https://accounts.google.com/.well-known/openid-configuration' },
    oidc:     { label: 'OIDC Genérico',       icon: '🔑', discovery: 'https://your-idp.com/.well-known/openid-configuration' },
    saml:     { label: 'SAML 2.0',            icon: '🔐', discovery: '' },
  }

  const cardStyle = { background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 10, padding: '14px 18px', marginBottom: 10 }
  const inputStyle = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 7, padding: '7px 11px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
  const labelStyle = { fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Single Sign-On (SSO)</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Configura Azure AD, Okta, Google o cualquier proveedor OIDC/SAML</div>
        </div>
        <button onClick={() => setShowCreate(s => !s)} style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
          {showCreate ? '✕ Cancelar' : '+ Añadir proveedor'}
        </button>
      </div>

      {/* Información de integración */}
      <div style={{ ...cardStyle, background: 'var(--purple-bg)', borderColor: 'var(--purple-bg)', marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--purple)', marginBottom: 8 }}>📋 Cómo integrar SSO</div>
        <div style={{ fontSize: 11, color: 'var(--text-2)', lineHeight: 1.7 }}>
          1. Registra Clarive como aplicación en tu proveedor (Azure, Okta, Google).<br/>
          2. Configura el <strong style={{ color: 'var(--text-1)' }}>Redirect URI</strong>: <code style={{ background: 'var(--surface-4)', padding: '1px 6px', borderRadius: 4 }}>{window.location.origin}/auth/sso/callback</code><br/>
          3. Copia el Client ID y Client Secret del proveedor y pégalos aquí.<br/>
          4. Añade el botón de login SSO desde <strong style={{ color: 'var(--text-1)' }}>Ajustes {'>'} Seguridad</strong>.
        </div>
      </div>

      {/* Formulario de creación */}
      {showCreate && (
        <div style={{ ...cardStyle, borderColor: 'var(--accent-glow)' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent)', marginBottom: 14 }}>Nuevo proveedor SSO</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>Proveedor</label>
              <select value={form.provider} onChange={e => {
                const info = PROVIDER_INFO[e.target.value] || {}
                setForm(f => ({ ...f, provider: e.target.value, oidc_discovery_url: info.discovery || '' }))
              }} style={inputStyle}>
                {Object.entries(PROVIDER_INFO).map(([k, v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Nombre (para mostrar en login)</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inputStyle} placeholder={PROVIDER_INFO[form.provider]?.label} />
            </div>
            <div>
              <label style={labelStyle}>Client ID *</label>
              <input value={form.oidc_client_id} onChange={e => setForm(f=>({...f,oidc_client_id:e.target.value}))} style={inputStyle} placeholder="Client ID del proveedor" aria-label="Client ID del proveedor" />
            </div>
            <div>
              <label style={labelStyle}>Client Secret *</label>
              <input type="password" value={form.oidc_client_secret} onChange={e => setForm(f=>({...f,oidc_client_secret:e.target.value}))} style={inputStyle} />
            </div>
            <div style={{ gridColumn: '1/-1' }}>
              <label style={labelStyle}>Discovery URL (OpenID Connect)</label>
              <input value={form.oidc_discovery_url} onChange={e => setForm(f=>({...f,oidc_discovery_url:e.target.value}))} style={inputStyle} placeholder={PROVIDER_INFO[form.provider]?.discovery} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 7, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <button onClick={() => create(form)} disabled={creating || !form.oidc_client_id} style={{ background: 'var(--accent-glow)', border: '1px solid #00d4ff40', borderRadius: 7, padding: '6px 14px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600 }}>
              {creating ? '⟳ Guardando...' : '✓ Guardar SSO'}
            </button>
          </div>
        </div>
      )}

      {/* Lista de proveedores */}
      {configs.length === 0 && !showCreate ? (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 36, marginBottom: 10 }}>🔑</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Sin SSO configurado</div>
          <div style={{ fontSize: 12 }}>Añade Azure AD, Okta o Google para que los usuarios puedan acceder con su cuenta corporativa</div>
        </div>
      ) : (
        configs.map(c => {
          const info = PROVIDER_INFO[c.provider] || { icon: '🔑', label: c.provider }
          return (
            <div key={c.id} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ fontSize: 24 }}>{info.icon}</span>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{c.name || info.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                      Client ID: {c.oidc_client_id?.slice(0,8)}...
                      {c.is_active
                        ? <span style={{ marginLeft: 8, color: 'var(--success)' }}>● Activo</span>
                        : <span style={{ marginLeft: 8, color: 'var(--danger)' }}>● Inactivo</span>}
                    </div>
                    {c.oidc_discovery_url && (
                      <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{c.oidc_discovery_url.slice(0, 60)}...</div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => testSSO(c.id)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                    🔧 Verificar config
                  </button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar ${c.name || c.provider}?`, onConfirm: () => del(c.id), danger: true }) }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                </div>
              </div>
            </div>
          )
        })
      )}

      {/* Resultado del test */}
      {testResult && (
        <div style={{ ...cardStyle, borderColor: testResult.valid ? 'var(--success-border)' : 'var(--danger-border)', background: testResult.valid ? 'var(--success-bg)' : 'var(--danger-bg)' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: testResult.valid ? 'var(--success)' : 'var(--danger)', marginBottom: 8 }}>
            {testResult.valid ? '✅ Configuración válida' : '✗ Configuración incompleta'}
          </div>
          {testResult.issues?.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {testResult.issues.map((i, idx) => <li key={idx} style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 4 }}>{i}</li>)}
            </ul>
          )}
          <button onClick={() => setTestResult(null)} style={{ marginTop: 8, background: 'transparent', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>Cerrar</button>
        </div>
      )}
    </div>
  )
}


// ── Componente principal ───────────────────────────────────────────────────────
export default function EnterprisePage() {
  const _t = useAppT()
  const [tab, setTab] = useState('webhooks')

  const TABS = [
    { id: 'webhooks',     label: '🔗 Webhooks' },
    { id: 'gdpr',         label: '🔒 GDPR' },
    { id: 'email',        label: '📧 Email' },
    { id: 'integrations', label: '🔌 Integraciones' },
    { id: 'sso',          label: '🔑 SSO' },
    { id: 'audit',        label: '📋 Auditoría' },
    { id: 'apikeys',      label: '🗝 API Keys' },
  ]

  const card = {
    background: 'var(--surface-2)',
    border: '1px solid #1e2d45',
    borderRadius: 12,
    padding: '20px 24px',
    marginBottom: 16,
  }

  return (
    <div style={{ padding: 32, maxWidth: 1100 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 4px' }}>⚙️ Enterprise</h1>
        <p style={{ fontSize: 13, color: 'var(--text-2)', margin: 0 }}>
          Configuración avanzada: webhooks, integraciones, SSO, GDPR y auditoría
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: '1px solid #1e2d45', paddingBottom: 0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '8px 16px', border: 'none', cursor: 'pointer',
            background: 'transparent', fontFamily: 'inherit', fontSize: 13,
            fontWeight: tab === t.id ? 700 : 400,
            color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
            borderBottom: tab === t.id ? '2px solid #00d4ff' : '2px solid transparent',
            marginBottom: -1, transition: 'all 0.15s',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Contenido */}
      <div style={card}>
        {tab === 'webhooks'     && <WebhooksTab />}
        {tab === 'gdpr'         && <GDPRTab />}
        {tab === 'email'        && <EmailTab />}
        {tab === 'integrations' && <IntegrationsTab />}
        {tab === 'sso'          && <SSOTab />}
        {tab === 'audit'        && <AuditTab />}
        {tab === 'apikeys'      && <APIKeysTab />}
      </div>
    </div>
  )
}
