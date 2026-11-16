/**
 * ProjectTemplatesPage — Manage and instantiate project templates.
 * Templates predefine phases, tasks, risks and deliverables for fast project creation.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { templatesApi, type ApiError } from '../services/api'
import type { PlantillaDeProyecto, ProyectoDesdePlantilla } from '../services/api/tipos-proyectos'
import { Spinner, useDialogo } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { LayoutTemplate } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { SUCCESS_MESSAGE_LONG_MS, SUCCESS_MESSAGE_MS } from '../constants/timings'
import './ProjectTemplatesPage.css'

const PHASE_COLOR = 'var(--accent)'
const TASK_COLOR  = 'var(--success)'
const RISK_COLOR  = 'var(--warning)'
const DELIV_COLOR = 'var(--accent)'

// Formas de `list_templates_all` (app/services/billing_reports_service/plantillas.py)
// y de lo que acepta `TemplateCreate` (app/schemas/billing_reports.py).
type TplTask = { id?: string; title: string; estimated_hours: number | null; skill_required: string | null }
type TplPhase = {
  id?: string; name: string; order?: number; description?: string | null
  estimated_weeks: number | null; estimated_hours?: number | null; tasks: TplTask[]
}
type TplRisk = { title: string; category: string | null; probability: string; impact: string; mitigation_plan: string | null }
type TplDeliverable = {
  name: string; format: string | null; week_offset: number | null; billing_pct: number | null; acceptance_criteria: string | null
}
/** ProjectTemplateOut: el listado trae fases y tareas, y de riesgos y entregables solo el recuento. */
type Tpl = PlantillaDeProyecto



function TemplateCard({ tpl, onInstantiate, t }: { tpl: Tpl; onInstantiate: (tpl: Tpl) => void; t: (k: string, p?: Record<string, unknown>) => string }) {
  const [expanded, setExpanded] = useState(false)
  const phaseCount = tpl.phases?.length || 0
  const taskCount = (tpl.phases || []).reduce((acc, p) => acc + (p.tasks?.length || 0), 0)
  const riskCount = tpl.risk_count
  const deliverableCount = tpl.deliverable_count

  return (
    <div className="ptpl-card"
    >
      <div className="ptpl-row">
        <div>
          <div className="ptpl-text-md-em-strong">{tpl.name}</div>
          {tpl.description && (
            <div className="ptpl-box-muted">
              {tpl.description}
            </div>
          )}
        </div>
        <div className="ptpl-row-2">
          {tpl.estimated_weeks && (
            <StatusBadge color="var(--text-3)" caps={false}>{`${tpl.estimated_weeks}${t('project_templates.weeks_abbr')}`}</StatusBadge>
          )}
          {tpl.estimated_hours && (
            <StatusBadge color="var(--text-3)" caps={false}>{`${tpl.estimated_hours}h`}</StatusBadge>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="ptpl-row-3">
        {phaseCount > 0 && <StatusBadge color={PHASE_COLOR} caps={false}>{`${phaseCount} ${t('projects.phases').toLowerCase()}`}</StatusBadge>}
        {taskCount > 0 && <StatusBadge color={TASK_COLOR} caps={false}>{`${taskCount} ${t('tasks.title').toLowerCase()}`}</StatusBadge>}
        {riskCount > 0 && <StatusBadge color={RISK_COLOR} caps={false}>{`${riskCount} ${t('risks.title').toLowerCase()}`}</StatusBadge>}
        {deliverableCount > 0 && <StatusBadge color={DELIV_COLOR} caps={false}>{`${deliverableCount} ${t('project_templates.deliverables').toLowerCase()}`}</StatusBadge>}
        {(tpl.dependency_count ?? 0) > 0 && <StatusBadge color={TASK_COLOR} caps={false}>{t('planificador.plantilla_dependencias', { n: tpl.dependency_count ?? 0 })}</StatusBadge>}
        {(tpl.role_count ?? 0) > 0 && <StatusBadge color={PHASE_COLOR} caps={false}>{t('planificador.plantilla_roles', { n: tpl.role_count ?? 0 })}</StatusBadge>}
        {(tpl.document_count ?? 0) > 0 && <StatusBadge color={DELIV_COLOR} caps={false}>{t('planificador.plantilla_documentos', { n: tpl.document_count ?? 0 })}</StatusBadge>}
      </div>

      <div className="u-row-10">
        <button className="ptpl-btn-ghost-sm"
          onClick={() => setExpanded(v => !v)}
        >
          {expanded ? t('project_templates.hide_detail') : t('project_templates.view_detail')}
        </button>
        <button className="ptpl-btn-sm"
          onClick={() => onInstantiate(tpl)}
        >
          {t('project_templates.create_from_template')}
        </button>
      </div>

      {expanded && (
        <div className="ptpl-box">
          {/* Phases */}
          {tpl.phases?.map((phase, i) => (
            <div key={i} className="u-mb-10">
              <div className="ptpl-text-sm-strong ptpl-text">
                {t('project_templates.phase')} {phase.order}: {phase.name}
              </div>
              {phase.tasks?.map((task, j) => (
                <div className="ptpl-row-muted" key={j}>
                  <span className="ptpl-text-2">●</span>
                  {task.title}
                  {task.estimated_hours && <span className="u-text3">({task.estimated_hours}h)</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function CreateTemplateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useAppT()
  const [form, setForm] = useState<{ name: string; description: string; project_type: string; estimated_weeks: string; estimated_hours: string; phases: TplPhase[]; risks: TplRisk[]; deliverables: TplDeliverable[] }>({
    name: '',
    description: '',
    project_type: 'consulting',
    estimated_weeks: '',
    estimated_hours: '',
    phases: [],
    risks: [],
    deliverables: [],
  })
  const [phase, setPhase] = useState<{ name: string; description: string; estimated_weeks: string; estimated_hours: string; tasks: TplTask[] }>({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
  const [task, setTask] = useState({ title: '', estimated_hours: '', skill_required: '' })
  const [risk, setRisk] = useState({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  const [deliverable, setDeliverable] = useState({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => templatesApi.create(payload),
    onSuccess: () => onDone(),
    onError: (err: ApiError) => setError(err.response?.data?.detail || t('plantillas_ui.error_crear')),
  })

  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))

  const addTaskToPhase = () => {
    if (!task.title?.trim()) return
    setPhase(p => ({
      ...p,
      tasks: [
        ...p.tasks,
        {
          title: task.title.trim(),
          estimated_hours: task.estimated_hours ? Number(task.estimated_hours) : null,
          skill_required: task.skill_required || null,
        },
      ],
    }))
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addPhase = () => {
    if (!phase.name?.trim()) return
    setForm(f => ({
      ...f,
      phases: [
        ...f.phases,
        {
          name: phase.name.trim(),
          description: phase.description || null,
          estimated_weeks: phase.estimated_weeks ? Number(phase.estimated_weeks) : null,
          estimated_hours: phase.estimated_hours ? Number(phase.estimated_hours) : null,
          tasks: phase.tasks,
        },
      ],
    }))
    setPhase({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addRisk = () => {
    if (!risk.title?.trim()) return
    setForm(f => ({
      ...f,
      risks: [
        ...f.risks,
        {
          title: risk.title.trim(),
          category: risk.category || null,
          probability: risk.probability,
          impact: risk.impact,
          mitigation_plan: risk.mitigation_plan || null,
        },
      ],
    }))
    setRisk({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  }

  const addDeliverable = () => {
    if (!deliverable.name?.trim()) return
    setForm(f => ({
      ...f,
      deliverables: [
        ...f.deliverables,
        {
          name: deliverable.name.trim(),
          format: deliverable.format || null,
          week_offset: deliverable.week_offset ? Number(deliverable.week_offset) : null,
          billing_pct: deliverable.billing_pct ? Number(deliverable.billing_pct) : null,
          acceptance_criteria: deliverable.acceptance_criteria || null,
        },
      ],
    }))
    setDeliverable({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  }

  const submit = () => {
    if (!form.name.trim()) {
      setError(t('plantillas_ui.nombre_obligatorio'))
      return
    }
    mutation.mutate({
      ...form,
      estimated_weeks: form.estimated_weeks ? Number(form.estimated_weeks) : null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
    })
  }
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)

  return (
    <div className="ptpl-row-4">
      <div className="ptpl-card-2" ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('projecttemplates.nueva_plantilla_desde_cero')}>
        <div className="ptpl-text-lg-em-strong">{t('projecttemplates.nueva_plantilla_desde_cero')}</div>

        <div className="ptpl-grid">
          <input className="ptpl-inp" aria-label={t('plantillas_ui.nombre_req')} value={form.name} onChange={set('name')} placeholder={t('plantillas_ui.nombre_req')} />
          <input className="ptpl-inp" aria-label={t('plantillas_ui.tipo')} value={form.project_type} onChange={set('project_type')} placeholder={t('plantillas_ui.tipo')} />
          <input className="ptpl-inp" aria-label={t('plantillas_ui.semanas')} type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} placeholder={t('plantillas_ui.semanas')} />
          <input className="ptpl-inp" aria-label={t('plantillas_ui.horas')} type="number" value={form.estimated_hours} onChange={set('estimated_hours')} placeholder={t('plantillas_ui.horas')} />
        </div>
        <textarea className="ptpl-inp ptpl-input" aria-label={t('projecttemplates.descripcion')} value={form.description} onChange={set('description')} rows={2} placeholder={t('projecttemplates.descripcion')} />

        <div className="u-mb-16">
          <div className="ptpl-h3">{t('plantillas_ui.fases_n', { n: form.phases.length })}</div>
          <div className="ptpl-grid-2">
            <input className="ptpl-inp" aria-label={t('plantillas_ui.nombre_fase')} value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} placeholder={t('plantillas_ui.nombre_fase')} />
            <input className="ptpl-inp" aria-label={t('projecttemplates.descripcion_fase')} value={phase.description} onChange={e => setPhase(f => ({ ...f, description: e.target.value }))} placeholder={t('projecttemplates.descripcion_fase')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.semanas')} type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} placeholder={t('plantillas_ui.semanas')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.horas')} type="number" value={phase.estimated_hours} onChange={e => setPhase(f => ({ ...f, estimated_hours: e.target.value }))} placeholder={t('plantillas_ui.horas')} />
          </div>
          <div className="ptpl-grid-3">
            <input className="ptpl-inp" aria-label={t('projecttemplates.titulo_tarea')} value={task.title} onChange={e => setTask(f => ({ ...f, title: e.target.value }))} placeholder={t('projecttemplates.titulo_tarea')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.horas')} type="number" value={task.estimated_hours} onChange={e => setTask(f => ({ ...f, estimated_hours: e.target.value }))} placeholder={t('plantillas_ui.horas')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.skill')} value={task.skill_required} onChange={e => setTask(f => ({ ...f, skill_required: e.target.value }))} placeholder={t('plantillas_ui.skill')} />
            <button className="ptpl-btn-secondary" onClick={addTaskToPhase}>{t('plantillas_ui.anadir_tarea')}</button>
          </div>
          {phase.tasks.length > 0 && (
            <div className="ptpl-row-5">
              {phase.tasks.map((tk, i) => <span className="ptpl-chip" key={`${tk.title}-${i}`}>{tk.title}{tk.estimated_hours ? ` (${tk.estimated_hours}h)` : ''}</span>)}
            </div>
          )}
          <div className="ptpl-row-6">
            <button className="ptpl-btn-secondary" onClick={addPhase}>{t('plantillas_ui.anadir_fase')}</button>
          </div>
        </div>

        <div className="u-mb-16">
          <div className="ptpl-h3">{t('plantillas_ui.riesgos_n', { n: form.risks.length })}</div>
          <div className="ptpl-grid-4">
            <input className="ptpl-inp" aria-label={t('projecttemplates.titulo_riesgo')} value={risk.title} onChange={e => setRisk(f => ({ ...f, title: e.target.value }))} placeholder={t('projecttemplates.titulo_riesgo')} />
            <input className="ptpl-inp" aria-label={t('projecttemplates.categoria')} value={risk.category} onChange={e => setRisk(f => ({ ...f, category: e.target.value }))} placeholder={t('projecttemplates.categoria')} />
            <select className="ptpl-inp" aria-label={t('plantillas_ui.probabilidad')} value={risk.probability} onChange={e => setRisk(f => ({ ...f, probability: e.target.value }))}><option value="low">{t('plantillas_ui.prob_low')}</option><option value="medium">{t('plantillas_ui.prob_medium')}</option><option value="high">{t('plantillas_ui.prob_high')}</option></select>
            <select className="ptpl-inp" aria-label={t('plantillas_ui.impacto')} value={risk.impact} onChange={e => setRisk(f => ({ ...f, impact: e.target.value }))}><option value="minor">{t('plantillas_ui.imp_minor')}</option><option value="moderate">{t('plantillas_ui.imp_moderate')}</option><option value="major">{t('plantillas_ui.imp_major')}</option><option value="critical">{t('plantillas_ui.imp_critical')}</option></select>
            <button className="ptpl-btn-secondary" onClick={addRisk}>{t('plantillas_ui.anadir_riesgo')}</button>
          </div>
          <textarea className="ptpl-inp ptpl-input-2" aria-label={t('projecttemplates.mitigacion_opcional')} value={risk.mitigation_plan} onChange={e => setRisk(f => ({ ...f, mitigation_plan: e.target.value }))} rows={2} placeholder={t('projecttemplates.mitigacion_opcional')} />
        </div>

        <div className="u-mb-16">
          <div className="ptpl-h3">{t('plantillas_ui.entregables_n', { n: form.deliverables.length })}</div>
          <div className="ptpl-grid-4">
            <input className="ptpl-inp" aria-label={t('plantillas_ui.nombre')} value={deliverable.name} onChange={e => setDeliverable(f => ({ ...f, name: e.target.value }))} placeholder={t('plantillas_ui.nombre')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.formato')} value={deliverable.format} onChange={e => setDeliverable(f => ({ ...f, format: e.target.value }))} placeholder={t('plantillas_ui.formato')} />
            <input className="ptpl-inp" aria-label={t('plantillas_ui.semana')} type="number" value={deliverable.week_offset} onChange={e => setDeliverable(f => ({ ...f, week_offset: e.target.value }))} placeholder={t('plantillas_ui.semana')} />
            <input className="ptpl-inp" aria-label={t('projecttemplates.facturacion')} type="number" value={deliverable.billing_pct} onChange={e => setDeliverable(f => ({ ...f, billing_pct: e.target.value }))} placeholder={t('projecttemplates.facturacion')} />
            <button className="ptpl-btn-secondary" onClick={addDeliverable}>{t('plantillas_ui.anadir_entregable')}</button>
          </div>
          <textarea className="ptpl-inp ptpl-input-2" aria-label={t('projecttemplates.criterio_aceptacion_opcional')} value={deliverable.acceptance_criteria} onChange={e => setDeliverable(f => ({ ...f, acceptance_criteria: e.target.value }))} rows={2} placeholder={t('projecttemplates.criterio_aceptacion_opcional')} />
        </div>

        {error && <div className="ptpl-text-danger-sm">{error}</div>}

        <div className="u-actions-10">
          <button className="ptpl-btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
          <button className="ptpl-btn-primary" onClick={submit} disabled={mutation.isPending}>{mutation.isPending ? t('plantillas_ui.creando') : t('plantillas_ui.crear_plantilla')}</button>
        </div>
      </div>
    </div>
  )
}






// ── Modal: instantiate template ───────────────────────────────────────────────

function InstantiateModal({ tpl, onClose, onDone, t }: { tpl: Tpl; onClose: () => void; onDone: (data: ProyectoDesdePlantilla) => void; t: (k: string) => string }) {
  const [projectName, setProjectName] = useState(tpl?.name || '')
  const [clientName, setClientName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => templatesApi.instantiate(tpl.id, data),
    onSuccess: (res) => {
      onDone(res.data)
    },
    onError: (err: ApiError) => {
      setError(err.response?.data?.detail || t('project_templates.creation_error'))
    },
  })

  const submit = () => {
    if (!projectName.trim()) { setError(t('project_templates.project_name_required')); return }
    mutation.mutate({
      // `instantiate_template` lee `name`; con `project_name` (auditoría 2026-11) el nombre
      // escrito se perdía y el proyecto se llamaba como la plantilla y la fecha.
      name: projectName.trim(),
      client_name: clientName.trim() || undefined,
      start_date: startDate || undefined,
    })
  }
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose)

  return (
    <div className="ptpl-row-4">
      <div className="ptpl-card-3" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="template-apply-title">
        <div className="ptpl-text-lg-em-strong-2" id="template-apply-title">
          {t('project_templates.create_project_from')} «{tpl?.name}»
        </div>

        <label className="ptpl-label">
          <div className="ptpl-text-muted-sm">
            {t('project_templates.project_name_label')}
          </div>
          <input className="ptpl-input-3"
            aria-label={t('project_templates.project_name_label')}
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            placeholder={t('project_templates.project_name_placeholder')}
          />
        </label>

        <label className="ptpl-label">
          <div className="ptpl-text-muted-sm">
            {t('project_templates.client_label')}
          </div>
          <input className="ptpl-input-3"
            aria-label={t('project_templates.client_label')}
            value={clientName}
            onChange={e => setClientName(e.target.value)}
            placeholder={t('project_templates.client_placeholder')}
          />
        </label>

        <label className="ptpl-label-2">
          <div className="ptpl-text-muted-sm">
            {t('project_templates.start_date_label')}
          </div>
          <DateInput
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            className="ptpl-input-3"
          />
        </label>

        {error && (
          <div className="ptpl-card-danger">
            {error}
          </div>
        )}

        <div className="u-actions-10">
          <button className="ptpl-btn-ghost"
            onClick={onClose}
          >
            {t('project_templates.cancel')}
          </button>
          <button className="ptpl-btn"
            onClick={submit}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? t('project_templates.creating') : t('project_templates.create_project')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProjectTemplatesPage() {
  const t = useAppT()
  const queryClient = useQueryClient()
  const [selectedTpl, setSelectedTpl] = useState<Tpl | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['project-templates'],
    queryFn: () => templatesApi.list().then(r => r.data),
  })

  const handleInstantiateSuccess = (result: ProyectoDesdePlantilla) => {
    setSelectedTpl(null)
    setSuccessMsg(
      t('project_templates.created_ok')
        .replace('{project_name}', result.project_name)
        .replace('{project_code}', result.project_code)
    )
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    setTimeout(() => setSuccessMsg(null), SUCCESS_MESSAGE_LONG_MS)
  }

  return (
    <PageShell>
      <PageHeader
        icon={<LayoutTemplate size={18} />}
        title={t('project_templates.title')}
        subtitle={t('project_templates.subtitle')}
        showListExport={templates.length > 0}
        exportTargetSelector='[data-export-table="project-templates-list"]'
        exportFilePrefix='project_templates'
      />

      <div className="ptpl-row-7">
        <button className="ptpl-btn-primary" onClick={() => setShowCreate(true)}>{t('plantillas_ui.crear_desde_cero')}</button>
      </div>

      {/* Success banner */}
      {successMsg && (
        <div className="ptpl-row-success">
          {successMsg}
          <button className="ptpl-btn-success-lg-em" onClick={() => setSuccessMsg(null)}>×</button>
        </div>
      )}

      {isLoading ? (
        <div className="ptpl-box-2"><Spinner /></div>
      ) : templates.length === 0 ? (
        <div className="ptpl-box-muted-2">
          <div className="u-empty-icon">📋</div>
          <div className="ptpl-text-lg">{t('project_templates.empty_title')}</div>
          <div className="ptpl-text-base">
            {t('project_templates.empty_subtitle')}
          </div>
        </div>
      ) : (
        <div data-export-table="project-templates-list" className="u-stack-16">
          {templates.map(tpl => (
            <TemplateCard
              key={tpl.id}
              tpl={tpl}
              onInstantiate={setSelectedTpl}
              t={t}
            />
          ))}
        </div>
      )}

      {selectedTpl && (
        <InstantiateModal
          tpl={selectedTpl}
          onClose={() => setSelectedTpl(null)}
          onDone={handleInstantiateSuccess}
          t={t}
        />
      )}
      {showCreate && (
        <CreateTemplateModal
          onClose={() => setShowCreate(false)}
          onDone={() => {
            setShowCreate(false)
            queryClient.invalidateQueries({ queryKey: ['project-templates'] })
            setSuccessMsg(t('plantillas_ui.creada'))
            setTimeout(() => setSuccessMsg(null), SUCCESS_MESSAGE_MS)
          }}
        />
      )}
    </PageShell>
  )
}
