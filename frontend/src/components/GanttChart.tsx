// @ts-nocheck
import { useAppT } from '../i18n/AppLangContext'
/**
 * GanttChart v2 — Production-quality Interactive Gantt
 * Pure SVG + React — no Gantt library required.
 *
 * vs v1: sticky label column · two-tier header · 4 zoom levels ·
 *   milestone diamonds · phase/group rows · assignee avatar ·
 *   dep creation via Shift+drag · critical path amber · baseline bar ·
 *   progress % outside bar · keyboard +/−/Esc
 */
import { useState, useRef, useCallback, useMemo, useEffect } from 'react'

const ZOOM_PRESETS = ['day', 'week', 'month', 'quarter']
const DAY_PX = { day: 22, week: 12, month: 6, quarter: 3 }
const ROW_H    = 38
const GROUP_H  = 28
const HDR_TOP  = 28
const HDR_BOT  = 22
const HEADER_H = HDR_TOP + HDR_BOT
const LABEL_W  = 252
const BAR_PAD  = 7
const MS_R     = 7

const STATUS_COLOR = {
  todo: 'var(--text-3)',
  in_progress: 'var(--accent)',
  in_review: 'var(--warning)',
  done: 'var(--success)',
  blocked: 'var(--danger)',
  active: 'var(--accent)',
  planning: 'var(--purple)',
  paused: 'var(--warning)',
  closed: 'var(--success)',
  cancelled: 'var(--text-3)',
  on_hold: 'var(--warning)',
}

function parseDate(s) {
  if (!s) return null
  if (s instanceof Date) return s
  // Handle both 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:mm:ss' formats
  const d = new Date(s.length > 10 ? s : s + 'T00:00:00')
  return isNaN(d.getTime()) ? null : d
}
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r }
function daysBetween(a, b) { return Math.round((b - a) / 86400000) }
function fmtDate(d) { return d ? d.toISOString().slice(0, 10) : '' }
function weekNum(d) {
  const s = new Date(d.getFullYear(), 0, 1)
  return Math.ceil(((d - s) / 86400000 + s.getDay() + 1) / 7)
}
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1) }
function startOfQuarter(d) { return new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1) }
function startOfMonday(d) { const r = new Date(d); const day = r.getDay(); r.setDate(r.getDate() - (day === 0 ? 6 : day - 1)); return r }

function getTopTicks(zoom, minD, maxD) {
  const ticks = []
  if (zoom === 'day' || zoom === 'week') {
    let d = startOfMonth(minD)
    while (d <= maxD) {
      ticks.push({ d: new Date(d), label: d.toLocaleString('es', { month: 'long', year: 'numeric' }) })
      d = new Date(d.getFullYear(), d.getMonth() + 1, 1)
    }
  } else if (zoom === 'month') {
    let d = startOfQuarter(minD)
    while (d <= maxD) {
      const q = Math.floor(d.getMonth() / 3) + 1
      ticks.push({ d: new Date(d), label: `Q${q} ${d.getFullYear()}` })
      const m = d.getMonth() + 3
      d = new Date(d.getFullYear() + Math.floor(m / 12), m % 12, 1)
    }
  } else {
    let year = minD.getFullYear()
    while (year <= maxD.getFullYear()) {
      ticks.push({ d: new Date(year, 0, 1), label: String(year) })
      year++
    }
  }
  return ticks
}

function getBotTicks(zoom, minD, maxD) {
  const ticks = []
  if (zoom === 'day') {
    let d = new Date(minD)
    while (d <= maxD) {
      const day = d.getDay()
      if (day !== 0 && day !== 6) ticks.push({ d: new Date(d), label: d.getDate().toString() })
      d = addDays(d, 1)
    }
  } else if (zoom === 'week') {
    let d = startOfMonday(minD)
    while (d <= maxD) {
      ticks.push({ d: new Date(d), label: `W${weekNum(d)} · ${d.getDate()}/${d.getMonth() + 1}` })
      d = addDays(d, 7)
    }
  } else if (zoom === 'month') {
    let d = startOfMonth(minD)
    while (d <= maxD) {
      ticks.push({ d: new Date(d), label: d.toLocaleString('es', { month: 'short' }) + " '" + d.getFullYear().toString().slice(2) })
      d = new Date(d.getFullYear(), d.getMonth() + 1, 1)
    }
  } else {
    let d = startOfQuarter(minD)
    while (d <= maxD) {
      ticks.push({ d: new Date(d), label: `Q${Math.floor(d.getMonth() / 3) + 1}` })
      const m = d.getMonth() + 3
      d = new Date(d.getFullYear() + Math.floor(m / 12), m % 12, 1)
    }
  }
  return ticks
}

function getWeekends(zoom, minD, maxD, dateToX, dayPx) {
  if (zoom !== 'day' && zoom !== 'week') return []
  const result = []
  let d = new Date(minD)
  while (d <= maxD) {
    if (d.getDay() === 0 || d.getDay() === 6) result.push({ x: dateToX(d), w: dayPx })
    d = addDays(d, 1)
  }
  return result
}

export default function GanttChart({
  tasks = [],
  projects = [],
  mode = 'project',
  onTaskUpdate,
  onDepCreate,
  showBaseline = false,
  dependencies = [],
  aiSuggestions = {},
}) {
    const t = useAppT()
  const [zoom, setZoom]           = useState('month')
  const [dragState, setDragState] = useState(null)
  const [depDraw, setDepDraw]     = useState(null)
  const [collapsed, setCollapsed] = useState(new Set())
  const [tooltip, setTooltip]     = useState(null)
  const [hoveredDep, setHoveredDep] = useState(null)

  const scrollRef = useRef(null)
  const labelRef  = useRef(null)
  const dayPx = DAY_PX[zoom]

  const allItems = mode === 'portfolio' ? projects : tasks

  const { minDate, maxDate } = useMemo(() => {
    const dates = []
    for (const item of allItems) {
      const s = parseDate(item.start_date)
      const e = parseDate(item.due_date || item.end_date_planned || item.end_date)
      if (s) dates.push(s)
      if (e) dates.push(e)
    }
    if (!dates.length) {
      const t = new Date()
      return { minDate: addDays(t, -30), maxDate: addDays(t, 60) }
    }
    return {
      minDate: addDays(new Date(Math.min(...dates)), -14),
      maxDate: addDays(new Date(Math.max(...dates)), 21),
    }
  }, [allItems])

  const totalDays = daysBetween(minDate, maxDate)
  const chartW    = Math.max(totalDays * dayPx, 600)

  const dateToX = useCallback((d) => {
    if (!d) return 0
    return daysBetween(minDate, d) * dayPx
  }, [minDate, dayPx])

  const topTicks = useMemo(() => getTopTicks(zoom, minDate, maxDate), [zoom, minDate, maxDate])
  const botTicks = useMemo(() => getBotTicks(zoom, minDate, maxDate), [zoom, minDate, maxDate])
  const weekends = useMemo(() => getWeekends(zoom, minDate, maxDate, dateToX, dayPx), [zoom, minDate, maxDate, dateToX, dayPx])

  const today  = new Date()
  const todayX = dateToX(today)

  const items = useMemo(() => allItems.filter(item => {
    if (!item.group_id) return true
    return !collapsed.has(item.group_id)
  }), [allItems, collapsed])

  const rowsLayout = useMemo(() => {
    const acc = { y: 0, rows: [] }
    for (const item of items) {
      const isGroup = item.is_group || item.type === 'group' || item.type === 'phase'
      const h = isGroup ? GROUP_H : ROW_H
      acc.rows.push({ item, y: acc.y, h, isGroup })
      acc.y += h
    }
    return acc.rows
  }, [items])

  const totalContentH = rowsLayout.reduce((acc, r) => acc + r.h, 0)
  const svgHeight = HEADER_H + totalContentH + 16

  const itemYCenter = useMemo(() => {
    const map = {}
    rowsLayout.forEach(({ item, y, h }) => { map[item.id] = HEADER_H + y + h / 2 })
    return map
  }, [rowsLayout])

  const onRightScroll = useCallback((e) => {
    if (labelRef.current) labelRef.current.scrollTop = e.target.scrollTop
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') { setDragState(null); setDepDraw(null) }
      if ((e.key === '+' || e.key === '=') && !e.target.closest('input,textarea')) {
        setZoom(z => { const i = ZOOM_PRESETS.indexOf(z); return i > 0 ? ZOOM_PRESETS[i - 1] : z })
      }
      if (e.key === '-' && !e.target.closest('input,textarea')) {
        setZoom(z => { const i = ZOOM_PRESETS.indexOf(z); return i < ZOOM_PRESETS.length - 1 ? ZOOM_PRESETS[i + 1] : z })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const startDrag = useCallback((e, item, type) => {
    if (type === 'resize' && e.shiftKey && onDepCreate) {
      e.preventDefault(); e.stopPropagation()
      const svgR  = scrollRef.current?.getBoundingClientRect()
      const row   = rowsLayout.find(r => r.item.id === item.id)
      const fromX = dateToX(parseDate(item.due_date || item.end_date_planned)) + 8
      const fromY = HEADER_H + (row?.y || 0) + (row?.h || ROW_H) / 2
      setDepDraw({ fromId: item.id, fromX, fromY, toX: fromX, toY: fromY })
      const onMove = (me) => {
        const scrollX = scrollRef.current?.scrollLeft || 0
        const scrollY = scrollRef.current?.scrollTop  || 0
        setDepDraw(d => ({ ...d,
          toX: me.clientX - (svgR?.left || 0) + scrollX,
          toY: me.clientY - (svgR?.top  || 0) + scrollY,
        }))
      }
      const onUp = (me) => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        setDepDraw(null)
        const svgR2   = scrollRef.current?.getBoundingClientRect()
        const scrollY2 = scrollRef.current?.scrollTop || 0
        const relY    = me.clientY - (svgR2?.top || 0) + scrollY2 - HEADER_H
        const hit     = rowsLayout.find(r => relY >= r.y && relY < r.y + r.h)
        if (hit && hit.item.id !== item.id) onDepCreate({ predecessor_id: item.id, successor_id: hit.item.id })
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
      return
    }
    if (!onTaskUpdate) return
    e.preventDefault(); e.stopPropagation()
    const startX = e.clientX
    const origS  = parseDate(item.start_date)
    const origE  = parseDate(item.due_date || item.end_date_planned || item.end_date)
    const onMove = (me) => {
      const dDays = Math.round((me.clientX - startX) / dayPx)
      if (type === 'move') {
        setDragState({ id: item.id, start: fmtDate(origS ? addDays(origS, dDays) : null), end: fmtDate(origE ? addDays(origE, dDays) : null), type: 'move' })
      } else {
        if (!origE) return
        const rawE = addDays(origE, dDays)
        const minE = origS ? addDays(origS, 1) : rawE
        setDragState({ id: item.id, start: fmtDate(origS), end: fmtDate(rawE > minE ? rawE : minE), type: 'resize' })
      }
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setDragState(prev => { if (prev) onTaskUpdate(prev); return null })
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [dayPx, dateToX, onTaskUpdate, onDepCreate, rowsLayout])

  const LBL_ZOOM = {
    day: t('gantt.view_day'),
    week: t('gantt.view_week'),
    month: t('gantt.view_month'),
    quarter: t('gantt.view_quarter'),
  }

  // Check if we have any items with valid dates
  if (!allItems || allItems.length === 0) {
    const emptyMsg = mode === 'portfolio' 
      ? t('projects.empty') || 'No hay proyectos para mostrar'
      : t('tasks.empty') || 'No hay tareas para mostrar'
    return (
      <div style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-3)' }}>
        <p style={{ fontSize: "var(--text-md)", marginBottom: 8 }}>📊 {emptyMsg}</p>
      </div>
    )
  }

  return (
    <div style={{ userSelect: 'none', fontFamily: 'var(--font-sans)' }}>
      {/* Controls */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>{t('gantt.zoom')}</span>
        {ZOOM_PRESETS.map(z => (
          <button key={z} onClick={() => setZoom(z)}
            style={{
              padding: '4px 12px', borderRadius: 6,
              border: `1px solid ${zoom === z ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
              background: zoom === z ? 'var(--accent-muted)' : 'transparent',
              color: zoom === z ? 'var(--accent)' : 'var(--text-2)',
              fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: zoom === z ? 600 : 400,
            }}>
            {LBL_ZOOM[z]}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, fontSize: "var(--text-xs)", color: 'var(--text-2)', alignItems: 'center', flexWrap: 'wrap' }}>
          {[['var(--accent)', t('tasks.status_in_progress'), false], ['var(--success)', t('common.completed'), false], ['var(--danger)', t('tasks.status_blocked'), false], ['var(--purple)', t('gantt.milestone'), true]].map(([c, l, rot]) => (
            <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 10, height: 10, background: c, borderRadius: rot ? 2 : 3, transform: rot ? 'rotate(45deg)' : 'none' }} />
              {l}
            </span>
          ))}
          {showBaseline && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 10, height: 3, background: 'rgba(255,255,255,0.25)', borderRadius: 2 }} />{t('gantt.baseline')}
            </span>
          )}
          <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', borderLeft: '1px solid var(--surface-4)', paddingLeft: 10 }}>
            +/− zoom · Esc cancelar{onDepCreate ? ' · Shift+▶ dep' : ''}
          </span>
        </div>
      </div>

      {/* Main: 2-column CSS grid */}
      <div style={{ display: 'grid', gridTemplateColumns: `${LABEL_W}px 1fr`, border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden', background: 'var(--surface-1)' }}>

        {/* Left: label column */}
        <div style={{ borderRight: '1px solid var(--surface-4)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ height: HEADER_H, minHeight: HEADER_H, flexShrink: 0, borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-0)', display: 'flex', alignItems: 'flex-end', padding: '0 14px 6px' }}>
            <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.07em' }}>
              {mode === 'portfolio' ? 'Proyecto' : 'Tarea / Fase'}
            </span>
          </div>
          <div ref={labelRef} style={{ overflow: 'hidden', flex: 1 }}>
            {rowsLayout.map(({ item, h, isGroup }) => {
              const isOverdue = !isGroup && item.due_date && parseDate(item.due_date) < today &&
                !['done', 'closed', 'cancelled'].includes(item.status)
              const dotColor = isOverdue ? 'var(--danger)' : (STATUS_COLOR[item.status] || 'var(--text-3)')
              return (
                <div key={item.id} style={{
                  height: h, borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 60%, transparent)',
                  display: 'flex', alignItems: 'center',
                  padding: isGroup ? '0 10px' : '0 14px', gap: 7,
                  background: isGroup ? 'rgba(79,142,247,0.04)' : 'transparent',
                }}>
                  {isGroup ? (
                    <>
                      <button
                        onClick={() => setCollapsed(s => { const n = new Set(s); n.has(item.id) ? n.delete(item.id) : n.add(item.id); return n })}
                        aria-label={collapsed.has(item.id) ? 'Expandir grupo' : 'Contraer grupo'}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text-3)', fontSize: "var(--text-3xs)" }}>
                        {collapsed.has(item.id) ? '▶' : '▼'}
                      </button>
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '.05em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                        {item.title || item.name}
                      </span>
                    </>
                  ) : (
                    <>
                      <div style={{ width: 7, height: 7, borderRadius: item.is_milestone ? 0 : '50%', background: dotColor, flexShrink: 0, transform: item.is_milestone ? 'rotate(45deg)' : 'none' }} />
                      <span style={{ fontSize: "var(--text-sm)", color: isOverdue ? 'var(--danger)' : 'rgba(200,216,240,0.85)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                        {item.title || item.name}
                      </span>
                      {item.story_points > 0 && (
                        <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', background: 'var(--surface-4)', padding: '1px 4px', borderRadius: 4, flexShrink: 0 }}>
                          {item.story_points}p
                        </span>
                      )}
                      {item.assignee_name && (
                        <div style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--accent-glow)', border: '1px solid var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-8)", fontWeight: 700, color: 'var(--accent)', flexShrink: 0 }}>
                          {item.assignee_name.slice(0, 1).toUpperCase()}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: SVG scroll area */}
        <div ref={scrollRef} onScroll={onRightScroll} style={{ overflow: 'auto', maxHeight: 540 }}>
          <svg width={chartW} height={svgHeight} style={{ display: 'block' }}>

            {/* Weekend shading */}
            {weekends.map((w, i) => (
              <rect key={i} x={w.x} y={0} width={w.w} height={svgHeight} fill="rgba(255,255,255,0.025)" />
            ))}

            {/* Header */}
            <rect x={0} y={0} width={chartW} height={HEADER_H} fill="var(--surface-0)" />

            {/* Top ticks (months / quarters / years) */}
            {topTicks.map(({ d, label }, i) => {
              const x = Math.max(0, dateToX(d))
              return (
                <g key={i}>
                  <line x1={x} y1={0} x2={x} y2={HEADER_H} stroke="var(--surface-4)" />
                  <text x={x + 6} y={HDR_TOP / 2 + 5} fontSize={11} fill="var(--text-2)" fontFamily="inherit" fontWeight={600}>{label}</text>
                </g>
              )
            })}
            <line x1={0} y1={HDR_TOP} x2={chartW} y2={HDR_TOP} stroke="var(--surface-4)" />

            {/* Bottom ticks (weeks / days / months) */}
            {botTicks.map(({ d, label }, i) => {
              const x = dateToX(d)
              const isToday = fmtDate(d) === fmtDate(today)
              return (
                <g key={i}>
                  <line x1={x} y1={HDR_TOP} x2={x} y2={svgHeight} stroke="color-mix(in srgb, var(--surface-4) 50%, transparent)" />
                  <text x={x + 4} y={HDR_TOP + HDR_BOT / 2 + 5} fontSize={10}
                    fill={isToday ? 'var(--danger)' : 'var(--text-3)'} fontFamily="inherit" fontWeight={isToday ? 700 : 400}>
                    {label}
                  </text>
                </g>
              )
            })}
            <line x1={0} y1={HEADER_H} x2={chartW} y2={HEADER_H} stroke="var(--surface-4)" />

            {/* Today line */}
            {todayX >= 0 && todayX <= chartW && (
              <g>
                <line x1={todayX} y1={HEADER_H} x2={todayX} y2={svgHeight} stroke="var(--danger)" strokeWidth={1.5} strokeDasharray="3 3" opacity={0.65} />
                <rect x={todayX - 16} y={HEADER_H - 14} width={32} height={12} rx={3} fill="var(--danger)" />
                <text x={todayX} y={HEADER_H - 5} textAnchor="middle" fontSize={8} fontWeight={700} fill="white" fontFamily="inherit">HOY</text>
              </g>
            )}

            {/* Bars */}
            {rowsLayout.map(({ item, y: rowY, h, isGroup }) => {
              const svgY = HEADER_H + rowY
              if (isGroup) {
                return <rect key={item.id} x={0} y={svgY} width={chartW} height={h} fill="rgba(79,142,247,0.04)" />
              }

              const eff = dragState?.id === item.id
                ? { ...item, start_date: dragState.start, due_date: dragState.end, end_date_planned: dragState.end }
                : item
              const startD    = parseDate(eff.start_date)
              const endD      = parseDate(eff.due_date || eff.end_date_planned || eff.end_date)
              const isOverdue = endD && endD < today && !['done', 'closed', 'cancelled'].includes(item.status)
              const barColor  = isOverdue ? 'var(--danger)' : item.is_critical ? 'var(--orange)' : (STATUS_COLOR[item.status] || 'var(--text-3)')
              const isDragging = dragState?.id === item.id
              const progress   = item.progress_pct != null ? item.progress_pct / 100
                : item.status === 'done' ? 1 : item.status === 'in_progress' ? 0.4 : 0

              // Milestone diamond
              if (item.is_milestone && endD) {
                const mx = dateToX(endD)
                const my = svgY + h / 2
                return (
                  <g key={item.id} onMouseEnter={() => setTooltip({ item, x: mx, y: svgY })} onMouseLeave={() => setTooltip(null)}>
                    <rect x={0} y={svgY} width={chartW} height={h} fill="transparent" />
                    <line x1={0} y1={svgY + h} x2={chartW} y2={svgY + h} stroke="color-mix(in srgb, var(--surface-4) 40%, transparent)" />
                    <rect x={mx - MS_R} y={my - MS_R} width={MS_R * 2} height={MS_R * 2}
                      fill={barColor + '30'} stroke={barColor} strokeWidth={1.5}
                      transform={`rotate(45,${mx},${my})`} rx={1} style={{ cursor: 'pointer' }} />
                  </g>
                )
              }

              if (!startD || !endD) {
                // Show placeholder bar for items without dates
                const x1 = 40  // Fixed position for items without dates
                return (
                  <g key={item.id} onMouseEnter={() => setTooltip({ item, x: x1 + 80, y: svgY })} onMouseLeave={() => setTooltip(null)}>
                    <rect x={0} y={svgY} width={chartW} height={h} fill="transparent" />
                    <line x1={0} y1={svgY + h} x2={chartW} y2={svgY + h} stroke="color-mix(in srgb, var(--surface-4) 40%, transparent)" />
                    <rect x={x1} y={svgY + BAR_PAD} width={150} height={h - BAR_PAD * 2} rx={4}
                      fill="color-mix(in srgb, var(--surface-4) 50%, transparent)" stroke="color-mix(in srgb, var(--surface-4) 70%, transparent)" strokeWidth={1.5} strokeDasharray="3,2"
                      style={{ cursor: 'default', opacity: 0.7 }} />
                    <text x={x1 + 10} y={svgY + h / 2 + 3} fontSize={11} fill="var(--text-3)" fontFamily="inherit" fontWeight={500}
                      style={{ pointerEvents: 'none', fontStyle: 'italic' }}>
                      📅 Sin fechas definidas
                    </text>
                  </g>
                )
              }

              const x1 = dateToX(startD)
              const bW  = Math.max(dateToX(endD) - x1, 10)
              const bY  = svgY + BAR_PAD
              const bH  = h - BAR_PAD * 2

              return (
                <g key={item.id} onMouseEnter={() => setTooltip({ item, x: x1 + bW / 2, y: svgY })} onMouseLeave={() => setTooltip(null)}>
                  <rect x={0} y={svgY} width={chartW} height={h} fill={item.is_critical ? 'rgba(251,146,60,0.04)' : 'transparent'} />
                  <line x1={0} y1={svgY + h} x2={chartW} y2={svgY + h} stroke="color-mix(in srgb, var(--surface-4) 40%, transparent)" />

                  {/* Baseline */}
                  {showBaseline && item.baseline_start && item.baseline_end && (() => {
                    const bx1 = dateToX(parseDate(item.baseline_start))
                    const bx2 = dateToX(parseDate(item.baseline_end))
                    return <rect x={bx1} y={svgY + h - 5} width={Math.max(bx2 - bx1, 4)} height={4} rx={2} fill="rgba(255,255,255,0.15)" />
                  })()}

                  {/* Main bar */}
                  <rect x={x1} y={bY} width={bW} height={bH} rx={4}
                    fill={barColor + '28'} stroke={barColor} strokeWidth={isDragging ? 2 : 1}
                    style={{ cursor: onTaskUpdate ? 'grab' : 'default', opacity: isDragging ? 0.65 : 1, filter: isDragging ? `drop-shadow(0 0 6px ${barColor})` : 'none' }}
                    onMouseDown={e => startDrag(e, item, 'move')} />

                  {/* Progress fill */}
                  {progress > 0 && (
                    <rect x={x1} y={bY} width={Math.max(bW * progress, 4)} height={bH} rx={4}
                      fill={barColor + '80'} style={{ pointerEvents: 'none' }} />
                  )}

                  {/* Text label */}
                  {bW > 50 && (
                    <>
                      <clipPath id={`gc${item.id}`}><rect x={x1 + 4} y={bY} width={bW - 16} height={bH} /></clipPath>
                      <text x={x1 + 8} y={bY + bH / 2 + 4} fontSize={10} fill="white" fontFamily="inherit"
                        style={{ pointerEvents: 'none' }} clipPath={`url(#gc${item.id})`}>
                        {(item.title || item.name || '').slice(0, Math.ceil(bW / 7))}
                      </text>
                    </>
                  )}

                  {/* Progress % outside bar */}
                  {progress > 0 && bW > 38 && (
                    <text x={x1 + bW + 5} y={bY + bH / 2 + 4} fontSize={9} fill={barColor}
                      fontFamily="inherit" style={{ pointerEvents: 'none' }}>
                      {Math.round(progress * 100)}%
                    </text>
                  )}

                  {/* Resize handle */}
                  {onTaskUpdate && (
                    <rect x={x1 + bW - 8} y={bY + 2} width={8} height={bH - 4} rx={2}
                      fill={barColor + '55'} style={{ cursor: 'ew-resize' }}
                      title={onDepCreate ? 'Redimensionar · Shift+drag = crear dependencia' : 'Redimensionar'}
                      onMouseDown={e => { e.stopPropagation(); startDrag(e, item, 'resize') }} />
                  )}

                  {/* Item #47: badge IA si la tarea tiene sugerencia (overdue/stalled).
                      Color por severidad (high=danger, medium=warning). El tooltip
                      mostrará el detalle al hover sobre el bar entero. */}
                  {aiSuggestions[item.id] && (() => {
                    const sug = aiSuggestions[item.id]
                    const sevColor = sug.severity === 'high'
                      ? 'var(--danger)'
                      : 'var(--warning)'
                    return (
                      <g style={{ pointerEvents: 'none' }}>
                        <circle cx={x1 - 8} cy={bY + bH / 2} r={7}
                          fill={sevColor} stroke="var(--surface-0)" strokeWidth={1.5} />
                        <text x={x1 - 8} y={bY + bH / 2 + 3.5} fontSize={9}
                          fill="white" fontFamily="inherit" fontWeight={700}
                          textAnchor="middle">!</text>
                      </g>
                    )
                  })()}
                </g>
              )
            })}

            {/* Dependency arrows */}
            {dependencies.map((dep, di) => {
              const pred = items.find(t => t.id === dep.predecessor_id)
              const succ = items.find(t => t.id === dep.successor_id)
              if (!pred || !succ) return null
              const predEndD   = parseDate(pred.due_date || pred.end_date_planned)
              const succStartD = parseDate(succ.start_date)
              if (!predEndD || !succStartD) return null
              const x1 = dateToX(predEndD); const y1 = itemYCenter[pred.id]
              const x2 = dateToX(succStartD); const y2 = itemYCenter[succ.id]
              if (!y1 || !y2) return null
              const isHov = hoveredDep === di
              const col   = 'var(--warning)'
              const midX  = x1 + 16
              const path  = y1 === y2
                ? `M ${x1} ${y1} L ${x2} ${y2}`
                : `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`
              return (
                <g key={di} style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredDep(di)} onMouseLeave={() => setHoveredDep(null)}>
                  <path d={path} fill="none" stroke="transparent" strokeWidth={8} />
                  <path d={path} fill="none" stroke={col} strokeWidth={isHov ? 2 : 1.5} strokeDasharray="5 3" opacity={0.75} />
                  <polygon points={`${x2},${y2} ${x2 - 7},${y2 - 4} ${x2 - 7},${y2 + 4}`} fill={col} opacity={0.75} />
                  {isHov && (
                    <text x={(x1 + x2) / 2} y={Math.min(y1, y2) - 4} fontSize={9} fill={col}
                      textAnchor="middle" fontFamily="inherit" fontWeight={700}>
                      {dep.dependency_type || 'FS'}
                    </text>
                  )}
                </g>
              )
            })}

            {/* Dep creation ghost line */}
            {depDraw && (
              <g style={{ pointerEvents: 'none' }}>
                <line x1={depDraw.fromX} y1={depDraw.fromY} x2={depDraw.toX} y2={depDraw.toY}
                  stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="5 3" opacity={0.85} />
                <circle cx={depDraw.toX} cy={depDraw.toY} r={5} fill="var(--accent)" opacity={0.85} />
              </g>
            )}

            {/* Tooltip — item #47: si la tarea tiene sugerencia IA, ampliamos
                la altura del tooltip y añadimos el mensaje + primera sugerencia. */}
            {tooltip && (() => {
              const { item, x, y } = tooltip
              const sug = aiSuggestions[item.id]
              const TW = sug ? 240 : 180
              const TH = sug ? 92 : 50
              const tx = Math.min(Math.max(x - TW / 2, 4), chartW - TW - 4)
              const ty = y - (TH + 6)
              const sevColor = sug?.severity === 'high'
                ? 'var(--danger)'
                : sug?.severity === 'medium'
                  ? 'var(--warning)'
                  : 'var(--text-3)'
              return (
                <g style={{ pointerEvents: 'none' }}>
                  <rect x={tx} y={ty} width={TW} height={TH} rx={7} fill="var(--surface-1)" stroke="var(--surface-4)" />
                  <text x={tx + 8} y={ty + 16} fontSize={11} fill="var(--text-1)" fontFamily="inherit" fontWeight={600}>
                    {(item.title || item.name || '').slice(0, 32)}
                  </text>
                  <text x={tx + 8} y={ty + 30} fontSize={10} fill="var(--text-3)" fontFamily="inherit">
                    {item.start_date || '?'} {'→'} {item.due_date || item.end_date_planned || '?'}
                  </text>
                  <text x={tx + 8} y={ty + 44} fontSize={10} fill={STATUS_COLOR[item.status] || 'var(--text-3)'} fontFamily="inherit">
                    {item.status}{item.progress_pct != null ? ` · ${item.progress_pct}%` : ''}{item.story_points ? ` · ${item.story_points}p` : ''}
                  </text>
                  {sug && (
                    <>
                      <line x1={tx + 8} y1={ty + 52} x2={tx + TW - 8} y2={ty + 52}
                        stroke="var(--surface-4)" strokeWidth={1} />
                      <text x={tx + 8} y={ty + 65} fontSize={10} fill={sevColor}
                        fontFamily="inherit" fontWeight={600}>
                        {sug.type === 'overdue' ? '⚠ Retraso' : '⏳ Estancada'} · {sug.message?.slice(0, 32)}
                      </text>
                      <text x={tx + 8} y={ty + 80} fontSize={9} fill="var(--text-2)" fontFamily="inherit">
                        💡 {(sug.suggestions?.[0] || '').slice(0, 38)}
                      </text>
                    </>
                  )}
                </g>
              )
            })()}
          </svg>
        </div>
      </div>
    </div>
  )
}
