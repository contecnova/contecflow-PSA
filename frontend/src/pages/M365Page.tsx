/**
 * M365Page — integración con Microsoft 365: calendario (leer eventos, llevar
 * hitos), notificaciones a Teams y guía de configuración.
 *
 * 16-11-2026: rehecha con los componentes comunes (Tabs, Card, Input, Button,
 * iconos lucide). Antes tenía pestañas y botones propios con el texto en azul
 * fijo (`--info`) sobre el fondo del tema, emojis en títulos y botones, y un
 * ancho máximo centrado: no seguía el tema elegido ni el resto de pantallas.
 */

import { PRODUCT_NAME } from '../constants/brand'
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { m365Api, apiUrl } from '../services/api'
import type { CalendarioM365Leido, EstadoM365, HitosEnCalendarioM365 } from '../services/api/tipos-plataforma'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarDays, CalendarPlus, LayoutGrid, MessageSquare, RefreshCw, Send, Settings, CheckCircle2, AlertTriangle } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { Button, Card, Input, Pulsable, Section, Table, Tabs } from '../components/ui'
import DsBadge from '../components/ui/StatusBadge'
import { POLL_FREQUENT_MS } from '../constants/timings'
import './M365Page.css'

/** El resultado o el error que se pinta en su lugar. */
type CalendarPullResult = Partial<CalendarioM365Leido> & { error?: string }
type MilestonePushResult = Partial<HitosEnCalendarioM365> & { error?: string }
type Pestana = 'calendar' | 'teams' | 'config'

interface ApiErrorLike {
  response?: { data?: { detail?: string } }
}

function detalleDeError(e: unknown, porDefecto: string): string {
  const d = (e as ApiErrorLike)?.response?.data?.detail
  return typeof d === 'string' && d ? d : porDefecto
}

function EstadoConexion({ ok, label }: { ok?: boolean; label: string }) {
  return <DsBadge kind={ok ? 'success' : 'neutral'} dot caps={false}>{label}</DsBadge>
}

function Aviso({ tipo, children }: { tipo: 'ok' | 'error'; children: ReactNode }) {
  return (
    <div className={`m365-aviso m365-aviso--${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {tipo === 'ok' ? <CheckCircle2 size={15} aria-hidden /> : <AlertTriangle size={15} aria-hidden />}
      <span>{children}</span>
    </div>
  )
}

function fechaHora(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function CalendarTab() {
  const t = useAppT()
  const [upn, setUpn] = useState('')
  const [days, setDays] = useState(14)
  const [synced, setSynced] = useState<CalendarPullResult | null>(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [msUpn, setMsUpn] = useState('')
  const [msDays, setMsDays] = useState(30)
  const [msResult, setMsResult] = useState<MilestonePushResult | null>(null)
  const [msLoading, setMsLoading] = useState(false)

  const pullCalendar = async () => {
    setSyncLoading(true)
    try {
      setSynced((await m365Api.syncCalendar(upn, days)).data)
    } catch (e: unknown) {
      setSynced({ error: detalleDeError(e, t('pagina_m365.error_al_conectar_con_microsoft_graph')) })
    } finally {
      setSyncLoading(false)
    }
  }

  const pushMilestones = async () => {
    setMsLoading(true)
    try {
      setMsResult((await m365Api.syncMilestones({ user_upn: msUpn, days_ahead: msDays })).data)
    } catch (e: unknown) {
      setMsResult({ error: detalleDeError(e, t('pagina_m365.error_al_sincronizar_milestones')) })
    } finally {
      setMsLoading(false)
    }
  }

  return (
    <div className="u-stack-16">
      <Card>
        <Section title={<span className="m365-titulo"><CalendarDays size={16} aria-hidden />{t('m365.pull_eventos_de_calendario')}</span>}>
          <div className="m365-fila">
            <Input label={t('m365.upn_del_usuario_usuario_empresa_com')} value={upn}
              onChange={e => setUpn(e.target.value)} placeholder={t('pagina_m365.usuario_empresa_com')} />
            <Input label={t('m365.dias')} type="number" value={days} onChange={e => setDays(Number(e.target.value))} />
            <Button icon={<RefreshCw size={14} />} onClick={pullCalendar} disabled={!upn} loading={syncLoading}>
              {syncLoading ? t('pagina_m365.sincronizando') : t('pagina_m365.pull_eventos')}
            </Button>
          </div>
          {synced && !synced.error && (
            <div className="u-stack-8">
              <Aviso tipo="ok">{synced.pulled} {t('pagina_m365.evento_s_encontrados')}</Aviso>
              <ul className="m365-eventos">
                {(synced.events || []).map((ev, i) => (
                  <li key={i} className="m365-evento">
                    <span className="m365-evento__asunto">{ev.subject}</span>
                    <span className="m365-evento__cuando">{fechaHora(ev.start?.dateTime)} – {fechaHora(ev.end?.dateTime)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {synced?.error && <Aviso tipo="error">{synced.error}</Aviso>}
        </Section>
      </Card>

      <Card>
        <Section title={<span className="m365-titulo"><CalendarPlus size={16} aria-hidden />{t('pagina_m365.sincronizar_milestones_calendario')}</span>}>
          <div className="m365-fila">
            <Input label={t('pagina_m365.calendario_destino_upn')} value={msUpn}
              onChange={e => setMsUpn(e.target.value)} placeholder={t('pagina_m365.usuario_empresa_com')} />
            <Input label={t('m365.dias')} type="number" value={msDays} onChange={e => setMsDays(Number(e.target.value))} />
            <Button icon={<Send size={14} />} onClick={pushMilestones} disabled={!msUpn} loading={msLoading}>
              {msLoading ? t('pagina_m365.creando_eventos') : t('pagina_m365.push_milestones')}
            </Button>
          </div>
          {msResult && !msResult.error && (
            <Aviso tipo="ok">
              {msResult.created} {t('pagina_m365.milestones_sincronizados')}
              {(msResult.errors?.length ?? 0) > 0 && <> · {t('pagina_m365.n_errores', { n: msResult.errors?.length ?? 0 })}</>}
            </Aviso>
          )}
          {msResult?.error && <Aviso tipo="error">{msResult.error}</Aviso>}
        </Section>
      </Card>
    </div>
  )
}

// Colores de marca de Microsoft que se envían tal cual a la tarjeta de Teams
// (no son colores de la interfaz, por eso no son tokens del producto).
// https://learn.microsoft.com/microsoftteams/platform/task-modules-and-cards/cards/cards-format
const TEAMS_BRAND_PRESETS = ['0078D4', 'FF0000', 'FF8C00', '107C10', '5C2D91']

function TeamsTab() {
  const t = useAppT()
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [color, setColor] = useState(TEAMS_BRAND_PRESETS[0])
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok?: boolean; error?: string } | null>(null)

  const sendNotif = async () => {
    setSending(true)
    setResult(null)
    try {
      await m365Api.teamsNotify({ title, text, color })
      setResult({ ok: true })
    } catch (e: unknown) {
      setResult({ error: detalleDeError(e, t('pagina_m365.error_enviando_a_teams')) })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="u-stack-16">
      <Card>
        <Section title={<span className="m365-titulo"><MessageSquare size={16} aria-hidden />{t('m365.enviar_notificacion_a_teams')}</span>}>
          <div className="u-stack-12">
            <Input label={t('m365.titulo')} value={title} onChange={e => setTitle(e.target.value)} placeholder={t('m365.titulo_de_la_notificacion')} />
            <div className="ui-field">
              <label htmlFor="m365-mensaje" className="uiinde-estiloetiqueta">{t('pagina_m365.mensaje')}</label>
              <textarea id="m365-mensaje" value={text} onChange={e => setText(e.target.value)} className="ds-input m365-textarea" rows={3} placeholder={t('m365.texto_del_mensaje')} />
            </div>
            <div className="ui-field">
              <label htmlFor="m365-color" className="uiinde-estiloetiqueta">{t('m365.color_hex_sin')}</label>
              <div className="u-row-center-8">
                <input id="m365-color" value={color} onChange={e => setColor(e.target.value)} className="ds-input m365-color ds-campo-codigo" placeholder="0078D4" />
                {TEAMS_BRAND_PRESETS.map(c => (
                  <Pulsable key={c} onClick={() => setColor(c)}
                    aria-label={t('pagina_m365.color_de_marca_teams', { c })} title={t('pagina_m365.color_de_marca_teams', { c })}
                    aria-pressed={color === c}
                    className="m365-muestra" style={{ '--m365-muestra': `#${c}` } as CSSProperties}>{null}</Pulsable>
                ))}
              </div>
            </div>
            <div>
              <Button icon={<Send size={14} />} onClick={sendNotif} disabled={!title || !text} loading={sending}>
                {sending ? t('pagina_m365.enviando') : t('pagina_m365.enviar_a_teams')}
              </Button>
            </div>
            {result?.ok && <Aviso tipo="ok">{t('m365.notificacion_enviada_correctamente')}</Aviso>}
            {result?.error && <Aviso tipo="error">{result.error}</Aviso>}
          </div>
        </Section>
      </Card>

      <Card>
        <Section title={<span className="m365-titulo"><Settings size={16} aria-hidden />{t('m365.notificaciones_automaticas')}</span>}
          subtitle={t('m365.configura_contecflow_para_enviar_automaticamente_notificaciones_a')}>
          <ul className="m365-lista">
            <li>{t('m365.un_milestone_esta_proximo_3_dias')}</li>
            <li>{t('m365.un_ticket_critico_se_abre_en_el')}</li>
            <li>{t('m365.el_presupuesto_supera_el_90')}</li>
            <li>{t('m365.una_aprobacion_queda_pendiente_por_mas_de')}</li>
          </ul>
          <p className="m365-nota">
            {t('m365.estas_se_activan_via_las')} <strong>{t('pagina_m365.automatizaciones')}</strong> {t('m365.o_mediante_el_endpoint')} <code className="ds-codigo">POST {apiUrl('/m365/teams/notify-project')}</code>.
          </p>
        </Section>
      </Card>
    </div>
  )
}

function ConfigTab({ status }: { status?: EstadoM365 | null }) {
  const t = useAppT()
  const envVars = [
    { key: 'AZURE_TENANT_ID', label: t('pagina_m365.tenant_id_de_azure_ad'), ok: status?.required_env_vars?.AZURE_TENANT_ID },
    { key: 'AZURE_CLIENT_ID', label: t('pagina_m365.client_id_app_id'), ok: status?.required_env_vars?.AZURE_CLIENT_ID },
    { key: 'AZURE_CLIENT_SECRET', label: t('pagina_m365.client_secret'), ok: status?.required_env_vars?.AZURE_CLIENT_SECRET },
    { key: 'TEAMS_WEBHOOK_URL', label: t('pagina_m365.teams_incoming_webhook_url'), ok: status?.required_env_vars?.TEAMS_WEBHOOK_URL },
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
      <Card>
        <Section title={t('m365.estado_de_la_integracion')}>
          <div className="u-wrap-8">
            {envVars.map(v => <EstadoConexion key={v.key} ok={v.ok} label={v.label} />)}
          </div>
        </Section>
      </Card>

      <Card>
        <Section title={t('m365.guia_de_configuracion')}>
          <ol className="m365-pasos">
            {steps.map(s => (
              <li key={s.n} className="m365-paso">
                <span className="m365-paso__n" aria-hidden>{s.n}</span>
                <div className="u-stack-6 u-min0">
                  <span className="m365-paso__titulo">{s.title}</span>
                  <span className="m365-paso__desc">{s.desc}</span>
                  {s.code && <pre className="ds-codigo m365-codigo">{s.code}</pre>}
                </div>
              </li>
            ))}
          </ol>
        </Section>
      </Card>

      <Card>
        <Section title={t('pagina_m365.permisos_graph_requeridos')}>
          <Table
            data={[
              { perm: 'Calendars.ReadWrite', type: 'Application', desc: t('pagina_m365.leer_escribir_calendarios_de_todos_los') },
              { perm: 'User.Read.All', type: 'Application', desc: t('pagina_m365.leer_perfiles_de_usuario_para_buscar') },
              { perm: 'ChannelMessage.Send', type: 'Application', desc: t('pagina_m365.enviar_mensajes_a_canales_de_teams') },
            ]}
            columns={[
              { key: 'perm', label: t('pagina_m365.permiso'), render: (_v, r) => <code className="ds-codigo m365-permiso">{r.perm}</code> },
              { key: 'type', label: t('pagina_m365.tipo'), render: (_v, r) => <span className="u-text2">{r.type}</span> },
              { key: 'desc', label: t('pagina_m365.funcionalidad'), render: (_v, r) => <span className="u-text2">{r.desc}</span> },
            ]}
          />
        </Section>
      </Card>
    </div>
  )
}

export default function M365Page() {
  const t = useAppT()
  const [activeTab, setTab] = useState<Pestana>('calendar')

  const { data: status } = useQuery<EstadoM365>({
    queryKey: ['m365-status'],
    queryFn: () => m365Api.status().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const graphOk = status?.graph_configured
  const teamsOk = status?.teams_webhook_configured
  const estado = (ok?: boolean) => (ok ? t('pagina_m365.activo') : t('pagina_m365.no_configurado'))

  return (
    <PageShell>
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title={t('pagina_m365.microsoft_365')}
        subtitle={t('pagina_m365.integracion_con_graph_api_y_microsoft')}
      />

      <div className="u-stack-16">
      <div className="u-wrap-center-8">
        <EstadoConexion ok={graphOk} label={t('pagina_m365.graph_api', { v1: estado(graphOk) })} />
        <EstadoConexion ok={teamsOk} label={t('pagina_m365.teams_webhook', { v1: estado(teamsOk) })} />
        {!graphOk && <span className="m365-pista">{t('m365.pestana_configuracion_para_el_setup')}</span>}
      </div>

      <Tabs
        ariaLabel={t('pagina_m365.microsoft_365')}
        active={activeTab}
        onChange={id => setTab(id as Pestana)}
        items={[
          { id: 'calendar', label: t('pagina_m365.calendario'), icon: <CalendarDays size={14} /> },
          { id: 'teams', label: t('pagina_m365.teams'), icon: <MessageSquare size={14} /> },
          { id: 'config', label: t('pagina_m365.configuracion'), icon: <Settings size={14} /> },
        ]}
      />

      {activeTab === 'calendar' && <CalendarTab />}
      {activeTab === 'teams' && <TeamsTab />}
      {activeTab === 'config' && <ConfigTab status={status} />}
      </div>
    </PageShell>
  )
}
