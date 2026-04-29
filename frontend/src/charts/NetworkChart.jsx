/**
 * NetworkChart — D3 force-directed graph.
 * Renders nodes as circles connected by edges with force simulation.
 * Supports dark mode via useChartTheme.
 */
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { useChartTheme } from './useChartTheme'

const DEFAULT_NODES = [
  { id: 'Router-Core', group: 1 },
  { id: 'Server-A', group: 2 },
  { id: 'Server-B', group: 2 },
  { id: 'DB-Primary', group: 3 },
  { id: 'DB-Replica', group: 3 },
  { id: 'LB-01', group: 1 },
  { id: 'Client-01', group: 4 },
  { id: 'Client-02', group: 4 },
]

const DEFAULT_LINKS = [
  { source: 'Router-Core', target: 'LB-01', value: 3 },
  { source: 'LB-01', target: 'Server-A', value: 2 },
  { source: 'LB-01', target: 'Server-B', value: 2 },
  { source: 'Server-A', target: 'DB-Primary', value: 1 },
  { source: 'Server-B', target: 'DB-Primary', value: 1 },
  { source: 'DB-Primary', target: 'DB-Replica', value: 1 },
  { source: 'Router-Core', target: 'Client-01', value: 1 },
  { source: 'Router-Core', target: 'Client-02', value: 1 },
]

const GROUP_COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#10b981', '#ef4444', '#a855f7']

export default function NetworkChart({ data, width = 900, height = 420 }) {
  const svgRef = useRef(null)
  const { tokens, dark } = useChartTheme()

  const nodes = (data?.nodes || DEFAULT_NODES).map((n) => ({ ...n }))
  const links = (data?.links || DEFAULT_LINKS).map((l) => ({ ...l }))

  useEffect(() => {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const simulation = d3
      .forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d) => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(22))

    const g = svg.append('g')

    // Zoom
    svg.call(
      d3.zoom().scaleExtent([0.3, 4]).on('zoom', (event) => {
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
      .attr('stroke-width', (d) => Math.sqrt(d.value || 1))
      .attr('marker-end', 'url(#arrow)')

    const node = g
      .append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .call(
        d3
          .drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          })
      )

    node
      .append('circle')
      .attr('r', 14)
      .attr('fill', (d) => GROUP_COLORS[(d.group || 1) - 1] || GROUP_COLORS[0])
      .attr('stroke', dark ? '#ffffff30' : '#00000020')
      .attr('stroke-width', 1.5)

    node
      .append('text')
      .text((d) => d.id)
      .attr('x', 18)
      .attr('dy', '0.35em')
      .attr('fill', tokens.text1)
      .attr('font-size', '11px')
      .attr('font-family', 'system-ui, sans-serif')

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
  }, [nodes.length, links.length, tokens, dark, width, height])

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
