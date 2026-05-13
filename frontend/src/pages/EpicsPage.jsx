import { CHART_COLORS_EXTENDED, COLOR } from '../constants/theme'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, epicsApi } from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Layers } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const COLORS = CHART_COLORS_EXTENDED

const daysBetween = (a, b) => {
  if(!a||!b) return 0
  return Math.max(0, Math.round((new Date(b)-new Date(a))/(1000*60*60*24)))
}

function EpicForm({ projectId, epic, onClose }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!epic?.id
  const [form, setForm] = useState({
    title:       epic?.title       || '',
    description: epic?.description || '',
    color:       epic?.color       || COLOR.purple,
    status:      epic?.status      || 'open',
    priority:    epic?.priority    || 'medium',
    start_date:  epic?.start_date  || '',
    end_date:    epic?.end_date    || '',
    sort_order:  epic?.sort_order  || 0,
  })
  const set = k => v => setForm(f=>({...f,[k]:v}))

  const STATUS_CFG = {
    open:        { label: t('epics.status_open'),        color:'var(--text-2)', bg:'rgba(120,138,170,0.09)' },
    in_progress: { label: t('epics.status_in_progress'), color:'var(--accent)', bg:'var(--accent-muted)' },
    done:        { label: t('epics.status_done'),        color:'var(--success)', bg:'var(--success-bg)' },
    cancelled:   { label: t('epics.status_cancelled'),   color:'var(--danger)', bg:'var(--danger-bg)' },
  }
  const PRIORITY_CFG = {
    low:      { label: t('epics.priority_low'),      color:'var(--text-2)' },
    medium:   { label: t('epics.priority_medium'),   color:'var(--warning)' },
    high:     { label: t('epics.priority_high'),     color:'var(--warning)' },
    critical: { label: t('epics.priority_critical'), color:'var(--danger)' },
  }

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? epicsApi.update(epic.id, d).then(r=>r.data)
      : epicsApi.createForProject(projectId, d).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries(['epics',projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('epics.edit_epic') : t('epics.new_epic')}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div><label style={ls}>{t('epics.title_label')}</label><input style={is} value={form.title} onChange={e=>set('title')(e.target.value)} placeholder={t('epics.epic_name')}/></div>
        <div><label style={ls}>{t('common.description')}</label><textarea style={{...is,height:70,resize:'vertical'}} value={form.description} onChange={e=>set('description')(e.target.value)}/></div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div><label style={ls}>{t('common.status')}</label>
            <select style={is} value={form.status} onChange={e=>set('status')(e.target.value)}>
              {Object.entries(STATUS_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div><label style={ls}>{t('common.priority')}</label>
            <select style={is} value={form.priority} onChange={e=>set('priority')(e.target.value)}>
              {Object.entries(PRIORITY_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div><label style={ls}>{t('epics.start_date')}</label><input type="date" style={is} value={form.start_date} onChange={e=>set('start_date')(e.target.value)}/></div>
          <div><label style={ls}>{t('epics.end_date')}</label><input type="date" style={is} value={form.end_date} onChange={e=>set('end_date')(e.target.value)}/></div>
        </div>
        <div><label style={ls}>{t('epics.color_label')}</label>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
            {COLORS.map(c=>(
              <button key={c} onClick={()=>set('color')(c)}
                style={{width:28,height:28,borderRadius:'50%',background:c,border:form.color===c?'3px solid #fff':'2px solid transparent',cursor:'pointer'}}/>
            ))}
            <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR.purple} onChange={e=>set('color')(e.target.value)}
              style={{width:28,height:28,borderRadius:'50%',border:'none',cursor:'pointer',padding:0}}/>
          </div>
        </div>
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={()=>mutate(form)} disabled={isPending||!form.title} loading={isPending}>
            {isPending ? t('common.saving') : (isEdit ? t('common.save') : t('epics.new_epic'))}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function RoadmapView({ epics, t }) {
  if(!epics.length) return <EmptyState icon="🗺" title={t('epics.no_epics')} description={t('epics.no_epics_desc')}/>

  const datesWithValues = epics.flatMap(e=>[e.start_date,e.end_date].filter(Boolean))
  if(!datesWithValues.length) return <div style={{textAlign:'center',padding:40,color:'var(--text-2)',fontSize: "var(--text-base)"}}>{t('epics.no_epics_desc')}</div>

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
            <div key={i} style={{flex:1,fontSize: "var(--text-xs)",color:'var(--text-3)',textAlign:'center',borderLeft:'1px solid #1e2d45',padding:'4px 0'}}>{m}</div>
          ))}
        </div>
        {/* Épicas */}
        {epics.map(epic=>{
          const left  = epic.start_date ? pct(epic.start_date) : 0
          const w     = epic.start_date && epic.end_date ? width(epic.start_date, epic.end_date) : 20
          const _st    = STATUS_CFG[epic.status]||STATUS_CFG.open
          return (
            <div key={epic.id} style={{display:'flex',alignItems:'center',marginBottom:8,gap:0}}>
              <div style={{width:160,flexShrink:0,fontSize: "var(--text-sm)",fontWeight:500,paddingRight:10,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',color:'var(--text-1)'}}>
                {epic.title}
              </div>
              <div style={{flex:1,height:28,position:'relative',background:'var(--surface-1)',borderRadius:4,border:'1px solid #1e2d45'}}>
                <div style={{position:'absolute',left:`${left}%`,width:`${w}%`,height:'100%',background:epic.color||'var(--purple)',borderRadius:4,opacity:0.85,display:'flex',alignItems:'center',paddingLeft:8,overflow:'hidden',minWidth:4}}>
                  {w>8&&<span style={{fontSize: "var(--text-xs)",fontWeight:600,color:'#fff',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{epic.title}</span>}
                </div>
                {epic.progress>0&&(
                  <div style={{position:'absolute',left:`${left}%`,width:`${w*epic.progress/100}%`,height:'100%',background:'#fff',opacity:0.15,borderRadius:4}}/>
                )}
              </div>
              <div style={{width:50,flexShrink:0,textAlign:'right',fontSize: "var(--text-xs)",color:'var(--text-2)',paddingLeft:8}}>{epic.progress||0}%</div>
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

  const STATUS_CFG = {
    open:        { label: t('epics.status_open'),        color:'var(--text-2)', bg:'rgba(120,138,170,0.09)' },
    in_progress: { label: t('epics.status_in_progress'), color:'var(--accent)', bg:'var(--accent-muted)' },
    done:        { label: t('epics.status_done'),        color:'var(--success)', bg:'var(--success-bg)' },
    cancelled:   { label: t('epics.status_cancelled'),   color:'var(--danger)', bg:'var(--danger-bg)' },
  }
  const PRIORITY_CFG = {
    low:      { label: t('epics.priority_low'),      color:'var(--text-2)' },
    medium:   { label: t('epics.priority_medium'),   color:'var(--warning)' },
    high:     { label: t('epics.priority_high'),     color:'var(--warning)' },
    critical: { label: t('epics.priority_critical'), color:'var(--danger)' },
  }

  const { data:projects=[] } = useQuery({queryKey:['projects'],queryFn:()=>projectsApi.list().then(r=>Array.isArray(r.data)?r.data:[]).catch(()=>[])})
  const { data:epics=[],isLoading } = useQuery({
    queryKey:['epics',project],
    queryFn:()=>epicsApi.list(project).then(r=>r.data).catch(()=>[]),
    enabled:!!project,
  })
  const { data:roadmap } = useQuery({
    queryKey:['roadmap',project],
    queryFn:()=>epicsApi.roadmap(project).then(r=>r.data).catch(()=>null),
    enabled:!!project&&view==='roadmap',
  })

  const { mutate:deleteEpic } = useMutation({
    mutationFn: id=>epicsApi.delete(id),
    onSuccess:()=>qc.invalidateQueries(['epics',project]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const roadmapEpics = roadmap?.epics || epics

  return (
    <PageShell>
      <PageHeader icon={<Layers size={18} />} title={t('epics.title')} subtitle={t('epics.subtitle')}
        actions={project&&(
          <div style={{display:'flex',gap:8}}>
            <button onClick={()=>setView('list')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:view==='list'?'var(--accent-muted)':'transparent',color:view==='list'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>{t('epics.list_view')}</button>
            <button onClick={()=>setView('roadmap')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:view==='roadmap'?'var(--accent-muted)':'transparent',color:view==='roadmap'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>🗺 {t('epics.roadmap')}</button>
            <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ {t('epics.new_epic')}</Button>
          </div>
        )}
        showListExport={view==='list' && epics.length > 0}
        exportTargetSelector='[data-export-table="epics-list"]'
        exportFilePrefix='epics'
      />

      {/* Selector proyecto */}
      <div style={{...ps,marginBottom:20}}>
        <label style={ls}>{t('epics.project_label')}</label>
        <select value={project} onChange={e=>setProject(e.target.value)} style={{...is,width:360}}>
          <option value="">{t('epics.select_project_placeholder')}</option>
          {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="🗂" title={t('epics.no_project_title')} description={t('epics.no_project_desc')}/>}
      {project&&isLoading&&<Spinner/>}

      {project&&!isLoading&&epics.length===0&&(
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)",marginBottom:16}}>🎯</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>{t('epics.no_epics')}</div>
          <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:20}}>{t('epics.no_epics_desc')}</div>
          <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ {t('epics.create_first')}</Button>
        </div>
      )}

      {project&&epics.length>0&&view==='roadmap'&&(
        <div style={ps}>
          <div style={{fontSize: "var(--text-md)",fontWeight:600,marginBottom:20}}>{t('epics.roadmap_title')} — {projects.find(p=>p.id===project)?.name}</div>
          <RoadmapView epics={roadmapEpics} t={t}/>
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
                  <div style={{fontSize: "var(--text-xl-em)",fontWeight:700,color:c.color}}>{cnt}</div>
                  <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)'}}>{c.label}</div>
                </div>
              )
            })}
          </div>

          {/* Lista de épicas */}
          <div data-export-table="epics-list" style={{display:'flex',flexDirection:'column',gap:10}}>
            {epics.map(epic=>{
              const st  = STATUS_CFG[epic.status]  || STATUS_CFG.open
              const pri = PRIORITY_CFG[epic.priority] || PRIORITY_CFG.medium
              const progress = epic.task_count>0 ? Math.round((epic.done_tasks||0)/epic.task_count*100) : 0
              return (
                <button key={epic.id} type="button" style={{...ps,padding:'16px 20px',border:`1px solid ${epic.color}30`,cursor:'pointer',width:'100%',textAlign:'left',fontFamily:'inherit'}}
                  onClick={()=>setDetailEpic(epic)}>
                  <div style={{display:'flex',alignItems:'flex-start',gap:14}}>
                    <div style={{width:4,height:48,borderRadius:2,background:epic.color,flexShrink:0,marginTop:2}}/>
                    <div style={{flex:1}}>
                      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:6}}>
                        <span style={{fontWeight:600,fontSize: "var(--text-md)"}}>{epic.title}</span>
                        <span style={{fontSize: "var(--text-xs)",padding:'2px 8px',borderRadius:20,background:st.bg,color:st.color}}>{st.label}</span>
                        <span style={{fontSize: "var(--text-xs)",color:pri.color}}>⬆ {pri.label}</span>
                      </div>
                      {epic.description&&<div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:8}}>{epic.description}</div>}
                      <div style={{display:'flex',alignItems:'center',gap:20,fontSize: "var(--text-sm)",color:'var(--text-2)'}}>
                        {epic.start_date&&<span>📅 {epic.start_date} → {epic.end_date||t('epics.no_end_date')}</span>}
                        <span>📌 {epic.task_count||0} {t('epics.tasks_count')}</span>
                        {epic.task_count>0&&<span style={{color:'var(--success)'}}>{progress}% {t('epics.completed_label')}</span>}
                      </div>
                      {epic.task_count>0&&(
                        <div style={{marginTop:8,height:4,background:'var(--surface-4)',borderRadius:2,overflow:'hidden'}}>
                          <div style={{height:'100%',width:`${progress}%`,background:epic.color,borderRadius:2,transition:'width .3s'}}/>
                        </div>
                      )}
                    </div>
                    <div style={{display:'flex',gap:6,flexShrink:0}}>
                      <button onClick={e=>{e.stopPropagation();setEditEpic(epic);setShowForm(true)}}
                        style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>{t('common.edit')}</button>
                      <button onClick={e=>{e.stopPropagation();openConfirmGlobal({message:`${t('common.are_you_sure')} "${epic.title}"?`,onConfirm:()=>deleteEpic(epic.id),danger:true})}}
                        style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:6,padding:'4px 10px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>{t('common.delete')}</button>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {showForm&&(
        <EpicForm projectId={project} epic={editEpic}
          onClose={()=>{setShowForm(false);setEditEpic(null)}}/>
      )}
    </PageShell>
  )
}
