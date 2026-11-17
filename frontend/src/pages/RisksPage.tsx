/*
 * RisksPage — registro y matriz de riesgos.
 *
 * 16-11-2026: pasada de diseño. Título como el menú ("Riesgos"); selector de
 * proyecto fuera de la cabecera, en la barra de filtros; "Nuevo riesgo" con
 * icono lucide (deshabilitado con explicación si no hay proyecto); KPIs con
 * KpiCard (antes cifra monoespaciada propia); pestañas del tamaño estándar
 * con icono (antes pequeñas y con emojis); emojis de niveles, editar,
 * borrar, mitigación, proyecto y responsable cambiados por iconos lucide;
 * campos con .ds-input.
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, risksApi } from '../services/api'
import type { RiesgosDelProyecto } from '../services/api/tipos'
import type { RiesgoSerializado } from '../services/api/tipos-proyectos'
import { Button, KpiCard, Modal, Spinner, EmptyState, useSort, ViewToggle, Tabs, Select, IconButton, TablaSimple } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertOctagon, AlertTriangle, CircleDot, Folder, Grid3x3, List, Pencil, Plus, ShieldCheck, Trash2, User } from 'lucide-react'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './RisksPage.css'

type RiskStatus = RiesgoSerializado['status']
type RiskProbability = RiesgoSerializado['probability']
type RiskImpact = RiesgoSerializado['impact']

type ProjectItem = { id: string | number; code?: string; name: string }
type UserItem = { id: string | number; full_name?: string }

/** risk_service.serialize_risk; `project_name` solo en la vista de cartera. */
type RiskItem = RiesgoSerializado & { project_name?: string }
type RiskSummary = Partial<RiesgosDelProyecto['summary']>
type RisksResponse = { risks: RiskItem[]; summary: RiskSummary }

type RiskFormState = {
  title: string
  description: string
  category: string
  probability: RiskProbability
  impact: RiskImpact
  status: RiskStatus
  mitigation_plan: string
  contingency_plan: string
  response_type: string
  owner_id: string
  review_date: string
  cost_impact_min: number | string
  cost_impact_max: number | string
  schedule_impact_days: number | string
  notes: string
}

type SortKey = 'risk_level' | 'title' | 'status' | 'project_name'

// Valores que acepta el backend; los textos salen de `risks.options.*`.
const PROB_OPTIONS = ['very_low', 'low', 'medium', 'high', 'very_high']
const IMPACT_OPTIONS = ['negligible', 'minor', 'moderate', 'major', 'critical']
const STATUS_OPTIONS = ['identified', 'analyzing', 'mitigating', 'monitoring', 'closed', 'materialized']
const CATEGORIES = ['technical', 'financial', 'schedule', 'resource', 'external', 'quality']
const RESPONSE_TYPES = ['avoid', 'mitigate', 'transfer', 'accept']
const LEVELS = ['critical', 'high', 'medium', 'low'] as const
type Level = typeof LEVELS[number]
const nivel = (l: string | null | undefined): Level => (LEVELS as readonly string[]).includes(l ?? '') ? l as Level : 'low'

function RiskMatrix({ risks }: { risks: RiskItem[] }) {
  const t = useAppT()

  // Puntuación probabilidad × impacto → nivel de color de la celda.
  const nivelDeCelda = (p: string, i: string): Level => {
    const score = (PROB_OPTIONS.indexOf(p) + 1) * (IMPACT_OPTIONS.indexOf(i) + 1)
    if (score >= 15) return 'critical'
    if (score >= 8) return 'high'
    if (score >= 4) return 'medium'
    return 'low'
  }

  const cellRisks = (p: string, i: string) => risks.filter((r) => r.probability === p && r.impact === i)

  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="rsk-matrix">
        <thead>
          <tr>
            <th scope="col" className="rsk-matrix__axis">{t('risks.matrix.axis')}</th>
            {PROB_OPTIONS.map(p => <th key={p} scope="col">{t(`risks.options.prob_${p}_short`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {[...IMPACT_OPTIONS].reverse().map(imp => (
            <tr key={imp}>
              <th scope="row" className="rsk-matrix__row">{t(`risks.options.impact_${imp}_short`)}</th>
              {PROB_OPTIONS.map(prob => {
                const cr = cellRisks(prob, imp)
                return (
                  <td key={prob}>
                    <div className={`rsk-cell rsk-lvl--${nivelDeCelda(prob, imp)}`}>
                      {cr.length > 0 && (
                        <>
                          <div className="rsk-cell__count">{cr.length}</div>
                          <div className="rsk-cell__codes">
                            {cr[0].code}
                            {cr.length > 1 ? ` +${cr.length - 1}` : ''}
                          </div>
                        </>
                      )}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

function RiskFormModal({ risk, projectId, onClose }: { risk?: RiskItem | null; projectId: string | number; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!risk?.id
  const { data: users = [] } = useQuery<UserItem[]>({ queryKey: ['users'], queryFn: () => usersApi.list({}).then(r => r.data as UserItem[]) })
  const [form, setForm] = useState<RiskFormState>({
    title: risk?.title || '',
    description: risk?.description || '',
    category: risk?.category || 'technical',
    probability: risk?.probability || 'medium',
    impact: risk?.impact || 'moderate',
    status: risk?.status || 'identified',
    mitigation_plan: risk?.mitigation_plan || '',
    contingency_plan: risk?.contingency_plan || '',
    response_type: risk?.response_type || 'mitigate',
    owner_id: risk?.owner_id != null ? String(risk.owner_id) : '',
    review_date: risk?.review_date || '',
    cost_impact_min: risk?.cost_impact_min || '',
    cost_impact_max: risk?.cost_impact_max || '',
    schedule_impact_days: risk?.schedule_impact_days || '',
    notes: risk?.notes || '',
  })
  const set = <K extends keyof RiskFormState>(k: K) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value as RiskFormState[K] }))

  const { mutate, isPending } = useMutation({
    mutationFn: (data: RiskFormState) => isEdit && risk
      ? risksApi.update(projectId, risk.id, data)
      : risksApi.create(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['risks', projectId] }); onClose() },
    onError: e => toast.error(extractErr(e, t('risks_page.error_generico'))),
  })

  return (
    <Modal open title={isEdit ? t('risks.edit_title') : t('risks.new_title')} onClose={onClose} width={660}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="rsk-label">{t('risks.form.title')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} className="ds-input" placeholder={t('risks.form.title_ph')} required aria-required="true" />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="rsk-label">{t('risks.form.category')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.category} onChange={set('category')}>
            {CATEGORIES.map(c => <option key={c} value={c}>{t(`risks.options.cat_${c}`)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="rsk-label">{t('risks.form.status')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.status} onChange={set('status')}>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{t(`risks.options.status_${s}`)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="rsk-label">{t('risks.form.prob')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.probability} onChange={set('probability')}>
            {PROB_OPTIONS.map(p => <option key={p} value={p}>{t(`risks.options.prob_${p}`)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="rsk-label">{t('risks.form.impact')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.impact} onChange={set('impact')}>
            {IMPACT_OPTIONS.map(i => <option key={i} value={i}>{t(`risks.options.impact_${i}`)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="rsk-label">{t('risks.form.response_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-6`} value={form.response_type} onChange={set('response_type')}>
            {RESPONSE_TYPES.map(r => <option key={r} value={r}>{t(`risks.options.resp_${r}`)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="rsk-label">{t('risks.form.owner')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-7`} value={form.owner_id} onChange={set('owner_id')}>
            <option value="">{t('risks.form.unassigned')}</option>
            {users.map(u => <option key={u.id} value={String(u.id)}>{u.full_name}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="rsk-label">{t('risks_page.coste_min')}</label>
          <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={form.cost_impact_min} onChange={set('cost_impact_min')} className="ds-input" placeholder={t('risks.form.cost_min_ph')} />
        </div>
        <div>
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="rsk-label">{t('risks_page.coste_max')}</label>
          <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.cost_impact_max} onChange={set('cost_impact_max')} className="ds-input" placeholder={t('risks.form.cost_max_ph')} />
        </div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="rsk-label">{t('risks.form.days_impact')}</label>
          <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} className="ds-input" placeholder={t('risks.form.days_impact_ph')} />
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="rsk-label">{t('risks.form.review_date')}</label>
          <DateInput id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={form.review_date} onChange={set('review_date')} className="ds-input" />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="rsk-label">{t('risks.form.description')}</label>
          <textarea id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.description} onChange={set('description')} rows={2} className="ds-input" />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="rsk-label">{t('risks.form.mitigation_plan')}</label>
          <textarea id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} value={form.mitigation_plan} onChange={set('mitigation_plan')} rows={2} className="ds-input" placeholder={t('risks.form.mitigation_plan_ph')} />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="rsk-label">{t('risks.form.contingency_plan')}</label>
          <textarea id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={form.contingency_plan} onChange={set('contingency_plan')} rows={2} className="ds-input" placeholder={t('risks.form.contingency_plan_ph')} />
        </div>
        <div className="rsk-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('risks.form.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
            {isPending ? t('risks.form.saving') : isEdit ? t('risks.form.save') : t('risks.form.create')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function RisksPage() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<RiskItem | null>(null)
  const [tab, setTab] = useState<'register' | 'matrix'>('register')
  const [riskLevelFilter, setRiskLevelFilter] = useState('')
  const [riskSortBy, setRiskSortBy] = useState<SortKey>('risk_level')
  const [view, setView] = useState<'list' | 'cards'>('list')
  const qc = useQueryClient()

  // Cualquier proyecto vivo, no sólo los activos: un riesgo se anota también en
  // planificación o en pausa (revisión 2026-11).
  const { data: projects = [] } = useQuery<ProjectItem[]>({ queryKey: ['projects', 'vivos'], queryFn: () => projectsApi.list().then(r => ((r.data ?? []) as ProjectItem[]).filter(p => !['completed', 'closed', 'cancelled', 'archived'].includes(String((p as { status?: string }).status ?? '')))) })

  const { data: risksData, isLoading } = useQuery<RisksResponse>({
    queryKey: ['risks', selectedProject],
    queryFn: () => selectedProject
      ? risksApi.list<RiesgoSerializado>(selectedProject, {}).then(r => r.data)
      : risksApi.portfolioAll().then(r => ({ risks: r.data, summary: { total: r.data.length } })),
  })

  const { mutate: deleteRisk } = useMutation({
    mutationFn: ({ projectId, riskId }: { projectId: string | number; riskId: string | number }) => risksApi.delete(projectId, riskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks', selectedProject] }),
    onError: e => toast.error(extractErr(e, t('risks_page.error_generico'))),
  })

  const risks: RiskItem[] = risksData?.risks || []
  const summary: RiskSummary = risksData?.summary || {}
  const filteredRisks: RiskItem[] = riskLevelFilter ? risks.filter(r => r.risk_level === riskLevelFilter) : risks
  const { sortedData: sortedRisks } = useSort(filteredRisks, riskSortBy)

  const confirmarBorrado = (r: RiskItem) => openConfirmGlobal({
    message: t('risks.delete_confirm'),
    onConfirm: () => deleteRisk({ projectId: r.project_id, riskId: r.id }),
    danger: true,
  })

  const botones = (r: RiskItem) => (
    <>
      <IconButton type="button" onClick={() => setEditing(r)} className="rsk-icon-btn"
        ariaLabel={t('risks_page.editar_riesgo', { titulo: r.title })} title={t('risks_page.editar')}>
        <Pencil size={14} aria-hidden />
      </IconButton>
      <IconButton type="button" onClick={() => confirmarBorrado(r)} className="rsk-icon-btn rsk-icon-btn--danger"
        ariaLabel={t('risks_page.eliminar_riesgo', { titulo: r.title })} title={t('risks_page.eliminar')}>
        <Trash2 size={14} aria-hidden />
      </IconButton>
    </>
  )

  const total = summary.total || risks.length
  const abiertos = summary.open || risks.filter(r => !['closed','materialized'].includes(r.status)).length
  const criticos = summary.critical_count || risks.filter(r => r.risk_level === 'critical').length
  const altos = summary.high_count || risks.filter(r => r.risk_level === 'high').length

  return (
    <PageShell>
      <PageHeader
        icon={<AlertTriangle size={18} />}
        title={t('risks.title')}
        subtitle={t('risks.subtitle')}
        actions={
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)} disabled={!selectedProject}
            title={selectedProject ? undefined : t('risks_page.elige_proyecto_crear')}>
            {t('risks.new_risk')}
          </Button>
        }
      />

      {/* Proyecto: filtro de toda la pantalla, bajo la cabecera */}
      <div className="ds-toolbar rsk-barra">
        <Select suelto placeholder={false} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          aria-label={t('risks_page.proyecto')} className="rsk-input--project">
          <option value="">{t('risks.all_projects')}</option>
          {projects.map(p => <option key={p.id} value={String(p.id)}>{p.code} — {p.name}</option>)}
        </Select>
      </div>

      {/* Summary */}
      <div className="ds-grid-stats rsk-summary">
        <KpiCard icon={<ShieldCheck size={16} />} label={t('risks.summary.total')} value={total} />
        <KpiCard icon={<CircleDot size={16} />} label={t('risks.summary.open')} value={abiertos} warning={abiertos > 0} />
        <KpiCard icon={<AlertOctagon size={16} />} label={t('risks.summary.critical')} value={criticos} danger={criticos > 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('risks.summary.high')} value={altos} warning={altos > 0} />
      </div>

      <Tabs
        items={[
          { id: 'register', label: t('risks.tabs.register'), icon: <List size={14} /> },
          { id: 'matrix',   label: t('risks.tabs.matrix'), icon: <Grid3x3 size={14} /> },
        ]}
        active={tab}
        onChange={(id: string) => setTab(id as 'register' | 'matrix')}
        ariaLabel={t('risks.title')}
        className="rsk-tabs"
      />

      {isLoading ? <Spinner /> : risks.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={t('risks.empty.title')} description={selectedProject ? t('risks.empty.no_risks_project') : t('risks.empty.no_risks_portfolio')}
          action={selectedProject ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('risks.new_risk')}</Button> : undefined} />
      ) : tab === 'matrix' ? (
        <div className="ds-card">
          <h3 className="rsk-matrix-title">{t('risks.matrix.title')}</h3>
          <RiskMatrix risks={risks} />
        </div>
      ) : (
        <div>
          <div className="rsk-filters">
            <Select suelto placeholder={false} value={riskLevelFilter} onChange={e => setRiskLevelFilter(e.target.value)}
              aria-label={t('risks_page.filtrar_nivel')}
              className="rsk-input--auto">
              <option value="">{t('risks.filters.all_levels')}</option>
              <option value="critical">{t('risks.options.level_critical')}</option>
              <option value="high">{t('risks.options.level_high')}</option>
              <option value="medium">{t('risks.options.level_medium')}</option>
              <option value="low">{t('risks.options.level_low')}</option>
            </Select>
            <Select suelto placeholder={false} value={riskSortBy} onChange={e => setRiskSortBy(e.target.value as SortKey)}
              aria-label={t('risks_page.ordenar')} className="rsk-input--auto">
              <option value="risk_level">{t('risks.sort.level')}</option>
              <option value="title">{t('risks.sort.title')}</option>
              <option value="status">{t('risks.sort.status')}</option>
              <option value="project_name">{t('risks.sort.project')}</option>
            </Select>
            <div className="rsk-filters__end">
              <ViewToggle view={view} onChange={(v: string) => setView(v as 'list' | 'cards')} />
            </div>
          </div>
          {view === 'list' ? (
          <div className="u-stack-10">
          {sortedRisks.map((r: RiskItem) => {
            const lvl = nivel(r.risk_level)
            return (
              <div key={r.id} className={`rsk-item rsk-lvl--${lvl}`}>
                <div className="rsk-item__row">
                  <div className="rsk-dot" aria-hidden="true" />
                  <div className="u-flex1">
                    <div className="rsk-item__head">
                      <div>
                        <span className="u-md-700">{r.title}</span>
                        <span className="rsk-meta rsk-meta--mono">{r.code}</span>
                        {r.project_name && <span className="rsk-meta">· {r.project_name}</span>}
                      </div>
                      <div className="u-row-center-6">
                        <span className="rsk-badge">{t(`risks.options.level_${lvl}`)}</span>
                        <span className="u-text2-xs">{r.status_label}</span>
                        {botones(r)}
                      </div>
                    </div>
                    <div className="rsk-facts">
                      <span>{t('risks_page.prob')} <span className="u-text1">{r.probability_label}</span></span>
                      <span>{t('risks_page.impacto')} <span className="u-text1">{r.impact_label}</span></span>
                      {r.category_label && <span>{t('risks_page.tipo')} <span className="u-text1">{r.category_label}</span></span>}
                      {r.owner_name && <span>{t('risks_page.responsable')} <span className="u-text1">{r.owner_name}</span></span>}
                      {r.cost_impact_max && <span>{t('risks_page.impacto')} <span className="u-warning">{t('risks_page.hasta', { importe: fmtMoneda(Number(r.cost_impact_max), { decimales: 0 }) })}</span></span>}
                      {r.schedule_impact_days && <span>{t('risks_page.plazo')} <span className="u-warning">{t('risks_page.dias_mas', { n: r.schedule_impact_days })}</span></span>}
                    </div>
                    {r.mitigation_plan && (
                      <div className="rsk-mitigation">
                        <ShieldCheck size={13} aria-hidden /> <span className="u-text1">{r.mitigation_plan}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
          </div>
          ) : (
          <div className="rsk-grid">
            {sortedRisks.map((r: RiskItem) => {
              const lvl = nivel(r.risk_level)
              return (
                <div key={r.id} className={`rsk-card rsk-lvl--${lvl}`}>
                  <div className="rsk-card__head">
                    <div className="u-row-center-8">
                      <div className="rsk-dot" aria-hidden="true" />
                      <span className="rsk-badge">{t(`risks.options.level_${lvl}`)}</span>
                    </div>
                    <div className="rsk-card__actions">{botones(r)}</div>
                  </div>
                  <div className="rsk-card__title">{r.title}</div>
                  {r.project_name && <div className="rsk-card__project"><Folder size={12} aria-hidden /> {r.project_name}</div>}
                  <div className="rsk-card__tags">
                    <span className="rsk-tag">{t('risks_page.prob_corta')} {r.probability_label}</span>
                    <span className="rsk-tag">{t('risks_page.impacto_corto')} {r.impact_label}</span>
                    {r.owner_name && <span className="rsk-tag"><User size={11} aria-hidden /> {r.owner_name}</span>}
                  </div>
                  {r.mitigation_plan && (
                    <div className="rsk-card__mitigation">
                      <ShieldCheck size={12} aria-hidden /> {r.mitigation_plan.length > 80 ? r.mitigation_plan.slice(0, 80) + '…' : r.mitigation_plan}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          )}
        </div>
      )}

      {showCreate && <RiskFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <RiskFormModal risk={editing} projectId={editing.project_id} onClose={() => setEditing(null)} />}
    </PageShell>
  )
}
