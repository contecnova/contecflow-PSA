import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, sprintsApi, tasksApi, semanticApi, sprintPlansApi } from '../services/api'
import type { EstadoDePlanDeSprint, PlanDeSprint, PlanDeSprintGenerado } from '../services/api/tipos-proyectos'
import type { EstimacionDelBacklog } from '../services/api/tipos-analitica'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ListTodo } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties } from 'react'
import './SprintPlanningPage.css'
import { LARGE_PAGE_SIZE } from '../constants/pagination'

interface ProjectItem {
  id: string | number
  name?: string
}

type PlanStatus = EstadoDePlanDeSprint

const is = 'ds-input spl-input'
const ls = 'spl-label'

/** Color del porcentaje de uso: rojo si se pasa, verde en la franja buena, ámbar si se queda corto. */
const colorDeUso = (pct: number) => pct >= 90 ? 'var(--danger)' : pct >= 70 ? 'var(--success)' : 'var(--warning)'

const STATUS_CFG = {
  draft:    {color:'var(--text-2)', bg:'var(--surface-3)'},
  accepted: {color:'var(--success)', bg:'var(--success-bg)'},
  rejected: {color:'var(--danger)', bg:'var(--danger-bg)'},
}
const PRIORITY_COLORS: Record<string, string> = {critical:'var(--danger)',high:'var(--warning)',medium:'var(--warning)',low:'var(--text-2)'}

function GenerateModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ name: '', team_capacity: 40, sprint_id: '' })
  const set = (k: 'name' | 'team_capacity' | 'sprint_id') => (v: string | number) => setForm((f) => ({ ...f, [k]: v }))
  const [result, setResult] = useState<PlanDeSprintGenerado | null>(null)
  const [semEstimate, setSemEstimate] = useState<EstimacionDelBacklog | null>(null)
  const [estimating, setEstimating] = useState(false)

  const estimateBacklog = async () => {
    if (!projectId) return
    setEstimating(true)
    try {
      // Obtener TODAS las tareas del backlog (con y sin story_points)
      const tasksRes = await tasksApi.list({ project_id: projectId, status: 'todo', page_size: LARGE_PAGE_SIZE })
      const tasks = tasksRes.data
      if (!tasks.length) { toast.info(t('sprint_planning.no_todo_tasks')); return }
      const res = await semanticApi.estimateSprint({
        tasks: tasks.map(task => ({ id: task.id, title: task.title, description: task.description || '', story_points: task.story_points })),
        team_capacity_hours: form.team_capacity * 2, // aprox 2h por story point
      })
      setSemEstimate(res.data)
      const unest = tasks.filter(tk => !tk.story_points).length
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
    onSuccess: (data) => { setResult(data); qc.invalidateQueries({ queryKey: ['sprint-plans', projectId] }) },
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_generate'))),
  })

  const utilizationPct = result?.utilization_pct || 0
  const utilizationColor = colorDeUso(utilizationPct)
  const usoVars = { '--spl-c': utilizationColor, '--spl-pct': `${Math.min(100, utilizationPct)}%` } as CSSProperties

  return (
    <Modal open onClose={onClose} title={t('sprint_planning.modal_title')}>
      <div className="u-stack-14">
        {!result ? (
          <>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{t('sprint_planning.plan_name')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} className={is} value={form.name} onChange={e => set('name')(e.target.value)} placeholder={traducir('sprintplanning.nombre_del_plan')} />
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{t('sprint_planning.team_capacity_sp')}</label>
                <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" className={is} value={form.team_capacity}
                  onChange={e => set('team_capacity')(+e.target.value)} min={1} />
              </div>
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={ls}>{t('sprint_planning.sprint_optional')}</label>
                <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} className={is} value={form.sprint_id} onChange={e => set('sprint_id')(e.target.value)}>
                  <option value="">{t('sprint_planning.no_specific_sprint')}</option>
                  {(sprints as Array<{ id: string | number; name: string }>).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div className="spl-info">
              <strong className="u-accent">{t('sprint_planning.how_it_works')}:</strong> {t('sprint_planning.how_it_works_desc')}
              {semEstimate && (
                <div className="spl-semantic">
                  <div className="spl-semantic__title">🧠 {t('sprint_planning.semantic_estimate_title')}</div>
                  <div className="spl-semantic__row">
                    <span>⏱ {t('sprint_planning.base_label')}: <strong className="u-text1">{semEstimate.total_base_hours}h</strong></span>
                    <span>⚠ {t('sprint_planning.risk_label')}: <strong className="u-warning">+{semEstimate.risk_premium_pct}%</strong></span>
                    <span>📦 {t('sprint_planning.recommended_label')}: <strong className="u-success">{semEstimate.recommended_hours}h</strong></span>
                    <span>✅ {t('sprint_planning.fits_sprint_label')}: <strong className={semEstimate.fit_in_sprint ? 'spl-fit--yes' : 'spl-fit--no'}>{semEstimate.fit_in_sprint ? t('sprint_planning.yes') : t('sprint_planning.no')}</strong></span>
                  </div>
                </div>
              )}
            </div>
            <div className="spl-footer">
              <button type="button" onClick={estimateBacklog} disabled={estimating || !projectId} className="spl-estimate-btn">
                {estimating ? `⏳ ${t('sprint_planning.estimating')}` : `🧠 ${t('sprint_planning.estimate_backlog')}`}
              </button>
              <div className="u-row-10">
                <Button variant="secondary" onClick={onClose}>{t('sprint_planning.cancel')}</Button>
                <Button onClick={() => generate()} disabled={isPending || !form.name.trim() || !form.team_capacity}>
                  {isPending ? `✨ ${t('sprint_planning.generating')}` : `✨ ${t('sprint_planning.generate_plan_btn')}`}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="spl-result">
              <div className="spl-result__title">✅ {t('sprint_planning.plan_generated_label')}: {result.name}</div>
              <div className="u-text2-sm">{result.task_count} {t('sprint_planning.tasks_label')} · {result.total_points}{traducir('sprintplanning.p_de')} {result.team_capacity}p</div>
            </div>
            {/* Barra de utilización */}
            <div>
              <div className="spl-util-head" style={usoVars}>
                <span className="u-text2">{t('sprint_planning.sprint_utilization')}</span>
                <span className="spl-util-pct">{utilizationPct}%</span>
              </div>
              <div className="spl-bar" style={usoVars} role="progressbar" aria-valuenow={Math.min(100, utilizationPct)} aria-valuemin={0} aria-valuemax={100} aria-label={t('sprint_planning.sprint_utilization')}>
                <div className="spl-bar__fill" />
              </div>
            </div>
            {/* Razonamiento IA */}
            <div>
              <div className="spl-eyebrow">{t('sprint_planning.ai_reasoning')}</div>
              <pre className="spl-reasoning" tabIndex={0}>
                {result.ai_reasoning}
              </pre>
            </div>
            {/* Warning tareas sin story points */}
            {(result.unestimated_count ?? 0) > 0 && (
              <div className="spl-warning" role="status">
                ⚠ {result.unestimated_count} {t('sprint_planning.unestimated_warning_suffix')}
              </div>
            )}
            {/* Lista de tareas */}
            <div className="spl-tasks" tabIndex={0}>
              {result.tasks.map((tk,i) => (
                <div key={tk.task_id} className="spl-task">
                  <span className="spl-task__n">{i+1}</span>
                  <span className="spl-task__title" title={tk.title}>{tk.title}</span>
                  <span className="spl-task__prio" style={{ '--spl-c': (tk.priority && PRIORITY_COLORS[tk.priority]) || 'var(--text-2)' } as CSSProperties}>{tk.priority ? t('sprint_planning.prioridad_' + tk.priority, tk.priority) : ''}</span>
                  <span className={`spl-task__sp${tk.unestimated ? ' spl-task__sp--est' : ''}`}>
                    {tk.story_points}p{tk.unestimated ? ' ~' : ''}
                  </span>
                </div>
              ))}
            </div>
            <div className="spl-footer spl-footer--end">
              <Button onClick={onClose}>{t('sprint_planning.close')}</Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

export default function SprintPlanningPage() {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [showGenerate, setShowGenerate] = useState(false)
  const [expandPlan, setExpandPlan] = useState<string | null>(null)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data)?r.data:[]).catch(()=>[]),
  })
  const projects = projectsRaw as ProjectItem[]
  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['sprint-plans', project],
    queryFn: () => sprintPlansApi.get(project).then(r => r.data).catch((): PlanDeSprint[] => []),
    enabled: !!project,
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({id, status}: { id: string; status: PlanStatus }) => sprintPlansApi.updateStatus(id, status).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprint-plans', project] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_delete'))),
  })

  const { mutate: deletePlan } = useMutation({
    mutationFn: (id: string) => sprintPlansApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sprint-plans', project] }); setExpandPlan(null) },
    onError: (e: unknown) => toast.error(extractErr(e, t('sprint_planning.error_delete'))),
  })

  return (
    <PageShell>
      <PageHeader icon={<ListTodo size={18} />} title={t('sprint_planning.title')} subtitle={t('sprint_planning.subtitle')}
        actions={project && <Button onClick={() => setShowGenerate(true)}>✨ {t('sprint_planning.generate_plan_action')}</Button>} showListExport={false} />

      <div className="spl-panel spl-panel--mb">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{t('sprint_planning.project_label')}</label>
        <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e => setProject(e.target.value)} className={`${is} spl-input--project`}>
          <option value="">{t('sprint_planning.select_project_opt')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="✨" title={t('sprint_planning.select_project_title')} description={t('sprint_planning.select_project_desc2')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && plans.length === 0 && (
        <div className="spl-panel spl-panel--empty">
          <div className="u-empty-icon">✨</div>
          <div className="spl-empty-title">{t('sprint_planning.no_plans_title')}</div>
          <div className="u-text2-base-mb20">
            {t('sprint_planning.no_plans_desc')}
          </div>
          <Button onClick={() => setShowGenerate(true)}>✨ {t('sprint_planning.generate_first_plan')}</Button>
        </div>
      )}

      {project && plans.length > 0 && (
        <div className="u-stack-10">
          {plans.map(plan => {
            const sc = STATUS_CFG[plan.status] || STATUS_CFG.draft
            const pct = plan.team_capacity > 0 ? Math.round(plan.total_points/plan.team_capacity*100) : 0
            const isExpanded = expandPlan === plan.id
            const planVars = { '--spl-c': sc.color, '--spl-bg': sc.bg } as CSSProperties
            const usoPlan = { '--spl-c': colorDeUso(pct), '--spl-pct': `${Math.min(100, pct)}%` } as CSSProperties
            return (
              <div key={plan.id} className="spl-plan" style={planVars}>
                <div className={`spl-plan__head${isExpanded ? ' spl-plan__head--open' : ''}`}>
                  <div className="u-flex1">
                    <div className="u-row-center-10">
                      <span className="u-md-600">{plan.name}</span>
                      <span className="spl-status">{t('sprint_planning.status_' + plan.status)}</span>
                    </div>
                    <div className="spl-plan__meta">
                      {plan.task_count} {t('sprint_planning.tasks_label')} · {plan.total_points}{traducir('sprintplanning.p_de')} {plan.team_capacity}p ({pct}% {t('sprint_planning.utilization_label')})
                    </div>
                  </div>
                  <div className="u-row-8">
                    {plan.status === 'draft' && <>
                      <button type="button" onClick={() => updateStatus({id:plan.id,status:'accepted'})} className="spl-btn spl-btn--accept">
                        ✓ {t('sprint_planning.accept_btn')}
                      </button>
                      <button type="button" onClick={() => updateStatus({id:plan.id,status:'rejected'})} className="spl-btn spl-btn--reject">
                        ✕ {t('sprint_planning.reject_btn')}
                      </button>
                    </>}
                    <button type="button" onClick={() => setExpandPlan(isExpanded ? null : plan.id)} className="spl-btn" aria-expanded={isExpanded}>
                      {isExpanded ? `▲ ${t('sprint_planning.hide_details')}` : `▼ ${t('sprint_planning.view_details')}`}
                    </button>
                    <button type="button" onClick={() => { openConfirmGlobal({ message: t('sprint_planning.delete_confirm', { name: plan.name }), onConfirm: () => deletePlan(plan.id), danger: true }) }}
                      className="spl-btn spl-btn--delete" aria-label={t('sprint_planning.eliminar_plan')} title={t('sprint_planning.eliminar_plan')}>
                      <span aria-hidden="true">🗑</span>
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="spl-plan__detail" style={usoPlan}>
                    <div className="spl-eyebrow spl-eyebrow--tight">
                      {t('sprint_planning.created_label')}: {fmtDateTime(plan.created_at)}
                    </div>
                    <div className="spl-util-head spl-util-head--sm">
                      <span>{t('sprint_planning.sprint_utilization')}</span>
                      <span className="spl-util-pct">{pct}%</span>
                    </div>
                    <div className="spl-bar spl-bar--sm" role="progressbar" aria-valuenow={Math.min(100, pct)} aria-valuemin={0} aria-valuemax={100} aria-label={t('sprint_planning.sprint_utilization')}>
                      <div className="spl-bar__fill" />
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
