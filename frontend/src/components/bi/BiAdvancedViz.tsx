import React, { useState } from 'react'
import DynamicChart from '../../charts/DynamicChart'
import useMediaQuery from '../../hooks/useMediaQuery'

const CHART_TYPES = [
  { key: 'sankey', label: 'Sankey (D3)' },
  { key: 'treemap', label: 'Treemap (D3)' },
  { key: 'sunburst', label: 'Sunburst (D3)' },
  { key: 'dendrogram', label: 'Dendrogram (D3)' },
  { key: 'gauge', label: 'Gauge (ECharts)' },
  { key: 'heatmap', label: 'Heatmap (ECharts)' },
  { key: 'funnel', label: 'Funnel (ECharts)' },
  { key: 'candlestick', label: 'Candlestick (ECharts)' },
  { key: 'bar3d', label: 'Bar 3D (ECharts)' },
  { key: 'box', label: 'Box Plot (Plotly)' },
  { key: 'violin', label: 'Violin (Plotly)' },
  { key: 'scatter3d', label: 'Scatter 3D (Plotly)' },
]

export default function BiAdvancedViz({ style }: { style?: React.CSSProperties }) {
  const [activeChart, setActiveChart] = useState<string>('sankey')
  const isMobile = useMediaQuery('(max-width: 900px)')

  return (
    <div style={{ background: 'var(--surface-1,#fff)', borderRadius: 12, padding: '1.25rem', ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: '1rem' }}>Visualizacion avanzada (D3 + ECharts + Plotly)</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {CHART_TYPES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveChart(key)}
              style={{
                padding: '4px 12px',
                borderRadius: 20,
                border: '1.5px solid var(--border)',
                background: activeChart === key ? 'var(--accent,var(--accent))' : 'transparent',
                color: activeChart === key ? '#fff' : 'var(--text-secondary,var(--text-3))',
                fontSize: '0.75rem',
                minHeight: 36,
                cursor: 'pointer',
                fontWeight: activeChart === key ? 700 : 400,
                transition: 'all .15s',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <DynamicChart type={activeChart} config={{ width: isMobile ? 340 : 900, height: 380 }} />
    </div>
  )
}
