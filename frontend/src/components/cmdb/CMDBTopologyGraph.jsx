/**
 * CMDBTopologyGraph — SVG force-free radial topology viewer.
 *
 * Props:
 *  - nodes: [{id, name, ci_type, status, is_center}]
 *  - edges: [{source, target, rel_type}]
 *  - onNodeClick: (node) => void
 *  - centerName: string
 */
import { useMemo, useState } from 'react'

const CI_ICONS = {
  server:'🖥️', application:'📱', database:'🗄️', network:'🌐',
  service:'⚙️', container:'📦', cloud:'☁️', endpoint:'💻',
  storage:'💾', other:'📌',
}

const STATUS_COLORS = {
  active: '#22c55e',
  maintenance: '#f59e0b',
  decommissioned: '#ef4444',
}

const REL_COLORS = {
  depends_on: '#6366f1',
  runs_on: '#0ea5e9',
  connects_to: '#8b5cf6',
  hosts: '#10b981',
  monitors: '#f59e0b',
  backs_up: '#64748b',
}

function layoutNodes(nodes, width, height) {
  const center = nodes.find(n => n.is_center)
  const rest = nodes.filter(n => !n.is_center)

  const cx = width / 2
  const cy = height / 2
  const r = Math.min(width, height) * 0.35

  const positions = {}
  if (center) positions[center.id] = { x: cx, y: cy }

  rest.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / rest.length - Math.PI / 2
    positions[n.id] = {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    }
  })

  return positions
}

export default function CMDBTopologyGraph({ nodes = [], edges = [], onNodeClick, centerName }) {
  const W = 680
  const H = 480
  const [hovered, setHovered] = useState(null)

  const positions = useMemo(() => layoutNodes(nodes, W, H), [nodes])

  if (!nodes.length) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-2)', fontSize: 13 }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>🔭</div>
        Selecciona un CI para ver su topología de dependencias
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      {centerName && (
        <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>
          Topología centrada en <strong style={{ color: 'var(--accent)' }}>{centerName}</strong>
          {' — '}{nodes.length} nodos · {edges.length} relaciones
        </div>
      )}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', maxHeight: 480, borderRadius: 12, background: 'var(--surface-3)', border: '1px solid var(--surface-4)' }}
      >
        {/* Marker arrowhead */}
        <defs>
          {Object.entries(REL_COLORS).map(([rel, color]) => (
            <marker
              key={rel}
              id={`arrow-${rel}`}
              markerWidth="8" markerHeight="8"
              refX="16" refY="3"
              orient="auto"
            >
              <path d="M0,0 L0,6 L8,3 z" fill={color} opacity={0.7} />
            </marker>
          ))}
        </defs>

        {/* Edges */}
        {edges.map((e, i) => {
          const sp = positions[e.source]
          const tp = positions[e.target]
          if (!sp || !tp) return null
          const color = REL_COLORS[e.rel_type] || '#64748b'
          const isHov = hovered === e.source || hovered === e.target
          return (
            <g key={i}>
              <line
                x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                stroke={color}
                strokeWidth={isHov ? 2.5 : 1.5}
                strokeOpacity={isHov ? 0.9 : 0.45}
                markerEnd={`url(#arrow-${e.rel_type || 'depends_on'})`}
              />
              {/* Relation label on midpoint */}
              {isHov && (
                <text
                  x={(sp.x + tp.x) / 2}
                  y={(sp.y + tp.y) / 2 - 5}
                  textAnchor="middle"
                  fill={color}
                  fontSize="10"
                  fontFamily="inherit"
                  opacity={0.9}
                >
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
          const sc = STATUS_COLORS[n.status] || STATUS_COLORS.active
          const isCenter = !!n.is_center
          const isHov = hovered === n.id
          const r = isCenter ? 30 : 22
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onNodeClick && onNodeClick(n)}
            >
              <circle
                r={r}
                fill={isCenter ? 'var(--accent)' : 'var(--surface-2)'}
                stroke={isCenter ? 'var(--accent)' : sc}
                strokeWidth={isCenter ? 0 : (isHov ? 2.5 : 1.5)}
                opacity={isHov ? 1 : 0.9}
              />
              {/* Status ring */}
              {!isCenter && (
                <circle r={r + 4} fill="none" stroke={sc} strokeWidth={1.5} strokeDasharray="4 3" opacity={0.4} />
              )}
              <text textAnchor="middle" dominantBaseline="middle" fontSize={isCenter ? 18 : 14} style={{ userSelect: 'none' }}>
                {CI_ICONS[n.ci_type] || '📌'}
              </text>
              <text
                textAnchor="middle"
                y={r + 13}
                fontSize="10"
                fill={isCenter ? 'var(--accent)' : 'var(--text-1)'}
                fontWeight={isCenter ? 700 : 500}
                fontFamily="inherit"
                style={{ userSelect: 'none' }}
              >
                {n.name && n.name.length > 16 ? n.name.slice(0, 15) + '…' : (n.name || n.id)}
              </text>
              {/* Hover card */}
              {isHov && (
                <foreignObject x={r + 6} y={-(r)} width="160" height="70">
                  <div
                    xmlns="http://www.w3.org/1999/xhtml"
                    style={{
                      background: 'var(--surface-2)',
                      border: '1px solid var(--surface-4)',
                      borderRadius: 8,
                      padding: '6px 10px',
                      fontSize: 11,
                      color: 'var(--text-1)',
                      boxShadow: '0 4px 16px rgba(0,0,0,.4)',
                      pointerEvents: 'none',
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: 3 }}>{n.name}</div>
                    <div style={{ color: 'var(--text-2)' }}>{n.ci_type} · {n.status}</div>
                    {n.hostname && <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{n.hostname}</div>}
                  </div>
                </foreignObject>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
        {Object.entries(REL_COLORS).map(([rel, color]) => (
          <div key={rel} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-2)' }}>
            <div style={{ width: 24, height: 2, background: color, borderRadius: 1 }} />
            {rel.replace(/_/g, ' ')}
          </div>
        ))}
      </div>
    </div>
  )
}
