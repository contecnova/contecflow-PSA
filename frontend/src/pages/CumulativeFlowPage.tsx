import { CHART } from '../constants/theme'
import { extractErr, fmtDate, fmtNumber } from '../utils/helpers'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { projectsApi, epicsApi } from '../services/api'
import type { FlujoAcumulado } from '../services/api/tipos-proyectos'
import { Button, Spinner, EmptyState, KpiCard, SelectorDePeriodo } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo, formatearTramo } from '../utils/periodo'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, CalendarDays, Camera, CheckCircle2, ListChecks, Percent, TrendingUp } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './CumulativeFlowPage.css'
import { LEYENDA_SM } from '../constants/estilosGrafico'

interface ProjectItem {
  id: string | number
  name?: string
}

/** epics_service.get_cfd_data: una fila por día con `date` y el recuento de cada estado. */
type CfdDataRow = FlujoAcumulado['data'][number]

const STATUS_COLORS: Record<string, string> = {
  todo:        'var(--text-2)',
  in_progress: 'var(--accent)',
  in_review:   'var(--warning)',
  done:        'var(--success)',
  blocked:     'var(--danger)',
}

/** Estados con etiqueta traducida en `cumulative_flow.*`; el resto se muestra tal cual. */
const ESTADOS_TRADUCIDOS = new Set(['todo', 'backlog', 'in_progress', 'in_review', 'review', 'done', 'blocked'])

const getColor = (status: string, idx: number) => {
  if(STATUS_COLORS[status]) return STATUS_COLORS[status]
  const fallbacks = ['var(--purple)','var(--warning)','var(--accent)',CHART.pink,CHART.lime]
  return fallbacks[idx % fallbacks.length]
}

const TOOLTIP_STYLE = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', fontSize: 'var(--text-base)' }
const TICK = { fill: 'var(--text-2)', fontSize: 'var(--text-xs)' }

export default function CumulativeFlowPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [project, setProject] = useState('')
  // Periodo libre (16-11-2026): antes 7/14/30/60/90 propio. Fotos diarias -> sin hora;
  // por semana o mes cada tramo es la última foto del tramo.
  const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA })

  const { data:projects=[] } = useQuery<ProjectItem[]>({queryKey:['projects'],queryFn:()=>projectsApi.list({}).then(r=>Array.isArray(r.data)?(r.data as ProjectItem[]):[]).catch(()=>[])})
  const { data:cfd,isLoading,error } = useQuery({
    queryKey:['cfd',project,periodo.params],
    queryFn:()=>epicsApi.cfd({ project_id: project, ...periodo.params }).then(r=>r.data).catch((e: unknown):FlujoAcumulado|null=>{
      // Los errores de periodo se muestran traducidos; el resto, como antes, sin datos.
      if (codigoDeErrorDePeriodo(e)) throw e
      return null
    }),
    enabled:!!project,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)

  const { mutate:snapshot, isPending:snapping } = useMutation({
    mutationFn: ()=>epicsApi.cfdSnapshot(project).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries({ queryKey: ['cfd',project] }); toast.info(t('cumulative_flow.snapshot_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('cumulative_flow.snapshot_create_error'))),
  })

  const data: CfdDataRow[] = cfd?.data || []
  const statuses: string[] = cfd?.statuses || []
  const etiqueta = (st: string) => ESTADOS_TRADUCIDOS.has(st) ? t(`cumulative_flow.${st}`) : st.replace(/_/g, ' ')
  const colorVar = (st: string) => ({ '--cfd-color': getColor(st, statuses.indexOf(st)) } as CSSProperties)

  // Calcular insights
  const lastDay  = data[data.length-1]
  const totalLast  = lastDay  ? statuses.reduce((s,st)=>s+Number(lastDay[st]||0),0)  : 0
  const doneLast   = Number(lastDay?.done || 0)

  const snapshotButton = (
    <Button icon={<Camera size={14} />} onClick={()=>snapshot()} disabled={!project||snapping} loading={snapping}>
      {snapping ? t('cumulative_flow.saving') : t('cumulative_flow.snapshot_today')}
    </Button>
  )

  return (
    <PageShell>
      <PageHeader icon={<TrendingUp size={18} />} title={t('nav.cumulative_flow')} subtitle={t('cumulative_flow.subtitle')}
        showListExport={Boolean(project && data.length > 0)} actions={snapshotButton}/>
      <div className="ds-page">

      {/* Filtros */}
      <div className="cfd-panel">
        <div className="cfd-controls">
          <div className="cfd-controls__project">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cfd-label">{t('cumulative_flow.project')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e=>setProject(e.target.value)} className="cfd-input">
              <option value="">{t('cumulative_flow.select_project')}</option>
              {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <span className="cfd-label">{t('cumulative_flow.period')}</span>
            <SelectorDePeriodo {...periodo.selector} />
          </div>
        </div>
        <div className="cfd-help">{t('cumulative_flow.snapshot_help')}</div>
      </div>

      {!project && <EmptyState icon={<TrendingUp size={28} />} title={t('cumulative_flow.empty_title')} description={t('cumulative_flow.empty_desc')}/>}
      {project&&isLoading&&<Spinner/>}

      {project&&errorDePeriodo&&(
        <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
      )}

      {project&&!isLoading&&!errorDePeriodo&&data.length===0&&(
        <EmptyState icon={<Camera size={28} />} title={t('cumulative_flow.no_history')}
          description={t('cumulative_flow.no_history_desc')} action={snapshotButton} />
      )}

      {project&&data.length>0&&(
        <div>
          {/* KPIs */}
          <div className="ds-grid-stats cfd-kpis">
            <KpiCard label={t('cumulative_flow.kpi_completed_today')} value={fmtNumber(doneLast, 0)} icon={<CheckCircle2 size={14} />} />
            <KpiCard label={t('cumulative_flow.kpi_total_tasks')} value={fmtNumber(totalLast, 0)} icon={<ListChecks size={14} />} />
            <KpiCard label={t('cumulative_flow.kpi_days_with_data')} value={fmtNumber(data.length, 0)} icon={<CalendarDays size={14} />} />
            <KpiCard label={t('cumulative_flow.kpi_completed_pct')} value={`${fmtNumber(totalLast>0?Math.round(doneLast/totalLast*100):0, 0)}%`} accent={totalLast>0} icon={<Percent size={14} />} />
          </div>

          {/* Gráfico CFD */}
          <div className="cfd-panel">
            <h2 className="cfd-title">{t('cumulative_flow.title')}</h2>
            <div role="img" aria-label={t('cumulative_flow.subtitle')}>
              <ResponsiveContainer width="100%" height={350}>
                <AreaChart data={data} margin={{top:10,right:20,left:0,bottom:0}}>
                  <defs>
                    {statuses.map((st,i)=>(
                      <linearGradient key={st} id={`grad-${st}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={getColor(st,i)} stopOpacity={0.3}/>
                        <stop offset="95%" stopColor={getColor(st,i)} stopOpacity={0.05}/>
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)"/>
                  <XAxis dataKey="t" tick={TICK} tickFormatter={(v) => formatearTramo(String(v), periodo.granularidad)} interval="preserveStartEnd"/>
                  <YAxis tick={TICK}/>
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => formatearTramo(String(v), periodo.granularidad, true)}/>
                  <Legend wrapperStyle={LEYENDA_SM}/>
                  {statuses.map((st,i)=>(
                    <Area key={st} type="monotone" dataKey={st}
                      name={etiqueta(st)}
                      stackId="1"
                      stroke={getColor(st,i)}
                      fill={`url(#grad-${st})`}
                      strokeWidth={2}/>
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Tabla de datos */}
          <div className="cfd-panel cfd-panel--table">
            <h2 className="cfd-title cfd-title--table">{t('cumulative_flow.table_title')}</h2>
            <div className="u-scroll-x">
              <table className="u-table-sm cfd-table">
                <thead>
                  <tr className="u-border-b">
                    <th scope="col" className="cfd-col-date">{t('cumulative_flow.col_date')}</th>
                    {statuses.map(st=>(
                      <th scope="col" key={st} className="cfd-status" style={colorVar(st)}>{etiqueta(st)}</th>
                    ))}
                    <th scope="col">{t('cumulative_flow.col_total')}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data].reverse().slice(0,14).map((row)=>{
                    const total = statuses.reduce((s,st)=>s+Number(row[st]||0),0)
                    return (
                      <tr key={row.date}>
                        <td className="cfd-col-date">{fmtDate(row.date)}</td>
                        {statuses.map(st=>(
                          <td key={st} className="cfd-status" style={colorVar(st)}>{fmtNumber(Number(row[st]||0), 0)}</td>
                        ))}
                        <td className="cfd-col-total">{fmtNumber(total, 0)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      </div>
    </PageShell>
  )
}
