import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { Avatar, IconButton } from '../ui'
import api, { projectsApi, tasksApi } from '../../services/api'
import GlobalSearch from './GlobalSearch'
import QuickCreateMenu from './QuickCreateMenu'
import NexusAssistPanel from './NexusAssistPanel'
import SelectorDeEmpresa from './SelectorDeEmpresa'
import GlobalChatPanel from './GlobalChatPanel'
import VoiceCommandModal from './VoiceCommandModal'
import UserProfilePanel from './UserProfilePanel'
import AlertsDrawer from './AlertsDrawer'
import Breadcrumbs from './Breadcrumbs'
import useUserPreferences from '../../hooks/useUserPreferences'
import useNotificationBadges from '../../hooks/useNotificationBadges'
import { useChatRealtime } from '../../context/ChatRealtimeContext'
import OfflineIndicator from '../OfflineIndicator'
import { useSwipeGesture } from '../../hooks/useSwipeGesture'
import { useAppLang, EVENTO_IDIOMA_ELEGIDO } from '../../i18n/AppLangContext'
import {
  LayoutDashboard, CheckSquare, Clock, Calendar, Umbrella,
  FileText, Receipt, CheckCircle, Folder, RefreshCw, Sparkles,
  BarChart2, Target, Package, ArrowLeftRight, AlertTriangle, Link,
  GitBranch, BookOpen, Mic, Users, TrendingUp, Award, Network,
  Trophy, Star, UserCheck, Megaphone, CreditCard, DollarSign,
  Briefcase, HardHat, Calculator, ThumbsUp, MessageSquare, Monitor,
  Key, Bell, Download, Zap, Eye, Brain, Bot, Settings, Tag, Sliders,
  Lock, Plug, PenLine, Upload, ShieldCheck, Scale, Building2, Globe,
  Search, LogOut, ChevronRight, ChevronLeft, Menu, X, Activity,
  Timer, Flag, Layers, Shield, Keyboard, BarChart, LayoutGrid,
  Wrench, GitMerge, FolderOpen, ScrollText, ClipboardCheck,
  CalendarRange, Plus, Inbox, Database, Wallet, MessageSquareText, Lightbulb,
} from 'lucide-react'

const ROUTE_LABELS: Record<string, string> = {
  '/work-dashboard': 'Dashboard', '/projects-dashboard': 'Dashboard',
  '/team-dashboard': 'Dashboard', '/finance-dashboard': 'Dashboard',
  '/support-dashboard': 'Dashboard',
  '/tasks': 'Tasks',
  '/time': 'Tiempo', '/imputar': 'Log hours', '/timer': 'Timer', '/timesheets': 'Timesheets',
  '/calendar': 'Calendar', '/absences': 'Absences', '/documents': 'Documents',
  '/expenses': 'Expenses', '/approvals': 'Approvals', '/projects': 'Projects',
  '/sprints': 'Sprints', '/sprint-planning': 'Sprint Planning AI', '/gantt': 'Gantt', '/epic-gantt': 'Epic Gantt',
  '/epics': 'Epics & Roadmap', '/deliverables': 'Deliverables', '/changes': 'Changes',
  '/risks': 'Risks', '/dependencies': 'Dependencies', '/git': 'Git',
  '/wiki': 'Wiki', '/meetings-ai': 'Meeting Assistant',
  '/resources': 'Resources', '/capacity': 'Capacity Planning',
  '/resource-forecast': 'Resource Forecast', '/resource-scheduler': 'Visual Scheduler', '/skills': 'Skills', '/org-chart': 'Org Chart',
  '/okrs': 'OKRs', '/performance-reviews': 'Performance Reviews', '/training': 'Training & Certs',
  '/clients': 'Clients / CRM', '/pipeline': 'Sales Pipeline', '/contracts': 'Contracts',
  '/invoices': 'Invoicing', '/milestone-billing': 'Milestone Billing',
  '/profitability': 'Profitability', '/revenue': 'Revenue Recognition', '/budgets': 'Budgets',
  '/rate-cards': 'Rate Cards', '/subcontractors': 'Subcontractors',
  '/scenarios': 'What-If Scenarios', '/nps': 'NPS & Health',
  '/service-desk': 'Service Desk', '/cmdb': 'CMDB', '/sd/workflow-designer': 'Workflow Designer', '/alm': 'Licenses & Assets',
  '/sla-calendars': 'SLA Calendars', '/agent-dashboard': 'Agent Dashboard',
  '/reports': 'Reports', '/report-builder': 'Report Builder',
  '/executive': 'Executive Dashboard',
  '/data-explorer': 'Data Explorer', '/ask-company': 'Ask the company', '/lessons': 'Lessons learned', '/predictions': 'Predictions',
  '/data-platform': 'Data Platform', '/data-governance': 'Data Governance',
  '/evm': 'EVM — Earned Value', '/portfolio': 'Project Portfolio', '/sprint-charts': 'Burnup & Velocity',
  '/cumulative-flow': 'Cumulative Flow', '/risk-scores': 'Project Risk',
  '/alerts': 'Alerts', '/exports': 'Data Export',
  '/nexus-agent': 'NexusAgent', '/oracle': 'NexusOracle',
  '/semantic-engine': 'AI Assignment', '/automations': 'Automations',
  '/bpm': 'BPM Procesos',
  '/chat': 'Chat',
  '/settings/chat-admin': 'Admin Collaboration',
  '/settings': 'Settings', '/workflows': 'Workflows', '/issue-types': 'Issue Types',
  '/custom-fields': 'Custom Fields', '/project-permissions': 'Project Permissions',
  '/ai-hub': 'AI Hub', '/esign': 'E-Signature', '/m365': 'Microsoft 365',
  '/import': 'Import Data', '/mfa': 'MFA Security',
  '/governance': 'AI Governance', '/grc': 'GRC / SoD', '/organizations': 'Organizations',
  '/enterprise': 'Enterprise', '/webhook-log': 'Webhook Log',
  '/raci': 'RACI Matrix', '/changelog': 'Changelog', '/uat': 'UAT',
  '/jira-integration': 'Jira Integration',
  '/project-templates': 'Project Templates',
  '/search': 'Search',
  '/public-forms': 'Public Forms',
  '/developer': 'Developer Portal',
  '/settings/approval-workflows': 'Approval Flows (Config)',
  '/settings/project-workflows': 'Project Issue Flows',
}

const ROUTE_SECTION: Record<string, string> = {
  '/work-dashboard': 'My Work', '/projects-dashboard': 'Projects',
  '/team-dashboard': 'Team', '/finance-dashboard': 'Finance',
  '/support-dashboard': 'Support',
  '/tasks': 'My Work', '/time': 'My Work', '/imputar': 'My Work', '/chat': 'My Work', '/settings/chat-admin': 'Settings',
  '/timer': 'My Work', '/timesheets': 'My Work', '/calendar': 'My Work',
  '/absences': 'My Work', '/documents': 'My Work', '/expenses': 'My Work',
  '/approvals': 'My Work',
  '/projects': 'Projects', '/projects/:id': 'Detalle de proyecto', '/sprints': 'Projects', '/sprint-planning': 'Projects',
  '/raci': 'Projects', '/changelog': 'Projects', '/uat': 'Projects',
  '/gantt': 'Projects', '/epic-gantt': 'Projects', '/epics': 'Projects', '/deliverables': 'Projects',
  '/changes': 'Projects', '/risks': 'Projects', '/dependencies': 'Projects',
  '/git': 'Projects', '/wiki': 'Projects', '/meetings-ai': 'Projects',
  '/resources': 'Team', '/capacity': 'Team', '/resource-forecast': 'Team', '/resource-scheduler': 'Team',
  '/skills': 'Team', '/org-chart': 'Team', '/okrs': 'Team',
  '/performance-reviews': 'Team', '/training': 'Team',
  '/clients': 'Finance', '/pipeline': 'Finance', '/contracts': 'Finance',
  '/invoices': 'Finance', '/milestone-billing': 'Finance',
  '/profitability': 'Finance', '/revenue': 'Finance', '/budgets': 'Finance',
  '/rate-cards': 'Finance', '/subcontractors': 'Finance',
  '/scenarios': 'Finance', '/nps': 'Finance',
  '/service-desk': 'Support', '/cmdb': 'Support', '/sd/workflow-designer': 'Support', '/alm': 'Support',
  '/sla-calendars': 'Support', '/agent-dashboard': 'Support',
  '/reports': 'Analytics', '/report-builder': 'Analytics',
  '/executive': 'Analytics',
  '/data-explorer': 'Analytics', '/ask-company': 'Analytics', '/lessons': 'Projects', '/predictions': 'Analytics',
  '/data-platform': 'Analytics', '/data-governance': 'Analytics',
  '/evm': 'Analytics', '/portfolio': 'Analytics', '/sprint-charts': 'Analytics',
  '/cumulative-flow': 'Analytics', '/risk-scores': 'Analytics',
  '/alerts': 'Analytics', '/exports': 'Analytics',
  '/nexus-agent': 'AI', '/oracle': 'AI', '/semantic-engine': 'AI', '/automations': 'AI', '/bpm': 'AI',
  '/settings': 'Settings', '/workflows': 'Settings', '/issue-types': 'Settings',
  '/custom-fields': 'Settings', '/project-permissions': 'Settings',
  '/ai-hub': 'Settings', '/esign': 'Settings', '/m365': 'Settings',
  '/import': 'Settings', '/mfa': 'Settings',
  '/governance': 'Settings', '/grc': 'Settings', '/organizations': 'Settings',
  '/enterprise': 'Settings', '/webhook-log': 'Settings',
  '/jira-integration': 'Settings',
  '/project-templates': 'Settings',
  '/settings/approval-workflows': 'Settings',
  '/settings/project-workflows': 'Settings',
  '/search': 'My Work',
  '/public-forms': 'Settings',
  '/developer': 'Settings',
}

const PATH_NAV_KEY: Record<string, string> = {
  '/work-dashboard': 'work_dashboard', '/projects-dashboard': 'projects_dashboard',
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
  '/settings/project-workflows': 'project_issue_flows',
}

const SZ = 13

// ── Quick Access defaults per role ─────────────────────────────────────────────
const QUICK_ACCESS: Record<string, string[]> = {
  admin:     ['/projects', '/alerts', '/settings', '/users', '/pipeline', '/executive'],
  pm:        ['/projects', '/tasks', '/pipeline', '/invoices', '/resources', '/reports'],
  team_lead: ['/tasks', '/sprints', '/projects', '/imputar', '/timesheets'],
  hr:        ['/resources', '/absences', '/performance-reviews', '/training', '/org-chart'],
  employee:  ['/tasks', '/time', '/expenses', '/absences', '/service-desk', '/calendar'],
}

const NAV_WORKSPACE_KEY = 'contecflow_nav_workspace'
const WORKSPACE_GROUPS: Record<string, string[]> = {
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

const LAYOUT_TEXT: Record<string, Record<string, string>> = {
  es: {
    shortcuts: 'Atajos',
    keyboard_shortcuts: 'Atajos de teclado',
    shortcuts_hint: 'Pulsa',
    shortcuts_hint_suffix: 'para ver atajos',
    close: 'Cerrar',
    filter_menu: 'Filtrar menu...',
    filter_menu_aria: 'Filtrar elementos del menú',
    clear_search_aria: 'Borrar búsqueda',
    no_results: 'Sin resultados',
    quick_access: 'Acceso rapido',
    favorites: 'Favoritos',
    add_favorite: 'Añadir a favoritos',
    remove_favorite: 'Quitar de favoritos',
    personalize_hint: 'Arrastra para personalizar',
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
    global_search_title: 'Búsqueda global (⌘K)',
    open_global_search: 'Abrir búsqueda global',
    search_placeholder: 'Buscar...',
    ai_title: 'NexusAgent IA',
    open_ai: 'Abrir asistente IA',
    ai_short: 'Nexus',
    active_alerts_title: 'Alertas activas: {count}',
    pending_approvals_title: 'Aprobaciones pendientes: {count}',
    skip_to_content: 'Ir al contenido',
    main_navigation: 'Navegación principal',
    side_menu: 'Menú lateral',
    expand_sidebar: 'Expandir menú',
    collapse_sidebar: 'Colapsar menú',
    main_content: 'Contenido principal',
    open_menu: 'Abrir menú',
  },
  en: {
    shortcuts: 'Shortcuts',
    keyboard_shortcuts: 'Keyboard shortcuts',
    shortcuts_hint: 'Press',
    shortcuts_hint_suffix: 'to see shortcuts',
    close: 'Close',
    filter_menu: 'Filter menu...',
    filter_menu_aria: 'Filter menu items',
    clear_search_aria: 'Clear search',
    no_results: 'No results',
    quick_access: 'Quick access',
    favorites: 'Favorites',
    add_favorite: 'Add to favorites',
    remove_favorite: 'Remove from favorites',
    personalize_hint: 'Drag to personalize',
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
    global_search_title: 'Global search (⌘K)',
    open_global_search: 'Open global search',
    search_placeholder: 'Search...',
    ai_title: 'NexusAgent AI',
    open_ai: 'Open AI assistant',
    ai_short: 'Nexus',
    active_alerts_title: 'Active alerts: {count}',
    pending_approvals_title: 'Pending approvals: {count}',
    skip_to_content: 'Skip to content',
    main_navigation: 'Main navigation',
    side_menu: 'Side menu',
    expand_sidebar: 'Expand menu',
    collapse_sidebar: 'Collapse menu',
    main_content: 'Main content',
    open_menu: 'Open menu',
  },
}

const NAV_GROUPS: NavGroupConfig[] = [
  { id: 'trabajo', label: 'My Work', groupKey: 'group_work', icon: <Clock size={12} />, roles: ['admin','pm','team_lead','employee','hr'], items: [
    { to: '/work-dashboard',  icon: <LayoutGrid size={SZ} />,   label: 'Mi día',       roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/inbox',           icon: <Inbox size={SZ} />,        label: 'Bandeja de entrada', roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/chat',            icon: <MessageSquare size={SZ} />, label: 'Chat (Teams)',     roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/tasks',           icon: <CheckSquare size={SZ} />,  label: 'Tasks',           roles: ['admin','pm','team_lead','employee'] },
    { to: '/time',            icon: <Clock size={SZ} />,        label: 'Tiempo',          roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/calendar',        icon: <Calendar size={SZ} />,     label: 'Calendar',        roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/absences',        icon: <Umbrella size={SZ} />,     label: 'Absences',        roles: ['admin','pm','hr','team_lead','employee'] },
    { to: '/documents',       icon: <FileText size={SZ} />,     label: 'Documents',       roles: ['admin','pm','hr','team_lead','employee'] },
    { to: '/expenses',        icon: <Receipt size={SZ} />,      label: 'Expenses',        roles: ['admin','pm','hr','employee'] },
    { to: '/approvals',       icon: <CheckCircle size={SZ} />,  label: 'Approval Inbox',       roles: ['admin','pm','team_lead','hr','employee'] },
  ]},
  { id: 'proyectos', label: 'Projects', groupKey: 'group_projects', icon: <Folder size={12} />, roles: ['admin','pm','team_lead'], items: [
    { to: '/projects-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Salud del portfolio', roles: ['admin','pm','team_lead'] },
    { to: '/projects',        icon: <FolderOpen size={SZ} />,     label: 'Projects',            roles: ['admin','pm','team_lead'] },
    { to: '/lessons',         icon: <Lightbulb size={SZ} />,      label: 'Lessons learned',     roles: ['admin','pm','team_lead'] },
    { to: '/sprints',         icon: <RefreshCw size={SZ} />,      label: 'Sprints',             roles: ['admin','pm','team_lead'] },
    { to: '/sprint-planning', icon: <Sparkles size={SZ} />,       label: 'Sprint Planning AI',  roles: ['admin','pm'] },
    { to: '/raci',            icon: <Shield size={SZ} />,          label: 'RACI Matrix',         roles: ['admin','pm','team_lead'] },
    { to: '/changelog',       icon: <ScrollText size={SZ} />,      label: 'Changelog',           roles: ['admin','pm','team_lead'] },
    { to: '/uat',            icon: <ClipboardCheck size={SZ} />,  label: 'UAT',                  roles: ['admin','pm','team_lead'] },
    { to: '/gantt',           icon: <BarChart2 size={SZ} />,      label: 'Gantt',               roles: ['admin','pm','team_lead','employee'] },
    // Auditoria 2026-11 (#45): /epic-gantt existia sin entrada en el menu.
    { to: '/epic-gantt',      icon: <BarChart2 size={SZ} />,      label: 'Gantt de épicas',     roles: ['admin','pm','team_lead'] },
    { to: '/epics',           icon: <Target size={SZ} />,         label: 'Epics & Roadmap',     roles: ['admin','pm','team_lead'] },
    { to: '/deliverables',    icon: <Package size={SZ} />,        label: 'Deliverables',        roles: ['admin','pm'] },
    { to: '/changes',         icon: <ArrowLeftRight size={SZ} />, label: 'Changes',             roles: ['admin','pm'] },
    { to: '/risks',           icon: <AlertTriangle size={SZ} />,  label: 'Risks',               roles: ['admin','pm'] },
    { to: '/dependencies',    icon: <Link size={SZ} />,           label: 'Dependencies',        roles: ['admin','pm','team_lead','employee'] },
    { to: '/git',             icon: <GitBranch size={SZ} />,      label: 'Git Integration',     roles: ['admin','pm'] },
    { to: '/wiki',            icon: <BookOpen size={SZ} />,       label: 'Wiki',                roles: ['admin','pm','team_lead','employee','hr'] },
    { to: '/meetings-ai',     icon: <Mic size={SZ} />,            label: 'Meeting Assistant',   roles: ['admin','pm','team_lead'] },
  ]},
  { id: 'equipo', label: 'Team & People', groupKey: 'group_team', icon: <Users size={12} />, roles: ['admin','pm','hr','team_lead'], items: [
    { to: '/team-dashboard',  icon: <LayoutGrid size={SZ} />,     label: 'Capacidad del equipo', roles: ['admin','pm','hr','team_lead'] },
    { to: '/resources',           icon: <Users size={SZ} />,      label: 'Resources',          roles: ['admin','hr','pm'] },
    { to: '/capacity',            icon: <TrendingUp size={SZ} />, label: 'Capacity',           roles: ['admin','hr','pm'] },
    { to: '/resource-forecast',   icon: <BarChart size={SZ} />,   label: 'Resource Forecast',  roles: ['admin','pm','team_lead'] },
    { to: '/resource-scheduler',  icon: <CalendarRange size={SZ} />, label: 'Visual Scheduler', roles: ['admin','pm','team_lead'] },
    { to: '/skills',              icon: <Award size={SZ} />,      label: 'Skills',             roles: ['admin','pm','hr','employee'] },
    { to: '/org-chart',           icon: <Network size={SZ} />,    label: 'Org Chart',          roles: ['admin','pm','hr'] },
    { to: '/okrs',                icon: <Trophy size={SZ} />,     label: 'OKRs',               roles: ['admin','pm','hr'] },
    { to: '/performance-reviews', icon: <Star size={SZ} />,       label: 'Performance Reviews', roles: ['admin','pm','hr'] },
    { to: '/training',            icon: <BookOpen size={SZ} />,   label: 'Training & Certs',   roles: ['admin','pm','hr','employee'] },
  ]},
  { id: 'negocio', label: 'Clients & Finance', groupKey: 'group_business', icon: <DollarSign size={12} />, roles: ['admin','pm'], items: [
    { to: '/finance-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Resumen financiero',  roles: ['admin','pm'] },
    { to: '/clients',           icon: <UserCheck size={SZ} />,   label: 'Clients / CRM',       roles: ['admin','pm'] },
    { to: '/pipeline',          icon: <Megaphone size={SZ} />,   label: 'Sales Pipeline',       roles: ['admin','pm'] },
    { to: '/contracts',         icon: <ScrollText size={SZ} />,  label: 'Contracts',            roles: ['admin','pm'] },
    { to: '/invoices',          icon: <CreditCard size={SZ} />,  label: 'Invoicing',            roles: ['admin','pm'] },
    { to: '/milestone-billing', icon: <Flag size={SZ} />,        label: 'Milestone Billing',    roles: ['admin','pm'] },
    { to: '/profitability',     icon: <TrendingUp size={SZ} />,  label: 'Profitability',        roles: ['admin','pm'] },
    { to: '/revenue',           icon: <DollarSign size={SZ} />,  label: 'Revenue Recognition',  roles: ['admin','pm'] },
    { to: '/budgets',           icon: <Briefcase size={SZ} />,   label: 'Budgets',              roles: ['admin','pm'] },
    { to: '/rate-cards',        icon: <Tag size={SZ} />,         label: 'Rate Cards',           roles: ['admin','pm'] },
    { to: '/user-costs',        icon: <Wallet size={SZ} />,      label: 'Estructura de coste',  roles: ['admin','hr'] },
    { to: '/subcontractors',    icon: <HardHat size={SZ} />,     label: 'Subcontractors',       roles: ['admin','pm'] },
    { to: '/scenarios',         icon: <Calculator size={SZ} />,  label: 'What-If Scenarios',    roles: ['admin','pm'] },
    { to: '/nps',               icon: <ThumbsUp size={SZ} />,    label: 'NPS & Health',         roles: ['admin','pm'] },
  ]},
  { id: 'soporte', label: 'Support & ITSM', groupKey: 'group_support', icon: <MessageSquare size={12} />, roles: ['admin','pm','hr','employee','team_lead'], items: [
    { to: '/support-dashboard', icon: <LayoutGrid size={SZ} />,  label: 'Estado del soporte',  roles: ['admin','pm','employee','hr','team_lead'] },
    { to: '/service-desk',    icon: <MessageSquare size={SZ} />, label: 'Service Desk',     roles: ['admin','pm','employee','hr','team_lead'] },
    { to: '/cmdb',            icon: <Monitor size={SZ} />,       label: 'CMDB',             roles: ['admin','pm'] },
    { to: '/sd/workflow-designer', icon: <GitBranch size={SZ} />,  label: 'Workflow Designer', roles: ['admin','pm'] },
    { to: '/alm',             icon: <Key size={SZ} />,           label: 'Licenses & Assets', roles: ['admin','pm'] },
    { to: '/sla-calendars',   icon: <Calendar size={SZ} />,      label: 'SLA Calendars',    roles: ['admin','pm'] },
    { to: '/agent-dashboard', icon: <LayoutGrid size={SZ} />,    label: 'Agent Dashboard',  roles: ['admin','pm'] },
  ]},
  { id: 'analisis', label: 'Analytics & BI', groupKey: 'group_analytics', icon: <BarChart2 size={12} />, roles: ['admin','pm','team_lead','hr','employee'], items: [
    { to: '/executive',       icon: <LayoutDashboard size={SZ} />, label: 'Executive Dashboard', roles: ['admin','pm'] },
    { to: '/data-explorer',   icon: <Search size={SZ} />,          label: 'Data Explorer',       roles: ['admin','pm'] },
    { to: '/ask-company',     icon: <MessageSquareText size={SZ} />, label: 'Ask the company',   roles: ['admin','pm','team_lead','hr','employee'] },
    { to: '/reports',         icon: <FileText size={SZ} />,        label: 'Reports',             roles: ['admin','pm','hr','employee'] },
    { to: '/report-builder',  icon: <Wrench size={SZ} />,          label: 'Report Builder',      roles: ['admin','pm'] },
    { to: '/predictions',     icon: <Brain size={SZ} />,           label: 'Predictions',         roles: ['admin','pm'] },
    { to: '/alerts',          icon: <Bell size={SZ} />,            label: 'Alerts',              roles: ['admin','pm','hr'] },
    { to: '/evm',             icon: <BarChart size={SZ} />,        label: 'EVM — Earned Value',  roles: ['admin','pm'] },
    { to: '/portfolio',       icon: <Layers size={SZ} />,          label: 'Project Portfolio',   roles: ['admin','pm'] },
    { to: '/sprint-charts',   icon: <Activity size={SZ} />,        label: 'Burnup & Velocity',   roles: ['admin','pm'] },
    { to: '/cumulative-flow', icon: <BarChart2 size={SZ} />,       label: 'Cumulative Flow',     roles: ['admin','pm'] },
    { to: '/risk-scores',     icon: <Shield size={SZ} />,          label: 'Project Risk',        roles: ['admin','pm'] },
    { to: '/exports',         icon: <Download size={SZ} />,        label: 'Data Export',         roles: ['admin','pm','hr'] },
    { divider: true },
    { to: '/data-platform',   icon: <Database size={SZ} />,        label: 'Data Platform',       roles: ['admin'] },
    { to: '/data-governance', icon: <Shield size={SZ} />,          label: 'Data Governance',     roles: ['admin'] },
  ]},
  { id: 'ia', label: 'AI & Automation', groupKey: 'group_ai', icon: <Brain size={12} />, roles: ['admin','pm'], items: [
    { to: '/nexus-agent',     icon: <Zap size={SZ} />,           label: 'NexusAgent',       roles: ['admin','pm'] },
    { to: '/oracle',          icon: <Eye size={SZ} />,           label: 'NexusOracle',      roles: ['admin','pm'] },
    { to: '/semantic-engine', icon: <Brain size={SZ} />,         label: 'AI Assignment',    roles: ['admin','pm','hr'] },
    { to: '/automations',     icon: <Bot size={SZ} />,           label: 'Automations',      roles: ['admin','pm'] },
    { to: '/bpm',             icon: <Network size={SZ} />,       label: 'BPM Procesos',     roles: ['admin','pm','team_lead'] },
  ]},
  { id: 'configuracion', label: 'Settings', groupKey: 'group_settings', icon: <Settings size={12} />, roles: ['admin','pm','hr','employee','team_lead'], items: [
    { to: '/settings',            icon: <Settings size={SZ} />,    label: 'Settings',               roles: ['admin'] },
      { to: '/project-templates',   icon: <Layers size={SZ} />,      label: 'Project Templates',      roles: ['admin','pm'] },
    { to: '/settings/approval-workflows', icon: <CheckCircle size={SZ} />, label: 'Approval Flows (Config)', roles: ['admin','pm','team_lead'] },
    { to: '/settings/project-workflows',  icon: <GitMerge size={SZ} />,    label: 'Project Issue Flows',     roles: ['admin','pm'] },
    { to: '/issue-types',         icon: <Tag size={SZ} />,         label: 'Issue Types',            roles: ['admin','pm'] },
    { to: '/custom-fields',       icon: <Sliders size={SZ} />,     label: 'Custom Fields',          roles: ['admin','pm'] },
    { to: '/project-permissions', icon: <Lock size={SZ} />,        label: 'Project Permissions',    roles: ['admin','pm'] },
    { to: '/ai-hub',              icon: <Plug size={SZ} />,        label: 'AI Hub / Connectors',    roles: ['admin','pm'] },
    { to: '/esign',               icon: <PenLine size={SZ} />,     label: 'E-Signature',            roles: ['admin','pm'] },
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
    { divider: true },
    { to: '/public-forms',        icon: <Globe size={SZ} />,       label: 'Public Forms',           roles: ['admin','pm'] },
    { to: '/developer',           icon: <Wrench size={SZ} />,      label: 'Developer Portal',       roles: ['admin','pm'] },
  ]},
]

function formatTimerDisplay(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// TODO type: timer payload — needs shared type from timer API
interface TimerState {
  started_at: string
  paused_at?: string | null
  paused_duration_secs?: number
  total_elapsed_seconds?: number | null
  [key: string]: unknown
}

function computeTimerElapsed(timer: TimerState | null | undefined): number {
  if (!timer) return 0
  if (timer.paused_at && timer.total_elapsed_seconds != null) return timer.total_elapsed_seconds
  const startStr = timer.started_at.endsWith('Z') || timer.started_at.includes('+')
    ? timer.started_at : timer.started_at + 'Z'
  const paused = timer.paused_duration_secs || 0
  if (timer.paused_at) {
    const pausedStr = timer.paused_at.endsWith('Z') || timer.paused_at.includes('+')
      ? timer.paused_at : timer.paused_at + 'Z'
    return Math.max(0, Math.floor((new Date(pausedStr).getTime() - new Date(startStr).getTime()) / 1000) - paused)
  }
  return Math.max(0, Math.floor((Date.now() - new Date(startStr).getTime()) / 1000) - paused)
}

const SHORTCUTS = [
  { keys: ['⌘', 'K'], labelKey: 'shortcut_global_search' },
  { keys: ['Ctrl', 'I'], labelKey: 'shortcut_ai_assist' },
  { keys: ['?'], labelKey: 'shortcut_view_shortcuts' },
  { keys: ['Esc'], labelKey: 'shortcut_close_modal' },
  { keys: ['⌘', 'B'], labelKey: 'shortcut_toggle_sidebar' },
  { keys: ['G', 'T'], labelKey: 'shortcut_go_tasks' },
  { keys: ['G', 'P'], labelKey: 'shortcut_go_projects' },
  { keys: ['G', 'I'], labelKey: 'shortcut_go_log_hours' },
  { keys: ['G', 'S'], labelKey: 'shortcut_go_service_desk' },
]

// TODO type: i18n t() — uses module-shorthand signature
type TFn = (module: string, key?: string) => string

function getNavKeyForPath(path: string): string {
  return PATH_NAV_KEY[path] || path?.replace(/^\//, '').replace(/-/g, '_')
}

function getNavLabel(path: string, fallbackLabel: string | undefined, t: TFn | null | undefined): string {
  const navKey = getNavKeyForPath(path)
  const translated = t ? t('nav', navKey) : null
  if (translated && translated !== navKey) return translated
  return ROUTE_LABELS[path] || fallbackLabel || path?.replace(/^\//, '').replace(/-/g, ' ')
}

function getSectionLabel(path: string, t: TFn | null | undefined): string | null {
  const group = NAV_GROUPS.find(g => (g.items || []).some(
    i => !i.divider && (path === i.to || path.startsWith(i.to + '/'))
  ))
  if (!group || group.single) return null
  const translated = (t && group.groupKey) ? t('nav', group.groupKey) : null
  if (translated && translated !== group.groupKey) return translated
  return group.label
}

function ShortcutsModal({ onClose, text }: { onClose: () => void; text: Record<string, string> }) {
  const dialogRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // Focus the modal container on mount
    dialogRef.current?.focus()
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      // Focus trap
      if (e.key === 'Tab') {
        const focusable = dialogRef.current?.querySelectorAll<HTMLElement>('button,[href],[tabindex]:not([tabindex="-1"])')
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
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={text.keyboard_shortcuts}
        className="modal-glass" style={{ width: 480 }} onMouseDown={e => e.stopPropagation()}
        tabIndex={-1}
      >
        <div className="modal-header">
          <span className="modal-title">
            <Keyboard size={15} style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }} />
            {text.keyboard_shortcuts}
          </span>
          <IconButton className="modal-close" onClick={onClose} ariaLabel={text.close}><X size={14} /></IconButton>
        </div>
        <div className="shortcuts-grid">
          {SHORTCUTS.map((s, i) => (
            <div key={i} className="shortcut-row">
              <span className="u-text2-sm">{text[s.labelKey]}</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {s.keys.map((k, j) => <span key={j} className="kbd">{k}</span>)}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, fontSize: "var(--text-xs)", color: 'var(--text-3)', textAlign: 'center' }}>
          {text.shortcuts_hint} <span className="kbd">?</span> {text.shortcuts_hint_suffix}
        </div>
      </div>
    </div>
  )
}

// TODO type: nav item config — defined as plain object literal in NAV_GROUPS
interface NavItemConfig {
  to?: string
  icon?: React.ReactNode
  label?: string
  roles?: string[]
  divider?: boolean
}

interface NavItemProps {
  item: NavItemConfig
  collapsed?: boolean
  alertCount?: number
  approvalCount?: number
  t?: TFn | null
  pinned?: string[]
  onPin?: (to: string) => void
  text?: Record<string, string>
}

function NavItem({ item, collapsed, alertCount, approvalCount, t, pinned, onPin, text = {} }: NavItemProps) {
  const { unread: chatUnread } = useChatRealtime()
  const badge = (item.to === '/alerts' ? alertCount
              : item.to === '/approvals' ? approvalCount
              : item.to === '/chat' ? chatUnread
              : 0) ?? 0
  const badgeColor = item.to === '/approvals' ? 'var(--warning)'
                   : item.to === '/chat' ? 'var(--accent)'
                   : 'var(--danger)'
  const displayLabel = getNavLabel(item.to || '', item.label, t)
  const isPinned = pinned?.includes(item.to || '')
  const [hover, setHover] = useState<boolean>(false)

  // El «hover» va en el contenedor y no en el enlace: la estrella es hermana del
  // enlace, y al mover el ratón hacia ella se salía del enlace y desaparecía
  // antes de poder pulsarla (revisión 2026-11).
  const verEstrella = !collapsed && Boolean(onPin) && (hover || isPinned)
  return (
    <div role="group" style={{ position: 'relative' }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHover(false) }}>
      <NavLink to={item.to || '#'} title={displayLabel} aria-label={displayLabel}
        style={({ isActive }) => ({
          display: 'flex', alignItems: 'center', gap: 8,
          paddingTop: collapsed ? 7 : 5,
          paddingBottom: collapsed ? 7 : 5,
          paddingLeft: collapsed ? 9 : 14,
          paddingRight: verEstrella ? 28 : (collapsed ? 9 : 8),
          borderRadius: 'var(--radius-sm)', textDecoration: 'none', fontSize: "var(--text-sm-h)", fontWeight: 500,
          background: isActive ? 'var(--accent-muted)' : 'transparent',
          color: isActive ? 'var(--accent)' : 'var(--text-2)',
          border: `1px solid ${isActive ? 'color-mix(in srgb, var(--accent) 22%, transparent)' : 'transparent'}`,
          transition: 'background 0.1s, color 0.1s', whiteSpace: 'nowrap',
          minHeight: 28,
        })}
      >
        <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          {item.icon}
          {collapsed && badge > 0 && (
            <span style={{ position: 'absolute', top: -3, right: -4, width: 6, height: 6,
              background: badgeColor, borderRadius: '50%' }} />
          )}
        </span>
        {!collapsed && <span style={{ flex: 1, fontSize: "var(--text-sm-h)" }}>{displayLabel}</span>}
        {!collapsed && badge > 0 && (
          <span style={{ background: 'color-mix(in srgb, var(--warning) 15%, transparent)', color: badgeColor, borderRadius: 9,
            padding: '1px 5px', fontSize: "var(--text-3xs-h)", fontWeight: 700, flexShrink: 0 }}>{badge}</span>
        )}
      </NavLink>
      {verEstrella && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onPin(item.to || '') }}
          aria-label={isPinned ? text.remove_favorite : text.add_favorite}
          title={isPinned ? text.remove_favorite : text.add_favorite}
          style={{
            position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer',
            color: isPinned ? 'var(--warning)' : 'var(--text-3)', padding: '2px 4px', lineHeight: 1, fontSize: "var(--text-base)",
          }}
        >{isPinned ? '★' : '☆'}</button>
      )}
    </div>
  )
}

// TODO type: nav group config — defined as plain object literal in NAV_GROUPS
interface NavGroupConfig {
  id?: string
  label: string
  groupKey?: string
  icon?: React.ReactNode
  roles?: string[]
  items: NavItemConfig[]
  single?: boolean
}

interface NavGroupProps {
  group: NavGroupConfig
  collapsed?: boolean
  alertCount?: number
  approvalCount?: number
  hasRole: (...roles: string[]) => boolean
  t?: TFn | null
  pinned?: string[]
  onPin: (to: string) => void
  /** Textos del menú (nombre accesible de la estrella de favoritos). */
  text?: Record<string, string>
  /** Acordeón: solo un grupo abierto a la vez (lo decide `Layout`). */
  open: boolean
  onToggle: () => void
  onActive: () => void
}

function NavGroup({ group, collapsed, alertCount, approvalCount, hasRole, t, pinned, onPin, text, open, onToggle, onActive }: NavGroupProps) {
  const location = useLocation()
  const isAnyChildActive = group.items.filter(i => !i.divider).some(
    i => location.pathname === i.to || location.pathname.startsWith(i.to + '/')
  )
  const [hoverOpen, setHoverOpen] = useState<boolean>(false)
  const [hoverTop, setHoverTop] = useState<number>(0)
  const groupRef = useRef<HTMLDivElement | null>(null)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Al navegar a una pantalla de este grupo, se abre (y se cierran los demás).
  useEffect(() => { if (isAnyChildActive) onActive() }, [isAnyChildActive]) // eslint-disable-line react-hooks/exhaustive-deps

  const visibleItems = group.items.filter(i => i.divider || !i.roles || i.roles.some(r => hasRole(r)))
  const realVisible = visibleItems.filter(i => !i.divider)
  if (realVisible.length === 0) return null

  const groupKey = group.groupKey
  const translatedGroupLabel = (t && groupKey) ? t('nav', groupKey) : null
  const groupLabel = (translatedGroupLabel && translatedGroupLabel !== groupKey) ? translatedGroupLabel : group.label

  const handleEnter = () => {
    if (!collapsed) return
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
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
      <div ref={groupRef} style={{ marginBottom: 3 }} onPointerEnter={handleEnter} onPointerLeave={handleLeave}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {realVisible.map(item => (
            <NavItem key={item.to} item={item} collapsed alertCount={alertCount} approvalCount={approvalCount} t={t} pinned={pinned} onPin={onPin} text={text} />
          ))}
        </div>
        {hoverOpen && (
          <div className="nav-hover-preview" style={{ left: 52, top: hoverTop - 4 }}
            onPointerEnter={() => { if (hoverTimer.current) clearTimeout(hoverTimer.current); setHoverOpen(true) }}
            onPointerLeave={() => { hoverTimer.current = setTimeout(() => setHoverOpen(false), 150) }}
          >
            <div className="nav-hover-title">{groupLabel}</div>
            {realVisible.map(item => {
              const itemLabel = getNavLabel(item.to || '', item.label, t)
              return (
              <NavLink key={item.to} to={item.to || '#'} onClick={() => setHoverOpen(false)}
                style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 'var(--radius-sm)',
                  textDecoration: 'none', fontSize: "var(--text-sm-h)", fontWeight: 500,
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
      <button onClick={onToggle} aria-expanded={open} aria-controls={`nav-group-${group.id}`} style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 6,
        padding: '6px 8px', border: 'none', borderRadius: 5, cursor: 'pointer',
        fontFamily: 'inherit', background: 'transparent',
        color: isAnyChildActive ? 'var(--accent)' : 'var(--text-3)',
        fontSize: "var(--text-2xs)", fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.08em', textAlign: 'left', transition: 'color 0.1s',
      }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-2)' }}
        onMouseLeave={e => { e.currentTarget.style.color = isAnyChildActive ? 'var(--accent)' : 'var(--text-3)' }}
      >
        <span style={{ opacity: 0.75, display: 'flex', alignItems: 'center' }}>{group.icon}</span>
        <span className="u-flex1">{groupLabel}</span>
        {!open && realVisible.length > 0 && (
          <span style={{ fontSize: "var(--text-3xs)", background: 'var(--surface-4)', color: 'var(--text-4)',
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
                : <NavItem key={item.to} item={item} collapsed={false} alertCount={alertCount} approvalCount={approvalCount} t={t} pinned={pinned} onPin={onPin} text={text} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Favourites / Recents ─────────────────────────────────────────────────────
const PINNED_KEY = 'contecflow_pinned_routes'

function _lsGet(key: string): string[] {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}

interface FavoritesSectionProps {
  pinned: string[]
  onPin: (to: string) => void
  collapsed?: boolean
  alertCount?: number
  approvalCount?: number
  t?: TFn | null
  allNavItems: NavItemConfig[]
  quickItems: NavItemConfig[]
  text: Record<string, string>
}

function FavoritesSection({ pinned, onPin, collapsed, alertCount, approvalCount, t, allNavItems, quickItems, text }: FavoritesSectionProps) {
  const pinnedItems = pinned.map(path => allNavItems.find(i => i.to === path)).filter((i): i is NavItemConfig => Boolean(i))
  const showQuick   = pinnedItems.length === 0
  const displayItems = showQuick ? quickItems : pinnedItems
  if (displayItems.length === 0) return null
  return (
    <div style={{ marginBottom: 4 }}>
      {!collapsed && (
        <div style={{ padding: '4px 8px 4px 10px', fontSize: "var(--text-3xs-h)", fontWeight: 700,
          letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--text-3)', marginTop: 4,
          display: 'flex', alignItems: 'center', gap: 6 }}>
          {showQuick ? `⚡ ${text.quick_access}` : `★ ${text.favorites}`}
          {showQuick && <span style={{ fontSize: "var(--text-3xs)", color: 'var(--text-4)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>{text.personalize_hint}</span>}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {displayItems.map(item => (
          <NavItem key={item.to} item={item} collapsed={collapsed}
            alertCount={alertCount} approvalCount={approvalCount}
            t={t} pinned={pinned} onPin={onPin} text={text} />
        ))}
      </div>
      <div style={{ height: 1, background: 'var(--surface-4)', margin: collapsed ? '5px 0' : '5px 3px' }} />
    </div>
  )
}

// TODO type: timer payload — needs shared type from timer API
interface ActiveTimer {
  project_id?: string | number
  task_id?: string | number
  project_name?: string
  task_name?: string
  started_at?: string
  paused_at?: string | null
  paused_duration_secs?: number
  total_elapsed_seconds?: number | null
  [key: string]: unknown
}

// TODO type: auth user payload — needs shared type from authContext
interface AuthUser {
  id?: string | number
  full_name?: string
  email?: string
  role?: string
  avatar_url?: string
  [key: string]: unknown
}

interface TopAppBarProps {
  onSearchOpen: () => void
  onAiToggle: () => void
  aiOpen: boolean
  onChatToggle: () => void
  chatOpen: boolean
  chatUnread: number
  user: AuthUser | null | undefined
  onProfileOpen: () => void
  onLogout: () => void
  alertCount?: number
  approvalCount?: number
  t?: TFn | null
  allNavItems: NavItemConfig[]
  text: Record<string, string>
  activeTimer: ActiveTimer | null | undefined
  timerElapsed: number
  onAlertsOpen: () => void
  onQuickCreate: () => void
  onVoiceOpen: () => void
}

function TopAppBar({ onSearchOpen, onAiToggle, aiOpen, onChatToggle, chatOpen, chatUnread, user, onProfileOpen, onLogout, alertCount, approvalCount, t, allNavItems, text, activeTimer, timerElapsed, onAlertsOpen: _onAlertsOpen, onQuickCreate, onVoiceOpen }: TopAppBarProps) {
  const { t: traducir } = useAppLang()
  const location = useLocation()
  const [chatBadgeVisible, setChatBadgeVisible] = useState<boolean>(chatUnread > 0)
  const [chatBadgeCount, setChatBadgeCount] = useState<number>(chatUnread)

  useEffect(() => {
    if (chatUnread > 0) {
      setChatBadgeCount(chatUnread)
      setChatBadgeVisible(true)
      return undefined
    }
    const id = setTimeout(() => setChatBadgeVisible(false), 120)
    return () => clearTimeout(id)
  }, [chatUnread])

  const section = getSectionLabel(location.pathname, t) || ROUTE_SECTION[location.pathname]
  const currentNavItem = allNavItems
    .filter(i => location.pathname === i.to || location.pathname.startsWith((i.to || '') + '/'))
    .sort((a, b) => (b.to || '').length - (a.to || '').length)[0]

  // Resolve project name for /projects/:id breadcrumb
  const projectIdMatch = location.pathname.match(/^\/projects\/([^/]+)$/)
  const projectId = projectIdMatch?.[1]
  const { data: breadcrumbProject } = useQuery({
    queryKey: ['breadcrumb-project', projectId],
    queryFn: () => projectsApi.get(projectId as string).then(r => r.data),
    enabled: !!projectId,
    staleTime: 300_000,
  })

  const { data: timerProject } = useQuery({
    queryKey: ['topbar-timer-project', activeTimer?.project_id],
    queryFn: () => projectsApi.get(activeTimer?.project_id as string).then(r => r.data),
    enabled: !!activeTimer?.project_id && !activeTimer?.project_name,
    staleTime: 300_000,
  })

  const { data: timerTask } = useQuery({
    queryKey: ['topbar-timer-task', activeTimer?.task_id],
    queryFn: () => tasksApi.get(activeTimer?.task_id as string).then(r => r.data),
    enabled: !!activeTimer?.task_id && !activeTimer?.task_name,
    staleTime: 300_000,
  })

  const topbarProjectLabel = activeTimer?.project_name || timerProject?.name || (activeTimer?.project_id ? `Proyecto #${activeTimer.project_id}` : null)
  const topbarTaskLabel = activeTimer?.task_name || timerTask?.title || (activeTimer?.task_id ? `Tarea #${activeTimer.task_id}` : null)
  const topbarTimerSubtitle = topbarTaskLabel ? `${topbarProjectLabel} · ${topbarTaskLabel}` : topbarProjectLabel

  const breadcrumbs = useMemo(() => {
    const items: { label: string; to: string | null }[] = []
    const pathname = location.pathname || '/'
    const segments = pathname.split('/').filter(Boolean)

    if (section) {
      items.push({ label: section, to: null })
    }

    if (currentNavItem) {
      const baseLabel = getNavLabel(currentNavItem.to || '', currentNavItem.label, t)
      const isExactBase = pathname === currentNavItem.to
      items.push({ label: baseLabel, to: isExactBase ? null : (currentNavItem.to ?? null) })

      if (!isExactBase) {
        const baseSegments = (currentNavItem.to || '').split('/').filter(Boolean)
        const extraSegments = segments.slice(baseSegments.length)
        let accPath = currentNavItem.to || ''

        extraSegments.forEach((seg, idx) => {
          accPath += `/${seg}`
          const isLast = idx === extraSegments.length - 1
          const isIdLike = /^\d+$/.test(seg) || /^[0-9a-fA-F-]{8,}$/.test(seg)
          let label = isIdLike ? 'Detalle' : decodeURIComponent(seg).replace(/-/g, ' ')
          // Use real project name when on /projects/:id
          if (isIdLike && currentNavItem?.to === '/projects' && breadcrumbProject?.name) {
            label = breadcrumbProject.name
          }
          items.push({ label, to: isLast ? null : accPath })
        })
      }

      return items
    }

    if (!segments.length) {
      items.push({ label: 'Inicio', to: null })
      return items
    }

    let accPath = ''
    segments.forEach((seg, idx) => {
      accPath += `/${seg}`
      const isLast = idx === segments.length - 1
      const isIdLike = /^\d+$/.test(seg) || /^[0-9a-fA-F-]{8,}$/.test(seg)
      const label = isIdLike ? 'Detalle' : decodeURIComponent(seg).replace(/-/g, ' ')
      items.push({ label, to: isLast ? null : accPath })
    })
    return items
  }, [location.pathname, section, currentNavItem, t, breadcrumbProject])

  return (
    <div className="app-topbar" role="banner">
      <Breadcrumbs items={breadcrumbs} />
      <div className="app-topbar-center">
        <button onClick={onSearchOpen} title={text.global_search_title}
          aria-label={text.open_global_search}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 20, color: 'var(--text-3)', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: "var(--text-sm)", minWidth: 180,
          }}
        >
          <Search size={12} />
          <span className="app-topbar-texto u-flex1">{text.search_placeholder}</span>
          <span className="app-topbar-texto" style={{ fontSize: "var(--text-2xs)", background: 'var(--surface-4)', borderRadius: 4,
            padding: '1px 4px', fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>⌘K</span>
        </button>
      </div>
      <div className="app-topbar-right">
        <button onClick={onQuickCreate}
          title={traducir('layout.crear_nuevo')}
          aria-label={traducir('layout.crear_nuevo_2')}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 30, height: 30,
            background: 'var(--accent)', border: 'none',
            borderRadius: 8, color: 'var(--on-accent-light)', cursor: 'pointer',
            fontWeight: 700, fontSize: "var(--text-lg-em)", lineHeight: 1,
          }}
          onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          <Plus size={16} />
        </button>
        <button onClick={onAiToggle} title={text.ai_title}
          aria-label={text.open_ai} aria-pressed={aiOpen}
          style={{
            display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
            background: aiOpen ? 'var(--accent-muted)' : 'var(--surface-3)',
            border: `1px solid ${aiOpen ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--surface-4)'}`,
            borderRadius: 8, color: aiOpen ? 'var(--accent)' : 'var(--text-2)',
            cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit',
          }}
        >
          <Brain size={13} />
          <span className="app-topbar-texto">{text.ai_short}</span>
        </button>
        {/* I25: Voice command modal — accesible desde cualquier página */}
        <button
          onClick={onVoiceOpen}
          title={traducir('layout.comando_de_voz_imputar_crear_ticket_tarea')}
          aria-label={traducir('layout.abrir_comando_de_voz')}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 30, height: 30,
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, color: 'var(--text-2)', cursor: 'pointer',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-2)' }}
        >
          <Mic size={14} />
        </button>
        <button
          onClick={onChatToggle}
          title="Abrir chat interno"
          aria-label="Abrir chat interno"
          aria-pressed={chatOpen}
          style={{
            display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
            background: chatOpen ? 'var(--accent-muted)' : 'var(--surface-3)',
            border: `1px solid ${chatOpen ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--surface-4)'}`,
            borderRadius: 8, color: chatOpen ? 'var(--accent)' : 'var(--text-2)',
            cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit',
            position: 'relative',
          }}
        >
          <MessageSquare size={13} />
          <span className="app-topbar-texto">Chat</span>
          {chatBadgeVisible && (
            <span style={{
              position: 'absolute', top: -5, right: -5,
              minWidth: 16, height: 16, borderRadius: 'var(--radius-full)',
              background: 'var(--danger)', color: 'var(--on-accent-light)',
              fontSize: "var(--text-3xs)", fontWeight: 800,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              padding: '0 4px',
              opacity: chatUnread > 0 ? 1 : 0,
              transform: chatUnread > 0 ? 'scale(1)' : 'scale(0.9)',
              transition: 'opacity .12s ease, transform .12s ease',
            }}>
              {chatBadgeCount > 99 ? '99+' : chatBadgeCount}
            </span>
          )}
        </button>
        {activeTimer && !activeTimer.paused_at && (
          <NavLink to="/timer"
            title={topbarTimerSubtitle ? `Cronómetro activo: ${topbarTimerSubtitle}` : 'Cronómetro activo — click para gestionar'}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
              background: 'var(--success-bg)', border: '1px solid var(--success-border)',
              borderRadius: 8, color: 'var(--success)', textDecoration: 'none',
              fontSize: "var(--text-sm)", fontWeight: 700,
            }}
          >
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: 'var(--success)',
              boxShadow: '0 0 10px var(--success)', animation: 'timerPulse 1.5s ease-in-out infinite',
            }} />
            <Timer size={12} />
            <span className="u-mono">{formatTimerDisplay(timerElapsed)}</span>
            {topbarTimerSubtitle && (
              <span style={{
                maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                color: 'var(--text-2)', fontSize: "var(--text-xs)", fontWeight: 600,
              }}>
                {topbarTimerSubtitle}
              </span>
            )}
          </NavLink>
        )}
        {/* Inbox bell unificado: alerts + mentions + approvals */}
        {(() => {
          const total = (alertCount || 0) + (approvalCount || 0)
          if (total === 0) return null
          const tone = (alertCount || 0) > 0 ? 'danger' : 'warning'
          const bg = tone === 'danger' ? 'var(--danger-bg)' : 'var(--warning-bg)'
          const border = tone === 'danger' ? 'var(--danger-border)' : 'var(--warning-border)'
          const color = tone === 'danger' ? 'var(--danger)' : 'var(--warning)'
          return (
            <NavLink to="/inbox"
              style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px',
                background: bg, border: `1px solid ${border}`,
                borderRadius: 8, color, textDecoration: 'none',
                fontSize: "var(--text-sm)", fontWeight: 600 }}
              title={`${total} pendientes en bandeja`}
              aria-label={`Bandeja de entrada — ${total} pendientes`}
            >
              <Bell size={13} /><span>{total}</span>
            </NavLink>
          )
        })()}
        {user && <SelectorDeEmpresa />}
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 4px 3px 8px', background: 'var(--surface-3)',
            border: '1px solid var(--surface-4)', borderRadius: 8 }}
          >
            <button onClick={onProfileOpen} title={user.full_name}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                display: 'flex', alignItems: 'center', gap: 7 }}
            >
              <Avatar name={user.full_name} size={24} url={undefined} />
              <span className="app-topbar-texto" style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)',
                maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.full_name}
              </span>
            </button>
            <IconButton onClick={onLogout}
              ariaLabel={t ? t('nav', 'logout') : 'Cerrar sesión'}
              style={{ color: 'var(--text-3)',
                cursor: 'pointer', padding: '3px 4px', display: 'flex', alignItems: 'center',
                borderRadius: 5, transition: 'color 0.1s' }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--danger)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
            >
              <LogOut size={13} />
            </IconButton>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sidebar nav search ────────────────────────────────────────────────────────
function NavSearch({ value, onChange, text }: { value: string; onChange: (v: string) => void; text: Record<string, string> }) {
  const ref = useRef<HTMLInputElement | null>(null)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.key === '/' && !target?.matches?.('input,textarea,[contenteditable]')) { e.preventDefault(); ref.current?.focus() }
    }
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
          borderRadius: 'var(--radius-sm)', color: 'var(--text-1)', fontSize: "var(--text-xs-h)",
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

interface NavSearchResultsProps {
  query: string
  hasRole: (...roles: string[]) => boolean
  alertCount?: number
  approvalCount?: number
  onNavigate: () => void
  text: Record<string, string>
  t?: TFn | null
}

function NavSearchResults({ query, hasRole, alertCount, approvalCount, onNavigate, text, t, groups = NAV_GROUPS }: NavSearchResultsProps & { groups?: NavGroupConfig[] }) {
  const allItems = useMemo(() => groups.flatMap(g => g.items || []).filter(i => !i.divider), [groups])
  const q = query.toLowerCase().trim()
  const matches = allItems.filter(i => {
    if (i.roles && !i.roles.some(r => hasRole(r))) return false
    const translatedLabel = getNavLabel(i.to || '', i.label, t)
    const fallbackLabel = ROUTE_LABELS[i.to || ''] || i.label || ''
    return translatedLabel.toLowerCase().includes(q) || fallbackLabel.toLowerCase().includes(q)
  })
  if (matches.length === 0) {
    return <div style={{ padding: '8px 14px', fontSize: "var(--text-xs-h)", color: 'var(--text-4)' }}>{text.no_results}</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '3px 4px' }}>
      {matches.map(item => {
        const badge = (item.to === '/alerts' ? alertCount : item.to === '/approvals' ? approvalCount : 0) ?? 0
        const badgeColor = item.to === '/approvals' ? 'var(--warning)' : 'var(--danger)'
        const itemLabel = getNavLabel(item.to || '', item.label, t)
        return (
          <NavLink key={item.to} to={item.to || ''} onClick={onNavigate}
            aria-label={itemLabel}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 8px 5px 14px', borderRadius: 'var(--radius-sm)', textDecoration: 'none',
              fontSize: "var(--text-sm-h)", fontWeight: 500,
              background: isActive ? 'var(--accent-muted)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              border: `1px solid ${isActive ? 'color-mix(in srgb, var(--accent) 22%, transparent)' : 'transparent'}`,
              minHeight: 28,
            })}
          >
            <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{item.icon}</span>
            <span style={{ flex: 1, fontSize: "var(--text-sm-h)" }}>{itemLabel}</span>
            {badge > 0 && <span style={{ background: 'color-mix(in srgb, var(--warning) 15%, transparent)', color: badgeColor, borderRadius: 9, padding: '1px 5px', fontSize: "var(--text-3xs-h)", fontWeight: 700 }}>{badge}</span>}
          </NavLink>
        )
      })}
    </div>
  )
}

export default function Layout({ children }: { children?: React.ReactNode }) {
  const { user, logout, hasRole, canOpen = () => true } = useAuth()
  const navigate = useNavigate()
  const { prefs, save } = useUserPreferences()
  const { t, lang, setCustomTranslations } = useAppLang()

  // Revisión 2026-11: el idioma elegido se guarda en el servidor (antes no se
  // guardaba nunca), y las traducciones que personaliza el administrador se
  // leen de la empresa (antes solo existían en su navegador).
  useEffect(() => {
    const guardar = (e: Event) => {
      const code = (e as CustomEvent<{ lang?: string }>).detail?.lang
      if (code) save({ language: code })
    }
    window.addEventListener(EVENTO_IDIOMA_ELEGIDO, guardar)
    return () => window.removeEventListener(EVENTO_IDIOMA_ELEGIDO, guardar)
  }, [save])
  const { data: traduccionesDeLaEmpresa } = useQuery({
    queryKey: ['app-translations'],
    queryFn: () => api.get('/settings/app-translations').then((r: { data: Record<string, Record<string, unknown>> }) => r.data),
    enabled: !!user, staleTime: 5 * 60 * 1000, retry: false,
  })
  useEffect(() => {
    if (traduccionesDeLaEmpresa) setCustomTranslations(traduccionesDeLaEmpresa as Record<string, Record<string, unknown>>)
  }, [traduccionesDeLaEmpresa, setCustomTranslations])
  const text = LAYOUT_TEXT[lang] || LAYOUT_TEXT.es
  const { alertCount, approvalCount } = useNotificationBadges()
  const { unread: chatUnread } = useChatRealtime()

  // La densidad la aplica useUserPreferences (applyDensity), un solo sitio.

  const location = useLocation()
  const [pinned, setPinned] = useState<string[]>(() => _lsGet(PINNED_KEY))
  // Auditoría 2026-11: acordeón. Abrir un grupo del menú cierra los demás.
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  // Auditoría 2026-11: los módulos que cierra el rol desaparecen del menú.
  const navGroups = useMemo(() => NAV_GROUPS.map(g => ({
    ...g, items: (g.items || []).filter(i => i.divider || !i.to || canOpen(i.to)),
  })), [canOpen])
  const allNavItems = useMemo(() => navGroups.flatMap(g => g.items || []).filter(i => !i.divider), [navGroups])

  // Quick access items based on user role
  const quickItems = useMemo(() => {
    const role = user?.role || 'employee'
    const paths = QUICK_ACCESS[role] || QUICK_ACCESS.employee
    return paths.map(p => allNavItems.find(i => i.to === p)).filter((i): i is NavItemConfig => Boolean(i))
  }, [user?.role, allNavItems])

  const togglePin = useCallback((path: string) => {
    setPinned(prev => {
      const updated = prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]
      localStorage.setItem(PINNED_KEY, JSON.stringify(updated))
      return updated
    })
  }, [])

  const [collapsed, setCollapsed] = useState<boolean>(false)
  const [mobileOpen, setMobileOpen] = useState<boolean>(false)
  const swipeHandlers = useSwipeGesture({
    onSwipeRight: () => setMobileOpen(true),
    onSwipeLeft:  () => setMobileOpen(false),
  })
  // Auditoría 2026-11: un solo panel de la barra abierto a la vez. Abrir uno
  // (búsqueda, IA, chat, perfil, atajos, alertas, crear, voz) cierra el resto.
  const [panel, setPanel] = useState<string | null>(null)
  const setters = useMemo(() => {
    const de = (id: string) => (v: boolean | ((actual: boolean) => boolean)) =>
      setPanel(p => {
        const actual = p === id
        const nuevo = typeof v === 'function' ? v(actual) : v
        return nuevo ? id : (actual ? null : p)
      })
    return { search: de('search'), ai: de('ai'), chat: de('chat'), profile: de('profile'),
      shortcuts: de('shortcuts'), alerts: de('alerts'), quick: de('quick'), voice: de('voice') }
  }, [])
  const searchOpen = panel === 'search', setSearchOpen = setters.search
  const aiOpen = panel === 'ai', setAiOpen = setters.ai
  const chatOpen = panel === 'chat', setChatOpen = setters.chat
  const profileOpen = panel === 'profile', setProfileOpen = setters.profile
  const shortcutsOpen = panel === 'shortcuts', setShortcutsOpen = setters.shortcuts
  const alertsDrawerOpen = panel === 'alerts', setAlertsDrawerOpen = setters.alerts
  const quickCreateOpen = panel === 'quick', setQuickCreateOpen = setters.quick
  const voiceOpen = panel === 'voice', setVoiceOpen = setters.voice
  const [navSearch, setNavSearch] = useState<string>('')
  const [workspace, setWorkspace] = useState<string>(() => localStorage.getItem(NAV_WORKSPACE_KEY) || 'all')
  const [timerElapsed, setTimerElapsed] = useState<number>(0)

  const { data: activeTimer } = useQuery<ActiveTimer | null>({
    queryKey: ['timer-current'],
    queryFn: () => api.get('/imputations/timer/current').then(r => r.data).catch(() => null),
    refetchInterval: 5_000,
    retry: false,
    staleTime: 10_000,
  })

  useEffect(() => {
    if (!activeTimer || activeTimer.paused_at) {
      setTimerElapsed(activeTimer?.total_elapsed_seconds ?? 0)
      return undefined
    }
    const tick = () => setTimerElapsed(computeTimerElapsed(activeTimer as TimerState))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [activeTimer])
  const [isOverlayNav, setIsOverlayNav] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.innerWidth <= 1024
  })

  useEffect(() => {
    localStorage.setItem(NAV_WORKSPACE_KEY, workspace)
    // Un workspace concreto abre su grupo; en «Todo» manda el acordeón (uno a
    // la vez: el de la pantalla actual, o el que abra el usuario).
    if (workspace !== 'all') setOpenGroup(WORKSPACE_GROUPS[workspace]?.[0] ?? null)
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
    if (!isOverlayNav) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = mobileOpen ? 'hidden' : previousOverflow || ''
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [isOverlayNav, mobileOpen])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target as HTMLElement | null)?.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setSearchOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && e.key === 'i') { e.preventDefault(); setAiOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); setCollapsed(c => !c); return }
      if (e.key === 'Escape') { setSearchOpen(false); setAiOpen(false); setShortcutsOpen(false); setProfileOpen(false); setMobileOpen(false); return }
      if (!isInput && e.key === '?') { e.preventDefault(); setShortcutsOpen(o => !o); return }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setSearchOpen, setAiOpen, setShortcutsOpen, setProfileOpen])

  const _currentDensity = prefs?.ui_density || 'normal'
  const _setDensity = (d: string) => save({ ui_density: d })

  // «Entrar como» (soporte de plataforma): aviso permanente y salida. La cookie de
  // refresco sigue siendo la del superadmin, así que refrescar le devuelve su sesión.
  const suplantadoPor = typeof user?.impersonated_by === 'string' ? user.impersonated_by : null
  async function salirDeSuplantacion() {
    try { await api.post('/auth/refresh') } finally { window.location.href = '/organizations' }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--surface-0)' }}>
      <a href="#main-content" className="skip-nav">{text.skip_to_content}</a>
      {suplantadoPor && (
        <div role="alert" style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 2000,
          display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, padding: '6px 12px',
          background: 'var(--warning)', color: 'var(--on-accent-dark)', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
          <span>Estás dentro como {user?.full_name ?? user?.email} (soporte: {suplantadoPor}). Todo queda auditado.</span>
          <button type="button" onClick={() => { void salirDeSuplantacion() }}
            style={{ background: 'var(--on-accent-dark)', color: 'var(--on-accent-light)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '3px 10px', cursor: 'pointer', fontFamily: 'inherit' }}>
            Salir
          </button>
        </div>
      )}

      <aside aria-label={text.main_navigation} role="navigation"
        id="mobile-primary-nav"
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
            boxShadow: '0 2px 8px color-mix(in srgb, var(--accent) 35%, transparent)',
          }}>
            <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
              <path d="M12 4C10.8 2.9 9.5 2.5 8 2.5C5 2.5 2.5 5 2.5 8C2.5 11 5 13.5 8 13.5C9.5 13.5 10.8 13.1 12 12"
                stroke="white" strokeWidth="1.6" strokeLinecap="round" />
              <rect x="7" y="6.5" width="7" height="1.2" rx="0.6" fill="white" opacity="0.95" />
              <rect x="7" y="9" width="5.5" height="1.2" rx="0.6" fill="white" opacity="0.65" />
            </svg>
          </div>
          {!collapsed && (
            <span style={{ fontWeight: 700, fontSize: "var(--text-md-h)", letterSpacing: '-0.02em',
              color: 'var(--text-1)', whiteSpace: 'nowrap', userSelect: 'none' }}>Contecflow</span>
          )}
          {isOverlayNav && mobileOpen && (
            <IconButton
              onClick={() => setMobileOpen(false)}
              ariaLabel={text.close_menu || 'Cerrar menú'}
              style={{
                marginLeft: 'auto',
                background: 'transparent',
                border: '1px solid var(--surface-4)',
                borderRadius: 8,
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </IconButton>
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
              <div style={{ fontSize: "var(--text-3xs-h)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
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
                      borderRadius: 'var(--radius-full)',
                      padding: '2px 7px',
                      fontSize: "var(--text-2xs-h)",
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

          {navGroups.map(group => {
            const visible = group.items.some(i => !i.divider && (!i.roles || i.roles.some(r => hasRole(r))))
            if (!visible) return null
            if (!group.single && workspace !== 'all' && !WORKSPACE_GROUPS[workspace]?.includes(group.id || '')) return null
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
                pinned={pinned} onPin={togglePin} text={text}
                open={openGroup === group.id}
                onToggle={() => setOpenGroup(g => (g === group.id ? null : group.id))}
                onActive={() => setOpenGroup(group.id)} />
            )
          })}
          {navSearch.trim() && !collapsed && (
            <NavSearchResults
              query={navSearch} hasRole={hasRole} groups={navGroups}
              alertCount={alertCount} approvalCount={approvalCount}
              onNavigate={() => setNavSearch('')}
              text={text}
              t={t}
            />
          )}
        </nav>

        {/* Footer */}
        <div style={{
          padding: collapsed ? '6px 3px' : '6px 8px',
          borderTop: '1px solid var(--surface-4)',
          display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0,
        }}>
          <IconButton onClick={() => setCollapsed(c => !c)}
            ariaLabel={collapsed ? text.expand_sidebar : text.collapse_sidebar}
            style={{
              background: 'transparent', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-sm)', padding: '5px', cursor: 'pointer', color: 'var(--text-3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.1s', width: '100%',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--surface-5)'; e.currentTarget.style.color = 'var(--text-2)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-3)' }}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </IconButton>

          {!collapsed && (
            <button onClick={() => setShortcutsOpen(true)} title={`${text.keyboard_shortcuts} (?)`}
              style={{
                background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer',
                fontSize: "var(--text-2xs)", display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: 4, padding: '2px', fontFamily: 'inherit', transition: 'color 0.1s',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--text-2)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
            >
              <Keyboard size={11} />
              <span>{text.shortcuts}</span>
              <span className="kbd" style={{ fontSize: "var(--text-3xs)" }}>?</span>
            </button>
          )}
        </div>
      </aside>

      {isOverlayNav && mobileOpen && (
        <div role="presentation" onMouseDown={() => setMobileOpen(false)} className="mobile-overlay"
          style={{ position: 'fixed', inset: 0, zIndex: 99, background: 'rgba(0,0,0,0.55)', display: 'block' }} />
      )}

      <main id="main-content" aria-label={text.main_content} role="main"
        className="app-main-shell"
        style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, minHeight: '100vh', overflow: 'auto' }}
        {...swipeHandlers}>
        {!mobileOpen && (
          <IconButton className="mobile-hamburger" onClick={() => { setCollapsed(false); setMobileOpen(true) }}
            ariaLabel={text.open_menu}
            aria-expanded={mobileOpen}
            aria-controls="mobile-primary-nav"
            style={{
              position: 'fixed', top: 'calc(12px + var(--safe-top))', left: 'calc(12px + var(--safe-left))', zIndex: 'var(--z-mobile-nav)',
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 8, width: 36, height: 36, alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
            }}
          >
            <Menu size={18} color="var(--text-2)" />
          </IconButton>
        )}
        <TopAppBar
          onSearchOpen={() => setSearchOpen(true)}
          onAiToggle={() => setAiOpen(o => !o)}
          aiOpen={aiOpen}
          onChatToggle={() => setChatOpen(o => !o)}
          chatOpen={chatOpen}
          chatUnread={chatUnread}
          user={user as AuthUser | null}
          onProfileOpen={() => setProfileOpen(true)}
          onLogout={logout}
          alertCount={alertCount}
          approvalCount={approvalCount}
          t={t}
          allNavItems={allNavItems}
          text={text}
          activeTimer={activeTimer}
          timerElapsed={timerElapsed}
          onAlertsOpen={() => setAlertsDrawerOpen(true)}
          onQuickCreate={() => setQuickCreateOpen(o => !o)}
          onVoiceOpen={() => setVoiceOpen(true)}
        />
        {children}
      </main>

      {searchOpen && <GlobalSearch onClose={() => setSearchOpen(false)} />}
      {aiOpen && <NexusAssistPanel open={aiOpen} onClose={() => setAiOpen(false)} context={{ page: location.pathname, search: location.search }} />}
      {chatOpen && (
        <GlobalChatPanel
          open={chatOpen}
          unread={chatUnread}
          onClose={() => setChatOpen(false)}
          onOpenFull={() => {
            navigate('/chat')
            setChatOpen(false)
          }}
        />
      )}
      {profileOpen && <UserProfilePanel onClose={() => setProfileOpen(false)} />}
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} text={text} />}
      {alertsDrawerOpen && <AlertsDrawer onClose={() => setAlertsDrawerOpen(false)} />}
      {quickCreateOpen && <QuickCreateMenu onClose={() => setQuickCreateOpen(false)} />}
      <VoiceCommandModal open={voiceOpen} onClose={() => setVoiceOpen(false)} />
      <OfflineIndicator />
    </div>
  )
}
