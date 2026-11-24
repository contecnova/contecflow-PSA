/**
 * SprintPlanningPage — planes de sprint generados por IA, por proyecto.
 *
 * 16-11-2026: título igual que el menú; selector de proyecto en una Card;
 * vacíos con EmptyState e icono lucide (antes emoji ✨ y caja propia); botones
 * del kit con iconos lucide (antes emojis ✨🧠⏳✓✕▲▼🗑 y botones a mano con
 * fondo de color); estado del plan con StatusBadge.
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sprintsApi, tasksApi, semanticApi, sprintPlansApi } from '../services/api'
import type { EstadoDePlanDeSprint, PlanDeSprintGenerado } from '../services/api/tipos-proyectos'
import type { EstimacionDelBacklog } from '../services/api/tipos-analitica'
import { Button, Card, EmptyState, IconButton, Modal, Spinner, Select, Input } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, Brain, Check, CheckCircle2, ChevronDown, ChevronUp, Clock, FolderKanban, Package, Sparkles, Trash2, X } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties } from 'react'
import './SprintPlanningPage.css'
import { LARGE_PAGE_SIZE } from '../constants/pagination'
import { useListaDeProyectos } from '../hooks/useListas'

interface ProjectItem {
  id: string | number
  name?: string
}

type PlanStatus = EstadoDePlanDeSprint

const is = 'ds-input spl-input'
const ls = 'spl-label'

/** Color del porcentaje de uso: rojo si se pasa, verde en la franja buena, ámbar si se queda corto. */
const colorDeUso = (pct: number) => pct >= 90 ? 'var(--danger)' : pct >= 70 ? 'var(--success)' : 'var(--warning)'

const STATUS_KIND: Record<string, StatusBadgeKind> = {
  draft: 'neutral',
  accepted: 'success',
  rejected: 'danger',
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
      toast.error(extractErr(e, t('sprint_planning.error_estimate')))
    }
    finally { setEstimating(false) }
  }

  const { data: sprints = [] } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => sprintsApi.list(projectId, {}).then(r => {
      const d = r.data
      if (Array.isArray(d)) return d
      return []
    }),
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
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => set('name')(e.target.value)} placeholder={traducir('sprintplanning.nombre_del_plan')} inputClassName="spl-input" />
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{t('sprint_planning.team_capacity_sp')}</label>
                <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={form.team_capacity} onChange={e => set('team_capacity')(+e.target.value)} min={1} inputClassName="spl-input" />
              </div>
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={ls}>{t('sprint_planning.sprint_optional')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-3`} className={is} value={form.sprint_id} onChange={e => set('sprint_id')(e.target.value)}>
                  <option value="">{t('sprint_planning.no_specific_sprint')}</option>
                  {(sprints as Array<{ id: string | number; name: string }>).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </Select>
              </div>
            </div>
            <div className="spl-info">
              <strong className="u-accent">{t('sprint_planning.how_it_works')}:</strong> {t('sprint_planning.how_it_works_desc')}
              {semEstimate && (
                <div className="spl-semantic">
                  <div className="spl-semantic__title"><Brain size={14} aria-hidden />{t('sprint_planning.semantic_estimate_title')}</div>
                  <div className="spl-semantic__row">
                    <span><Clock size={13} aria-hidden />{t('sprint_planning.base_label')}: <strong className="u-text1">{semEstimate.total_base_hours}h</strong></span>
                    <span><AlertTriangle size={13} aria-hidden />{t('sprint_planning.risk_label')}: <strong className="u-warning">+{semEstimate.risk_premium_pct}%</strong></span>
                    <span><Package size={13} aria-hidden />{t('sprint_planning.recommended_label')}: <strong className="u-success">{semEstimate.recommended_hours}h</strong></span>
                    <span><CheckCircle2 size={13} aria-hidden />{t('sprint_planning.fits_sprint_label')}: <strong className={semEstimate.fit_in_sprint ? 'spl-fit--yes' : 'spl-fit--no'}>{semEstimate.fit_in_sprint ? t('sprint_planning.yes') : t('sprint_planning.no')}</strong></span>
                  </div>
                </div>
              )}
            </div>
            <div className="spl-footer">
              <Button variant="ghost" icon={<Brain size={14} />} onClick={estimateBacklog} disabled={!projectId} loading={estimating}>
                {estimating ? t('sprint_planning.estimating') : t('sprint_planning.estimate_backlog')}
              </Button>
              <div className="u-row-10">
                <Button variant="secondary" onClick={onClose}>{t('sprint_planning.cancel')}</Button>
                <Button icon={<Sparkles size={14} />} onClick={() => generate()} disabled={!form.name.trim() || !form.team_capacity} loading={isPending}>
                  {isPending ? t('sprint_planning.generating') : t('sprint_planning.generate_plan_btn')}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="spl-result">
              <div className="spl-result__title"><CheckCircle2 size={16} aria-hidden />{t('sprint_planning.plan_generated_label')}: {result.name}</div>
              <div className="u-text2-sm">{t('sprint_planning.resultado_meta', { tareas: result.task_count, puntos: result.total_points, capacidad: result.team_capacity })}</div>
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
                <AlertTriangle size={14} aria-hidden className="spl-warning__icon" />
                <span>{result.unestimated_count} {t('sprint_planning.unestimated_warning_suffix')}</span>
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
    const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [showGenerate, setShowGenerate] = useState(false)
  const [expandPlan, setExpandPlan] = useState<string | null>(null)

  const { data: projectsRaw = [] } = useListaDeProyectos()
  const projects = projectsRaw as unknown as ProjectItem[]
  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['sprint-plans', project],
    queryFn: () => sprintPlansApi.get(project).then(r => r.data),
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
      <PageHeader icon={<Sparkles size={18} />} title={t('nav.sprint_planning')} subtitle={t('sprint_planning.subtitle')}
        actions={project && <Button icon={<Sparkles size={14} />} onClick={() => setShowGenerate(true)}>{t('sprint_planning.generate_plan_action')}</Button>} showListExport={false} />

      <div className="u-stack-16">
      <Card className="spl-filtros">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{t('sprint_planning.project_label')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-1`} value={project} onChange={e => setProject(e.target.value)} className={`${is} spl-input--project`}>
          <option value="">{t('sprint_planning.select_project_opt')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </Card>

      {!project && <EmptyState icon={<FolderKanban size={28} />} title={t('sprint_planning.select_project_title')} description={t('sprint_planning.select_project_desc2')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && plans.length === 0 && (
        <EmptyState
          icon={<Sparkles size={28} />}
          title={t('sprint_planning.no_plans_title')}
          description={t('sprint_planning.no_plans_desc')}
          action={<Button icon={<Sparkles size={14} />} onClick={() => setShowGenerate(true)}>{t('sprint_planning.generate_first_plan')}</Button>}
        />
      )}

      {project && plans.length > 0 && (
        <div className="u-stack-10">
          {plans.map(plan => {
            const pct = plan.team_capacity > 0 ? Math.round(plan.total_points/plan.team_capacity*100) : 0
            const isExpanded = expandPlan === plan.id
            const usoPlan = { '--spl-c': colorDeUso(pct), '--spl-pct': `${Math.min(100, pct)}%` } as CSSProperties
            return (
              <Card key={plan.id} className="spl-plan">
                <div className={`spl-plan__head${isExpanded ? ' spl-plan__head--open' : ''}`}>
                  <div className="u-flex1-min0">
                    <div className="u-row-center-10 u-wrap-8">
                      <span className="u-md-600">{plan.name}</span>
                      <StatusBadge kind={STATUS_KIND[plan.status] || 'neutral'} caps={false}>{t('sprint_planning.status_' + plan.status, plan.status)}</StatusBadge>
                    </div>
                    <div className="spl-plan__meta">
                      {t('sprint_planning.plan_meta', { tareas: plan.task_count, puntos: plan.total_points, capacidad: plan.team_capacity, pct })}
                    </div>
                  </div>
                  <div className="u-row-8">
                    {plan.status === 'draft' && <>
                      <Button size="sm" icon={<Check size={14} />} onClick={() => updateStatus({id:plan.id,status:'accepted'})}>
                        {t('sprint_planning.accept_btn')}
                      </Button>
                      <Button size="sm" variant="secondary" icon={<X size={14} />} onClick={() => updateStatus({id:plan.id,status:'rejected'})}>
                        {t('sprint_planning.reject_btn')}
                      </Button>
                    </>}
                    <Button size="sm" variant="ghost" icon={isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />} onClick={() => setExpandPlan(isExpanded ? null : plan.id)}>
                      {isExpanded ? t('sprint_planning.hide_details') : t('sprint_planning.view_details')}
                    </Button>
                    <IconButton variante="caja" tono="peligro" onClick={() => { openConfirmGlobal({ message: t('sprint_planning.delete_confirm', { name: plan.name }), onConfirm: () => deletePlan(plan.id), danger: true }) }} ariaLabel={t('sprint_planning.eliminar_plan')} title={t('sprint_planning.eliminar_plan')}>
                      <Trash2 size={15} aria-hidden />
                    </IconButton>
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
              </Card>
            )
          })}
        </div>
      )}
      </div>

      {showGenerate && (
        <GenerateModal projectId={project} onClose={() => setShowGenerate(false)} />
      )}
    </PageShell>
  )
}
