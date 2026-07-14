import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { alertsApi } from '../services/api'
import { Button, Spinner, EmptyState, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import SmartAlertsPanel from '../components/bi/SmartAlertsPanel'
import { Bell, ExternalLink, Brain } from 'lucide-react'
import { fmtRelative, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

function alertSourceUrl(alert: any) {
  if (alert.project?.id) return `/projects/${alert.project.id}`
  const t = alert.alert_type
  if (t === 'task_blocked' || t === 'hours_deviation') return '/tasks'
  if (t === 'overload' || t === 'burnout_risk' || t === 'no_imputation') return '/team'
  return null
}

const SEVERITY_CONFIG = {
  critical: { bg: 'var(--danger-bg)', border: 'var(--danger-border)', dot: 'var(--danger)', label: 'alerts.severity_critical' },
  warning:  { bg: 'var(--warning-bg)', border: 'var(--warning-border)', dot: 'var(--warning)', label: 'alerts.severity_warning' },
  info:     { bg: 'var(--accent-muted)', border: 'var(--accent-glow)', dot: 'var(--accent)', label: 'alerts.severity_info' },
}

const TYPE_ICONS = {
  overload: '🔥',
  burnout_risk: '⚠️',
  budget_exceeded: '💰',
  budget_critical: '🚨',
  deadline_risk: '📅',
  task_blocked: '🔒',
  hours_deviation: '⏱️',
  no_imputation: '📋',
}

export default function AlertsPage(): JSX.Element {
  const t = useAppT()
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [tab, setTab] = useState<string>('operational')

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts-page'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data?.items ?? r.data ?? []),
    refetchInterval: 30_000,
    enabled: tab === 'operational',
  })

  const { mutate: runEngine, isPending: running } = useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-page'] }),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: resolve } = useMutation({
    mutationFn: (id: any) => alertsApi.resolve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-page'] }),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: markRead } = useMutation({
    mutationFn: (id: any) => alertsApi.read(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-page'] }),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const unread = alerts.filter((a: any) => !a.is_read).length
  const bySeverity: Record<string, any[]> = {
    critical: alerts.filter((a: any) => a.severity === 'critical'),
    warning:  alerts.filter((a: any) => a.severity === 'warning'),
    info:     alerts.filter((a: any) => a.severity === 'info'),
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('alerts.title')}
        subtitle={tab === 'operational'
          ? t('alerts.subtitle_active_unread', { active: alerts.length, unread })
          : 'Alertas inteligentes basadas en forecasting, anomalías y tendencias'}
        actions={
          tab === 'operational' && hasRole('admin') && (
            <Button onClick={() => runEngine()} disabled={running} icon="⚡">
              {running ? t('alerts.running_engine') : t('alerts.run_engine')}
            </Button>
          )
        }
        showListExport={tab === 'operational' && alerts.length > 0}
        exportTargetSelector='[data-export-table="alerts-list"]'
        exportFilePrefix='alerts'
      />

      <Tabs
        items={[
          { id: 'operational', label: 'Operativas', icon: <Bell size={14} />, count: alerts.length || undefined },
          { id: 'smart',       label: 'Inteligentes', icon: <Brain size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Tipos de alertas"
      />

      {tab === 'smart' && <SmartAlertsPanel />}

      {tab === 'operational' && <>
      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 28 }}>
        {Object.entries(SEVERITY_CONFIG).map(([sev, cfg]) => (
          <div key={sev} style={{
            flex: 1, background: cfg.bg, border: `1px solid ${cfg.border}`,
            borderRadius: 12, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: cfg.dot }} />
            <div>
              <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: cfg.dot }}>
                {bySeverity[sev].length}
              </div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t(cfg.label)}</div>
            </div>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><Spinner /><span style={{ color: 'var(--text-2)' }}>{t('alerts.loading')}</span></div>
      ) : alerts.length === 0 ? (
        <EmptyState icon="✅" title={t('alerts.no_alerts')} description={t('alerts.empty_description')} />
      ) : (
        <div data-export-table="alerts-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map((alert: any) => {
            const cfg = SEVERITY_CONFIG[alert.severity as keyof typeof SEVERITY_CONFIG] || SEVERITY_CONFIG.info
            const sourceUrl = alertSourceUrl(alert)
            return (
              <div key={alert.id} style={{
                display: 'flex', gap: 16, padding: '16px 20px',
                background: alert.is_read ? 'var(--surface-2)' : cfg.bg,
                border: `1px solid ${alert.is_read ? 'var(--surface-4)' : cfg.border}`,
                borderRadius: 12, alignItems: 'flex-start',
                opacity: alert.is_resolved ? 0.5 : 1,
              }}>
                {/* Dot */}
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: cfg.dot, marginTop: 4, flexShrink: 0 }} />

                {/* Icon + content */}
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: "var(--text-lg-em)" }}>{TYPE_ICONS[alert.alert_type as keyof typeof TYPE_ICONS] || '🔔'}</span>
                      <div>
                        <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{alert.title}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {alert.alert_type} · {fmtRelative(alert.created_at)}
                          {alert.project?.name && <span style={{ marginLeft: 6, color: cfg.dot }}>· {alert.project.name}</span>}
                          {alert.user?.display_name && <span style={{ marginLeft: 6 }}>· {alert.user.display_name}</span>}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {sourceUrl && (
                        <button onClick={() => navigate(sourceUrl)}
                          style={{ background: 'transparent', border: `1px solid ${cfg.border}`, borderRadius: 6, padding: '4px 10px', color: cfg.dot, cursor: 'pointer', fontSize: "var(--text-xs)", display: 'flex', alignItems: 'center', gap: 4 }}>
                          <ExternalLink size={10} /> Ver origen
                        </button>
                      )}
                      {!alert.is_read && (
                        <button onClick={() => markRead(alert.id)}
                          style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                          {t('alerts.mark_as_read')}
                        </button>
                      )}
                      {hasRole('admin', 'pm', 'hr') && (
                        <button onClick={() => resolve(alert.id)}
                          style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 600 }}>
                          Resolver
                        </button>
                      )}
                    </div>
                  </div>
                  {alert.description && (
                    <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginTop: 6, marginLeft: 26 }}>{alert.description}</p>
                  )}
                  {alert.value !== null && alert.threshold !== null && (
                    <div style={{ marginLeft: 26, marginTop: 8, fontSize: "var(--text-sm)" }}>
                      <span style={{ color: cfg.dot, fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                        {alert.value?.toFixed(0)}{alert.alert_type.includes('budget') ? '€' : '%'}
                      </span>
                      <span style={{ color: 'var(--text-3)' }}> / {t('alerts.threshold_label')} {alert.threshold?.toFixed(0)}{alert.alert_type.includes('budget') ? '€' : '%'}</span>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
      </>}
    </PageShell>
  )
}
