/**
 * Aprobaciones: bandeja (/approvals) y configuración de flujos (/settings/approval-workflows).
 *
 * Fase 2 (rev. 166): estilos en ApprovalsPage.css (los colores que son datos —entidad,
 * paso, porcentajes— llegan como propiedades personalizadas), todos los textos por i18n
 * (`approvals.*`) y, en vez de JSON escrito a mano, la condición de un paso y las reglas
 * de auto-aprobación se editan con controles (`components/aprobaciones/CondicionesSimples`).
 */
import type { ComponentProps, CSSProperties, MouseEvent, ReactNode } from 'react'
import PoliticaDeLaSolicitud from '../components/politicas/PoliticaDeLaSolicitud'
import type { ResumenDePolitica } from '../services/api/tipos-politicas'
import CondicionesDelFlujo from '../components/aprobaciones/CondicionesDelFlujo'
import { CondicionDePaso, EditorDeReglasDeAutoaprobacion } from '../components/aprobaciones/CondicionesSimples'
import { lazy, Suspense, useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate, fmtDateTime } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import type { CargaDeAprobadores, CuelloDeBotella, CuellosDeBotella, EstadisticasDeAprobacion, FlujoDeAprobacion, GrupoDeAprobadores, PasoDeAprobacion, PlantillaDeFlujo, SimulacionDeFlujo, SolicitudPendienteDeMi } from '../services/api/tipos-rendimiento'
import { usersApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import {
  CheckCircle, CheckCircle2, Info, Trash2,
  Clock as ClockIcon, Users, BarChart3, Sparkles, Layers, Workflow,
  FileText, Receipt, RefreshCw, Flag, ShoppingCart, FileSignature, PiggyBank, ArrowLeftRight, LayoutGrid,
  Palmtree, Package, ClipboardList, Handshake, GitBranch, UserPlus, Tag, Plug, Laptop, Undo2, Circle,
  ArrowLeft, FolderOpen, Pencil, Check, Plus, X, AlertTriangle, Download,
} from 'lucide-react'
import { Button, Modal, EmptyState, Tabs, Page, Table, KpiCard, IconButton, StatusBadge, SelectorDePeriodo, Pulsable, Select, TablaSimple, Checkbox } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo, formatearTramo } from '../utils/periodo'
import { useAppT } from '../i18n/AppLangContext'
import { UserSelect } from '../components/ui/EntitySelect'
import DateInput from '../components/ui/DateInput'
import { POLL_FREQUENT_MS } from '../constants/timings'
import './ApprovalsPage.css'

// Diseñador gráfico (tarea #26): carga @xyflow/react solo al abrirlo.
const DisenadorDeFlujo = lazy(() => import('../components/aprobaciones/DisenadorDeFlujo'))

type T = (k: string, p?: Record<string, unknown> | string) => string
type EntityConfig = { label: string; icon: ReactNode; color: string }
// 16-11-2026 (pasada de diseño): iconos lucide en vez de emojis.
const ENTIDADES: Record<string, { icon: ReactNode; color: string }> = {
  document: { icon: <FileText size={14} />, color: 'var(--accent)' },
  timesheet: { icon: <ClockIcon size={14} />, color: 'var(--accent)' },
  expense: { icon: <Receipt size={14} />, color: 'var(--warning)' },
  change_request: { icon: <RefreshCw size={14} />, color: 'var(--purple)' },
  milestone: { icon: <Flag size={14} />, color: 'var(--success)' },
  purchase: { icon: <ShoppingCart size={14} />, color: 'var(--danger)' },
  invoice: { icon: <Receipt size={14} />, color: 'var(--warning)' },
  contract: { icon: <FileSignature size={14} />, color: 'var(--purple)' },
  budget: { icon: <PiggyBank size={14} />, color: 'var(--success)' },
  budget_transfer: { icon: <ArrowLeftRight size={14} />, color: 'var(--success)' },
  // Mejoras de mercado 16-11-2026: peticiones del catálogo del service desk.
  catalog_request: { icon: <LayoutGrid size={14} />, color: 'var(--accent)' },
  leave: { icon: <Palmtree size={14} />, color: 'var(--accent)' },
  deliverable: { icon: <Package size={14} />, color: 'var(--text-2)' },
  proposal: { icon: <ClipboardList size={14} />, color: 'var(--purple)' },
  subcontractor: { icon: <Handshake size={14} />, color: 'var(--warning)' },
  scope_change: { icon: <GitBranch size={14} />, color: 'var(--danger)' },
  hire: { icon: <UserPlus size={14} />, color: 'var(--success)' },
  price_change: { icon: <Tag size={14} />, color: 'var(--danger)' },
  // Revisión 2026-11: escritura de un agente externo con MCP_WRITE_MODE=approval
  mcp_action: { icon: <Plug size={14} />, color: 'var(--purple)' },
  // Licencias y hardware, fase 1: asignar una licencia o un equipo con aprobación.
  alm_assignment: { icon: <Laptop size={14} />, color: 'var(--accent)' },
  // Licencias fase 2: liberar una licencia sin uso (recuperación).
  license_reclaim: { icon: <Undo2 size={14} />, color: 'var(--warning)' },
}
const ICONO_ENTIDAD_DESCONOCIDA = <Circle size={14} />
/** Nombre de cada tipo de entidad: `approvals.entity_<tipo>`. */
const entityLabels = (t: T): Record<string, EntityConfig> =>
  Object.fromEntries(Object.entries(ENTIDADES).map(([k, v]) => [k, { ...v, label: t(`approvals.entity_${k}`, k) }]))

const approverTypeLabels = (t: T): Record<string, string> => ({
  user: t('approvals.approver_user'),
  role: t('approvals.approver_role'),
  manager: t('approvals.approver_manager'),
  any_in_department: t('approvals.approver_any_department'),
  group: t('approvals.grupo_de_aprobadores'),
})

const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'developer', 'designer', 'finance']
const CATEGORIAS_DE_DOCUMENTO = ['contract', 'deliverable', 'proposal', 'sop', 'requirements', 'meeting_notes', 'legal', 'other']
const COLORES_DE_PASO = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--danger)']
const color = (c: string) => ({ '--apv-color': c } as CSSProperties)
/** Umbral → clase de nivel (alto/medio/bajo). */
const nivel = (v: number, alto: number, medio: number) => v >= alto ? 'apv-nivel--alto' : v >= medio ? 'apv-nivel--medio' : 'apv-nivel--bajo'

// Formas de las respuestas de /approvals: services/api/tipos-rendimiento.ts.
type ApprovalStep = PasoDeAprobacion
type ApprovalWorkflow = FlujoDeAprobacion
type WorkflowTemplate = PlantillaDeFlujo
type ApprovalGroup = GrupoDeAprobadores
/** Rev. 166: más el resumen de las políticas al abrirla y el origen del paso (si lo añadió una política). */
type PendingRequest = SolicitudPendienteDeMi & { politica?: ResumenDePolitica | null; step_origin?: string | null }
type ApprovalStats = EstadisticasDeAprobacion
type SimulationResult = SimulacionDeFlujo
type BottleneckItem = CuelloDeBotella
type BottleneckSummary = CuellosDeBotella['summary']
type WorkflowAtRisk = CuellosDeBotella['top_workflows'][number]
type WeeklyRejection = CuellosDeBotella['trend'][number]
type Recommendation = CuellosDeBotella['recommendations'][number]
type BottlenecksResponse = CuellosDeBotella
type ApproverLoadResponse = CargaDeAprobadores

interface SimulationPayload {
  entity_type: string
  context: { category: string; department: string; amount?: number; requested_by_user_id?: string }
}

type CondicionesDeDisparo = ComponentProps<typeof CondicionesDelFlujo>['actuales']

interface GroupForm {
  name: string
  description: string
  member_ids: string[]
}

// ── Modal de paso ─────────────────────────────────────────────────────────────
function StepModal({ workflowId, step, onClose }: { workflowId: string; step: ApprovalStep | null; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!step?.id
  const [form, setForm] = useState({
    step_order:          step?.step_order          || 1,
    name:                step?.name                || '',
    approver_type:       step?.approver_type       || 'role',
    approver_role:       step?.approver_role       || '',
    approver_user_id:    step?.approver_user_id    || '',
    approver_department: step?.approver_department || '',
    is_optional:         step?.is_optional         || false,
    timeout_hours:       step?.timeout_hours       || 72,
    on_timeout:          step?.on_timeout          || 'escalate',
    // v2 enterprise
    approver_group_id:   step?.approver_group_id   || '',
    parallel_quorum:     step?.parallel_quorum     || false,
    required_approvals:  step?.required_approvals  || 1,
    step_condition:      step?.step_condition      || '',
    requires_attachment: step?.requires_attachment || false,
    reminder_hours:      step?.reminder_hours      || '',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })

  const { data: groups = [] } = useQuery<ApprovalGroup[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (d: typeof form) => isEdit
      ? approvalsApi.updateStep(workflowId, step.id, d)
      : approvalsApi.addStep(workflowId, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })
      toast.success(isEdit ? t('approvals.step_updated') : t('approvals.step_added'))
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })
  const id = (k: string) => `${idPrefix}-${k}`

  return (
    <Modal open title={isEdit ? t('approvals.step_modal_edit_title') : t('approvals.step_modal_new_title')} onClose={onClose} width={560}>
      <div className="apv-rejilla-2">
        <div>
          <label htmlFor={id('name')} className="apv-label">{t('approvals.step_name_required')}</label>
          <input id={id('name')} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="apv-input" placeholder={t('approvals.step_name_placeholder')} />
        </div>
        <div>
          <label htmlFor={id('order')} className="apv-label">{t('approvals.order')}</label>
          <input id={id('order')} type="number" value={form.step_order} onChange={e => setForm(f => ({ ...f, step_order: +e.target.value }))} className="apv-input" min="1" max="10" />
        </div>
        <div className="u-col-full">
          <label htmlFor={id('approver-type')} className="apv-label">{t('approvals.approver_type')}</label>
          <Select suelto placeholder={false} id={id('approver-type')} value={form.approver_type} onChange={e => setForm(f => ({ ...f, approver_type: e.target.value }))} className="apv-input">
            {Object.entries(approverTypeLabels(t)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>

        {form.approver_type === 'role' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-role')} className="apv-label">{t('approvals.required_role')}</label>
            <Select suelto placeholder={false} id={id('approver-role')} value={form.approver_role} onChange={e => setForm(f => ({ ...f, approver_role: e.target.value }))} className="apv-input">
              <option value="">{t('approvals.select_role')}</option>
              {ROLES.map(r => <option key={r} value={r}>{t(`pol.rol_${r}`, r)}</option>)}
            </Select>
          </div>
        )}

        {form.approver_type === 'user' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-user')} className="apv-label">{t('approvals.approver_user_label')}</label>
            <Select suelto placeholder={false} id={id('approver-user')} value={form.approver_user_id} onChange={e => setForm(f => ({ ...f, approver_user_id: e.target.value }))} className="apv-input">
              <option value="">{t('approvals.select_user')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
            </Select>
          </div>
        )}

        {form.approver_type === 'any_in_department' && (
          <div className="u-col-full">
            <label htmlFor={id('approver-department')} className="apv-label">{t('approvals.department')}</label>
            <Select suelto placeholder={false} id={id('approver-department')} value={form.approver_department} onChange={e => setForm(f => ({ ...f, approver_department: e.target.value }))} className="apv-input">
              <option value="">{t('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </Select>
          </div>
        )}

        <div>
          <label htmlFor={id('timeout-hours')} className="apv-label">{t('approvals.timeout_hours')}</label>
          <input id={id('timeout-hours')} type="number" value={form.timeout_hours} onChange={e => setForm(f => ({ ...f, timeout_hours: +e.target.value }))} className="apv-input" min="1" />
        </div>
        <div>
          <label htmlFor={id('on-timeout')} className="apv-label">{t('approvals.on_timeout')}</label>
          <Select suelto placeholder={false} id={id('on-timeout')} value={form.on_timeout} onChange={e => setForm(f => ({ ...f, on_timeout: e.target.value }))} className="apv-input">
            <option value="escalate">{t('approvals.timeout_escalate')}</option>
            <option value="auto_approve">{t('approvals.timeout_auto_approve')}</option>
            <option value="reject">{t('approvals.timeout_reject')}</option>
          </Select>
        </div>
        <div className="u-col-full">
          <label htmlFor={id('is-optional')} className="apv-check">
            <Checkbox id={id('is-optional')} checked={form.is_optional} onChange={(_, e) => setForm(f => ({ ...f, is_optional: e.target.checked }))} />
            {t('approvals.optional_step_label')}
          </label>
        </div>

        {form.approver_type === 'group' && (
          <div className="u-col-full">
            <label htmlFor={id('group')} className="apv-label">{t('approvals.grupo_de_aprobadores')}</label>
            <Select suelto placeholder={false} id={id('group')} value={form.approver_group_id} onChange={e => setForm(f => ({ ...f, approver_group_id: e.target.value }))} className="apv-input">
              <option value="">{t('approvals.seleccionar_grupo')}</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </Select>
          </div>
        )}

        <div className="u-col-full">
          <label htmlFor={id('quorum')} className="apv-check">
            <Checkbox id={id('quorum')} checked={form.parallel_quorum} onChange={(_, e) => setForm(f => ({ ...f, parallel_quorum: e.target.checked }))} />
            {t('approvals.quorum_paralelo_varios_aprobadores_simultaneos')}
          </label>
        </div>

        {form.parallel_quorum && (
          <div>
            <label htmlFor={id('req-approvals')} className="apv-label">{t('approvals.aprobaciones_requeridas')}</label>
            <input id={id('req-approvals')} type="number" min="1" value={form.required_approvals}
              onChange={e => setForm(f => ({ ...f, required_approvals: +e.target.value }))} className="apv-input" />
          </div>
        )}

        <div>
          <label htmlFor={id('reminder')} className="apv-label">{t('approvals.recordatorio_horas')}</label>
          <input id={id('reminder')} type="number" min="1" value={form.reminder_hours}
            onChange={e => setForm(f => ({ ...f, reminder_hours: e.target.value ? +e.target.value : '' }))} className="apv-input" placeholder={t('approvals.recordatorio_ejemplo')} />
        </div>

        <div className="u-col-full">
          <label htmlFor={id('adjunto')} className="apv-check">
            <Checkbox id={id('adjunto')} checked={form.requires_attachment} onChange={(_, e) => setForm(f => ({ ...f, requires_attachment: e.target.checked }))} />
            {t('approvals.requiere_adjunto_obligatorio_para_aprobar')}
          </label>
        </div>

        <fieldset className="ds-grupo-opciones u-col-full apr-regla">
          <legend className="apv-label">{t('approvals.condicion_de_paso')}</legend>
          <CondicionDePaso raw={form.step_condition} onChange={raw => setForm(f => ({ ...f, step_condition: raw }))} />
          <p className="apv-ayuda">{t('approvals.si_se_define_este_paso_solo_se')}</p>
        </fieldset>
      </div>
      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate(form)} loading={isPending} disabled={!form.name || isPending}>
          {isEdit ? t('approvals.save_step') : t('approvals.add_step')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de flujo ──────────────────────────────────────────────────────────
function WorkflowDetail({ workflowId, onBack }: { workflowId: string; onBack: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showStep, setShowStep] = useState(false)
  const [editStep, setEditStep] = useState<ApprovalStep | null>(null)

  const { data: wf } = useQuery<ApprovalWorkflow>({
    queryKey: ['approval-workflow', workflowId],
    queryFn: () => approvalsApi.getWorkflow(workflowId).then(r => r.data),
  })

  const { mutate: delStep } = useMutation({
    mutationFn: (sid: string) => approvalsApi.deleteStep(workflowId, sid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success(t('approvals.step_deleted')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: toggleActive } = useMutation({
    mutationFn: (val: boolean) => approvalsApi.updateWorkflow(workflowId, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }),
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: updateCategory } = useMutation({
    mutationFn: (cat: string) => approvalsApi.updateWorkflow(workflowId, {
      trigger_conditions: cat ? JSON.stringify({ category: cat }) : '{}'
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] }); toast.success(t('approvals.categoria_actualizada')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const [editingCategory, setEditingCategory] = useState(false)
  const [disenar, setDisenar] = useState(false)

  if (!wf) return null
  if (disenar) {
    return <Suspense fallback={null}><DisenadorDeFlujo workflowId={workflowId} onCerrar={() => setDisenar(false)} /></Suspense>
  }
  const steps = [...(wf.steps || [])].sort((a, b) => a.step_order - b.step_order)
  const entity = entityLabels(t)[wf.entity_type] || { label: wf.entity_type, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }

  let parsedConditions: CondicionesDeDisparo = {}
  try { parsedConditions = JSON.parse(wf.trigger_conditions || '{}') } catch (_) { /* condiciones ilegibles: sin condiciones */ }
  const configuredCategory = parsedConditions.category || ''
  const categoria = (c: string) => t(`approvals.doc_cat_${c}`, c)

  return (
    <div>
      {wf.entity_type !== 'document' && (
        <CondicionesDelFlujo workflowId={workflowId} entityType={wf.entity_type} actuales={parsedConditions}
          onGuardado={() => qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })} />
      )}
      <div className="apv-detalle-cabecera">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={onBack}>{t('approvals.back')}</Button>
        <div className="u-flex1-min0">
          <div className="apv-detalle-titulo">{wf.name}</div>
          <div className="u-text2-sm">
            <span className="apv-color apv-icono-texto" style={color(entity.color)}>{entity.icon} {entity.label}</span>
            {wf.is_default && <StatusBadge kind="accent" caps={false} className="apv-separado">{t('approvals.default_badge')}</StatusBadge>}
            {!wf.is_active && <StatusBadge kind="danger" caps={false} className="apv-separado">{t('approvals.inactive_badge')}</StatusBadge>}
            {wf.entity_type === 'document' && (
              <span className="apv-separado">
                {editingCategory ? (
                  <Select suelto placeholder={false}
                    autoFocus
                    aria-label={t('approvals.cambiar_categoria_del_documento')}
                    value={configuredCategory}
                    onBlur={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    onChange={e => { updateCategory(e.target.value); setEditingCategory(false) }}
                    className="apv-categoria-select"
                  >
                    <option value="">{t('approvals.doc_cat_todos')}</option>
                    {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{categoria(c)}</option>)}
                  </Select>
                ) : (
                  <Pulsable type="button" title={t('approvals.cambiar_categoria_del_documento')} onClick={() => setEditingCategory(true)}
                    className={`apv-categoria${configuredCategory ? ' apv-categoria--puesta' : ''}`}>
                    <FolderOpen size={13} aria-hidden /> {configuredCategory ? categoria(configuredCategory) : t('approvals.todos_los_documentos')} <Pencil size={12} aria-hidden />
                  </Pulsable>
                )}
              </span>
            )}
          </div>
        </div>
        <Button variant="secondary" icon={<Workflow size={14} />} onClick={() => setDisenar(true)}>{t('pol.disenar_graficamente')}</Button>
        <Button variant="secondary" onClick={() => toggleActive(!wf.is_active)}>
          {wf.is_active ? t('approvals.deactivate') : t('approvals.activate')}
        </Button>
        <Button icon={<Plus size={14} />} onClick={() => setShowStep(true)}>{t('approvals.add_step')}</Button>
      </div>

      {steps.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<Layers size={28} />} title={t('approvals.no_steps_defined')} description={t('approvals.no_steps_description')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowStep(true)}>{t('approvals.add_step')}</Button>} />
        </div>
      ) : (
        <ol className="apv-pasos" aria-label={t('approvals.pasos_de_aprobacion')}>
          {steps.map((step, i) => (
            <li key={step.id} className="apv-paso" style={color(COLORES_DE_PASO[i % COLORES_DE_PASO.length])}>
              <div className="apv-paso__eje" aria-hidden>
                <div className="apv-paso__numero">{step.step_order}</div>
                {i < steps.length - 1 && <div className="apv-paso__linea" />}
              </div>
              <div className="ds-card apv-paso__tarjeta">
                <div className="apv-paso__cabecera">
                  <div>
                    <div className="apv-paso__nombre">{step.name}</div>
                    <div className="u-text2-sm">
                      {approverTypeLabels(t)[step.approver_type]}
                      {step.approver_role && ` · ${t('approvals.role_prefix')}: ${step.approver_role}`}
                      {step.approver_user_name && ` · ${step.approver_user_name}`}
                      {step.approver_department && ` · ${t('approvals.dept_prefix')}: ${step.approver_department}`}
                    </div>
                    <div className="u-hint">
                      {t('approvals.timeout_summary', {
                        hours: step.timeout_hours,
                        action: step.on_timeout === 'escalate'
                          ? t('approvals.timeout_waiting')
                          : step.on_timeout === 'auto_approve'
                            ? t('approvals.timeout_auto_approve_short')
                            : t('approvals.timeout_auto_reject_short')
                      })}
                      {step.is_optional && ` · ${t('approvals.optional_short')}`}
                    </div>
                  </div>
                  <div className="u-row-6">
                    <IconButton ariaLabel={t('approvals.edit_step_aria', { name: step.name })} onClick={() => setEditStep(step)}><Pencil size={14} aria-hidden /></IconButton>
                    <IconButton ariaLabel={t('approvals.delete_step_aria', { name: step.name })}
                      onClick={() => openConfirmGlobal({ message: t('approvals.delete_step_confirm', { name: step.name }), onConfirm: () => delStep(step.id), danger: true })}><Trash2 size={14} aria-hidden /></IconButton>
                  </div>
                </div>
              </div>
            </li>
          ))}

          {/* Resultado final */}
          <li className="apv-paso">
            <div className="apv-paso__eje" aria-hidden><div className="apv-paso__numero apv-paso__numero--fin"><Check size={14} /></div></div>
            <div className="ds-card apv-paso__tarjeta apv-paso__tarjeta--fin">
              <div className="apv-paso__fin">{t('approvals.approved_auto_title')}</div>
              <div className="u-text2-xs-mt2">{t('approvals.approved_auto_desc')}</div>
            </div>
          </li>
        </ol>
      )}

      {(showStep || editStep) && (
        <StepModal workflowId={workflowId} step={editStep} onClose={() => { setShowStep(false); setEditStep(null) }} />
      )}
    </div>
  )
}

// ── Fuera de la oficina (revisión 2026-11) ───────────────────────────────────
// Mientras dura, los avisos de mis aprobaciones llegan también al delegado y
// este puede decidir los pasos que me tocarían.
function FueraDeLaOficina() {
  const t = useAppT()
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ delegate_id?: string | null; away_from?: string | null; away_until?: string | null }>({
    queryKey: ['approvals-ooo'], queryFn: () => approvalsApi.getOutOfOffice().then(r => r.data),
  })
  const [form, setForm] = useState<{ delegate_id: string; away_from: string; away_until: string } | null>(null)
  const actual = form ?? { delegate_id: data?.delegate_id ?? '', away_from: data?.away_from ?? '', away_until: data?.away_until ?? '' }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: (d: typeof actual) => approvalsApi.setOutOfOffice({ delegate_id: d.delegate_id || null, away_from: d.away_from || null, away_until: d.away_until || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approvals-ooo'] }); setForm(null); toast.success(t('approvals.guardado')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_guardar'))),
  })
  return (
    <details className="ds-card apv-ooo" open={Boolean(data?.delegate_id)}>
      <summary>
        {t('approvals.fuera_de_la_oficina')}{data?.delegate_id && data.away_until ? ` · ${t('approvals.delegado_hasta', { fecha: fmtDate(data.away_until) })}` : ''}
      </summary>
      <div className="apv-ooo__fila">
        <div className="apv-ooo__delegado">
          <div className="u-text3-xs" id={`${idCampo}-delegar`}>{t('approvals.delegar_en')}</div>
          <span aria-labelledby={`${idCampo}-delegar`}>
            <UserSelect value={actual.delegate_id} onChange={id => setForm({ ...actual, delegate_id: id })} placeholder={t('approvals.elige_a_quien')} />
          </span>
        </div>
        <label htmlFor={`${idCampo}-desde`} className="u-text3-xs">{t('approvals.desde')}<br />
          <DateInput id={`${idCampo}-desde`} value={actual.away_from} onChange={e => setForm({ ...actual, away_from: e.target.value })} className="apv-ooo__fecha" /></label>
        <label htmlFor={`${idCampo}-hasta`} className="u-text3-xs">{t('approvals.hasta')}<br />
          <DateInput id={`${idCampo}-hasta`} value={actual.away_until} onChange={e => setForm({ ...actual, away_until: e.target.value })} className="apv-ooo__fecha" /></label>
        <Button size="sm" disabled={isPending || !actual.delegate_id || !actual.away_from || !actual.away_until} onClick={() => guardar(actual)}>{t('approvals.guardar')}</Button>
        {data?.delegate_id && <Button size="sm" variant="secondary" disabled={isPending} onClick={() => guardar({ delegate_id: '', away_from: '', away_until: '' })}>{t('approvals.quitar')}</Button>}
      </div>
    </details>
  )
}

// ── Tab de mis solicitudes pendientes ─────────────────────────────────────────
function MyPendingTab() {
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [entityFilter, setEntityFilter] = useState('all')
  const [sortMode, setSortMode] = useState('oldest') // oldest | newest

  const { data: pending = [], isLoading } = useQuery<PendingRequest[]>({
    queryKey: ['approvals-pending-me'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
    enabled: !loading && !!user,
  })

  const refrescar = () => {
    // Cascade to the affected entity caches (approval could be for timesheets, expenses, or absences)
    for (const k of ['approvals-pending-me', 'timesheets-pending', 'timesheets-mine', 'expenses-pending', 'expenses-my', 'absences-pending', 'team-absences']) {
      qc.invalidateQueries({ queryKey: [k] })
    }
  }
  const { mutate: decide, isPending: deciding } = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: string; note?: string }) => approvalsApi.decide(id, { decision, note }),
    onSuccess: () => { refrescar(); toast.success(t('approvals.decision_registered')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const [bulkApproving, setBulkApproving] = useState(false)

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return
    setBulkApproving(true)
    try {
      await Promise.all(Array.from(selectedIds).map(id => approvalsApi.decide(id, { decision: 'approved' })))
      toast.success(t('approvals.approve_selected', { count: selectedIds.size }))
      setSelectedIds(new Set())
      refrescar()
    } catch (e) {
      toast.error(extractErr(e, t('approvals.bulk_approval_error')))
    } finally {
      setBulkApproving(false)
    }
  }

  const toggleSelect = (id: string) => setSelectedIds(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const queue = pending
    .filter(r => entityFilter === 'all' ? true : r.entity_type === entityFilter)
    .sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime()
      const tb = new Date(b.created_at || 0).getTime()
      return sortMode === 'oldest' ? ta - tb : tb - ta
    })

  const toggleAll = () => setSelectedIds(prev =>
    prev.size === queue.length ? new Set() : new Set(queue.map(r => r.id))
  )

  const statsByEntity: Record<string, number> = pending.reduce((acc: Record<string, number>, r) => {
    acc[r.entity_type] = (acc[r.entity_type] || 0) + 1
    return acc
  }, {})

  if (isLoading) return <div className="apv-cargando" role="status">{t('approvals.loading')}</div>

  if (pending.length === 0) return (
    <div className="ds-stack-lg">
      <FueraDeLaOficina />
      <div className="ds-card">
        <EmptyState icon={<CheckCircle2 size={28} />} title={t('approvals.no_pending_title')} description={t('approvals.no_pending_desc')} />
      </div>
    </div>
  )

  return (
    <div className="ds-stack-lg">
      <FueraDeLaOficina />
      <div className="ds-grid-stats">
        <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.total_pending')} value={pending.length} warning={pending.length > 0} />
        {Object.entries(statsByEntity).slice(0, 3).map(([k, count]) => {
          const entity = entityLabels(t)[k] || { label: k, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }
          return <KpiCard key={k} icon={entity.icon} label={entity.label} value={count} />
        })}
      </div>

      <div className="ds-toolbar">
        <Select suelto placeholder={false} aria-label={t('approvals.filter_by_entity')} value={entityFilter} onChange={e => setEntityFilter(e.target.value)} className="ds-input apv-input--auto">
          <option value="all">{t('approvals.all_entities')}</option>
          {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('approvals.sort_requests')} value={sortMode} onChange={e => setSortMode(e.target.value)} className="ds-input apv-input--auto">
          <option value="oldest">{t('approvals.sort_oldest')}</option>
          <option value="newest">{t('approvals.sort_newest')}</option>
        </Select>
      </div>

      <div className="ds-row-between">
        <label htmlFor="approvals-select-all" className="apv-seleccion">
          <Checkbox id="approvals-select-all" className="apv-casilla"
            checked={queue.length > 0 && selectedIds.size === queue.length} onChange={toggleAll} />
          {selectedIds.size === 0
            ? t('approvals.queue_for_approval', { count: queue.length })
            : t('approvals.selected_of_total', { selected: selectedIds.size, total: queue.length })}
        </label>
        {selectedIds.size > 0 && (
          <Button size="sm" icon={<Check size={14} />} onClick={handleBulkApprove} loading={bulkApproving}>
            {t('approvals.approve_selected', { count: selectedIds.size })}
          </Button>
        )}
      </div>
      <div data-export-table="approvals-export" className="ds-stack-sm">
        {queue.map(req => {
          const entity = entityLabels(t)[req.entity_type] || { label: req.entity_type, icon: ICONO_ENTIDAD_DESCONOCIDA, color: 'var(--text-2)' }
          const ageHours = Math.max(0, Math.floor((Date.now() - new Date(req.created_at || Date.now()).getTime()) / 3600000))
          const isUrgent = ageHours >= 24
          const marcada = selectedIds.has(req.id)
          return (
            <div key={req.id} className={`ds-card apv-solicitud${marcada ? ' apv-solicitud--marcada' : isUrgent ? ' apv-solicitud--urgente' : ''}`}>
              <div className="apv-solicitud__fila">
                <Checkbox className="apv-casilla apv-casilla--arriba"
                  aria-label={t('approvals.select_request_aria', { name: req.entity_summary || req.entity_id })}
                  checked={marcada} onChange={() => toggleSelect(req.id)} />
                <div className="u-flex1-min0">
                  <div className="ds-row-wrap apv-solicitud__chips">
                    <span className="ds-pill apv-entidad apv-icono-texto" style={color(entity.color)}>{entity.icon} {entity.label}</span>
                    {req.step_name && (
                      <span className="ds-muted u-xs">{t('approvals.step_n', { order: req.step_order })}: {req.step_name}</span>
                    )}
                  </div>
                  <div className="apv-solicitud__titulo">{req.entity_summary || req.entity_id}</div>
                  <div className="ds-muted">{t('approvals.request_by')}: {req.requester_name} · {fmtDateTime(req.created_at)}</div>
                  <PoliticaDeLaSolicitud resumen={req.politica} entidadId={req.entity_id} origenDelPaso={req.step_origin} />
                  {isUrgent && (
                    <div className="apv-solicitud__urgente">
                      <ClockIcon size={11} aria-hidden />
                      {t('approvals.pending_since', { hours: ageHours })}
                    </div>
                  )}
                </div>
                <div className="apv-solicitud__botones">
                  <Button size="sm" variant="secondary" icon={<X size={14} />}
                    title={t('approvals.reject_request_aria', { name: req.entity_summary || req.entity_id })}
                    onClick={() => decide({ id: req.id, decision: 'rejected', note: '' })}
                    disabled={deciding}>
                    {t('approvals.reject_action')}
                  </Button>
                  <Button size="sm" icon={<Check size={14} />} onClick={() => decide({ id: req.id, decision: 'approved' })} loading={deciding}>
                    {t('approvals.approve_action')}
                  </Button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Plantillas y creación desde cero ─────────────────────────────────────────
type PasoBorrador = {
  name: string; approver_type: string; approver_role: string; approver_department: string
  timeout_hours: number | string; on_timeout: string; is_optional: boolean
}
const pasoNuevo = (name: string): PasoBorrador => ({
  name, approver_type: 'role', approver_role: 'pm', approver_department: '', timeout_hours: 48, on_timeout: 'escalate', is_optional: false,
})

function WorkflowTemplatesTab() {
  const t = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const qc = useQueryClient()
  const borradorVacio = () => ({
    name: '', description: '', entity_type: 'document', is_default: false, document_category: '',
    steps: [pasoNuevo(t('approvals.aprobacion_inicial'))],
  })
  const [showCreateScratch, setShowCreateScratch] = useState(false)
  const [scratch, setScratch] = useState(borradorVacio)

  const { data: templates = [], isLoading } = useQuery<WorkflowTemplate[]>({
    queryKey: ['approval-workflow-templates'],
    queryFn: () => approvalsApi.listTemplates().then(r => r.data || []),
  })
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })
  const { mutate: createFromTemplate, isPending } = useMutation({
    mutationFn: (payload: { template_id: string }) => approvalsApi.createFromTemplate(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.flujo_creado_plantilla'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_crear_plantilla'))),
  })

  const { mutate: createScratchWorkflow, isPending: isCreatingScratch } = useMutation({
    mutationFn: async (payload: typeof scratch) => {
      const triggerConditions = payload.entity_type === 'document' && payload.document_category
        ? JSON.stringify({ category: payload.document_category })
        : '{}'

      const created = await approvalsApi.createWorkflow({
        name: payload.name,
        description: payload.description || null,
        entity_type: payload.entity_type,
        is_default: !!payload.is_default,
        trigger_conditions: triggerConditions,
      })

      const workflowId = created?.data?.id
      const normalizedSteps = (payload.steps || [])
        .filter(s => (s.name || '').trim())
        .map((s, idx) => ({
          step_order: idx + 1,
          name: s.name.trim(),
          approver_type: s.approver_type,
          approver_role: s.approver_type === 'role' ? (s.approver_role || null) : null,
          approver_department: s.approver_type === 'any_in_department' ? (s.approver_department || null) : null,
          timeout_hours: Number(s.timeout_hours || 48),
          on_timeout: s.on_timeout || 'escalate',
          is_optional: !!s.is_optional,
        }))

      for (const step of normalizedSteps) {
        await approvalsApi.addStep(workflowId, step)
      }

      return created
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreateScratch(false)
      setScratch(borradorVacio())
      toast.success(t('approvals.flujo_creado_cero'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_crear_cero'))),
  })

  const addScratchStep = () => setScratch(s => ({ ...s, steps: [...s.steps, pasoNuevo(t('approvals.paso_n_nombre', { n: s.steps.length + 1 }))] }))
  const updateScratchStep = (index: number, field: keyof PasoBorrador, value: string) => {
    setScratch(s => ({ ...s, steps: s.steps.map((step, idx) => (idx === index ? { ...step, [field]: value } : step)) }))
  }
  const removeScratchStep = (index: number) => setScratch(s => ({ ...s, steps: s.steps.filter((_, idx) => idx !== index) }))

  const canCreateScratch = (scratch.name || '').trim().length > 0 && (scratch.steps || []).some(s => (s.name || '').trim().length > 0)
  const id = (k: string) => `${idPrefix}-${k}`

  return (
    <>
      <div className="apv-fin apv-fin--12">
        <Button icon={<Plus size={14} />} onClick={() => setShowCreateScratch(true)}>{t('approvals.crear_desde_cero')}</Button>
      </div>

      {isLoading && <div className="apv-cargando apv-cargando--compacto" role="status">{t('approvals.cargando_plantillas')}</div>}

      {!isLoading && !templates.length && (
        <div className="ds-card">
          <EmptyState icon={<Sparkles size={28} />} title={t('approvals.sin_plantillas')} description={t('approvals.no_hay_plantillas')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowCreateScratch(true)}>{t('approvals.crear_desde_cero')}</Button>} />
        </div>
      )}

      {!isLoading && templates.length > 0 && (
        <div className="apv-rejilla-tarjetas">
          {templates.map(tpl => (
            <div key={tpl.id} className="ds-card apv-tarjeta">
              <div className="apv-tarjeta__titulo">{tpl.name}</div>
              <div className="apv-tarjeta__texto">{tpl.description || t('approvals.plantilla_lista')}</div>
              <div className="apv-tarjeta__nota">{t('approvals.plantilla_resumen', { entidad: entityLabels(t)[tpl.entity_type]?.label ?? tpl.entity_type, n: (tpl.steps || []).length })}</div>
              <Button size="sm" onClick={() => createFromTemplate({ template_id: tpl.id })} loading={isPending}>{t('approvals.usar_plantilla')}</Button>
            </div>
          ))}
        </div>
      )}

      {showCreateScratch && (
        <Modal open title={t('approvals.crear_flujo_desde_cero')} onClose={() => setShowCreateScratch(false)} width={760}>
          <div className="apv-rejilla-2">
            <div>
              <label htmlFor={id('scratch-name')} className="apv-label">{t('approvals.nombre')}</label>
              <input id={id('scratch-name')} value={scratch.name} onChange={e => setScratch(s => ({ ...s, name: e.target.value }))} className="apv-input" placeholder={t('approvals.nombre_ejemplo')} />
            </div>
            <div>
              <label htmlFor={id('scratch-entity')} className="apv-label">{t('approvals.entidad')}</label>
              <Select suelto placeholder={false} id={id('scratch-entity')} value={scratch.entity_type} onChange={e => setScratch(s => ({ ...s, entity_type: e.target.value }))} className="apv-input">
                {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </div>
            {scratch.entity_type === 'document' && (
              <div className="u-col-full">
                <label htmlFor={id('scratch-category')} className="apv-label">{t('approvals.categoria_documento_opcional')}</label>
                <Select suelto placeholder={false} id={id('scratch-category')} value={scratch.document_category} onChange={e => setScratch(s => ({ ...s, document_category: e.target.value }))} className="apv-input">
                  <option value="">{t('approvals.fallback_aplica_a_todos_los_documentos')}</option>
                  {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{t(`approvals.doc_cat_${c}`, c)}</option>)}
                </Select>
              </div>
            )}
            <div className="u-col-full">
              <label htmlFor={id('scratch-description')} className="apv-label">{t('approvals.description')}</label>
              <input id={id('scratch-description')} value={scratch.description} onChange={e => setScratch(s => ({ ...s, description: e.target.value }))} className="apv-input" placeholder={t('approvals.descripcion_ejemplo')} />
            </div>
            <label htmlFor={id('scratch-default')} className="apv-check apv-check--fila">
              <Checkbox id={id('scratch-default')} checked={scratch.is_default} onChange={(_, e) => setScratch(s => ({ ...s, is_default: e.target.checked }))} />
              {t('approvals.marcar_como_flujo_por_defecto')}
            </label>
          </div>

          <div className="apv-pasos-cabecera">
            <div className="u-sm-700">{t('approvals.pasos_de_aprobacion')}</div>
            <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={addScratchStep}>{t('approvals.add_step')}</Button>
          </div>

          <div className="apv-pasos-lista">
            {scratch.steps.map((step, idx) => (
              <div key={idx} className="apv-paso-borrador">
                <div className="apv-paso-borrador__fila">
                  <div>
                    <label htmlFor={id(`step-name-${idx}`)} className="apv-label">{t('approvals.paso_n_nombre', { n: idx + 1 })}</label>
                    <input id={id(`step-name-${idx}`)} value={step.name} onChange={e => updateScratchStep(idx, 'name', e.target.value)} className="apv-input" placeholder={t('approvals.nombre_del_paso')} />
                  </div>
                  <div>
                    <label htmlFor={id(`step-type-${idx}`)} className="apv-label">{t('approvals.aprobador')}</label>
                    <Select suelto placeholder={false} id={id(`step-type-${idx}`)} value={step.approver_type} onChange={e => updateScratchStep(idx, 'approver_type', e.target.value)} className="apv-input">
                      <option value="role">{t('approvals.approver_role')}</option>
                      <option value="manager">{t('approvals.approver_manager')}</option>
                      <option value="any_in_department">{t('approvals.department')}</option>
                    </Select>
                  </div>
                  <div>
                    <label htmlFor={id(`step-timeout-${idx}`)} className="apv-label">{t('approvals.timeout_hours')}</label>
                    <input id={id(`step-timeout-${idx}`)} type="number" min="1" value={step.timeout_hours} onChange={e => updateScratchStep(idx, 'timeout_hours', e.target.value)} className="apv-input" />
                  </div>
                  <div>
                    <label htmlFor={id(`step-ontimeout-${idx}`)} className="apv-label">{t('approvals.on_timeout')}</label>
                    <Select suelto placeholder={false} id={id(`step-ontimeout-${idx}`)} value={step.on_timeout} onChange={e => updateScratchStep(idx, 'on_timeout', e.target.value)} className="apv-input">
                      <option value="escalate">{t('approvals.timeout_escalate')}</option>
                      <option value="auto_approve">{t('approvals.timeout_auto_approve')}</option>
                      <option value="reject">{t('approvals.timeout_reject')}</option>
                    </Select>
                  </div>
                  <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => removeScratchStep(idx)} disabled={scratch.steps.length === 1}>{t('approvals.eliminar')}</Button>
                </div>

                {step.approver_type === 'role' && (
                  <div className="apv-mt-8">
                    <label htmlFor={id(`step-role-${idx}`)} className="apv-label">{t('approvals.required_role')}</label>
                    <Select suelto placeholder={false} id={id(`step-role-${idx}`)} value={step.approver_role || ''} onChange={e => updateScratchStep(idx, 'approver_role', e.target.value)} className="apv-input">
                      <option value="">{t('approvals.select_role')}</option>
                      {ROLES.map(r => <option key={r} value={r}>{t(`pol.rol_${r}`, r)}</option>)}
                    </Select>
                  </div>
                )}

                {step.approver_type === 'any_in_department' && (
                  <div className="apv-mt-8">
                    <label htmlFor={id(`step-dept-${idx}`)} className="apv-label">{t('approvals.department')}</label>
                    <Select suelto placeholder={false} id={id(`step-dept-${idx}`)} value={step.approver_department || ''} onChange={e => updateScratchStep(idx, 'approver_department', e.target.value)} className="apv-input">
                      <option value="">{t('approvals.sin_departamento')}</option>
                      {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
                    </Select>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="apv-acciones">
            <Button variant="secondary" onClick={() => setShowCreateScratch(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => createScratchWorkflow(scratch)} loading={isCreatingScratch} disabled={!canCreateScratch}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </>
  )
}

// ── Simulador ─────────────────────────────────────────────────────────────────
function WorkflowSimulatorTab() {
  const idCampo = useId()
  const t = useAppT()
  const [entityType, setEntityType] = useState('document')
  const [category, setCategory] = useState('')
  const [department, setDepartment] = useState('')
  const [amount, setAmount] = useState('')
  const [requestedByUserId, setRequestedByUserId] = useState('')
  const [result, setResult] = useState<SimulationResult | null>(null)
  const toast = useToast()
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const { mutate: simulate, isPending } = useMutation({
    mutationFn: (payload: SimulationPayload) => approvalsApi.simulate(payload),
    onSuccess: (res) => setResult(res.data),
    onError: e => toast.error(extractErr(e, t('approvals.error_simular'))),
  })
  const id = (k: string) => `${idCampo}-${k}`
  const accion = (a: string) => a === 'escalate' ? t('approvals.timeout_escalate') : a === 'auto_approve' ? t('approvals.timeout_auto_approve') : a === 'reject' ? t('approvals.timeout_reject') : a

  return (
    <div className="apv-simulador">
      <div className="ds-card apv-tarjeta">
        <div className="apv-tarjeta__texto">{t('approvals.simula_antes_de_publicar_para_validar_ruta')}</div>
        <div className="apv-simulador__rejilla">
          <div>
            <label htmlFor={id('tipo')} className="apv-label">{t('approvals.entity_type')}</label>
            <Select suelto placeholder={false} id={id('tipo')} value={entityType} onChange={e => setEntityType(e.target.value)} className="apv-input">
              {['document', 'expense', 'timesheet', 'milestone', 'purchase'].map(k => <option key={k} value={k}>{entityLabels(t)[k].label}</option>)}
            </Select>
          </div>
          <div>
            <label htmlFor={id('cat')} className="apv-label">{t('approvals.categoria')}</label>
            <input id={id('cat')} value={category} onChange={e => setCategory(e.target.value)} className="apv-input" placeholder={t('approvals.categoria_ejemplo')} />
          </div>
          <div>
            <label htmlFor={id('dep')} className="apv-label">{t('approvals.department')}</label>
            <Select suelto placeholder={false} id={id('dep')} value={department} onChange={e => setDepartment(e.target.value)} className="apv-input">
              <option value="">{t('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </Select>
          </div>
          <div>
            <label htmlFor={id('imp')} className="apv-label">{t('approvals.importe')}</label>
            <input id={id('imp')} value={amount} onChange={e => setAmount(e.target.value)} className="apv-input" type="number" />
          </div>
          <div className="apv-span-2">
            <label htmlFor={id('sol')} className="apv-label">{t('approvals.solicitante_opcional')}</label>
            <span id={id('sol')}><UserSelect value={requestedByUserId} onChange={setRequestedByUserId} placeholder={t('approvals.elige_a_quien')} /></span>
          </div>
        </div>
        <div className="apv-mt-8">
          <Button onClick={() => simulate({ entity_type: entityType, context: { category, department, amount: amount ? Number(amount) : undefined, requested_by_user_id: requestedByUserId || undefined } })} loading={isPending}>{t('approvals.simular_flujo')}</Button>
        </div>
      </div>

      {result && (
        <div className="ds-card apv-tarjeta" aria-live="polite">
          {!result.matched ? (
            <div className="apv-aviso">{t('approvals.sin_coincidencia')} {result.reason}</div>
          ) : (
            <>
              <div className="apv-tarjeta__titulo">{t('approvals.flujo_seleccionado', { nombre: result.workflow?.name ?? '' })}</div>
              <div className="apv-tarjeta__nota">{t('approvals.sla_estimado', { h: result.estimated_total_timeout_hours })}</div>
              <div className="u-stack-8">
                {(result.route || []).map(step => (
                  <div key={step.step_order} className="apv-ruta">
                    <div className="u-sm-700">{t('approvals.step_n', { order: step.step_order })}: {step.step_name}</div>
                    <div className="u-text2-xs">{t('approvals.ruta_paso', { aprobador: step.resolved_approver || t('approvals.no_resoluble'), h: step.timeout_hours, accion: accion(step.on_timeout) })}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function exportBottlenecksCSV(t: T, items: BottleneckItem[], recommendations: Recommendation[], periodo: string, workflowFilterName: string | null) {
  const header = [t('approvals.cb_flujo'), t('approvals.cb_paso'), t('approvals.cb_nombre_paso'), t('approvals.cb_decisiones'), t('approvals.cb_media_h'),
    t('approvals.cb_rechazo'), t('approvals.cb_pendientes'), t('approvals.cb_riesgo_sla'), t('approvals.cb_puntuacion')]
  const rows = items.map(it => [
    it.workflow_name, it.step_order, it.step_name, it.decisions_total, it.avg_decision_time_hours,
    it.rejection_rate_pct, it.pending_count, it.sla_risk_pct, it.bottleneck_score,
  ])

  const recHeader = [t('approvals.cb_prioridad'), t('approvals.cb_titulo'), t('approvals.cb_accion'), t('approvals.cb_porque')]
  const recRows = recommendations.map(r => [r.priority, r.title, r.action, r.why])

  const escape = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const toCSV = (hdr: unknown[], data: unknown[][]) => [hdr, ...data].map(r => r.map(escape).join(',')).join('\n')

  const label = workflowFilterName ? t('approvals.cb_flujo_nombre', { nombre: workflowFilterName }) : t('approvals.todos_los_flujos')
  const content = [
    `# ${t('approvals.cb_titulo_csv', { ambito: label, periodo })}`,
    '',
    `## ${t('approvals.cb_seccion_pasos')}`,
    toCSV(header, rows),
    '',
    `## ${t('approvals.cb_seccion_recomendaciones')}`,
    toCSV(recHeader, recRows),
  ].join('\n')

  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bottlenecks_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function WorkflowBottlenecksTab() {
  const t = useAppT()
  const idCampo = useId()
  // Periodo libre (16-11-2026): antes 30/60/90/180 días propios y tendencia semanal fija.
  const periodo = usePeriodo({ defecto: '90d', granularidades: CON_HORA, prefijo: 'cb_' })
  const [workflowFilter, setWorkflowFilter] = useState('')

  const { data: workflowsData = [] } = useQuery<ApprovalWorkflow[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const params = { ...periodo.params, ...(workflowFilter ? { workflow_id: workflowFilter } : {}) }
  const { data, isLoading, refetch, isFetching, error } = useQuery<BottlenecksResponse>({
    queryKey: ['approval-bottlenecks', periodo.params, workflowFilter],
    queryFn: () => approvalsApi.bottlenecks(params).then(r => r.data),
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)
  const textoDelPeriodo = `${periodo.fechas.desde} – ${periodo.fechas.hasta}`

  const items: BottleneckItem[] = data?.items || []
  const summary: BottleneckSummary = data?.summary || {
    steps_analyzed: items.length,
    critical_steps: items.filter(it => it.sla_risk_pct >= 80 || it.pending_count >= 3 || it.rejection_rate_pct >= 25).length,
    pending_total: items.reduce((acc: number, it) => acc + (it.pending_count || 0), 0),
    avg_decision_time_hours: items.length ? Number((items.reduce((acc: number, it) => acc + (it.avg_decision_time_hours || 0), 0) / items.length).toFixed(2)) : 0,
  }
  const topWorkflows: WorkflowAtRisk[] = data?.top_workflows || []
  // Serie completa del periodo: se listan los últimos tramos con decisiones.
  const weeklyTrend: WeeklyRejection[] = (data?.trend || []).filter(row => row.decisions > 0)
  const recommendations: Recommendation[] = data?.recommendations || []

  const selectedWorkflowName = workflowFilter
    ? (workflowsData.find(w => w.id === workflowFilter)?.name || workflowFilter)
    : null

  return (
    <div className="u-stack-12">
      <div className="ds-card apv-barra">
        <span className="u-text2-sm">{t('approvals.ventana')}</span>
        <SelectorDePeriodo {...periodo.selector} />
        <label htmlFor={`${idCampo}-flujo`} className="u-text2-sm">{t('approvals.flujo')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-flujo`} value={workflowFilter} onChange={e => setWorkflowFilter(e.target.value)} className="apv-input apv-input--w200">
          <option value="">{t('approvals.todos_los_flujos')}</option>
          {workflowsData.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </Select>
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()} loading={isFetching}>{t('approvals.actualizar')}</Button>
        {items.length > 0 && (
          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => exportBottlenecksCSV(t, items, recommendations, textoDelPeriodo, selectedWorkflowName)}>
            {t('approvals.exportar_csv')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="apv-cargando apv-cargando--compacto" role="status">{t('approvals.cargando_cuellos_de_botella')}</div>
      ) : errorDePeriodo ? (
        <div className="ds-card">
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </div>
      ) : items.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<BarChart3 size={28} />} title={t('approvals.sin_datos_suficientes')} description={t('approvals.sin_decisiones_historicas')} />
        </div>
      ) : (
        <>
          <div className="ds-grid-stats">
            <KpiCard icon={<Layers size={16} />} label={t('approvals.cb_pasos_analizados')} value={summary.steps_analyzed} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('approvals.cb_pasos_criticos')} value={summary.critical_steps} danger={summary.critical_steps > 0} />
            <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.cb_pendientes_total')} value={summary.pending_total} warning={summary.pending_total > 0} />
            <KpiCard icon={<BarChart3 size={16} />} label={t('approvals.cb_decision_media')} value={summary.avg_decision_time_hours} />
          </div>

          {(topWorkflows.length > 0 || weeklyTrend.length > 0) && (
            <div className="apv-dos-columnas">
              <div className="ds-card apv-kpi">
                <div className="apv-eyebrow">{t('approvals.cb_flujos_en_riesgo')}</div>
                <div className="u-stack-8">
                  {topWorkflows.map((wf, idx) => (
                    <div key={wf.workflow_id || idx} className="apv-riesgo">
                      <span className="u-sm-700">{wf.workflow_name}</span>
                      <span className="u-text2-xs">{t('approvals.cb_puntuacion_n', { n: wf.avg_bottleneck_score })}</span>
                      <span className={`apv-xs ${nivel(wf.max_sla_risk_pct, 80, 50)}`}>{t('approvals.cb_sla_n', { n: wf.max_sla_risk_pct })}</span>
                      <span className="apv-xs apv-nivel--medio">{t('approvals.cb_pend_n', { n: wf.pending_total })}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ds-card apv-kpi">
                <div className="apv-eyebrow">{t('approvals.cb_tendencia_rechazo')}</div>
                {weeklyTrend.length === 0 ? (
                  <div className="u-text2-sm">{t('approvals.sin_tendencia_semanal_disponible')}</div>
                ) : (
                  <div className="u-stack-6">
                    {weeklyTrend.slice(-8).map(row => (
                      <div key={row.t} className="apv-tendencia">
                        <span className="u-text2-mono-xs">{formatearTramo(row.t, periodo.granularidad)}</span>
                        <div className="apv-tendencia__pista" role="img" aria-label={t('approvals.cb_rechazo_semana', { semana: formatearTramo(row.t, periodo.granularidad, true), pct: row.rejection_rate_pct })}>
                          <div className={`apv-tendencia__barra ${nivel(row.rejection_rate_pct, 25, 10)}`}
                            style={{ '--apv-pct': `${Math.min(100, row.rejection_rate_pct)}%` } as CSSProperties} />
                        </div>
                        <span className="u-text2-xs">{row.rejection_rate_pct}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {recommendations.length > 0 && (
            <div className="ds-card apv-kpi">
              <div className="apv-eyebrow">{t('approvals.cb_acciones_recomendadas')}</div>
              <div className="u-stack-8">
                {recommendations.map((rec, idx) => (
                  <div key={`${rec.title}-${idx}`} className="apv-recomendacion">
                    <div className="u-row-center-8">
                      <span className={`apv-prioridad ${rec.priority === 'high' ? 'apv-nivel--alto' : 'apv-nivel--medio'}`}>{t(`approvals.prioridad_${rec.priority}`, rec.priority)}</span>
                      <span className="u-sm-700">{rec.title}</span>
                    </div>
                    <div className="apv-recomendacion__accion">{rec.action}</div>
                    <div className="u-text3-xs-mt2">{rec.why}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="ds-card apv-tabla" role="table" aria-label={t('approvals.cb_seccion_pasos')}>
            <div className="apv-tabla__fila apv-tabla__fila--cabecera" role="row">
              {['cb_paso', 'cb_decis', 'cb_media_h', 'cb_rechazo', 'cb_pendientes', 'cb_riesgo_sla', 'cb_puntuacion'].map(k => (
                <span key={k} role="columnheader">{t(`approvals.${k}`)}</span>
              ))}
            </div>
            {items.slice(0, 30).map((it) => (
              <div key={`${it.workflow_id}-${it.step_order}`} className="apv-tabla__fila" role="row">
                <div role="cell">
                  <div className="u-sm-700">{it.workflow_name}</div>
                  <div className="u-text3-xs">{t('approvals.step_n', { order: it.step_order })}: {it.step_name}</div>
                </div>
                <span className="u-sm" role="cell">{it.decisions_total}</span>
                <span className="u-sm" role="cell">{it.avg_decision_time_hours}</span>
                <span role="cell" className={`apv-sm ${it.rejection_rate_pct >= 20 ? 'apv-nivel--alto' : 'apv-nivel--neutro'}`}>{it.rejection_rate_pct}%</span>
                <span role="cell" className={`apv-sm ${it.pending_count > 0 ? 'apv-nivel--medio' : 'apv-nivel--neutro'}`}>{it.pending_count}</span>
                <span role="cell" className={`apv-sm ${nivel(it.sla_risk_pct, 80, 50)}`}>{it.sla_risk_pct}%</span>
                <span className="u-sm-700" role="cell">{it.bottleneck_score}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Grupos de aprobadores ─────────────────────────────────────────────────────
function ApprovalGroupsTab() {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: groups = [], isLoading } = useQuery<ApprovalGroup[]>({
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const [showCreate, setShowCreate] = useState(false)
  const [editGroup, setEditGroup] = useState<ApprovalGroup | null>(null)
  const [form, setForm] = useState<GroupForm>({ name: '', description: '', member_ids: [] })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: GroupForm) => editGroup ? approvalsApi.updateGroup(editGroup.id, d) : approvalsApi.createGroup(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-groups'] }); setShowCreate(false); setEditGroup(null)
      setForm({ name: '', description: '', member_ids: [] })
      toast.success(editGroup ? t('approvals.grupo_actualizado') : t('approvals.grupo_creado'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_guardar_grupo'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteGroup,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-groups'] }); toast.success(t('approvals.grupo_eliminado')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_eliminar_grupo'))),
  })

  const openEdit = (g: ApprovalGroup) => {
    setEditGroup(g)
    setForm({ name: g.name, description: g.description || '', member_ids: g.member_ids || [] })
    setShowCreate(true)
  }

  const toggleMember = (uid: string) => setForm(f => ({
    ...f,
    member_ids: f.member_ids.includes(uid) ? f.member_ids.filter(x => x !== uid) : [...f.member_ids, uid],
  }))

  if (isLoading) return <div className="apv-cargando" role="status">{t('approvals.cargando_grupos')}</div>

  return (
    <div>
      <div className="apv-fin">
        <Button icon={<Plus size={14} />} onClick={() => { setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); setShowCreate(true) }}>{t('approvals.nuevo_grupo')}</Button>
      </div>
      {groups.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<Users size={28} />} title={t('approvals.sin_grupos')} description={t('approvals.sin_grupos_texto')}
            action={<Button icon={<Plus size={14} />} onClick={() => { setEditGroup(null); setForm({ name: '', description: '', member_ids: [] }); setShowCreate(true) }}>{t('approvals.nuevo_grupo')}</Button>} />
        </div>
      ) : (
        <div className="apv-rejilla-tarjetas apv-rejilla-tarjetas--280">
          {groups.map(g => {
            const members = g.member_ids || []
            return (
              <div key={g.id} className="ds-card apv-grupo">
                <div className="apv-grupo__nombre apv-icono-texto"><Users size={14} aria-hidden /> {g.name}</div>
                {g.description && <div className="apv-grupo__descripcion">{g.description}</div>}
                <div className="u-text3-xs">{t('approvals.n_miembros', { n: members.length })}</div>
                <div className="apv-grupo__acciones">
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEdit(g)}>{t('approvals.editar')}</Button>
                  <IconButton ariaLabel={t('approvals.eliminar_grupo_aria', { nombre: g.name })}
                    onClick={() => openConfirmGlobal({ message: t('approvals.eliminar_grupo_confirmar', { nombre: g.name }), onConfirm: () => del(g.id), danger: true })}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {showCreate && (
        <Modal open title={editGroup ? t('approvals.editar_grupo') : t('approvals.nuevo_grupo_titulo')} onClose={() => { setShowCreate(false); setEditGroup(null) }} width={480}>
          <div className="apv-columna">
            <div>
              <label htmlFor={`${idCampo}-1`} className="apv-label">{t('approvals.name_required')}</label>
              <input id={`${idCampo}-1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="apv-input" placeholder={t('approvals.ej_comite_financiero')} />
            </div>
            <div>
              <label htmlFor={`${idCampo}-2`} className="apv-label">{t('approvals.description')}</label>
              <input id={`${idCampo}-2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="apv-input" />
            </div>
            <div>
              <div id={`${idCampo}-miembros`} className="apv-label">{t('approvals.miembros')}</div>
              <div role="group" aria-labelledby={`${idCampo}-miembros`} className="apv-miembros">
                {users.map(u => (
                  <label key={u.id} className="apv-miembro">
                    <Checkbox checked={form.member_ids.includes(u.id)} onChange={() => toggleMember(u.id)} />
                    {u.full_name} <span className="u-text3-xs">({t(`pol.rol_${u.role}`, u.role)})</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setShowCreate(false); setEditGroup(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => save(form)} loading={isPending} disabled={!form.name || isPending}>{t('approvals.guardar')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Carga de aprobadores ──────────────────────────────────────────────────────
function ApproverLoadTab() {
  const t = useAppT()
  // Periodo libre (16-11-2026): antes 30/60/90/180 días propios. Prefijo propio:
  // otra pestaña de la pantalla tiene su periodo.
  const periodo = usePeriodo({ defecto: '90d', granularidades: CON_HORA, prefijo: 'carga_' })
  const { data, isLoading, error } = useQuery<ApproverLoadResponse>({
    queryKey: ['approver-load', periodo.params],
    queryFn: () => approvalsApi.approverLoad({ ...periodo.params }).then(r => r.data),
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)

  return (
    <div>
      <div className="ds-card apv-barra">
        <span className="u-text2-sm">{t('approvals.periodo')}</span>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
      </div>
      {isLoading ? (
        <div className="apv-cargando" role="status">{t('approvals.cargando_carga_de_aprobadores')}</div>
      ) : errorDePeriodo ? (
        <div className="ds-card">
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </div>
      ) : !data ? null : (
        <>
          {(data.overloaded_approvers || []).length > 0 && (
            <div className="apv-alerta" role="alert">
              <strong className="u-danger apv-icono-texto"><AlertTriangle size={14} aria-hidden /> {t('approvals.aprobadores_sobrecargados')}</strong>
              <span className="apv-alerta__lista">{data.overloaded_approvers.map(a => a.user_name).join(', ')}</span>
            </div>
          )}
          <div className="u-scroll-x">
            <Table
              data={data.items || []}
              columns={[
                { key: 'user_name', label: t('approvals.aprobador'), render: (_v, row) => <span className="u-600">{row.user_name}</span> },
                { key: 'pending_count', label: t('approvals.pending') },
                { key: 'avg_response_hours', label: t('approvals.tiempo_respuesta'), render: (_v, row) => (row.avg_response_hours != null ? row.avg_response_hours.toFixed(1) : '—') },
                { key: 'rejection_rate_pct', label: t('approvals.tasa_rechazo'), render: (_v, row) => (row.rejection_rate_pct != null ? row.rejection_rate_pct.toFixed(0) + '%' : '—') },
                { key: 'load_score', label: t('approvals.score_carga'), render: (_v, row) => (
                  <span className={`apv-score ${row.load_score > 7 ? 'apv-nivel--alto' : row.load_score > 4 ? 'apv-nivel--medio' : 'apv-nivel--bajo'}`}>
                    {row.load_score?.toFixed(1) || '—'}
                  </span>
                ) },
                { key: 'overloaded', label: '', render: (_v, row) => (
                  row.load_score > 7 && <StatusBadge kind="danger" caps={false}>{t('approvals.sobrecargado')}</StatusBadge>
                ) },
              ]}
            />
          </div>
        </>
      )}
    </div>
  )
}

// ── Matriz de aprobación ──────────────────────────────────────────────────────
function ApprovalMatrixTab({ workflows = [] }: { workflows?: ApprovalWorkflow[] }) {
  const t = useAppT()
  const entityMap = entityLabels(t)
  const entityTypes = Object.keys(entityMap)
  const allWorkflowNames = [...new Set(workflows.map(w => w.name))]

  return (
    <div>
      <p className="apv-intro">{t('approvals.vista_de_que_flujos_estan_activos_por')}</p>
      <div className="u-scroll-x">
        <TablaSimple claseTabla="apv-matriz">
          <thead>
            <tr>
              <th scope="col">{t('approvals.entidad')}</th>
              {allWorkflowNames.map(name => <th key={name} scope="col">{name}</th>)}
            </tr>
          </thead>
          <tbody>
            {entityTypes.map(et => {
              const cfg = entityMap[et]
              return (
                <tr key={et} className="u-border-b">
                  <th scope="row"><span className="apv-icono-texto">{cfg.icon} {cfg.label}</span></th>
                  {allWorkflowNames.map(name => {
                    const wf = workflows.find(w => w.entity_type === et && w.name === name)
                    if (!wf) return <td key={name} className="apv-matriz__vacio">—</td>
                    const estado = wf.is_default ? 'defecto' : wf.is_active ? 'activo' : 'inactivo'
                    return (
                      <td key={name}>
                        <span className={`apv-estado apv-estado--${estado}`}>{t(`approvals.estado_${estado}`)}</span>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </TablaSimple>
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
interface ApprovalsPageProps {
  mode?: string
}

export default function ApprovalsPage({ mode = 'inbox' }: ApprovalsPageProps): JSX.Element {
  const createIdPrefix = useId()
  const t = useAppT()
  const { user, loading } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const isConfigMode = mode === 'config'
  const [tab, setTab]           = useState(isConfigMode ? 'workflows' : 'pending')
  const [selected, setSelected] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', entity_type: 'timesheet', is_default: false, document_category: '', chain_on_approval_workflow_id: '', sla_block_on_breach: false, auto_approval_rules: '' })
  const canQueryProtected = !loading && !!user

  const { data: workflows = [], isLoading } = useQuery<ApprovalWorkflow[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { data: stats } = useQuery<ApprovalStats>({
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
    enabled: canQueryProtected && tab === 'workflows',
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: approvalsApi.createWorkflow,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      setShowCreate(false)
      setSelected(res.data.id)
      toast.success(t('approvals.workflow_created'))
    },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteWorkflow,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['approval-workflows'] }); toast.success(t('approvals.workflow_deleted')) },
    onError: e => toast.error(extractErr(e, t('approvals.error_generic'))),
  })

  const runValidate = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      const res = await approvalsApi.validateWorkflow(workflowId)
      if (res.data?.valid) {
        toast.success(t('approvals.flujo_valido'))
      } else {
        toast.error(t('approvals.flujo_no_valido', { motivos: (res.data?.issues || []).join(' | ') || t('approvals.revisar_configuracion') }))
      }
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_validar')))
    }
  }

  const runPublish = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      await approvalsApi.publishWorkflow(workflowId)
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.flujo_publicado'))
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_publicar')))
    }
  }

  const runClone = async (e: MouseEvent, workflowId: string) => {
    e.stopPropagation()
    try {
      await approvalsApi.cloneVersion(workflowId, {})
      qc.invalidateQueries({ queryKey: ['approval-workflows'] })
      toast.success(t('approvals.version_clonada'))
    } catch (err) {
      toast.error(extractErr(err, t('approvals.error_clonar')))
    }
  }

  const tituloDePagina = isConfigMode ? t('approvals.page_title_config') : t('nav.approvals')
  const subtituloDePagina = isConfigMode ? t('approvals.page_subtitle_config') : t('approvals.page_subtitle_inbox')
  if (selected) return (
    <Page icon={<CheckCircle size={18} />} title={tituloDePagina} subtitle={subtituloDePagina}>
      <WorkflowDetail workflowId={selected} onBack={() => setSelected(null)} />
    </Page>
  )

  const tarjetaDeFlujo = (wf: ApprovalWorkflow, cfg: EntityConfig) => (
    <div key={wf.id}
      role="button"
      tabIndex={0}
      onClick={() => setSelected(wf.id)}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }}
      aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
      className={`apv-flujo${wf.is_active ? '' : ' apv-flujo--inactivo'}`}
      style={{ '--apv-color': cfg.color, '--apv-borde': wf.is_active ? `color-mix(in srgb, ${cfg.color} 19%, transparent)` : undefined,
        '--apv-borde-activo': `color-mix(in srgb, ${cfg.color} 38%, transparent)` } as CSSProperties}
    >
      <div className="apv-flujo__cabecera">
        <div className="u-row-center-8">
          <span className="apv-flujo__icono" aria-hidden>{cfg.icon}</span>
          <div>
            <div className="u-md-700">{wf.name}</div>
            <div className="apv-flujo__entidad apv-color">{cfg.label}</div>
          </div>
        </div>
        <div className="apv-flujo__insignias">
          {wf.is_default && <StatusBadge kind="accent" caps={false}>{t('approvals.default_badge')}</StatusBadge>}
          {!wf.is_active && <StatusBadge kind="danger" caps={false}>{t('approvals.inactive_badge')}</StatusBadge>}
        </div>
      </div>
      <div className="apv-flujo__texto">
        {t('approvals.steps_count', { count: wf.step_count, suffix: wf.step_count !== 1 ? t('approvals.steps_suffix_plural') : '' })}
        {wf.description && ` · ${wf.description}`}
      </div>
      <div className="apv-flujo__acciones">
        <Button size="xs" variant="secondary" onClick={(e) => { void runValidate(e as MouseEvent, wf.id) }}>{t('approvals.validar')}</Button>
        <Button size="xs" variant="secondary" onClick={(e) => { void runPublish(e as MouseEvent, wf.id) }}>{t('approvals.publicar')}</Button>
        <Button size="xs" variant="secondary" onClick={(e) => { void runClone(e as MouseEvent, wf.id) }}>{t('approvals.clonar_version')}</Button>
        <IconButton ariaLabel={t('approvals.workflow_delete_aria', { name: wf.name })}
          onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: t('approvals.workflow_delete_confirm', { name: wf.name }), onConfirm: () => del(wf.id), danger: true }) }}>
          <Trash2 size={14} aria-hidden />
        </IconButton>
      </div>
    </div>
  )

  return (
    <Page
      icon={<CheckCircle size={18} />}
      title={tituloDePagina}
      subtitle={subtituloDePagina}
      rightActions={isConfigMode && tab === 'workflows'
        ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('approvals.new_workflow')}</Button>
        : undefined}
    >
      <div className="ds-card--inset apv-info">
        <Info size={14} aria-hidden className="apv-info__icono" />
        <div className="u-text2-sm">
          {isConfigMode ? t('approvals.info_config') : t('approvals.info_inbox')}
        </div>
      </div>

      {stats && tab === 'workflows' && (
        <div className="ds-grid-stats">
          <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.pending')} value={stats.pending} warning={stats.pending > 0} />
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('approvals.approved')} value={stats.approved} />
          <KpiCard icon={<X size={16} />} label={t('approvals.rejected')} value={stats.rejected} />
          <KpiCard icon={<Workflow size={16} />} label={t('approvals.active_flows')} value={workflows.filter(w => w.is_active).length} accent />
        </div>
      )}

      {/* La bandeja solo tiene una sección: sin barra de pestañas. */}
      {isConfigMode && (
        <div className="apv-pestanas">
          <Tabs
            items={[
              { id: 'workflows',   label: t('approvals.tab_workflows') },
              { id: 'templates',   label: t('approvals.tab_plantillas') },
              { id: 'simulator',   label: t('approvals.tab_simulador') },
              { id: 'bottlenecks', label: t('approvals.tab_cuellos') },
              { id: 'groups',      label: t('approvals.tab_grupos') },
              { id: 'load',        label: t('approvals.tab_carga') },
              { id: 'matrix',      label: t('approvals.tab_matriz') },
            ]}
            active={tab}
            onChange={setTab}
            ariaLabel={t('approvals.sections_aria')}
          />
        </div>
      )}

      {tab === 'pending' && <MyPendingTab />}

      {tab === 'workflows' && (
        <div id="approvals-panel-workflows" role="tabpanel" aria-labelledby="approvals-tab-workflows">
          {isLoading ? (
            <div className="apv-cargando" role="status">{t('approvals.loading')}</div>
          ) : workflows.length === 0 ? (
            <div className="ds-card">
              <EmptyState icon={<Workflow size={28} />} title={t('approvals.no_workflows')}
                description={t('approvals.workflows_description')}
                action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('approvals.new_workflow')}</Button>} />
            </div>
          ) : (
            <div data-export-table="approvals-export" className="apv-rejilla-tarjetas apv-rejilla-tarjetas--300">
              {Object.entries(entityLabels(t)).flatMap(([entityType, cfg]) =>
                workflows.filter(w => w.entity_type === entityType).map(wf => tarjetaDeFlujo(wf, cfg)))}
              {workflows.filter(w => !Object.keys(ENTIDADES).includes(w.entity_type)).map(wf => (
                <div key={wf.id} role="button" tabIndex={0} onClick={() => setSelected(wf.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(wf.id) } }} aria-label={t('approvals.workflow_open_aria', { name: wf.name })}
                  className="apv-flujo">
                  <div className="u-md-700">{wf.name}</div>
                  <div className="u-text2-xs">{t(`approvals.entity_${wf.entity_type}`, wf.entity_type)} · {wf.step_count} {t('approvals.steps_word')}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'templates' && isConfigMode && <WorkflowTemplatesTab />}
      {tab === 'simulator' && isConfigMode && <WorkflowSimulatorTab />}
      {tab === 'bottlenecks' && isConfigMode && <WorkflowBottlenecksTab />}
      {tab === 'groups' && isConfigMode && <ApprovalGroupsTab />}
      {tab === 'load' && isConfigMode && <ApproverLoadTab />}
      {tab === 'matrix' && isConfigMode && <ApprovalMatrixTab workflows={workflows} />}

      {showCreate && (
        <Modal open title={t('approvals.new_workflow_title')} onClose={() => setShowCreate(false)} width={560}>
          <div className="apv-columna">
            <div>
              <label htmlFor={`${createIdPrefix}-name`} className="apv-label">{t('approvals.name_required')}</label>
              <input id={`${createIdPrefix}-name`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="apv-input" placeholder={t('approvals.workflow_name_placeholder')} />
            </div>
            <div>
              <label htmlFor={`${createIdPrefix}-entity-type`} className="apv-label">{t('approvals.entity_type')}</label>
              <Select suelto placeholder={false} id={`${createIdPrefix}-entity-type`} value={form.entity_type} onChange={e => setForm(f => ({ ...f, entity_type: e.target.value }))} className="apv-input">
                {Object.entries(entityLabels(t)).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </div>
            {form.entity_type === 'document' && (
              <div>
                <label htmlFor={`${createIdPrefix}-doc-category`} className="apv-label">{t('approvals.categoria_del_documento')}</label>
                <Select suelto placeholder={false} id={`${createIdPrefix}-doc-category`} value={form.document_category} onChange={e => setForm(f => ({ ...f, document_category: e.target.value }))} className="apv-input"
                  aria-describedby={`${createIdPrefix}-doc-category-ayuda`}>
                  <option value="">{t('approvals.fallback_aplica_a_todos_los_documentos')}</option>
                  {CATEGORIAS_DE_DOCUMENTO.map(c => <option key={c} value={c}>{t(`approvals.doc_cat_${c}`, c)}</option>)}
                </Select>
                <div id={`${createIdPrefix}-doc-category-ayuda`} className="apv-ayuda apv-ayuda--2xs">{t('approvals.si_no_se_especifica_categoria_este_flujo')}</div>
              </div>
            )}
            <div>
              <label htmlFor={`${createIdPrefix}-description`} className="apv-label">{t('approvals.description')}</label>
              <input id={`${createIdPrefix}-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="apv-input" placeholder={t('approvals.description_placeholder')} />
            </div>
            <label htmlFor={`${createIdPrefix}-is-default`} className="apv-check">
              <Checkbox id={`${createIdPrefix}-is-default`} checked={form.is_default} onChange={(_, e) => setForm(f => ({ ...f, is_default: e.target.checked }))} />
              {t('approvals.default_flow_label')}
            </label>
            <div>
              <label htmlFor={`${createIdPrefix}-chain`} className="apv-label">{t('approvals.encadenar_con_flujo_al_aprobar_opcional')}</label>
              <Select suelto placeholder={false} id={`${createIdPrefix}-chain`} value={form.chain_on_approval_workflow_id}
                onChange={e => setForm(f => ({ ...f, chain_on_approval_workflow_id: e.target.value }))} className="apv-input">
                <option value="">{t('approvals.sin_encadenamiento')}</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
            <label htmlFor={`${createIdPrefix}-sla`} className="apv-check">
              <Checkbox id={`${createIdPrefix}-sla`} checked={form.sla_block_on_breach} onChange={(_, e) => setForm(f => ({ ...f, sla_block_on_breach: e.target.checked }))} />
              {t('approvals.bloquear_entidad_si_se_supera_el_sla')}
            </label>
            <fieldset className="ds-grupo-opciones apr-regla">
              <legend className="apv-label">{t('approvals.reglas_de_auto_aprobacion')}</legend>
              <EditorDeReglasDeAutoaprobacion raw={form.auto_approval_rules} onChange={raw => setForm(f => ({ ...f, auto_approval_rules: raw }))} />
            </fieldset>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => {
              const { document_category, ...rest } = form
              const trigger_conditions = (form.entity_type === 'document' && document_category)
                ? JSON.stringify({ category: document_category })
                : '{}'
              create({ ...rest, trigger_conditions })
            }} loading={creating} disabled={!form.name || creating}>{t('approvals.create_workflow')}</Button>
          </div>
        </Modal>
      )}
    </Page>
  )
}
