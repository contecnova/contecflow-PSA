import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { alertsApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Bell } from 'lucide-react'
import { fmtRelative, extractErr} from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

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

export default function AlertsPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts-page'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data),
    refetchInterval: 30_000,
  })

  const { mutate: runEngine, isPending: running } = useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries(['alerts-page']),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: resolve } = useMutation({
    mutationFn: (id) => alertsApi.resolve(id),
    onSuccess: () => qc.invalidateQueries(['alerts-page']),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: markRead } = useMutation({
    mutationFn: (id) => alertsApi.read(id),
    onSuccess: () => qc.invalidateQueries(['alerts-page']),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const unread = alerts.filter(a => !a.is_read).length
  const bySeverity = {
    critical: alerts.filter(a => a.severity === 'critical'),
    warning:  alerts.filter(a => a.severity === 'warning'),
    info:     alerts.filter(a => a.severity === 'info'),
  }

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('alerts.title')}
        subtitle={t('alerts.subtitle_active_unread', { active: alerts.length, unread })}
        actions={
          hasRole('admin') && (
            <Button onClick={() => runEngine()} disabled={running} icon="⚡">
              {running ? t('alerts.running_engine') : t('alerts.run_engine')}
            </Button>
          )
        }
      />

      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 28 }}>
        {Object.entries(SEVERITY_CONFIG).map(([sev, cfg]) => (
          <div key={sev} style={{
            flex: 1, background: cfg.bg, border: `1px solid ${cfg.border}`,
            borderRadius: 12, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: cfg.dot }} />
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: cfg.dot }}>
                {bySeverity[sev].length}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t(cfg.label)}</div>
            </div>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><Spinner /><span style={{ color: 'var(--text-2)' }}>{t('alerts.loading')}</span></div>
      ) : alerts.length === 0 ? (
        <EmptyState icon="✅" title={t('alerts.no_alerts')} description={t('alerts.empty_description')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map(alert => {
            const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info
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
                      <span style={{ fontSize: 18 }}>{TYPE_ICONS[alert.alert_type] || '🔔'}</span>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>{alert.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {alert.alert_type} · {fmtRelative(alert.created_at)}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {!alert.is_read && (
                        <button onClick={() => markRead(alert.id)}
                          style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>
                          {t('alerts.mark_as_read')}
                        </button>
                      )}
                      {hasRole('admin', 'pm', 'hr') && (
                        <button onClick={() => resolve(alert.id)}
                          style={{ background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 6, padding: '4px 10px', color: 'var(--success)', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}>
                          Resolver
                        </button>
                      )}
                    </div>
                  </div>
                  {alert.description && (
                    <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6, marginLeft: 26 }}>{alert.description}</p>
                  )}
                  {alert.value !== null && alert.threshold !== null && (
                    <div style={{ marginLeft: 26, marginTop: 8, fontSize: 12 }}>
                      <span style={{ color: cfg.dot, fontFamily: "'Space Mono', monospace", fontWeight: 700 }}>
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
    </div>
  )
}
