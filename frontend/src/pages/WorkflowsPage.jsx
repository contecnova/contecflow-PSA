import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, projectWorkflowsApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Workflow } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { CHART_COLORS_EXTENDED } from '../constants/theme'

const panelStyle = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 24px' }
const inputStyle = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const labelStyle = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const ROLES = ['admin', 'pm', 'team_lead', 'employee', 'hr']
const COLORS = CHART_COLORS_EXTENDED

function StateForm({ projectId, state, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!state?.id
  const [form, setForm] = useState({
    name:       state?.name      || '',
    value:      state?.value     || '',
    color:      state?.color     || '#7a8aaa',
    icon:       state?.icon      || '',
    is_initial: state?.is_initial || false,
    is_final:   state?.is_final  || false,
    sort_order: state?.sort_order || 0,
  })
  const set = k => v => setForm(f => ({ ...f, [k]: v }))

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? projectWorkflowsApi.updateState(projectId, state.id, d).then(r => r.data)
      : projectWorkflowsApi.createState(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['workflow', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar estado' : 'Nuevo estado'}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={labelStyle}>Nombre del estado</label>
          <input style={inputStyle} value={form.name}
            onChange={e => {
              const n = e.target.value
              setForm(f => ({ ...f, name: n, value: isEdit ? f.value : n.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))
            }} placeholder="Nombre visible del estado" aria-label="Nombre del estado" />
        </div>
        <div>
          <label style={labelStyle}>Valor interno</label>
          <input style={{ ...inputStyle, fontFamily: 'var(--font-mono)', fontSize: "var(--text-sm)" }}
            value={form.value} disabled={isEdit}
            onChange={e => set('value')(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
            placeholder="valor_interno" aria-label="Valor interno" />
        </div>
        <div>
          <label style={labelStyle}>Icono (emoji)</label>
          <input style={{ ...inputStyle, width: 80, textAlign: 'center', fontSize: "var(--text-xl)" }}
            value={form.icon} onChange={e => set('icon')(e.target.value)} placeholder="📝" aria-label="Icono del estado" />
        </div>
        <div>
          <label style={labelStyle}>Color</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {COLORS.map(c => (
              <button key={c} onClick={() => set('color')(c)}
                style={{ width: 28, height: 28, borderRadius: '50%', background: c, border: form.color === c ? '3px solid #fff' : '2px solid transparent', cursor: 'pointer' }} />
            ))}
            <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : '#7a8aaa'} onChange={e => set('color')(e.target.value)}
              style={{ width: 28, height: 28, borderRadius: '50%', border: 'none', cursor: 'pointer', padding: 0 }} />
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
            <input type="checkbox" checked={form.is_initial} onChange={e => set('is_initial')(e.target.checked)} />
            Estado inicial (punto de entrada)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
            <input type="checkbox" checked={form.is_final} onChange={e => set('is_final')(e.target.checked)} />
            Estado final (cuenta como completado)
          </label>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.value} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear estado'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TransitionForm({ projectId, states, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    from_state_id: '',
    to_state_id: '',
    label: '',
    required_role: '',
    requires_comment: false,
  })
  const set = k => v => setForm(f => ({ ...f, [k]: v }))

  const { mutate, isPending } = useMutation({
    mutationFn: d => projectWorkflowsApi.createTransition(projectId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['workflow', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title="Nueva transicion">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={labelStyle}>Desde</label>
            <select style={inputStyle} value={form.from_state_id} onChange={e => set('from_state_id')(e.target.value)}>
              <option value="">Selecciona estado...</option>
              {states.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Hasta</label>
            <select style={inputStyle} value={form.to_state_id} onChange={e => set('to_state_id')(e.target.value)}>
              <option value="">Selecciona estado...</option>
              {states.filter(s => s.id !== form.from_state_id).map(s => (
                <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label style={labelStyle}>Etiqueta de la transición (opcional)</label>
          <input style={inputStyle} value={form.label} onChange={e => set('label')(e.target.value)} placeholder="Ejecutar, Validar o Cerrar" aria-label="Etiqueta de la transicion" />
        </div>
        <div>
          <label style={labelStyle}>Solo puede ejecutarla este rol</label>
          <select style={inputStyle} value={form.required_role} onChange={e => set('required_role')(e.target.value)}>
            <option value="">Cualquier rol</option>
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-base)" }}>
          <input type="checkbox" checked={form.requires_comment} onChange={e => set('requires_comment')(e.target.checked)} />
          Requiere comentario obligatorio al ejecutar
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.from_state_id || !form.to_state_id} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear transición'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function WorkflowsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showStateForm, setShowStateForm] = useState(false)
  const [showTransitionForm, setShowTransitionForm] = useState(false)
  const [editingState, setEditingState] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })

  const { data: workflow, isLoading } = useQuery({
    queryKey: ['workflow', selectedProject],
    queryFn: () => projectWorkflowsApi.get(selectedProject).then(r => r.data).catch(() => null),
    enabled: !!selectedProject,
  })

  const states = workflow?.states || []

  const { mutate: initWorkflow, isPending: isIniting } = useMutation({
    mutationFn: () => projectWorkflowsApi.init(selectedProject).then(r => r.data),
    onSuccess: () => qc.invalidateQueries(['workflow', selectedProject]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: deleteState } = useMutation({
    mutationFn: sid => projectWorkflowsApi.deleteState(selectedProject, sid),
    onSuccess: () => qc.invalidateQueries(['workflow', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const { mutate: deleteTransition } = useMutation({
    mutationFn: tid => projectWorkflowsApi.deleteTransition(selectedProject, tid),
    onSuccess: () => qc.invalidateQueries(['workflow', selectedProject]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: resetWorkflow, isPending: isResetting } = useMutation({
    mutationFn: () => projectWorkflowsApi.resetWorkflow(selectedProject).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['workflow', selectedProject])
      qc.invalidateQueries(['project-workflow', selectedProject])
      toast.success('Workflow restablecido al Scrum estándar')
    },
    onError: e => toast.error(extractErr(e, 'Error al restablecer')),
  })

  const _selectedProj = projects.find(p => p.id === selectedProject)
  const totalTransitions = states.reduce((sum, s) => sum + (s.transitions_from?.length || 0), 0)

  return (
    <PageShell>
      <PageHeader
        icon={<Workflow size={18} />}
        title={t('project_workflows.page_title')}
        subtitle={t('project_workflows.page_subtitle')}
        actions={selectedProject && states.length > 0 && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => openConfirmGlobal({
                message: `¿Restablecer el workflow de "${_selectedProj?.name}" al Scrum estándar?\n\nEsto eliminará todos los estados y transiciones personalizados y los sustituirá por los 5 estados Scrum por defecto. Las tareas conservarán su valor de estado actual.`,
                onConfirm: () => resetWorkflow(),
                danger: true,
              })}
              disabled={isResetting}
              style={{ background: 'transparent', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '7px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit', fontWeight: 600 }}>
              {isResetting ? '⏳' : '↺ Restablecer'}
            </button>
            <Button variant="secondary" onClick={() => setShowTransitionForm(true)}>+ Transición</Button>
            <Button onClick={() => { setEditingState(null); setShowStateForm(true) }}>+ Estado</Button>
          </div>
        )}
      showListExport={false}
      />

      {/* Selector de proyecto */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <label style={labelStyle}>Proyecto</label>
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ ...inputStyle, width: 360 }}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!selectedProject && (
        <EmptyState icon="⚙" title="Selecciona un proyecto" description="Elige un proyecto para configurar su workflow" />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && states.length === 0 && (
        <div style={{ ...panelStyle, textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>⚙️</div>
          <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, marginBottom: 8 }}>Sin workflow definido</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 24 }}>
            Puedes inicializar un workflow Scrum estándar o crear los estados manualmente.
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <Button onClick={() => initWorkflow()} disabled={isIniting}>
              {isIniting ? 'Inicializando...' : '⚡ Workflow Scrum estándar'}
            </Button>
            <Button variant="secondary" onClick={() => { setEditingState(null); setShowStateForm(true) }}>
              + Crear estado manualmente
            </Button>
          </div>
          <div style={{ marginTop: 20, fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            El workflow Scrum incluye: Pendiente → En progreso → En revisión → Completado (+ Bloqueado)
          </div>
        </div>
      )}

      {selectedProject && states.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {/* Panel de estados */}
          <div style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>Estados ({states.length})</div>
              <button onClick={() => { setEditingState(null); setShowStateForm(true) }}
                style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 6, padding: '5px 12px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                + Estado
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {states.map(s => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                  <span style={{ fontSize: "var(--text-lg)" }}>{s.icon}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 500, fontSize: "var(--text-base)" }}>{s.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{s.value}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {s.is_initial && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>Inicial</span>}
                    {s.is_final  && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--success-bg)', color: 'var(--success)' }}>Final</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => { setEditingState(s); setShowStateForm(true) }}
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                    <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el estado "${s.name}"?`, onConfirm: () => deleteState(s.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 5, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Panel de transiciones */}
          <div style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>Transiciones ({totalTransitions})</div>
              <button onClick={() => setShowTransitionForm(true)}
                style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 6, padding: '5px 12px', color: 'var(--purple)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                + Transición
              </button>
            </div>
            {totalTransitions === 0 && (
              <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
                Sin transiciones. Define qué estados pueden pasar a cuáles.
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {states.flatMap(s =>
                (s.transitions_from || []).map(tr => {
                  const toState = states.find(ss => ss.id === tr.to_state_id)
                  return (
                    <div key={tr.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--surface-1)', borderRadius: 8, border: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, display: 'inline-block' }} />
                        <span style={{ color: 'var(--text-1)' }}>{s.icon} {s.name}</span>
                        <span style={{ color: 'var(--text-3)' }}>→</span>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: toState?.color || 'var(--text-2)', display: 'inline-block' }} />
                        <span style={{ color: 'var(--text-1)' }}>{toState?.icon} {toState?.name}</span>
                        {tr.label && <span style={{ color: 'var(--text-2)', fontStyle: 'italic' }}>&quot;{tr.label}&quot;</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {tr.required_role && (
                          <span style={{ fontSize: "var(--text-2xs)", padding: '1px 5px', borderRadius: 4, background: 'var(--warning-bg)', color: 'var(--warning)' }}>{tr.required_role}</span>
                        )}
                        {tr.requires_comment && (
                          <span style={{ fontSize: "var(--text-2xs)", padding: '1px 5px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>💬</span>
                        )}
                      </div>
                      <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta transición?', onConfirm: () => deleteTransition(tr.id), danger: true }) }}
                        style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-base)", padding: '2px 4px' }}>✕</button>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Diagrama visual */}
          <div style={{ ...panelStyle, gridColumn: '1 / -1' }}>
            <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 16 }}>Diagrama del workflow</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflowX: 'auto', paddingBottom: 8 }}>
              {states.sort((a, b) => a.sort_order - b.sort_order).map((s, i) => (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ textAlign: 'center', minWidth: 100 }}>
                    <div style={{ width: 64, height: 64, borderRadius: '50%', background: s.color + '25', border: `2px solid ${s.color}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', margin: '0 auto 6px', fontSize: "var(--text-xl)" }}>
                      {s.icon || s.name.charAt(0)}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: s.color }}>{s.name}</div>
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{s.is_initial ? 'Inicio' : s.is_final ? 'Fin' : ''}</div>
                  </div>
                  {i < states.length - 1 && (
                    <div style={{ color: 'var(--surface-4)', fontSize: "var(--text-xl)" }}>→</div>
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
