/**
 * Panel de construcción/consulta de un informe de métrica.
 * Troceado de ReportsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useMemo, useId, type CSSProperties } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Button, Spinner, EmptyState, SelectorDePeriodo, Select, Pulsable, Input } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { Download, Image, BarChart3, AlertTriangle, Save } from 'lucide-react'
import { COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import { useAppT } from '../../i18n/AppLangContext'
import { descripcionMetrica, etiquetaMetrica } from '../../i18n/catalogoMetricas'
import useMediaQuery from '../../hooks/useMediaQuery'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo, isoConDesfase } from '../../utils/periodo'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import {
  type Catalogue,
  CHART_TYPES,
  esEjeDeMoneda,
  etiquetaCategoria,
  type FilterOptions,
  IconoCategoria,
  type MetricResult,
  PALETTE,
  type ReportConfig,
} from './compartido'
import { ChartRenderer, SummaryBar, TablaDeMetrica } from './graficos'

// ── Report panel ──────────────────────────────────────────────────────────────
export function ReportPanel({ initialMetric, initialChart, onSave }: { initialMetric?: string; initialChart?: string; onSave?: (config: ReportConfig) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const narrow = useMediaQuery('(max-width: 900px)')

  const toast = useToast()
  const [metric, setMetric] = useState(initialMetric || '')
  const [chartType, setChartType] = useState(initialChart || 'bar')
  // Periodo libre (16-11-2026): antes «desde/hasta» propios con accesos de
  // 7/30 días, 3/6 meses y 1 año. Las métricas agrupan por su cuenta (día,
  // semana o mes de calendario): sin hora y sin elegir agrupación.
  const periodo = usePeriodo({ defecto: '90d', granularidades: SIN_HORA })
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [department, setDepartment] = useState('')
  const [topN, setTopN] = useState(20)
  const [color, setColor] = useState<string>(PALETTE[0])
  const [reportName, setReportName] = useState('')

  const { data: catalogue } = useQuery<Catalogue>({ queryKey: ['analytics-catalogue'], queryFn: () => analyticsApi.catalogue().then(r => r.data) })
  const { data: filters } = useQuery<FilterOptions>({ queryKey: ['analytics-filters'], queryFn: () => analyticsApi.filterOptions().then(r => r.data) })

  const filtros = { project_id: projectId || undefined, user_id: userId || undefined, department: department || undefined, top_n: topN }
  const { data: result, isLoading, isFetching, error: errorConsulta } = useQuery<MetricResult | null>({
    queryKey: ['analytics-query', metric, periodo.params, projectId, userId, department, topN],
    // Un periodo no válido (422 `periodo.*`) se explica en la página; el resto avisa por el toast global (23-11-2026).
    queryFn: () => analyticsApi.query(metric, { ...periodo.params, ...filtros }).then(r => r.data),
    enabled: !!metric,
    retry: false,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(errorConsulta)

  // Período anterior (misma duración, justo antes) para la comparativa de SummaryBar.
  const paramsAnteriores = useMemo(() => {
    const { desde, hasta } = periodo.rango
    const duracion = hasta.getTime() - desde.getTime()
    return { desde: isoConDesfase(new Date(desde.getTime() - duracion)), hasta: isoConDesfase(desde), tz: periodo.params.tz }
  }, [periodo.rango, periodo.params.tz])

  const { data: prevResult } = useQuery<MetricResult | null>({
    queryKey: ['analytics-prev', metric, paramsAnteriores, projectId, userId, department, topN],
    queryFn: () => analyticsApi.query(metric, { ...paramsAnteriores, ...filtros }).then(r => r.data),
    enabled: !!metric && !errorDePeriodo,
    staleTime: STALE_DEFAULT_MS,
    retry: false,
  })

  // Auto-set chart type from metric default
  const handleMetricChange = (m: string) => {
    setMetric(m)
    if (catalogue) {
      for (const cat of Object.values(catalogue)) {
        const found = cat.find(item => item.id === m)
        if (found) { setChartType(found.default_chart || 'bar'); break }
      }
    }
  }



  return (
    <div>
      {/* Controls bar */}
      <div className="rep-card-3">
        <div className="rep-grid" style={{ '--rep-grid-grid-template-columns': narrow ? 'repeat(2, minmax(0, 1fr))' : '2fr 1.5fr 1.5fr 1fr 1fr 1fr' } as CSSProperties}>
          {/* Metric selector */}
          <div className={narrow ? 'rep-campo-ancho' : undefined}>
            <label className="rep-ls" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('reports.metrica')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={metric} onChange={e => handleMetricChange(e.target.value)}>
              <option value="">{traducir('reports.seleccionar_metrica')}</option>
              {catalogue && Object.entries(catalogue).map(([cat, items]) => (
                <optgroup key={cat} label={etiquetaCategoria(cat, traducir)}>
                  {items.map(item => <option key={item.id} value={item.id}>{etiquetaMetrica(traducir, item.id, item.label)}</option>)}
                </optgroup>
              ))}
            </Select>
          </div>

          {/* Project filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('reportes_ui.proyecto')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={projectId} onChange={e => setProjectId(e.target.value)}>
              <option value="">{traducir('reports.todos_los_proyectos')}</option>
              {filters?.projects?.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </Select>
          </div>

          {/* User filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('reportes_ui.persona_icono')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={userId} onChange={e => setUserId(e.target.value)}>
              <option value="">{traducir('reports.todas_las_personas')}</option>
              {filters?.users?.map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
            </Select>
          </div>

          {/* Dept filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{traducir('reportes_ui.departamento')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={department} onChange={e => setDepartment(e.target.value)}>
              <option value="">{traducir('reports.todos')}</option>
              {filters?.departments?.map(d => <option key={d} value={d}>{d}</option>)}
            </Select>
          </div>

          {/* Top N */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{traducir('reportes_ui.top_n')}</label>
            <Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" min={5} max={100} value={topN} onChange={e => setTopN(+e.target.value)} />
          </div>

          {/* Color */}
          <div>
            <span className="rep-ls" id={`${idCampo}-eta746`}>{traducir('reportes_ui.color')}</span>
            <div className="rep-row-6" role="group" aria-labelledby={`${idCampo}-eta746`}>
              {PALETTE.slice(0, 5).map(c => (
                <Pulsable type="button" className={`rep-btn${color === c ? ' rep-btn--activo' : ''}`} key={c} aria-label={traducir('reportes_ui.color_n', { c })} aria-pressed={color === c} onClick={() => setColor(c)}
                  style={{ '--rep-btn-background': c } as CSSProperties}>{null}</Pulsable>
              ))}
              <input className="rep-input" type="color" aria-label={traducir('reportes_ui.color_personalizado')} value={/^#[0-9a-fA-F]{6}$/.test(color) ? color : COLOR_DATO_POR_DEFECTO} onChange={e => setColor(e.target.value)} />
            </div>
          </div>
        </div>

        <div className="rep-row-7">
          {/* Periodo (accesos rápidos y rango libre) */}
          <SelectorDePeriodo {...periodo.selector} sinGranularidad />

          {/* Chart type */}
          <div className="rep-row-9">
            {CHART_TYPES.map(ct => (
              <Pulsable type="button" className={`rep-grafico${chartType === ct.id ? ' rep-grafico--activo' : ''}`} key={ct.id} onClick={() => setChartType(ct.id)} title={traducir(ct.label)} aria-label={traducir(ct.label)} aria-pressed={chartType === ct.id}>
                <ct.Icon size={15} aria-hidden />
              </Pulsable>
            ))}
          </div>
        </div>
      </div>

      {/* Chart area */}
      {!metric ? (
        <div>
          <EmptyState icon={<BarChart3 size={28} />} title={traducir('reports.selecciona_una_metrica_para_empezar')}
            description={traducir('reportes_ui.elige_entre_metricas', { n: Object.values(catalogue || {}).flat().length || '…' })} />
          {/* Métricas populares como acceso rápido */}
          <div className="rep-grid-2">
            {[
              { id: 'hours_by_month', label: traducir('reportes_ui.m_horas_mes'), cat: 'Horas' },
              { id: 'margin_by_project', label: traducir('reportes_ui.m_margen_proyecto'), cat: 'Rentabilidad' },
              { id: 'ticket_volume_trend', label: traducir('reportes_ui.m_volumen_tickets'), cat: 'Service Desk' },
              { id: 'sprint_velocity', label: traducir('reportes_ui.m_velocidad_sprint'), cat: 'Agilidad' },
              { id: 'productivity_by_person', label: traducir('reportes_ui.m_productividad'), cat: 'RRHH' },
              { id: 'pipeline_by_stage', label: traducir('reportes_ui.m_pipeline'), cat: 'Negocio' },
              { id: 'tasks_overdue', label: traducir('reportes_ui.m_tareas_retraso'), cat: 'Agilidad' },
              { id: 'cost_vs_budget', label: traducir('reportes_ui.m_coste_presupuesto'), cat: 'Rentabilidad' },
            ].map(m => (
              <Pulsable className="rep-btn-2" key={m.id} type="button" onClick={() => handleMetricChange(m.id)}>
                <div className="rep-icono-metrica"><IconoCategoria cat={m.cat} size={18} /></div>
                <div className="u-text1-sm-600">{m.label}</div>
                <div className="rep-text-muted-2xs">{etiquetaCategoria(m.cat, traducir)}</div>
              </Pulsable>
            ))}
          </div>
        </div>
      ) : isLoading || isFetching ? (
        <div className="rep-state"><Spinner /></div>
      ) : errorDePeriodo ? (
        <EmptyState icon={<AlertTriangle size={28} />} title={traducir(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
      ) : result ? (
        <div>
          <div className="rep-row-10">
            <div className="u-min0">
              <div className="u-wrap-center-8">
                <h3 className="rep-title-lg-strong">{etiquetaMetrica(traducir, metric, result.meta?.label)}</h3>
                <StatusBadge caps={false}>
                  {etiquetaCategoria(result.meta?.category, traducir)}
                </StatusBadge>
                <span className="u-text3-xs">{traducir('reportes_ui.n_registros', { n: result.total })}</span>
              </div>
              <p className="rep-text-muted-base">{descripcionMetrica(traducir, metric, result.meta?.description)}</p>
            </div>
            <div className="u-wrap-8">
              {onSave && (
                <div className="rep-row-11">
                  <Input inputClassName="rep-input-2" aria-label={traducir('reports.report_name')} value={reportName} onChange={e => setReportName(e.target.value)} placeholder={traducir('reports.report_name')} />
                  <Button size="sm" icon={<Save size={13} />} onClick={() => onSave({ name: reportName || etiquetaMetrica(traducir, metric, result.meta?.label), metric, chartType, color, dateFrom: periodo.fechas.desde, dateTo: periodo.fechas.hasta, projectId, userId, department, topN })} disabled={!metric}>{traducir('reportes_ui.guardar')}</Button>
                </div>
              )}
              <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={() => {
                // Revisión 2026-11: cada valor entre comillas (una coma o un salto de línea rompían las columnas).
                const celda = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
                const csv = [Object.keys(result.rows[0] || {}).map(celda).join(','), ...result.rows.map(r => Object.values(r).map(celda).join(','))].join('\n')
                const a = document.createElement('a'); a.href = 'data:text/csv,' + encodeURIComponent(csv); a.download = `${metric}.csv`; a.click()
              }}>CSV</Button>
              <Button size="sm" variant="secondary" icon={<Image size={13} />} onClick={() => {
                const el = document.querySelector('.recharts-wrapper') || document.querySelector('[data-chart]')
                if (!el) { toast.info(traducir('reportes_ui.elige_grafico')); return }
                import('html2canvas').then(({ default: html2canvas }) => {
                  html2canvas(el as HTMLElement).then(canvas => {
                    const a = document.createElement('a'); a.href = canvas.toDataURL(); a.download = `${metric}.png`; a.click()
                  })
                }).catch(() => toast.error(traducir('reportes_ui.error_imagen')))
              }}>PNG</Button>
            </div>
          </div>

          <SummaryBar summary={result.summary} meta={result.meta} prevSummary={prevResult?.summary} />
          <ChartRenderer data={result.rows} chartType={chartType} meta={result.meta} color={color} height={360} />

          {/* Small data table below chart */}
          {chartType !== 'table' && result.rows.length > 0 && result.rows.length <= 30 && (
            <div className="rep-text-2">
              <div className="rep-text-muted-xs-strong">{traducir('reportes_ui.datos')}</div>
              <TablaDeMetrica data={result.rows} isCurrency={esEjeDeMoneda(result.meta?.y_label, fmtMoneda)} isPercent={result.meta?.y_label?.includes('%')} />
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          icon={<AlertTriangle size={28} />}
          title={traducir('reports.plantilla_no_disponible')}
          description={traducir('reportes_ui.no_disponible_desc')}
        />
      )}
    </div>
  )
}
