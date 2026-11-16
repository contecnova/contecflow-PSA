import { useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { alertsApi, type PathId } from '../services/api'
import type { Alerta } from '../services/api/tipos-documentos'
import { Button, Spinner, EmptyState, Tabs, KpiCard } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import SmartAlertsPanel from '../components/bi/SmartAlertsPanel'
import {
  Bell, ExternalLink, Brain, Zap, CheckCircle2, Check, Flame, AlertTriangle, Wallet, Settings, Siren, CalendarClock,
  Lock, Timer, ClipboardList, AlertOctagon, Info,
} from 'lucide-react'
import { fmtRelative, fmtNumber, extractErr } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { POLL_FREQUENT_MS } from '../constants/timings'
import './AlertsPage.css'

type Alert = Alerta

function alertSourceUrl(alert: Alert) {
  if (alert.project?.id) return `/projects/${alert.project.id}`
  const t = alert.alert_type
  if (t === 'task_blocked' || t === 'hours_deviation') return '/tasks'
  if (t === 'overload' || t === 'burnout_risk' || t === 'no_imputation') return '/team'
  return null
}

// Los colores de cada severidad viven en AlertsPage.css (.alr-sev--*).
const SEVERITY_CONFIG = {
  critical: { label: 'alerts.severity_critical' },
  warning:  { label: 'alerts.severity_warning' },
  info:     { label: 'alerts.severity_info' },
}

const TYPE_ICONS: Record<string, ReactNode> = {
  overload: <Flame size={16} />,
  burnout_risk: <AlertTriangle size={16} />,
  budget_exceeded: <Wallet size={16} />,
  automation: <Settings size={16} />,
  budget_critical: <Siren size={16} />,
  deadline_risk: <CalendarClock size={16} />,
  task_blocked: <Lock size={16} />,
  hours_deviation: <Timer size={16} />,
  no_imputation: <ClipboardList size={16} />,
}

export default function AlertsPage(): JSX.Element {
  const t = useAppT()
  // La unidad viene de Ajustes → Alertas: «days» se traduce, el resto («%») va tal cual.
  const unidad = (u?: string | null) => (u === 'days' ? ` ${t('alerts.dias')}` : u || '')
  // Tipos conocidos traducidos; uno nuevo del backend se enseña tal cual.
  const tipoAlerta = (tipo: string) => (tipo in TYPE_ICONS ? t(`alerts.alert_type_${tipo}`) : tipo)
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [tab, setTab] = useState<string>('operational')

  const { data: alerts = [], isLoading } = useQuery<Alert[]>({
    queryKey: ['alerts-page'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
    enabled: tab === 'operational',
  })

  const { mutate: runEngine, isPending: running } = useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-page'] }),
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: resolve } = useMutation({
    mutationFn: (id: PathId) => alertsApi.resolve(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts-page'] }); qc.invalidateQueries({ queryKey: ['alerts-count'] }) },
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const { mutate: markRead } = useMutation({
    mutationFn: (id: PathId) => alertsApi.read(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts-page'] }); qc.invalidateQueries({ queryKey: ['alerts-count'] }) },
    onError: e => toast.error(extractErr(e, t('alerts.generic_error'))),
  })

  const unread = alerts.filter((a) => !a.is_read).length
  const bySeverity: Record<string, Alert[]> = {
    critical: alerts.filter((a) => a.severity === 'critical'),
    warning:  alerts.filter((a) => a.severity === 'warning'),
    info:     alerts.filter((a) => a.severity === 'info'),
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('alerts.title')}
        subtitle={tab === 'operational'
          ? t('alerts.subtitle_active_unread', { active: alerts.length, unread })
          : t('alerts.subtitle_smart')}
        actions={
          tab === 'operational' && hasRole('admin') && (
            <Button onClick={() => runEngine()} disabled={running} loading={running} icon={<Zap size={14} />}>
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
          { id: 'operational', label: t('alerts.tab_operational'), icon: <Bell size={14} />, count: alerts.length || undefined },
          { id: 'smart',       label: t('alerts.tab_smart'), icon: <Brain size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('alerts.tabs_aria')}
      />

      {tab === 'smart' && <SmartAlertsPanel />}

      {tab === 'operational' && <>
      {/* Summary cards */}
      <div className="ds-grid-stats alr-summary">
        <KpiCard icon={<AlertOctagon size={16} />} label={t(SEVERITY_CONFIG.critical.label)} value={bySeverity.critical.length} danger={bySeverity.critical.length > 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t(SEVERITY_CONFIG.warning.label)} value={bySeverity.warning.length} warning={bySeverity.warning.length > 0} />
        <KpiCard icon={<Info size={16} />} label={t(SEVERITY_CONFIG.info.label)} value={bySeverity.info.length} />
      </div>

      {isLoading ? (
        <div className="u-row-center-12"><Spinner /><span className="u-text2">{t('alerts.loading')}</span></div>
      ) : alerts.length === 0 ? (
        <div className="ds-card"><EmptyState icon={<CheckCircle2 size={28} />} title={t('alerts.no_alerts')} description={t('alerts.empty_description')} /></div>
      ) : (
        <div data-export-table="alerts-list" className="u-stack-10">
          {alerts.map((alert) => {
            const sev = alert.severity && alert.severity in SEVERITY_CONFIG ? alert.severity : 'info'
            const sourceUrl = alertSourceUrl(alert)
            return (
              <div key={alert.id}
                className={`alr-item alr-sev--${sev}${alert.is_read ? ' is-read' : ''}${alert.is_resolved ? ' is-resolved' : ''}`}>
                {/* Dot */}
                <div className="alr-dot alr-dot--item" aria-hidden="true" />

                {/* Icon + content */}
                <div className="u-flex1-min0">
                  <div className="alr-item-head">
                    <div className="u-row-center-8">
                      <span className="alr-type-icon" aria-hidden="true">{TYPE_ICONS[alert.alert_type] || <Bell size={16} />}</span>
                      <div>
                        <div className="u-md-700">{alert.title}</div>
                        <div className="alr-meta">
                          {tipoAlerta(alert.alert_type)} · {fmtRelative(alert.created_at)}
                          {alert.project?.name && <span className="alr-meta-sep alr-meta-project">· {alert.project.name}</span>}
                          {alert.user?.full_name && <span className="alr-meta-sep">· {alert.user.full_name}</span>}
                        </div>
                      </div>
                    </div>
                    <div className="alr-actions">
                      {sourceUrl && (
                        <Button variant="ghost" size="sm" icon={<ExternalLink size={14} />} onClick={() => navigate(sourceUrl)}>
                          {t('alerts.view_source')}
                        </Button>
                      )}
                      {!alert.is_read && (
                        <Button variant="secondary" size="sm" onClick={() => markRead(alert.id)}>
                          {t('alerts.mark_as_read')}
                        </Button>
                      )}
                      {hasRole('admin', 'pm', 'hr') && (
                        <Button variant="secondary" size="sm" icon={<Check size={14} />} onClick={() => resolve(alert.id)}>
                          {t('alerts.resolve')}
                        </Button>
                      )}
                    </div>
                  </div>
                  {alert.description && (
                    <p className="alr-desc">{alert.description}</p>
                  )}
                  {alert.value !== null && alert.threshold !== null && (
                    <div className="alr-values">
                      <span className="alr-value">
                        {fmtNumber(alert.value, 0)}{unidad(alert.unit)}
                      </span>
                      <span className="u-text3"> / {t('alerts.threshold_label')} {fmtNumber(alert.threshold, 0)}{unidad(alert.unit)}</span>
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
