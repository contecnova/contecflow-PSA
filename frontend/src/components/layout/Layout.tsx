import { useAppName } from '../../hooks/useAppName'
import React, { type CSSProperties, lazy, Suspense, useState, useEffect, useRef, useMemo } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { Avatar, Button, IconButton, Pulsable } from '../ui'
import { armazonApi, imputationsApi, projectsApi, tasksApi } from '../../services/api'
import GlobalSearch from './GlobalSearch'
import QuickCreateMenu from './QuickCreateMenu'
import NexusAssistPanel from './NexusAssistPanel'
import SelectorDeEmpresa from './SelectorDeEmpresa'
import GlobalChatPanel from './GlobalChatPanel'
import VoiceCommandModal from './VoiceCommandModal'
import UserProfilePanel from './UserProfilePanel'
import AlertsDrawer from './AlertsDrawer'
import CampanaDeAvisos from './CampanaDeAvisos'
import Breadcrumbs from './Breadcrumbs'
import { ATAJOS_IR, crearSecuenciaIr, esCampoDeTexto } from './atajosDeTeclado'
import useUserPreferences from '../../hooks/useUserPreferences'
import useNotificationBadges from '../../hooks/useNotificationBadges'
import { useChatRealtime } from '../../context/ChatRealtimeContext'
import OfflineIndicator from '../OfflineIndicator'
import { useSwipeGesture } from '../../hooks/useSwipeGesture'
import { useAppLang, EVENTO_IDIOMA_ELEGIDO } from '../../i18n/AppLangContext'
import {
  Calendar, MessageSquare, Brain, Search, LogOut, ChevronRight, ChevronLeft, Menu, X,
  Timer, Keyboard, Plus, Inbox, Mic, SlidersHorizontal, RotateCcw, NotebookPen,
} from 'lucide-react'
import { ANIMATION_FAST_MS, CLOCK_TICK_MS, DROPDOWN_DELAY_MS, POLL_FAST_MS, STALE_5_MIN_MS, STALE_LIVE_MS } from '../../constants/timings'
import './Layout.css'
// 23-11-2026 (menú personalizable): categorías y pestañas en `menuLateral.tsx`;
// orden y ocultas de cada persona en `permisos/menuPersonal.ts`.
import {
  NAV_GROUPS, PANEL_DE_CATEGORIA, EVENTO_PERSONALIZAR_MENU, getGroupLabel, getNavLabel,
  type NavGroupConfig, type NavItemConfig, type TFn,
} from './menuLateral'
import EditorDeMenu from './EditorDeMenu'
import useMenuPersonal from '../../hooks/useMenuPersonal'
import { aplicarMenu } from '../../permisos/menuPersonal'
import { puedeAbrir } from '../../permisos/navegacion'
import { px } from '../../utils/estilos'
// «Mi cuaderno» (migración 202): panel de notas rápidas; el editor se carga al abrirlo.
const PanelRapido = lazy(() => import('../cuaderno/PanelRapido'))

// Auditoría 22-11-2026 (M2 y B1 del 04): fuera `ROUTE_LABELS` (≈20 rutas retiradas y
// literales en inglés) y `ROUTE_SECTION` en inglés/castellano. Las rutas que no están
// en el menú dicen aquí a qué grupo pertenecen y la miga sale traducida (`nav.group_*`).
const GRUPO_DE_RUTA_FUERA_DEL_MENU: Record<string, string> = {
  '/calendar': 'group_work', '/timer': 'group_work', '/timesheets': 'group_work', '/imputar': 'group_work',
  '/chat': 'group_work', '/search': 'group_work', '/inbox': 'group_work', '/pir': 'group_work',
  '/contracts-ai': 'group_business',
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

// Textos del armazón: diccionarios, módulo `layout_texto` (es/en/zh).
const CLAVES_LAYOUT = ["shortcut_global_search", "shortcut_ai_assist", "shortcut_view_shortcuts", "shortcut_close_modal", "shortcut_toggle_sidebar", "shortcut_go_tasks", "shortcut_go_projects", "shortcut_go_log_hours", "shortcut_go_service_desk", "shortcuts", "keyboard_shortcuts", "shortcuts_hint", "shortcuts_hint_suffix", "close", "recent", "workspace", "workspace_all", "workspace_work", "workspace_projects", "workspace_team", "workspace_business", "workspace_support", "workspace_analytics", "workspace_ai", "workspace_settings", "global_search_title", "open_global_search", "search_placeholder", "ai_title", "open_ai", "ai_short", "active_alerts_title", "pending_approvals_title", "skip_to_content", "main_navigation", "side_menu", "expand_sidebar", "collapse_sidebar", "main_content", "open_menu"] as const

function formatTimerDisplay(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

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

// Rutas del menú que son padre de otra entrada (p. ej. /settings y
// /settings/policies): se marcan solo en coincidencia exacta, para que no
// queden dos entradas activas a la vez.
const RUTAS_DEL_MENU = NAV_GROUPS.flatMap(g => g.items.map(i => i.to || '')).filter(Boolean)
const RUTAS_PADRE_DEL_MENU = new Set(RUTAS_DEL_MENU.filter(r => RUTAS_DEL_MENU.some(o => o !== r && o.startsWith(r + '/'))))

/** ⌘ solo en Mac; en Windows y Linux la tecla es Ctrl (19-11-2026). */
const ES_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const SHORTCUTS = [
  { keys: ['⌘', 'K'], labelKey: 'shortcut_global_search' },
  { keys: ['Ctrl', 'I'], labelKey: 'shortcut_ai_assist' },
  { keys: ['?'], labelKey: 'shortcut_view_shortcuts' },
  { keys: ['Esc'], labelKey: 'shortcut_close_modal' },
  { keys: ['⌘', 'B'], labelKey: 'shortcut_toggle_sidebar' },
  // 23-11-2026: «G + letra» se anunciaban y no los atendía nadie; ahora sí
  // (atajosDeTeclado.ts) y solo se muestran los que el usuario puede abrir.
  { keys: ['G', 'T'], labelKey: 'shortcut_go_tasks', ruta: ATAJOS_IR.t },
  { keys: ['G', 'P'], labelKey: 'shortcut_go_projects', ruta: ATAJOS_IR.p },
  { keys: ['G', 'I'], labelKey: 'shortcut_go_log_hours', ruta: ATAJOS_IR.i },
  { keys: ['G', 'S'], labelKey: 'shortcut_go_service_desk', ruta: ATAJOS_IR.s },
] as Array<{ keys: string[]; labelKey: string; ruta?: string }>

function getSectionLabel(path: string, t: TFn | null | undefined): string | null {
  const group = NAV_GROUPS.find(g => (g.items || []).some(
    i => !i.divider && (path === i.to || path.startsWith(i.to + '/'))
  ))
  if (!group) return null
  const translated = (t && group.groupKey) ? t('nav', group.groupKey) : null
  if (translated && translated !== group.groupKey) return translated
  return group.label
}

function ShortcutsModal({ onClose, text, puedeIr }: { onClose: () => void; text: Record<string, string>; puedeIr: (ruta: string) => boolean }) {
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
        className="modal-glass layo-box-1" onMouseDown={e => e.stopPropagation()}
        tabIndex={-1}
      >
        <div className="modal-header">
          <span className="modal-title">
            <Keyboard size={15} className="layout-sx1" />
            {text.keyboard_shortcuts}
          </span>
          <IconButton className="modal-close" onClick={onClose} ariaLabel={text.close}><X size={14} /></IconButton>
        </div>
        <div className="shortcuts-grid">
          {SHORTCUTS.filter(s => !s.ruta || puedeIr(s.ruta)).map((s, i) => (
            <div key={i} className="shortcut-row">
              <span className="u-text2-sm">{text[s.labelKey]}</span>
              <div className="layo-row-1">
                {s.keys.map((k, j) => <span key={j} className="kbd">{k === '⌘' && !ES_MAC ? 'Ctrl' : k}</span>)}
              </div>
            </div>
          ))}
        </div>
        <div className="layo-box-2">
          {text.shortcuts_hint} <span className="kbd">?</span> {text.shortcuts_hint_suffix}
        </div>
      </div>
    </div>
  )
}

interface NavItemProps {
  item: NavItemConfig
  collapsed?: boolean
  alertCount?: number
  approvalCount?: number
  t?: TFn | null
}

// 16-11-2026: fuera la estrella de favoritos. Guardaba la ruta, pero la sección
// de favoritos solo se pintaba dentro de un grupo `single` que ya no existe:
// marcar no tenía ningún efecto visible. El buscador global (⌘K) cubre el acceso
// rápido.
function NavItem({ item, collapsed, alertCount, approvalCount, t }: NavItemProps) {
  const { unread: chatUnread } = useChatRealtime()
  const badge = (item.to === '/alerts' ? alertCount
              : item.to === '/approvals' ? approvalCount
              : item.to === '/chat' ? chatUnread
              : 0) ?? 0
  const badgeColor = item.to === '/approvals' ? 'var(--warning)'
                   : item.to === '/chat' ? 'var(--accent)'
                   : 'var(--danger)'
  const displayLabel = getNavLabel(item.to || '', item.label, t)
  return (
    <div className="layo-box-3">
      {/* Verificación 16-11-2026: el nombre se cortaba («Flujos de estado de
          proyecto») y /settings seguía marcado en /settings/*. Ahora el nombre
          pasa a dos líneas si no cabe (nunca se corta, en ningún idioma) y una
          ruta que es padre de otra entrada del menú solo se marca exacta. */}
      <NavLink to={item.to || '#'} title={displayLabel} aria-label={displayLabel}
        end={RUTAS_PADRE_DEL_MENU.has(item.to || '')}
        className={({ isActive }) => [
          'nav-enlace',
          collapsed ? 'nav-enlace--plegado' : '',
          isActive ? 'nav-enlace--activo' : '',
        ].filter(Boolean).join(' ')}
      >
        <span className="layo-row-2">
          {item.icon}
          {collapsed && badge > 0 && (
            <span className="layo-box-20 layout-e1" style={{ '--layout-background': badgeColor } as CSSProperties} />
          )}
        </span>
        {!collapsed && <span className="layo-box-4">{displayLabel}</span>}
        {!collapsed && badge > 0 && (
          <span className="layo-box-21 layout-e2" style={{ '--layout-color': badgeColor } as CSSProperties}>{badge}</span>
        )}
      </NavLink>
    </div>
  )
}

interface NavGroupProps {
  group: NavGroupConfig
  collapsed?: boolean
  alertCount?: number
  approvalCount?: number
  t?: TFn | null
  /** Panel de la categoría, si la persona puede abrirlo (`PANEL_DE_CATEGORIA`). */
  panel?: string
  /** Acordeón: solo un grupo abierto a la vez (lo decide `Layout`). */
  open: boolean
  onToggle: () => void
  onActive: () => void
}

// 23-11-2026 (menú personalizable): con panel, el icono y el nombre de la
// categoría llevan a su panel y la flecha despliega; sin panel, como antes (el
// nombre despliega). Plegado: un icono por categoría (al panel, o abre el
// desplegable si no tiene) y el desplegable sale al pasar el ratón o con el
// foco; con el teclado, → o ↓ entran en él, ↑/↓ recorren, Esc/←/Tab vuelven.
function NavGroup({ group, collapsed, alertCount, approvalCount, t, panel, open, onToggle, onActive }: NavGroupProps) {
  const location = useLocation()
  const { t: traducir } = useAppLang()
  const isAnyChildActive = group.items.filter(i => !i.divider).some(
    i => location.pathname === i.to || location.pathname.startsWith(i.to + '/')
  )
  const enPanel = !!panel && (location.pathname === panel || location.pathname.startsWith(panel + '/'))
  const [hoverOpen, setHoverOpen] = useState<boolean>(false)
  const [hoverTop, setHoverTop] = useState<number>(0)
  const groupRef = useRef<HTMLDivElement | null>(null)
  const flyoutRef = useRef<HTMLDivElement | null>(null)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Al navegar a una pantalla de este grupo, se abre (y se cierran los demás).
  useEffect(() => { if (isAnyChildActive || enPanel) onActive() }, [isAnyChildActive, enPanel]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (hoverTimer.current) clearTimeout(hoverTimer.current) }, [])

  // Ya filtrados por permiso y por el menú de la persona en `Layout`.
  const visibleItems = group.items
  const realVisible = visibleItems.filter(i => !i.divider)
  if (realVisible.length === 0) return null

  const groupLabel = getGroupLabel(group, t)
  const idDesplegable = `nav-flyout-${group.id}`

  const abrir = () => {
    if (!collapsed) return
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    const rect = groupRef.current?.getBoundingClientRect()
    if (rect) setHoverTop(rect.top)
    setHoverOpen(true)
  }
  const cerrarLuego = () => {
    if (!collapsed) return
    hoverTimer.current = setTimeout(() => setHoverOpen(false), DROPDOWN_DELAY_MS)
  }
  const dentro = (n: EventTarget | null) =>
    n instanceof Node && (!!groupRef.current?.contains(n) || !!flyoutRef.current?.contains(n))
  const enlaces = () => Array.from(flyoutRef.current?.querySelectorAll<HTMLElement>('a[href]') ?? [])
  const disparador = () => groupRef.current?.querySelector<HTMLElement>('[data-disparador]')
  const entrar = () => { abrir(); requestAnimationFrame(() => enlaces()[0]?.focus()) }
  const alTeclado = (e: React.KeyboardEvent) => {
    if (!collapsed) return
    const lista = enlaces()
    const i = lista.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'Escape' && hoverOpen) { setHoverOpen(false); disparador()?.focus(); return }
    if (i === -1 && (e.key === 'ArrowRight' || e.key === 'ArrowDown')) { e.preventDefault(); entrar(); return }
    if (i >= 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      lista[(i + (e.key === 'ArrowDown' ? 1 : -1) + lista.length) % lista.length]?.focus()
      return
    }
    if (i >= 0 && (e.key === 'ArrowLeft' || e.key === 'Tab')) { e.preventDefault(); setHoverOpen(false); disparador()?.focus() }
  }
  const alSalirElFoco = (e: React.FocusEvent) => { if (!dentro(e.relatedTarget)) setHoverOpen(false) }

  if (collapsed) {
    const conAviso = realVisible.some(i => (i.to === '/alerts' && (alertCount ?? 0) > 0) || (i.to === '/approvals' && (approvalCount ?? 0) > 0))
    const claseIcono = ['nav-enlace', 'nav-enlace--plegado', 'nav-cat-plegada__icono',
      (isAnyChildActive || enPanel) ? 'nav-enlace--activo' : ''].filter(Boolean).join(' ')
    const icono = (
      <span className="layo-row-2">
        {group.icon}
        {conAviso && <span className="layo-box-20 layout-e1" style={{ '--layout-background': 'var(--danger)' } as CSSProperties} />}
      </span>
    )
    return (
      <div ref={groupRef} className="layo-sp-1 nav-cat-plegada"
        onPointerEnter={abrir} onPointerLeave={cerrarLuego}>
        {panel ? (
          <NavLink to={panel} data-disparador="" className={claseIcono} title={groupLabel}
            aria-label={traducir('menu_personal.ir_al_panel', { nombre: groupLabel })}
            aria-haspopup="true" aria-expanded={hoverOpen} aria-controls={hoverOpen ? idDesplegable : undefined}
            onKeyDown={alTeclado} onFocus={abrir} onBlur={alSalirElFoco}>
            {icono}
          </NavLink>
        ) : (
          <IconButton data-disparador="" ariaLabel={groupLabel} className={claseIcono}
            aria-haspopup="true" aria-expanded={hoverOpen} aria-controls={hoverOpen ? idDesplegable : undefined}
            onClick={entrar} onKeyDown={alTeclado} onFocus={abrir} onBlur={alSalirElFoco}>
            {icono}
          </IconButton>
        )}
        {/* 19-11-2026: en un portal al <body>. Dentro de la barra lateral quedaba en su
            capa y lo tapaban columnas de las páginas (p. ej. la del chat). */}
        {hoverOpen && createPortal(
          <div ref={flyoutRef} id={idDesplegable} role="group" aria-label={groupLabel}
            className="nav-hover-preview layo-box-23 layout-e5" style={{ '--layout-top': px(hoverTop - 4) } as CSSProperties}
            onPointerEnter={abrir} onPointerLeave={cerrarLuego}
          >
            <div className="nav-hover-title">{groupLabel}</div>
            {realVisible.map(item => {
              const itemLabel = getNavLabel(item.to || '', item.label, t)
              return (
              <NavLink key={item.to} to={item.to || '#'} onClick={() => setHoverOpen(false)} onKeyDown={alTeclado} onBlur={alSalirElFoco}
                style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 'var(--radius-sm)',
                  textDecoration: 'none', fontSize: "var(--text-sm-h)", fontWeight: 500,
                  color: isActive ? 'var(--accent)' : 'var(--text-2)',
                  background: isActive ? 'var(--accent-muted)' : 'transparent',
                })}
              >
                <span className="layo-row-3">{item.icon}</span>
                <span>{itemLabel}</span>
              </NavLink>
              )
            })}
          </div>,
          document.body,
        )}
      </div>
    )
  }

  const lista = (
    <div className={`layo-grid-1 ${open ? 'layout-m9' : 'layout-m10'}`} id={`nav-group-${group.id}`}>
      <div className="layo-box-7">
        <div className="layo-stack-2">
          {visibleItems.map((item, idx) =>
            item.divider
              ? <div key={'div-' + idx} className="layo-box-8" />
              : <NavItem key={item.to} item={item} collapsed={false} alertCount={alertCount} approvalCount={approvalCount} t={t} />
          )}
        </div>
      </div>
    </div>
  )

  if (!panel) {
    return (
      <div className="layo-sp-2">
        <IconButton ariaLabel={String(groupLabel)} title={String(groupLabel)} className={`layo-row-17 ${isAnyChildActive ? 'layout-m6' : 'layout-m4'}`} onClick={onToggle} aria-expanded={open} aria-controls={`nav-group-${group.id}`}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-2)' }}
          onMouseLeave={e => { e.currentTarget.style.color = isAnyChildActive ? 'var(--accent)' : 'var(--text-3)' }}
        >
          <span className="layo-row-4">{group.icon}</span>
          <span className="u-flex1">{groupLabel}</span>
          {!open && realVisible.length > 0 && (
            <span className="layo-box-6">{realVisible.length}</span>
          )}
          <ChevronRight size={10} className={`layout-sx2 ${open ? 'layout-m7' : 'layout-m8'}`} />
        </IconButton>
        {lista}
      </div>
    )
  }

  return (
    <div className="layo-sp-2">
      <div className={`nav-cat ${isAnyChildActive || enPanel ? 'nav-cat--activa' : ''}`}>
        {/* 24-11-2026: el nombre del grupo pliega y despliega igual que la flecha.
            Desplegado: pliega sin navegar. Plegado: despliega y abre su panel
            (que además sigue en la lista como «Panel de …»). */}
        <NavLink to={panel} end className="nav-cat__enlace" title={traducir('menu_personal.ir_al_panel', { nombre: groupLabel })}
          aria-expanded={open} aria-controls={`nav-group-${group.id}`}
          onClick={e => { if (open) e.preventDefault(); onToggle() }}>
          <span className="layo-row-4">{group.icon}</span>
          <span className="u-flex1">{groupLabel}</span>
        </NavLink>
        {!open && <span className="layo-box-6">{realVisible.length}</span>}
        <IconButton ariaLabel={traducir(open ? 'menu_personal.plegar' : 'menu_personal.desplegar', { nombre: groupLabel })}
          aria-expanded={open} aria-controls={`nav-group-${group.id}`} className="nav-cat__flecha" onClick={onToggle}>
          <ChevronRight size={10} className={`layout-sx2 ${open ? 'layout-m7' : 'layout-m8'}`} />
        </IconButton>
      </div>
      {lista}
    </div>
  )
}

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
  onNotebookToggle: () => void
  notebookOpen: boolean
}

function TopAppBar({ onSearchOpen, onAiToggle, aiOpen, onChatToggle, chatOpen, chatUnread, user, onProfileOpen, onLogout, alertCount, approvalCount, t, allNavItems, text, activeTimer, timerElapsed, onAlertsOpen: _onAlertsOpen, onQuickCreate, onVoiceOpen, onNotebookToggle, notebookOpen }: TopAppBarProps) {
  const { puede } = useAuth()
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
    const id = setTimeout(() => setChatBadgeVisible(false), ANIMATION_FAST_MS)
    return () => clearTimeout(id)
  }, [chatUnread])

  const grupoFuera = GRUPO_DE_RUTA_FUERA_DEL_MENU[location.pathname]
  const section = getSectionLabel(location.pathname, t) || (grupoFuera && t ? t('nav', grupoFuera) : null)
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
    staleTime: STALE_5_MIN_MS,
  })

  const { data: timerProject } = useQuery({
    queryKey: ['topbar-timer-project', activeTimer?.project_id],
    queryFn: () => projectsApi.get(activeTimer?.project_id as string).then(r => r.data),
    enabled: !!activeTimer?.project_id && !activeTimer?.project_name,
    staleTime: STALE_5_MIN_MS,
  })

  const { data: timerTask } = useQuery({
    queryKey: ['topbar-timer-task', activeTimer?.task_id],
    queryFn: () => tasksApi.get(activeTimer?.task_id as string).then(r => r.data),
    enabled: !!activeTimer?.task_id && !activeTimer?.task_name,
    staleTime: STALE_5_MIN_MS,
  })

  const topbarProjectLabel = activeTimer?.project_name || timerProject?.name || (activeTimer?.project_id && t ? t('layout_texto', 'proyecto') : null)
  const topbarTaskLabel = activeTimer?.task_name || timerTask?.title || (activeTimer?.task_id && t ? t('layout_texto', 'tarea') : null)
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
          let label = isIdLike ? (t ? t('layout_texto', 'detalle') : seg) : decodeURIComponent(seg).replace(/-/g, ' ')
          // Use real project name when on /projects/:id
          // 18-11-2026: /settings/<seccion> → nombre de la sección del catálogo de Configuración.
          if (currentNavItem?.to === '/settings' && idx === 0) label = t('ajustes', `s_${seg.replace(/-/g, '_')}`)
          if (isIdLike && currentNavItem?.to === '/projects' && breadcrumbProject?.name) {
            label = breadcrumbProject.name
          }
          items.push({ label, to: isLast ? null : accPath })
        })
      }

      return items
    }

    if (!segments.length) {
      items.push({ label: t ? t('layout_texto', 'inicio') : '/', to: null })
      return items
    }

    let accPath = ''
    segments.forEach((seg, idx) => {
      accPath += `/${seg}`
      const isLast = idx === segments.length - 1
      const isIdLike = /^\d+$/.test(seg) || /^[0-9a-fA-F-]{8,}$/.test(seg)
      const label = isIdLike ? (t ? t('layout_texto', 'detalle') : seg) : decodeURIComponent(seg).replace(/-/g, ' ')
      items.push({ label, to: isLast ? null : accPath })
    })
    return items
  }, [location.pathname, section, currentNavItem, t, breadcrumbProject])

  return (
    <div className="app-topbar" role="banner">
      <Breadcrumbs items={breadcrumbs} />
      <div className="app-topbar-center">
        <Pulsable onClick={onSearchOpen} title={text.global_search_title} aria-label={text.open_global_search} className="layo-row-6">
          <Search size={12} />
          <span className="app-topbar-texto u-flex1">{text.search_placeholder}</span>
          <span className="app-topbar-texto layo-box-9">⌘K</span>
        </Pulsable>
      </div>
      <div className="app-topbar-right">
        <IconButton onClick={onQuickCreate}
          title={traducir('layout.crear_nuevo')}
          ariaLabel={traducir('layout.crear_nuevo_2')}
          className="layo-row-7"
          onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          <Plus size={16} />
        </IconButton>
        <Pulsable className={`layo-row-18 layout-sx3 layout-e13 ${aiOpen ? 'layout-m14' : 'layout-m15'}`} onClick={onAiToggle} title={text.ai_title} aria-label={text.open_ai} aria-pressed={aiOpen} style={{ '--layout-border': `1px solid ${aiOpen ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
          <Brain size={13} />
          <span className="app-topbar-texto">{text.ai_short}</span>
        </Pulsable>
        {/* I25: Voice command modal — accesible desde cualquier página */}
        <IconButton
          onClick={onVoiceOpen}
          title={traducir('layout.comando_de_voz_imputar_crear_ticket_tarea')}
          ariaLabel={traducir('layout.abrir_comando_de_voz')}
          className="layo-row-8"
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-2)' }}
        >
          <Mic size={14} />
        </IconButton>
        <Pulsable className={`layo-row-19 layout-sx3 layout-e13 ${chatOpen ? 'layout-m14' : 'layout-m15'}`} onClick={onChatToggle} title={traducir('layoutshell.abrir_chat')} aria-label={traducir('layoutshell.abrir_chat')} aria-pressed={chatOpen} style={{ '--layout-border': `1px solid ${chatOpen ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
          <MessageSquare size={13} />
          {chatBadgeVisible && (
            <span className={`layo-row-20 ${chatUnread > 0 ? 'layout-m16' : 'layout-m17'}`}>
              {chatBadgeCount > 99 ? '99+' : chatBadgeCount}
            </span>
          )}
        </Pulsable>
        {/* Campana de avisos sin leer (16-11-2026): contador y panel con los últimos. */}
        {user && <CampanaDeAvisos />}
        {/* 19-11-2026: Calendario y Chat salen del menú lateral y quedan como iconos
            de la barra superior (como la campana), visibles desde cualquier pantalla. */}
        {user && puedeAbrir('/calendar', puede) && (
          <NavLink to="/calendar" title={traducir('layoutshell.abrir_calendario')} aria-label={traducir('layoutshell.abrir_calendario')}
            className={({ isActive }) => `layo-row-19 layout-sx3 layout-e13 ${isActive ? 'layout-m14' : 'layout-m15'}`}>
            <Calendar size={13} aria-hidden />
          </NavLink>
        )}
        {/* «Mi cuaderno» (migración 202): notas rápidas desde cualquier pantalla. */}
        {user && puede('cuaderno.usar') && (
          <Pulsable /* eslint-disable-line contec/sin-boton-de-icono-propio -- excepción: conmutador del cuaderno en el cromo de la barra superior */ className={`layo-row-19 layout-sx3 layout-e13 ${notebookOpen ? 'layout-m14' : 'layout-m15'}`} onClick={onNotebookToggle}
            title={traducir('layoutshell.abrir_cuaderno')} aria-label={traducir('layoutshell.abrir_cuaderno')} aria-pressed={notebookOpen}>
            <NotebookPen size={13} aria-hidden />
          </Pulsable>
        )}
        {activeTimer && !activeTimer.paused_at && (
          <NavLink to="/timer"
            title={topbarTimerSubtitle ? `Cronómetro activo: ${topbarTimerSubtitle}` : 'Cronómetro activo — click para gestionar'} className="layout-sx4"
          >
            <span className="layo-box-10" />
            <Timer size={12} />
            <span className="u-mono">{formatTimerDisplay(timerElapsed)}</span>
            {topbarTimerSubtitle && (
              <span className="layo-box-11">
                {topbarTimerSubtitle}
              </span>
            )}
          </NavLink>
        )}
        {/* Pendientes de la bandeja (alertas + aprobaciones). Icono de bandeja:
            la campana es la de avisos sin leer, justo antes. */}
        {(() => {
          const total = (alertCount || 0) + (approvalCount || 0)
          if (total === 0) return null
          const tone = (alertCount || 0) > 0 ? 'danger' : 'warning'
          const bg = tone === 'danger' ? 'var(--danger-bg)' : 'var(--warning-bg)'
          const border = tone === 'danger' ? 'var(--danger-border)' : 'var(--warning-border)'
          const color = tone === 'danger' ? 'var(--danger)' : 'var(--warning)'
          return (
            <NavLink to="/inbox"
              className="layout-e18" style={{ '--layout-background': bg, '--layout-border': `1px solid ${border}`, '--layout-color': color } as CSSProperties}
              title={`${total} pendientes en bandeja`}
              aria-label={`Bandeja de entrada — ${total} pendientes`}
            >
              <Inbox size={13} aria-hidden /><span>{total}</span>
            </NavLink>
          )
        })()}
        {user && <SelectorDeEmpresa />}
        {user && (
          <div className="layo-row-9"
          >
            <Pulsable onClick={onProfileOpen} title={user.full_name} className="layo-row-10">
              <Avatar name={user.full_name} size={24} url={undefined} />
              <span className="app-topbar-texto layo-box-12">
                {user.full_name}
              </span>
            </Pulsable>
            <IconButton onClick={onLogout}
              ariaLabel={t ? t('nav', 'logout') : ''}
              className="layout-e34"
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

export default function Layout({ children }: { children?: React.ReactNode }) {
  const appName = useAppName()
  const { user, logout, puede, canOpen = () => true } = useAuth()
  const navigate = useNavigate()
  const { prefs, save } = useUserPreferences()
  const { t, setCustomTranslations } = useAppLang()

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
    queryFn: () => armazonApi.traduccionesDeLaApp().then(r => r.data),
    enabled: !!user, staleTime: STALE_5_MIN_MS, retry: false,
  })
  useEffect(() => {
    if (traduccionesDeLaEmpresa) setCustomTranslations(traduccionesDeLaEmpresa as Record<string, Record<string, unknown>>)
  }, [traduccionesDeLaEmpresa, setCustomTranslations])
  const text = useMemo<Record<string, string>>(
    () => Object.fromEntries(CLAVES_LAYOUT.map(k => [k, t(`layout_texto.${k}`)])),
    [t],
  )
  const { alertCount, approvalCount } = useNotificationBadges()
  const { unread: chatUnread } = useChatRealtime()

  // La densidad la aplica useUserPreferences (applyDensity), un solo sitio.

  const location = useLocation()
  // Auditoría 2026-11: acordeón. Abrir un grupo del menú cierra los demás.
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  // Auditoría 2026-11: los módulos que cierra el rol desaparecen del menú.
  // 19-11-2026 (matriz de permisos): un elemento se ve si su ruta está permitida
  // en `permisos/navegacion.ts`, la misma declaración que protege la ruta.
  const navGroups = useMemo(() => NAV_GROUPS.map(g => ({
    ...g, items: (g.items || []).filter(i => i.divider || !i.to || (canOpen(i.to) && puedeAbrir(i.to, puede))),
  })), [canOpen, puede])
  const allNavItems = useMemo(() => navGroups.flatMap(g => g.items || []).filter(i => !i.divider), [navGroups])

  const [collapsed, setCollapsed] = useState<boolean>(false)
  const [mobileOpen, setMobileOpen] = useState<boolean>(false)
  // Menú personalizable (23-11-2026): orden y pestañas ocultas de la persona (o de su rol).
  // Se aplica DESPUÉS del filtro por permisos: ocultar no quita ni da permisos, y las
  // migas, la búsqueda ⌘K y las rutas siguen usando el menú completo permitido.
  const menuPersonal = useMenuPersonal()
  const [personalizando, setPersonalizando] = useState<boolean>(false)
  const gruposDelMenu = useMemo(() => aplicarMenu(navGroups, menuPersonal.efectivo), [navGroups, menuPersonal.efectivo])
  const panelDe = (id?: string): string | undefined => {
    const p = id ? PANEL_DE_CATEGORIA[id] : undefined
    return p && canOpen(p) && puedeAbrir(p, puede) ? p : undefined
  }
  useEffect(() => {
    const abrir = () => {
      setPersonalizando(true); setCollapsed(false)
      if (window.innerWidth <= 1024) setMobileOpen(true)
    }
    window.addEventListener(EVENTO_PERSONALIZAR_MENU, abrir)
    return () => window.removeEventListener(EVENTO_PERSONALIZAR_MENU, abrir)
  }, [])
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
      shortcuts: de('shortcuts'), alerts: de('alerts'), quick: de('quick'), voice: de('voice'), notebook: de('notebook') }
  }, [])
  const searchOpen = panel === 'search', setSearchOpen = setters.search
  const aiOpen = panel === 'ai', setAiOpen = setters.ai
  const chatOpen = panel === 'chat', setChatOpen = setters.chat
  const profileOpen = panel === 'profile', setProfileOpen = setters.profile
  const shortcutsOpen = panel === 'shortcuts', setShortcutsOpen = setters.shortcuts
  const alertsDrawerOpen = panel === 'alerts', setAlertsDrawerOpen = setters.alerts
  const quickCreateOpen = panel === 'quick', setQuickCreateOpen = setters.quick
  const voiceOpen = panel === 'voice', setVoiceOpen = setters.voice
  const notebookOpen = panel === 'notebook', setNotebookOpen = setters.notebook
  const [workspace, setWorkspace] = useState<string>(() => { try { return localStorage.getItem(NAV_WORKSPACE_KEY) || 'all' } catch { return 'all' } })
  const [timerElapsed, setTimerElapsed] = useState<number>(0)

  const { data: activeTimer } = useQuery<ActiveTimer | null>({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data as unknown as ActiveTimer | null).catch(() => null),
    refetchInterval: POLL_FAST_MS,
    retry: false,
    staleTime: STALE_LIVE_MS,
  })

  useEffect(() => {
    if (!activeTimer || activeTimer.paused_at) {
      setTimerElapsed(activeTimer?.total_elapsed_seconds ?? 0)
      return undefined
    }
    const tick = () => setTimerElapsed(computeTimerElapsed(activeTimer as TimerState))
    tick()
    const id = setInterval(tick, CLOCK_TICK_MS)
    return () => clearInterval(id)
  }, [activeTimer])
  const [isOverlayNav, setIsOverlayNav] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.innerWidth <= 1024
  })

  useEffect(() => {
    try { localStorage.setItem(NAV_WORKSPACE_KEY, workspace) } catch { /* accesorio: almacenamiento bloqueado */ }
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

  const secuenciaIr = useRef(crearSecuenciaIr())
  const puedeIrA = (ruta: string) => canOpen(ruta) && puedeAbrir(ruta, puede)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput = esCampoDeTexto(e.target)
      const tecla = (e.key || '').toLowerCase()
      if ((e.metaKey || e.ctrlKey) && tecla === 'k') { e.preventDefault(); setSearchOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && tecla === 'i') { e.preventDefault(); setAiOpen(o => !o); return }
      if ((e.metaKey || e.ctrlKey) && tecla === 'b') { e.preventDefault(); setCollapsed(c => !c); return }
      if (e.key === 'Escape') { setPersonalizando(false); setSearchOpen(false); setAiOpen(false); setShortcutsOpen(false); setProfileOpen(false); setMobileOpen(false); return }
      if (!isInput && e.key === '?') { e.preventDefault(); setShortcutsOpen(o => !o); return }
      // «G + letra» (23-11-2026): fuera de campos de texto, sin modificadores y
      // solo hacia lo que el usuario puede abrir (mismas reglas que el menú).
      if (!isInput && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const r = secuenciaIr.current(tecla)
        if (r?.tipo === 'ir' && canOpen(r.ruta) && puedeAbrir(r.ruta, puede)) {
          e.preventDefault()
          setShortcutsOpen(false)
          navigate(r.ruta)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setSearchOpen, setAiOpen, setShortcutsOpen, setProfileOpen, navigate, canOpen, puede])

  const _currentDensity = prefs?.ui_density || 'normal'
  const _setDensity = (d: string) => save({ ui_density: d })

  // «Entrar como» (soporte de plataforma): aviso permanente y salida. La cookie de
  // refresco sigue siendo la del superadmin, así que refrescar le devuelve su sesión.
  const suplantadoPor = typeof user?.impersonated_by === 'string' ? user.impersonated_by : null
  async function salirDeSuplantacion() {
    try { await armazonApi.renovarSesion() } finally { window.location.href = '/settings/organizations' /* recarga completa a propósito: cambia la sesión */ }
  }

  return (
    <div className="layo-row-12">
      <a href="#main-content" className="skip-nav">{text.skip_to_content}</a>
      {suplantadoPor && (
        <div role="alert" className="layo-row-13">
          <span>{t('layoutshell.suplantando', { nombre: user?.full_name ?? user?.email ?? '', soporte: suplantadoPor })}</span>
          <Pulsable onClick={() => { void salirDeSuplantacion() }} className="layo-box-17">
            {t('layoutshell.salir')}
          </Pulsable>
        </div>
      )}

      <aside aria-label={text.main_navigation} role="navigation"
        id="mobile-primary-nav"
        className={`${mobileOpen ? 'mobile-open' : ''} layout-sx6 layout-e19 ${collapsed && !isOverlayNav ? 'layout-m20' : 'layout-m21'} ${isOverlayNav ? 'layout-m22' : 'layout-m23'}`}
        style={{ '--layout-transform': isOverlayNav ? (mobileOpen ? 'translateX(0)' : 'translateX(-100%)') : 'none' } as CSSProperties}
      >
        {/* Logo row */}
        <div className={`layo-row-21 ${collapsed ? 'layout-m24' : 'layout-m25'}`}>
          <div className="layo-row-14">
            <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
              <path d="M12 4C10.8 2.9 9.5 2.5 8 2.5C5 2.5 2.5 5 2.5 8C2.5 11 5 13.5 8 13.5C9.5 13.5 10.8 13.1 12 12"
                stroke="white" strokeWidth="1.6" strokeLinecap="round" />
              <rect x="7" y="6.5" width="7" height="1.2" rx="0.6" fill="white" opacity="0.95" />
              <rect x="7" y="9" width="5.5" height="1.2" rx="0.6" fill="white" opacity="0.65" />
            </svg>
          </div>
          {!collapsed && (
            <span className="layo-box-18">{appName}</span>
          )}
          {isOverlayNav && mobileOpen && (
            <IconButton
              onClick={() => setMobileOpen(false)}
              ariaLabel={text.close_menu || 'Cerrar menú'}
              className="layout-e35"
            >
              <X size={16} />
            </IconButton>
          )}
        </div>

        {/* Nav */}
        <nav className={`layo-stack-4 ${collapsed ? 'layout-m26' : 'layout-m27'}`} aria-label={text.side_menu}>
          {personalizando && !collapsed ? (
            <div className="nav-personalizar">
              <div className="nav-personalizar__cabecera">
                <span className="nav-personalizar__titulo">{t('menu_personal.personalizar')}</span>
                <Button size="sm" onClick={() => setPersonalizando(false)}>{t('menu_personal.hecho')}</Button>
              </div>
              <EditorDeMenu grupos={navGroups} valor={menuPersonal.efectivo} onChange={menuPersonal.guardar} idBase="menu-personal" />
              <div className="nav-personalizar__pie">
                <span>{t(menuPersonal.personalizado ? 'menu_personal.estado_propio' : 'menu_personal.estado_rol')}</span>
                <Button size="sm" variant="ghost" icon={<RotateCcw size={13} />} disabled={!menuPersonal.personalizado}
                  onClick={menuPersonal.restablecer}>{t('menu_personal.restablecer')}</Button>
              </div>
            </div>
          ) : (
            <>
            {!collapsed && (
              <div className="layo-sp-4">
                <div className="layo-box-19">
                  {text.workspace}
                </div>
                <div className="layo-row-15">
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
                    <Pulsable className={`layo-box-26 ${workspace === key ? 'layout-m28' : 'layout-m29'}`} key={key} onClick={() => setWorkspace(key)}>
                      {label}
                    </Pulsable>
                  ))}
                </div>
              </div>
            )}

            {gruposDelMenu.map(group => {
              const visible = group.items.some(i => !i.divider)
              if (!visible) return null
              if (workspace !== 'all' && !WORKSPACE_GROUPS[workspace]?.includes(group.id || '')) return null
              return (
                <NavGroup key={group.id} group={group} collapsed={collapsed} panel={panelDe(group.id)}
                  alertCount={alertCount} approvalCount={approvalCount} t={t}
                  open={openGroup === group.id}
                  onToggle={() => setOpenGroup(g => (g === group.id ? null : group.id))}
                  onActive={() => setOpenGroup(group.id)} />
              )
            })}
            </>
          )}
        </nav>

        {/* Footer */}
        <div className={`layo-stack-5 ${collapsed ? 'layout-m32' : 'layout-m33'}`}>
          <IconButton onClick={() => setCollapsed(c => !c)}
            ariaLabel={collapsed ? text.expand_sidebar : text.collapse_sidebar}
            className="layout-e36"
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--surface-5)'; e.currentTarget.style.color = 'var(--text-2)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-3)' }}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </IconButton>

          {!collapsed && (
            <IconButton ariaLabel={`${text.keyboard_shortcuts} (?)`} onClick={() => setShortcutsOpen(true)} title={`${text.keyboard_shortcuts} (?)`}
              className="layo-row-16"
              onMouseEnter={e => e.currentTarget.style.color = 'var(--text-2)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
            >
              <Keyboard size={11} />
              <span>{text.shortcuts}</span>
              <span className="kbd layo-txt-2">?</span>
            </IconButton>
          )}
          {/* 23-11-2026: modo «Personalizar menú» (también desde el perfil). */}
          <IconButton ariaLabel={t('menu_personal.personalizar')} title={t('menu_personal.personalizar')}
            aria-pressed={personalizando && !collapsed} className="layo-row-16 nav-personalizar__abrir"
            onClick={() => { if (collapsed) { setCollapsed(false); setPersonalizando(true) } else setPersonalizando(p => !p) }}
          >
            <SlidersHorizontal size={11} />
            {!collapsed && <span>{t('menu_personal.personalizar')}</span>}
          </IconButton>
        </div>
      </aside>

      {isOverlayNav && mobileOpen && (
        <div role="presentation" onMouseDown={() => setMobileOpen(false)} className="mobile-overlay layout-sx7" />
      )}

      <main id="main-content" aria-label={text.main_content} role="main"
        className="app-main-shell layout-sx8"
        {...swipeHandlers}>
        {!mobileOpen && (
          <IconButton className="mobile-hamburger layout-e37" onClick={() => { setCollapsed(false); setMobileOpen(true) }}
            ariaLabel={text.open_menu}
            aria-expanded={mobileOpen}
            aria-controls="mobile-primary-nav"
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
          onNotebookToggle={() => setNotebookOpen(o => !o)}
          notebookOpen={notebookOpen}
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
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} text={text} puedeIr={puedeIrA} />}
      {alertsDrawerOpen && <AlertsDrawer onClose={() => setAlertsDrawerOpen(false)} />}
      {quickCreateOpen && <QuickCreateMenu onClose={() => setQuickCreateOpen(false)} />}
      <VoiceCommandModal open={voiceOpen} onClose={() => setVoiceOpen(false)} />
      {notebookOpen && <Suspense fallback={null}><PanelRapido onClose={() => setNotebookOpen(false)} /></Suspense>}
      <OfflineIndicator />
    </div>
  )
}
