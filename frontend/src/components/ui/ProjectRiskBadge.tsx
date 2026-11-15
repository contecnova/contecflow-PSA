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
import { STALE_5_MIN_MS } from '../../constants/timings'
import './ProjectRiskBadge.css'

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

interface RiskCfg {
  color: string
  bg: string
  label: string
  dot: string
}

const RISK_CFG: Record<RiskLevel, RiskCfg> = {
  low:      { color: 'var(--success)', bg: 'var(--success-bg)',                                          label: 'uikit.riesgo_low',      dot: 'var(--success)' },
  medium:   { color: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 15%, transparent)',        label: 'uikit.riesgo_medium',   dot: 'var(--warning)' },
  high:     { color: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 12%, transparent)',         label: 'uikit.riesgo_high',     dot: 'var(--danger)' },
  critical: { color: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 18%, transparent)',         label: 'uikit.riesgo_critical', dot: 'var(--danger)' },
}

export interface ProjectRiskBadgeProps {
  projectId: string | number | null | undefined
  hasData?: boolean
}

export default function ProjectRiskBadge({ projectId, hasData = true }: ProjectRiskBadgeProps) {
  const { t } = useAppLang()
  const [showTooltip, setShowTooltip] = useState(false)

  // Skip prediction if project has insufficient data
  const { data, isError } = useQuery({
    queryKey: ['ml-risk', projectId],
    queryFn: () => predictionsApi.overrunRisk(projectId).then(r => r.data),
    staleTime: STALE_5_MIN_MS,
    retry: false,
    enabled: !!projectId && hasData,
  })

  // Don't render badge for projects without data or errors
  if (!hasData || isError || !data) return null
  if ('can_predict' in data) return null  // sin datos para predecir (200 con `can_predict: false`)

  const level: RiskLevel = data.risk_level
  const cfg   = RISK_CFG[level] || RISK_CFG.low

  return (
    <div className="uiprriba-box-1"
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
      <div className="uiprriba-row-1 projectr-sx1" style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${alpha(cfg.color, '33')}` }}>
        <span className="uiprriba-box-8" style={{ background: cfg.dot }} />
        {t(cfg.label)}
        {data.used_heuristic && (
          <span className="uiprriba-box-2">~</span>
        )}
      </div>

      {/* Tooltip */}
      {showTooltip && (
        <div className="projectr-sx2">
          {/* Arrow */}
          <div className="uiprriba-box-3" />

          <div className="uiprriba-box-9" style={{ color: cfg.color }}>{t(cfg.label)}</div>

          <div className="uiprriba-grid-1">
            {([
              ['CPI', data.cpi],
              ['SPI', data.spi],
              [t('uikit.presupuesto'), `${data.budget_used_pct?.toFixed(0)}%`],
              [t('uikit.avance'), `${data.elapsed_pct?.toFixed(0)}%`],
            ] as Array<[string, number | string | undefined]>).map(([k, v]) => (
              <div key={k}>
                <span className="u-text3">{k}: </span>
                <span className="uiprriba-txt-1">{typeof v === 'number' ? v.toFixed(2) : v}</span>
              </div>
            ))}
          </div>

          {data.signals && data.signals.length > 0 && (
            <div>
              <div className="uiprriba-box-4">{t('projectriskbadge.senales')}</div>
              {data.signals.slice(0, 3).map((s, i) => (
                <div key={i} className="uiprriba-box-5">
                  · {s.signal}
                </div>
              ))}
            </div>
          )}

          {data.recommendation && (
            <div className="uiprriba-box-6">
              {data.recommendation}
            </div>
          )}

          {data.used_heuristic && (
            <div className="uiprriba-box-7">
              {t('projectriskbadge.basado_en_heuristica_sin_modelo_ml_entrenado')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
