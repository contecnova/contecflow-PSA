/**
 * PortalDashboard – pizarra del cliente totalmente rediseñada.
 *
 * Combina datos de varios endpoints existentes para mostrar métricas que
 * realmente importan al cliente: salud del proyecto, progreso, presupuesto,
 * calidad (UAT), service desk + SLA, factura­ción y acciones pendientes.
 */
import { type CSSProperties, useState, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Activity, Clock, CheckCircle2, AlertTriangle,
  Wallet, Receipt, FileSignature, FlaskConical, Lightbulb, Headphones,
  TrendingUp, ArrowRight, CalendarDays, Target, Sparkles, Zap,
  ShieldCheck, TimerReset, ThumbsUp, FolderOpen, Pin,
} from 'lucide-react'
import {
  useIdiomaDelPortal,
  CLIENT_API, useLang, useClientAuth, rellenar, Badge, type SesionDeCliente,
} from './portalClientContext'
import {
  PortalPageHeader,
  PortalCard,
  PortalKpi,
  PortalSection,
  PortalEmpty,
  PortalProgress,
  PortalBadge,
  PortalButton,
  PortalBanner,
  PortalDonut,
  PortalSpark,
  PortalBars,
  formatDuration, formatMoney, MONEDA_PORTAL_POR_DEFECTO,
  type PortalIcon, metaItems,
} from './PortalUI'
import { localeActivo, fmtDate, fmtDateTime } from '../../utils/helpers'
import { conDefectos, tonoDe } from '../../utils/umbrales'
import type { Umbrales } from '../../utils/umbrales'
import type { ApiError } from '../../services/api'
import { STALE_DEFAULT_MS, STALE_SHORT_MS } from '../../constants/timings'
import './PortalDashboard.css'
import TraduccionAutomatica, { type ContenidoTraducido } from './TraduccionAutomatica'
import { px } from '../../utils/estilos'
import { Pulsable } from '../../components/ui'

// ── Lo que devuelven los endpoints del portal que usa la pizarra ─────────────
interface DashProject {
  id: string
  code?: string
  name: string
  status?: string
  start_date?: string | null
  end_date_planned?: string | null
}

interface DashKpis {
  budget_total?: number
  budget_spent?: number
  milestones_done?: number
  milestones_total?: number
  deliverables_total?: number
  uat_total?: number
}

interface DashServiceDesk {
  sla_compliance_pct?: number | null
  csat_avg?: number | null
  response_breached_open?: number
  resolution_breached_open?: number
  avg_first_response_minutes?: number | null
  avg_resolution_minutes?: number | null
}

interface DashActivity {
  type?: string
  description?: string
  date?: string | null
}

/** `GET /portal/dashboard`. */
interface PortalDashboardData {
  needs_project_selection?: boolean
  projects?: DashProject[]
  project?: DashProject | null
  message?: string
  kpis?: DashKpis
  service_desk?: DashServiceDesk
  recent_activity?: DashActivity[]
  /** Umbrales de semáforo de la empresa (19-11-2026; el portal no lee /settings/org-defaults). */
  umbrales?: Partial<Umbrales>
}

interface DashMilestone {
  id: string
  name: string
  due_date?: string | null
  is_completed?: boolean
  billing_pct?: number | null
}

interface DashDeliverable {
  id: string
  status: string
}

/** `GET /portal/project` (solo lo que usa la pizarra). */
interface PortalProjectFull {
  milestones?: DashMilestone[]
  deliverables?: DashDeliverable[]
}

interface DashInvoice {
  status: string
  client_approval_status?: string | null
  total?: number | string | null
  currency?: string
}

interface DashTicket {
  status: string
  priority?: string
  ticket_type?: string
  created_at?: string | null
  csat_requested_at?: string | null
  csat_score?: number | null
}

interface DashUat {
  status: string
  overdue?: boolean
  issues?: Array<{ status: string }>
}

interface DashFeatureRequest {
  status: string
  client_approved?: boolean | null
}

interface DashDocument {
  requires_signature?: boolean
  signed_by_client?: boolean
}

interface DashAnnouncement extends ContenidoTraducido {
  id: string
  title: string
  body?: string
  type?: string
  show_to_clients?: boolean
}

interface DashSurvey {
  status: string
}

interface ActionItem {
  count: number
  label: string
  icon: PortalIcon
  target: string
  tone: string
}

const SECTION_GAP = 24

export function PortalDashboard({ onNavigate }: { onNavigate?: (section: string) => void }) {
  const traducir = useLang()
  const t = useLang()
  const idioma = useIdiomaDelPortal()
  const tf = (k: string, v?: Record<string, string | number | null | undefined>) => rellenar(t(k), v)
  const { client, isReady }: Partial<SesionDeCliente> = useClientAuth() ?? {}
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    () => localStorage.getItem('portal_selected_project') || null
  )

  const allowedProjectIds = Array.isArray(client?.project_ids)
    ? client.project_ids.filter(Boolean) : []
  const hasList = isReady && allowedProjectIds.length > 0
  const valid = selectedProjectId && (!hasList || allowedProjectIds.includes(selectedProjectId))
  const effectiveProjectId = valid ? selectedProjectId : null

  useEffect(() => {
    if (!isReady || !selectedProjectId || !hasList || valid) return
    localStorage.removeItem('portal_selected_project')
    setSelectedProjectId(null)
  }, [hasList, valid, isReady, selectedProjectId])

  const params = effectiveProjectId ? { project_id: effectiveProjectId } : {}

  const { data: dash, isLoading } = useQuery<PortalDashboardData, ApiError>({
    queryKey: ['portal-dashboard', effectiveProjectId],
    enabled: isReady,
    queryFn: async () => {
      try {
        const r = await CLIENT_API.get('/portal/dashboard', { params })
        return r.data
      } catch (e) {
        if ((e as ApiError)?.response?.status === 403 && effectiveProjectId) {
          localStorage.removeItem('portal_selected_project')
          setSelectedProjectId(null)
          const fb = await CLIENT_API.get('/portal/dashboard')
          return fb.data
        }
        throw e
      }
    },
    retry: (n, e) => e?.response?.status !== 403 && n < 2,
    refetchOnWindowFocus: false,
  })

  // Datos auxiliares (sólo si tenemos proyecto)
  const projReady = !!dash?.project?.id
  const { data: projectFull } = useQuery<PortalProjectFull>({
    queryKey: ['portal-dashboard-project'],
    queryFn: () => CLIENT_API.get('/portal/project').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: invoices = [] } = useQuery<DashInvoice[]>({
    queryKey: ['portal-dashboard-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: tickets = [] } = useQuery<DashTicket[]>({
    queryKey: ['portal-dashboard-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: uats = [] } = useQuery<DashUat[]>({
    queryKey: ['portal-dashboard-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: frs = [] } = useQuery<DashFeatureRequest[]>({
    queryKey: ['portal-dashboard-frs'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: docs = [] } = useQuery<DashDocument[]>({
    queryKey: ['portal-dashboard-docs'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data),
    enabled: projReady, staleTime: STALE_SHORT_MS,
  })
  const { data: announcements = [] } = useQuery<DashAnnouncement[]>({
    queryKey: ['portal-dashboard-anns', idioma],
    queryFn: () => CLIENT_API.get('/sd/announcements', { params: { lang: idioma } }).then(r => r.data),
    enabled: projReady, staleTime: STALE_DEFAULT_MS,
  })
  const { data: surveys = [] } = useQuery<DashSurvey[]>({
    queryKey: ['portal-dashboard-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
    enabled: projReady, staleTime: STALE_DEFAULT_MS,
  })

  // Loading skeleton
  if (isLoading) {
    return (
      <div>
        <PortalPageHeader title={traducir('chat.loading')} icon={LayoutDashboard} />
        <div className="ds-grid-stats">
          {Array.from({ length: 8 }).map((_, i) => (
            <PortalCard key={i} className="portalda-sx1">{null}</PortalCard>
          ))}
        </div>
      </div>
    )
  }
  if (!dash) return null

  // Project picker
  if (dash.needs_project_selection) {
    return (
      <div>
        <PortalPageHeader
          title={tf('pdash_welcome', { name: client?.full_name?.split(' ')[0] || '' })}
          subtitle={tf('pdash_pick_project', { n: dash.projects?.length || 0 })}
          icon={FolderOpen}
        />
        <div className="portdash-grid-2">
          {(dash.projects || []).map(p => (
            <PortalCard key={p.id} onClick={() => { setSelectedProjectId(p.id); localStorage.setItem('portal_selected_project', p.id) }}>
              <div className="portdash-box-1">{p.code}</div>
              <div className="portdash-box-2">{p.name}</div>
              <Badge status={p.status} />
            </PortalCard>
          ))}
        </div>
      </div>
    )
  }

  if (!dash.project) {
    return (
      <div>
        <PortalPageHeader title={traducir('portaldashboard.sin_proyecto_asignado')} icon={FolderOpen} />
        <PortalEmpty
          icon={FolderOpen}
          title={traducir('portaldashboard.aun_no_tienes_acceso_a_ningun_proyecto')}
          description={dash.message || t('pdash_no_project_desc')}
        />
      </div>
    )
  }

  // ── Derived metrics ────────────────────────────────────────────────────────
  const project = dash.project
  const kpis: DashKpis = dash.kpis || {}
  const sd: DashServiceDesk = dash.service_desk || {}
  const milestones: DashMilestone[] = projectFull?.milestones || []
  const deliverables: DashDeliverable[] = projectFull?.deliverables || []
  // 19-11-2026: una definición por métrica (presupuesto, SLA, hitos) para todo el producto.
  const umbrales = conDefectos(dash.umbrales)
  const horizonteHitos = umbrales.sueltos.UMBRAL_HITOS_HORIZONTE_DIAS
  const hitoInminente = umbrales.sueltos.UMBRAL_HITOS_INMINENTE_DIAS

  const today = new Date()
  const startDate = project.start_date ? new Date(project.start_date) : null
  const endDate = project.end_date_planned ? new Date(project.end_date_planned) : null
  const totalDays = (startDate && endDate) ? Math.max(1, Math.round((+endDate - +startDate) / 86400000)) : null
  const elapsedDays = startDate ? Math.max(0, Math.round((+today - +startDate) / 86400000)) : 0
  const remainingDays = endDate ? Math.round((+endDate - +today) / 86400000) : null
  const timePct = totalDays ? Math.min(100, Math.round((elapsedDays / totalDays) * 100)) : 0

  const budgetPct = kpis.budget_total > 0 ? Math.round((kpis.budget_spent / kpis.budget_total) * 100) : 0
  const burnRate = (kpis.budget_spent && elapsedDays > 0) ? (kpis.budget_spent / elapsedDays) : 0
  const projectedTotal = totalDays ? burnRate * totalDays : null
  const burnRisk = (projectedTotal && kpis.budget_total)
    ? Math.round(((projectedTotal - kpis.budget_total) / kpis.budget_total) * 100) : null

  // SPI proxy (avance esperado vs presupuesto consumido)
  const spi = (timePct > 0 && budgetPct > 0) ? +(timePct / budgetPct).toFixed(2) : null

  const milestonesDone = kpis.milestones_done || milestones.filter(m => m.is_completed).length
  const milestonesTotal = kpis.milestones_total || milestones.length
  const milestonesPct = milestonesTotal ? Math.round((milestonesDone / milestonesTotal) * 100) : 0

  // Próximos hitos en 30 días
  const upcomingMilestones = milestones
    .filter(m => !m.is_completed && m.due_date)
    .map(m => ({ ...m, days: Math.round((+new Date(m.due_date) - +today) / 86400000) }))
    .filter(m => m.days <= horizonteHitos)
    .sort((a, b) => a.days - b.days)
    .slice(0, 4)

  // Deliverables status
  const delTotal = deliverables.length || kpis.deliverables_total || 0
  const delAccepted = deliverables.filter(d => d.status === 'accepted').length
  const delDelivered = deliverables.filter(d => d.status === 'delivered').length
  const delRejected = deliverables.filter(d => d.status === 'rejected').length
  const delPlanned = deliverables.filter(d => d.status === 'planned').length

  // UATs
  const uatTotal = uats.length || kpis.uat_total || 0
  const uatPassed = uats.filter(u => ['passed', 'conditional'].includes(u.status)).length
  const uatFailed = uats.filter(u => u.status === 'failed').length
  const uatPending = uats.filter(u => ['pending', 'in_progress'].includes(u.status)).length
  const uatPassPct = uatTotal ? Math.round((uatPassed / uatTotal) * 100) : 0
  const uatOverdue = uats.filter(u => u.overdue).length
  const uatIssues = uats.reduce((s, u) => s + (u.issues?.filter(i => i.status === 'open')?.length || 0), 0)

  // Tickets distribution & SLA
  const ticketsOpen = tickets.filter(t => !['closed', 'cancelled', 'resolved'].includes(t.status)).length
  const ticketsResolved = tickets.filter(t => ['resolved', 'closed'].includes(t.status)).length
  const ticketsByPriority = {
    p1_critical: tickets.filter(t => t.priority === 'p1_critical').length,
    p2_high:     tickets.filter(t => t.priority === 'p2_high').length,
    p3_medium:   tickets.filter(t => t.priority === 'p3_medium').length,
    p4_low:      tickets.filter(t => t.priority === 'p4_low').length,
  }
  const ticketsByType = {
    incident:        tickets.filter(t => t.ticket_type === 'incident').length,
    service_request: tickets.filter(t => t.ticket_type === 'service_request').length,
    change:          tickets.filter(t => t.ticket_type === 'change').length,
    question:        tickets.filter(t => t.ticket_type === 'question').length,
  }
  const slaCompliance = sd.sla_compliance_pct
  const csat = sd.csat_avg

  // Last 12 weeks ticket trend (computed each render — cheap)
  const ticketTrend = (() => {
    const buckets = Array(12).fill(0)
    const cutoff = new Date(today)
    cutoff.setDate(cutoff.getDate() - 7 * 12)
    tickets.forEach(tk => {
      const d = tk.created_at ? new Date(tk.created_at) : null
      if (!d || d < cutoff) return
      const weekIdx = 11 - Math.floor((+today - +d) / (7 * 86400000))
      if (weekIdx >= 0 && weekIdx < 12) buckets[weekIdx]++
    })
    return buckets
  })()

  // Invoices
  const invoicesPaid    = invoices.filter(i => i.status === 'paid')
  const invoicesPending = invoices.filter(i => ['sent', 'submitted', 'pending'].includes(i.status))
  const invoicesOverdue = invoices.filter(i => i.status === 'overdue')
  const invoicesAwaiting = invoices.filter(i => i.client_approval_status === 'pending')
  const totalBilled = invoices.reduce((s, i) => s + Number(i.total || 0), 0)
  const totalPaid   = invoicesPaid.reduce((s, i) => s + Number(i.total || 0), 0)
  const totalOverdue = invoicesOverdue.reduce((s, i) => s + Number(i.total || 0), 0)
  const collectionPct = totalBilled ? Math.round((totalPaid / totalBilled) * 100) : 0
  const currency = invoices[0]?.currency || MONEDA_PORTAL_POR_DEFECTO

  // Action items (lo que requiere atención del cliente)
  const docsToSign = docs.filter(d => d.requires_signature && !d.signed_by_client)
  const frsAwaitDecision = frs.filter(f => f.status === 'estimated' && f.client_approved == null)
  const ticketsPendingClient = tickets.filter(t => t.status === 'pending_client').length
  const ticketsCSATPending = tickets.filter(t => t.csat_requested_at && !t.csat_score).length
  const uatToRun = uats.filter(u => ['pending', 'in_progress'].includes(u.status)).length
  const pendingSurveys = surveys.filter(s => s.status === 'pending').length
  const invoicesToReview = invoicesAwaiting.length

  const candidatos: Array<ActionItem | 0 | false> = [
    docsToSign.length          && { count: docsToSign.length, label: t('pdash_act_docs'), icon: FileSignature, target: 'documents', tone: 'warning' },
    frsAwaitDecision.length    && { count: frsAwaitDecision.length, label: t('pdash_act_frs'), icon: Lightbulb, target: 'requests', tone: 'warning' },
    invoicesToReview           && { count: invoicesToReview, label: t('pdash_act_invoices'), icon: Receipt, target: 'invoices', tone: 'warning' },
    uatToRun                   && { count: uatToRun, label: t('pdash_act_uat'), icon: FlaskConical, target: 'uat', tone: 'accent' },
    ticketsPendingClient       && { count: ticketsPendingClient, label: t('pdash_act_tickets'), icon: Headphones, target: 'support', tone: 'warning' },
    ticketsCSATPending         && { count: ticketsCSATPending, label: t('pdash_act_csat'), icon: ThumbsUp, target: 'support', tone: 'accent' },
    pendingSurveys             && { count: pendingSurveys, label: t('pdash_act_surveys'), icon: Sparkles, target: 'surveys', tone: 'accent' },
  ]
  const actionItems = candidatos.filter((it): it is ActionItem => Boolean(it))

  const totalActions = actionItems.reduce((s: number, a) => s + a.count, 0)

  // Recent activity (combinar varios)
  const activity = [...(dash.recent_activity || [])].slice(0, 6)

  // Helper navigation
  const go = (s: string) => onNavigate?.(s)

  // Active outage banners
  const outages = announcements.filter(a => a.show_to_clients && a.type === 'outage')

  // Multi-project switcher
  const showProjectSwitcher = (client?.projects?.length > 1 || client?.project_ids?.length > 1)

  return (
    <div>
      <PortalPageHeader
        title={tf('pdash_hello', { name: client?.full_name?.split(' ')[0] || '' })}
        subtitle={tf('pdash_summary_of', { name: project.name })}
        icon={LayoutDashboard}
        meta={metaItems([
          project.code && { icon: <Pin size={12} />, value: project.code, color: 'var(--accent)' },
          { icon: <CalendarDays size={12} />, value: today.toLocaleDateString(localeActivo(), { weekday: 'long', day: 'numeric', month: 'long' }) },
          remainingDays != null && remainingDays >= 0 && { icon: <Clock size={12} />, value: tf('pdash_days_left', { n: remainingDays }), color: remainingDays < 14 ? 'var(--warning)' : 'var(--text-2)' },
          remainingDays != null && remainingDays < 0 && { icon: <AlertTriangle size={12} />, value: tf('pdash_days_overdue', { n: Math.abs(remainingDays) }), color: 'var(--danger)' },
        ])}
        actions={
          showProjectSwitcher ? (
            <PortalButton variant="secondary" size="sm" icon={<FolderOpen size={13} />}
              onClick={() => { setSelectedProjectId(null); localStorage.removeItem('portal_selected_project') }}>
              {traducir('portaldashboard.cambiar_proyecto')}
            </PortalButton>
          ) : null
        }
      />

      {/* Outages */}
      {/* 16-11-2026: con la marca «Traducido automáticamente» si el servidor lo tradujo. */}
      {outages.map(a => (
        <TraduccionAutomatica key={a.id} item={a}>
          {texto => (
            <PortalBanner tone="danger" icon={<AlertTriangle size={18} />}
              title={texto('title', a.title)} body={texto('body', a.body)} />
          )}
        </TraduccionAutomatica>
      ))}

      {/* ── Action items hero ─────────────────────────────────────────── */}
      {totalActions > 0 && (
        <PortalCard accent className="portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
          <div className="portdash-row-1">
            <div className="u-row-center-12">
              <div className="portdash-row-2"><Zap size={18} /></div>
              <div>
                <div className="portdash-txt-1">
                  {traducir('portaldashboard.acciones_pendientes', { n: totalActions })}
                </div>
                <div className="u-text2-sm">
                  {traducir('portaldashboard.estos_son_los_puntos_donde_el_proyecto')}
                </div>
              </div>
            </div>
          </div>
          <div className="portdash-grid-3">
            {actionItems.map((it, i) => {
              const Icon = it.icon
              return (
                <Pulsable key={i} onClick={() => go(it.target)} className="portdash-row-3">
                  <div className={`portdash-row-13 ${it.tone === 'warning' ? 'portal-dashboard-m2' : 'portal-dashboard-m3'}`}><Icon size={15} /></div>
                  <div className="u-flex1-min0">
                    <div className="u-sm-700">
                      <span className={`portdash-txt-3 ${it.tone === 'warning' ? 'portal-dashboard-m4' : 'portal-dashboard-m5'}`}>{it.count}</span> {it.label}
                    </div>
                  </div>
                  <ArrowRight size={14} aria-hidden="true" className="portalda-sx2" />
                </Pulsable>
              )
            })}
          </div>
        </PortalCard>
      )}

      {/* ── KPI grid ───────────────────────────────────────────────────── */}
      <div className="ds-grid-stats portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalKpi
          icon={Activity} tone="accent"
          label={traducir('portaldashboard.avance_temporal')}
          value={`${timePct}%`}
          sub={remainingDays != null ? (remainingDays >= 0 ? tf('pdash_days_to_delivery', { n: remainingDays }) : tf('pdash_days_past', { n: Math.abs(remainingDays) })) : t('pdash_no_dates')}
          footer={<PortalProgress value={timePct} color="var(--accent)" />}
        />
        <PortalKpi
          icon={Wallet}
          tone={tonoDe('presupuesto', budgetPct, umbrales)}
          label={traducir('uikit.presupuesto')}
          value={`${budgetPct}%`}
          sub={kpis.budget_total ? `${(kpis.budget_spent || 0).toLocaleString(localeActivo())}h / ${kpis.budget_total.toLocaleString(localeActivo())}h` : t('pdash_no_budget')}
          footer={<PortalProgress value={budgetPct} umbrales={umbrales} />}
        />
        <PortalKpi
          icon={Target} tone="accent"
          label={traducir('portaldashboard.hitos_completados')}
          value={`${milestonesDone}/${milestonesTotal}`}
          sub={tf('pdash_pct_of_plan', { n: milestonesPct })}
          footer={<PortalProgress value={milestonesPct} color="var(--accent)" />}
        />
        <PortalKpi
          icon={CheckCircle2}
          tone={delAccepted === delTotal && delTotal > 0 ? 'success' : 'default'}
          label={traducir('portaldashboard.entregables_aceptados')}
          value={`${delAccepted}/${delTotal}`}
          sub={tf('pdash_del_sub', { delivered: delDelivered, rejected: delRejected })}
        />
        <PortalKpi
          icon={FlaskConical}
          tone={uatPassPct >= 80 ? 'success' : uatPassPct >= 50 ? 'warning' : 'danger'}
          label={traducir('portaldashboard.uat_pasados')}
          value={`${uatPassPct}%`}
          sub={tf('pdash_uat_sub', { ok: uatPassed, ko: uatFailed, pending: uatPending })}
        />
        <PortalKpi
          icon={Headphones}
          tone={ticketsOpen > 5 ? 'warning' : 'default'}
          label={traducir('bi.open_tickets')}
          value={ticketsOpen}
          sub={tf('pdash_tickets_sub', { closed: ticketsResolved, waiting: ticketsPendingClient })}
        />
        <PortalKpi
          icon={ShieldCheck}
          tone={tonoDe('sla', slaCompliance, umbrales) ?? 'default'}
          label={traducir('reportes_presets.p14')}
          value={slaCompliance != null ? `${slaCompliance}%` : '—'}
          sub={tf('pdash_sla_sub', { resp: sd.response_breached_open || 0, resol: sd.resolution_breached_open || 0 })}
        />
        <PortalKpi
          icon={ThumbsUp}
          tone={csat == null ? 'default' : csat >= 4 ? 'success' : csat >= 3 ? 'warning' : 'danger'}
          label={traducir('portaldashboard.satisfaccion_csat')}
          value={csat != null ? `${csat}/5` : '—'}
          sub={ticketsCSATPending ? tf('pdash_csat_pending', { n: ticketsCSATPending }) : t('pdash_csat_rated')}
        />
      </div>

      {/* ── Health & schedule ──────────────────────────────────────────── */}
      <div className="portdash-grid-8 portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.salud_del_proyecto')} hint={t('pdash_health_hint')}>
            <div className="portdash-row-4">
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: timePct,                       color: 'var(--accent)' },
                  { value: Math.max(0, 100 - timePct),    color: 'transparent' },
                ]}
                centerTop={`${timePct}%`}
                centerBottom={t('pdash_time')}
              />
              <div className="portdash-box-3">
                <DataRow label={traducir('bpm.inicio')} value={fmtDate(project.start_date)} />
                <DataRow label={traducir('project_detail.meta_end_planned')} value={fmtDate(project.end_date_planned)} />
                <DataRow label={traducir('portaldashboard.dias_transcurridos')} value={`${elapsedDays}${totalDays ? ` / ${totalDays}` : ''}`} />
                <DataRow label={traducir('portaldashboard.spi_eficiencia')} value={spi != null ? spi : '—'}
                  tone={spi == null ? 'default' : spi >= 1 ? 'success' : spi >= 0.85 ? 'warning' : 'danger'}
                  hint={spi == null ? null : spi >= 1 ? t('pdash_on_time') : spi >= 0.85 ? t('pdash_spi_slight') : t('pdash_spi_risk')} />
                <DataRow label={traducir('portaldashboard.burn_rate')} value={burnRate ? tf('pdash_hours_per_day', { n: burnRate.toLocaleString(localeActivo(), { maximumFractionDigits: 1 }) }) : '—'} />
                {burnRisk != null && (
                  <DataRow label={traducir('portaldashboard.desviacion_proyectada')} value={`${burnRisk > 0 ? '+' : ''}${burnRisk}%`}
                    tone={burnRisk > 10 ? 'danger' : burnRisk > 0 ? 'warning' : 'success'}
                    hint={burnRisk > 10 ? t('pdash_burn_over') : burnRisk > 0 ? t('pdash_burn_warn') : t('pdash_burn_ok')} />
                )}
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.proximos_hitos')} hint={t('pdash_next60', { n: horizonteHitos })}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('roadmap')} icon={<ArrowRight size={13} />}>{t('nav_roadmap')}</PortalButton>}>
            {upcomingMilestones.length === 0 ? (
              <PortalEmpty icon={CalendarDays} title={traducir('portaldashboard.no_hay_hitos_previstos_a_corto_plazo')} />
            ) : (
              <div className="u-stack-10">
                {upcomingMilestones.map(m => {
                  const tone = m.days < 0 ? 'danger' : m.days < hitoInminente ? 'warning' : 'accent'
                  return (
                    <div key={m.id} className="u-row-center-12">
                      <div className="portdash-row-14 portal-dashboard-e6" style={{ '--portal-dashboard-background': tone === 'danger' ? 'var(--danger-bg, rgba(239,68,68,0.12))'
                          : tone === 'warning' ? 'var(--warning-bg, rgba(245,158,11,0.12))'
                          : 'var(--accent-muted)', '--portal-dashboard-color': tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : 'var(--accent)' } as CSSProperties}>{m.days < 0 ? '!' : m.days}</div>
                      <div className="u-flex1-min0">
                        <div className="portdash-box-5">{m.name}</div>
                        <div className="u-text3-xs">
                          {fmtDate(m.due_date)} · {m.days < 0 ? tf('pdash_overdue_ago', { n: Math.abs(m.days) }) : m.days === 0 ? t('pdash_today') : tf('pdash_in_days', { n: m.days })}
                          {m.billing_pct ? ` · ${tf('pdash_billing_pct', { n: m.billing_pct })}` : ''}
                        </div>
                      </div>
                      <PortalBadge tone={tone}>{m.days < 0 ? t('pdash_badge_overdue') : m.days < hitoInminente ? t('pdash_badge_soon') : t('pdash_on_time')}</PortalBadge>
                    </div>
                  )
                })}
              </div>
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Delivery quality (UAT + Deliverables) ──────────────────────── */}
      <div className="portdash-grid-8 portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.calidad_de_entrega')}
            hint={t('pdash_quality_hint')}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('uat')} icon={<ArrowRight size={13} />}>{t('nav_uat')}</PortalButton>}>
            <div className="portdash-row-5">
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: uatPassed, color: 'var(--success)' },
                  { value: uatPending, color: 'var(--accent)' },
                  { value: uatFailed, color: 'var(--danger)' },
                ]}
                centerTop={`${uatPassPct}%`}
                centerBottom={t('pdash_passed')}
              />
              <div className="portdash-box-6">
                <DataRow label={traducir('portaldashboard.sesiones_aprobadas')} value={uatPassed} tone="success" />
                <DataRow label={traducir('portaldashboard.en_curso_pendientes')} value={uatPending} tone="accent" />
                <DataRow label={traducir('portaldashboard.sesiones_rechazadas')} value={uatFailed} tone={uatFailed ? 'danger' : 'default'} />
                <DataRow label={traducir('portaldashboard.vencidas')} value={uatOverdue} tone={uatOverdue ? 'warning' : 'default'} />
                <DataRow label={traducir('portaldashboard.defectos_abiertos')} value={uatIssues} tone={uatIssues ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.estado_de_entregables')} hint={tf('pdash_deliverables_total', { n: delTotal })}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('roadmap')} icon={<ArrowRight size={13} />}>{traducir('portaldashboard.ver_roadmap')}</PortalButton>}>
            {delTotal === 0 ? (
              <PortalEmpty icon={CheckCircle2} title={traducir('portaldashboard.todavia_no_se_han_definido_entregables')} />
            ) : (
              <PortalBars items={[
                { label: t('pdash_del_accepted'),  value: delAccepted,  color: 'var(--success)' },
                { label: t('pdash_del_delivered'), value: delDelivered, color: 'var(--accent)' },
                { label: t('pdash_del_planned'),   value: delPlanned,   color: 'var(--text-3)' },
                { label: t('pdash_del_rejected'),  value: delRejected,  color: 'var(--danger)' },
              ]} />
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Service desk ───────────────────────────────────────────────── */}
      <div className="portdash-grid-8 portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.service_desk_sla')} hint={t('pdash_sd_hint')}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('support')} icon={<ArrowRight size={13} />}>{traducir('search_page.tickets')}</PortalButton>}>
            <div className="portdash-grid-4">
              <PortalBars items={[
                { label: t('pdash_p1'), value: ticketsByPriority.p1_critical, color: 'var(--danger)' },
                { label: t('pdash_p2'), value: ticketsByPriority.p2_high,     color: 'var(--orange)' },
                { label: t('pdash_p3'), value: ticketsByPriority.p3_medium,   color: 'var(--warning)' },
                { label: t('pdash_p4'), value: ticketsByPriority.p4_low,      color: 'var(--success)' },
              ]} />
              <PortalBars items={[
                { label: t('pdash_type_incident'), value: ticketsByType.incident,        color: 'var(--danger)' },
                { label: t('pdash_type_request'),  value: ticketsByType.service_request, color: 'var(--accent)' },
                { label: t('pdash_type_change'),   value: ticketsByType.change,          color: 'var(--warning)' },
                { label: t('pdash_type_question'), value: ticketsByType.question,        color: 'var(--text-3)' },
              ]} />
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.tiempos_de_respuesta_y_resolucion')} hint={t('pdash_times_hint')}>
            <div className="portdash-grid-5">
              <MetricBlock icon={TimerReset} label={traducir('portaldashboard.1_respuesta_media')} value={formatDuration(sd.avg_first_response_minutes)} tone="accent" />
              <MetricBlock icon={Clock}       label={traducir('portaldashboard.resolucion_media')}   value={formatDuration(sd.avg_resolution_minutes)}     tone="success" />
            </div>
            <DataRow label={traducir('reportes_presets.p14')} value={slaCompliance != null ? `${slaCompliance}%` : '—'} tone={tonoDe('sla', slaCompliance, umbrales) ?? 'default'} />
            <DataRow label={traducir('portaldashboard.riesgo_sla_respuesta')} value={sd.response_breached_open || 0} tone={sd.response_breached_open ? 'danger' : 'default'} />
            <DataRow label={traducir('portaldashboard.riesgo_sla_resolucion')} value={sd.resolution_breached_open || 0} tone={sd.resolution_breached_open ? 'danger' : 'default'} />
            <DataRow label={traducir('grc.retencion_tipo_tickets')} value={ticketsResolved} tone="default" />
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Trend & ageing ─────────────────────────────────────────────── */}
      <div className="portdash-grid-8 portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.tendencia_de_tickets')} hint={t('pdash_last12')}>
            <div className="portdash-row-6">
              <div className="u-flex1">
                <PortalSpark values={ticketTrend} width={280} height={56} color="var(--accent)" />
                <div className="portdash-row-7">
                  <span>{traducir('portaldashboard.hace_12_sem')}</span>
                  <span>{traducir('portaldashboard.esta_semana')}</span>
                </div>
              </div>
              <div className="portdash-box-8">
                <DataRow label={traducir('portaldashboard.total_12_sem')} value={ticketTrend.reduce((s, n) => s + n, 0)} />
                <DataRow label={traducir('portaldashboard.ultima_sem')} value={ticketTrend[ticketTrend.length - 1] || 0} />
                <DataRow label={traducir('portaldashboard.pico')} value={Math.max(...ticketTrend, 0)} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.solicitudes_de_cambio_fr')} hint={t('pdash_frs_hint')}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('requests')} icon={<ArrowRight size={13} />}>{traducir('portaldashboard.ver_todas')}</PortalButton>}>
            <div className="portdash-row-5">
              <PortalDonut
                size={110} stroke={12}
                segments={[
                  { value: frs.filter(f => f.status === 'new').length,        color: 'var(--text-3)' },
                  { value: frs.filter(f => f.status === 'reviewing').length,  color: 'var(--accent)' },
                  { value: frs.filter(f => f.status === 'estimated').length,  color: 'var(--warning)' },
                  { value: frs.filter(f => f.status === 'approved').length,   color: 'var(--success)' },
                  { value: frs.filter(f => f.status === 'rejected').length,   color: 'var(--danger)' },
                ]}
                centerTop={frs.length}
                centerBottom={t('pdash_total_short')}
              />
              <div className="portdash-box-6">
                <DataRow label={traducir('portaldashboard.nuevas_en_revision')} value={frs.filter(f => ['new', 'reviewing'].includes(f.status)).length} />
                <DataRow label={traducir('portaldashboard.con_presupuesto')} value={frs.filter(f => f.status === 'estimated').length} tone="warning" />
                <DataRow label={traducir('approvals.approved')} value={frs.filter(f => f.status === 'approved').length} tone="success" />
                <DataRow label={traducir('approvals.rejected')} value={frs.filter(f => f.status === 'rejected').length} tone="default" />
                <DataRow label={traducir('portaldashboard.esperan_tu_decision')} value={frsAwaitDecision.length} tone={frsAwaitDecision.length ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Financial ──────────────────────────────────────────────────── */}
      <div className="portdash-grid-8 portal-dashboard-e1" style={{ '--portal-dashboard-margin-bottom': px(SECTION_GAP) } as CSSProperties}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.facturacion')} hint={tf('pdash_invoices_hint', { n: invoices.length, currency })}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('invoices')} icon={<ArrowRight size={13} />}>{traducir('portaldashboard.ver_facturas')}</PortalButton>}>
            <div className="portdash-row-4">
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: totalPaid, color: 'var(--success)' },
                  { value: invoicesPending.reduce((s, i) => s + Number(i.total || 0), 0), color: 'var(--warning)' },
                  { value: totalOverdue, color: 'var(--danger)' },
                ]}
                centerTop={`${collectionPct}%`}
                centerBottom={t('pdash_collected')}
              />
              <div className="portdash-box-3">
                <DataRow label={traducir('portaldashboard.facturado_total')} value={formatMoney(totalBilled, currency)} />
                <DataRow label={traducir('invoices.total_paid')} value={formatMoney(totalPaid, currency)} tone="success" />
                <DataRow label={traducir('uat.pending')} value={formatMoney(invoicesPending.reduce((s, i) => s + Number(i.total || 0), 0), currency)} tone="warning" />
                <DataRow label={traducir('alm.status_expired')} value={formatMoney(totalOverdue, currency)} tone={totalOverdue ? 'danger' : 'default'} />
                <DataRow label={traducir('portaldashboard.por_aprobar')} value={tf('pdash_n_invoices', { n: invoicesAwaiting.length })} tone={invoicesAwaiting.length ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.proximas_facturaciones_por_hito')}
            hint={t('pdash_billing_ms_hint')}>
            {milestones.filter(m => m.billing_pct).slice(0, 5).length === 0 ? (
              <PortalEmpty icon={Receipt} title={traducir('portaldashboard.no_hay_facturacion_por_hito_configurada_en')} />
            ) : (
              <div className="u-stack-10">
                {milestones.filter(m => m.billing_pct).slice(0, 5).map(m => (
                  <div key={m.id} className="u-row-center-10">
                    <div className={`portdash-row-15 ${m.is_completed ? 'portal-dashboard-m7' : 'portal-dashboard-m8'}`}>{m.is_completed ? <CheckCircle2 size={14} /> : <Pin size={13} />}</div>
                    <div className="u-flex1-min0">
                      <div className="u-sm-700">{m.name}</div>
                      <div className="u-text3-xs">{fmtDate(m.due_date)}</div>
                    </div>
                    <PortalBadge tone={m.is_completed ? 'success' : 'warning'}>{m.billing_pct}{traducir('portaldashboard.factura')}</PortalBadge>
                  </div>
                ))}
              </div>
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Recent activity + quick links ──────────────────────────────── */}
      <div className="portdash-grid-6">
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.actividad_reciente')} hint={t('pdash_activity_hint')}>
            {activity.length === 0 ? (
              <PortalEmpty icon={Activity} title={traducir('portaldashboard.sin_actividad_reciente')} />
            ) : (
              <div className="portdash-stack-1">
                {activity.map((it, i) => {
                  const ICONS: Record<string, PortalIcon> = { deliverable: CheckCircle2, message: Headphones, uat: FlaskConical, fr: Lightbulb }
                  const Icon = ICONS[it.type] || Activity
                  return (
                    <div className={`portdash-row-16 ${i < activity.length - 1 ? 'portal-dashboard-m9' : 'portal-dashboard-m10'}`} key={i}>
                      <div className="portdash-row-8"><Icon size={14} /></div>
                      <div className="u-flex1-min0">
                        <div className="portdash-txt-2">{it.description}</div>
                        <div className="u-text3-xs-mt2">{it.date ? fmtDateTime(it.date) : ''}</div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.atajos_rapidos')}>
            <div className="u-grid2-10">
              <QuickLink onClick={() => go('support')} icon={Headphones} label={traducir('portaldashboard.abrir_ticket')} hint={t('pdash_ql_support_hint')} />
              <QuickLink onClick={() => go('requests')} icon={Lightbulb} label={traducir('portaldashboard.pedir_cambio')} hint={t('pdash_ql_requests_hint')} />
              <QuickLink onClick={() => go('uat')} icon={FlaskConical} label={traducir('client_portal.stat_pending_uat')} hint={tf('pdash_ql_uat_hint', { n: uatToRun })} />
              <QuickLink onClick={() => go('documents')} icon={FileSignature} label={traducir('docs.titulo')} hint={tf('pdash_ql_docs_hint', { n: docsToSign.length })} />
              <QuickLink onClick={() => go('invoices')} icon={Receipt} label={traducir('nav.invoices')} hint={tf('pdash_ql_invoices_hint', { n: invoicesAwaiting.length })} />
              <QuickLink onClick={() => go('roadmap')} icon={TrendingUp} label={t('nav_roadmap')} hint={t('pdash_ql_roadmap_hint')} />
            </div>
          </PortalSection>
        </PortalCard>
      </div>
    </div>
  )
}

// ── Helpers locales ──────────────────────────────────────────────────────────
function DataRow({ label, value, tone = 'default', hint }: { label: ReactNode; value: ReactNode; tone?: string; hint?: ReactNode }) {
  const color = tone === 'success' ? 'var(--success)'
    : tone === 'warning' ? 'var(--warning)'
    : tone === 'danger'  ? 'var(--danger)'
    : tone === 'accent'  ? 'var(--accent)'
    : 'var(--text-1)'
  return (
    <div className="portdash-row-9">
      <div>
        <span className="u-text2-sm">{label}</span>
        {hint && <div className="u-text3-xs">{hint}</div>}
      </div>
      <span className="portdash-txt-4 portal-dashboard-e11" style={{ '--portal-dashboard-color': color } as CSSProperties}>{value}</span>
    </div>
  )
}

function MetricBlock({ icon: Icon, label, value, tone }: { icon: PortalIcon; label: ReactNode; value: ReactNode; tone?: string }) {
  const color = tone === 'success' ? 'var(--success)' : tone === 'accent' ? 'var(--accent)' : 'var(--text-1)'
  return (
    <div className="portdash-box-9">
      <div className="portdash-row-10">
        <Icon size={12} /> {label}
      </div>
      <div className="portdash-txt-5 portal-dashboard-e11" style={{ '--portal-dashboard-color': color } as CSSProperties}>{value}</div>
    </div>
  )
}

function QuickLink({ icon: Icon, label, hint, onClick }: { icon: PortalIcon; label: ReactNode; hint?: ReactNode; onClick?: () => void }) {
  return (
    <Pulsable onClick={onClick} className="portdash-row-11">
      <div className="portdash-row-12"><Icon size={16} /></div>
      <div className="u-flex1-min0">
        <div className="u-sm-700">{label}</div>
        <div className="u-text3-xs">{hint}</div>
      </div>
      <ArrowRight size={14} className="portalda-sx2" aria-hidden="true" />
    </Pulsable>
  )
}

export default PortalDashboard
