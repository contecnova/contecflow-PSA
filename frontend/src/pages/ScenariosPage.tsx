/**
 * ScenariosPage — Scenario planning / What-if capacity
 *
 * 16-11-2026: pasada de diseño. Título como el menú; "Nuevo escenario" a la
 * cabecera con icono (antes suelto en el cuerpo y con "+" de texto); vacíos
 * con EmptyState e icono lucide (antes emoji y un vacío propio sin caja);
 * KPIs con KpiCard; botones del kit con icono (calcular, eliminar, añadir
 * proyecto); recomendación con icono lucide; campos con .ds-input.
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate, fmtHours, fmtPct } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scenariosApi } from '../services/api'
import type { EscenarioDetalle, EscenarioResumen, ResultadoDeEscenario } from '../services/api/tipos-finanzas'
import { Button, Card, KpiCard, Modal, Spinner, EmptyState, Pulsable, Input } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, CheckCircle2, Clock, Gauge, GitBranch, Lightbulb, MousePointerClick, Play, Plus, Trash2, XCircle } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { useTono } from '../hooks/useOrgSettings'
import DateInput from '../components/ui/DateInput'
import './ScenariosPage.css'

/** Proyecto hipotético del formulario de alta (create_scenario). */
interface ScenarioProject {
  id?: string | number
  name: string
  start_date: string
  end_date: string
  total_hours: number
  is_existing?: boolean
}

type ScenarioSummary = EscenarioResumen
type ScenarioResults = ResultadoDeEscenario
type ScenarioDetail = EscenarioDetalle

interface ScenarioForm {
  name: string
  description: string
  horizon_weeks: number
  projects: ScenarioProject[]
}

/** Estados de ScenarioModel.status (draft | computed | archived). */
const ESTADOS = ['draft', 'computed', 'archived']

export default function ScenariosPage() {
  const idCampo = useId()
  const t = useAppT()
  const tono = useTono()
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

  const results: ScenarioResults | undefined = detail?.results
  const etiquetaEstado = (estado?: string | null) =>
    estado && ESTADOS.includes(estado) ? t(`scenarios.estado_${estado}`) : (estado ?? '—')

  return (
    <PageShell>
      <PageHeader icon={<GitBranch size={18} />} title={t('scenarios.title')} subtitle={t('scenarios.subtitle')} showListExport={false}
        actions={<Button icon={<Plus size={14} />} onClick={()=>setShowCreate(true)}>{t('scenarios.nuevo_escenario')}</Button>} />

      <div className={`scn-layout${narrow ? ' scn-layout--narrow' : ''}`}>
        <div>
          {isLoading ? <Spinner /> : scenarios.length === 0 ? (
            <Card>
              <EmptyState icon={<GitBranch size={28} />} title={t('scenarios.no_scenarios')} description={t('scenarios.vacio_descripcion')}
                action={<Button icon={<Plus size={14} />} onClick={()=>setShowCreate(true)}>{t('scenarios.nuevo_escenario')}</Button>} />
            </Card>
          ) : scenarios.map(s => (
            <Pulsable key={s.id} type="button" onClick={()=>setSelected(s.id)} aria-pressed={selected===s.id}
              className={`scn-card scn-item${selected===s.id ? ' scn-item--selected' : ''}`}>
              <div className="scn-item-name">{s.name}</div>
              <div className="scn-item-meta">{t('scenarios.resumen_proyectos_semanas', { proyectos: s.project_count, semanas: s.horizon_weeks })}</div>
              <div className="u-row-center-8">
                <span className={`scn-status${s.status==='computed' ? ' scn-status--computed' : ''}`}>{etiquetaEstado(s.status)}</span>
                <span className="u-text3-xs">{fmtDate(s.created_at)}</span>
              </div>
            </Pulsable>
          ))}
        </div>

        <div>
          {!selected ? (
            <Card>
              <EmptyState icon={<MousePointerClick size={28} />} title={t('scenarios.selecciona_un_escenario')}
                description={t('scenarios.o_crea_uno_nuevo_para_simular_el')} />
            </Card>
          ) : !detail ? <Spinner /> : (
            <div>
              <div className="scn-card scn-card--pad scn-head">
                <div className="u-min0">
                  <div className="scn-head-title">{detail.name}</div>
                  <div className="u-text2-sm">{t('scenarios.descripcion_y_horizonte', { descripcion: detail.description || '—', semanas: detail.horizon_weeks })}</div>
                </div>
                <div className="u-row-8">
                  <Button icon={<Play size={14} />} onClick={()=>compute(selected)} loading={computing}>{computing ? t('scenarios.calculando') : t('scenarios.calcular')}</Button>
                  <Button variant="danger" icon={<Trash2 size={14} />} onClick={()=>{ openConfirmGlobal({ message: t('scenarios.confirmar_eliminar'), onConfirm: () => del(selected), danger: true }) }}>{t('common.delete')}</Button>
                </div>
              </div>

              {results && (
                <div>
                  {/* KPIs */}
                  <div className="ds-grid-stats scn-kpis">
                    <KpiCard icon={results.feasible ? <CheckCircle2 size={16} /> : <XCircle size={16} />} label={t('scenarios.kpi_resultado')}
                      value={results.feasible ? t('scenarios.viable') : t('scenarios.inviable')} danger={!results.feasible} />
                    <KpiCard icon={<AlertTriangle size={16} />} label={t('scenarios.kpi_semanas_sobrecargadas')}
                      value={results.overloaded_weeks_count ?? 0} danger={(results.overloaded_weeks_count ?? 0) > 0} />
                    <KpiCard icon={<Gauge size={16} />} label={t('scenarios.kpi_utilizacion_media')} value={fmtPct(results.avg_utilization_pct)} />
                    <KpiCard icon={<Clock size={16} />} label={t('scenarios.kpi_demanda_total')} value={fmtHours(results.total_demand_hours)} />
                  </div>

                  {/* Timeline chart */}
                  {(results.capacity_timeline?.length ?? 0) > 0 && (
                    <div className="scn-card scn-card--pad">
                      <div className="scn-section-title">{t('scenarios.utilizacion_semanal')}</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={(results.capacity_timeline ?? []).slice(0,16)}>
                          <XAxis dataKey="week" tick={{ fontSize: "var(--text-3xs)" }} tickFormatter={w=>w.slice(-4)} />
                          <YAxis tick={{ fontSize: "var(--text-2xs)" }} tickFormatter={v=>`${v}%`} />
                          <Tooltip formatter={v=>[`${v}%`, t('scenarios.utilizacion')]} />
                          <Bar dataKey="utilization_pct" radius={[3,3,0,0]}>
                            {(results.capacity_timeline||[]).slice(0,16).map((c,i)=>(
                              <Cell key={i} fill={c.is_overloaded?'var(--danger)':tono('carga', c.utilization_pct)==='success'?'var(--success)':'var(--warning)'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  {/* Recommendation */}
                  <div className={`scn-card scn-reco ${results.feasible ? 'scn-reco--ok' : 'scn-reco--ko'}`}>
                    <div className="scn-reco-text"><Lightbulb size={16} aria-hidden /><span>{results.recommendation}</span></div>
                  </div>
                </div>
              )}

              {/* Projects list */}
              {(detail.projects?.length ?? 0) > 0 && (
                <div className="scn-card scn-card--pad scn-card--mt">
                  <div className="scn-section-title">{t('scenarios.proyectos_en_el_escenario')}</div>
                  {(detail.projects ?? []).map(p => (
                    <div key={p.id} className="scn-project-row">
                      <div>
                        <span className="scn-project-name">{p.name}</span>
                        {p.is_existing && <span className="scn-tag">{t('scenarios.existente')}</span>}
                      </div>
                      <span className="u-text2">{fmtHours(p.total_hours)} · {fmtDate(p.start_date)} – {fmtDate(p.end_date)}</span>
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
            <Input label={t('common.name')} id={`${idCampo}-1`} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} />
            <Input label={t('scenarios.descripcion')} id={`${idCampo}-2`} value={form.description} onChange={e=>setForm(f=>({...f,description:e.target.value}))} />
            <Input label={t('scenarios.horizonte_de_simulacion_semanas')} id={`${idCampo}-3`} type="number" min={4} max={52} value={form.horizon_weeks} onChange={e=>setForm(f=>({...f,horizon_weeks:+e.target.value}))} />

            <div className="scn-form-block">
              <div className="scn-form-title">{t('scenarios.anadir_proyectos_hipoteticos')}</div>
              <div className="scn-form-grid">
                <Input aria-label={t('scenarios.nombre_del_proyecto')} placeholder={t('scenarios.nombre_del_proyecto')} value={newProject.name} onChange={e=>setNewProject(p=>({...p,name:e.target.value}))} />
                <Input aria-label={t('scenarios.total_horas')} type="number" placeholder={t('scenarios.total_horas')} value={newProject.total_hours||''} onChange={e=>setNewProject(p=>({...p,total_hours:+e.target.value}))} />
                <DateInput label={t('scenarios.inicio')} id={`${idCampo}-4`} value={newProject.start_date} onChange={e=>setNewProject(p=>({...p,start_date:e.target.value}))} />
                <DateInput label={t('scenarios.fin')} id={`${idCampo}-5`} value={newProject.end_date} onChange={e=>setNewProject(p=>({...p,end_date:e.target.value}))} />
              </div>
              <Button variant="secondary" icon={<Plus size={14} />} disabled={!newProject.name}
                onClick={()=>{ if(newProject.name){ setForm(f=>({...f,projects:[...f.projects,{...newProject}]})); setNewProject({name:'',start_date:'',end_date:'',total_hours:0}) }}}>
                {t('scenarios.anadir_proyecto')}
              </Button>
              {form.projects.length > 0 && (
                <div className="scn-added">
                  {form.projects.map((p,i) => (
                    <div key={i} className="scn-added-row">
                      <span>{p.name}</span>
                      <span className="u-text2">{fmtHours(p.total_hours)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="u-actions-10">
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>{t('common.cancel')}</Button>
              <Button onClick={()=>create(form)} disabled={!form.name} loading={creating}>{creating ? t('scenarios.creando') : t('scenarios.crear_escenario')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
