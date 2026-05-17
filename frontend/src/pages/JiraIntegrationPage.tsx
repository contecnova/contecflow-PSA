import { useEffect, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings2, CheckCircle, XCircle, RefreshCw, ArrowDownToLine,
  ArrowUpFromLine, Link2, Eye, EyeOff, AlertTriangle,
} from 'lucide-react'
import { jiraApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { Card, Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

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

interface JiraPushResult {
  pushed?: number
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
function StatusBadge({ ok, t }) {
  if (ok === null) return null
  return ok
    ? (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: "var(--text-base)", color: 'var(--success)', fontWeight: 600 }}>
        <CheckCircle size={14} /> {t('jira_integration.connected_status')}
      </span>
    ) : (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: "var(--text-base)", color: 'var(--danger)', fontWeight: 600 }}>
        <XCircle size={14} /> {t('jira_integration.disconnected_status')}
      </span>
    )
}

function SectionTitle({ children }) {
  return (
    <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 14 }}>
      {children}
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function JiraIntegrationPage(): JSX.Element {
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
    mutationFn: (payload: JiraFormState) => jiraApi.saveConfig(payload).then(r => r.data),
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

  const pushToJira = useMutation({
    mutationFn: () => jiraApi.push().then(r => r.data),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['jira-linked'] })
      toast.success(`${t('jira_integration.push_complete')} ${d.pushed} ${t('jira_integration.tasks_pushed')}`)
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
    const payload = { ...form }
    if (!payload.jira_api_token) delete payload.jira_api_token
    saveConfig.mutate(payload)
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
        actions={<StatusBadge ok={connStatus} t={t} />}
      showListExport={false}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20 }}>

        {/* ── left: configuration + sync actions ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Configuration */}
          <Card>
            <SectionTitle>{t('jira_integration.configuration_section')}</SectionTitle>
            {loadingConfig ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
            ) : (
              <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={_ls}>{t('jira_integration.url_label')}</label>
                  <input
                    type="url"
                    placeholder={t('jira_integration.url_placeholder')}
                    value={form.jira_url}
                    onChange={e => setForm(p => ({ ...p, jira_url: e.target.value }))}
                    style={_fs}
                  />
                </div>
                <div>
                  <label style={_ls}>{t('jira_integration.email_label')}</label>
                  <input
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
                  <label style={_ls}>{t('jira_integration.project_key_label')}</label>
                  <input
                    type="text"
                    placeholder={t('jira_integration.project_key_placeholder')}
                    value={form.jira_project_key}
                    onChange={e => setForm(p => ({ ...p, jira_project_key: e.target.value.toUpperCase() }))}
                    style={{ ..._fs, textTransform: 'uppercase' }}
                  />
                </div>
                <div style={{ display: 'flex', gap: 8, paddingTop: 4 }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button
                onClick={() => syncPull.mutate({})}
                disabled={syncPull.isPending}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                  background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)',
                  borderRadius: 10, cursor: syncPull.isPending ? 'not-allowed' : 'pointer',
                  opacity: syncPull.isPending ? 0.5 : 1, width: '100%', textAlign: 'left',
                }}
              >
                {syncPull.isPending
                  ? <Spinner size={16} />
                  : <ArrowDownToLine size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                }
                <div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{t('jira_integration.import_button_title')}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('jira_integration.import_button_subtitle')}</div>
                </div>
              </button>
              <button
                onClick={() => pushToJira.mutate()}
                disabled={pushToJira.isPending}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                  background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.2)',
                  borderRadius: 10, cursor: pushToJira.isPending ? 'not-allowed' : 'pointer',
                  opacity: pushToJira.isPending ? 0.5 : 1, width: '100%', textAlign: 'left',
                }}
              >
                {pushToJira.isPending
                  ? <Spinner size={16} />
                  : <ArrowUpFromLine size={16} style={{ color: 'var(--purple)', flexShrink: 0 }} />
                }
                <div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{t('jira_integration.export_button_title')}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('jira_integration.export_button_subtitle')}</div>
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
          </Card>
        </div>

        {/* ── right: issues + linked tasks ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Jira issues */}
          <Card>
            <SectionTitle>{t('jira_integration.issues_section_title')} {issueCount > 0 && `(${issueCount})`}</SectionTitle>
            {!connStatus ? (
              <EmptyState icon="search" title={t('jira_integration.no_connection_title')} message={t('jira_integration.no_connection_message')} />
            ) : loadingIssues ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
            ) : issueList.length === 0 ? (
              <EmptyState icon="tasks" title={t('jira_integration.no_issues_title')} message={t('jira_integration.no_issues_message')} />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                      {[t('jira_integration.col_key'), t('jira_integration.col_summary'), t('jira_integration.col_status'), t('jira_integration.col_priority')].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '6px 10px 8px', fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {issueList.map(issue => (
                      <tr key={issue.key} style={{ borderBottom: '1px solid var(--surface-3)' }}>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: "var(--text-sm)", whiteSpace: 'nowrap' }}>{issue.key}</td>
                        <td style={{ padding: '8px 10px', color: 'var(--text-1)', maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.summary}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                            {issue.status}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: PRIORITY_COLORS[issue.priority?.toLowerCase() as keyof typeof PRIORITY_COLORS] || 'var(--surface-5)', flexShrink: 0 }} />
                            {issue.priority}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Linked tasks */}
          <Card>
            <SectionTitle>{t('jira_integration.linked_section_title')} {linkedCount > 0 && `(${linkedCount})`}</SectionTitle>
            {loadingLinked ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
            ) : linkedList.length === 0 ? (
              <EmptyState icon="tasks" title={t('jira_integration.no_linked_title')} message={t('jira_integration.no_linked_message')} />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                      {[t('jira_integration.col_task'), t('jira_integration.col_jira_key'), t('jira_integration.col_status'), t('jira_integration.col_synced')].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '6px 10px 8px', fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {linkedList.map((row) => (
                      <tr key={row.id} style={{ borderBottom: '1px solid var(--surface-3)' }}>
                        <td style={{ padding: '8px 10px', color: 'var(--text-1)' }}>{row.title}</td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: "var(--text-sm)" }}>{row.jira_issue_key}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                            {row.status}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px', fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
                          {row.jira_synced_at ? new Date(row.jira_synced_at).toLocaleString() : '\u2014'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </PageShell>
  )
}
