import { CHART_COLORS_EXTENDED, COLOR, alpha } from '../constants/theme'
import { extractErr, localeActivo, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { epicsApi, tasksApi } from '../services/api'
import { useListaDeProyectos } from '../hooks/useListas'
import type { EpicaDelRoadmap, EpicaSerializada } from '../services/api/tipos-proyectos'
import { useAuth } from '../context/AuthContext'
import { Button, Spinner, EmptyState, Modal, KpiCard, Tabs, IconButton, Pulsable, Select, useErroresDeCampo, Input, Textarea, EstadoDeError } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarDays, CalendarRange, FolderKanban, Layers, List, ListChecks, Map as MapIcon, Pencil, Plus, Target, Trash2 } from 'lucide-react'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './EpicsPage.css'

// EpicIn: estado y prioridad son texto (la interfaz ofrece los de STATUS_CFG y PRIORITY_CFG).
type EpicStatus = EpicaSerializada['status']
type EpicPriority = EpicaSerializada['priority']

/** epics_service.serialize_epic; `progress` solo llega en el roadmap (get_roadmap_data). */
type EpicItem = EpicaSerializada & { progress?: EpicaDelRoadmap['progress'] }

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


const COLORS = CHART_COLORS_EXTENDED

const daysBetween = (a?: string, b?: string) => {
  if(!a||!b) return 0
  return Math.max(0, Math.round((new Date(b).getTime()-new Date(a).getTime())/(1000*60*60*24)))
}

// 19-11-2026: estados y prioridades de épica en UN sitio (antes, copiados en el
// formulario y en la página).
function cfgDeEpicas(t: (k: string) => string) {
  const STATUS_CFG = {
    open:        { label: t('epics.status_open'),        color:'var(--text-2)', bg:'color-mix(in srgb, var(--text-2) 9%, transparent)' },
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
  return { STATUS_CFG, PRIORITY_CFG }
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
  const set = <K extends keyof EpicFormState>(k: K) => (v: EpicFormState[K]) => { campos.limpiar(k); setForm((f) => ({ ...f, [k]: v })) }

  const { STATUS_CFG, PRIORITY_CFG } = cfgDeEpicas(t)

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: EpicFormState) => isEdit
      ? epicsApi.update(epic.id, d).then(r=>r.data)
      : epicsApi.createForProject(projectId, d).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['epics',projectId] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('pagina_epics.error_al_guardar'))) },
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('epics.edit_epic') : t('epics.new_epic')}>
      <div className="u-stack-14">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="epics-page-e13">{t('epics.title_label')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e=>set('title')(e.target.value)} placeholder={t('epics.epic_name')} inputClassName="epics-page-e14" />{msg('title')}</div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="epics-page-e13">{t('common.description')}</label><Textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e=>set('description')(e.target.value)} inputClassName="epics-page-e1" />{msg('description')}</div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="epics-page-e13">{t('common.status')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} className="epics-page-e14" value={form.status} onChange={e=>set('status')(e.target.value)}>
              {Object.entries(STATUS_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </Select>{msg('status')}
          </div>
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="epics-page-e13">{t('common.priority')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} className="epics-page-e14" value={form.priority} onChange={e=>set('priority')(e.target.value)}>
              {Object.entries(PRIORITY_CFG).map(([v,c])=><option key={v} value={v}>{c.label}</option>)}
            </Select>{msg('priority')}
          </div>
        </div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="epics-page-e13">{t('epics.start_date')}</label><DateInput id={`${idCampo}-5`} className="epics-page-e14" value={form.start_date} onChange={e=>set('start_date')(e.target.value)}/>{msg('start_date')}</div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="epics-page-e13">{t('epics.end_date')}</label><DateInput id={`${idCampo}-6`} className="epics-page-e14" value={form.end_date} onChange={e=>set('end_date')(e.target.value)}/>{msg('end_date')}</div>
        </div>
        <div><label className="epics-page-e13">{t('epics.color_label')}</label>
          <div className="u-wrap-8">
            {COLORS.map(c=>(
              <Pulsable type="button" key={c} aria-pressed={form.color===c} onClick={()=>set('color')(c)} aria-label={`${t('epics.color_label')} ${c}`}
                className={`epics-btn epicspag-sx1 ${form.color===c ? 'epicspag-sx2' : 'epicspag-sx3'} epics-page-e2`} style={{ '--epics-page-background': c } as CSSProperties}><span aria-hidden="true" /></Pulsable>
            ))}
            <input type="color" aria-label={t('epics.color_label')} value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR.purple} onChange={e=>set('color')(e.target.value)}
              className="epics-input"/>
          </div>
        </div>
        <div className="epics-row">
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
  const ficha = useQuery({ queryKey: ['epic', epic.id], queryFn: () => epicsApi.get(epic.id).then(r => r.data) })
  const tareas = useQuery({ queryKey: ['tasks', projectId, 'epic'], enabled: canEdit,
    queryFn: () => tasksApi.list({ project_id: projectId, page_size: FULL_LIST_SIZE }).then(r => r.data) })
  const enlazadas = ficha.data?.tasks ?? []
  const libres = (tareas.data ?? []).filter(x => !enlazadas.some(e => e.id === x.id))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['epic', epic.id] }); qc.invalidateQueries({ queryKey: ['epics'] }); qc.invalidateQueries({ queryKey: ['roadmap'] }) }
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
            <div key={x.id} className="epics-row-2">
              <span className="epics-label">{x.title}</span>
              <span className={`u-xs ${x.status === 'done' ? 'epicspag-sx4' : 'epicspag-sx5'}`}>{etiquetaCodigo(t, 'estado', x.status)}</span>
              {canEdit && <Button size="xs" variant="ghost" onClick={() => openConfirmGlobal({
                // 23-11-2026: desvincular una tarea de la épica cambia su avance: pide confirmación.
                title: t('epics.confirmar_quitar_titulo'), message: t('epics.confirmar_quitar_msg', { tarea: x.title ?? '' }),
                confirmLabel: t('epics.quitar'), danger: true, onConfirm: () => { void enlazar(x.id, true) },
              })}>{t('epics.quitar')}</Button>}
            </div>))}
        {canEdit && (
          <div className="u-wrap-8">
            <Select suelto placeholder={false} aria-label={t('epics.anadir_tarea')} value={elegida} onChange={e => setElegida(e.target.value)}
              className="epics-input-2">
              <option value="">{t('epics.anadir_tarea')}</option>
              {libres.map(x => <option key={x.id} value={x.id}>{x.title}</option>)}
            </Select>
            <Button size="sm" disabled={!elegida} onClick={() => enlazar(elegida)}>{t('epics.enlazar')}</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}

function RoadmapView({ epics, t }: { epics: EpicItem[]; t: (key: string, params?: Record<string, string | number>) => string }) {
  if(!epics.length) return <EmptyState icon={<MapIcon size={28} />} title={t('epics.no_epics')} description={t('epics.no_epics_desc')}/>

  const datesWithValues = epics.flatMap((e) => [e.start_date, e.end_date].filter((v): v is string => Boolean(v)))
  if(!datesWithValues.length) return <EmptyState icon={<CalendarRange size={28} />} title={t('epics.no_epics_desc')}/>

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
      <div className="epics-box-2">
        {/* Cabecera meses */}
        <div className="epics-row-3">
          {months.map((m,i)=>(
            <div key={i} className="epics-box-3">{m}</div>
          ))}
        </div>
        {/* Épicas */}
        {epics.map(epic=>{
          const left  = epic.start_date ? pct(epic.start_date) : 0
          const w     = epic.start_date && epic.end_date ? width(epic.start_date, epic.end_date) : 20
          return (
            <div key={epic.id} className="epics-row-4">
              <div className="epics-box-4">
                {epic.title}
              </div>
              <div className="epics-card">
                <div className="epics-row-5 epics-page-e3" style={{ '--epics-page-left': `${left}%`, '--epics-page-width': `${w}%`, '--epics-page-background': epic.color||'var(--purple)' } as CSSProperties}>
                  {w>8&&<span className="epics-label-2">{epic.title}</span>}
                </div>
                {(epic.progress ?? 0)>0&&(
                  <div className="epics-card-2 epics-page-e4" style={{ '--epics-page-left': `${left}%`, '--epics-page-width': `${w*(epic.progress ?? 0)/100}%` } as CSSProperties}/>
                )}
              </div>
              <div className="epics-box-5">{epic.progress||0}%</div>
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
  const { puede } = useAuth()
  const canEdit = puede('proyectos.gestionar')

  const { STATUS_CFG, PRIORITY_CFG } = cfgDeEpicas(t)

  // 23-11-2026 (04 A8 / M6): lista compartida de proyectos y sin `.catch` tragados (avisa el onError global;
  // la lista de épicas, además, pinta el estado de error con reintento).
  const { data:projects=[] } = useListaDeProyectos()
  const { data:epics=[],isLoading,error:errorEpicas,refetch:refetchEpicas } = useQuery({
    queryKey:['epics',project],
    queryFn:()=>epicsApi.list(project).then(r=>r.data),
    enabled:!!project,
  })
  const { data:roadmap } = useQuery({
    queryKey:['roadmap',project],
    queryFn:()=>epicsApi.roadmap(project).then(r=>r.data),
    // También en la lista: el avance (tareas hechas) solo lo calcula el roadmap.
    enabled:!!project,
  })

  const { mutate:deleteEpic } = useMutation({
    mutationFn: (id: string | number) => epicsApi.delete(id),
    onSuccess:()=>qc.invalidateQueries({ queryKey: ['epics',project] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const roadmapEpics = roadmap?.epics || epics
  const avancePorEpica = new Map((roadmap?.epics ?? []).map(e => [e.id, e]))

  return (
    <PageShell>
      <PageHeader icon={<Layers size={18} />} title={t('nav.epics')} subtitle={t('epics.subtitle')}
        actions={project && canEdit ? (
          <Button icon={<Plus size={14} />} onClick={()=>{setEditEpic(null);setShowForm(true)}}>{t('epics.new_epic')}</Button>
        ) : undefined}
        showListExport={view==='list' && epics.length > 0}
        exportTargetSelector='[data-export-table="epics-list"]'
        exportFilePrefix='epics'
      />

      {/* Selector proyecto */}
      <div className="ds-toolbar epics-filtros">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="u-sr-only">{t('epics.project_label')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-1`} value={project} onChange={e=>setProject(e.target.value)} className="ds-input epics-proyecto">
          <option value="">{t('epics.select_project_placeholder')}</option>
          {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </div>

      {project && epics.length > 0 && (
        <Tabs
          items={[
            { id: 'list', label: t('epics.list_view'), icon: <List size={14} /> },
            { id: 'roadmap', label: t('epics.roadmap'), icon: <MapIcon size={14} /> },
          ]}
          active={view}
          onChange={(id) => setView(id as 'list' | 'roadmap')}
          className="epics-tabs"
        />
      )}

      {!project && <EmptyState icon={<FolderKanban size={28} />} title={t('epics.no_project_title')} description={t('epics.no_project_desc')}/>}
      {project&&isLoading&&<Spinner/>}

      {project&&errorEpicas&&<EstadoDeError error={errorEpicas} onReintentar={()=>{ void refetchEpicas() }}/>}

      {project&&!isLoading&&!errorEpicas&&epics.length===0&&(
        <EmptyState icon={<Target size={28} />} title={t('epics.no_epics')} description={t('epics.no_epics_desc')}
          action={canEdit ? <Button icon={<Plus size={14} />} onClick={()=>{setEditEpic(null);setShowForm(true)}}>{t('epics.new_epic')}</Button> : undefined} />
      )}

      {project&&epics.length>0&&view==='roadmap'&&(
        <div className="epics-page-e15">
          <div className="epics-box-7">{t('epics.roadmap_title')} — {projects.find(p=>p.id===project)?.name}</div>
          <RoadmapView epics={roadmapEpics} t={t}/>
        </div>
      )}

      {project&&epics.length>0&&view==='list'&&(
        <div>
          {/* Resumen */}
          <div className="ds-grid-stats epics-kpis">
            {Object.entries(STATUS_CFG).map(([s,c])=>{
              const cnt = epics.filter(e=>e.status===s).length
              return (
                <KpiCard key={s} label={c.label} value={cnt} accent={s === 'in_progress' && cnt > 0} />
              )
            })}
          </div>

          {/* Lista de épicas */}
          <div data-export-table="epics-list" className="u-stack-10">
            {epics.map(epic=>{
              const st  = STATUS_CFG[epic.status ?? 'open']  || STATUS_CFG.open
              const pri = PRIORITY_CFG[epic.priority ?? 'medium'] || PRIORITY_CFG.medium
              // La lista no trae `done_tasks` (antes salía siempre 0 %): el avance viene del roadmap.
              const progress = avancePorEpica.get(epic.id)?.progress ?? 0
              return (
                <div key={epic.id} role="button" tabIndex={0} className="epics-page-e12" style={{ '--epics-page-border': `1px solid ${alpha(epic.color, '30')}` } as CSSProperties}
                  onClick={()=>setDetailEpic(epic)}
                  onKeyDown={e=>{ if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setDetailEpic(epic) } }}>
                  <div className="epics-row-6">
                    <div className="epics-box-9 epics-page-e2" style={{ '--epics-page-background': epic.color } as CSSProperties}/>
                    <div className="u-flex1">
                      <div className="epics-row-7">
                        <span className="u-md-600">{epic.title}</span>
                        <span className="epics-label-3 epics-page-e10" style={{ '--epics-page-background': st.bg, '--epics-page-color': st.color } as CSSProperties}>{st.label}</span>
                        <span className="u-xs epics-page-e9" style={{ '--epics-page-color': pri.color } as CSSProperties}>{pri.label}</span>
                      </div>
                      {epic.description&&<div className="epics-box-10">{epic.description}</div>}
                      <div className="epics-row-8">
                        {epic.start_date&&<span className="epics-dato"><CalendarDays size={13} aria-hidden /> {fmtDate(epic.start_date)} – {epic.end_date ? fmtDate(epic.end_date) : t('epics.no_end_date')}</span>}
                        <span className="epics-dato"><ListChecks size={13} aria-hidden /> {epic.task_count||0} {t('epics.tasks_count')}</span>
                        {(epic.task_count ?? 0)>0&&<span className="u-success">{progress}% {t('epics.completed_label')}</span>}
                      </div>
                      {(epic.task_count ?? 0)>0&&(
                        <div className="epics-card-3">
                          <div className="epics-box-11 epics-page-e11" style={{ '--epics-page-width': `${progress}%`, '--epics-page-background': epic.color } as CSSProperties}/>
                        </div>
                      )}
                    </div>
                    {canEdit && <div className="epics-row-9">
                      <IconButton variante="caja" ariaLabel={t('common.edit')} onClick={e=>{e.stopPropagation();setEditEpic(epic);setShowForm(true)}}><Pencil size={14} aria-hidden /></IconButton>
                      <IconButton variante="caja" tono="peligro" ariaLabel={t('common.delete')} onClick={e=>{e.stopPropagation();openConfirmGlobal({message:`${t('common.are_you_sure')} "${epic.title}"?`,onConfirm:()=>deleteEpic(epic.id),danger:true})}}><Trash2 size={14} aria-hidden /></IconButton>
                    </div>}
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
      {detailEpic && <EpicDetail epic={detailEpic} projectId={project} canEdit={canEdit} onClose={()=>setDetailEpic(null)} />}
    </PageShell>
  )
}
