/**
 * Icono (lucide) y tono de cada tipo de aviso.
 *
 * 16-11-2026 (campana de notificaciones): la bandeja pintaba un emoji por tipo
 * y el servidor guardaba otro en `icon`. Ahora el icono lo decide la interfaz,
 * por tipo, con lucide y en colores del tema; el campo `icon` del servidor no
 * se pinta. Lo comparten la bandeja (/inbox) y la campana de la barra superior.
 */
import type { LucideIcon } from 'lucide-react'
import {
  AlertOctagon, AlertTriangle, ArrowUpCircle, AtSign, Bell, CalendarClock, CheckCircle2,
  ClipboardList, Clock, FileText, Flag, Flame, Hourglass, Info, MessageSquare, PauseCircle,
  RefreshCw, Settings2, ShieldAlert, Ticket, TrendingDown, Wallet, XCircle, Zap,
} from 'lucide-react'

export type TonoDeAviso = 'accent' | 'success' | 'warning' | 'danger' | 'purple' | 'neutral'

export interface EstiloDeAviso {
  Icono: LucideIcon
  tono: TonoDeAviso
}

/** Avisos (`/enterprise/notifications`), por `type`. */
const POR_TIPO: Record<string, EstiloDeAviso> = {
  task_assigned:       { Icono: ClipboardList, tono: 'success' },
  task_mentioned:      { Icono: AtSign,        tono: 'accent' },
  mention:             { Icono: AtSign,        tono: 'accent' },
  task_due_soon:       { Icono: Clock,         tono: 'warning' },
  task_overdue:        { Icono: AlertTriangle, tono: 'danger' },
  sprint_started:      { Icono: RefreshCw,     tono: 'accent' },
  sprint_ending:       { Icono: Flag,          tono: 'warning' },
  expense_approved:    { Icono: CheckCircle2,  tono: 'success' },
  expense_rejected:    { Icono: XCircle,       tono: 'danger' },
  ticket_assigned:     { Icono: Ticket,        tono: 'purple' },
  ticket_created:      { Icono: Ticket,        tono: 'neutral' },
  ticket_updated:      { Icono: RefreshCw,     tono: 'neutral' },
  ticket_replied:      { Icono: MessageSquare, tono: 'accent' },
  ticket_resolved:     { Icono: CheckCircle2,  tono: 'success' },
  ticket_sla_warning:  { Icono: Hourglass,     tono: 'warning' },
  ticket_sla_breached: { Icono: AlertOctagon,  tono: 'danger' },
  ticket_escalated:    { Icono: ArrowUpCircle, tono: 'danger' },
  approval_requested:  { Icono: Hourglass,     tono: 'warning' },
  approval_done:       { Icono: CheckCircle2,  tono: 'success' },
  budget_alert:        { Icono: Wallet,        tono: 'danger' },
  budget_warning:      { Icono: Wallet,        tono: 'warning' },
  risk_escalated:      { Icono: ShieldAlert,   tono: 'danger' },
  project_risk_high:   { Icono: AlertTriangle, tono: 'danger' },
  contract_expiring:   { Icono: FileText,      tono: 'warning' },
  timesheet_reminder:  { Icono: CalendarClock, tono: 'warning' },
  timesheet_approved:  { Icono: CheckCircle2,  tono: 'success' },
  automation:          { Icono: Settings2,     tono: 'accent' },
  system:              { Icono: Info,          tono: 'neutral' },
  // Portal de clientes (`payload.tipo`)
  mensaje_del_equipo:  { Icono: MessageSquare, tono: 'accent' },
}

/** Alertas del sistema (`/alerts`), por `alert_type`. */
const POR_ALERTA: Record<string, EstiloDeAviso> = {
  budget_overrun:   { Icono: Wallet,        tono: 'danger' },
  overdue_tasks:    { Icono: Clock,         tono: 'danger' },
  capacity_risk:    { Icono: Zap,           tono: 'warning' },
  sla_breach:       { Icono: AlertOctagon,  tono: 'danger' },
  sla_risk:         { Icono: AlertTriangle, tono: 'warning' },
  low_margin:       { Icono: TrendingDown,  tono: 'warning' },
  overbudget:       { Icono: Wallet,        tono: 'danger' },
  high_utilization: { Icono: Flame,         tono: 'warning' },
  stalled_project:  { Icono: PauseCircle,   tono: 'warning' },
}

const AVISO: EstiloDeAviso = { Icono: Bell, tono: 'neutral' }
const ALERTA: EstiloDeAviso = { Icono: AlertTriangle, tono: 'danger' }

export function estiloDeAviso(tipo: string | null | undefined, esAlerta = false): EstiloDeAviso {
  if (esAlerta) return POR_ALERTA[tipo || ''] ?? ALERTA
  return POR_TIPO[tipo || ''] ?? AVISO
}

/** El color (variable del tema) de un tono. */
export const COLOR_DE_TONO: Record<TonoDeAviso, string> = {
  accent: 'var(--accent)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
  purple: 'var(--purple)',
  neutral: 'var(--text-2)',
}

/** Emojis y sus modificadores: los títulos generados por el sistema no los
 *  pintan (los avisos antiguos pueden traerlos guardados). */
const RE_EMOJI = /\p{Extended_Pictographic}|\u{FE0F}|\u{200D}|\u{20E3}/gu

export function sinEmojis(texto: string | null | undefined): string {
  return (texto ?? '').replace(RE_EMOJI, '').replace(/\s{2,}/g, ' ').trim()
}
