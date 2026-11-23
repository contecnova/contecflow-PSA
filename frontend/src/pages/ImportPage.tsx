/**
 * ImportPage — Importación masiva de datos desde CSV/Excel
 */
import { useState, useRef, useEffect, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { importApi } from '../services/api'
import type { ErrorDeFilaImportada, ResultadoDeImportacion, ValidacionDeImportacion } from '../services/api/tipos-plataforma'
import { Button, Card, EmptyState, KpiCard, Page, StatusBadge, Select, TablaSimple } from '../components/ui'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { AlertTriangle, CheckCircle2, Download, FileSearch, FileUp, History, Loader2, Upload, XCircle } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { CLOCK_TICK_MS } from '../constants/timings'
import './ImportPage.css'

/** La validacion; si la peticion falla, un error sin fila. */
type ImportValidation = Omit<ValidacionDeImportacion, 'errors'> & { errors: Array<Partial<ErrorDeFilaImportada> & { error: string }> }
/** El resultado o el error que se pinta en su lugar. */
type ImportResult = Partial<ResultadoDeImportacion> & { error?: string }



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
  const [nombreFichero, setNombreFichero] = useState('')

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
      // 23-11-2026: extractErr traduce los códigos del servidor y los errores de validación (antes `String(detail)`).
      const _msg = extractErr(e, t('pagina_impt.error_al_procesar_el_fichero'))
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
      setResult({
        status: 'failed',
        error: extractErr(e, t('pagina_impt.error_en_la_importacion')),
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

  const ESTADO_KIND: Record<string, StatusBadgeKind> = { completed: 'success', partial: 'warning', failed: 'danger' }

  return (
    <div>
      <div className="impt-grid">
        {/* Import panel */}
        <div className="u-stack-16">
          <Card>
            <div className="impt-box">{t('import_data.title_panel')}</div>

            <div className="u-mb-16">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="import-page-e8">{t('import_data.type_label')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={entityType} onChange={e => { setEntityType(e.target.value); setStep('select'); setValidation(null); setResult(null) }} className="import-page-e9">
                {Object.entries(ENTITY_LABELS).map(([v,l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </div>

            {template && (
              <div className="impt-card">
                <div className="impt-box-2">{t('import_data.csv_columns')}</div>
                <div className="ds-codigo impt-box-3">
                  {template.columns.join(' | ')}
                </div>
                <div className="impt-plantilla">
                  <Button size="sm" variant="secondary" icon={<Download size={14} />} onClick={downloadTemplate}>
                    {t('import_data.download_template')}
                  </Button>
                </div>
              </div>
            )}

            <div>
              <span id={`${idCampo}-et2`} className="import-page-e8">{t('import_data.file_label')}</span>
              {/* Selector de fichero nativo oculto: se abre con el botón y se muestra el nombre elegido. */}
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} ref={fileRef} type="file" accept=".csv,.txt"
                onChange={e => {
                  const f = e.target.files?.[0]
                  setNombreFichero(f?.name ?? '')
                  if (f) { setStep('select'); setValidation(null); setResult(null) }
                }}
                className="u-sr-only" tabIndex={-1} />
              <div className="impt-fichero">
                <Button variant="secondary" icon={<FileUp size={14} />} onClick={() => fileRef.current?.click()}>
                  {t('import_data.elegir_fichero')}
                </Button>
                <span className={`impt-fichero__nombre ${nombreFichero ? '' : 'impt-fichero__nombre--vacio'}`}>
                  {nombreFichero || t('import_data.ningun_fichero')}
                </span>
              </div>
            </div>

            <div className="impt-row">
              {(validating || importing || opStage === 'failed' || opStage === 'done') && (
                <div className={`impt-row-2 ${validating || importing ? 'impt-estado--curso' : opStage === 'failed' ? 'impt-estado--mal' : 'impt-estado--bien'}`}>
                  {validating || importing ? <Loader2 size={14} className="impt-girando" aria-hidden />
                    : opStage === 'failed' ? <XCircle size={14} aria-hidden /> : <CheckCircle2 size={14} aria-hidden />}
                  <span>
                    {validating ? t('import_data.validating') : importing ? t('import_data.importing') : opStage === 'failed' ? t('import_data.failed') : t('import_data.completed')}
                  </span>
                  {(validating || importing) && <span className="u-text3">{opElapsed}s</span>}
                </div>
              )}
              <Button variant={step === 'validate' && validation?.valid ? 'secondary' : 'primary'} icon={<FileSearch size={14} />}
                onClick={() => { if(fileRef.current?.files?.[0]) validateFile(fileRef.current.files[0]) }}
                disabled={!nombreFichero} loading={validating}>
                {validating ? t('import_data.validating_btn') : t('import_data.validate_btn')}
              </Button>
              {step === 'validate' && validation?.valid && (
                <Button icon={<Upload size={14} />} onClick={doImport} loading={importing}>
                  {importing ? t('import_data.importing_btn') : t('import_data.import_btn')}
                </Button>
              )}
            </div>
          </Card>

          {/* Validation results */}
          {validation && step === 'validate' && (
            <Card>
              <div className={`impt-box-4 ${validation.valid ? 'importpa-sx1' : 'importpa-sx2'}`}>
                {validation.valid ? <CheckCircle2 size={16} aria-hidden /> : <XCircle size={16} aria-hidden />}
                {validation.valid ? t('import_data.file_valid') : t('import_data.validation_errors')}
              </div>
              <div className="impt-box-5">{validation.total_rows} {t('import_data.rows_detected')}</div>
              {validation.warnings?.map((w,i) => <div key={i} className="impt-card-2"><AlertTriangle size={14} aria-hidden /><span>{t('import_data.warning')} {w}</span></div>)}
              {validation.errors?.map((e,i) => <div key={i} className="impt-card-3"><XCircle size={14} aria-hidden /><span>{e.row != null && `${t('import_data.row')} ${e.row}: `}{e.error}</span></div>)}
              {(validation.preview ?? []).length > 0 && (
                <div className="impt-box-6">
                  <div className="impt-box-7">{t('import_data.preview')}</div>
                  <div className="u-scroll-x">
                    <TablaSimple claseTabla="impt-table">
                      <thead><tr>{Object.keys((validation.preview ?? [])[0] || {}).map(k => <th key={k} className="impt-th">{k}</th>)}</tr></thead>
                      <tbody>
                        {(validation.preview ?? []).map((row,i) => <tr key={i}>{Object.values(row).map((v,j) => <td key={j} className="impt-td">{String(v).slice(0,30)}</td>)}</tr>)}
                      </tbody>
                    </TablaSimple>
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Import result */}
          {result && step === 'result' && (
            <Card>
              <div className={`impt-box-8 ${(result.succeeded ?? 0)>0 ? 'importpa-sx1' : 'importpa-sx2'}`}>
                {(result.succeeded ?? 0) > 0 ? <CheckCircle2 size={16} aria-hidden /> : <XCircle size={16} aria-hidden />}
                {(result.succeeded ?? 0) > 0 ? t('import_data.import_completed') : t('import_data.import_failed')}
              </div>
              <div className="ds-grid-stats impt-kpis">
                <KpiCard label={t('import_data.total')} value={result.total ?? 0} />
                <KpiCard label={t('import_data.imported')} value={result.succeeded ?? 0} accent />
                <KpiCard label={t('import_data.errors')} value={result.failed ?? 0} danger={(result.failed ?? 0) > 0} />
              </div>
              {result.error && <div className="impt-box-10">{result.error}</div>}
              {result.errors?.map((e,i) => <div key={i} className="impt-box-10">{t('import_data.row')} {e.row}: {e.error}</div>)}
            </Card>
          )}
        </div>

        {/* Import history */}
        <div className="import-page-e5">
          <div className="impt-box-11">{t('import_data.import_history')}</div>
          {jobs.length === 0 ? (
            <EmptyState icon={<History size={28} />} title={t('import_data.no_imports')} />
          ) : (
            jobs.slice(0,10).map(j => (
              <div key={j.id} className="impt-grid-3">
                <StatusBadge kind={ESTADO_KIND[j.status ?? ''] ?? 'neutral'} caps={false}>
                  {etiquetaCodigo(t, 'import_data.estado', j.status)}
                </StatusBadge>
                <div className="u-min0">
                  <div className="impt-box-13">{ENTITY_LABELS[j.entity_type as keyof typeof ENTITY_LABELS]||j.entity_type}</div>
                  <div className="u-text3-xs impt-corta">{j.filename} · {fmtDateTime(j.started_at)}</div>
                </div>
                <span className="impt-label-2">{j.succeeded}/{j.total_rows}</span>
                <span className="impt-label-3">{(j.failed_rows ?? 0) > 0 ? t('import_data.con_errores', { n: j.failed_rows ?? 0 }) : ''}</span>
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
    <Page icon={<Upload size={18} />} title={t('nav.import')} subtitle={t('import_data.subtitle')}>
      <ImportTab />
    </Page>
  )
}
