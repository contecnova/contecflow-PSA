/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 *
 * 16-11-2026 (pasada de diseño): <Page>, KpiCard, Tabs y StatusBadge comunes;
 * iconos lucide en lugar de emojis; fechas con el formateador de la app.
 *
 * 19-11-2026: la pestaña «Configuración» (webhooks de GitHub/GitLab, secreto,
 * eventos y pasos) vive en Configuración → Integraciones → Git
 * (`/settings/git`, components/git/ConfigGit.tsx). Aquí queda el botón
 * «Configurar» para quien tiene `proyectos.gobierno` y `?tab=config` redirige.
 */

import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { gitApi } from '../services/api'
import type { EstadoDeDespliegue, EstadoDePullRequest } from '../services/api/tipos-proyectos'
import {
  CheckCircle2, GitBranch, GitMerge, GitPullRequest, Rocket, Settings2, XCircle,
} from 'lucide-react'
import { Button, EmptyState, KpiCard, Page, Spinner, StatusBadge, Table, Tabs } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { fmtDateTime } from '../utils/helpers'
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
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const configura = useAuth().puede('proyectos.gobierno')

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
  ]

  // La configuración vive en Configuración (19-11-2026): los enlaces antiguos redirigen.
  if (searchParams.get('tab') === 'config') return <Navigate to="/settings/git" replace />
  return (
    <Page
      icon={<GitBranch size={18} />}
      title={t('nav.git')}
      subtitle={t('git_integration.subtitle')}
      actions={configura ? (
        <Button variant="secondary" icon={<Settings2 size={14} />} onClick={() => navigate('/settings/git')}>{t('ajustes.configurar')}</Button>
      ) : undefined}
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
                { key: 'source_branch', label: t('git_integration.col_branch'), render: (_v, pr) => <span className="ds-codigo gitp-label-4">{pr.source_branch || t('git_integration.dash')}</span> },
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
                { key: 'sha', label: t('git_integration.col_sha'), render: (_v, d) => <span className="ds-codigo gitp-label-4">{d.sha ? d.sha.slice(0, 8) : t('git_integration.dash')}</span> },
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

    </Page>
  )
}

