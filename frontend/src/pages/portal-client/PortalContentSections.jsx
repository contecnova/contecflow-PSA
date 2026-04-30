import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CLIENT_API,
  useLang,
  useClientAuth,
} from './portalClientContext'

export function PortalDashboard() {
  const [selectedProjectId, setSelectedProjectId] = useState(
    () => localStorage.getItem('portal_selected_project') || null
  )
  const t = useLang()
  const { client, isReady } = useClientAuth()
  const allowedProjectIds = Array.isArray(client?.project_ids)
    ? client.project_ids.filter(Boolean)
    : []
  const hasProjectAccessList = isReady && allowedProjectIds.length > 0
  const hasValidSelectedProject = selectedProjectId && (!hasProjectAccessList || allowedProjectIds.includes(selectedProjectId))
  const effectiveProjectId = hasValidSelectedProject ? selectedProjectId : null

  useEffect(() => {
    if (!isReady || !selectedProjectId || !hasProjectAccessList || hasValidSelectedProject) return
    localStorage.removeItem('portal_selected_project')
    setSelectedProjectId(null)
  }, [hasProjectAccessList, hasValidSelectedProject, isReady, selectedProjectId])

  const params = effectiveProjectId ? { project_id: effectiveProjectId } : {}
  const { data, isLoading } = useQuery({
    queryKey: ['portal-dashboard', effectiveProjectId],
    enabled: isReady,
    queryFn: async () => {
      try {
        const response = await CLIENT_API.get('/portal/dashboard', { params })
        return response.data
      } catch (error) {
        if (error?.response?.status === 403 && effectiveProjectId) {
          localStorage.removeItem('portal_selected_project')
          setSelectedProjectId(null)
          const fallback = await CLIENT_API.get('/portal/dashboard')
          return fallback.data
        }
        throw error
      }
    },
    retry: (failureCount, error) => {
      if (error?.response?.status === 403) return false
      return failureCount < 2
    },
    refetchOnWindowFocus: false,
  })

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300, color: 'var(--text-2)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 12 }}>◈</div>
        {t('dashboard_loading')}
      </div>
    </div>
  )
  if (!data) return null

  if (data.needs_project_selection) {
    return (
      <div>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, marginBottom: 4 }}>
            {t('dashboard_welcome').replace('{{name}}', client?.full_name?.split(' ')[0] || '')}
          </div>
          <div style={{ fontSize: "var(--text-md)", color: 'var(--text-2)' }}>
            {t('dashboard_choose_project_cta').replace('{{count}}', String(data.projects?.length || 0))}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
          {(data.projects || []).map(p => (
            <div key={p.id} role="button" tabIndex={0} onClick={() => {
              setSelectedProjectId(p.id)
              localStorage.setItem('portal_selected_project', p.id)
            }}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedProjectId(p.id); localStorage.setItem('portal_selected_project', p.id) } }}
              aria-label={`Abrir proyecto ${p.name}`}
              style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 14,
                padding: '20px 22px', cursor: 'pointer', transition: 'border-color .15s',
                ':hover': { borderColor: 'var(--accent)' } }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.06em' }}>{p.code}</div>
              <div style={{ fontSize: "var(--text-17)", fontWeight: 700, marginBottom: 8 }}>{p.name}</div>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 9px', borderRadius: 20,
                background: p.status === 'active' ? 'var(--success-border)' : '#94a3b820',
                color: p.status === 'active' ? 'var(--success)' : '#94a3b8',
                border: `1px solid ${p.status === 'active' ? 'var(--success-border)' : '#94a3b840'}`,
                textTransform: 'uppercase' }}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!data.project) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: 300, textAlign: 'center', gap: 12 }}>
      <div style={{ fontSize: "var(--text-5xl)" }}>🏗</div>
      <div style={{ fontSize: "var(--text-17)", fontWeight: 700, color: 'var(--text-1)' }}>{t('dashboard_not_configured')}</div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', maxWidth: 380, lineHeight: 1.6 }}>
        {data.message || t('dashboard_not_configured_hint')}
      </div>
    </div>
  )

  const { project, kpis, next_milestone, recent_activity } = data
  const budgetPct = kpis?.budget_total > 0 ? Math.round((kpis.budget_spent / kpis.budget_total) * 100) : 0

  return (
    <div>
      <div style={{ marginBottom: 28, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, marginBottom: 4 }}>
            {t('dashboard_welcome').replace('{{name}}', client?.full_name?.split(' ')[0] || '')}
          </div>
          <div style={{ fontSize: "var(--text-md)", color: 'var(--text-2)' }}>
            {project?.name || t('portal')} · {new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </div>
        {(client?.projects?.length > 1 || client?.project_ids?.length > 1) && (
          <button onClick={() => { setSelectedProjectId(null); localStorage.removeItem('portal_selected_project') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
              padding: '7px 14px', color: 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer',
              fontFamily: 'inherit', fontWeight: 600 }}>
            ⇆ {t('dashboard_change_project')}
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 14, marginBottom: 28 }}>
        {[
          { icon: '📦', label: t('kpi_deliverables'), value: `${kpis?.deliverables_approved || 0}/${kpis?.deliverables_total || 0}`, sub: t('kpi_approved'), color: 'var(--success)' },
          { icon: '🧪', label: t('kpi_uat'), value: `${kpis?.uat_passed || 0}/${kpis?.uat_total || 0}`, sub: t('kpi_passed'), color: 'var(--accent)' },
          { icon: '💡', label: t('kpi_requests'), value: kpis?.feature_requests_open || 0, sub: t('kpi_pending'), color: 'var(--warning)' },
          { icon: '🎫', label: t('kpi_tickets'), value: kpis?.tickets_open || 0, sub: t('kpi_open'), color: 'var(--purple)' },
          { icon: '💬', label: t('kpi_messages'), value: kpis?.unread_messages || 0, sub: t('kpi_unread'), color: 'var(--warning)' },
        ].map(k => (
          <div key={k.label} style={{
            background: 'var(--surface-1)', border: `1px solid ${k.color}20`,
            borderRadius: 12, padding: '16px 18px',
          }}>
            <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 8 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color, marginBottom: 2, fontFamily: 'var(--font-mono)' }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>{k.label}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{t('dashboard_budget_section')}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('stats_budget_consumed')}</span>
            <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)' }}>
              {budgetPct}%
            </span>
          </div>
          <div style={{ height: 8, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden', marginBottom: 12 }}>
            <div style={{
              width: `${Math.min(budgetPct, 100)}%`, height: '100%', borderRadius: 4,
              background: budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)',
              transition: 'width 0.5s ease',
            }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
            <span>{t('dashboard_budget_spent')}: <strong style={{ color: 'var(--text-1)' }}>{kpis?.budget_spent?.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' }) || '—'}</strong></span>
            <span>{t('dashboard_budget_total')}: <strong style={{ color: 'var(--text-1)' }}>{kpis?.budget_total?.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' }) || '—'}</strong></span>
          </div>
        </div>

        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{t('dashboard_next_milestone')}</div>
          {next_milestone ? (
            <>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{next_milestone.title}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>{next_milestone.due_date}</div>
              <div style={{ fontSize: "var(--text-xs)", padding: '4px 10px', borderRadius: 20, display: 'inline-flex',
                background: 'var(--accent-muted)', color: 'var(--accent)', fontWeight: 700 }}>
                {next_milestone.days_remaining > 0 ? t('dashboard_days_remaining').replace('{{n}}', next_milestone.days_remaining) : t('dashboard_today')}
              </div>
            </>
          ) : (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', padding: '20px 0', textAlign: 'center' }}>
              {t('dashboard_no_milestone')}
            </div>
          )}
        </div>
      </div>

      {recent_activity?.length > 0 && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{t('dashboard_activity')}</div>
          {recent_activity.slice(0, 5).map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, padding: '8px 0',
              borderBottom: i < 4 ? '1px solid var(--surface-4)' : 'none', alignItems: 'flex-start' }}>
              <span style={{ fontSize: "var(--text-lg)", flexShrink: 0 }}>
                {item.type === 'deliverable' ? '📦' : item.type === 'message' ? '💬' : item.type === 'uat' ? '🧪' : '●'}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>{item.description}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>{item.date?.slice(0, 16)?.replace('T', ' ')}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

