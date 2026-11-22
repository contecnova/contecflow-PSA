import { lazy, Suspense, useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, risksApi, plantillasApi, type ProjectDetail, type ProjectUpdatePayload } from '../services/api'
import { Spinner, LoadBar as LoadBarRaw, EmptyState as EstadoVacio, MarcaExterno, Pulsable, Select, Input, Textarea } from '../components/ui'
import { extractErr, fmtDate, fmtCurrency } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
// 16-11-2026 (pasada de diseño): vacíos de miembros/riesgos y «proyecto no
// encontrado» con EmptyState e icono lucide (antes emojis); enlace de IA sin emoji.
import { ChevronLeft, FolderOpen, Users, CheckSquare, AlertTriangle, BarChart2, ExternalLink, Edit2, X, Check, Sparkles, FileText, Lightbulb, Laptop, RefreshCw, Wallet, Gauge, Flag, Shield, ClipboardCheck, Brain, Copy, ShieldCheck, SearchX } from 'lucide-react'

import DocumentosDeFicha from '../components/conectores/DocumentosDeFicha'
import LeccionesDelProyecto from '../components/lecciones/LeccionesDeOrigen'
import RecursosTecnicosDelProyecto from '../components/alm/RecursosTecnicosDelProyecto'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { alpha } from '../constants/theme'
import { useTono } from '../hooks/useOrgSettings'
import { colorDeTono } from '../utils/umbrales'
import DateInput from '../components/ui/DateInput'
import { STALE_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import './ProjectDetailPage.css'

// LoadBar's inferred props are all-required; expose a loose signature for callers.
const LoadBar = LoadBarRaw as (props: { value: number; max?: number; height?: number; label?: string; color?: string }) => JSX.Element

// ── Loose project / task / member / risk shapes (API slices are narrowly typed) ──
 
/**
 * `ProjectOut` (app/schemas/projects.py), tal como lo tipa el slice de proyectos.
 * `pm_name` NO viene en `GET /projects/{id}` (ProjectOut trae `project_manager`):
 * la pantalla lo lee igualmente, así que el PM no se muestra nunca. Se declara
 * opcional para no cambiar el comportamiento; ver informe de la auditoría #25.
 */
type Project = ProjectDetail & { pm_name?: string | null }
 
 
type Member = { id?: string; user_id?: string; full_name?: string; name?: string; role?: string; project_role?: string; allocation_pct?: number | null; external_company?: string | null }
 
type Risk = { id?: string; title?: string; description?: string; impact?: string; severity?: string; status?: string }

const STATUS_COLOR_MAP: Record<string, string> = {
  planning:  'var(--text-2)',
  active:    'var(--accent)',
  on_hold:   'var(--warning)',
  paused:    'var(--warning)',
  completed: 'var(--success)',
  closed:    'var(--success)',
  cancelled: 'var(--text-3)',
  archived:  'var(--text-4)',
}

const RISK_COLOR: Record<string, string> = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)', critical: 'var(--danger)' }

// 19-11-2026: etiquetas y colores de estado de proyecto en UN sitio (antes, dos copias en esta página).
function cfgDeEstadoDeProyecto(t: (k: string) => string) {
  return {
    planning:  { color: STATUS_COLOR_MAP.planning,  label: t('project_detail.status_planning') },
    active:    { color: STATUS_COLOR_MAP.active,    label: t('project_detail.status_active') },
    on_hold:   { color: STATUS_COLOR_MAP.on_hold,   label: t('project_detail.status_on_hold') },
    paused:    { color: STATUS_COLOR_MAP.paused,    label: t('project_detail.status_paused') },
    completed: { color: STATUS_COLOR_MAP.completed, label: t('project_detail.status_completed') },
    closed:    { color: STATUS_COLOR_MAP.closed,    label: t('project_detail.status_closed') },
    cancelled: { color: STATUS_COLOR_MAP.cancelled, label: t('project_detail.status_cancelled') },
    archived:  { color: STATUS_COLOR_MAP.archived,  label: t('project_detail.status_archived') },
  }
}

function MetaItem({ label, value }: { label: string; value?: string | number | null }) {
  if (!value) return null
  return (
    <div>
      <div className="pd-text-muted-2xs-strong">{label}</div>
      <div className="pd-text-base">{value}</div>
    </div>
  )
}

function OverviewTab({ project }: { project: Project }) {
  const t = useAppT()
  const tono = useTono()
  const budgetPct = project.budget_used_pct ?? 0
  // 19-11-2026: umbrales de la empresa (useUmbrales), no cortes propios.
  const budgetColor = colorDeTono(tono('presupuesto', budgetPct))

  return (
    <div className="u-stack-20">
      {/* Progress */}
      <div className="pd-card">
        <div className="pd-row">
          <span className="pd-text">{t('project_detail.project_progress')}</span>
          <span className="pd-text-accent-strong-mono">{(project.progress_pct ?? 0).toFixed(0)}%</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} />
      </div>

      {/* Metadata grid */}
      <div className="pd-grid">
        <MetaItem label={t('project_detail.meta_type')} value={etiquetaCodigo(t, 'tipo_proyecto', project.project_type)} />
        <MetaItem label={t('project_detail.meta_pm')} value={project.pm_name} />
        <MetaItem label={t('project_detail.meta_client')} value={project.client_name} />
        <MetaItem label={t('project_detail.meta_department')} value={project.department} />
        <MetaItem label={t('project_detail.meta_start')} value={project.start_date ? fmtDate(project.start_date) : null} />
        <MetaItem label={t('project_detail.meta_end_planned')} value={project.end_date_planned ? fmtDate(project.end_date_planned) : null} />
        {project.budget_amount && (
          <MetaItem label={t('project_detail.meta_budget')} value={fmtCurrency(project.budget_amount)} />
        )}
        <MetaItem label={t('project_detail.meta_team')} value={project.team_size ? `${project.team_size} ${t('project_detail.people')}` : null} />
      </div>

      {/* Budget bar */}
      {project.budget_amount && (
        <div className="pd-card">
          <div className="pd-row">
            <span className="pd-text">{t('project_detail.budget_execution')}</span>
            <span className="pd-text-strong-mono pd-text-3" style={{ '--pd-text-3-color': budgetColor } as CSSProperties}>{budgetPct.toFixed(0)}%</span>
          </div>
          <LoadBar value={Math.min(budgetPct, 100)} color={budgetColor} />
          <div className="pd-text-muted-xs">
            {t('project_detail.total')}: {fmtCurrency(project.budget_amount)}
          </div>
        </div>
      )}

      {/* Description */}
      {project.description && (
        <div className="pd-card">
          <div className="pd-text-muted-xs-strong">{t('project_detail.description')}</div>
          <p className="pd-text-base-2">{project.description}</p>
        </div>
      )}

      {/* Quick links */}
      <div className="u-wrap-10">
        {[
          { label: t('project_detail.view_gantt'), to: `/gantt?project=${project.id}`, icon: BarChart2 },
          { label: t('project_detail.view_full_tasks'), to: `/tasks?project_id=${project.id}`, icon: CheckSquare },
        ].map(({ label, to, icon: Icon }) => (
          <Link key={to} to={to} className="pd-enlace-rapido">
            <Icon size={12} />{label} <ExternalLink size={10} />
          </Link>
        ))}
      </div>
    </div>
  )
}

// Rev. 173: la pestaña Tareas son las vistas de trabajo (components/planificador/VistasDeTrabajo).

function TeamTab({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data: members = [], isLoading } = useQuery<Member[]>({
    queryKey: ['project-detail-team', projectId],
    queryFn: () => projectsApi.team(projectId!).then(r => {
      const d = r.data as Member[] | { members?: Member[]; items?: Member[] }
      return Array.isArray(d) ? d : (d?.members || d?.items || [])
    }),
    staleTime: STALE_DEFAULT_MS,
  })

  if (isLoading) return <div className="pd-row-2"><Spinner /></div>

  if (members.length === 0) return (
    <div className="pd-state-muted">
      <EstadoVacio icon={<Users size={28} />} title={t('project_detail.no_members')} />
      <Link to="/resources" className="pd-enlace-accion">
        {t('project_detail.manage_resources')}
      </Link>
    </div>
  )

  return (
    <div className="u-stack-8">
      {members.map((m, i) => (
        <div className="pd-row-3" key={m.id || m.user_id || i}>
          <div className="pd-row-accent">
            {(m.full_name || m.name || '?').charAt(0).toUpperCase()}
          </div>
          <div className="u-flex1">
            <div className="u-text1-base-600">{m.full_name || m.name || '—'} <MarcaExterno persona={m} /></div>
            {(m.role || m.project_role) && (
              <div className="pd-text-muted-xs-2">{m.role || m.project_role}</div>
            )}
          </div>
          {m.allocation_pct != null && (
            <span className="pd-text-accent-sm-strong-mono">
              {m.allocation_pct}%
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function RisksTab({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data: risks = [], isLoading } = useQuery<Risk[]>({
    queryKey: ['project-detail-risks', projectId],
    // Auditoria 2026-11 (#39): el endpoint devuelve `{risks, summary}`; se leia
    // como lista o `{items}` y la pestana de riesgos salia siempre vacia.
    queryFn: () => risksApi.list<Risk>(projectId, undefined).then(r => r.data?.risks ?? []),
    staleTime: STALE_DEFAULT_MS,
  })

  if (isLoading) return <div className="pd-row-2"><Spinner /></div>

  if (risks.length === 0) return (
    <div className="pd-state-muted">
      <EstadoVacio icon={<ShieldCheck size={28} />} title={t('project_detail.no_risks')} />
      <Link to="/risks" className="pd-enlace-accion">
        {t('project_detail.view_risk_mgmt')}
      </Link>
    </div>
  )

  const IMPACT_COLOR: Record<string, string> = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)', critical: 'var(--danger)' }

  return (
    <div className="u-stack-8">
      {risks.map((risk, i) => {
        const impColor = IMPACT_COLOR[risk.impact || risk.severity || ''] || 'var(--text-3)'
        return (
          <div className="pd-card-2" key={risk.id || i} style={{ '--pd-card-2-border': `1px solid ${alpha(impColor, '30')}`, '--pd-card-2-border-left': `3px solid ${impColor}` } as CSSProperties}>
            <div className="pd-row-4">
              <div>
                <div className="pd-text-base-3">
                  {risk.title || risk.description}
                </div>
                {risk.description && risk.title && (
                  <div className="pd-text-muted-sm">{risk.description}</div>
                )}
              </div>
              <div className="pd-row-5">
                {(risk.impact || risk.severity) && (
                  <span className="pd-box-4 pd-box-10" style={{ '--pd-box-10-background': alpha(impColor, '18'), '--pd-box-10-color': impColor } as CSSProperties}>
                    {risk.impact || risk.severity}
                  </span>
                )}
                {risk.status && (
                  <span className="pd-card-muted">
                    {risk.status}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

type EditProjectFormState = {
  name: string
  description: string
  status: string
  end_date_planned: string
  budget_amount: number | string
}

function EditProjectForm({ project, onSave, onCancel, isPending }: {
  project: Project
  onSave: (form: EditProjectFormState) => void
  onCancel: () => void
  isPending: boolean
}) {
  const idCampo = useId()
  const t = useAppT()
  const STATUS_CFG = cfgDeEstadoDeProyecto(t)
  // `budget_amount` arranca con el número del proyecto y pasa a texto al editarlo.
  const [form, setForm] = useState<EditProjectFormState>({
    name: project.name || '',
    description: project.description || '',
    status: project.status || 'active',
    end_date_planned: project.end_date_planned?.slice(0, 10) || '',
    budget_amount: project.budget_amount ?? '',
  })
  const set = (k: keyof EditProjectFormState, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="pd-stack">
      <div>
        <label className="pd-label-style" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('project_detail.project_name_label')}</label>
        <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => set('name', e.target.value)} onFocus={e => e.target.style.borderColor = 'var(--accent)'} onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} inputClassName="pd-input-style" />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{t('project_detail.status_label')}</label>
        <Select suelto placeholder={false} className="pd-input-style pd-input" id={`${idCampo}-2`} value={form.status} onChange={e => set('status', e.target.value)}>
          {Object.entries(STATUS_CFG).map(([v, cfg]) => (
            <option key={v} value={v}>{cfg.label}</option>
          ))}
        </Select>
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{t('project_detail.end_date_label')}</label>
        <DateInput id={`${idCampo}-3`} value={form.end_date_planned} onChange={e => set('end_date_planned', e.target.value)} className="pd-input-style"
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{t('project_detail.budget_label')}</label>
        <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={form.budget_amount} onChange={e => set('budget_amount', e.target.value)} onFocus={e => e.target.style.borderColor = 'var(--accent)'} onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} inputClassName="pd-input-style" />
      </div>
      <div>
        <label className="pd-label-style" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{t('project_detail.description_label')}</label>
        <Textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={e => set('description', e.target.value)} rows={4} onFocus={e => e.target.style.borderColor = 'var(--accent)'} onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} inputClassName="pd-input-style pd-input-2" />
      </div>
      <div className="u-row-8">
        <Pulsable className="pd-btn-sm" onClick={() => onSave(form)} disabled={isPending || !form.name.trim()}
          style={{ '--pd-btn-sm-cursor': isPending || !form.name.trim() ? 'not-allowed' : 'pointer', '--pd-btn-sm-opacity': !form.name.trim() ? '0.5' : '1' } as CSSProperties}>
          <Check size={13} />{isPending ? t('project_detail.saving') : t('project_detail.save_changes')}
        </Pulsable>
        <Pulsable className="pd-btn-ghost-sm" onClick={onCancel}>
          <X size={13} /> {t('project_detail.cancel')}
        </Pulsable>
      </div>
    </div>
  )
}

/** Una pestaña de la ficha. `render` pinta su contenido con el id del proyecto;
 *  sin él, la pestaña la pinta el bloque de contenido de siempre. */
interface PestanaDeFicha {
  id: string
  label: string
  icon: typeof FolderOpen
  visible?: boolean
  render?: (projectId: string) => JSX.Element
}

// Las pantallas globales que la ficha reutiliza, cargadas solo al abrir su pestaña.
const GanttPage = lazy(() => import('./GanttPage'))
const SprintsPage = lazy(() => import('./SprintsPage'))
const RACIPage = lazy(() => import('./RACIPage'))
const UATPage = lazy(() => import('./UATPage'))
const MilestoneBillingPage = lazy(() => import('./MilestoneBillingPage'))
const FinanzasDelProyecto = lazy(() => import('../components/planificador/FinanzasDelProyecto'))
const PanelValorGanado = lazy(() => import('../components/planificador/PanelValorGanado'))
const PanelIaDelProyecto = lazy(() => import('../components/planificador/PanelIaDelProyecto'))
const VistasDeTrabajo = lazy(() => import('../components/planificador/VistasDeTrabajo'))

export default function ProjectDetailPage() {
  const t = useAppT()
  const { puede } = useAuth()
  // Rev. 173: la ficha es el hub del proyecto. Cada pestaña es una entrada de
  // esta lista (id, etiqueta, icono, roles y qué pinta): añadir una pestaña es
  // añadir una entrada, sin tocar la barra ni el contenido. Las que vienen de
  // pantallas globales (Gantt, sprints, RACI, UAT, hitos) son esas mismas
  // pantallas con el proyecto fijo, no copias.
  const gestiona = puede('proyectos.gestionar')
  const TABS: PestanaDeFicha[] = [
    { id: 'overview',  label: t('project_detail.tab_overview'), icon: FolderOpen },
    { id: 'tasks',     label: t('project_detail.tab_tasks'),    icon: CheckSquare },
    { id: 'gantt',     label: t('planificador.tab_gantt'),      icon: BarChart2, render: pid => <GanttPage projectId={pid} /> },
    { id: 'sprints',   label: t('planificador.tab_sprints'),    icon: RefreshCw, render: pid => <SprintsPage projectId={pid} /> },
    { id: 'finance',   label: t('planificador.tab_finanzas'),   icon: Wallet, visible: gestiona, render: pid => <FinanzasDelProyecto projectId={pid} /> },
    { id: 'evm',       label: t('planificador.tab_evm'),        icon: Gauge, visible: gestiona, render: pid => <PanelValorGanado projectId={pid} /> },
    { id: 'milestones', label: t('planificador.tab_hitos'),     icon: Flag, visible: gestiona, render: pid => <MilestoneBillingPage projectId={pid} /> },
    { id: 'team',      label: t('project_detail.tab_team'),     icon: Users },
    { id: 'risks',     label: t('project_detail.tab_risks'),    icon: AlertTriangle },
    { id: 'raci',      label: t('planificador.tab_raci'),       icon: Shield, render: pid => <RACIPage projectId={pid} /> },
    { id: 'uat',       label: t('planificador.tab_uat'),        icon: ClipboardCheck, render: pid => <UATPage projectId={pid} /> },
    { id: 'ai',        label: t('planificador.tab_ia'),         icon: Brain, render: pid => <PanelIaDelProyecto projectId={pid} /> },
    { id: 'documents', label: t('project_detail.tab_documents'), icon: FileText },
    { id: 'lessons',   label: t('project_detail.tab_lessons'), icon: Lightbulb },
    { id: 'tech',      label: t('project_detail.tab_tech_resources'), icon: Laptop },
  ].filter(p => p.visible !== false)
  const STATUS_CFG: Record<string, { color: string; label: string }> = cfgDeEstadoDeProyecto(t)
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')
  const [editing, setEditing] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)

  const { data: project, isLoading } = useQuery<Project>({
    queryKey: ['project', id],
    queryFn: () => projectsApi.get(id!).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })

  const { mutate: guardarComoPlantilla, isPending: guardandoPlantilla } = useMutation({
    mutationFn: () => plantillasApi.desdeProyecto(id!, {}),
    onSuccess: r => toast.success(t('planificador.plantilla_creada', { nombre: r.name, n: r.tasks_exported })),
    onError: (e: unknown) => toast.error(extractErr(e, t('project_detail.save_error'))),
  })

  const { mutate: updateProject, isPending: saving } = useMutation({
    // El formulario manda `status` y `budget_amount` tal como salen de los inputs (texto).
    mutationFn: (data: EditProjectFormState) => projectsApi.update(id!, data as ProjectUpdatePayload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success(t('project_detail.project_updated'))
      setEditing(false)
    },
    onError: () => toast.error(t('project_detail.save_error')),
  })

  if (isLoading) return (
    <div className="pd-row-6">
      <Spinner size={28} />
    </div>
  )

  if (!project) return (
    <div className="pd-state-muted-2">
      <EstadoVacio icon={<SearchX size={28} />} title={t('project_detail.project_not_found')} />
    </div>
  )

  const statusCfg = STATUS_CFG[project.status || ''] || STATUS_CFG.planning
  const riskColor = RISK_COLOR[project.risk_level || ''] || 'var(--text-3)'

  return (
    <div className="pd-stack-2">
      {/* Header — sticky para mantener contexto al scroll */}
      <div className="pd-card-3">
        {/* Back + code */}
        <div className="pd-row-7">
          <Pulsable className="pd-btn-sm-2" onClick={() => navigate('/projects')}>
            <ChevronLeft size={14} /> {t('project_detail.back_projects')}
          </Pulsable>
          {project.code && (
            <>
              <span className="pd-text-2">/</span>
              <span className="u-text3-mono-xs">{project.code}</span>
            </>
          )}
        </div>

        {/* Title row */}
        <div className="pd-row-8">
          <div>
            <h1 className="pd-title-xl-em-strong">{project.name}</h1>
            <div className="pd-row-9">
              <span className="pd-box-5" style={{ '--pd-box-5-border': `1px solid ${alpha(statusCfg.color, '40')}`, '--pd-box-5-background': alpha(statusCfg.color, '18'), '--pd-box-5-color': statusCfg.color } as CSSProperties}>
                {statusCfg.label}
              </span>
              {project.risk_level && (
                <span className="pd-box-6" style={{ '--pd-box-6-border': `1px solid ${alpha(riskColor, '35')}`, '--pd-box-6-background': alpha(riskColor, '15'), '--pd-box-6-color': riskColor } as CSSProperties}>
                  {t('project_detail.risk_label')} {project.risk_level}
                </span>
              )}
              {project.pm_name && (
                <span className="u-text2-sm">{t('project_detail.pm_label')}: {project.pm_name}</span>
              )}
              {project.client_name && (
                <span className="u-text2-sm">· {project.client_name}</span>
              )}
            </div>
          </div>
          <div className="pd-row-10">
            {tab === 'overview' && !editing && (
              <Pulsable className="pd-btn-sm-3" onClick={() => setEditing(true)}>
                <Edit2 size={12} /> {t('project_detail.edit_button')}
              </Pulsable>
            )}
            <Link to={`/tasks?project_id=${project.id}`} className="pd-enlace-cabecera">
              <CheckSquare size={12} /> {t('project_detail.tab_tasks')}
            </Link>
            <Link to={`/gantt?project=${project.id}`} className="pd-enlace-cabecera pd-enlace-cabecera--acento">
              <BarChart2 size={12} /> Gantt
            </Link>
            {/* H22: shortcut a /contracts-ai con project_id pre-rellenado */}
            <Link to={`/contracts-ai?project_id=${project.id}`} className="pd-enlace-cabecera">
              <Brain size={12} /> {t('project_detail.analyze_contract_ai')}
            </Link>
            {/* Rev. 173: plantilla desde el proyecto (fases, tareas, dependencias, roles, documentos) */}
            {gestiona && (
              <Pulsable className="pd-btn-sm-4" disabled={guardandoPlantilla}
                onClick={() => guardarComoPlantilla()} title={t('planificador.guardar_como_plantilla_ayuda')}>
                <Copy size={12} /> {t('planificador.guardar_como_plantilla')}
              </Pulsable>
            )}
            {/* I27: Auto-planificar tareas del proyecto */}
            <Pulsable className="pd-btn-sm-4"
              onClick={() => setSmartScheduleOpen(true)}
              title={t('project_detail.auto_schedule_tooltip')}
            >
              <Sparkles size={12} /> {t('project_detail.auto_schedule')}
            </Pulsable>
          </div>
        </div>

        {/* Tab bar */}
        <div className="pd-row-11">
          {TABS.map(({ id: tid, label, icon: Icon }) => (
            <Pulsable className="pd-btn-ghost-base"
              key={tid}
              onClick={() => setTab(tid)}
              data-activa={tab === tid ? 'true' : undefined}
              style={{ '--pd-btn-ghost-base-border-bottom': `2px solid ${tab === tid ? 'var(--accent)' : 'transparent'}`, '--pd-btn-ghost-base-color': tab === tid ? 'var(--accent)' : 'var(--text-2)', '--pd-btn-ghost-base-font-weight': tab === tid ? '700' : '500' } as CSSProperties}
            >
              <Icon size={13} />{label}
            </Pulsable>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="pd-box-7">
        {tab === 'overview' && editing
          ? <EditProjectForm project={project} onSave={updateProject} onCancel={() => setEditing(false)} isPending={saving} />
          : tab === 'overview'  ? <OverviewTab project={project} />
          : tab === 'tasks' && id ? <Suspense fallback={<Spinner />}><VistasDeTrabajo projectId={id} /></Suspense>
          : tab === 'team'      ? <TeamTab projectId={id} />
          : tab === 'risks'     ? <RisksTab projectId={id} />
          : tab === 'documents' && id ? <DocumentosDeFicha ficha="project" id={id} preguntar />
          : tab === 'lessons' && id ? <LeccionesDelProyecto id={id} cerrado={['completed', 'closed'].includes(String(project?.status))} />
          : tab === 'tech' && id ? <RecursosTecnicosDelProyecto projectId={id} />
          : (() => {
              const pestana = TABS.find(p => p.id === tab)
              return pestana?.render && id
                ? <Suspense fallback={<Spinner />}>{pestana.render(id)}</Suspense>
                : null
            })()
        }
      </div>
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={id}
        projectName={project?.name}
      />
    </div>
  )
}
