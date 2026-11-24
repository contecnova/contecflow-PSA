/**
 * Menú lateral: categorías, pestañas y panel de cada categoría (23-11-2026).
 *
 * Salió de `Layout.tsx` para que lo lean también el editor «Personalizar menú»
 * (`EditorDeMenu.tsx`) y Configuración › «Menú por defecto»
 * (`pages/settings-sections/MenuPorDefectoSection.tsx`). Qué se ve lo decide la
 * matriz de permisos (`permisos/navegacion.ts`); el orden y las pestañas ocultas
 * de cada persona, `permisos/menuPersonal.ts`.
 */
import type React from 'react'
import {
  LayoutDashboard, CheckSquare, Clock, Umbrella, AlarmClockPlus,
  FileText, Receipt, CheckCircle, Folder, RefreshCw, Sparkles,
  BarChart2, Target, Package, ArrowLeftRight, AlertTriangle, Link,
  GitBranch, BookOpen, Mic, Users, TrendingUp, Award, Network,
  Trophy, Star, UserCheck, Megaphone, CreditCard, DollarSign,
  Briefcase, HardHat, Calculator, ThumbsUp, MessageSquare, Monitor,
  Key, Bell, Download, Zap, Eye, Brain, Bot, Settings, Search, Activity,
  Flag, Layers, Shield, BarChart, LayoutGrid,
  Wrench, FolderOpen, ScrollText, ClipboardCheck,
  CalendarRange, Inbox, Database, MessageSquareText, Lightbulb,
  Laptop, UserMinus, Globe, ClipboardList, Building, Building2, FileSignature, NotebookPen,
} from 'lucide-react'

export interface NavItemConfig {
  to?: string
  icon?: React.ReactNode
  label?: string
  divider?: boolean
}

export interface NavGroupConfig {
  id?: string
  label: string
  groupKey?: string
  icon?: React.ReactNode
  items: NavItemConfig[]
}

export type TFn = (module: string, key?: string) => string

/** Abre el modo «Personalizar menú» del menú lateral (lo lanza, p. ej., el perfil). */
export const EVENTO_PERSONALIZAR_MENU = 'contecflow-personalizar-menu'

const SZ = 13

export const PATH_NAV_KEY: Record<string, string> = {
  '/work-dashboard': 'work_dashboard', '/projects-dashboard': 'projects_dashboard',
  '/my-equipment': 'my_equipment', '/alm/altas-y-bajas': 'alm_onboarding_offboarding',
  '/portfolio/intake': 'portfolio_intake', '/demand': 'demand', '/resources/planning': 'resource_planning',
  '/team-dashboard': 'team_dashboard', '/finance-dashboard': 'finance_dashboard',
  '/support-dashboard': 'support_dashboard',
  '/time': 'time', '/imputar': 'log_hours', '/meetings-ai': 'meetings',
  '/sprint-planning': 'sprint_planning', '/resource-forecast': 'resource_forecast', '/resource-scheduler': 'resource_scheduler',
  '/org-chart': 'org_chart', '/milestone-billing': 'milestone_billing',
  '/rate-cards': 'rate_cards', '/service-desk': 'service_desk',
  '/agent-dashboard': 'agent_dashboard', '/report-builder': 'report_builder',
  '/data-explorer': 'data_explorer', '/ask-company': 'ask_company', '/lessons': 'lessons', '/predictions': 'predictions',
  '/data-platform': 'data_platform', '/data-governance': 'data_governance',
  '/sprint-charts': 'sprint_charts', '/cumulative-flow': 'cumulative_flow',
  '/risk-scores': 'risk_scores', '/ai-hub': 'ai_hub', '/nexus-agent': 'nexus_agent',
  '/semantic-engine': 'semantic_engine', '/webhook-log': 'webhook_log',
  '/issue-types': 'issue_types', '/custom-fields': 'custom_fields',
  '/project-permissions': 'project_permissions', '/sla-calendars': 'sla_calendars',
  '/performance-reviews': 'performance_reviews', '/kanban': 'kanban',
  '/exports': 'data_exports', '/jira-integration': 'jira_integration',
  '/public-forms': 'public_forms',
  '/developer': 'developer_portal',
  '/settings/approval-workflows': 'approval_flows',
  '/settings/policies': 'policies',
  '/settings/project-workflows': 'project_issue_flows',
  '/sd/workflow-designer': 'sd_workflow_designer',
  '/client-portal': 'client_portal', '/contracts-ai': 'contracts_ai',
  '/notebook': 'notebook',
}

export function getNavKeyForPath(path: string): string {
  return PATH_NAV_KEY[path] || path?.replace(/^\//, '').replace(/-/g, '_')
}

export function getNavLabel(path: string, fallbackLabel: string | undefined, t: TFn | null | undefined): string {
  const navKey = getNavKeyForPath(path)
  const translated = t ? t('nav', navKey) : null
  if (translated && translated !== navKey) return translated
  return fallbackLabel || path?.replace(/^\//, '').replace(/-/g, ' ')
}

/** Nombre traducido de una categoría (`nav.group_*`). */
export function getGroupLabel(group: Pick<NavGroupConfig, 'label' | 'groupKey'>, t: TFn | null | undefined): string {
  const translated = (t && group.groupKey) ? t('nav', group.groupKey) : null
  return (translated && translated !== group.groupKey) ? translated : group.label
}

export const NAV_GROUPS: NavGroupConfig[] = [
  { id: 'trabajo', label: 'My Work', groupKey: 'group_work', icon: <Clock size={12} />, items: [
    { to: '/work-dashboard',  icon: <LayoutGrid size={SZ} />,   label: 'Mi día' },
    { to: '/inbox',           icon: <Inbox size={SZ} />,        label: 'Bandeja de entrada' },
    { to: '/tasks',           icon: <CheckSquare size={SZ} />,  label: 'Tasks' },
    { to: '/time',            icon: <Clock size={SZ} />,        label: 'Tiempo' },
    { to: '/meetings-ai',     icon: <Mic size={SZ} />,            label: 'Meeting Assistant' },
    // «Mi cuaderno» (migración 202): notas personales; también desde el icono de la barra superior.
    { to: '/notebook',        icon: <NotebookPen size={SZ} />,  label: 'My notebook' },
    // PIR (migración 206): revisiones posteriores a la implantación asignadas, todas e informes.
    { to: '/pir',             icon: <ClipboardCheck size={SZ} />, label: 'PIR reviews' },
    { to: '/absences',        icon: <Umbrella size={SZ} />,     label: 'Absences' },
    { to: '/overtime',        icon: <AlarmClockPlus size={SZ} />,label: 'Overtime' },
    { to: '/documents',       icon: <FileText size={SZ} />,     label: 'Documents' },
    { to: '/expenses',        icon: <Receipt size={SZ} />,      label: 'Expenses' },
    { to: '/approvals',       icon: <CheckCircle size={SZ} />,  label: 'Approval Inbox' },
    // Licencias y hardware, fase 4: la ve toda persona con sesión (cada uno lo suyo).
    { to: '/my-equipment',    icon: <Laptop size={SZ} />,       label: 'My equipment & licences' },
    // Migración 191: portal del proveedor (solo externos con `proveedores.portal`).
    { to: '/supplier-portal', icon: <Globe size={SZ} />,        label: 'Supplier portal' },
    // Clientes internos (22-11-2026): portal de la unidad interna (`interno.portal`).
    { to: '/mi-departamento', icon: <Building size={SZ} />,     label: 'My department' },
  ]},
  { id: 'proyectos', label: 'Projects', groupKey: 'group_projects', icon: <Folder size={12} />, items: [
    { to: '/projects-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Salud del portfolio' },
    { to: '/projects',        icon: <FolderOpen size={SZ} />,     label: 'Projects' },
    { to: '/lessons',         icon: <Lightbulb size={SZ} />,      label: 'Lessons learned' },
    { to: '/sprints',         icon: <RefreshCw size={SZ} />,      label: 'Sprints' },
    { to: '/sprint-planning', icon: <Sparkles size={SZ} />,       label: 'Sprint Planning AI' },
    { to: '/raci',            icon: <Shield size={SZ} />,          label: 'RACI Matrix' },
    { to: '/changelog',       icon: <ScrollText size={SZ} />,      label: 'Changelog' },
    { to: '/uat',            icon: <ClipboardCheck size={SZ} />,  label: 'UAT' },
    { to: '/gantt',           icon: <BarChart2 size={SZ} />,      label: 'Gantt' },
    // Auditoria 2026-11 (#45): /epic-gantt existia sin entrada en el menu.
    { to: '/epic-gantt',      icon: <BarChart2 size={SZ} />,      label: 'Gantt de épicas' },
    { to: '/epics',           icon: <Target size={SZ} />,         label: 'Epics & Roadmap' },
    { to: '/deliverables',    icon: <Package size={SZ} />,        label: 'Deliverables' },
    { to: '/changes',         icon: <ArrowLeftRight size={SZ} />, label: 'Changes' },
    // 23-11-2026 (A1 del 04): la firma electrónica era una página huérfana (solo por URL).
    { to: '/esign',           icon: <FileSignature size={SZ} />,  label: 'E-Signature' },
    // 22-11-2026: expedientes del flujo de demanda configurable.
    { to: '/demand',          icon: <ClipboardList size={SZ} />,  label: 'Demand requests' },
    { to: '/risks',           icon: <AlertTriangle size={SZ} />,  label: 'Risks' },
    { to: '/dependencies',    icon: <Link size={SZ} />,           label: 'Dependencies' },
    { to: '/git',             icon: <GitBranch size={SZ} />,      label: 'Git Integration' },
    { to: '/wiki',            icon: <BookOpen size={SZ} />,       label: 'Wiki' },
  ]},
  { id: 'equipo', label: 'Team & People', groupKey: 'group_team', icon: <Users size={12} />, items: [
    { to: '/team-dashboard',  icon: <LayoutGrid size={SZ} />,     label: 'Capacidad del equipo' },
    { to: '/resources',           icon: <Users size={SZ} />,      label: 'Resources' },
    { to: '/resources/planning',  icon: <CalendarRange size={SZ} />, label: 'Resource planning' },
    { to: '/capacity',            icon: <TrendingUp size={SZ} />, label: 'Capacity' },
    { to: '/resource-forecast',   icon: <BarChart size={SZ} />,   label: 'Resource Forecast' },
    { to: '/resource-scheduler',  icon: <CalendarRange size={SZ} />, label: 'Visual Scheduler' },
    { to: '/skills',              icon: <Award size={SZ} />,      label: 'Skills' },
    { to: '/org-chart',           icon: <Network size={SZ} />,    label: 'Org Chart' },
    { to: '/okrs',                icon: <Trophy size={SZ} />,     label: 'OKRs' },
    { to: '/performance-reviews', icon: <Star size={SZ} />,       label: 'Performance Reviews' },
    { to: '/training',            icon: <BookOpen size={SZ} />,   label: 'Training & Certs' },
  ]},
  { id: 'negocio', label: 'Clients & Finance', groupKey: 'group_business', icon: <DollarSign size={12} />, items: [
    { to: '/finance-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Resumen financiero' },
    { to: '/clients',           icon: <UserCheck size={SZ} />,   label: 'Clients / CRM' },
    // 23-11-2026 (A1 del 04): gestión del portal de clientes (UAT, documentos, peticiones,
    // estadísticas). No es duplicado de la ficha del cliente: ahí no se crean UAT ni documentos.
    { to: '/client-portal',     icon: <Globe size={SZ} />,       label: 'Client portal' },
    { to: '/pipeline',          icon: <Megaphone size={SZ} />,   label: 'Sales Pipeline' },
    { to: '/contracts',         icon: <ScrollText size={SZ} />,  label: 'Contracts' },
    { to: '/invoices',          icon: <CreditCard size={SZ} />,  label: 'Invoicing' },
    { to: '/milestone-billing', icon: <Flag size={SZ} />,        label: 'Milestone Billing' },
    { to: '/profitability',     icon: <TrendingUp size={SZ} />,  label: 'Profitability' },
    { to: '/revenue',           icon: <DollarSign size={SZ} />,  label: 'Revenue Recognition' },
    { to: '/budgets',           icon: <Briefcase size={SZ} />,   label: 'Budgets' },
    { to: '/subcontractors',    icon: <HardHat size={SZ} />,     label: 'Subcontractors' },
    // Clientes internos (22-11-2026): cuadro de dirección, cargos y beneficios (`interno.gestionar`).
    { to: '/internal-clients',  icon: <Building2 size={SZ} />,   label: 'Internal clients' },
    { to: '/scenarios',         icon: <Calculator size={SZ} />,  label: 'What-If Scenarios' },
    { to: '/nps',               icon: <ThumbsUp size={SZ} />,    label: 'NPS & Health' },
  ]},
  { id: 'soporte', label: 'Support & ITSM', groupKey: 'group_support', icon: <MessageSquare size={12} />, items: [
    { to: '/support-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Estado del soporte' },
    { to: '/service-desk',    icon: <MessageSquare size={SZ} />, label: 'Service Desk' },
    { to: '/cmdb',            icon: <Monitor size={SZ} />,       label: 'CMDB' },
    { to: '/alm',             icon: <Key size={SZ} />,           label: 'Licenses & Assets' },
    { to: '/alm/altas-y-bajas', icon: <UserMinus size={SZ} />,   label: 'Onboarding & offboarding' },
    { to: '/agent-dashboard', icon: <LayoutGrid size={SZ} />,    label: 'Agent Dashboard' },
  ]},
  { id: 'analisis', label: 'Analytics & BI', groupKey: 'group_analytics', icon: <BarChart2 size={12} />, items: [
    { to: '/executive',       icon: <LayoutDashboard size={SZ} />, label: 'Executive Dashboard' },
    { to: '/data-explorer',   icon: <Search size={SZ} />,          label: 'Data Explorer' },
    { to: '/ask-company',     icon: <MessageSquareText size={SZ} />, label: 'Ask the company' },
    { to: '/reports',         icon: <FileText size={SZ} />,        label: 'Reports' },
    { to: '/report-builder',  icon: <Wrench size={SZ} />,          label: 'Report Builder' },
    { to: '/predictions',     icon: <Brain size={SZ} />,           label: 'Predictions' },
    { to: '/alerts',          icon: <Bell size={SZ} />,            label: 'Alerts' },
    { to: '/evm',             icon: <BarChart size={SZ} />,        label: 'EVM — Earned Value' },
    { to: '/portfolio',       icon: <Layers size={SZ} />,          label: 'Project Portfolio' },
    { to: '/portfolio/intake', icon: <Inbox size={SZ} />,          label: 'Portfolio intake' },
    { to: '/sprint-charts',   icon: <Activity size={SZ} />,        label: 'Burnup & Velocity' },
    { to: '/cumulative-flow', icon: <BarChart2 size={SZ} />,       label: 'Cumulative Flow' },
    { to: '/risk-scores',     icon: <Shield size={SZ} />,          label: 'Project Risk' },
    { to: '/exports',         icon: <Download size={SZ} />,        label: 'Data Export' },
    { to: '/data-platform',   icon: <Database size={SZ} />,        label: 'Data Platform' },
    { to: '/data-governance', icon: <Shield size={SZ} />,          label: 'Data Governance' },
  ]},
  { id: 'ia', label: 'AI & Automation', groupKey: 'group_ai', icon: <Brain size={12} />, items: [
    { to: '/nexus-agent',     icon: <Zap size={SZ} />,           label: 'NexusAgent' },
    { to: '/oracle',          icon: <Eye size={SZ} />,           label: 'NexusOracle' },
    { to: '/semantic-engine', icon: <Brain size={SZ} />,         label: 'AI Assignment' },
    { to: '/automations',     icon: <Bot size={SZ} />,           label: 'Automations' },
    { to: '/bpm',             icon: <Network size={SZ} />,       label: 'BPM Procesos' },
  ]},
  // 18-11-2026: una sola entrada. Toda la configuración (antes 20 entradas aquí,
  // más /rate-cards, /user-costs, /sla-calendars y el diseñador de flujos del
  // service desk en otros grupos) vive en /settings/:seccion, con su propia
  // navegación agrupada y buscador (pages/settings/catalogoDeAjustes.tsx).
  { id: 'configuracion', label: 'Settings', groupKey: 'group_settings', icon: <Settings size={12} />, items: [
    { to: '/settings',            icon: <Settings size={SZ} />,    label: 'Settings' },
  ]},
]

/**
 * Panel de cada categoría (medido 23-11-2026): la pantalla resumen a la que
 * lleva pulsar el icono o el nombre de la categoría. Es siempre su primera
 * pestaña de fábrica y cada una pide su propia capacidad (`navegacion.ts`):
 * quien no la tiene ve la categoría como antes (el nombre despliega).
 * «IA y automatización» no tiene panel propio (NexusAgent es una herramienta,
 * no un resumen): se queda como antes.
 */
export const PANEL_DE_CATEGORIA: Record<string, string> = {
  trabajo: '/work-dashboard',        // Mi día (cualquiera con sesión)
  proyectos: '/projects-dashboard',  // Salud del portfolio (proyectos.panel)
  equipo: '/team-dashboard',         // Capacidad del equipo (equipo.ver)
  negocio: '/finance-dashboard',     // Resumen financiero (finanzas.ver)
  soporte: '/support-dashboard',     // Estado del soporte (soporte.panel)
  analisis: '/executive',            // Executive Dashboard (analitica.ver)
  configuracion: '/settings',        // Configuración (su única pestaña)
}
