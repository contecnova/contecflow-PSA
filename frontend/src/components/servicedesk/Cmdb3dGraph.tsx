/**
 * Cmdb3dGraph.jsx — CMDB dependency graph (D3 force-directed) + blast radius lookup.
 * Connects to /api/v1/sd/cmdb/3d-graph and /api/v1/sd/cmdb/blast-radius/*.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as d3 from 'd3'
import { cmdb3dApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Card, Button, Spinner } from '../ui'

// TODO type: cmdb3dApi payloads — needs shared types
interface CiNode extends d3.SimulationNodeDatum {
  id: string
  label?: string
  name?: string
  layer?: number
  z?: number
  type?: string
  [k: string]: unknown
}

interface CiEdge extends d3.SimulationLinkDatum<CiNode> {
  source: string | CiNode
  target: string | CiNode
  type?: string
  [k: string]: unknown
}

interface GraphData {
  nodes?: CiNode[]
  edges?: CiEdge[]
}

interface BlastResult {
  error?: string
  ci_name?: string
  ci_id?: string
  impacted_cis?: Array<string | { id: string; name?: string; impact_depth?: number }>
  impacted_count?: number
  affected_cis?: string[]
  affected_count?: number
  [k: string]: unknown
}

const LAYER_COLORS = [
  'var(--accent)',
  'var(--success)',
  'var(--warning)',
  'var(--danger)',
  'var(--purple)',
  'var(--orange)',
]
const LAYER_LABELS = ['Aplicación', 'Infraestructura', 'Red', 'Base de datos', 'Servicio', 'Externo']

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 4,
}
const inputBase: React.CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}

export default function Cmdb3dGraph({ className = '' }: { className?: string }) {
  const t = useAppT()
  const svgRef = useRef<SVGSVGElement | null>(null)
  // TODO type: d3.Simulation generics — keep loose to avoid widening every callsite
  const simulationRef = useRef<d3.Simulation<CiNode, CiEdge> | null>(null)
  const [blastCiId, setBlastCiId] = useState<string>('')
  const [blastResult, setBlastResult] = useState<BlastResult | null>(null)
  const [maxNodes, setMaxNodes] = useState<number>(80)

  const { data, isLoading } = useQuery<GraphData>({
    queryKey: ['cmdb-3d-graph', maxNodes],
    queryFn: () => cmdb3dApi.getGraph({ max_nodes: maxNodes }).then(r => r.data),
  })

  const handleBlastRadius = async () => {
    if (!blastCiId.trim()) return
    try {
      const res = await cmdb3dApi.blastRadius(encodeURIComponent(blastCiId.trim()))
      setBlastResult(res.data)
    } catch {
      setBlastResult({ error: 'CI no encontrado o error al calcular' })
    }
  }

  const renderGraph = useCallback((graphData: GraphData | undefined, width?: number) => {
    if (!graphData || !svgRef.current) return
    const nodes = (graphData.nodes ?? []).map(n => ({ ...n }))
    const links = (graphData.edges ?? []).map(e => ({ ...e }))
    if (!nodes.length) return

    if (simulationRef.current) simulationRef.current.stop()

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const w = width || svgRef.current.getBoundingClientRect().width || svgRef.current.clientWidth || 700
    const h = 420

    const g = svg.append('g')
    svg.call(
      d3.zoom().scaleExtent([0.2, 5]).on('zoom', (event) => {
        g.attr('transform', event.transform)
      })
    )

    svg.append('defs').append('marker')
      .attr('id', 'cmdb-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 18)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('fill', 'var(--text-3)')
      .attr('d', 'M0,-5L10,0L0,5')

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide(22))

    simulationRef.current = simulation

    const link = g.append('g').selectAll('line')
      .data(links).enter().append('line')
      .attr('stroke', 'var(--text-3)')
      .attr('stroke-opacity', 0.5)
      .attr('stroke-width', 1.2)
      .attr('marker-end', 'url(#cmdb-arrow)')

    const nodeG = g.append('g').selectAll('g')
      .data(nodes).enter().append('g')
      .call(d3.drag()
        .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )

    nodeG.append('circle')
      .attr('r', 10)
      .attr('fill', d => LAYER_COLORS[(d.layer ?? d.z ?? 0) % LAYER_COLORS.length])
      .attr('stroke', 'var(--surface-2)')
      .attr('stroke-width', 2)

    nodeG.append('text')
      .attr('dy', 22)
      .attr('text-anchor', 'middle')
      .attr('font-size', 10)
      .attr('fill', 'var(--text-2)')
      .attr('font-family', 'var(--font-sans)')
      .text(d => (d.name ?? d.label ?? d.id ?? '').slice(0, 18))

    simulation.on('tick', () => {
      const getX = (nodeLike: string | CiNode) => (typeof nodeLike === 'object' ? (nodeLike.x ?? 0) : 0)
      const getY = (nodeLike: string | CiNode) => (typeof nodeLike === 'object' ? (nodeLike.y ?? 0) : 0)
      link
        .attr('x1', d => getX(d.source))
        .attr('y1', d => getY(d.source))
        .attr('x2', d => getX(d.target))
        .attr('y2', d => getY(d.target))
      nodeG.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })
  }, [])

  useEffect(() => {
    if (!data || !svgRef.current) return
    // Use rAF to ensure the SVG has been painted and has real dimensions
    const raf = requestAnimationFrame(() => {
      renderGraph(data, svgRef.current?.getBoundingClientRect().width)
    })
    return () => {
      cancelAnimationFrame(raf)
      if (simulationRef.current) simulationRef.current.stop()
    }
  }, [data, renderGraph])

  return (
    <Card className={className} style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
          {t('sd.cmdb3d.title', 'Mapa 3D de Dependencias CMDB')}
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Máx. nodos</span>
          <select
            value={maxNodes}
            onChange={e => setMaxNodes(Number(e.target.value))}
            style={{ ...inputBase, width: 'auto', padding: '6px 10px', fontSize: 'var(--text-xs)' }}
          >
            {[50, 80, 120, 200].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginBottom: 14 }}>
        {LAYER_LABELS.map((lbl, i) => (
          <span key={lbl} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
            <span aria-hidden style={{ width: 9, height: 9, borderRadius: '50%', background: LAYER_COLORS[i] }} />
            {lbl}
          </span>
        ))}
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 420 }}>
          <Spinner />
        </div>
      ) : (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          <svg
            ref={svgRef}
            style={{ width: '100%', height: 420, cursor: 'grab', display: 'block' }}
            role="img"
            aria-label={t('sd.cmdb3d.aria', 'Grafo de dependencias CMDB')}
          />
        </div>
      )}

      <div style={{
        marginTop: 18,
        background: 'var(--surface-3)',
        border: '1px solid var(--surface-4)',
        borderRadius: 10,
        padding: '14px 16px',
      }}>
        <div style={fieldLabel}>{t('sd.cmdb3d.blast_radius', 'Radio de impacto (Blast Radius)')}</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
          <input
            type="text"
            placeholder="CI ID (ej: ci-app-server-01)"
            value={blastCiId}
            onChange={e => setBlastCiId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleBlastRadius()}
            style={{ ...inputBase, flex: 1 }}
          />
          <Button onClick={handleBlastRadius} disabled={!blastCiId.trim()}>
            {t('sd.cmdb3d.calculate', 'Calcular')}
          </Button>
        </div>

        {blastResult && (() => {
          if (blastResult.error) {
            return (
              <div style={{
                marginTop: 12,
                color: 'var(--danger)',
                background: 'var(--danger-bg, rgba(239,68,68,0.08))',
                border: '1px solid var(--danger-border, rgba(239,68,68,0.25))',
                padding: '8px 12px', borderRadius: 8, fontSize: 'var(--text-sm)',
              }}>{blastResult.error}</div>
            )
          }
          // Soporta forma actual del backend (impacted_*) y posibles aliases (affected_*)
          const list = blastResult.impacted_cis ?? blastResult.affected_cis ?? []
          const total = blastResult.impacted_count ?? blastResult.affected_count ?? list.length
          const ciName = blastResult.ci_name || blastResult.ci_id
          return (
            <div style={{ marginTop: 12, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
              <div style={{ marginBottom: 8 }}>
                <strong style={{ color: 'var(--text-1)' }}>{ciName}</strong>
                {' afecta a '}
                <strong style={{ color: total > 0 ? 'var(--danger)' : 'var(--success)' }}>{total}</strong>
                {' CI(s) dependientes'}
              </div>
              {list.length === 0 ? (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                  Ningún CI depende de este — fallo aislado.
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {list.slice(0, 20).map((ci, idx) => {
                    const id = typeof ci === 'string' ? ci : ci.id
                    const label = typeof ci === 'string' ? ci : (ci.name || ci.id)
                    const depth = typeof ci === 'object' ? ci.impact_depth : undefined
                    return (
                      <span key={id || idx} title={depth != null ? `Profundidad: ${depth}` : undefined} style={{
                        fontSize: 'var(--text-xs)',
                        background: 'var(--surface-4)',
                        color: 'var(--text-2)',
                        borderRadius: 'var(--radius-full, 999px)',
                        padding: '2px 9px',
                      }}>{label}{depth != null && depth > 0 ? ` · L${depth}` : ''}</span>
                    )
                  })}
                  {list.length > 20 && (
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', alignSelf: 'center' }}>
                      +{list.length - 20} más
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })()}
      </div>
    </Card>
  )
}
