/**
 * ImportPage — Importación masiva de datos desde CSV/Excel
 */
import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Button } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12 }

// ── Import Tab ────────────────────────────────────────────────────────────────
function ImportTab() {
  const [entityType, setEntityType] = useState('projects')
  const [step, setStep] = useState('select') // select | validate | result
  const [validating, setValidating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [validation, setValidation] = useState(null)
  const [result, setResult] = useState(null)
  const [opStage, setOpStage] = useState('idle') // idle | validating | importing | done | failed
  const [opStartedAt, setOpStartedAt] = useState(null)
  const [opElapsed, setOpElapsed] = useState(0)
  const fileRef = useRef(null)

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

  const { data: template } = useQuery({
    queryKey: ['import-template', entityType],
    queryFn: () => api.get(`/import/template/${entityType}`).then(r => r.data),
  })
  const { data: jobs = [] } = useQuery({
    queryKey: ['import-jobs'],
    queryFn: () => api.get('/import/jobs').then(r => r.data),
  })

  const validateFile = async (file) => {
    setValidating(true)
    setOpStage('validating')
    setOpStartedAt(Date.now())
    try {
      const fd = new FormData(); fd.append('file', file)
      const resp = await api.post(`/import/validate?entity_type=${entityType}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setValidation(resp.data); setStep('validate')
      setOpStage(resp.data?.valid ? 'done' : 'failed')
    } catch(e) {
      const _raw = e.response?.data?.detail
      const _msg = Array.isArray(_raw) ? _raw.map(d => d.msg).join(', ') : (_raw || 'Error al procesar el fichero')
      setValidation({ valid: false, errors: [{error: _msg}], warnings: [], preview: [], total_rows: 0 })
      setStep('validate')
      setOpStage('failed')
    } finally { setValidating(false) }
  }

  const doImport = async () => {
    if (!fileRef.current?.files[0]) return
    setImporting(true)
    setOpStage('importing')
    setOpStartedAt(Date.now())
    try {
      const fd = new FormData(); fd.append('file', fileRef.current.files[0])
      const resp = await api.post(`/import/execute?entity_type=${entityType}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setResult(resp.data); setStep('result')
      setOpStage(resp.data?.status === 'failed' ? 'failed' : 'done')
    } catch(e) {
      const _raw2 = e.response?.data?.detail
      setResult({ status: 'failed', error: Array.isArray(_raw2) ? _raw2.map(d => d.msg).join(', ') : (_raw2 || 'Error en la importación') })
      setStep('result')
      setOpStage('failed')
    } finally { setImporting(false) }
  }

  const ENTITY_LABELS = { projects:'Proyectos', tasks:'Tareas', users:'Usuarios', imputations:'Imputaciones', expenses:'Gastos' }

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
            <div style={{fontSize:14,fontWeight:700,marginBottom:16}}>Importación masiva desde CSV</div>

            <div style={{marginBottom:16}}>
              <label style={ls}>Tipo de datos</label>
              <select value={entityType} onChange={e => { setEntityType(e.target.value); setStep('select'); setValidation(null); setResult(null) }} style={fs}>
                {Object.entries(ENTITY_LABELS).map(([v,l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            {template && (
              <div style={{background:'var(--surface-3)',borderRadius:8,padding:'12px 16px',marginBottom:16,fontSize:12}}>
                <div style={{fontWeight:700,color:'var(--text-2)',marginBottom:6,textTransform:'uppercase',fontSize:10,letterSpacing:'0.06em'}}>Columnas del CSV</div>
                <div style={{color:'var(--text-2)',fontFamily:'monospace',fontSize:11,lineHeight:1.8}}>
                  {template.columns.join(' | ')}
                </div>
                <button onClick={downloadTemplate}
                  style={{marginTop:10,background:'transparent',border:'1px solid #00d4ff40',borderRadius:6,padding:'5px 12px',color:'var(--accent)',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
                  ⬇ Descargar plantilla CSV
                </button>
              </div>
            )}

            <div>
              <label style={ls}>Fichero CSV</label>
              <input ref={fileRef} type="file" accept=".csv,.txt"
                onChange={e => { if(e.target.files[0]) { setStep('select'); setValidation(null); setResult(null) } }}
                style={{...fs,padding:'7px'}} />
            </div>

            <div style={{display:'flex',gap:10,marginTop:16}}>
              {(validating || importing || opStage === 'failed' || opStage === 'done') && (
                <div style={{
                  marginRight: 8,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 12,
                  color: validating || importing ? 'var(--warning)' : opStage === 'failed' ? 'var(--danger)' : 'var(--success)'
                }}>
                  <span>
                    {validating ? '⏳ Validando fichero…' : importing ? '⏳ Importación en curso…' : opStage === 'failed' ? '✗ Operación fallida' : '✓ Operación completada'}
                  </span>
                  {(validating || importing) && <span style={{ color: 'var(--text-3)' }}>{opElapsed}s</span>}
                </div>
              )}
              <Button onClick={() => { if(fileRef.current?.files[0]) validateFile(fileRef.current.files[0]) }} disabled={validating}>
                {validating ? '⟳ Validando...' : '🔍 Validar fichero'}
              </Button>
              {step === 'validate' && validation?.valid && (
                <Button onClick={doImport} disabled={importing}>
                  {importing ? '⟳ Importando...' : '⬆ Importar'}
                </Button>
              )}
            </div>
          </div>

          {/* Validation results */}
          {validation && step === 'validate' && (
            <div style={{...card,padding:'16px 20px'}}>
              <div style={{fontSize:13,fontWeight:700,color:validation.valid?'var(--success)':'var(--danger)',marginBottom:12}}>
                {validation.valid ? '✓ Fichero válido' : '✗ Errores de validación'}
              </div>
              <div style={{fontSize:12,color:'var(--text-2)',marginBottom:10}}>{validation.total_rows} filas detectadas</div>
              {validation.warnings?.map((w,i) => <div key={i} style={{background:'var(--warning-bg)',border:'1px solid #ffb80030',borderRadius:6,padding:'6px 10px',color:'var(--warning)',fontSize:12,marginBottom:6}}>⚠ {w}</div>)}
              {validation.errors?.map((e,i) => <div key={i} style={{background:'var(--danger-bg)',border:'1px solid #ff475730',borderRadius:6,padding:'6px 10px',color:'var(--danger)',fontSize:12,marginBottom:6}}>✗ Fila {e.row}: {e.error}</div>)}
              {validation.preview?.length > 0 && (
                <div style={{marginTop:12,fontSize:11,color:'var(--text-2)'}}>
                  <div style={{fontWeight:700,marginBottom:6}}>Vista previa (5 filas):</div>
                  <div style={{overflowX:'auto'}}>
                    <table style={{borderCollapse:'collapse',fontSize:11}}>
                      <thead><tr>{Object.keys(validation.preview[0]).map(k => <th key={k} style={{padding:'4px 8px',borderBottom:'1px solid #1e2d45',textAlign:'left',color:'var(--text-3)',whiteSpace:'nowrap'}}>{k}</th>)}</tr></thead>
                      <tbody>
                        {validation.preview.map((row,i) => <tr key={i}>{Object.values(row).map((v,j) => <td key={j} style={{padding:'4px 8px',borderBottom:'1px solid #1e2d4520',color:'var(--text-1)',whiteSpace:'nowrap'}}>{String(v).slice(0,30)}</td>)}</tr>)}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Import result */}
          {result && step === 'result' && (
            <div style={{...card,padding:'16px 20px',border:`1px solid ${result.succeeded>0?'rgba(52,211,153,0.25)':'rgba(248,113,113,0.25)'}`}}>
              <div style={{fontSize:14,fontWeight:700,color:result.succeeded>0?'var(--success)':'var(--danger)',marginBottom:12}}>
                {result.succeeded > 0 ? `✓ Importación completada` : '✗ Importación fallida'}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12,marginBottom:12}}>
                {[['Total',result.total,'var(--text-2)'],['Importados',result.succeeded,'var(--success)'],['Errores',result.failed,'var(--danger)']].map(([l,v,c]) => (
                  <div key={l} style={{textAlign:'center',background:'var(--surface-3)',borderRadius:8,padding:'12px'}}>
                    <div style={{fontSize:24,fontWeight:800,color:c}}>{v}</div>
                    <div style={{fontSize:11,color:'var(--text-2)'}}>{l}</div>
                  </div>
                ))}
              </div>
              {result.errors?.map((e,i) => <div key={i} style={{fontSize:12,color:'var(--danger)',padding:'3px 0'}}>Fila {e.row}: {e.error}</div>)}
            </div>
          )}
        </div>

        {/* Import history */}
        <div style={{...card,overflow:'hidden',alignSelf:'start'}}>
          <div style={{padding:'14px 18px',borderBottom:'1px solid #1e2d45',fontSize:13,fontWeight:700}}>Historial de importaciones</div>
          {jobs.length === 0 ? <div style={{padding:'24px',textAlign:'center',color:'var(--text-3)',fontSize:13}}>Sin importaciones previas</div> : (
            jobs.slice(0,10).map(j => (
              <div key={j.id} style={{display:'grid',gridTemplateColumns:'80px 1fr 80px 60px',gap:10,padding:'10px 18px',borderBottom:'1px solid #1e2d4520',alignItems:'center'}}>
                <span style={{fontSize:11,fontWeight:700,padding:'2px 6px',borderRadius:4,background:j.status==='completed'?'var(--success-bg)':j.status==='partial'?'var(--warning-bg)':'var(--danger-bg)',color:j.status==='completed'?'var(--success)':j.status==='partial'?'var(--warning)':'var(--danger)'}}>
                  {j.status}
                </span>
                <div>
                  <div style={{fontSize:12,fontWeight:600}}>{ENTITY_LABELS[j.entity_type]||j.entity_type}</div>
                  <div style={{fontSize:11,color:'var(--text-3)'}}>{j.filename} · {j.started_at}</div>
                </div>
                <span style={{fontSize:12,color:'var(--text-2)',textAlign:'right'}}>{j.succeeded}/{j.total_rows}</span>
                <span style={{fontSize:11,color:'var(--danger)'}}>{j.failed_rows>0?`${j.failed_rows} err`:''}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default function ImportPage() {
  const t = useAppT()
  return (
    <div style={{ padding: 32 }}>
      <PageHeader title={t('import_data.title')} subtitle={t('import_data.subtitle')} />
      <ImportTab />
    </div>
  )
}
