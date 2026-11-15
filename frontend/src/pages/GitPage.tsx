/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { gitApi, apiUrl } from '../services/api'
import type { EstadoDeDespliegue, EstadoDePullRequest } from '../services/api/tipos-proyectos'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { GitBranch } from 'lucide-react'
import { Spinner, EmptyState, Table } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { localeActivo } from '../utils/helpers'
import { UI_FEEDBACK_MS } from '../constants/timings'
import './GitPage.css'


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

function PRStatusPill({ status }: { status?: EstadoDePullRequest }) {
  const t = useAppT()
  const s = (status && STATUS_PR[status]) || STATUS_PR.open
  return (
    <span className="gitp-label" style={{ background: s.bg, color: s.color, border: `1px solid ${alpha(s.color, '40')}`, borderRadius: 12 }}>{t(s.key)}</span>
  )
}

function DeployPill({ status }: { status?: EstadoDeDespliegue }) {
  const t = useAppT()
  const s = (status && STATUS_DEPLOY[status]) || STATUS_DEPLOY.pending
  return (
    <span className="gitp-label" style={{ background: s.bg, color: s.color, border: `1px solid ${alpha(s.color, '40')}`, borderRadius: 12 }}>{t(s.key)}</span>
  )
}


export default function GitPage(): JSX.Element {
  const t = useAppT()
  const [tab, setTab] = useState<'prs' | 'deps' | 'config'>('prs')

  const { data: webhooks } = useQuery({
    queryKey: ['git-webhooks'],
    queryFn: () => gitApi.webhooks().then(r => r.data),
  })
  const { data: prs = [], isLoading: loadPR } = useQuery({
    queryKey: ['git-prs'],
    queryFn: () => gitApi.pullRequests().then(r => r.data),
  })

  const { data: deploys = [], isLoading: loadDep } = useQuery({
    queryKey: ['git-deploys'],
    queryFn: () => gitApi.deployments().then(r => r.data),
  })

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
            href={apiUrl('/git/webhooks/github')}
            target="_blank"
            rel="noopener noreferrer"
            className="gitp-link"
          >
            📋 {t('git_integration.webhook_url')}
          </a>
        }
      />

      {/* KPI row */}
      <div className="gitp-grid">
        {[
          { label: t('git_integration.kpi_prs_open'),  value: openPRs,   color: 'var(--success)' },
          { label: t('git_integration.kpi_prs_merged'), value: mergedPRs,  color: 'var(--purple)' },
          { label: t('git_integration.kpi_deploys_ok'),    value: okDeploys,  color: 'var(--success)' },
          { label: t('git_integration.kpi_deploys_ko'),    value: failDeps,   color: 'var(--danger)' },
        ].map(k => (
          <div key={k.label} className="gitp-card">
            <div className="gitp-box" style={{ color: k.color }}>{k.value}</div>
            <div className="u-text2-sm-mt2">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="gitp-row">
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
          <div className="gitp-card-2">
            <Table
              data={prs}
              columns={[
                { key: 'repo_full_name', label: t('git_integration.col_repo_pr'), render: (_v, pr) => (
                  <>
                    <span className="u-text2-xs">{pr.repo_full_name}</span>
                    <span className="gitp-label-2">#{pr.pr_number}</span>
                  </>
                ) },
                { key: 'pr_title', label: t('git_integration.col_title'), render: (_v, pr) => (
                  <span className="gitp-label-3">
                    {pr.pr_url ? (
                      <a href={pr.pr_url} target="_blank" rel="noreferrer"
                        className="gitp-link-2">
                        {pr.pr_title || t('git_integration.dash')}
                      </a>
                    ) : (pr.pr_title || t('git_integration.dash'))}
                  </span>
                ) },
                { key: 'source_branch', label: t('git_integration.col_branch'), render: (_v, pr) => <span className="gitp-label-4">{pr.source_branch || t('git_integration.dash')}</span> },
                { key: 'author_login', label: t('git_integration.col_author'), render: (_v, pr) => pr.author_login || t('git_integration.dash') },
                { key: 'status', label: t('git_integration.col_status'), render: (_v, pr) => <PRStatusPill status={pr.status} /> },
                { key: 'task_id', label: t('git_integration.col_task'), render: (_v, pr) => (pr.task_id ? (
                  <a href={`/tasks?id=${pr.task_id}`} className="gitp-link-3">
                    #{pr.task_id}
                  </a>
                ) : <span className="gitp-label-5">{t('git_integration.dash')}</span>) },
                { key: 'merged_at', label: t('git_integration.col_date'), render: (_v, pr) => <span className="u-text2-xs">{fmtDate(pr.merged_at || pr.created_at)}</span> },
              ]}
            />
          </div>
        )
      )}

      {/* Deployments table */}
      {tab === 'deps' && (
        loadDep ? <Spinner /> : deploys.length === 0 ? (
          <EmptyState icon="🚀" title={t('git_integration.empty_deploys_title')} description={t('git_integration.empty_deploys_desc')} />
        ) : (
          <div className="gitp-card-2">
            <Table
              data={deploys}
              columns={[
                { key: 'repo_full_name', label: t('git_integration.col_repo'), render: (_v, d) => <span className="u-text2-sm">{d.repo_full_name}</span> },
                { key: 'sha', label: t('git_integration.col_sha'), render: (_v, d) => <span className="gitp-label-4">{d.sha ? d.sha.slice(0, 8) : t('git_integration.dash')}</span> },
                { key: 'environment', label: t('git_integration.col_env'), render: (_v, d) => (
                  <span className="gitp-card-3">{d.environment || t('git_integration.env_production')}</span>
                ) },
                { key: 'status', label: t('git_integration.col_status'), render: (_v, d) => <DeployPill status={d.status} /> },
                { key: 'task_id', label: t('git_integration.col_task'), render: (_v, d) => (d.task_id ? (
                  <a href={`/tasks?id=${d.task_id}`} className="gitp-link-3">
                    #{d.task_id}
                  </a>
                ) : <span className="gitp-label-5">{t('git_integration.dash')}</span>) },
                { key: 'deployed_at', label: t('git_integration.col_deployed'), render: (_v, d) => <span className="u-text2-xs">{fmtDate(d.deployed_at || d.created_at)}</span> },
              ]}
            />
          </div>
        )
      )}

      {/* Config tab */}
      {tab === 'config' && (
        <div className="u-stack-20">
          <ConfigSection
            title={t('git_integration.config_github_title')}
            icon="🐙"
            webhook={webhooks?.github}
            clave="github_secret"
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
            webhook={webhooks?.gitlab}
            clave="gitlab_secret"
            events={['merge_requests', 'deployment']}
            steps={[
              t('git_integration.config_gitlab_step1'),
              t('git_integration.config_gitlab_step2'),
              t('git_integration.config_gitlab_step3'),
              t('git_integration.config_gitlab_step4'),
            ]}
          />
          <div className="gitp-card-4">
            <h3 className="gitp-title">🔗 {t('git_integration.auto_link_title')}</h3>
            <p className="gitp-text">
              {t('git_integration.auto_link_desc')}
            </p>
            <ul className="gitp-box-2">
              <li>{t('git_integration.auto_link_code')}: <code className="gitp-box-3">PROJ-123</code> {t('git_integration.auto_link_code_desc')}</li>
              <li>{t('git_integration.auto_link_id')}: <code className="gitp-box-3">#456</code></li>
            </ul>
            <p className="gitp-text-2">
              {t('git_integration.auto_link_example')}: <code className="u-success">feature/PROJ-42-add-login</code>
            </p>
          </div>
        </div>
      )}
    </PageShell>
  )
}

// Revisión 2026-11: cada empresa tiene su dirección y su propio secreto
// (Credenciales → Inbound webhooks); antes había uno para toda la instalación.
function ConfigSection({ title, icon, webhook, clave, events, steps }: { title: string; icon: string; webhook?: { ruta: string; secreto: boolean }; clave: string; events: string[]; steps: string[] }) {
  const t = useAppT()
  const [copied, setCopied] = useState(false)
  const url = webhook ? `${window.location.origin}${webhook.ruta}` : '…'
  const copy = () => {
    navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), UI_FEEDBACK_MS) })
  }
  return (
    <div className="gitp-card-4">
      <h3 className="gitp-title-2">{icon} {title}</h3>
      <div className="u-mb-12">
        <div className="u-text2-xs-mb4">{t('git_integration.webhook_url_label')}</div>
        <div className="u-row-center-8">
          <code className="gitp-card-5">{url}</code>
          <button onClick={copy} className="gitp-btn" style={{ background: copied ? 'var(--success-bg)' : 'var(--surface-4)', border: `1px solid ${copied ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 'var(--radius-sm)', color: copied ? 'var(--success)' : 'var(--text-2)' }}>
            {copied ? t('git_integration.copied') : t('git_integration.copy')}
          </button>
        </div>
      </div>
      <div className="u-mb-12">
        <div className="u-text2-xs-mb4">{t('git_integration.secreto_label')}</div>
        <div className="gitp-box-4" style={{ color: webhook?.secreto ? 'var(--success)' : 'var(--warning)' }}>
          {t(webhook?.secreto ? 'git_integration.secreto_puesto' : 'git_integration.secreto_falta', { clave })}
        </div>
      </div>
      <div className="u-mb-12">
        <div className="gitp-box-5">{t('git_integration.events_label')}</div>
        <div className="u-wrap-6">
          {events.map(e => (
            <span key={e} className="gitp-card-6">{e}</span>
          ))}
        </div>
      </div>
      <div>
        <div className="gitp-box-5">{t('git_integration.steps_label')}</div>
        <ol className="gitp-box-6">
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </div>
  )
}
