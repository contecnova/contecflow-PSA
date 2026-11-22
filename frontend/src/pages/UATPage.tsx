/**
 * UATPage — Gestión de casos UAT (User Acceptance Testing)
 * Define criterios de aceptación por proyecto/tarea y registra su ejecución.
 * Permite exportar el plan para enviar al cliente.
 *
 * 16-11-2026: título del menú (nav.uat); acciones con icono lucide (antes emojis
 * en los textos); filtros en una barra bajo la cabecera con el
 * selector "Selecciona un proyecto" sin guiones; KPIs con KpiCard (antes
 * centrados y monoespaciados); estado y prioridad con iconos lucide y
 * StatusBadge; "Fallar" ya no usa la variante de borrar.
 */
import { useId, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { uatApi, projectsApi, tasksApi } from '../services/api'
import type { CasoUat, InformeUat } from '../services/api/tipos-proyectos'
import { Spinner, EmptyState, Button, Modal, KpiCard, IconButton, StatusBadge, Select, Input, Textarea } from '../components/ui'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { Ban, Check, CheckCircle2, ClipboardCheck, Clock, Copy, Download, ListChecks, Lock, Pencil, Plus, SkipForward, Trash2, X, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties, ChangeEvent } from 'react'
import './UATPage.css'
import { UI_FEEDBACK_MS } from '../constants/timings'

// raci_service.serialize_uat_case / list_uat_cases / export_uat_report. La prioridad es
// texto libre en la tabla (String(20)); la interfaz ofrece estas cuatro.
type UATStatus = CasoUat['status']
type UATPriority = 'critical' | 'high' | 'medium' | 'low'
type UATCase = CasoUat

type UATFormData = {
  title: string
  description: string
  expected_result: string
  actual_result: string
  status: UATStatus
  priority: string
  task_id: string
  notes: string
}

type ProjectItem = {
  id: string | number
  name: string
}

type TaskItem = {
  id: string | number
  title?: string
}


const STATUS_META: Record<UATStatus, { label: string; icon: LucideIcon; color: string }> = {
  pending:  { label: 'uat.estado_pending', icon: Clock,        color: 'var(--text-3)' },
  passed:   { label: 'uat.estado_passed',  icon: CheckCircle2, color: 'var(--success)' },
  failed:   { label: 'uat.estado_failed',  icon: XCircle,      color: 'var(--danger)' },
  blocked:  { label: 'uat.estado_blocked', icon: Lock,         color: 'var(--warning)' },
  skipped:  { label: 'uat.estado_skipped', icon: SkipForward,  color: 'var(--text-3)' },
}

const PRIORITY_META: Record<UATPriority, { label: string; kind: StatusBadgeKind }> & Record<string, { label: string; kind: StatusBadgeKind }> = {
  critical: { label: 'uat.prioridad_critical', kind: 'danger' },
  high:     { label: 'uat.prioridad_high',     kind: 'warning' },
  medium:   { label: 'uat.prioridad_medium',   kind: 'accent' },
  low:      { label: 'uat.prioridad_low',      kind: 'neutral' },
}

const fs = 'ds-input uat-input'
const ta = 'ds-input uat-input uat-textarea'
const ls = 'uat-label'

function CaseFormModal({ open, onClose, onSave, initial, tasks = [] }: { open: boolean; onClose: () => void; onSave: (data: UATFormData) => void; initial?: UATCase | null; tasks?: TaskItem[] }) {
  const traducir = useAppT()
  const idPrefix = useId()
  const [form, setForm] = useState<UATFormData>({
    title: initial?.title || '',
    description: initial?.description || '',
    expected_result: initial?.expected_result || '',
    actual_result: initial?.actual_result || '',
    status: initial?.status || 'pending',
    priority: initial?.priority || 'medium',
    task_id: initial?.task_id != null ? String(initial.task_id) : '',
    notes: initial?.notes || '',
  })
  const s = <K extends keyof UATFormData>(k: K) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value as UATFormData[K] }))
  const isEdit = !!initial?.id

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? traducir('uat.editar_caso') : traducir('uat.nuevo_caso_titulo')} width={640}>
      <div className="u-stack-14">
        <div>
          <label htmlFor={`${idPrefix}-title`} id={`${idPrefix}-title-etiqueta`} className={ls}>{traducir('uat.titulo')}</label>
          <Input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-etiqueta`} value={form.title} onChange={s('title')} placeholder={traducir('uat.titulo_del_caso_uat')} inputClassName="uat-input" />
        </div>

        <div className="uat-grid3">
          <div>
            <label htmlFor={`${idPrefix}-status`} className={ls}>{traducir('uat.estado')}</label>
            <Select suelto placeholder={false} id={`${idPrefix}-status`} value={form.status} onChange={s('status')} className={fs}>
              {Object.entries(STATUS_META).map(([v, m]) => (
                <option key={v} value={v}>{traducir(m.label)}</option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-priority`} className={ls}>{traducir('uat.prioridad')}</label>
            <Select suelto placeholder={false} id={`${idPrefix}-priority`} value={form.priority} onChange={s('priority')} className={fs}>
              {Object.entries(PRIORITY_META).map(([v, m]) => (
                <option key={v} value={v}>{traducir(m.label)}</option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-task-id`} className={ls}>{traducir('uat.tarea_vinculada')}</label>
            <Select suelto placeholder={false} id={`${idPrefix}-task-id`} value={form.task_id} onChange={s('task_id')} className={fs}>
              <option value="">{traducir('uat.sin_tarea')}</option>
              {tasks.map(t => (
                <option key={t.id} value={String(t.id)}>{t.title}</option>
              ))}
            </Select>
          </div>
        </div>

        <div>
          <label htmlFor={`${idPrefix}-description`} id={`${idPrefix}-description-etiqueta`} className={ls}>{traducir('uat.pasos_para_ejecutar_el_test')}</label>
          <Textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-etiqueta`} value={form.description} onChange={s('description')} rows={3} placeholder={traducir('uat.pasos_para_ejecutar_el_test')} inputClassName="uat-input uat-textarea" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-expected-result`} id={`${idPrefix}-expected-result-etiqueta`} className={ls}>{traducir('uat.resultado_esperado_req')}</label>
          <Textarea id={`${idPrefix}-expected-result`} aria-labelledby={`${idPrefix}-expected-result-etiqueta`} value={form.expected_result} onChange={s('expected_result')} rows={2} placeholder={traducir('uat.resultado_esperado')} inputClassName="uat-input uat-textarea" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-actual-result`} id={`${idPrefix}-actual-result-etiqueta`} className={ls}>{traducir('uat.resultado_obtenido_rellenar_al_ejecutar')}</label>
          <Textarea id={`${idPrefix}-actual-result`} aria-labelledby={`${idPrefix}-actual-result-etiqueta`} value={form.actual_result} onChange={s('actual_result')} rows={2} placeholder={traducir('uat.resultado_obtenido')} inputClassName="uat-input uat-textarea" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-notes`} id={`${idPrefix}-notes-etiqueta`} className={ls}>{traducir('uat.notas_internas')}</label>
          <Textarea id={`${idPrefix}-notes`} aria-labelledby={`${idPrefix}-notes-etiqueta`} value={form.notes} onChange={s('notes')} rows={2} placeholder={traducir('uat.notas_internas')} inputClassName="uat-input uat-textarea" />
        </div>

        <div className="uat-form-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={!form.title || !form.expected_result}>
            {isEdit ? traducir('uat.guardar_cambios') : traducir('uat.crear_caso')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ExportModal({ open, onClose, report }: { open: boolean; onClose: () => void; report: InformeUat }) {
  const traducir = useAppT()
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(report?.text || '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), UI_FEEDBACK_MS)
    })
  }
  return (
    <Modal open={open} onClose={onClose} title={traducir('uat.exportar_plan')} width={700}>
      <div className="uat-export-bar">
        <Button variant="secondary" icon={copied ? <Check size={14} /> : <Copy size={14} />} onClick={handleCopy}>
          <span aria-live="polite">{copied ? traducir('uat.copiado') : traducir('uat.copiar_texto')}</span>
        </Button>
      </div>
      <pre className="ds-codigo uat-export-pre" tabIndex={0}>
        {report?.text || ''}
      </pre>
      <div className="uat-export-hint">
        {report?.cases_count} {traducir('uat.casos_uat_copia_este_texto_para_enviar')}
      </div>
    </Modal>
  )
}

/** Rev. 173: con `projectId` va dentro de la ficha del proyecto, con el proyecto fijo y sin selector. */
export default function UATPage({ projectId }: { projectId?: string } = {}) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState(projectId ?? '')
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editCase, setEditCase] = useState<UATCase | null>(null)
  const [exportReport, setExportReport] = useState<InformeUat | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<UATCase | null>(null)

  const { data: projects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data ?? []),
  })

  const { data: tasksData = [] } = useQuery<TaskItem[]>({
    queryKey: ['tasks', selectedProject],
    queryFn: () => tasksApi.list({ project_id: selectedProject }).then(r => r.data),
    enabled: !!selectedProject,
    select: (d: unknown) => {
      if (Array.isArray(d)) return d as TaskItem[]
      if (d && typeof d === 'object') {
        const maybe = d as { items?: TaskItem[]; tasks?: TaskItem[] }
        return maybe.items || maybe.tasks || []
      }
      return []
    },
  })

  const { data: uatData, isLoading } = useQuery({
    queryKey: ['uat-cases', selectedProject, statusFilter],
    queryFn: () => uatApi.list(selectedProject, { status: statusFilter || undefined }).then(r => r.data),
    enabled: !!selectedProject,
  })

  const cases = uatData?.cases || []
  const stats = uatData?.stats || { total: 0, pending: 0, passed: 0, failed: 0, blocked: 0 }

  const { mutate: createCase } = useMutation({
    mutationFn: (data: UATFormData) => uatApi.create(selectedProject, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); setShowCreate(false); toast.success(t('uat.toast_creado')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('uat.error_crear'))),
  })

  const { mutate: updateCase } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UATFormData | UATCase }) => uatApi.update(selectedProject, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); setEditCase(null); toast.success(t('uat.toast_actualizado')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('uat.error_actualizar'))),
  })

  const { mutate: deleteCase } = useMutation({
    mutationFn: (id: string | number) => uatApi.remove(selectedProject, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); toast.success(t('uat.toast_eliminado')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('uat.error_eliminar'))),
  })

  const handleExport = async () => {
    try {
      const r = await uatApi.export(selectedProject)
      setExportReport(r.data)
    } catch (e) {
      toast.error(extractErr(e, t('uat.error_exportar')))
    }
  }

  const quickStatus = (caseItem: UATCase, newStatus: UATStatus) => {
    updateCase({ id: caseItem.id, data: { ...caseItem, status: newStatus } })
  }

  return (
    <PageShell>
      <PageHeader
        title={t('nav.uat')}
        subtitle={t('uat.subtitle')}
        icon={<ClipboardCheck size={18} />}
        actions={
          selectedProject ? (
            <>
              <Button variant="secondary" icon={<Download size={14} />} onClick={handleExport}>{traducir('uat.exportar_para_cliente')}</Button>
              <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('uat.nuevo_caso')}</Button>
            </>
          ) : null
        }
        showListExport={Boolean(selectedProject && cases.length)}
        exportTargetSelector='[data-export-table="uat-list"]'
        exportFilePrefix='uat'
      />

      <div className="ds-page">
      {(!projectId || selectedProject) && (
        <div className="ds-toolbar uat-filters">
          {!projectId && <Select suelto placeholder={false}
            value={selectedProject}
            onChange={e => { setSelectedProject(e.target.value); setStatusFilter('') }}
            className={`${fs} uat-input--project`}
            aria-label={traducir('uat.selecciona_un_proyecto_2')}
          >
            <option value="">{traducir('uat.selecciona_un_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
          </Select>}

          {selectedProject && (
            <Select suelto placeholder={false} value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={`${fs} uat-input--status`} aria-label={traducir('uat.estado')}>
              <option value="">{traducir('uat.todos_los_estados')}</option>
              {Object.entries(STATUS_META).map(([v, m]) => (
                <option key={v} value={v}>{traducir(m.label)}</option>
              ))}
            </Select>
          )}
        </div>
      )}

      {selectedProject && stats.total > 0 && (
        <div className="ds-grid-stats">
          <KpiCard icon={<ListChecks size={16} />} label={t('uat.kpi_total')} value={stats.total} />
          <KpiCard icon={<Clock size={16} />} label={t('uat.kpi_pendientes')} value={stats.pending} />
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('uat.kpi_pasados')} value={stats.passed} />
          <KpiCard icon={<XCircle size={16} />} label={t('uat.kpi_fallidos')} value={stats.failed} danger={stats.failed > 0} />
          <KpiCard icon={<Ban size={16} />} label={t('uat.kpi_bloqueados')} value={stats.blocked} warning={stats.blocked > 0} />
        </div>
      )}

      {!selectedProject ? (
        <EmptyState
          icon={<ClipboardCheck size={28} />}
          title={traducir('uat.selecciona_un_proyecto_2')}
          description={traducir('uat.selecciona_proyecto_desc')}
        />
      ) : isLoading ? (
        <Spinner />
      ) : cases.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck size={28} />}
          title={statusFilter ? traducir('uat.sin_casos_filtro') : traducir('uat.sin_casos_uat')}
          description={statusFilter ? traducir('uat.sin_casos_filtro_desc') : traducir('uat.sin_casos_desc')}
          action={statusFilter ? undefined : <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('uat.nuevo_caso')}</Button>}
        />
      ) : (
        <div data-export-table="uat-list" className="u-stack-8">
          {cases.map(c => {
            const st = STATUS_META[c.status] || STATUS_META.pending
            const pr = PRIORITY_META[c.priority] || PRIORITY_META.medium
            const StIcon = st.icon
            return (
              <div key={c.id} className={`uat-case${c.status === 'failed' ? ' uat-case--failed' : c.status === 'passed' ? ' uat-case--passed' : ''}`}>
                <div className="uat-case__row">
                  <div className="uat-case__main">
                    <div className="uat-case__head">
                      <span className="uat-case__icon" style={{ '--uat-c': st.color } as CSSProperties} role="img" aria-label={traducir(st.label)} title={traducir(st.label)}>
                        <StIcon size={16} aria-hidden="true" />
                      </span>
                      <span className="uat-case__title">{c.title}</span>
                      <StatusBadge kind={pr.kind} caps={false}>{traducir(pr.label)}</StatusBadge>
                      {c.task_title && (
                        <span className="uat-task">
                          <ListChecks size={12} aria-hidden="true" /> {c.task_title}
                        </span>
                      )}
                    </div>
                    {c.expected_result && (
                      <div className="uat-case__detail">
                        <span className="u-text3">{traducir('uat.esperado')} </span>{c.expected_result}
                      </div>
                    )}
                    {c.actual_result && (
                      <div className="uat-case__detail">
                        <span className="u-text3">{traducir('uat.resultado')} </span>{c.actual_result}
                      </div>
                    )}
                  </div>

                  <div className="uat-case__actions">
                    {c.status !== 'passed' && (
                      <Button size="sm" variant="secondary" icon={<Check size={13} />} onClick={() => quickStatus(c, 'passed')}>
                        {traducir('uat.pasar')}
                      </Button>
                    )}
                    {c.status !== 'failed' && (
                      <Button size="sm" variant="secondary" icon={<X size={13} />} onClick={() => quickStatus(c, 'failed')}>
                        {traducir('uat.fallar')}
                      </Button>
                    )}
                    <IconButton ariaLabel={traducir('uat.editar_caso')} onClick={() => setEditCase(c)}><Pencil size={14} /></IconButton>
                    <IconButton ariaLabel={traducir('uat.eliminar_caso')} className="uat-danger" onClick={() => setDeleteTarget(c)}><Trash2 size={14} /></IconButton>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      </div>

      {/* Modals */}
      {showCreate && (
        <CaseFormModal
          open
          onClose={() => setShowCreate(false)}
          onSave={createCase}
          tasks={tasksData}
        />
      )}
      {editCase && (
        <CaseFormModal
          open
          onClose={() => setEditCase(null)}
          onSave={data => updateCase({ id: editCase.id, data })}
          initial={editCase}
          tasks={tasksData}
        />
      )}
      {exportReport && (
        <ExportModal open onClose={() => setExportReport(null)} report={exportReport} />
      )}
      {/* Delete confirmation modal (no browser confirm()) */}
      {deleteTarget && (
        <Modal open onClose={() => setDeleteTarget(null)} title={traducir('uat.eliminar_caso')} width={420}>
          <p className="u-text2-base-mb20">
            {traducir('uat.eliminar_el_caso')} <strong className="u-text1">&quot;{deleteTarget.title}&quot;</strong>{traducir('uat.esta_accion_no_se_puede_deshacer')}
          </p>
          <div className="u-actions-10">
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>{traducir('common.cancel')}</Button>
            <Button
              variant="danger"
              onClick={() => { deleteCase(deleteTarget.id); setDeleteTarget(null) }}
            >{traducir('common.delete')}</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
