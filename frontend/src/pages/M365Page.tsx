/**
 * M365Page — Microsoft 365 deep integration
 * - Calendar sync: pull events, push milestones
 * - Teams notifications: send messages, test webhook
 * - Connection status
 */

import { useState, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { m365Api, apiUrl } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { LayoutGrid } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { Table } from '../components/ui'
import type { CSSProperties } from 'react'
import DsBadge from '../components/ui/StatusBadge'

interface M365Status {
  graph_configured?: boolean
  teams_webhook_configured?: boolean
  required_env_vars?: Record<string, boolean>
}

interface CalendarEvent {
  subject?: string
  start?: { dateTime?: string }
  end?: { dateTime?: string }
}

interface CalendarPullResult {
  pulled?: number
  events?: CalendarEvent[]
  error?: string
}

interface MilestonePushResult {
  created?: number
  errors?: unknown[]
  error?: string
}

interface ApiErrorLike {
  response?: { data?: { detail?: string } }
}

const fs: CSSProperties = { width: '100%', background: 'var(--surface-4)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const _TABS = ['calendar', 'teams', 'config']

function StatusBadge({ ok, label }: { ok?: boolean; label: string }) {
  return (
    <DsBadge kind={ok ? 'success' : 'neutral'} dot caps={false}>{label}</DsBadge>
  )
}

function CalendarTab() {
  const idCampo = useId()
  const t = useAppT()
  const [upn,  setUpn]  = useState('')
  const [days, setDays] = useState(14)
  const [synced, setSynced] = useState<CalendarPullResult | null>(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [msUpn, setMsUpn]   = useState('')
  const [msDays, setMsDays] = useState(30)
  const [msResult, setMsResult] = useState<MilestonePushResult | null>(null)
  const [msLoading, setMsLoading] = useState(false)

  const pullCalendar = async () => {
    setSyncLoading(true)
    try {
      const res = await m365Api.syncCalendar(upn, days)
      setSynced(res.data)
    } catch (e: unknown) {
      setSynced({ error: (e as ApiErrorLike)?.response?.data?.detail || 'Error al conectar con Microsoft Graph' })
    } finally {
      setSyncLoading(false)
    }
  }

  const pushMilestones = async () => {
    setMsLoading(true)
    try {
      const res = await m365Api.syncMilestones({ user_upn: msUpn, days_ahead: msDays })
      setMsResult(res.data)
    } catch (e: unknown) {
      setMsResult({ error: (e as ApiErrorLike)?.response?.data?.detail || 'Error al sincronizar milestones' })
    } finally {
      setMsLoading(false)
    }
  }

  return (
    <div className="u-stack-20">
      {/* Pull calendar */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>{t('m365.pull_eventos_de_calendario')}</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('m365.upn_del_usuario_usuario_empresa_com')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={upn} onChange={e => setUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('m365.dias')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={fs} min={1} max={90} />
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
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>📌 Sincronizar Milestones → Calendario</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Calendario destino (UPN)</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={msUpn} onChange={e => setMsUpn(e.target.value)} style={fs} placeholder="usuario@empresa.com" />
          </div>
          <div style={{ width: 100 }}>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('m365.dias')}</label>
            <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={msDays} onChange={e => setMsDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pushMilestones} disabled={!msUpn || msLoading} style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, color: 'var(--success)', padding: '10px 18px', cursor: msUpn ? 'pointer' : 'not-allowed', fontSize: "var(--text-base)", fontFamily: 'inherit', whiteSpace: 'nowrap', fontWeight: 600 }}>
            {msLoading ? 'Creando eventos…' : '📤 Push Milestones'}
          </button>
        </div>
        {msResult && !msResult.error && (
          <div style={{ marginTop: 10, fontSize: "var(--text-sm)" }}>
            <span className="u-success">✓ {msResult.created} milestones sincronizados</span>
            {(msResult.errors?.length ?? 0) > 0 && <span style={{ color: 'var(--orange)', marginLeft: 10 }}>⚠ {msResult.errors?.length} errores</span>}
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
  const idCampo = useId()
  const t = useAppT()
  const [title,   setTitle]   = useState('')
  const [text,    setText]    = useState('')
  const [color,   setColor]   = useState(TEAMS_BRAND_PRESETS[0])
  const [sending, setSending] = useState(false)
  const [result,  setResult]  = useState<{ ok?: boolean; error?: string } | null>(null)

  const sendNotif = async () => {
    setSending(true)
    setResult(null)
    try {
      await m365Api.teamsNotify({ title, text, color })
      setResult({ ok: true })
    } catch (e: unknown) {
      setResult({ error: (e as ApiErrorLike)?.response?.data?.detail || 'Error enviando a Teams' })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="u-stack-16">
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 20 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>{t('m365.enviar_notificacion_a_teams')}</div>
        <div className="u-stack-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('m365.titulo')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={title} onChange={e => setTitle(e.target.value)} style={fs} placeholder={t('m365.titulo_de_la_notificacion')} />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Mensaje</label>
            <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={text} onChange={e => setText(e.target.value)} style={{ ...fs, resize: 'vertical' }} rows={3} placeholder={t('m365.texto_del_mensaje')} />
          </div>
          <div>
            <label style={ls}>{t('m365.color_hex_sin')}</label>
            <div className="u-row-center-8">
              <input value={color} onChange={e => setColor(e.target.value)} style={{ ...fs, width: 120 }} placeholder="0078D4" />
              {TEAMS_BRAND_PRESETS.map(c => (
                <button aria-label={`Color de marca Teams #${c}`} key={c} onClick={() => setColor(c)} title={`Color de marca Teams #${c}`}
                  style={{ width: 22, height: 22, background: `#${c}`, border: color === c ? '2px solid var(--text-1)' : '2px solid transparent', borderRadius: 4, cursor: 'pointer' }} />
              ))}
            </div>
          </div>
          <button onClick={sendNotif} disabled={!title || !text || sending} style={{ alignSelf: 'flex-start', background: 'var(--accent-glow)', border: 'none', borderRadius: 8, color: 'var(--info)', padding: '10px 20px', cursor: 'pointer', fontSize: "var(--text-base)", fontFamily: 'inherit' }}>
            {sending ? 'Enviando…' : '📨 Enviar a Teams'}
          </button>
          {result?.ok && <div style={{ color: 'var(--success)', fontSize: "var(--text-sm)" }}>{t('m365.notificacion_enviada_correctamente')}</div>}
          {result?.error && <div style={{ color: 'var(--danger)', fontSize: "var(--text-sm)" }}>⚠ {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}</div>}
        </div>
      </div>

      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 10 }}>{t('m365.notificaciones_automaticas')}</div>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.6 }}>
          {t('m365.configura_contecflow_para_enviar_automaticamente_notificaciones_a')}
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            <li>{t('m365.un_milestone_esta_proximo_3_dias')}</li>
            <li>{t('m365.un_ticket_critico_se_abre_en_el')}</li>
            <li>{t('m365.el_presupuesto_supera_el_90')}</li>
            <li>{t('m365.una_aprobacion_queda_pendiente_por_mas_de')}</li>
          </ul>
          {t('m365.estas_se_activan_via_las')} <strong style={{ color: 'var(--info)' }}>Automatizaciones</strong> {t('m365.o_mediante_el_endpoint')} <code style={{ color: 'var(--orange)' }}>POST {apiUrl('/m365/teams/notify-project')}</code>.
        </div>
      </div>
    </div>
  )
}

function ConfigTab({ status }: { status?: M365Status | null }) {
  const t = useAppT()
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
    <div className="u-stack-16">
      {/* Status */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>{t('m365.estado_de_la_integracion')}</div>
        <div className="u-wrap-8">
          {envVars.map(v => (
            <StatusBadge key={v.key} ok={v.ok} label={v.label} />
          ))}
        </div>
      </div>

      {/* Setup steps */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 18 }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>{t('m365.guia_de_configuracion')}</div>
        <div className="u-stack-14">
          {steps.map(s => (
            <div key={s.n} style={{ display: 'flex', gap: 12 }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-glow)', color: 'var(--info)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, flexShrink: 0, marginTop: 2 }}>
                {s.n}
              </div>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 4 }}>{s.title}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{s.desc}</div>
                {s.code && (
                  <pre style={{ background: 'var(--surface-0)', border: '1px solid var(--surface-5)', borderRadius: 'var(--radius-sm)', padding: '8px 12px', fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 6, overflow: 'auto' }}>{s.code}</pre>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scopes reference */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 18 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 8 }}>Permisos Graph requeridos</div>
        <Table
          data={[
            { perm: 'Calendars.ReadWrite', type: 'Application', desc: 'Leer/escribir calendarios de todos los usuarios' },
            { perm: 'User.Read.All',       type: 'Application', desc: 'Leer perfiles de usuario para buscar por UPN' },
            { perm: 'ChannelMessage.Send', type: 'Application', desc: 'Enviar mensajes a canales de Teams' },
          ]}
          columns={[
            { key: 'perm', label: 'Permiso', render: (_v, r) => <span style={{ color: 'var(--orange)', fontFamily: 'var(--font-mono)' }}>{r.perm}</span> },
            { key: 'type', label: 'Tipo', render: (_v, r) => <span className="u-text2">{r.type}</span> },
            { key: 'desc', label: 'Funcionalidad', render: (_v, r) => <span className="u-text2">{r.desc}</span> },
          ]}
        />
      </div>
    </div>
  )
}

export default function M365Page() {
  const t = useAppT()
  const _t = useAppT()
  const [activeTab, setTab] = useState<'calendar' | 'teams' | 'config'>('calendar')

  const { data: status } = useQuery<M365Status>({
    queryKey: ['m365-status'],
    queryFn: () => m365Api.status().then(r => r.data),
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
            {t('m365.pestana_configuracion_para_el_setup')}
          </span>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[['calendar', '📅 Calendario'], ['teams', '💬 Teams'], ['config', '⚙ Configuración']].map(([tabId, label]) => (
          <button key={tabId} onClick={() => setTab(tabId as 'calendar' | 'teams' | 'config')} style={{
            background: activeTab === tabId ? 'var(--accent-glow)' : 'none',
            border: `1px solid ${activeTab === tabId ? 'var(--info)' : 'var(--surface-5)'}`,
            borderRadius: 8, padding: '6px 16px',
            color: activeTab === tabId ? 'var(--info)' : 'var(--text-2)',
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
