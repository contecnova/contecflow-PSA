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
import PageShell from '../components/layout/PageShell'
import { LayoutGrid } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: 'var(--surface-4)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const _TABS = ['calendar', 'teams', 'config']

function StatusBadge({ ok, label }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: ok ? 'var(--success-bg)' : 'var(--surface-2)',
      border: `1px solid ${ok ? 'var(--success-border)' : 'var(--surface-5)'}`,
      borderRadius: 8, padding: '4px 10px', fontSize: "var(--text-sm)",
      color: ok ? 'var(--success)' : 'var(--text-2)',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: ok ? 'var(--success)' : 'var(--surface-5)' }} />
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
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>📅 Pull eventos de calendario</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={ls}>UPN del usuario (usuario@empresa.com)</label>
            <input value={upn} onChange={e => setUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label style={ls}>Días</label>
            <input type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pullCalendar} disabled={!upn || syncLoading} style={{ background: 'var(--accent-glow)', border: 'none', borderRadius: 8, color: 'var(--info)', padding: '10px 18px', cursor: upn ? 'pointer' : 'not-allowed', fontSize: "var(--text-base)", fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
            {syncLoading ? 'Sincronizando…' : '🔄 Pull eventos'}
          </button>
        </div>
        {synced && !synced.error && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--success)', marginBottom: 8 }}>✓ {synced.pulled} evento(s) encontrados</div>
            <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(synced.events || []).map((ev, i) => (
                <div key={i} style={{ background: 'var(--surface-4)', borderRadius: 8, padding: '8px 12px', fontSize: "var(--text-sm)" }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-1)' }}>{ev.subject}</div>
                  <div style={{ color: 'var(--text-2)', marginTop: 2 }}>
                    {ev.start?.dateTime?.slice(0, 16)?.replace('T', ' ')} → {ev.end?.dateTime?.slice(0, 16)?.replace('T', ' ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {synced?.error && <div style={{ marginTop: 10, color: 'var(--danger)', fontSize: "var(--text-sm)" }}>⚠ {typeof synced.error === 'string' ? synced.error : JSON.stringify(synced.error)}</div>}
      </div>

      {/* Push milestones */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>📌 Sincronizar Milestones → Calendario</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={ls}>Calendario destino (UPN)</label>
            <input value={msUpn} onChange={e => setMsUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label style={ls}>Días</label>
            <input type="number" value={msDays} onChange={e => setMsDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pushMilestones} disabled={!msUpn || msLoading} style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, color: 'var(--success)', padding: '10px 18px', cursor: msUpn ? 'pointer' : 'not-allowed', fontSize: "var(--text-base)", fontFamily: 'inherit', whiteSpace: 'nowrap', fontWeight: 600 }}>
            {msLoading ? 'Creando eventos…' : '📤 Push Milestones'}
          </button>
        </div>
        {msResult && !msResult.error && (
          <div style={{ marginTop: 10, fontSize: "var(--text-sm)" }}>
            <span style={{ color: 'var(--success)' }}>✓ {msResult.created} milestones sincronizados</span>
            {msResult.errors?.length > 0 && <span style={{ color: '#fb923c', marginLeft: 10 }}>⚠ {msResult.errors.length} errores</span>}
          </div>
        )}
        {msResult?.error && <div style={{ marginTop: 10, color: 'var(--danger)', fontSize: "var(--text-sm)" }}>⚠ {typeof msResult.error === 'string' ? msResult.error : JSON.stringify(msResult.error)}</div>}
      </div>
    </div>
  )
}

// Microsoft Teams brand color palette (NO USAR tokens del producto — son colores
// corporativos de Microsoft que se envían literalmente al Adaptive Card de Teams).
// Ver https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format
const TEAMS_BRAND_PRESETS = ['0078D4', 'FF0000', 'FF8C00', '107C10', '5C2D91']

function TeamsTab() {
  const [title,   setTitle]   = useState('')
  const [text,    setText]    = useState('')
  const [color,   setColor]   = useState(TEAMS_BRAND_PRESETS[0])
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
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>💬 Enviar notificación a Teams</div>
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
              {TEAMS_BRAND_PRESETS.map(c => (
                <button key={c} onClick={() => setColor(c)} title={`Color de marca Teams #${c}`}
                  style={{ width: 22, height: 22, background: `#${c}`, border: color === c ? '2px solid var(--text-1)' : '2px solid transparent', borderRadius: 4, cursor: 'pointer' }} />
              ))}
            </div>
          </div>
          <button onClick={sendNotif} disabled={!title || !text || sending} style={{ alignSelf: 'flex-start', background: 'var(--accent-glow)', border: 'none', borderRadius: 8, color: 'var(--info)', padding: '10px 20px', cursor: 'pointer', fontSize: "var(--text-base)", fontFamily: 'inherit' }}>
            {sending ? 'Enviando…' : '📨 Enviar a Teams'}
          </button>
          {result?.ok && <div style={{ color: 'var(--success)', fontSize: "var(--text-sm)" }}>✓ Notificación enviada correctamente</div>}
          {result?.error && <div style={{ color: 'var(--danger)', fontSize: "var(--text-sm)" }}>⚠ {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}</div>}
        </div>
      </div>

      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 10 }}>⚙ Notificaciones automáticas</div>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6 }}>
          Configura Contecflow para enviar automáticamente notificaciones a Teams cuando:
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            <li>Un milestone está próximo (≤3 días)</li>
            <li>Un ticket crítico se abre en el Service Desk</li>
            <li>El presupuesto supera el 90%</li>
            <li>Una aprobación queda pendiente por más de 48h</li>
          </ul>
          Estas se activan via las <strong style={{ color: 'var(--info)' }}>Automatizaciones</strong> o mediante el endpoint <code style={{ color: '#fb923c' }}>POST /api/v1/m365/teams/notify-project</code>.
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
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>Estado de la integración</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {envVars.map(v => (
            <StatusBadge key={v.key} ok={v.ok} label={v.label} />
          ))}
        </div>
      </div>

      {/* Setup steps */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>Guía de configuración</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {steps.map(s => (
            <div key={s.n} style={{ display: 'flex', gap: 12 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-glow)', color: 'var(--info)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, flexShrink: 0, marginTop: 2 }}>
                {s.n}
              </div>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 4 }}>{s.title}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{s.desc}</div>
                {s.code && (
                  <pre style={{ background: '#0d1117', border: '1px solid var(--surface-5)', borderRadius: 6, padding: '8px 12px', fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 6, overflow: 'auto' }}>{s.code}</pre>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scopes reference */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 8 }}>Permisos Graph requeridos</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-sm)" }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-2)', fontWeight: 700, borderBottom: '1px solid var(--surface-4)' }}>Permiso</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-2)', fontWeight: 700, borderBottom: '1px solid var(--surface-4)' }}>Tipo</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-2)', fontWeight: 700, borderBottom: '1px solid var(--surface-4)' }}>Funcionalidad</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Calendars.ReadWrite', 'Application', 'Leer/escribir calendarios de todos los usuarios'],
              ['User.Read.All',        'Application', 'Leer perfiles de usuario para buscar por UPN'],
              ['ChannelMessage.Send',  'Application', 'Enviar mensajes a canales de Teams'],
            ].map(([perm, type, desc]) => (
              <tr key={perm}>
                <td style={{ padding: '6px 8px', color: '#fb923c', fontFamily: 'var(--font-mono)' }}>{perm}</td>
                <td style={{ padding: '6px 8px', color: 'var(--text-2)' }}>{type}</td>
                <td style={{ padding: '6px 8px', color: 'var(--text-2)' }}>{desc}</td>
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
    <PageShell style={{ maxWidth: 900, margin: '0 auto' }}>
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
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', alignSelf: 'center' }}>
            → pestaña Configuración para el setup
          </span>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[['calendar', '📅 Calendario'], ['teams', '💬 Teams'], ['config', '⚙ Configuración']].map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: activeTab === t ? 'var(--accent-glow)' : 'none',
            border: `1px solid ${activeTab === t ? 'var(--info)' : 'var(--surface-5)'}`,
            borderRadius: 8, padding: '6px 16px',
            color: activeTab === t ? 'var(--info)' : 'var(--text-2)',
            cursor: 'pointer', fontSize: "var(--text-base)", fontFamily: 'inherit',
          }}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'calendar' && <CalendarTab />}
      {activeTab === 'teams'    && <TeamsTab />}
      {activeTab === 'config'   && <ConfigTab status={status} />}
    </PageShell>
  )
}
