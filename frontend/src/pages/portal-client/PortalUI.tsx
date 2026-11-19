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
  Bell, X, Menu, Plus, Sparkles, PanelLeftClose, Inbox,
} from 'lucide-react'
import { useClientAuth, useLang } from './portalClientContext'
import PortalQuickCreateMenu from './PortalQuickCreateMenu'
import CampanaDelPortal from './CampanaDelPortal'
import Tabs from '../../components/ui/Tabs'
import { Button, EmptyState, Pulsable, Select } from '../../components/ui'
import { formatearMoneda } from '../../utils/helpers'
import { tonoDe, UMBRALES_POR_DEFECTO } from '../../utils/umbrales'
import type { Umbrales } from '../../utils/umbrales'
import StatusBadge, { type StatusBadgeKind } from '../../components/ui/StatusBadge'
import './PortalUI.css'
import { px } from '../../utils/estilos'

// ── Section configuration (grouped like the backoffice) ──────────────────────
export const PORTAL_NAV_GROUPS = [
  {
    label: 'Resumen', labelKey: 'group_overview',
    items: [
      { id: 'dashboard', icon: LayoutDashboard, labelKey: 'nav_dashboard', fallback: 'Inicio' },
    ],
  },
  {
    label: 'Entrega', labelKey: 'group_delivery',
    items: [
      { id: 'roadmap',  icon: Map,          labelKey: 'nav_roadmap',  fallback: 'Hoja de ruta' },
      { id: 'uat',      icon: FlaskConical, labelKey: 'nav_uat',      fallback: 'Pruebas UAT' },
      { id: 'requests', icon: Lightbulb,    labelKey: 'nav_requests', fallback: 'Solicitudes' },
    ],
  },
  {
    label: 'Soporte', labelKey: 'group_support',
    items: [
      { id: 'support',  icon: Headphones,     labelKey: 'nav_support',  fallback: 'Autoservicio' },
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
      { id: 'notifications', icon: Bell, labelKey: 'nav.notifications', fallback: 'Notificaciones' },
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
  /** El WebSocket del portal está abierto: la campana no sondea. */
  avisosEnVivo?: boolean
  children?: ReactNode
}

export function PortalShell({ section, onSection, branding, badges, avisosEnVivo = false, children }: PortalShellProps) {
  const traducir = useLang()
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
        className={`${mobileOpen ? 'portal-sidebar portal-sidebar--open' : 'portal-sidebar'} portalui-sx1 ${collapsed ? 'portal-ui-m1' : 'portal-ui-m2'}`}
      >
        {/* Brand */}
        <div className={`portui-row-22 ${collapsed ? 'portal-ui-m3' : 'portal-ui-m4'}`}>
          {branding?.logo_url ? (
            <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} loading="lazy" decoding="async" className="portui-box-1" />
          ) : (
            <div className="portui-row-23 portal-ui-e5" style={{ '--portal-ui-background': `linear-gradient(135deg, ${branding?.primary_color || 'var(--accent)'}, var(--purple, #7c3aed))` } as CSSProperties}>◈</div>
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
          <Pulsable className={`portui-box-25 ${collapsed ? 'portal-ui-m6' : 'portal-ui-m7'}`}
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? traducir('portalui.expandir_menu') : tr('sidebar_collapse', 'Contraer menú')}
            title={tr('sidebar_collapse', 'Contraer menú')}
          ><PanelLeftClose size={14} /></Pulsable>
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
                    <Pulsable className={`portui-row-24 ${collapsed ? 'portal-ui-m8' : 'portal-ui-m9'} ${active ? 'portal-ui-m10' : 'portal-ui-m11'}`}
                      key={it.id}
                      onClick={() => { onSection(it.id); setMobileOpen(false) }}
                      title={collapsed ? tr(it.labelKey, it.fallback) : undefined}
                      aria-current={active ? 'page' : undefined}
                    >
                      <Icon size={16} aria-hidden="true" className="portal-ui-icono-fijo" />
                      {!collapsed && <span className="portui-box-8">{tr(it.labelKey, it.fallback)}</span>}
                      {!collapsed && badge != null && badge > 0 && (
                        <span className="portui-box-34">{badge > 99 ? '99+' : badge}</span>
                      )}
                      {collapsed && badge != null && badge > 0 && (
                        <span className="portui-box-35" />
                      )}
                    </Pulsable>
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
                  <div className="portui-box-12">{(projectsCount === 1 ? tr('sidebar_projects_one', '{{n}} proyecto') : tr('sidebar_projects_other', '{{n}} proyectos')).replace('{{n}}', String(projectsCount))}</div>
                </div>
              </div>
              <Pulsable
                onClick={logout}
                className="portui-row-3"
              ><LogOut size={13} /> {tr('logout', 'Cerrar sesión')}</Pulsable>
            </>
          ) : (
            <Pulsable onClick={() => setCollapsed(false)}
              aria-label={traducir('portalui.expandir_menu')}
              className="portui-row-4"><Menu size={14} /></Pulsable>
          )}
        </div>
      </aside>

      {/* ── Main column ─────────────────────────────────────────────────── */}
      <main className="portui-stack-1">
        {/* Topbar */}
        <header className="portui-row-5">
          <Pulsable onClick={() => setMobileOpen(true)}
            className="portal-mobile-toggle portui-box-13"
            aria-label={traducir('portalui.abrir_menu')}
            ><Menu size={18} /></Pulsable>

          <div className="u-flex1-min0">
            <div className="portui-txt-1">
              {tr(sectionCfg.groupKey, sectionCfg.group)}
            </div>
            <div className="portui-box-14">
              {tr(sectionCfg.labelKey, sectionCfg.fallback)}
            </div>
          </div>

          <div className="u-row-center-10">
            <Pulsable
              onClick={() => setQuickOpen(true)}
              title={traducir('portalui.crear_nuevo')}
              aria-label={traducir('portalui.crear_nuevo_2')}
              className="portui-row-6"
            >
              <Plus size={16} />
            </Pulsable>
            {/* Campana de avisos del cliente (16-11-2026): contador y panel. */}
            <CampanaDelPortal onSection={onSection} enVivo={avisosEnVivo} />
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
                <Pulsable className={`portui-box-26 ${i === breadcrumb.length - 1 ? 'portal-ui-m12' : 'portal-ui-m13'}`} onClick={c.onClick}>{c.label}</Pulsable>
              ) : (
                <span className={`portui-txt-8 ${i === breadcrumb.length - 1 ? 'portal-ui-m12' : 'portal-ui-m13'}`}>{c.label}</span>
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
            <p className={`portui-box-27 ${Icon ? 'portal-ui-m14' : 'portal-ui-m15'}`}>{subtitle}</p>
          )}
          {meta && meta.length > 0 && (
            <div className={`portui-row-25 ${Icon ? 'portal-ui-m14' : 'portal-ui-m15'}`}>
              {meta.map((m, i) => (
                <div key={i} className="portui-row-11">
                  {m.icon && <span className="portui-row-12">{m.icon}</span>}
                  <span className="portal-ui-e16" style={{ '--portal-ui-color': m.color || 'var(--text-2)' } as CSSProperties}>{m.value}</span>
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

/**
 * 16-11-2026 (pasada de diseño): misma forma que `KpiCard` (components/ui):
 * cifra grande sin monoespaciado, etiqueta en versalitas debajo, icono pequeño
 * y apagado. Se queda aquí solo porque el portal necesita `footer` (barra de
 * progreso), que KpiCard no tiene; `big` se acepta y se ignora.
 */
export function PortalKpi({ icon: Icon, label, value, sub, tone = 'default', trend, footer }: PortalKpiProps) {
  const toneColor = ({
    default: 'var(--text-1)',
    accent:  'var(--accent)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    danger:  'var(--danger)',
    purple:  'var(--text-1)',
  } as Record<string, string>)[tone] || 'var(--text-1)'
  const trendColor = (trend ?? 0) > 0 ? 'var(--success)' : (trend ?? 0) < 0 ? 'var(--danger)' : 'var(--text-3)'
  const hayTrend = trend !== undefined && trend !== null
  return (
    <div className="ds-card ui-kpi portal-ui-kpi">
      <div className="ui-kpi__fila">
        <div className="ui-kpi__valor portal-ui-e16" style={{ '--portal-ui-color': toneColor } as CSSProperties}>{value}</div>
        {(Icon || hayTrend) && (
          <div className="ui-kpi__extra">
            {trend !== undefined && trend !== null && (
              <span className="portui-txt-9 portal-ui-e16" style={{ '--portal-ui-color': trendColor } as CSSProperties}>
                {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
              </span>
            )}
            {Icon && <span className="ui-kpi__icono" aria-hidden="true"><Icon size={16} /></span>}
          </div>
        )}
      </div>
      <div className="ds-eyebrow">{label}</div>
      {sub && <div className="ui-kpi__sub">{sub}</div>}
      {footer && <div className="portui-sp-2">{footer}</div>}
    </div>
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
    <div className="portal-ui-e32" style={style}>
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

/** 16-11-2026 (pasada de diseño): las pestañas del portal son las de la
 *  aplicación (`Tabs`, pastilla); antes eran un subrayado propio. */
export function PortalTabs({ tabs, value, onChange, ariaLabel }: PortalTabsProps) {
  return (
    <Tabs
      className="portui-tabs"
      ariaLabel={ariaLabel}
      active={value}
      onChange={onChange}
      items={tabs.map(tab => ({
        id: tab.id,
        label: tab.label,
        icon: tab.icon,
        count: tab.badge != null && tab.badge > 0 ? tab.badge : undefined,
      }))}
    />
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────
interface PortalEmptyProps {
  icon?: PortalIcon
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}

/** 16-11-2026 (pasada de diseño): el vacío de la aplicación (`EmptyState`). */
export function PortalEmpty({ icon: Icon, title, description, action }: PortalEmptyProps) {
  return (
    <EmptyState
      icon={Icon ? <Icon size={28} /> : <Inbox size={28} />}
      title={title}
      description={description}
      action={action}
    />
  )
}

// ── Progress ─────────────────────────────────────────────────────────────────
interface PortalProgressProps {
  value: number
  max?: number
  color?: string
  height?: number
  showLabel?: boolean
  /** Sin `color`: semáforo de presupuesto con estos umbrales (los de la empresa llegan con el panel). */
  umbrales?: Umbrales
}

export function PortalProgress({ value, max = 100, color, height = 6, showLabel = false, umbrales = UMBRALES_POR_DEFECTO }: PortalProgressProps) {
  const pct = max ? Math.min((value / max) * 100, 100) : 0
  // 19-11-2026: los umbrales de presupuesto de la empresa (antes 70/90 aquí).
  const c = color || `var(--${tonoDe('presupuesto', pct, umbrales) ?? 'success'})`
  return (
    <div>
      <div className="portui-box-30 portal-ui-e27" style={{ '--portal-ui-height': px(height) } as CSSProperties}>
        <div className="portui-box-31 portal-ui-e28" style={{ '--portal-ui-width': `${pct}%`, '--portal-ui-background': c } as CSSProperties} />
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

/** 16-11-2026 (pasada de diseño): el botón de la aplicación (`Button`), con
 *  la misma API de siempre. */
export function PortalButton({ children, onClick, variant = 'primary', size = 'md', disabled, loading, icon, type = 'button', style }: PortalButtonProps) {
  const v = (['primary', 'secondary', 'danger', 'ghost', 'subtle'].includes(variant) ? variant : 'primary') as 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle'
  const sz = (['xs', 'sm', 'md', 'lg'].includes(size) ? size : 'md') as 'xs' | 'sm' | 'md' | 'lg'
  return (
    <Button type={type} onClick={onClick} variant={v} size={sz} disabled={disabled} loading={loading} icon={icon} style={style}>
      {children}
    </Button>
  )
}

// ── Input / Select / Textarea ────────────────────────────────────────────────
interface PortalFieldProps {
  label?: ReactNode
  hint?: ReactNode
  required?: boolean
  /** Error de validación del servidor (o local) de este campo. */
  error?: string
  children?: ReactNode
}

export function PortalField({ label, hint, required, error, children }: PortalFieldProps) {
  return (
    <div className="portui-stack-3">
      {label && (
        <label className="portui-txt-5">
          {label}{required && <span className="u-danger"> *</span>}
        </label>
      )}
      {children}
      {error && <div className="u-field-error" role="alert">{error}</div>}
      {hint && <div className="u-text3-xs">{hint}</div>}
    </div>
  )
}

export function PortalInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={props.className ? `portal-campo ${props.className}` : 'portal-campo'}
      onFocus={e => { e.target.style.borderColor = 'var(--accent-border-strong, color-mix(in srgb, var(--accent) 50%, transparent))'; e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)' }}
      onBlur={e => { e.target.style.borderColor = 'var(--surface-4)'; e.target.style.boxShadow = 'none' }}
    />
  )
}

/** Desplegable del portal: el `Select` del kit (suelto) con la clase `portal-campo`. Conserva la API de
 *  atributos de `<select>`; las opciones van como hijos (la opción vacía, si la hay, también). */
export function PortalSelect({ className, children, value, onChange, id, name, disabled, required, autoFocus, title, onBlur, onKeyDown,
  'aria-label': ariaLabel, 'aria-describedby': ariaDescribedBy }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Select suelto placeholder={false} className={className ? `portal-campo ${className}` : 'portal-campo'}
      value={value as string | number | undefined} onChange={onChange} id={id} name={name} disabled={disabled} required={required}
      autoFocus={autoFocus} title={title} onBlur={onBlur} onKeyDown={onKeyDown} aria-label={ariaLabel} aria-describedby={ariaDescribedBy}>
      {children}
    </Select>
  )
}

export function PortalTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea {...props} className={props.className ? `portal-campo portal-campo--vertical ${props.className}` : 'portal-campo portal-campo--vertical'} />
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
  const traducir = useLang()
  if (!open) return null
  return (
    <div role="presentation" onMouseDown={onClose} className="portalui-sx5">
      <div className="portui-box-32 portalui-sx6 portal-ui-e29" role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()} style={{ '--portal-ui-max-width': px(width) } as CSSProperties}>
        <div className="portui-row-18">
          <div>
            <h2 className="portui-box-22">{title}</h2>
            {subtitle && <p className="portui-box-23">{subtitle}</p>}
          </div>
          <Pulsable onClick={onClose} aria-label={traducir('common.close')} className="portui-row-19"><X size={14} /></Pulsable>
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
    <div className="portui-row-28 portalui-sx7 portal-ui-e30" style={{ '--portal-ui-background': c.bg, '--portal-ui-border': `1px solid ${c.bd}` } as CSSProperties}>
      {icon && <div className="portui-row-29 portal-ui-e16" style={{ '--portal-ui-color': c.fg } as CSSProperties}>{icon}</div>}
      <div className="u-flex1-min0">
        <div className="portui-txt-10 portal-ui-e16" style={{ '--portal-ui-color': c.fg } as CSSProperties}>{title}</div>
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
  const traducir = useLang()
  const radius = size / 2 - stroke / 2
  const circ = 2 * Math.PI * radius
  const total = segments.reduce((s, x) => s + Math.max(0, x.value || 0), 0)
  let offset = 0
  return (
    <div className="portui-box-33 portal-ui-e31" style={{ '--portal-ui-width': px(size), '--portal-ui-height': px(size) } as CSSProperties}>
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
  const traducir = useLang()
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
            <span className="portui-txt-11 portal-ui-e16" style={{ '--portal-ui-color': it.color || 'var(--text-1)' } as CSSProperties}>{it.value}{it.suffix || ''}</span>
          </div>
          <div className="portui-box-24">
            <div className="portui-box-31 portal-ui-e28" style={{ '--portal-ui-width': `${((it.value || 0) / max) * 100}%`, '--portal-ui-background': it.color || 'var(--accent)' } as CSSProperties} />
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

