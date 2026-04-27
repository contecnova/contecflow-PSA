import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings2, CheckCircle, XCircle, RefreshCw, ArrowDownToLine,
  ArrowUpFromLine, Link2, Eye, EyeOff, AlertTriangle,
} from 'lucide-react'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { Card, Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

// ── helpers ───────────────────────────────────────────────────────────────────
const PRIORITY_COLORS = {
  blocker:  'var(--danger)',
  critical: 'var(--danger)',
  high:     'var(--warning)',
  medium:   'var(--accent)',
  low:      'var(--success)',
}

const _fs = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 13,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const _ls = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-2)',
  textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5,
}

// ── sub-components ────────────────────────────────────────────────────────────
function StatusBadge({ ok, t }) {
  if (ok === null) return null
  return ok
    ? (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
        <CheckCircle size={14} /> {t('jira_integration.connected_status')}
      </span>
    ) : (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--danger)', fontWeight: 600 }}>
        <XCircle size={14} /> {t('jira_integration.disconnected_status')}
      </span>
    )
}

function SectionTitle({ children }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 14 }}>
      {children}
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function JiraIntegrationPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()

  const [form, setForm]             = useState({ jira_url: '', jira_email: '', jira_api_token: '', jira_project_key: '' })
  const [showToken, setShowToken]   = useState(false)
  const [connStatus, setConnStatus] = useState(null)   // null | true | false

  // ── queries ────────────────────────────────────────────────────────────────
  const { data: config, isLoading: loadingConfig } = useQuery({
    queryKey: ['jira-config'],
    queryFn:  () => api.get('/jira/config').then(r => r.data),
    onSuccess: (d) => {
      setForm(prev => ({
        ...prev,
        jira_url:         d.jira_url         || '',
        jira_email:       d.jira_email        || '',
        jira_project_key: d.jira_project_key  || '',
      }))
    },
  })

  const { data: issues, isLoading: loadingIssues } = useQuery({
    queryKey: ['jira-issues'],
    queryFn:  () => api.get('/jira/issues').then(r => r.data),
    enabled:  connStatus === true,
  })

  const { data: linked, isLoading: loadingLinked } = useQuery({
    queryKey: ['jira-linked'],
    queryFn:  () => api.get('/jira/linked').then(r => r.data),
  })

  // ── mutations ──────────────────────────────────────────────────────────────
  const saveConfig = useMutation({
    mutationFn: (payload) => api.post('/jira/config', payload).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['jira-config']); toast.success(t('jira_integration.config_saved')) },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.save_error'))),
  })

  const testConn = useMutation({
    mutationFn: () => api.get('/jira/test').then(r => r.data),
    onSuccess: (d) => {
      setConnStatus(d.ok)
      if (d.ok) { toast.success(`${t('jira_integration.connected_as')} ${d.display_name}`); qc.invalidateQueries(['jira-issues']) }
      else toast.error(d.error || t('jira_integration.connection_error'))
    },
    onError: () => { setConnStatus(false); toast.error(t('jira_integration.connection_error')) },
  })

  const syncPull = useMutation({
    mutationFn: (payload) => api.post('/jira/sync', payload).then(r => r.data),
    onSuccess: (d) => {
      qc.invalidateQueries(['jira-linked'])
      toast.success(`${t('jira_integration.sync_complete')} ${d.created} ${t('jira_integration.created')}, ${d.updated} ${t('jira_integration.updated')}`)
    },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.sync_error'))),
  })

  const pushToJira = useMutation({
    mutationFn: () => api.post('/jira/push').then(r => r.data),
    onSuccess: (d) => {
      qc.invalidateQueries(['jira-linked'])
      toast.success(`${t('jira_integration.push_complete')} ${d.pushed} ${t('jira_integration.tasks_pushed')}`)
    },
    onError: (e) => toast.error(extractErr(e, t('jira_integration.push_error'))),
  })

  // ── handlers ───────────────────────────────────────────────────────────────
  const handleSave = (e) => {
    e.preventDefault()
    if (!form.jira_url || !form.jira_email || !form.jira_project_key) {
      toast.error(t('jira_integration.required_fields_error'))
      return
    }
    const payload = { ...form }
    if (!payload.jira_api_token) delete payload.jira_api_token
    saveConfig.mutate(payload)
  }

  const issueList   = issues?.issues  || issues       || []
  const linkedList  = linked?.tasks   || []
  const issueCount  = issues?.total   ?? issueList.length
  const linkedCount = linked?.count   ?? linkedList.length ?? 0

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Link2 size={18} />}
        title={t('jira_integration.title')}
        subtitle={t('jira_integration.subtitle')}
        actions={<StatusBadge ok={connStatus} t={t} />}
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
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{t('jira_integration.import_button_title')}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{t('jira_integration.import_button_subtitle')}</div>
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
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{t('jira_integration.export_button_title')}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{t('jira_integration.export_button_subtitle')}</div>
                </div>
              </button>
            </div>
            <div style={{
              marginTop: 12, padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'flex-start',
              background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 8,
            }}>
              <AlertTriangle size={14} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 1 }} />
              <p style={{ fontSize: 11, color: 'var(--text-2)', margin: 0, lineHeight: 1.5 }}>
                {t('jira_integration.webhook_note')}{' '}
                <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 11 }}>/jira/webhook</code>{' '}
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
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                      {[t('jira_integration.col_key'), t('jira_integration.col_summary'), t('jira_integration.col_status'), t('jira_integration.col_priority')].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '6px 10px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {issueList.map(issue => (
                      <tr key={issue.key} style={{ borderBottom: '1px solid var(--surface-3)' }}>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 12, whiteSpace: 'nowrap' }}>{issue.key}</td>
                        <td style={{ padding: '8px 10px', color: 'var(--text-1)', maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{issue.summary}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                            {issue.status}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-2)' }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: PRIORITY_COLORS[issue.priority?.toLowerCase()] || 'var(--surface-5)', flexShrink: 0 }} />
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
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                      {[t('jira_integration.col_task'), t('jira_integration.col_jira_key'), t('jira_integration.col_status'), t('jira_integration.col_synced')].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '6px 10px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {linkedList.map(row => (
                      <tr key={row.id} style={{ borderBottom: '1px solid var(--surface-3)' }}>
                        <td style={{ padding: '8px 10px', color: 'var(--text-1)' }}>{row.title}</td>
                        <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 12 }}>{row.jira_issue_key}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                            {row.status}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-3)' }}>
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
    </div>
  )
}
