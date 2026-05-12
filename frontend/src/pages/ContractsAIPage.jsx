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
import { useState, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contractsAIApi, projectsApi } from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import { Button, Card, Spinner, EmptyState } from '../components/ui'
import { FileText, Upload } from 'lucide-react'

const CLAUSE_TYPE_LABEL = {
  payment:       'Pagos',
  penalty:       'Penalizaciones',
  deliverable:   'Entregables',
  milestone:     'Hitos',
  sla:           'SLA',
  termination:   'Terminación',
  scope:         'Alcance',
  confidentiality: 'Confidencialidad',
}

const CLAUSE_TYPE_ICON = {
  payment:        '💰',
  penalty:        '⚠️',
  deliverable:    '📦',
  milestone:      '🚩',
  sla:            '⏱️',
  termination:    '🚪',
  scope:          '📐',
  confidentiality:'🔒',
}

const RISK_COLOR = {
  high:   'var(--danger)',
  medium: 'var(--warning)',
  low:    'var(--success)',
}


function ContractDetailPanel({ contractId, onClose }) {
  const { data, isLoading } = useQuery({
    queryKey: ['contracts-ai', contractId],
    queryFn:  () => contractsAIApi.get(contractId).then(r => r.data),
    enabled:  !!contractId,
  })

  // Agrupar cláusulas por tipo
  const groups = useMemo(() => {
    if (!data?.clauses) return {}
    const out = {}
    for (const cl of data.clauses) {
      const key = cl.clause_type || 'other'
      if (!out[key]) out[key] = []
      out[key].push(cl)
    }
    return out
  }, [data])

  if (!contractId) return null

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}>
      <div onClick={e => e.stopPropagation()}
        style={{
          width: 720, maxWidth: '95vw', height: '100%',
          background: 'var(--surface-1)', borderLeft: '1px solid var(--surface-4)',
          overflowY: 'auto', padding: '24px 28px',
        }}>
        {isLoading ? <Spinner /> : !data ? <EmptyState title="No encontrado" /> : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700 }}>
                  {data.filename || 'Análisis de contrato'}
                </h2>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginTop: 4 }}>
                  {data.client_name || '—'} · {data.created_at}
                  {data.risk_level && (
                    <span style={{
                      marginLeft: 10, padding: '2px 8px', borderRadius: 6,
                      background: 'var(--surface-3)', color: RISK_COLOR[data.risk_level] || 'var(--text-2)',
                      fontWeight: 600, fontSize: 'var(--text-xs)',
                    }}>
                      Riesgo {data.risk_level}
                    </span>
                  )}
                </div>
              </div>
              <button onClick={onClose}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', fontSize: 22, cursor: 'pointer' }}>✕</button>
            </div>

            {data.scope_summary && (
              <Card style={{ marginBottom: 16 }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--text-sm)', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-3)' }}>
                  Resumen del alcance
                </h4>
                <div style={{ fontSize: 'var(--text-base)', lineHeight: 1.5, color: 'var(--text-1)' }}>
                  {data.scope_summary}
                </div>
              </Card>
            )}

            {data.total_value != null && (
              <Card style={{ marginBottom: 16, display: 'flex', gap: 30 }}>
                <div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>Valor total</div>
                  <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>{data.total_value?.toLocaleString()} €</div>
                </div>
                {data.scope_creep_alerts > 0 && (
                  <div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>Scope creep</div>
                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--warning)' }}>
                      {data.scope_creep_alerts} alertas
                    </div>
                  </div>
                )}
              </Card>
            )}

            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, marginBottom: 12 }}>
              Cláusulas extraídas ({data.clauses?.length || 0})
            </h3>
            {Object.entries(groups).map(([type, list]) => (
              <div key={type} style={{ marginBottom: 18 }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                  {CLAUSE_TYPE_ICON[type] || '📄'} {CLAUSE_TYPE_LABEL[type] || type} ({list.length})
                </h4>
                {list.map(cl => (
                  <Card key={cl.id} style={{
                    marginBottom: 8,
                    borderColor: cl.is_at_risk ? 'var(--danger)' : 'var(--surface-4)',
                    borderWidth: cl.is_at_risk ? 2 : 1,
                  }}>
                    <div style={{ fontWeight: 700, fontSize: 'var(--text-base)', marginBottom: 4 }}>
                      {cl.is_at_risk && <span style={{ color: 'var(--danger)' }}>⚠ </span>}
                      {cl.title}
                    </div>
                    {cl.description && (
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 6 }}>
                        {cl.description}
                      </div>
                    )}
                    {cl.is_at_risk && cl.risk_reason && (
                      <div style={{
                        fontSize: 'var(--text-sm)', color: 'var(--danger)',
                        background: 'rgba(239,68,68,0.08)', padding: '6px 10px',
                        borderRadius: 6, marginBottom: 6,
                      }}>
                        🛑 {cl.risk_reason}
                      </div>
                    )}
                    {(cl.impact_amount != null || cl.due_date) && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 6 }}>
                        {cl.impact_amount != null && `Impacto: ${cl.impact_amount.toLocaleString()} €`}
                        {cl.impact_amount != null && cl.due_date && ' · '}
                        {cl.due_date && `Vencimiento: ${cl.due_date}`}
                      </div>
                    )}
                    {cl.original_text && (
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ fontSize: 'var(--text-xs)', cursor: 'pointer', color: 'var(--text-3)' }}>
                          Ver cita textual
                        </summary>
                        <blockquote style={{
                          fontSize: 'var(--text-sm)', fontStyle: 'italic',
                          color: 'var(--text-2)', borderLeft: '3px solid var(--surface-4)',
                          padding: '4px 10px', margin: '6px 0 0 0',
                        }}>
                          {cl.original_text}
                        </blockquote>
                      </details>
                    )}
                  </Card>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}


export default function ContractsAIPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const initialProjectId = params.get('project_id') || ''

  const [mode, setMode] = useState('text')         // 'text' | 'pdf'
  const [text, setText] = useState('')
  const [pdfFile, setPdfFile] = useState(null)
  const [projectId, setProjectId] = useState(initialProjectId)
  const [clientName, setClientName] = useState('')
  const [openContractId, setOpenContractId] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn:  () => projectsApi.list().then(r => r.data),
  })

  const { data: contracts = [], isLoading } = useQuery({
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
      toast.success('Contrato analizado correctamente')
      setText('')
      qc.invalidateQueries({ queryKey: ['contracts-ai'] })
    },
    onError: e => toast.error(e?.response?.data?.detail || 'Error al analizar contrato'),
  })

  const { mutate: analyzePdf, isPending: isAnalyzingPdf } = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('file', pdfFile)
      if (projectId)  fd.append('project_id', projectId)
      if (clientName) fd.append('client_name', clientName)
      return contractsAIApi.analyzePdf(fd)
    },
    onSuccess: () => {
      toast.success('PDF analizado correctamente')
      setPdfFile(null)
      qc.invalidateQueries({ queryKey: ['contracts-ai'] })
    },
    onError: e => toast.error(e?.response?.data?.detail || 'Error al analizar PDF'),
  })

  const isAnalyzing = isAnalyzingText || isAnalyzingPdf
  const canSubmit = mode === 'text' ? text.trim().length > 100 : !!pdfFile

  return (
    <div style={{ padding: '20px 24px', maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        icon={<FileText size={18} />}
        title="Contratos IA"
        subtitle="Análisis estructurado de cláusulas, riesgos y obligaciones con LLM + map-reduce"
        showListExport={false}
      />

      <Card style={{ marginBottom: 20 }}>
        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 16, borderBottom: '1px solid var(--surface-4)' }}>
          {[
            { id: 'text', label: 'Pegar texto', icon: <FileText size={14} /> },
            { id: 'pdf',  label: 'Subir PDF',   icon: <Upload size={14} /> },
          ].map(opt => (
            <button
              key={opt.id}
              onClick={() => setMode(opt.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 18px', border: 'none', cursor: 'pointer',
                borderBottom: `2px solid ${mode === opt.id ? 'var(--accent)' : 'transparent'}`,
                background: 'transparent',
                color: mode === opt.id ? 'var(--accent)' : 'var(--text-2)',
                fontWeight: 600, fontSize: 'var(--text-base)',
              }}
            >
              {opt.icon} {opt.label}
            </button>
          ))}
        </div>

        {/* Common fields */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>
              Proyecto (opcional)
            </label>
            <select
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              style={{
                width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)',
              }}
            >
              <option value="">— Sin proyecto (ad-hoc) —</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>
              Cliente (opcional)
            </label>
            <input
              type="text"
              value={clientName}
              onChange={e => setClientName(e.target.value)}
              placeholder="Nombre del cliente"
              style={{
                width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 'var(--text-sm)',
              }}
            />
          </div>
        </div>

        {/* Input by mode */}
        {mode === 'text' ? (
          <>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Pega aquí el texto del contrato. Mínimo 100 caracteres. El análisis tomará 10-30 segundos según la longitud."
              rows={12}
              style={{
                width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                borderRadius: 8, padding: '12px', color: 'var(--text-1)', fontFamily: 'var(--font-sans)',
                fontSize: 'var(--text-sm)', boxSizing: 'border-box', resize: 'vertical',
              }}
            />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6 }}>
              {text.length} caracteres
            </div>
          </>
        ) : (
          <div style={{
            border: '2px dashed var(--surface-4)', borderRadius: 10,
            padding: 32, textAlign: 'center', background: 'var(--surface-2)',
          }}>
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={e => setPdfFile(e.target.files?.[0] || null)}
              style={{ display: 'block', margin: '0 auto' }}
            />
            {pdfFile && (
              <div style={{ marginTop: 12, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                📎 {pdfFile.name} ({Math.round(pdfFile.size / 1024)} KB)
              </div>
            )}
            <div style={{ marginTop: 12, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              Máx. 10 MB. Solo PDFs con texto (no escaneados — no hay OCR).
            </div>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <Button
            variant="primary"
            disabled={!canSubmit || isAnalyzing}
            onClick={() => (mode === 'text' ? analyzeText() : analyzePdf())}
          >
            {isAnalyzing ? '⏳ Analizando…' : '🤖 Analizar con IA'}
          </Button>
        </div>
      </Card>

      {/* Historial */}
      <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, marginBottom: 12 }}>
        Análisis recientes{initialProjectId ? ' (este proyecto)' : ''}
      </h3>
      {isLoading ? (
        <Spinner />
      ) : contracts.length === 0 ? (
        <EmptyState icon="📄" title="Aún no hay contratos analizados" description="Pega texto o sube un PDF arriba para empezar." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {contracts.map(c => (
            <Card key={c.id}
              onClick={() => setOpenContractId(c.id)}
              style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14 }}
            >
              <div style={{ fontSize: 22 }}>📄</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>{c.filename || 'Sin nombre'}</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>
                  {c.client_name || '—'} · {c.created_at}
                  {' · '}{c.clauses_count} cláusulas
                  {c.at_risk_clauses > 0 && (
                    <span style={{ color: 'var(--danger)', fontWeight: 600 }}>
                      {' · '}{c.at_risk_clauses} en riesgo
                    </span>
                  )}
                </div>
              </div>
              {c.risk_level && (
                <span style={{
                  padding: '4px 10px', borderRadius: 6, fontWeight: 600,
                  fontSize: 'var(--text-xs)', textTransform: 'uppercase',
                  background: 'var(--surface-3)', color: RISK_COLOR[c.risk_level] || 'var(--text-2)',
                }}>
                  {c.risk_level}
                </span>
              )}
              {c.status === 'analyzing' && (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>⏳ procesando</span>
              )}
              {c.status === 'failed' && (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>✗ falló</span>
              )}
            </Card>
          ))}
        </div>
      )}

      <ContractDetailPanel
        contractId={openContractId}
        onClose={() => setOpenContractId(null)}
      />
    </div>
  )
}
