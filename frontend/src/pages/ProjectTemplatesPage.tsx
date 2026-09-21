/**
 * ProjectTemplatesPage — Manage and instantiate project templates.
 * Templates predefine phases, tasks, risks and deliverables for fast project creation.
 */
import type { CSSProperties, ReactNode } from 'react'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { templatesApi } from '../services/api'
import { Spinner } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { LayoutTemplate } from 'lucide-react'

const PHASE_COLOR = 'var(--accent)'
const TASK_COLOR  = 'var(--success)'
const RISK_COLOR  = 'var(--warning)'
const DELIV_COLOR = 'var(--accent)'

type Tpl = { [k: string]: unknown; id: string; name?: string; description?: string; estimated_weeks?: number; estimated_hours?: number; phases?: any[]; risks?: any[]; deliverables?: any[]; risk_count?: number; deliverable_count?: number }

function Badge({ color, label }: { color: string; label: ReactNode }) {
  return (
    <span style={{
      fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 7px', borderRadius: 4,
      background: `${color}20`, color,
    }}>{label}</span>
  )
}

function TemplateCard({ tpl, onInstantiate, t }: { tpl: Tpl; onInstantiate: (tpl: Tpl) => void; t: (k: string) => string }) {
  const [expanded, setExpanded] = useState(false)
  const phaseCount = tpl.phases?.length || 0
  const taskCount = (tpl.phases || []).reduce((acc: number, p: any) => acc + (p.tasks?.length || 0), 0)
  const riskCount = tpl.risk_count || tpl.risks?.length || 0
  const deliverableCount = tpl.deliverable_count || tpl.deliverables?.length || 0

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 12, padding: 20, transition: 'box-shadow .15s',
    }}
      onPointerEnter={e => e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,.08)'}
      onPointerLeave={e => e.currentTarget.style.boxShadow = 'none'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>{tpl.name}</div>
          {tpl.description && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 3, maxWidth: 380 }}>
              {tpl.description}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {tpl.estimated_weeks && (
            <Badge color="var(--text-3)" label={`${tpl.estimated_weeks}${t('project_templates.weeks_abbr')}`} />
          )}
          {tpl.estimated_hours && (
            <Badge color="var(--text-3)" label={`${tpl.estimated_hours}h`} />
          )}
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 14, flexWrap: 'wrap' }}>
        {phaseCount > 0 && <Badge color={PHASE_COLOR} label={`${phaseCount} ${t('projects.phases').toLowerCase()}`} />}
        {taskCount > 0 && <Badge color={TASK_COLOR}  label={`${taskCount} ${t('tasks.title').toLowerCase()}`} />}
        {riskCount > 0 && <Badge color={RISK_COLOR}  label={`${riskCount} ${t('risks.title').toLowerCase()}`} />}
        {deliverableCount > 0 && <Badge color={DELIV_COLOR} label={`${deliverableCount} ${t('project_templates.deliverables').toLowerCase()}`} />}
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            padding: '6px 14px', borderRadius: 7, border: '1px solid var(--surface-4)',
            background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)",
          }}
        >
          {expanded ? t('project_templates.hide_detail') : t('project_templates.view_detail')}
        </button>
        <button
          onClick={() => onInstantiate(tpl)}
          style={{
            padding: '6px 14px', borderRadius: 7, border: 'none',
            background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 700,
          }}
        >
          {t('project_templates.create_from_template')}
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: 16, borderTop: '1px solid var(--surface-4)', paddingTop: 14 }}>
          {/* Phases */}
          {tpl.phases?.map((phase, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: PHASE_COLOR, marginBottom: 4 }}>
                {t('project_templates.phase')} {phase.order}: {phase.name}
              </div>
              {phase.tasks?.map((task: any, j: number) => (
                <div key={j} style={{
                  fontSize: "var(--text-xs)", color: 'var(--text-2)', paddingLeft: 14,
                  display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2,
                }}>
                  <span style={{ color: TASK_COLOR }}>●</span>
                  {task.title}
                  {task.estimated_hours && <span style={{ color: 'var(--text-3)' }}>({task.estimated_hours}h)</span>}
                </div>
              ))}
            </div>
          ))}
          {/* Risks */}
          {(tpl.risks?.length ?? 0) > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: RISK_COLOR, marginBottom: 4 }}>{t('project_templates.predefined_risks')}</div>
              {tpl.risks!.map((risk: any, i: number) => (
                <div key={i} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', paddingLeft: 14, marginBottom: 2, display: 'flex', gap: 8 }}>
                  <span style={{ color: RISK_COLOR }}>▲</span>{risk.title}
                </div>
              ))}
            </div>
          )}
          {/* Deliverables */}
          {(tpl.deliverables?.length ?? 0) > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: DELIV_COLOR, marginBottom: 4 }}>{t('project_templates.deliverables')}</div>
              {tpl.deliverables!.map((d: any, i: number) => (
                <div key={i} style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', paddingLeft: 14, marginBottom: 2, display: 'flex', gap: 8 }}>
                  <span style={{ color: DELIV_COLOR }}>◆</span>{d.title}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CreateTemplateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useAppT()
  const [form, setForm] = useState<{ name: string; description: string; project_type: string; estimated_weeks: string; estimated_hours: string; phases: any[]; risks: any[]; deliverables: any[] }>({
    name: '',
    description: '',
    project_type: 'consulting',
    estimated_weeks: '',
    estimated_hours: '',
    phases: [],
    risks: [],
    deliverables: [],
  })
  const [phase, setPhase] = useState<{ name: string; description: string; estimated_weeks: string; estimated_hours: string; tasks: any[] }>({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
  const [task, setTask] = useState({ title: '', estimated_hours: '', skill_required: '' })
  const [risk, setRisk] = useState({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  const [deliverable, setDeliverable] = useState({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => templatesApi.create(payload),
    onSuccess: () => onDone(),
    onError: (err: any) => setError(err.response?.data?.detail || 'No se pudo crear la plantilla'),
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
      setError('El nombre es obligatorio')
      return
    }
    mutation.mutate({
      ...form,
      estimated_weeks: form.estimated_weeks ? Number(form.estimated_weeks) : null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
    })
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div role="dialog" aria-modal="true" style={{
        background: 'var(--surface-1)', borderRadius: 14, padding: 24, width: 900,
        maxWidth: '95vw', maxHeight: '92vh', overflowY: 'auto',
        boxShadow: '0 20px 60px rgba(0,0,0,.3)',
      }}>
        <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, marginBottom: 16 }}>{t('projecttemplates.nueva_plantilla_desde_cero')}</div>

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
          <input value={form.name} onChange={set('name')} placeholder="Nombre *" style={inp} />
          <input value={form.project_type} onChange={set('project_type')} placeholder="Tipo" style={inp} />
          <input type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} placeholder="Semanas" style={inp} />
          <input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} placeholder="Horas" style={inp} />
        </div>
        <textarea value={form.description} onChange={set('description')} rows={2} placeholder={t('projecttemplates.descripcion')} style={{ ...inp, width: '100%', resize: 'vertical', marginBottom: 14 }} />

        <div style={{ marginBottom: 16 }}>
          <div style={h3}>Fases ({form.phases.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr', gap: 8, marginBottom: 8 }}>
            <input value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} placeholder="Nombre fase" style={inp} />
            <input value={phase.description} onChange={e => setPhase(f => ({ ...f, description: e.target.value }))} placeholder={t('projecttemplates.descripcion_fase')} style={inp} />
            <input type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} placeholder="Semanas" style={inp} />
            <input type="number" value={phase.estimated_hours} onChange={e => setPhase(f => ({ ...f, estimated_hours: e.target.value }))} placeholder="Horas" style={inp} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8 }}>
            <input value={task.title} onChange={e => setTask(f => ({ ...f, title: e.target.value }))} placeholder={t('projecttemplates.titulo_tarea')} style={inp} />
            <input type="number" value={task.estimated_hours} onChange={e => setTask(f => ({ ...f, estimated_hours: e.target.value }))} placeholder="Horas" style={inp} />
            <input value={task.skill_required} onChange={e => setTask(f => ({ ...f, skill_required: e.target.value }))} placeholder="Skill" style={inp} />
            <button onClick={addTaskToPhase} style={btnSecondary}>+ Tarea</button>
          </div>
          {phase.tasks.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {phase.tasks.map((tk, i) => <span key={`${tk.title}-${i}`} style={chip}>{tk.title}{tk.estimated_hours ? ` (${tk.estimated_hours}h)` : ''}</span>)}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <button onClick={addPhase} style={btnSecondary}>+ Fase</button>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={h3}>Riesgos ({form.risks.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8 }}>
            <input value={risk.title} onChange={e => setRisk(f => ({ ...f, title: e.target.value }))} placeholder={t('projecttemplates.titulo_riesgo')} style={inp} />
            <input value={risk.category} onChange={e => setRisk(f => ({ ...f, category: e.target.value }))} placeholder={t('projecttemplates.categoria')} style={inp} />
            <select value={risk.probability} onChange={e => setRisk(f => ({ ...f, probability: e.target.value }))} style={inp}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select>
            <select value={risk.impact} onChange={e => setRisk(f => ({ ...f, impact: e.target.value }))} style={inp}><option value="minor">minor</option><option value="moderate">moderate</option><option value="major">major</option><option value="critical">critical</option></select>
            <button onClick={addRisk} style={btnSecondary}>+ Riesgo</button>
          </div>
          <textarea value={risk.mitigation_plan} onChange={e => setRisk(f => ({ ...f, mitigation_plan: e.target.value }))} rows={2} placeholder={t('projecttemplates.mitigacion_opcional')} style={{ ...inp, width: '100%', resize: 'vertical', marginTop: 8 }} />
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={h3}>Entregables ({form.deliverables.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8 }}>
            <input value={deliverable.name} onChange={e => setDeliverable(f => ({ ...f, name: e.target.value }))} placeholder="Nombre" style={inp} />
            <input value={deliverable.format} onChange={e => setDeliverable(f => ({ ...f, format: e.target.value }))} placeholder="Formato" style={inp} />
            <input type="number" value={deliverable.week_offset} onChange={e => setDeliverable(f => ({ ...f, week_offset: e.target.value }))} placeholder="Semana" style={inp} />
            <input type="number" value={deliverable.billing_pct} onChange={e => setDeliverable(f => ({ ...f, billing_pct: e.target.value }))} placeholder={t('projecttemplates.facturacion')} style={inp} />
            <button onClick={addDeliverable} style={btnSecondary}>+ Entregable</button>
          </div>
          <textarea value={deliverable.acceptance_criteria} onChange={e => setDeliverable(f => ({ ...f, acceptance_criteria: e.target.value }))} rows={2} placeholder={t('projecttemplates.criterio_aceptacion_opcional')} style={{ ...inp, width: '100%', resize: 'vertical', marginTop: 8 }} />
        </div>

        {error && <div style={{ color: 'var(--danger)', marginBottom: 12, fontSize: "var(--text-sm)" }}>{error}</div>}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={btnSecondary}>Cancelar</button>
          <button onClick={submit} disabled={mutation.isPending} style={btnPrimary}>{mutation.isPending ? 'Creando...' : 'Crear plantilla'}</button>
        </div>
      </div>
    </div>
  )
}

const inp: CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  color: 'var(--text-1)',
  padding: '8px 10px',
  fontSize: "var(--text-sm)",
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}

const btnPrimary: CSSProperties = {
  padding: '8px 16px',
  borderRadius: 8,
  border: 'none',
  background: 'var(--accent)',
  color: '#fff',
  cursor: 'pointer',
  fontWeight: 700,
  fontFamily: 'inherit',
}

const btnSecondary: CSSProperties = {
  padding: '8px 14px',
  borderRadius: 8,
  border: '1px solid var(--surface-4)',
  background: 'transparent',
  color: 'var(--text-2)',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const chip: CSSProperties = {
  fontSize: "var(--text-xs)",
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 16,
  padding: '2px 8px',
}

const h3: CSSProperties = {
  fontSize: "var(--text-base)",
  fontWeight: 700,
  marginBottom: 8,
}

// ── Modal: instantiate template ───────────────────────────────────────────────

function InstantiateModal({ tpl, onClose, onDone, t }: { tpl: Tpl; onClose: () => void; onDone: (data: any) => void; t: (k: string) => string }) {
  const [projectName, setProjectName] = useState(tpl?.name || '')
  const [clientName, setClientName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => templatesApi.instantiate(tpl.id, data),
    onSuccess: (res: { data: unknown }) => {
      onDone(res.data)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || t('project_templates.creation_error'))
    },
  })

  const submit = () => {
    if (!projectName.trim()) { setError(t('project_templates.project_name_required')); return }
    mutation.mutate({
      project_name: projectName.trim(),
      client_name: clientName.trim() || undefined,
      start_date: startDate || undefined,
    })
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div role="dialog" aria-modal="true" aria-labelledby="template-apply-title" style={{
        background: 'var(--surface-1)', borderRadius: 14, padding: 32, width: 480,
        maxWidth: '95vw', boxShadow: '0 20px 60px rgba(0,0,0,.3)',
      }}>
        <div id="template-apply-title" style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 20 }}>
          {t('project_templates.create_project_from')} «{tpl?.name}»
        </div>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.project_name_label')}
          </div>
          <input
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            placeholder={t('project_templates.project_name_placeholder')}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: "var(--text-base)", boxSizing: 'border-box',
            }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.client_label')}
          </div>
          <input
            value={clientName}
            onChange={e => setClientName(e.target.value)}
            placeholder={t('project_templates.client_placeholder')}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: "var(--text-base)", boxSizing: 'border-box',
            }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-2)', marginBottom: 5 }}>
            {t('project_templates.start_date_label')}
          </div>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 8,
              border: '1px solid var(--surface-4)', background: 'var(--surface-2)',
              color: 'var(--text-1)', fontSize: "var(--text-base)", boxSizing: 'border-box',
            }}
          />
        </label>

        {error && (
          <div style={{
            padding: '8px 12px', borderRadius: 8, background: 'color-mix(in srgb, var(--danger) 10%, transparent)',
            color: 'var(--danger)', fontSize: "var(--text-base)", marginBottom: 14,
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: 8, border: '1px solid var(--surface-4)',
              background: 'transparent', color: 'var(--text-2)', cursor: 'pointer',
            }}
          >
            {t('project_templates.cancel')}
          </button>
          <button
            onClick={submit}
            disabled={mutation.isPending}
            style={{
              padding: '8px 18px', borderRadius: 8, border: 'none',
              background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontWeight: 700,
            }}
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

  const { data: templates = [], isLoading } = useQuery<Tpl[]>({
    queryKey: ['project-templates'],
    queryFn: () => templatesApi.list().then((r: { data: Tpl[] }) => r.data),
  })

  const handleInstantiateSuccess = (result: any) => {
    setSelectedTpl(null)
    setSuccessMsg(
      t('project_templates.created_ok')
        .replace('{project_name}', result.project_name)
        .replace('{project_code}', result.project_code)
    )
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    setTimeout(() => setSuccessMsg(null), 6000)
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

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button onClick={() => setShowCreate(true)} style={btnPrimary}>+ Crear plantilla desde cero</button>
      </div>

      {/* Success banner */}
      {successMsg && (
        <div style={{
          padding: '12px 18px', borderRadius: 10, background: 'color-mix(in srgb, var(--success) 10%, transparent)',
          border: '1px solid color-mix(in srgb, var(--success) 25%, transparent)', color: 'var(--success)', fontSize: "var(--text-md)",
          marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {successMsg}
          <button onClick={() => setSuccessMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--success)', fontSize: "var(--text-lg-em)" }}>×</button>
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', paddingTop: 60 }}><Spinner /></div>
      ) : templates.length === 0 ? (
        <div style={{
          textAlign: 'center', paddingTop: 60, color: 'var(--text-3)',
        }}>
          <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>📋</div>
          <div style={{ fontSize: "var(--text-lg)", fontWeight: 600, marginBottom: 8 }}>{t('project_templates.empty_title')}</div>
          <div style={{ fontSize: "var(--text-base)" }}>
            {t('project_templates.empty_subtitle')}
          </div>
        </div>
      ) : (
        <div data-export-table="project-templates-list" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
            setSuccessMsg('Plantilla creada correctamente')
            setTimeout(() => setSuccessMsg(null), 5000)
          }}
        />
      )}
    </PageShell>
  )
}
