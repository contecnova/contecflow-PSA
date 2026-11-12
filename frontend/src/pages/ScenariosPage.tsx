/**
 * ScenariosPage — Scenario planning / What-if capacity
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scenariosApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { GitBranch } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import DateInput from '../components/ui/DateInput'

interface ScenarioProject {
  id?: string | number
  name: string
  start_date: string
  end_date: string
  total_hours: number
  is_existing?: boolean
}

interface ScenarioSummary {
  id: string | number
  name?: string
  project_count?: number
  horizon_weeks?: number
  status?: string
  created_at?: string
}

interface ScenarioTimelinePoint {
  week: string
  utilization_pct: number
  is_overloaded?: boolean
}

interface ScenarioResults {
  feasible?: boolean
  overloaded_weeks_count?: number
  avg_utilization_pct?: number
  total_demand_hours?: number
  recommendation?: string
  capacity_timeline?: ScenarioTimelinePoint[]
}

interface ScenarioDetail {
  id: string | number
  name?: string
  description?: string
  horizon_weeks?: number
  projects?: ScenarioProject[]
  results?: ScenarioResults
}

interface ScenarioForm {
  name: string
  description: string
  horizon_weeks: number
  projects: ScenarioProject[]
}

const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }
const fs: CSSProperties = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }

export default function ScenariosPage() {
  const t = useAppT()
  const narrow = useMediaQuery('(max-width: 900px)')
  const qc = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState<string | number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<ScenarioForm>({ name:'', description:'', horizon_weeks:12, projects:[] })
  const [newProject, setNewProject] = useState<ScenarioProject>({ name:'', start_date:'', end_date:'', total_hours:0 })

  const { data: scenarios = [], isLoading } = useQuery<ScenarioSummary[]>({ queryKey:['scenarios'], queryFn:()=>scenariosApi.list().then(r=>r.data) })
  const { data: detail } = useQuery<ScenarioDetail>({ queryKey:['scenario-detail', selected], queryFn:()=>scenariosApi.get(selected).then(r=>r.data), enabled:!!selected })

  const { mutate: create, isPending:creating } = useMutation({
    mutationFn: (d: ScenarioForm) => scenariosApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scenarios'] }); setShowCreate(false) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: compute, isPending:computing } = useMutation({
    mutationFn: (id: string | number) => scenariosApi.compute(id).then(r=>r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenario-detail', selected] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string | number) => scenariosApi.delete(id),
    onSuccess: () => { setSelected(null); qc.invalidateQueries({ queryKey: ['scenarios'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const _RISK_CFG = { low:{ c:'var(--success)', b:'var(--success-bg)', l:'Viable' }, medium:{ c:'var(--warning)', b:'var(--warning-bg)', l:'Riesgo medio' }, high:{ c:'var(--danger)', b:'var(--danger-bg)', l:'Inviable' } }

  const results: ScenarioResults | undefined = detail?.results

  return (
    <PageShell>
      <PageHeader icon={<GitBranch size={18} />} title={t('scenarios.title')} subtitle={t('scenarios.subtitle')} showListExport={false} />
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:20 }}>
        <Button onClick={()=>setShowCreate(true)}>{t('scenarios.nuevo_escenario')}</Button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: narrow ? 'minmax(0, 1fr)' : '340px minmax(0, 1fr)', gap:20 }}>
        <div>
          {isLoading ? <Spinner /> : scenarios.length === 0 ? (
            <EmptyState icon="🔮" title={t('scenarios.no_scenarios')} description="Crea un escenario para simular el impacto en capacidad" />
          ) : scenarios.map(s => (
            <button key={s.id} type="button" onClick={()=>setSelected(s.id)}
              style={{ ...card, padding:'14px 18px', marginBottom:10, cursor:'pointer', border: selected===s.id ? '.5px solid rgba(0,212,255,0.25)' : '.5px solid var(--surface-4)', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:4 }}>{s.name}</div>
              <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:6 }}>{s.project_count} proyectos · {s.horizon_weeks} semanas</div>
              <div className="u-row-center-8">
                <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background: s.status==='computed'?'var(--success-bg)':'var(--surface-2)', color: s.status==='computed'?'var(--success)':'var(--text-2)' }}>{s.status}</span>
                <span className="u-text3-xs">{s.created_at}</span>
              </div>
            </button>
          ))}
        </div>

        <div>
          {!selected ? (
            <div style={{ ...card, padding: narrow ? '32px 16px' : '48px', textAlign:'center', color:'var(--text-3)' }}>
              <div style={{ fontSize: "var(--text-5xl)", marginBottom:12 }}>🔮</div>
              <div style={{ fontSize: "var(--text-md)", fontWeight:500, marginBottom:6 }}>{t('scenarios.selecciona_un_escenario')}</div>
              <div className="u-sm">{t('scenarios.o_crea_uno_nuevo_para_simular_el')}</div>
            </div>
          ) : !detail ? <Spinner /> : (
            <div>
              <div style={{ ...card, padding:'16px 20px', marginBottom:16, display:'flex', flexWrap:'wrap', gap:12, justifyContent:'space-between', alignItems:'center' }}>
                <div className="u-min0">
                  <div style={{ fontSize: "var(--text-md-em)", fontWeight:500 }}>{detail.name}</div>
                  <div className="u-text2-sm">{detail.description || '—'} · horizonte {detail.horizon_weeks} semanas</div>
                </div>
                <div className="u-row-8">
                  <Button onClick={()=>compute(selected)} disabled={computing}>{computing?'Calculando...':'▶ Calcular'}</Button>
                  <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar este escenario?', onConfirm: () => del(selected), danger: true }) }} style={{ background:'transparent', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:8, padding:'7px 12px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>Eliminar</button>
                </div>
              </div>

              {results && (
                <div>
                  {/* KPIs */}
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(140px, 100%), 1fr))', gap:12, marginBottom:20 }}>
                    {[
                      { l:'Resultado', v: results.feasible?'✓ Viable':'✗ Inviable', c: results.feasible?'var(--success)':'var(--danger)' },
                      { l:'Semanas sobrecargadas', v: results.overloaded_weeks_count, c: (results.overloaded_weeks_count ?? 0)>0?'var(--danger)':'var(--success)' },
                      { l:'Utilización media', v: `${results.avg_utilization_pct}%` },
                      { l:'Demanda total', v: `${results.total_demand_hours}h` },
                    ].map((k,i) => (
                      <div key={i} style={{ background:'var(--surface-2)', borderRadius:10, padding:'14px 16px' }}>
                        <div style={{ fontSize: "var(--text-sm)", color: k.c || 'var(--text-1)', fontWeight:500, marginBottom:2 }}>{k.v}</div>
                        <div className="u-text2-xs">{k.l}</div>
                      </div>
                    ))}
                  </div>

                  {/* Timeline chart */}
                  {(results.capacity_timeline?.length ?? 0) > 0 && (
                    <div style={{ ...card, padding:'16px 20px', marginBottom:16 }}>
                      <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:12 }}>{t('scenarios.utilizacion_semanal')}</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={(results.capacity_timeline ?? []).slice(0,16)}>
                          <XAxis dataKey="week" tick={{ fontSize: "var(--text-3xs)" }} tickFormatter={w=>w.slice(-4)} />
                          <YAxis tick={{ fontSize: "var(--text-2xs)" }} tickFormatter={v=>`${v}%`} />
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
                  <div style={{ ...card, padding:'14px 18px', background: results.feasible?'var(--success-bg)':'var(--danger-bg)', border:`.5px solid ${results.feasible?'rgba(52,211,153,0.25)':'rgba(239,68,68,0.25)'}` }}>
                    <div style={{ fontSize: "var(--text-base)", color: results.feasible?'var(--success)':'var(--danger)' }}>💡 {results.recommendation}</div>
                  </div>
                </div>
              )}

              {/* Projects list */}
              {(detail.projects?.length ?? 0) > 0 && (
                <div style={{ ...card, padding:'16px 20px', marginTop:16 }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:12 }}>{t('scenarios.proyectos_en_el_escenario')}</div>
                  {(detail.projects ?? []).map(p => (
                    <div key={p.id} style={{ display:'flex', flexWrap:'wrap', gap:'4px 12px', justifyContent:'space-between', padding:'8px 0', borderBottom:'.5px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                      <div>
                        <span style={{ fontWeight:500, marginRight:8 }}>{p.name}</span>
                        {p.is_existing && <span style={{ fontSize: "var(--text-2xs)", padding:'1px 5px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>Existente</span>}
                      </div>
                      <span className="u-text2">{p.total_hours}h · {p.start_date} → {p.end_date}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <Modal open title={t('scenarios.nuevo_escenario_2')} onClose={()=>setShowCreate(false)} width={560}>
          <div className="u-stack-14">
            <div><label style={ls}>Nombre</label><input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>{t('scenarios.descripcion')}</label><input value={form.description} onChange={e=>setForm(f=>({...f,description:e.target.value}))} style={fs} /></div>
            <div><label style={ls}>{t('scenarios.horizonte_de_simulacion_semanas')}</label><input type="number" min={4} max={52} value={form.horizon_weeks} onChange={e=>setForm(f=>({...f,horizon_weeks:+e.target.value}))} style={fs} /></div>

            <div style={{ borderTop:'.5px solid var(--surface-4)', paddingTop:14 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:10 }}>{t('scenarios.anadir_proyectos_hipoteticos')}</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
                <input placeholder={t('scenarios.nombre_del_proyecto')} value={newProject.name} onChange={e=>setNewProject(p=>({...p,name:e.target.value}))} style={fs} />
                <input type="number" placeholder="Total horas" value={newProject.total_hours||''} onChange={e=>setNewProject(p=>({...p,total_hours:+e.target.value}))} style={fs} />
                <div><label style={ls}>Inicio</label><DateInput value={newProject.start_date} onChange={e=>setNewProject(p=>({...p,start_date:e.target.value}))} style={fs} /></div>
                <div><label style={ls}>Fin</label><DateInput value={newProject.end_date} onChange={e=>setNewProject(p=>({...p,end_date:e.target.value}))} style={fs} /></div>
              </div>
              <button onClick={()=>{ if(newProject.name){ setForm(f=>({...f,projects:[...f.projects,{...newProject}]})); setNewProject({name:'',start_date:'',end_date:'',total_hours:0}) }}}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding:'6px 14px', color:'var(--text-1)', cursor:'pointer', fontSize: "var(--text-base)", fontFamily:'inherit' }}>
                {t('scenarios.anadir_proyecto')}
              </button>
              {form.projects.length > 0 && (
                <div style={{ marginTop:10 }}>
                  {form.projects.map((p,i) => (
                    <div key={i} style={{ display:'flex', justifyContent:'space-between', fontSize: "var(--text-sm)", padding:'4px 0' }}>
                      <span>{p.name}</span>
                      <span className="u-text2">{p.total_hours}h</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="u-actions-10">
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>Cancelar</Button>
              <Button onClick={()=>create(form)} disabled={creating||!form.name}>{creating?'Creando...':'Crear escenario'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
