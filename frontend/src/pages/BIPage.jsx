import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { PieChart as PieChartIcon } from 'lucide-react'
import useUserPreferences from '../hooks/useUserPreferences'
import { useAppT } from '../i18n/AppLangContext'
import DateRangeFilterBar from '../components/bi/DateRangeFilterBar'
import {
  DEFAULT_LAYOUT,
  WIDGET_ENDPOINTS,
  WIDGET_REGISTRY,
  WidgetPanel,
  ConfigPanel,
  buildWidgetComponents,
} from '../features/bi/widgets'

const FILTERS_STORAGE_KEY = 'bi_filters_v2'

const toCsv = (rows) => {
  if (!rows || !rows.length) return ''
  const keys = Array.from(rows.reduce((acc, row) => {
    Object.keys(row || {}).forEach(k => acc.add(k))
    return acc
  }, new Set()))
  const escape = (v) => {
    if (v == null) return ''
    const s = String(v)
    if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replaceAll('"', '""')}"`
    return s
  }
  const head = keys.join(',')
  const body = rows.map(r => keys.map(k => escape(r[k])).join(',')).join('\n')
  return `${head}\n${body}`
}

const downloadTextFile = (content, filename, mimeType = 'text/plain;charset=utf-8') => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const printNodeInNewWindow = (node, title) => {
  if (!node) return
  const w = window.open('', '_blank', 'width=1280,height=900')
  if (!w) return
  w.document.write(`
    <html>
      <head>
        <title>${title}</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 24px; color: #111; }
          .sheet { max-width: 1200px; margin: 0 auto; }
        </style>
      </head>
      <body>
        <div class="sheet">${node.outerHTML}</div>
      </body>
    </html>
  `)
  w.document.close()
  w.focus()
  w.print()
}

const emptyFilters = {
  dateFrom: '',
  dateTo: '',
  projectId: '',
  projectType: '',
  clientId: '',
  userId: '',
  department: '',
}

const loadStoredFilters = () => {
  try {
    const raw = window.localStorage.getItem(FILTERS_STORAGE_KEY)
    if (!raw) return emptyFilters
    const parsed = JSON.parse(raw)
    return { ...emptyFilters, ...parsed }
  } catch {
    return emptyFilters
  }
}

const buildApiParamsFromFilters = (filters) => ({
  date_from: filters.dateFrom || undefined,
  date_to: filters.dateTo || undefined,
  project_id: filters.projectId || undefined,
  project_type: filters.projectType || undefined,
  client_id: filters.clientId || undefined,
  user_id: filters.userId || undefined,
  department: filters.department || undefined,
})

export default function BIPage() {
  const navigate = useNavigate()
  const t = useAppT()
  const { prefs, save } = useUserPreferences()
  const [configMode, setConfigMode] = useState(false)
  const [showThemePanel, setShowThemePanel] = useState(false)
  const [presentationMode, setPresentationMode] = useState(false)
  const [filters, setFilters] = useState(loadStoredFilters)

  const { data: filterOptions = {} } = useQuery({
    queryKey: ['bi-filter-options'],
    queryFn: () => api.get('/analytics/filters/options').then(r => r.data).catch(() => ({})),
  })

  const [layout, setLayout] = useState(() => prefs.dashboard_widgets || DEFAULT_LAYOUT)

  const prefsLoaded = useRef(false)
  if (!prefsLoaded.current && prefs.dashboard_widgets) {
    prefsLoaded.current = true
    const savedIds = (prefs.dashboard_widgets || []).map(w => w.id)
    const newWidgets = DEFAULT_LAYOUT.filter(w => !savedIds.includes(w.id))
    setLayout([...(prefs.dashboard_widgets || DEFAULT_LAYOUT), ...newWidgets])
  }

  const updateLayout = (newLayout) => {
    setLayout(newLayout)
    save({ dashboard_widgets: newLayout })
  }

  const updateFilters = (updater) => {
    setFilters(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      window.localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }

  const resetFilters = () => updateFilters(emptyFilters)

  const handleSizeChange = (id, size) => updateLayout(layout.map(w => w.id === id ? { ...w, size } : w))
  const handleToggle = (id) => updateLayout(layout.map(w => w.id === id ? { ...w, visible: !w.visible } : w))
  const handleMoveUp = (id) => {
    const idx = layout.findIndex(w => w.id === id)
    if (idx <= 0) return
    const nl = [...layout]
    ;[nl[idx - 1], nl[idx]] = [nl[idx], nl[idx - 1]]
    updateLayout(nl)
  }
  const handleMoveDown = (id) => {
    const idx = layout.findIndex(w => w.id === id)
    if (idx >= layout.length - 1) return
    const nl = [...layout]
    ;[nl[idx], nl[idx + 1]] = [nl[idx + 1], nl[idx]]
    updateLayout(nl)
  }

  const handleDrillProject = useCallback((project) => {
    if (!project?.id) return
    navigate(`/bi/project/${project.id}`, {
      state: {
        projectName: project.fullName || project.name || project.id,
        fromFilters: filters,
      },
    })
  }, [navigate, filters])

  const widgetComponents = useMemo(
    () => buildWidgetComponents({ filters, setFilters: updateFilters, setDrillProject: handleDrillProject }),
    [filters, handleDrillProject],
  )

  const visibleCount = layout.filter(w => w.visible).length

  const handleExportWidgetData = async (wid) => {
    const params = buildApiParamsFromFilters(filters)
    const endpoint = WIDGET_ENDPOINTS[wid]
    if (!endpoint) return
    const res = await api.get(endpoint, { params }).catch(() => null)
    if (!res?.data) return
    const raw = res.data?.rows || res.data?.data || res.data?.team || res.data?.projects || (Array.isArray(res.data) ? res.data : [res.data])
    const rows = Array.isArray(raw) ? raw : [raw]
    const csv = toCsv(rows)
    if (!csv) return
    downloadTextFile(csv, `bi_${wid}_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8')
  }

  const handleExportWidgetPdf = (wid) => {
    const node = document.getElementById(`widget-${wid}`)
    printNodeInNewWindow(node, `Widget ${wid}`)
  }

  const handleExportDashboardPdf = () => {
    const node = document.getElementById('bi-dashboard-root')
    printNodeInNewWindow(node, 'BI Dashboard')
  }

  return (
    <div id="bi-dashboard-root" style={{ padding: presentationMode ? 12 : 28, maxWidth: presentationMode ? '100%' : 1400 }}>
      {!presentationMode && (
        <PageHeader
          icon={<PieChartIcon size={18} />}
          title={t('bi.title')}
          subtitle="Dashboard ejecutivo configurable — datos en tiempo real"
          actions={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {configMode && (
                <button onClick={() => updateLayout(DEFAULT_LAYOUT)} style={{ fontSize: 11, padding: '6px 12px', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                  ↺ Restablecer
                </button>
              )}
              <button onClick={handleExportDashboardPdf} style={{ fontSize: 12, padding: '7px 14px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500 }}>
                PDF
              </button>
              <button onClick={() => setPresentationMode(true)} style={{ fontSize: 12, padding: '7px 14px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500 }}>
                Presentación
              </button>
              <button onClick={() => setShowThemePanel(s => !s)} style={{ fontSize: 12, padding: '7px 14px', borderRadius: 8, background: showThemePanel ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${showThemePanel ? 'var(--accent-glow)' : 'var(--surface-4)'}`, color: showThemePanel ? 'var(--accent)' : 'var(--text-1)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500 }}>
                🎨 Tema
              </button>
              <button onClick={() => setConfigMode(s => !s)} style={{ fontSize: 12, padding: '7px 14px', borderRadius: 8, background: configMode ? 'var(--accent)' : 'var(--surface-2)', border: `1px solid ${configMode ? 'var(--accent)' : 'var(--surface-4)'}`, color: configMode ? '#fff' : 'var(--text-1)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                {configMode ? '✓ Listo' : '⚙ Configurar'}
              </button>
            </div>
          }
        />
      )}

      {!presentationMode && (
        <div style={{ marginTop: 16, marginBottom: 16 }}>
          <DateRangeFilterBar
            dateFrom={filters.dateFrom}
            dateTo={filters.dateTo}
            onDateChange={(from, to) => updateFilters(prev => ({ ...prev, dateFrom: from, dateTo: to }))}
          />
        </div>
      )}

      {!presentationMode && (
        <div style={{ marginBottom: 16, padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 }}>
          <select value={filters.projectId} onChange={e => updateFilters(prev => ({ ...prev, projectId: e.target.value }))} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)' }}>
            <option value="">Todos los proyectos</option>
            {(filterOptions.projects || []).map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <select value={filters.projectType} onChange={e => updateFilters(prev => ({ ...prev, projectType: e.target.value }))} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)' }}>
            <option value="">Todos los tipos</option>
            {(filterOptions.project_types || []).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={filters.clientId} onChange={e => updateFilters(prev => ({ ...prev, clientId: e.target.value }))} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)' }}>
            <option value="">Todos los clientes</option>
            {(filterOptions.clients || []).map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <select value={filters.userId} onChange={e => updateFilters(prev => ({ ...prev, userId: e.target.value }))} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)' }}>
            <option value="">Todas las personas</option>
            {(filterOptions.users || []).map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
          </select>
          <select value={filters.department} onChange={e => updateFilters(prev => ({ ...prev, department: e.target.value }))} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-1)' }}>
            <option value="">Todos los departamentos</option>
            {(filterOptions.departments || []).map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <button onClick={resetFilters} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-3)', color: 'var(--text-2)', cursor: 'pointer' }}>
            Limpiar filtros
          </button>
        </div>
      )}

      {configMode && !presentationMode && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10, fontSize: 12, color: 'var(--accent)' }}>
          Modo configuración activo — usa ↑↓ para reordenar, S/M/L para cambiar tamaño, y ✓ Visible para mostrar/ocultar.
          <span style={{ color: 'var(--text-2)', marginLeft: 8 }}>{visibleCount} de {layout.length} widgets visibles</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 16 }}>
        {layout.map((cfg, idx) => {
          const reg = WIDGET_REGISTRY.find(w => w.id === cfg.id)
          if (!reg) return null
          return (
            <WidgetPanel
              key={cfg.id}
              wid={cfg.id}
              layout={layout}
              onSizeChange={handleSizeChange}
              onToggle={handleToggle}
              onMoveUp={handleMoveUp}
              onMoveDown={handleMoveDown}
              isFirst={idx === 0}
              isLast={idx === layout.length - 1}
              configMode={configMode && !presentationMode}
              onExportData={handleExportWidgetData}
              onExportPdf={handleExportWidgetPdf}
            >
              {widgetComponents[cfg.id]}
            </WidgetPanel>
          )
        })}
      </div>

      {showThemePanel && (
        <ConfigPanel
          prefs={prefs}
          onSave={(patch) => save(patch)}
          onClose={() => setShowThemePanel(false)}
        />
      )}
    </div>
  )
}
