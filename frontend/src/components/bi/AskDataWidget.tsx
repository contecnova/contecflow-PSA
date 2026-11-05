import React, { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { analyticsApi } from '../../services/api'
import { Search, Send, AlertTriangle, Info, ChevronDown, ChevronUp } from 'lucide-react'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'

const EXAMPLE_QUESTIONS = [
  '¿Cuáles son los 5 proyectos con más horas imputadas este mes?',
  '¿Qué usuarios tienen menos del 70% de utilización?',
  '¿Cuánto pipeline ponderado hay en etapa "propuesta"?',
  '¿Cuál es el coste total por departamento este trimestre?',
  'Muéstrame los tickets con SLA incumplido esta semana',
]

function ResultTable({ columns, rows }: { columns?: string[]; rows?: Array<Record<string, unknown>> }) {
  if (!columns?.length || !rows?.length) return null
  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-sm)" }}>
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

// TODO type: analyticsApi.ask response — needs shared type
interface AskResult {
  error?: string
  row_count?: number
  truncated?: boolean
  sql?: string
  columns?: string[]
  rows?: Array<Record<string, unknown>>
  // Revisión 2026-11: ¿responde a esta pregunta o a otra parecida?
  verification?: { verdict: 'verified' | 'warning' | 'not_checked'; checks: Array<{ name: string; status: string }> }
  // Revisión 2026-11: valores reales con cero filas, reintento y banco de preguntas validadas.
  zero_result_hints?: Array<{ table: string; column: string; op: string; searched: string; exists: boolean; closest: string[]; sample: string[] }> | null
  retried_with_real_values?: { first_sql: string }
  from_validated_example?: { id: string; question: string }
  model_sql?: string
}

/** Lo que se buscó y no existe, con los valores que sí hay (revisión 2026-11). */
function PistasSinFilas({ pistas }: { pistas: AskResult['zero_result_hints'] }) {
  const { t } = useAppLang()
  const faltan = (pistas || []).filter(p => !p.exists)
  if (!faltan.length) return null
  return (
    <div role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-1)', background: alpha(COLOR.warning, '10'), border: `1px solid ${alpha(COLOR.warning, '30')}`, borderRadius: 7, padding: '8px 10px' }}>
      {faltan.map((p, i) => (
        <div key={i} style={{ marginTop: i ? 6 : 0 }}>
          {t('askdatawidget.pista_no_existe', { columna: `${p.table}.${p.column}`, valor: p.searched })}{' '}
          <span style={{ color: 'var(--text-2)' }}>
            {!p.sample.length ? t('askdatawidget.pista_sin_datos') : (
              <>
                {t(p.closest.length ? 'askdatawidget.pista_parecidos' : 'askdatawidget.pista_existen')}{' '}
                {(p.closest.length ? p.closest : p.sample).map(v => <code key={v} style={{ fontFamily: 'var(--font-mono)', marginRight: 6 }}>{v}</code>)}
              </>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

// Lo que se comprobó, en el idioma del usuario. «No comprobado» se dice tal cual:
// un «verificado» sin haber mirado nada sería peor que no verificar.
function Verificacion({ v }: { v?: AskResult['verification'] }) {
  const { t } = useAppLang()
  if (!v) return null
  const avisos = v.checks.filter(c => c.status === 'warning')
  const hechas = v.checks.filter(c => c.status !== 'skipped').length
  const color = v.verdict === 'warning' ? COLOR.warning : v.verdict === 'verified' ? COLOR.success : 'var(--text-3)'
  return (
    <div role={v.verdict === 'warning' ? 'alert' : undefined} style={{ fontSize: 'var(--text-xs)', color, background: alpha(v.verdict === 'not_checked' ? '#888888' : color, '12'), border: `1px solid ${alpha(v.verdict === 'not_checked' ? '#888888' : color, '30')}`, borderRadius: 7, padding: '7px 10px' }}>
      <strong>{t('askdatawidget.verif_' + v.verdict, { n: hechas })}</strong>
      {avisos.map(c => <div key={c.name} style={{ marginTop: 3 }}>⚠ {t('askdatawidget.verif_aviso_' + c.name)}</div>)}
    </div>
  )
}

export default function AskDataWidget({ style = {} }: { style?: React.CSSProperties }) {
  const { t } = useAppLang()
  const [question, setQuestion] = useState<string>('')
  const [showSql, setShowSql] = useState<boolean>(false)
  const [showExamples, setShowExamples] = useState<boolean>(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const mutation = useMutation<AskResult, unknown, string>({
    mutationFn: (q: string) => analyticsApi.ask(q).then(r => r.data),
    onSuccess: () => setGuardada(false),
  })
  const { user } = useAuth()
  const puedeValidar = user?.role === 'admin' || user?.role === 'pm'
  const [guardada, setGuardada] = useState(false)
  const guardar = useMutation({
    mutationFn: () => analyticsApi.saveAskExample(question.trim(), mutation.data?.model_sql || ''),
    onSuccess: () => setGuardada(true),
  })

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    mutation.mutate(q)
  }

  const handleExample = (q: string) => {
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
          background: alpha(COLOR.purple, '18'), borderRadius: 8, padding: '5px 7px',
          display: 'flex', alignItems: 'center',
        }}>
          <Search size={14} color={COLOR.purple} />
        </span>
        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>
            Ask the Data
          </div>
          <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>
            {t('askdatawidget.pregunta_en_lenguaje_natural_responde_con_sql')}
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
            placeholder={t('askdatawidget.que_proyectos_tienen_margen_negativo_este_ano')}
            disabled={mutation.isPending}
            style={{
              flex: 1, padding: '9px 14px', borderRadius: 8, fontSize: "var(--text-base)",
              background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
              color: 'var(--text-1)', outline: 'none', fontFamily: 'inherit',
            }}
          />
          <button type="submit" disabled={mutation.isPending || !question.trim()} style={{
            padding: '9px 16px', borderRadius: 8, border: 'none',
            background: mutation.isPending ? 'var(--surface-4)' : COLOR.accent,
            color: '#fff', cursor: mutation.isPending ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: "var(--text-sm)",
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
            color: 'var(--text-3)', fontSize: "var(--text-xs)", padding: '6px 2px',
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          {showExamples ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {t('askdatawidget.ver_preguntas_de_ejemplo')}
        </button>

        {showExamples && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
            {EXAMPLE_QUESTIONS.map(q => (
              <button key={q} onClick={() => handleExample(q)} style={{
                background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
                borderRadius: 7, padding: '6px 12px', cursor: 'pointer',
                textAlign: 'left', fontSize: "var(--text-sm)", color: 'var(--text-2)', fontFamily: 'inherit',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: COLOR.danger, fontSize: "var(--text-sm)" }}>
            <AlertTriangle size={13} /> {t('askdatawidget.error_de_conexion_con_el_servidor')}
          </div>
        )}

        {mutation.data && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {mutation.data.error ? (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                color: COLOR.warning, fontSize: "var(--text-sm)",
                background: alpha(COLOR.warning, '10'),
                border: `1px solid ${alpha(COLOR.warning, '30')}`,
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
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                    {mutation.data.row_count} resultado{mutation.data.row_count !== 1 ? 's' : ''}
                    {mutation.data.truncated ? ' (truncado a 200)' : ''}
                  </span>
                  <button
                    onClick={() => setShowSql(v => !v)}
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      fontSize: "var(--text-2xs)", color: 'var(--text-3)',
                      display: 'flex', alignItems: 'center', gap: 3,
                    }}
                  >
                    <Info size={10} />
                    {showSql ? 'Ocultar SQL' : 'Ver SQL'}
                  </button>
                </div>

                {showSql && mutation.data.sql && (
                  <pre style={{
                    fontSize: "var(--text-xs)", color: 'var(--text-2)', background: 'var(--surface-1)',
                    border: '1px solid var(--surface-4)', borderRadius: 7,
                    padding: '10px 14px', overflowX: 'auto', lineHeight: 1.6,
                    margin: 0,
                  }}>{mutation.data.sql}</pre>
                )}

                {mutation.data.from_validated_example && (
                  <div style={{ fontSize: 'var(--text-xs)', color: COLOR.success }}>
                    ✓ {t('askdatawidget.de_ejemplo_validado', { pregunta: mutation.data.from_validated_example.question })}
                  </div>
                )}
                {mutation.data.retried_with_real_values && (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>↻ {t('askdatawidget.reintentada_con_valores_reales')}</div>
                )}
                <Verificacion v={mutation.data.verification} />
                <PistasSinFilas pistas={mutation.data.zero_result_hints} />
                <ResultTable columns={mutation.data.columns} rows={mutation.data.rows} />
                {puedeValidar && mutation.data.model_sql && !mutation.data.from_validated_example && (
                  <div>
                    <button type="button" onClick={() => guardar.mutate()} disabled={guardada || guardar.isPending}
                      title={t('askdatawidget.validar_ayuda')}
                      style={{ background: 'transparent', border: `1px solid ${guardada ? COLOR.success : 'var(--surface-4)'}`, color: guardada ? COLOR.success : 'var(--text-2)', borderRadius: 7, padding: '4px 10px', fontSize: 'var(--text-xs)', cursor: guardada ? 'default' : 'pointer', fontFamily: 'inherit' }}>
                      {guardada ? `✓ ${t('askdatawidget.validada')}` : t('askdatawidget.validar')}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
