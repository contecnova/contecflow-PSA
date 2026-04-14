/**
 * GitPage — bidirectional Git integration dashboard
 * Shows all PRs and deployments across repositories, with task linkage.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_PR = {
  open:   { label: 'Open',   color: '#68d391', bg: '#1a3a1a' },
  draft:  { label: 'Draft',  color: '#a0aec0', bg: '#1a202c' },
  merged: { label: 'Merged', color: '#9f7aea', bg: '#2d1a4a' },
  closed: { label: 'Closed', color: '#fc8181', bg: '#2d1a1a' },
}

const STATUS_DEPLOY = {
  pending:   { label: 'Pending',  color: '#f6e05e', bg: '#3d3000' },
  running:   { label: 'Running',  color: '#63b3ed', bg: '#1a2844' },
  success:   { label: 'Success',  color: '#68d391', bg: '#1a3a1a' },
  failure:   { label: 'Failure',  color: '#fc8181', bg: '#2d1a1a' },
  cancelled: { label: 'Cancelled',color: '#a0aec0', bg: '#1a202c' },
}

function PRStatusPill({ status }) {
  const s = STATUS_PR[status] || STATUS_PR.open
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 12, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>{s.label}</span>
  )
}

function DeployPill({ status }) {
  const s = STATUS_DEPLOY[status] || STATUS_DEPLOY.pending
  return (
    <span style={{
      background: s.bg, color: s.color,
      border: `1px solid ${s.color}40`,
      borderRadius: 12, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>{s.label}</span>
  )
}

const cell = { padding: '10px 14px', fontSize: 13, color: '#e2e8f0', borderBottom: '1px solid #1e2d45' }
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
        title={t('git_integration.title')}
        subtitle="Pull Requests y Deployments vinculados a tareas"
        action={
          <a
            href="/api/v1/git/webhooks/github"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#90cdf4', textDecoration: 'none' }}
          >
            📋 Webhook URL
          </a>
        }
      />

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'PRs abiertos',  value: openPRs,   color: '#68d391' },
          { label: 'PRs mergeados', value: mergedPRs,  color: '#9f7aea' },
          { label: 'Deploys OK',    value: okDeploys,  color: '#68d391' },
          { label: 'Deploys KO',    value: failDeps,   color: '#fc8181' },
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
          🔀 Pull Requests ({prs.length})
        </button>
        <button style={tabStyle(tab === 'deps')} onClick={() => setTab('deps')}>
          🚀 Deployments ({deploys.length})
        </button>
        <button style={tabStyle(tab === 'config')} onClick={() => setTab('config')}>
          ⚙️ Configuración
        </button>
      </div>

      {/* PR table */}
      {tab === 'prs' && (
        loadPR ? <Spinner /> : prs.length === 0 ? (
          <EmptyState icon="🔀" title="No hay Pull Requests" description="Los PRs aparecerán aquí cuando el webhook reciba eventos de GitHub/GitLab." />
        ) : (
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Repo / PR', 'Título', 'Rama', 'Autor', 'Estado', 'Tarea', 'Fecha'].map(h => (
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
                          {pr.pr_title || '—'}
                        </a>
                      ) : (pr.pr_title || '—')}
                    </td>
                    <td style={{ ...cell, fontFamily: 'monospace', fontSize: 12, color: '#90cdf4' }}>
                      {pr.source_branch || '—'}
                    </td>
                    <td style={cell}>{pr.author_login || '—'}</td>
                    <td style={cell}><PRStatusPill status={pr.status} /></td>
                    <td style={cell}>
                      {pr.task_id ? (
                        <a href={`/tasks?id=${pr.task_id}`} style={{ color: '#90cdf4', fontSize: 12 }}>
                          #{pr.task_id}
                        </a>
                      ) : <span style={{ color: '#4a5568', fontSize: 12 }}>—</span>}
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
          <EmptyState icon="🚀" title="No hay deployments" description="Los deployments aparecerán aquí cuando el webhook reciba eventos de GitHub/GitLab." />
        ) : (
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Repo', 'SHA', 'Entorno', 'Estado', 'Tarea', 'Desplegado'].map(h => (
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
                      {d.sha ? d.sha.slice(0, 8) : '—'}
                    </td>
                    <td style={cell}>
                      <span style={{
                        background: '#2d3748', color: '#e2e8f0', borderRadius: 6,
                        padding: '2px 8px', fontSize: 11, fontWeight: 600,
                      }}>{d.environment || 'production'}</span>
                    </td>
                    <td style={cell}><DeployPill status={d.status} /></td>
                    <td style={cell}>
                      {d.task_id ? (
                        <a href={`/tasks?id=${d.task_id}`} style={{ color: '#90cdf4', fontSize: 12 }}>
                          #{d.task_id}
                        </a>
                      ) : <span style={{ color: '#4a5568', fontSize: 12 }}>—</span>}
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
            title="GitHub"
            icon="🐙"
            webhookPath="/api/v1/git/webhooks/github"
            envVar="GITHUB_WEBHOOK_SECRET"
            events={['pull_request', 'deployment_status', 'push']}
            steps={[
              'Ve a tu repositorio → Settings → Webhooks → Add webhook',
              `Payload URL: https://tu-dominio.com/api/v1/git/webhooks/github`,
              'Content type: application/json',
              'Secret: el valor de GITHUB_WEBHOOK_SECRET en tu .env',
              'Events: Pull requests, Deployment statuses, Pushes',
            ]}
          />
          <ConfigSection
            title="GitLab"
            icon="🦊"
            webhookPath="/api/v1/git/webhooks/gitlab"
            envVar="GITLAB_WEBHOOK_SECRET"
            events={['merge_requests', 'deployment']}
            steps={[
              'Ve a tu proyecto → Settings → Webhooks',
              `URL: https://tu-dominio.com/api/v1/git/webhooks/gitlab`,
              'Secret token: el valor de GITLAB_WEBHOOK_SECRET en tu .env',
              'Triggers: Merge request events, Deployment events',
            ]}
          />
          <div style={{
            background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20,
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e2e8f0' }}>🔗 Vinculación automática de tareas</h3>
            <p style={{ fontSize: 13, color: '#a0aec0', margin: '0 0 8px' }}>
              Clarive detecta automáticamente referencias a tareas en el nombre de la rama o título del PR:
            </p>
            <ul style={{ fontSize: 13, color: '#a0aec0', paddingLeft: 20, lineHeight: 1.8 }}>
              <li>Código de tarea: <code style={{ color: '#90cdf4' }}>PROJ-123</code> (mayúsculas, guion, número)</li>
              <li>ID de tarea: <code style={{ color: '#90cdf4' }}>#456</code></li>
            </ul>
            <p style={{ fontSize: 12, color: '#718096', marginTop: 8 }}>
              Ejemplo de rama: <code style={{ color: '#68d391' }}>feature/PROJ-42-add-login</code>
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
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 4 }}>WEBHOOK URL</div>
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
            {copied ? '✓' : 'Copiar'}
          </button>
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 4 }}>VARIABLE DE ENTORNO</div>
        <code style={{ fontSize: 12, color: '#f6e05e' }}>{envVar}=tu-secreto-largo</code>
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 6 }}>EVENTOS RECOMENDADOS</div>
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
        <div style={{ fontSize: 11, color: '#718096', marginBottom: 6 }}>PASOS</div>
        <ol style={{ padding: 0, paddingLeft: 18, margin: 0, fontSize: 12, color: '#a0aec0', lineHeight: 2 }}>
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </div>
  )
}
