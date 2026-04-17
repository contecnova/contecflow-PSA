import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { Avatar } from '../ui'
import NotificationCenter from './NotificationCenter'
import GlobalSearch from './GlobalSearch'
import NexusAssistPanel from './NexusAssistPanel'
import UserProfilePanel from './UserProfilePanel'
import useUserPreferences from '../../hooks/useUserPreferences'
import useNotificationBadges from '../../hooks/useNotificationBadges'
import OfflineIndicator from '../OfflineIndicator'
import { useAppLang } from '../../i18n/AppLangContext'
import {
  LayoutDashboard, CheckSquare, Columns, Clock, Calendar, Umbrella,
  FileText, Receipt, CheckCircle, Folder, RefreshCw, Sparkles,
  BarChart2, Target, Package, ArrowLeftRight, AlertTriangle, Link,
  GitBranch, BookOpen, Mic, Users, TrendingUp, Award, Network,
  Trophy, Star, UserCheck, Megaphone, CreditCard, DollarSign,
  Briefcase, HardHat, Calculator, ThumbsUp, MessageSquare, Monitor,
  Key, Bell, Download, Zap, Eye, Brain, Bot, Settings, Tag, Sliders,
  Lock, Plug, PenLine, Upload, ShieldCheck, Scale, Building2, Globe,
  Search, LogOut, ChevronRight, ChevronLeft, Menu, X, Activity,
  Timer, Flag, Layers, Shield, Keyboard, BarChart, LayoutGrid,
  Wrench, GitMerge, FolderOpen, ScrollText, ClipboardCheck, ListChecks,
  CalendarRange,
} from 'lucide-react'

const ROUTE_LABELS = {
  '/dashboard': 'Dashboard', '/tasks': 'Tareas', '/kanban-advanced': 'Kanban',
  '/imputar': 'Imputar horas', '/timer': 'Timer', '/timesheets': 'Timesheets',
  '/calendar': 'Calendario', '/absences': 'Ausencias', '/documents': 'Documentos',
  '/expenses': 'Gastos', '/approvals': 'Aprobaciones', '/projects': 'Proyectos',
  '/sprints': 'Sprints', '/sprint-planning': 'Planif. Sprint IA', '/gantt': 'Gantt',
  '/epics': 'Épicas & Roadmap', '/deliverables': 'Entregables', '/changes': 'Cambios',
  '/risks': 'Riesgos', '/dependencies': 'Dependencias', '/git': 'Git',
  '/wiki': 'Wiki', '/meetings-ai': 'Reuniones → Tareas',
  '/resources': 'Gestión Recursos', '/capacity': 'Planif. Capacidad',
  '/resource-forecast': 'Forecast Recursos', '/resource-scheduler': 'Planificador Recursos', '/skills': 'Skills', '/org-chart': 'Organigrama',
  '/okrs': 'OKRs', '/performance-reviews': 'Evaluaciones', '/training': 'Formación',
  '/clients': 'Clientes / CRM', '/pipeline': 'Pipeline Ventas', '/contracts': 'Contratos',
  '/invoices': 'Facturación', '/milestone-billing': 'Factura Milestones',
  '/profitability': 'Rentabilidad', '/revenue': 'Ingresos', '/budgets': 'Presupuestos',
  '/rate-cards': 'Rate Cards', '/subcontractors': 'Subcontratistas',
  '/scenarios': 'Escenarios What-If', '/nps': 'NPS & Salud',
  '/service-desk': 'Service Desk', '/cmdb': 'CMDB', '/alm': 'ALM / Licencias',
  '/sla-calendars': 'Calendarios SLA', '/agent-dashboard': 'Dashboard Agente',
  '/bi': 'Dashboard Ejecutivo', '/reports': 'Reportes', '/report-builder': 'Report Builder',
  '/executive': 'Dashboard Ejecutivo',
  '/evm': 'EVM — Valor Ganado', '/portfolio': 'Carteras', '/sprint-charts': 'Burnup & Velocity',
  '/cumulative-flow': 'Flujo Acumulado', '/risk-scores': 'Riesgo Proyectos',
  '/alerts': 'Alertas', '/exports': 'Exportar Datos',
  '/nexus-agent': 'NexusAgent', '/oracle': 'NexusOracle',
  '/semantic-engine': 'Asignación IA', '/automations': 'Automatizaciones',
  '/settings': 'Configuración General', '/workflows': 'Workflows', '/issue-types': 'Tipos de Issue',
  '/custom-fields': 'Campos Personalizados', '/project-permissions': 'Permisos Proyecto',
  '/ai-hub': 'IA Hub', '/esign': 'E-Firma', '/m365': 'Microsoft 365',
  '/import': 'Importar Datos', '/mfa': 'Seguridad MFA',
  '/governance': 'AI Governance', '/grc': 'GRC / SoD', '/organizations': 'Organizaciones',
  '/enterprise': 'Enterprise', '/webhook-log': 'Log Webhooks',
  '/raci': 'Matriz RACI', '/changelog': 'Changelog', '/uat': 'UAT — Pruebas de Aceptación',
  '/jira-integration': 'Integración Jira',
  '/project-templates': 'Plantillas de proyecto',
}

const ROUTE_SECTION = {
  '/tasks': 'Mi Trabajo', '/kanban-advanced': 'Mi Trabajo', '/imputar': 'Mi Trabajo',
  '/timer': 'Mi Trabajo', '/timesheets': 'Mi Trabajo', '/calendar': 'Mi Trabajo',
  '/absences': 'Mi Trabajo', '/documents': 'Mi Trabajo', '/expenses': 'Mi Trabajo',
  '/approvals': 'Mi Trabajo',
  '/projects': 'Proyectos', '/sprints': 'Proyectos', '/sprint-planning': 'Proyectos',
  '/raci': 'Proyectos', '/changelog': 'Proyectos', '/uat': 'Proyectos',
  '/gantt': 'Proyectos', '/epics': 'Proyectos', '/deliverables': 'Proyectos',
  '/changes': 'Proyectos', '/risks': 'Proyectos', '/dependencies': 'Proyectos',
  '/git': 'Proyectos', '/wiki': 'Proyectos', '/meetings-ai': 'Proyectos',
  '/resources': 'Equipo', '/capacity': 'Equipo', '/resource-forecast': 'Equipo', '/resource-scheduler': 'Equipo',
  '/skills': 'Equipo', '/org-chart': 'Equipo', '/okrs': 'Equipo',
  '/performance-reviews': 'Equipo', '/training': 'Equipo',
  '/clients': 'Finanzas', '/pipeline': 'Finanzas', '/contracts': 'Finanzas',
  '/invoices': 'Finanzas', '/milestone-billing': 'Finanzas',
  '/profitability': 'Finanzas', '/revenue': 'Finanzas', '/budgets': 'Finanzas',
  '/rate-cards': 'Finanzas', '/subcontractors': 'Finanzas',
  '/scenarios': 'Finanzas', '/nps': 'Finanzas',
  '/service-desk': 'Soporte', '/cmdb': 'Soporte', '/alm': 'Soporte',
  '/sla-calendars': 'Soporte', '/agent-dashboard': 'Soporte',
  '/bi': 'Analítica', '/reports': 'Analítica', '/report-builder': 'Analítica',
  '/executive': 'Analítica',
  '/evm': 'Analítica', '/portfolio': 'Analítica', '/sprint-charts': 'Analítica',
  '/cumulative-flow': 'Analítica', '/risk-scores': 'Analítica',
  '/alerts': 'Analítica', '/exports': 'Analítica',
  '/nexus-agent': 'IA', '/oracle': 'IA', '/semantic-engine': 'IA', '/automations': 'IA',
  '/settings': 'Configuración', '/workflows': 'Configuración', '/issue-types': 'Configuración',
  '/custom-fields': 'Configuración', '/project-permissions': 'Configuración',
  '/ai-hub': 'Configuración', '/esign': 'Configuración', '/m365': 'Configuración',
  '/import': 'Configuración', '/mfa': 'Configuración',
  '/governance': 'Configuración', '/grc': 'Configuración', '/organizations': 'Configuración',
  '/enterprise': 'Configuración', '/webhook-log': 'Configuración',
  '/jira-integration': 'Configuración',
  '/project-templates': 'Configuración',
}

const PATH_NAV_KEY = {
  '/imputar': 'log_hours', '/kanban-advanced': 'kanban', '/meetings-ai': 'meetings',
  '/sprint-planning': 'sprint_planning', '/resource-forecast': 'resource_forecast', '/resource-scheduler': 'resource_scheduler',
  '/org-chart': 'org_chart', '/milestone-billing': 'milestone_billing',
  '/rate-cards': 'rate_cards', '/service-desk': 'service_desk',
  '/agent-dashboard': 'agent_dashboard', '/report-builder': 'report_builder',
  '/sprint-charts': 'sprint_charts', '/cumulative-flow': 'cumulative_flow',
  '/risk-scores': 'risk_scores', '/ai-hub': 'ai_hub', '/nexus-agent': 'nexus_agent',
  '/semantic-engine': 'semantic_engine', '/webhook-log': 'webhook_log',
  '/issue-types': 'issue_types', '/custom-fields': 'custom_fields',
  '/project-permissions': 'project_permissions', '/sla-calendars': 'sla_calendars',
  '/performance-reviews': 'performance_reviews', '/kanban': 'kanban',
  '/exports': 'data_exports', '/jira-integration': 'jira_integration',
}

const SZ = 13

// ── Quick Access defaults per role ─────────────────────────────────────────────
const QUICK_ACCESS = {
  admin:     ['/projects', '/alerts', '/settings', '/users', '/pipeline', '/executive'],
  pm:        ['/projects', '/tasks', '/pipeline', '/invoices', '/resources', '/reports'],
  team_lead: ['/tasks', '/sprints', '/projects', '/kanban-advanced', '/imputar', '/timesheets'],
  hr:        ['/resources', '/absences', '/performance-reviews', '/training', '/org-chart'],
  employee:  ['/tasks', '/imputar', '/timesheets', '/expenses', '/absences', '/service-desk'],
}

const NAV_WORKSPACE_KEY = 'clarive_nav_workspace'
const WORKSPACE_GROUPS = {
  all: ['trabajo', 'proyectos', 'equipo', 'negocio', 'soporte', 'analisis', 'ia', 'configuracion'],
  work: ['trabajo'],
  projects: ['proyectos'],
  team: ['equipo'],
  business: ['negocio'],
  support: ['soporte'],
  analytics: ['analisis'],
  ai: ['ia'],
  settings: ['configuracion'],
}

const LAYOUT_TEXT = {
  es: {
    shortcuts: 'Atajos',
    keyboard_shortcuts: 'Atajos de teclado',
    filter_menu: 'Filtrar menu...',
    no_results: 'Sin resultados',
    quick_access: 'Acceso rapido',
    favorites: 'Favoritos',
    recent: 'Recientes',
    workspace: 'Workspace',
    workspace_all: 'Todo',
    workspace_work: 'Trabajo',
    workspace_projects: 'Proyectos',
    workspace_team: 'Equipo',
    workspace_business: 'Finanzas',
    workspace_support: 'Soporte',
    workspace_analytics: 'Analitica',
    workspace_ai: 'IA',
    workspace_settings: 'Config',
  },
  en: {
    shortcuts: 'Shortcuts',
    keyboard_shortcuts: 'Keyboard shortcuts',
    filter_menu: 'Filter menu...',
    no_results: 'No results',
    quick_access: 'Quick access',
    favorites: 'Favorites',
    recent: 'Recent',
    workspace: 'Workspace',
    workspace_all: 'All',
    workspace_work: 'Work',
    workspace_projects: 'Projects',
    workspace_team: 'Team',
    workspace_business: 'Finance',
    workspace_support: 'Support',
    workspace_analytics: 'Analytics',
    workspace_ai: 'AI',
    workspace_settings: 'Settings',
  },
}

const NAV_GROUPS = [
  { id: 'dashboard', single: true, items: [
    { to: '/dashboard', icon: <LayoutDashboard size={SZ} />, label: 'Dashboard', roles: ['admin','pm','hr','team_lead','employee'] },
  ]},
  { id: 'trabajo', label: 'Mi Trabajo', groupKey: 'group_work', icon: <Clock size={12} />, roles: ['admin','pm','team_lead','employee','hr'], items: [
    { to: '/tasks',           icon: <CheckSquare size={SZ} />,  label: 'Tareas',          roles: ['admin','pm','team_lead','employee'] },
    { to: '/kanban-advanced', icon: <Columns size={SZ} />,      label: 'Kanban',          roles: ['admin','pm','team_lead','employee'] },
    { to: '/imputar',         icon: <Clock size={SZ} />,        label: 'Imputar horas',   roles: ['admin','pm','team_lead','employee'] },
    { to: '/timer',           icon: <Timer size={SZ} />,        label: 'Timer',           roles: ['admin','pm','team_lead','employee'] },
    { to: '/timesheets',      icon: <ListChecks size={SZ} />,   label: 'Timesheets',      roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/calendar',        icon: <Calendar size={SZ} />,     label: 'Calendario',      roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/absences',        icon: <Umbrella size={SZ} />,     label: 'Ausencias',       roles: ['admin','pm','hr','team_lead','employee'] },
    { to: '/documents',       icon: <FileText size={SZ} />,     label: 'Documentos',      roles: ['admin','pm','hr','team_lead','employee'] },
    { to: '/expenses',        icon: <Receipt size={SZ} />,      label: 'Gastos',          roles: ['admin','pm','hr','employee'] },
    { to: '/approvals',       icon: <CheckCircle size={SZ} />,  label: 'Aprobaciones',    roles: ['admin','pm','team_lead'] },
  ]},
  { id: 'proyectos', label: 'Proyectos', groupKey: 'group_projects', icon: <Folder size={12} />, roles: ['admin','pm','team_lead'], items: [
    { to: '/projects',        icon: <FolderOpen size={SZ} />,     label: 'Proyectos',           roles: ['admin','pm','team_lead'] },
    { to: '/sprints',         icon: <RefreshCw size={SZ} />,      label: 'Sprints',             roles: ['admin','pm','team_lead'] },
    { to: '/sprint-planning', icon: <Sparkles size={SZ} />,       label: 'Planif. sprint IA',   roles: ['admin','pm'] },
    { to: '/raci',            icon: <Shield size={SZ} />,          label: 'Matriz RACI',         roles: ['admin','pm','team_lead'] },
    { to: '/changelog',       icon: <ScrollText size={SZ} />,      label: 'Changelog',           roles: ['admin','pm','team_lead'] },
    { to: '/uat',            icon: <ClipboardCheck size={SZ} />,  label: 'UAT / Pruebas',        roles: ['admin','pm','team_lead'] },
    { to: '/gantt',           icon: <BarChart2 size={SZ} />,      label: 'Gantt',               roles: ['admin','pm','team_lead','employee'] },
    { to: '/epics',           icon: <Target size={SZ} />,         label: 'Épicas & Roadmap',    roles: ['admin','pm','team_lead'] },
    { to: '/deliverables',    icon: <Package size={SZ} />,        label: 'Entregables',         roles: ['admin','pm'] },
    { to: '/changes',         icon: <ArrowLeftRight size={SZ} />, label: 'Cambios',             roles: ['admin','pm'] },
    { to: '/risks',           icon: <AlertTriangle size={SZ} />,  label: 'Riesgos',             roles: ['admin','pm'] },
    { to: '/dependencies',    icon: <Link size={SZ} />,           label: 'Dependencias',        roles: ['admin','pm','team_lead','employee'] },
    { to: '/git',             icon: <GitBranch size={SZ} />,      label: 'Git Integration',     roles: ['admin','pm'] },
    { to: '/wiki',            icon: <BookOpen size={SZ} />,       label: 'Wiki',                roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/meetings-ai',     icon: <Mic size={SZ} />,            label: 'Reuniones → Tareas',  roles: ['admin','pm','team_lead'] },
  ]},
  { id: 'equipo', label: 'Equipo & Personas', groupKey: 'group_team', icon: <Users size={12} />, roles: ['admin','pm','hr','team_lead'], items: [
    { to: '/resources',           icon: <Users size={SZ} />,      label: 'Gestión recursos',   roles: ['admin','hr','pm'] },
    { to: '/capacity',            icon: <TrendingUp size={SZ} />, label: 'Planif. capacidad',  roles: ['admin','hr','pm'] },
    { to: '/resource-forecast',   icon: <BarChart size={SZ} />,   label: 'Forecast recursos',     roles: ['admin','pm','team_lead'] },
    { to: '/resource-scheduler',  icon: <CalendarRange size={SZ} />, label: 'Planificador visual', roles: ['admin','pm','team_lead'] },
    { to: '/skills',              icon: <Award size={SZ} />,      label: 'Skills',             roles: ['admin','pm','hr','employee'] },
    { to: '/org-chart',           icon: <Network size={SZ} />,    label: 'Organigrama',        roles: ['admin','pm','hr'] },
    { to: '/okrs',                icon: <Trophy size={SZ} />,     label: 'OKRs',               roles: ['admin','pm','hr'] },
    { to: '/performance-reviews', icon: <Star size={SZ} />,       label: 'Evaluaciones',       roles: ['admin','pm','hr'] },
    { to: '/training',            icon: <BookOpen size={SZ} />,   label: 'Formación & Certs',  roles: ['admin','pm','hr','employee'] },
  ]},
  { id: 'negocio', label: 'Clientes & Finanzas', groupKey: 'group_business', icon: <DollarSign size={12} />, roles: ['admin','pm'], items: [
    { to: '/clients',           icon: <UserCheck size={SZ} />,   label: 'Clientes / CRM',      roles: ['admin','pm'] },
    { to: '/pipeline',          icon: <Megaphone size={SZ} />,   label: 'Pipeline ventas',      roles: ['admin','pm'] },
    { to: '/contracts',         icon: <ScrollText size={SZ} />,  label: 'Contratos',            roles: ['admin','pm'] },
    { to: '/invoices',          icon: <CreditCard size={SZ} />,  label: 'Facturación',          roles: ['admin','pm'] },
    { to: '/milestone-billing', icon: <Flag size={SZ} />,        label: 'Factura milestones',   roles: ['admin','pm'] },
    { to: '/profitability',     icon: <TrendingUp size={SZ} />,  label: 'Rentabilidad',         roles: ['admin','pm'] },
    { to: '/revenue',           icon: <DollarSign size={SZ} />,  label: 'Reconoc. ingresos',    roles: ['admin','pm'] },
    { to: '/budgets',           icon: <Briefcase size={SZ} />,   label: 'Presupuestos',         roles: ['admin','pm'] },
    { to: '/rate-cards',        icon: <Tag size={SZ} />,         label: 'Rate Cards',           roles: ['admin','pm'] },
    { to: '/subcontractors',    icon: <HardHat size={SZ} />,     label: 'Subcontratistas',      roles: ['admin','pm'] },
    { to: '/scenarios',         icon: <Calculator size={SZ} />,  label: 'Escenarios what-if',   roles: ['admin','pm'] },
    { to: '/nps',               icon: <ThumbsUp size={SZ} />,    label: 'NPS & Salud cliente',  roles: ['admin','pm'] },
  ]},
  { id: 'soporte', label: 'Soporte & ITSM', groupKey: 'group_support', icon: <MessageSquare size={12} />, roles: ['admin','pm','hr','employee','team_lead'], items: [
    { to: '/service-desk',    icon: <MessageSquare size={SZ} />, label: 'Service Desk',     roles: ['admin','pm','employee','hr','team_lead'] },
    { to: '/cmdb',            icon: <Monitor size={SZ} />,       label: 'CMDB',             roles: ['admin','pm'] },
    { to: '/alm',             icon: <Key size={SZ} />,           label: 'ALM / Licencias',  roles: ['admin','pm'] },
    { to: '/sla-calendars',   icon: <Calendar size={SZ} />,      label: 'Calendarios SLA',  roles: ['admin','pm'] },
    { to: '/agent-dashboard', icon: <LayoutGrid size={SZ} />,    label: 'Dashboard agente', roles: ['admin','pm'] },
  ]},
  { id: 'analisis', label: 'Analítica & BI', groupKey: 'group_analytics', icon: <BarChart2 size={12} />, roles: ['admin','pm','hr','employee'], items: [
    { to: '/executive',       icon: <LayoutDashboard size={SZ} />,  label: 'Dashboard ejecutivo', roles: ['admin','pm'] },
    { to: '/reports',         icon: <FileText size={SZ} />,      label: 'Reportes',            roles: ['admin','pm','hr','employee'] },
    { to: '/report-builder',  icon: <Wrench size={SZ} />,        label: 'Report Builder',      roles: ['admin','pm'] },
    { to: '/evm',             icon: <BarChart size={SZ} />,      label: 'EVM — Valor Ganado',  roles: ['admin','pm'] },
    { to: '/portfolio',       icon: <Layers size={SZ} />,        label: 'Gestión de Carteras', roles: ['admin','pm'] },
    { to: '/sprint-charts',   icon: <Activity size={SZ} />,      label: 'Burnup & Velocity',   roles: ['admin','pm'] },
    { to: '/cumulative-flow', icon: <BarChart2 size={SZ} />,     label: 'Flujo acumulado',     roles: ['admin','pm'] },
    { to: '/risk-scores',     icon: <Shield size={SZ} />,        label: 'Riesgo proyectos',    roles: ['admin','pm'] },
    { to: '/alerts',          icon: <Bell size={SZ} />,          label: 'Alertas',             roles: ['admin','pm','hr'] },
    { to: '/exports',         icon: <Download size={SZ} />,      label: 'Exportar datos',      roles: ['admin','pm','hr'] },
  ]},
  { id: 'ia', label: 'IA & Automatización', groupKey: 'group_ai', icon: <Brain size={12} />, roles: ['admin','pm'], items: [
    { to: '/nexus-agent',     icon: <Zap size={SZ} />,           label: 'NexusAgent',       roles: ['admin','pm'] },
    { to: '/oracle',          icon: <Eye size={SZ} />,           label: 'NexusOracle',      roles: ['admin','pm'] },
    { to: '/semantic-engine', icon: <Brain size={SZ} />,         label: 'Asignación IA',    roles: ['admin','pm'] },
    { to: '/automations',     icon: <Bot size={SZ} />,           label: 'Automatizaciones', roles: ['admin','pm'] },
  ]},
  { id: 'configuracion', label: 'Configuración', groupKey: 'group_settings', icon: <Settings size={12} />, roles: ['admin','pm','hr','employee','team_lead'], items: [
    { to: '/settings',            icon: <Settings size={SZ} />,    label: 'Config. general',        roles: ['admin'] },
      { to: '/project-templates',   icon: <Layers size={SZ} />,      label: 'Plantillas proyecto',    roles: ['admin','pm'] },
    { to: '/workflows',           icon: <GitMerge size={SZ} />,    label: 'Workflows',              roles: ['admin','pm'] },
    { to: '/issue-types',         icon: <Tag size={SZ} />,         label: 'Tipos de issue',         roles: ['admin','pm'] },
    { to: '/custom-fields',       icon: <Sliders size={SZ} />,     label: 'Campos personalizados',  roles: ['admin','pm'] },
    { to: '/project-permissions', icon: <Lock size={SZ} />,        label: 'Permisos proyecto',      roles: ['admin','pm'] },
    { to: '/ai-hub',              icon: <Plug size={SZ} />,        label: 'IA Hub / Conectores',    roles: ['admin','pm'] },
    { to: '/esign',               icon: <PenLine size={SZ} />,     label: 'E-Firma',                roles: ['admin','pm'] },
    { to: '/m365',                icon: <Globe size={SZ} />,       label: 'Microsoft 365',          roles: ['admin'] },
    { to: '/import',              icon: <Upload size={SZ} />,      label: 'Importar datos',         roles: ['admin','pm'] },
    { to: '/mfa',                 icon: <ShieldCheck size={SZ} />, label: 'Seguridad MFA',          roles: ['admin','pm','hr','employee','team_lead'] },
    { divider: true },
    { to: '/governance',          icon: <Building2 size={SZ} />,   label: 'AI Governance',          roles: ['admin'] },
    { to: '/grc',                 icon: <Scale size={SZ} />,       label: 'GRC / SoD',              roles: ['admin'] },
    { to: '/organizations',       icon: <Building2 size={SZ} />,   label: 'Organizaciones',         roles: ['admin'] },
    { to: '/enterprise',          icon: <Globe size={SZ} />,       label: 'Enterprise',             roles: ['admin'] },
    { to: '/webhook-log',         icon: <Activity size={SZ} />,    label: 'Log Webhooks',           roles: ['admin'] },
    { to: '/jira-integration',     icon: <Link size={SZ} />,        label: 'Jira Integration',       roles: ['admin','pm'] },
  ]},
]

const SHORTCUTS = [
  { keys: ['⌘', 'K'], labelKey: 'shortcut_global_search' },
  { keys: ['Ctrl', 'I'], labelKey: 'shortcut_ai_assist' },
  { keys: ['?'], labelKey: 'shortcut_view_shortcuts' },
  { keys: ['Esc'], labelKey: 'shortcut_close_modal' },
  { keys: ['⌘', 'B'], labelKey: 'shortcut_toggle_sidebar' },
  { keys: ['G', 'D'], labelKey: 'shortcut_go_dashboard' },
  { keys: ['G', 'T'], labelKey: 'shortcut_go_tasks' },
  { keys: ['G', 'P'], labelKey: 'shortcut_go_projects' },
  { keys: ['G', 'I'], labelKey: 'shortcut_go_log_hours' },
  { keys: ['G', 'S'], labelKey: 'shortcut_go_service_desk' },
]

function getNavKeyForPath(path) {
  return PATH_NAV_KEY[path] || path?.replace(/^\//, '').replace(/-/g, '_')
}

function getNavLabel(path, fallbackLabel, t) {
  const navKey = getNavKeyForPath(path)
  const translated = t ? t('nav', navKey) : null
  if (translated && translated !== navKey) return translated
  return ROUTE_LABELS[path] || fallbackLabel || path?.replace(/^\//, '').replace(/-/g, ' ')
}

function getSectionLabel(path, t) {
  const group = NAV_GROUPS.find(g => (g.items || []).some(
    i => !i.divider && (path === i.to || path.startsWith(i.to + '/'))
  ))
  if (!group || group.single) return null
  const translated = (t && group.groupKey) ? t('nav', group.groupKey) : null
  if (translated && translated !== group.groupKey) return translated
  return group.label
}

function ShortcutsModal({ onClose, text }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    // Focus the modal container on mount
    dialogRef.current?.focus()
    const h = (e) => {
      if (e.key === 'Escape') { onClose(); return }
      // Focus trap
      if (e.key === 'Tab') {
        const focusable = dialogRef.current?.querySelectorAll('button,[href],[tabindex]:not([tabindex="-1"])')
        if (!focusable?.length) return
        const first = focusable[0]; const last = focusable[focusable.length - 1]
        if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
          e.preventDefault()
          ;(e.shiftKey ? last : first).focus()
        }
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={text.keyboard_shortcuts}
        className="modal-glass" style={{ width: 480 }} onClick={e => e.stopPropagation()}
        tabIndex={-1}
      >
        <div className="modal-header">
          <span className="modal-title">
            <Keyboard size={15} style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }} />
            {text.keyboard_shortcuts}
          </span>
          <button className="modal-close" onClick={onClose} aria-label={text.close}><X size={14} /></button>
        </div>
        <div className="shortcuts-grid">
          {SHORTCUTS.map((s, i) => (
            <div key={i} className="shortcut-row">
              <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{text[s.labelKey]}</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {s.keys.map((k, j) => <span key={j} className="kbd">{k}</span>)}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-3)', textAlign: 'center' }}>
          {text.shortcuts_hint} <span className="kbd">?</span> {text.shortcuts_hint_suffix}
        </div>
      </div>
    </div>
  )
}

function NavItem({ item, collapsed, alertCount, approvalCount, t, pinned, onPin, text }) {
  const badge = item.to === '/alerts' ? alertCount : item.to === '/approvals' ? approvalCount : 0
  const badgeColor = item.to === '/approvals' ? '#ffb800' : '#ff4757'
  const displayLabel = getNavLabel(item.to, item.label, t)
  const isPinned = pinned?.includes(item.to)
  const [hover, setHover] = useState(false)

  return (
    <div style={{ position: 'relative' }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <NavLink to={item.to} title={displayLabel} aria-label={displayLabel}
        style={({ isActive }) => ({
          display: 'flex', alignItems: 'center', gap: 8,
          padding: collapsed ? '7px 9px' : '5px 8px 5px 14px',
          borderRadius: 6, textDecoration: 'none', fontSize: 12.5, fontWeight: 500,
          background: isActive ? 'var(--accent-muted)' : 'transparent',
          color: isActive ? 'var(--accent)' : 'var(--text-2)',
          border: `1px solid ${isActive ? 'rgba(79,142,247,0.22)' : 'transparent'}`,
          transition: 'background 0.1s, color 0.1s', whiteSpace: 'nowrap',
          minHeight: 28, paddingRight: (!collapsed && hover && onPin) ? 28 : undefined,
        })}
      >
        <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          {item.icon}
          {collapsed && badge > 0 && (
            <span style={{ position: 'absolute', top: -3, right: -4, width: 6, height: 6,
              background: badgeColor, borderRadius: '50%' }} />
          )}
        </span>
        {!collapsed && <span style={{ flex: 1, fontSize: 12.5 }}>{displayLabel}</span>}
        {!collapsed && badge > 0 && (
          <span style={{ background: badgeColor + '22', color: badgeColor, borderRadius: 9,
            padding: '1px 5px', fontSize: 9.5, fontWeight: 700, flexShrink: 0 }}>{badge}</span>
        )}
      </NavLink>
      {!collapsed && hover && onPin && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onPin(item.to) }}
          title={isPinned ? text.remove_favorite : text.add_favorite}
          style={{
            position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer',
            color: isPinned ? '#f59e0b' : 'var(--text-3)', padding: '2px 4px', lineHeight: 1, fontSize: 13,
          }}
        >{isPinned ? '★' : '☆'}</button>
      )}
    </div>
  )
}

function NavGroup({ group, collapsed, alertCount, approvalCount, hasRole, t, pinned, onPin }) {
  const location = useLocation()
  const isAnyChildActive = group.items.filter(i => !i.divider).some(
    i => location.pathname === i.to || location.pathname.startsWith(i.to + '/')
  )
  const [open, setOpen] = useState(isAnyChildActive)
  const [hoverOpen, setHoverOpen] = useState(false)
  const [hoverTop, setHoverTop] = useState(0)
  const groupRef = useRef(null)
  const hoverTimer = useRef(null)

  // Keep open when the active child lives here; respect forceOpen override
  useEffect(() => { if (isAnyChildActive) setOpen(true) }, [isAnyChildActive])

  const visibleItems = group.items.filter(i => i.divider || !i.roles || i.roles.some(r => hasRole(r)))
  const realVisible = visibleItems.filter(i => !i.divider)
  if (realVisible.length === 0) return null

  const groupKey = group.groupKey
  const translatedGroupLabel = (t && groupKey) ? t('nav', groupKey) : null
  const groupLabel = (translatedGroupLabel && translatedGroupLabel !== groupKey) ? translatedGroupLabel : group.label

  const handleEnter = () => {
    if (!collapsed) return
    clearTimeout(hoverTimer.current)
    const rect = groupRef.current?.getBoundingClientRect()
    if (rect) setHoverTop(rect.top)
    setHoverOpen(true)
  }
  const handleLeave = () => {
    if (!collapsed) return
    hoverTimer.current = setTimeout(() => setHoverOpen(false), 150)
  }

  if (collapsed) {
    return (
      <div ref={groupRef} style={{ marginBottom: 3 }} onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {realVisible.map(item => (
            <NavItem key={item.to} item={item} collapsed alertCount={alertCount} approvalCount={approvalCount} t={t} pinned={pinned} onPin={onPin} />
          ))}
        </div>
        {hoverOpen && (
          <div className="nav-hover-preview" style={{ left: 52, top: hoverTop - 4 }}
            onMouseEnter={() => { clearTimeout(hoverTimer.current); setHoverOpen(true) }}
            onMouseLeave={() => { hoverTimer.current = setTimeout(() => setHoverOpen(false), 150) }}
          >
            <div className="nav-hover-title">{groupLabel}</div>
            {realVisible.map(item => {
              const itemLabel = getNavLabel(item.to, item.label, t)
              return (
              <NavLink key={item.to} to={item.to} onClick={() => setHoverOpen(false)}
                style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 6,
                  textDecoration: 'none', fontSize: 12.5, fontWeight: 500,
                  color: isActive ? 'var(--accent)' : 'var(--text-2)',
                  background: isActive ? 'var(--accent-muted)' : 'transparent',
                })}
              >
                <span style={{ width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{item.icon}</span>
                <span>{itemLabel}</span>
              </NavLink>
              )
            })}
          </div>
        )}
        <div style={{ height: 1, background: 'var(--surface-4)', margin: '3px 0' }} />
      </div>
    )
  }

  return (
    <div style={{ marginBottom: 1 }}>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open} aria-controls={`nav-group-${group.id}`} style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 8px', border: 'none', borderRadius: 5, cursor: 'pointer',
        fontFamily: 'inherit', background: 'transparent',
        color: isAnyChildActive ? 'var(--accent)' : 'var(--text-3)',
        fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.08em', textAlign: 'left', transition: 'color 0.1s',
      }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-2)' }}
        onMouseLeave={e => { e.currentTarget.style.color = isAnyChildActive ? 'var(--accent)' : 'var(--text-3)' }}
      >
        <span style={{ opacity: 0.75, display: 'flex', alignItems: 'center' }}>{group.icon}</span>
        <span style={{ flex: 1 }}>{groupLabel}</span>
        {!open && realVisible.length > 0 && (
          <span style={{ fontSize: 9, background: 'var(--surface-4)', color: 'var(--text-4)',
            borderRadius: 8, padding: '1px 5px', fontWeight: 600, flexShrink: 0 }}>{realVisible.length}</span>
        )}
        <ChevronRight size={10} style={{ opacity: 0.45, transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none', flexShrink: 0 }} />
      </button>
      <div id={`nav-group-${group.id}`} style={{ display: 'grid', gridTemplateRows: open ? '1fr' : '0fr', transition: 'grid-template-rows 0.2s ease' }}>
        <div style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, paddingTop: 1, paddingBottom: 8 }}>
            {visibleItems.map((item, idx) =>
              item.divider
                ? <div key={'div-' + idx} style={{ height: 1, background: 'var(--surface-4)', margin: '4px 8px 5px' }} />
                : <NavItem key={item.to} item={item} collapsed={false} alertCount={alertCount} approvalCount={approvalCount} t={t} pinned={pinned} onPin={onPin} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Favourites / Recents ─────────────────────────────────────────────────────
const PINNED_KEY = 'clarive_pinned_routes'
const RECENT_KEY = 'clarive_recent_routes'
const MAX_RECENT = 5

function _lsGet(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}

function FavoritesSection({ pinned, onPin, collapsed, alertCount, approvalCount, t, allNavItems, quickItems, text }) {
  const pinnedItems = pinned.map(path => allNavItems.find(i => i.to === path)).filter(Boolean)
  const showQuick   = pinnedItems.length === 0
  const displayItems = showQuick ? quickItems : pinnedItems
  if (displayItems.length === 0) return null
  return (
    <div style={{ marginBottom: 4 }}>
      {!collapsed && (
        <div style={{ padding: '4px 8px 4px 10px', fontSize: 9.5, fontWeight: 700,
          letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--text-3)', marginTop: 4,
          display: 'flex', alignItems: 'center', gap: 6 }}>
          {showQuick ? `⚡ ${text.quick_access}` : `★ ${text.favorites}`}
          {showQuick && <span style={{ fontSize: 9, color: 'var(--text-4)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>{text.personalize_hint}</span>}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {displayItems.map(item => (
          <NavItem key={item.to} item={item} collapsed={collapsed}
            alertCount={alertCount} approvalCount={approvalCount}
            t={t} pinned={pinned} onPin={onPin} />
        ))}
      </div>
      <div style={{ height: 1, background: 'var(--surface-4)', margin: collapsed ? '5px 0' : '5px 3px' }} />
    </div>
  )
}

function RecentsSection({ recent, collapsed, text, t }) {
  const allItems = NAV_GROUPS.flatMap(g => g.items || []).filter(i => !i.divider)
  const recentItems = recent.map(path => allItems.find(i => i.to === path)).filter(Boolean)
  if (recentItems.length === 0) return null
  return (
    <div style={{ marginBottom: 4 }}>
      {!collapsed && (
        <div style={{ padding: '2px 8px 2px 10px', fontSize: 9.5, fontWeight: 700,
          letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--text-3)', marginTop: 2 }}>{`⏱ ${text.recent}`}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {recentItems.map(item => {
          const itemLabel = getNavLabel(item.to, item.label, t)
          return (
          <NavLink key={item.to} to={item.to}
            title={itemLabel}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 8,
              padding: collapsed ? '7px 9px' : '5px 8px 5px 14px',
              borderRadius: 6, textDecoration: 'none', fontSize: 12.5, fontWeight: 500,
              background: isActive ? 'var(--accent-muted)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              border: `1px solid ${isActive ? 'rgba(79,142,247,0.22)' : 'transparent'}`,
              minHeight: 28,
            })}
          >
            <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.6 }}>
              {item.icon}
            </span>
            {!collapsed && <span style={{ flex: 1, fontSize: 12.5 }}>{itemLabel}</span>}
          </NavLink>
          )
        })}
      </div>
      <div style={{ height: 1, background: 'var(--surface-4)', margin: collapsed ? '5px 0' : '5px 3px' }} />
    </div>
  )
}

function TopAppBar({ onSearchOpen, onAiToggle, aiOpen, user, onProfileOpen, onLogout, alertCount, approvalCount, t, allNavItems, text }) {
  const location = useLocation()
  const section = getSectionLabel(location.pathname, t) || ROUTE_SECTION[location.pathname]
  const currentNavItem = allNavItems.find(i => location.pathname === i.to)
    || allNavItems.find(i => location.pathname.startsWith(i.to + '/'))
  const pageLabel = currentNavItem
    ? getNavLabel(currentNavItem.to, currentNavItem.label, t)
    : location.pathname.replace(/^\//, '').replace(/-/g, ' ')

  return (
    <div className="app-topbar" role="banner">
      <div className="app-topbar-breadcrumb">
        {section && (
          <>
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{section}</span>
            <ChevronRight size={12} style={{ color: 'var(--text-4)', flexShrink: 0 }} />
          </>
        )}
        <span style={{ color: 'var(--text-1)', fontSize: 13, fontWeight: 600, textTransform: 'capitalize' }}>
          {pageLabel}
        </span>
      </div>
      <div className="app-topbar-center">
        <button onClick={onSearchOpen} title={text.global_search_title}
          aria-label={text.open_global_search}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 20, color: 'var(--text-3)', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: 12, minWidth: 180,
          }}
        >
          <Search size={12} />
          <span style={{ flex: 1 }}>{text.search_placeholder}</span>
          <span style={{ fontSize: 10, background: 'var(--surface-4)', borderRadius: 4,
            padding: '1px 4px', fontFamily: 'monospace', color: 'var(--text-3)' }}>⌘K</span>
        </button>
      </div>
      <div className="app-topbar-right">
        <button onClick={onAiToggle} title={text.ai_title}
          aria-label={text.open_ai} aria-pressed={aiOpen}
          style={{
            display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
            background: aiOpen ? 'var(--accent-muted)' : 'var(--surface-3)',
            border: `1px solid ${aiOpen ? 'rgba(79,142,247,0.35)' : 'var(--surface-4)'}`,
            borderRadius: 8, color: aiOpen ? 'var(--accent)' : 'var(--text-2)',
            cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
          }}
        >
          <Brain size={13} />
          <span>{text.ai_short}</span>
        </button>
        {alertCount > 0 && (
          <NavLink to="/alerts"
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px',
              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: 8, color: 'var(--danger)', textDecoration: 'none',
              fontSize: 12, fontWeight: 600 }}
            title={text.active_alerts_title.replace('{count}', alertCount)}
          >
            <Bell size={13} /><span>{alertCount}</span>
          </NavLink>
        )}
        {approvalCount > 0 && (
          <NavLink to="/approvals"
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px',
              background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 8, color: 'var(--warning)', textDecoration: 'none',
              fontSize: 12, fontWeight: 600 }}
            title={text.pending_approvals_title.replace('{count}', approvalCount)}
          >
            <CheckCircle size={13} /><span>{approvalCount}</span>
          </NavLink>
        )}
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 4px 3px 8px', background: 'var(--surface-3)',
            border: '1px solid var(--surface-4)', borderRadius: 8 }}
          >
            <button onClick={onProfileOpen} title={user.full_name}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                display: 'flex', alignItems: 'center', gap: 7 }}
            >
              <Avatar name={user.full_name} size={24} />
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.full_name}
              </span>
            </button>
            <button onClick={onLogout} title={t ? t('nav', 'logout') : 'Cerrar sesión'}
              style={{ background: 'none', border: 'none', color: 'var(--text-3)',
                cursor: 'pointer', padding: '3px 4px', display: 'flex', alignItems: 'center',
                borderRadius: 5, transition: 'color 0.1s' }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--danger)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
            >
              <LogOut size={13} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sidebar nav search ────────────────────────────────────────────────────────
function NavSearch({ value, onChange, text }) {
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (e.key === '/' && !e.target?.matches('input,textarea,[contenteditable]')) { e.preventDefault(); ref.current?.focus() } }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [])
  return (
    <div style={{ padding: '5px 6px 5px', position: 'relative' }}>
      <Search size={11} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)', pointerEvents: 'none' }} />
      <input
        ref={ref}
        type="search"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={text.filter_menu}
        aria-label={text.filter_menu_aria}
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: '5px 8px 5px 24px',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 6, color: 'var(--text-1)', fontSize: 11.5,
          fontFamily: 'inherit', outline: 'none',
        }}
        onFocus={e => e.target.style.borderColor = 'var(--accent)'}
        onBlur={e => e.target.style.borderColor = 'var(--surface-4)'}
      />
      {value && (
        <button
          onClick={() => onChange('')}
          aria-label={text.clear_search_aria}
          style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)', padding: 2, lineHeight: 1 }}
        ><X size={10} /></button>
      )}
    </div>
  )
}

function NavSearchResults({ query, hasRole, alertCount, approvalCount, onNavigate, text, t }) {
  const allItems = useMemo(() => NAV_GROUPS.flatMap(g => g.items || []).filter(i => !i.divider), [])
  const q = query.toLowerCase().trim()
  const matches = allItems.filter(i => {
    if (i.roles && !i.roles.some(r => hasRole(r))) return false
    const translatedLabel = getNavLabel(i.to, i.label, t)
    const fallbackLabel = ROUTE_LABELS[i.to] || i.label
    return translatedLabel.toLowerCase().includes(q) || fallbackLabel.toLowerCase().includes(q)
  })
  if (matches.length === 0) {
    return <div style={{ padding: '8px 14px', fontSize: 11.5, color: 'var(--text-4)' }}>{text.no_results}</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '3px 4px' }}>
      {matches.map(item => {
        const badge = item.to === '/alerts' ? alertCount : item.to === '/approvals' ? approvalCount : 0
        const badgeColor = item.to === '/approvals' ? '#ffb800' : '#ff4757'
        const itemLabel = getNavLabel(item.to, item.label, t)
        return (
          <NavLink key={item.to} to={item.to} onClick={onNavigate}
            aria-label={itemLabel}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 8px 5px 14px', borderRadius: 6, textDecoration: 'none',
              fontSize: 12.5, fontWeight: 500,
              background: isActive ? 'var(--accent-muted)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              border: `1px solid ${isActive ? 'rgba(79,142,247,0.22)' : 'transparent'}`,
              minHeight: 28,
            })}
          >
            <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{item.icon}</span>
            <span style={{ flex: 1, fontSize: 12.5 }}>{itemLabel}</span>
            {badge > 0 && <span style={{ background: badgeColor + '22', color: badgeColor, borderRadius: 9, padding: '1px 5px', fontSize: 9.5, fontWeight: 700 }}>{badge}</span>}
          </NavLink>
        )
      })}
    </div>
  )
}

export default function Layout({ children }) {
  const { user, logout, hasRole } = useAuth()
  const { prefs, save } = useUserPreferences()
  const { t, lang } = useAppLang()
  const text = LAYOUT_TEXT[lang] || LAYOUT_TEXT.es
  const { alertCount, approvalCount } = useNotificationBadges()

  useEffect(() => {
    const density = prefs?.ui_density || 'normal'
    document.documentElement.setAttribute('data-density', density)
    const root = document.documentElement
    if (density === 'compact') {
      root.style.setProperty('--space-item', '5px')
      root.style.setProperty('--font-size-base', '12px')
    } else if (density === 'comfortable') {
      root.style.setProperty('--space-item', '10px')
      root.style.setProperty('--font-size-base', '14px')
    } else {
      root.style.setProperty('--space-item', '7px')
      root.style.setProperty('--font-size-base', '13px')
    }
  }, [prefs?.ui_density])

  const location = useLocation()
  const [pinned, setPinned] = useState(() => _lsGet(PINNED_KEY))
  const [recent, setRecent] = useState(() => _lsGet(RECENT_KEY))

  // Build helpers once
  const allNavItems = useMemo(() => NAV_GROUPS.flatMap(g => g.items || []).filter(i => !i.divider), [])

  // Quick access items based on user role
  const quickItems = useMemo(() => {
    const role = user?.role || 'employee'
    const paths = QUICK_ACCESS[role] || QUICK_ACCESS.employee
    return paths.map(p => allNavItems.find(i => i.to === p)).filter(Boolean)
  }, [user?.role, allNavItems])

  useEffect(() => {
    const path = location.pathname
    if (path === '/' || path === '/login' || path === '/dashboard') return
    setRecent(prev => {
      const updated = [path, ...prev.filter(p => p !== path)].slice(0, MAX_RECENT)
      localStorage.setItem(RECENT_KEY, JSON.stringify(updated))
      return updated
    })
  }, [location.pathname])

  const togglePin = useCallback((path) => {
    setPinned(prev => {
      const updated = prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]
      localStorage.setItem(PINNED_KEY, JSON.stringify(updated))
      return updated
    })
  }, [])

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [navSearch, setNavSearch] = useState('')
  const [workspace, setWorkspace] = useState(() => localStorage.getItem(NAV_WORKSPACE_KEY) || 'all')
  const [isOverlayNav, setIsOverlayNav] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.innerWidth <= 1024
  })

  useEffect(() => {
    localStorage.setItem(NAV_WORKSPACE_KEY, workspace)
  }, [workspace])

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth
      setCollapsed(width < 1280)
      setIsOverlayNav(width <= 1024)
      if (width > 1024) setMobileOpen(false)
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const handler = (e) => {
      const tag = e.target?.tagName
      const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setSearchOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && e.key === 'i') { e.preventDefault(); setAiOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); setCollapsed(c => !c); return }
      if (e.key === 'Escape') { setSearchOpen(false); setAiOpen(false); setShortcutsOpen(false); setProfileOpen(false); return }
      if (!isInput && e.key === '?') { e.preventDefault(); setShortcutsOpen(o => !o); return }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const _currentDensity = prefs?.ui_density || 'normal'
  const _setDensity = (d) => save({ ui_density: d })

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--surface-0)' }}>
      <a href="#main-content" className="skip-nav">{text.skip_to_content}</a>

      <aside aria-label={text.main_navigation} role="navigation"
        className={mobileOpen ? 'mobile-open' : ''}
        style={{
          width: collapsed && !isOverlayNav ? 46 : 222, flexShrink: 0,
          background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)',
          display: 'flex', flexDirection: 'column',
          transition: 'width 0.2s cubic-bezier(0.4,0,0.2,1), transform 0.25s cubic-bezier(0.4,0,0.2,1)',
          position: isOverlayNav ? 'fixed' : 'sticky',
          left: isOverlayNav ? 0 : undefined,
          top: 0,
          height: '100vh',
          overflow: 'hidden',
          zIndex: isOverlayNav ? 120 : undefined,
          transform: isOverlayNav ? (mobileOpen ? 'translateX(0)' : 'translateX(-100%)') : 'none',
          boxShadow: isOverlayNav ? '4px 0 24px rgba(0,0,0,0.4)' : 'none',
        }}
      >
        {/* Logo row */}
        <div style={{
          padding: collapsed ? '11px 8px' : '11px 13px',
          borderBottom: '1px solid var(--surface-4)',
          display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0, minHeight: 48,
        }}>
          <div style={{
            width: 27, height: 27, flexShrink: 0, borderRadius: 7, background: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(79,142,247,0.35)',
          }}>
            <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
              <path d="M12 4C10.8 2.9 9.5 2.5 8 2.5C5 2.5 2.5 5 2.5 8C2.5 11 5 13.5 8 13.5C9.5 13.5 10.8 13.1 12 12"
                stroke="white" strokeWidth="1.6" strokeLinecap="round" />
              <rect x="7" y="6.5" width="7" height="1.2" rx="0.6" fill="white" opacity="0.95" />
              <rect x="7" y="9" width="5.5" height="1.2" rx="0.6" fill="white" opacity="0.65" />
            </svg>
          </div>
          {!collapsed && (
            <span style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: '-0.02em',
              color: 'var(--text-1)', whiteSpace: 'nowrap', userSelect: 'none' }}>Clarive</span>
          )}
        </div>

        {/* Nav */}
        <nav aria-label={text.side_menu} style={{
          flex: 1, overflowY: 'auto', overflowX: 'hidden',
          padding: collapsed ? '5px 3px' : '5px 4px',
          display: 'flex', flexDirection: 'column', gap: 0,
          scrollbarWidth: 'thin', scrollbarColor: 'var(--surface-4) transparent',
        }}>
          {!collapsed && (
            <div style={{ padding: '4px 6px 3px' }}>
              <div style={{ fontSize: 9.5, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                {text.workspace}
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {[
                  ['all', text.workspace_all],
                  ['work', text.workspace_work],
                  ['projects', text.workspace_projects],
                  ['team', text.workspace_team],
                  ['business', text.workspace_business],
                  ['support', text.workspace_support],
                  ['analytics', text.workspace_analytics],
                  ['ai', text.workspace_ai],
                  ['settings', text.workspace_settings],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setWorkspace(key)}
                    style={{
                      border: '1px solid var(--surface-4)',
                      borderRadius: 999,
                      padding: '2px 7px',
                      fontSize: 10.5,
                      cursor: 'pointer',
                      color: workspace === key ? 'var(--accent)' : 'var(--text-3)',
                      background: workspace === key ? 'var(--accent-muted)' : 'transparent',
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {NAV_GROUPS.map(group => {
            const visible = group.items.some(i => !i.divider && (!i.roles || i.roles.some(r => hasRole(r))))
            if (!visible) return null
            if (!group.single && workspace !== 'all' && !WORKSPACE_GROUPS[workspace]?.includes(group.id)) return null
            if (group.single) {
              const item = group.items[0]
              if (!item.roles || item.roles.some(r => hasRole(r))) {
                return (
                  <div key={group.id} style={{ marginBottom: 0 }}>
                    <NavItem item={item} collapsed={collapsed} alertCount={alertCount} approvalCount={approvalCount} t={t} pinned={pinned} onPin={togglePin} />
                    <div style={{ height: 1, background: 'var(--surface-4)', margin: collapsed ? '4px 0' : '4px 3px' }} />
                    {!collapsed && (
                      <NavSearch value={navSearch} onChange={v => setNavSearch(v)} text={text} />
                    )}
                    <RecentsSection recent={recent} collapsed={collapsed} text={text} t={t} />
                    <FavoritesSection pinned={pinned} onPin={togglePin} collapsed={collapsed}
                      alertCount={alertCount} approvalCount={approvalCount} t={t}
                      allNavItems={allNavItems} quickItems={quickItems} text={text} />
                  </div>
                )
              }
              return null
            }
            if (navSearch.trim()) return null
            return (
              <NavGroup key={group.id} group={group} collapsed={collapsed}
                alertCount={alertCount} approvalCount={approvalCount} hasRole={hasRole} t={t}
                pinned={pinned} onPin={togglePin} />
            )
          })}
          {navSearch.trim() && !collapsed && (
            <NavSearchResults
              query={navSearch} hasRole={hasRole}
              alertCount={alertCount} approvalCount={approvalCount}
              onNavigate={() => setNavSearch('')}
              text={text}
              t={t}
            />
          )}
          <div style={{ padding: '3px 0', marginTop: 4 }}>
            <NotificationCenter collapsed={collapsed} />
          </div>
        </nav>

        {/* Footer */}
        <div style={{
          padding: collapsed ? '6px 3px' : '6px 8px',
          borderTop: '1px solid var(--surface-4)',
          display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0,
        }}>
          <button onClick={() => setCollapsed(c => !c)} title={collapsed ? text.expand_sidebar : text.collapse_sidebar}
            style={{
              background: 'transparent', border: '1px solid var(--surface-4)',
              borderRadius: 6, padding: '5px', cursor: 'pointer', color: 'var(--text-3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.1s', width: '100%',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--surface-5)'; e.currentTarget.style.color = 'var(--text-2)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-3)' }}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>

          {!collapsed && (
            <button onClick={() => setShortcutsOpen(true)} title={`${text.keyboard_shortcuts} (?)`}
              style={{
                background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer',
                fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: 4, padding: '2px', fontFamily: 'inherit', transition: 'color 0.1s',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--text-2)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
            >
              <Keyboard size={11} />
              <span>{text.shortcuts}</span>
              <span className="kbd" style={{ fontSize: 9 }}>?</span>
            </button>
          )}
        </div>
      </aside>

      {isOverlayNav && mobileOpen && (
        <div onClick={() => setMobileOpen(false)} className="mobile-overlay"
          style={{ position: 'fixed', inset: 0, zIndex: 99, background: 'rgba(0,0,0,0.55)', display: 'block' }} />
      )}

      <main id="main-content" aria-label={text.main_content} role="main"
        className="app-main-shell flex min-h-screen min-w-0 flex-1 flex-col"
        style={{ overflow: 'auto' }}>
        <button className="mobile-hamburger" onClick={() => { setCollapsed(false); setMobileOpen(true) }}
          aria-label={text.open_menu}
          style={{
            position: 'fixed', top: 'calc(12px + var(--safe-top))', left: 'calc(12px + var(--safe-left))', zIndex: 100,
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
            borderRadius: 8, width: 36, height: 36, alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
          }}
        >
          <Menu size={18} color="var(--text-2)" />
        </button>
        <TopAppBar
          onSearchOpen={() => setSearchOpen(true)}
          onAiToggle={() => setAiOpen(o => !o)}
          aiOpen={aiOpen}
          user={user}
          onProfileOpen={() => setProfileOpen(true)}
          onLogout={logout}
          alertCount={alertCount}
          approvalCount={approvalCount}
          t={t}
          allNavItems={allNavItems}
        />
        {children}
      </main>

      {searchOpen && <GlobalSearch onClose={() => setSearchOpen(false)} />}
      {aiOpen && <NexusAssistPanel open={aiOpen} onClose={() => setAiOpen(false)} context={{ page: location.pathname }} />}
      {profileOpen && <UserProfilePanel onClose={() => setProfileOpen(false)} />}
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} text={text} />}
      <OfflineIndicator />
    </div>
  )
}
