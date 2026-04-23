/**
 * DashboardGrid — Motor compartido para todos los dashboards del sistema
 *
 * Nivel 1: rowHeight=30, alturas adaptativas, bloqueo de layout
 * Nivel 2: Pantalla completa por widget (Esc para cerrar)
 * Nivel 3: Pestañas multi-dashboard, filtro global de fechas, exportar
 */
import { useState, useRef, useEffect, useCallback, createContext, useContext, useMemo } from 'react'
import GridLayout from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

// ── Contexto para propagar dateRange a todos los widgets ──────────────────────
export const DateRangeCtx = createContext(null)
export const useDateRange = () => useContext(DateRangeCtx)

// ── Hook de persistencia multi-dashboard ─────────────────────────────────────
function buildDefaultConfig(allWidgets) {
  return {
    visible: allWidgets.filter(w => !w.defaultHidden).map(w => w.id),
    layout: allWidgets.map(w => ({ i: w.id, ...w.defaultPos })),
  }
}

function useDashboards(storageKey, allWidgets, api) {
  const [dashboards, setDashboards] = useState(null)
  const [activeId, setActiveId] = useState('main')

  const defaultDashboards = useMemo(
    () => [{ id: 'main', name: 'Principal', config: buildDefaultConfig(allWidgets) }],
    [allWidgets],
  )

  const saveLocal = useCallback((d) => {
    try { localStorage.setItem(storageKey, JSON.stringify(d)) } catch {}
  }, [storageKey])

  const saveBackend = useCallback((d) => {
    if (!api) return
    api.patch('/users/me/preferences', { [`dboards_${storageKey}`]: d }).catch(() => {})
  }, [api, storageKey])

  useEffect(() => {
    let ok = true
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length > 0) {
          if (ok) setDashboards(parsed)
          return
        }
      }
    } catch {}
    if (ok) setDashboards(defaultDashboards)
    return () => { ok = false }
  }, [storageKey, defaultDashboards])

  const boards = dashboards || defaultDashboards
  const active = boards.find(d => d.id === activeId) || boards[0]
  const config = active?.config || buildDefaultConfig(allWidgets)

  const save = useCallback((newBoards) => {
    setDashboards(newBoards)
    saveLocal(newBoards)
    saveBackend(newBoards)
  }, [saveLocal, saveBackend])

  const updConfig = useCallback((newCfg) => {
    save(boards.map(d => d.id === activeId ? { ...d, config: newCfg } : d))
  }, [boards, activeId, save])

  const toggleWidget = useCallback((id) => {
    const visible = config.visible.includes(id)
      ? config.visible.filter(x => x !== id)
      : [...config.visible, id]
    updConfig({ ...config, visible })
  }, [config, updConfig])

  const updateLayout = useCallback((newLayout) => {
    const byId = Object.fromEntries(allWidgets.map(w => [w.id, w]))
    const map = Object.fromEntries(config.layout.map(l => [l.i, l]))
    newLayout.forEach(item => {
      const meta = byId[item.i] || {}
      let normalized = { ...item }
      if (meta.aspectRatio && Number(meta.aspectRatio) > 0) {
        const minH = Number(meta.defaultPos?.minH) || 1
        const expectedH = Math.max(minH, Math.round((item.w || 1) / Number(meta.aspectRatio)))
        normalized = { ...normalized, h: expectedH }
      }
      map[item.i] = { ...map[item.i], ...normalized }
    })
    updConfig({ ...config, layout: Object.values(map) })
  }, [allWidgets, config, updConfig])

  const resetConfig = useCallback(() => updConfig(buildDefaultConfig(allWidgets)), [allWidgets, updConfig])

  const createDashboard = useCallback(() => {
    const id = `d${Date.now()}`
    const newB = [...boards, { id, name: `Dashboard ${boards.length + 1}`, config: buildDefaultConfig(allWidgets) }]
    save(newB)
    setActiveId(id)
  }, [boards, allWidgets, save])

  const deleteDashboard = useCallback((id) => {
    if (boards.length <= 1) return
    const newB = boards.filter(d => d.id !== id)
    save(newB)
    if (activeId === id) setActiveId(newB[0].id)
  }, [boards, activeId, save])

  const renameDashboard = useCallback((id, name) => {
    save(boards.map(d => d.id === id ? { ...d, name } : d))
  }, [boards, save])

  const visibleLayout = config.layout
    .filter(l => config.visible.includes(l.i))
    .map(l => {
      const w = allWidgets.find(x => x.id === l.i)
      return { ...w?.defaultPos, ...l }
    })

  return {
    boards, activeId, setActiveId,
    config, visibleLayout,
    toggleWidget, updateLayout, resetConfig,
    createDashboard, deleteDashboard, renameDashboard,
  }
}

// ── Filtro de fecha ───────────────────────────────────────────────────────────
const PRESETS = [
  { label: '7d',   fn: () => sub(7) },
  { label: '30d',  fn: () => sub(30) },
  { label: '90d',  fn: () => sub(90) },
  { label: 'Mes',  fn: () => startOf('month') },
  { label: 'Trim', fn: () => startOf('quarter') },
  { label: 'Año',  fn: () => startOf('year') },
]
function sub(days) {
  const to = new Date(), from = new Date()
  from.setDate(from.getDate() - days)
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) }
}
function startOf(unit) {
  const to = new Date()
  let from = new Date()
  if (unit === 'month') from = new Date(to.getFullYear(), to.getMonth(), 1)
  if (unit === 'quarter') { const q = Math.floor(to.getMonth() / 3); from = new Date(to.getFullYear(), q * 3, 1) }
  if (unit === 'year') from = new Date(to.getFullYear(), 0, 1)
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) }
}

function DateRangePicker({ value, onChange }) {
  const [custom, setCustom] = useState(false)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {PRESETS.map(p => (
        <button key={p.label} onClick={() => { onChange(p.fn()); setCustom(false) }} style={{
          padding: '4px 8px', borderRadius: 6, border: '1px solid var(--surface-4)',
          background: 'var(--surface-2)', color: 'var(--text-2)', fontSize: 10, fontWeight: 700,
          cursor: 'pointer', fontFamily: 'inherit',
        }}>{p.label}</button>
      ))}
      <button onClick={() => setCustom(c => !c)} style={{
        padding: '4px 8px', borderRadius: 6, border: '1px solid var(--surface-4)',
        background: custom ? 'var(--accent-muted)' : 'var(--surface-2)',
        color: custom ? 'var(--accent)' : 'var(--text-2)',
        fontSize: 10, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
      }}>✏</button>
      {custom && (
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="date" value={value?.from || ''} onChange={e => onChange({ ...value, from: e.target.value })}
            style={{ padding: '3px 6px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 10 }} />
          <span style={{ color: 'var(--text-3)', fontSize: 10 }}>→</span>
          <input type="date" value={value?.to || ''} onChange={e => onChange({ ...value, to: e.target.value })}
            style={{ padding: '3px 6px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 10 }} />
        </div>
      )}
      {value && !custom && (
        <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{value.from} → {value.to}</span>
      )}
      {value && (
        <button onClick={() => onChange(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 12, padding: '2px' }}>×</button>
      )}
    </div>
  )
}

// ── Celda de widget — mide su altura y la pasa al widget ──────────────────────
function WidgetCell({
  id,
  allWidgets,
  renderWidget,
  dateRange,
  locked,
  onFullScreen,
  rowHeight,
  marginY,
  currentRows,
  onAutoHeight,
}) {
  const contentRef = useRef(null)
  const [height, setHeight] = useState(200)
  const rafRef = useRef(null)

  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => setHeight(entries[0].contentRect.height))
    ro.observe(el)
    setHeight(el.getBoundingClientRect().height)
    return () => ro.disconnect()
  }, [])

  const w = allWidgets.find(x => x.id === id)

  useEffect(() => {
    if (!w?.fitContent || !onAutoHeight) return
    const el = contentRef.current
    if (!el) return

    const updateAutoHeight = () => {
      const contentNode = el.firstElementChild
      const intrinsicContentPx = contentNode
        ? Math.ceil(contentNode.getBoundingClientRect().height)
        : Math.ceil(el.scrollHeight)
      const bodyPx = Math.max(0, intrinsicContentPx)
      const headerPx = 28
      const framePx = 2
      const breathingPx = Number(w.fitContentExtraPx) || 10
      const wantedPx = bodyPx + headerPx + framePx + breathingPx
      const wantedRowsRaw = toGridRows(wantedPx, rowHeight, marginY)
      const minRows = Number(w.defaultPos?.minH) || 1
      const maxRows = Number(w.fitContentMaxRows) || null
      let wantedRows = Math.max(minRows, wantedRowsRaw)
      if (maxRows) wantedRows = Math.min(wantedRows, maxRows)
      if (Math.abs(wantedRows - currentRows) >= 1) onAutoHeight(id, wantedRows)
    }

    updateAutoHeight()
    const ro = new ResizeObserver(() => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(updateAutoHeight)
    })
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      ro.disconnect()
    }
  }, [id, currentRows, marginY, onAutoHeight, rowHeight, w])

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, overflow: 'hidden',
    }}>
      {/* Drag handle */}
      <div
        className="dash-drag-handle"
        style={{
          height: 28, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 8px 0 8px',
          background: 'var(--surface-3)', borderBottom: '1px solid var(--surface-4)',
          cursor: locked ? 'default' : 'grab', userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          {!locked && <span style={{ color: 'var(--text-4, var(--text-3))', fontSize: 9, letterSpacing: 2, flexShrink: 0 }}>⠿⠿</span>}
          <span style={{ fontSize: 12, flexShrink: 0 }}>{w?.icon}</span>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w?.title}</span>
        </div>
        <button
          onMouseDown={e => e.stopPropagation()}
          onClick={() => onFullScreen(id)}
          title="Pantalla completa · Esc para cerrar"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 11, padding: '2px 4px', flexShrink: 0 }}
        >⛶</button>
      </div>
      {/* Widget content with measured height */}
      <div
        ref={contentRef}
        style={{
          flex: w?.fitContent ? '0 0 auto' : 1,
          minHeight: 0,
          overflow: w?.fitContent ? 'visible' : 'auto',
        }}
      >
        {renderWidget(id, { dateRange, height })}
      </div>
    </div>
  )
}

function toGridRows(px, rowHeight, marginY) {
  const rh = Number(rowHeight) || 30
  const my = Number(marginY) || 0
  return Math.max(1, Math.ceil((Math.max(0, px) + my) / (rh + my)))
}

// ── DashboardGrid principal ───────────────────────────────────────────────────
export default function DashboardGrid({
  storageKey,
  title,
  subtitle,
  allWidgets,
  renderWidget,
  headerExtra,
  api,
}) {
  const GRID_ROW_HEIGHT = 30
  const GRID_MARGIN_Y = 12

  const {
    boards, activeId, setActiveId,
    config, visibleLayout,
    toggleWidget, updateLayout, resetConfig,
    createDashboard, deleteDashboard, renameDashboard,
  } = useDashboards(storageKey, allWidgets, api)

  const [locked, setLocked] = useState(false)
  const [fullScreenId, setFullScreenId] = useState(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [dateRange, setDateRange] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const containerRef = useRef(null)
  const [gridWidth, setGridWidth] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => setGridWidth(el.getBoundingClientRect().width)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const autoFitWidgetHeight = useCallback((id, newRows) => {
    const target = Number(newRows)
    if (!Number.isFinite(target) || target <= 0) return
    const current = config.layout.find(l => l.i === id)
    if (!current || current.h === target) return
    updateLayout(config.layout.map(l => (l.i === id ? { ...l, h: target } : l)))
  }, [config.layout, updateLayout])

  // Esc cierra pantalla completa
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setFullScreenId(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleExport = () => window.print()

  return (
    <DateRangeCtx.Provider value={dateRange}>
      <div style={{ padding: 28, maxWidth: '100%' }}>

        {/* ── Pantalla completa (Level 2) ─────────────────────────────────── */}
        {fullScreenId && (
          <div style={{
            position: 'fixed', inset: 0, background: 'var(--surface-1)', zIndex: 9998,
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{
              height: 48, flexShrink: 0, display: 'flex', alignItems: 'center',
              justifyContent: 'space-between', padding: '0 20px',
              background: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)',
            }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>
                {allWidgets.find(w => w.id === fullScreenId)?.icon}{' '}
                {allWidgets.find(w => w.id === fullScreenId)?.title}
              </span>
              <button onClick={() => setFullScreenId(null)} style={{
                background: 'none', border: '1px solid var(--surface-4)', borderRadius: 7,
                cursor: 'pointer', color: 'var(--text-2)', fontSize: 13, padding: '4px 10px', fontFamily: 'inherit',
              }}>✕ Esc</button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 24 }}>
              {renderWidget(fullScreenId, { dateRange, height: window.innerHeight - 100 })}
            </div>
          </div>
        )}

        {/* ── Pestañas multi-dashboard (Level 3) ─────────────────────────── */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          {boards.map(d => (
            <div key={d.id} style={{ display: 'flex', alignItems: 'center' }}>
              {renamingId === d.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onBlur={() => { renameDashboard(d.id, renameValue || d.name); setRenamingId(null) }}
                  onKeyDown={e => { if (e.key === 'Enter') { renameDashboard(d.id, renameValue || d.name); setRenamingId(null) } if (e.key === 'Escape') setRenamingId(null) }}
                  style={{ padding: '4px 8px', borderRadius: 7, border: '1px solid var(--accent)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 12, fontFamily: 'inherit', width: 120 }}
                />
              ) : (
                <button
                  onClick={() => setActiveId(d.id)}
                  onDoubleClick={() => { setRenamingId(d.id); setRenameValue(d.name) }}
                  title="Doble clic para renombrar"
                  style={{
                    padding: '5px 12px', borderRadius: renamingId ? 0 : 7,
                    border: `1px solid ${activeId === d.id ? 'rgba(79,142,247,0.45)' : 'var(--surface-4)'}`,
                    background: activeId === d.id ? 'var(--accent-muted)' : 'var(--surface-2)',
                    color: activeId === d.id ? 'var(--accent)' : 'var(--text-2)',
                    cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
                  }}
                >{d.name}</button>
              )}
              {boards.length > 1 && (
                <button onClick={() => deleteDashboard(d.id)} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-3)', fontSize: 13, padding: '3px 5px',
                }} title="Eliminar">×</button>
              )}
            </div>
          ))}
          <button onClick={createDashboard} style={{
            padding: '5px 10px', borderRadius: 7, border: '1px dashed var(--surface-4)',
            background: 'transparent', color: 'var(--text-3)', cursor: 'pointer',
            fontSize: 12, fontFamily: 'inherit',
          }} title="Nuevo dashboard">＋</button>
        </div>

        {/* ── Cabecera ────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 2 }}>{title}</div>
            {subtitle && <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{typeof subtitle === 'function' ? subtitle() : subtitle}</div>}
          </div>
          <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Filtro fecha (Level 3) */}
            <DateRangePicker value={dateRange} onChange={setDateRange} />

            {/* Bloquear (Level 1) */}
            <button onClick={() => setLocked(l => !l)} title={locked ? 'Desbloquear layout' : 'Bloquear layout'} style={{
              padding: '6px 10px', borderRadius: 7,
              border: `1px solid ${locked ? 'rgba(79,142,247,0.45)' : 'var(--surface-4)'}`,
              background: locked ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: locked ? 'var(--accent)' : 'var(--text-2)',
              cursor: 'pointer', fontSize: 13, lineHeight: 1,
            }}>{locked ? '🔒' : '🔓'}</button>

            {/* Exportar (Level 3) */}
            <button onClick={handleExport} title="Exportar dashboard como imagen/PDF" style={{
              padding: '6px 11px', borderRadius: 7, border: '1px solid var(--surface-4)',
              background: 'var(--surface-2)', color: 'var(--text-2)', cursor: 'pointer',
              fontSize: 12, fontFamily: 'inherit',
            }}>⬇ Exportar</button>

            {/* Personalizar */}
            <button onClick={() => setConfigOpen(o => !o)} style={{
              padding: '6px 13px', borderRadius: 7,
              border: `1px solid ${configOpen ? 'rgba(79,142,247,0.45)' : 'var(--surface-4)'}`,
              background: configOpen ? 'var(--accent-muted)' : 'var(--surface-2)',
              color: configOpen ? 'var(--accent)' : 'var(--text-2)',
              cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
            }}>⊞ Personalizar</button>
            {headerExtra}
          </div>
        </div>

        {/* ── Catálogo de widgets ─────────────────────────────────────────── */}
        {configOpen && (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '18px 22px', marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Widgets disponibles</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Arrastra ⠿⠿ para mover · esquina inferior derecha para redimensionar</div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={resetConfig} style={{ fontSize: 11, color: 'var(--text-2)', background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontFamily: 'inherit' }}>Restablecer</button>
                <button onClick={() => setConfigOpen(false)} style={{ fontSize: 17, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px' }}>×</button>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(155px, 1fr))', gap: 7 }}>
              {allWidgets.map(w => {
                const visible = config.visible.includes(w.id)
                return (
                  <div key={w.id} style={{
                    display: 'flex', alignItems: 'center', gap: 7, padding: '7px 10px',
                    background: 'var(--surface-3)', borderRadius: 8,
                    border: `1px solid ${visible ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
                    opacity: visible ? 1 : 0.55, transition: 'all 0.15s',
                  }}>
                    <span style={{ fontSize: 13 }}>{w.icon}</span>
                    <span style={{ flex: 1, fontSize: 11, color: visible ? 'var(--text-1)' : 'var(--text-3)', fontWeight: 500 }}>{w.title}</span>
                    <button onClick={() => toggleWidget(w.id)} style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: visible ? 'var(--accent)' : 'var(--text-3)', fontSize: 13, padding: '1px',
                    }}>{visible ? '👁' : '○'}</button>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ── Grid (Level 1) ──────────────────────────────────────────────── */}
        <div id="dashboard-print-area" ref={containerRef}>
          {gridWidth > 0 && config.visible.length > 0 && (
            <GridLayout
              layout={visibleLayout}
              cols={12}
              rowHeight={GRID_ROW_HEIGHT}
              width={gridWidth}
              onLayoutChange={locked ? undefined : updateLayout}
              isDraggable={!locked}
              isResizable={!locked}
              draggableHandle=".dash-drag-handle"
              margin={[12, GRID_MARGIN_Y]}
              containerPadding={[0, 0]}
              resizeHandles={['se', 's', 'e']}
              useCSSTransforms
            >
              {config.visible.map(id => {
                const item = visibleLayout.find(l => l.i === id)
                return (
                <div key={id}>
                  <WidgetCell
                    id={id}
                    allWidgets={allWidgets}
                    renderWidget={renderWidget}
                    dateRange={dateRange}
                    locked={locked}
                    onFullScreen={setFullScreenId}
                    rowHeight={GRID_ROW_HEIGHT}
                    marginY={GRID_MARGIN_Y}
                    currentRows={item?.h || 1}
                    onAutoHeight={autoFitWidgetHeight}
                  />
                </div>
                )
              })}
            </GridLayout>
          )}
          {config.visible.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-3)' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>⊞</div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Dashboard vacío</div>
              <div style={{ fontSize: 13 }}>Abre «Personalizar» para añadir widgets</div>
            </div>
          )}
        </div>
      </div>

      {/* Print styles */}
      <style>{`
        @media print {
          body > * { display: none !important; }
          #dashboard-print-area { display: block !important; position: static !important; }
          .dash-drag-handle { display: none !important; }
          .react-resizable-handle { display: none !important; }
          .react-grid-item { break-inside: avoid; }
        }
      `}</style>
    </DateRangeCtx.Provider>
  )
}
