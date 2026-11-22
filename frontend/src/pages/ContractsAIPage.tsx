/**
 * ContractsAIPage — H22 (Item H22 cerrado).
 *
 * Analizador de contratos con IA. Soporta dos vías de entrada:
 *   1. Pegar texto del contrato (textarea)
 *   2. Subir PDF (extracción de texto vía pypdf en backend)
 *
 * Opcionalmente se enlaza a un proyecto (parámetro URL ``?project_id=X``).
 * Lista histórica de análisis con vista de detalle por contrato (cláusulas
 * agrupadas por tipo, badges de riesgo, citas verbatim del contrato).
 */
import { useState, useMemo, useId, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contractsAIApi, projectsApi } from '../services/api'
import type { ProjectListItem } from '../services/api/projects'
import type { ClausulaDeContratoIa, ContratoIa, ContratoIaDetalle } from '../services/api/tipos-finanzas'
import { useToast } from '../context/ToastContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Button, Card, Spinner, EmptyState, Drawer, Tabs, IconButton, Select, Textarea } from '../components/ui'
import { Coins, DoorOpen, FileText, Flag, Lock, Package, Paperclip, Ruler, ShieldAlert, Sparkles, Timer, TriangleAlert, Upload, X, type LucideIcon } from 'lucide-react'
import { extractErr, fmtDate, fmtDateTime, fmtNumber } from '../utils/helpers'
import { useAppLang } from '../i18n/AppLangContext'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './ContractsAIPage.css'

type ContractItem = ContratoIa
type ContractClause = ClausulaDeContratoIa
type ContractDetail = ContratoIaDetalle

// Etiqueta en i18n: `contractsaipage.clausula_<tipo>`.
const CLAUSE_TYPES = ['payment', 'penalty', 'deliverable', 'milestone', 'sla', 'termination', 'scope', 'confidentiality']

const CLAUSE_TYPE_ICON: Record<string, LucideIcon> = {
  payment:         Coins,
  penalty:         TriangleAlert,
  deliverable:     Package,
  milestone:       Flag,
  sla:             Timer,
  termination:     DoorOpen,
  scope:           Ruler,
  confidentiality: Lock,
}

/** El nombre que se envía al analizar texto pegado: no se enseña tal cual. */
const NOMBRE_TEXTO_PEGADO = 'pasted_text.txt'

const RISK_COLOR: Record<string, string> = {
  high:   'var(--danger)',
  medium: 'var(--warning)',
  low:    'var(--success)',
}

/** Color de datos → custom property que consume `.cai-risk`. */
const riskVar = (level: string): CSSProperties =>
  ({ '--cai-color': RISK_COLOR[level] || 'var(--text-2)' } as CSSProperties)


function ContractDetailPanel({ contractId, onClose }: { contractId: string | number | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const { t } = useAppLang()
  const idTitulo = useId()
  const { data, isLoading } = useQuery<ContractDetail | null>({
    queryKey: ['contracts-ai', contractId],
    queryFn:  () => contractsAIApi.get(contractId).then(r => r.data),
    enabled:  !!contractId,
  })

  // Agrupar cláusulas por tipo
  const groups = useMemo<Record<string, ContractClause[]>>(() => {
    if (!data?.clauses) return {}
    const out: Record<string, ContractClause[]> = {}
    for (const cl of data.clauses) {
      const key = cl.clause_type || 'other'
      if (!out[key]) out[key] = []
      out[key].push(cl)
    }
    return out
  }, [data])

  if (!contractId) return null

  const nivel = (r: string) => (RISK_COLOR[r] ? t(`contractsaipage.riesgo_${r}`) : r)

  return (
    <Drawer onClose={onClose} variant="borde" width={720} zIndex="var(--z-modal)"
      backdrop="var(--overlay-light)"
      ariaLabelledby={data ? idTitulo : undefined} ariaLabel={data ? undefined : t('contractsaipage.analisis_de_contrato')}>
      <div className="cai-panel">
        {isLoading ? <Spinner /> : !data ? <EmptyState icon={<FileText size={28} />} title={t('contractsai.no_encontrado')} /> : (
          <>
            <div className="cai-panel__head">
              <div className="u-min0">
                <h2 id={idTitulo} className="cai-panel__title">
                  {data.filename === NOMBRE_TEXTO_PEGADO ? t('contractsaipage.texto_pegado') : (data.filename || t('contractsaipage.analisis_de_contrato'))}
                </h2>
                <div className="cai-panel__meta">
                  {data.client_name || '—'} · {fmtDateTime(data.created_at)}
                  {data.risk_level && (
                    <span className="cai-risk cai-risk--head" style={riskVar(data.risk_level)}>
                      {t('contractsaipage.riesgo_nivel', { nivel: nivel(data.risk_level) })}
                    </span>
                  )}
                </div>
              </div>
              <IconButton onClick={onClose} ariaLabel={t('contractsaipage.cerrar')}><X size={16} /></IconButton>
            </div>

            {data.scope_summary && (
              <Card className="cai-mb-16">
                <h4 className="cai-subheading">
                  {t('contractsai.resumen_del_alcance')}
                </h4>
                <div className="cai-summary">
                  {data.scope_summary}
                </div>
              </Card>
            )}

            {data.total_value != null && (
              <Card className="cai-mb-16 cai-kpis">
                <div>
                  <div className="cai-kpi__label">{t('contractsaipage.valor_total')}</div>
                  <div className="cai-kpi__value">{fmtMoneda(data.total_value)}</div>
                </div>
                {(data.scope_creep_alerts ?? 0) > 0 && (
                  <div>
                    <div className="cai-kpi__label">{t('contractsaipage.scope_creep')}</div>
                    <div className="cai-kpi__value cai-kpi__value--warning">
                      {t('contractsaipage.n_alertas', { count: data.scope_creep_alerts ?? 0 })}
                    </div>
                  </div>
                )}
              </Card>
            )}

            <h3 className="cai-heading">
              {t('contractsaipage.clausulas_extraidas_n', { count: data.clauses?.length || 0 })}
            </h3>
            {Object.entries(groups).map(([type, list]) => (
              <div key={type} className="cai-group">
                <h4 className="cai-group__title">
                  {(() => { const Icono = CLAUSE_TYPE_ICON[type] ?? FileText; return <Icono size={15} aria-hidden="true" /> })()}
                  {CLAUSE_TYPES.includes(type) ? t(`contractsaipage.clausula_${type}`) : type} ({list.length})
                </h4>
                {list.map((cl) => (
                  <div key={cl.id} className={cl.is_at_risk ? 'cai-clause is-at-risk' : 'cai-clause'}>
                    <div className="cai-clause__title">
                      {cl.is_at_risk && <span className="u-danger cai-ico" title={t('contractsaipage.en_riesgo')}><TriangleAlert size={13} aria-label={t('contractsaipage.en_riesgo')} /></span>}
                      {cl.title}
                    </div>
                    {cl.description && (
                      <div className="cai-clause__desc">
                        {cl.description}
                      </div>
                    )}
                    {cl.is_at_risk && cl.risk_reason && (
                      <div className="cai-clause__risk cai-ico">
                        <ShieldAlert size={13} aria-hidden="true" />{cl.risk_reason}
                      </div>
                    )}
                    {(cl.impact_amount != null || cl.due_date) && (
                      <div className="cai-clause__meta">
                        {cl.impact_amount != null && t('contractsaipage.impacto', { importe: fmtMoneda(cl.impact_amount) })}
                        {cl.impact_amount != null && cl.due_date && ' · '}
                        {cl.due_date && t('contractsaipage.vencimiento', { fecha: fmtDate(cl.due_date) })}
                      </div>
                    )}
                    {cl.original_text && (
                      <details className="cai-clause__quote-wrap">
                        <summary>{t('contractsaipage.ver_cita')}</summary>
                        <blockquote className="cai-clause__quote">
                          {cl.original_text}
                        </blockquote>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </Drawer>
  )
}


export default function ContractsAIPage(): JSX.Element {
  const idCampo = useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const initialProjectId = params.get('project_id') || ''

  const [mode, setMode] = useState<'text' | 'pdf'>('text')
  const [text, setText] = useState('')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [projectId, setProjectId] = useState(initialProjectId)
  const [clientName, setClientName] = useState('')
  const [openContractId, setOpenContractId] = useState<string | number | null>(null)
  const selectorPdf = useRef<HTMLInputElement>(null)

  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list({}).then(r => r.data),
  })

  const { data: contracts = [], isLoading } = useQuery<ContractItem[]>({
    queryKey: ['contracts-ai', { project_id: initialProjectId }],
    queryFn:  () => contractsAIApi.list(
      initialProjectId ? { project_id: initialProjectId } : {}
    ).then(r => r.data),
  })

  const { mutate: analyzeText, isPending: isAnalyzingText } = useMutation({
    mutationFn: () => contractsAIApi.analyze({
      project_id: projectId || null,
      client_name: clientName || null,
      filename: 'pasted_text.txt',
      contract_text: text,
    }),
    onSuccess: () => {
      toast.success(t('contractsaipage.texto_analizado'))
      setText('')
      qc.invalidateQueries({ queryKey: ['contracts-ai'] })
    },
    onError: e => toast.error(extractErr(e, t('contractsaipage.error_texto'))),
  })

  const { mutate: analyzePdf, isPending: isAnalyzingPdf } = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('file', pdfFile as Blob)
      if (projectId)  fd.append('project_id', projectId)
      if (clientName) fd.append('client_name', clientName)
      return contractsAIApi.analyzePdf(fd)
    },
    onSuccess: () => {
      toast.success(t('contractsaipage.pdf_analizado'))
      setPdfFile(null)
      qc.invalidateQueries({ queryKey: ['contracts-ai'] })
    },
    onError: e => toast.error(extractErr(e, t('contractsaipage.error_pdf'))),
  })

  const isAnalyzing = isAnalyzingText || isAnalyzingPdf
  const canSubmit = mode === 'text' ? text.trim().length > 100 : !!pdfFile
  const nivel = (r: string) => (RISK_COLOR[r] ? t(`contractsaipage.riesgo_${r}`) : r)

  return (
    <PageShell>
      <PageHeader
        icon={<FileText size={18} />}
        title={t('contractsaipage.titulo')}
        subtitle={t('contractsaipage.subtitulo')}
        showListExport={false}
      />
      <div className="ds-page">

      <Card>
        {/* Modo de entrada */}
        <Tabs
          items={[
            { id: 'text', label: t('contractsaipage.modo_texto'), icon: <FileText size={14} /> },
            { id: 'pdf',  label: t('contractsaipage.modo_pdf'),   icon: <Upload size={14} /> },
          ]}
          active={mode}
          onChange={id => setMode(id as 'text' | 'pdf')}
          className="cai-modes"
        />

        {/* Common fields */}
        <div className="cai-fields">
          <div className="u-flex1">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cai-label">
              {t('contractsaipage.proyecto_opcional')}
            </label>
            <Select suelto placeholder={false} id={`${idCampo}-1`}
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              className="cai-input"
            >
              <option value="">{t('contractsai.sin_proyecto_ad_hoc')}</option>
              {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.code} — {p.name}</option>)}
            </Select>
          </div>
          <div className="u-flex1">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cai-label">
              {t('contractsaipage.cliente_opcional')}
            </label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`}
              type="text"
              value={clientName}
              onChange={e => setClientName(e.target.value)}
              placeholder={t('contractsai.nombre_del_cliente')}
              className="cai-input"
            />
          </div>
        </div>

        {/* Input by mode */}
        {mode === 'text' ? (
          <>
            <Textarea aria-label={t('contractsai.pega_aqui_el_texto_del_contrato_minimo')} aria-describedby={`${idCampo}-contador`} value={text} onChange={e => setText(e.target.value)} placeholder={t('contractsai.pega_aqui_el_texto_del_contrato_minimo')} rows={12} inputClassName="cai-input cai-textarea" />
            <div id={`${idCampo}-contador`} className="cai-counter">
              {t('contractsaipage.n_caracteres', { count: fmtNumber(text.length, 0) })}
            </div>
          </>
        ) : (
          <div className="cai-dropzone">
            <input
              ref={selectorPdf}
              type="file"
              hidden
              accept=".pdf,application/pdf"
              aria-label={t('contractsaipage.archivo_pdf')}
              aria-describedby={`${idCampo}-pdf-hint`}
              onChange={e => setPdfFile(e.target.files?.[0] || null)}
            />
            <Button variant="secondary" icon={<Upload size={14} />} onClick={() => selectorPdf.current?.click()}>
              {t('contractsaipage.elegir_pdf')}
            </Button>
            {pdfFile && (
              <div className="cai-file cai-ico">
                <Paperclip size={13} aria-hidden="true" />{t('contractsaipage.archivo_kb', { name: pdfFile.name, kb: fmtNumber(Math.round(pdfFile.size / 1024), 0) })}
              </div>
            )}
            <div id={`${idCampo}-pdf-hint`} className="cai-file-hint">
              {t('contractsai.max_10_mb_solo_pdfs_con_texto')}
            </div>
          </div>
        )}

        <div className="cai-submit">
          <Button
            variant="primary"
            icon={<Sparkles size={14} />}
            loading={isAnalyzing}
            disabled={!canSubmit || isAnalyzing}
            onClick={() => (mode === 'text' ? analyzeText() : analyzePdf())}
          >
            {isAnalyzing ? t('contractsaipage.analizando') : t('contractsaipage.analizar')}
          </Button>
        </div>
      </Card>

      {/* Historial */}
      <div>
      <h3 className="cai-heading">
        {t('contractsai.analisis_recientes')}{initialProjectId ? ` ${t('contractsaipage.este_proyecto')}` : ''}
      </h3>
      {isLoading ? (
        <Spinner />
      ) : contracts.length === 0 ? (
        <EmptyState icon={<FileText size={28} />} title={t('contractsai.aun_no_hay_contratos_analizados')} description={t('contractsaipage.vacio_desc')} />
      ) : (
        <div className="u-stack-8">
          {contracts.map((c) => (
            <Card key={c.id}
              onClick={() => setOpenContractId(c.id)}
              className="cai-item"
            >
              <div className="cai-item__icon" aria-hidden="true"><FileText size={18} /></div>
              <div className="u-flex1-min0">
                <div className="cai-item__name">{c.filename === NOMBRE_TEXTO_PEGADO ? t('contractsaipage.texto_pegado') : (c.filename || t('contractsaipage.sin_nombre'))}</div>
                <div className="u-text3-sm">
                  {c.client_name || '—'} · {fmtDateTime(c.created_at)}
                  {' · '}{c.clauses_count} {t('contractsai.clausulas')}
                  {(c.at_risk_clauses ?? 0) > 0 && (
                    <span className="cai-at-risk">
                      {' · '}{t('contractsaipage.n_en_riesgo', { count: c.at_risk_clauses ?? 0 })}
                    </span>
                  )}
                </div>
              </div>
              {c.risk_level && (
                <span className="cai-risk cai-risk--list" style={riskVar(c.risk_level)}>
                  {nivel(c.risk_level)}
                </span>
              )}
              {c.status === 'analyzing' && (
                <span className="cai-flag cai-flag--accent">{t('contractsaipage.procesando')}</span>
              )}
              {c.status === 'failed' && (
                <span className="cai-flag cai-flag--danger">{t('contractsai.fallo')}</span>
              )}
            </Card>
          ))}
        </div>
      )}
      </div>

      <ContractDetailPanel
        contractId={openContractId}
        onClose={() => setOpenContractId(null)}
      />
      </div>
    </PageShell>
  )
}
