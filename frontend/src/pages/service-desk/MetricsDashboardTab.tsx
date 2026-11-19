/**
 * MetricsDashboardTab — métricas ITIL del service desk (se muestra en
 * /support-dashboard, bajo la cabecera de SupportDashboardPage).
 *
 * 16-11-2026 (pasada de diseño):
 * - Sin cabecera propia (h2 "Métricas ITIL" duplicaba la de la página) ni
 *   PageShell anidado: el contenido va directamente bajo la cabecera.
 * - Periodo con las pestañas del kit (antes botones propios).
 * - KPIs con el KpiCard del kit en .ds-grid-stats e iconos lucide (antes emojis
 *   y barra superior de color).
 * - SLA y FCR sin tickets: "—" y "Sin tickets en este periodo" (antes 100 %
 *   "Excelente" con 0 tickets por el `?? 100`).
 * - Bloques con Card + Section, vacíos con EmptyState, avatares con Avatar,
 *   incumplimientos con StatusBadge (antes ⚠/✓), y todos los textos por t()
 *   (prioridades, tipos, cabeceras de tabla y subtítulos estaban fijos).
 */
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, CheckCircle2, FolderOpen, Star, Ticket, Timer, Users } from 'lucide-react'
import { sdMetricsApi } from '../../services/api'
import type { SdRendimientoDeAgente } from '../../services/api/tipos-sd'
import { Avatar, Card, EmptyState, KpiCard, Section, SelectorDePeriodo, Spinner, StatusBadge, TablaSimple, useSort, SortableTH, ariaSort } from '../../components/ui'
import { BarRow, GaugeCard, typePalette } from '../../components/dashboard/DashKit'
import { usePeriodo } from '../../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../../utils/periodo'
import { COLOR } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import { useTono } from '../../hooks/useOrgSettings'
import { TIPOS_DE_TICKET } from '../../constants/catalogos'
import './MetricsDashboardTab.css'

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function fmtMinutes(m: number | null | undefined) {
  if (m == null || m === 0) return '—'
  if (m < 60) return `${Math.round(m)}m`
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

const PRIORIDADES: Record<string, string> = {
  p1_critical: COLOR.danger,
  p2_high: 'var(--orange)',
  p3_medium: COLOR.warning,
  p4_low: COLOR.text3,
}
const TIPOS = TIPOS_DE_TICKET  // 19-11-2026: una sola fuente (constants/catalogos)

/* ── Sub-components ───────────────────────────────────────────────────────── */
function ResolutionBar({ resolved, total }: { resolved: number; total: number }) {
  const pct = total > 0 ? Math.round((resolved / total) * 100) : 0
  const color = pct >= 80 ? COLOR.success : pct >= 60 ? COLOR.warning : COLOR.danger
  return (
    <div className="medata-row-2">
      <div className="medata-box-7">
        <div className="medata-box-19 metrics-dashboard-tab-e2" style={{ '--metrics-dashboard-tab-width': `${pct}%`, '--metrics-dashboard-tab-background': color } as CSSProperties} />
      </div>
      <span className="medata-box-20 metrics-dashboard-tab-e4" style={{ '--metrics-dashboard-tab-color': color } as CSSProperties}>{pct}%</span>
    </div>
  )
}

function StarRating({ value }: { value: number | null }) {
  if (value == null) return <span className="u-text3-sm">—</span>
  const filled = Math.round(value)
  const color = value >= 4 ? COLOR.success : value >= 3 ? COLOR.warning : COLOR.danger
  return (
    <div className="medata-row-3">
      <div className="medata-row-4" aria-hidden>
        {Array.from({ length: 5 }, (_, i) => (
          <svg key={i} width="10" height="10" viewBox="0 0 10 10">
            <polygon
              points="5,1 6.2,3.5 9,3.8 7,5.7 7.6,8.5 5,7 2.4,8.5 3,5.7 1,3.8 3.8,3.5"
              fill={i < filled ? color : 'var(--surface-4)'}
            />
          </svg>
        ))}
      </div>
      <span className="medata-txt-5 metrics-dashboard-tab-e4" style={{ '--metrics-dashboard-tab-color': color } as CSSProperties}>{value.toFixed(1)}</span>
    </div>
  )
}

/* ── Main component ───────────────────────────────────────────────────────── */
type AgentPerf = SdRendimientoDeAgente

export default function MetricsDashboardTab() {
  const { t } = useAppLang()
  const tono = useTono()
  // Periodo libre (16-11-2026): antes 7/30/90 propio con date_from/date_to.
  // Los tickets tienen instante: admite agrupación por hora.
  const periodoSel = usePeriodo({ defecto: '30d', granularidades: CON_HORA })

  const { data: metrics, isLoading, error } = useQuery({
    queryKey: ['sd-itil-metrics', periodoSel.params],
    queryFn: () => sdMetricsApi.itil({ ...periodoSel.params }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: agents } = useQuery({
    queryKey: ['sd-agent-perf', periodoSel.params],
    queryFn: () => sdMetricsApi.agentPerformance({ ...periodoSel.params }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)

  const { sort: agentSort, setSort: setAgentSort, sortedData: sortedAgents } = useSort<AgentPerf>(agents || [], 'total', 'desc')

  const periodo = (
    <div className="medata-periodo">
      <SelectorDePeriodo {...periodoSel.selector} />
    </div>
  )

  if (isLoading) {
    return (
      <div className="medata-cuerpo">
        {periodo}
        <div className="medata-row-5"><Spinner /></div>
      </div>
    )
  }

  if (errorDePeriodo) {
    return (
      <div className="medata-cuerpo">
        {periodo}
        <Card>
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </Card>
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="medata-cuerpo">
        {periodo}
        <Card>
          <EmptyState icon={<BarChart3 size={28} />} title={t('metricsdashboard.sin_datos_de_metricas')} description={t('metricsdashboard.crea_y_gestiona_tickets_para_ver_las')} />
        </Card>
      </div>
    )
  }

  const total = metrics.volume?.total ?? 0
  const sinTickets = total === 0
  // Sin tickets no hay cumplimiento que medir: "—", no un 100 % "Excelente".
  const slaPct = sinTickets ? null : (metrics.sla_compliance_pct ?? null)
  const fcrPct = sinTickets ? null : (metrics.fcr_percent ?? null)

  // 19-11-2026: los cortes de SLA de la empresa (antes 95/80 aquí).
  const slaTono = tono('sla', slaPct)
  const slaColor = slaTono == null ? COLOR.text3 : COLOR[slaTono]
  const slaSub = slaTono == null ? t('metricsdashboard.sin_tickets_periodo')
    : slaTono === 'success' ? t('metricsdashboard.sla_excelente') : slaTono === 'warning' ? t('metricsdashboard.sla_aceptable') : t('metricsdashboard.sla_bajo_objetivo')

  const fcrColor = fcrPct == null ? COLOR.text3
    : fcrPct >= 70 ? COLOR.success : fcrPct >= 50 ? COLOR.warning : COLOR.danger

  const open = metrics.volume?.open ?? 0
  const breached = metrics.volume?.breached_sla ?? 0
  const csat = metrics.avg_csat != null ? Number(metrics.avg_csat) : null

  const typeEntries = Object.entries<number>(metrics.by_type || {}).sort((a, b) => b[1] - a[1])
  const priorityEntries = Object.entries<number>(metrics.by_priority || {})
  const totalTickets = total || 1

  const nombreDeTipo = (tipo: string) => TIPOS.includes(tipo) ? t(`metricsdashboard.tipo_${tipo}`) : tipo.replace(/_/g, ' ')
  const nombreDePrioridad = (p: string) => PRIORIDADES[p] ? t(`metricsdashboard.prio_${p}`) : p.replace(/_/g, ' ')

  const columnas = [
    { col: 'agent_name', label: t('metricsdashboard.col_agente') },
    { col: 'total', label: t('metricsdashboard.col_total') },
    { col: 'resolved', label: t('metricsdashboard.col_tasa_resolucion') },
    { col: 'mttr_minutes', label: t('metricsdashboard.col_mttr') },
    { col: 'avg_csat', label: t('metricsdashboard.col_csat') },
    { col: 'sla_breaches', label: t('metricsdashboard.col_incumplimientos') },
  ]

  return (
    <div className="medata-cuerpo">
      {periodo}

      {/* ── KPIs ── */}
      <div className="ds-grid-stats">
        <KpiCard icon={<Ticket size={16} />} label={t('metricsdashboard.tickets_totales')} value={total} />
        <KpiCard icon={<FolderOpen size={16} />} label={t('metricsdashboard.abiertos')} value={open} warning={open > 20} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('metricsdashboard.resueltos')} value={metrics.volume?.resolved ?? 0} />
        <KpiCard icon={<Timer size={16} />} label={t('metricsdashboard.mttr')} value={fmtMinutes(metrics.mttr_minutes)}
          sub={t('metricsdashboard.tiempo_medio_resolucion')} />
        <KpiCard icon={<Star size={16} />} label={t('metricsdashboard.csat_medio')} value={csat ? `${csat.toFixed(1)}/5` : '—'}
          danger={csat != null && csat < 3} warning={csat != null && csat >= 3 && csat < 4} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('metricsdashboard.brechas_sla')} value={breached} danger={breached > 0} />
      </div>

      {/* ── SLA + FCR ── */}
      <div className="medata-grid-2">
        <GaugeCard label={t('metricsdashboard.cumplimiento_sla')} value={slaPct} color={slaColor} sub={slaSub} />
        <GaugeCard label={t('metricsdashboard.fcr_1er_contacto')} value={fcrPct} color={fcrColor}
          sub={fcrPct == null ? t('metricsdashboard.sin_tickets_periodo') : t('metricsdashboard.fcr_desc')} />
      </div>

      {/* ── Distribución ── */}
      <div className="medata-grid-3">
        <Card>
          <Section title={t('metricsdashboard.volumen_por_tipo')}>
            {typeEntries.length === 0 ? (
              <EmptyState icon={<BarChart3 size={28} />} title={t('metricsdashboard.sin_datos')} description={t('metricsdashboard.sin_tickets_periodo')} />
            ) : typeEntries.map(([type, count], i) => (
              <BarRow key={type} label={nombreDeTipo(type)} count={count} total={totalTickets} color={typePalette[i % typePalette.length]} />
            ))}
          </Section>
        </Card>

        <Card>
          <Section title={t('metricsdashboard.distribucion_por_prioridad')}>
            {priorityEntries.length === 0 ? (
              <EmptyState icon={<BarChart3 size={28} />} title={t('metricsdashboard.sin_datos')} description={t('metricsdashboard.sin_tickets_periodo')} />
            ) : priorityEntries.map(([prio, count]) => (
              <BarRow key={prio} label={nombreDePrioridad(prio)} count={count} total={totalTickets} color={PRIORIDADES[prio] ?? COLOR.text3} />
            ))}
          </Section>
        </Card>
      </div>

      {/* ── Rendimiento de agentes ── */}
      <Card>
        <Section
          title={t('metricsdashboard.rendimiento_de_agentes')}
          actions={sortedAgents.length > 0 ? <StatusBadge caps={false}>{sortedAgents.length}</StatusBadge> : undefined}
        >
          {sortedAgents.length === 0 ? (
            <EmptyState icon={<Users size={28} />} title={t('metricsdashboard.sin_datos_de_agentes_en_este_periodo')} description={t('metricsdashboard.sin_agentes_desc')} />
          ) : (
            <div className="u-scroll-x">
              <TablaSimple claseTabla="u-table">
                <thead>
                  <tr className="medata-box-13">
                    {columnas.map(({ col, label }) => (
                      <th className={`medata-box-21 ${col === 'agent_name' ? 'metrics-dashboard-tab-m6' : 'metrics-dashboard-tab-m7'}`} aria-sort={ariaSort(agentSort, col)} key={col}>
                        <SortableTH col={col} sort={agentSort} onSort={setAgentSort}>{label}</SortableTH>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map(a => (
                    <tr className="medata-box-22" key={a.agent_id}>
                      <td className="medata-sp-1">
                        <div className="u-row-center-10">
                          <Avatar name={a.agent_name} size={32} />
                          <span className="medata-txt-2">{a.agent_name}</span>
                        </div>
                      </td>
                      <td className="medata-box-14"><span className="medata-txt-3">{a.total}</span></td>
                      <td className="medata-box-15">
                        <div className="medata-row-7"><ResolutionBar resolved={a.resolved} total={a.total} /></div>
                      </td>
                      <td className="medata-box-14"><span className="medata-box-16">{fmtMinutes(a.mttr_minutes)}</span></td>
                      <td className="medata-sp-1">
                        <div className="medata-row-8"><StarRating value={a.avg_csat ? Number(a.avg_csat) : null} /></div>
                      </td>
                      <td className="medata-box-14">
                        <StatusBadge kind={a.sla_breaches > 0 ? 'danger' : 'success'} caps={false}>{a.sla_breaches}</StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
            </div>
          )}
        </Section>
      </Card>
    </div>
  )
}
