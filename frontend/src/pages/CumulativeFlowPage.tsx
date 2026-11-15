import { CHART } from '../constants/theme'
import { extractErr, fmtDate, fmtNumber, formateadorDeFecha } from '../utils/helpers'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { projectsApi, epicsApi } from '../services/api'
import type { FlujoAcumulado } from '../services/api/tipos-proyectos'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './CumulativeFlowPage.css'

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

const PERIODOS = [7, 14, 30, 60, 90]

const getColor = (status: string, idx: number) => {
  if(STATUS_COLORS[status]) return STATUS_COLORS[status]
  const fallbacks = ['var(--purple)','var(--warning)','var(--accent)',CHART.pink,CHART.lime]
  return fallbacks[idx % fallbacks.length]
}

/** Eje X: día y mes en el formato del idioma activo. */
const fmtDiaMes = (d: string) => {
  const f = new Date(d)
  return Number.isNaN(f.getTime()) ? d : formateadorDeFecha({ day: '2-digit', month: '2-digit' }).format(f)
}

const TOOLTIP_STYLE = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', fontSize: 'var(--text-base)' }
const TICK = { fill: 'var(--text-2)', fontSize: 'var(--text-xs)' }

export default function CumulativeFlowPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [project, setProject] = useState('')
  const [days,    setDays]    = useState(30)

  const { data:projects=[] } = useQuery<ProjectItem[]>({queryKey:['projects'],queryFn:()=>projectsApi.list({}).then(r=>Array.isArray(r.data)?(r.data as ProjectItem[]):[]).catch(()=>[])})
  const { data:cfd,isLoading } = useQuery({
    queryKey:['cfd',project,days],
    queryFn:()=>epicsApi.cfd({ project_id: project, days }).then(r=>r.data).catch(():FlujoAcumulado|null=>null),
    enabled:!!project,
  })

  const { mutate:snapshot, isPending:snapping } = useMutation({
    mutationFn: ()=>epicsApi.cfdSnapshot(project).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries({ queryKey: ['cfd',project,days] }); toast.info(t('cumulative_flow.snapshot_created')) },
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

  return (
    <PageShell>
      <PageHeader icon={<TrendingUp size={18} />} title={t('cumulative_flow.title')} subtitle={t('cumulative_flow.subtitle')} showListExport={Boolean(project && data.length > 0)}/>

      {/* Controles */}
      <div className="cfd-panel cfd-panel--controls">
        <div className="cfd-controls">
          <div className="cfd-controls__project">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cfd-label">{t('cumulative_flow.project')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={project} onChange={e=>setProject(e.target.value)} className="cfd-input">
              <option value="">{t('cumulative_flow.select_project')}</option>
              {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cfd-label">{t('cumulative_flow.period')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={days} onChange={e=>setDays(+e.target.value)} className="cfd-input cfd-input--days">
              {PERIODOS.map(n => <option key={n} value={n}>{t('cumulative_flow.days_n', { count: n })}</option>)}
            </select>
          </div>
          <Button onClick={()=>snapshot()} disabled={!project||snapping}>
            {snapping ? t('cumulative_flow.saving') : <><span aria-hidden="true">📸 </span>{t('cumulative_flow.snapshot_today')}</>}
          </Button>
        </div>
        <div className="cfd-help">
          {t('cumulative_flow.snapshot_help')} (<code>POST /epics/cfd/snapshot?project_id=...</code>)
        </div>
      </div>

      {!project && <EmptyState icon="📊" title={t('cumulative_flow.empty_title')} description={t('cumulative_flow.empty_desc')}/>}
      {project&&isLoading&&<Spinner/>}

      {project&&!isLoading&&data.length===0&&(
        <div className="cfd-panel cfd-panel--empty">
          <div className="u-empty-icon" aria-hidden="true">📸</div>
          <div className="cfd-empty-title">{t('cumulative_flow.no_history')}</div>
          <div className="u-text2-base-mb20">{t('cumulative_flow.no_history_desc')}</div>
          <Button onClick={()=>snapshot()} disabled={snapping}>{snapping ? t('cumulative_flow.creating') : t('cumulative_flow.create_first_snapshot')}</Button>
        </div>
      )}

      {project&&data.length>0&&(
        <div>
          {/* KPIs */}
          <div className="cfd-kpis">
            <div className="cfd-panel">
              <div className="cfd-kpi__value cfd-kpi__value--success">{fmtNumber(doneLast, 0)}</div>
              <div className="cfd-kpi__label">{t('cumulative_flow.kpi_completed_today')}</div>
            </div>
            <div className="cfd-panel">
              <div className="cfd-kpi__value">{fmtNumber(totalLast, 0)}</div>
              <div className="cfd-kpi__label">{t('cumulative_flow.kpi_total_tasks')}</div>
            </div>
            <div className="cfd-panel">
              <div className="cfd-kpi__value cfd-kpi__value--accent">{fmtNumber(data.length, 0)}</div>
              <div className="cfd-kpi__label">{t('cumulative_flow.kpi_days_with_data')}</div>
            </div>
            <div className="cfd-panel">
              <div className={`cfd-kpi__value ${totalLast>0 ? 'cfd-kpi__value--success' : 'cfd-kpi__value--muted'}`}>
                {fmtNumber(totalLast>0?Math.round(doneLast/totalLast*100):0, 0)}%
              </div>
              <div className="cfd-kpi__label">{t('cumulative_flow.kpi_completed_pct')}</div>
            </div>
          </div>

          {/* Gráfico CFD */}
          <div className="cfd-panel">
            <h2 className="cfd-title">{t('cumulative_flow.chart_title_n', { count: days })}</h2>
            <div role="img" aria-label={t('cumulative_flow.chart_aria', { count: days })}>
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
                  <XAxis dataKey="date" tick={TICK} tickFormatter={fmtDiaMes} interval="preserveStartEnd"/>
                  <YAxis tick={TICK}/>
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(d) => fmtDate(String(d))}/>
                  <Legend wrapperStyle={{fontSize: 'var(--text-sm)',color:'var(--text-2)'}}/>
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
    </PageShell>
  )
}
