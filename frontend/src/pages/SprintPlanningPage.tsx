import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, sprintsApi, tasksApi, semanticApi, sprintPlansApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ListTodo } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties } from 'react'

interface ProjectItem {
  id: string | number
  name?: string
}

type PlanStatus = 'draft' | 'accepted' | 'rejected'

interface SprintPlanTask {
  task_id: string | number
  title: string
  priority?: 'critical' | 'high' | 'medium' | 'low'
  story_points: number
  unestimated?: boolean
}

interface SprintPlanResult {
  id: string | number
  name: string
  status: PlanStatus
  task_count: number
  total_points: number
  team_capacity: number
  utilization_pct?: number
  ai_reasoning?: string
  unestimated_count?: number
  created_at?: string
  tasks: SprintPlanTask[]
}

interface SemanticEstimate {
  total_base_hours: number
  risk_premium_pct: number
  recommended_hours: number
  fit_in_sprint: boolean
}

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const STATUS_CFG = {
  draft:    {color:'var(--text-2)', bg:'rgba(120,138,170,0.09)'},
  accepted: {color:'var(--success)', bg:'var(--success-bg)'},
  rejected: {color:'var(--danger)', bg:'var(--danger-bg)'},
}
const PRIORITY_COLORS: Record<string, string> = {critical:'var(--danger)',high:'var(--warning)',medium:'var(--warning)',low:'var(--text-2)'}

function GenerateModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ name: '', team_capacity: 40, sprint_id: '' })
  const set = (k: 'name' | 'team_capacity' | 'sprint_id') => (v: string | number) => setForm((f) => ({ ...f, [k]: v }))
  const [result, setResult] = useState<SprintPlanResult | null>(null)
  const [semEstimate, setSemEstimate] = useState<SemanticEstimate | null>(null)
  const [estimating, setEstimating] = useState(false)

  const estimateBacklog = async () => {
    if (!projectId) return
    setEstimating(true)
    try {
      // Obtener TODAS las tareas del backlog (con y sin story_points)
      const tasksRes = await tasksApi.list({ project_id: projectId, status: 'todo', page_size: 200 })
      const tasks = (tasksRes.data ?? []) as unknown as Array<{ id: string | number; title: string; description?: string; story_points?: number }>
      if (!tasks.length) { toast.info(t('sprint_planning.no_todo_tasks')); return }
      const res = await semanticApi.estimateSprint({
        tasks: tasks.map((task: { id: string | number; title: string; description?: string; story_points?: number }) => ({ id: task.id, title: task.title, description: task.description || '', story_points: task.story_points })),
        team_capacity_hours: form.team_capacity * 2, // aprox 2h por story point
      })
      setSemEstimate(res.data as SemanticEstimate)
      const unest = tasks.filter((tk: { story_points?: number }) => !tk.story_points).length
      if (unest > 0) toast.info(`${unest} ${t('sprint_planning.unestimated_toast_suffix')}`)
    } catch (e: unknown) {
      const message = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('sprint_planning.error_estimate')
      toast.error(message)
    }
    finally { setEstimating(false) }
  }

  const { data: sprints = [] } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => sprintsApi.list(projectId, {}).then(r => {
      const d = r.data
      if (Array.isArray(d?.items)) return d.items
      if (Array.isArray(d)) return d
      return []
    }).catch(()=>[]),
    enabled: !!projectId,
  })

  const { mutate: generate, isPending } = useMutation({
    mutationFn: () => sprintPlansApi.generate({
      ...form,
      project_id: projectId,
      sprint_id: form.sprint_id || null,
    }).then(r => r.data),
    onSuccess: (data) => { setResult(data as SprintPlanResult); qc.invalidateQueries({ queryKey: ['sprint-plans', projectId] }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_generate'))),
  })

  const utilizationPct = result?.utilization_pct || 0
  const utilizationColor = utilizationPct >= 90 ? 'var(--danger)' : utilizationPct >= 70 ? 'var(--success)' : 'var(--warning)'

  return (
    <Modal open onClose={onClose} title={t('sprint_planning.modal_title')}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        {!result ? (
          <>
            <div>
              <label style={ls}>{t('sprint_planning.plan_name')}</label>
              <input style={is} value={form.name} onChange={e => set('name')(e.target.value)} placeholder="Nombre del plan..." />
            </div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <div>
                <label style={ls}>{t('sprint_planning.team_capacity_sp')}</label>
                <input type="number" style={is} value={form.team_capacity}
                  onChange={e => set('team_capacity')(+e.target.value)} min={1} />
              </div>
              <div>
                <label style={ls}>{t('sprint_planning.sprint_optional')}</label>
                <select style={is} value={form.sprint_id} onChange={e => set('sprint_id')(e.target.value)}>
                  <option value="">{t('sprint_planning.no_specific_sprint')}</option>
                  {(sprints as Array<{ id: string | number; name: string }>).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div style={{padding:'12px 14px',background:'var(--surface-1)',borderRadius:8,border:'1px solid var(--surface-4)',fontSize: "var(--text-sm)",color:'var(--text-2)',lineHeight:1.7}}>
              <strong style={{color:'var(--accent)'}}>{t('sprint_planning.how_it_works')}:</strong> {t('sprint_planning.how_it_works_desc')}
              {semEstimate && (
                <div style={{marginTop:10,padding:'8px 10px',background:'var(--purple-bg)',border:'1px solid var(--purple-border)',borderRadius:8}}>
                  <div style={{color:'var(--purple)',fontWeight:700,marginBottom:4}}>🧠 {t('sprint_planning.semantic_estimate_title')}</div>
                  <div style={{display:'flex',gap:16,flexWrap:'wrap'}}>
                    <span>⏱ {t('sprint_planning.base_label')}: <strong style={{color:'var(--text-1)'}}>{semEstimate.total_base_hours}h</strong></span>
                    <span>⚠ {t('sprint_planning.risk_label')}: <strong style={{color:'var(--warning)'}}>+{semEstimate.risk_premium_pct}%</strong></span>
                    <span>📦 {t('sprint_planning.recommended_label')}: <strong style={{color:'var(--success)'}}>{semEstimate.recommended_hours}h</strong></span>
                    <span>✅ {t('sprint_planning.fits_sprint_label')}: <strong style={{color: semEstimate.fit_in_sprint ? 'var(--success)' : 'var(--danger)'}}>{semEstimate.fit_in_sprint ? t('sprint_planning.yes') : t('sprint_planning.no')}</strong></span>
                  </div>
                </div>
              )}
            </div>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginTop:8}}>
              <button onClick={estimateBacklog} disabled={estimating || !projectId}
                style={{background:'transparent',border:'1px solid var(--purple-border-strong)',borderRadius:6,padding:'5px 12px',color:'var(--purple)',fontSize: "var(--text-xs)",cursor:'pointer',fontFamily:'inherit',fontWeight:700}}>
                {estimating ? `⏳ ${t('sprint_planning.estimating')}` : `🧠 ${t('sprint_planning.estimate_backlog')}`}
              </button>
              <div style={{display:'flex',gap:10}}>
                <Button variant="secondary" onClick={onClose}>{t('sprint_planning.cancel')}</Button>
                <Button onClick={() => generate()} disabled={isPending || !form.name.trim() || !form.team_capacity}>
                  {isPending ? `✨ ${t('sprint_planning.generating')}` : `✨ ${t('sprint_planning.generate_plan_btn')}`}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div style={{padding:'14px 16px',background:'var(--success-bg)',border:'1px solid var(--success-border)',borderRadius:8}}>
              <div style={{fontSize: "var(--text-md)",fontWeight:600,color:'var(--success)',marginBottom:4}}>✅ {t('sprint_planning.plan_generated_label')}: {result.name}</div>
              <div style={{fontSize: "var(--text-sm)",color:'var(--text-2)'}}>{result.task_count} {t('sprint_planning.tasks_label')} · {result.total_points}p de {result.team_capacity}p</div>
            </div>
            {/* Barra de utilización */}
            <div>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:6,fontSize: "var(--text-sm)"}}>
                <span style={{color:'var(--text-2)'}}>{t('sprint_planning.sprint_utilization')}</span>
                <span style={{color:utilizationColor,fontWeight:700}}>{utilizationPct}%</span>
              </div>
              <div style={{height:10,background:'var(--surface-4)',borderRadius:5,overflow:'hidden'}}>
                <div style={{height:'100%',width:`${Math.min(100,utilizationPct)}%`,background:utilizationColor,borderRadius:5,transition:'width .5s'}} />
              </div>
            </div>
            {/* Razonamiento IA */}
            <div>
              <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>{t('sprint_planning.ai_reasoning')}</div>
              <pre style={{background:'var(--surface-1)',borderRadius:8,padding:'12px 14px',fontSize: "var(--text-xs)",color:'var(--text-2)',
                lineHeight:1.6,overflow:'auto',maxHeight:180,whiteSpace:'pre-wrap',border:'1px solid var(--surface-4)',fontFamily:'var(--font-mono)'}}>
                {result.ai_reasoning}
              </pre>
            </div>
            {/* Warning tareas sin story points */}
            {(result.unestimated_count ?? 0) > 0 && (
              <div style={{padding:'8px 12px',background:'rgba(255,184,0,0.08)',border:'1px solid rgba(255,184,0,0.3)',borderRadius:8,fontSize: "var(--text-sm)",color:'var(--warning)'}}>
                ⚠ {result.unestimated_count} {t('sprint_planning.unestimated_warning_suffix')}
              </div>
            )}
            {/* Lista de tareas */}
            <div style={{maxHeight:220,overflowY:'auto',border:'1px solid var(--surface-4)',borderRadius:8}}>
              {result.tasks.map((t,i) => (
                <div key={t.task_id} style={{display:'flex',gap:10,padding:'8px 12px',
                  borderBottom:'1px solid var(--surface-4)',fontSize: "var(--text-sm)",background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                  <span style={{color:'var(--text-3)',minWidth:20}}>{i+1}</span>
                  <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.title}</span>
                  <span style={{color:(t.priority && PRIORITY_COLORS[t.priority])||'var(--text-2)',flexShrink:0}}>{t.priority}</span>
                  <span style={{color: t.unestimated ? 'var(--warning)' : 'var(--accent)',flexShrink:0,fontWeight:600}}>
                    {t.story_points}p{t.unestimated ? ' ~' : ''}
                  </span>
                </div>
              ))}
            </div>
            <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
              <Button onClick={onClose}>{t('sprint_planning.close')}</Button>
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
  const [expandPlan, setExpandPlan] = useState<string | number | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data)?r.data:[]).catch(()=>[]),
  })
  const projects = projectsRaw as ProjectItem[]
  const { data: plansRaw = [], isLoading } = useQuery({
    queryKey: ['sprint-plans', project],
    queryFn: () => sprintPlansApi.get(project).then(r => r.data).catch(()=>[]),
    enabled: !!project,
  })
  const plans = plansRaw as SprintPlanResult[]

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({id, status}: { id: string | number; status: PlanStatus }) => sprintPlansApi.updateStatus(id, status).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprint-plans', project] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_delete'))),
  })

  const { mutate: deletePlan } = useMutation({
    mutationFn: (id: string | number) => sprintPlansApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sprint-plans', project] }); setExpandPlan(null) },
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_delete'))),
  })

  return (
    <PageShell>
      <PageHeader icon={<ListTodo size={18} />} title={t('sprint_planning.title')} subtitle={t('sprint_planning.subtitle')}
        actions={project && <Button onClick={() => setShowGenerate(true)}>✨ {t('sprint_planning.generate_plan_action')}</Button>} showListExport={false} />

      <div style={{...ps,marginBottom:20}}>
        <label style={ls}>{t('sprint_planning.project_label')}</label>
        <select value={project} onChange={e => setProject(e.target.value)} style={{...is,width:360}}>
          <option value="">{t('sprint_planning.select_project_opt')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="✨" title={t('sprint_planning.select_project_title')} description={t('sprint_planning.select_project_desc2')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && plans.length === 0 && (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)",marginBottom:16}}>✨</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>{t('sprint_planning.no_plans_title')}</div>
          <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:20}}>
            {t('sprint_planning.no_plans_desc')}
          </div>
          <Button onClick={() => setShowGenerate(true)}>✨ {t('sprint_planning.generate_first_plan')}</Button>
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
                      <span style={{fontWeight:600,fontSize: "var(--text-md)"}}>{plan.name}</span>
                      <span style={{fontSize: "var(--text-xs)",padding:'2px 8px',borderRadius:20,
                        background:sc.bg,color:sc.color,fontWeight:600}}>{t('sprint_planning.status_' + plan.status)}</span>
                    </div>
                    <div style={{fontSize: "var(--text-sm)",color:'var(--text-2)',marginTop:4}}>
                      {plan.task_count} {t('sprint_planning.tasks_label')} · {plan.total_points}p de {plan.team_capacity}p ({pct}% {t('sprint_planning.utilization_label')})
                    </div>
                  </div>
                  <div style={{display:'flex',gap:8}}>
                    {plan.status === 'draft' && <>
                      <button onClick={() => updateStatus({id:plan.id,status:'accepted'})}
                        style={{padding:'5px 12px',borderRadius:8,border:'1px solid var(--success-border)',
                          background:'var(--success-bg)',color:'var(--success)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)"}}>
                        ✓ {t('sprint_planning.accept_btn')}
                      </button>
                      <button onClick={() => updateStatus({id:plan.id,status:'rejected'})}
                        style={{padding:'5px 12px',borderRadius:8,border:'1px solid var(--danger-border)',
                          background:'var(--danger-bg)',color:'var(--danger)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)"}}>
                        ✕ {t('sprint_planning.reject_btn')}
                      </button>
                    </>}
                    <button onClick={() => setExpandPlan(isExpanded ? null : plan.id)}
                      style={{padding:'5px 12px',borderRadius:8,border:'1px solid var(--surface-4)',
                        background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)"}}>
                      {isExpanded ? `▲ ${t('sprint_planning.hide_details')}` : `▼ ${t('sprint_planning.view_details')}`}
                    </button>
                    <button onClick={() => { openConfirmGlobal({ message: t('sprint_planning.delete_confirm').replace('{name}', plan.name), onConfirm: () => deletePlan(plan.id), danger: true }) }}
                      style={{padding:'5px 8px',borderRadius:8,border:'1px solid var(--danger-border)',
                        background:'transparent',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-sm)"}}>
                      🗑
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div style={{borderTop:'1px solid var(--surface-4)',paddingTop:12}}>
                    <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:6}}>
                      {t('sprint_planning.created_label')}: {plan.created_at ? new Date(plan.created_at).toLocaleString() : '—'}
                    </div>
                    <div style={{display:'flex',justifyContent:'space-between',fontSize: "var(--text-xs)",color:'var(--text-2)',marginBottom:4}}>
                      <span>{t('sprint_planning.sprint_utilization')}</span>
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
    </PageShell>
  )
}
