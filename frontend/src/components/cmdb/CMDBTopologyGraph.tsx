/**
 * CMDBTopologyGraph — 2D SVG radial + 3D Plotly scatter3d topology viewer.
 *
 * Props (acepta ambas formas de payload):
 *  - nodes: [{id, name, ci_type, is_root|is_center, criticality|status, depth?, hostname?}]
 *  - edges: [{source, target, relation_type|rel_type}]
 *  - onNodeClick: (node) => void
 *  - centerName: string
 */
import { useMemo, useState, useCallback } from 'react'
import type { CSSProperties } from 'react'
// @ts-expect-error react-plotly.js ships no type declarations
import Plot from 'react-plotly.js'

interface RawNode {
  [key: string]: unknown
  id: string
  name?: string
  ci_type?: string
  is_center?: boolean
  is_root?: boolean
  status?: string
  criticality?: string
  hostname?: string
  depth?: number
}
interface GraphNode extends RawNode {
  is_center: boolean
  status: string
}
interface RawEdge {
  [key: string]: unknown
  source: string
  target: string
  rel_type?: string
  relation_type?: string
}
interface GraphEdge extends RawEdge {
  rel_type: string
}
type Pos2D = { x: number; y: number }
type Pos3D = { x: number; y: number; z: number }
type DistMap = Record<string, number>

const CI_ICONS: Record<string, string> = {
  server: '🖥️', application: '📱', database: '🗄️', network: '🌐',
  service: '⚙️', container: '📦', cloud: '☁️', endpoint: '💻',
  storage: '💾', other: '📌',
}

const STATUS_COLORS: Record<string, string> = {
  active: '#34d399',
  maintenance: '#f59e0b',
  decommissioned: '#f87171',
}

// Color por criticidad (cuando el payload viene del endpoint SD CMDB)
const CRITICALITY_COLORS: Record<string, string> = {
  low:      '#34d399',
  medium:   '#f59e0b',
  high:     '#fb923c',
  critical: '#f87171',
}

function normalizeNode(n: RawNode): GraphNode {
  return {
    ...n,
    is_center: (n.is_center ?? n.is_root ?? false) as boolean,
    status: (n.status ?? n.criticality ?? 'active') as string,
  }
}

function normalizeEdge(e: RawEdge): GraphEdge {
  return {
    ...e,
    rel_type: (e.rel_type ?? e.relation_type ?? 'depends_on') as string,
  }
}

function pickNodeColor(n: GraphNode): string {
  // Prioriza criticality si está presente; fallback a status
  if (n.criticality && CRITICALITY_COLORS[n.criticality]) return CRITICALITY_COLORS[n.criticality]
  return STATUS_COLORS[n.status] || STATUS_COLORS.active
}

const REL_COLORS: Record<string, string> = {
  depends_on: '#4f8ef7',
  runs_on: '#60a5fa',
  connects_to: '#a78bfa',
  hosts: '#34d399',
  monitors: '#f59e0b',
  backs_up: '#64748b',
}

// Impact coloring by BFS hop distance from selected source node
const IMPACT_COLORS: Record<number, string> = {
  0: '#a78bfa', // source — violet
  1: '#f87171', // hop 1 — red (direct impact)
  2: '#fb923c', // hop 2 — orange
  3: '#f59e0b', // hop 3 — yellow
}
const IMPACT_LABELS: Record<number, string> = {
  0: 'Origen del impacto',
  1: 'Impacto directo (hop 1)',
  2: 'Impacto indirecto (hop 2)',
  3: 'Impacto periférico (hop 3)',
}

// ─── BFS ─────────────────────────────────────────────────────────────────────

function bfsDistances(nodes: GraphNode[], edges: GraphEdge[], sourceId: string): DistMap {
  const adj: Record<string, string[]> = {}
  nodes.forEach(n => { adj[n.id] = [] })
  edges.forEach(e => {
    if (adj[e.source] !== undefined) adj[e.source].push(e.target)
    if (adj[e.target] !== undefined) adj[e.target].push(e.source)
  })
  const dist: DistMap = { [sourceId]: 0 }
  const queue: string[] = [sourceId]
  while (queue.length) {
    const curr = queue.shift() as string
    for (const nb of (adj[curr] || [])) {
      if (dist[nb] === undefined) {
        dist[nb] = dist[curr] + 1
        queue.push(nb)
      }
    }
  }
  return dist
}

// ─── 2D LAYOUT (radial layered by BFS hop) ───────────────────────────────────

function layoutNodes2D(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number): Record<string, Pos2D> {
  const center = nodes.find(n => n.is_center) || nodes[0]
  if (!center) return {}
  const cx = width / 2
  const cy = height / 2
  const dist = bfsDistances(nodes, edges, center.id)
  const layers: Record<number, GraphNode[]> = {}
  nodes.forEach(n => {
    const d = dist[n.id] ?? 99
    if (!layers[d]) layers[d] = []
    layers[d].push(n)
  })
  const positions: Record<string, Pos2D> = {}
  Object.entries(layers).forEach(([dStr, layerNodes]) => {
    const d = Number(dStr)
    if (d === 0) { positions[center.id] = { x: cx, y: cy }; return }
    const r = Math.min(width, height) * (0.17 + 0.16 * d)
    layerNodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / layerNodes.length - Math.PI / 2
      positions[n.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
    })
  })
  return positions
}

// ─── 3D LAYOUT (fibonacci sphere per BFS layer) ──────────────────────────────

function fibonacciSphere(n: number, R: number): Array<[number, number, number]> {
  if (n === 0) return []
  if (n === 1) return [[R, 0, 0]]
  const phi = Math.PI * (3 - Math.sqrt(5))
  return Array.from({ length: n }, (_, i): [number, number, number] => {
    const y = (1 - (i / (n - 1)) * 2) * R
    const r = Math.sqrt(Math.max(0, R * R - y * y))
    const theta = phi * i
    return [r * Math.cos(theta), y, r * Math.sin(theta)]
  })
}

function layout3D(nodes: GraphNode[], edges: GraphEdge[]): Record<string, Pos3D> {
  if (!nodes.length) return {}
  const center = nodes.find(n => n.is_center) || nodes[0]
  const dist = bfsDistances(nodes, edges, center.id)
  const layers: Record<number, string[]> = {}
  nodes.forEach(n => {
    const d = dist[n.id] ?? 99
    if (!layers[d]) layers[d] = []
    layers[d].push(n.id)
  })
  const positions: Record<string, Pos3D> = { [center.id]: { x: 0, y: 0, z: 0 } }
  Object.entries(layers).forEach(([dStr, ids]) => {
    const d = Number(dStr)
    if (d === 0) return
    const pts = fibonacciSphere(ids.length, d * 2.8)
    ids.forEach((id, i) => {
      positions[id] = { x: pts[i][0], y: pts[i][1], z: pts[i][2] }
    })
  })
  return positions
}

// ─── TOOLBAR BUTTON STYLE ────────────────────────────────────────────────────

const tbBtn = (active: boolean): CSSProperties => ({
  padding: '4px 12px', borderRadius: 6, fontSize: "var(--text-sm)", cursor: 'pointer',
  border: '1px solid var(--surface-4)', fontFamily: 'inherit',
  background: active ? 'var(--accent)' : 'var(--surface-3)',
  color: active ? '#fff' : 'var(--text-2)', transition: 'background .15s, color .15s',
})

// ─── 2D SVG COMPONENT ────────────────────────────────────────────────────────

interface GraphViewProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  impactDist: DistMap | null
  impactRadius: number
  onNodeClick?: (node: GraphNode) => void
  onImpactSourceChange: (nodeId: string) => void
}
interface Graph2DProps extends GraphViewProps {
  hovered: string | null
  setHovered: (id: string | null) => void
}

function Graph2D({ nodes, edges, impactDist, impactRadius, onNodeClick, onImpactSourceChange, hovered, setHovered }: Graph2DProps) {
  const W = 700
  const H = 500

  const positions = useMemo(() => layoutNodes2D(nodes, edges, W, H), [nodes, edges])

  const getColor = useCallback((node: GraphNode) => {
    if (impactDist) {
      const d = impactDist[node.id]
      if (d === undefined || d > impactRadius) return '#334155'
      return IMPACT_COLORS[Math.min(d, 3)]
    }
    return pickNodeColor(node)
  }, [impactDist, impactRadius])

  const getEdgeOpacity = useCallback((e: GraphEdge) => {
    if (!impactDist) return 0.45
    const sd = impactDist[e.source], td = impactDist[e.target]
    if (sd === undefined || td === undefined) return 0.1
    if (Math.max(sd, td) <= impactRadius) return 0.85
    return 0.1
  }, [impactDist, impactRadius])

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', maxHeight: 500, borderRadius: 12, background: 'var(--surface-3)', border: '1px solid var(--surface-4)' }}
      aria-label="CMDB topology graph 2D"
    >
      <defs>
        {Object.entries(REL_COLORS).map(([rel, color]) => (
          <marker key={rel} id={`arrow-${rel}`} markerWidth="8" markerHeight="8" refX="16" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill={color} opacity={0.7} />
          </marker>
        ))}
      </defs>

      {/* Edges */}
      {edges.map((e, i) => {
        const sp = positions[e.source], tp = positions[e.target]
        if (!sp || !tp) return null
        const color = REL_COLORS[e.rel_type] || '#64748b'
        const isHov = hovered === e.source || hovered === e.target
        const opacity = getEdgeOpacity(e)
        return (
          <g key={i}>
            <line
              x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
              stroke={color} strokeWidth={isHov ? 2.5 : 1.5}
              strokeOpacity={isHov ? 0.9 : opacity}
              markerEnd={`url(#arrow-${e.rel_type || 'depends_on'})`}
            />
            {isHov && (
              <text x={(sp.x + tp.x) / 2} y={(sp.y + tp.y) / 2 - 5}
                textAnchor="middle" fill={color} fontSize="10" fontFamily="inherit" opacity={0.9}>
                {e.rel_type}
              </text>
            )}
          </g>
        )
      })}

      {/* Nodes */}
      {nodes.map((n) => {
        const p = positions[n.id]
        if (!p) return null
        const isCenter = !!n.is_center
        const isHov = hovered === n.id
        const isImpactSrc = impactDist && impactDist[n.id] === 0
        const nodeColor = getColor(n)
        const r = isCenter ? 30 : 22
        const isOutside = impactDist && (impactDist[n.id] === undefined || impactDist[n.id] > impactRadius)

        return (
          <g
            key={n.id}
            transform={`translate(${p.x},${p.y})`}
            style={{ cursor: 'pointer' }}
            onMouseEnter={() => setHovered(n.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => { onImpactSourceChange(n.id); onNodeClick && onNodeClick(n) }}
            role="button"
            aria-label={`CI ${n.name}`}
          >
            {(isCenter || isImpactSrc) && (
              <circle r={r + 8} fill="none" stroke={nodeColor} strokeWidth={2} opacity={0.3} />
            )}
            {isImpactSrc && (
              <circle r={r + 14} fill="none" stroke={IMPACT_COLORS[0]} strokeWidth={1}
                strokeDasharray="6 4" opacity={0.5} />
            )}
            <circle
              r={r}
              fill={isCenter ? 'var(--accent)' : (isOutside ? 'var(--surface-4)' : 'var(--surface-2)')}
              stroke={nodeColor}
              strokeWidth={isHov ? 3 : (isImpactSrc ? 2.5 : 1.5)}
              opacity={isOutside ? 0.35 : 0.95}
            />
            {!isCenter && !isOutside && (
              <circle r={r + 4} fill="none" stroke={nodeColor} strokeWidth={1.5}
                strokeDasharray="4 3" opacity={0.3} />
            )}
            <text textAnchor="middle" dominantBaseline="middle"
              fontSize={isCenter ? 18 : 14} style={{ userSelect: 'none' }}
              opacity={isOutside ? 0.25 : 1}>
              {CI_ICONS[n.ci_type || ''] || '📌'}
            </text>
            <text
              textAnchor="middle" y={r + 13} fontSize="10"
              fill={isCenter ? 'var(--accent)' : (isOutside ? 'var(--text-3)' : 'var(--text-1)')}
              fontWeight={isCenter ? 700 : 500} fontFamily="inherit"
              style={{ userSelect: 'none' }} opacity={isOutside ? 0.35 : 1}
            >
              {n.name && n.name.length > 16 ? n.name.slice(0, 15) + '…' : (n.name || n.id)}
            </text>
            {isHov && (
              <foreignObject x={r + 6} y={-r} width="170" height="92">
                <div
                  {...{ xmlns: 'http://www.w3.org/1999/xhtml' }}
                  style={{
                    background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
                    borderRadius: 8, padding: '6px 10px', fontSize: "var(--text-xs)",
                    color: 'var(--text-1)', boxShadow: '0 4px 16px rgba(0,0,0,.5)',
                    pointerEvents: 'none',
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: 3 }}>{n.name}</div>
                  <div style={{ color: 'var(--text-2)' }}>{n.ci_type} · {n.status}</div>
                  {n.hostname && <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{n.hostname}</div>}
                  {impactDist && impactDist[n.id] !== undefined && impactDist[n.id] <= impactRadius && (
                    <div style={{ marginTop: 3, color: IMPACT_COLORS[Math.min(impactDist[n.id], 3)], fontWeight: 600 }}>
                      {IMPACT_LABELS[Math.min(impactDist[n.id], 3)]}
                    </div>
                  )}
                  <div style={{ marginTop: 4, color: 'var(--text-3)', fontSize: "var(--text-2xs)" }}>
                    Click → drill-down &amp; fijar impacto
                  </div>
                </div>
              </foreignObject>
            )}
          </g>
        )
      })}
    </svg>
  )
}

// ─── 3D PLOTLY COMPONENT ─────────────────────────────────────────────────────

function Graph3D({ nodes, edges, impactDist, impactRadius, onNodeClick, onImpactSourceChange }: GraphViewProps) {
  const positions = useMemo(() => layout3D(nodes, edges), [nodes, edges])

  const getNodeColor = useCallback((n: GraphNode) => {
    if (impactDist) {
      const d = impactDist[n.id]
      if (d === undefined || d > impactRadius) return '#334155'
      return IMPACT_COLORS[Math.min(d, 3)]
    }
    return pickNodeColor(n)
  }, [impactDist, impactRadius])

  const edgeX: Array<number | null> = [], edgeY: Array<number | null> = [], edgeZ: Array<number | null> = []
  edges.forEach(e => {
    const sp = positions[e.source], tp = positions[e.target]
    if (!sp || !tp) return
    edgeX.push(sp.x, tp.x, null)
    edgeY.push(sp.y, tp.y, null)
    edgeZ.push(sp.z, tp.z, null)
  })

  const nodeTrace = {
    type: 'scatter3d',
    mode: 'markers+text',
    x: nodes.map(n => positions[n.id]?.x ?? 0),
    y: nodes.map(n => positions[n.id]?.y ?? 0),
    z: nodes.map(n => positions[n.id]?.z ?? 0),
    text: nodes.map(n => n.name && n.name.length > 13 ? n.name.slice(0, 12) + '…' : (n.name || n.id)),
    textposition: 'top center',
    textfont: { size: 9, color: '#cbd5e1' },
    customdata: nodes.map(n => n.id),
    marker: {
      size: nodes.map(n => n.is_center ? 14 : 9),
      color: nodes.map(n => getNodeColor(n)),
      opacity: nodes.map(n => {
        if (impactDist) {
          const d = impactDist[n.id]
          return (d === undefined || d > impactRadius) ? 0.2 : 1
        }
        return 0.9
      }),
      line: { color: '#1e293b', width: 1 },
      symbol: nodes.map(n => n.is_center ? 'diamond' : 'circle'),
    },
    hovertemplate: nodes.map(n => {
      const d = impactDist ? impactDist[n.id] : undefined
      const impactLine = (d !== undefined && d <= impactRadius)
        ? `<br><b>${IMPACT_LABELS[Math.min(d, 3)]}</b>`
        : ''
      return `<b>${n.name}</b><br>${n.ci_type} · ${n.status}${n.hostname ? '<br>' + n.hostname : ''}${impactLine}<extra></extra>`
    }),
    showlegend: false,
  }

  const edgeTrace = {
    type: 'scatter3d',
    mode: 'lines',
    x: edgeX, y: edgeY, z: edgeZ,
    line: { color: '#475569', width: 1.5 },
    hoverinfo: 'none',
    showlegend: false,
    opacity: 0.45,
  }

  const layout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    margin: { l: 0, r: 0, t: 0, b: 0 },
    scene: {
      bgcolor: '#0f172a',
      xaxis: { showgrid: false, zeroline: false, showticklabels: false, showspikes: false },
      yaxis: { showgrid: false, zeroline: false, showticklabels: false, showspikes: false },
      zaxis: { showgrid: false, zeroline: false, showticklabels: false, showspikes: false },
    },
    uirevision: 'topology3d',
  }

  return (
    <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
      <Plot
        data={[edgeTrace, nodeTrace]}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: 500 }}
        onClick={(event: { points?: Array<{ curveNumber: number; customdata: string }> }) => {
          if (!event.points?.length) return
          const pt = event.points[0]
          // curveNumber 1 = nodeTrace (edgeTrace is 0)
          if (pt.curveNumber === 1) {
            const nodeId = pt.customdata
            const node = nodes.find(n => n.id === nodeId)
            if (node) {
              onImpactSourceChange(nodeId)
              onNodeClick && onNodeClick(node)
            }
          }
        }}
      />
    </div>
  )
}

// ─── IMPACT LEGEND ───────────────────────────────────────────────────────────

function ImpactLegend({ impactRadius, sourceName }: { impactRadius: number; sourceName?: string }) {
  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
      fontSize: "var(--text-xs)", padding: '8px 2px',
    }}>
      {sourceName && (
        <span style={{ color: 'var(--text-2)', marginRight: 4 }}>
          Impacto de <strong style={{ color: IMPACT_COLORS[0] }}>{sourceName}</strong>:
        </span>
      )}
      {Array.from({ length: impactRadius + 1 }, (_, d) => (
        <span key={d} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: IMPACT_COLORS[d], display: 'inline-block', flexShrink: 0 }} />
          <span style={{ color: 'var(--text-2)' }}>{IMPACT_LABELS[d]}</span>
        </span>
      ))}
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#334155', display: 'inline-block', flexShrink: 0 }} />
        <span style={{ color: 'var(--text-3)' }}>Sin impacto / fuera del radio</span>
      </span>
    </div>
  )
}

// ─── MAIN EXPORT ─────────────────────────────────────────────────────────────

export default function CMDBTopologyGraph({ nodes: rawNodes = [], edges: rawEdges = [], onNodeClick, centerName }: {
  nodes?: RawNode[]
  edges?: RawEdge[]
  onNodeClick?: (node: GraphNode) => void
  centerName?: string
}) {
  const [hovered, setHovered] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState('2d')
  const [impactSource, setImpactSource] = useState<string | null>(null)
  const [impactRadius, setImpactRadius] = useState(2)

  const nodes = useMemo(() => rawNodes.map(normalizeNode), [rawNodes])
  const edges = useMemo(() => rawEdges.map(normalizeEdge), [rawEdges])

  const impactDist = useMemo(
    () => impactSource ? bfsDistances(nodes, edges, impactSource) : null,
    [impactSource, nodes, edges],
  )

  const impactSourceNode = nodes.find(n => n.id === impactSource)

  const handleImpactSource = useCallback((nodeId: string) => {
    setImpactSource(prev => prev === nodeId ? null : nodeId)
  }, [])

  if (!nodes.length) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
        <div style={{ fontSize: "var(--text-4xl)", marginBottom: 8 }}>🔭</div>
        Selecciona un CI para ver su topología de dependencias
      </div>
    )
  }

  return (
    <div>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', padding: '6px 0' }}>
        {/* 2D / 3D toggle */}
        <div style={{ display: 'flex', gap: 2, background: 'var(--surface-4)', padding: 2, borderRadius: 8 }}>
          {[['2d', '2D SVG'], ['3d', '3D Plotly']].map(([mode, label]) => (
            <button key={mode} onClick={() => setViewMode(mode)} style={tbBtn(viewMode === mode)}>{label}</button>
          ))}
        </div>

        {/* Impact radius buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 6 }}>
          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>
            Radio impacto:
          </span>
          {[1, 2, 3].map(r => (
            <button key={r} onClick={() => setImpactRadius(r)} style={tbBtn(impactRadius === r)}>{r}</button>
          ))}
        </div>

        {/* Clear impact */}
        {impactSource && (
          <button
            onClick={() => setImpactSource(null)}
            style={{
              padding: '4px 10px', borderRadius: 6, fontSize: "var(--text-xs)", cursor: 'pointer',
              border: '1px solid var(--danger)', background: 'transparent',
              color: 'var(--danger)', fontFamily: 'inherit',
            }}
          >
            ✕ Limpiar impacto
          </button>
        )}

        {centerName && (
          <span style={{ marginLeft: 'auto', fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
            Centro: <strong style={{ color: 'var(--accent)' }}>{centerName}</strong>
            {' · '}{nodes.length} nodos · {edges.length} aristas
          </span>
        )}
      </div>

      {/* Hint */}
      {!impactSource && (
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>
          💡 Haz clic en cualquier nodo para analizar su radio de impacto y abrir el panel de detalle
        </div>
      )}

      {/* Graph */}
      {viewMode === '2d' ? (
        <Graph2D
          nodes={nodes} edges={edges}
          impactDist={impactDist} impactRadius={impactRadius}
          onNodeClick={onNodeClick} onImpactSourceChange={handleImpactSource}
          hovered={hovered} setHovered={setHovered}
        />
      ) : (
        <Graph3D
          nodes={nodes} edges={edges}
          impactDist={impactDist} impactRadius={impactRadius}
          onNodeClick={onNodeClick} onImpactSourceChange={handleImpactSource}
        />
      )}

      {/* Impact legend */}
      {impactDist && (
        <ImpactLegend impactRadius={impactRadius} sourceName={impactSourceNode?.name} />
      )}
    </div>
  )
}
