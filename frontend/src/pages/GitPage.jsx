/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { GitBranch } from 'lucide-react'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_PR = {
  open:   { key: 'git_integration.status_open',   color: '#68d391', bg: '#1a3a1a' },
  draft:  { key: 'git_integration.status_draft',  color: '#a0aec0', bg: '#1a202c' },
  merged: { key: 'git_integration.status_merged', color: '#9f7aea', bg: '#2d1a4a' },
  closed: { key: 'git_integration.status_closed', color: '#fc8181', bg: '#2d1a1a' },
}

const STATUS_DEPLOY = {
  pending:   { key: 'git_integration.status_pending',  color: '#f6e05e', bg: '#3d3000' },
  running:   { key: 'git_integration.status_running',  color: '#63b3ed', bg: '#1a2844' },
  success:   { key: 'git_integration.status_success',  color: '#68d391', bg: '#1a3a1a' },
  failure:   { key: 'git_integration.status_failure',  color: '#fc8181', bg: '#2d1a1a' },
  cancelled: { key: 'git_integration.status_cancelled',color: '#a0aec0', bg: '#1a202c' },
}

function PRStatusPill({ status }) {
  const t = useAppT()
  const s = STATUS_PR[status] || STATUS_PR.open
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 12, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>{t(s.key)}</span>
  )
}

function DeployPill({ status }) {
  const t = useAppT()
  const s = STATUS_DEPLOY[status] || STATUS_DEPLOY.pending
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 12, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>{t(s.key)}</span>
  )
}

const cell = { padding: '10px 14px', fontSize: 13, color: '#e2e8f0', borderBottom: '1px solid var(--surface-4)' }
const th   = { ...cell, fontWeight: 700, fontSize: 11, color: '#718096', textTransform: 'uppercase', background: '#1a202c' }

export default function GitPage() {
  const t = useAppT()
  const [tab, setTab] = useState('prs')

  const { data: prs = [], isLoading: loadPR } = useQuery({
    queryKey: ['git-prs'],
    queryFn: () => api.get('/git/pull-requests').then(r => r.data),
  })

  const { data: deploys = [], isLoading: loadDep } = useQuery({
    queryKey: ['git-deploys'],
    queryFn: () => api.get('/git/deployments').then(r => r.data),
  })

  const fmtDate = (d) => d ? new Date(d).toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  }) : '—'

  const tabStyle = (active) => ({
    padding: '8px 18px',
    borderRadius: 8,
    border: 'none',
    background: active ? '#2b4a7a' : 'transparent',
    color: active ? '#90cdf4' : '#718096',
    fontWeight: 600,
    fontSize: 13,
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
    <div style={{ padding: 32, maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        icon={<GitBranch size={18} />}
        title={t('git_integration.title')}
        subtitle={t('git_integration.subtitle')}
        action={
          <a
            href="/api/v1/git/webhooks/github"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#90cdf4', textDecoration: 'none' }}
          >
            📋 {t('git_integration.webhook_url')}
          </a>
        }
      />

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { label: t('git_integration.kpi_prs_open'),  value: openPRs,   color: '#68d391' },
          { label: t('git_integration.kpi_prs_merged'), value: mergedPRs,  color: '#9f7aea' },
          { label: t('git_integration.kpi_deploys_ok'),    value: okDeploys,  color: '#68d391' },
          { label: t('git_integration.kpi_deploys_ko'),    value: failDeps,   color: '#fc8181' },
        ].map(k => (
          <div key={k.label} style={{
            background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: k.color }}>{k.value}</div>
            <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
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
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden' }}>
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
                    onMouseEnter={e => e.currentTarget.style.background = '#2d3748'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <td style={cell}>
                      <span style={{ fontSize: 11, color: '#718096' }}>{pr.repo_full_name}</span>
                      <span style={{ marginLeft: 6, color: '#90cdf4', fontWeight: 600 }}>#{pr.pr_number}</span>
                    </td>
                    <td style={{ ...cell, maxWidth: 260 }}>
                      {pr.pr_url ? (
                        <a href={pr.pr_url} target="_blank" rel="noreferrer"
                          style={{ color: '#e2e8f0', textDecoration: 'none' }}>
                          {pr.pr_title || t('git_integration.dash')}
                        </a>
                      ) : (pr.pr_title || t('git_integration.dash'))}
                    </td>
                    <td style={{ ...cell, fontFamily: 'monospace', fontSize: 12, color: '#90cdf4' }}>
                      {pr.source_branch || t('git_integration.dash')}
                    </td>
                    <td style={cell}>{pr.author_login || t('git_integration.dash')}</td>
                    <td style={cell}><PRStatusPill status={pr.status} /></td>
                    <td style={cell}>
                      {pr.task_id ? (
                        <a href={`/tasks?id=${pr.task_id}`} style={{ color: '#90cdf4', fontSize: 12 }}>
                          #{pr.task_id}
                        </a>
                      ) : <span style={{ color: '#4a5568', fontSize: 12 }}>{t('git_integration.dash')}</span>}
                    </td>
                    <td style={{ ...cell, fontSize: 11, color: '#718096' }}>
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
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden' }}>
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
                    onMouseEnter={e => e.currentTarget.style.background = '#2d3748'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <td style={{ ...cell, fontSize: 12, color: '#718096' }}>{d.repo_full_name}</td>
                    <td style={{ ...cell, fontFamily: 'monospace', fontSize: 12, color: '#90cdf4' }}>
                      {d.sha ? d.sha.slice(0, 8) : t('git_integration.dash')}
                    </td>
                    <td style={cell}>
                      <span style={{
                        background: '#2d3748', color: '#e2e8f0', borderRadius: 6,
                        padding: '2px 8px', fontSize: 11, fontWeight: 600,
                      }}>{d.environment || t('git_integration.env_production')}</span>
                    </td>
                    <td style={cell}><DeployPill status={d.status} /></td>
                    <td style={cell}>
                      {d.task_id ? (
                        <a href={`/tasks?id=${d.task_id}`} style={{ color: '#90cdf4', fontSize: 12 }}>
                          #{d.task_id}
                        </a>
                      ) : <span style={{ color: '#4a5568', fontSize: 12 }}>{t('git_integration.dash')}</span>}
                    </td>
                    <td style={{ ...cell, fontSize: 11, color: '#718096' }}>
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
            background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20,
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e2e8f0' }}>🔗 {t('git_integration.auto_link_title')}</h3>
            <p style={{ fontSize: 13, color: '#a0aec0', margin: '0 0 8px' }}>
              {t('git_integration.auto_link_desc')}
            </p>
            <ul style={{ fontSize: 13, color: '#a0aec0', paddingLeft: 20, lineHeight: 1.8 }}>
              <li>{t('git_integration.auto_link_code')}: <code style={{ color: '#90cdf4' }}>PROJ-123</code> {t('git_integration.auto_link_code_desc')}</li>
              <li>{t('git_integration.auto_link_id')}: <code style={{ color: '#90cdf4' }}>#456</code></li>
            </ul>
            <p style={{ fontSize: 12, color: '#718096', marginTop: 8 }}>
              {t('git_integration.auto_link_example')}: <code style={{ color: '#68d391' }}>feature/PROJ-42-add-login</code>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

function ConfigSection({ title, icon, webhookPath, envVar, events, steps }) {
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}${webhookPath}`
  const copy = () => {
    navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }
  return (
    <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20 }}>
      <h3 style={{ margin: '0 0 14px', fontSize: 15, color: '#e2e8f0' }}>{icon} {title}</h3>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 4 }}>{t('git_integration.webhook_url_label')}</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <code style={{
            flex: 1, background: '#0d1117', border: '1px solid #2d3748', borderRadius: 6,
            padding: '8px 12px', fontSize: 12, color: '#90cdf4', overflowX: 'auto',
          }}>{url}</code>
          <button onClick={copy} style={{
            background: copied ? '#276227' : '#2d3748', border: 'none', borderRadius: 6,
            color: copied ? '#68d391' : '#a0aec0', padding: '8px 14px', cursor: 'pointer',
            fontSize: 12, fontFamily: 'inherit', flexShrink: 0,
          }}>
            {copied ? t('git_integration.copied') : t('git_integration.copy')}
          </button>
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 4 }}>{t('git_integration.env_var_label')}</div>
        <code style={{ fontSize: 12, color: '#f6e05e' }}>{envVar}=tu-secreto-largo</code>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 6 }}>{t('git_integration.events_label')}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {events.map(e => (
            <span key={e} style={{
              background: '#2d3748', color: '#e2e8f0', borderRadius: 6,
              padding: '3px 10px', fontSize: 11, fontFamily: 'monospace',
            }}>{e}</span>
          ))}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 6 }}>{t('git_integration.steps_label')}</div>
        <ol style={{ padding: 0, paddingLeft: 18, margin: 0, fontSize: 12, color: '#a0aec0', lineHeight: 2 }}>
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </div>
  )
}
