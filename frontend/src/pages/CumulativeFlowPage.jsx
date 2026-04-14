import { CHART } from '../constants/theme'
import { extractErr } from '../utils/helpers'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const STATUS_COLORS = {
  todo:        'var(--text-2)',
  in_progress: 'var(--accent)',
  in_review:   'var(--warning)',
  done:        'var(--success)',
  blocked:     'var(--danger)',
}

const getColor = (status, idx) => {
  if(STATUS_COLORS[status]) return STATUS_COLORS[status]
  const fallbacks = ['var(--purple)','var(--warning)','var(--accent)',CHART.pink,CHART.lime]
  return fallbacks[idx % fallbacks.length]
}

export default function CumulativeFlowPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [project, setProject] = useState('')
  const [days,    setDays]    = useState(30)

  const { data:projects=[] } = useQuery({queryKey:['projects'],queryFn:()=>api.get('/projects').then(r=>Array.isArray(r.data)?r.data:[]).catch(()=>[])})
  const { data:cfd,isLoading } = useQuery({
    queryKey:['cfd',project,days],
    queryFn:()=>api.get(`cfd?project_id=${project}&days=${days}`).then(r=>r.data).catch(()=>null),
    enabled:!!project,
  })

  const { mutate:snapshot, isPending:snapping } = useMutation({
    mutationFn: ()=>api.post(`cfd/snapshot?project_id=${project}`).then(r=>r.data),
    onSuccess: (d)=>{ qc.invalidateQueries(['cfd',project,days]); toast.info(`Snapshot creado: ${d.states} estados, ${new Date().toLocaleDateString()}`) },
    onError: e => toast.error(extractErr(e, 'Error al crear snapshot')),
  })

  const data    = cfd?.data      || []
  const statuses= cfd?.statuses  || []

  // Calcular insights
  const lastDay  = data[data.length-1]
  const firstDay = data[0]
  const totalLast  = lastDay  ? statuses.reduce((s,st)=>s+(lastDay[st]||0),0)  : 0
  const _totalFirst = firstDay ? statuses.reduce((s,st)=>s+(firstDay[st]||0),0) : 0
  const doneLast   = lastDay?.done || 0

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('cumulative_flow.title')} subtitle="Cumulative Flow Diagram — evolución de tareas por estado para detectar cuellos de botella"/>

      {/* Controles */}
      <div style={{...ps,marginBottom:20}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr auto auto',gap:12,alignItems:'flex-end'}}>
          <div>
            <label style={ls}>Proyecto</label>
            <select value={project} onChange={e=>setProject(e.target.value)} style={is}>
              <option value="">Selecciona un proyecto...</option>
              {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Período</label>
            <select value={days} onChange={e=>setDays(+e.target.value)} style={{...is,width:140}}>
              <option value={7}>7 días</option>
              <option value={14}>14 días</option>
              <option value={30}>30 días</option>
              <option value={60}>60 días</option>
              <option value={90}>90 días</option>
            </select>
          </div>
          <Button onClick={()=>snapshot()} disabled={!project||snapping}>
            {snapping?'Guardando...':'📸 Snapshot hoy'}
          </Button>
        </div>
        <div style={{marginTop:10,fontSize:12,color:'var(--text-3)',lineHeight:1.6}}>
          El snapshot captura el estado actual del proyecto. Ejecútalo diariamente (o configura un cron en <code style={{color:'var(--text-2)'}}>POST cfd/snapshot?project_id=...</code>) para acumular datos.
        </div>
      </div>

      {!project && <EmptyState icon="📊" title="Selecciona un proyecto" description="El CFD muestra la evolución de tareas por estado a lo largo del tiempo"/>}
      {project&&isLoading&&<Spinner/>}

      {project&&!isLoading&&data.length===0&&(
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize:48,marginBottom:16}}>📸</div>
          <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>Sin datos históricos</div>
          <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>Crea el primer snapshot para empezar a acumular datos. Repite diariamente para ver la evolución.</div>
          <Button onClick={()=>snapshot()} disabled={snapping}>{snapping?'Creando...':'Crear primer snapshot'}</Button>
        </div>
      )}

      {project&&data.length>0&&(
        <div>
          {/* KPIs */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12,marginBottom:20}}>
            <div style={ps}>
              <div style={{fontSize:22,fontWeight:700,color:'var(--success)'}}>{doneLast}</div>
              <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>Completadas hoy</div>
            </div>
            <div style={ps}>
              <div style={{fontSize:22,fontWeight:700}}>{totalLast}</div>
              <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>Total tareas</div>
            </div>
            <div style={ps}>
              <div style={{fontSize:22,fontWeight:700,color:'var(--accent)'}}>{data.length}</div>
              <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>Días con datos</div>
            </div>
            <div style={ps}>
              <div style={{fontSize:22,fontWeight:700,color:totalLast>0?'var(--success)':'var(--text-2)'}}>
                {totalLast>0?Math.round(doneLast/totalLast*100):0}%
              </div>
              <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>% completado</div>
            </div>
          </div>

          {/* Gráfico CFD */}
          <div style={ps}>
            <div style={{fontSize:14,fontWeight:600,marginBottom:20}}>
              Flujo acumulado — últimos {days} días
            </div>
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
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45"/>
                <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:11}}
                  tickFormatter={d=>d.slice(5)} interval="preserveStartEnd"/>
                <YAxis tick={{fill:'var(--text-2)',fontSize:11}}/>
                <Tooltip contentStyle={{background:'var(--surface-2)',border:'1px solid #1e2d45',borderRadius:8,color:'var(--text-1)',fontSize:12}}/>
                <Legend wrapperStyle={{fontSize:12,color:'var(--text-2)'}}/>
                {statuses.map((st,i)=>(
                  <Area key={st} type="monotone" dataKey={st}
                    name={st.replace(/_/g,' ')}
                    stackId="1"
                    stroke={getColor(st,i)}
                    fill={`url(#grad-${st})`}
                    strokeWidth={2}/>
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Tabla de datos */}
          <div style={{...ps,marginTop:16}}>
            <div style={{fontSize:13,fontWeight:600,marginBottom:12}}>Datos por día</div>
            <div style={{overflowX:'auto'}}>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
                <thead>
                  <tr style={{borderBottom:'1px solid #1e2d45'}}>
                    <th style={{textAlign:'left',padding:'8px 12px',color:'var(--text-2)',fontWeight:600}}>Fecha</th>
                    {statuses.map(st=>(
                      <th key={st} style={{textAlign:'center',padding:'8px 12px',color:getColor(st,statuses.indexOf(st)),fontWeight:600}}>{st.replace(/_/g,' ')}</th>
                    ))}
                    <th style={{textAlign:'center',padding:'8px 12px',color:'var(--text-2)',fontWeight:600}}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data].reverse().slice(0,14).map((row,i)=>{
                    const total = statuses.reduce((s,st)=>s+(row[st]||0),0)
                    return (
                      <tr key={row.date} style={{borderBottom:'1px solid #1a2640',background:i%2===0?'transparent':'rgba(255,255,255,0.03)'}}>
                        <td style={{padding:'7px 12px',color:'var(--text-1)'}}>{row.date}</td>
                        {statuses.map(st=>(
                          <td key={st} style={{padding:'7px 12px',textAlign:'center',color:getColor(st,statuses.indexOf(st))}}>{row[st]||0}</td>
                        ))}
                        <td style={{padding:'7px 12px',textAlign:'center',fontWeight:600}}>{total}</td>
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
  )
}
