/**
 * Gráficos, tabla, tooltip y barra resumen de una métrica.
 * Troceado de ReportsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { CSSProperties, ReactNode } from 'react'
import type { ConsultaDeMetrica, ResumenDeMetrica } from '../../services/api/tipos-analitica'
import { EmptyState, KpiCard, Table, type ColumnaDeTabla, TablaSimple } from '../../components/ui'
import { Grid3X3, Table as TableIcon, BarChartBig } from 'lucide-react'
import { fmtCurrency, localeActivo } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
  AreaChart,
  Area,
  ScatterChart,
  Scatter,
} from 'recharts'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { LEYENDA_SM_SEPARADA } from '../../constants/estilosGrafico'
import { esEjeDeMoneda, type MetricCell, type MetricRow, PALETTE, STATUS_COLORS, type TooltipEntry } from './compartido'

// ── Tooltip customizado ───────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label, isCurrency, isPercent }: { active?: boolean; payload?: TooltipEntry[]; label?: ReactNode; isCurrency?: boolean; isPercent?: boolean }) => {
  if (!active || !payload?.length) return null
  const fmt = (v: number | string | null | undefined) => {
    if (v == null) return '—'
    if (isCurrency) return fmtCurrency(Number(v) || 0)
    if (isPercent) return `${Number(v) || 0}%`
    return typeof v === 'number' ? v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 }) : v
  }
  return (
    <div className="rep-card">
      <div className="rep-text-strong">{label}</div>
      {payload.map((p, i) => (
        <div className="rep-text rep-text-4" key={i} style={{ '--rep-text-4-color': p.color || 'var(--text-1)' } as CSSProperties}>
          {p.name}: <span className="rep-text-strong-mono">{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Heatmap component ─────────────────────────────────────────────────────────
function HeatmapChart({ data, meta }: { data: MetricRow[]; meta?: ConsultaDeMetrica['meta'] }) {
  const traducir = useAppT()
  const weeks = meta?.weeks || []
  if (!data.length || !weeks.length) return <EmptyState svgIcon={<Grid3X3 size={36} />} title={traducir('reports.sin_datos_disponibles')} />
  const maxVal = Math.max(...data.flatMap(r => weeks.map(w => Number(r[w] || 0))))
  const getColor = (v: number) => {
    if (!v) return 'var(--surface-3)'
    const pct = v / maxVal
    if (pct > 0.75) return 'var(--danger)'
    if (pct > 0.5) return 'var(--warning)'
    if (pct > 0.25) return 'var(--accent)'
    return 'var(--success)'
  }
  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="rep-table">
        <thead>
          <tr>
            <th className="rep-th">{traducir('reportes_ui.persona')}</th>
            {weeks.map(w => <th className="rep-th-2" key={w}>{w}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map(row => (
            <tr key={row.label}>
              <td className="rep-td-sm">{row.label}</td>
              {weeks.map(w => {
                const v = Number(row[w] || 0)
                return (
                  <td className="rep-td" key={w} title={`${row.label} · ${w}: ${v}h`}>
                    <div className="rep-row" style={{ '--rep-row-color': v ? 'var(--surface-0)' : 'transparent', '--rep-row-background': getColor(v) } as CSSProperties}>
                      {v > 0 ? v : ''}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </TablaSimple>
      <div className="rep-row-muted">
        {[['var(--success)', traducir('reportes_ui.nivel_bajo')], ['var(--accent)', traducir('reportes_ui.nivel_medio')], ['var(--warning)', traducir('reportes_ui.nivel_alto')], ['var(--danger)', traducir('reportes_ui.nivel_critico')]].map(([c, l]) => (
          <div className="rep-row-2" key={l}>
            <div className="rep-box rep-box-9" style={{ '--rep-box-9-background': c } as CSSProperties} />{l}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tabla de la metrica ───────────────────────────────────────────────────────
// Auditoria 2026-11 (#41): era un `DataTable` propio que tapaba el del kit. Las
// columnas salen de la fila (la metrica decide cuales hay), asi que se monta
// sobre <Table> del kit; los numeros a la derecha y en mono como antes.
export function TablaDeMetrica({ data, isCurrency, isPercent }: { data: MetricRow[]; isCurrency?: boolean; isPercent?: boolean }) {
  const traducir = useAppT()
  const fmtMoneda = useFormatoMoneda()
  if (!data.length) return <EmptyState svgIcon={<TableIcon size={36} />} title={traducir('reports.sin_datos_disponibles')} />
  const keys = Object.keys(data[0]).filter(k => k !== 'status')
  const fmt = (v: MetricCell) => {
    if (typeof v !== 'number') return v
    if (isCurrency) return fmtMoneda(v, { decimales: 0 })
    if (isPercent) return `${v.toFixed(1)}%`
    return v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })
  }
  const columnas: ColumnaDeTabla<MetricRow>[] = keys.map(k => ({
    key: k,
    label: k === 'label' ? '' : <span className="rep-box-2">{k}</span>,
    render: (v: MetricCell, row: MetricRow) => (
      <span className="rep-box-3" style={{ '--rep-box-3-text-align': k === 'label' ? 'left' : 'right', '--rep-box-3-font-family': k !== 'label' ? 'var(--font-mono)' : 'inherit', '--rep-box-3-font-weight': k === 'value' ? '700' : '400', '--rep-box-3-color': k === 'value' && row.status ? STATUS_COLORS[row.status] : 'var(--text-1)' } as CSSProperties}>
        {fmt(v)}
      </span>
    ),
  }))
  return <Table columns={columnas} data={data} />
}

// ── Chart renderer ────────────────────────────────────────────────────────────
export function ChartRenderer({ data, chartType, meta, color = 'var(--accent)', height = 320 }: { data: MetricRow[]; chartType?: string; meta?: ConsultaDeMetrica['meta']; color?: string; height?: number }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  // Revisión 2026-11: un cálculo que falla lo dice; antes salía como «sin datos».
  if (meta?.error) return <EmptyState svgIcon={<BarChartBig size={36} />} title={meta.error} />
  if (!data || data.length === 0) return <EmptyState svgIcon={<BarChartBig size={36} />} title={traducir('reports.sin_datos')} description={traducir('reportes_ui.sin_datos_desc')} />

  const isCurrency = esEjeDeMoneda(meta?.y_label, fmtMoneda)
  const isPercent = meta?.y_label?.includes('%')
  const fmtY = (v: number | string) => {
    const n = Number(v) || 0
    return isCurrency ? fmtMoneda(n, { compacto: true }) : isPercent ? `${n}%` : String(n)
  }

  if (chartType === 'heatmap') return <HeatmapChart data={data} meta={meta} />
  if (chartType === 'table') return <TablaDeMetrica data={data} isCurrency={isCurrency} isPercent={isPercent} />

  if (chartType === 'pie' || chartType === 'donut') {
    return (
      <div className="rep-row-3">
        <PieChart width={300} height={height}>
          <Pie data={data} dataKey="value" nameKey="label" cx="50%" cy="50%"
            innerRadius={chartType === 'donut' ? 70 : 0} outerRadius={120}
            paddingAngle={2}>
            {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
        </PieChart>
        <div className="u-stack-8">
          {data.map((row, i) => {
            const total = data.reduce((s: number, r) => s + (r.value || 0), 0)
            const pct = total > 0 ? ((row.value / total) * 100).toFixed(1) : 0
            return (
              <div className="rep-row-4" key={i}>
                <div className="rep-box-4 rep-box-10" style={{ '--rep-box-10-background': PALETTE[i % PALETTE.length] } as CSSProperties} />
                <span className="rep-box-5">{row.label}</span>
                <span className="rep-text-strong-mono rep-text-5" style={{ '--rep-text-5-color': PALETTE[i % PALETTE.length] } as CSSProperties}>
                  {isCurrency
                    ? fmtCurrency(Number(row.value) || 0)
                    : (Number(row.value) || 0).toLocaleString(localeActivo(), { maximumFractionDigits: 1 })}
                </span>
                <span className="u-text2-xs">{pct}%</span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (chartType === 'bar_grouped') {
    const numericKeys = Object.keys(data[0] || {}).filter(k => k !== 'label' && typeof data[0][k] === 'number')
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Legend wrapperStyle={LEYENDA_SM_SEPARADA} />
          {numericKeys.map((k, i) => <Bar key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} name={k} />)}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'bar_stacked') {
    const numericKeys = Object.keys(data[0] || {}).filter(k => k !== 'label' && typeof data[0][k] === 'number')
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Legend wrapperStyle={LEYENDA_SM_SEPARADA} />
          {numericKeys.map((k, i) => <Bar key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} stackId="a" name={k} />)}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={{ fill: color, r: 4 }} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'area') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#areaGrad)" />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" type="category" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis dataKey="value" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Scatter data={data} fill={color} />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // Default: bar
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
        <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {data.map((row, i) => (
            <Cell key={i} fill={row.status ? STATUS_COLORS[row.status] || color : color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Summary bar ───────────────────────────────────────────────────────────────
export function SummaryBar({ summary, meta, prevSummary }: { summary?: ResumenDeMetrica; meta?: ConsultaDeMetrica['meta']; prevSummary?: ResumenDeMetrica }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  if (!summary || !summary.total) return null
  const isCurrency = esEjeDeMoneda(meta?.y_label, fmtMoneda)
  const isPercent  = meta?.y_label?.includes('%')
  const fmt = (v: number) => isCurrency ? fmtMoneda(v, { decimales: 0 }) : isPercent ? `${v.toFixed(1)}%` : v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })

  const trend = (curr: number, prev: number | undefined) => {
    if (!prev || prev === 0) return undefined
    return Math.round(((curr - prev) / Math.abs(prev)) * 1000) / 10
  }

  const kpis = [
    { label: traducir('reportes_ui.kpi_total'), value: summary.total,  prev: prevSummary?.total },
    { label: traducir('reportes_ui.kpi_maximo'), value: summary.max,    prev: prevSummary?.max   },
    { label: traducir('reportes_ui.kpi_media'), value: summary.avg,    prev: prevSummary?.avg   },
    { label: traducir('reportes_ui.kpi_registros'), value: summary.count,  prev: prevSummary?.count, raw: true },
  ]

  return (
    <div className="ds-grid-stats rep-resumen">
      {kpis.map(({ label, value, prev, raw }) => {
        const t = trend(value, prev)
        return (
          <KpiCard key={label} label={label} value={raw ? value : fmt(value)} trend={t}
            sub={t !== undefined ? traducir('reportes_ui.vs_periodo_anterior') : undefined} />
        )
      })}
    </div>
  )
}
