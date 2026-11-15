import { CSSProperties, useState, useMemo, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, tasksApi, taskDependenciesApi } from '../services/api'
import type { DependenciaDeTarea } from '../services/api/tipos-proyectos'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { GitMerge } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './DependenciesPage.css'

// Los tipos del Gantt y el autoplanificador (revisión 2026-11): antes ofrecía tipos de Jira que no se podían guardar.
type DependencyType = DependenciaDeTarea['dependency_type']
const DE_ORDEN = new Set(['FS', 'SS', 'FF', 'SF'])
type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked' | 'in_review' | string

type ProjectItem = {
  id: string | number
  name: string
}

type TaskItem = {
  id: string | number
  title?: string
  status?: TaskStatus
}

/** task_service.list_task_dependencies (sin nota: la tabla `task_dependencies` no la tiene). */
type DependencyItem = DependenciaDeTarea

type EdgeItem = DependencyItem & {
  from_task_id: string | number
  to_task_id: string | number
  dep_type: DependencyType
  from_task_title: string | number
  from_task_status?: TaskStatus
  to_task_title: string | number
  to_task_status?: TaskStatus
}

type DepFormState = {
  predecessor_id: string
  successor_id: string
  dependency_type: DependencyType
  lag_days: number
}


const DEP_TYPES: Array<{ value: DependencyType; label: string; color: string; desc: string }> = [
  { value:'FS', label: 'pagina_deps.bloquea_fin_inicio', color:'var(--danger)', desc: 'pagina_deps.la_siguiente_no_empieza_hasta_que' },
  { value:'SS', label: 'pagina_deps.inicio_inicio',        color:'var(--warning)', desc: 'pagina_deps.la_siguiente_empieza_cuando_empieza_la' },
  { value:'FF', label: 'pagina_deps.fin_fin',              color:'var(--warning)', desc: 'pagina_deps.la_siguiente_acaba_cuando_acaba_la' },
  { value:'SF', label: 'pagina_deps.inicio_fin',           color:'var(--warning)', desc: 'pagina_deps.la_siguiente_acaba_cuando_empieza_la' },
];

const STATUS_COLOR: Record<string, string> = {todo:'var(--text-2)',in_progress:'var(--accent)',done:'var(--success)',blocked:'var(--danger)',in_review:'var(--warning)'}

function DepForm({ projectId, tasks, onClose }: { projectId: string; tasks: TaskItem[]; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT();
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<DepFormState>({ predecessor_id:'', successor_id:'', dependency_type:'FS', lag_days:0 });
  const set = <K extends keyof DepFormState>(k: K) => (v: DepFormState[K]) => setForm(f => ({...f, [k]: v}));
  const selType = DEP_TYPES.find(d => d.value === form.dependency_type);

  const { mutate, isPending } = useMutation({
    mutationFn: () => taskDependenciesApi.create({
      predecessor_id: form.predecessor_id,
      successor_id: form.successor_id,
      dependency_type: form.dependency_type,
      lag_days: form.lag_days,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['task-deps', projectId] }); onClose(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('dependencies.error_create'))),
  });

  return (
    <Modal open onClose={onClose} title={t('dependencies.title')}>
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="dependencies-page-e7">{t('dependencies.from_task')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} className="dependencies-page-e8" value={form.predecessor_id} onChange={e => set('predecessor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.map(tk => <option key={tk.id} value={String(tk.id)}>{tk.title?.slice(0,45)}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="dependencies-page-e7">{t('dependencies.to_task')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} className="dependencies-page-e8" value={form.successor_id} onChange={e => set('successor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.filter(tk => String(tk.id) !== form.predecessor_id).map(tk => (
                <option key={tk.id} value={String(tk.id)}>{tk.title?.slice(0,45)}</option>))}
            </select>
          </div>
        </div>

        <div>
          <label className="dependencies-page-e7">{t('dependencies.tipo_de_dependencia')}</label>
          <div className="u-stack-6">
            {DEP_TYPES.map(dt => (
              <button key={dt.value} onClick={() => set('dependency_type')(dt.value)}
                className="deps-btn dependen-sx1 dependencies-page-e1" style={{ '--dependencies-page-border': `1px solid ${form.dependency_type===dt.value ? alpha(dt.color, '50') : 'var(--surface-4)'}`, '--dependencies-page-background': form.dependency_type===dt.value ? alpha(dt.color, '15') : 'transparent' } as CSSProperties}>
                <div className="deps-box dependencies-page-e2" style={{ '--dependencies-page-background': dt.color } as CSSProperties} />
                <div className="u-flex1">
                  <div className={`deps-box-2 ${form.dependency_type===dt.value ? 'dependen-sx2' : 'dependen-sx3'} dependencies-page-e3`} style={{ '--dependencies-page-color': form.dependency_type===dt.value?dt.color:'var(--text-1)' } as CSSProperties}>{t(dt.label)}</div>
                  <div className="u-text2-xs">{t(dt.desc)}</div>
                </div>
                {form.dependency_type===dt.value && <span className="dependen-sx5" style={{ '--dependen-v4': dt.color } as React.CSSProperties}>✓</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="dependencies-page-e7">{t('dependencies.dias_de_lag_retraso')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" className="dependencies-page-e8" value={form.lag_days} min={0}
              onChange={e => set('lag_days')(+e.target.value)} />
            <div className="u-hint">{t('dependencies.dias_extra_tras_cumplir_la_condicion')}</div>
          </div>
        </div>

        {form.predecessor_id && form.successor_id && (
          <div className="deps-card">
            <span className="u-600 dependencies-page-e3" style={{ '--dependencies-page-color': selType?.color } as CSSProperties}>
              &quot;{tasks.find(task=>String(task.id)===form.predecessor_id)?.title?.slice(0,30)}&quot;
            </span>
            <span className="u-text2"> {selType && t(selType.label).toLowerCase()} </span>
            <span className="deps-label">
              &quot;{tasks.find(task=>String(task.id)===form.successor_id)?.title?.slice(0,30)}&quot;
            </span>
            {form.lag_days > 0 && <span className="u-text2"> + {form.lag_days}d</span>}
          </div>
        )}

        <div className="deps-row">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.predecessor_id || !form.successor_id} loading={isPending}>
            {isPending ? t('pagina_deps.creando') : t('pagina_deps.crear_dependencia')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function GanttDepsView({ nodes, edges }: { nodes: TaskItem[]; edges: EdgeItem[] }) {
  const t = useAppT()
  if (!nodes.length) return <EmptyState icon="🔗" title={t('dependencies.sin_tareas')} description={t('pagina_deps.este_proyecto_no_tiene_tareas_para')} />
  if (!edges.length) return (
    <div className="deps-box-3">
      {t('dependencies.sin_dependencias_definidas_crea_dependencias_entre_tareas')}
    </div>
  )

  const nodeMap: Record<string, TaskItem> = Object.fromEntries(nodes.map(n => [String(n.id), n]))
  const _blockedIds = new Set(edges.map(e => e.to_task_id))
  const _blockingIds = new Set(edges.map(e => e.from_task_id))

  return (
    <div className="u-scroll-x">
      <div className="deps-box-4">
        {/* Cabecera */}
        <div className="deps-grid">
          <div>{t('pagina_deps.tarea')}</div><div>{t('pagina_deps.estado')}</div><div>{t('pagina_deps.dependencias')}</div><div>{t('pagina_deps.tipo')}</div>
        </div>
        {nodes.map(node => {
          const outEdges = edges.filter(e => e.from_task_id === node.id)
          const inEdges  = edges.filter(e => e.to_task_id   === node.id)
          const isBlocking = outEdges.length > 0
          const isBlocked  = inEdges.filter(e => DE_ORDEN.has(String(e.dep_type))).length > 0
          const sc = STATUS_COLOR[node.status ?? ''] || 'var(--text-2)'
          return (
            <div key={node.id} className={`deps-grid-2 ${isBlocked ? 'dependen-sx6' : 'dependen-sx7'}`}>
              <div className="deps-box-5">
                {node.title}
              </div>
              <div>
                <span className="deps-label-2 dependencies-page-e4" style={{ '--dependencies-page-background': alpha(sc, '20'), '--dependencies-page-color': sc } as CSSProperties}>{node.status}</span>
              </div>
              <div className="deps-stack">
                {outEdges.map(e => {
                  const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                  const target = nodeMap[String(e.to_task_id)]
                  return (
                    <div key={e.id} className="deps-row-2">
                      <span className="u-600 dependencies-page-e3" style={{ '--dependencies-page-color': dt?.color || 'var(--text-2)' } as CSSProperties}>→</span>
                      <span className="deps-label-3">
                        {target?.title}
                      </span>
                      {(e.lag_days ?? 0) > 0 && <span className="u-text3">+{e.lag_days}d</span>}
                    </div>
                  )
                })}
                {inEdges.map(e => {
                  const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                  const source = nodeMap[String(e.from_task_id)]
                  return (
                    <div key={e.id} className="deps-row-3">
                      <span className="dependen-sx9" style={{ '--dependen-v8': dt?.color || 'var(--text-2)' } as React.CSSProperties}>←</span>
                      <span className="deps-label-4">
                        {source?.title}
                      </span>
                    </div>
                  )
                })}
                {outEdges.length===0 && inEdges.length===0 && (
                  <span className="deps-label-5">{t('dependencies.sin_dependencias')}</span>
                )}
              </div>
              <div className="u-text2-2xs">
                {isBlocking && <div className="u-danger">{t('pagina_deps.bloquea')}</div>}
                {isBlocked  && <div className="u-warning">{t('pagina_deps.bloqueada')}</div>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DependenciesPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [view,    setView]    = useState<'list' | 'visual'>('list')
  const [showForm,setShowForm]= useState(false)

  const { data: projects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  // Usar siempre el endpoint correcto y nunca llamar sin projectId
  const { data: tasks = [] } = useQuery<TaskItem[]>({
    queryKey: ['tasks-list', project],
    queryFn: () => project
      ? tasksApi.list({ project_id: project, limit: FULL_LIST_SIZE })
          .then(r => Array.isArray(r.data) ? r.data : [])
          .catch(() => [])
      : Promise.resolve([]),
    enabled: !!project,
  })

  const { data: deps = [], isLoading } = useQuery({
    queryKey: ['task-deps', project],
    queryFn: () => project
      ? taskDependenciesApi.getByProject(project).then(r => r.data).catch((): DependencyItem[] => [])
      : Promise.resolve<DependencyItem[]>([]),
    enabled: !!project,
  })

  const { mutate: deleteEdge } = useMutation({
    mutationFn: (id: string | number) => taskDependenciesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-deps', project] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const taskMap = useMemo<Record<string, TaskItem>>(() => Object.fromEntries(tasks.map(task => [String(task.id), task])), [tasks])

  // Enrich flat deps with task titles/statuses using legacy field names for UI compatibility
  const edges = useMemo<EdgeItem[]>(() => deps.map(d => ({
    ...d,
    from_task_id: d.predecessor_id,
    to_task_id: d.successor_id,
    dep_type: d.dependency_type,
    from_task_title: taskMap[String(d.predecessor_id)]?.title ?? d.predecessor_id,
    from_task_status: taskMap[String(d.predecessor_id)]?.status,
    to_task_title: taskMap[String(d.successor_id)]?.title ?? d.successor_id,
    to_task_status: taskMap[String(d.successor_id)]?.status,
  })), [deps, taskMap])

  const nodes = tasks
  const blocked = edges.filter(e => DE_ORDEN.has(String(e.dep_type)))

  return (
    <PageShell>
      <PageHeader icon={<GitMerge size={18} />} title={t('dependencies.title')} subtitle={t('dependencies.subtitle')}
        actions={project && (
          <Button onClick={() => setShowForm(true)}>{t('dependencies.nueva_dependencia')}</Button>
        )} />

      <div className="dependencies-page-e5">
        <div className="deps-grid-3">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="dependencies-page-e7">{t('pagina_deps.proyecto')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e => setProject(e.target.value)} className="dependencies-page-e8">
              <option value="">{t('dependencies.selecciona_un_proyecto')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          {project && (
            <div className="u-row-6">
              {(['list','visual'] as const).map(v => (
                <button key={v} onClick={() => setView(v)}
                  className={`deps-btn-2 ${view===v ? 'dependen-sx10' : 'dependen-sx11'}`}>
                  {v === 'list' ? t('pagina_deps.lista') : t('pagina_deps.mapa_visual')}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {!project && <EmptyState icon="🔗" title={t('dependencies.selecciona_un_proyecto_2')} description={t('pagina_deps.elige_un_proyecto_para_ver_o')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && (
        <>
          {/* KPIs */}
          {edges.length > 0 && (
            <div className="deps-grid-4">
              {[
                { label: t('pagina_deps.total_deps'), val: edges.length, color: 'var(--text-1)' },
                { label: t('pagina_deps.bloqueos'), val: blocked.length, color: 'var(--danger)' },
                { label: t('pagina_deps.tareas_bloqueadas'), val: new Set(blocked.map(e=>e.to_task_id)).size, color: 'var(--warning)' },
                { label: t('pagina_deps.tareas_bloqueantes'), val: new Set(blocked.map(e=>e.from_task_id)).size, color: 'var(--accent)' },
              ].map(({ label, val, color }) => (
                <div key={label} className="dependencies-page-e6">
                  <div className="deps-box-6 dependencies-page-e3" style={{ '--dependencies-page-color': color } as CSSProperties}>{val}</div>
                  <div className="deps-box-7">{label}</div>
                </div>
              ))}
            </div>
          )}

          {view === 'visual' && <div className="dependencies-page-e9"><GanttDepsView nodes={nodes} edges={edges} /></div>}

          {view === 'list' && (
            <div className="dependencies-page-e9">
              {edges.length === 0 ? (
                <div className="deps-box-8">
                  <div className="u-empty-icon">🔗</div>
                  <div className="deps-box-9">{t('dependencies.sin_dependencias_2')}</div>
                  <div className="u-text2-base-mb20">
                    {t('dependencies.define_que_tareas_bloquean_a_otras_para')}
                  </div>
                  <Button onClick={() => setShowForm(true)}>{t('pagina_deps.crear_primera_dependencia')}</Button>
                </div>
              ) : (
                <table className="deps-table">
                  <thead>
                    <tr className="u-border-b">
                      {[t('pagina_deps.tarea_a'),t('pagina_deps.tipo'),t('pagina_deps.tarea_b'),t('pagina_deps.lag'),''].map(h => (
                        <th key={h} className="deps-th">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {edges.map((e, i) => {
                      const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                      return (
                        <tr key={e.id} className={`u-border-b ${i%2===0 ? 'dependen-sx7' : 'dependen-sx12'}`}>
                          <td className="deps-td">
                            <div className="deps-box-10">
                              {e.from_task_title}
                            </div>
                            <div className="u-xs dependencies-page-e3" style={{ '--dependencies-page-color': STATUS_COLOR[e.from_task_status ?? '']||'var(--text-2)' } as CSSProperties}>
                              {e.from_task_status}
                            </div>
                          </td>
                          <td className="u-pad-10-12">
                            <span className="deps-label-6 dependencies-page-e4" style={{ '--dependencies-page-background': alpha((dt?.color||'var(--text-2)'), '20'), '--dependencies-page-color': dt?.color||'var(--text-2)' } as CSSProperties}>
                              {dt && t(dt.label)}
                            </span>
                          </td>
                          <td className="deps-td">
                            <div className="deps-box-10">
                              {e.to_task_title}
                            </div>
                            <div className="u-xs dependencies-page-e3" style={{ '--dependencies-page-color': STATUS_COLOR[e.to_task_status ?? '']||'var(--text-2)' } as CSSProperties}>
                              {e.to_task_status}
                            </div>
                          </td>
                          <td className="deps-td-2">
                            {(e.lag_days ?? 0) > 0 ? t('pagina_deps.d', { lag_days: e.lag_days }) : '—'}
                          </td>
                          <td className="u-pad-10-12">
                            <button onClick={() => { openConfirmGlobal({ message: t('pagina_deps.eliminar_esta_dependencia'), onConfirm: () => deleteEdge(e.id), danger: true }) }}
                              className="deps-btn-3">
                              ✕
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}

      {showForm && (
        <DepForm projectId={project} tasks={tasks}
          onClose={() => setShowForm(false)} />
      )}
    </PageShell>
  )
}
