import { CHART } from '../constants/theme'
import { extractErr } from '../utils/helpers'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const STATUS_CFG = {
  open:        { label:'Abierta',     color:'var(--text-2)', bg:'rgba(120,138,170,0.09)' },
  in_progress: { label:'En progreso', color:'var(--accent)', bg:'var(--accent-muted)' },
  done:        { label:'Completada',  color:'var(--success)', bg:'var(--success-bg)' },
  cancelled:   { label:'Cancelada',   color:'var(--danger)', bg:'var(--danger-bg)' },
}
const PRIORITY_CFG = {
  low:      { label:'Baja',     color:'var(--text-2)' },
  medium:   { label:'Media',    color:'var(--warning)' },
  high:     { label:'Alta',     color:'var(--warning)' },
  critical: { label:'Crítica',  color:'var(--danger)' },
}
const COLORS = ['var(--purple)','var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--warning)','var(--accent)',CHART.pink]

const daysBetween = (a, b) => {
  if(!a||!b) return 0
  return Math.max(0, Math.round((new Date(b)-new Date(a))/(1000*60*60*24)))
}

function EpicForm({ projectId, epic, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!epic?.id
  const [form, setForm] = useState({
    title:       epic?.title       || '',
    description: epic?.description || '',
    color:       epic?.color       || 'var(--purple)',
    status:      epic?.status      || 'open',
    priority:    epic?.priority    || 'medium',
    start_date:  epic?.start_date  || '',
    end_date:    epic?.end_date    || '',
    sort_order:  epic?.sort_order  || 0,
  })
  const set = k => v => setForm(f=>({...f,[k]:v}))

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? api.patch(`epics/${epic.id}`, d).then(r=>r.data)
      : api.post(`epics?project_id=${projectId}`, d).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries(['epics',projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit?'Editar épica':'Nueva épica'}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div><label style={ls}>Título</label><input style={is} value={form.title} onChange={e=>set('title')(e.target.value)} placeholder="Título de la épica"/></div>
        <div><label style={ls}>Descripción</label><textarea style={{...is,height:70,resize:'vertical'}} value={form.description} onChange={e=>set('description')(e.target.value)}/></div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div><label style={ls}>Estado</label>
            <select style={is} value={form.status} onChange={e=>set('status')(e.target.value)}>
              {Object.entries(STATUS_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div><label style={ls}>Prioridad</label>
            <select style={is} value={form.priority} onChange={e=>set('priority')(e.target.value)}>
              {Object.entries(PRIORITY_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div><label style={ls}>Fecha inicio</label><input type="date" style={is} value={form.start_date} onChange={e=>set('start_date')(e.target.value)}/></div>
          <div><label style={ls}>Fecha fin</label><input type="date" style={is} value={form.end_date} onChange={e=>set('end_date')(e.target.value)}/></div>
        </div>
        <div><label style={ls}>Color</label>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
            {COLORS.map(c=>(
              <button key={c} onClick={()=>set('color')(c)}
                style={{width:28,height:28,borderRadius:'50%',background:c,border:form.color===c?'3px solid #fff':'2px solid transparent',cursor:'pointer'}}/>
            ))}
            <input type="color" value={form.color} onChange={e=>set('color')(e.target.value)}
              style={{width:28,height:28,borderRadius:'50%',border:'none',cursor:'pointer',padding:0}}/>
          </div>
        </div>
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={()=>mutate(form)} disabled={isPending||!form.title} loading={isPending}>
            {isPending?'Guardando...':(isEdit?'Guardar':'Crear épica')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function RoadmapView({ epics }) {
  if(!epics.length) return <EmptyState icon="🗺" title="Sin épicas" description="Crea épicas con fechas para verlas en el roadmap"/>

  const datesWithValues = epics.flatMap(e=>[e.start_date,e.end_date].filter(Boolean))
  if(!datesWithValues.length) return <div style={{textAlign:'center',padding:40,color:'var(--text-2)',fontSize:13}}>Asigna fechas de inicio y fin a las épicas para ver el roadmap visual</div>

  const minDate = new Date(Math.min(...datesWithValues.map(d=>new Date(d))))
  const maxDate = new Date(Math.max(...datesWithValues.map(d=>new Date(d))))
  const totalDays = Math.max(daysBetween(minDate.toISOString().split('T')[0], maxDate.toISOString().split('T')[0]), 1)

  const pct = (d) => {
    if(!d) return 0
    const diff = daysBetween(minDate.toISOString().split('T')[0], d)
    return Math.min(100, Math.max(0, (diff/totalDays)*100))
  }
  const width = (sd, ed) => {
    if(!sd||!ed) return 10
    return Math.max(2, pct(ed)-pct(sd))
  }

  // Cabecera de meses
  const months = []
  const cur = new Date(minDate); cur.setDate(1)
  while(cur <= maxDate) {
    months.push(cur.toLocaleDateString('es-ES',{month:'short',year:'2-digit'}))
    cur.setMonth(cur.getMonth()+1)
  }

  return (
    <div style={{overflowX:'auto'}}>
      <div style={{minWidth:700}}>
        {/* Cabecera meses */}
        <div style={{display:'flex',marginLeft:160,marginBottom:8,gap:0}}>
          {months.map((m,i)=>(
            <div key={i} style={{flex:1,fontSize:11,color:'var(--text-3)',textAlign:'center',borderLeft:'1px solid #1a2640',padding:'4px 0'}}>{m}</div>
          ))}
        </div>
        {/* Épicas */}
        {epics.map(epic=>{
          const left  = epic.start_date ? pct(epic.start_date) : 0
          const w     = epic.start_date && epic.end_date ? width(epic.start_date, epic.end_date) : 20
          const _st    = STATUS_CFG[epic.status]||STATUS_CFG.open
          return (
            <div key={epic.id} style={{display:'flex',alignItems:'center',marginBottom:8,gap:0}}>
              <div style={{width:160,flexShrink:0,fontSize:12,fontWeight:500,paddingRight:10,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',color:'var(--text-1)'}}>
                {epic.title}
              </div>
              <div style={{flex:1,height:28,position:'relative',background:'var(--surface-1)',borderRadius:4,border:'1px solid #1a2640'}}>
                <div style={{position:'absolute',left:`${left}%`,width:`${w}%`,height:'100%',background:epic.color||'var(--purple)',borderRadius:4,opacity:0.85,display:'flex',alignItems:'center',paddingLeft:8,overflow:'hidden',minWidth:4}}>
                  {w>8&&<span style={{fontSize:11,fontWeight:600,color:'#fff',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{epic.title}</span>}
                </div>
                {epic.progress>0&&(
                  <div style={{position:'absolute',left:`${left}%`,width:`${w*epic.progress/100}%`,height:'100%',background:'#fff',opacity:0.15,borderRadius:4}}/>
                )}
              </div>
              <div style={{width:50,flexShrink:0,textAlign:'right',fontSize:11,color:'var(--text-2)',paddingLeft:8}}>{epic.progress||0}%</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function EpicsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project,   setProject]   = useState('')
  const [view,      setView]      = useState('list')   // list | roadmap
  const [showForm,  setShowForm]  = useState(false)
  const [editEpic,  setEditEpic]  = useState(null)
  const [_detailEpic,setDetailEpic]= useState(null)

  const { data:projects=[] } = useQuery({queryKey:['projects'],queryFn:()=>api.get('/projects').then(r=>Array.isArray(r.data)?r.data:[]).catch(()=>[])})
  const { data:epics=[],isLoading } = useQuery({
    queryKey:['epics',project],
    queryFn:()=>api.get(`epics?project_id=${project}`).then(r=>r.data).catch(()=>[]),
    enabled:!!project,
  })
  const { data:roadmap } = useQuery({
    queryKey:['roadmap',project],
    queryFn:()=>api.get(`roadmap?project_id=${project}`).then(r=>r.data).catch(()=>null),
    enabled:!!project&&view==='roadmap',
  })

  const { mutate:deleteEpic } = useMutation({
    mutationFn: id=>api.delete(`epics/${id}`),
    onSuccess:()=>qc.invalidateQueries(['epics',project]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const roadmapEpics = roadmap?.epics || epics

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('epics.title')} subtitle="Agrupa tareas en objetivos de mayor nivel y visualiza el roadmap"
        actions={project&&(
          <div style={{display:'flex',gap:8}}>
            <button onClick={()=>setView('list')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid #1e2d45',background:view==='list'?'var(--accent-muted)':'transparent',color:view==='list'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>Lista</button>
            <button onClick={()=>setView('roadmap')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid #1e2d45',background:view==='roadmap'?'var(--accent-muted)':'transparent',color:view==='roadmap'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>🗺 Roadmap</button>
            <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ Nueva épica</Button>
          </div>
        )}/>

      {/* Selector proyecto */}
      <div style={{...ps,marginBottom:20}}>
        <label style={ls}>Proyecto</label>
        <select value={project} onChange={e=>setProject(e.target.value)} style={{...is,width:360}}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="🗂" title="Selecciona un proyecto" description="Las épicas se organizan por proyecto"/>}
      {project&&isLoading&&<Spinner/>}

      {project&&!isLoading&&epics.length===0&&(
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize:48,marginBottom:16}}>🎯</div>
          <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>Sin épicas</div>
          <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>Las épicas agrupan historias y tareas en objetivos estratégicos de mayor nivel.</div>
          <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ Crear primera épica</Button>
        </div>
      )}

      {project&&epics.length>0&&view==='roadmap'&&(
        <div style={ps}>
          <div style={{fontSize:14,fontWeight:600,marginBottom:20}}>Roadmap de épicas — {projects.find(p=>p.id===project)?.name}</div>
          <RoadmapView epics={roadmapEpics}/>
        </div>
      )}

      {project&&epics.length>0&&view==='list'&&(
        <div>
          {/* Resumen */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,marginBottom:20}}>
            {Object.entries(STATUS_CFG).map(([s,c])=>{
              const cnt = epics.filter(e=>e.status===s).length
              return (
                <div key={s} style={{...ps,padding:'14px 16px'}}>
                  <div style={{fontSize:22,fontWeight:700,color:c.color}}>{cnt}</div>
                  <div style={{fontSize:11,color:'var(--text-2)'}}>{c.label}</div>
                </div>
              )
            })}
          </div>

          {/* Lista de épicas */}
          <div style={{display:'flex',flexDirection:'column',gap:10}}>
            {epics.map(epic=>{
              const st  = STATUS_CFG[epic.status]  || STATUS_CFG.open
              const pri = PRIORITY_CFG[epic.priority] || PRIORITY_CFG.medium
              const progress = epic.task_count>0 ? Math.round((epic.done_tasks||0)/epic.task_count*100) : 0
              return (
                <div key={epic.id} style={{...ps,padding:'16px 20px',border:`1px solid ${epic.color}30`,cursor:'pointer'}}
                  onClick={()=>setDetailEpic(epic)}>
                  <div style={{display:'flex',alignItems:'flex-start',gap:14}}>
                    <div style={{width:4,height:48,borderRadius:2,background:epic.color,flexShrink:0,marginTop:2}}/>
                    <div style={{flex:1}}>
                      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:6}}>
                        <span style={{fontWeight:600,fontSize:14}}>{epic.title}</span>
                        <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:st.bg,color:st.color}}>{st.label}</span>
                        <span style={{fontSize:11,color:pri.color}}>⬆ {pri.label}</span>
                      </div>
                      {epic.description&&<div style={{fontSize:13,color:'var(--text-2)',marginBottom:8}}>{epic.description}</div>}
                      <div style={{display:'flex',alignItems:'center',gap:20,fontSize:12,color:'var(--text-2)'}}>
                        {epic.start_date&&<span>📅 {epic.start_date} → {epic.end_date||'sin fecha fin'}</span>}
                        <span>📌 {epic.task_count||0} tareas</span>
                        {epic.task_count>0&&<span style={{color:'var(--success)'}}>{progress}% completado</span>}
                      </div>
                      {epic.task_count>0&&(
                        <div style={{marginTop:8,height:4,background:'var(--surface-4)',borderRadius:2,overflow:'hidden'}}>
                          <div style={{height:'100%',width:`${progress}%`,background:epic.color,borderRadius:2,transition:'width .3s'}}/>
                        </div>
                      )}
                    </div>
                    <div style={{display:'flex',gap:6,flexShrink:0}}>
                      <button onClick={e=>{e.stopPropagation();setEditEpic(epic);setShowForm(true)}}
                        style={{background:'none',border:'1px solid #1e2d45',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:11}}>Editar</button>
                      <button onClick={e=>{e.stopPropagation();openConfirmGlobal({message:`¿Eliminar "${epic.title}"?`,onConfirm:()=>deleteEpic(epic.id),danger:true})}}
                        style={{background:'none',border:'1px solid #ff475730',borderRadius:6,padding:'4px 10px',color:'var(--danger)',cursor:'pointer',fontSize:11}}>Eliminar</button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {showForm&&(
        <EpicForm projectId={project} epic={editEpic}
          onClose={()=>{setShowForm(false);setEditEpic(null)}}/>
      )}
    </div>
  )
}
