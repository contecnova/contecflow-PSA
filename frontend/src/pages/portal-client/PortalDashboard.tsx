/**
 * PortalDashboard – pizarra del cliente totalmente rediseñada.
 *
 * Combina datos de varios endpoints existentes para mostrar métricas que
 * realmente importan al cliente: salud del proyecto, progreso, presupuesto,
 * calidad (UAT), service desk + SLA, factura­ción y acciones pendientes.
 */
import { useState, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Activity, Clock, CheckCircle2, AlertTriangle,
  Wallet, Receipt, FileSignature, FlaskConical, Lightbulb, Headphones,
  TrendingUp, ArrowRight, CalendarDays, Target, Sparkles, Zap,
  ShieldCheck, TimerReset, ThumbsUp, FolderOpen, Pin,
} from 'lucide-react'
import {
  CLIENT_API, useLang, useClientAuth, type SesionDeCliente,
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
  formatDuration, formatMoney,
  type PortalIcon, metaItems,
} from './PortalUI'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import type { ApiError } from '../../services/api'

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

interface DashAnnouncement {
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
  const { t: traducir } = useAppLang()
  const _t = useLang()
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
    enabled: projReady, staleTime: 30000,
  })
  const { data: invoices = [] } = useQuery<DashInvoice[]>({
    queryKey: ['portal-dashboard-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
    enabled: projReady, staleTime: 30000,
  })
  const { data: tickets = [] } = useQuery<DashTicket[]>({
    queryKey: ['portal-dashboard-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data),
    enabled: projReady, staleTime: 30000,
  })
  const { data: uats = [] } = useQuery<DashUat[]>({
    queryKey: ['portal-dashboard-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data),
    enabled: projReady, staleTime: 30000,
  })
  const { data: frs = [] } = useQuery<DashFeatureRequest[]>({
    queryKey: ['portal-dashboard-frs'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data),
    enabled: projReady, staleTime: 30000,
  })
  const { data: docs = [] } = useQuery<DashDocument[]>({
    queryKey: ['portal-dashboard-docs'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data),
    enabled: projReady, staleTime: 30000,
  })
  const { data: announcements = [] } = useQuery<DashAnnouncement[]>({
    queryKey: ['portal-dashboard-anns'],
    queryFn: () => CLIENT_API.get('/sd/announcements').then(r => r.data),
    enabled: projReady, staleTime: 60000,
  })
  const { data: surveys = [] } = useQuery<DashSurvey[]>({
    queryKey: ['portal-dashboard-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
    enabled: projReady, staleTime: 60000,
  })

  // Loading skeleton
  if (isLoading) {
    return (
      <div>
        <PortalPageHeader title="Cargando…" icon={LayoutDashboard} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 14 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <PortalCard key={i} style={{ height: 116, opacity: 0.5 }}>{null}</PortalCard>
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
          title={`Bienvenido, ${client?.full_name?.split(' ')[0] || ''}`}
          subtitle={`Selecciona uno de tus ${dash.projects?.length || 0} proyectos para abrir el portal.`}
          icon={FolderOpen}
        />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
          {(dash.projects || []).map(p => (
            <PortalCard key={p.id} onClick={() => { setSelectedProjectId(p.id); localStorage.setItem('portal_selected_project', p.id) }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.07em', fontFamily: 'var(--font-mono)' }}>{p.code}</div>
              <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, marginBottom: 8 }}>{p.name}</div>
              <PortalBadge tone={p.status === 'active' ? 'success' : 'default'}>{p.status}</PortalBadge>
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
          description={dash.message || 'Cuando el equipo te asigne un proyecto, lo verás aquí con todas sus métricas.'}
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
    .filter(m => m.days <= 60)
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
  const currency = invoices[0]?.currency || 'EUR'

  // Action items (lo que requiere atención del cliente)
  const docsToSign = docs.filter(d => d.requires_signature && !d.signed_by_client)
  const frsAwaitDecision = frs.filter(f => f.status === 'estimated' && f.client_approved == null)
  const ticketsPendingClient = tickets.filter(t => t.status === 'pending_client').length
  const ticketsCSATPending = tickets.filter(t => t.csat_requested_at && !t.csat_score).length
  const uatToRun = uats.filter(u => ['pending', 'in_progress'].includes(u.status)).length
  const pendingSurveys = surveys.filter(s => s.status === 'pending').length
  const invoicesToReview = invoicesAwaiting.length

  const candidatos: Array<ActionItem | 0 | false> = [
    docsToSign.length          && { count: docsToSign.length, label: 'documento(s) por firmar', icon: FileSignature, target: 'documents', tone: 'warning' },
    frsAwaitDecision.length    && { count: frsAwaitDecision.length, label: 'solicitud(es) con presupuesto que aprobar', icon: Lightbulb, target: 'requests', tone: 'warning' },
    invoicesToReview           && { count: invoicesToReview, label: 'factura(s) pendiente(s) de aprobación', icon: Receipt, target: 'invoices', tone: 'warning' },
    uatToRun                   && { count: uatToRun, label: 'UAT(s) por ejecutar', icon: FlaskConical, target: 'uat', tone: 'accent' },
    ticketsPendingClient       && { count: ticketsPendingClient, label: 'ticket(s) esperan tu respuesta', icon: Headphones, target: 'support', tone: 'warning' },
    ticketsCSATPending         && { count: ticketsCSATPending, label: 'ticket(s) con encuesta pendiente', icon: ThumbsUp, target: 'support', tone: 'accent' },
    pendingSurveys             && { count: pendingSurveys, label: 'encuesta(s) de satisfacción', icon: Sparkles, target: 'surveys', tone: 'accent' },
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
        title={`Hola, ${client?.full_name?.split(' ')[0] || ''}`}
        subtitle={`Resumen del proyecto ${project.name}.`}
        icon={LayoutDashboard}
        meta={metaItems([
          project.code && { icon: <Pin size={12} />, value: project.code, color: 'var(--accent)' },
          { icon: <CalendarDays size={12} />, value: today.toLocaleDateString(localeActivo(), { weekday: 'long', day: 'numeric', month: 'long' }) },
          remainingDays != null && remainingDays >= 0 && { icon: <Clock size={12} />, value: `${remainingDays} días restantes`, color: remainingDays < 14 ? 'var(--warning)' : 'var(--text-2)' },
          remainingDays != null && remainingDays < 0 && { icon: <AlertTriangle size={12} />, value: `${Math.abs(remainingDays)} días vencido`, color: 'var(--danger)' },
        ])}
        actions={
          showProjectSwitcher ? (
            <PortalButton variant="secondary" size="sm" icon={<FolderOpen size={13} />}
              onClick={() => { setSelectedProjectId(null); localStorage.removeItem('portal_selected_project') }}>
              Cambiar proyecto
            </PortalButton>
          ) : null
        }
      />

      {/* Outages */}
      {outages.map(a => (
        <PortalBanner key={a.id} tone="danger" icon={<AlertTriangle size={18} />}
          title={a.title} body={a.body} />
      ))}

      {/* ── Action items hero ─────────────────────────────────────────── */}
      {totalActions > 0 && (
        <PortalCard accent style={{ marginBottom: SECTION_GAP }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 38, height: 38, borderRadius: 10, background: 'var(--accent-muted)',
                color: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}><Zap size={18} /></div>
              <div>
                <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 800, color: 'var(--text-1)' }}>
                  Tienes {totalActions} {traducir('portaldashboard.accion_es_pendiente_s')}
                </div>
                <div className="u-text2-sm">
                  {traducir('portaldashboard.estos_son_los_puntos_donde_el_proyecto')}
                </div>
              </div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
            {actionItems.map((it, i) => {
              const Icon = it.icon
              return (
                <button key={i} onClick={() => go(it.target)} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 10, padding: '10px 14px',
                  cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                  color: 'var(--text-1)', transition: 'border-color 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                  <div style={{
                    width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                    background: it.tone === 'warning' ? 'var(--warning-bg, rgba(245,158,11,0.12))' : 'var(--accent-muted)',
                    color: it.tone === 'warning' ? 'var(--warning)' : 'var(--accent)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}><Icon size={15} /></div>
                  <div className="u-flex1-min0">
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: it.tone === 'warning' ? 'var(--warning)' : 'var(--accent)' }}>{it.count}</span> {it.label}
                    </div>
                  </div>
                  <ArrowRight size={14} aria-hidden="true" style={{ color: 'var(--text-3)' }} />
                </button>
              )
            })}
          </div>
        </PortalCard>
      )}

      {/* ── KPI grid ───────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: SECTION_GAP }}>
        <PortalKpi
          icon={Activity} tone="accent"
          label="Avance temporal"
          value={`${timePct}%`}
          sub={remainingDays != null ? (remainingDays >= 0 ? `${remainingDays} días para entrega` : `${Math.abs(remainingDays)} días pasada la fecha`) : 'Sin fechas'}
          footer={<PortalProgress value={timePct} color="var(--accent)" />}
        />
        <PortalKpi
          icon={Wallet}
          tone={budgetPct > 90 ? 'danger' : budgetPct > 75 ? 'warning' : 'success'}
          label="Presupuesto"
          value={`${budgetPct}%`}
          sub={kpis.budget_total ? `${(kpis.budget_spent || 0).toLocaleString(localeActivo())}h / ${kpis.budget_total.toLocaleString(localeActivo())}h` : 'Sin presupuesto'}
          footer={<PortalProgress value={budgetPct} />}
        />
        <PortalKpi
          icon={Target} tone="purple"
          label="Hitos completados"
          value={`${milestonesDone}/${milestonesTotal}`}
          sub={`${milestonesPct}% del plan`}
          footer={<PortalProgress value={milestonesPct} color="var(--purple, #7c3aed)" />}
        />
        <PortalKpi
          icon={CheckCircle2}
          tone={delAccepted === delTotal && delTotal > 0 ? 'success' : 'default'}
          label="Entregables aceptados"
          value={`${delAccepted}/${delTotal}`}
          sub={`${delDelivered} pendientes UAT · ${delRejected} rechazados`}
        />
        <PortalKpi
          icon={FlaskConical}
          tone={uatPassPct >= 80 ? 'success' : uatPassPct >= 50 ? 'warning' : 'danger'}
          label="UAT pasados"
          value={`${uatPassPct}%`}
          sub={`${uatPassed} ok · ${uatFailed} ko · ${uatPending} pendientes`}
        />
        <PortalKpi
          icon={Headphones}
          tone={ticketsOpen > 5 ? 'warning' : 'default'}
          label="Tickets abiertos"
          value={ticketsOpen}
          sub={`${ticketsResolved} cerrados · ${ticketsPendingClient} esperan a ti`}
        />
        <PortalKpi
          icon={ShieldCheck}
          tone={slaCompliance == null ? 'default' : slaCompliance >= 90 ? 'success' : slaCompliance >= 75 ? 'warning' : 'danger'}
          label="Cumplimiento SLA"
          value={slaCompliance != null ? `${slaCompliance}%` : '—'}
          sub={`Riesgo: ${sd.response_breached_open || 0} resp · ${sd.resolution_breached_open || 0} resol`}
        />
        <PortalKpi
          icon={ThumbsUp}
          tone={csat == null ? 'default' : csat >= 4 ? 'success' : csat >= 3 ? 'warning' : 'danger'}
          label={traducir('portaldashboard.satisfaccion_csat')}
          value={csat != null ? `${csat}/5` : '—'}
          sub={ticketsCSATPending ? `${ticketsCSATPending} encuestas pendientes` : 'Tickets valorados'}
        />
      </div>

      {/* ── Health & schedule ──────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: SECTION_GAP }}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.salud_del_proyecto')} hint="Plazo, presupuesto y eficiencia (SPI)">
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: timePct,                       color: 'var(--accent)' },
                  { value: Math.max(0, 100 - timePct),    color: 'transparent' },
                ]}
                centerTop={`${timePct}%`}
                centerBottom="tiempo"
              />
              <div style={{ flex: 1, minWidth: 200 }}>
                <DataRow label="Inicio" value={project.start_date || '—'} />
                <DataRow label="Fin previsto" value={project.end_date_planned || '—'} />
                <DataRow label={traducir('portaldashboard.dias_transcurridos')} value={`${elapsedDays}${totalDays ? ` / ${totalDays}` : ''}`} />
                <DataRow label="SPI (eficiencia)" value={spi != null ? spi : '—'}
                  tone={spi == null ? 'default' : spi >= 1 ? 'success' : spi >= 0.85 ? 'warning' : 'danger'}
                  hint={spi == null ? null : spi >= 1 ? 'En plazo' : spi >= 0.85 ? 'Ligero retraso' : 'Riesgo de retraso'} />
                <DataRow label="Burn rate" value={burnRate ? `${burnRate.toFixed(1)} h/día` : '—'} />
                {burnRisk != null && (
                  <DataRow label={traducir('portaldashboard.desviacion_proyectada')} value={`${burnRisk > 0 ? '+' : ''}${burnRisk}%`}
                    tone={burnRisk > 10 ? 'danger' : burnRisk > 0 ? 'warning' : 'success'}
                    hint={burnRisk > 10 ? 'Sobreconsumo previsto' : burnRisk > 0 ? 'Aviso temprano' : 'Bajo control'} />
                )}
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.proximos_hitos')} hint="Lo que viene en los próximos 60 días"
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('roadmap')} icon={<ArrowRight size={13} />}>Roadmap</PortalButton>}>
            {upcomingMilestones.length === 0 ? (
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', padding: '8px 0' }}>{traducir('portaldashboard.no_hay_hitos_previstos_a_corto_plazo')}</div>
            ) : (
              <div className="u-stack-10">
                {upcomingMilestones.map(m => {
                  const tone = m.days < 0 ? 'danger' : m.days < 7 ? 'warning' : 'accent'
                  return (
                    <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                        background: tone === 'danger' ? 'var(--danger-bg, rgba(239,68,68,0.12))'
                          : tone === 'warning' ? 'var(--warning-bg, rgba(245,158,11,0.12))'
                          : 'var(--accent-muted)',
                        color: tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : 'var(--accent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)',
                        fontWeight: 800, fontSize: 'var(--text-sm)',
                      }}>{m.days < 0 ? '!' : m.days}</div>
                      <div className="u-flex1-min0">
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.name}</div>
                        <div className="u-text3-xs">
                          {m.due_date} · {m.days < 0 ? `vencido hace ${Math.abs(m.days)}d` : m.days === 0 ? 'hoy' : `en ${m.days}d`}
                          {m.billing_pct ? ` · facturación ${m.billing_pct}%` : ''}
                        </div>
                      </div>
                      <PortalBadge tone={tone}>{m.days < 0 ? 'Vencido' : m.days < 7 ? 'Pronto' : 'En plazo'}</PortalBadge>
                    </div>
                  )
                })}
              </div>
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Delivery quality (UAT + Deliverables) ──────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: SECTION_GAP }}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.calidad_de_entrega')}
            hint="UAT y entregables aceptados"
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('uat')} icon={<ArrowRight size={13} />}>UAT</PortalButton>}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: uatPassed, color: 'var(--success, #10b981)' },
                  { value: uatPending, color: 'var(--accent)' },
                  { value: uatFailed, color: 'var(--danger)' },
                ]}
                centerTop={`${uatPassPct}%`}
                centerBottom="UAT ok"
              />
              <div style={{ flex: 1, minWidth: 180 }}>
                <DataRow label="Sesiones aprobadas" value={uatPassed} tone="success" />
                <DataRow label="En curso / pendientes" value={uatPending} tone="accent" />
                <DataRow label="Sesiones rechazadas" value={uatFailed} tone={uatFailed ? 'danger' : 'default'} />
                <DataRow label="Vencidas" value={uatOverdue} tone={uatOverdue ? 'warning' : 'default'} />
                <DataRow label="Defectos abiertos" value={uatIssues} tone={uatIssues ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.estado_de_entregables')} hint={`${delTotal} entregables totales`}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('roadmap')} icon={<ArrowRight size={13} />}>Ver roadmap</PortalButton>}>
            <PortalBars items={[
              { label: 'Aceptados',    value: delAccepted,  color: 'var(--success)' },
              { label: 'Entregados (pendiente revisión)', value: delDelivered, color: 'var(--accent)' },
              { label: 'Planificados', value: delPlanned,   color: 'var(--text-3)' },
              { label: 'Rechazados',   value: delRejected,  color: 'var(--danger)' },
            ]} />
            {delTotal === 0 && (
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginTop: 8 }}>{traducir('portaldashboard.todavia_no_se_han_definido_entregables')}</div>
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Service desk ───────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: SECTION_GAP }}>
        <PortalCard>
          <PortalSection title="Service Desk · SLA" hint="Distribución por prioridad e impacto"
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('support')} icon={<ArrowRight size={13} />}>Tickets</PortalButton>}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <PortalBars items={[
                { label: 'P1 Crítico', value: ticketsByPriority.p1_critical, color: 'var(--danger)' },
                { label: 'P2 Alto',    value: ticketsByPriority.p2_high,     color: 'var(--orange)' },
                { label: 'P3 Medio',   value: ticketsByPriority.p3_medium,   color: 'var(--warning)' },
                { label: 'P4 Bajo',    value: ticketsByPriority.p4_low,      color: 'var(--success)' },
              ]} />
              <PortalBars items={[
                { label: 'Incidencias', value: ticketsByType.incident,        color: 'var(--danger)' },
                { label: 'Solicitudes', value: ticketsByType.service_request, color: 'var(--accent)' },
                { label: 'Cambios',     value: ticketsByType.change,          color: 'var(--purple, #7c3aed)' },
                { label: 'Consultas',   value: ticketsByType.question,        color: 'var(--text-3)' },
              ]} />
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.tiempos_de_respuesta_y_resolucion')} hint="Promedios sobre tus tickets">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 14 }}>
              <MetricBlock icon={TimerReset} label="1ª respuesta media" value={formatDuration(sd.avg_first_response_minutes)} tone="accent" />
              <MetricBlock icon={Clock}       label={traducir('portaldashboard.resolucion_media')}   value={formatDuration(sd.avg_resolution_minutes)}     tone="success" />
            </div>
            <DataRow label="Cumplimiento SLA" value={slaCompliance != null ? `${slaCompliance}%` : '—'} tone={slaCompliance == null ? 'default' : slaCompliance >= 90 ? 'success' : 'warning'} />
            <DataRow label="Riesgo SLA respuesta" value={sd.response_breached_open || 0} tone={sd.response_breached_open ? 'danger' : 'default'} />
            <DataRow label={traducir('portaldashboard.riesgo_sla_resolucion')} value={sd.resolution_breached_open || 0} tone={sd.resolution_breached_open ? 'danger' : 'default'} />
            <DataRow label="Tickets cerrados" value={ticketsResolved} tone="default" />
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Trend & ageing ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: SECTION_GAP }}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.tendencia_de_tickets')} hint="Últimas 12 semanas">
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 14, marginTop: 6 }}>
              <div className="u-flex1">
                <PortalSpark values={ticketTrend} width={280} height={56} color="var(--accent)" />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>
                  <span>hace 12 sem</span>
                  <span>{traducir('portaldashboard.esta_semana')}</span>
                </div>
              </div>
              <div style={{ minWidth: 120 }}>
                <DataRow label="Total 12 sem" value={ticketTrend.reduce((s, n) => s + n, 0)} />
                <DataRow label={traducir('portaldashboard.ultima_sem')} value={ticketTrend[ticketTrend.length - 1] || 0} />
                <DataRow label="Pico" value={Math.max(...ticketTrend, 0)} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.solicitudes_de_cambio_fr')} hint="Estado actual de tus peticiones"
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('requests')} icon={<ArrowRight size={13} />}>{traducir('portaldashboard.ver_todas')}</PortalButton>}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
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
                centerBottom="totales"
              />
              <div style={{ flex: 1, minWidth: 180 }}>
                <DataRow label={traducir('portaldashboard.nuevas_en_revision')} value={frs.filter(f => ['new', 'reviewing'].includes(f.status)).length} />
                <DataRow label={traducir('portaldashboard.con_presupuesto')} value={frs.filter(f => f.status === 'estimated').length} tone="warning" />
                <DataRow label="Aprobadas" value={frs.filter(f => f.status === 'approved').length} tone="success" />
                <DataRow label="Rechazadas" value={frs.filter(f => f.status === 'rejected').length} tone="default" />
                <DataRow label={traducir('portaldashboard.esperan_tu_decision')} value={frsAwaitDecision.length} tone={frsAwaitDecision.length ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Financial ──────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: SECTION_GAP }}>
        <PortalCard>
          <PortalSection title={traducir('portaldashboard.facturacion')} hint={`${invoices.length} facturas (${currency})`}
            action={<PortalButton variant="ghost" size="sm" onClick={() => go('invoices')} icon={<ArrowRight size={13} />}>Ver facturas</PortalButton>}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <PortalDonut
                size={120} stroke={14}
                segments={[
                  { value: totalPaid, color: 'var(--success)' },
                  { value: invoicesPending.reduce((s, i) => s + Number(i.total || 0), 0), color: 'var(--warning)' },
                  { value: totalOverdue, color: 'var(--danger)' },
                ]}
                centerTop={`${collectionPct}%`}
                centerBottom="cobrado"
              />
              <div style={{ flex: 1, minWidth: 200 }}>
                <DataRow label="Facturado total" value={formatMoney(totalBilled, currency)} />
                <DataRow label="Pagado" value={formatMoney(totalPaid, currency)} tone="success" />
                <DataRow label="Pendiente" value={formatMoney(invoicesPending.reduce((s, i) => s + Number(i.total || 0), 0), currency)} tone="warning" />
                <DataRow label="Vencido" value={formatMoney(totalOverdue, currency)} tone={totalOverdue ? 'danger' : 'default'} />
                <DataRow label={traducir('portaldashboard.por_aprobar')} value={`${invoicesAwaiting.length} factura(s)`} tone={invoicesAwaiting.length ? 'warning' : 'default'} />
              </div>
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard>
          <PortalSection title={traducir('portaldashboard.proximas_facturaciones_por_hito')}
            hint="Hitos con porcentaje de facturación asociado">
            {milestones.filter(m => m.billing_pct).slice(0, 5).length === 0 ? (
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', padding: '8px 0' }}>{traducir('portaldashboard.no_hay_facturacion_por_hito_configurada_en')}</div>
            ) : (
              <div className="u-stack-10">
                {milestones.filter(m => m.billing_pct).slice(0, 5).map(m => (
                  <div key={m.id} className="u-row-center-10">
                    <div style={{
                      width: 26, height: 26, borderRadius: 999, flexShrink: 0,
                      background: m.is_completed ? 'var(--success-bg, rgba(16,185,129,0.12))' : 'var(--surface-3)',
                      color: m.is_completed ? 'var(--success)' : 'var(--text-2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>{m.is_completed ? <CheckCircle2 size={14} /> : <Pin size={13} />}</div>
                    <div className="u-flex1-min0">
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{m.name}</div>
                      <div className="u-text3-xs">{m.due_date || '—'}</div>
                    </div>
                    <PortalBadge tone={m.is_completed ? 'success' : 'warning'}>{m.billing_pct}% factura</PortalBadge>
                  </div>
                ))}
              </div>
            )}
          </PortalSection>
        </PortalCard>
      </div>

      {/* ── Recent activity + quick links ──────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <PortalCard>
          <PortalSection title="Actividad reciente" hint="Últimos eventos del proyecto">
            {activity.length === 0 ? (
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', padding: '8px 0' }}>{traducir('portaldashboard.sin_actividad_reciente')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {activity.map((it, i) => {
                  const ICONS: Record<string, PortalIcon> = { deliverable: CheckCircle2, message: Headphones, uat: FlaskConical, fr: Lightbulb }
                  const Icon = ICONS[it.type] || Activity
                  return (
                    <div key={i} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: i < activity.length - 1 ? '1px solid var(--surface-4)' : 'none' }}>
                      <div style={{
                        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                        background: 'var(--accent-muted)', color: 'var(--accent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}><Icon size={14} /></div>
                      <div className="u-flex1-min0">
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{it.description}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>{it.date?.slice(0, 16)?.replace('T', ' ')}</div>
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
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <QuickLink onClick={() => go('support')} icon={Headphones} label="Abrir ticket" hint="Service desk" />
              <QuickLink onClick={() => go('requests')} icon={Lightbulb} label="Pedir cambio" hint="Feature request" />
              <QuickLink onClick={() => go('uat')} icon={FlaskConical} label="UAT pendientes" hint={`${uatToRun} sesion(es)`} />
              <QuickLink onClick={() => go('documents')} icon={FileSignature} label="Documentos" hint={`${docsToSign.length} por firmar`} />
              <QuickLink onClick={() => go('invoices')} icon={Receipt} label="Facturas" hint={`${invoicesAwaiting.length} por aprobar`} />
              <QuickLink onClick={() => go('roadmap')} icon={TrendingUp} label="Roadmap" hint="Hitos & entregables" />
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
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '5px 0', borderBottom: '1px dashed var(--surface-4)' }}>
      <div>
        <span className="u-text2-sm">{label}</span>
        {hint && <div className="u-text3-xs">{hint}</div>}
      </div>
      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }}>{value}</span>
    </div>
  )
}

function MetricBlock({ icon: Icon, label, value, tone }: { icon: PortalIcon; label: ReactNode; value: ReactNode; tone?: string }) {
  const color = tone === 'success' ? 'var(--success)' : tone === 'accent' ? 'var(--accent)' : 'var(--text-1)'
  return (
    <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-xs)', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
        <Icon size={12} /> {label}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg-em)', fontWeight: 800, color }}>{value}</div>
    </div>
  )
}

function QuickLink({ icon: Icon, label, hint, onClick }: { icon: PortalIcon; label: ReactNode; hint?: ReactNode; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 12,
      background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
      borderRadius: 10, padding: '12px 14px',
      cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
      color: 'var(--text-1)', transition: 'border-color 0.15s',
    }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
      <div style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        background: 'var(--accent-muted)', color: 'var(--accent)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}><Icon size={16} /></div>
      <div className="u-flex1-min0">
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{label}</div>
        <div className="u-text3-xs">{hint}</div>
      </div>
      <ArrowRight size={14} style={{ color: 'var(--text-3)' }} aria-hidden="true" />
    </button>
  )
}

export default PortalDashboard
