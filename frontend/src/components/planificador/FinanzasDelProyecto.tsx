/**
 * FinanzasDelProyecto — pestaña «Presupuesto y finanzas» de la ficha (rev. 173).
 * La cuenta de resultados del proyecto (GET /profitability/{id}, el mismo
 * cálculo que la pantalla de rentabilidad) y sus presupuestos (los de ámbito
 * proyecto que apuntan a él), con enlace a cada ficha de presupuesto.
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ExternalLink, PiggyBank, Receipt, TrendingDown, TrendingUp } from 'lucide-react'
import { presupuestosApi, profitabilityApi } from '../../services/api'
import { EmptyState, KpiCard, Spinner, StatusBadge } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr } from '../../utils/helpers'
import './planificador.css'

const ESTADO_KIND: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  aprobado: 'success', enviado: 'warning', rechazado: 'danger', borrador: 'neutral', sustituido: 'neutral',
}

export default function FinanzasDelProyecto({ projectId }: { projectId: string }) {
  const t = useAppT()
  const dinero = useFormatoMoneda()
  const { data: pnl, isLoading, isError, error } = useQuery({
    queryKey: ['profitability', projectId],
    queryFn: () => profitabilityApi.get(projectId).then(r => r.data),
    retry: false,
  })
  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos', 'proyecto', projectId],
    queryFn: () => presupuestosApi.listar({ ambito: 'proyecto' }),
    retry: false,
  })
  const propios = presupuestos.filter(p => p.project_id === projectId)

  if (isLoading) return <Spinner />
  if (isError || !pnl) return <EmptyState title={t('planificador.finanzas_sin_acceso')} description={extractErr(error, '')} />

  return (
    <div className="plan-stack">
      <div className="plan-kpis">
        <KpiCard icon={<TrendingUp size={16} />} label={t('planificador.ingreso')} value={dinero(pnl.billing_revenue)} />
        <KpiCard icon={<TrendingDown size={16} />} label={t('planificador.coste_total')} value={dinero(pnl.total_cost)}
          sub={t('planificador.coste_desglose', { personal: dinero(pnl.internal_cost), gastos: dinero(pnl.expenses_cost), sub: dinero(pnl.subcontract_cost) })} />
        <KpiCard icon={<Receipt size={16} />} label={t('planificador.margen')} value={dinero(pnl.gross_margin)}
          sub={`${pnl.margin_pct} %`} danger={pnl.gross_margin < 0} />
        <KpiCard icon={<PiggyBank size={16} />} label={t('planificador.presupuesto_consumido')} value={`${pnl.budget_used_pct} %`}
          sub={pnl.budget_amount ? dinero(pnl.budget_amount) : t('planificador.sin_presupuesto')} warning={pnl.budget_used_pct > 90} />
        <KpiCard label={t('planificador.coste_previsto')} value={dinero(pnl.forecast_cost)} />
        <KpiCard label={t('planificador.margen_al_cierre')} value={`${pnl.margin_at_completion} %`} danger={pnl.margin_at_completion < 0} />
      </div>
      <div className="plan-card">
        <h3 className="plan-card__titulo">{t('planificador.presupuestos_del_proyecto')}</h3>
        {propios.length === 0 ? (
          <p className="plan-muted">{t('planificador.sin_presupuestos')} <Link to="/budgets">{t('planificador.ir_a_presupuestos')}</Link></p>
        ) : (
          <ul className="plan-lista">
            {propios.map(p => (
              <li key={p.id}>
                <span>{p.name} · {p.year}</span>
                <span className="plan-row">
                  <StatusBadge kind={ESTADO_KIND[p.estado] ?? 'neutral'}>{t(`planificador.presupuesto_${p.estado}`)}</StatusBadge>
                  <span className="plan-num">{dinero(p.total_plan)}</span>
                  <Link to={`/budgets?budget=${p.id}`} aria-label={t('planificador.abrir_presupuesto')}><ExternalLink size={12} /></Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
