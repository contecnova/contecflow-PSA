import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, epicsApi, epicDependenciesApi } from '../services/api'
import type { DependenciaDeEpica, EpicaDelRoadmap, RoadmapDeEpicas } from '../services/api/tipos-proyectos'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import './EpicGanttPage.css'

interface ProjectItem {
  id: string | number
  name?: string
}

/** epics_service.get_roadmap_data. */
type EpicItem = EpicaDelRoadmap
type EpicDependency = DependenciaDeEpica

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const DEP_TYPES = [
  { value:'finish_to_start',  label:'pagina_egantt.fin_inicio',    color:'var(--danger)', symbol:'FS', desc:'pagina_egantt.b_no_empieza_hasta_que_a' },
  { value:'start_to_start',   label:'pagina_egantt.inicio_inicio', color:'var(--warning)', symbol:'SS', desc:'pagina_egantt.b_no_empieza_hasta_que_a_2' },
  { value:'finish_to_finish', label:'pagina_egantt.fin_fin',       color:'var(--accent)', symbol:'FF', desc:'pagina_egantt.b_no_termina_hasta_que_a' },
  { value:'relates_to',       label:'pagina_egantt.relacionada',     color:'var(--text-2)', symbol:'RE', desc:'pagina_egantt.sin_bloqueo_solo_vinculadas' },
]

function daysBetween(a?: string, b?: string) {
  if (!a || !b) return 0
  return Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000))
}

function GanttWithDeps({ epics, deps }: { epics: EpicItem[]; deps: EpicDependency[] }) {
  const t = useAppT()
  const dates = epics.flatMap((e) => [e.start_date, e.end_date].filter((v): v is string => Boolean(v)))
  if (!dates.length) return (
    <div className="egantt-box">
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
    months.push(cur.toLocaleDateString(localeActivo(), {month:'short', year:'2-digit'}))
    cur.setMonth(cur.getMonth() + 1)
  }

  return (
    <div className="u-scroll-x">
      <div className="egantt-box-2">
        {/* Meses */}
        <div className="egantt-row">
          {months.map((m, i) => (
            <div key={i} className="egantt-box-3">{m}</div>
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
            <div key={epic.id} className="egantt-row-2">
              <div className="egantt-row-3">
                <div className="egantt-box-4" style={{ background:epic.color }} />
                {epic.title}
              </div>
              <div className="egantt-card">
                {/* Barra principal */}
                <div className="egantt-row-4" style={{ left:`${left}%`, width:`${w}%`, background:epic.color }}>
                  {w > 8 && <span className="egantt-label">{epic.title}</span>}
                </div>
                {/* Progreso overlay */}
                {prog > 0 && (
                  <div className="egantt-card-2" style={{ left:`${left}%`, width:`${w * prog / 100}%` }} />
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
                      className={`egantt-svg ${dy > 0 ? 'epicgant-sx1' : 'epicgant-sx2'} ${dy < 0 ? 'epicgant-sx3' : 'epicgant-sx4'}`} style={{ left:`${Math.min(fromX,toX)}%`, width:`${Math.abs(toX-fromX) || 2}%`, height:Math.abs(dy) }}
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
              <div className="egantt-box-5">
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
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ epic_id:'', depends_on_id:'', dep_type:'finish_to_start', lag_days:0 })
  const set = (k: 'epic_id' | 'depends_on_id' | 'dep_type' | 'lag_days') => (v: string | number) => setForm((f) => ({...f, [k]: v}))
  const _selType = DEP_TYPES.find(d => d.value === form.dep_type)

  const { mutate, isPending } = useMutation({
    mutationFn: () => epicDependenciesApi.create(form).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['epic-deps', projectId] }); qc.invalidateQueries({ queryKey: ['epic-gantt', projectId] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_egantt.error_al_crear_dependencia'))),
  })

  return (
    <Modal open onClose={onClose} title={t('epicgantt.nueva_dependencia_entre_epicas')}>
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('epicgantt.epica_a')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} style={is} value={form.epic_id} onChange={e => set('epic_id')(e.target.value)}>
              <option value="">{t('epicgantt.selecciona_epica')}</option>
              {epics.map(e => <option key={e.id} value={e.id}>{e.title}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('epicgantt.epica_b_depende_de_a')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} style={is} value={form.depends_on_id} onChange={e => set('depends_on_id')(e.target.value)}>
              <option value="">{t('epicgantt.selecciona_epica')}</option>
              {epics.filter(e => e.id !== form.epic_id).map(e => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label style={ls}>{t('epicgantt.tipo_de_dependencia')}</label>
          <div className="u-stack-6">
            {DEP_TYPES.map(dt => (
              <button key={dt.value} onClick={() => set('dep_type')(dt.value)}
                className="egantt-btn epicgant-sx5" style={{ border:`1px solid ${form.dep_type===dt.value ? alpha(dt.color, '50') : 'var(--surface-4)'}`, background:form.dep_type===dt.value ? alpha(dt.color, '15') : 'transparent' }}>
                <span className="egantt-label-2" style={{ background:alpha(dt.color, '30'), color:dt.color }}>{dt.symbol}</span>
                <div className="u-flex1">
                  <div className={`egantt-box-6 ${form.dep_type===dt.value ? 'epicgant-sx6' : 'epicgant-sx7'}`} style={{ color:form.dep_type===dt.value ? dt.color : 'var(--text-1)' }}>{t(dt.label)}</div>
                  <div className="u-text2-xs">{t(dt.desc)}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('epicgantt.lag_dias_de_retraso_adicional')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" style={{...is, width:120}} value={form.lag_days} min={0}
            onChange={e => set('lag_days')(+e.target.value)} />
        </div>

        <div className="egantt-row-5">
          <Button variant="secondary" onClick={onClose}>{t('pagina_egantt.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.epic_id || !form.depends_on_id} loading={isPending}>
            {isPending ? t('pagina_egantt.creando') : t('pagina_egantt.crear_dependencia')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function EpicGanttPage(): JSX.Element {
  const idCampo = useId()
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
  const { data: roadmap, isLoading: lRoadmap } = useQuery({
    queryKey: ['epic-gantt', project],
    queryFn: () => epicsApi.roadmap(project).then(r => r.data).catch((): RoadmapDeEpicas | null => null),
    enabled: !!project,
  })
  const { data: epicDeps = [], isLoading: lDeps } = useQuery({
    queryKey: ['epic-deps', project],
    queryFn: () => epicDependenciesApi.get(project).then(r => r.data).catch((): EpicDependency[] => []),
    enabled: !!project,
  })

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
          <Button onClick={() => setShowForm(true)}>{t('pagina_egantt.dependencia')}</Button>
        )} showListExport={false} />

      <div style={{...ps, marginBottom:20}}>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('pagina_egantt.proyecto')}</label>
        <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e => setProject(e.target.value)} style={{...is, width:360}}>
          <option value="">{t('epicgantt.selecciona_un_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!project && <EmptyState icon="📊" title={t('epicgantt.selecciona_un_proyecto_2')} description={t('pagina_egantt.elige_un_proyecto_para_ver_el')} />}
      {project && isLoading && <Spinner />}

      {project && !isLoading && epics.length === 0 && (
        <div style={{...ps, textAlign:'center', padding:'48px 24px'}}>
          <div className="u-empty-icon">🎯</div>
          <div className="egantt-box-7">{t('epicgantt.sin_epicas')}</div>
          <div className="u-text2-base-mb20">
            {t('epicgantt.crea_epicas_con_fechas_en_la_seccion')} <strong>{t('epicgantt.epicas')}</strong> {t('epicgantt.para_verlas_en_el_gantt_con_dependencias')}
          </div>
        </div>
      )}

      {project && !isLoading && epics.length > 0 && (
        <div>
          {/* Gantt visual */}
          <div style={ps}>
            <div className="egantt-box-8">
              {t('epicgantt.roadmap_con_dependencias')} {projects.find(p => p.id === project)?.name}
            </div>
            <GanttWithDeps epics={epics} deps={epicDeps} />
          </div>

          {/* Lista de dependencias */}
          <div style={{...ps, marginTop:16}}>
            <div className="u-row-between-mb16">
              <div className="u-md-600">
                {t('pagina_egantt.dependencias')}{epicDeps.length})
              </div>
              <Button onClick={() => setShowForm(true)}>{t('epicgantt.anadir')}</Button>
            </div>
            {epicDeps.length === 0 ? (
              <div className="egantt-box-9">
                {t('epicgantt.sin_dependencias_entre_epicas_las_dependencias_aparecen')}
              </div>
            ) : (
              <div className="u-stack-8">
                {epicDeps.map(dep => {
                  const dt = DEP_TYPES.find(d => d.value === dep.dep_type)
                  return (
                    <div key={dep.id} className="egantt-row-6">
                      <span className="egantt-label-3" style={{ background:alpha(dt?.color, '30'), color:dt?.color }}>
                        {dt?.symbol}
                      </span>
                      <div className="u-flex1">
                        <span className="egantt-label-4">{dep.epic_title}</span>
                        <span className="egantt-label-5">→</span>
                        <span className="egantt-label-6">{dep.depends_on_title}</span>
                        <span className="egantt-label-7">{dt && t(dt.label)}</span>
                        {dep.lag_days > 0 && <span className="egantt-label-8">+{dep.lag_days}d</span>}
                      </div>
                      <button onClick={() => { openConfirmGlobal({ message: t('pagina_egantt.eliminar_dependencia'), onConfirm: () => deleteDep(dep.id), danger: true }) }}
                        className="egantt-btn-2">✕</button>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Leyenda tipos */}
            <div className="egantt-row-7">
              {DEP_TYPES.map(dt => (
                <div key={dt.value} className="egantt-row-8">
                  <span className="egantt-label-9" style={{ background:alpha(dt.color, '30'), color:dt.color }}>{dt.symbol}</span>
                  <span className="u-text2">{t(dt.label)}</span>
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
