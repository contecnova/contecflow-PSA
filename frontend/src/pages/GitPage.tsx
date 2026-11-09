/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { gitApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { GitBranch } from 'lucide-react'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { localeActivo } from '../utils/helpers'

type PrStatus = 'open' | 'draft' | 'merged' | 'closed'
type DeployStatus = 'pending' | 'running' | 'success' | 'failure' | 'cancelled'

interface PullRequestItem {
  id: string | number
  status?: PrStatus
  repo_full_name?: string
  pr_number?: number
  pr_url?: string
  pr_title?: string
  source_branch?: string
  author_login?: string
  task_id?: string | number
  merged_at?: string
  created_at?: string
}

interface DeploymentItem {
  id: string | number
  status?: DeployStatus
  repo_full_name?: string
  sha?: string
  environment?: string
  task_id?: string | number
  deployed_at?: string
  created_at?: string
}

const STATUS_PR = {
  open:   { key: 'git_integration.status_open',   color: 'var(--success)', bg: 'var(--success-bg)' },
  draft:  { key: 'git_integration.status_draft',  color: 'var(--text-2)', bg: 'var(--surface-2)' },
  merged: { key: 'git_integration.status_merged', color: 'var(--purple)', bg: 'var(--purple-bg)' },
  closed: { key: 'git_integration.status_closed', color: 'var(--danger)', bg: 'var(--danger-bg)' },
}

const STATUS_DEPLOY = {
  pending:   { key: 'git_integration.status_pending',  color: 'var(--warning)', bg: 'var(--warning-bg)' },
  running:   { key: 'git_integration.status_running',  color: 'var(--info)', bg: 'var(--accent-muted)' },
  success:   { key: 'git_integration.status_success',  color: 'var(--success)', bg: 'var(--success-bg)' },
  failure:   { key: 'git_integration.status_failure',  color: 'var(--danger)', bg: 'var(--danger-bg)' },
  cancelled: { key: 'git_integration.status_cancelled',color: 'var(--text-2)', bg: 'var(--surface-2)' },
}

function PRStatusPill({ status }: { status?: PrStatus }) {
  const t = useAppT()
  const s = (status && STATUS_PR[status]) || STATUS_PR.open
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${alpha(s.color, '40')}`,
      borderRadius: 12, padding: '2px 10px', fontSize: "var(--text-xs)", fontWeight: 600,
    }}>{t(s.key)}</span>
  )
}

function DeployPill({ status }: { status?: DeployStatus }) {
  const t = useAppT()
  const s = (status && STATUS_DEPLOY[status]) || STATUS_DEPLOY.pending
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${alpha(s.color, '40')}`,
      borderRadius: 12, padding: '2px 10px', fontSize: "var(--text-xs)", fontWeight: 600,
    }}>{t(s.key)}</span>
  )
}

const cell = { padding: '10px 14px', fontSize: "var(--text-base)", color: 'var(--text-1)', borderBottom: '1px solid var(--surface-4)' }
const th   = { ...cell, fontWeight: 700, fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', background: 'var(--surface-2)' }

export default function GitPage(): JSX.Element {
  const t = useAppT()
  const [tab, setTab] = useState<'prs' | 'deps' | 'config'>('prs')

  const { data: prsRaw = [], isLoading: loadPR } = useQuery({
    queryKey: ['git-prs'],
    queryFn: () => gitApi.pullRequests().then(r => r.data?.items ?? r.data ?? []),
  })
  const prs = prsRaw as PullRequestItem[]

  const { data: deploysRaw = [], isLoading: loadDep } = useQuery({
    queryKey: ['git-deploys'],
    queryFn: () => gitApi.deployments().then(r => r.data?.items ?? r.data ?? []),
  })
  const deploys = deploysRaw as DeploymentItem[]

  const fmtDate = (d?: string) => d ? new Date(d).toLocaleString(localeActivo(), {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  }) : '—'

  const tabStyle = (active: boolean) => ({
    padding: '8px 18px',
    borderRadius: 8,
    border: 'none',
    background: active ? 'var(--accent-glow)' : 'transparent',
    color: active ? 'var(--info)' : 'var(--text-2)',
    fontWeight: 600,
    fontSize: "var(--text-base)",
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'all 0.15s',
  })

  // Stats
  const openPRs   = prs.filter(p => p.status === 'open').length
  const mergedPRs = prs.filter(p => p.status === 'merged').length
  const okDeploys = deploys.filter(d => d.status === 'success').length
  const failDeps  = deploys.filter(d => d.status === 'failure').length

  return (
    <PageShell style={{ maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        icon={<GitBranch size={18} />}
        title={t('git_integration.title')}
        subtitle={t('git_integration.subtitle')}
        actions={
          <a
            href="/api/v1/git/webhooks/github"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: "var(--text-sm)", color: 'var(--info)', textDecoration: 'none' }}
          >
            📋 {t('git_integration.webhook_url')}
          </a>
        }
      />

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 14, marginBottom: 24 }}>
        {[
          { label: t('git_integration.kpi_prs_open'),  value: openPRs,   color: 'var(--success)' },
          { label: t('git_integration.kpi_prs_merged'), value: mergedPRs,  color: 'var(--purple)' },
          { label: t('git_integration.kpi_deploys_ok'),    value: okDeploys,  color: 'var(--success)' },
          { label: t('git_integration.kpi_deploys_ko'),    value: failDeps,   color: 'var(--danger)' },
        ].map(k => (
          <div key={k.label} style={{
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: k.color }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
        <button style={tabStyle(tab === 'prs')}   onClick={() => setTab('prs')}>
          🔀 {t('git_integration.tab_prs', { count: prs.length })}
        </button>
        <button style={tabStyle(tab === 'deps')} onClick={() => setTab('deps')}>
          🚀 {t('git_integration.tab_deploys', { count: deploys.length })}
        </button>
        <button style={tabStyle(tab === 'config')} onClick={() => setTab('config')}>
          ⚙️ {t('git_integration.tab_config')}
        </button>
      </div>

      {/* PR table */}
      {tab === 'prs' && (
        loadPR ? <Spinner /> : prs.length === 0 ? (
          <EmptyState icon="🔀" title={t('git_integration.empty_prs_title')} description={t('git_integration.empty_prs_desc')} />
        ) : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {[t('git_integration.col_repo_pr'), t('git_integration.col_title'), t('git_integration.col_branch'), t('git_integration.col_author'), t('git_integration.col_status'), t('git_integration.col_task'), t('git_integration.col_date')].map(h => (
                    <th key={h} style={th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prs.map(pr => (
                  <tr key={pr.id} style={{ transition: 'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <td style={cell}>
                      <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{pr.repo_full_name}</span>
                      <span style={{ marginLeft: 6, color: 'var(--info)', fontWeight: 600 }}>#{pr.pr_number}</span>
                    </td>
                    <td style={{ ...cell, maxWidth: 260 }}>
                      {pr.pr_url ? (
                        <a href={pr.pr_url} target="_blank" rel="noreferrer"
                          style={{ color: 'var(--text-1)', textDecoration: 'none' }}>
                          {pr.pr_title || t('git_integration.dash')}
                        </a>
                      ) : (pr.pr_title || t('git_integration.dash'))}
                    </td>
                    <td style={{ ...cell, fontFamily: 'var(--font-mono)', fontSize: "var(--text-sm)", color: 'var(--info)' }}>
                      {pr.source_branch || t('git_integration.dash')}
                    </td>
                    <td style={cell}>{pr.author_login || t('git_integration.dash')}</td>
                    <td style={cell}><PRStatusPill status={pr.status} /></td>
                    <td style={cell}>
                      {pr.task_id ? (
                        <a href={`/tasks?id=${pr.task_id}`} style={{ color: 'var(--info)', fontSize: "var(--text-sm)" }}>
                          #{pr.task_id}
                        </a>
                      ) : <span style={{ color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>{t('git_integration.dash')}</span>}
                    </td>
                    <td style={{ ...cell, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                      {fmtDate(pr.merged_at || pr.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Deployments table */}
      {tab === 'deps' && (
        loadDep ? <Spinner /> : deploys.length === 0 ? (
          <EmptyState icon="🚀" title={t('git_integration.empty_deploys_title')} description={t('git_integration.empty_deploys_desc')} />
        ) : (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {[t('git_integration.col_repo'), t('git_integration.col_sha'), t('git_integration.col_env'), t('git_integration.col_status'), t('git_integration.col_task'), t('git_integration.col_deployed')].map(h => (
                    <th key={h} style={th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {deploys.map(d => (
                  <tr key={d.id}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <td style={{ ...cell, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{d.repo_full_name}</td>
                    <td style={{ ...cell, fontFamily: 'var(--font-mono)', fontSize: "var(--text-sm)", color: 'var(--info)' }}>
                      {d.sha ? d.sha.slice(0, 8) : t('git_integration.dash')}
                    </td>
                    <td style={cell}>
                      <span style={{
                        background: 'var(--surface-4)', color: 'var(--text-1)', borderRadius: 6,
                        padding: '2px 8px', fontSize: "var(--text-xs)", fontWeight: 600,
                      }}>{d.environment || t('git_integration.env_production')}</span>
                    </td>
                    <td style={cell}><DeployPill status={d.status} /></td>
                    <td style={cell}>
                      {d.task_id ? (
                        <a href={`/tasks?id=${d.task_id}`} style={{ color: 'var(--info)', fontSize: "var(--text-sm)" }}>
                          #{d.task_id}
                        </a>
                      ) : <span style={{ color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>{t('git_integration.dash')}</span>}
                    </td>
                    <td style={{ ...cell, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                      {fmtDate(d.deployed_at || d.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Config tab */}
      {tab === 'config' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <ConfigSection
            title={t('git_integration.config_github_title')}
            icon="🐙"
            webhookPath="/api/v1/git/webhooks/github"
            envVar="GITHUB_WEBHOOK_SECRET"
            events={['pull_request', 'deployment_status', 'push']}
            steps={[
              t('git_integration.config_github_step1'),
              t('git_integration.config_github_step2'),
              t('git_integration.config_github_step3'),
              t('git_integration.config_github_step4'),
              t('git_integration.config_github_step5'),
            ]}
          />
          <ConfigSection
            title={t('git_integration.config_gitlab_title')}
            icon="🦊"
            webhookPath="/api/v1/git/webhooks/gitlab"
            envVar="GITLAB_WEBHOOK_SECRET"
            events={['merge_requests', 'deployment']}
            steps={[
              t('git_integration.config_gitlab_step1'),
              t('git_integration.config_gitlab_step2'),
              t('git_integration.config_gitlab_step3'),
              t('git_integration.config_gitlab_step4'),
            ]}
          />
          <div style={{
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20,
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: "var(--text-md)", color: 'var(--text-1)' }}>🔗 {t('git_integration.auto_link_title')}</h3>
            <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '0 0 8px' }}>
              {t('git_integration.auto_link_desc')}
            </p>
            <ul style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', paddingLeft: 20, lineHeight: 1.8 }}>
              <li>{t('git_integration.auto_link_code')}: <code style={{ color: 'var(--info)' }}>PROJ-123</code> {t('git_integration.auto_link_code_desc')}</li>
              <li>{t('git_integration.auto_link_id')}: <code style={{ color: 'var(--info)' }}>#456</code></li>
            </ul>
            <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 8 }}>
              {t('git_integration.auto_link_example')}: <code style={{ color: 'var(--success)' }}>feature/PROJ-42-add-login</code>
            </p>
          </div>
        </div>
      )}
    </PageShell>
  )
}

function ConfigSection({ title, icon, webhookPath, envVar, events, steps }: { title: string; icon: string; webhookPath: string; envVar: string; events: string[]; steps: string[] }) {
  const t = useAppT()
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}${webhookPath}`
  const copy = () => {
    navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20 }}>
      <h3 style={{ margin: '0 0 14px', fontSize: "var(--text-md-em)", color: 'var(--text-1)' }}>{icon} {title}</h3>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>{t('git_integration.webhook_url_label')}</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <code style={{
            flex: 1, minWidth: 0, background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 6,
            padding: '8px 12px', fontSize: "var(--text-sm)", color: 'var(--info)', overflowX: 'auto',
          }}>{url}</code>
          <button onClick={copy} style={{
            background: copied ? 'var(--success-bg)' : 'var(--surface-4)',
            border: `1px solid ${copied ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 6,
            color: copied ? 'var(--success)' : 'var(--text-2)', padding: '8px 14px', cursor: 'pointer',
            fontSize: "var(--text-sm)", fontFamily: 'inherit', flexShrink: 0,
          }}>
            {copied ? t('git_integration.copied') : t('git_integration.copy')}
          </button>
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>{t('git_integration.env_var_label')}</div>
        <code style={{ fontSize: "var(--text-sm)", color: 'var(--warning)', overflowWrap: 'anywhere' }}>{envVar}=tu-secreto-largo</code>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6 }}>{t('git_integration.events_label')}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {events.map(e => (
            <span key={e} style={{
              background: 'var(--surface-4)', color: 'var(--text-1)', borderRadius: 6,
              padding: '3px 10px', fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)',
            }}>{e}</span>
          ))}
        </div>
      </div>
      <div>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6 }}>{t('git_integration.steps_label')}</div>
        <ol style={{ padding: 0, paddingLeft: 18, margin: 0, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 2 }}>
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </div>
  )
}
