import { NavLink } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../../services/api'
import type { Alerta } from '../../services/api/tipos-documentos'
import { X, Bell, ExternalLink } from 'lucide-react'
import { fmtRelative } from '../../utils/helpers'
import { useAuth } from '../../context/AuthContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { Drawer } from '../ui'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './AlertsDrawer.css'
import type { CSSProperties } from 'react'

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
  overload: '🔥', burnout_risk: '⚠️', budget_exceeded: '💰', budget_critical: '🚨', automation: '⚙️',
  deadline_risk: '📅', task_blocked: '🔒', hours_deviation: '⏱️', no_imputation: '📋',
}

type AlertItem = Alerta

interface Props {
  onClose: () => void
}

export default function AlertsDrawer({ onClose }: Props) {
  const { t } = useAppLang()
  const { hasRole } = useAuth()
  const qc = useQueryClient()

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts-drawer'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: (id: AlertItem['id']) => alertsApi.resolve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts-drawer'] })
      qc.invalidateQueries({ queryKey: ['alerts-page'] })
      qc.invalidateQueries({ queryKey: ['alerts-count'] })
    },
  })

  const { mutate: markRead } = useMutation({
    mutationFn: (id: AlertItem['id']) => alertsApi.read(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts-drawer'] })
      qc.invalidateQueries({ queryKey: ['alerts-count'] })
    },
  })

  const critical = alerts.filter(a => a.severity === 'critical')
  const warning  = alerts.filter(a => a.severity === 'warning')
  const info     = alerts.filter(a => a.severity === 'info')

  return (
    // Fondo, Esc, trampa de foco y devolucion del foco: los pone <Drawer>.
    <Drawer onClose={onClose} ariaLabel="Alertas activas" variant="borde" width={400} zIndex={200}>
        {/* Header */}
        <div className="alerdraw-row-1">
          <div className="u-row-center-10">
            <Bell size={16} color="var(--text-1)" />
            <span className="alerdraw-txt-1">{t('layoutshell.alertas_activas')}</span>
            {alerts.length > 0 && (
              <span className="alerdraw-box-1">{alerts.length}</span>
            )}
          </div>
          <button type="button" onClick={onClose} aria-label={t('common.close')} className="alerdraw-row-2">
            <X size={16} />
          </button>
        </div>

        {/* Severity summary */}
        {alerts.length > 0 && (
          <div className="alerdraw-row-3">
            {[
              { label: 'Críticas', count: critical.length, color: 'var(--danger)' },
              { label: 'Avisos',   count: warning.length,  color: 'var(--warning)' },
              { label: 'Info',     count: info.length,     color: 'var(--accent)' },
            ].map(({ label, count, color }) => count > 0 && (
              <div key={label} className="alerdraw-box-2">
                <div className="alerdraw-txt-7 alerts-drawer-e1" style={{ '--alerts-drawer-color': color } as CSSProperties}>{count}</div>
                <div className="alerdraw-txt-2">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Alert list */}
        <div className="alerdraw-box-3">
          {isLoading ? (
            <div className="alerdraw-row-4">
              <div className="alerdraw-box-4" />
            </div>
          ) : alerts.length === 0 ? (
            <div className="alerdraw-box-5">
              <div className="alerdraw-box-6">✅</div>
              <div className="alerdraw-txt-3">{t('alertsdrawer.sin_alertas_activas')}</div>
              <div className="alerdraw-box-7">{t('alertsdrawer.todo_esta_en_orden')}</div>
            </div>
          ) : (
            alerts.slice(0, 20).map(alert => {
              const cfg = SEVERITY_CFG[alert.severity] || SEVERITY_CFG.info
              return (
                <div className="alerdraw-sp-1 alertsdr-sx1 alerts-drawer-e2"
                  key={alert.id}
                  style={{ '--alerts-drawer-background': alert.is_read ? 'var(--surface-2)' : cfg.bg, '--alerts-drawer-border': `1px solid ${alert.is_read ? 'var(--surface-4)' : cfg.border}` } as CSSProperties}
                >
                  <div className="alerdraw-row-5">
                    <div className="alerdraw-box-12 alerts-drawer-e3" style={{ '--alerts-drawer-background': cfg.dot } as CSSProperties} />
                    <div className="u-flex1-min0">
                      <div className="alerdraw-row-6">
                        <span className="alerdraw-txt-4">{(alert.alert_type && TYPE_ICONS[alert.alert_type]) || '🔔'}</span>
                        <span className="alerdraw-txt-5">{alert.title}</span>
                      </div>
                      {alert.description && (
                        <p className="alerdraw-box-8">
                          {alert.description}
                        </p>
                      )}
                      <div className="alerdraw-row-7">
                        <span className="alerdraw-txt-6">
                          {fmtRelative(alert.created_at)}
                        </span>
                        <div className="alerdraw-row-8">
                          {!alert.is_read && (
                            <button onClick={() => markRead(alert.id)} className="alerdraw-box-9">
                              {t('alertsdrawer.leida')}
                            </button>
                          )}
                          {hasRole('admin', 'pm', 'hr') && (
                            <button type="button" onClick={() => resolve(alert.id)} className="alerdraw-box-10">
                              {t('layoutshell.resolver')}
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
        <div className="alerdraw-box-11">
          <NavLink
            to="/alerts"
            onClick={onClose} className="alertsdr-sx2"
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)' }}
          >
            <ExternalLink size={13} />
            {t('alertsdrawer.ver_todas_las_alertas')}
          </NavLink>
        </div>
    </Drawer>
  )
}
