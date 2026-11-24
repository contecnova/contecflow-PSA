import React, { type CSSProperties, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Sparkles, RefreshCw, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import MarkdownText from '../ui/MarkdownText'
import { STALE_AI_NARRATIVE_MS } from '../../constants/timings'
import './NarrativeCard.css'
import { IconButton } from '../ui'


interface NarrativeCardProps {
  lang?: string
  style?: React.CSSProperties
}

export default function NarrativeCard({ lang = 'es', style = {} }: NarrativeCardProps) {
  const { t } = useAppLang()
  const [expanded, setExpanded] = useState<boolean>(true)
  const [forceRefresh, setForceRefresh] = useState<boolean>(false)

  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ['bi-narrative', lang, forceRefresh],
    queryFn: () => analyticsApi.narrative({ lang, force_refresh: forceRefresh }).then(r => r.data),
    staleTime: STALE_AI_NARRATIVE_MS,
    retry: 1,
  })

  const handleRefresh = () => {
    // Toggling forceRefresh changes the queryKey, which triggers an automatic refetch.
    setForceRefresh(f => !f)
  }

  return (
    <div className="narrative-card-e10" style={style}>
      {/* Header bar */}
      <div className={`narrcard-row-2 ${expanded ? 'narrative-card-m1' : 'narrative-card-m2'}`}
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(e => !e)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setExpanded((prev) => !prev)
          }
        }}
      >
        <div className="u-row-center-10">
          <span className="narrcard-row-3 narrative-card-e3" style={{ '--narrative-card-background': alpha(COLOR.accent, '18') } as CSSProperties}>
            <Sparkles size={14} color={COLOR.accent} />
          </span>
          <div>
            <div className="narrcard-txt-1">
              {t('narrativecard.resumen_ejecutivo_ia')}
            </div>
            {data?.cached && (
              <div className="u-text3-2xs">{t('narrativecard.desde_cache_1h_ttl')}</div>
            )}
          </div>
        </div>
        <div className="u-row-center-8">
          <IconButton variante="caja" ariaLabel={t('narrativecard.regenerar_narrativa')}
            onClick={e => { e.stopPropagation(); handleRefresh() }}
            disabled={isFetching}
            title={t('narrativecard.regenerar_narrativa')}
          >
            <RefreshCw size={13} className={`${isFetching ? 'narrative-card-m6' : 'narrative-card-m7'}`} />
          </IconButton>
          {expanded ? <ChevronUp size={14} color="var(--text-3)" /> : <ChevronDown size={14} color="var(--text-3)" />}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="narrcard-sp-1">
          {isLoading || isFetching ? (
            <div className="u-stack-10">
              {[80, 100, 65, 90, 55].map((w, i) => (
                <div className="narrcard-box-2 narrative-card-e8" key={i} style={{ '--narrative-card-width': `${w}%` } as CSSProperties} />
              ))}
            </div>
          ) : isError ? (
            <div className="narrcard-row-5 narrative-card-e9" style={{ '--narrative-card-color': COLOR.danger } as CSSProperties}>
              <AlertCircle size={14} />
              {t('narrativecard.error_al_generar_la_narrativa_verifica_la')}
            </div>
          ) : data?.narrative ? (
            <>
              <MarkdownText
                text={data.narrative}
                className="narrative-card-e11"
              />
              <div className="narrcard-row-1">
                {data.source && (
                  <span className="narrcard-box-1">
                    {t('narrativecard.fuente')} {data.source}
                  </span>
                )}
                {data.kpis?.hours_mtd != null && (
                  <span className="u-text3-2xs">
                    {data.kpis.hours_mtd}{t('narrativecard.h_imputadas_este_mes')}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="u-text3-sm">
              {t('narrativecard.sin_datos_suficientes_para_generar_narrativa_ejecuta')}
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
