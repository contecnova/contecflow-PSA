/**
 * Cmdb3dGraph.jsx — CMDB dependency graph (D3 force-directed) + blast radius lookup.
 * Connects to /api/v1/sd/cmdb/3d-graph and /api/v1/sd/cmdb/blast-radius/*.
 *
 * 16-11-2026 (pasada de diseño): capas, título, aviso de error y «profundidad»
 * traducidos (antes fijos en castellano o con claves `sd.cmdb3d.*` inexistentes,
 * que en inglés y chino salían en castellano); CMDB vacía con <EmptyState>;
 * campos con `ds-input`; sin «Blast Radius» en el texto.
 */
import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as d3 from 'd3'
import { cmdb3dApi } from '../../services/api'
import type { SdGrafo3d, SdNodo3d, SdRadioDeImpacto } from '../../services/api/tipos-sd'
import { useAppT } from '../../i18n/AppLangContext'
import { Network } from 'lucide-react'
import { Card, Button, EmptyState, Spinner } from '../ui'
import './Cmdb3dGraph.css'

/** Nodo del grafo (`SdNodo3d`) con el estado que añade la simulación de d3. */
type CiNode = SdNodo3d & d3.SimulationNodeDatum
type CiEdge = d3.SimulationLinkDatum<CiNode> & { type: string }

const LAYER_COLORS = [
  'var(--accent)',
  'var(--success)',
  'var(--warning)',
  'var(--danger)',
  'var(--purple)',
  'var(--orange)',
]
/** Claves de `cmdb3dgraph` para cada capa, en el orden de LAYER_COLORS. */
const LAYER_KEYS = ['capa_aplicacion', 'capa_infraestructura', 'capa_red', 'capa_base_de_datos', 'capa_servicio', 'capa_externo']


export default function Cmdb3dGraph({ className = '' }: { className?: string }) {
  const t = useAppT()
  const svgRef = useRef<SVGSVGElement | null>(null)
  // TODO type: d3.Simulation generics — keep loose to avoid widening every callsite
  const simulationRef = useRef<d3.Simulation<CiNode, CiEdge> | null>(null)
  const [blastCiId, setBlastCiId] = useState<string>('')
  const [blastResult, setBlastResult] = useState<SdRadioDeImpacto | null>(null)
  const [blastError, setBlastError] = useState<string | null>(null)
  const [maxNodes, setMaxNodes] = useState<number>(80)

  const { data, isLoading } = useQuery({
    queryKey: ['cmdb-3d-graph', maxNodes],
    queryFn: () => cmdb3dApi.getGraph({ max_nodes: maxNodes }).then(r => r.data),
  })

  const handleBlastRadius = async () => {
    if (!blastCiId.trim()) return
    try {
      const res = await cmdb3dApi.blastRadius(encodeURIComponent(blastCiId.trim()))
      setBlastResult(res.data)
      setBlastError(null)
    } catch {
      setBlastResult(null)
      setBlastError(t('cmdb3dgraph.error_radio'))
    }
  }

  const renderGraph = useCallback((graphData: SdGrafo3d | undefined, width?: number) => {
    if (!graphData || !svgRef.current) return
    const nodes: CiNode[] = graphData.nodes.map(n => ({ ...n }))
    const links: CiEdge[] = graphData.edges.map(e => ({ ...e }))
    if (!nodes.length) return

    if (simulationRef.current) simulationRef.current.stop()

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const w = width || svgRef.current.getBoundingClientRect().width || svgRef.current.clientWidth || 700
    const h = 420

    const g = svg.append('g')
    svg.call(
      // El genérico dice sobre qué elemento actúa el zoom. Sin `@types/d3`
      // instalado esto era `any` y compilaba igual; con los tipos puestos hay
      // que decirlo, y decirlo es mejor: `svg.call(...)` sólo acepta un
      // comportamiento declarado sobre `SVGSVGElement`.
      d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.2, 5]).on('zoom', (event) => {
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
      // Los genéricos hacen que `d` sea un `CiNode` y no el
      // `SimulationNodeDatum` genérico, que no tiene `id`. Los tipos ya
      // estaban declarados arriba; lo que faltaba era usarlos aquí.
      .force('link', d3.forceLink<CiNode, CiEdge>(links).id(d => d.id).distance(80))
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
      // Igual que el zoom: el arrastre se declara sobre el elemento y el dato
      // que de verdad lleva la selección.
      .call(d3.drag<SVGGElement, CiNode>()
        .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )

    nodeG.append('circle')
      .attr('r', 10)
      .attr('fill', d => LAYER_COLORS[d.layer % LAYER_COLORS.length])
      .attr('stroke', 'var(--surface-2)')
      .attr('stroke-width', 2)

    nodeG.append('text')
      .attr('dy', 22)
      .attr('text-anchor', 'middle')
      .attr('font-size', 10)
      .attr('fill', 'var(--text-2)')
      .attr('font-family', 'var(--font-sans)')
      .text(d => (d.name || d.id).slice(0, 18))

    simulation.on('tick', () => {
      const getX = (nodeLike: CiEdge['source']) => (typeof nodeLike === 'object' ? (nodeLike.x ?? 0) : 0)
      const getY = (nodeLike: CiEdge['source']) => (typeof nodeLike === 'object' ? (nodeLike.y ?? 0) : 0)
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
    <Card className={`${className} cmdb3dgr-sx1`}>
      <div className="cmdb3d-row-1">
        <h2 className="cmdb3d-box-1">
          {t('cmdb3dgraph.titulo')}
        </h2>
        <div className="u-row-center-8">
          <span className="u-text3-xs">{t('cmdb3dgraph.max_nodos')}</span>
          <select
            aria-label={t('cmdb3dgraph.max_nodos')}
            value={maxNodes}
            onChange={e => setMaxNodes(Number(e.target.value))}
            className="ds-input cmdb3d-select"
          >
            {[50, 80, 120, 200].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      <div className="cmdb3d-row-2">
        {LAYER_KEYS.map((clave, i) => (
          <span key={clave} className="cmdb3d-row-3">
            <span className="cmdb3d-box-8 cmdb3d-graph-e1" aria-hidden style={{ '--cmdb3d-graph-background': LAYER_COLORS[i] } as CSSProperties} />
            {t(`cmdb3dgraph.${clave}`)}
          </span>
        ))}
      </div>

      {isLoading ? (
        <div className="cmdb3d-row-4">
          <Spinner />
        </div>
      ) : data && !data.nodes.length ? (
        // El backend ya no inventa CIs de demostración: un CMDB vacío se dice.
        <EmptyState icon={<Network size={28} />} title={t('cmdb3dgraph.vacio_titulo')} description={t('cmdb3dgraph.vacio_desc')} />
      ) : (
        <div className="cmdb3d-box-2">
          <svg
            ref={svgRef}
            className="cmdb3d-box-3"
            role="img"
            aria-label={t('cmdb3dgraph.aria')}
          />
        </div>
      )}

      <div className="cmdb3d-box-4">
        <label className="cmdb3d-fieldlabel" htmlFor="cmdb3d-ci">{t('cmdb3dgraph.radio_impacto')}</label>
        <div className="cmdb3d-row-6">
          <input id="cmdb3d-ci"
            type="text"
            placeholder={t('cmdb3dgraph.ci_id_ej_ci_app_server_01')}
            value={blastCiId}
            onChange={e => setBlastCiId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleBlastRadius()}
            className="ds-input cmdb3d-ci"
          />
          <Button onClick={handleBlastRadius} disabled={!blastCiId.trim()}>
            {t('cmdb3dgraph.calcular')}
          </Button>
        </div>

        {blastError && (
          <div className="cmdb3d-box-9" role="alert">{blastError}</div>
        )}
        {blastResult && (() => {
          const list = blastResult.impacted_cis
          const total = blastResult.impacted_count
          const ciName = blastResult.ci_name || blastResult.ci_id
          return (
            <div className="cmdb3d-box-5">
              <div className="cmdb3d-sp-1">
                <strong className="u-text1">{ciName}</strong>
                {` ${t('cmdb3dgraph.afecta_a')} `}
                <strong className={`${total > 0 ? 'cmdb3d-graph-m2' : 'cmdb3d-graph-m3'}`}>{total}</strong>
                {` ${t('cmdb3dgraph.ci_s_dependientes')}`}
              </div>
              {list.length === 0 ? (
                <div className="u-text2-xs">
                  {t('cmdb3dgraph.ningun_ci_depende_de_este_fallo_aislado')}
                </div>
              ) : (
                <div className="u-wrap-6">
                  {list.slice(0, 20).map((ci, idx) => {
                    const depth = ci.impact_depth
                    return (
                      <span key={ci.id || idx} title={t('cmdb3dgraph.profundidad', { n: depth })} className="cmdb3d-box-6">{ci.name || ci.id}{depth > 0 ? ` · L${depth}` : ''}</span>
                    )
                  })}
                  {list.length > 20 && (
                    <span className="cmdb3d-box-7">
                      +{list.length - 20} {t('cmdb3dgraph.mas')}
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
