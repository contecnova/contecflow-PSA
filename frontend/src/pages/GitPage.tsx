/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 *
 * 16-11-2026 (pasada de diseño): <Page>, KpiCard, Tabs y StatusBadge comunes;
 * iconos lucide en lugar de emojis; fechas con el formateador de la app.
 */

import { type ReactNode, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { gitApi } from '../services/api'
import type { EstadoDeDespliegue, EstadoDePullRequest } from '../services/api/tipos-proyectos'
import {
  Check, CheckCircle2, Copy, GitBranch, GitMerge, GitPullRequest, Github, Gitlab, Link2, Rocket, Settings, XCircle,
} from 'lucide-react'
import { Button, Card, EmptyState, KpiCard, Page, Spinner, StatusBadge, Table, Tabs } from '../components/ui'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { fmtDateTime } from '../utils/helpers'
import { UI_FEEDBACK_MS } from '../constants/timings'
import './GitPage.css'


const STATUS_PR: Record<EstadoDePullRequest, { key: string; kind: StatusBadgeKind }> = {
  open:   { key: 'git_integration.status_open',   kind: 'success' },
  draft:  { key: 'git_integration.status_draft',  kind: 'neutral' },
  merged: { key: 'git_integration.status_merged', kind: 'purple' },
  closed: { key: 'git_integration.status_closed', kind: 'danger' },
}

const STATUS_DEPLOY: Record<EstadoDeDespliegue, { key: string; kind: StatusBadgeKind }> = {
  pending:   { key: 'git_integration.status_pending',   kind: 'warning' },
  running:   { key: 'git_integration.status_running',   kind: 'accent' },
  success:   { key: 'git_integration.status_success',   kind: 'success' },
  failure:   { key: 'git_integration.status_failure',   kind: 'danger' },
  cancelled: { key: 'git_integration.status_cancelled', kind: 'neutral' },
}

function PRStatusPill({ status }: { status?: EstadoDePullRequest }) {
  const t = useAppT()
  const s = (status && STATUS_PR[status]) || STATUS_PR.open
  return <StatusBadge kind={s.kind}>{t(s.key)}</StatusBadge>
}

function DeployPill({ status }: { status?: EstadoDeDespliegue }) {
  const t = useAppT()
  const s = (status && STATUS_DEPLOY[status]) || STATUS_DEPLOY.pending
  return <StatusBadge kind={s.kind}>{t(s.key)}</StatusBadge>
}


export default function GitPage(): JSX.Element {
  const t = useAppT()
  const [tab, setTab] = useState<string>('prs')

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

  // Stats
  const openPRs   = prs.filter(p => p.status === 'open').length
  const mergedPRs = prs.filter(p => p.status === 'merged').length
  const okDeploys = deploys.filter(d => d.status === 'success').length
  const failDeps  = deploys.filter(d => d.status === 'failure').length

  const pestanas = [
    { id: 'prs', label: t('git_integration.tab_prs', { count: prs.length }), icon: <GitPullRequest size={14} /> },
    { id: 'deps', label: t('git_integration.tab_deploys', { count: deploys.length }), icon: <Rocket size={14} /> },
    { id: 'config', label: t('git_integration.tab_config'), icon: <Settings size={14} /> },
  ]

  return (
    <Page
      icon={<GitBranch size={18} />}
      title={t('nav.git')}
      subtitle={t('git_integration.subtitle')}
    >
      <div className="ds-grid-stats">
        <KpiCard icon={<GitPullRequest size={14} />} label={t('git_integration.kpi_prs_open')} value={openPRs} />
        <KpiCard icon={<GitMerge size={14} />} label={t('git_integration.kpi_prs_merged')} value={mergedPRs} />
        <KpiCard icon={<CheckCircle2 size={14} />} label={t('git_integration.kpi_deploys_ok')} value={okDeploys} />
        <KpiCard icon={<XCircle size={14} />} label={t('git_integration.kpi_deploys_ko')} value={failDeps} danger={failDeps > 0} />
      </div>

      <Tabs items={pestanas} active={tab} onChange={setTab} ariaLabel={t('git_integration.title')} />

      {/* PR table */}
      {tab === 'prs' && (
        loadPR ? <Spinner /> : prs.length === 0 ? (
          <EmptyState icon={<GitPullRequest size={28} />} title={t('git_integration.empty_prs_title')} description={t('git_integration.empty_prs_desc')} />
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
                { key: 'merged_at', label: t('git_integration.col_date'), render: (_v, pr) => <span className="u-text2-xs">{fmtDateTime(pr.merged_at || pr.created_at)}</span> },
              ]}
            />
          </div>
        )
      )}

      {/* Deployments table */}
      {tab === 'deps' && (
        loadDep ? <Spinner /> : deploys.length === 0 ? (
          <EmptyState icon={<Rocket size={28} />} title={t('git_integration.empty_deploys_title')} description={t('git_integration.empty_deploys_desc')} />
        ) : (
          <div className="gitp-card-2">
            <Table
              data={deploys}
              columns={[
                { key: 'repo_full_name', label: t('git_integration.col_repo'), render: (_v, d) => <span className="u-text2-sm">{d.repo_full_name}</span> },
                { key: 'sha', label: t('git_integration.col_sha'), render: (_v, d) => <span className="gitp-label-4">{d.sha ? d.sha.slice(0, 8) : t('git_integration.dash')}</span> },
                { key: 'environment', label: t('git_integration.col_env'), render: (_v, d) => (
                  <StatusBadge kind="neutral" caps={false}>{d.environment || t('git_integration.env_production')}</StatusBadge>
                ) },
                { key: 'status', label: t('git_integration.col_status'), render: (_v, d) => <DeployPill status={d.status} /> },
                { key: 'task_id', label: t('git_integration.col_task'), render: (_v, d) => (d.task_id ? (
                  <a href={`/tasks?id=${d.task_id}`} className="gitp-link-3">
                    #{d.task_id}
                  </a>
                ) : <span className="gitp-label-5">{t('git_integration.dash')}</span>) },
                { key: 'deployed_at', label: t('git_integration.col_deployed'), render: (_v, d) => <span className="u-text2-xs">{fmtDateTime(d.deployed_at || d.created_at)}</span> },
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
            icon={<Github size={16} aria-hidden />}
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
            icon={<Gitlab size={16} aria-hidden />}
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
          <Card>
            <h3 className="gitp-title"><Link2 size={16} aria-hidden />{t('git_integration.auto_link_title')}</h3>
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
          </Card>
        </div>
      )}
    </Page>
  )
}

// Revisión 2026-11: cada empresa tiene su dirección y su propio secreto
// (Credenciales → Inbound webhooks); antes había uno para toda la instalación.
function ConfigSection({ title, icon, webhook, clave, events, steps }: { title: string; icon: ReactNode; webhook?: { ruta: string; secreto: boolean }; clave: string; events: string[]; steps: string[] }) {
  const t = useAppT()
  const [copied, setCopied] = useState(false)
  const url = webhook ? `${window.location.origin}${webhook.ruta}` : '…'
  const copy = () => {
    navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), UI_FEEDBACK_MS) })
  }
  return (
    <Card>
      <h3 className="gitp-title">{icon}{title}</h3>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.webhook_url_label')}</div>
        <div className="u-row-center-8">
          <code className="gitp-card-5">{url}</code>
          <Button size="sm" variant="secondary" onClick={copy} icon={copied ? <Check size={14} /> : <Copy size={14} />}>
            {copied ? t('git_integration.copied') : t('git_integration.copy')}
          </Button>
        </div>
      </div>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.secreto_label')}</div>
        <div className={`gitp-box-4 ${webhook?.secreto ? 'gitpage-sx5' : 'gitpage-sx6'}`}>
          {t(webhook?.secreto ? 'git_integration.secreto_puesto' : 'git_integration.secreto_falta', { clave })}
        </div>
      </div>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.events_label')}</div>
        <div className="u-wrap-6">
          {events.map(e => (
            <span key={e} className="gitp-card-6">{e}</span>
          ))}
        </div>
      </div>
      <div>
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.steps_label')}</div>
        <ol className="gitp-box-6">
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </Card>
  )
}
