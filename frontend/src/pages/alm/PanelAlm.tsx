/**
 * Panel resumen (dashboard) del módulo ALM.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useQuery } from '@tanstack/react-query'
import { almExtApi } from '../../services/api'
import type { AlmKpis } from '../../services/api/tipos-alm'
import { Button, Spinner, EmptyState, Pulsable } from '../../components/ui'
import {
  Building2,
  FileText,
  Key,
  Monitor,
  Briefcase,
  CheckCircle2,
  Coins,
  BarChart3,
  CalendarClock,
  Lightbulb,
  ShieldAlert,
  UserPlus,
  HandCoins,
  FileSignature,
  Receipt,
  ChevronRight,
} from 'lucide-react'
import { fmtCurrency, fmtDate } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { useUmbrales } from '../../hooks/useOrgSettings'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import { KPI, SectionTitle, tonoPorDias } from './compartidoAlm'

// ── Dashboard ALM ─────────────────────────────────────────────────────────────
export function ALMDashboard({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const t = useAppT()
  const umbrales = useUmbrales()
  const { data: dash, isLoading } = useQuery({
    queryKey: ['alm-dashboard'],
    queryFn: () => almExtApi.dashboard().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const kpis: Partial<AlmKpis> = dash?.kpis || {}
  const renewals = dash?.upcoming_renewals || []

  if (isLoading) return <div className="alm-loading"><Spinner size={32} /></div>

  return (
    <div>
      {/* KPIs */}
      <div className="ds-grid-stats alm-kpis">
        <KPI icon={<FileText size={16} />} label={t('alm.dashboard_contracts_active')} value={kpis.total_contracts ?? 0}
          sub={kpis.expiring_soon ? `${kpis.expiring_soon} ${t('alm.dashboard_expire_60')}` : undefined}
          alert={kpis.expiring_soon > 0} />
        <KPI icon={<Key size={16} />} label={t('alm.dashboard_licenses_managed')} value={kpis.total_licenses ?? 0}
          sub={kpis.expired_licenses ? `${kpis.expired_licenses} ${t('alm.dashboard_expired')}` : undefined}
          alert={kpis.expired_licenses > 0} danger />
        <KPI icon={<Monitor size={16} />} label={t('alm.dashboard_assets_inventory')} value={kpis.total_assets ?? 0}
          sub={`${kpis.assets_in_use ?? 0} ${t('alm.dashboard_in_use')}`} />
        <KPI icon={<Building2 size={16} />} label={t('alm.dashboard_vendors_active')} value={kpis.total_vendors ?? 0} />
        <KPI icon={<Coins size={16} />} label={t('alm.dashboard_license_annual_cost')} value={fmtCurrency(kpis.annual_license_cost ?? 0)} sub={t('alm.dashboard_license_cost_scope')} />
        <KPI icon={<BarChart3 size={16} />} label={t('alm.dashboard_total_annual_cost')} value={fmtCurrency(kpis.total_annual_cost ?? 0)} sub={t('alm.dashboard_total_cost_scope')} />
        <KPI icon={<UserPlus size={16} />} label={t('alm.dashboard_pending_approvals')} value={kpis.pending_approvals ?? 0}
          alert={(kpis.pending_approvals ?? 0) > 0} onClick={() => onNavigate('assignments')} />
        <KPI icon={<HandCoins size={16} />} label={t('alm.dashboard_loans_overdue')} value={kpis.loans_overdue ?? 0}
          alert={(kpis.loans_overdue ?? 0) > 0} danger onClick={() => onNavigate('loans')} />
        <KPI icon={<FileSignature size={16} />} label={t('alm.dashboard_acts_pending')} value={kpis.acts_pending_signature ?? 0}
          onClick={() => onNavigate('acts')} />
      </div>

      {/* Renovaciones próximas */}
      <div className="alm-dash-grid">
        <div className="alm-card">
          <div className="alm-dash-panel">
            <SectionTitle action={<Button onClick={() => onNavigate('renewals')} variant="secondary">{t('alm.dashboard_view_renewals')}</Button>}>
              <span className="u-row-center-8"><CalendarClock size={16} aria-hidden="true" />{t('alm.dashboard_upcoming_renewals')}</span>
            </SectionTitle>
            {renewals.length === 0 ? (
              <EmptyState icon={<CheckCircle2 size={28} />} title={t('alm.dashboard_no_urgent_renewals')} description={t('alm.dashboard_no_urgent_renewals_desc')} />
            ) : (
              renewals.map(c => (
                <div key={c.id} className="alm-renewal">
                  <div>
                    <div className="u-base-600">{c.title}</div>
                    <div className="u-text2-xs">{c.vendor_name}</div>
                  </div>
                  <div className="alm-renewal__when">
                    <div className={`alm-renewal__days ${tonoPorDias(c.days_to_renewal, umbrales, 'success')}`}>
                        {c.days_to_renewal === 0 ? t('alm.dashboard_today') : `${c.days_to_renewal}${t('alm.dashboard_days_short')}`}
                    </div>
                    <div className="u-text2-xs">{fmtDate(c.renewal_date)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="alm-card">
          <div className="alm-dash-panel">
            <SectionTitle><span className="u-row-center-8"><Lightbulb size={16} aria-hidden="true" />{t('alm.dashboard_quick_actions')}</span></SectionTitle>
            {[
              { icon: <Building2 size={16} />, label: t('alm.action_add_vendor'), tab: 'vendors' },
              { icon: <FileText size={16} />, label: t('alm.action_new_contract'), tab: 'contracts' },
              { icon: <Key size={16} />, label: t('alm.action_register_license'), tab: 'licenses' },
              { icon: <Monitor size={16} />, label: t('alm.action_add_asset'), tab: 'assets' },
              { icon: <CalendarClock size={16} />, label: t('alm.action_renewals'), tab: 'renewals' },
              { icon: <Coins size={16} />, label: t('alm.action_costs'), tab: 'costs' },
              { icon: <Receipt size={16} />, label: t('alm.action_reconciliation'), tab: 'reconciliation' },
              { icon: <Briefcase size={16} />, label: t('alm.action_cost_centers'), tab: 'cost' },
              { icon: <ShieldAlert size={16} />, label: t('alm.action_compliance_report'), tab: 'compliance' },
            ].map(a => (
              <Pulsable key={a.tab} type="button" onClick={() => onNavigate(a.tab)} className="alm-quick">
                <span className="alm-quick__icon" aria-hidden="true">{a.icon}</span>
                <span className="alm-quick__label">{a.label}</span>
                <ChevronRight size={14} aria-hidden="true" className="alm-quick__chevron" />
              </Pulsable>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
