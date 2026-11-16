import { useAppLang } from '../i18n/AppLangContext'
import { useEffect, useState, useId } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings2, RefreshCw, ArrowDownToLine,
  ArrowUpFromLine, Link2, Eye, EyeOff, AlertTriangle, ListChecks, Search, Unplug,
} from 'lucide-react'
import { jiraApi } from '../services/api'
import type { ConfigJira, IssueDeJira, TareaVinculadaAJira } from '../services/api/tipos-plataforma'
import { apiUrlAbsoluta } from '../services/api/urls'
import { useAuth } from '../context/AuthContext'
import { useConfirm } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { Card, Button, Spinner, EmptyState, Table, StatusBadge as DsBadge, ProjectSelect, Page, IconButton } from '../components/ui'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { DELAYED_REFETCH_MS } from '../constants/timings'
import './JiraIntegrationPage.css'

interface JiraFormState {
  jira_url: string
  jira_email: string
  jira_api_token: string
  jira_project_key: string
}

// ── helpers ───────────────────────────────────────────────────────────────────
const PRIORITY_COLORS = {
  blocker:  'var(--danger)',
  critical: 'var(--danger)',
  high:     'var(--warning)',
  medium:   'var(--accent)',
  low:      'var(--success)',
}


// ── sub-components ────────────────────────────────────────────────────────────
function EstadoDeConexion({ ok, t }: { ok?: boolean; t: (clave: string) => string }) {
  // Auditoria 2026-11 (#41): era un badge hecho a mano; ahora el del kit.
  if (ok == null) return null
  return ok
    ? <DsBadge kind="success" dot caps={false}>{t('jira_integration.connected_status')}</DsBadge>
    : <DsBadge kind="danger" dot caps={false}>{t('jira_integration.disconnected_status')}</DsBadge>
}

/** Título de sección: el mismo que <Section> (16-11-2026: antes en versalitas grandes). */
function SectionTitle({ children }: { children?: React.ReactNode }) {
  return (
    <h3 className="ds-section__title jira-box">
      {children}
    </h3>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────
/**
 * Secreto del webhook de Jira (auditoria 2026-11, #14). Es por organizacion y
 * solo lo genera un admin; el servidor lo ensena UNA vez, asi que aqui se
 * muestra con boton de copiar hasta salir de la pantalla. Generar otro invalida
 * el anterior (Jira dejaria de autenticar hasta pegar el nuevo).
 */
function SecretoDelWebhook() {
  const { t } = useAppLang()
  const { hasRole } = useAuth()
  const { confirmar } = useConfirm()
  const toast = useToast()
  const [datos, setDatos] = useState<{ secret: string; header: string; url: string } | null>(null)
  const rotar = useMutation({
    mutationFn: () => jiraApi.rotarSecretoWebhook().then(r => r.data),
    onSuccess: (d) => {
      const ruta = (d.webhook_paths?.[0] || '/api/v1/jira/webhook').replace(/^\/api\/v1/, '')
      setDatos({ secret: d.secret, header: d.header || 'X-Atlassian-Webhook-Token', url: apiUrlAbsoluta(ruta) })
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_jira.no_se_pudo_generar_el_secreto'))),
  })
  if (!hasRole('admin')) return null
  const copiar = (texto: string) => {
    void navigator.clipboard?.writeText(texto).then(() => toast.success(t('pagina_jira.copiado')), () => toast.error(t('pagina_jira.no_se_pudo_copiar')))
  }
  const generar = async () => {
    const ok = await confirmar({
      title: t('pagina_jira.generar_secreto_del_webhook'),
      message: t('pagina_jira.se_crea_un_secreto_nuevo_y'),
      confirmLabel: t('pagina_jira.generar'),
      danger: true,
    })
    if (ok) rotar.mutate()
  }

  return (
    <div className="jira-box-2">
      <Button variant="secondary" size="sm" onClick={() => void generar()} loading={rotar.isPending}>
        {t('pagina_jira.generar_secreto_del_webhook')}
      </Button>
      {datos && (
        <div role="status" className="jira-card">
          <div className="u-text2-xs">{t('pagina_jira.url_del_webhook_a_configurar_en')}</div>
          <div className="jira-integration-page-e4"><code className="jira-integration-page-e5">{datos.url}</code><Button size="xs" variant="ghost" onClick={() => copiar(datos.url)}>{t('pagina_jira.copiar')}</Button></div>
          <div className="u-text2-xs jira-box-3">{t('pagina_jira.secreto_cabecera')}{' '}<code>{datos.header}</code>{t('pagina_jira.solo_se_muestra_ahora')}</div>
          <div className="jira-integration-page-e4"><code className="jira-integration-page-e5">{datos.secret}</code><Button size="xs" variant="ghost" onClick={() => copiar(datos.secret)}>{t('pagina_jira.copiar')}</Button></div>
        </div>
      )}
    </div>
  )
}

export default function JiraIntegrationPage(): JSX.Element {
  const idCampo = useId()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()

  const [form, setForm] = useState<JiraFormState>({ jira_url: '', jira_email: '', jira_api_token: '', jira_project_key: '' })
  const [showToken, setShowToken] = useState(false)
  const [connStatus, setConnStatus] = useState<boolean | null>(null)

  // ── queries ────────────────────────────────────────────────────────────────
  const { data: config, isLoading: loadingConfig } = useQuery<ConfigJira>({
    queryKey: ['jira-config'],
    queryFn:  () => jiraApi.config().then(r => r.data),
  })

  useEffect(() => {
    if (!config) return
    setForm((prev) => ({
      ...prev,
      jira_url: config.jira_url || '',
      jira_email: config.jira_email || '',
      jira_project_key: config.jira_project_key || '',
    }))
  }, [config])

  // GET /jira/issues devuelve `{total, issues}` (antes se leia como lista y la tabla salia siempre vacia).
  const { data: issues, isLoading: loadingIssues } = useQuery<IssueDeJira[]>({
    queryKey: ['jira-issues'],
    queryFn:  () => jiraApi.issues().then(r => r.data.issues),
    enabled:  connStatus === true,
  })

  const { data: linked, isLoading: loadingLinked } = useQuery<TareaVinculadaAJira[]>({
    queryKey: ['jira-linked'],
    queryFn:  () => jiraApi.linked().then(r => r.data),
  })

  // ── mutations ──────────────────────────────────────────────────────────────
  const saveConfig = useMutation({
    // El token es opcional **al guardar**: si no se escribe uno nuevo la clave
    // no viaja, para no pisar el que ya hay guardado. La firma decia
    // `JiraFormState` entero, que es la forma del formulario y no la del
    // payload, y por eso el `delete` de mas abajo tuvo que existir.
    mutationFn: (payload: Omit<JiraFormState, 'jira_api_token'> & { jira_api_token?: string }) =>
      jiraApi.saveConfig(payload).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['jira-config'] }); toast.success(t('jira_integration.config_saved')) },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.save_error'))),
  })

  const testConn = useMutation({
    mutationFn: () => jiraApi.test().then(r => r.data),
    onSuccess: (d) => {
      setConnStatus(d.ok)
      if (d.ok) { toast.success(`${t('jira_integration.connected_as')} ${d.display_name}`); qc.invalidateQueries({ queryKey: ['jira-issues'] }) }
      else toast.error(t('jira_integration.connection_error'))
    },
    onError: () => { setConnStatus(false); toast.error(t('jira_integration.connection_error')) },
  })

  const syncPull = useMutation({
    // JiraSyncIn deja `project_id` opcional, pero sin el las issues nuevas crearian
    // tareas sin proyecto (`tasks.project_id` es NOT NULL): se pide el proyecto.
    mutationFn: (payload: { project_id: string }) => jiraApi.sync(payload).then(r => r.data),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['jira-linked'] })
      toast.success(t('jira_integration.sync_resumen', { created: d.created, updated: d.updated }))
    },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.sync_error'))),
  })

  const [proyectoPush, setProyectoPush] = useState('')
  const pushToJira = useMutation({
    // Auditoria 2026-11: se enviaba sin cuerpo (422: falta project_id) y se leia
    // `d.pushed`, que el backend no devuelve (es `created`).
    mutationFn: () => jiraApi.push({ project_id: proyectoPush, jira_project_key: form.jira_project_key || undefined }).then(r => r.data),
    onSuccess: (d) => {
      if ('status' in d) {
        toast.success(t('pagina_jira.envio_a_jira_en_curso_las'))
        setTimeout(() => qc.invalidateQueries({ queryKey: ['jira-linked'] }), DELAYED_REFETCH_MS)
        return
      }
      qc.invalidateQueries({ queryKey: ['jira-linked'] })
      toast.success(t('jira_integration.push_resumen', { n: d.created }))
    },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.push_error'))),
  })

  // ── handlers ───────────────────────────────────────────────────────────────
  const handleSave = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!form.jira_url || !form.jira_email || !form.jira_project_key) {
      toast.error(t('jira_integration.required_fields_error'))
      return
    }
    // Sin token nuevo no se manda la clave: mandar cadena vacia borraria el
    // token guardado, que es justo lo contrario de «dejalo como esta».
    const { jira_api_token, ...resto } = form
    saveConfig.mutate({ ...resto, ...(jira_api_token ? { jira_api_token } : {}) })
  }

  const issueList = issues ?? []
  const linkedList = linked ?? []
  const issueCount = issueList.length
  const linkedCount = linkedList.length

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <Page
      icon={<Link2 size={18} />}
      title={t('nav.jira_integration')}
      subtitle={t('jira_integration.subtitle')}
      actions={<EstadoDeConexion ok={connStatus ?? undefined} t={t} />}
    >

      <div className={`jira-grid ${isNarrow ? 'jirainte-sx2' : 'jirainte-sx3'}`}>

        {/* ── left: configuration + sync actions ── */}
        <div className="jira-stack">

          {/* Configuration */}
          <Card>
            <SectionTitle>{t('jira_integration.configuration_section')}</SectionTitle>
            {loadingConfig ? (
              <div className="jira-row"><Spinner /></div>
            ) : (
              <form onSubmit={handleSave} className="u-stack-12">
                <div>
                  <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="jira-integration-page-e6">{t('jira_integration.url_label')}</label>
                  <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
                    type="url"
                    placeholder={t('jira_integration.url_placeholder')}
                    value={form.jira_url}
                    onChange={e => setForm(p => ({ ...p, jira_url: e.target.value }))}
                    className="jira-integration-page-e7"
                  />
                </div>
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="jira-integration-page-e6">{t('jira_integration.email_label')}</label>
                  <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`}
                    type="email"
                    autoComplete="email"
                    placeholder={t('jira_integration.email_placeholder')}
                    value={form.jira_email}
                    onChange={e => setForm(p => ({ ...p, jira_email: e.target.value }))}
                    className="jira-integration-page-e7"
                  />
                </div>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="jira-integration-page-e6">{t('jira_integration.token_label')}</label>
                  <div className="jira-box-4">
                    <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`}
                      type={showToken ? 'text' : 'password'}
                      autoComplete="current-password"
                      placeholder={config?.jira_api_token_hint || t('jira_integration.token_placeholder')}
                      value={form.jira_api_token}
                      onChange={e => setForm(p => ({ ...p, jira_api_token: e.target.value }))}
                      className="jira-integration-page-e1"
                    />
                    <IconButton
                      onClick={() => setShowToken(v => !v)}
                      ariaLabel={showToken ? t('pagina_jira.ocultar_token') : t('pagina_jira.mostrar_token')}
                      aria-pressed={showToken}
                      className="jira-btn"
                    >
                      {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
                    </IconButton>
                  </div>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="jira-integration-page-e6">{t('jira_integration.project_key_label')}</label>
                  <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`}
                    type="text"
                    placeholder={t('jira_integration.project_key_placeholder')}
                    value={form.jira_project_key}
                    onChange={e => setForm(p => ({ ...p, jira_project_key: e.target.value.toUpperCase() }))}
                    className="jira-integration-page-e2"
                  />
                </div>
                <div className="jira-row-2">
                  <Button type="submit" loading={saveConfig.isPending} icon={<Settings2 size={13} />} className="jirainte-sx1">
                    {t('jira_integration.save_button')}
                  </Button>
                  <Button
                    variant="secondary"
                    loading={testConn.isPending}
                    onClick={() => testConn.mutate()}
                    icon={<RefreshCw size={13} />} className="jirainte-sx1"
                  >
                    {t('jira_integration.test_button')}
                  </Button>
                </div>
              </form>
            )}
          </Card>

          {/* Sync actions */}
          <Card>
            <SectionTitle>{t('jira_integration.sync_actions_section')}</SectionTitle>
            <div className="u-stack-10">
              <ProjectSelect value={proyectoPush} onChange={(id) => setProyectoPush(id)} placeholder={t('pagina_jira.proyecto_de_las_tareas')} />
              {/* 16-11-2026 (pasada de diseño): eran tarjetas-botón propias que,
                  desactivadas, quedaban casi ilegibles. */}
              <div className="jira-accion">
                <Button variant="secondary" icon={<ArrowDownToLine size={14} />} loading={syncPull.isPending}
                  disabled={!proyectoPush} onClick={() => syncPull.mutate({ project_id: proyectoPush })}>
                  {t('jira_integration.import_button_title')}
                </Button>
                <span className="u-text2-xs">{t('jira_integration.import_button_subtitle')}</span>
              </div>
              <div className="jira-accion">
                <Button variant="secondary" icon={<ArrowUpFromLine size={14} />} loading={pushToJira.isPending}
                  disabled={!proyectoPush} onClick={() => pushToJira.mutate()}>
                  {t('jira_integration.export_button_title')}
                </Button>
                <span className="u-text2-xs">{t('jira_integration.export_button_subtitle')}</span>
              </div>
            </div>
            <div className="jira-row-3">
              <AlertTriangle size={14} className="jira-box-8" />
              <p className="jira-text">
                {t('jira_integration.webhook_note')}{' '}
                <code className="jira-box-5">/jira/webhook</code>{' '}
                {t('jira_integration.webhook_note_end')}
              </p>
            </div>
            <SecretoDelWebhook />
          </Card>
        </div>

        {/* ── right: issues + linked tasks ── */}
        <div className="jira-stack">

          {/* Jira issues */}
          <Card>
            <SectionTitle>{t('jira_integration.issues_section_title')} {issueCount > 0 && `(${issueCount})`}</SectionTitle>
            {!connStatus ? (
              <EmptyState icon={<Unplug size={28} />} title={t('jira_integration.no_connection_title')} description={t('jira_integration.no_connection_message')} />
            ) : loadingIssues ? (
              <div className="jira-row-4"><Spinner /></div>
            ) : issueList.length === 0 ? (
              <EmptyState icon={<Search size={28} />} title={t('jira_integration.no_issues_title')} description={t('jira_integration.no_issues_message')} />
            ) : (
              <div className="u-scroll-x">
                <Table
                  data={issueList}
                  columns={[
                    { key: 'key', label: t('jira_integration.col_key'), render: (_v, issue) => <span className="jira-label">{issue.key}</span> },
                    { key: 'summary', label: t('jira_integration.col_summary'), render: (_v, issue) => <span className="jira-label-2">{issue.summary}</span> },
                    { key: 'status', label: t('jira_integration.col_status'), render: (_v, issue) => (
                      <span className="jira-card-2">
                        {issue.status}
                      </span>
                    ) },
                    { key: 'priority', label: t('jira_integration.col_priority'), render: (_v, issue) => (
                      <span className="jira-row-5">
                        <span className="jira-label-3 jira-integration-page-e3" style={{ '--jira-integration-page-background': PRIORITY_COLORS[issue.priority?.toLowerCase() as keyof typeof PRIORITY_COLORS] || 'var(--surface-5)' } as CSSProperties} />
                        {issue.priority}
                      </span>
                    ) },
                  ]}
                />
              </div>
            )}
          </Card>

          {/* Linked tasks */}
          <Card>
            <SectionTitle>{t('jira_integration.linked_section_title')} {linkedCount > 0 && `(${linkedCount})`}</SectionTitle>
            {loadingLinked ? (
              <div className="jira-row-4"><Spinner /></div>
            ) : linkedList.length === 0 ? (
              <EmptyState icon={<ListChecks size={28} />} title={t('jira_integration.no_linked_title')} description={t('jira_integration.no_linked_message')} />
            ) : (
              <div className="u-scroll-x">
                <Table
                  data={linkedList}
                  columns={[
                    { key: 'title', label: t('jira_integration.col_task') },
                    { key: 'jira_issue_key', label: t('jira_integration.col_jira_key'), render: (_v, row) => <span className="jira-label-4">{row.jira_issue_key}</span> },
                    { key: 'status', label: t('jira_integration.col_status'), render: (_v, row) => (
                      <span className="jira-card-2">
                        {etiquetaCodigo(t, 'estado', row.status)}
                      </span>
                    ) },
                    { key: 'jira_synced_at', label: t('jira_integration.col_synced'), render: (_v, row) => (
                      <span className="u-text3-sm">
                        {fmtDateTime(row.jira_synced_at)}
                      </span>
                    ) },
                  ]}
                />
              </div>
            )}
          </Card>
        </div>
      </div>
    </Page>
  )
}
