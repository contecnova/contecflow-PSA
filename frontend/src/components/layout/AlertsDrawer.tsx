import { useEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../../services/api'
import { X, Bell, ExternalLink } from 'lucide-react'
import { fmtRelative } from '../../utils/helpers'
import { useAuth } from '../../context/AuthContext'
import { useAppLang } from '../../i18n/AppLangContext'

interface SeverityCfg {
  dot: string
  bg: string
  border: string
  label: string
}

const SEVERITY_CFG: Record<string, SeverityCfg> = {
  critical: { dot: 'var(--danger)',  bg: 'var(--danger-bg)',  border: 'var(--danger-border)',  label: 'Crítica' },
  warning:  { dot: 'var(--warning)', bg: 'var(--warning-bg)', border: 'var(--warning-border)', label: 'Aviso' },
  info:     { dot: 'var(--accent)',  bg: 'var(--accent-muted)', border: 'var(--accent-glow)',   label: 'Info' },
}

const TYPE_ICONS: Record<string, string> = {
  overload: '🔥', burnout_risk: '⚠️', budget_exceeded: '💰', budget_critical: '🚨',
  deadline_risk: '📅', task_blocked: '🔒', hours_deviation: '⏱️', no_imputation: '📋',
}

// TODO type: backend alert payload — needs shared type from alertsApi
interface AlertItem {
  id: string | number
  severity: string
  alert_type?: string
  title: string
  description?: string
  created_at: string
  is_read?: boolean
}

interface Props {
  onClose: () => void
}

export default function AlertsDrawer({ onClose }: Props) {
  const { t } = useAppLang()
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const drawerRef = useRef<HTMLDivElement | null>(null)

  const { data: alerts = [], isLoading } = useQuery<AlertItem[]>({
    queryKey: ['alerts-drawer'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data?.items ?? r.data ?? []),
    refetchInterval: 30_000,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: (id: AlertItem['id']) => alertsApi.resolve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts-drawer'] })
      qc.invalidateQueries({ queryKey: ['alerts-page'] })
      qc.invalidateQueries({ queryKey: ['notification-badges'] })
    },
  })

  const { mutate: markRead } = useMutation({
    mutationFn: (id: AlertItem['id']) => alertsApi.read(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts-drawer'] })
      qc.invalidateQueries({ queryKey: ['notification-badges'] })
    },
  })

  // Close on Escape + focus trap
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    drawerRef.current?.focus()
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const critical = alerts.filter(a => a.severity === 'critical')
  const warning  = alerts.filter(a => a.severity === 'warning')
  const info     = alerts.filter(a => a.severity === 'info')

  return (
    <>
      {/* Backdrop */}
      <div
        role="presentation"
        onMouseDown={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.35)',
        }}
      />

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        tabIndex={-1}
        role="dialog"
        aria-label="Alertas activas"
        aria-modal="true"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 400, maxWidth: '95vw',
          background: 'var(--surface-1)',
          borderLeft: '1px solid var(--surface-4)',
          zIndex: 201,
          display: 'flex', flexDirection: 'column',
          boxShadow: '-8px 0 32px rgba(0,0,0,0.4)',
          outline: 'none',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid var(--surface-4)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Bell size={16} color="var(--text-1)" />
            <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>Alertas activas</span>
            {alerts.length > 0 && (
              <span style={{
                fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px',
                background: 'var(--danger-bg)', color: 'var(--danger)',
                border: '1px solid var(--danger-border)', borderRadius: 20,
              }}>{alerts.length}</span>
            )}
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', padding: 4, borderRadius: 6, display: 'flex',
          }}>
            <X size={16} />
          </button>
        </div>

        {/* Severity summary */}
        {alerts.length > 0 && (
          <div style={{
            display: 'flex', gap: 8, padding: '10px 20px',
            borderBottom: '1px solid var(--surface-4)', flexShrink: 0,
          }}>
            {[
              { label: 'Críticas', count: critical.length, color: 'var(--danger)' },
              { label: 'Avisos',   count: warning.length,  color: 'var(--warning)' },
              { label: 'Info',     count: info.length,     color: 'var(--accent)' },
            ].map(({ label, count, color }) => count > 0 && (
              <div key={label} style={{
                flex: 1, textAlign: 'center', padding: '8px 4px',
                background: 'var(--surface-3)', borderRadius: 8,
              }}>
                <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>{count}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Alert list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <div style={{ width: 24, height: 24, border: '3px solid var(--surface-4)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            </div>
          ) : alerts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-3)' }}>
              <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>✅</div>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-2)' }}>{t('alertsdrawer.sin_alertas_activas')}</div>
              <div style={{ fontSize: "var(--text-sm)", marginTop: 4 }}>{t('alertsdrawer.todo_esta_en_orden')}</div>
            </div>
          ) : (
            alerts.slice(0, 20).map(alert => {
              const cfg = SEVERITY_CFG[alert.severity] || SEVERITY_CFG.info
              return (
                <div
                  key={alert.id}
                  style={{
                    marginBottom: 8, padding: '12px 14px',
                    background: alert.is_read ? 'var(--surface-2)' : cfg.bg,
                    border: `1px solid ${alert.is_read ? 'var(--surface-4)' : cfg.border}`,
                    borderRadius: 10,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.dot, marginTop: 5, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                        <span style={{ fontSize: "var(--text-md)" }}>{(alert.alert_type && TYPE_ICONS[alert.alert_type]) || '🔔'}</span>
                        <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>{alert.title}</span>
                      </div>
                      {alert.description && (
                        <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', margin: '0 0 6px', lineHeight: 1.4 }}>
                          {alert.description}
                        </p>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                        <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {fmtRelative(alert.created_at)}
                        </span>
                        <div style={{ display: 'flex', gap: 5 }}>
                          {!alert.is_read && (
                            <button onClick={() => markRead(alert.id)} style={{
                              background: 'transparent', border: '1px solid var(--surface-4)',
                              borderRadius: 5, padding: '3px 8px', color: 'var(--text-2)',
                              cursor: 'pointer', fontSize: "var(--text-2xs)", fontFamily: 'inherit',
                            }}>
                              {t('alertsdrawer.leida')}
                            </button>
                          )}
                          {hasRole('admin', 'pm', 'hr') && (
                            <button onClick={() => resolve(alert.id)} style={{
                              background: 'var(--success-bg)', border: '1px solid var(--success-border)',
                              borderRadius: 5, padding: '3px 8px', color: 'var(--success)',
                              cursor: 'pointer', fontSize: "var(--text-2xs)", fontWeight: 600, fontFamily: 'inherit',
                            }}>
                              Resolver
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--surface-4)',
          flexShrink: 0,
        }}>
          <NavLink
            to="/alerts"
            onClick={onClose}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
              padding: '9px', borderRadius: 8,
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              color: 'var(--text-2)', textDecoration: 'none', fontSize: "var(--text-base)", fontWeight: 600,
              transition: 'all 0.1s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
          >
            <ExternalLink size={13} />
            {t('alertsdrawer.ver_todas_las_alertas')}
          </NavLink>
        </div>
      </div>
    </>
  )
}
