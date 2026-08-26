/**
 * NetworkChart — D3 force-directed graph.
 * Renders nodes as circles connected by edges with force simulation.
 * Supports dark mode via useChartTheme.
 */
import { useEffect, useRef } from 'react'
// TODO type: d3 ESM types are partial; treat selections as any internally.
import * as d3 from 'd3'
import { useChartTheme } from './useChartTheme'

export interface NetworkNode {
  id: string
  group?: number
  // d3 simulation attaches x/y/fx/fy at runtime
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

export interface NetworkLink {
  source: string | NetworkNode
  target: string | NetworkNode
  value?: number
}

export interface NetworkChartData {
  nodes?: NetworkNode[]
  links?: NetworkLink[]
}

export interface NetworkChartProps {
  data?: NetworkChartData
  width?: number
  height?: number
}

const DEFAULT_NODES: NetworkNode[] = [
  { id: 'Router-Core', group: 1 },
  { id: 'Server-A', group: 2 },
  { id: 'Server-B', group: 2 },
  { id: 'DB-Primary', group: 3 },
  { id: 'DB-Replica', group: 3 },
  { id: 'LB-01', group: 1 },
  { id: 'Client-01', group: 4 },
  { id: 'Client-02', group: 4 },
]

const DEFAULT_LINKS: NetworkLink[] = [
  { source: 'Router-Core', target: 'LB-01', value: 3 },
  { source: 'LB-01', target: 'Server-A', value: 2 },
  { source: 'LB-01', target: 'Server-B', value: 2 },
  { source: 'Server-A', target: 'DB-Primary', value: 1 },
  { source: 'Server-B', target: 'DB-Primary', value: 1 },
  { source: 'DB-Primary', target: 'DB-Replica', value: 1 },
  { source: 'Router-Core', target: 'Client-01', value: 1 },
  { source: 'Router-Core', target: 'Client-02', value: 1 },
]

const GROUP_COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#34d399', '#f87171', '#a855f7']

export default function NetworkChart({ data, width = 900, height = 420 }: NetworkChartProps) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const { tokens, dark } = useChartTheme()

  const nodes: NetworkNode[] = (data?.nodes || DEFAULT_NODES).map((n) => ({ ...n }))
  const links: NetworkLink[] = (data?.links || DEFAULT_LINKS).map((l) => ({ ...l }))

  useEffect(() => {
    // d3 selection typing is complex; treat as any inside the effect.
     
    const svg = d3.select(svgRef.current as unknown as Element) as any
    svg.selectAll('*').remove()

    const simulation = (d3 as any)
      .forceSimulation(nodes)
      .force('link', (d3 as any).forceLink(links).id((d: NetworkNode) => d.id).distance(80))
      .force('charge', (d3 as any).forceManyBody().strength(-200))
      .force('center', (d3 as any).forceCenter(width / 2, height / 2))
      .force('collision', (d3 as any).forceCollide(22))

    const g = svg.append('g')

    // Zoom
    svg.call(
      (d3 as any).zoom().scaleExtent([0.3, 4]).on('zoom', (event: any) => {
        g.attr('transform', event.transform)
      })
    )

    // Arrow marker
    svg
      .append('defs')
      .append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', tokens.text3)

    const link = g
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', tokens.text3)
      .attr('stroke-opacity', 0.5)
      .attr('stroke-width', (d: NetworkLink) => Math.sqrt(d.value || 1))
      .attr('marker-end', 'url(#arrow)')

    const node = g
      .append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .call(
        (d3 as any)
          .drag()
          .on('start', (event: any, d: NetworkNode) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event: any, d: NetworkNode) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event: any, d: NetworkNode) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          })
      )

    node
      .append('circle')
      .attr('r', 14)
      .attr('fill', (d: NetworkNode) => GROUP_COLORS[(d.group || 1) - 1] || GROUP_COLORS[0])
      .attr('stroke', dark ? '#ffffff30' : '#00000020')
      .attr('stroke-width', 1.5)

    node
      .append('text')
      .text((d: NetworkNode) => d.id)
      .attr('x', 18)
      .attr('dy', '0.35em')
      .attr('fill', tokens.text1)
      .attr('font-size', '11px')
      .attr('font-family', 'system-ui, sans-serif')

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)

      node.attr('transform', (d: NetworkNode) => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
     
  }, [nodes, links, tokens, dark, width, height])

  return (
    <div role="img" aria-label="Network graph chart">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ background: 'transparent', cursor: 'grab', overflow: 'hidden', borderRadius: 8 }}
      />
    </div>
  )
}
