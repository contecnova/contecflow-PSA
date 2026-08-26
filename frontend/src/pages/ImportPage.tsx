/**
 * ImportPage — Importación masiva de datos desde CSV/Excel
 */
import { useState, useRef, useEffect } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { importApi } from '../services/api'
import { Button } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Upload } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

interface ImportTemplate {
  columns: string[]
  example: Array<Array<string | number>>
}

interface ImportValidation {
  valid?: boolean
  warnings?: string[]
  errors?: Array<{ row?: number; error?: string }>
  preview?: Array<Record<string, unknown>>
  total_rows?: number
}

interface ImportResult {
  status?: string
  total?: number
  total_rows?: number
  succeeded?: number
  failed?: number
  failed_rows?: number
  errors?: Array<{ row?: number; error?: string }>
  error?: string
}

interface ImportJob {
  id: string | number
  status?: string
  entity_type?: string
  filename?: string
  started_at?: string
  succeeded?: number
  total_rows?: number
  failed_rows?: number
}


const fs: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12 }

// ── Import Tab ────────────────────────────────────────────────────────────────
function ImportTab() {
  const t = useAppT()
  const [entityType, setEntityType] = useState('projects')
  const [step, setStep] = useState<'select' | 'validate' | 'result'>('select')
  const [validating, setValidating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [validation, setValidation] = useState<ImportValidation | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [opStage, setOpStage] = useState<'idle' | 'validating' | 'importing' | 'done' | 'failed'>('idle')
  const [opStartedAt, setOpStartedAt] = useState<number | null>(null)
  const [opElapsed, setOpElapsed] = useState(0)
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!opStartedAt) {
      setOpElapsed(0)
      return
    }
    const id = setInterval(() => {
      setOpElapsed(Math.floor((Date.now() - opStartedAt) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [opStartedAt])

  const { data: template } = useQuery<ImportTemplate>({
    queryKey: ['import-template', entityType],
    queryFn: () => importApi.template(entityType).then(r => r.data),
  })
  const { data: jobs = [] } = useQuery<ImportJob[]>({
    queryKey: ['import-jobs'],
    queryFn: () => importApi.jobs().then(r => r.data),
  })

  const validateFile = async (file: File) => {
    setValidating(true)
    setOpStage('validating')
    setOpStartedAt(Date.now())
    try {
      const fd = new FormData(); fd.append('file', file)
      const resp = await importApi.validate(entityType, fd as unknown as Record<string, unknown>)
      setValidation(resp.data); setStep('validate')
      setOpStage(resp.data?.valid ? 'done' : 'failed')
    } catch(e) {
      const _raw = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      const _msg = Array.isArray(_raw)
        ? _raw.map((d) => String((d as { msg?: unknown }).msg ?? '')).join(', ')
        : String(_raw || 'Error al procesar el fichero')
      setValidation({ valid: false, errors: [{error: _msg}], warnings: [], preview: [], total_rows: 0 })
      setStep('validate')
      setOpStage('failed')
    } finally { setValidating(false) }
  }

  const doImport = async () => {
    if (!fileRef.current?.files![0]) return
    setImporting(true)
    setOpStage('importing')
    setOpStartedAt(Date.now())
    try {
      const fd = new FormData(); fd.append('file', fileRef.current.files![0])
      const resp = await importApi.execute(entityType, fd as unknown as Record<string, unknown>)
      setResult(resp.data); setStep('result')
      setOpStage(resp.data?.status === 'failed' ? 'failed' : 'done')
    } catch(e) {
      const _raw2 = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setResult({
        status: 'failed',
        error: Array.isArray(_raw2)
          ? _raw2.map((d) => String((d as { msg?: unknown }).msg ?? '')).join(', ')
          : String(_raw2 || 'Error en la importación')
      })
      setStep('result')
      setOpStage('failed')
    } finally { setImporting(false) }
  }

  const ENTITY_LABELS = {
    projects: t('import_data.entity_projects'),
    tasks: t('import_data.entity_tasks'),
    users: t('import_data.entity_users'),
    imputations: t('import_data.entity_imputations'),
    expenses: t('import_data.entity_expenses')
  }

  const downloadTemplate = () => {
    if (!template) return
    const csv = [template.columns.join(','), template.example.map(r => r.join(',')).join('\n')].join('\n')
    const blob = new Blob([csv], {type:'text/csv'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `plantilla_${entityType}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:24}}>
        {/* Import panel */}
        <div>
          <div style={{...card,padding:'20px 24px',marginBottom:20}}>
            <div style={{fontSize: "var(--text-md)",fontWeight:700,marginBottom:16}}>{t('import_data.title_panel')}</div>

            <div style={{marginBottom:16}}>
              <label style={ls}>{t('import_data.type_label')}</label>
              <select value={entityType} onChange={e => { setEntityType(e.target.value); setStep('select'); setValidation(null); setResult(null) }} style={fs}>
                {Object.entries(ENTITY_LABELS).map(([v,l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            {template && (
              <div style={{background:'var(--surface-3)',borderRadius:8,padding:'12px 16px',marginBottom:16,fontSize: "var(--text-sm)"}}>
                <div style={{fontWeight:700,color:'var(--text-2)',marginBottom:6,textTransform:'uppercase',fontSize: "var(--text-2xs)",letterSpacing:'0.06em'}}>{t('import_data.csv_columns')}</div>
                <div style={{color:'var(--text-2)',fontFamily:'var(--font-mono)',fontSize: "var(--text-xs)",lineHeight:1.8}}>
                  {template.columns.join(' | ')}
                </div>
                <button onClick={downloadTemplate}
                  style={{marginTop:10,background:'transparent',border:'1px solid var(--accent-border-strong)',borderRadius:6,padding:'5px 12px',color:'var(--accent)',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>
                  ⬇ {t('import_data.download_template')}
                </button>
              </div>
            )}

            <div>
              <label style={ls}>{t('import_data.file_label')}</label>
              <input ref={fileRef} type="file" accept=".csv,.txt"
                onChange={e => { if(e.target.files![0]) { setStep('select'); setValidation(null); setResult(null) } }}
                style={{...fs,padding:'7px'}} />
            </div>

            <div style={{display:'flex',gap:10,marginTop:16}}>
              {(validating || importing || opStage === 'failed' || opStage === 'done') && (
                <div style={{
                  marginRight: 8,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: "var(--text-sm)",
                  color: validating || importing ? 'var(--warning)' : opStage === 'failed' ? 'var(--danger)' : 'var(--success)'
                }}>
                  <span>
                    {validating ? t('import_data.validating') : importing ? t('import_data.importing') : opStage === 'failed' ? t('import_data.failed') : t('import_data.completed')}
                  </span>
                  {(validating || importing) && <span style={{ color: 'var(--text-3)' }}>{opElapsed}s</span>}
                </div>
              )}
              <Button onClick={() => { if(fileRef.current?.files![0]) validateFile(fileRef.current.files![0]) }} disabled={validating}>
                {validating ? t('import_data.validating_btn') : t('import_data.validate_btn')}
              </Button>
              {step === 'validate' && validation?.valid && (
                <Button onClick={doImport} disabled={importing}>
                  {importing ? t('import_data.importing_btn') : t('import_data.import_btn')}
                </Button>
              )}
            </div>
          </div>

          {/* Validation results */}
          {validation && step === 'validate' && (
            <div style={{...card,padding:'16px 20px'}}>
              <div style={{fontSize: "var(--text-base)",fontWeight:700,color:validation.valid?'var(--success)':'var(--danger)',marginBottom:12}}>
                {validation.valid ? t('import_data.file_valid') : t('import_data.validation_errors')}
              </div>
              <div style={{fontSize: "var(--text-sm)",color:'var(--text-2)',marginBottom:10}}>{validation.total_rows} {t('import_data.rows_detected')}</div>
              {validation.warnings?.map((w,i) => <div key={i} style={{background:'var(--warning-bg)',border:'1px solid var(--warning-border)',borderRadius:6,padding:'6px 10px',color:'var(--warning)',fontSize: "var(--text-sm)",marginBottom:6}}>⚠ {t('import_data.warning')} {w}</div>)}
              {validation.errors?.map((e,i) => <div key={i} style={{background:'var(--danger-bg)',border:'1px solid var(--danger-border)',borderRadius:6,padding:'6px 10px',color:'var(--danger)',fontSize: "var(--text-sm)",marginBottom:6}}>✗ {t('import_data.row')} {e.row}: {e.error}</div>)}
              {(validation.preview ?? []).length > 0 && (
                <div style={{marginTop:12,fontSize: "var(--text-xs)",color:'var(--text-2)'}}>
                  <div style={{fontWeight:700,marginBottom:6}}>{t('import_data.preview')}</div>
                  <div style={{overflowX:'auto'}}>
                    <table style={{borderCollapse:'collapse',fontSize: "var(--text-xs)"}}>
                      <thead><tr>{Object.keys((validation.preview ?? [])[0] || {}).map(k => <th key={k} style={{padding:'4px 8px',borderBottom:'1px solid var(--surface-4)',textAlign:'left',color:'var(--text-3)',whiteSpace:'nowrap'}}>{k}</th>)}</tr></thead>
                      <tbody>
                        {(validation.preview ?? []).map((row,i) => <tr key={i}>{Object.values(row).map((v,j) => <td key={j} style={{padding:'4px 8px',borderBottom:'1px solid var(--surface-4)20',color:'var(--text-1)',whiteSpace:'nowrap'}}>{String(v).slice(0,30)}</td>)}</tr>)}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Import result */}
          {result && step === 'result' && (
            <div style={{...card,padding:'16px 20px',border:`1px solid ${(result.succeeded ?? 0)>0?'rgba(52,211,153,0.25)':'rgba(248,113,113,0.25)'}`}}>
              <div style={{fontSize: "var(--text-md)",fontWeight:700,color:(result.succeeded ?? 0)>0?'var(--success)':'var(--danger)',marginBottom:12}}>
                {(result.succeeded ?? 0) > 0 ? t('import_data.import_completed') : t('import_data.import_failed')}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12,marginBottom:12}}>
                {[
                  { label: t('import_data.total'), value: result.total ?? result.total_rows ?? 0, color: 'var(--text-2)' },
                  { label: t('import_data.imported'), value: result.succeeded ?? 0, color: 'var(--success)' },
                  { label: t('import_data.errors'), value: result.failed ?? result.failed_rows ?? 0, color: 'var(--danger)' }
                ].map((item) => (
                  <div key={item.label} style={{textAlign:'center',background:'var(--surface-3)',borderRadius:8,padding:'12px'}}>
                    <div style={{fontSize: "var(--text-2xl)",fontWeight:800,color:item.color}}>{item.value}</div>
                    <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)'}}>{item.label}</div>
                  </div>
                ))}
              </div>
              {result.errors?.map((e,i) => <div key={i} style={{fontSize: "var(--text-sm)",color:'var(--danger)',padding:'3px 0'}}>{t('import_data.row')} {e.row}: {e.error}</div>)}
            </div>
          )}
        </div>

        {/* Import history */}
        <div style={{...card,overflow:'hidden',alignSelf:'start'}}>
          <div style={{padding:'14px 18px',borderBottom:'1px solid var(--surface-4)',fontSize: "var(--text-base)",fontWeight:700}}>{t('import_data.import_history')}</div>
          {jobs.length === 0 ? <div style={{padding:'24px',textAlign:'center',color:'var(--text-3)',fontSize: "var(--text-base)"}}>{t('import_data.no_imports')}</div> : (
            jobs.slice(0,10).map(j => (
              <div key={j.id} style={{display:'grid',gridTemplateColumns:'80px 1fr 80px 60px',gap:10,padding:'10px 18px',borderBottom:'1px solid var(--surface-4)20',alignItems:'center'}}>
                <span style={{fontSize: "var(--text-xs)",fontWeight:700,padding:'2px 6px',borderRadius:4,background:j.status==='completed'?'var(--success-bg)':j.status==='partial'?'var(--warning-bg)':'var(--danger-bg)',color:j.status==='completed'?'var(--success)':j.status==='partial'?'var(--warning)':'var(--danger)'}}>
                  {j.status}
                </span>
                <div>
                  <div style={{fontSize: "var(--text-sm)",fontWeight:600}}>{ENTITY_LABELS[j.entity_type as keyof typeof ENTITY_LABELS]||j.entity_type}</div>
                  <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{j.filename} · {j.started_at}</div>
                </div>
                <span style={{fontSize: "var(--text-sm)",color:'var(--text-2)',textAlign:'right'}}>{j.succeeded}/{j.total_rows}</span>
                <span style={{fontSize: "var(--text-xs)",color:'var(--danger)'}}>{(j.failed_rows ?? 0)>0?`${j.failed_rows} ${t('import_data.err')}`:''}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default function ImportPage(): JSX.Element {
  const t = useAppT()
  return (
    <PageShell>
      <PageHeader icon={<Upload size={18} />} title={t('import_data.title')} subtitle={t('import_data.subtitle')} showListExport={false} />
      <ImportTab />
    </PageShell>
  )
}
