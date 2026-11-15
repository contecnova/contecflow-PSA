/**
 * M365Page — Microsoft 365 deep integration
 * - Calendar sync: pull events, push milestones
 * - Teams notifications: send messages, test webhook
 * - Connection status
 */

import { PRODUCT_NAME } from '../constants/brand'
import { useState, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { m365Api, apiUrl } from '../services/api'
import type { CalendarioM365Leido, EstadoM365, HitosEnCalendarioM365 } from '../services/api/tipos-plataforma'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { LayoutGrid } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { Table } from '../components/ui'
import type { CSSProperties } from 'react'
import DsBadge from '../components/ui/StatusBadge'
import { POLL_FREQUENT_MS } from '../constants/timings'
import './M365Page.css'

/** El resultado o el error que se pinta en su lugar. */
type CalendarPullResult = Partial<CalendarioM365Leido> & { error?: string }
type MilestonePushResult = Partial<HitosEnCalendarioM365> & { error?: string }

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
      setSynced({ error: (e as ApiErrorLike)?.response?.data?.detail || t('pagina_m365.error_al_conectar_con_microsoft_graph') })
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
      setMsResult({ error: (e as ApiErrorLike)?.response?.data?.detail || t('pagina_m365.error_al_sincronizar_milestones') })
    } finally {
      setMsLoading(false)
    }
  }

  return (
    <div className="u-stack-20">
      {/* Pull calendar */}
      <div className="m365-card">
        <div className="m365-box">{t('m365.pull_eventos_de_calendario')}</div>
        <div className="m365-row">
          <div className="m365-box-2">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('m365.upn_del_usuario_usuario_empresa_com')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={upn} onChange={e => setUpn(e.target.value)} style={fs} placeholder={t('pagina_m365.usuario_empresa_com')} />
          </div>
          <div className="m365-box-3">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('m365.dias')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pullCalendar} disabled={!upn || syncLoading} className={`m365-btn ${upn ? 'm365page-sx1' : 'm365page-sx2'}`}>
            {syncLoading ? t('pagina_m365.sincronizando') : t('pagina_m365.pull_eventos')}
          </button>
        </div>
        {synced && !synced.error && (
          <div className="m365-box-4">
            <div className="m365-box-5">✓ {synced.pulled}{' '}{t('pagina_m365.evento_s_encontrados')}</div>
            <div className="m365-stack">
              {(synced.events || []).map((ev, i) => (
                <div key={i} className="m365-card-2">
                  <div className="m365-box-6">{ev.subject}</div>
                  <div className="m365-box-7">
                    {ev.start?.dateTime?.slice(0, 16)?.replace('T', ' ')} → {ev.end?.dateTime?.slice(0, 16)?.replace('T', ' ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {synced?.error && <div className="m365-box-8">⚠ {typeof synced.error === 'string' ? synced.error : JSON.stringify(synced.error)}</div>}
      </div>

      {/* Push milestones */}
      <div className="m365-card">
        <div className="m365-box">{t('pagina_m365.sincronizar_milestones_calendario')}</div>
        <div className="m365-row">
          <div className="m365-box-2">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('pagina_m365.calendario_destino_upn')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={msUpn} onChange={e => setMsUpn(e.target.value)} style={fs} placeholder={t('pagina_m365.usuario_empresa_com')} />
          </div>
          <div className="m365-box-3">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('m365.dias')}</label>
            <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={msDays} onChange={e => setMsDays(Number(e.target.value))} style={fs} min={1} max={90} />
          </div>
          <button onClick={pushMilestones} disabled={!msUpn || msLoading} className={`m365-btn-2 ${msUpn ? 'm365page-sx1' : 'm365page-sx2'}`}>
            {msLoading ? t('pagina_m365.creando_eventos') : t('pagina_m365.push_milestones')}
          </button>
        </div>
        {msResult && !msResult.error && (
          <div className="m365-box-9">
            <span className="u-success">✓ {msResult.created}{' '}{t('pagina_m365.milestones_sincronizados')}</span>
            {(msResult.errors?.length ?? 0) > 0 && <span className="m365-label">⚠ {t('pagina_m365.n_errores', { n: msResult.errors?.length ?? 0 })}</span>}
          </div>
        )}
        {msResult?.error && <div className="m365-box-8">⚠ {typeof msResult.error === 'string' ? msResult.error : JSON.stringify(msResult.error)}</div>}
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
      setResult({ error: (e as ApiErrorLike)?.response?.data?.detail || t('pagina_m365.error_enviando_a_teams') })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="u-stack-16">
      <div className="m365-card">
        <div className="m365-box">{t('m365.enviar_notificacion_a_teams')}</div>
        <div className="u-stack-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('m365.titulo')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={title} onChange={e => setTitle(e.target.value)} style={fs} placeholder={t('m365.titulo_de_la_notificacion')} />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('pagina_m365.mensaje')}</label>
            <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={text} onChange={e => setText(e.target.value)} style={{ ...fs, resize: 'vertical' }} rows={3} placeholder={t('m365.texto_del_mensaje')} />
          </div>
          <div>
            <label style={ls}>{t('m365.color_hex_sin')}</label>
            <div className="u-row-center-8">
              <input aria-label={t('m365.color_hex_sin')} value={color} onChange={e => setColor(e.target.value)} style={{ ...fs, width: 120 }} placeholder="0078D4" />
              {TEAMS_BRAND_PRESETS.map(c => (
                <button aria-label={t('pagina_m365.color_de_marca_teams', { c })} key={c} onClick={() => setColor(c)} title={t('pagina_m365.color_de_marca_teams', { c })}
                  className={`m365-btn-3 m365page-sx3 ${color === c ? 'm365page-sx4' : 'm365page-sx5'}`} style={{ background: `#${c}` }} />
              ))}
            </div>
          </div>
          <button onClick={sendNotif} disabled={!title || !text || sending} className="m365-btn-4">
            {sending ? t('pagina_m365.enviando') : t('pagina_m365.enviar_a_teams')}
          </button>
          {result?.ok && <div className="m365-box-10">{t('m365.notificacion_enviada_correctamente')}</div>}
          {result?.error && <div className="m365-box-11">⚠ {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}</div>}
        </div>
      </div>

      <div className="m365-card-3">
        <div className="m365-box-12">{t('m365.notificaciones_automaticas')}</div>
        <div className="m365-box-13">
          {t('m365.configura_contecflow_para_enviar_automaticamente_notificaciones_a')}
          <ul className="m365-box-14">
            <li>{t('m365.un_milestone_esta_proximo_3_dias')}</li>
            <li>{t('m365.un_ticket_critico_se_abre_en_el')}</li>
            <li>{t('m365.el_presupuesto_supera_el_90')}</li>
            <li>{t('m365.una_aprobacion_queda_pendiente_por_mas_de')}</li>
          </ul>
          {t('m365.estas_se_activan_via_las')} <strong className="m365-box-15">{t('pagina_m365.automatizaciones')}</strong> {t('m365.o_mediante_el_endpoint')} <code className="m365-box-16">POST {apiUrl('/m365/teams/notify-project')}</code>.
        </div>
      </div>
    </div>
  )
}

function ConfigTab({ status }: { status?: EstadoM365 | null }) {
  const t = useAppT()
  const envVars = [
    { key: 'AZURE_TENANT_ID',     label: t('pagina_m365.tenant_id_de_azure_ad'),   ok: status?.required_env_vars?.AZURE_TENANT_ID },
    { key: 'AZURE_CLIENT_ID',     label: t('pagina_m365.client_id_app_id'),       ok: status?.required_env_vars?.AZURE_CLIENT_ID },
    { key: 'AZURE_CLIENT_SECRET', label: t('pagina_m365.client_secret'),            ok: status?.required_env_vars?.AZURE_CLIENT_SECRET },
    { key: 'TEAMS_WEBHOOK_URL',   label: t('pagina_m365.teams_incoming_webhook_url'), ok: status?.required_env_vars?.TEAMS_WEBHOOK_URL },
  ]

  const steps = [
    { n: 1, title: t('pagina_m365.registrar_app_en_azure_ad'), desc: t('pagina_m365.ve_a_portal_azure_com_microsoft') },
    { n: 2, title: t('pagina_m365.asignar_permisos_graph'), desc: t('pagina_m365.en_la_app_api_permissions_add') },
    { n: 3, title: t('pagina_m365.crear_client_secret'), desc: t('pagina_m365.en_la_app_certificates_secrets_new') },
    { n: 4, title: t('pagina_m365.configurar_teams_webhook'), desc: t('pagina_m365.en_un_canal_de_teams_connectors') },
    { n: 5, title: t('pagina_m365.anadir_variables_de_entorno'), desc: t('pagina_m365.anade_las_4_variables_a_tu', { PRODUCT_NAME }), code: 'AZURE_TENANT_ID=...\nAZURE_CLIENT_ID=...\nAZURE_CLIENT_SECRET=...\nTEAMS_WEBHOOK_URL=https://...' },
  ]

  return (
    <div className="u-stack-16">
      {/* Status */}
      <div className="m365-card-3">
        <div className="m365-box-17">{t('m365.estado_de_la_integracion')}</div>
        <div className="u-wrap-8">
          {envVars.map(v => (
            <StatusBadge key={v.key} ok={v.ok} label={v.label} />
          ))}
        </div>
      </div>

      {/* Setup steps */}
      <div className="m365-card-3">
        <div className="m365-box">{t('m365.guia_de_configuracion')}</div>
        <div className="u-stack-14">
          {steps.map(s => (
            <div key={s.n} className="m365-row-2">
              <div className="m365-row-3">
                {s.n}
              </div>
              <div>
                <div className="m365-box-18">{s.title}</div>
                <div className="m365-box-19">{s.desc}</div>
                {s.code && (
                  <pre className="m365-card-4">{s.code}</pre>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Scopes reference */}
      <div className="m365-card-3">
        <div className="m365-box-20">{t('pagina_m365.permisos_graph_requeridos')}</div>
        <Table
          data={[
            { perm: 'Calendars.ReadWrite', type: 'Application', desc: t('pagina_m365.leer_escribir_calendarios_de_todos_los') },
            { perm: 'User.Read.All',       type: 'Application', desc: t('pagina_m365.leer_perfiles_de_usuario_para_buscar') },
            { perm: 'ChannelMessage.Send', type: 'Application', desc: t('pagina_m365.enviar_mensajes_a_canales_de_teams') },
          ]}
          columns={[
            { key: 'perm', label: t('pagina_m365.permiso'), render: (_v, r) => <span className="m365-label-2">{r.perm}</span> },
            { key: 'type', label: t('pagina_m365.tipo'), render: (_v, r) => <span className="u-text2">{r.type}</span> },
            { key: 'desc', label: t('pagina_m365.funcionalidad'), render: (_v, r) => <span className="u-text2">{r.desc}</span> },
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

  const { data: status } = useQuery<EstadoM365>({
    queryKey: ['m365-status'],
    queryFn: () => m365Api.status().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const graphOk = status?.graph_configured
  const teamsOk = status?.teams_webhook_configured

  return (
    <PageShell className="m365-box-21">
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title={t('pagina_m365.microsoft_365')}
        subtitle={t('pagina_m365.integracion_con_graph_api_y_microsoft')}
      />

      {/* Connection pills */}
      <div className="m365-row-4">
        <StatusBadge ok={graphOk} label={t('pagina_m365.graph_api', { v1: graphOk ? t('pagina_m365.activo') : t('pagina_m365.no_configurado') })} />
        <StatusBadge ok={teamsOk} label={t('pagina_m365.teams_webhook', { v1: teamsOk ? t('pagina_m365.activo') : t('pagina_m365.no_configurado') })} />
        {!graphOk && (
          <span className="m365-label-3">
            {t('m365.pestana_configuracion_para_el_setup')}
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="m365-row-5">
        {[['calendar', t('pagina_m365.calendario')], ['teams', t('pagina_m365.teams')], ['config', t('pagina_m365.configuracion')]].map(([tabId, label]) => (
          <button key={tabId} onClick={() => setTab(tabId as 'calendar' | 'teams' | 'config')} className={`m365-btn-5 m365page-sx6 ${activeTab === tabId ? 'm365page-sx7' : 'm365page-sx8'}`} style={{ border: `1px solid ${activeTab === tabId ? 'var(--info)' : 'var(--surface-5)'}` }}>
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
