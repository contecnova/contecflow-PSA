// Calculo de las metricas derivadas del panel del portal de cliente (presupuesto, hitos, UAT, tickets, facturas, acciones). 23-11-2026: troceado de PortalDashboard sin cambio de comportamiento.
import { Receipt, FileSignature, FlaskConical, Lightbulb, Headphones, Sparkles, ThumbsUp } from 'lucide-react'
import { useLang } from './portalClientContext'
import { MONEDA_PORTAL_POR_DEFECTO } from './PortalUI'
import { conDefectos } from '../../utils/umbrales'
import type { DashDeliverable, DashDocument, DashFeatureRequest, DashInvoice, DashKpis, DashMilestone, DashProject, DashServiceDesk, DashSurvey, DashTicket, DashUat, PortalDashboardData, PortalProjectFull, ActionItem } from './PortalDashboardTipos'

type EntradaDelPanel = {
  dash: PortalDashboardData
  project: DashProject
  projectFull: PortalProjectFull | undefined
  invoices: DashInvoice[]
  tickets: DashTicket[]
  uats: DashUat[]
  frs: DashFeatureRequest[]
  docs: DashDocument[]
  surveys: DashSurvey[]
  t: ReturnType<typeof useLang>
}

/** Metricas derivadas del panel: mismo calculo que antes dentro del componente, sin hooks. */
export function calcularPanelDelPortal({ dash, project, projectFull, invoices, tickets, uats, frs, docs, surveys, t }: EntradaDelPanel) {
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

  return {
    kpis,
    sd,
    milestones,
    umbrales,
    horizonteHitos,
    hitoInminente,
    today,
    totalDays,
    elapsedDays,
    remainingDays,
    timePct,
    budgetPct,
    burnRate,
    burnRisk,
    spi,
    milestonesDone,
    milestonesTotal,
    milestonesPct,
    upcomingMilestones,
    delTotal,
    delAccepted,
    delDelivered,
    delRejected,
    delPlanned,
    uatPassed,
    uatFailed,
    uatPending,
    uatPassPct,
    uatOverdue,
    uatIssues,
    ticketsOpen,
    ticketsResolved,
    ticketsByPriority,
    ticketsByType,
    slaCompliance,
    csat,
    ticketTrend,
    invoicesPending,
    invoicesAwaiting,
    totalBilled,
    totalPaid,
    totalOverdue,
    collectionPct,
    currency,
    docsToSign,
    frsAwaitDecision,
    ticketsPendingClient,
    ticketsCSATPending,
    uatToRun,
    actionItems,
    totalActions,
    activity,
  }
}
