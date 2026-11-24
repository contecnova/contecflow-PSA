/*
 * WorkflowsPage — flujos de estado de las tareas de cada proyecto.
 *
 * 16-11-2026: pasada de diseño. Selector de proyecto en una barra bajo la
 * cabecera con .ds-input; acciones (nuevo estado, nueva transición,
 * restablecer) solo en la cabecera, con icono lucide y sin «+» de texto
 * (antes repetidas dentro de los paneles); vacíos con EmptyState e icono;
 * editar, borrar y «requiere comentario» con iconos lucide (antes emojis y
 * símbolos de texto); color por defecto del tema.
 */
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectWorkflowsApi } from '../services/api'
import type { EstadoDelFlujoDeProyecto, FlujoDelProyecto } from '../services/api/tipos-rendimiento'
import { Button, Spinner, EmptyState, Modal, Select, IconButton, Pulsable, Checkbox, useErroresDeCampo, Input, SelectorDeContexto } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FolderOpen, GitBranch, MessageSquare, Pencil, Plus, RotateCcw, Trash2, Workflow, X, Zap } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { CHART_COLORS_EXTENDED, COLOR_DATO_POR_DEFECTO, alpha } from '../constants/theme'
import './WorkflowsPage.css'
import { useRolesReales } from '../hooks/useRolesReales'
import { useListaDeProyectos } from '../hooks/useListas'

type ProjectItem = {
  id: string | number
  name: string
}

/** custom_fields_service.serialize_state (con sus transiciones de salida). */
type WorkflowState = EstadoDelFlujoDeProyecto

type StateFormData = {
  name: string
  value: string
  color: string
  icon: string
  is_initial: boolean
  is_final: boolean
  sort_order: number
}

type TransitionFormData = {
  from_state_id: string
  to_state_id: string
  label: string
  required_role: string
  requires_comment: boolean
}

/** Variables de color por estado (dato del usuario). */
const colorVars = (color: string, bg?: string) => ({ '--wf-color': color, ...(bg ? { '--wf-bg': bg } : {}) }) as CSSProperties

const COLORS = CHART_COLORS_EXTENDED

function StateForm({ projectId, state, onClose }: { projectId: string; state: WorkflowState | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!state?.id
  const [form, setForm] = useState<StateFormData>({
    name:       state?.name      || '',
    value:      state?.value     || '',
    color:      state?.color     || COLOR_DATO_POR_DEFECTO,
    icon:       state?.icon      || '',
    is_initial: state?.is_initial || false,
    is_final:   state?.is_final  || false,
    sort_order: state?.sort_order || 0,
  })
  const set = <K extends keyof StateFormData>(k: K) => (v: StateFormData[K]) => setForm(f => ({ ...f, [k]: v }))

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: StateFormData) => isEdit && state
      ? projectWorkflowsApi.updateState(projectId, state.id, d).then(r => r.data)
      : projectWorkflowsApi.createState(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', projectId] }); onClose() },
    onError: (e: unknown) => { camposB.recoger(e); toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('workflows.editar_estado') : t('workflows.nuevo_estado')}>
      <div className="u-stack-14">
        <Input label={t('workflows.nombre_del_estado')} id={`${idCampo}-nombre`} value={form.name} onChange={e => {
              const n = e.target.value
              setForm(f => ({ ...f, name: n, value: isEdit ? f.value : n.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))
            }} placeholder={t('workflows.nombre_visible_del_estado')} />
        <div>
          <Input label={t('workflows.valor_interno')} id={`${idCampo}-valor`} value={form.value} disabled={isEdit} onChange={e => set('value')(e.target.value.toLowerCase().replace(/\s+/g, '_'))} placeholder={t('workflows.valor_interno_ph')} inputClassName="ds-campo-codigo" />{msgB('value')}
        </div>
        <div>
          <Input label={t('workflows.icono_emoji')} id={`${idCampo}-icono`} value={form.icon} onChange={e => set('icon')(e.target.value)} />{msgB('icon')}
        </div>
        <div>
          <div id={`${idCampo}-color-et`} className="wf-label">{t('workflows.color')}</div>
          <div className="u-wrap-8" role="group" aria-labelledby={`${idCampo}-color-et`}>
            {COLORS.map(c => (
              <Pulsable key={c} type="button" aria-label={t('workflows.color_n', { color: c })} aria-pressed={form.color === c} onClick={() => set('color')(c)}
                className={`wf-swatch${form.color === c ? ' wf-swatch--active' : ''}`} style={colorVars(c)}>{null}</Pulsable>
            ))}
            <input type="color" aria-label={t('workflows.color_personalizado')} value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => set('color')(e.target.value)}
              className="wf-color-input" />
          </div>
        </div>
        <div className="u-grid2-12">
          <Checkbox className="u-row-center-8-pointer" checked={!!form.is_initial} onChange={v => set('is_initial')(v)}
            label={t('workflows.estado_inicial_punto_de_entrada')} />
          <Checkbox className="u-row-center-8-pointer" checked={!!form.is_final} onChange={v => set('is_final')(v)}
            label={t('workflows.estado_final_cuenta_como_completado')} />
        </div>
        <div className="wf-actions">
          <Button variant="secondary" onClick={onClose}>{t('workflows.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.value} loading={isPending}>
            {isPending ? t('workflows.guardando') : isEdit ? t('workflows.guardar') : t('workflows.crear_estado')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TransitionForm({ projectId, states, onClose }: { projectId: string; states: WorkflowState[]; onClose: () => void }) {
  const idCampo = useId()
  // 19-11-2026: roles reales del backend (`GET /auth/roles`).
  const roles = useRolesReales()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<TransitionFormData>({
    from_state_id: '',
    to_state_id: '',
    label: '',
    required_role: '',
    requires_comment: false,
  })
  const set = <K extends keyof TransitionFormData>(k: K) => (v: TransitionFormData[K]) => setForm(f => ({ ...f, [k]: v }))

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: TransitionFormData) => projectWorkflowsApi.createTransition(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', projectId] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open onClose={onClose} title={t('workflows.nueva_transicion')}>
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <div>
            <Select label={t('workflows.desde')} placeholder={false} id={`${idCampo}-1`} value={form.from_state_id} onChange={e => set('from_state_id')(e.target.value)}>
              <option value="">{t('workflows.selecciona_estado')}</option>
              {states.map(s => <option key={s.id} value={String(s.id)}>{s.icon} {s.name}</option>)}
            </Select>{msg('from_state_id')}
          </div>
          <div>
            <Select label={t('workflows.hasta')} placeholder={false} id={`${idCampo}-2`} value={form.to_state_id} onChange={e => set('to_state_id')(e.target.value)}>
              <option value="">{t('workflows.selecciona_estado')}</option>
              {states.filter(s => String(s.id) !== form.from_state_id).map(s => (
                <option key={s.id} value={String(s.id)}>{s.icon} {s.name}</option>
              ))}
            </Select>{msg('to_state_id')}
          </div>
        </div>
        <div>
          <Input label={t('workflows.etiqueta_de_la_transicion_opcional')} id={`${idCampo}-etiqueta`} value={form.label} onChange={e => set('label')(e.target.value)} placeholder={t('workflows.etiqueta_placeholder')} />{msg('label')}
        </div>
        <div>
          <Select label={t('workflows.solo_puede_ejecutarla_este_rol')} placeholder={false} id={`${idCampo}-3`} value={form.required_role} onChange={e => set('required_role')(e.target.value)}>
            <option value="">{t('workflows.cualquier_rol')}</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
          </Select>{msg('required_role')}
        </div>
        <Checkbox className="u-row-center-8-pointer" checked={!!form.requires_comment} onChange={v => set('requires_comment')(v)}
          label={t('workflows.requiere_comentario_obligatorio_al_ejecutar')} />
        <div className="wf-actions">
          <Button variant="secondary" onClick={onClose}>{t('workflows.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.from_state_id || !form.to_state_id} loading={isPending}>
            {isPending ? t('workflows.creando') : t('workflows.crear_transicion')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function WorkflowsPage() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showStateForm, setShowStateForm] = useState(false)
  const [showTransitionForm, setShowTransitionForm] = useState(false)
  const [editingState, setEditingState] = useState<WorkflowState | null>(null)

  const { data: projectsRaw = [] } = useListaDeProyectos()
  const projects = projectsRaw as unknown as ProjectItem[]

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', selectedProject],
    queryFn: () => projectWorkflowsApi.get(selectedProject).then(r => r.data).catch((err: { response?: { status?: number } }): FlujoDelProyecto | null => {
      // 23-11-2026: solo el 404 («sin flujo propio») es un null válido; cualquier otro fallo sube y avisa.
      if (err?.response?.status === 404) return null
      throw err
    }),
    enabled: !!selectedProject,
  })

  const states = workflow?.states || []

  const { mutate: initWorkflow, isPending: isIniting } = useMutation({
    mutationFn: () => projectWorkflowsApi.init(selectedProject).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflow', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: deleteState } = useMutation({
    mutationFn: (sid: string | number) => projectWorkflowsApi.deleteState(selectedProject, sid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflow', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('workflows.error_eliminar'))),
  })

  const { mutate: deleteTransition } = useMutation({
    mutationFn: (tid: string | number) => projectWorkflowsApi.deleteTransition(selectedProject, tid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflow', selectedProject] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: resetWorkflow, isPending: isResetting } = useMutation({
    mutationFn: () => projectWorkflowsApi.resetWorkflow(selectedProject).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workflow', selectedProject] })
      qc.invalidateQueries({ queryKey: ['project-workflow', selectedProject] })
      toast.success(t('workflows.restablecido'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('workflows.error_restablecer'))),
  })

  const _selectedProj = projects.find(p => String(p.id) === selectedProject)
  const totalTransitions = states.reduce((sum: number, s: WorkflowState) => sum + (s.transitions_from?.length || 0), 0)

  return (
    <PageShell>
      <PageHeader
        icon={<Workflow size={18} />}
        title={t('project_workflows.page_title')}
        subtitle={t('project_workflows.page_subtitle')}
        actions={selectedProject && states.length > 0 && (
          <div className="u-row-8">
            <Button variant="ghost" icon={<RotateCcw size={14} />} loading={isResetting}
              onClick={() => openConfirmGlobal({
                message: t('workflows.confirmar_restablecer', { proyecto: _selectedProj?.name ?? '' }),
                onConfirm: () => resetWorkflow(),
                danger: true,
              })}>
              {t('workflows.restablecer')}
            </Button>
            <Button variant="secondary" icon={<GitBranch size={14} />} onClick={() => setShowTransitionForm(true)}>{t('workflows.nueva_transicion')}</Button>
            <Button icon={<Plus size={14} />} onClick={() => { setEditingState(null); setShowStateForm(true) }}>{t('workflows.nuevo_estado')}</Button>
          </div>
        )}
      showListExport={false}
      />

      {/* Selector de proyecto */}
      <SelectorDeContexto>
        <Select label={t('workflows.proyecto')} placeholder={false} id={`${idCampo}-1`} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
          <option value="">{t('workflows.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
        </Select>
      </SelectorDeContexto>

      {!selectedProject && (
        <EmptyState icon={<FolderOpen size={28} />} title={t('workflows.selecciona_un_proyecto_2')} description={t('workflows.elige_proyecto_desc')} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && states.length === 0 && (
        <EmptyState icon={<Workflow size={28} />} title={t('workflows.sin_workflow_definido')}
          description={<>{t('workflows.puedes_inicializar_un_workflow_scrum_estandar_o')}<br />{t('workflows.el_workflow_scrum_incluye_pendiente_en_progreso')}</>}
          action={
            <div className="wf-empty-actions">
              <Button icon={<Zap size={14} />} onClick={() => initWorkflow()} loading={isIniting}>
                {isIniting ? t('workflows.inicializando') : t('workflows.workflow_scrum_estandar')}
              </Button>
              <Button variant="secondary" icon={<Plus size={14} />} onClick={() => { setEditingState(null); setShowStateForm(true) }}>
                {t('workflows.crear_estado_manual')}
              </Button>
            </div>
          } />
      )}

      {selectedProject && states.length > 0 && (
        <div className="wf-grid">
          {/* Panel de estados */}
          <div className="wf-panel">
            <div className="u-row-between-mb16">
              <div className="u-md-600">{t('workflows.estados_n', { n: states.length })}</div>
            </div>
            <div className="u-stack-8">
              {states.map(s => (
                <div key={s.id} className="wf-state">
                  <div className="wf-dot" style={colorVars(s.color)} aria-hidden="true" />
                  <span className="wf-state-icon" aria-hidden="true">{s.icon}</span>
                  <div className="u-flex1">
                    <div className="wf-state-name">{s.name}</div>
                    <div className="u-text3-mono-xs">{s.value}</div>
                  </div>
                  <div className="u-row-6">
                    {s.is_initial && <span className="wf-tag wf-tag--initial">{t('workflows.tag_inicial')}</span>}
                    {s.is_final  && <span className="wf-tag wf-tag--final">{t('workflows.tag_final')}</span>}
                  </div>
                  <div className="u-row-6">
                    <IconButton variante="caja" type="button" onClick={() => { setEditingState(s); setShowStateForm(true) }}
                      ariaLabel={t('workflows.editar_estado_n', { nombre: s.name })} title={t('workflows.editar_estado')}><Pencil size={14} aria-hidden /></IconButton>
                    <IconButton variante="caja" tono="peligro" type="button" onClick={() => { openConfirmGlobal({ message: t('workflows.confirmar_eliminar_estado', { nombre: s.name }), onConfirm: () => deleteState(s.id), danger: true }) }}
                      ariaLabel={t('workflows.eliminar_estado_n', { nombre: s.name })} title={t('workflows.eliminar_estado')}><Trash2 size={14} aria-hidden /></IconButton>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Panel de transiciones */}
          <div className="wf-panel">
            <div className="u-row-between-mb16">
              <div className="u-md-600">{t('workflows.transiciones_n', { n: totalTransitions })}</div>
            </div>
            {totalTransitions === 0 && (
              <div className="wf-no-transitions">
                {t('workflows.sin_transiciones_define_que_estados_pueden_pasar')}
              </div>
            )}
            <div className="u-stack-6">
              {states.flatMap(s =>
                (s.transitions_from || []).map(tr => {
                  const toState = states.find(ss => String(ss.id) === String(tr.to_state_id))
                  return (
                    <div key={tr.id} className="wf-transition">
                      <div className="wf-transition-path">
                        <span className="wf-dot wf-dot--sm" style={colorVars(s.color)} aria-hidden="true" />
                        <span className="u-text1">{s.icon} {s.name}</span>
                        <span className="u-text3" aria-hidden="true">→</span>
                        <span className="wf-dot wf-dot--sm" style={colorVars(toState?.color || 'var(--text-2)')} aria-hidden="true" />
                        <span className="u-text1">{toState?.icon} {toState?.name}</span>
                        {tr.label && <span className="wf-transition-label">&quot;{tr.label}&quot;</span>}
                      </div>
                      <div className="wf-transition-tags">
                        {tr.required_role && (
                          <span className="wf-tag wf-tag--role">{t(`workflows.rol_${tr.required_role}`, tr.required_role)}</span>
                        )}
                        {tr.requires_comment && (
                          <span className="wf-tag wf-tag--comment" title={t('workflows.requiere_comentario')} aria-label={t('workflows.requiere_comentario')}><MessageSquare size={12} aria-hidden /></span>
                        )}
                      </div>
                      <IconButton type="button" onClick={() => { openConfirmGlobal({ message: t('workflows.confirmar_eliminar_transicion'), onConfirm: () => deleteTransition(tr.id), danger: true }) }}
                        ariaLabel={t('workflows.eliminar_transicion')} title={t('workflows.eliminar_transicion')}
                        className="wf-transition-del"><X size={14} aria-hidden /></IconButton>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Diagrama visual */}
          <div className="wf-panel wf-panel--full">
            <div className="wf-diagram-title">{t('workflows.diagrama_del_workflow')}</div>
            <div className="wf-diagram">
              {[...states].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)).map((s, i) => (
                <div key={s.id} className="u-row-center-8">
                  <div className="wf-node" style={colorVars(s.color, alpha(s.color, '25'))}>
                    <div className="wf-node-circle">
                      {s.icon || s.name.charAt(0)}
                    </div>
                    <div className="wf-node-name">{s.name}</div>
                    <div className="u-text3-2xs">{s.is_initial ? t('workflows.inicio') : s.is_final ? t('workflows.fin') : ''}</div>
                  </div>
                  {i < states.length - 1 && (
                    <div className="wf-arrow" aria-hidden="true">→</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showStateForm && (
        <StateForm
          projectId={selectedProject}
          state={editingState}
          onClose={() => { setShowStateForm(false); setEditingState(null) }}
        />
      )}
      {showTransitionForm && (
        <TransitionForm
          projectId={selectedProject}
          states={states}
          onClose={() => setShowTransitionForm(false)}
        />
      )}
    </PageShell>
  )
}
