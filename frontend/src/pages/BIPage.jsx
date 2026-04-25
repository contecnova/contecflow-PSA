import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Spinner } from '../components/ui'
import { PieChart as PieChartIcon } from 'lucide-react'
import { useAppT, useAppLang } from '../i18n/AppLangContext'
import { COLOR } from '../constants/theme'

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function dateRange(days) {
  const d_to = new Date().toISOString().slice(0, 10)
  const d_from = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
  return { date_from: d_from, date_to: d_to }
}

const getLocale = (lang) => (lang === 'en' ? 'en-US' : 'es-ES')

function fmtCur(v, lang = 'es') {
  if (v == null) return '—'
  return new Intl.NumberFormat(getLocale(lang), {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(v)
}

function fmtPct(v) { return v != null ? `${Number(v).toFixed(1)}%` : '—' }

/* ── Design tokens ────────────────────────────────────────────────────────── */
const S = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 14,
    overflow: 'hidden',
  },
  cardPad: { padding: '20px 24px' },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.09em',
    marginBottom: 16,
    margin: 0,
  },
}

/* ── Sub-components (identical visual language to MetricsDashboardTab) ─────── */
function PeriodButton({ active, label, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 18px', borderRadius: 8,
      border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`,
      background: active ? COLOR.accentMuted : 'transparent',
      color: active ? COLOR.accent : 'var(--text-2)',
      fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
      transition: 'all 0.15s',
    }}>{label}</button>
  )
}

function KpiCard({ label, value, sub, color, icon, accentBar }) {
  const bar = accentBar ?? color ?? COLOR.accent
  return (
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: bar, borderRadius: '14px 14px 0 0' }} />
      <div style={{ ...S.cardPad, flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && (
            <span style={{
              fontSize: 18, background: `${bar}18`, borderRadius: 8,
              padding: '5px 7px', lineHeight: 1,
            }}>{icon}</span>
          )}
          <span style={{
            fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
            textTransform: 'uppercase', letterSpacing: '0.09em',
          }}>{label}</span>
        </div>
        <div style={{
          fontSize: 34, fontWeight: 700, color: color || 'var(--text-1)',
          lineHeight: 1.1, letterSpacing: '-0.5px',
        }}>{value ?? '—'}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function RingGauge({ value, color, size = 64 }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={7} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={7}
        strokeDasharray={circ} strokeDashoffset={circ * (1 - progress)} strokeLinecap="round" />
    </svg>
  )
}

function GaugeCard({ label, value, color, suffix = '%', sub }) {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} size={68} />
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700, color,
        }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div style={{
          fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 4,
        }}>{label}</div>
        <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1, letterSpacing: '-0.5px' }}>
          {value != null ? `${value}${suffix}` : '—'}
        </div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  )
}

function BarRow({ label, count, total, color, fmt }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  const displayVal = fmt ? fmt(count) : count
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-2)', textTransform: 'capitalize' }}>
          {label.replace(/_/g, ' ')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, color: 'var(--text-1)',
            background: 'var(--surface-4)', borderRadius: 6, padding: '2px 7px',
          }}>{displayVal}</span>
          <span style={{ fontSize: 11, color: 'var(--text-3)', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
        </div>
      </div>
      <div style={{ height: 7, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color, borderRadius: 4,
          transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  )
}

function ProjectAvatar({ name, code }) {
  const initials = (code || name || '?').slice(0, 2).toUpperCase()
  const colors = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']
  const idx = (name || '').charCodeAt(0) % colors.length
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 8,
      background: `${colors[idx]}22`, border: `1.5px solid ${colors[idx]}44`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 700, color: colors[idx], flexShrink: 0,
    }}>{initials}</div>
  )
}

function MarginBar({ margin, revenue }) {
  const pct = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const color = pct >= 30 ? COLOR.success : pct >= 15 ? COLOR.warning : COLOR.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
        <div style={{ width: `${Math.max(0, Math.min(pct, 100))}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 36 }}>{pct}%</span>
    </div>
  )
}

function EmptyDash() {
  return (
    <div style={{ textAlign: 'center', padding: '80px 24px', color: 'var(--text-3)' }}>
      <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>📊</div>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>Sin datos ejecutivos</div>
      <div style={{ fontSize: 13, maxWidth: 280, margin: '0 auto', lineHeight: 1.6 }}>
        Crea proyectos y registra actividad para ver el dashboard ejecutivo aquí
      </div>
    </div>
  )
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function BIPage() {
  const t = useAppT()
  const { lang } = useAppLang()
  const [days, setDays] = useState(30)

  const params = dateRange(days)

  const { data: kpis, isLoading: loadingKpis } = useQuery({
    queryKey: ['bi-exec-kpis', days],
    queryFn: () => api.get('/dashboard/kpis', { params }).then(r => r.data).catch(() => ({})),
    staleTime: 60_000,
  })

  const { data: health = [], isLoading: loadingHealth } = useQuery({
    queryKey: ['bi-exec-health', days],
    queryFn: () => api.get('/dashboard/projects-health', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: profitSummary } = useQuery({
    queryKey: ['bi-exec-profit', days],
    queryFn: () => api.get('/profitability/summary', { params: { ...params, period: 'custom' } }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const { data: topProjects = [] } = useQuery({
    queryKey: ['bi-exec-top-projects', days],
    queryFn: () => api.get('/profitability/projects', { params }).then(r => r.data).catch(() => []),
    staleTime: 60_000,
  })

  const { data: byType = [] } = useQuery({
    queryKey: ['bi-exec-by-type', days],
    queryFn: () => api.get('/analytics/query/projects_by_type', { params }).then(r => r.data?.rows || []).catch(() => []),
    staleTime: 60_000,
  })

  const { data: utilData } = useQuery({
    queryKey: ['bi-exec-utilization', days],
    queryFn: () => api.get('/analytics/utilization/advanced', { params }).then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })

  const isLoading = loadingKpis || loadingHealth

  if (isLoading) {
    return (
      <div style={{ padding: 32 }}>
        <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle={t('bi.subtitle')} />
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
          <Spinner />
        </div>
      </div>
    )
  }

  /* ── Derived stats ── */
  const totalProjects = health.length
  const critProj = health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100).length
  const warnProj = health.filter(p => p.budget_used_pct > 80 || p.alerts_count > 0).length
  const okProj   = totalProjects - critProj - warnProj
  const onTimePct = totalProjects > 0 ? Math.round((okProj / totalProjects) * 100) : 0

  const revenue    = profitSummary?.total_revenue ?? 0
  const costs      = profitSummary?.total_cost ?? 0
  const margin     = revenue - costs
  const marginPct  = revenue > 0 ? Math.round((margin / revenue) * 100) : 0
  const marginColor = marginPct >= 30 ? COLOR.success : marginPct >= 15 ? COLOR.warning : COLOR.danger

  const onTimeColor = onTimePct >= 80 ? COLOR.success : onTimePct >= 60 ? COLOR.warning : COLOR.danger

  const totalByType = byType.reduce((s, r) => s + (r.value || 0), 0)
  const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', '#fb923c']

  const healthRows = [
    { label: 'En tiempo y presupuesto', count: okProj,   color: COLOR.success },
    { label: 'En riesgo',              count: warnProj,  color: COLOR.warning },
    { label: 'Crítico',                count: critProj,  color: COLOR.danger  },
  ]

  const utilPct = utilData?.avg_utilization_pct ?? null

  if (!totalProjects && !revenue) return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<PieChartIcon size={18} />} title={t('bi.title')} subtitle={t('bi.subtitle')} />
      <EmptyDash />
    </div>
  )

  return (
    <div style={{ padding: 32, maxWidth: 1400, margin: '0 auto' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,0.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--accent)', flexShrink: 0,
            }}>
              <PieChartIcon size={18} />
            </div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0 }}>
              {t('bi.title')}
            </h1>
          </div>
          <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-2)', paddingLeft: 46 }}>
            {t('bi.subtitle')} · últimos {days} días
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[7, 30, 90, 365].map(d => (
            <PeriodButton key={d} active={days === d} label={d === 365 ? '1a' : `${d}d`} onClick={() => setDays(d)} />
          ))}
        </div>
      </div>

      {/* ── KPI row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 14, marginBottom: 14,
      }}>
        <KpiCard
          icon="⬡" label={t('bi.active_projects')}
          value={totalProjects}
          color="var(--text-1)" accentBar={COLOR.accent}
        />
        <KpiCard
          icon="🚨" label={t('bi.critical_projects')}
          value={critProj}
          color={critProj > 0 ? COLOR.danger : COLOR.success}
          accentBar={critProj > 0 ? COLOR.danger : COLOR.success}
          sub={critProj > 0 ? 'Fuera de plazo o presupuesto' : 'Sin proyectos críticos'}
        />
        <KpiCard
          icon="▦" label={t('bi.overdue_tasks')}
          value={kpis?.tasks_overdue ?? 0}
          color={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
          accentBar={(kpis?.tasks_overdue ?? 0) > 0 ? COLOR.warning : COLOR.success}
          sub={t('bi.need_attention')}
        />
        <KpiCard
          icon="💰" label={t('bi.budget_used')}
          value={kpis?.total_budget > 0 ? `${Math.round((kpis.total_spent / kpis.total_budget) * 100)}%` : '—'}
          color={COLOR.warning} accentBar={COLOR.warning}
          sub={`${fmtCur(kpis?.total_spent ?? 0, lang)} gastado`}
        />
        <KpiCard
          icon="⏱" label={t('bi.hours_this_week')}
          value={kpis?.hours_logged_this_week?.toFixed(0) ?? '0'}
          color="var(--sky-blue)" accentBar="var(--sky-blue)"
          sub="horas imputadas esta semana"
        />
        <KpiCard
          icon="🎫" label={t('bi.open_tickets')}
          value={kpis?.tasks_open ?? 0}
          color={COLOR.purple} accentBar={COLOR.purple}
          sub={t('bi.service_desk_short')}
        />
      </div>

      {/* ── Gauge row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 14, marginBottom: 20,
      }}>
        <GaugeCard
          label="Proyectos a tiempo"
          value={onTimePct}
          color={onTimeColor}
          sub={onTimePct >= 80 ? 'Excelente estado' : onTimePct >= 60 ? 'Aceptable' : 'Requiere atención'}
        />
        <GaugeCard
          label="Margen bruto"
          value={marginPct}
          color={marginColor}
          sub={`${fmtCur(margin, lang)} de ${fmtCur(revenue, lang)}`}
        />
        {utilPct != null && (
          <GaugeCard
            label="Utilización equipo"
            value={Math.round(utilPct)}
            color={utilPct >= 70 ? COLOR.success : utilPct >= 50 ? COLOR.warning : COLOR.danger}
            sub={utilPct >= 70 ? 'Buen aprovechamiento' : 'Capacidad disponible'}
          />
        )}
      </div>

      {/* ── Charts row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 14, marginBottom: 20,
      }}>
        {/* Distribución por tipo */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Proyectos por tipo</div>
          </div>
          <div style={S.cardPad}>
            {byType.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin datos</div>
            ) : byType.map((row, i) => (
              <BarRow
                key={row.label}
                label={row.label || 'Sin tipo'}
                count={row.value || 0}
                total={totalByType}
                color={typePalette[i % typePalette.length]}
              />
            ))}
          </div>
        </div>

        {/* Salud de proyectos */}
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}>
            <div style={S.sectionTitle}>Estado de salud</div>
          </div>
          <div style={S.cardPad}>
            {totalProjects === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 12, padding: '16px 0' }}>Sin datos</div>
            ) : healthRows.map(row => (
              <BarRow
                key={row.label}
                label={row.label}
                count={row.count}
                total={totalProjects}
                color={row.color}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Revenue section ── */}
      {revenue > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 14, marginBottom: 20,
        }}>
          <KpiCard
            icon="📈" label="Ingresos totales"
            value={fmtCur(revenue, lang)}
            color={COLOR.accent} accentBar={COLOR.accent}
          />
          <KpiCard
            icon="💸" label="Costes totales"
            value={fmtCur(costs, lang)}
            color={COLOR.warning} accentBar={COLOR.warning}
          />
          <KpiCard
            icon="✅" label="Margen bruto"
            value={fmtCur(margin, lang)}
            color={margin >= 0 ? COLOR.success : COLOR.danger}
            accentBar={margin >= 0 ? COLOR.success : COLOR.danger}
            sub={`${marginPct}% de margen`}
          />
        </div>
      )}

      {/* ── Top projects table ── */}
      {topProjects.length > 0 && (
        <div style={S.card}>
          <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={S.sectionTitle}>Rentabilidad por proyecto</div>
            <span style={{
              fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
              background: 'var(--surface-4)', borderRadius: 12,
              padding: '2px 8px', marginLeft: 4, marginTop: -14,
            }}>{topProjects.length}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {['Proyecto', 'Cliente', 'Ingresos', 'Costes', 'Margen', 'Estado'].map((col, i) => (
                    <th key={col} style={{
                      padding: '10px 16px',
                      textAlign: i === 0 ? 'left' : 'center',
                      fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
                      textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap',
                    }}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {topProjects.slice(0, 10).map((p, idx) => {
                  const rev  = p.revenue_actual ?? p.budget_amount ?? 0
                  const cost = p.cost_actual ?? 0
                  const mgn  = rev - cost
                  const statusColor = p.status === 'active' ? COLOR.accent : p.status === 'completed' ? COLOR.success : 'var(--text-3)'
                  return (
                    <tr key={p.project_id || p.id} style={{
                      borderBottom: '1px solid var(--surface-4)',
                      background: idx % 2 === 0 ? 'transparent' : 'var(--surface-3)08',
                    }}>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <ProjectAvatar name={p.project_name || p.name} code={p.project_code || p.code} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>
                              {p.project_name || p.name}
                            </div>
                            {(p.project_code || p.code) && (
                              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.project_code || p.code}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{p.client_name || '—'}</span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{fmtCur(rev, lang)}</span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', background: 'var(--surface-4)', padding: '3px 8px', borderRadius: 6, whiteSpace: 'nowrap' }}>
                          {fmtCur(cost, lang)}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', minWidth: 160 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <MarginBar margin={mgn} revenue={rev} />
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 11, fontWeight: 700, color: statusColor,
                          background: `${statusColor}18`,
                          border: `1px solid ${statusColor}30`,
                          borderRadius: 6, padding: '3px 9px',
                          textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>{p.status || '—'}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  )
}
