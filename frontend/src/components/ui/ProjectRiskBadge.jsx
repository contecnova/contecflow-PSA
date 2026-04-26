/**
 * ProjectRiskBadge — ML-powered overrun risk badge for project cards.
 *
 * Calls POST /predictions/overrun-risk for the given projectId.
 * Shows a coloured dot + label. On hover shows a tooltip with CPI/SPI and
 * the top risk signals.
 *
 * Usage:
 *   <ProjectRiskBadge projectId={project.id} />
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'

const RISK_CFG = {
  low:      { color: 'var(--success)',  bg: 'rgba(29,158,117,0.12)',  label: 'Bajo riesgo',     dot: '#1D9E75' },
  medium:   { color: 'var(--warning)',  bg: 'rgba(250,199,117,0.15)', label: 'Riesgo moderado', dot: '#FAC775' },
  high:     { color: '#F87171',         bg: 'rgba(248,113,113,0.12)', label: 'Alto riesgo',     dot: '#F87171' },
  critical: { color: '#EF4444',         bg: 'rgba(239,68,68,0.15)',   label: 'Riesgo crítico',  dot: '#EF4444' },
}

export default function ProjectRiskBadge({ projectId, hasData = true }) {
  const [showTooltip, setShowTooltip] = useState(false)

  // Skip prediction if project has insufficient data
  const { data, isLoading, isError } = useQuery({
    queryKey: ['ml-risk', projectId],
    queryFn: () => api.post('/predictions/overrun-risk', { project_id: projectId }).then(r => r.data),
    staleTime: 5 * 60 * 1000,   // 5 min — don't hammer the endpoint
    retry: false,
    enabled: !!projectId && hasData,  // Skip call if hasData=false
  })

  // Don't render badge for projects without data or errors
  if (!hasData || isError || !data) return null
  if (data.can_predict === false) return null  // Project has no tasks

  const level = data.risk_level || 'low'
  const cfg   = RISK_CFG[level] || RISK_CFG.low

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Badge pill */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '2px 8px', borderRadius: 20,
        background: cfg.bg, fontSize: 11, fontWeight: 500,
        color: cfg.color, cursor: 'default', userSelect: 'none',
        border: `1px solid ${cfg.color}33`,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
        {cfg.label}
        {data.used_heuristic && (
          <span style={{ fontSize: 9, opacity: 0.7, fontWeight: 400 }}>~</span>
        )}
      </div>

      {/* Tooltip */}
      {showTooltip && (
        <div style={{
          position: 'absolute', bottom: 'calc(100% + 8px)', left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
          borderRadius: 10, padding: '10px 14px', width: 240,
          boxShadow: '0 8px 24px rgba(0,0,0,0.3)', zIndex: 1000,
          fontSize: 11, lineHeight: 1.5,
        }}>
          {/* Arrow */}
          <div style={{
            position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)',
            width: 0, height: 0,
            borderLeft: '5px solid transparent', borderRight: '5px solid transparent',
            borderTop: '5px solid var(--surface-4)',
          }} />

          <div style={{ fontWeight: 600, marginBottom: 6, color: cfg.color }}>{cfg.label}</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 8 }}>
            {[
              ['CPI', data.cpi],
              ['SPI', data.spi],
              ['Presupuesto', `${data.budget_used_pct?.toFixed(0)}%`],
              ['Avance', `${data.elapsed_pct?.toFixed(0)}%`],
            ].map(([k, v]) => (
              <div key={k}>
                <span style={{ color: 'var(--text-3)' }}>{k}: </span>
                <span style={{ fontWeight: 500 }}>{typeof v === 'number' ? v.toFixed(2) : v}</span>
              </div>
            ))}
          </div>

          {data.signals?.length > 0 && (
            <div>
              <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>Señales:</div>
              {data.signals.slice(0, 3).map((s, i) => (
                <div key={i} style={{ color: 'var(--text-2)', marginBottom: 2 }}>
                  · {s.signal}
                </div>
              ))}
            </div>
          )}

          {data.recommendation && (
            <div style={{ marginTop: 6, color: 'var(--text-2)', borderTop: '1px solid var(--surface-4)', paddingTop: 6 }}>
              {data.recommendation}
            </div>
          )}

          {data.used_heuristic && (
            <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text-3)' }}>
              ~ Basado en heurística (sin modelo ML entrenado)
            </div>
          )}
        </div>
      )}
    </div>
  )
}
