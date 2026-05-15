import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Sparkles, RefreshCw, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { COLOR } from '../../constants/theme'

function MarkdownText({ text, style }) {
  const paragraphs = text.split(/\n\n+/)
  return (
    <div style={style}>
      {paragraphs.map((para, pi) => (
        <p key={pi} style={{ margin: pi > 0 ? '10px 0 0' : 0 }}>
          {para.split(/\n/).map((line, li) => (
            <span key={li}>
              {li > 0 && <br />}
              {line.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).map((chunk, ci) => {
                if (/^\*\*[^*]+\*\*$/.test(chunk))
                  return <strong key={ci}>{chunk.slice(2, -2)}</strong>
                if (/^\*[^*]+\*$/.test(chunk))
                  return <em key={ci}>{chunk.slice(1, -1)}</em>
                return chunk
              })}
            </span>
          ))}
        </p>
      ))}
    </div>
  )
}

export default function NarrativeCard({ lang = 'es', style = {} }) {
  const [expanded, setExpanded] = useState(true)
  const [forceRefresh, setForceRefresh] = useState(false)

  const { data, isLoading, isError, isFetching } = useQuery({
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
      borderRadius: 14,
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            background: `${COLOR.accent}18`, borderRadius: 8, padding: '5px 7px',
            display: 'flex', alignItems: 'center',
          }}>
            <Sparkles size={14} color={COLOR.accent} />
          </span>
          <div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>
              Resumen ejecutivo IA
            </div>
            {data?.cached && (
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>desde caché · 1h TTL</div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={e => { e.stopPropagation(); handleRefresh() }}
            disabled={isFetching}
            title="Regenerar narrativa"
            style={{
              background: 'transparent', border: 'none', cursor: isFetching ? 'not-allowed' : 'pointer',
              color: 'var(--text-3)', padding: 4, borderRadius: 6,
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[80, 100, 65, 90, 55].map((w, i) => (
                <div key={i} style={{
                  height: 12, width: `${w}%`, borderRadius: 6,
                  background: 'var(--surface-4)',
                  animation: 'pulse 1.5s ease-in-out infinite',
                }} />
              ))}
            </div>
          ) : isError ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: COLOR.danger, fontSize: "var(--text-sm)" }}>
              <AlertCircle size={14} />
              Error al generar la narrativa. Verifica la conexión con el proveedor IA.
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
                  <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>
                    {data.kpis.hours_mtd}h imputadas este mes
                  </span>
                )}
              </div>
            </>
          ) : (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
              Sin datos suficientes para generar narrativa. Ejecuta el ETL OLAP primero.
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
