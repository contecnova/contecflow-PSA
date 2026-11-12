import { useState, useMemo } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { analyticsApi, scheduledReportsApi, apiUrl } from '../services/api'
import { Card, Button, Spinner, EmptyState } from '../components/ui'
import { Page } from '../components/ui'
import {
  BarChart2, Grid3X3, Search, Zap, Pin, Calendar,
  Table as TableIcon, BarChartBig,
} from 'lucide-react'
import { fmtCurrency, extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { CHART_COLORS_EXTENDED, COLOR_DATO_POR_DEFECTO, alpha } from '../constants/theme'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid, AreaChart, Area, ScatterChart, Scatter,
} from 'recharts'
import DateInput from '../components/ui/DateInput'

// ── Colours ───────────────────────────────────────────────────────────────────
const PALETTE = CHART_COLORS_EXTENDED

// Shared style constants used across sub-components
const _card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', cursor: 'pointer' }
const ls: CSSProperties = { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const STATUS_COLORS: Record<string, string> = {
  ok: 'var(--success)', warning: 'var(--warning)', critical: 'var(--danger)',
  Crítico: 'var(--danger)', Alto: 'var(--warning)', Medio: 'var(--accent)', Bajo: 'var(--success)',
}
const CAT_ICONS: Record<string, string> = { Horas: '⏱️', Costes: '💸', Rentabilidad: '💰', Capacidad: '📅', Proyectos: '⬡', Negocio: '💼', RRHH: '👥', 'Service Desk': '🎫', Agilidad: '🏃', ALM: '🔑', IA: '🧠', Estrategia: '🎯', Bienestar: '🧘', OKR: '🎯', NPS: '⭐', Formación: '🎓', Git: '🔀', Ingresos: '📈', Gastos: '🧾', Sprints: '🏃', Tareas: '✅', Portfolio: '🗂️', Facturación: '🧾', Alertas: '🔔', Automatizaciones: '⚙️', CMDB: '🖥️' }


// ── Presets ───────────────────────────────────────────────────────────────────
const PRESETS = [
  // Horas y costes
  { id: 'p1',  label: 'Horas mensuales',        icon: '⏱️', metric: 'hours_by_month',            chart: 'area',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p2',  label: 'Carga por persona',       icon: '👥', metric: 'hours_by_person',            chart: 'bar',         color: 'var(--success)', cat: 'Horas' },
  { id: 'p3',  label: 'Heatmap horas',           icon: '▦',  metric: 'hours_heatmap',              chart: 'heatmap',     color: 'var(--accent)', cat: 'Horas' },
  { id: 'p4',  label: 'Facturables vs internas', icon: '⚖️', metric: 'hours_billable_vs_internal', chart: 'bar_stacked', color: 'var(--accent)', cat: 'Horas' },
  { id: 'p24', label: 'Horas por proyecto',      icon: '📁', metric: 'hours_by_project',           chart: 'bar',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p25', label: 'Horas semanales',         icon: '🗓️', metric: 'hours_by_week',              chart: 'line',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p26', label: 'Horas por departamento',  icon: '🏢', metric: 'hours_by_department',        chart: 'pie',         color: 'var(--accent)', cat: 'Horas' },
  // Rentabilidad y costes
  { id: 'p5',  label: 'Margen por proyecto',     icon: '💰', metric: 'margin_by_project',          chart: 'bar_grouped', color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p6',  label: 'Coste vs Presupuesto',    icon: '💸', metric: 'cost_vs_budget',             chart: 'bar_grouped', color: 'var(--danger)', cat: 'Rentabilidad' },
  { id: 'p7',  label: 'Evolución del margen',    icon: '📈', metric: 'margin_evolution',           chart: 'line',        color: 'var(--success)', cat: 'Rentabilidad' },
  { id: 'p8',  label: 'Consumo de presupuesto',  icon: '📊', metric: 'budget_consumption',         chart: 'bar',         color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p27', label: 'Coste por proyecto',      icon: '📂', metric: 'cost_by_project',            chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p28', label: 'Coste por persona',       icon: '👤', metric: 'cost_by_person',             chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p29', label: 'Coste mensual',           icon: '📆', metric: 'cost_by_month',              chart: 'line',        color: 'var(--danger)', cat: 'Costes' },
  // Estructura de coste (perfiles versionados, multi-país)
  { id: 'pc1', label: 'Coste/hora por persona',     icon: '🧮', metric: 'cost_per_hour_by_person',     chart: 'bar',  color: 'var(--orange)', cat: 'Costes' },
  { id: 'pc2', label: 'Coste/hora por departamento',icon: '🏢', metric: 'cost_per_hour_by_department', chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc3', label: 'Coste/hora por país',        icon: '🌍', metric: 'cost_per_hour_by_country',    chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc4', label: 'Coste empresa anual / persona', icon: '💼', metric: 'annual_cost_by_person',    chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc5', label: 'Coste empresa anual / país', icon: '🌐', metric: 'annual_cost_by_country',      chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc6', label: 'Cobertura perfiles de coste',icon: '📋', metric: 'cost_profile_coverage',       chart: 'pie',  color: 'var(--success)', cat: 'Costes' },
  { id: 'pc7', label: '% Coste empresa por país',   icon: '🧾', metric: 'employer_cost_pct_by_country',chart: 'bar',  color: 'var(--purple)', cat: 'Costes' },
  { id: 'pc8', label: 'Evolución coste/hora medio', icon: '📈', metric: 'cost_per_hour_drift',         chart: 'line', color: 'var(--info)', cat: 'Costes' },
  // Proyectos y agilidad
  { id: 'p9',  label: 'Tareas por estado',        icon: '▦',  metric: 'tasks_by_status',            chart: 'pie',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p10', label: 'Velocity de sprint',       icon: '🏃', metric: 'sprint_velocity',            chart: 'bar',         color: 'var(--purple)', cat: 'Agilidad' },
  { id: 'p11', label: 'Tareas con retraso',       icon: '⚠️', metric: 'tasks_overdue',              chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p12', label: 'Lead time por proyecto',   icon: '⏳', metric: 'tasks_lead_time',            chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  { id: 'p30', label: 'Tareas por proyecto',      icon: '🧩', metric: 'tasks_by_project',           chart: 'bar',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p31', label: 'Proyectos por estado',     icon: '📌', metric: 'projects_by_status',         chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p32', label: 'Proyectos por tipo',       icon: '🗂️', metric: 'projects_by_type',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p33', label: 'Entregables por estado',   icon: '📦', metric: 'deliverables_status',        chart: 'pie',         color: 'var(--purple)', cat: 'Proyectos' },
  { id: 'p34', label: 'Riesgos por nivel',        icon: '🛡️', metric: 'risks_by_level',             chart: 'pie',         color: 'var(--danger)', cat: 'Proyectos' },
  { id: 'p35', label: 'Tareas por responsable',   icon: '👥', metric: 'tasks_by_assignee',          chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Agilidad' },
  { id: 'p36', label: 'Tareas bloqueadas',        icon: '🚫', metric: 'tasks_blocked_by_project',   chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p37', label: 'Cumplimiento de sprint',   icon: '✅', metric: 'sprint_completion_rate',     chart: 'line',        color: 'var(--success)', cat: 'Agilidad' },
  { id: 'p38', label: 'Estado de cambios',        icon: '🔄', metric: 'change_requests_status',     chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  // Service Desk
  { id: 'p13', label: 'Volumen de tickets',       icon: '🎫', metric: 'ticket_volume_trend',        chart: 'line',        color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p14', label: 'Cumplimiento SLA',         icon: '✅', metric: 'ticket_sla_compliance',      chart: 'line',        color: 'var(--success)', cat: 'Service Desk' },
  { id: 'p15', label: 'Tiempo de resolución',     icon: '⚡', metric: 'ticket_resolution_time',     chart: 'bar',         color: 'var(--purple)', cat: 'Service Desk' },
  { id: 'p16', label: 'CSAT por agente',          icon: '⭐', metric: 'ticket_csat',                chart: 'bar',         color: 'var(--warning)', cat: 'Service Desk' },
  { id: 'p39', label: 'Tickets por estado',       icon: '📊', metric: 'tickets_by_status',          chart: 'pie',         color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p40', label: 'Tickets por tipo',         icon: '🧾', metric: 'tickets_by_type',            chart: 'bar',         color: 'var(--info)', cat: 'Service Desk' },
  { id: 'p41', label: 'Tickets por prioridad',    icon: '🚨', metric: 'tickets_by_priority',        chart: 'bar',         color: 'var(--coral)', cat: 'Service Desk' },
  { id: 'p42', label: 'Tickets por agente',       icon: '👩‍💻', metric: 'tickets_by_agent',          chart: 'bar_grouped', color: 'var(--accent)', cat: 'Service Desk' },
  // Negocio y RRHH
  { id: 'p17', label: 'Pipeline por etapa',       icon: '🎪', metric: 'pipeline_by_stage',          chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p18', label: 'Win rate comercial',       icon: '🏆', metric: 'win_rate_evolution',         chart: 'line',        color: 'var(--success)', cat: 'Negocio' },
  { id: 'p19', label: 'Ingresos por cliente',     icon: '🏢', metric: 'revenue_by_client',          chart: 'bar',         color: 'var(--warning)', cat: 'Negocio' },
  { id: 'p20', label: 'Productividad equipo',     icon: '📊', metric: 'productivity_by_person',     chart: 'bar_grouped', color: 'var(--chart-lime)', cat: 'RRHH' },
  { id: 'p21', label: 'Ausencias por tipo',       icon: '🏖️', metric: 'absences_by_type',           chart: 'pie',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p43', label: 'Evolución del pipeline',   icon: '📈', metric: 'pipeline_evolution',         chart: 'line',        color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p44', label: 'Contratos por estado',     icon: '📃', metric: 'contracts_by_status',        chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p45', label: 'Proyectos por cliente',    icon: '🤝', metric: 'projects_by_client',         chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p46', label: 'Ausencias por persona',    icon: '🧑', metric: 'absences_by_person',         chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p47', label: 'Ausencias mensuales',      icon: '🗓️', metric: 'absences_by_month',          chart: 'line',        color: 'var(--orange)', cat: 'RRHH' },
  { id: 'p48', label: 'Carga semanal por persona',icon: '🧮', metric: 'load_by_person',             chart: 'line',        color: 'var(--chart-teal)', cat: 'Capacidad' },
  { id: 'p49', label: 'Carga media semanal',      icon: '📉', metric: 'load_by_week',               chart: 'line',        color: 'var(--sky-blue)', cat: 'Capacidad' },
  // ALM e IA
  { id: 'p22', label: 'Coste licencias/proveedor',icon: '🔑', metric: 'license_cost_by_vendor',     chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p23', label: 'Precisión asignación IA',  icon: '🧠', metric: 'semantic_accuracy_trend',    chart: 'line',        color: 'var(--purple)', cat: 'IA' },
  { id: 'p50', label: 'Vencimiento de licencias', icon: '⏳', metric: 'license_expiry_timeline',    chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p51', label: 'Utilización de licencias', icon: '📐', metric: 'license_utilization',        chart: 'bar',         color: 'var(--info)', cat: 'ALM' },
  { id: 'p52', label: 'Activos por tipo',         icon: '🧰', metric: 'assets_by_type',             chart: 'pie',         color: 'var(--sky-blue)', cat: 'ALM' },
  { id: 'p53', label: 'Asignaciones por modo IA', icon: '⚙️', metric: 'semantic_assignments_by_mode', chart: 'pie',       color: 'var(--purple)', cat: 'IA' },
  { id: 'p54', label: 'Proyección de ingresos',   icon: '🎯', metric: 'forecast_revenue',           chart: 'bar_stacked', color: 'var(--success)', cat: 'Estrategia' },
  { id: 'p55', label: 'Riesgo de burnout',        icon: '🧘', metric: 'burnout_index',              chart: 'bar',         color: 'var(--orange)', cat: 'Bienestar' },
  // OKR
  { id: 'p56', label: 'Progreso OKR',               icon: '🎯', metric: 'okr_progress_by_objective',   chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  { id: 'p57', label: 'Tasa KR por objetivo',        icon: '🎯', metric: 'okr_kr_completion_rate',       chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  // NPS
  { id: 'p58', label: 'NPS por cliente',             icon: '⭐', metric: 'nps_by_client',                chart: 'bar',         color: 'var(--warning)', cat: 'NPS' },
  { id: 'p59', label: 'Evolución NPS',               icon: '⭐', metric: 'nps_trend',                    chart: 'line',        color: 'var(--warning)', cat: 'NPS' },
  { id: 'p60', label: 'Distribución NPS',            icon: '⭐', metric: 'nps_distribution',             chart: 'pie',         color: 'var(--orange)', cat: 'NPS' },
  { id: 'p61', label: 'Health score cliente',        icon: '⭐', metric: 'client_health_score',          chart: 'bar',         color: 'var(--danger)', cat: 'NPS' },
  // Formación
  { id: 'p62', label: 'Finalización cursos',         icon: '🎓', metric: 'training_completion_rate',     chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  { id: 'p63', label: 'Certificaciones por persona', icon: '🎓', metric: 'certifications_by_user',        chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  // Git
  { id: 'p64', label: 'PRs por autor',               icon: '🔀', metric: 'prs_by_author',                chart: 'bar',         color: 'var(--info)', cat: 'Git' },
  { id: 'p65', label: 'PRs por proyecto',            icon: '🔀', metric: 'prs_by_project',               chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p66', label: 'Tiempo ciclo PR',             icon: '🔀', metric: 'pr_cycle_time',                chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p67', label: 'Despliegues por entorno',     icon: '🔀', metric: 'deployments_by_env',           chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p68', label: 'Tasa éxito despliegues',      icon: '🔀', metric: 'deployment_success_rate',      chart: 'bar',         color: 'var(--accent-dim)', cat: 'Git' },
  // Ingresos
  { id: 'p69', label: 'Ingresos reconocidos/mes',   icon: '📈', metric: 'revenue_recognized_by_month',  chart: 'line',        color: 'var(--success)', cat: 'Ingresos' },
  { id: 'p70', label: 'Ingresos por contrato',       icon: '📈', metric: 'revenue_by_contract',          chart: 'bar',         color: 'var(--success)', cat: 'Ingresos' },
  // Gastos
  { id: 'p71', label: 'Gastos por categoría',        icon: '🧾', metric: 'expenses_by_category',         chart: 'pie',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p72', label: 'Gastos por proyecto',         icon: '🧾', metric: 'expenses_by_project',          chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p73', label: 'Gastos fact. vs internos',    icon: '🧾', metric: 'expenses_billable_vs_internal', chart: 'pie',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p74', label: 'Evolución de gastos',         icon: '🧾', metric: 'expenses_trend',               chart: 'line',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p75', label: 'Gastos pendientes aprobación',icon: '🧾', metric: 'expenses_pending_approval',    chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  // Sprints
  { id: 'p76', label: 'Velocidad por sprint',          icon: '🏃', metric: 'sprint_velocity_trend',         chart: 'line',        color: 'var(--accent)', cat: 'Sprints' },
  { id: 'p77', label: 'Completado por sprint',         icon: '🏃', metric: 'sprint_completion_rate',        chart: 'bar',         color: 'var(--purple)', cat: 'Sprints' },
  // Tareas
  { id: 'p78', label: 'Tareas por estado',             icon: '✅', metric: 'tasks_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p79', label: 'Tareas por prioridad',          icon: '✅', metric: 'tasks_by_priority',             chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p80', label: 'Tareas vencidas por persona',   icon: '✅', metric: 'tasks_overdue_by_assignee',     chart: 'bar',         color: 'var(--danger)', cat: 'Tareas' },
  { id: 'p81', label: 'Completado mensual de tareas',  icon: '✅', metric: 'task_completion_trend',         chart: 'line',        color: 'var(--success)', cat: 'Tareas' },
  { id: 'p82', label: 'Carga de trabajo por persona',  icon: '✅', metric: 'tasks_by_assignee',             chart: 'bar',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p83', label: 'Épicas por estado',             icon: '✅', metric: 'epics_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p84', label: 'Hitos: a tiempo vs tarde',      icon: '⬡',  metric: 'milestones_on_time_rate',       chart: 'pie',         color: 'var(--info)', cat: 'Proyectos' },
  // Portfolio
  { id: 'p85', label: 'Uso de presupuesto portfolio',  icon: '🗂️', metric: 'portfolio_budget_usage',        chart: 'bar_stacked', color: 'var(--purple)', cat: 'Portfolio' },
  // RRHH evaluaciones
  { id: 'p86', label: 'Score de desempeño por persona',icon: '👥', metric: 'performance_scores_by_person',  chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p87', label: 'Completado ciclos evaluación',  icon: '👥', metric: 'performance_cycle_completion_rate', chart: 'bar',    color: 'var(--warning)', cat: 'RRHH' },
  // Horas (timesheets)
  { id: 'p88', label: 'Partes de horas por estado',    icon: '⏱️', metric: 'timesheets_approval_rate',      chart: 'pie',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p89', label: 'H. facturables mensual (partes)',icon: '⏱️', metric: 'timesheets_billable_hours_trend', chart: 'line',     color: 'var(--accent)', cat: 'Horas' },
  // RRHH ausencias
  { id: 'p90', label: 'Ausencias por tipo',            icon: '👥', metric: 'absences_by_type',              chart: 'pie',         color: 'var(--purple)', cat: 'RRHH' },
  { id: 'p91', label: 'Ausencias por persona',         icon: '👥', metric: 'absences_by_person',            chart: 'bar',         color: 'var(--purple)', cat: 'RRHH' },
  // Facturación
  { id: 'p92', label: 'Facturas por estado',           icon: '🧾', metric: 'invoices_by_status',            chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p93', label: 'Facturación mensual',           icon: '🧾', metric: 'invoice_amount_by_month',       chart: 'line',        color: 'var(--chart-teal)', cat: 'Facturación' },
  { id: 'p94', label: 'Facturación por cliente',       icon: '🧾', metric: 'invoice_amount_by_client',      chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p95', label: 'Facturas vencidas',             icon: '🧾', metric: 'invoice_overdue_amount',        chart: 'bar',         color: 'var(--danger)', cat: 'Facturación' },
  // Alertas
  { id: 'p96', label: 'Alertas por severidad',         icon: '🔔', metric: 'alerts_by_severity',            chart: 'pie',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p97', label: 'Alertas por tipo',              icon: '🔔', metric: 'alerts_by_type',                chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p98', label: 'Alertas no resueltas/proyecto', icon: '🔔', metric: 'unresolved_alerts_by_project',  chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  // Service Desk SLA
  { id: 'p99', label: 'Incumplimientos SLA/mes',       icon: '🎫', metric: 'sla_breach_trend',              chart: 'line',        color: 'var(--danger)', cat: 'Service Desk' },
  { id: 'p100', label: 'Incumplimientos SLA por tipo', icon: '🎫', metric: 'sla_breach_by_type',            chart: 'bar',         color: 'var(--danger)', cat: 'Service Desk' },
  // Automatizaciones
  { id: 'p101', label: 'Éxito automatizaciones',       icon: '⚙️', metric: 'automation_success_rate',       chart: 'pie',         color: 'var(--purple)', cat: 'Automatizaciones' },
  { id: 'p102', label: 'Ejecuciones por regla',        icon: '⚙️', metric: 'automation_run_stats',          chart: 'bar_stacked', color: 'var(--purple)', cat: 'Automatizaciones' },
  // CMDB
  { id: 'p103', label: 'CMDB por estado',              icon: '🖥️', metric: 'cmdb_items_by_status',          chart: 'pie',         color: 'var(--accent-dim)', cat: 'CMDB' },
  { id: 'p104', label: 'CMDB por entorno',             icon: '🖥️', metric: 'cmdb_items_by_environment',     chart: 'bar',         color: 'var(--accent)', cat: 'CMDB' },
  { id: 'p105', label: 'CMDB por tipo de CI',          icon: '🖥️', metric: 'cmdb_items_by_type',            chart: 'pie',         color: 'var(--accent)', cat: 'CMDB' },
  // Negocio extra
  { id: 'p106', label: 'Clientes por sector',          icon: '💼', metric: 'clients_by_industry',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p107', label: 'Pipeline por responsable',     icon: '💼', metric: 'opportunity_by_owner',          chart: 'bar',         color: 'var(--chart-teal)', cat: 'Negocio' },
]

type Preset = typeof PRESETS[number]

/** Celda de una fila de métrica: `label`, `value`, `status` o una serie por columna. */
type MetricCell = string | number | null | undefined

/** Fila de `/analytics/query/{metric}` (`rows`). */
interface MetricRow {
  label?: string
  value?: number
  status?: string
  [columna: string]: MetricCell
}

/** `meta` de una métrica (registro de métricas del backend). */
interface MetricMeta {
  label?: string
  category?: string
  description?: string
  y_label?: string
  weeks?: string[]
  error?: string
}

/** `summary` de una métrica (`compute_summary`). */
interface MetricSummary {
  total?: number
  max?: number
  avg?: number
  count?: number
}

/** Respuesta de `/analytics/query/{metric}` (`_respuesta_de_metrica`). */
interface MetricResult {
  metric_id: string
  meta?: MetricMeta
  rows: MetricRow[]
  total: number
  summary?: MetricSummary
}

interface CatalogueItem {
  id: string
  label: string
  default_chart?: string
}

/** `/analytics/catalogue`: métricas agrupadas por categoría. */
type Catalogue = Record<string, CatalogueItem[]>

interface FilterOption {
  id: string
  label: string
}

/** `/analytics/filters/options`. */
interface FilterOptions {
  projects?: FilterOption[]
  users?: FilterOption[]
  departments?: string[]
}

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

/** `ScheduledReportOut` (app/schemas/billing_reports.py). */
interface ScheduledReport {
  id: string
  name: string
  metric?: string | null
  frequency: string
  recipients: string[]
  include_pdf: boolean
  is_active: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  created_at?: string | null
}

interface ScheduledReportCreate {
  name: string
  metric: string
  frequency: string
  include_pdf: boolean
  recipients: string[]
}

/** `ScheduledReportRunOut` (app/schemas/billing_reports.py). */
interface ScheduledReportRun {
  ok: boolean
  recipients: string[]
}

interface TooltipEntry {
  name?: string
  value?: number | string
  color?: string
}

const CHART_TYPES = [
  { id: 'bar',         label: 'Barras',          icon: '▬' },
  { id: 'bar_grouped', label: 'Barras agrupadas', icon: '▮▮' },
  { id: 'bar_stacked', label: 'Barras apiladas',  icon: '▰' },
  { id: 'line',        label: 'Línea',            icon: '∿' },
  { id: 'area',        label: 'Área',             icon: '◭' },
  { id: 'pie',         label: 'Tarta',            icon: '◔' },
  { id: 'donut',       label: 'Donut',            icon: '◎' },
  { id: 'scatter',     label: 'Dispersión',       icon: '⁘' },
  { id: 'heatmap',     label: 'Mapa calor',       icon: '▦' },
  { id: 'table',       label: 'Tabla',            icon: '☰' },
]

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
    <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', fontSize: "var(--text-sm)" }}>
      <div style={{ fontWeight: 700, marginBottom: 6, color: 'var(--text-1)' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || 'var(--text-1)', marginBottom: 2 }}>
          {p.name}: <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Heatmap component ─────────────────────────────────────────────────────────
function HeatmapChart({ data, meta }: { data: MetricRow[]; meta?: MetricMeta }) {
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
      <table style={{ borderCollapse: 'separate', borderSpacing: 3, fontSize: "var(--text-xs)" }}>
        <thead>
          <tr>
            <th style={{ padding: '4px 8px', color: 'var(--text-2)', textAlign: 'left', minWidth: 120 }}>Persona</th>
            {weeks.map(w => <th key={w} style={{ padding: '4px 4px', color: 'var(--text-2)', textAlign: 'center', minWidth: 42 }}>{w}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map(row => (
            <tr key={row.label}>
              <td style={{ padding: '3px 8px', fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 600 }}>{row.label}</td>
              {weeks.map(w => {
                const v = Number(row[w] || 0)
                return (
                  <td key={w} title={`${row.label} · ${w}: ${v}h`} style={{ padding: 2 }}>
                    <div style={{ width: 38, height: 28, borderRadius: 5, background: getColor(v), display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-2xs)", fontWeight: 700, color: v ? 'var(--surface-0)' : 'transparent' }}>
                      {v > 0 ? v : ''}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: 'flex', gap: 12, marginTop: 12, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
        {[['var(--success)', 'Bajo'], ['var(--accent)', 'Medio'], ['var(--warning)', 'Alto'], ['var(--danger)', 'Crítico']].map(([c, l]) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: c }} />{l}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Data table ────────────────────────────────────────────────────────────────
function DataTable({ data, isCurrency, isPercent }: { data: MetricRow[]; isCurrency?: boolean; isPercent?: boolean }) {
  const traducir = useAppT()
  if (!data.length) return <EmptyState svgIcon={<TableIcon size={36} />} title={traducir('reports.sin_datos_disponibles')} />
  const keys = Object.keys(data[0]).filter(k => k !== 'status')
  const fmt = (v: MetricCell) => {
    if (typeof v !== 'number') return v
    if (isCurrency) return fmtCurrency(v)
    if (isPercent) return `${v.toFixed(1)}%`
    return v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })
  }
  return (
    <div className="u-scroll-x">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
            {keys.map(k => <th key={k} style={{ padding: '8px 12px', textAlign: k === 'label' ? 'left' : 'right', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k === 'label' ? '' : k}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' }}>
              {keys.map(k => (
                <td key={k} style={{ padding: '10px 12px', textAlign: k === 'label' ? 'left' : 'right', fontFamily: k !== 'label' ? 'var(--font-mono)' : 'inherit', fontWeight: k === 'value' ? 700 : 400, color: k === 'value' ? (row.status ? STATUS_COLORS[row.status] : 'var(--text-1)') : 'var(--text-1)' }}>
                  {fmt(row[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Chart renderer ────────────────────────────────────────────────────────────
function ChartRenderer({ data, chartType, meta, color = 'var(--accent)', height = 320 }: { data: MetricRow[]; chartType?: string; meta?: MetricMeta; color?: string; height?: number }) {
  const traducir = useAppT()
  // Revisión 2026-11: un cálculo que falla lo dice; antes salía como «sin datos».
  if (meta?.error) return <EmptyState svgIcon={<BarChartBig size={36} />} title={meta.error} />
  if (!data || data.length === 0) return <EmptyState svgIcon={<BarChartBig size={36} />} title={traducir('reports.sin_datos')} description="No hay datos disponibles para este gráfico" />

  const isCurrency = meta?.y_label?.includes('€')
  const isPercent = meta?.y_label?.includes('%')
  const fmtY = (v: number | string) => {
    const n = Number(v) || 0
    return isCurrency ? `${(n / 1000).toFixed(0)}k€` : isPercent ? `${n}%` : String(n)
  }

  if (chartType === 'heatmap') return <HeatmapChart data={data} meta={meta} />
  if (chartType === 'table') return <DataTable data={data} isCurrency={isCurrency} isPercent={isPercent} />

  if (chartType === 'pie' || chartType === 'donut') {
    return (
      <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
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
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: "var(--text-base)" }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: PALETTE[i % PALETTE.length], flexShrink: 0 }} />
                <span style={{ color: 'var(--text-1)', flex: 1 }}>{row.label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: PALETTE[i % PALETTE.length], fontWeight: 700 }}>
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
          <Legend wrapperStyle={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', paddingTop: 8 }} />
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
          <Legend wrapperStyle={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', paddingTop: 8 }} />
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
function SummaryBar({ summary, meta, prevSummary }: { summary?: MetricSummary; meta?: MetricMeta; prevSummary?: MetricSummary }) {
  const traducir = useAppT()
  if (!summary || !summary.total) return null
  const isCurrency = meta?.y_label?.includes('€')
  const isPercent  = meta?.y_label?.includes('%')
  const fmt = (v: number) => isCurrency ? fmtCurrency(v) : isPercent ? `${v.toFixed(1)}%` : v.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })

  const trend = (curr: number, prev: number | undefined) => {
    if (!prev || prev === 0) return null
    const pct = ((curr - prev) / Math.abs(prev) * 100)
    const up  = pct >= 0
    return { pct: Math.abs(pct).toFixed(1), up, color: up ? 'var(--success)' : 'var(--danger)', icon: up ? '↑' : '↓' }
  }

  const kpis = [
    { label: 'Total',     value: summary.total,  prev: prevSummary?.total },
    { label: 'Máximo',    value: summary.max,    prev: prevSummary?.max   },
    { label: 'Media',     value: summary.avg,    prev: prevSummary?.avg   },
    { label: 'Registros', value: summary.count,  prev: prevSummary?.count, raw: true },
  ]

  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
      {kpis.map(({ label, value, prev, raw }) => {
        const t = trend(value, prev)
        return (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', flex: 1, minWidth: 110 }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
              {raw ? value : fmt(value)}
            </div>
            {t && (
              <div style={{ fontSize: "var(--text-xs)", color: t.color, marginTop: 3, fontWeight: 700 }}>
                {t.icon} {t.pct}{traducir('reports.vs_periodo_anterior')}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Report panel ──────────────────────────────────────────────────────────────
function ReportPanel({ initialMetric, initialChart, onSave }: { initialMetric?: string; initialChart?: string; onSave?: (config: ReportConfig) => void }) {
  const traducir = useAppT()
  const narrow = useMediaQuery('(max-width: 900px)')
  const today = new Date().toISOString().split('T')[0]
  const threeMonthsAgo = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0]

  const toast = useToast()
  const [metric, setMetric] = useState(initialMetric || '')
  const [chartType, setChartType] = useState(initialChart || 'bar')
  const [dateFrom, setDateFrom] = useState(threeMonthsAgo)
  const [dateTo, setDateTo] = useState(today)
  const [projectId, setProjectId] = useState('')
  const [userId, setUserId] = useState('')
  const [department, setDepartment] = useState('')
  const [topN, setTopN] = useState(20)
  const [color, setColor] = useState('#4f8ef7')
  const [reportName, setReportName] = useState('')

  const { data: catalogue } = useQuery<Catalogue>({ queryKey: ['analytics-catalogue'], queryFn: () => analyticsApi.catalogue().then(r => r.data).catch(() => ({})) })
  const { data: filters } = useQuery<FilterOptions>({ queryKey: ['analytics-filters'], queryFn: () => analyticsApi.filterOptions().then(r => r.data).catch(() => ({})) })

  const { data: result, isLoading, isFetching } = useQuery<MetricResult | null>({
    queryKey: ['analytics-query', metric, dateFrom, dateTo, projectId, userId, department, topN],
    queryFn: () => analyticsApi.query(metric, { date_from: dateFrom, date_to: dateTo, project_id: projectId || undefined, user_id: userId || undefined, department: department || undefined, top_n: topN }).then(r => r.data).catch(() => null),
    enabled: !!metric,
    retry: false,
  })

  // Período anterior para comparativa en SummaryBar
  const prevDateFrom = useMemo(() => {
    if (!dateFrom || !dateTo) return null
    const diff = new Date(dateTo).getTime() - new Date(dateFrom).getTime()
    return new Date(new Date(dateFrom).getTime() - diff).toISOString().split('T')[0]
  }, [dateFrom, dateTo])
  const prevDateTo = dateFrom

  const { data: prevResult } = useQuery<MetricResult | null>({
    queryKey: ['analytics-prev', metric, prevDateFrom, prevDateTo, projectId, userId, department, topN],
    queryFn: () => analyticsApi.query(metric, { date_from: prevDateFrom, date_to: prevDateTo, project_id: projectId || undefined, user_id: userId || undefined, department: department || undefined, top_n: topN }).then(r => r.data).catch(() => null),
    enabled: !!metric && !!prevDateFrom,
    staleTime: 60000,
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

  const DATE_PRESETS = [
    { label: '7d', days: 7 }, { label: '30d', days: 30 }, { label: '3m', days: 90 },
    { label: '6m', days: 180 }, { label: '1a', days: 365 },
  ]

  const setDatePreset = (days: number) => {
    const end = new Date()
    const start = new Date(Date.now() - days * 86400000)
    setDateFrom(start.toISOString().split('T')[0])
    setDateTo(end.toISOString().split('T')[0])
  }


  return (
    <div>
      {/* Controls bar */}
      <div style={{ background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: narrow ? 'repeat(2, minmax(0, 1fr))' : '2fr 1.5fr 1.5fr 1fr 1fr 1fr', gap: 12, marginBottom: 14 }}>
          {/* Metric selector */}
          <div style={narrow ? { gridColumn: '1 / -1' } : undefined}>
            <label style={ls}>{traducir('reports.metrica')}</label>
            <select value={metric} onChange={e => handleMetricChange(e.target.value)} style={fs}>
              <option value="">{traducir('reports.seleccionar_metrica')}</option>
              {catalogue && Object.entries(catalogue).map(([cat, items]) => (
                <optgroup key={cat} label={`${CAT_ICONS[cat] || '📊'} ${cat}`}>
                  {items.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
                </optgroup>
              ))}
            </select>
          </div>

          {/* Project filter */}
          <div>
            <label style={ls}>📁 Proyecto</label>
            <select value={projectId} onChange={e => setProjectId(e.target.value)} style={fs}>
              <option value="">{traducir('reports.todos_los_proyectos')}</option>
              {filters?.projects?.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>

          {/* User filter */}
          <div>
            <label style={ls}>👤 Persona</label>
            <select value={userId} onChange={e => setUserId(e.target.value)} style={fs}>
              <option value="">{traducir('reports.todas_las_personas')}</option>
              {filters?.users?.map(u => <option key={u.id} value={u.id}>{u.label}</option>)}
            </select>
          </div>

          {/* Dept filter */}
          <div>
            <label style={ls}>🏢 Departamento</label>
            <select value={department} onChange={e => setDepartment(e.target.value)} style={fs}>
              <option value="">{traducir('reports.todos')}</option>
              {filters?.departments?.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>

          {/* Top N */}
          <div>
            <label style={ls}>Top N</label>
            <input type="number" min={5} max={100} value={topN} onChange={e => setTopN(+e.target.value)} style={fs} />
          </div>

          {/* Color */}
          <div>
            <label style={ls}>🎨 Color</label>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 2 }}>
              {PALETTE.slice(0, 5).map(c => (
                <button key={c} onClick={() => setColor(c)}
                  style={{ width: 24, height: 24, borderRadius: 6, background: c, border: color === c ? `2px solid #fff` : '2px solid transparent', cursor: 'pointer' }} />
              ))}
              <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(color) ? color : COLOR_DATO_POR_DEFECTO} onChange={e => setColor(e.target.value)} style={{ width: 24, height: 24, border: 'none', background: 'transparent', cursor: 'pointer', padding: 0 }} />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Date range */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <label style={{ ...ls, marginBottom: 0 }}>📅 Desde</label>
            <DateInput value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...fs, width: 140, maxWidth: '100%' }} />
            <label style={{ ...ls, marginBottom: 0 }}>Hasta</label>
            <DateInput value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...fs, width: 140, maxWidth: '100%' }} />
          </div>

          {/* Presets */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {DATE_PRESETS.map(p => (
              <button key={p.label} onClick={() => setDatePreset(p.days)}
                style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                {p.label}
              </button>
            ))}
          </div>

          {/* Chart type */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginLeft: 'auto' }}>
            {CHART_TYPES.map(ct => (
              <button key={ct.id} onClick={() => setChartType(ct.id)} title={ct.label}
                style={{ padding: '5px 10px', borderRadius: 6, border: `1px solid ${chartType === ct.id ? 'var(--accent)' : 'var(--surface-4)'}`, background: chartType === ct.id ? 'var(--accent-glow)' : 'var(--surface-2)', color: chartType === ct.id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {ct.icon}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart area */}
      {!metric ? (
        <div>
          <div style={{ textAlign: 'center', padding: '40px 0 24px', color: 'var(--text-3)' }}>
            <div style={{ fontSize: "var(--text-42)", marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6, color: 'var(--text-2)' }}>{traducir('reports.selecciona_una_metrica_para_empezar')}</div>
            <div className="u-text3-sm">Elige entre {Object.values(catalogue || {}).flat().length || '...'} {traducir('reports.metricas_disponibles')}</div>
          </div>
          {/* Métricas populares como acceso rápido */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(180px, 100%), 1fr))', gap: 10 }}>
            {[
              { id: 'hours_by_month', label: 'Horas por mes', icon: '⏱️', cat: 'Horas' },
              { id: 'margin_by_project', label: 'Margen por proyecto', icon: '💰', cat: 'Rentabilidad' },
              { id: 'ticket_volume_trend', label: 'Volumen de tickets', icon: '🎫', cat: 'Service Desk' },
              { id: 'sprint_velocity', label: 'Velocidad de sprint', icon: '🏃', cat: 'Agilidad' },
              { id: 'productivity_by_person', label: 'Productividad', icon: '📊', cat: 'RRHH' },
              { id: 'pipeline_by_stage', label: 'Pipeline', icon: '🎪', cat: 'Negocio' },
              { id: 'tasks_overdue', label: 'Tareas con retraso', icon: '⚠️', cat: 'Agilidad' },
              { id: 'cost_vs_budget', label: 'Coste vs Presupuesto', icon: '💸', cat: 'Rentabilidad' },
            ].map(m => (
              <button key={m.id} onClick={() => handleMetricChange(m.id)}
                style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '14px 16px', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left', transition: 'all 0.12s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.background = 'var(--accent-muted)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.background = 'var(--surface-2)' }}>
                <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 6 }}>{m.icon}</div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{m.label}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 3 }}>{m.cat}</div>
              </button>
            ))}
          </div>
        </div>
      ) : isLoading || isFetching ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spinner /></div>
      ) : result ? (
        <div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div className="u-min0">
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 700, margin: 0 }}>{result.meta?.label}</h3>
                <span style={{ fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 20, background: 'var(--surface-4)', color: 'var(--text-2)', fontWeight: 700, textTransform: 'uppercase' }}>
                  {result.meta?.category}
                </span>
                <span className="u-text3-xs">{result.total} registros</span>
              </div>
              <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '4px 0 0' }}>{result.meta?.description}</p>
            </div>
            <div className="u-wrap-8">
              {onSave && (
                <div style={{ display: 'flex', gap: 6, minWidth: 0 }}>
                  <input value={reportName} onChange={e => setReportName(e.target.value)} placeholder={traducir('reports.report_name')} style={{ ...fs, width: 200, minWidth: 0, fontSize: "var(--text-sm)" }} />
                  <Button size="sm" onClick={() => onSave({ name: reportName || result.meta?.label, metric, chartType, color, dateFrom, dateTo, projectId, userId, department, topN })} disabled={!metric}>💾 Guardar</Button>
                </div>
              )}
              <button onClick={() => {
                // Revisión 2026-11: cada valor entre comillas (una coma o un salto de línea rompían las columnas).
                const celda = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
                const csv = [Object.keys(result.rows[0] || {}).map(celda).join(','), ...result.rows.map(r => Object.values(r).map(celda).join(','))].join('\n')
                const a = document.createElement('a'); a.href = 'data:text/csv,' + encodeURIComponent(csv); a.download = `${metric}.csv`; a.click()
              }} style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, padding: '6px 12px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>⬇ CSV</button>
              <button onClick={() => {
                const el = document.querySelector('.recharts-wrapper') || document.querySelector('[data-chart]')
                if (!el) { toast.info('Selecciona un tipo de gráfico visual primero'); return }
                import('html2canvas').then(({ default: html2canvas }) => {
                  html2canvas(el as HTMLElement).then(canvas => {
                    const a = document.createElement('a'); a.href = canvas.toDataURL(); a.download = `${metric}.png`; a.click()
                  })
                }).catch(() => toast.error('Error al exportar imagen'))
              }} style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 8, padding: '6px 12px', color: 'var(--purple)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>📷 PNG</button>
            </div>
          </div>

          <SummaryBar summary={result.summary} meta={result.meta} prevSummary={prevResult?.summary} />
          <ChartRenderer data={result.rows} chartType={chartType} meta={result.meta} color={color} height={360} />

          {/* Small data table below chart */}
          {chartType !== 'table' && result.rows.length > 0 && result.rows.length <= 30 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Datos</div>
              <DataTable data={result.rows} isCurrency={result.meta?.y_label?.includes('€')} isPercent={result.meta?.y_label?.includes('%')} />
            </div>
          )}
        </div>
      ) : (
        <EmptyState
          icon="⚠️"
          title={traducir('reports.plantilla_no_disponible')}
          description="La métrica seleccionada no está disponible en este entorno o devolvió un error."
        />
      )}
    </div>
  )
}

// ── Dashboard mode: multiple panels ──────────────────────────────────────────
function ReportsDashboard({ saved, onRemove, onOpen }: { saved: SavedReport[]; onRemove?: (id: string) => void; onOpen?: (report: SavedReport) => void }) {
  const _today = new Date().toISOString().split('T')[0]
  const _d90 = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(480px, 100%), 1fr))', gap: 20 }}>
      {saved.map(r => (
        <Card key={r.id} style={{ padding: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div className="u-md-700">{r.name}</div>
            <div className="u-row-6">
              <button onClick={() => onOpen(r)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>✏️ Editar</button>
              <button onClick={() => onRemove(r.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
            </div>
          </div>
          <MiniPanel config={r} />
        </Card>
      ))}
    </div>
  )
}

function MiniPanel({ config }: { config: SavedReport }) {
  const { data: result, isLoading } = useQuery<MetricResult | null>({
    queryKey: ['analytics-mini', config.metric, config.dateFrom, config.dateTo, config.projectId, config.userId],
    queryFn: () => analyticsApi.query(config.metric, { date_from: config.dateFrom, date_to: config.dateTo, project_id: config.projectId || undefined, user_id: config.userId || undefined, top_n: 10 }).then(r => r.data).catch(() => null),
    enabled: !!config.metric,
    retry: false,
  })
  if (isLoading) return <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Spinner /></div>
  if (!result) return null
  return (
    <div>
      {result.summary?.total > 0 && (
        <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: config.color || 'var(--accent)', marginBottom: 8 }}>
          {result.meta?.y_label?.includes('€') ? fmtCurrency(result.summary.total) : result.summary.total.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })}
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', fontFamily: 'inherit', marginLeft: 6 }}>total</span>
        </div>
      )}
      <ChartRenderer data={result.rows} chartType={config.chartType || 'bar'} meta={result.meta} color={config.color || 'var(--accent)'} height={160} />
    </div>
  )
}



// ── ScheduledReportsTab ────────────────────────────────────────────────────────
function ScheduledReportsTab() {
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [_editing, _setEditing] = useState(null)
  const [form, setForm] = useState({
    name: '', metric: 'hours_by_month', recipients: '',
    frequency: 'weekly', include_pdf: true,
  })

  const { data: scheduled = [], isLoading } = useQuery<ScheduledReport[]>({
    queryKey: ['scheduled-reps'],
    queryFn: () => scheduledReportsApi.list().then(r => r.data).catch(() => []),
    refetchInterval: 30000,
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: ScheduledReportCreate) => scheduledReportsApi.create(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      setShowCreate(false)
      setForm({ name: '', metric: 'hours_by_month', recipients: '', frequency: 'weekly', include_pdf: true })
      toast.success('Informe programado creado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear')),
  })

  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => scheduledReportsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scheduled-reps'] }); toast.success('Informe eliminado') },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: runNow, isPending: running } = useMutation({
    mutationFn: (id: string): Promise<ScheduledReportRun> => scheduledReportsApi.run(id).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      const to = data.recipients?.join(', ') || '—'
      toast.success(`Informe enviado a: ${to}`)
    },
    onError: e => toast.error(extractErr(e, 'Error al ejecutar')),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, val }: { id: string; val: boolean }) => scheduledReportsApi.toggle(id, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-reps'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const FREQ_LABELS: Record<string, string> = { daily: 'Diario', weekly: 'Semanal', monthly: 'Mensual' }
  const FREQ_ICONS: Record<string, string>  = { daily: '📆', weekly: '📅', monthly: '🗓' }

  const METRICS = [
    { id: 'hours_by_month',        label: 'Horas por mes' },
    { id: 'margin_by_project',     label: 'Margen por proyecto' },
    { id: 'ticket_volume_trend',   label: 'Volumen de tickets' },
    { id: 'sprint_velocity',       label: 'Velocidad de sprint' },
    { id: 'productivity_by_person',label: 'Productividad por persona' },
    { id: 'pipeline_by_stage',     label: 'Pipeline por etapa' },
    { id: 'tasks_overdue',         label: 'Tareas vencidas' },
    { id: 'cost_vs_budget',        label: 'Coste vs Presupuesto' },
  ]

  const ps: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '18px 22px', marginBottom: 12 }
  const is: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>Informes programados</div>
          <div className="u-text2-sm">
            {traducir('reports.envio_automatico_por_email_los_informes_se')}
          </div>
        </div>
        <Button onClick={() => setShowCreate(s => !s)}>
          {showCreate ? '✕ Cancelar' : '+ Nuevo informe'}
        </Button>
      </div>

      {/* Aviso SMTP */}
      <div style={{ background: 'var(--warning-bg)', border: '1px solid #ffb80025', borderRadius: 8,
        padding: '10px 14px', marginBottom: 16, fontSize: "var(--text-xs)", color: 'var(--warning)',
        display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <span style={{ flexShrink: 0 }}>⚙️</span>
        <span>
          Configura <strong>SMTP_HOST</strong>, <strong>SMTP_USER</strong> y <strong>SMTP_PASS</strong> {traducir('reports.en_las_variables_de_entorno_para_envio')}
        </span>
      </div>

      {/* Formulario nuevo */}
      {showCreate && (
        <div style={{ ...ps, border: '1px solid var(--accent-border)', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16, color: 'var(--accent)' }}>
            {traducir('reports.nuevo_informe_programado')}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label style={ls}>Nombre *</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder={traducir('reports.report_name')} style={is} />
            </div>
            <div>
              <label style={ls}>{traducir('reports.metrica_2')}</label>
              <select value={form.metric} onChange={e => setForm(f => ({ ...f, metric: e.target.value }))} style={is}>
                {METRICS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </div>
            <div>
              <label style={ls}>Frecuencia</label>
              <select value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))} style={is}>
                {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{FREQ_ICONS[k]} {v}</option>)}
              </select>
            </div>
            <div>
              <label style={ls}>{traducir('reports.destinatarios_emails_separados_por_coma')}</label>
              <input value={form.recipients} onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))}
                placeholder="email1@empresa.com, email2@empresa.com" style={is} />
            </div>
          </div>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer',
            fontSize: "var(--text-sm)", color: form.include_pdf ? 'var(--text-1)' : 'var(--text-2)', marginBottom: 14 }}>
            <input type="checkbox" checked={form.include_pdf}
              onChange={e => setForm(f => ({ ...f, include_pdf: e.target.checked }))}
              style={{ accentColor: 'var(--accent)' }} />
            {traducir('reports.adjuntar_pdf_del_informe_al_email')}
          </label>
          <div className="u-actions-8">
            <button onClick={() => setShowCreate(false)}
              style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              Cancelar
            </button>
            <Button onClick={submitForm} loading={creating}
              disabled={creating || !form.name || !form.recipients}>
              📅 Programar informe
            </Button>
          </div>
        </div>
      )}

      {/* Lista */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>Cargando...</div>
      ) : scheduled.length === 0 ? (
        <div style={{ ...ps, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: "var(--text-4xl)", marginBottom: 10 }}>📅</div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 4 }}>{traducir('reports.sin_informes_programados')}</div>
          <div className="u-sm">{traducir('reports.crea_informes_para_recibir_datos_automaticamente_por')}</div>
        </div>
      ) : (
        scheduled.map(rep => (
          <div key={rep.id} style={{ ...ps, opacity: rep.is_active ? 1 : 0.55 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div className="u-flex1-min0">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: "var(--text-lg)" }}>{FREQ_ICONS[rep.frequency]}</span>
                  <span className="u-md-700">{rep.name}</span>
                  {!rep.is_active && (
                    <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4,
                      background: 'var(--danger-bg)', color: 'var(--danger)' }}>Pausado</span>
                  )}
                  {rep.include_pdf && (
                    <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4,
                      background: 'var(--purple-bg)', color: 'var(--purple)' }}>📎 PDF</span>
                  )}
                </div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 4 }}>
                  {FREQ_LABELS[rep.frequency]} ·{' '}
                  {METRICS.find(m => m.id === rep.metric)?.label || rep.metric}
                </div>
                <div className="u-text3-xs">
                  📧 {(rep.recipients || []).join(', ')}
                </div>
                {(rep.last_run_at || rep.next_run_at) && (
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 4 }}>
                    {rep.last_run_at && `Último envío: ${rep.last_run_at}`}
                    {rep.last_run_at && rep.next_run_at && ' · '}
                    {rep.next_run_at && `Próximo: ${rep.next_run_at}`}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <button onClick={() => toggle({ id: rep.id, val: !rep.is_active })}
                  style={{ background: rep.is_active ? 'var(--warning-bg)' : 'var(--success-bg)',
                    border: `1px solid ${rep.is_active ? 'var(--warning-border)' : 'var(--success-border)'}`,
                    borderRadius: 7, padding: '5px 10px',
                    color: rep.is_active ? 'var(--warning)' : 'var(--success)',
                    cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                  {rep.is_active ? '⏸ Pausar' : '▶ Activar'}
                </button>
                <button onClick={() => runNow(rep.id)} disabled={running || !rep.is_active}
                  style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)',
                    borderRadius: 7, padding: '5px 10px', color: 'var(--accent)',
                    cursor: running ? 'wait' : 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit',
                    opacity: !rep.is_active ? 0.4 : 1 }}>
                  ▶ Enviar ahora
                </button>
                {/* Enlace y no el cliente: el navegador abre el PDF en otra pestaña con la cookie de sesión. */}
                <a href={apiUrl(`/billing-reports/scheduled-reports/${rep.id}/preview-pdf`)} target="_blank"
                  rel="noopener noreferrer"
                  style={{ background: 'var(--purple-bg)', border: '1px solid var(--purple-border)',
                    borderRadius: 7, padding: '5px 10px', color: 'var(--purple)',
                    fontSize: "var(--text-xs)", textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>
                  📄 PDF
                </a>
                <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${rep.name}"?`, onConfirm: () => remove(rep.id), danger: true }) }}
                  style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
                    borderRadius: 7, padding: '5px 10px', color: 'var(--danger)',
                    cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                  🗑
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  )
}



// ── PresetsTab ─────────────────────────────────────────────────────────────────
function PresetsTab({ presets, supportedMetrics, onOpen }: { presets: readonly Preset[]; supportedMetrics?: Set<string> | null; onOpen?: (preset: Preset) => void }) {
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
    : byCat.filter(p => p.label.toLowerCase().includes(searchQ.toLowerCase()) || p.cat?.toLowerCase().includes(searchQ.toLowerCase()))
  const catIcons: Record<string, string> = { Horas:'⏱️', Costes:'💸', Rentabilidad:'💰', Capacidad:'📅',
    Proyectos:'⬡', Negocio:'💼', RRHH:'👥', 'Service Desk':'🎫', Agilidad:'🏃', ALM:'🔑', IA:'🧠' }
  const chartLabels: Record<string, string> = { bar:'Barras', bar_grouped:'Agrupadas', bar_stacked:'Apiladas',
    line:'Línea', area:'Área', pie:'Tarta', donut:'Donut', heatmap:'Heatmap', table:'Tabla' }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <input
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder="Buscar plantilla..."
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)',
            fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit',
          }}
          onFocus={e => e.target.style.borderColor = 'var(--accent)'}
          onBlur={e => e.target.style.borderColor = 'var(--surface-4)'}
        />
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {cats.map(c => (
          <button key={c} onClick={() => setFilterCat(c)}
            style={{ padding: '5px 12px', borderRadius: 20, border: `1px solid ${filterCat === c ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: filterCat === c ? 'var(--accent-muted)' : 'transparent',
              color: filterCat === c ? 'var(--accent)' : 'var(--text-2)',
              fontSize: "var(--text-xs)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {c === 'all' ? `✦ Todas (${enabledPresets.length})` : `${catIcons[c] || ''} ${c}`}
          </button>
        ))}
      </div>
      {searchQ.trim().length >= 2 && (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 10 }}>
          {filtered.length === 0 ? 'Sin resultados' : `${filtered.length} plantilla${filtered.length !== 1 ? 's' : ''} encontrada${filtered.length !== 1 ? 's' : ''}`}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(200px, 100%), 1fr))', gap: 12 }}>
        {filtered.map(p => (
          <button key={p.id} type="button" onClick={() => onOpen(p)}
            style={{ background: 'var(--surface-2)', border: `1px solid ${alpha(p.color, '25')}`, borderRadius: 12,
              padding: '16px 18px', cursor: 'pointer', transition: 'all 0.15s', width:'100%', textAlign:'left', fontFamily:'inherit' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(p.color, '70'); e.currentTarget.style.background = alpha(p.color, '08') }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = alpha(p.color, '25'); e.currentTarget.style.background = 'var(--surface-2)' }}>
            <div style={{ fontSize: "var(--text-2xl)", marginBottom: 8 }}>{p.icon}</div>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>{p.label}</div>
            <div style={{ fontSize: "var(--text-2xs)", color: p.color, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {p.cat} · {chartLabels[p.chart] || p.chart} →
            </div>
          </button>
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
    staleTime: 5 * 60 * 1000,
  })
  const saved: SavedReport[] = Array.isArray(prefs?.extra?.informes_guardados) ? prefs.extra.informes_guardados : []
  const guardar = useMutation({
    mutationFn: (lista: SavedReport[]) => api.patch('/users/me/preferences', { extra: { informes_guardados: lista } }),
    onMutate: (lista: SavedReport[]) => qc.setQueryData<UserPreferences>(['user-preferences'], old => ({ ...(old || {}), extra: { ...(old?.extra || {}), informes_guardados: lista } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ['user-preferences'] }),
    onError: (e: unknown) => toast.error(extractErr(e, 'No se pudo guardar el informe')),
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
    { id: 'overview',  label: 'Métricas',         Icon: Grid3X3 },
    { id: 'explorer',  label: 'Explorador',       Icon: Search },
    { id: 'presets',   label: 'Plantillas',       Icon: Zap },
    { id: 'dashboard', label: `Guardados${saved.length ? ` (${saved.length})` : ''}`, Icon: Pin },
    ...(veProgramados ? [{ id: 'scheduled', label: 'Programados', Icon: Calendar }] : []),
  ]

  return (
    <Page
      icon={<BarChart2 size={18} />}
      title={t('reports.title')}
      subtitle={t('reports.subtitle')}
      rightActions={
        <div className="ds-segmented" role="group" aria-label={traducir('reports.modo_de_informe')}>
          {MODES.map(({ id, label, Icon }) => (
            <button key={id} type="button"
              aria-pressed={mode === id}
              onClick={() => setMode(id)}>
              <Icon size={11} /> {label}
            </button>
          ))}
        </div>
      }
    >

      {/* Plantillas */}
      {mode === 'presets' && <PresetsTab presets={PRESETS} supportedMetrics={supportedMetrics} onOpen={p => { setEditingReport({ metric: p.metric, chartType: p.chart, color: p.color }); setMode('explorer') }} />}

      {/* Overview — todas las métricas organizadas por categoría */}
      {mode === 'overview' && (
        <div>
          <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 24, lineHeight: 1.6 }}>
            {totalMetrics} {traducir('reports.metricas_disponibles_en')} {Object.keys(catalogue || {}).length} {traducir('reports.categorias_haz_clic_en_cualquier_metrica_para')}
          </p>
          {catalogue && Object.entries(catalogue).map(([cat, items]) => (
            <div key={cat} style={{ marginBottom: 28 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>{CAT_ICONS[cat] || '📊'}</span> {cat}
                <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontWeight: 400 }}>({items.length})</span>
              </div>
              <div className="u-wrap-8">
                {items.map(item => (
                  <button key={item.id} onClick={() => { setEditingReport({ metric: item.id, chartType: item.default_chart }); setMode('explorer') }}
                    style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left', transition: 'all 0.12s' }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-glow)'; e.currentTarget.style.color = 'var(--accent)'; e.currentTarget.style.background = 'var(--accent-muted)' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-2)'; e.currentTarget.style.background = 'var(--surface-2)' }}>
                    <span style={{ marginRight: 6, fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>
                      {({bar:'▬',bar_grouped:'▮▮',bar_stacked:'▰',line:'∿',area:'◭',pie:'◔',donut:'◎',heatmap:'▦'} as Record<string, string>)[item.default_chart] || '📊'}
                    </span>
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Explorer */}
      {mode === 'explorer' && (
        <Card style={{ padding: 24 }}>
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
          <EmptyState svgIcon={<Pin size={36} />} title={traducir('reports.sin_informes_guardados')} description="Genera un informe y guárdalo para verlo aquí" />
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