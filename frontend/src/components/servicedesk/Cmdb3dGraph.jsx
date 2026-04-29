/**
 * Cmdb3dGraph.jsx — CMDB 3D Network graph using D3 force simulation.
 * Connects to /api/v1/sd/cmdb/3d-graph and /api/v1/sd/cmdb/blast-radius/* endpoints.
 * 
 * Note: Renders as a 2D force-directed graph with Z-coordinate encoded as color/layer.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as d3 from 'd3'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'

const LAYER_COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#f87171', '#a78bfa', '#fb923c']

export default function Cmdb3dGraph({ className = '' }) {
  const t = useAppT()
  const { dark } = useChartTheme()
  const svgRef = useRef(null)
  const [blastCiId, setBlastCiId] = useState('')
  const [blastResult, setBlastResult] = useState(null)
  const [maxNodes, setMaxNodes] = useState(80)

  const { data, isLoading } = useQuery({
    queryKey: ['cmdb-3d-graph', maxNodes],
    queryFn: () => api.get('/sd/cmdb/3d-graph', { params: { max_nodes: maxNodes } }).then(r => r.data),
  })

  const handleBlastRadius = async () => {
    if (!blastCiId.trim()) return
    try {
      const res = await api.get(`/sd/cmdb/blast-radius/${encodeURIComponent(blastCiId.trim())}`)
      setBlastResult(res.data)
    } catch {
      setBlastResult({ error: 'CI no encontrado o error al calcular' })
    }
  }

  useEffect(() => {
    if (!data || !svgRef.current) return
    const nodes = (data.nodes ?? []).map(n => ({ ...n }))
    const links = (data.edges ?? []).map(e => ({ ...e }))
    if (!nodes.length) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const w = svgRef.current.clientWidth || 700
    const h = 420

    const g = svg.append('g')
    svg.call(
      d3.zoom().scaleExtent([0.2, 5]).on('zoom', (event) => {
        g.attr('transform', event.transform)
      })
    )

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id', 'cmdb-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 18)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('fill', '#6b7280')
      .attr('d', 'M0,-5L10,0L0,5')

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide(22))

    const link = g.append('g').selectAll('line')
      .data(links).enter().append('line')
      .attr('stroke', '#6b7280')
      .attr('stroke-opacity', 0.6)
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
      .attr('stroke', dark ? '#1f2937' : '#fff')
      .attr('stroke-width', 2)

    nodeG.append('text')
      .attr('dy', 20)
      .attr('text-anchor', 'middle')
      .attr('font-size', 9)
      .attr('fill', dark ? '#d1d5db' : '#374151')
      .text(d => (d.label ?? d.id ?? '').slice(0, 16))

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      nodeG.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
  }, [data, dark])

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`

  return (
    <div className={`${cardCls} ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold">{t('sd.cmdb3d.title', 'Mapa 3D de Dependencias CMDB')}</h2>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Max nodes:</label>
          <select
            value={maxNodes}
            onChange={e => setMaxNodes(Number(e.target.value))}
            className={`rounded border px-2 py-1 text-xs ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          >
            {[50, 80, 120, 200].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      {/* Layer legend */}
      <div className="flex flex-wrap gap-2 mb-3">
        {['Aplicación', 'Infraestructura', 'Red', 'Base de datos', 'Servicio', 'Externo'].map((lbl, i) => (
          <span key={i} className="flex items-center gap-1 text-xs">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: LAYER_COLORS[i] }} />
            {lbl}
          </span>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-96 text-gray-400">
          {t('sd.cmdb3d.loading', 'Cargando grafo...')}
        </div>
      ) : (
        <svg
          ref={svgRef}
          className="w-full"
          style={{ height: 420, cursor: 'grab' }}
          role="img"
          aria-label={t('sd.cmdb3d.aria', 'Grafo de dependencias CMDB')}
        />
      )}

      {/* Blast radius */}
      <div className={`mt-4 rounded-lg border p-4 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
        <p className="text-sm font-medium mb-2">{t('sd.cmdb3d.blast_radius', 'Radio de impacto (Blast Radius)')}</p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="CI ID (ej: ci-app-server-01)"
            value={blastCiId}
            onChange={e => setBlastCiId(e.target.value)}
            className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
          />
          <button
            onClick={handleBlastRadius}
            className="px-4 py-1.5 rounded bg-red-600 text-white text-sm hover:bg-red-700"
          >
            {t('sd.cmdb3d.calculate', 'Calcular')}
          </button>
        </div>
        {blastResult && (
          <div className="mt-2 text-sm">
            {blastResult.error ? (
              <p className="text-red-500">{blastResult.error}</p>
            ) : (
              <div>
                <p><strong>{blastResult.ci_id}</strong> afecta a <strong>{blastResult.affected_count ?? blastResult.affected_cis?.length ?? 0}</strong> CIs</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(blastResult.affected_cis ?? []).slice(0, 20).map(cid => (
                    <span key={cid} className={`text-xs px-2 py-0.5 rounded-full ${dark ? 'bg-gray-700' : 'bg-gray-200'}`}>{cid}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
