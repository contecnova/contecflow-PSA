import React, { type CSSProperties, useState, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { analyticsApi, conectoresApi } from '../../services/api'
import type { RespuestaDeAskTheData } from '../../services/api/tipos-analitica'
import { Search, Send, AlertTriangle, Info, ChevronDown, ChevronUp, Check, RotateCcw, ArrowRight } from 'lucide-react'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { Button, Table, Pulsable } from '../ui'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './AskDataWidget.css'

/** Preguntas de ejemplo: `askdatawidget.ejemplo_<n>` en el idioma del usuario. */
const EXAMPLE_QUESTIONS = ['ejemplo_1', 'ejemplo_2', 'ejemplo_3', 'ejemplo_4', 'ejemplo_5']

function ResultTable({ columns, rows }: { columns?: string[]; rows?: Array<Record<string, unknown>> }) {
  if (!columns?.length || !rows?.length) return null
  return (
    <div className="asdawi-box-1">
      <Table
        data={rows}
        columns={columns.map(col => ({
          key: col,
          label: <span className="asdawi-txt-1">{col}</span>,
          render: (_v: never, row: Record<string, unknown>) => (row[col] == null ? '—' : String(row[col])),
        }))}
      />
    </div>
  )
}

type AskResult = RespuestaDeAskTheData

/** Lo que se buscó y no existe, con los valores que sí hay (revisión 2026-11). */
function PistasSinFilas({ pistas }: { pistas: AskResult['zero_result_hints'] }) {
  const { t } = useAppLang()
  const faltan = (pistas || []).filter(p => !p.exists)
  if (!faltan.length) return null
  return (
    <div className="asdawi-box-8 askdataw-sx1 ask-data-widget-e1" role="status" style={{ '--ask-data-widget-background': alpha(COLOR.warning, '10'), '--ask-data-widget-border': `1px solid ${alpha(COLOR.warning, '30')}` } as CSSProperties}>
      {faltan.map((p, i) => (
        <div key={i} className={`${i ? 'ask-data-widget-m2' : 'ask-data-widget-m3'}`}>
          {t('askdatawidget.pista_no_existe', { columna: `${p.table}.${p.column}`, valor: p.searched })}{' '}
          <span className="u-text2">
            {!p.sample.length ? t('askdatawidget.pista_sin_datos') : (
              <>
                {t(p.closest.length ? 'askdatawidget.pista_parecidos' : 'askdatawidget.pista_existen')}{' '}
                {(p.closest.length ? p.closest : p.sample).map(v => <code key={v} className="ds-codigo asdawi-box-2">{v}</code>)}
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
    <div className="asdawi-box-9 ask-data-widget-e4" role={v.verdict === 'warning' ? 'alert' : undefined} style={{ '--ask-data-widget-color': color, '--ask-data-widget-background': alpha(v.verdict === 'not_checked' ? 'var(--text-3)' : color, '12'), '--ask-data-widget-border': `1px solid ${alpha(v.verdict === 'not_checked' ? 'var(--text-3)' : color, '30')}` } as CSSProperties}>
      <strong>{t('askdatawidget.verif_' + v.verdict, { n: hechas })}</strong>
      {avisos.map(c => <div key={c.name} className="asdawi-sp-1 asdawi-ico"><AlertTriangle size={12} aria-hidden="true" />{t('askdatawidget.verif_aviso_' + c.name)}</div>)}
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
  const { puede } = useAuth()
  const puedeValidar = puede('analitica.ver')
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
    <div className="ask-data-widget-e12" style={style}>
      {/* Header */}
      <div className="asdawi-row-1">
        <span className="asdawi-row-5 ask-data-widget-e5" style={{ '--ask-data-widget-background': alpha(COLOR.purple, '18') } as CSSProperties}>
          <Search size={14} color={COLOR.purple} />
        </span>
        <div>
          <div className="asdawi-txt-2">
            {t('askdatawidget.titulo')}
          </div>
          <div className="u-text3-2xs">
            {t('askdatawidget.pregunta_en_lenguaje_natural_responde_con_sql')}
          </div>
        </div>
      </div>

      {/* Input */}
      <div className="asdawi-sp-2">
        <form onSubmit={handleSubmit} className="u-row-8">
          <input aria-label={t('askdatawidget.que_proyectos_tienen_margen_negativo_este_ano')}
            ref={inputRef}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder={t('askdatawidget.que_proyectos_tienen_margen_negativo_este_ano')}
            disabled={mutation.isPending}
            className="asdawi-box-3"
          />
          <Button type="submit" icon={<Send size={13} />} disabled={mutation.isPending || !question.trim()} loading={mutation.isPending}>
            {mutation.isPending ? t('askdatawidget.consultando') : t('askdatawidget.consultar')}
          </Button>
        </form>

        {/* Examples toggle */}
        <Pulsable
          aria-expanded={showExamples}
          onClick={() => setShowExamples(v => !v)}
          className="asdawi-row-2"
        >
          {showExamples ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {t('askdatawidget.ver_preguntas_de_ejemplo')}
        </Pulsable>

        {showExamples && (
          <div className="asdawi-stack-1">
            {EXAMPLE_QUESTIONS.map(clave => {
              const q = t(`askdatawidget.${clave}`)
              return (
                <Pulsable key={clave} onClick={() => handleExample(q)} className="asdawi-box-4">
                  {q}
                </Pulsable>
              )
            })}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="asdawi-sp-3">
        {mutation.isError && (
          <div className="asdawi-row-7 ask-data-widget-e8" style={{ '--ask-data-widget-color': COLOR.danger } as CSSProperties}>
            <AlertTriangle size={13} /> {t('askdatawidget.error_de_conexion_con_el_servidor')}
          </div>
        )}

        {mutation.data && (
          <div className="u-stack-10">
            {mutation.data.error ? (
              <div className="asdawi-row-8 askdataw-sx2 ask-data-widget-e9" style={{ '--ask-data-widget-color': COLOR.warning, '--ask-data-widget-background': alpha(COLOR.warning, '10'), '--ask-data-widget-border': `1px solid ${alpha(COLOR.warning, '30')}` } as CSSProperties}>
                <AlertTriangle size={13} className="askdataw-sx3" />
                <div>
                  <strong>{t('askdatawidget.consulta_bloqueada')}</strong> {mutation.data.error}
                </div>
              </div>
            ) : (
              <>
                <div className="u-row-between">
                  <span className="u-text3-xs">
                    {t('askdatawidget.n_resultados', { count: mutation.data.row_count ?? 0 })}
                    {mutation.data.truncated ? ` ${t('askdatawidget.truncado')}` : ''}
                  </span>
                  <Button size="sm" variant="ghost" icon={<Info size={12} />} onClick={() => setShowSql(v => !v)}>
                    {showSql ? t('askdatawidget.ocultar_sql') : t('askdatawidget.ver_sql')}
                  </Button>
                </div>

                {showSql && mutation.data.sql && (
                  <pre className="asdawi-box-5">{mutation.data.sql}</pre>
                )}

                {mutation.data.from_validated_example && (
                  <div className="asdawi-txt-3 ask-data-widget-e8" style={{ '--ask-data-widget-color': COLOR.success } as CSSProperties}>
                    <Check size={12} aria-hidden="true" /> {t('askdatawidget.de_ejemplo_validado', { pregunta: mutation.data.from_validated_example.question })}
                  </div>
                )}
                {mutation.data.retried_with_real_values && (
                  <div className="u-text2-xs asdawi-ico"><RotateCcw size={12} aria-hidden="true" />{t('askdatawidget.reintentada_con_valores_reales')}</div>
                )}
                <Verificacion v={mutation.data.verification} />
                <PistasSinFilas pistas={mutation.data.zero_result_hints} />
                <ResultTable columns={mutation.data.columns} rows={mutation.data.rows} />
                {puedeValidar && mutation.data.model_sql && !mutation.data.from_validated_example && (
                  <div>
                    <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => guardar.mutate()} disabled={guardada || guardar.isPending}
                      loading={guardar.isPending} title={t('askdatawidget.validar_ayuda')}>
                      {guardada ? t('askdatawidget.validada') : t('askdatawidget.validar')}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {(mutation.data || mutation.isError) && question.trim() && <PasarAContecintelligence pregunta={question.trim()} />}
      </div>
    </div>
  )
}

/** Revisión 2026-11: con contecintelligence configurado, la misma pregunta sobre TODAS las fuentes. */
function PasarAContecintelligence({ pregunta }: { pregunta: string }) {
  const { t } = useAppLang()
  const navigate = useNavigate()
  const disp = useQuery({ queryKey: ['conectores', 'ci-disponible'], queryFn: conectoresApi.ciDisponible, staleTime: STALE_DEFAULT_MS, retry: false })
  if (!disp.data?.configurado || !disp.data.pasar_preguntas) return null
  return (
    <div className="asdawi-row-4">
      <span className="asdawi-box-6">{t('ci.pasar_texto')}</span>
      <Button size="sm" variant="secondary" icon={<ArrowRight size={14} />} onClick={() => navigate(`/ask-company?q=${encodeURIComponent(pregunta)}`)}>
        {t('ci.pasar')}
      </Button>
    </div>
  )
}
