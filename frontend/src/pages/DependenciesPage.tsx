import { CSSProperties, useState, useMemo, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, taskDependenciesApi } from '../services/api'
import { useListaDeProyectos } from '../hooks/useListas'
import type { DependenciaDeTarea } from '../services/api/tipos-proyectos'
import { Button, Spinner, EmptyState, Modal, KpiCard, IconButton, Tabs, Pulsable, Select, TablaSimple, useErroresDeCampo, Input, EstadoDeError } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ArrowLeft, ArrowRight, Check, FolderKanban, GitMerge, List, Network, Plus, Trash2 } from 'lucide-react'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './DependenciesPage.css'

// Los tipos del Gantt y el autoplanificador (revisión 2026-11): antes ofrecía tipos de Jira que no se podían guardar.
type DependencyType = DependenciaDeTarea['dependency_type']
const DE_ORDEN = new Set(['FS', 'SS', 'FF', 'SF'])
type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked' | 'in_review' | string

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

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => taskDependenciesApi.create({
      predecessor_id: form.predecessor_id,
      successor_id: form.successor_id,
      dependency_type: form.dependency_type,
      lag_days: form.lag_days,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['task-deps', projectId] }); onClose(); },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('dependencies.error_create'))) },
  });

  return (
    <Modal open onClose={onClose} title={t('dependencies.nueva_dependencia')}>
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="dependencies-page-e7">{t('dependencies.from_task')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} className="dependencies-page-e8" value={form.predecessor_id} onChange={e => set('predecessor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.map(tk => <option key={tk.id} value={String(tk.id)}>{tk.title?.slice(0,45)}</option>)}
            </Select>{msg('predecessor_id')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="dependencies-page-e7">{t('dependencies.to_task')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} className="dependencies-page-e8" value={form.successor_id} onChange={e => set('successor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.filter(tk => String(tk.id) !== form.predecessor_id).map(tk => (
                <option key={tk.id} value={String(tk.id)}>{tk.title?.slice(0,45)}</option>))}
            </Select>{msg('successor_id')}
          </div>
        </div>

        <div>
          <label className="dependencies-page-e7">{t('dependencies.tipo_de_dependencia')}</label>
          <div className="u-stack-6">
            {DEP_TYPES.map(dt => (
              <Pulsable type="button" key={dt.value} aria-pressed={form.dependency_type===dt.value} onClick={() => set('dependency_type')(dt.value)}
                className="deps-btn dependen-sx1 dependencies-page-e1" style={{ '--dependencies-page-border': `1px solid ${form.dependency_type===dt.value ? alpha(dt.color, '50') : 'var(--surface-4)'}`, '--dependencies-page-background': form.dependency_type===dt.value ? alpha(dt.color, '15') : 'transparent' } as CSSProperties}>
                <div className="deps-box dependencies-page-e2" style={{ '--dependencies-page-background': dt.color } as CSSProperties} />
                <div className="u-flex1">
                  <div className={`deps-box-2 ${form.dependency_type===dt.value ? 'dependen-sx2' : 'dependen-sx3'} dependencies-page-e3`} style={{ '--dependencies-page-color': form.dependency_type===dt.value?dt.color:'var(--text-1)' } as CSSProperties}>{t(dt.label)}</div>
                  <div className="u-text2-xs">{t(dt.desc)}</div>
                </div>
                {form.dependency_type===dt.value && <span className="dependen-sx5" style={{ '--dependen-v4': dt.color } as CSSProperties}><Check size={16} aria-hidden /></span>}
              </Pulsable>
            ))}
          </div>
        </div>

        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="dependencies-page-e7">{t('dependencies.dias_de_lag_retraso')}</label>
            <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.lag_days} min={0} onChange={e => set('lag_days')(+e.target.value)} inputClassName="dependencies-page-e8" />{msg('lag_days')}
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
  if (!nodes.length) return <EmptyState icon={<GitMerge size={28} />} title={t('dependencies.sin_tareas')} description={t('pagina_deps.este_proyecto_no_tiene_tareas_para')} />
  if (!edges.length) return (
    <EmptyState icon={<GitMerge size={28} />} title={t('dependencies.sin_dependencias_2')} description={t('dependencies.sin_dependencias_definidas_crea_dependencias_entre_tareas')} />
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
                <span className="deps-label-2 dependencies-page-e4" style={{ '--dependencies-page-background': alpha(sc, '20'), '--dependencies-page-color': sc } as CSSProperties}>{etiquetaCodigo(t, 'estado', node.status)}</span>
              </div>
              <div className="deps-stack">
                {outEdges.map(e => {
                  const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                  const target = nodeMap[String(e.to_task_id)]
                  return (
                    <div key={e.id} className="deps-row-2">
                      <span className="u-600 dependencies-page-e3 deps-flecha" style={{ '--dependencies-page-color': dt?.color || 'var(--text-2)' } as CSSProperties}><ArrowRight size={12} aria-hidden /></span>
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
                      <span className="dependen-sx9 deps-flecha" style={{ '--dependen-v8': dt?.color || 'var(--text-2)' } as CSSProperties}><ArrowLeft size={12} aria-hidden /></span>
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

  // 23-11-2026 (04 A8 / M6): lista compartida de proyectos y sin `.catch` tragados; si fallan las
  // dependencias o las tareas se pinta el estado de error en vez de un mapa vacío que parece correcto.
  const { data: projects = [] } = useListaDeProyectos()
  // Usar siempre el endpoint correcto y nunca llamar sin projectId
  const { data: tasks = [], error: errorTareas, refetch: refetchTareas } = useQuery<TaskItem[]>({
    queryKey: ['tasks-list', project],
    queryFn: () => project
      ? tasksApi.list({ project_id: project, limit: FULL_LIST_SIZE })
          .then(r => Array.isArray(r.data) ? r.data : [])
      : Promise.resolve([]),
    enabled: !!project,
  })

  const { data: deps = [], isLoading, error: errorDeps, refetch: refetchDeps } = useQuery({
    queryKey: ['task-deps', project],
    queryFn: () => project
      ? taskDependenciesApi.getByProject(project).then(r => r.data)
      : Promise.resolve<DependencyItem[]>([]),
    enabled: !!project,
  })
  const errorDeCarga = errorDeps ?? errorTareas ?? null

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
      <PageHeader icon={<GitMerge size={18} />} title={t('nav.dependencies')} subtitle={t('dependencies.subtitle')}
        actions={project ? (
          <Button icon={<Plus size={14} />} onClick={() => setShowForm(true)}>{t('dependencies.nueva_dependencia')}</Button>
        ) : undefined} />

      <div className="ds-toolbar deps-filtros">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="u-sr-only">{t('pagina_deps.proyecto')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-1`} value={project} onChange={e => setProject(e.target.value)} className="ds-input deps-proyecto">
          <option value="">{t('dependencies.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {project && (
        <Tabs
          items={[
            { id: 'list', label: t('pagina_deps.lista'), icon: <List size={14} /> },
            { id: 'visual', label: t('pagina_deps.mapa_visual'), icon: <Network size={14} /> },
          ]}
          active={view}
          onChange={(id) => setView(id as 'list' | 'visual')}
          className="deps-tabs"
        />
      )}

      {!project && <EmptyState icon={<FolderKanban size={28} />} title={t('dependencies.selecciona_un_proyecto_2')} description={t('pagina_deps.elige_un_proyecto_para_ver_o')} />}
      {project && isLoading && <Spinner />}

      {project && errorDeCarga && <EstadoDeError error={errorDeCarga} onReintentar={() => { void refetchDeps(); void refetchTareas() }} />}

      {project && !isLoading && !errorDeCarga && (
        <>
          {/* KPIs */}
          {edges.length > 0 && (
            <div className="ds-grid-stats deps-kpis">
              <KpiCard label={t('pagina_deps.total_deps')} value={edges.length} />
              <KpiCard label={t('pagina_deps.bloqueos')} value={blocked.length} danger={blocked.length > 0} />
              <KpiCard label={t('pagina_deps.tareas_bloqueadas')} value={new Set(blocked.map(e=>e.to_task_id)).size} warning={blocked.length > 0} />
              <KpiCard label={t('pagina_deps.tareas_bloqueantes')} value={new Set(blocked.map(e=>e.from_task_id)).size} />
            </div>
          )}

          {view === 'visual' && <div className="dependencies-page-e9"><GanttDepsView nodes={nodes} edges={edges} /></div>}

          {view === 'list' && edges.length === 0 && (
            <EmptyState icon={<GitMerge size={28} />} title={t('dependencies.sin_dependencias_2')}
              description={t('dependencies.define_que_tareas_bloquean_a_otras_para')}
              action={<Button icon={<Plus size={14} />} onClick={() => setShowForm(true)}>{t('dependencies.nueva_dependencia')}</Button>} />
          )}
          {view === 'list' && edges.length > 0 && (
            <div className="dependencies-page-e9">
              {(
                <TablaSimple claseTabla="deps-table">
                  <thead>
                    <tr className="u-border-b">
                      {[t('pagina_deps.tarea_a'),t('pagina_deps.tipo'),t('pagina_deps.tarea_b'),t('pagina_deps.lag'),''].map((h, i) => (
                        <th key={i} className="deps-th">{h}</th>
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
                              {etiquetaCodigo(t, 'estado', e.from_task_status)}
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
                              {etiquetaCodigo(t, 'estado', e.to_task_status)}
                            </div>
                          </td>
                          <td className="deps-td-2">
                            {(e.lag_days ?? 0) > 0 ? t('pagina_deps.d', { lag_days: e.lag_days }) : '—'}
                          </td>
                          <td className="u-pad-10-12">
                            <IconButton className="deps-borrar" ariaLabel={t('pagina_deps.eliminar_esta_dependencia')}
                              onClick={() => { openConfirmGlobal({ message: t('pagina_deps.eliminar_esta_dependencia'), onConfirm: () => deleteEdge(e.id), danger: true }) }}>
                              <Trash2 size={14} aria-hidden />
                            </IconButton>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </TablaSimple>
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
