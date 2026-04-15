import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const STATUS_CFG = {
  draft:    {label:'Borrador',   color:'var(--text-2)', bg:'rgba(120,138,170,0.09)'},
  accepted: {label:'Aceptado',   color:'var(--success)', bg:'var(--success-bg)'},
  rejected: {label:'Rechazado',  color:'var(--danger)', bg:'var(--danger-bg)'},
}
const PRIORITY_COLORS = {critical:'var(--danger)',high:'var(--warning)',medium:'var(--warning)',low:'var(--text-2)'}

function GenerateModal({ projectId, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ name: '', team_capacity: 40, sprint_id: '' })
  const set = k => v => setForm(f => ({...f, [k]: v}))
  const [result, setResult] = useState(null)
  const [semEstimate, setSemEstimate] = useState(null)
  const [estimating, setEstimating] = useState(false)

  const estimateBacklog = async () => {
    if (!projectId) return
    setEstimating(true)
    try {
      // Obtener TODAS las tareas del backlog (con y sin story_points)
      const tasksRes = await api.get(`/tasks?project_id=${projectId}&status=todo&page_size=200`)
      const tasks = Array.isArray(tasksRes.data) ? tasksRes.data : []
      if (!tasks.length) { toast.info('No hay tareas en estado "todo" en este proyecto'); return }
      const res = await api.post('/semantic/estimate/sprint-backlog', {
        tasks: tasks.map(t => ({ id: t.id, title: t.title, description: t.description || '', story_points: t.story_points })),
        team_capacity_hours: form.team_capacity * 2, // aprox 2h por story point
      })
      setSemEstimate(res.data)
      const unest = tasks.filter(t => !t.story_points).length
      if (unest > 0) toast.info(`${unest} tarea(s) sin story points — se usará estimación semántica`)
    } catch (e) { toast.error(e?.response?.data?.detail || 'Error al estimar') }
    finally { setEstimating(false) }
  }

  const { data: sprints = [] } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => api.get(`/sprints?project_id=${projectId}`).then(r => Array.isArray(r.data)?r.data:[]).catch(()=>[]),
    enabled: !!projectId,
  })

  const { mutate: generate, isPending } = useMutation({
    mutationFn: () => api.post('/sprint-plans/generate', {
      ...form,
      project_id: projectId,
      sprint_id: form.sprint_id || null,
    }).then(r => r.data),
    onSuccess: data => { setResult(data); qc.invalidateQueries(['sprint-plans', projectId]) },
    onError: e => toast.error(extractErr(e, 'Error al generar')),
  })

  const utilizationPct = result?.utilization_pct || 0
  const utilizationColor = utilizationPct >= 90 ? 'var(--danger)' : utilizationPct >= 70 ? 'var(--success)' : 'var(--warning)'

  return (
    <Modal open onClose={onClose} title="Generar plan de sprint con IA">
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        {!result ? (
          <>
            <div>
              <label style={ls}>Nombre del plan</label>
              <input style={is} value={form.name} onChange={e => set('name')(e.target.value)} placeholder="Sprint 12 — Plan IA" />
            </div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <div>
                <label style={ls}>Capacidad del equipo (story points)</label>
                <input type="number" style={is} value={form.team_capacity}
                  onChange={e => set('team_capacity')(+e.target.value)} min={1} />
              </div>
              <div>
                <label style={ls}>Sprint (opcional)</label>
                <select style={is} value={form.sprint_id} onChange={e => set('sprint_id')(e.target.value)}>
                  <option value="">Sin sprint específico</option>
                  {sprints.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div style={{padding:'12px 14px',background:'var(--surface-1)',borderRadius:8,border:'1px solid #1a2640',fontSize:12,color:'var(--text-2)',lineHeight:1.7}}>
              <strong style={{color:'var(--accent)'}}>Cómo funciona:</strong> La IA selecciona tareas del backlog (estado &quot;todo&quot;) ordenadas por story points,
              respetando la capacidad del equipo. Las tareas con mayor estimación tienen prioridad para maximizar la utilización.
              {semEstimate && (
                <div style={{marginTop:10,padding:'8px 10px',background:'var(--purple-bg)',border:'1px solid #7c3aed30',borderRadius:8}}>
                  <div style={{color:'var(--purple)',fontWeight:700,marginBottom:4}}>🧠 Estimación semántica del backlog</div>
                  <div style={{display:'flex',gap:16,flexWrap:'wrap'}}>
                    <span>⏱ Base: <strong style={{color:'var(--text-1)'}}>{semEstimate.total_base_hours}h</strong></span>
                    <span>⚠ Riesgo: <strong style={{color:'var(--warning)'}}>+{semEstimate.risk_premium_pct}%</strong></span>
                    <span>📦 Recomendado: <strong style={{color:'var(--success)'}}>{semEstimate.recommended_hours}h</strong></span>
                    <span>✅ Cabe en sprint: <strong style={{color: semEstimate.fit_in_sprint ? 'var(--success)' : 'var(--danger)'}}>{semEstimate.fit_in_sprint ? 'Sí' : 'No'}</strong></span>
                  </div>
                </div>
              )}
            </div>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginTop:8}}>
              <button onClick={estimateBacklog} disabled={estimating || !projectId}
                style={{background:'transparent',border:'1px solid #7c3aed40',borderRadius:6,padding:'5px 12px',color:'var(--purple)',fontSize:11,cursor:'pointer',fontFamily:'inherit',fontWeight:700}}>
                {estimating ? '⏳ Estimando...' : '🧠 Estimar esfuerzo del backlog'}
              </button>
              <div style={{display:'flex',gap:10}}>
                <Button variant="secondary" onClick={onClose}>Cancelar</Button>
                <Button onClick={() => generate()} disabled={isPending || !form.name.trim() || !form.team_capacity}>
                  {isPending ? '✨ Generando...' : '✨ Generar plan'}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div style={{padding:'14px 16px',background:'var(--success-bg)',border:'1px solid #00e5a030',borderRadius:8}}>
              <div style={{fontSize:14,fontWeight:600,color:'var(--success)',marginBottom:4}}>✅ Plan generado: {result.name}</div>
              <div style={{fontSize:12,color:'var(--text-2)'}}>{result.task_count} tareas · {result.total_points}p de {result.team_capacity}p</div>
            </div>
            {/* Barra de utilización */}
            <div>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize:12}}>
                <span style={{color:'var(--text-2)'}}>Utilización del sprint</span>
                <span style={{color:utilizationColor,fontWeight:700}}>{utilizationPct}%</span>
              </div>
              <div style={{height:10,background:'var(--surface-4)',borderRadius:5,overflow:'hidden'}}>
                <div style={{height:'100%',width:`${Math.min(100,utilizationPct)}%`,background:utilizationColor,borderRadius:5,transition:'width .5s'}} />
              </div>
            </div>
            {/* Razonamiento IA */}
            <div>
              <div style={{fontSize:11,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Razonamiento IA</div>
              <pre style={{background:'var(--surface-1)',borderRadius:8,padding:'12px 14px',fontSize:11,color:'var(--text-2)',
                lineHeight:1.6,overflow:'auto',maxHeight:180,whiteSpace:'pre-wrap',border:'1px solid #1a2640',fontFamily:'monospace'}}>
                {result.ai_reasoning}
              </pre>
            </div>
            {/* Warning tareas sin story points */}
            {result.unestimated_count > 0 && (
              <div style={{padding:'8px 12px',background:'rgba(255,184,0,0.08)',border:'1px solid rgba(255,184,0,0.3)',borderRadius:8,fontSize:12,color:'var(--warning)'}}>
                ⚠ {result.unestimated_count} tarea(s) sin story points estimados — asignado 1p por defecto.
                Se recomienda estimar el backlog desde la vista de tareas.
              </div>
            )}
            {/* Lista de tareas */}
            <div style={{maxHeight:220,overflowY:'auto',border:'1px solid #1a2640',borderRadius:8}}>
              {result.tasks.map((t,i) => (
                <div key={t.task_id} style={{display:'flex',gap:10,padding:'8px 12px',
                  borderBottom:'1px solid #1a2640',fontSize:12,background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                  <span style={{color:'var(--text-3)',minWidth:20}}>{i+1}</span>
                  <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.title}</span>
                  <span style={{color:PRIORITY_COLORS[t.priority]||'var(--text-2)',flexShrink:0}}>{t.priority}</span>
                  <span style={{color: t.unestimated ? 'var(--warning)' : 'var(--accent)',flexShrink:0,fontWeight:600}}>
                    {t.story_points}p{t.unestimated ? ' ~' : ''}
                  </span>
                </div>
              ))}
            </div>
            <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
              <Button onClick={onClose}>Cerrar</Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

export default function SprintPlanningPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [showGenerate, setShowGenerate] = useState(false)
  const [expandPlan, setExpandPlan] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data)?r.data:[]).catch(()=>[]),
  })
  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['sprint-plans', project],
    queryFn: () => api.get(`/sprint-plans/${project}`).then(r => r.data).catch(()=>[]),
    enabled: !!project,
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({id, status}) => api.patch(`/sprint-plans/${id}/status?status=${status}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries(['sprint-plans', project]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: deletePlan } = useMutation({
    mutationFn: id => api.delete(`/sprint-plans/${id}`),
    onSuccess: () => { qc.invalidateQueries(['sprint-plans', project]); setExpandPlan(null) },
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('sprint_planning.title')} subtitle={t('sprint_planning.subtitle')}
        actions={project && <Button onClick={() => setShowGenerate(true)}>✨ Generar plan</Button>} />

      <div style={{...ps,marginBottom:20}}>
        <label style={ls}>Proyecto</label>
        <select value={project} onChange={e => setProject(e.target.value)} style={{...is,width:360}}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="✨" title="Selecciona un proyecto" description="El sprint planning IA funciona por proyecto" />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && plans.length === 0 && (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize:48,marginBottom:16}}>✨</div>
          <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>Sin planes generados</div>
          <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>
            La IA analizará el backlog y generará un plan de sprint optimizado para la capacidad del equipo.
          </div>
          <Button onClick={() => setShowGenerate(true)}>✨ Generar primer plan</Button>
        </div>
      )}

      {project && plans.length > 0 && (
        <div style={{display:'flex',flexDirection:'column',gap:10}}>
          {plans.map(plan => {
            const sc = STATUS_CFG[plan.status] || STATUS_CFG.draft
            const pct = plan.team_capacity > 0 ? Math.round(plan.total_points/plan.team_capacity*100) : 0
            const isExpanded = expandPlan === plan.id
            return (
              <div key={plan.id} style={{...ps,padding:'16px 20px',border:`1px solid ${sc.color}30`}}>
                <div style={{display:'flex',alignItems:'center',gap:12,marginBottom:isExpanded?12:0}}>
                  <div style={{flex:1}}>
                    <div style={{display:'flex',alignItems:'center',gap:10}}>
                      <span style={{fontWeight:600,fontSize:14}}>{plan.name}</span>
                      <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,
                        background:sc.bg,color:sc.color,fontWeight:600}}>{sc.label}</span>
                    </div>
                    <div style={{fontSize:12,color:'var(--text-2)',marginTop:4}}>
                      {plan.task_count} tareas · {plan.total_points}p de {plan.team_capacity}p ({pct}% utilización)
                    </div>
                  </div>
                  <div style={{display:'flex',gap:8}}>
                    {plan.status === 'draft' && <>
                      <button onClick={() => updateStatus({id:plan.id,status:'accepted'})}
                        style={{padding:'5px 12px',borderRadius:8,border:'1px solid #00e5a030',
                          background:'var(--success-bg)',color:'var(--success)',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>
                        ✓ Aceptar
                      </button>
                      <button onClick={() => updateStatus({id:plan.id,status:'rejected'})}
                        style={{padding:'5px 12px',borderRadius:8,border:'1px solid #ff475730',
                          background:'var(--danger-bg)',color:'var(--danger)',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>
                        ✕ Rechazar
                      </button>
                    </>}
                    <button onClick={() => setExpandPlan(isExpanded ? null : plan.id)}
                      style={{padding:'5px 12px',borderRadius:8,border:'1px solid #1e2d45',
                        background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>
                      {isExpanded ? '▲ Ocultar' : '▼ Ver detalles'}
                    </button>
                    <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${plan.name}"?`, onConfirm: () => deletePlan(plan.id), danger: true }) }}
                      style={{padding:'5px 8px',borderRadius:8,border:'1px solid #ff475730',
                        background:'transparent',color:'var(--danger)',cursor:'pointer',fontSize:12}}>
                      🗑
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div style={{borderTop:'1px solid #1e2d45',paddingTop:12}}>
                    <div style={{fontSize:11,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:6}}>
                      Creado: {plan.created_at ? new Date(plan.created_at).toLocaleString('es-ES') : '—'}
                    </div>
                    <div style={{display:'flex',justifyContent:'space-between',fontSize:11,color:'var(--text-2)',marginBottom:4}}>
                      <span>Utilización del sprint</span>
                      <span style={{fontWeight:700,color: pct>=90?'var(--danger)':pct>=70?'var(--success)':'var(--warning)'}}>{pct}%</span>
                    </div>
                    <div style={{height:8,background:'var(--surface-4)',borderRadius:4,overflow:'hidden',marginBottom:0}}>
                      <div style={{height:'100%',width:`${Math.min(100,pct)}%`,
                        background: pct>=90?'var(--danger)':pct>=70?'var(--success)':'var(--warning)',borderRadius:4,transition:'width .5s'}} />
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showGenerate && (
        <GenerateModal projectId={project} onClose={() => setShowGenerate(false)} />
      )}
    </div>
  )
}
