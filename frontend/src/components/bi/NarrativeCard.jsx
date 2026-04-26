import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Sparkles, RefreshCw, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { COLOR } from '../../constants/theme'

function parseMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
}

export default function NarrativeCard({ lang = 'es', style = {} }) {
  const [expanded, setExpanded] = useState(true)
  const [forceRefresh, setForceRefresh] = useState(false)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['bi-narrative', lang, forceRefresh],
    queryFn: () => analyticsApi.narrative({ lang, force_refresh: forceRefresh }).then(r => r.data),
    staleTime: 55 * 60 * 1000,
    retry: 1,
  })

  const handleRefresh = () => {
    setForceRefresh(f => !f)
    setTimeout(() => refetch(), 50)
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
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 20px',
        borderBottom: expanded ? '1px solid var(--surface-4)' : 'none',
        cursor: 'pointer',
      }} onClick={() => setExpanded(e => !e)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            background: `${COLOR.accent}18`, borderRadius: 8, padding: '5px 7px',
            display: 'flex', alignItems: 'center',
          }}>
            <Sparkles size={14} color={COLOR.accent} />
          </span>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>
              Resumen ejecutivo IA
            </div>
            {data?.cached && (
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>desde caché · 1h TTL</div>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: COLOR.danger, fontSize: 12 }}>
              <AlertCircle size={14} />
              Error al generar la narrativa. Verifica la conexión con el proveedor IA.
            </div>
          ) : data?.narrative ? (
            <>
              <div
                style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}
                dangerouslySetInnerHTML={{
                  __html: `<p>${parseMarkdown(data.narrative)}</p>`,
                }}
              />
              <div style={{
                marginTop: 14,
                display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
              }}>
                {data.source && (
                  <span style={{
                    fontSize: 10, color: 'var(--text-3)',
                    background: 'var(--surface-4)', borderRadius: 5, padding: '2px 7px',
                  }}>
                    fuente: {data.source}
                  </span>
                )}
                {data.kpis?.hours_mtd != null && (
                  <span style={{ fontSize: 10, color: 'var(--text-3)' }}>
                    {data.kpis.hours_mtd}h imputadas este mes
                  </span>
                )}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
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
