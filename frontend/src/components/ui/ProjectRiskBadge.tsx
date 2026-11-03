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
// TODO type: services/api still JS.
import { predictionsApi } from '../../services/api'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

interface RiskCfg {
  color: string
  bg: string
  label: string
  dot: string
}

const RISK_CFG: Record<RiskLevel, RiskCfg> = {
  low:      { color: 'var(--success)', bg: 'var(--success-bg)',                                          label: 'Bajo riesgo',     dot: 'var(--success)' },
  medium:   { color: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 15%, transparent)',        label: 'Riesgo moderado', dot: 'var(--warning)' },
  high:     { color: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 12%, transparent)',         label: 'Alto riesgo',     dot: 'var(--danger)' },
  critical: { color: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 18%, transparent)',         label: 'Riesgo crítico',  dot: 'var(--danger)' },
}

export interface ProjectRiskBadgeProps {
  projectId: string | number | null | undefined
  hasData?: boolean
}

interface RiskSignal {
  signal: string
}

interface RiskData {
  can_predict?: boolean
  risk_level?: RiskLevel
  cpi?: number
  spi?: number
  budget_used_pct?: number
  elapsed_pct?: number
  signals?: RiskSignal[]
  recommendation?: string
  used_heuristic?: boolean
}

export default function ProjectRiskBadge({ projectId, hasData = true }: ProjectRiskBadgeProps) {
  const { t } = useAppLang()
  const [showTooltip, setShowTooltip] = useState(false)

  // Skip prediction if project has insufficient data
  const { data, isError } = useQuery<RiskData>({
    queryKey: ['ml-risk', projectId],
    // TODO type: predictionsApi is JS-typed; cast response to RiskData.
    queryFn: () => predictionsApi.overrunRisk(projectId).then((r: { data: RiskData }) => r.data),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: !!projectId && hasData,
  })

  // Don't render badge for projects without data or errors
  if (!hasData || isError || !data) return null
  if (data.can_predict === false) return null  // Project has no tasks

  const level: RiskLevel = data.risk_level || 'low'
  const cfg   = RISK_CFG[level] || RISK_CFG.low

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}
      role="button"
      tabIndex={0}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onFocus={() => setShowTooltip(true)}
      onBlur={() => setShowTooltip(false)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          setShowTooltip(false)
        }
      }}
    >
      {/* Badge pill */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '2px 8px', borderRadius: 20,
        background: cfg.bg, fontSize: 'var(--text-xs)', fontWeight: 500,
        color: cfg.color, cursor: 'default', userSelect: 'none',
        border: `1px solid ${alpha(cfg.color, '33')}`,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
        {cfg.label}
        {data.used_heuristic && (
          <span style={{ fontSize: 'var(--text-3xs)', opacity: 0.7, fontWeight: 400 }}>~</span>
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
          fontSize: 'var(--text-xs)', lineHeight: 1.5,
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
            {([
              ['CPI', data.cpi],
              ['SPI', data.spi],
              ['Presupuesto', `${data.budget_used_pct?.toFixed(0)}%`],
              ['Avance', `${data.elapsed_pct?.toFixed(0)}%`],
            ] as Array<[string, number | string | undefined]>).map(([k, v]) => (
              <div key={k}>
                <span style={{ color: 'var(--text-3)' }}>{k}: </span>
                <span style={{ fontWeight: 500 }}>{typeof v === 'number' ? v.toFixed(2) : v}</span>
              </div>
            ))}
          </div>

          {data.signals && data.signals.length > 0 && (
            <div>
              <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>{t('projectriskbadge.senales')}</div>
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
            <div style={{ marginTop: 6, fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>
              {t('projectriskbadge.basado_en_heuristica_sin_modelo_ml_entrenado')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
