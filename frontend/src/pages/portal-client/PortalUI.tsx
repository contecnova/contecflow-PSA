/**
 * PortalUI – diseño compartido del portal cliente, alineado con el backoffice.
 *
 * Provee:
 *   PortalShell        — sidebar agrupado + topbar + área principal
 *   PortalPageHeader   — cabecera de página con título / subtítulo / acciones / meta
 *   PortalCard         — tarjeta base (var(--surface-2))
 *   PortalKpi          — tarjeta KPI con valor / icono / trend
 *   PortalSection      — heading reutilizable
 *   PortalTabs         — pestañas
 *   PortalEmpty        — estado vacío
 *   PortalProgress     — barra de progreso
 *   PortalSpark        — sparkline mini
 *   PortalDonut        — donut SVG ligero
 *   PortalBars         — barras horizontales para distribuciones
 *   PortalAlert        — banner de aviso
 *
 * Inspirado en components/layout/Layout.jsx + components/ui/index.jsx pero
 * autocontenido para no acoplar el portal al AuthContext del operador.
 */
import { useEffect, useState } from 'react'
import type {
  CSSProperties, ComponentType, ReactNode, MouseEvent as ReactMouseEvent, KeyboardEvent as ReactKeyboardEvent,
  InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes,
} from 'react'
import {
  LayoutDashboard, FlaskConical, Lightbulb, Map, BookOpen, FileText,
  Receipt, Headphones, MessageSquare, Settings, LogOut, Search,
  Bell, X, Menu, Plus, Sparkles,
} from 'lucide-react'
import { useClientAuth, useLang } from './portalClientContext'
import PortalQuickCreateMenu from './PortalQuickCreateMenu'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { useTabListKeys } from '../../components/ui/Tabs'
import { formatearMoneda } from '../../utils/helpers'
import StatusBadge, { type StatusBadgeKind } from '../../components/ui/StatusBadge'
import './PortalUI.css'

// ── Section configuration (grouped like the backoffice) ──────────────────────
export const PORTAL_NAV_GROUPS = [
  {
    label: 'Resumen', labelKey: 'group_overview',
    items: [
      { id: 'dashboard', icon: LayoutDashboard, labelKey: 'nav_dashboard', fallback: 'Dashboard' },
    ],
  },
  {
    label: 'Entrega', labelKey: 'group_delivery',
    items: [
      { id: 'roadmap',  icon: Map,          labelKey: 'nav_roadmap',  fallback: 'Roadmap' },
      { id: 'uat',      icon: FlaskConical, labelKey: 'nav_uat',      fallback: 'UAT' },
      { id: 'requests', icon: Lightbulb,    labelKey: 'nav_requests', fallback: 'Solicitudes' },
    ],
  },
  {
    label: 'Soporte', labelKey: 'group_support',
    items: [
      { id: 'support',  icon: Headphones,     labelKey: 'nav_support',  fallback: 'Service Desk' },
      { id: 'messages', icon: MessageSquare,  labelKey: 'nav_messages', fallback: 'Mensajes' },
    ],
  },
  {
    label: 'Documentación', labelKey: 'group_docs',
    items: [
      { id: 'documents', icon: FileText, labelKey: 'nav_documents', fallback: 'Documentos' },
      { id: 'wiki',      icon: BookOpen, labelKey: 'nav_wiki',      fallback: 'Wiki' },
      { id: 'invoices',  icon: Receipt,  labelKey: 'invoices_title', fallback: 'Facturas' },
    ],
  },
  {
    label: 'Cuenta', labelKey: 'group_account',
    items: [
      { id: 'surveys', icon: Sparkles, labelKey: 'nav_surveys', fallback: 'Encuestas' },
      { id: 'profile', icon: Settings, labelKey: 'profile_title', fallback: 'Mi perfil' },
    ],
  },
]

type NavItem = (typeof PORTAL_NAV_GROUPS)[number]['items'][number]
type SectionCfg = NavItem & { group: string; groupKey: string }

/** Icono de lucide (o compatible) que se pinta con un tamaño. */
export type PortalIcon = ComponentType<{ size?: number | string }>

const SECTION_INDEX: Record<string, SectionCfg> = (() => {
  const out: Record<string, SectionCfg> = {}
  for (const g of PORTAL_NAV_GROUPS) for (const it of g.items) out[it.id] = { ...it, group: g.label, groupKey: g.labelKey }
  return out
})()

// ── Shell ────────────────────────────────────────────────────────────────────
export interface PortalBranding {
  logo_url?: string | null
  brand_name?: string | null
  primary_color?: string | null
}

/** Contadores por sección (id de sección → pendientes). */
export type PortalBadges = Record<string, number | undefined>

interface PortalShellProps {
  section: string
  onSection: (section: string) => void
  branding?: PortalBranding | null
  badges?: PortalBadges
  children?: ReactNode
}

export function PortalShell({ section, onSection, branding, badges, children }: PortalShellProps) {
  const { t: traducir } = useAppLang()
  const { client, logout } = useClientAuth()
  const t = useLang()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('portal_sidebar_collapsed') === '1')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [quickOpen, setQuickOpen] = useState(false)

  useEffect(() => { localStorage.setItem('portal_sidebar_collapsed', collapsed ? '1' : '0') }, [collapsed])

  // Atajo de teclado: ⌘+Shift+N / Ctrl+Shift+N abre el menú quick-create (igual que backoffice)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault()
        setQuickOpen(o => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const projectsCount = (client?.projects?.length || client?.project_ids?.length || 0)
  const sectionCfg = SECTION_INDEX[section] || SECTION_INDEX.dashboard

  const tr = (key: string, fallback: string) => {
    const v = t(key)
    return (v && v !== key) ? v : fallback
  }

  return (
    <div className="portui-row-1">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside
        className={`${mobileOpen ? 'portal-sidebar portal-sidebar--open' : 'portal-sidebar'} portalui-sx1`}
        style={{ width: collapsed ? 68 : 240 }}
      >
        {/* Brand */}
        <div className="portui-row-22" style={{ padding: collapsed ? '16px 12px' : '16px 18px' }}>
          {branding?.logo_url ? (
            <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} loading="lazy" decoding="async" className="portui-box-1" />
          ) : (
            <div className="portui-row-23" style={{ background: `linear-gradient(135deg, ${branding?.primary_color || 'var(--accent)'}, var(--purple, #7c3aed))` }}>◈</div>
          )}
          {!collapsed && (
            <div className="u-flex1-min0">
              <div className="portui-box-2">
                {branding?.brand_name || tr('portal', 'Portal cliente')}
              </div>
              <div className="portui-box-3">
                {client?.organization_name || client?.company || ''}
              </div>
            </div>
          )}
          <button className="portui-box-25"
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? 'Expandir menú' : 'Colapsar menú'}
            style={{ display: collapsed ? 'none' : 'inline-flex' }}
          ><X size={14} /></button>
        </div>

        {/* Filter */}
        {!collapsed && (
          <div className="portui-sp-1">
            <div className="portui-box-4">
              <Search size={13} className="portalui-sx2" />
              <input
                value={filter}
                onChange={e => setFilter(e.target.value)}
                placeholder={traducir('portalui.buscar')}
                aria-label={traducir('portalui.filtrar_menu')}
                className="portui-box-5"
              />
            </div>
          </div>
        )}

        {/* Nav */}
        <nav className="portui-box-6">
          {PORTAL_NAV_GROUPS.map(group => {
            const items = group.items.filter(it => {
              if (!filter) return true
              const label = tr(it.labelKey, it.fallback).toLowerCase()
              return label.includes(filter.toLowerCase())
            })
            if (items.length === 0) return null
            return (
              <div key={group.label} className="u-mb-14">
                {!collapsed && (
                  <div className="portui-box-7">
                    {tr(group.labelKey, group.label)}
                  </div>
                )}
                {items.map(it => {
                  const Icon = it.icon
                  const active = section === it.id
                  const badge = badges?.[it.id]
                  return (
                    <button className="portui-row-24"
                      key={it.id}
                      onClick={() => { onSection(it.id); setMobileOpen(false) }}
                      title={collapsed ? tr(it.labelKey, it.fallback) : undefined}
                      style={{ padding: collapsed ? '9px 10px' : '8px 10px', background: active ? 'var(--accent-muted)' : 'transparent', color: active ? 'var(--accent)' : 'var(--text-2)', fontWeight: active ? 700 : 500, justifyContent: collapsed ? 'center' : 'flex-start' }}
                      onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text-1)' } }}
                      onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-2)' } }}
                    >
                      <Icon size={16} aria-hidden="true" style={{ flexShrink: 0 }} />
                      {!collapsed && <span className="portui-box-8">{tr(it.labelKey, it.fallback)}</span>}
                      {!collapsed && badge != null && badge > 0 && (
                        <span className="portui-box-34">{badge > 99 ? '99+' : badge}</span>
                      )}
                      {collapsed && badge != null && badge > 0 && (
                        <span className="portui-box-35" />
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </nav>

        {/* User block */}
        <div className="portui-box-9">
          {!collapsed ? (
            <>
              <div className="portui-row-2">
                <div className="portui-row-30">{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
                <div className="portui-box-10">
                  <div className="portui-box-11">{client?.full_name || client?.email}</div>
                  <div className="portui-box-12">{projectsCount} {traducir('portalui.proyecto')}{projectsCount === 1 ? '' : 's'}</div>
                </div>
              </div>
              <button
                onClick={logout}
                className="portui-row-3"
              ><LogOut size={13} /> {tr('logout', 'Cerrar sesión')}</button>
            </>
          ) : (
            <button onClick={() => setCollapsed(false)}
              aria-label={traducir('portalui.expandir_menu')}
              className="portui-row-4"><Menu size={14} /></button>
          )}
        </div>
      </aside>

      {/* ── Main column ─────────────────────────────────────────────────── */}
      <main className="portui-stack-1">
        {/* Topbar */}
        <header className="portui-row-5">
          <button onClick={() => setMobileOpen(true)}
            className="portal-mobile-toggle portui-box-13"
            aria-label={traducir('portalui.abrir_menu')}
            ><Menu size={18} /></button>

          <div className="u-flex1-min0">
            <div className="portui-txt-1">
              {tr(sectionCfg.groupKey, sectionCfg.group)}
            </div>
            <div className="portui-box-14">
              {tr(sectionCfg.labelKey, sectionCfg.fallback)}
            </div>
          </div>

          <div className="u-row-center-10">
            <button
              onClick={() => setQuickOpen(true)}
              title={traducir('portalui.crear_nuevo')}
              aria-label={traducir('portalui.crear_nuevo_2')}
              className="portui-row-6"
              onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              <Plus size={16} />
            </button>
            <button
              onClick={() => onSection('support')}
              title={traducir('portalui.notificaciones_pendientes')}
              aria-label={traducir('nav.notifications')}
              className="portui-row-7"
            >
              <Bell size={15} />
              {(badges?.support || 0) + (badges?.messages || 0) > 0 && (
                <span className="portui-row-31">{Math.min((badges?.support || 0) + (badges?.messages || 0), 99)}</span>
              )}
            </button>
            <div className="portui-row-32">{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
          </div>
        </header>

        {/* Content */}
        <div className="page-content portui-box-15">
          {children}
        </div>
      </main>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div role="presentation" onClick={() => setMobileOpen(false)} className="portalui-sx3" />
      )}

      {/* Quick create floating panel (réplica del backoffice) */}
      {quickOpen && (
        <PortalQuickCreateMenu
          onClose={() => setQuickOpen(false)}
          onAction={(target) => onSection(target)}
          badges={badges}
        />
      )}

      <style>{`
        @media (max-width: 880px) {
          .portal-sidebar {
            position: fixed !important;
            top: 0; left: 0;
            transform: translateX(-100%);
            transition: transform 0.2s ease, width 0.18s ease !important;
          }
          .portal-sidebar--open {
            transform: translateX(0) !important;
          }
          .portal-mobile-toggle {
            display: inline-flex !important;
          }
        }
      `}</style>
    </div>
  )
}

// ── Page Header ──────────────────────────────────────────────────────────────
export interface PortalBreadcrumb {
  label: ReactNode
  onClick?: () => void
}

export interface PortalMetaItem {
  icon?: ReactNode
  value?: ReactNode
  label?: ReactNode
  color?: string
}

/** Quita las entradas condicionales (`cond && {...}`) de una lista de meta. */
export function metaItems(items: Array<PortalMetaItem | false | null | undefined | 0 | ''>): PortalMetaItem[] {
  return items.filter((m): m is PortalMetaItem => Boolean(m))
}

interface PortalPageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  icon?: PortalIcon
  actions?: ReactNode
  meta?: PortalMetaItem[]
  breadcrumb?: PortalBreadcrumb[]
}

export function PortalPageHeader({ title, subtitle, icon: Icon, actions, meta, breadcrumb }: PortalPageHeaderProps) {
  return (
    <div className="portui-box-16">
      {breadcrumb && (
        <div className="portui-row-8">
          {breadcrumb.map((c, i) => (
            <span key={i} className="u-row-center-6">
              {i > 0 && <span className="portui-txt-2">›</span>}
              {c.onClick ? (
                <button className="portui-box-26" type="button" onClick={c.onClick} style={{ color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)' }}>{c.label}</button>
              ) : (
                <span className="portui-txt-8" style={{ color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)' }}>{c.label}</span>
              )}
            </span>
          ))}
        </div>
      )}
      <div className="portui-row-9">
        <div className="u-min0">
          <div className="u-row-center-12">
            {Icon && (
              <div className="portui-row-10"><Icon size={18} /></div>
            )}
            <h1 className="portui-box-17">{title}</h1>
          </div>
          {subtitle && (
            <p className="portui-box-27" style={{ paddingLeft: Icon ? 50 : 0 }}>{subtitle}</p>
          )}
          {meta && meta.length > 0 && (
            <div className="portui-row-25" style={{ paddingLeft: Icon ? 50 : 0 }}>
              {meta.map((m, i) => (
                <div key={i} className="portui-row-11">
                  {m.icon && <span className="portui-row-12">{m.icon}</span>}
                  <span style={{ color: m.color || 'var(--text-2)' }}>{m.value}</span>
                  {m.label && <span className="u-text3">{m.label}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        {actions && (
          <div className="portui-row-13">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────
interface PortalCardProps {
  children?: ReactNode
  className?: string
  style?: CSSProperties
  accent?: boolean
  padding?: CSSProperties['padding']
  onClick?: (e: ReactMouseEvent<HTMLDivElement> | ReactKeyboardEvent<HTMLDivElement>) => void
}

export function PortalCard({ children, className, style, accent, padding, onClick }: PortalCardProps) {
  const cls = `portal-card${accent ? ' portal-card--accent' : ''}${onClick ? ' portal-card--click' : ''}${className ? ` ${className}` : ''}`
  const st = padding === undefined ? style : ({ '--portal-card-pad': typeof padding === 'number' ? `${padding}px` : padding, ...style } as CSSProperties)
  if (onClick) {
    return (
      <div
        role="button" tabIndex={0}
        onClick={onClick}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(e) } }}
        className={cls}
        style={st}
      >{children}</div>
    )
  }
  return <div className={cls} style={st}>{children}</div>
}

// ── KPI ──────────────────────────────────────────────────────────────────────
interface PortalKpiProps {
  icon?: PortalIcon
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: string
  trend?: number | null
  footer?: ReactNode
  big?: boolean
}

export function PortalKpi({ icon: Icon, label, value, sub, tone = 'default', trend, footer, big = false }: PortalKpiProps) {
  const toneColor = ({
    default: 'var(--text-1)',
    accent:  'var(--accent)',
    success: 'var(--success, #10b981)',
    warning: 'var(--warning, #f59e0b)',
    danger:  'var(--danger, #ef4444)',
    purple:  'var(--purple, #7c3aed)',
  } as Record<string, string>)[tone] || 'var(--text-1)'
  const trendColor = trend > 0 ? 'var(--success)' : trend < 0 ? 'var(--danger)' : 'var(--text-3)'
  return (
    <PortalCard padding={big ? 22 : 18} className="portalui-sx4" style={{ minHeight: big ? 132 : 116 }}>
      <div className="portui-row-14">
        {Icon && (
          <div className="portui-row-26" style={{ background: `${toneColor === 'var(--text-1)' ? 'var(--accent-muted)' : alpha(toneColor, '18')}`, color: toneColor === 'var(--text-1)' ? 'var(--accent)' : toneColor }}><Icon size={15} /></div>
        )}
        {trend !== undefined && trend !== null && (
          <span className="portui-txt-9" style={{ color: trendColor }}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div className="portui-box-28" style={{ fontSize: big ? 'var(--text-3xl-em, 28px)' : 'var(--text-2xl-em)', color: toneColor }}>{value}</div>
      <div className="portui-txt-3">{label}</div>
      {sub && <div className="u-hint">{sub}</div>}
      {footer && <div className="portui-sp-2">{footer}</div>}
    </PortalCard>
  )
}

// ── Section heading ──────────────────────────────────────────────────────────
interface PortalSectionProps {
  title?: ReactNode
  hint?: ReactNode
  action?: ReactNode
  children?: ReactNode
  style?: CSSProperties
}

export function PortalSection({ title, hint, action, children, style = {} }: PortalSectionProps) {
  return (
    <div style={{ marginBottom: 22, ...style }}>
      <div className="portui-row-15">
        <div>
          <div className="portui-txt-4">{title}</div>
          {hint && <div className="u-text3-xs-mt2">{hint}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
export interface PortalTab {
  id: string
  label: ReactNode
  icon?: ReactNode
  badge?: number | null
}

interface PortalTabsProps {
  tabs: PortalTab[]
  value: string
  onChange: (id: string) => void
  ariaLabel?: string
}

export function PortalTabs({ tabs, value, onChange, ariaLabel }: PortalTabsProps) {
  const { listRef, onKeyDown, focusId } = useTabListKeys(tabs.map(tab => tab.id), value, onChange)
  return (
    <div ref={listRef} role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown} className="portui-row-16">
      {tabs.map(tab => {
        const active = value === tab.id
        return (
          <button className="portui-row-27"
            key={tab.id} role="tab" aria-selected={active}
            data-tab-id={tab.id} tabIndex={tab.id === focusId ? 0 : -1}
            onClick={() => onChange(tab.id)}
            style={{ borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`, fontWeight: active ? 700 : 500, color: active ? 'var(--accent)' : 'var(--text-2)' }}
          >
            {tab.icon}
            {tab.label}
            {tab.badge != null && tab.badge > 0 && (
              <span className="portui-box-29" style={{ background: active ? 'var(--accent-muted)' : 'var(--surface-3)', color: active ? 'var(--accent)' : 'var(--text-2)' }}>{tab.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────
interface PortalEmptyProps {
  icon?: PortalIcon
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}

export function PortalEmpty({ icon: Icon, title, description, action }: PortalEmptyProps) {
  return (
    <div className="portui-stack-2">
      {Icon && (
        <div className="portui-row-17"><Icon size={22} /></div>
      )}
      <div className="portui-box-18">{title}</div>
      {description && (
        <div className="portui-box-19">
          {description}
        </div>
      )}
      {action && <div className="portui-sp-3">{action}</div>}
    </div>
  )
}

// ── Progress ─────────────────────────────────────────────────────────────────
interface PortalProgressProps {
  value: number
  max?: number
  color?: string
  height?: number
  showLabel?: boolean
}

export function PortalProgress({ value, max = 100, color, height = 6, showLabel = false }: PortalProgressProps) {
  const pct = max ? Math.min((value / max) * 100, 100) : 0
  const c = color || (pct > 90 ? 'var(--danger)' : pct > 70 ? 'var(--warning)' : 'var(--success)')
  return (
    <div>
      <div className="portui-box-30" style={{ height }}>
        <div className="portui-box-31" style={{ width: `${pct}%`, background: c }} />
      </div>
      {showLabel && (
        <div className="portui-box-20">
          {Math.round(pct)}%
        </div>
      )}
    </div>
  )
}

// ── Badge ────────────────────────────────────────────────────────────────────
interface PortalBadgeProps {
  children?: ReactNode
  tone?: string
  icon?: ReactNode
}

export function PortalBadge({ children, tone = 'default', icon }: PortalBadgeProps) {
  // Mismo API de siempre (tone/icon); el pintado es el badge compartido.
  const kinds: Record<string, StatusBadgeKind> = {
    default: 'neutral', accent: 'accent', success: 'success', warning: 'warning',
    danger: 'danger', orange: 'orange', purple: 'purple',
  }
  return (
    <StatusBadge kind={kinds[tone] || 'neutral'}>
      {icon}
      {children}
    </StatusBadge>
  )
}

// ── Button ───────────────────────────────────────────────────────────────────
interface PortalButtonProps {
  children?: ReactNode
  onClick?: (e: ReactMouseEvent<HTMLButtonElement>) => void
  variant?: string
  size?: string
  disabled?: boolean
  loading?: boolean
  icon?: ReactNode
  type?: 'button' | 'submit' | 'reset'
  style?: CSSProperties
}

export function PortalButton({ children, onClick, variant = 'primary', size = 'md', disabled, loading, icon, type = 'button', style = {} }: PortalButtonProps) {
  const v = ({
    primary:   { background: 'var(--accent)', color: 'var(--on-accent)', border: '1px solid var(--accent)' },
    secondary: { background: 'var(--surface-3)', color: 'var(--text-1)', border: '1px solid var(--surface-4)' },
    danger:    { background: 'var(--danger-bg, rgba(239,68,68,0.12))', color: 'var(--danger)', border: '1px solid var(--danger-border, rgba(239,68,68,0.3))' },
    ghost:     { background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))' },
    subtle:    { background: 'var(--accent-muted)', color: 'var(--accent)', border: '1px solid transparent' },
  } as Record<string, CSSProperties>)[variant] || {}
  const s = ({
    sm: { fontSize: 'var(--text-sm)', padding: '6px 12px', gap: 5 },
    md: { fontSize: 'var(--text-sm)', padding: '8px 16px', gap: 6 },
    lg: { fontSize: 'var(--text-base)', padding: '10px 22px', gap: 7 },
  } as Record<string, CSSProperties>)[size] || {}
  const dis = disabled || loading
  return (
    <button
      type={type} onClick={dis ? undefined : onClick} disabled={dis}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'inherit', fontWeight: 600, borderRadius: 'var(--radius-md, 8px)',
        cursor: dis ? 'not-allowed' : 'pointer', opacity: dis ? 0.55 : 1,
        transition: 'opacity 0.15s, transform 0.1s',
        whiteSpace: 'nowrap', ...v, ...s, ...style,
      }}
      onMouseEnter={e => { if (!dis) e.currentTarget.style.opacity = '0.85' }}
      onMouseLeave={e => { if (!dis) e.currentTarget.style.opacity = '1' }}
    >
      {loading ? (
        <span className="portui-box-21" />
      ) : icon}
      {children}
      <style>{`@keyframes portalspin { to { transform: rotate(360deg); } }`}</style>
    </button>
  )
}

// ── Input / Select / Textarea ────────────────────────────────────────────────
const fieldBase: CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md, 8px)', padding: '9px 13px',
  color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none',
  fontFamily: 'inherit', transition: 'border-color 0.15s, box-shadow 0.15s',
}

interface PortalFieldProps {
  label?: ReactNode
  hint?: ReactNode
  required?: boolean
  children?: ReactNode
}

export function PortalField({ label, hint, required, children }: PortalFieldProps) {
  return (
    <div className="portui-stack-3">
      {label && (
        <label className="portui-txt-5">
          {label}{required && <span className="u-danger"> *</span>}
        </label>
      )}
      {children}
      {hint && <div className="u-text3-xs">{hint}</div>}
    </div>
  )
}

export function PortalInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{ ...fieldBase, ...(props.style || {}) }}
      onFocus={e => { e.target.style.borderColor = 'var(--accent-border-strong, color-mix(in srgb, var(--accent) 50%, transparent))'; e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)' }}
      onBlur={e => { e.target.style.borderColor = 'var(--surface-4)'; e.target.style.boxShadow = 'none' }}
    />
  )
}

export function PortalSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} style={{ ...fieldBase, ...(props.style || {}) }}>
      {props.children}
    </select>
  )
}

export function PortalTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea {...props} style={{ ...fieldBase, resize: 'vertical', ...(props.style || {}) }} />
  )
}

// ── Modal ────────────────────────────────────────────────────────────────────
interface PortalModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  subtitle?: ReactNode
  width?: CSSProperties['maxWidth']
  children?: ReactNode
  footer?: ReactNode
}

export function PortalModal({ open, onClose, title, subtitle, width = 560, children, footer }: PortalModalProps) {
  const { t: traducir } = useAppLang()
  if (!open) return null
  return (
    <div role="presentation" onMouseDown={onClose} className="portalui-sx5">
      <div className="portui-box-32 portalui-sx6" role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()} style={{ maxWidth: width }}>
        <div className="portui-row-18">
          <div>
            <h2 className="portui-box-22">{title}</h2>
            {subtitle && <p className="portui-box-23">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label={traducir('common.close')} className="portui-row-19"><X size={14} /></button>
        </div>
        {children}
        {footer && (
          <div className="portui-row-20">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Banner ───────────────────────────────────────────────────────────────────
interface PortalBannerProps {
  tone?: string
  icon?: ReactNode
  title?: ReactNode
  body?: ReactNode
  action?: ReactNode
}

export function PortalBanner({ tone = 'info', icon, title, body, action }: PortalBannerProps) {
  const tones: Record<string, { bg: string; bd: string; fg: string }> = {
    info:    { bg: 'var(--accent-muted)', bd: 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))', fg: 'var(--accent)' },
    warning: { bg: 'var(--warning-bg, rgba(245,158,11,0.12))', bd: 'var(--warning-border, rgba(245,158,11,0.3))', fg: 'var(--warning)' },
    danger:  { bg: 'var(--danger-bg, rgba(239,68,68,0.12))',  bd: 'var(--danger-border, rgba(239,68,68,0.3))',  fg: 'var(--danger)' },
    success: { bg: 'var(--success-bg, rgba(16,185,129,0.12))', bd: 'var(--success-border, rgba(16,185,129,0.3))', fg: 'var(--success)' },
  }
  const c = tones[tone] || tones.info
  return (
    <div className="portui-row-28 portalui-sx7" style={{ background: c.bg, border: `1px solid ${c.bd}` }}>
      {icon && <div className="portui-row-29" style={{ color: c.fg }}>{icon}</div>}
      <div className="u-flex1-min0">
        <div className="portui-txt-10" style={{ color: c.fg }}>{title}</div>
        {body && <div className="u-text2-sm-mt2">{body}</div>}
      </div>
      {action}
    </div>
  )
}

// ── Donut chart (lightweight SVG) ────────────────────────────────────────────
export interface PortalDonutSegment {
  value?: number | null
  color?: string
}

interface PortalDonutProps {
  size?: number
  stroke?: number
  segments?: PortalDonutSegment[]
  centerTop?: ReactNode
  centerBottom?: ReactNode
}

export function PortalDonut({ size = 110, stroke = 12, segments = [], centerTop, centerBottom }: PortalDonutProps) {
  const { t: traducir } = useAppLang()
  const radius = size / 2 - stroke / 2
  const circ = 2 * Math.PI * radius
  const total = segments.reduce((s, x) => s + Math.max(0, x.value || 0), 0)
  let offset = 0
  return (
    <div className="portui-box-33" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={traducir('portalui.distribucion')}>
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="var(--surface-4)" strokeWidth={stroke} />
        {total > 0 && segments.map((seg, i) => {
          const len = (Math.max(0, seg.value || 0) / total) * circ
          const dasharray = `${len} ${circ - len}`
          const dashoffset = -offset
          offset += len
          return (
            <circle key={i} cx={size/2} cy={size/2} r={radius} fill="none"
              stroke={seg.color} strokeWidth={stroke}
              strokeDasharray={dasharray} strokeDashoffset={dashoffset}
              transform={`rotate(-90 ${size/2} ${size/2})`}
              strokeLinecap="butt" />
          )
        })}
      </svg>
      <div className="portui-stack-4">
        {centerTop && <div className="portui-txt-6">{centerTop}</div>}
        {centerBottom && <div className="portui-txt-1">{centerBottom}</div>}
      </div>
    </div>
  )
}

// ── Sparkline ────────────────────────────────────────────────────────────────
interface PortalSparkProps {
  values?: number[]
  width?: number
  height?: number
  color?: string
}

export function PortalSpark({ values = [], width = 110, height = 32, color = 'var(--accent)' }: PortalSparkProps) {
  const { t: traducir } = useAppLang()
  if (!values.length) return null
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 1)
  const span = max - min || 1
  const stepX = values.length > 1 ? width / (values.length - 1) : width
  const path = values
    .map((v: number, i: number) => {
      const x = i * stepX
      const y = height - ((v - min) / span) * height
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
  const areaPath = `${path} L ${(stepX * (values.length - 1)).toFixed(1)} ${height} L 0 ${height} Z`
  return (
    <svg width={width} height={height} role="img" aria-label={traducir('portalui.tendencia')}>
      <path d={areaPath} fill={color} opacity="0.15" />
      <path d={path} stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Horizontal bars (distribution) ──────────────────────────────────────────
export interface PortalBarItem {
  label: ReactNode
  value?: number | null
  color?: string
  suffix?: string
}

export function PortalBars({ items = [] }: { items?: PortalBarItem[] }) {
  const max = Math.max(1, ...items.map(i => i.value || 0))
  return (
    <div className="u-stack-10">
      {items.map((it, idx) => (
        <div key={idx}>
          <div className="portui-row-21">
            <span className="portui-txt-7">{it.label}</span>
            <span className="portui-txt-11" style={{ color: it.color || 'var(--text-1)' }}>{it.value}{it.suffix || ''}</span>
          </div>
          <div className="portui-box-24">
            <div className="portui-box-31" style={{ width: `${((it.value || 0) / max) * 100}%`, background: it.color || 'var(--accent)' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Helpers exportados ───────────────────────────────────────────────────────

export function formatDuration(minutes: number | string | null | undefined) {
  if (minutes == null || Number.isNaN(Number(minutes))) return '—'
  const m = Math.round(Number(minutes))
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h}h ${r}min` : `${h}h`
}

/**
 * Moneda por defecto del portal cuando el dato no trae la suya. El portal no
 * puede leer la de la empresa: /settings/org-defaults exige sesion de empleado
 * (get_current_user) y el cliente entra con token de portal. Las facturas y
 * pedidos traen `currency`; esto solo cubre el caso de no tener ninguno.
 */
export const MONEDA_PORTAL_POR_DEFECTO = 'EUR'

export function formatMoney(value: number | string | null | undefined, currency: string | null | undefined = MONEDA_PORTAL_POR_DEFECTO) {
  return formatearMoneda(Number(value || 0), currency || MONEDA_PORTAL_POR_DEFECTO)
}

