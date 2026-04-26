import { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { analyticsApi } from '../../services/api'
import { Search, Send, AlertTriangle, Info, ChevronDown, ChevronUp } from 'lucide-react'
import { COLOR } from '../../constants/theme'

const EXAMPLE_QUESTIONS = [
  '¿Cuáles son los 5 proyectos con más horas imputadas este mes?',
  '¿Qué usuarios tienen menos del 70% de utilización?',
  '¿Cuánto pipeline ponderado hay en etapa "propuesta"?',
  '¿Cuál es el coste total por departamento este trimestre?',
  'Muéstrame los tickets con SLA incumplido esta semana',
]

function ResultTable({ columns, rows }) {
  if (!columns?.length || !rows?.length) return null
  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--surface-3)' }}>
            {columns.map(col => (
              <th key={col} style={{
                padding: '8px 12px', textAlign: 'left',
                fontWeight: 600, color: 'var(--text-2)',
                borderBottom: '1px solid var(--surface-4)',
                whiteSpace: 'nowrap',
              }}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{
              background: i % 2 === 0 ? 'transparent' : 'var(--surface-1)',
              borderBottom: '1px solid var(--surface-4)',
            }}>
              {columns.map(col => (
                <td key={col} style={{ padding: '7px 12px', color: 'var(--text-1)' }}>
                  {row[col] == null ? '—' : String(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AskDataWidget({ style = {} }) {
  const [question, setQuestion] = useState('')
  const [showSql, setShowSql] = useState(false)
  const [showExamples, setShowExamples] = useState(false)
  const inputRef = useRef(null)

  const mutation = useMutation({
    mutationFn: (q) => analyticsApi.ask(q).then(r => r.data),
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    mutation.mutate(q)
  }

  const handleExample = (q) => {
    setQuestion(q)
    setShowExamples(false)
    mutation.mutate(q)
  }

  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--surface-4)',
      borderRadius: 14,
      overflow: 'hidden',
      ...style,
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--surface-4)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <span style={{
          background: `${COLOR.purple}18`, borderRadius: 8, padding: '5px 7px',
          display: 'flex', alignItems: 'center',
        }}>
          <Search size={14} color={COLOR.purple} />
        </span>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>
            Ask the Data
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
            Pregunta en lenguaje natural · responde con SQL sobre OLAP
          </div>
        </div>
      </div>

      {/* Input */}
      <div style={{ padding: '16px 20px 0' }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8 }}>
          <input
            ref={inputRef}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="¿Qué proyectos tienen margen negativo este año?"
            disabled={mutation.isPending}
            style={{
              flex: 1, padding: '9px 14px', borderRadius: 8, fontSize: 13,
              background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
              color: 'var(--text-1)', outline: 'none', fontFamily: 'inherit',
            }}
          />
          <button type="submit" disabled={mutation.isPending || !question.trim()} style={{
            padding: '9px 16px', borderRadius: 8, border: 'none',
            background: mutation.isPending ? 'var(--surface-4)' : COLOR.accent,
            color: '#fff', cursor: mutation.isPending ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 12,
          }}>
            <Send size={13} />
            {mutation.isPending ? 'Consultando…' : 'Consultar'}
          </button>
        </form>

        {/* Examples toggle */}
        <button
          onClick={() => setShowExamples(v => !v)}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', fontSize: 11, padding: '6px 2px',
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          {showExamples ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          Ver preguntas de ejemplo
        </button>

        {showExamples && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
            {EXAMPLE_QUESTIONS.map(q => (
              <button key={q} onClick={() => handleExample(q)} style={{
                background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
                borderRadius: 7, padding: '6px 12px', cursor: 'pointer',
                textAlign: 'left', fontSize: 12, color: 'var(--text-2)', fontFamily: 'inherit',
              }}>
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results */}
      <div style={{ padding: '12px 20px 18px' }}>
        {mutation.isError && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: COLOR.danger, fontSize: 12 }}>
            <AlertTriangle size={13} /> Error de conexión con el servidor.
          </div>
        )}

        {mutation.data && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {mutation.data.error ? (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                color: COLOR.warning, fontSize: 12,
                background: `${COLOR.warning}10`,
                border: `1px solid ${COLOR.warning}30`,
                borderRadius: 8, padding: '10px 14px',
              }}>
                <AlertTriangle size={13} style={{ marginTop: 1, flexShrink: 0 }} />
                <div>
                  <strong>Consulta bloqueada:</strong> {mutation.data.error}
                </div>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                    {mutation.data.row_count} resultado{mutation.data.row_count !== 1 ? 's' : ''}
                    {mutation.data.truncated ? ' (truncado a 200)' : ''}
                  </span>
                  <button
                    onClick={() => setShowSql(v => !v)}
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      fontSize: 10, color: 'var(--text-3)',
                      display: 'flex', alignItems: 'center', gap: 3,
                    }}
                  >
                    <Info size={10} />
                    {showSql ? 'Ocultar SQL' : 'Ver SQL'}
                  </button>
                </div>

                {showSql && mutation.data.sql && (
                  <pre style={{
                    fontSize: 11, color: 'var(--text-2)', background: 'var(--surface-1)',
                    border: '1px solid var(--surface-4)', borderRadius: 7,
                    padding: '10px 14px', overflowX: 'auto', lineHeight: 1.6,
                    margin: 0,
                  }}>{mutation.data.sql}</pre>
                )}

                <ResultTable columns={mutation.data.columns} rows={mutation.data.rows} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
