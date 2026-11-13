import { CHART_COLORS_EXTENDED, COLOR, alpha } from '../constants/theme'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, epicsApi, tasksApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Layers } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'

type EpicStatus = 'open' | 'in_progress' | 'done' | 'cancelled'
type EpicPriority = 'low' | 'medium' | 'high' | 'critical'

interface ProjectItem {
  id: string | number
  name?: string
}

interface EpicItem {
  id: string | number
  title: string
  description?: string
  color?: string
  status?: EpicStatus
  priority?: EpicPriority
  start_date?: string
  end_date?: string
  sort_order?: number
  task_count?: number
  done_tasks?: number
  progress?: number
}

interface EpicFormState {
  title: string
  description: string
  color: string
  status: EpicStatus
  priority: EpicPriority
  start_date: string
  end_date: string
  sort_order: number
}

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const COLORS = CHART_COLORS_EXTENDED

const daysBetween = (a?: string, b?: string) => {
  if(!a||!b) return 0
  return Math.max(0, Math.round((new Date(b).getTime()-new Date(a).getTime())/(1000*60*60*24)))
}

function EpicForm({ projectId, epic, onClose }: { projectId: string; epic?: EpicItem | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!epic?.id
  const [form, setForm] = useState<EpicFormState>({
    title:       epic?.title       || '',
    description: epic?.description || '',
    color:       epic?.color       || COLOR.purple,
    status:      epic?.status      || 'open',
    priority:    epic?.priority    || 'medium',
    start_date:  epic?.start_date  || '',
    end_date:    epic?.end_date    || '',
    sort_order:  epic?.sort_order  || 0,
  })
  const set = <K extends keyof EpicFormState>(k: K) => (v: EpicFormState[K]) => setForm((f) => ({ ...f, [k]: v }))

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
    mutationFn: (d: EpicFormState) => isEdit
      ? epicsApi.update(epic.id, d).then(r=>r.data)
      : epicsApi.createForProject(projectId, d).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['epics',projectId] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('epics.edit_epic') : t('epics.new_epic')}>
      <div className="u-stack-14">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('epics.title_label')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} style={is} value={form.title} onChange={e=>set('title')(e.target.value)} placeholder={t('epics.epic_name')}/></div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('common.description')}</label><textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} style={{...is,height:70,resize:'vertical'}} value={form.description} onChange={e=>set('description')(e.target.value)}/></div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('common.status')}</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} style={is} value={form.status} onChange={e=>set('status')(e.target.value as EpicStatus)}>
              {Object.entries(STATUS_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('common.priority')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} style={is} value={form.priority} onChange={e=>set('priority')(e.target.value as EpicPriority)}>
              {Object.entries(PRIORITY_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
        </div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('epics.start_date')}</label><DateInput id={`${idCampo}-5`} style={is} value={form.start_date} onChange={e=>set('start_date')(e.target.value)}/></div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('epics.end_date')}</label><DateInput id={`${idCampo}-6`} style={is} value={form.end_date} onChange={e=>set('end_date')(e.target.value)}/></div>
        </div>
        <div><label style={ls}>{t('epics.color_label')}</label>
          <div className="u-wrap-8">
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

/** Ficha de una épica: su avance y sus tareas; quien puede escribir enlaza y desenlaza. */
function EpicDetail({ epic, projectId, canEdit, onClose }: { epic: EpicItem; projectId: string; canEdit: boolean; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [elegida, setElegida] = useState('')
  const ficha = useQuery({ queryKey: ['epic', epic.id], queryFn: () => epicsApi.get(epic.id).then(r => r.data as { tasks?: { id: string; title: string; status: string }[] }) })
  const tareas = useQuery({ queryKey: ['tasks', projectId, 'epic'], enabled: canEdit,
    queryFn: () => tasksApi.list({ project_id: projectId, page_size: 500 }).then(r => {
      const d = r.data as { items?: { id: string; title: string }[] } | { id: string; title: string }[]
      return Array.isArray(d) ? d : (d?.items ?? [])
    }) })
  const enlazadas = ficha.data?.tasks ?? []
  const libres = (tareas.data ?? []).filter(x => !enlazadas.some(e => e.id === x.id))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['epic', epic.id] }); qc.invalidateQueries({ queryKey: ['epics'] }) }
  const enlazar = async (taskId: string, quitar = false) => {
    try { await (quitar ? epicsApi.unlinkTask(epic.id, taskId) : epicsApi.linkTask(epic.id, taskId)); setElegida(''); refrescar() }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const hechas = enlazadas.filter(x => x.status === 'done').length
  return (
    <Modal open onClose={onClose} title={epic.title}>
      <div className="u-stack-12">
        <div className="u-text2-sm">{t('epics.avance_de_tareas', { hechas, total: enlazadas.length })}</div>
        {ficha.isLoading ? <Spinner /> : enlazadas.length === 0
          ? <div className="u-text3-sm">{t('epics.sin_tareas')}</div>
          : enlazadas.map(x => (
            <div key={x.id} style={{ display: 'flex', gap: 8, alignItems: 'center', borderTop: '1px solid var(--surface-3)', paddingTop: 6 }}>
              <span style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', fontSize: 'var(--text-sm)' }}>{x.title}</span>
              <span style={{ fontSize: 'var(--text-xs)', color: x.status === 'done' ? 'var(--success)' : 'var(--text-3)' }}>{x.status}</span>
              {canEdit && <Button size="xs" variant="ghost" onClick={() => enlazar(x.id, true)}>{t('epics.quitar')}</Button>}
            </div>))}
        {canEdit && (
          <div className="u-wrap-8">
            <select aria-label={t('epics.anadir_tarea')} value={elegida} onChange={e => setElegida(e.target.value)}
              style={{ flex: '1 1 220px', minWidth: 0, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontFamily: 'inherit' }}>
              <option value="">{t('epics.anadir_tarea')}</option>
              {libres.map(x => <option key={x.id} value={x.id}>{x.title}</option>)}
            </select>
            <Button size="sm" disabled={!elegida} onClick={() => enlazar(elegida)}>{t('epics.enlazar')}</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}

function RoadmapView({ epics, t }: { epics: EpicItem[]; t: (key: string, params?: Record<string, string | number>) => string }) {
  if(!epics.length) return <EmptyState icon="🗺" title={t('epics.no_epics')} description={t('epics.no_epics_desc')}/>

  const datesWithValues = epics.flatMap((e) => [e.start_date, e.end_date].filter((v): v is string => Boolean(v)))
  if(!datesWithValues.length) return <div style={{textAlign:'center',padding:40,color:'var(--text-2)',fontSize: "var(--text-base)"}}>{t('epics.no_epics_desc')}</div>

  const minDate = new Date(Math.min(...datesWithValues.map((d) => new Date(d).getTime())))
  const maxDate = new Date(Math.max(...datesWithValues.map((d) => new Date(d).getTime())))
  const totalDays = Math.max(daysBetween(minDate.toISOString().split('T')[0], maxDate.toISOString().split('T')[0]), 1)

  const pct = (d?: string) => {
    if(!d) return 0
    const diff = daysBetween(minDate.toISOString().split('T')[0], d)
    return Math.min(100, Math.max(0, (diff/totalDays)*100))
  }
  const width = (sd?: string, ed?: string) => {
    if(!sd||!ed) return 10
    return Math.max(2, pct(ed)-pct(sd))
  }

  // Cabecera de meses
  const months = []
  const cur = new Date(minDate); cur.setDate(1)
  while(cur <= maxDate) {
    months.push(cur.toLocaleDateString(localeActivo(),{month:'short',year:'2-digit'}))
    cur.setMonth(cur.getMonth()+1)
  }

  return (
    <div className="u-scroll-x">
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
          return (
            <div key={epic.id} style={{display:'flex',alignItems:'center',marginBottom:8,gap:0}}>
              <div style={{width:160,flexShrink:0,fontSize: "var(--text-sm)",fontWeight:500,paddingRight:10,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',color:'var(--text-1)'}}>
                {epic.title}
              </div>
              <div style={{flex:1,height:28,position:'relative',background:'var(--surface-1)',borderRadius:4,border:'1px solid #1e2d45'}}>
                <div style={{position:'absolute',left:`${left}%`,width:`${w}%`,height:'100%',background:epic.color||'var(--purple)',borderRadius:4,opacity:0.85,display:'flex',alignItems:'center',paddingLeft:8,overflow:'hidden',minWidth:4}}>
                  {w>8&&<span style={{fontSize: "var(--text-xs)",fontWeight:600,color:'var(--on-accent-light)',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{epic.title}</span>}
                </div>
                {(epic.progress ?? 0)>0&&(
                  <div style={{position:'absolute',left:`${left}%`,width:`${w*(epic.progress ?? 0)/100}%`,height:'100%',background:'var(--on-accent-light)',opacity:0.15,borderRadius:4}}/>
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

export default function EpicsPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [project,   setProject]   = useState('')
  const [view,      setView]      = useState<'list' | 'roadmap'>('list')
  const [showForm,  setShowForm]  = useState(false)
  const [editEpic,  setEditEpic]  = useState<EpicItem | null>(null)
  const [detailEpic,setDetailEpic]= useState<EpicItem | null>(null)
  // Escribir épicas es de admin y PM (el backend lo exige): el jefe de equipo las ve en sólo lectura.
  const { user } = useAuth() as { user?: { role?: string } }
  const canEdit = ['admin', 'pm'].includes(user?.role ?? '')

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

  const { data:projectsRaw=[] } = useQuery({queryKey:['projects'],queryFn:()=>projectsApi.list({}).then(r=>Array.isArray(r.data)?r.data:[]).catch(()=>[])})
  const projects = projectsRaw as ProjectItem[]
  const { data:epicsRaw=[],isLoading } = useQuery({
    queryKey:['epics',project],
    queryFn:()=>epicsApi.list(project).then(r=>r.data).catch(()=>[]),
    enabled:!!project,
  })
  const epics = epicsRaw as EpicItem[]
  const { data:roadmapRaw } = useQuery({
    queryKey:['roadmap',project],
    queryFn:()=>epicsApi.roadmap(project).then(r=>r.data).catch(()=>null),
    enabled:!!project&&view==='roadmap',
  })
  const roadmap = (roadmapRaw ?? null) as { epics?: EpicItem[] } | null

  const { mutate:deleteEpic } = useMutation({
    mutationFn: (id: string | number) => epicsApi.delete(id),
    onSuccess:()=>qc.invalidateQueries({ queryKey: ['epics',project] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const roadmapEpics = roadmap?.epics || epics

  return (
    <PageShell>
      <PageHeader icon={<Layers size={18} />} title={t('epics.title')} subtitle={t('epics.subtitle')}
        actions={project&&(
          <div className="u-row-8">
            <button onClick={()=>setView('list')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:view==='list'?'var(--accent-muted)':'transparent',color:view==='list'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>{t('epics.list_view')}</button>
            <button onClick={()=>setView('roadmap')} style={{padding:'6px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:view==='roadmap'?'var(--accent-muted)':'transparent',color:view==='roadmap'?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>🗺 {t('epics.roadmap')}</button>
            {canEdit && <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ {t('epics.new_epic')}</Button>}
          </div>
        )}
        showListExport={view==='list' && epics.length > 0}
        exportTargetSelector='[data-export-table="epics-list"]'
        exportFilePrefix='epics'
      />

      {/* Selector proyecto */}
      <div style={{...ps,marginBottom:20}}>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('epics.project_label')}</label>
        <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e=>setProject(e.target.value)} style={{...is,width:360}}>
          <option value="">{t('epics.select_project_placeholder')}</option>
          {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="🗂" title={t('epics.no_project_title')} description={t('epics.no_project_desc')}/>}
      {project&&isLoading&&<Spinner/>}

      {project&&!isLoading&&epics.length===0&&(
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div className="u-empty-icon">🎯</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>{t('epics.no_epics')}</div>
          <div className="u-text2-base-mb20">{t('epics.no_epics_desc')}</div>
          {canEdit && <Button onClick={()=>{setEditEpic(null);setShowForm(true)}}>+ {t('epics.create_first')}</Button>}
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
                  <div className="u-text2-xs">{c.label}</div>
                </div>
              )
            })}
          </div>

          {/* Lista de épicas */}
          <div data-export-table="epics-list" className="u-stack-10">
            {epics.map(epic=>{
              const st  = STATUS_CFG[epic.status ?? 'open']  || STATUS_CFG.open
              const pri = PRIORITY_CFG[epic.priority ?? 'medium'] || PRIORITY_CFG.medium
              const progress = (epic.task_count ?? 0)>0 ? Math.round((epic.done_tasks||0)/(epic.task_count ?? 0)*100) : 0
              return (
                <button key={epic.id} type="button" style={{...ps,padding:'16px 20px',border:`1px solid ${alpha(epic.color, '30')}`,cursor:'pointer',width:'100%',textAlign:'left',fontFamily:'inherit'}}
                  onClick={()=>setDetailEpic(epic)}>
                  <div style={{display:'flex',alignItems:'flex-start',gap:14}}>
                    <div style={{width:4,height:48,borderRadius:2,background:epic.color,flexShrink:0,marginTop:2}}/>
                    <div className="u-flex1">
                      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:6}}>
                        <span className="u-md-600">{epic.title}</span>
                        <span style={{fontSize: "var(--text-xs)",padding:'2px 8px',borderRadius:20,background:st.bg,color:st.color}}>{st.label}</span>
                        <span style={{fontSize: "var(--text-xs)",color:pri.color}}>⬆ {pri.label}</span>
                      </div>
                      {epic.description&&<div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:8}}>{epic.description}</div>}
                      <div style={{display:'flex',alignItems:'center',gap:20,fontSize: "var(--text-sm)",color:'var(--text-2)'}}>
                        {epic.start_date&&<span>📅 {epic.start_date} → {epic.end_date||t('epics.no_end_date')}</span>}
                        <span>📌 {epic.task_count||0} {t('epics.tasks_count')}</span>
                        {(epic.task_count ?? 0)>0&&<span className="u-success">{progress}% {t('epics.completed_label')}</span>}
                      </div>
                      {(epic.task_count ?? 0)>0&&(
                        <div style={{marginTop:8,height:4,background:'var(--surface-4)',borderRadius:2,overflow:'hidden'}}>
                          <div style={{height:'100%',width:`${progress}%`,background:epic.color,borderRadius:2,transition:'width .3s'}}/>
                        </div>
                      )}
                    </div>
                    {canEdit && <div style={{display:'flex',gap:6,flexShrink:0}}>
                      <button onClick={e=>{e.stopPropagation();setEditEpic(epic);setShowForm(true)}}
                        style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:'var(--radius-sm)',padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>{t('common.edit')}</button>
                      <button onClick={e=>{e.stopPropagation();openConfirmGlobal({message:`${t('common.are_you_sure')} "${epic.title}"?`,onConfirm:()=>deleteEpic(epic.id),danger:true})}}
                        style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:'var(--radius-sm)',padding:'4px 10px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>{t('common.delete')}</button>
                    </div>}
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
      {detailEpic && <EpicDetail epic={detailEpic} projectId={project} canEdit={canEdit} onClose={()=>setDetailEpic(null)} />}
    </PageShell>
  )
}
