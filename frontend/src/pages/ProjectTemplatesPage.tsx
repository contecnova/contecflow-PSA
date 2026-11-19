/**
 * ProjectTemplatesPage — Manage and instantiate project templates.
 * Templates predefine phases, tasks, risks and deliverables for fast project creation.
 *
 * 16-11-2026: pasada de diseño. «Crear plantilla desde cero» pasa a la
 * cabecera (estaba en el cuerpo con «+ » en el texto); el vacío era propio
 * (emoji grande, título gris) y decía «Solicita al administrador» aunque hay
 * botón para crearla: ahora EmptyState con icono lucide y el mismo botón.
 * Modales y campos del kit (antes diálogos y campos grises propios), tipo de
 * proyecto como lista traducida (antes texto libre «consulting») y cliente
 * con el selector de clientes. Título = el del menú.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { templatesApi, type ApiError } from '../services/api'
import type { PlantillaDeProyecto, ProyectoDesdePlantilla } from '../services/api/tipos-proyectos'
import { Button, Card, ClientSelect, EmptyState, Input, Modal, Select, Spinner, Pulsable } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useCatalogo } from '../hooks/useCatalogo'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { LayoutTemplate, Plus, ChevronDown, ChevronUp, FolderPlus, CheckCircle2, X } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { SUCCESS_MESSAGE_LONG_MS, SUCCESS_MESSAGE_MS } from '../constants/timings'
import './ProjectTemplatesPage.css'

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
type Traducir = ReturnType<typeof useAppT>


function TemplateCard({ tpl, onInstantiate, t }: { tpl: Tpl; onInstantiate: (tpl: Tpl) => void; t: Traducir }) {
  const [expanded, setExpanded] = useState(false)
  const phaseCount = tpl.phases?.length || 0
  const taskCount = (tpl.phases || []).reduce((acc, p) => acc + (p.tasks?.length || 0), 0)
  const riskCount = tpl.risk_count
  const deliverableCount = tpl.deliverable_count

  return (
    <Card className="ptpl-tarjeta">
      <div className="ptpl-tarjeta__cabecera">
        <div className="u-min0">
          <div className="ptpl-tarjeta__nombre">{tpl.name}</div>
          {tpl.description && <div className="ptpl-tarjeta__desc">{tpl.description}</div>}
        </div>
        <div className="u-wrap-8">
          {tpl.estimated_weeks && (
            <StatusBadge caps={false}>{`${tpl.estimated_weeks} ${t('project_templates.weeks_abbr')}`}</StatusBadge>
          )}
          {tpl.estimated_hours && (
            <StatusBadge caps={false}>{`${tpl.estimated_hours} h`}</StatusBadge>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="u-wrap-8">
        {phaseCount > 0 && <StatusBadge kind="accent" caps={false}>{`${phaseCount} ${t('projects.phases').toLowerCase()}`}</StatusBadge>}
        {taskCount > 0 && <StatusBadge kind="success" caps={false}>{`${taskCount} ${t('tasks.title').toLowerCase()}`}</StatusBadge>}
        {riskCount > 0 && <StatusBadge kind="warning" caps={false}>{`${riskCount} ${t('risks.title').toLowerCase()}`}</StatusBadge>}
        {deliverableCount > 0 && <StatusBadge kind="accent" caps={false}>{`${deliverableCount} ${t('project_templates.deliverables').toLowerCase()}`}</StatusBadge>}
        {(tpl.dependency_count ?? 0) > 0 && <StatusBadge kind="neutral" caps={false}>{t('planificador.plantilla_dependencias', { n: tpl.dependency_count ?? 0 })}</StatusBadge>}
        {(tpl.role_count ?? 0) > 0 && <StatusBadge kind="neutral" caps={false}>{t('planificador.plantilla_roles', { n: tpl.role_count ?? 0 })}</StatusBadge>}
        {(tpl.document_count ?? 0) > 0 && <StatusBadge kind="neutral" caps={false}>{t('planificador.plantilla_documentos', { n: tpl.document_count ?? 0 })}</StatusBadge>}
      </div>

      <div className="u-wrap-8">
        <Button size="sm" variant="secondary" icon={expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />} onClick={() => setExpanded(v => !v)}>
          {expanded ? t('project_templates.hide_detail') : t('project_templates.view_detail')}
        </Button>
        <Button size="sm" icon={<FolderPlus size={13} />} onClick={() => onInstantiate(tpl)}>
          {t('project_templates.create_from_template')}
        </Button>
      </div>

      {expanded && (
        <div className="ptpl-detalle">
          {tpl.phases?.map((phase, i) => (
            <div key={i} className="u-stack-6">
              <div className="ptpl-detalle__fase">
                {t('project_templates.phase')} {phase.order}: {phase.name}
              </div>
              <ul className="ptpl-detalle__tareas">
                {phase.tasks?.map((task, j) => (
                  <li key={j}>
                    {task.title}
                    {task.estimated_hours && <span className="u-text3"> ({task.estimated_hours} h)</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function CreateTemplateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useAppT()
  const tiposDeProyecto = useCatalogo('project-types')
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

  return (
    <Modal open onClose={onClose} size="lg" title={t('projecttemplates.nueva_plantilla_desde_cero')}>
      <div className="u-stack-16">
        <div className="ptpl-campos ptpl-campos--4">
          <Input label={t('plantillas_ui.nombre_req')} value={form.name} onChange={set('name')} />
          <Select label={t('plantillas_ui.tipo')} value={form.project_type} onChange={set('project_type')}
            options={tiposDeProyecto.opciones} />
          <Input label={t('plantillas_ui.semanas')} type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} />
          <Input label={t('plantillas_ui.horas')} type="number" value={form.estimated_hours} onChange={set('estimated_hours')} />
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="ptpl-descripcion">{t('projecttemplates.descripcion')}</label>
          <textarea id="ptpl-descripcion" className="ds-input ptpl-textarea" value={form.description} onChange={set('description')} rows={2} />
        </div>

        <section className="ptpl-bloque">
          <h3 className="ptpl-bloque__titulo">{t('plantillas_ui.fases_n', { n: form.phases.length })}</h3>
          {form.phases.length > 0 && (
            <div className="u-wrap-8">
              {form.phases.map((ph, i) => <StatusBadge key={`${ph.name}-${i}`} kind="accent" caps={false}>{ph.name}</StatusBadge>)}
            </div>
          )}
          <div className="ptpl-campos ptpl-campos--4">
            <Input label={t('plantillas_ui.nombre_fase')} value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} />
            <Input label={t('projecttemplates.descripcion_fase')} value={phase.description} onChange={e => setPhase(f => ({ ...f, description: e.target.value }))} />
            <Input label={t('plantillas_ui.semanas')} type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} />
            <Input label={t('plantillas_ui.horas')} type="number" value={phase.estimated_hours} onChange={e => setPhase(f => ({ ...f, estimated_hours: e.target.value }))} />
          </div>
          <div className="ptpl-campos ptpl-campos--accion">
            <Input label={t('projecttemplates.titulo_tarea')} value={task.title} onChange={e => setTask(f => ({ ...f, title: e.target.value }))} />
            <Input label={t('plantillas_ui.horas')} type="number" value={task.estimated_hours} onChange={e => setTask(f => ({ ...f, estimated_hours: e.target.value }))} />
            <Input label={t('plantillas_ui.skill')} value={task.skill_required} onChange={e => setTask(f => ({ ...f, skill_required: e.target.value }))} />
            <Button variant="secondary" icon={<Plus size={14} />} onClick={addTaskToPhase} disabled={!task.title.trim()}>{t('plantillas_ui.anadir_tarea')}</Button>
          </div>
          {phase.tasks.length > 0 && (
            <div className="u-wrap-8">
              {phase.tasks.map((tk, i) => <StatusBadge key={`${tk.title}-${i}`} caps={false}>{tk.title}{tk.estimated_hours ? ` (${tk.estimated_hours} h)` : ''}</StatusBadge>)}
            </div>
          )}
          <div>
            <Button variant="secondary" icon={<Plus size={14} />} onClick={addPhase} disabled={!phase.name.trim()}>{t('plantillas_ui.anadir_fase')}</Button>
          </div>
        </section>

        <section className="ptpl-bloque">
          <h3 className="ptpl-bloque__titulo">{t('plantillas_ui.riesgos_n', { n: form.risks.length })}</h3>
          {form.risks.length > 0 && (
            <div className="u-wrap-8">
              {form.risks.map((rk, i) => <StatusBadge key={`${rk.title}-${i}`} kind="warning" caps={false}>{rk.title}</StatusBadge>)}
            </div>
          )}
          <div className="ptpl-campos ptpl-campos--riesgo">
            <Input label={t('projecttemplates.titulo_riesgo')} value={risk.title} onChange={e => setRisk(f => ({ ...f, title: e.target.value }))} />
            <Input label={t('projecttemplates.categoria')} value={risk.category} onChange={e => setRisk(f => ({ ...f, category: e.target.value }))} />
            <Select label={t('plantillas_ui.probabilidad')} value={risk.probability} onChange={e => setRisk(f => ({ ...f, probability: e.target.value }))} options={[
              { value: 'low', label: t('plantillas_ui.prob_low') },
              { value: 'medium', label: t('plantillas_ui.prob_medium') },
              { value: 'high', label: t('plantillas_ui.prob_high') },
            ]} />
            <Select label={t('plantillas_ui.impacto')} value={risk.impact} onChange={e => setRisk(f => ({ ...f, impact: e.target.value }))} options={[
              { value: 'minor', label: t('plantillas_ui.imp_minor') },
              { value: 'moderate', label: t('plantillas_ui.imp_moderate') },
              { value: 'major', label: t('plantillas_ui.imp_major') },
              { value: 'critical', label: t('plantillas_ui.imp_critical') },
            ]} />
          </div>
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor="ptpl-mitigacion">{t('projecttemplates.mitigacion_opcional')}</label>
            <textarea id="ptpl-mitigacion" className="ds-input ptpl-textarea" value={risk.mitigation_plan} onChange={e => setRisk(f => ({ ...f, mitigation_plan: e.target.value }))} rows={2} />
          </div>
          <div>
            <Button variant="secondary" icon={<Plus size={14} />} onClick={addRisk} disabled={!risk.title.trim()}>{t('plantillas_ui.anadir_riesgo')}</Button>
          </div>
        </section>

        <section className="ptpl-bloque">
          <h3 className="ptpl-bloque__titulo">{t('plantillas_ui.entregables_n', { n: form.deliverables.length })}</h3>
          {form.deliverables.length > 0 && (
            <div className="u-wrap-8">
              {form.deliverables.map((dl, i) => <StatusBadge key={`${dl.name}-${i}`} kind="accent" caps={false}>{dl.name}</StatusBadge>)}
            </div>
          )}
          <div className="ptpl-campos ptpl-campos--4">
            <Input label={t('plantillas_ui.nombre')} value={deliverable.name} onChange={e => setDeliverable(f => ({ ...f, name: e.target.value }))} />
            <Input label={t('plantillas_ui.formato')} value={deliverable.format} onChange={e => setDeliverable(f => ({ ...f, format: e.target.value }))} />
            <Input label={t('plantillas_ui.semana')} type="number" value={deliverable.week_offset} onChange={e => setDeliverable(f => ({ ...f, week_offset: e.target.value }))} />
            <Input label={t('projecttemplates.facturacion')} type="number" value={deliverable.billing_pct} onChange={e => setDeliverable(f => ({ ...f, billing_pct: e.target.value }))} />
          </div>
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor="ptpl-aceptacion">{t('projecttemplates.criterio_aceptacion_opcional')}</label>
            <textarea id="ptpl-aceptacion" className="ds-input ptpl-textarea" value={deliverable.acceptance_criteria} onChange={e => setDeliverable(f => ({ ...f, acceptance_criteria: e.target.value }))} rows={2} />
          </div>
          <div>
            <Button variant="secondary" icon={<Plus size={14} />} onClick={addDeliverable} disabled={!deliverable.name.trim()}>{t('plantillas_ui.anadir_entregable')}</Button>
          </div>
        </section>

        {error && <div className="ptpl-error" role="alert">{error}</div>}

        <div className="ptpl-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Plus size={14} />} onClick={submit} loading={mutation.isPending}>{mutation.isPending ? t('plantillas_ui.creando') : t('plantillas_ui.crear_plantilla')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Modal: instantiate template ───────────────────────────────────────────────

function InstantiateModal({ tpl, onClose, onDone, t }: { tpl: Tpl; onClose: () => void; onDone: (data: ProyectoDesdePlantilla) => void; t: Traducir }) {
  const [projectName, setProjectName] = useState(tpl?.name || '')
  const [clientId, setClientId] = useState('')
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

  return (
    <Modal open onClose={onClose} title={`${t('project_templates.create_project_from')} «${tpl?.name}»`}>
      <div className="u-stack-14">
        <Input label={t('project_templates.project_name_label')} value={projectName}
          onChange={e => setProjectName(e.target.value)} placeholder={t('project_templates.project_name_placeholder')} />
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="ptpl-cliente">{t('project_templates.client_label')}</label>
          <ClientSelect id="ptpl-cliente" value={clientId} placeholder={t('project_templates.client_placeholder')}
            onChange={(id, client) => { setClientId(id); setClientName(client?.name ?? '') }} />
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="ptpl-inicio">{t('project_templates.start_date_label')}</label>
          <DateInput id="ptpl-inicio" value={startDate} onChange={e => setStartDate(e.target.value)} className="ds-input" />
        </div>

        {error && <div className="ptpl-error" role="alert">{error}</div>}

        <div className="ptpl-acciones">
          <Button variant="secondary" onClick={onClose}>{t('project_templates.cancel')}</Button>
          <Button icon={<FolderPlus size={14} />} onClick={submit} loading={mutation.isPending}>
            {mutation.isPending ? t('project_templates.creating') : t('project_templates.create_project')}
          </Button>
        </div>
      </div>
    </Modal>
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
        title={t('nav.project_templates')}
        subtitle={t('project_templates.subtitle')}
        showListExport={templates.length > 0}
        exportTargetSelector='[data-export-table="project-templates-list"]'
        exportFilePrefix='project_templates'
        actions={
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('plantillas_ui.crear_desde_cero')}</Button>
        }
      />

      <div className="u-stack-16">
      {/* Success banner */}
      {successMsg && (
        <div className="ptpl-aviso" role="status">
          <CheckCircle2 size={15} aria-hidden />
          <span className="u-flex1-min0">{successMsg}</span>
          <Pulsable className="ptpl-aviso__cerrar" aria-label={t('common.close')} onClick={() => setSuccessMsg(null)}><X size={14} aria-hidden /></Pulsable>
        </div>
      )}

      {isLoading ? (
        <div className="ptpl-cargando"><Spinner /></div>
      ) : templates.length === 0 ? (
        <EmptyState icon={<LayoutTemplate size={28} />} title={t('project_templates.empty_title')}
          description={t('project_templates.empty_subtitle')}
          ctaLabel={t('plantillas_ui.crear_desde_cero')} onCta={() => setShowCreate(true)} />
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
      </div>

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
