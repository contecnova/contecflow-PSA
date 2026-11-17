/**
 * ReportsPage — informes (/reports): métricas, explorador, plantillas,
 * guardados y programados.
 *
 * 16-11-2026: pasada de diseño. Las pestañas (control segmentado) estaban
 * dentro de la cabecera: ahora Tabs bajo ella. Fuera todos los emojis (iconos
 * de categoría, de plantilla, de frecuencia, etiquetas de filtro, botones
 * CSV/PNG/PDF/papelera) por iconos lucide; tipos de gráfico con iconos lucide;
 * resumen con KpiCard (antes cifras monoespaciadas); vacíos con EmptyState;
 * campos `ds-input` (antes grises propios); aviso de correo en lenguaje llano
 * (antes nombres de variables de entorno SMTP_*); fechas con el formateador.
 */
import { useState, useMemo, useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { analyticsApi, scheduledReportsApi, apiUrl } from '../services/api'
import type { CatalogoDeMetricas, ConsultaDeMetrica, FilaDeMetrica, OpcionesDeFiltroAnalitico, ResumenDeMetrica } from '../services/api/tipos-analitica'
import { Card, Button, Spinner, EmptyState, KpiCard, SelectorDePeriodo, Table, Tabs, type ColumnaDeTabla, Select, Pulsable, IconButton, TablaSimple, Checkbox } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { Page } from '../components/ui'
import {
  BarChart2, Grid3X3, Search, Zap, Pin, Calendar,
  Table as TableIcon, BarChartBig, Clock, Wallet, Coins, CalendarDays, Hexagon, Briefcase, Users,
  Ticket, KeyRound, Brain, Target, HeartPulse, Star, GraduationCap, GitBranch, TrendingUp, Receipt,
  ListChecks, FolderKanban, Bell, Cog, Server, Activity, Layers, LineChart as LineChartIcon,
  AreaChart as AreaChartIcon, PieChart as PieChartIcon, Donut, ScatterChart as ScatterChartIcon,
  Columns3, Download, Image, Pencil, Trash2, Plus, X, Mail, Paperclip, FileText, Pause, PlayCircle, Send,
  CalendarClock, CalendarRange, Info, ArrowRight, BarChart3, AlertTriangle, Save,
} from 'lucide-react'
import { fmtCurrency, fmtDateTime, extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { CHART_COLORS_EXTENDED, COLOR_DATO_POR_DEFECTO, alpha } from '../constants/theme'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { descripcionMetrica, etiquetaCategoriaMetrica, etiquetaMetrica } from '../i18n/catalogoMetricas'
import useMediaQuery from '../hooks/useMediaQuery'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid, AreaChart, Area, ScatterChart, Scatter,
} from 'recharts'
import { usePeriodo } from '../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo, isoConDesfase } from '../utils/periodo'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { POLL_FREQUENT_MS, STALE_5_MIN_MS, STALE_DEFAULT_MS } from '../constants/timings'
import './ReportsPage.css'
import { LEYENDA_SM_SEPARADA } from '../constants/estilosGrafico'

/** El eje es de importes si su etiqueta (la pone el servidor) lleva el simbolo o
 *  el codigo de la moneda de la empresa, o el '€' con el que la escribe hoy. */
function esEjeDeMoneda(etiqueta: string | null | undefined, m: { moneda: string; simbolo: string }): boolean {
  if (!etiqueta) return false
  return etiqueta.includes('€') || etiqueta.includes(m.simbolo) || etiqueta.includes(m.moneda)
}
// ── Colours ───────────────────────────────────────────────────────────────────
const PALETTE = CHART_COLORS_EXTENDED

// Shared style constants used across sub-components
const STATUS_COLORS: Record<string, string> = {
  ok: 'var(--success)', warning: 'var(--warning)', critical: 'var(--danger)',
  Crítico: 'var(--danger)', Alto: 'var(--warning)', Medio: 'var(--accent)', Bajo: 'var(--success)',
}
/** Nombre visible de una categoría (las desconocidas, que vienen del catálogo, se muestran tal cual). */
const etiquetaCategoria = (cat: string | undefined, t: Parameters<typeof etiquetaCategoriaMetrica>[0]) => etiquetaCategoriaMetrica(t, cat)
/** Icono lucide de cada categoría del catálogo (antes, un emoji por categoría). */
const CAT_ICONS: Record<string, LucideIcon> = { Horas: Clock, Costes: Wallet, Rentabilidad: Coins, Capacidad: CalendarDays, Proyectos: Hexagon, Negocio: Briefcase, RRHH: Users, 'Service Desk': Ticket, Agilidad: Activity, ALM: KeyRound, IA: Brain, Estrategia: Target, Bienestar: HeartPulse, OKR: Target, NPS: Star, Formación: GraduationCap, Git: GitBranch, Ingresos: TrendingUp, Gastos: Receipt, Sprints: Activity, Tareas: ListChecks, Portfolio: FolderKanban, Facturación: Receipt, Alertas: Bell, Automatizaciones: Cog, CMDB: Server }
function IconoCategoria({ cat, size = 14 }: { cat?: string; size?: number }) {
  const Icono = (cat && CAT_ICONS[cat]) || BarChart3
  return <Icono size={size} aria-hidden />
}


// ── Presets ───────────────────────────────────────────────────────────────────
const PRESETS = [
  // Horas y costes
  { id: 'p1',  label: 'reportes_presets.p1', metric: 'hours_by_month',            chart: 'area',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p2',  label: 'reportes_presets.p2', metric: 'hours_by_person',            chart: 'bar',         color: 'var(--success)', cat: 'Horas' },
  { id: 'p3',  label: 'reportes_presets.p3', metric: 'hours_heatmap',              chart: 'heatmap',     color: 'var(--accent)', cat: 'Horas' },
  { id: 'p4',  label: 'reportes_presets.p4', metric: 'hours_billable_vs_internal', chart: 'bar_stacked', color: 'var(--accent)', cat: 'Horas' },
  { id: 'p24', label: 'reportes_presets.p24', metric: 'hours_by_project',           chart: 'bar',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p25', label: 'reportes_presets.p25', metric: 'hours_by_week',              chart: 'line',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p26', label: 'reportes_presets.p26', metric: 'hours_by_department',        chart: 'pie',         color: 'var(--accent)', cat: 'Horas' },
  // Rentabilidad y costes
  { id: 'p5',  label: 'reportes_presets.p5', metric: 'margin_by_project',          chart: 'bar_grouped', color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p6',  label: 'reportes_presets.p6', metric: 'cost_vs_budget',             chart: 'bar_grouped', color: 'var(--danger)', cat: 'Rentabilidad' },
  { id: 'p7',  label: 'reportes_presets.p7', metric: 'margin_evolution',           chart: 'line',        color: 'var(--success)', cat: 'Rentabilidad' },
  { id: 'p8',  label: 'reportes_presets.p8', metric: 'budget_consumption',         chart: 'bar',         color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p27', label: 'reportes_presets.p27', metric: 'cost_by_project',            chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p28', label: 'reportes_presets.p28', metric: 'cost_by_person',             chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p29', label: 'reportes_presets.p29', metric: 'cost_by_month',              chart: 'line',        color: 'var(--danger)', cat: 'Costes' },
  // Estructura de coste (perfiles versionados, multi-país)
  { id: 'pc1', label: 'reportes_presets.pc1', metric: 'cost_per_hour_by_person',     chart: 'bar',  color: 'var(--orange)', cat: 'Costes' },
  { id: 'pc2', label: 'reportes_presets.pc2', metric: 'cost_per_hour_by_department', chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc3', label: 'reportes_presets.pc3', metric: 'cost_per_hour_by_country',    chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc4', label: 'reportes_presets.pc4', metric: 'annual_cost_by_person',    chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc5', label: 'reportes_presets.pc5', metric: 'annual_cost_by_country',      chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc6', label: 'reportes_presets.pc6', metric: 'cost_profile_coverage',       chart: 'pie',  color: 'var(--success)', cat: 'Costes' },
  { id: 'pc7', label: 'reportes_presets.pc7', metric: 'employer_cost_pct_by_country',chart: 'bar',  color: 'var(--purple)', cat: 'Costes' },
  { id: 'pc8', label: 'reportes_presets.pc8', metric: 'cost_per_hour_drift',         chart: 'line', color: 'var(--info)', cat: 'Costes' },
  // Proyectos y agilidad
  { id: 'p9',  label: 'reportes_presets.p9', metric: 'tasks_by_status',            chart: 'pie',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p10', label: 'reportes_presets.p10', metric: 'sprint_velocity',            chart: 'bar',         color: 'var(--purple)', cat: 'Agilidad' },
  { id: 'p11', label: 'reportes_presets.p11', metric: 'tasks_overdue',              chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p12', label: 'reportes_presets.p12', metric: 'tasks_lead_time',            chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  { id: 'p30', label: 'reportes_presets.p30', metric: 'tasks_by_project',           chart: 'bar',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p31', label: 'reportes_presets.p31', metric: 'projects_by_status',         chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p32', label: 'reportes_presets.p32', metric: 'projects_by_type',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p33', label: 'reportes_presets.p33', metric: 'deliverables_status',        chart: 'pie',         color: 'var(--purple)', cat: 'Proyectos' },
  { id: 'p34', label: 'reportes_presets.p34', metric: 'risks_by_level',             chart: 'pie',         color: 'var(--danger)', cat: 'Proyectos' },
  { id: 'p35', label: 'reportes_presets.p35', metric: 'tasks_by_assignee',          chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Agilidad' },
  { id: 'p36', label: 'reportes_presets.p36', metric: 'tasks_blocked_by_project',   chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p37', label: 'reportes_presets.p37', metric: 'sprint_completion_rate',     chart: 'line',        color: 'var(--success)', cat: 'Agilidad' },
  { id: 'p38', label: 'reportes_presets.p38', metric: 'change_requests_status',     chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  // Service Desk
  { id: 'p13', label: 'reportes_presets.p13', metric: 'ticket_volume_trend',        chart: 'line',        color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p14', label: 'reportes_presets.p14', metric: 'ticket_sla_compliance',      chart: 'line',        color: 'var(--success)', cat: 'Service Desk' },
  { id: 'p15', label: 'reportes_presets.p15', metric: 'ticket_resolution_time',     chart: 'bar',         color: 'var(--purple)', cat: 'Service Desk' },
  { id: 'p16', label: 'reportes_presets.p16', metric: 'ticket_csat',                chart: 'bar',         color: 'var(--warning)', cat: 'Service Desk' },
  { id: 'p39', label: 'reportes_presets.p39', metric: 'tickets_by_status',          chart: 'pie',         color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p40', label: 'reportes_presets.p40', metric: 'tickets_by_type',            chart: 'bar',         color: 'var(--info)', cat: 'Service Desk' },
  { id: 'p41', label: 'reportes_presets.p41', metric: 'tickets_by_priority',        chart: 'bar',         color: 'var(--coral)', cat: 'Service Desk' },
  { id: 'p42', label: 'reportes_presets.p42', metric: 'tickets_by_agent',          chart: 'bar_grouped', color: 'var(--accent)', cat: 'Service Desk' },
  // Negocio y RRHH
  { id: 'p17', label: 'reportes_presets.p17', metric: 'pipeline_by_stage',          chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p18', label: 'reportes_presets.p18', metric: 'win_rate_evolution',         chart: 'line',        color: 'var(--success)', cat: 'Negocio' },
  { id: 'p19', label: 'reportes_presets.p19', metric: 'revenue_by_client',          chart: 'bar',         color: 'var(--warning)', cat: 'Negocio' },
  { id: 'p20', label: 'reportes_presets.p20', metric: 'productivity_by_person',     chart: 'bar_grouped', color: 'var(--chart-lime)', cat: 'RRHH' },
  { id: 'p21', label: 'reportes_presets.p21', metric: 'absences_by_type',           chart: 'pie',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p43', label: 'reportes_presets.p43', metric: 'pipeline_evolution',         chart: 'line',        color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p44', label: 'reportes_presets.p44', metric: 'contracts_by_status',        chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p45', label: 'reportes_presets.p45', metric: 'projects_by_client',         chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p46', label: 'reportes_presets.p46', metric: 'absences_by_person',         chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p47', label: 'reportes_presets.p47', metric: 'absences_by_month',          chart: 'line',        color: 'var(--orange)', cat: 'RRHH' },
  { id: 'p48', label: 'reportes_presets.p48', metric: 'load_by_person',             chart: 'line',        color: 'var(--chart-teal)', cat: 'Capacidad' },
  { id: 'p49', label: 'reportes_presets.p49', metric: 'load_by_week',               chart: 'line',        color: 'var(--sky-blue)', cat: 'Capacidad' },
  // ALM e IA
  { id: 'p22', label: 'reportes_presets.p22', metric: 'license_cost_by_vendor',     chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p23', label: 'reportes_presets.p23', metric: 'semantic_accuracy_trend',    chart: 'line',        color: 'var(--purple)', cat: 'IA' },
  { id: 'p50', label: 'reportes_presets.p50', metric: 'license_expiry_timeline',    chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p51', label: 'reportes_presets.p51', metric: 'license_utilization',        chart: 'bar',         color: 'var(--info)', cat: 'ALM' },
  { id: 'p52', label: 'reportes_presets.p52', metric: 'assets_by_type',             chart: 'pie',         color: 'var(--sky-blue)', cat: 'ALM' },
  { id: 'p53', label: 'reportes_presets.p53', metric: 'semantic_assignments_by_mode', chart: 'pie',       color: 'var(--purple)', cat: 'IA' },
  { id: 'p54', label: 'reportes_presets.p54', metric: 'forecast_revenue',           chart: 'bar_stacked', color: 'var(--success)', cat: 'Estrategia' },
  { id: 'p55', label: 'reportes_presets.p55', metric: 'burnout_index',              chart: 'bar',         color: 'var(--orange)', cat: 'Bienestar' },
  // OKR
  { id: 'p56', label: 'reportes_presets.p56', metric: 'okr_progress_by_objective',   chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  { id: 'p57', label: 'reportes_presets.p57', metric: 'okr_kr_completion_rate',       chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  // NPS
  { id: 'p58', label: 'reportes_presets.p58', metric: 'nps_by_client',                chart: 'bar',         color: 'var(--warning)', cat: 'NPS' },
  { id: 'p59', label: 'reportes_presets.p59', metric: 'nps_trend',                    chart: 'line',        color: 'var(--warning)', cat: 'NPS' },
  { id: 'p60', label: 'reportes_presets.p60', metric: 'nps_distribution',             chart: 'pie',         color: 'var(--orange)', cat: 'NPS' },
  { id: 'p61', label: 'reportes_presets.p61', metric: 'client_health_score',          chart: 'bar',         color: 'var(--danger)', cat: 'NPS' },
  // Formación
  { id: 'p62', label: 'reportes_presets.p62', metric: 'training_completion_rate',     chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  { id: 'p63', label: 'reportes_presets.p63', metric: 'certifications_by_user',        chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  // Git
  { id: 'p64', label: 'reportes_presets.p64', metric: 'prs_by_author',                chart: 'bar',         color: 'var(--info)', cat: 'Git' },
  { id: 'p65', label: 'reportes_presets.p65', metric: 'prs_by_project',               chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p66', label: 'reportes_presets.p66', metric: 'pr_cycle_time',                chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p67', label: 'reportes_presets.p67', metric: 'deployments_by_env',           chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p68', label: 'reportes_presets.p68', metric: 'deployment_success_rate',      chart: 'bar',         color: 'var(--accent-dim)', cat: 'Git' },
  // Ingresos
  { id: 'p69', label: 'reportes_presets.p69', metric: 'revenue_recognized_by_month',  chart: 'line',        color: 'var(--success)', cat: 'Ingresos' },
  { id: 'p70', label: 'reportes_presets.p70', metric: 'revenue_by_contract',          chart: 'bar',         color: 'var(--success)', cat: 'Ingresos' },
  // Gastos
  { id: 'p71', label: 'reportes_presets.p71', metric: 'expenses_by_category',         chart: 'pie',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p72', label: 'reportes_presets.p72', metric: 'expenses_by_project',          chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p73', label: 'reportes_presets.p73', metric: 'expenses_billable_vs_internal', chart: 'pie',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p74', label: 'reportes_presets.p74', metric: 'expenses_trend',               chart: 'line',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p75', label: 'reportes_presets.p75', metric: 'expenses_pending_approval',    chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  // Sprints
  { id: 'p76', label: 'reportes_presets.p76', metric: 'sprint_velocity_trend',         chart: 'line',        color: 'var(--accent)', cat: 'Sprints' },
  { id: 'p77', label: 'reportes_presets.p77', metric: 'sprint_completion_rate',        chart: 'bar',         color: 'var(--purple)', cat: 'Sprints' },
  // Tareas
  { id: 'p78', label: 'reportes_presets.p78', metric: 'tasks_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p79', label: 'reportes_presets.p79', metric: 'tasks_by_priority',             chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p80', label: 'reportes_presets.p80', metric: 'tasks_overdue_by_assignee',     chart: 'bar',         color: 'var(--danger)', cat: 'Tareas' },
  { id: 'p81', label: 'reportes_presets.p81', metric: 'task_completion_trend',         chart: 'line',        color: 'var(--success)', cat: 'Tareas' },
  { id: 'p82', label: 'reportes_presets.p82', metric: 'tasks_by_assignee',             chart: 'bar',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p83', label: 'reportes_presets.p83', metric: 'epics_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p84', label: 'reportes_presets.p84', metric: 'milestones_on_time_rate',       chart: 'pie',         color: 'var(--info)', cat: 'Proyectos' },
  // Portfolio
  { id: 'p85', label: 'reportes_presets.p85', metric: 'portfolio_budget_usage',        chart: 'bar_stacked', color: 'var(--purple)', cat: 'Portfolio' },
  // RRHH evaluaciones
  { id: 'p86', label: 'reportes_presets.p86', metric: 'performance_scores_by_person',  chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p87', label: 'reportes_presets.p87', metric: 'performance_cycle_completion_rate', chart: 'bar',    color: 'var(--warning)', cat: 'RRHH' },
  // Horas (timesheets)
  { id: 'p88', label: 'reportes_presets.p88', metric: 'timesheets_approval_rate',      chart: 'pie',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p89', label: 'reportes_presets.p89', metric: 'timesheets_billable_hours_trend', chart: 'line',     color: 'var(--accent)', cat: 'Horas' },
  // RRHH ausencias
  { id: 'p90', label: 'reportes_presets.p90', metric: 'absences_by_type',              chart: 'pie',         color: 'var(--purple)', cat: 'RRHH' },
  { id: 'p91', label: 'reportes_presets.p91', metric: 'absences_by_person',            chart: 'bar',         color: 'var(--purple)', cat: 'RRHH' },
  // Facturación
  { id: 'p92', label: 'reportes_presets.p92', metric: 'invoices_by_status',            chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p93', label: 'reportes_presets.p93', metric: 'invoice_amount_by_month',       chart: 'line',        color: 'var(--chart-teal)', cat: 'Facturación' },
  { id: 'p94', label: 'reportes_presets.p94', metric: 'invoice_amount_by_client',      chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p95', label: 'reportes_presets.p95', metric: 'invoice_overdue_amount',        chart: 'bar',         color: 'var(--danger)', cat: 'Facturación' },
  // Alertas
  { id: 'p96', label: 'reportes_presets.p96', metric: 'alerts_by_severity',            chart: 'pie',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p97', label: 'reportes_presets.p97', metric: 'alerts_by_type',                chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p98', label: 'reportes_presets.p98', metric: 'unresolved_alerts_by_project',  chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  // Service Desk SLA
  { id: 'p99', label: 'reportes_presets.p99', metric: 'sla_breach_trend',              chart: 'line',        color: 'var(--danger)', cat: 'Service Desk' },
  { id: 'p100', label: 'reportes_presets.p100', metric: 'sla_breach_by_type',            chart: 'bar',         color: 'var(--danger)', cat: 'Service Desk' },
  // Automatizaciones
  { id: 'p101', label: 'reportes_presets.p101', metric: 'automation_success_rate',       chart: 'pie',         color: 'var(--purple)', cat: 'Automatizaciones' },
  { id: 'p102', label: 'reportes_presets.p102', metric: 'automation_run_stats',          chart: 'bar_stacked', color: 'var(--purple)', cat: 'Automatizaciones' },
  // CMDB
  { id: 'p103', label: 'reportes_presets.p103', metric: 'cmdb_items_by_status',          chart: 'pie',         color: 'var(--accent-dim)', cat: 'CMDB' },
  { id: 'p104', label: 'reportes_presets.p104', metric: 'cmdb_items_by_environment',     chart: 'bar',         color: 'var(--accent)', cat: 'CMDB' },
  { id: 'p105', label: 'reportes_presets.p105', metric: 'cmdb_items_by_type',            chart: 'pie',         color: 'var(--accent)', cat: 'CMDB' },
  // Negocio extra
  { id: 'p106', label: 'reportes_presets.p106', metric: 'clients_by_industry',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p107', label: 'reportes_presets.p107', metric: 'opportunity_by_owner',          chart: 'bar',         color: 'var(--chart-teal)', cat: 'Negocio' },
]

type Preset = typeof PRESETS[number]

/** Celda de una fila de métrica: `label`, `value`, `status` o una serie por columna. */
type MetricCell = string | number | null | undefined

type MetricRow = FilaDeMetrica
type MetricResult = ConsultaDeMetrica
type Catalogue = CatalogoDeMetricas
type FilterOptions = Partial<OpcionesDeFiltroAnalitico>

/** Configuración de un informe del explorador (lo que se guarda). */
interface ReportConfig {
  name?: string
  metric?: string
  chartType?: string
  color?: string
  dateFrom?: string
  dateTo?: string
  projectId?: string
  userId?: string
  department?: string
  topN?: number
}

/** Informe guardado en `extra.informes_guardados` de las preferencias. */
interface SavedReport extends ReportConfig {
  id: string
  savedAt?: string
}

interface UserPreferences {
  extra?: { informes_guardados?: SavedReport[]; [clave: string]: unknown }
  [clave: string]: unknown
}


interface ScheduledReportCreate {
  name: string
  metric: string
  frequency: string
  include_pdf: boolean
  recipients: string[]
}


interface TooltipEntry {
  name?: string
  value?: number | string
  color?: string
}

const CHART_TYPES: Array<{ id: string; label: string; Icon: LucideIcon }> = [
  { id: 'bar',         label: 'reportes_ui.graf_bar', Icon: BarChart3 },
  { id: 'bar_grouped', label: 'reportes_ui.graf_bar_grouped', Icon: Columns3 },
  { id: 'bar_stacked', label: 'reportes_ui.graf_bar_stacked', Icon: Layers },
  { id: 'line',        label: 'reportes_ui.graf_line', Icon: LineChartIcon },
  { id: 'area',        label: 'reportes_ui.graf_area', Icon: AreaChartIcon },
  { id: 'pie',         label: 'reportes_ui.graf_pie', Icon: PieChartIcon },
  { id: 'donut',       label: 'reportes_ui.graf_donut', Icon: Donut },
  { id: 'scatter',     label: 'reportes_ui.graf_scatter', Icon: ScatterChartIcon },
  { id: 'heatmap',     label: 'reportes_ui.graf_heatmap', Icon: Grid3X3 },
  { id: 'table',       label: 'reportes_ui.graf_table', Icon: TableIcon },
]
const ICONO_GRAFICO: Record<string, LucideIcon> = Object.fromEntries(CHART_TYPES.map(c => [c.id, c.Icon]))

// ── Tooltip customizado ───────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label, isCurrency, isPercent }: { active?: boolean; payload?: TooltipEntry[]; label?: ReactNode; isCurrency?: boolean; isPercent?: boolean }) => {
  if (!active || !payload?.length) return null
  const fmt = (v: number | string | null | undefined) => {
    if (v == null) return '—'
    if (isCurrency) return fmtCurrency(Number(v) || 0)
    if (isPercent) return `${Number(v) || 0}%`
    return typeof v === 'number' ? v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 }) : v
  }
  return (
    <div className="rep-card">
      <div className="rep-text-strong">{label}</div>
      {payload.map((p, i) => (
        <div className="rep-text rep-text-4" key={i} style={{ '--rep-text-4-color': p.color || 'var(--text-1)' } as CSSProperties}>
          {p.name}: <span className="rep-text-strong-mono">{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Heatmap component ─────────────────────────────────────────────────────────
function HeatmapChart({ data, meta }: { data: MetricRow[]; meta?: ConsultaDeMetrica['meta'] }) {
  const traducir = useAppT()
  const weeks = meta?.weeks || []
  if (!data.length || !weeks.length) return <EmptyState svgIcon={<Grid3X3 size={36} />} title={traducir('reports.sin_datos_disponibles')} />
  const maxVal = Math.max(...data.flatMap(r => weeks.map(w => Number(r[w] || 0))))
  const getColor = (v: number) => {
    if (!v) return 'var(--surface-3)'
    const pct = v / maxVal
    if (pct > 0.75) return 'var(--danger)'
    if (pct > 0.5) return 'var(--warning)'
    if (pct > 0.25) return 'var(--accent)'
    return 'var(--success)'
  }
  return (
    <div className="u-scroll-x">
      <TablaSimple claseTabla="rep-table">
        <thead>
          <tr>
            <th className="rep-th">{traducir('reportes_ui.persona')}</th>
            {weeks.map(w => <th className="rep-th-2" key={w}>{w}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map(row => (
            <tr key={row.label}>
              <td className="rep-td-sm">{row.label}</td>
              {weeks.map(w => {
                const v = Number(row[w] || 0)
                return (
                  <td className="rep-td" key={w} title={`${row.label} · ${w}: ${v}h`}>
                    <div className="rep-row" style={{ '--rep-row-color': v ? 'var(--surface-0)' : 'transparent', '--rep-row-background': getColor(v) } as CSSProperties}>
                      {v > 0 ? v : ''}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </TablaSimple>
      <div className="rep-row-muted">
        {[['var(--success)', traducir('reportes_ui.nivel_bajo')], ['var(--accent)', traducir('reportes_ui.nivel_medio')], ['var(--warning)', traducir('reportes_ui.nivel_alto')], ['var(--danger)', traducir('reportes_ui.nivel_critico')]].map(([c, l]) => (
          <div className="rep-row-2" key={l}>
            <div className="rep-box rep-box-9" style={{ '--rep-box-9-background': c } as CSSProperties} />{l}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tabla de la metrica ───────────────────────────────────────────────────────
// Auditoria 2026-11 (#41): era un `DataTable` propio que tapaba el del kit. Las
// columnas salen de la fila (la metrica decide cuales hay), asi que se monta
// sobre <Table> del kit; los numeros a la derecha y en mono como antes.
function TablaDeMetrica({ data, isCurrency, isPercent }: { data: MetricRow[]; isCurrency?: boolean; isPercent?: boolean }) {
  const traducir = useAppT()
  const fmtMoneda = useFormatoMoneda()
  if (!data.length) return <EmptyState svgIcon={<TableIcon size={36} />} title={traducir('reports.sin_datos_disponibles')} />
  const keys = Object.keys(data[0]).filter(k => k !== 'status')
  const fmt = (v: MetricCell) => {
    if (typeof v !== 'number') return v
    if (isCurrency) return fmtMoneda(v, { decimales: 0 })
    if (isPercent) return `${v.toFixed(1)}%`
    return v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })
  }
  const columnas: ColumnaDeTabla<MetricRow>[] = keys.map(k => ({
    key: k,
    label: k === 'label' ? '' : <span className="rep-box-2">{k}</span>,
    render: (v: MetricCell, row: MetricRow) => (
      <span className="rep-box-3" style={{ '--rep-box-3-text-align': k === 'label' ? 'left' : 'right', '--rep-box-3-font-family': k !== 'label' ? 'var(--font-mono)' : 'inherit', '--rep-box-3-font-weight': k === 'value' ? '700' : '400', '--rep-box-3-color': k === 'value' && row.status ? STATUS_COLORS[row.status] : 'var(--text-1)' } as CSSProperties}>
        {fmt(v)}
      </span>
    ),
  }))
  return <Table columns={columnas} data={data} />
}

// ── Chart renderer ────────────────────────────────────────────────────────────
function ChartRenderer({ data, chartType, meta, color = 'var(--accent)', height = 320 }: { data: MetricRow[]; chartType?: string; meta?: ConsultaDeMetrica['meta']; color?: string; height?: number }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  // Revisión 2026-11: un cálculo que falla lo dice; antes salía como «sin datos».
  if (meta?.error) return <EmptyState svgIcon={<BarChartBig size={36} />} title={meta.error} />
  if (!data || data.length === 0) return <EmptyState svgIcon={<BarChartBig size={36} />} title={traducir('reports.sin_datos')} description={traducir('reportes_ui.sin_datos_desc')} />

  const isCurrency = esEjeDeMoneda(meta?.y_label, fmtMoneda)
  const isPercent = meta?.y_label?.includes('%')
  const fmtY = (v: number | string) => {
    const n = Number(v) || 0
    return isCurrency ? fmtMoneda(n, { compacto: true }) : isPercent ? `${n}%` : String(n)
  }

  if (chartType === 'heatmap') return <HeatmapChart data={data} meta={meta} />
  if (chartType === 'table') return <TablaDeMetrica data={data} isCurrency={isCurrency} isPercent={isPercent} />

  if (chartType === 'pie' || chartType === 'donut') {
    return (
      <div className="rep-row-3">
        <PieChart width={300} height={height}>
          <Pie data={data} dataKey="value" nameKey="label" cx="50%" cy="50%"
            innerRadius={chartType === 'donut' ? 70 : 0} outerRadius={120}
            paddingAngle={2}>
            {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
        </PieChart>
        <div className="u-stack-8">
          {data.map((row, i) => {
            const total = data.reduce((s: number, r) => s + (r.value || 0), 0)
            const pct = total > 0 ? ((row.value / total) * 100).toFixed(1) : 0
            return (
              <div className="rep-row-4" key={i}>
                <div className="rep-box-4 rep-box-10" style={{ '--rep-box-10-background': PALETTE[i % PALETTE.length] } as CSSProperties} />
                <span className="rep-box-5">{row.label}</span>
                <span className="rep-text-strong-mono rep-text-5" style={{ '--rep-text-5-color': PALETTE[i % PALETTE.length] } as CSSProperties}>
                  {isCurrency
                    ? fmtCurrency(Number(row.value) || 0)
                    : (Number(row.value) || 0).toLocaleString(localeActivo(), { maximumFractionDigits: 1 })}
                </span>
                <span className="u-text2-xs">{pct}%</span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (chartType === 'bar_grouped') {
    const numericKeys = Object.keys(data[0] || {}).filter(k => k !== 'label' && typeof data[0][k] === 'number')
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Legend wrapperStyle={LEYENDA_SM_SEPARADA} />
          {numericKeys.map((k, i) => <Bar key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} name={k} />)}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'bar_stacked') {
    const numericKeys = Object.keys(data[0] || {}).filter(k => k !== 'label' && typeof data[0][k] === 'number')
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Legend wrapperStyle={LEYENDA_SM_SEPARADA} />
          {numericKeys.map((k, i) => <Bar key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} stackId="a" name={k} />)}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={{ fill: color, r: 4 }} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'area') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#areaGrad)" />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
          <XAxis dataKey="label" type="category" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} />
          <YAxis dataKey="value" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
          <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
          <Scatter data={data} fill={color} />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // Default: bar
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="label" tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: "var(--text-xs)", fill: 'var(--text-2)' }} tickFormatter={fmtY} width={60} />
        <Tooltip content={<CustomTooltip isCurrency={isCurrency} isPercent={isPercent} />} />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {data.map((row, i) => (
            <Cell key={i} fill={row.status ? STATUS_COLORS[row.status] || color : color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Summary bar ───────────────────────────────────────────────────────────────
function SummaryBar({ summary, meta, prevSummary }: { summary?: ResumenDeMetrica; meta?: ConsultaDeMetrica['meta']; prevSummary?: ResumenDeMetrica }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  if (!summary || !summary.total) return null
  const isCurrency = esEjeDeMoneda(meta?.y_label, fmtMoneda)
  const isPercent  = meta?.y_label?.includes('%')
  const fmt = (v: number) => isCurrency ? fmtMoneda(v, { decimales: 0 }) : isPercent ? `${v.toFixed(1)}%` : v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })

  const trend = (curr: number, prev: number | undefined) => {
    if (!prev || prev === 0) return undefined
    return Math.round(((curr - prev) / Math.abs(prev)) * 1000) / 10
  }

  const kpis = [
    { label: traducir('reportes_ui.kpi_total'), value: summary.total,  prev: prevSummary?.total },
    { label: traducir('reportes_ui.kpi_maximo'), value: summary.max,    prev: prevSummary?.max   },
    { label: traducir('reportes_ui.kpi_media'), value: summary.avg,    prev: prevSummary?.avg   },
    { label: traducir('reportes_ui.kpi_registros'), value: summary.count,  prev: prevSummary?.count, raw: true },
  ]

  return (
    <div className="ds-grid-stats rep-resumen">
      {kpis.map(({ label, value, prev, raw }) => {
        const t = trend(value, prev)
        return (
          <KpiCard key={label} label={label} value={raw ? value : fmt(value)} trend={t}
            sub={t !== undefined ? traducir('reportes_ui.vs_periodo_anterior') : undefined} />
        )
      })}
    </div>
  )
}

// ── Report panel ──────────────────────────────────────────────────────────────
function ReportPanel({ initialMetric, initialChart, onSave }: { initialMetric?: string; initialChart?: string; onSave?: (config: ReportConfig) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const narrow = useMediaQuery('(max-width: 900px)')

  const toast = useToast()
  const [metric, setMetric] = useState(initialMetric || '')
  const [chartType, setChartType] = useState(initialChart || 'bar')
  // Periodo libre (16-11-2026): antes «desde/hasta» propios con accesos de
  // 7/30 días, 3/6 meses y 1 año. Las métricas agrupan por su cuenta (día,
  // semana o mes de calendario): sin hora y sin elegir agrupación.
  const periodo = usePeriodo({ defecto: '90d', granularidades: SIN_HORA })
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [department, setDepartment] = useState('')
  const [topN, setTopN] = useState(20)
  const [color, setColor] = useState('#4f8ef7')
  const [reportName, setReportName] = useState('')

  const { data: catalogue } = useQuery<Catalogue>({ queryKey: ['analytics-catalogue'], queryFn: () => analyticsApi.catalogue().then(r => r.data).catch(() => ({})) })
  const { data: filters } = useQuery<FilterOptions>({ queryKey: ['analytics-filters'], queryFn: () => analyticsApi.filterOptions().then(r => r.data).catch(() => ({})) })

  const filtros = { project_id: projectId || undefined, user_id: userId || undefined, department: department || undefined, top_n: topN }
  const { data: result, isLoading, isFetching, error: errorConsulta } = useQuery<MetricResult | null>({
    queryKey: ['analytics-query', metric, periodo.params, projectId, userId, department, topN],
    // Un periodo no válido (422 `periodo.*`) se explica; el resto, «sin datos» como antes.
    queryFn: () => analyticsApi.query(metric, { ...periodo.params, ...filtros }).then(r => r.data)
      .catch((e: unknown) => { if (codigoDeErrorDePeriodo(e)) throw e; return null }),
    enabled: !!metric,
    retry: false,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(errorConsulta)

  // Período anterior (misma duración, justo antes) para la comparativa de SummaryBar.
  const paramsAnteriores = useMemo(() => {
    const { desde, hasta } = periodo.rango
    const duracion = hasta.getTime() - desde.getTime()
    return { desde: isoConDesfase(new Date(desde.getTime() - duracion)), hasta: isoConDesfase(desde), tz: periodo.params.tz }
  }, [periodo.rango, periodo.params.tz])

  const { data: prevResult } = useQuery<MetricResult | null>({
    queryKey: ['analytics-prev', metric, paramsAnteriores, projectId, userId, department, topN],
    queryFn: () => analyticsApi.query(metric, { ...paramsAnteriores, ...filtros }).then(r => r.data).catch(() => null),
    enabled: !!metric && !errorDePeriodo,
    staleTime: STALE_DEFAULT_MS,
    retry: false,
  })

  // Auto-set chart type from metric default
  const handleMetricChange = (m: string) => {
    setMetric(m)
    if (catalogue) {
      for (const cat of Object.values(catalogue)) {
        const found = cat.find(item => item.id === m)
        if (found) { setChartType(found.default_chart || 'bar'); break }
      }
    }
  }



  return (
    <div>
      {/* Controls bar */}
      <div className="rep-card-3">
        <div className="rep-grid" style={{ '--rep-grid-grid-template-columns': narrow ? 'repeat(2, minmax(0, 1fr))' : '2fr 1.5fr 1.5fr 1fr 1fr 1fr' } as CSSProperties}>
          {/* Metric selector */}
          <div className={narrow ? 'rep-campo-ancho' : undefined}>
            <label className="rep-ls" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('reports.metrica')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={metric} onChange={e => handleMetricChange(e.target.value)}>
              <option value="">{traducir('reports.seleccionar_metrica')}</option>
              {catalogue && Object.entries(catalogue).map(([cat, items]) => (
                <optgroup key={cat} label={etiquetaCategoria(cat, traducir)}>
                  {items.map(item => <option key={item.id} value={item.id}>{etiquetaMetrica(traducir, item.id, item.label)}</option>)}
                </optgroup>
              ))}
            </Select>
          </div>

          {/* Project filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('reportes_ui.proyecto')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={projectId} onChange={e => setProjectId(e.target.value)}>
              <option value="">{traducir('reports.todos_los_proyectos')}</option>
              {filters?.projects?.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </Select>
          </div>

          {/* User filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('reportes_ui.persona_icono')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={userId} onChange={e => setUserId(e.target.value)}>
              <option value="">{traducir('reports.todas_las_personas')}</option>
              {filters?.users?.map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
            </Select>
          </div>

          {/* Dept filter */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{traducir('reportes_ui.departamento')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={department} onChange={e => setDepartment(e.target.value)}>
              <option value="">{traducir('reports.todos')}</option>
              {filters?.departments?.map(d => <option key={d} value={d}>{d}</option>)}
            </Select>
          </div>

          {/* Top N */}
          <div>
            <label className="rep-ls" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{traducir('reportes_ui.top_n')}</label>
            <input className="ds-input" id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" min={5} max={100} value={topN} onChange={e => setTopN(+e.target.value)} />
          </div>

          {/* Color */}
          <div>
            <span className="rep-ls" id={`${idCampo}-eta746`}>{traducir('reportes_ui.color')}</span>
            <div className="rep-row-6" role="group" aria-labelledby={`${idCampo}-eta746`}>
              {PALETTE.slice(0, 5).map(c => (
                <Pulsable type="button" className={`rep-btn${color === c ? ' rep-btn--activo' : ''}`} key={c} aria-label={traducir('reportes_ui.color_n', { c })} aria-pressed={color === c} onClick={() => setColor(c)}
                  style={{ '--rep-btn-background': c } as CSSProperties}>{null}</Pulsable>
              ))}
              <input className="rep-input" type="color" aria-label={traducir('reportes_ui.color_personalizado')} value={/^#[0-9a-fA-F]{6}$/.test(color) ? color : COLOR_DATO_POR_DEFECTO} onChange={e => setColor(e.target.value)} />
            </div>
          </div>
        </div>

        <div className="rep-row-7">
          {/* Periodo (accesos rápidos y rango libre) */}
          <SelectorDePeriodo {...periodo.selector} sinGranularidad />

          {/* Chart type */}
          <div className="rep-row-9">
            {CHART_TYPES.map(ct => (
              <Pulsable type="button" className={`rep-grafico${chartType === ct.id ? ' rep-grafico--activo' : ''}`} key={ct.id} onClick={() => setChartType(ct.id)} title={traducir(ct.label)} aria-label={traducir(ct.label)} aria-pressed={chartType === ct.id}>
                <ct.Icon size={15} aria-hidden />
              </Pulsable>
            ))}
          </div>
        </div>
      </div>

      {/* Chart area */}
      {!metric ? (
        <div>
          <EmptyState icon={<BarChart3 size={28} />} title={traducir('reports.selecciona_una_metrica_para_empezar')}
            description={traducir('reportes_ui.elige_entre_metricas', { n: Object.values(catalogue || {}).flat().length || '…' })} />
          {/* Métricas populares como acceso rápido */}
          <div className="rep-grid-2">
            {[
              { id: 'hours_by_month', label: traducir('reportes_ui.m_horas_mes'), cat: 'Horas' },
              { id: 'margin_by_project', label: traducir('reportes_ui.m_margen_proyecto'), cat: 'Rentabilidad' },
              { id: 'ticket_volume_trend', label: traducir('reportes_ui.m_volumen_tickets'), cat: 'Service Desk' },
              { id: 'sprint_velocity', label: traducir('reportes_ui.m_velocidad_sprint'), cat: 'Agilidad' },
              { id: 'productivity_by_person', label: traducir('reportes_ui.m_productividad'), cat: 'RRHH' },
              { id: 'pipeline_by_stage', label: traducir('reportes_ui.m_pipeline'), cat: 'Negocio' },
              { id: 'tasks_overdue', label: traducir('reportes_ui.m_tareas_retraso'), cat: 'Agilidad' },
              { id: 'cost_vs_budget', label: traducir('reportes_ui.m_coste_presupuesto'), cat: 'Rentabilidad' },
            ].map(m => (
              <Pulsable className="rep-btn-2" key={m.id} type="button" onClick={() => handleMetricChange(m.id)}>
                <div className="rep-icono-metrica"><IconoCategoria cat={m.cat} size={18} /></div>
                <div className="u-text1-sm-600">{m.label}</div>
                <div className="rep-text-muted-2xs">{etiquetaCategoria(m.cat, traducir)}</div>
              </Pulsable>
            ))}
          </div>
        </div>
      ) : isLoading || isFetching ? (
        <div className="rep-state"><Spinner /></div>
      ) : errorDePeriodo ? (
        <EmptyState icon={<AlertTriangle size={28} />} title={traducir(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
      ) : result ? (
        <div>
          <div className="rep-row-10">
            <div className="u-min0">
              <div className="u-wrap-center-8">
                <h3 className="rep-title-lg-strong">{etiquetaMetrica(traducir, metric, result.meta?.label)}</h3>
                <StatusBadge caps={false}>
                  {etiquetaCategoria(result.meta?.category, traducir)}
                </StatusBadge>
                <span className="u-text3-xs">{traducir('reportes_ui.n_registros', { n: result.total })}</span>
              </div>
              <p className="rep-text-muted-base">{descripcionMetrica(traducir, metric, result.meta?.description)}</p>
            </div>
            <div className="u-wrap-8">
              {onSave && (
                <div className="rep-row-11">
                  <input className="ds-input rep-input-2" aria-label={traducir('reports.report_name')} value={reportName} onChange={e => setReportName(e.target.value)} placeholder={traducir('reports.report_name')} />
                  <Button size="sm" icon={<Save size={13} />} onClick={() => onSave({ name: reportName || etiquetaMetrica(traducir, metric, result.meta?.label), metric, chartType, color, dateFrom: periodo.fechas.desde, dateTo: periodo.fechas.hasta, projectId, userId, department, topN })} disabled={!metric}>{traducir('reportes_ui.guardar')}</Button>
                </div>
              )}
              <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={() => {
                // Revisión 2026-11: cada valor entre comillas (una coma o un salto de línea rompían las columnas).
                const celda = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
                const csv = [Object.keys(result.rows[0] || {}).map(celda).join(','), ...result.rows.map(r => Object.values(r).map(celda).join(','))].join('\n')
                const a = document.createElement('a'); a.href = 'data:text/csv,' + encodeURIComponent(csv); a.download = `${metric}.csv`; a.click()
              }}>CSV</Button>
              <Button size="sm" variant="secondary" icon={<Image size={13} />} onClick={() => {
                const el = document.querySelector('.recharts-wrapper') || document.querySelector('[data-chart]')
                if (!el) { toast.info(traducir('reportes_ui.elige_grafico')); return }
                import('html2canvas').then(({ default: html2canvas }) => {
                  html2canvas(el as HTMLElement).then(canvas => {
                    const a = document.createElement('a'); a.href = canvas.toDataURL(); a.download = `${metric}.png`; a.click()
                  })
                }).catch(() => toast.error(traducir('reportes_ui.error_imagen')))
              }}>PNG</Button>
            </div>
          </div>

          <SummaryBar summary={result.summary} meta={result.meta} prevSummary={prevResult?.summary} />
          <ChartRenderer data={result.rows} chartType={chartType} meta={result.meta} color={color} height={360} />

          {/* Small data table below chart */}
          {chartType !== 'table' && result.rows.length > 0 && result.rows.length <= 30 && (
            <div className="rep-text-2">
              <div className="rep-text-muted-xs-strong">{traducir('reportes_ui.datos')}</div>
              <TablaDeMetrica data={result.rows} isCurrency={esEjeDeMoneda(result.meta?.y_label, fmtMoneda)} isPercent={result.meta?.y_label?.includes('%')} />
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          icon={<AlertTriangle size={28} />}
          title={traducir('reports.plantilla_no_disponible')}
          description={traducir('reportes_ui.no_disponible_desc')}
        />
      )}
    </div>
  )
}

// ── Dashboard mode: multiple panels ──────────────────────────────────────────
function ReportsDashboard({ saved, onRemove, onOpen }: { saved: SavedReport[]; onRemove?: (id: string) => void; onOpen?: (report: SavedReport) => void }) {
  const traducir = useAppT()
  const _today = new Date().toISOString().split('T')[0]
  const _d90 = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0]

  return (
    <div className="rep-grid-3">
      {saved.map(r => (
        <Card key={r.id} className="reportsp-sx1">
          <div className="rep-row-12">
            <div className="u-md-700">{r.name}</div>
            <div className="u-row-6">
              <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => onOpen(r)}>{traducir('reportes_ui.editar')}</Button>
              <IconButton className="rep-icono rep-icono--borrar" type="button" ariaLabel={traducir('reportes_ui.eliminar_informe')} title={traducir('reportes_ui.eliminar_informe')} onClick={() => onRemove(r.id)}><Trash2 size={14} aria-hidden /></IconButton>
            </div>
          </div>
          <MiniPanel config={r} />
        </Card>
      ))}
    </div>
  )
}

function MiniPanel({ config }: { config: SavedReport }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  const { data: result, isLoading } = useQuery<MetricResult | null>({
    queryKey: ['analytics-mini', config.metric, config.dateFrom, config.dateTo, config.projectId, config.userId],
    queryFn: () => analyticsApi.query(config.metric, { date_from: config.dateFrom, date_to: config.dateTo, project_id: config.projectId || undefined, user_id: config.userId || undefined, top_n: 10 }).then(r => r.data).catch(() => null),
    enabled: !!config.metric,
    retry: false,
  })
  if (isLoading) return <div className="rep-row-13"><Spinner /></div>
  if (!result) return null
  return (
    <div>
      {result.summary?.total > 0 && (
        <div className="rep-mini-total rep-text-7" style={{ '--rep-text-7-color': config.color || 'var(--accent)' } as CSSProperties}>
          {esEjeDeMoneda(result.meta?.y_label, fmtMoneda) ? fmtMoneda(result.summary.total, { decimales: 0 }) : result.summary.total.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })}
          <span className="rep-text-muted-sm">{traducir('reportes_ui.total')}</span>
        </div>
      )}
      <ChartRenderer data={result.rows} chartType={config.chartType || 'bar'} meta={result.meta} color={config.color || 'var(--accent)'} height={160} />
    </div>
  )
}



// ── ScheduledReportsTab ────────────────────────────────────────────────────────
function ScheduledReportsTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [_editing, _setEditing] = useState(null)
  const [form, setForm] = useState({
    name: '', metric: 'hours_by_month', recipients: '',
    frequency: 'weekly', include_pdf: true,
  })

  const { data: scheduled = [], isLoading } = useQuery({
    queryKey: ['scheduled-reps'],
    queryFn: () => scheduledReportsApi.list().then(r => r.data).catch(() => []),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: ScheduledReportCreate) => scheduledReportsApi.create(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      setShowCreate(false)
      setForm({ name: '', metric: 'hours_by_month', recipients: '', frequency: 'weekly', include_pdf: true })
      toast.success(traducir('reportes_ui.programado_creado'))
    },
    onError: e => toast.error(extractErr(e, traducir('reportes_ui.error_crear'))),
  })

  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => scheduledReportsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scheduled-reps'] }); toast.success(traducir('reportes_ui.informe_eliminado')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: runNow, isPending: running } = useMutation({
    mutationFn: (id: string) => scheduledReportsApi.run(id).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      const to = data.recipients.join(', ') || '—'
      toast.success(data.status === 'queued' ? traducir('reportes_ui.envio_en_curso', { to }) : traducir('reportes_ui.informe_enviado', { to }))
    },
    onError: e => toast.error(extractErr(e, traducir('reportes_ui.error_ejecutar'))),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, val }: { id: string; val: boolean }) => scheduledReportsApi.toggle(id, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-reps'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const FREQ_LABELS: Record<string, string> = { daily: traducir('reportes_ui.frec_daily'), weekly: traducir('reportes_ui.frec_weekly'), monthly: traducir('reportes_ui.frec_monthly') }
  const FREQ_ICONS: Record<string, LucideIcon> = { daily: CalendarClock, weekly: CalendarDays, monthly: CalendarRange }

  const METRICS = [
    { id: 'hours_by_month',        label: traducir('reportes_ui.m_horas_mes') },
    { id: 'margin_by_project',     label: traducir('reportes_ui.m_margen_proyecto') },
    { id: 'ticket_volume_trend',   label: traducir('reportes_ui.m_volumen_tickets') },
    { id: 'sprint_velocity',       label: traducir('reportes_ui.m_velocidad_sprint') },
    { id: 'productivity_by_person',label: traducir('reportes_ui.m_productividad_persona') },
    { id: 'pipeline_by_stage',     label: traducir('reportes_ui.m_pipeline_etapa') },
    { id: 'tasks_overdue',         label: traducir('reportes_ui.m_tareas_vencidas') },
    { id: 'cost_vs_budget',        label: traducir('reportes_ui.m_coste_presupuesto') },
  ]


  const submitForm = () => {
    const data = {
      name:       form.name,
      metric:     form.metric,
      frequency:  form.frequency,
      include_pdf: form.include_pdf,
      recipients: form.recipients.split(',').map(r => r.trim()).filter(Boolean),
    }
    create(data)
  }

  return (
    <div>
      <div className="u-row-between-mb16">
        <div>
          <div className="rep-text-md-strong">{traducir('reportes_ui.informes_programados')}</div>
          <div className="u-text2-sm">
            {traducir('reports.envio_automatico_por_email_los_informes_se')}
          </div>
        </div>
        <Button variant={showCreate ? 'secondary' : 'primary'} icon={showCreate ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowCreate(s => !s)}>
          {showCreate ? traducir('reportes_ui.cancelar_x') : traducir('reportes_ui.nuevo_informe')}
        </Button>
      </div>

      {/* Aviso de correo */}
      <div className="rep-row-warning">
        <Info size={14} className="rep-box-6" aria-hidden />
        <span>{traducir('reportes_ui.aviso_correo')}</span>
      </div>

      {/* Formulario nuevo */}
      {showCreate && (
        <div className="rep-ps rep-box-7">
          <div className="rep-text-accent-md-strong">
            {traducir('reports.nuevo_informe_programado')}
          </div>
          <div className="rep-grid-4">
            <div>
              <label className="rep-ls-2" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('reportes_ui.nombre_req')}</label>
              <input className="ds-input" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder={traducir('reports.report_name')} />
            </div>
            <div>
              <label className="rep-ls-2" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('reports.metrica_2')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.metric} onChange={e => setForm(f => ({ ...f, metric: e.target.value }))}>
                {METRICS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </Select>
            </div>
            <div>
              <label className="rep-ls-2" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('reportes_ui.frecuencia')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
                {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            </div>
            <div>
              <label className="rep-ls-2" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{traducir('reports.destinatarios_emails_separados_por_coma')}</label>
              <input className="ds-input" id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.recipients} onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))}
                placeholder={traducir('reportes_ui.emails_ejemplo')} />
            </div>
          </div>
          <Checkbox className="rep-label-sm" checked={!!form.include_pdf}
            onChange={v => setForm(f => ({ ...f, include_pdf: v }))}
            label={traducir('reports.adjuntar_pdf_del_informe_al_email')} />
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              {traducir('common.cancel')}
            </Button>
            <Button icon={<CalendarClock size={14} />} onClick={submitForm} loading={creating}
              disabled={!form.name || !form.recipients}>
              {traducir('reportes_ui.programar')}
            </Button>
          </div>
        </div>
      )}

      {/* Lista */}
      {isLoading ? (
        <div className="rep-state-muted-2"><Spinner /></div>
      ) : scheduled.length === 0 ? (
        <EmptyState icon={<CalendarClock size={28} />} title={traducir('reports.sin_informes_programados')}
          description={traducir('reports.crea_informes_para_recibir_datos_automaticamente_por')}
          ctaLabel={traducir('reportes_ui.nuevo_informe')} onCta={() => setShowCreate(true)} />
      ) : (
        scheduled.map(rep => {
          const IconoFrecuencia = FREQ_ICONS[rep.frequency] || CalendarDays
          return (
          <div className={`rep-ps${rep.is_active ? '' : ' rep-ps--pausado'}`} key={rep.id}>
            <div className="rep-row-14">
              <div className="u-flex1-min0">
                <div className="rep-row-15">
                  <IconoFrecuencia size={16} className="rep-icono-frecuencia" aria-hidden />
                  <span className="u-md-700">{rep.name}</span>
                  {!rep.is_active && (
                    <StatusBadge kind="warning" caps={false}>{traducir('reportes_ui.pausado')}</StatusBadge>
                  )}
                  {rep.include_pdf && (
                    <StatusBadge kind="neutral" caps={false}><Paperclip size={11} aria-hidden />PDF</StatusBadge>
                  )}
                </div>
                <div className="rep-text-muted-sm-2">
                  {FREQ_LABELS[rep.frequency]} ·{' '}
                  {METRICS.find(m => m.id === rep.metric)?.label || rep.metric}
                </div>
                <div className="rep-destinatarios">
                  <Mail size={12} aria-hidden /> {(rep.recipients || []).join(', ')}
                </div>
                {(rep.last_run_at || rep.next_run_at) && (
                  <div className="rep-text-muted-2xs-2">
                    {rep.last_run_at && traducir('reportes_ui.ultimo_envio', { fecha: fmtDateTime(rep.last_run_at) })}
                    {rep.last_run_at && rep.next_run_at && ' · '}
                    {rep.next_run_at && traducir('reportes_ui.proximo', { fecha: fmtDateTime(rep.next_run_at) })}
                  </div>
                )}
              </div>
              <div className="rep-row-16">
                <Button size="xs" variant="secondary" icon={rep.is_active ? <Pause size={12} /> : <PlayCircle size={12} />} onClick={() => toggle({ id: rep.id, val: !rep.is_active })}>
                  {rep.is_active ? traducir('reportes_ui.pausar') : traducir('reportes_ui.activar')}
                </Button>
                <Button size="xs" variant="secondary" icon={<Send size={12} />} onClick={() => runNow(rep.id)} disabled={!rep.is_active} loading={running}>
                  {traducir('reportes_ui.enviar_ahora')}
                </Button>
                {/* Enlace y no el cliente: el navegador abre el PDF en otra pestaña con la cookie de sesión. */}
                <a className="rep-enlace-pdf" href={apiUrl(`/billing-reports/scheduled-reports/${rep.id}/preview-pdf`)} target="_blank"
                  rel="noopener noreferrer">
                  <FileText size={12} aria-hidden /> PDF
                </a>
                <IconButton className="rep-icono rep-icono--borrar" type="button" ariaLabel={traducir('common.delete')} title={traducir('common.delete')} onClick={() => { openConfirmGlobal({ message: traducir('reportes_ui.eliminar_confirm', { nombre: rep.name }), onConfirm: () => remove(rep.id), danger: true }) }}>
                  <Trash2 size={14} aria-hidden />
                </IconButton>
              </div>
            </div>
          </div>
          )
        })
      )}
    </div>
  )
}



// ── PresetsTab ─────────────────────────────────────────────────────────────────
function PresetsTab({ presets, supportedMetrics, onOpen }: { presets: readonly Preset[]; supportedMetrics?: Set<string> | null; onOpen?: (preset: Preset) => void }) {
  const traducir = useAppT()
  const [filterCat, setFilterCat] = useState<string>('all')
  const [searchQ, setSearchQ] = useState('')
  // When supportedMetrics is null the analytics catalogue is unavailable (e.g. 503).
  // In that case show all presets so the user can still browse and attempt to run them.
  const enabledPresets = supportedMetrics !== null
    ? presets.filter(p => supportedMetrics.has(p.metric))
    : presets
  const cats = ['all', ...new Set(enabledPresets.map(p => p.cat).filter(Boolean))]
  const byCat = filterCat === 'all' ? enabledPresets : enabledPresets.filter(p => p.cat === filterCat)
  const filtered = searchQ.trim().length < 2
    ? byCat
    : byCat.filter(p => traducir(p.label).toLowerCase().includes(searchQ.toLowerCase()) || etiquetaCategoria(p.cat, traducir).toLowerCase().includes(searchQ.toLowerCase()))

  const chartLabels: Record<string, string> = { bar: traducir('reportes_ui.graf_bar'), bar_grouped: traducir('reportes_ui.graf_agrupadas'), bar_stacked: traducir('reportes_ui.graf_apiladas'),
    line: traducir('reportes_ui.graf_line'), area: traducir('reportes_ui.graf_area'), pie: traducir('reportes_ui.graf_pie'), donut: traducir('reportes_ui.graf_donut'), heatmap: traducir('reportes_ui.graf_heatmap'), table: traducir('reportes_ui.graf_table') }

  return (
    <div>
      <div className="u-mb-12">
        <input className="ds-input" aria-label={traducir('reportes_ui.buscar_plantilla')}
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder={traducir('reportes_ui.buscar_plantilla')}
        />
      </div>
      <div className="rep-row-17">
        {cats.map(c => (
          <Pulsable className={`rep-chip${filterCat === c ? ' rep-chip--activo' : ''}`} type="button" aria-pressed={filterCat === c} key={c} onClick={() => setFilterCat(c)}>
            {c !== 'all' && <IconoCategoria cat={c} size={12} />}
            {c === 'all' ? traducir('reportes_ui.todas_n', { n: enabledPresets.length }) : etiquetaCategoria(c, traducir)}
          </Pulsable>
        ))}
      </div>
      {searchQ.trim().length >= 2 && (
        <div className="rep-text-muted-sm-3">
          {filtered.length === 0 ? traducir('reportes_ui.sin_resultados') : filtered.length === 1 ? traducir('reportes_ui.una_plantilla') : traducir('reportes_ui.n_plantillas', { n: filtered.length })}
        </div>
      )}
      <div className="rep-grid-5">
        {filtered.map(p => (
          <Pulsable className="rep-btn-3" key={p.id} type="button" onClick={() => onOpen(p)}
            style={{ '--rep-btn-3-border': `1px solid ${alpha(p.color, '25')}`, '--rep-btn-3-tono': p.color } as CSSProperties}>
            <div className="rep-icono-metrica rep-text-8" style={{ '--rep-text-8-color': p.color } as CSSProperties}><IconoCategoria cat={p.cat} size={18} /></div>
            <div className="rep-text-base-strong">{traducir(p.label)}</div>
            <div className="rep-preset-pie">
              {etiquetaCategoria(p.cat, traducir)} · {chartLabels[p.chart] || p.chart}
              <ArrowRight size={12} aria-hidden />
            </div>
          </Pulsable>
        ))}
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const traducir = useAppT()
  const t = useAppT()
  const { hasRole } = useAuth()
  // Los programados son de responsables (la API solo los sirve a ellos).
  const veProgramados = hasRole('admin', 'pm', 'team_lead', 'hr')
  const [mode, setMode] = useState<string>('explorer') // explorer | dashboard | presets
  const [editingReport, setEditingReport] = useState<ReportConfig | null>(null)
  // Revisión 2026-11: los guardados viven en las preferencias del usuario en el
  // servidor (`extra.informes_guardados`); antes, en una variable que se perdía
  // al recargar la página.
  const qc = useQueryClient()
  const toast = useToast()
  const { data: prefs } = useQuery<UserPreferences>({
    queryKey: ['user-preferences'],
    queryFn: () => api.get('/users/me/preferences').then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
  const saved: SavedReport[] = Array.isArray(prefs?.extra?.informes_guardados) ? prefs.extra.informes_guardados : []
  const guardar = useMutation({
    mutationFn: (lista: SavedReport[]) => api.patch('/users/me/preferences', { extra: { informes_guardados: lista } }),
    onMutate: (lista: SavedReport[]) => qc.setQueryData<UserPreferences>(['user-preferences'], old => ({ ...(old || {}), extra: { ...(old?.extra || {}), informes_guardados: lista } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ['user-preferences'] }),
    onError: (e: unknown) => toast.error(extractErr(e, traducir('reportes_ui.error_guardar'))),
  })

  const saveReport = (config: ReportConfig) => {
    const existing = saved.find(r => r.name === config.name)
    const report: SavedReport = { ...config, id: existing?.id || Date.now().toString(), savedAt: new Date().toISOString() }
    guardar.mutate(existing ? saved.map(r => r.id === report.id ? report : r) : [...saved, report])
  }

  const removeReport = (id: string) => guardar.mutate(saved.filter(r => r.id !== id))

  const openReport = (r: SavedReport) => { setEditingReport(r); setMode('explorer') }

  const { data: catalogue } = useQuery<Catalogue>({ queryKey: ['analytics-catalogue'], queryFn: () => analyticsApi.catalogue().then(r => r.data).catch(() => ({})) })
  const catalogueLoaded = catalogue !== undefined
  const catalogueHasData = catalogueLoaded && Object.keys(catalogue || {}).length > 0
  const totalMetrics = Object.values(catalogue || {}).flat().length
  // null means catalogue not yet loaded or unavailable — PresetsTab will show all presets
  const supportedMetrics = catalogueHasData
    ? new Set(Object.values(catalogue).flat().map(m => m.id))
    : null

  const [_schedTab, _setSchedTab] = useState('main')
  const MODES = [
    { id: 'overview',  label: traducir('reportes_ui.modo_metricas'), Icon: Grid3X3 },
    { id: 'explorer',  label: traducir('reportes_ui.modo_explorador'), Icon: Search },
    { id: 'presets',   label: traducir('reportes_ui.modo_plantillas'), Icon: Zap },
    { id: 'dashboard', label: saved.length ? traducir('reportes_ui.modo_guardados_n', { n: saved.length }) : traducir('reportes_ui.modo_guardados'), Icon: Pin },
    ...(veProgramados ? [{ id: 'scheduled', label: traducir('reportes_ui.modo_programados'), Icon: Calendar }] : []),
  ]

  return (
    <Page
      icon={<BarChart2 size={18} />}
      title={t('nav.reports')}
      subtitle={t('reports.subtitle')}
    >
      <Tabs
        ariaLabel={traducir('reports.modo_de_informe')}
        active={mode}
        onChange={setMode}
        items={MODES.map(({ id, label, Icon }) => ({ id, label, icon: <Icon size={14} /> }))}
      />

      {/* Plantillas */}
      {mode === 'presets' && <PresetsTab presets={PRESETS} supportedMetrics={supportedMetrics} onOpen={p => { setEditingReport({ metric: p.metric, chartType: p.chart, color: p.color }); setMode('explorer') }} />}

      {/* Overview — todas las métricas organizadas por categoría */}
      {mode === 'overview' && (
        <div>
          <p className="rep-text-muted-base-2">
            {traducir('reports.metricas_en_categorias', { n: totalMetrics, categorias: Object.keys(catalogue || {}).length })}
          </p>
          {catalogue && Object.entries(catalogue).map(([cat, items]) => (
            <div className="rep-text-3" key={cat}>
              <div className="rep-row-muted-2">
                <IconoCategoria cat={cat} size={15} /> {etiquetaCategoria(cat, traducir)}
                <span className="rep-text-muted-2xs-3">({items.length})</span>
              </div>
              <div className="u-wrap-8">
                {items.map(item => (
                  <Pulsable className="rep-btn-sm-3" key={item.id} onClick={() => { setEditingReport({ metric: item.id, chartType: item.default_chart }); setMode('explorer') }}>
                    {(() => { const IconoGrafico = ICONO_GRAFICO[item.default_chart] || BarChart3; return <IconoGrafico size={12} className="rep-text-muted-2xs-4" aria-hidden /> })()}
                    {etiquetaMetrica(traducir, item.id, item.label)}
                  </Pulsable>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Explorer */}
      {mode === 'explorer' && (
        <Card className="reportsp-sx2">
          <ReportPanel
            key={editingReport ? `${editingReport.metric}-${editingReport.chartType || 'bar'}` : 'new'}
            initialMetric={editingReport?.metric}
            initialChart={editingReport?.chartType}
            onSave={saveReport}
          />
        </Card>
      )}

      {/* Dashboard */}
      {mode === 'dashboard' && (
        saved.length === 0 ? (
          <EmptyState svgIcon={<Pin size={36} />} title={traducir('reports.sin_informes_guardados')} description={traducir('reportes_ui.sin_guardados_desc')} />
        ) : (
          <ReportsDashboard saved={saved} onRemove={removeReport} onOpen={openReport} />
        )
      )}
      {/* Visualizaciones avanzadas (BI) */}

      {/* Scheduled Reports */}
      {mode === 'scheduled' && veProgramados && <ScheduledReportsTab />}
    </Page>
  )
}