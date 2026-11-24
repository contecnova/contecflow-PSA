/**
 * ReportsPage — informes (/reports): métricas, explorador, plantillas,
 * guardados y programados.
 *
 * 16-11-2026: pasada de diseño. Las pestañas (control segmentado) estaban
 * dentro de la cabecera: ahora Tabs bajo ella. Fuera todos los emojis (iconos
 * de categoría, de plantilla, de frecuencia, etiquetas de filtro, botones
 * CSV/PNG/PDF/papelera) por iconos lucide; tipos de gráfico con iconos lucide;
 * resumen con KpiCard (antes cifras monoespaciadas); vacíos con EmptyState;
 * campos `ds-input` (antes grises propios); aviso de correo en lenguaje llano
 * (antes nombres de variables de entorno SMTP_*); fechas con el formateador.
 */
import { useState, type CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { analyticsApi, usersApi } from '../services/api'
import { Buscador, Card, Button, Spinner, EmptyState, Tabs, Pulsable, IconButton, Page } from '../components/ui'
import { BarChart2, Grid3X3, Search, Zap, Pin, Calendar, Pencil, Trash2, ArrowRight, BarChart3 } from 'lucide-react'
import { extractErr, localeActivo } from '../utils/helpers'
import { alpha } from '../constants/theme'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaMetrica } from '../i18n/catalogoMetricas'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { STALE_5_MIN_MS } from '../constants/timings'
import {
  type Catalogue,
  esEjeDeMoneda,
  etiquetaCategoria,
  ICONO_GRAFICO,
  IconoCategoria,
  type MetricResult,
  type ReportConfig,
  type SavedReport,
  type UserPreferences,
} from './reportes/compartido'
import { ChartRenderer } from './reportes/graficos'
import { type Preset, PRESETS } from './reportes/presets'
import { ReportPanel } from './reportes/PanelDeReporte'
import { ScheduledReportsTab } from './reportes/ReportesProgramados'
import './ReportsPage.css'

// ── Dashboard mode: multiple panels ──────────────────────────────────────────
function ReportsDashboard({ saved, onRemove, onOpen }: { saved: SavedReport[]; onRemove?: (id: string) => void; onOpen?: (report: SavedReport) => void }) {
  const traducir = useAppT()
  const _today = new Date().toISOString().split('T')[0]
  const _d90 = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0]

  return (
    <div className="rep-grid-3">
      {saved.map(r => (
        <Card key={r.id} className="reportsp-sx1">
          <div className="rep-row-12">
            <div className="u-md-700">{r.name}</div>
            <div className="u-row-6">
              <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => onOpen(r)}>{traducir('reportes_ui.editar')}</Button>
              <IconButton variante="caja" tono="peligro" ariaLabel={traducir('reportes_ui.eliminar_informe')} title={traducir('reportes_ui.eliminar_informe')} onClick={() => openConfirmGlobal({ message: traducir('reportes_ui.eliminar_informe_confirm', { nombre: r.name || '' }), danger: true, onConfirm: () => onRemove?.(r.id) })}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          </div>
          <MiniPanel config={r} />
        </Card>
      ))}
    </div>
  )
}

function MiniPanel({ config }: { config: SavedReport }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  const { data: result, isLoading } = useQuery<MetricResult | null>({
    queryKey: ['analytics-mini', config.metric, config.dateFrom, config.dateTo, config.projectId, config.userId],
    queryFn: () => analyticsApi.query(config.metric, { date_from: config.dateFrom, date_to: config.dateTo, project_id: config.projectId || undefined, user_id: config.userId || undefined, top_n: 10 }).then(r => r.data),
    enabled: !!config.metric,
    retry: false,
  })
  if (isLoading) return <div className="rep-row-13"><Spinner /></div>
  if (!result) return null
  return (
    <div>
      {result.summary?.total > 0 && (
        <div className="rep-mini-total rep-text-7" style={{ '--rep-text-7-color': config.color || 'var(--accent)' } as CSSProperties}>
          {esEjeDeMoneda(result.meta?.y_label, fmtMoneda) ? fmtMoneda(result.summary.total, { decimales: 0 }) : result.summary.total.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })}
          <span className="rep-text-muted-sm">{traducir('reportes_ui.total')}</span>
        </div>
      )}
      <ChartRenderer data={result.rows} chartType={config.chartType || 'bar'} meta={result.meta} color={config.color || 'var(--accent)'} height={160} />
    </div>
  )
}

// ── PresetsTab ─────────────────────────────────────────────────────────────────
function PresetsTab({ presets, supportedMetrics, onOpen }: { presets: readonly Preset[]; supportedMetrics?: Set<string> | null; onOpen?: (preset: Preset) => void }) {
  const traducir = useAppT()
  const [filterCat, setFilterCat] = useState<string>('all')
  const [searchQ, setSearchQ] = useState('')
  // When supportedMetrics is null the analytics catalogue is unavailable (e.g. 503).
  // In that case show all presets so the user can still browse and attempt to run them.
  const enabledPresets = supportedMetrics !== null
    ? presets.filter(p => supportedMetrics.has(p.metric))
    : presets
  const cats = ['all', ...new Set(enabledPresets.map(p => p.cat).filter(Boolean))]
  const byCat = filterCat === 'all' ? enabledPresets : enabledPresets.filter(p => p.cat === filterCat)
  const filtered = searchQ.trim().length < 2
    ? byCat
    : byCat.filter(p => traducir(p.label).toLowerCase().includes(searchQ.toLowerCase()) || etiquetaCategoria(p.cat, traducir).toLowerCase().includes(searchQ.toLowerCase()))

  const chartLabels: Record<string, string> = { bar: traducir('reportes_ui.graf_bar'), bar_grouped: traducir('reportes_ui.graf_agrupadas'), bar_stacked: traducir('reportes_ui.graf_apiladas'),
    line: traducir('reportes_ui.graf_line'), area: traducir('reportes_ui.graf_area'), pie: traducir('reportes_ui.graf_pie'), donut: traducir('reportes_ui.graf_donut'), heatmap: traducir('reportes_ui.graf_heatmap'), table: traducir('reportes_ui.graf_table') }

  return (
    <div>
      <div className="u-mb-12">
        <Buscador aria-label={traducir('reportes_ui.buscar_plantilla')} value={searchQ} onChange={setSearchQ} placeholder={traducir('reportes_ui.buscar_plantilla')} />
      </div>
      <div className="rep-row-17">
        {cats.map(c => (
          <Pulsable className={`rep-chip${filterCat === c ? ' rep-chip--activo' : ''}`} type="button" aria-pressed={filterCat === c} key={c} onClick={() => setFilterCat(c)}>
            {c !== 'all' && <IconoCategoria cat={c} size={12} />}
            {c === 'all' ? traducir('reportes_ui.todas_n', { n: enabledPresets.length }) : etiquetaCategoria(c, traducir)}
          </Pulsable>
        ))}
      </div>
      {searchQ.trim().length >= 2 && (
        <div className="rep-text-muted-sm-3">
          {filtered.length === 0 ? traducir('reportes_ui.sin_resultados') : filtered.length === 1 ? traducir('reportes_ui.una_plantilla') : traducir('reportes_ui.n_plantillas', { n: filtered.length })}
        </div>
      )}
      <div className="rep-grid-5">
        {filtered.map(p => (
          <Pulsable className="rep-btn-3" key={p.id} type="button" onClick={() => onOpen(p)}
            style={{ '--rep-btn-3-border': `1px solid ${alpha(p.color, '25')}`, '--rep-btn-3-tono': p.color } as CSSProperties}>
            <div className="rep-icono-metrica rep-text-8" style={{ '--rep-text-8-color': p.color } as CSSProperties}><IconoCategoria cat={p.cat} size={18} /></div>
            <div className="rep-text-base-strong">{traducir(p.label)}</div>
            <div className="rep-preset-pie">
              {etiquetaCategoria(p.cat, traducir)} · {chartLabels[p.chart] || p.chart}
              <ArrowRight size={12} aria-hidden />
            </div>
          </Pulsable>
        ))}
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const traducir = useAppT()
  const t = useAppT()
  const { puede } = useAuth()
  // Los programados son de responsables (la API solo los sirve a ellos).
  const veProgramados = puede('informes.programar')
  const [mode, setMode] = useState<string>('explorer') // explorer | dashboard | presets
  const [editingReport, setEditingReport] = useState<ReportConfig | null>(null)
  // Revisión 2026-11: los guardados viven en las preferencias del usuario en el
  // servidor (`extra.informes_guardados`); antes, en una variable que se perdía
  // al recargar la página.
  const qc = useQueryClient()
  const toast = useToast()
  const { data: prefs } = useQuery<UserPreferences>({
    queryKey: ['user-preferences'],
    queryFn: () => usersApi.preferencias<UserPreferences>().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
  const saved: SavedReport[] = Array.isArray(prefs?.extra?.informes_guardados) ? prefs.extra.informes_guardados : []
  const guardar = useMutation({
    mutationFn: (lista: SavedReport[]) => usersApi.guardarPreferenciasExtra({ informes_guardados: lista }),
    onMutate: (lista: SavedReport[]) => qc.setQueryData<UserPreferences>(['user-preferences'], old => ({ ...(old || {}), extra: { ...(old?.extra || {}), informes_guardados: lista } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ['user-preferences'] }),
    onError: (e: unknown) => toast.error(extractErr(e, traducir('reportes_ui.error_guardar'))),
  })

  const saveReport = (config: ReportConfig) => {
    const existing = saved.find(r => r.name === config.name)
    const report: SavedReport = { ...config, id: existing?.id || Date.now().toString(), savedAt: new Date().toISOString() }
    guardar.mutate(existing ? saved.map(r => r.id === report.id ? report : r) : [...saved, report])
  }

  const removeReport = (id: string) => guardar.mutate(saved.filter(r => r.id !== id))

  const openReport = (r: SavedReport) => { setEditingReport(r); setMode('explorer') }

  const { data: catalogue } = useQuery<Catalogue>({ queryKey: ['analytics-catalogue'], queryFn: () => analyticsApi.catalogue().then(r => r.data) })
  const catalogueLoaded = catalogue !== undefined
  const catalogueHasData = catalogueLoaded && Object.keys(catalogue || {}).length > 0
  const totalMetrics = Object.values(catalogue || {}).flat().length
  // null means catalogue not yet loaded or unavailable — PresetsTab will show all presets
  const supportedMetrics = catalogueHasData
    ? new Set(Object.values(catalogue).flat().map(m => m.id))
    : null

  const [_schedTab, _setSchedTab] = useState('main')
  const MODES = [
    { id: 'overview',  label: traducir('reportes_ui.modo_metricas'), Icon: Grid3X3 },
    { id: 'explorer',  label: traducir('reportes_ui.modo_explorador'), Icon: Search },
    { id: 'presets',   label: traducir('reportes_ui.modo_plantillas'), Icon: Zap },
    { id: 'dashboard', label: saved.length ? traducir('reportes_ui.modo_guardados_n', { n: saved.length }) : traducir('reportes_ui.modo_guardados'), Icon: Pin },
    ...(veProgramados ? [{ id: 'scheduled', label: traducir('reportes_ui.modo_programados'), Icon: Calendar }] : []),
  ]

  return (
    <Page
      icon={<BarChart2 size={18} />}
      title={t('nav.reports')}
      subtitle={t('reports.subtitle')}
    >
      <Tabs
        ariaLabel={traducir('reports.modo_de_informe')}
        active={mode}
        onChange={setMode}
        items={MODES.map(({ id, label, Icon }) => ({ id, label, icon: <Icon size={14} /> }))}
      />

      {/* Plantillas */}
      {mode === 'presets' && <PresetsTab presets={PRESETS} supportedMetrics={supportedMetrics} onOpen={p => { setEditingReport({ metric: p.metric, chartType: p.chart, color: p.color }); setMode('explorer') }} />}

      {/* Overview — todas las métricas organizadas por categoría */}
      {mode === 'overview' && (
        <div>
          <p className="rep-text-muted-base-2">
            {traducir('reports.metricas_en_categorias', { n: totalMetrics, categorias: Object.keys(catalogue || {}).length })}
          </p>
          {catalogue && Object.entries(catalogue).map(([cat, items]) => (
            <div className="rep-text-3" key={cat}>
              <div className="rep-row-muted-2">
                <IconoCategoria cat={cat} size={15} /> {etiquetaCategoria(cat, traducir)}
                <span className="rep-text-muted-2xs-3">({items.length})</span>
              </div>
              <div className="u-wrap-8">
                {items.map(item => (
                  <Pulsable className="rep-btn-sm-3" key={item.id} onClick={() => { setEditingReport({ metric: item.id, chartType: item.default_chart }); setMode('explorer') }}>
                    {(() => { const IconoGrafico = ICONO_GRAFICO[item.default_chart] || BarChart3; return <IconoGrafico size={12} className="rep-text-muted-2xs-4" aria-hidden /> })()}
                    {etiquetaMetrica(traducir, item.id, item.label)}
                  </Pulsable>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Explorer */}
      {mode === 'explorer' && (
        <Card className="reportsp-sx2">
          <ReportPanel
            key={editingReport ? `${editingReport.metric}-${editingReport.chartType || 'bar'}` : 'new'}
            initialMetric={editingReport?.metric}
            initialChart={editingReport?.chartType}
            onSave={saveReport}
          />
        </Card>
      )}

      {/* Dashboard */}
      {mode === 'dashboard' && (
        saved.length === 0 ? (
          <EmptyState svgIcon={<Pin size={36} />} title={traducir('reports.sin_informes_guardados')} description={traducir('reportes_ui.sin_guardados_desc')} />
        ) : (
          <ReportsDashboard saved={saved} onRemove={removeReport} onOpen={openReport} />
        )
      )}
      {/* Visualizaciones avanzadas (BI) */}

      {/* Scheduled Reports */}
      {mode === 'scheduled' && veProgramados && <ScheduledReportsTab />}
    </Page>
  )
}
