import { useEffect, useState, useId } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings2, RefreshCw, ArrowDownToLine,
  ArrowUpFromLine, Link2, Eye, EyeOff, AlertTriangle,
} from 'lucide-react'
import { jiraApi } from '../services/api'
import { apiUrlAbsoluta } from '../services/api/urls'
import { useAuth } from '../context/AuthContext'
import { useConfirm } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { Card, Button, Spinner, EmptyState, Table, StatusBadge as DsBadge, ProjectSelect } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { extractErr, localeActivo } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'

interface JiraConfig {
  jira_url?: string
  jira_email?: string
  jira_project_key?: string
  token_hint?: string
}

interface JiraIssue {
  key: string
  summary?: string
  status?: string
  priority?: string
}

interface JiraLinkedTask {
  id: string | number
  title?: string
  jira_issue_key?: string
  status?: string
  jira_synced_at?: string
}

interface JiraSyncResult {
  created?: number
  updated?: number
}


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

const _fs: CSSProperties = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const _ls: CSSProperties = {
  fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)',
  textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5,
}

// ── sub-components ────────────────────────────────────────────────────────────
function EstadoDeConexion({ ok, t }: { ok?: boolean; t: (clave: string) => string }) {
  // Auditoria 2026-11 (#41): era un badge hecho a mano; ahora el del kit.
  if (ok == null) return null
  return ok
    ? <DsBadge kind="success" dot caps={false}>{t('jira_integration.connected_status')}</DsBadge>
    : <DsBadge kind="danger" dot caps={false}>{t('jira_integration.disconnected_status')}</DsBadge>
}

function SectionTitle({ children }: { children?: React.ReactNode }) {
  return (
    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 14 }}>
      {children}
    </div>
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
    onError: (e: unknown) => toast.error(extractErr(e, 'No se pudo generar el secreto del webhook')),
  })
  if (!hasRole('admin')) return null
  const copiar = (texto: string) => {
    void navigator.clipboard?.writeText(texto).then(() => toast.success('Copiado'), () => toast.error('No se pudo copiar'))
  }
  const generar = async () => {
    const ok = await confirmar({
      title: 'Generar secreto del webhook',
      message: 'Se crea un secreto nuevo y el anterior deja de valer: Jira no podrá avisar hasta que pegues el nuevo en su configuración. Se muestra una sola vez.',
      confirmLabel: 'Generar',
      danger: true,
    })
    if (ok) rotar.mutate()
  }
  const caja: CSSProperties = { display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }
  const codigo: CSSProperties = { flex: 1, minWidth: 0, overflowX: 'auto', whiteSpace: 'nowrap', padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }
  return (
    <div style={{ marginTop: 12 }}>
      <Button variant="secondary" size="sm" onClick={() => void generar()} loading={rotar.isPending}>
        Generar secreto del webhook
      </Button>
      {datos && (
        <div role="status" style={{ marginTop: 10, padding: '10px 12px', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
          <div className="u-text2-xs">URL del webhook a configurar en Jira</div>
          <div style={caja}><code style={codigo}>{datos.url}</code><Button size="xs" variant="ghost" onClick={() => copiar(datos.url)}>Copiar</Button></div>
          <div className="u-text2-xs" style={{ marginTop: 8 }}>Secreto (cabecera <code>{datos.header}</code>). Solo se muestra ahora.</div>
          <div style={caja}><code style={codigo}>{datos.secret}</code><Button size="xs" variant="ghost" onClick={() => copiar(datos.secret)}>Copiar</Button></div>
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
  const { data: config, isLoading: loadingConfig } = useQuery<JiraConfig>({
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

  const { data: issues, isLoading: loadingIssues } = useQuery<JiraIssue[]>({
    queryKey: ['jira-issues'],
    queryFn:  () => jiraApi.issues().then(r => r.data),
    enabled:  connStatus === true,
  })

  const { data: linked, isLoading: loadingLinked } = useQuery<JiraLinkedTask[]>({
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
      else toast.error(d.error || t('jira_integration.connection_error'))
    },
    onError: () => { setConnStatus(false); toast.error(t('jira_integration.connection_error')) },
  })

  const syncPull = useMutation({
    mutationFn: (payload: Record<string, never>) => jiraApi.sync(payload).then(r => r.data as JiraSyncResult),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['jira-linked'] })
      toast.success(`${t('jira_integration.sync_complete')} ${d.created} ${t('jira_integration.created')}, ${d.updated} ${t('jira_integration.updated')}`)
    },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.sync_error'))),
  })

  const [proyectoPush, setProyectoPush] = useState('')
  const pushToJira = useMutation({
    // Auditoria 2026-11: se enviaba sin cuerpo (422: falta project_id) y se leia
    // `d.pushed`, que el backend no devuelve (es `created`).
    mutationFn: () => jiraApi.push({ project_id: proyectoPush, jira_project_key: form.jira_project_key || undefined }).then(r => r.data),
    onSuccess: (d) => {
      if (d?.status === 'queued') {
        toast.success('Envío a Jira en curso: las tareas aparecerán vinculadas en unos minutos.')
        setTimeout(() => qc.invalidateQueries({ queryKey: ['jira-linked'] }), 30000)
        return
      }
      qc.invalidateQueries({ queryKey: ['jira-linked'] })
      toast.success(`${t('jira_integration.push_complete')} ${d?.created ?? 0} ${t('jira_integration.tasks_pushed')}`)
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

  // Normaliza ambas formas: array crudo vs {issues, total} / {tasks, count}
  const issueList = Array.isArray(issues) ? issues : []
  const linkedList = Array.isArray(linked) ? linked : []
  const issueCount = issueList.length
  const linkedCount = linkedList.length

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <PageShell>
      <PageHeader
        icon={<Link2 size={18} />}
        title={t('jira_integration.title')}
        subtitle={t('jira_integration.subtitle')}
        actions={<EstadoDeConexion ok={connStatus ?? undefined} t={t} />}
      showListExport={false}
      />

      <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) minmax(0, 2fr)', gap: 20 }}>

        {/* ── left: configuration + sync actions ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>

          {/* Configuration */}
          <Card>
            <SectionTitle>{t('jira_integration.configuration_section')}</SectionTitle>
            {loadingConfig ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
            ) : (
              <form onSubmit={handleSave} className="u-stack-12">
                <div>
                  <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={_ls}>{t('jira_integration.url_label')}</label>
                  <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
                    type="url"
                    placeholder={t('jira_integration.url_placeholder')}
                    value={form.jira_url}
                    onChange={e => setForm(p => ({ ...p, jira_url: e.target.value }))}
                    style={_fs}
                  />
                </div>
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={_ls}>{t('jira_integration.email_label')}</label>
                  <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`}
                    type="email"
                    autoComplete="email"
                    placeholder={t('jira_integration.email_placeholder')}
                    value={form.jira_email}
                    onChange={e => setForm(p => ({ ...p, jira_email: e.target.value }))}
                    style={_fs}
                  />
                </div>
                <div>
                  <label style={_ls}>{t('jira_integration.token_label')}</label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showToken ? 'text' : 'password'}
                      autoComplete="current-password"
                      placeholder={config?.token_hint ? `\u2022\u2022\u2022\u2022\u2022\u2022${config.token_hint}` : t('jira_integration.token_placeholder')}
                      value={form.jira_api_token}
                      onChange={e => setForm(p => ({ ...p, jira_api_token: e.target.value }))}
                      style={{ ..._fs, paddingRight: 36 }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken(v => !v)}
                      style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: 0 }}
                    >
                      {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={_ls}>{t('jira_integration.project_key_label')}</label>
                  <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`}
                    type="text"
                    placeholder={t('jira_integration.project_key_placeholder')}
                    value={form.jira_project_key}
                    onChange={e => setForm(p => ({ ...p, jira_project_key: e.target.value.toUpperCase() }))}
                    style={{ ..._fs, textTransform: 'uppercase' }}
                  />
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingTop: 4 }}>
                  <Button type="submit" loading={saveConfig.isPending} icon={<Settings2 size={13} />} style={{ flex: 1 }}>
                    {t('jira_integration.save_button')}
                  </Button>
                  <Button
                    variant="secondary"
                    loading={testConn.isPending}
                    onClick={() => testConn.mutate()}
                    icon={<RefreshCw size={13} />}
                    style={{ flex: 1 }}
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
              <button
                onClick={() => syncPull.mutate({})}
                disabled={syncPull.isPending}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                  background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)',
                  borderRadius: 'var(--radius-md)', cursor: syncPull.isPending ? 'not-allowed' : 'pointer',
                  opacity: syncPull.isPending ? 0.5 : 1, width: '100%', textAlign: 'left',
                }}
              >
                {syncPull.isPending
                  ? <Spinner size={16} />
                  : <ArrowDownToLine size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                }
                <div>
                  <div className="u-text1-base-600">{t('jira_integration.import_button_title')}</div>
                  <div className="u-text3-xs">{t('jira_integration.import_button_subtitle')}</div>
                </div>
              </button>
              <ProjectSelect value={proyectoPush} onChange={(id) => setProyectoPush(id)} placeholder="Proyecto a enviar a Jira…" />
              <button
                onClick={() => pushToJira.mutate()}
                disabled={pushToJira.isPending || !proyectoPush}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                  background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.2)',
                  borderRadius: 'var(--radius-md)', cursor: pushToJira.isPending ? 'not-allowed' : 'pointer',
                  opacity: pushToJira.isPending ? 0.5 : 1, width: '100%', textAlign: 'left',
                }}
              >
                {pushToJira.isPending
                  ? <Spinner size={16} />
                  : <ArrowUpFromLine size={16} style={{ color: 'var(--purple)', flexShrink: 0 }} />
                }
                <div>
                  <div className="u-text1-base-600">{t('jira_integration.export_button_title')}</div>
                  <div className="u-text3-xs">{t('jira_integration.export_button_subtitle')}</div>
                </div>
              </button>
            </div>
            <div style={{
              marginTop: 12, padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'flex-start',
              background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 8,
            }}>
              <AlertTriangle size={14} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 1 }} />
              <p style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', margin: 0, lineHeight: 1.5 }}>
                {t('jira_integration.webhook_note')}{' '}
                <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: "var(--text-xs)" }}>/jira/webhook</code>{' '}
                {t('jira_integration.webhook_note_end')}
              </p>
            </div>
            <SecretoDelWebhook />
          </Card>
        </div>

        {/* ── right: issues + linked tasks ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>

          {/* Jira issues */}
          <Card>
            <SectionTitle>{t('jira_integration.issues_section_title')} {issueCount > 0 && `(${issueCount})`}</SectionTitle>
            {!connStatus ? (
              <EmptyState icon="search" title={t('jira_integration.no_connection_title')} description={t('jira_integration.no_connection_message')} />
            ) : loadingIssues ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
            ) : issueList.length === 0 ? (
              <EmptyState icon="tasks" title={t('jira_integration.no_issues_title')} description={t('jira_integration.no_issues_message')} />
            ) : (
              <div className="u-scroll-x">
                <Table
                  data={issueList}
                  columns={[
                    { key: 'key', label: t('jira_integration.col_key'), render: (_v, issue) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: "var(--text-sm)", whiteSpace: 'nowrap' }}>{issue.key}</span> },
                    { key: 'summary', label: t('jira_integration.col_summary'), render: (_v, issue) => <span style={{ display: 'block', maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.summary}</span> },
                    { key: 'status', label: t('jira_integration.col_status'), render: (_v, issue) => (
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                        {issue.status}
                      </span>
                    ) },
                    { key: 'priority', label: t('jira_integration.col_priority'), render: (_v, issue) => (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: PRIORITY_COLORS[issue.priority?.toLowerCase() as keyof typeof PRIORITY_COLORS] || 'var(--surface-5)', flexShrink: 0 }} />
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
              <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
            ) : linkedList.length === 0 ? (
              <EmptyState icon="tasks" title={t('jira_integration.no_linked_title')} description={t('jira_integration.no_linked_message')} />
            ) : (
              <div className="u-scroll-x">
                <Table
                  data={linkedList}
                  columns={[
                    { key: 'title', label: t('jira_integration.col_task') },
                    { key: 'jira_issue_key', label: t('jira_integration.col_jira_key'), render: (_v, row) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: "var(--text-sm)" }}>{row.jira_issue_key}</span> },
                    { key: 'status', label: t('jira_integration.col_status'), render: (_v, row) => (
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                        {row.status}
                      </span>
                    ) },
                    { key: 'jira_synced_at', label: t('jira_integration.col_synced'), render: (_v, row) => (
                      <span className="u-text3-sm">
                        {row.jira_synced_at ? new Date(row.jira_synced_at).toLocaleString(localeActivo()) : '—'}
                      </span>
                    ) },
                  ]}
                />
              </div>
            )}
          </Card>
        </div>
      </div>
    </PageShell>
  )
}
