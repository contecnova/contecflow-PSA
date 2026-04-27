/**
 * M365Page — Microsoft 365 deep integration
 * - Calendar sync: pull events, push milestones
 * - Teams notifications: send messages, test webhook
 * - Connection status
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { LayoutGrid } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: '#2d3748', border: '1px solid #4a5568', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const _TABS = ['calendar', 'teams', 'config']

function StatusBadge({ ok, label }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: ok ? '#1a3a1a' : '#1a202c',
      border: `1px solid ${ok ? '#276227' : '#4a5568'}`,
      borderRadius: 8, padding: '4px 10px', fontSize: 12,
      color: ok ? '#68d391' : '#718096',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: ok ? '#68d391' : '#4a5568' }} />
      {label}
    </span>
  )
}

function CalendarTab() {
  const [upn,  setUpn]  = useState('')
  const [days, setDays] = useState(14)
  const [synced, setSynced] = useState(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [msUpn, setMsUpn]   = useState('')
  const [msDays, setMsDays] = useState(30)
  const [msResult, setMsResult] = useState(null)
  const [msLoading, setMsLoading] = useState(false)

  const pullCalendar = async () => {
    setSyncLoading(true)
    try {
      const res = await api.post(`/m365/calendar/sync?user_upn=${encodeURIComponent(upn)}&days=${days}`)
      setSynced(res.data)
    } catch (e) {
      setSynced({ error: e?.response?.data?.detail || 'Error al conectar con Microsoft Graph' })
    } finally {
      setSyncLoading(false)
    }
  }

  const pushMilestones = async () => {
    setMsLoading(true)
    try {
      const res = await api.post('/m365/calendar/sync-milestones', { user_upn: msUpn, days_ahead: msDays })
      setMsResult(res.data)
    } catch (e) {
      setMsResult({ error: e?.response?.data?.detail || 'Error al sincronizar milestones' })
    } finally {
      setMsLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Pull calendar */}
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 14 }}>📅 Pull eventos de calendario</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={ls}>UPN del usuario (usuario@empresa.com)</label>
            <input value={upn} onChange={e => setUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label style={ls}>Días</label>
            <input type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pullCalendar} disabled={!upn || syncLoading} style={{ background: '#2b4a7a', border: 'none', borderRadius: 8, color: '#90cdf4', padding: '10px 18px', cursor: upn ? 'pointer' : 'not-allowed', fontSize: 13, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
            {syncLoading ? 'Sincronizando…' : '🔄 Pull eventos'}
          </button>
        </div>
        {synced && !synced.error && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 12, color: '#68d391', marginBottom: 8 }}>✓ {synced.pulled} evento(s) encontrados</div>
            <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(synced.events || []).map((ev, i) => (
                <div key={i} style={{ background: '#2d3748', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                  <div style={{ fontWeight: 600, color: '#e2e8f0' }}>{ev.subject}</div>
                  <div style={{ color: '#718096', marginTop: 2 }}>
                    {ev.start?.dateTime?.slice(0, 16)?.replace('T', ' ')} → {ev.end?.dateTime?.slice(0, 16)?.replace('T', ' ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {synced?.error && <div style={{ marginTop: 10, color: '#fc8181', fontSize: 12 }}>⚠ {typeof synced.error === 'string' ? synced.error : JSON.stringify(synced.error)}</div>}
      </div>

      {/* Push milestones */}
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 14 }}>📌 Sincronizar Milestones → Calendario</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={ls}>Calendario destino (UPN)</label>
            <input value={msUpn} onChange={e => setMsUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label style={ls}>Días</label>
            <input type="number" value={msDays} onChange={e => setMsDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pushMilestones} disabled={!msUpn || msLoading} style={{ background: '#276227', border: 'none', borderRadius: 8, color: '#68d391', padding: '10px 18px', cursor: msUpn ? 'pointer' : 'not-allowed', fontSize: 13, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
            {msLoading ? 'Creando eventos…' : '📤 Push Milestones'}
          </button>
        </div>
        {msResult && !msResult.error && (
          <div style={{ marginTop: 10, fontSize: 12 }}>
            <span style={{ color: '#68d391' }}>✓ {msResult.created} milestones sincronizados</span>
            {msResult.errors?.length > 0 && <span style={{ color: '#f6ad55', marginLeft: 10 }}>⚠ {msResult.errors.length} errores</span>}
          </div>
        )}
        {msResult?.error && <div style={{ marginTop: 10, color: '#fc8181', fontSize: 12 }}>⚠ {typeof msResult.error === 'string' ? msResult.error : JSON.stringify(msResult.error)}</div>}
      </div>
    </div>
  )
}

function TeamsTab() {
  const [title,   setTitle]   = useState('')
  const [text,    setText]    = useState('')
  const [color,   setColor]   = useState('0078D4')
  const [sending, setSending] = useState(false)
  const [result,  setResult]  = useState(null)

  const sendNotif = async () => {
    setSending(true)
    setResult(null)
    try {
      await api.post('/m365/teams/notify', { title, text, color })
      setResult({ ok: true })
    } catch (e) {
      setResult({ error: e?.response?.data?.detail || 'Error enviando a Teams' })
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 14 }}>💬 Enviar notificación a Teams</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={ls}>Título</label>
            <input value={title} onChange={e => setTitle(e.target.value)} style={fs} placeholder="Titulo de la notificacion" />
          </div>
          <div>
            <label style={ls}>Mensaje</label>
            <textarea value={text} onChange={e => setText(e.target.value)} style={{ ...fs, resize: 'vertical' }} rows={3} placeholder="Texto del mensaje..." />
          </div>
          <div>
            <label style={ls}>Color (hex sin #)</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input value={color} onChange={e => setColor(e.target.value)} style={{ ...fs, width: 120 }} placeholder="0078D4" />
              {['0078D4','FF0000','FF8C00','107C10','5C2D91'].map(c => (
                <button key={c} onClick={() => setColor(c)} style={{ width: 22, height: 22, background: `#${c}`, border: color === c ? '2px solid #fff' : '2px solid transparent', borderRadius: 4, cursor: 'pointer' }} />
              ))}
            </div>
          </div>
          <button onClick={sendNotif} disabled={!title || !text || sending} style={{ alignSelf: 'flex-start', background: '#2b4a7a', border: 'none', borderRadius: 8, color: '#90cdf4', padding: '10px 20px', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit' }}>
            {sending ? 'Enviando…' : '📨 Enviar a Teams'}
          </button>
          {result?.ok && <div style={{ color: '#68d391', fontSize: 12 }}>✓ Notificación enviada correctamente</div>}
          {result?.error && <div style={{ color: '#fc8181', fontSize: 12 }}>⚠ {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}</div>}
        </div>
      </div>

      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 10 }}>⚙ Notificaciones automáticas</div>
        <div style={{ fontSize: 13, color: '#718096', lineHeight: 1.6 }}>
          Configura Contecflow para enviar automáticamente notificaciones a Teams cuando:
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            <li>Un milestone está próximo (≤3 días)</li>
            <li>Un ticket crítico se abre en el Service Desk</li>
            <li>El presupuesto supera el 90%</li>
            <li>Una aprobación queda pendiente por más de 48h</li>
          </ul>
          Estas se activan via las <strong style={{ color: '#90cdf4' }}>Automatizaciones</strong> o mediante el endpoint <code style={{ color: '#f6ad55' }}>POST /api/v1/m365/teams/notify-project</code>.
        </div>
      </div>
    </div>
  )
}

function ConfigTab({ status }) {
  const envVars = [
    { key: 'AZURE_TENANT_ID',     label: 'Tenant ID de Azure AD',   ok: status?.required_env_vars?.AZURE_TENANT_ID },
    { key: 'AZURE_CLIENT_ID',     label: 'Client ID (App ID)',       ok: status?.required_env_vars?.AZURE_CLIENT_ID },
    { key: 'AZURE_CLIENT_SECRET', label: 'Client Secret',            ok: status?.required_env_vars?.AZURE_CLIENT_SECRET },
    { key: 'TEAMS_WEBHOOK_URL',   label: 'Teams Incoming Webhook URL', ok: status?.required_env_vars?.TEAMS_WEBHOOK_URL },
  ]

  const steps = [
    { n: 1, title: 'Registrar app en Azure AD', desc: 'Ve a portal.azure.com → Microsoft Entra ID → App registrations → New registration. Añade redirect URI: https://tu-dominio/auth/callback/microsoft' },
    { n: 2, title: 'Asignar permisos Graph', desc: 'En la app → API permissions → Add: Calendars.ReadWrite, User.Read.All. Para Teams: ChannelMessage.Send. Haz clic en "Grant admin consent".' },
    { n: 3, title: 'Crear Client Secret', desc: 'En la app → Certificates & secrets → New client secret. Copia el valor inmediatamente, solo se muestra una vez.' },
    { n: 4, title: 'Configurar Teams webhook', desc: 'En un canal de Teams → ... → Connectors → Incoming Webhook → Create. Copia la URL resultante.' },
    { n: 5, title: 'Añadir variables de entorno', desc: 'Añade las 4 variables a tu .env o docker-compose.yml y reinicia Contecflow.', code: 'AZURE_TENANT_ID=...\nAZURE_CLIENT_ID=...\nAZURE_CLIENT_SECRET=...\nTEAMS_WEBHOOK_URL=https://...' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Status */}
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 12 }}>Estado de la integración</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {envVars.map(v => (
            <StatusBadge key={v.key} ok={v.ok} label={v.label} />
          ))}
        </div>
      </div>

      {/* Setup steps */}
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 14 }}>Guía de configuración</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {steps.map(s => (
            <div key={s.n} style={{ display: 'flex', gap: 12 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#2b4a7a', color: '#90cdf4', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 2 }}>
                {s.n}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>{s.title}</div>
                <div style={{ fontSize: 12, color: '#718096', lineHeight: 1.5 }}>{s.desc}</div>
                {s.code && (
                  <pre style={{ background: '#0d1117', border: '1px solid #4a5568', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#a0aec0', marginTop: 6, overflow: 'auto' }}>{s.code}</pre>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scopes reference */}
      <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0', marginBottom: 8 }}>Permisos Graph requeridos</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: '#718096', fontWeight: 700, borderBottom: '1px solid #2d3748' }}>Permiso</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: '#718096', fontWeight: 700, borderBottom: '1px solid #2d3748' }}>Tipo</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: '#718096', fontWeight: 700, borderBottom: '1px solid #2d3748' }}>Funcionalidad</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Calendars.ReadWrite', 'Application', 'Leer/escribir calendarios de todos los usuarios'],
              ['User.Read.All',        'Application', 'Leer perfiles de usuario para buscar por UPN'],
              ['ChannelMessage.Send',  'Application', 'Enviar mensajes a canales de Teams'],
            ].map(([perm, type, desc]) => (
              <tr key={perm}>
                <td style={{ padding: '6px 8px', color: '#f6ad55', fontFamily: 'monospace' }}>{perm}</td>
                <td style={{ padding: '6px 8px', color: '#718096' }}>{type}</td>
                <td style={{ padding: '6px 8px', color: '#a0aec0' }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function M365Page() {
  const _t = useAppT()
  const [activeTab, setTab] = useState('calendar')

  const { data: status } = useQuery({
    queryKey: ['m365-status'],
    queryFn: () => api.get('/m365/status').then(r => r.data),
    refetchInterval: 30000,
  })

  const graphOk = status?.graph_configured
  const teamsOk = status?.teams_webhook_configured

  return (
    <div style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title="Microsoft 365"
        subtitle="Integracion con Graph API y Microsoft Teams"
      />

      {/* Connection pills */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        <StatusBadge ok={graphOk} label={`Graph API ${graphOk ? 'activo' : 'no configurado'}`} />
        <StatusBadge ok={teamsOk} label={`Teams Webhook ${teamsOk ? 'activo' : 'no configurado'}`} />
        {!graphOk && (
          <span style={{ fontSize: 12, color: '#718096', alignSelf: 'center' }}>
            → pestaña Configuración para el setup
          </span>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[['calendar', '📅 Calendario'], ['teams', '💬 Teams'], ['config', '⚙ Configuración']].map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: activeTab === t ? '#2b4a7a' : 'none',
            border: `1px solid ${activeTab === t ? '#63b3ed' : '#4a5568'}`,
            borderRadius: 8, padding: '6px 16px',
            color: activeTab === t ? '#90cdf4' : '#718096',
            cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
          }}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'calendar' && <CalendarTab />}
      {activeTab === 'teams'    && <TeamsTab />}
      {activeTab === 'config'   && <ConfigTab status={status} />}
    </div>
  )
}
