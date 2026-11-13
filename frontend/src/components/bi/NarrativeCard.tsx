import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Sparkles, RefreshCw, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import MarkdownText from '../ui/MarkdownText'

// TODO type: analyticsApi.narrative response — needs shared type
interface NarrativeData {
  narrative?: string
  cached?: boolean
  source?: string
  kpis?: { hours_mtd?: number; [k: string]: unknown }
}

interface NarrativeCardProps {
  lang?: string
  style?: React.CSSProperties
}

export default function NarrativeCard({ lang = 'es', style = {} }: NarrativeCardProps) {
  const { t } = useAppLang()
  const [expanded, setExpanded] = useState<boolean>(true)
  const [forceRefresh, setForceRefresh] = useState<boolean>(false)

  const { data, isLoading, isError, isFetching } = useQuery<NarrativeData>({
    queryKey: ['bi-narrative', lang, forceRefresh],
    queryFn: () => analyticsApi.narrative({ lang, force_refresh: forceRefresh }).then(r => r.data),
    staleTime: 55 * 60 * 1000,
    retry: 1,
  })

  const handleRefresh = () => {
    // Toggling forceRefresh changes the queryKey, which triggers an automatic refetch.
    setForceRefresh(f => !f)
  }

  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--surface-4)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      ...style,
    }}>
      {/* Header bar */}
      <div
        role="button"
        tabIndex={0}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%',
          padding: '14px 20px',
          borderBottom: expanded ? '1px solid var(--surface-4)' : 'none',
          cursor: 'pointer',
          background: 'transparent',
        }}
        onClick={() => setExpanded(e => !e)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setExpanded((prev) => !prev)
          }
        }}
      >
        <div className="u-row-center-10">
          <span style={{
            background: alpha(COLOR.accent, '18'), borderRadius: 8, padding: '5px 7px',
            display: 'flex', alignItems: 'center',
          }}>
            <Sparkles size={14} color={COLOR.accent} />
          </span>
          <div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>
              Resumen ejecutivo IA
            </div>
            {data?.cached && (
              <div className="u-text3-2xs">{t('narrativecard.desde_cache_1h_ttl')}</div>
            )}
          </div>
        </div>
        <div className="u-row-center-8">
          <button aria-label="Regenerar narrativa"
            onClick={e => { e.stopPropagation(); handleRefresh() }}
            disabled={isFetching}
            title="Regenerar narrativa"
            style={{
              background: 'transparent', border: 'none', cursor: isFetching ? 'not-allowed' : 'pointer',
              color: 'var(--text-3)', padding: 4, borderRadius: 'var(--radius-sm)',
              display: 'flex', alignItems: 'center',
            }}
          >
            <RefreshCw size={13} style={{ animation: isFetching ? 'spin 1s linear infinite' : 'none' }} />
          </button>
          {expanded ? <ChevronUp size={14} color="var(--text-3)" /> : <ChevronDown size={14} color="var(--text-3)" />}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div style={{ padding: '18px 22px' }}>
          {isLoading || isFetching ? (
            <div className="u-stack-10">
              {[80, 100, 65, 90, 55].map((w, i) => (
                <div key={i} style={{
                  height: 12, width: `${w}%`, borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface-4)',
                  animation: 'pulse 1.5s ease-in-out infinite',
                }} />
              ))}
            </div>
          ) : isError ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: COLOR.danger, fontSize: "var(--text-sm)" }}>
              <AlertCircle size={14} />
              {t('narrativecard.error_al_generar_la_narrativa_verifica_la')}
            </div>
          ) : data?.narrative ? (
            <>
              <MarkdownText
                text={data.narrative}
                style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.7 }}
              />
              <div style={{
                marginTop: 14,
                display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
              }}>
                {data.source && (
                  <span style={{
                    fontSize: "var(--text-2xs)", color: 'var(--text-3)',
                    background: 'var(--surface-4)', borderRadius: 5, padding: '2px 7px',
                  }}>
                    fuente: {data.source}
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
