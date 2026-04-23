/**
 * ScenariosPage — Scenario planning / What-if capacity
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const card = { background:'var(--color-background-primary)', border:'.5px solid var(--color-border-tertiary)', borderRadius:12 }
const fs = { width:'100%', background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'9px 12px', color:'var(--color-text-primary)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--color-text-secondary)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }

export default function ScenariosPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name:'', description:'', horizon_weeks:12, projects:[] })
  const [newProject, setNewProject] = useState({ name:'', start_date:'', end_date:'', total_hours:0 })

  const { data: scenarios = [], isLoading } = useQuery({ queryKey:['scenarios'], queryFn:()=>api.get('/scenarios').then(r=>r.data) })
  const { data: detail } = useQuery({ queryKey:['scenario-detail', selected], queryFn:()=>api.get(`/scenarios/${selected}`).then(r=>r.data), enabled:!!selected })

  const { mutate: create, isPending:creating } = useMutation({
    mutationFn: d => api.post('/scenarios', d),
    onSuccess: () => { qc.invalidateQueries(['scenarios']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: compute, isPending:computing } = useMutation({
    mutationFn: id => api.post(`/scenarios/${id}/compute`).then(r=>r.data),
    onSuccess: () => qc.invalidateQueries(['scenario-detail', selected]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/scenarios/${id}`),
    onSuccess: () => { setSelected(null); qc.invalidateQueries(['scenarios']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const _RISK_CFG = { low:{ c:'var(--color-text-success)', b:'var(--color-background-success)', l:'Viable' }, medium:{ c:'var(--color-text-warning)', b:'var(--color-background-warning)', l:'Riesgo medio' }, high:{ c:'var(--color-text-danger)', b:'var(--color-background-danger)', l:'Inviable' } }

  const results = detail?.results

  return (
    <div style={{ padding:32 }}>
      <PageHeader title={t('scenarios.title')} subtitle={t('scenarios.subtitle')} />
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:20 }}>
        <Button onClick={()=>setShowCreate(true)}>+ Nuevo escenario</Button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'340px 1fr', gap:20 }}>
        <div>
          {isLoading ? <Spinner /> : scenarios.length === 0 ? (
            <EmptyState icon="🔮" title="Sin escenarios" description="Crea un escenario para simular el impacto en capacidad" />
          ) : scenarios.map(s => (
            <button key={s.id} type="button" onClick={()=>setSelected(s.id)}
              style={{ ...card, padding:'14px 18px', marginBottom:10, cursor:'pointer', border: selected===s.id ? '.5px solid var(--color-border-info)' : '.5px solid var(--color-border-tertiary)', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
              <div style={{ fontSize:13, fontWeight:500, marginBottom:4 }}>{s.name}</div>
              <div style={{ fontSize:11, color:'var(--color-text-secondary)', marginBottom:6 }}>{s.project_count} proyectos · {s.horizon_weeks} semanas</div>
              <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background: s.status==='computed'?'var(--color-background-success)':'var(--color-background-secondary)', color: s.status==='computed'?'var(--color-text-success)':'var(--color-text-secondary)' }}>{s.status}</span>
                <span style={{ fontSize:11, color:'var(--color-text-tertiary)' }}>{s.created_at}</span>
              </div>
            </button>
          ))}
        </div>

        <div>
          {!selected ? (
            <div style={{ ...card, padding:'48px', textAlign:'center', color:'var(--color-text-tertiary)' }}>
              <div style={{ fontSize:40, marginBottom:12 }}>🔮</div>
              <div style={{ fontSize:14, fontWeight:500, marginBottom:6 }}>Selecciona un escenario</div>
              <div style={{ fontSize:12 }}>O crea uno nuevo para simular el impacto en capacidad</div>
            </div>
          ) : !detail ? <Spinner /> : (
            <div>
              <div style={{ ...card, padding:'16px 20px', marginBottom:16, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <div>
                  <div style={{ fontSize:15, fontWeight:500 }}>{detail.name}</div>
                  <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>{detail.description || '—'} · horizonte {detail.horizon_weeks} semanas</div>
                </div>
                <div style={{ display:'flex', gap:8 }}>
                  <Button onClick={()=>compute(selected)} disabled={computing}>{computing?'Calculando...':'▶ Calcular'}</Button>
                  <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar este escenario?', onConfirm: () => del(selected), danger: true }) }} style={{ background:'transparent', border:'.5px solid var(--color-border-danger)', borderRadius:8, padding:'7px 12px', color:'var(--color-text-danger)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>Eliminar</button>
                </div>
              </div>

              {results && (
                <div>
                  {/* KPIs */}
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20 }}>
                    {[
                      { l:'Resultado', v: results.feasible?'✓ Viable':'✗ Inviable', c: results.feasible?'var(--color-text-success)':'var(--color-text-danger)' },
                      { l:'Semanas sobrecargadas', v: results.overloaded_weeks_count, c: results.overloaded_weeks_count>0?'var(--color-text-danger)':'var(--color-text-success)' },
                      { l:'Utilización media', v: `${results.avg_utilization_pct}%` },
                      { l:'Demanda total', v: `${results.total_demand_hours}h` },
                    ].map((k,i) => (
                      <div key={i} style={{ background:'var(--color-background-secondary)', borderRadius:10, padding:'14px 16px' }}>
                        <div style={{ fontSize:12, color: k.c || 'var(--color-text-primary)', fontWeight:500, marginBottom:2 }}>{k.v}</div>
                        <div style={{ fontSize:11, color:'var(--color-text-secondary)' }}>{k.l}</div>
                      </div>
                    ))}
                  </div>

                  {/* Timeline chart */}
                  {results.capacity_timeline?.length > 0 && (
                    <div style={{ ...card, padding:'16px 20px', marginBottom:16 }}>
                      <div style={{ fontSize:13, fontWeight:500, marginBottom:12 }}>Utilización semanal</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={results.capacity_timeline.slice(0,16)}>
                          <XAxis dataKey="week" tick={{ fontSize:9 }} tickFormatter={w=>w.slice(-4)} />
                          <YAxis tick={{ fontSize:10 }} tickFormatter={v=>`${v}%`} />
                          <Tooltip formatter={v=>[`${v}%`,'Utilización']} />
                          <Bar dataKey="utilization_pct" radius={[3,3,0,0]}>
                            {(results.capacity_timeline||[]).slice(0,16).map((c,i)=>(
                              <Cell key={i} fill={c.is_overloaded?'var(--danger)':c.utilization_pct>80?'var(--warning)':'var(--success)'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Recommendation */}
                  <div style={{ ...card, padding:'14px 18px', background: results.feasible?'var(--color-background-success)':'var(--color-background-danger)', border:`.5px solid ${results.feasible?'var(--color-border-success)':'var(--color-border-danger)'}` }}>
                    <div style={{ fontSize:13, color: results.feasible?'var(--color-text-success)':'var(--color-text-danger)' }}>💡 {results.recommendation}</div>
                  </div>
                </div>
              )}

              {/* Projects list */}
              {detail.projects?.length > 0 && (
                <div style={{ ...card, padding:'16px 20px', marginTop:16 }}>
                  <div style={{ fontSize:13, fontWeight:500, marginBottom:12 }}>Proyectos en el escenario</div>
                  {detail.projects.map(p => (
                    <div key={p.id} style={{ display:'flex', justifyContent:'space-between', padding:'8px 0', borderBottom:'.5px solid var(--color-border-tertiary)', fontSize:12 }}>
                      <div>
                        <span style={{ fontWeight:500, marginRight:8 }}>{p.name}</span>
                        {p.is_existing && <span style={{ fontSize:10, padding:'1px 5px', borderRadius:4, background:'var(--color-background-info)', color:'var(--color-text-info)' }}>Existente</span>}
                      </div>
                      <span style={{ color:'var(--color-text-secondary)' }}>{p.total_hours}h · {p.start_date} → {p.end_date}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <Modal open title="Nuevo escenario" onClose={()=>setShowCreate(false)} width={560}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Nombre</label><input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Descripción</label><input value={form.description} onChange={e=>setForm(f=>({...f,description:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Horizonte de simulación (semanas)</label><input type="number" min={4} max={52} value={form.horizon_weeks} onChange={e=>setForm(f=>({...f,horizon_weeks:+e.target.value}))} style={fs} /></div>

            <div style={{ borderTop:'.5px solid var(--color-border-tertiary)', paddingTop:14 }}>
              <div style={{ fontSize:13, fontWeight:500, marginBottom:10 }}>Añadir proyectos hipotéticos</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
                <input placeholder="Nombre del proyecto" value={newProject.name} onChange={e=>setNewProject(p=>({...p,name:e.target.value}))} style={fs} />
                <input type="number" placeholder="Total horas" value={newProject.total_hours||''} onChange={e=>setNewProject(p=>({...p,total_hours:+e.target.value}))} style={fs} />
                <div><label style={ls}>Inicio</label><input type="date" value={newProject.start_date} onChange={e=>setNewProject(p=>({...p,start_date:e.target.value}))} style={fs} /></div>
                <div><label style={ls}>Fin</label><input type="date" value={newProject.end_date} onChange={e=>setNewProject(p=>({...p,end_date:e.target.value}))} style={fs} /></div>
              </div>
              <button onClick={()=>{ if(newProject.name){ setForm(f=>({...f,projects:[...f.projects,{...newProject}]})); setNewProject({name:'',start_date:'',end_date:'',total_hours:0}) }}}
                style={{ background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'6px 14px', color:'var(--color-text-primary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                + Añadir proyecto
              </button>
              {form.projects.length > 0 && (
                <div style={{ marginTop:10 }}>
                  {form.projects.map((p,i) => (
                    <div key={i} style={{ display:'flex', justifyContent:'space-between', fontSize:12, padding:'4px 0' }}>
                      <span>{p.name}</span>
                      <span style={{ color:'var(--color-text-secondary)' }}>{p.total_hours}h</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>Cancelar</Button>
              <Button onClick={()=>create(form)} disabled={creating||!form.name}>{creating?'Creando...':'Crear escenario'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
