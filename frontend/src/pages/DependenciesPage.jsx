import { useState, useMemo } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, tasksApi, taskDependenciesApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { GitMerge } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const DEP_TYPES = [
  { value:'blocks',      label: 'Bloquea',            color:'var(--danger)', desc: 'La tarea origen bloquea la tarea destino' },
  { value:'blocked_by',  label: 'Bloqueada por',      color:'var(--danger)', desc: 'La tarea origen queda bloqueada por la destino' },
  { value:'relates_to',  label: 'Relacionada con',    color:'var(--text-2)', desc: 'Relación informativa sin bloqueo' },
  { value:'duplicates',  label: 'Duplica',            color:'var(--warning)', desc: 'Representa trabajo duplicado' },
  { value:'cloned_from', label: 'Clonada desde',      color:'var(--accent)', desc: 'La tarea origen se creó desde la destino' },
];
const _EPIC_DEP_TYPES = [
  { value:'finish_to_start',  label: 'Finish to start',   color:'var(--danger)', desc: 'La épica destino comienza cuando la origen finaliza' },
  { value:'start_to_start',   label: 'Start to start',    color:'var(--warning)', desc: 'Ambas épicas comienzan coordinadas' },
  { value:'finish_to_finish', label: 'Finish to finish',  color:'var(--accent)', desc: 'Ambas épicas deben cerrarse juntas' },
  { value:'relates_to',       label: 'Relacionada',       color:'var(--text-2)', desc: 'Relación informativa entre épicas' },
];

const STATUS_COLOR = {todo:'var(--text-2)',in_progress:'var(--accent)',done:'var(--success)',blocked:'var(--danger)',in_review:'var(--warning)'}

function DepForm({ projectId, tasks, onClose }) {
  const t = useAppT();
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ predecessor_id:'', successor_id:'', dependency_type:'blocks', lag_days:0 });
  const set = k => v => setForm(f => ({...f, [k]: v}));
  const selType = DEP_TYPES.find(d => d.value === form.dependency_type);

  const { mutate, isPending } = useMutation({
    mutationFn: () => taskDependenciesApi.create({
      predecessor_id: form.predecessor_id,
      successor_id: form.successor_id,
      dependency_type: form.dependency_type,
      lag_days: form.lag_days,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['task-deps', projectId]); onClose(); },
    onError: e => toast.error(extractErr(e, t('dependencies.error_create'))),
  });

  return (
    <Modal open onClose={onClose} title={t('dependencies.title')}>
      <div style={{display:'flex', flexDirection:'column', gap:14}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12}}>
          <div>
            <label style={ls}>{t('dependencies.from_task')}</label>
            <select style={is} value={form.predecessor_id} onChange={e => set('predecessor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.map(tk => <option key={tk.id} value={tk.id}>{tk.title?.slice(0,45)}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('dependencies.to_task')}</label>
            <select style={is} value={form.successor_id} onChange={e => set('successor_id')(e.target.value)}>
              <option value="">{t('dependencies.select')}</option>
              {tasks.filter(tk => tk.id !== form.predecessor_id).map(tk => (
                <option key={tk.id} value={tk.id}>{tk.title?.slice(0,45)}</option>))}
            </select>
          </div>
        </div>

        <div>
          <label style={ls}>Tipo de dependencia</label>
          <div style={{display:'flex', flexDirection:'column', gap:6}}>
            {DEP_TYPES.map(dt => (
              <button key={dt.value} onClick={() => set('dependency_type')(dt.value)}
                style={{display:'flex', alignItems:'center', gap:12, padding:'10px 14px', borderRadius:8,
                  border:`1px solid ${form.dependency_type===dt.value ? dt.color+'50' : 'var(--surface-4)'}`,
                  background:form.dependency_type===dt.value ? dt.color+'15' : 'transparent',
                  cursor:'pointer', fontFamily:'inherit', textAlign:'left'}}>
                <div style={{width:10, height:10, borderRadius:'50%', background:dt.color, flexShrink:0}} />
                <div style={{flex:1}}>
                  <div style={{fontSize: "var(--text-base)", fontWeight:form.dependency_type===dt.value?600:400, color:form.dependency_type===dt.value?dt.color:'var(--text-1)'}}>{dt.label}</div>
                  <div style={{fontSize: "var(--text-xs)", color:'var(--text-2)'}}>{dt.desc}</div>
                </div>
                {form.dependency_type===dt.value && <span style={{color:dt.color}}>✓</span>}
              </button>
            ))}
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12}}>
          <div>
            <label style={ls}>Días de lag (retraso)</label>
            <input type="number" style={is} value={form.lag_days} min={0}
              onChange={e => set('lag_days')(+e.target.value)} />
            <div style={{fontSize: "var(--text-xs)", color:'var(--text-3)', marginTop:4}}>Días extra tras cumplir la condición</div>
          </div>
        </div>

        {form.predecessor_id && form.successor_id && (
          <div style={{padding:'10px 14px', background:'var(--surface-1)', borderRadius:8, border:'1px solid var(--surface-4)', fontSize: "var(--text-sm)"}}>
            <span style={{color:selType?.color, fontWeight:600}}>
              &quot;{tasks.find(t=>t.id===form.predecessor_id)?.title?.slice(0,30)}&quot;
            </span>
            <span style={{color:'var(--text-2)'}}> {selType?.label.toLowerCase()} </span>
            <span style={{color:'var(--accent)', fontWeight:600}}>
              &quot;{tasks.find(t=>t.id===form.successor_id)?.title?.slice(0,30)}&quot;
            </span>
            {form.lag_days > 0 && <span style={{color:'var(--text-2)'}}> + {form.lag_days}d</span>}
          </div>
        )}

        <div style={{display:'flex', justifyContent:'flex-end', gap:10, marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.predecessor_id || !form.successor_id} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear dependencia'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function GanttDepsView({ nodes, edges }) {
  if (!nodes.length) return <EmptyState icon="🔗" title="Sin tareas" description="Este proyecto no tiene tareas para representar dependencias" />
  if (!edges.length) return (
    <div style={{textAlign:'center', padding:'32px', color:'var(--text-2)', fontSize: "var(--text-base)"}}>
      Sin dependencias definidas. Crea dependencias entre tareas para verlas aquí.
    </div>
  )

  const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))
  const _blockedIds = new Set(edges.map(e => e.to_task_id))
  const _blockingIds = new Set(edges.map(e => e.from_task_id))

  return (
    <div style={{overflowX:'auto'}}>
      <div style={{minWidth:600}}>
        {/* Cabecera */}
        <div style={{display:'grid', gridTemplateColumns:'200px 60px 1fr 80px', gap:0,
          padding:'8px 12px', background:'var(--surface-1)', borderBottom:'1px solid var(--surface-4)',
          fontSize: "var(--text-xs)", color:'var(--text-2)', fontWeight:600, textTransform:'uppercase', letterSpacing:'.06em'}}>
          <div>Tarea</div><div>Estado</div><div>Dependencias</div><div>Tipo</div>
        </div>
        {nodes.map(node => {
          const outEdges = edges.filter(e => e.from_task_id === node.id)
          const inEdges  = edges.filter(e => e.to_task_id   === node.id)
          const isBlocking = outEdges.length > 0
          const isBlocked  = inEdges.filter(e => e.dep_type === 'blocks').length > 0
          const sc = STATUS_COLOR[node.status] || 'var(--text-2)'
          return (
            <div key={node.id} style={{display:'grid', gridTemplateColumns:'200px 60px 1fr 80px',
              padding:'10px 12px', borderBottom:'1px solid var(--surface-4)',
              background: isBlocked ? 'var(--danger-bg)' : 'transparent'}}>
              <div style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', fontSize: "var(--text-base)", fontWeight:500}}>
                {node.title}
              </div>
              <div>
                <span style={{fontSize: "var(--text-2xs)", padding:'2px 6px', borderRadius:10,
                  background:sc+'20', color:sc}}>{node.status}</span>
              </div>
              <div style={{display:'flex', flexDirection:'column', gap:4}}>
                {outEdges.map(e => {
                  const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                  const target = nodeMap[e.to_task_id]
                  return (
                    <div key={e.id} style={{display:'flex', alignItems:'center', gap:8, fontSize: "var(--text-xs)"}}>
                      <span style={{color:dt?.color || 'var(--text-2)', fontWeight:600}}>→</span>
                      <span style={{color:'var(--text-1)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:180}}>
                        {target?.title}
                      </span>
                      {e.lag_days > 0 && <span style={{color:'var(--text-3)'}}>+{e.lag_days}d</span>}
                    </div>
                  )
                })}
                {inEdges.map(e => {
                  const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                  const source = nodeMap[e.from_task_id]
                  return (
                    <div key={e.id} style={{display:'flex', alignItems:'center', gap:8, fontSize: "var(--text-xs)", color:'var(--text-3)'}}>
                      <span style={{color:dt?.color || 'var(--text-2)'}}>←</span>
                      <span style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:180}}>
                        {source?.title}
                      </span>
                    </div>
                  )
                })}
                {outEdges.length===0 && inEdges.length===0 && (
                  <span style={{color:'var(--surface-4)', fontSize: "var(--text-xs)"}}>sin dependencias</span>
                )}
              </div>
              <div style={{fontSize: "var(--text-2xs)", color:'var(--text-2)'}}>
                {isBlocking && <div style={{color:'var(--danger)'}}>⬆ bloquea</div>}
                {isBlocked  && <div style={{color:'var(--warning)'}}>⬇ bloqueada</div>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DependenciesPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project, setProject] = useState('')
  const [view,    setView]    = useState('list')
  const [showForm,setShowForm]= useState(false)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  // Usar siempre el endpoint correcto y nunca llamar sin projectId
  const { data: tasks = [] } = useQuery({
    queryKey: ['tasks-list', project],
    queryFn: () => project
      ? tasksApi.list({ project_id: project, limit: 500 })
          .then(r => Array.isArray(r.data) ? r.data : (r.data?.items ?? []))
          .catch(() => [])
      : Promise.resolve([]),
    enabled: !!project,
  })

  const { data: deps = [], isLoading } = useQuery({
    queryKey: ['task-deps', project],
    queryFn: () => project
      ? taskDependenciesApi.getByProject(project).then(r => Array.isArray(r.data) ? r.data : []).catch(() => [])
      : Promise.resolve([]),
    enabled: !!project,
  })

  const { mutate: deleteEdge } = useMutation({
    mutationFn: id => taskDependenciesApi.delete(id),
    onSuccess: () => qc.invalidateQueries(['task-deps', project]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const taskMap = useMemo(() => Object.fromEntries(tasks.map(t => [t.id, t])), [tasks])

  // Enrich flat deps with task titles/statuses using legacy field names for UI compatibility
  const edges = useMemo(() => deps.map(d => ({
    ...d,
    from_task_id: d.predecessor_id,
    to_task_id: d.successor_id,
    dep_type: d.dependency_type,
    from_task_title: taskMap[d.predecessor_id]?.title ?? d.predecessor_id,
    from_task_status: taskMap[d.predecessor_id]?.status,
    to_task_title: taskMap[d.successor_id]?.title ?? d.successor_id,
    to_task_status: taskMap[d.successor_id]?.status,
  })), [deps, taskMap])

  const nodes = tasks
  const blocked = edges.filter(e => e.dep_type === 'blocks')

  return (
    <PageShell>
      <PageHeader icon={<GitMerge size={18} />} title={t('dependencies.title')} subtitle={t('dependencies.subtitle')}
        actions={project && (
          <Button onClick={() => setShowForm(true)}>+ Nueva dependencia</Button>
        )} />

      <div style={{...ps, marginBottom:20}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr auto', gap:12, alignItems:'flex-end'}}>
          <div>
            <label style={ls}>Proyecto</label>
            <select value={project} onChange={e => setProject(e.target.value)} style={is}>
              <option value="">Selecciona un proyecto...</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          {project && (
            <div style={{display:'flex', gap:6}}>
              {['list','visual'].map(v => (
                <button key={v} onClick={() => setView(v)}
                  style={{padding:'7px 14px', borderRadius:8, border:'1px solid var(--surface-4)',
                    background:view===v?'var(--accent-muted)':'transparent', color:view===v?'var(--accent)':'var(--text-2)',
                    cursor:'pointer', fontFamily:'inherit', fontSize: "var(--text-base)"}}>
                  {v === 'list' ? '📋 Lista' : '🗺 Mapa visual'}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {!project && <EmptyState icon="🔗" title="Selecciona un proyecto" description="Elige un proyecto para ver o crear dependencias entre tareas" />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && (
        <>
          {/* KPIs */}
          {edges.length > 0 && (
            <div style={{display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20}}>
              {[
                ['Total deps', edges.length, 'var(--text-1)'],
                ['Bloqueos', blocked.length, 'var(--danger)'],
                ['Tareas bloqueadas', new Set(blocked.map(e=>e.to_task_id)).size, 'var(--warning)'],
                ['Tareas bloqueantes', new Set(blocked.map(e=>e.from_task_id)).size, 'var(--accent)'],
              ].map(([label, val, color]) => (
                <div key={label} style={{...ps, padding:'14px 16px'}}>
                  <div style={{fontSize: "var(--text-2xl)", fontWeight:700, color}}>{val}</div>
                  <div style={{fontSize: "var(--text-xs)", color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em'}}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {view === 'visual' && <div style={ps}><GanttDepsView nodes={nodes} edges={edges} /></div>}

          {view === 'list' && (
            <div style={ps}>
              {edges.length === 0 ? (
                <div style={{textAlign:'center', padding:'48px 24px'}}>
                  <div style={{fontSize: "var(--text-6xl)", marginBottom:16}}>🔗</div>
                  <div style={{fontSize: "var(--text-md-em)", fontWeight:600, marginBottom:8}}>Sin dependencias</div>
                  <div style={{fontSize: "var(--text-base)", color:'var(--text-2)', marginBottom:20}}>
                    Define qué tareas bloquean a otras para visualizar el camino crítico.
                  </div>
                  <Button onClick={() => setShowForm(true)}>+ Crear primera dependencia</Button>
                </div>
              ) : (
                <table style={{width:'100%', borderCollapse:'collapse', fontSize: "var(--text-base)"}}>
                  <thead>
                    <tr style={{borderBottom:'1px solid var(--surface-4)'}}>
                      {['Tarea A','Tipo','Tarea B','Lag','Nota',''].map(h => (
                        <th key={h} style={{textAlign:'left', padding:'8px 12px', fontSize: "var(--text-xs)", color:'var(--text-2)',
                          textTransform:'uppercase', letterSpacing:'.06em'}}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {edges.map((e, i) => {
                      const dt = DEP_TYPES.find(d => d.value === e.dep_type)
                      return (
                        <tr key={e.id} style={{borderBottom:'1px solid var(--surface-4)', background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                          <td style={{padding:'10px 12px', fontWeight:500, maxWidth:180}}>
                            <div style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                              {e.from_task_title}
                            </div>
                            <div style={{fontSize: "var(--text-xs)", color:STATUS_COLOR[e.from_task_status]||'var(--text-2)'}}>
                              {e.from_task_status}
                            </div>
                          </td>
                          <td style={{padding:'10px 12px'}}>
                            <span style={{fontSize: "var(--text-xs)", padding:'3px 8px', borderRadius:20,
                              background:(dt?.color||'var(--text-2)')+'20', color:dt?.color||'var(--text-2)', fontWeight:600}}>
                              {dt?.label}
                            </span>
                          </td>
                          <td style={{padding:'10px 12px', fontWeight:500, maxWidth:180}}>
                            <div style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                              {e.to_task_title}
                            </div>
                            <div style={{fontSize: "var(--text-xs)", color:STATUS_COLOR[e.to_task_status]||'var(--text-2)'}}>
                              {e.to_task_status}
                            </div>
                          </td>
                          <td style={{padding:'10px 12px', color:'var(--text-2)', fontSize: "var(--text-sm)"}}>
                            {e.lag_days > 0 ? `+${e.lag_days}d` : '—'}
                          </td>
                          <td style={{padding:'10px 12px', color:'var(--text-2)', fontSize: "var(--text-sm)", maxWidth:160}}>
                            <div style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                              {e.note || '—'}
                            </div>
                          </td>
                          <td style={{padding:'10px 12px'}}>
                            <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta dependencia?', onConfirm: () => deleteEdge(e.id), danger: true }) }}
                              style={{background:'none', border:'1px solid var(--danger-border)', borderRadius:6,
                                padding:'4px 8px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-xs)"}}>
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
