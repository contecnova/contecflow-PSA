/**
 * ImportPage — Importación masiva de datos desde CSV/Excel
 */
import { useState, useRef, useEffect, useId } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { importApi } from '../services/api'
import type { ErrorDeFilaImportada, ResultadoDeImportacion, ValidacionDeImportacion } from '../services/api/tipos-plataforma'
import { Button } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Upload } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { CLOCK_TICK_MS } from '../constants/timings'
import './ImportPage.css'

/** La validacion; si la peticion falla, un error sin fila. */
type ImportValidation = Omit<ValidacionDeImportacion, 'errors'> & { errors: Array<Partial<ErrorDeFilaImportada> & { error: string }> }
/** El resultado o el error que se pinta en su lugar. */
type ImportResult = Partial<ResultadoDeImportacion> & { error?: string }


const card: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12 }

// ── Import Tab ────────────────────────────────────────────────────────────────
function ImportTab() {
  const idCampo = useId()
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
    }, CLOCK_TICK_MS)
    return () => clearInterval(id)
  }, [opStartedAt])

  const { data: template } = useQuery({
    queryKey: ['import-template', entityType],
    queryFn: () => importApi.template(entityType).then(r => r.data),
  })
  const { data: jobs = [] } = useQuery({
    queryKey: ['import-jobs'],
    queryFn: () => importApi.jobs().then(r => r.data),
  })

  const validateFile = async (file: File) => {
    setValidating(true)
    setOpStage('validating')
    setOpStartedAt(Date.now())
    try {
      const fd = new FormData(); fd.append('file', file)
      const resp = await importApi.validate(entityType, fd)
      setValidation(resp.data); setStep('validate')
      setOpStage(resp.data?.valid ? 'done' : 'failed')
    } catch(e) {
      const _raw = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      const _msg = Array.isArray(_raw)
        ? _raw.map((d) => String((d as { msg?: unknown }).msg ?? '')).join(', ')
        : String(_raw || t('pagina_impt.error_al_procesar_el_fichero'))
      setValidation({ valid: false, errors: [{ error: _msg }], warnings: [], preview: [], total_rows: 0 })
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
      const resp = await importApi.execute(entityType, fd)
      setResult(resp.data); setStep('result')
      setOpStage(resp.data?.status === 'failed' ? 'failed' : 'done')
    } catch(e) {
      const _raw2 = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setResult({
        status: 'failed',
        error: Array.isArray(_raw2)
          ? _raw2.map((d) => String((d as { msg?: unknown }).msg ?? '')).join(', ')
          : String(_raw2 || t('pagina_impt.error_en_la_importacion'))
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
      <div className="impt-grid">
        {/* Import panel */}
        <div>
          <div className="import-page-e1">
            <div className="impt-box">{t('import_data.title_panel')}</div>

            <div className="u-mb-16">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="import-page-e8">{t('import_data.type_label')}</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={entityType} onChange={e => { setEntityType(e.target.value); setStep('select'); setValidation(null); setResult(null) }} className="import-page-e9">
                {Object.entries(ENTITY_LABELS).map(([v,l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            {template && (
              <div className="impt-card">
                <div className="impt-box-2">{t('import_data.csv_columns')}</div>
                <div className="impt-box-3">
                  {template.columns.join(' | ')}
                </div>
                <button onClick={downloadTemplate}
                  className="impt-btn">
                  ⬇ {t('import_data.download_template')}
                </button>
              </div>
            )}

            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="import-page-e8">{t('import_data.file_label')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} ref={fileRef} type="file" accept=".csv,.txt"
                onChange={e => { if(e.target.files![0]) { setStep('select'); setValidation(null); setResult(null) } }}
                className="import-page-e2" />
            </div>

            <div className="impt-row">
              {(validating || importing || opStage === 'failed' || opStage === 'done') && (
                <div className="impt-row-2 import-page-e3" style={{ '--import-page-color': validating || importing ? 'var(--warning)' : opStage === 'failed' ? 'var(--danger)' : 'var(--success)' } as CSSProperties}>
                  <span>
                    {validating ? t('import_data.validating') : importing ? t('import_data.importing') : opStage === 'failed' ? t('import_data.failed') : t('import_data.completed')}
                  </span>
                  {(validating || importing) && <span className="u-text3">{opElapsed}s</span>}
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
            <div className="import-page-e4">
              <div className={`impt-box-4 ${validation.valid ? 'importpa-sx1' : 'importpa-sx2'}`}>
                {validation.valid ? t('import_data.file_valid') : t('import_data.validation_errors')}
              </div>
              <div className="impt-box-5">{validation.total_rows} {t('import_data.rows_detected')}</div>
              {validation.warnings?.map((w,i) => <div key={i} className="impt-card-2">⚠ {t('import_data.warning')} {w}</div>)}
              {validation.errors?.map((e,i) => <div key={i} className="impt-card-3">✗ {e.row != null && `${t('import_data.row')} ${e.row}: `}{e.error}</div>)}
              {(validation.preview ?? []).length > 0 && (
                <div className="impt-box-6">
                  <div className="impt-box-7">{t('import_data.preview')}</div>
                  <div className="u-scroll-x">
                    <table className="impt-table">
                      <thead><tr>{Object.keys((validation.preview ?? [])[0] || {}).map(k => <th key={k} className="impt-th">{k}</th>)}</tr></thead>
                      <tbody>
                        {(validation.preview ?? []).map((row,i) => <tr key={i}>{Object.values(row).map((v,j) => <td key={j} className="impt-td">{String(v).slice(0,30)}</td>)}</tr>)}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Import result */}
          {result && step === 'result' && (
            <div className="import-page-e7" style={{ '--import-page-border': `1px solid ${(result.succeeded ?? 0)>0?'var(--success-border)':'var(--danger-border)'}` } as CSSProperties}>
              <div className={`impt-box-8 ${(result.succeeded ?? 0)>0 ? 'importpa-sx1' : 'importpa-sx2'}`}>
                {(result.succeeded ?? 0) > 0 ? t('import_data.import_completed') : t('import_data.import_failed')}
              </div>
              <div className="impt-grid-2">
                {[
                  { label: t('import_data.total'), value: result.total ?? 0, color: 'var(--text-2)' },
                  { label: t('import_data.imported'), value: result.succeeded ?? 0, color: 'var(--success)' },
                  { label: t('import_data.errors'), value: result.failed ?? 0, color: 'var(--danger)' }
                ].map((item) => (
                  <div key={item.label} className="impt-card-4">
                    <div className="impt-box-9 import-page-e3" style={{ '--import-page-color': item.color } as CSSProperties}>{item.value}</div>
                    <div className="u-text2-xs">{item.label}</div>
                  </div>
                ))}
              </div>
              {result.errors?.map((e,i) => <div key={i} className="impt-box-10">{t('import_data.row')} {e.row}: {e.error}</div>)}
            </div>
          )}
        </div>

        {/* Import history */}
        <div className="import-page-e5">
          <div className="impt-box-11">{t('import_data.import_history')}</div>
          {jobs.length === 0 ? <div className="impt-box-12">{t('import_data.no_imports')}</div> : (
            jobs.slice(0,10).map(j => (
              <div key={j.id} className="impt-grid-3">
                <span className="impt-label import-page-e6" style={{ '--import-page-background': j.status==='completed'?'var(--success-bg)':j.status==='partial'?'var(--warning-bg)':'var(--danger-bg)', '--import-page-color': j.status==='completed'?'var(--success)':j.status==='partial'?'var(--warning)':'var(--danger)' } as CSSProperties}>
                  {j.status}
                </span>
                <div>
                  <div className="impt-box-13">{ENTITY_LABELS[j.entity_type as keyof typeof ENTITY_LABELS]||j.entity_type}</div>
                  <div className="u-text3-xs">{j.filename} · {j.started_at}</div>
                </div>
                <span className="impt-label-2">{j.succeeded}/{j.total_rows}</span>
                <span className="impt-label-3">{(j.failed_rows ?? 0)>0?`${j.failed_rows} ${t('import_data.err')}`:''}</span>
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
