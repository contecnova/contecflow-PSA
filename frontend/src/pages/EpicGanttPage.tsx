import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, epicsApi, epicDependenciesApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

type DepType = 'finish_to_start' | 'start_to_start' | 'finish_to_finish' | 'relates_to'

interface ProjectItem {
  id: string | number
  name?: string
}

interface EpicItem {
  id: string | number
  title: string
  color?: string
  start_date?: string
  end_date?: string
  progress?: number
}

interface EpicDependency {
  id: string | number
  epic_id: string | number
  depends_on_id: string | number
  dep_type: DepType
  lag_days: number
  epic_title?: string
  depends_on_title?: string
}

interface RoadmapData {
  epics?: EpicItem[]
}

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const DEP_TYPES = [
  { value:'finish_to_start',  label:'Fin → Inicio',    color:'var(--danger)', symbol:'FS', desc:'B no empieza hasta que A termine' },
  { value:'start_to_start',   label:'Inicio → Inicio', color:'var(--warning)', symbol:'SS', desc:'B no empieza hasta que A empiece' },
  { value:'finish_to_finish', label:'Fin → Fin',       color:'var(--accent)', symbol:'FF', desc:'B no termina hasta que A termine' },
  { value:'relates_to',       label:'Relacionada',     color:'var(--text-2)', symbol:'RE', desc:'Sin bloqueo, solo vinculadas' },
]

function daysBetween(a?: string, b?: string) {
  if (!a || !b) return 0
  return Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000))
}

function GanttWithDeps({ epics, deps }: { epics: EpicItem[]; deps: EpicDependency[] }) {
  const t = useAppT()
  const dates = epics.flatMap((e) => [e.start_date, e.end_date].filter((v): v is string => Boolean(v)))
  if (!dates.length) return (
    <div style={{textAlign:'center', padding:40, color:'var(--text-2)', fontSize: "var(--text-base)"}}>
      {t('epicgantt.asigna_fechas_de_inicio_y_fin_a')}
    </div>
  )

  const minDate   = new Date(Math.min(...dates.map((d) => new Date(d).getTime())))
  const maxDate   = new Date(Math.max(...dates.map((d) => new Date(d).getTime())))
  const totalDays = Math.max(daysBetween(minDate.toISOString().slice(0,10), maxDate.toISOString().slice(0,10)), 1)
  const epicMap   = Object.fromEntries(epics.map(e => [e.id, e]))

  const pct = (d?: string) => {
    if (!d) return 0
    const diff = daysBetween(minDate.toISOString().slice(0,10), d)
    return Math.min(100, Math.max(0, (diff / totalDays) * 100))
  }
  const barW = (sd?: string, ed?: string) => Math.max(2, pct(ed) - pct(sd))

  // Cabecera meses
  const months = []
  const cur = new Date(minDate); cur.setDate(1)
  while (cur <= maxDate) {
    months.push(cur.toLocaleDateString('es-ES', {month:'short', year:'2-digit'}))
    cur.setMonth(cur.getMonth() + 1)
  }

  return (
    <div style={{overflowX:'auto'}}>
      <div style={{minWidth:700}}>
        {/* Meses */}
        <div style={{display:'flex', marginLeft:180, marginBottom:8}}>
          {months.map((m, i) => (
            <div key={i} style={{flex:1, fontSize: "var(--text-xs)", color:'var(--text-3)', textAlign:'center',
              borderLeft:'1px solid var(--surface-4)', padding:'4px 0'}}>{m}</div>
          ))}
        </div>

        {/* Épicas */}
        {epics.map((epic, idx) => {
          const left = epic.start_date ? pct(epic.start_date) : 0
          const w    = (epic.start_date && epic.end_date) ? barW(epic.start_date, epic.end_date) : 15
          const prog = epic.progress || 0
          // Dependencias de esta épica
          const outDeps = deps.filter(d => d.epic_id === epic.id)
          return (
            <div key={epic.id} style={{display:'flex', alignItems:'center', marginBottom:4}}>
              <div style={{width:180, flexShrink:0, fontSize: "var(--text-sm)", fontWeight:500, paddingRight:10,
                overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', color:'var(--text-1)',
                display:'flex', alignItems:'center', gap:6}}>
                <div style={{width:10, height:10, borderRadius:'50%', background:epic.color, flexShrink:0}} />
                {epic.title}
              </div>
              <div style={{flex:1, height:32, position:'relative', background:'var(--surface-1)',
                border:'1px solid var(--surface-4)', borderRadius:4}}>
                {/* Barra principal */}
                <div style={{position:'absolute', left:`${left}%`, width:`${w}%`, height:'100%',
                  background:epic.color, borderRadius:4, opacity:0.85, minWidth:4,
                  display:'flex', alignItems:'center', paddingLeft:8, overflow:'hidden'}}>
                  {w > 8 && <span style={{fontSize: "var(--text-xs)", fontWeight:600, color:'#fff',
                    whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis'}}>{epic.title}</span>}
                </div>
                {/* Progreso overlay */}
                {prog > 0 && (
                  <div style={{position:'absolute', left:`${left}%`, width:`${w * prog / 100}%`,
                    height:'100%', background:'#fff', opacity:0.2, borderRadius:4}} />
                )}
                {/* Flechas de dependencia (SVG) */}
                {outDeps.map(dep => {
                  const target = epicMap[dep.depends_on_id]
                  if (!target?.start_date) return null
                  const dt = DEP_TYPES.find(d => d.value === dep.dep_type)
                  // Determinar punto de salida y llegada según tipo
                  const fromX = dep.dep_type.startsWith('start') ? left : (left + w)
                  const toX   = dep.dep_type.endsWith('finish') ? (pct(target.end_date)) : pct(target.start_date)
                  const toIdx = epics.findIndex(e => e.id === dep.depends_on_id)
                  const dy    = (toIdx - idx) * 36  // altura aproximada por fila
                  if (dy === 0) return null
                  return (
                    <svg key={dep.id}
                      style={{position:'absolute', left:`${Math.min(fromX,toX)}%`,
                        top:dy > 0 ? '50%' : 'auto', bottom:dy < 0 ? '50%' : 'auto',
                        width:`${Math.abs(toX-fromX) || 2}%`, height:Math.abs(dy), overflow:'visible', pointerEvents:'none'}}
                      overflow="visible">
                      <defs>
                        <marker id={`arr-${dep.id}`} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                          <path d="M0,0 L0,6 L6,3 Z" fill={dt?.color || 'var(--text-2)'} />
                        </marker>
                      </defs>
                      <path d={`M ${fromX > toX ? '100%' : '0'},0 L ${fromX > toX ? '0' : '100%'},${Math.abs(dy)}`}
                        stroke={dt?.color || 'var(--text-2)'} strokeWidth="1.5" strokeDasharray="4,3"
                        fill="none" markerEnd={`url(#arr-${dep.id})`} />
                    </svg>
                  )
                })}
              </div>
              <div style={{width:50, flexShrink:0, textAlign:'right', fontSize: "var(--text-xs)", color:'var(--text-2)', paddingLeft:8}}>
                {prog}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function EpicDepForm({ projectId, epics, onClose }: { projectId: string; epics: EpicItem[]; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ epic_id:'', depends_on_id:'', dep_type:'finish_to_start', lag_days:0 })
  const set = (k: 'epic_id' | 'depends_on_id' | 'dep_type' | 'lag_days') => (v: string | number) => setForm((f) => ({...f, [k]: v}))
  const _selType = DEP_TYPES.find(d => d.value === form.dep_type)

  const { mutate, isPending } = useMutation({
    mutationFn: () => epicDependenciesApi.create(form).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['epic-deps', projectId] }); qc.invalidateQueries({ queryKey: ['epic-gantt', projectId] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al crear dependencia')),
  })

  return (
    <Modal open onClose={onClose} title={t('epicgantt.nueva_dependencia_entre_epicas')}>
      <div style={{display:'flex', flexDirection:'column', gap:14}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12}}>
          <div>
            <label style={ls}>{t('epicgantt.epica_a')}</label>
            <select style={is} value={form.epic_id} onChange={e => set('epic_id')(e.target.value)}>
              <option value="">{t('epicgantt.selecciona_epica')}</option>
              {epics.map(e => <option key={e.id} value={e.id}>{e.title}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('epicgantt.epica_b_depende_de_a')}</label>
            <select style={is} value={form.depends_on_id} onChange={e => set('depends_on_id')(e.target.value)}>
              <option value="">{t('epicgantt.selecciona_epica')}</option>
              {epics.filter(e => e.id !== form.epic_id).map(e => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label style={ls}>{t('epicgantt.tipo_de_dependencia')}</label>
          <div style={{display:'flex', flexDirection:'column', gap:6}}>
            {DEP_TYPES.map(dt => (
              <button key={dt.value} onClick={() => set('dep_type')(dt.value)}
                style={{display:'flex', alignItems:'center', gap:12, padding:'10px 14px', borderRadius:8,
                  border:`1px solid ${form.dep_type===dt.value ? dt.color+'50' : 'var(--surface-4)'}`,
                  background:form.dep_type===dt.value ? dt.color+'15' : 'transparent',
                  cursor:'pointer', fontFamily:'inherit', textAlign:'left'}}>
                <span style={{fontSize: "var(--text-sm)", fontWeight:700, padding:'2px 6px', borderRadius:4,
                  background:dt.color+'30', color:dt.color, minWidth:28, textAlign:'center'}}>{dt.symbol}</span>
                <div style={{flex:1}}>
                  <div style={{fontSize: "var(--text-base)", fontWeight:form.dep_type===dt.value?600:400,
                    color:form.dep_type===dt.value ? dt.color : 'var(--text-1)'}}>{dt.label}</div>
                  <div style={{fontSize: "var(--text-xs)", color:'var(--text-2)'}}>{dt.desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label style={ls}>{t('epicgantt.lag_dias_de_retraso_adicional')}</label>
          <input type="number" style={{...is, width:120}} value={form.lag_days} min={0}
            onChange={e => set('lag_days')(+e.target.value)} />
        </div>

        <div style={{display:'flex', justifyContent:'flex-end', gap:10, marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.epic_id || !form.depends_on_id} loading={isPending}>
            {isPending ? 'Creando...' : 'Crear dependencia'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function EpicGanttPage(): JSX.Element {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project,  setProject]  = useState('')
  const [showForm, setShowForm] = useState(false)

  const { data: projectsRaw = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const projects = projectsRaw as ProjectItem[]
  const { data: roadmapRaw, isLoading: lRoadmap } = useQuery({
    queryKey: ['epic-gantt', project],
    queryFn: () => epicsApi.roadmapByProject(project).then(r => r.data).catch(() => null),
    enabled: !!project,
  })
  const roadmap = (roadmapRaw ?? null) as RoadmapData | null
  const { data: epicDepsRaw = [], isLoading: lDeps } = useQuery({
    queryKey: ['epic-deps', project],
    queryFn: () => epicDependenciesApi.get(project).then(r => r.data).catch(() => []),
    enabled: !!project,
  })
  const epicDeps = epicDepsRaw as EpicDependency[]

  const { mutate: deleteDep } = useMutation({
    mutationFn: (id: string | number) => epicDependenciesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['epic-deps', project] }); qc.invalidateQueries({ queryKey: ['epic-gantt', project] }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const epics = roadmap?.epics || []
  const isLoading = lRoadmap || lDeps

  return (
    <PageShell>
      <PageHeader icon={<BarChart2 size={18} />} title={t('epics.gantt_title')} subtitle={t('epics.subtitle')}
        actions={project && epics.length > 0 && (
          <Button onClick={() => setShowForm(true)}>+ Dependencia</Button>
        )} showListExport={false} />

      <div style={{...ps, marginBottom:20}}>
        <label style={ls}>Proyecto</label>
        <select value={project} onChange={e => setProject(e.target.value)} style={{...is, width:360}}>
          <option value="">{t('epicgantt.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="📊" title={t('epicgantt.selecciona_un_proyecto_2')} description="Elige un proyecto para ver el Gantt de epicas y sus dependencias" />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && epics.length === 0 && (
        <div style={{...ps, textAlign:'center', padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)", marginBottom:16}}>🎯</div>
          <div style={{fontSize: "var(--text-md-em)", fontWeight:600, marginBottom:8}}>{t('epicgantt.sin_epicas')}</div>
          <div style={{fontSize: "var(--text-base)", color:'var(--text-2)', marginBottom:20}}>
            {t('epicgantt.crea_epicas_con_fechas_en_la_seccion')} <strong>{t('epicgantt.epicas')}</strong> {t('epicgantt.para_verlas_en_el_gantt_con_dependencias')}
          </div>
        </div>
      )}

      {project && !isLoading && epics.length > 0 && (
        <div>
          {/* Gantt visual */}
          <div style={ps}>
            <div style={{fontSize: "var(--text-md)", fontWeight:600, marginBottom:20}}>
              {t('epicgantt.roadmap_con_dependencias')} {projects.find(p => p.id === project)?.name}
            </div>
            <GanttWithDeps epics={epics} deps={epicDeps} />
          </div>

          {/* Lista de dependencias */}
          <div style={{...ps, marginTop:16}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16}}>
              <div style={{fontSize: "var(--text-md)", fontWeight:600}}>
                Dependencias ({epicDeps.length})
              </div>
              <Button onClick={() => setShowForm(true)}>{t('epicgantt.anadir')}</Button>
            </div>
            {epicDeps.length === 0 ? (
              <div style={{textAlign:'center', padding:'24px', color:'var(--text-3)', fontSize: "var(--text-base)"}}>
                {t('epicgantt.sin_dependencias_entre_epicas_las_dependencias_aparecen')}
              </div>
            ) : (
              <div style={{display:'flex', flexDirection:'column', gap:8}}>
                {epicDeps.map(dep => {
                  const dt = DEP_TYPES.find(d => d.value === dep.dep_type)
                  return (
                    <div key={dep.id} style={{display:'flex', alignItems:'center', gap:12,
                      padding:'10px 14px', background:'var(--surface-1)', borderRadius:8, border:'1px solid var(--surface-4)', fontSize: "var(--text-sm)"}}>
                      <span style={{fontSize: "var(--text-xs)", fontWeight:700, padding:'2px 6px', borderRadius:4,
                        background:dt?.color+'30', color:dt?.color, minWidth:28, textAlign:'center'}}>
                        {dt?.symbol}
                      </span>
                      <div style={{flex:1}}>
                        <span style={{fontWeight:500}}>{dep.epic_title}</span>
                        <span style={{color:'var(--text-3)', margin:'0 8px'}}>→</span>
                        <span style={{fontWeight:500, color:'var(--accent)'}}>{dep.depends_on_title}</span>
                        <span style={{color:'var(--text-2)', marginLeft:8}}>{dt?.label}</span>
                        {dep.lag_days > 0 && <span style={{color:'var(--text-3)', marginLeft:6}}>+{dep.lag_days}d</span>}
                      </div>
                      <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar dependencia?', onConfirm: () => deleteDep(dep.id), danger: true }) }}
                        style={{background:'none', border:'none', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-base)"}}>✕</button>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Leyenda tipos */}
            <div style={{marginTop:16, padding:'12px 14px', background:'var(--surface-1)', borderRadius:8,
              border:'1px solid var(--surface-4)', display:'flex', gap:20, flexWrap:'wrap'}}>
              {DEP_TYPES.map(dt => (
                <div key={dt.value} style={{display:'flex', alignItems:'center', gap:6, fontSize: "var(--text-xs)"}}>
                  <span style={{fontWeight:700, padding:'1px 5px', borderRadius:3,
                    background:dt.color+'30', color:dt.color}}>{dt.symbol}</span>
                  <span style={{color:'var(--text-2)'}}>{dt.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <EpicDepForm projectId={project} epics={epics}
          onClose={() => setShowForm(false)} />
      )}
    </PageShell>
  )
}
