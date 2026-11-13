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
    <div style={{
      display: 'flex',
      minHeight: '100vh',
      background: 'var(--surface-0)',
      color: 'var(--text-1)',
      fontFamily: 'var(--font-sans, "Inter", system-ui, sans-serif)',
    }}>
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside
        className={mobileOpen ? 'portal-sidebar portal-sidebar--open' : 'portal-sidebar'}
        style={{
          width: collapsed ? 68 : 240,
          background: 'var(--surface-1)',
          borderRight: '1px solid var(--surface-4)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          transition: 'width 0.18s ease',
          position: 'sticky',
          top: 0,
          height: '100vh',
          zIndex: 5,
        }}
      >
        {/* Brand */}
        <div style={{ padding: collapsed ? '16px 12px' : '16px 18px', borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 10 }}>
          {branding?.logo_url ? (
            <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} loading="lazy" decoding="async" style={{ width: 32, height: 32, borderRadius: 8, objectFit: 'cover', border: '1px solid var(--surface-4)', flexShrink: 0 }} />
          ) : (
            <div style={{
              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
              background: `linear-gradient(135deg, ${branding?.primary_color || 'var(--accent)'}, var(--purple, #7c3aed))`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 'var(--text-lg)', fontWeight: 800, color: 'var(--on-accent-light)',
            }}>◈</div>
          )}
          {!collapsed && (
            <div className="u-flex1-min0">
              <div style={{ fontSize: 'var(--text-md)', fontWeight: 800, color: 'var(--text-1)', lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {branding?.brand_name || tr('portal', 'Portal cliente')}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginTop: 2 }}>
                {client?.organization_name || client?.company || ''}
              </div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? 'Expandir menú' : 'Colapsar menú'}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--text-3)', padding: 4, flexShrink: 0,
              display: collapsed ? 'none' : 'inline-flex',
            }}
          ><X size={14} /></button>
        </div>

        {/* Filter */}
        {!collapsed && (
          <div style={{ padding: '12px 14px 6px' }}>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
              <input
                value={filter}
                onChange={e => setFilter(e.target.value)}
                placeholder="Buscar..."
                aria-label={traducir('portalui.filtrar_menu')}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                  borderRadius: 'var(--radius-md, 8px)',
                  padding: '7px 10px 7px 28px',
                  color: 'var(--text-1)', fontSize: 'var(--text-sm)',
                  fontFamily: 'inherit', outline: 'none',
                }}
              />
            </div>
          </div>
        )}

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 10px 12px', overflowY: 'auto' }}>
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
                  <div style={{
                    fontSize: 'var(--text-2xs, 10px)', fontWeight: 700, color: 'var(--text-3)',
                    textTransform: 'uppercase', letterSpacing: '0.09em',
                    padding: '6px 10px',
                  }}>
                    {tr(group.labelKey, group.label)}
                  </div>
                )}
                {items.map(it => {
                  const Icon = it.icon
                  const active = section === it.id
                  const badge = badges?.[it.id]
                  return (
                    <button
                      key={it.id}
                      onClick={() => { onSection(it.id); setMobileOpen(false) }}
                      title={collapsed ? tr(it.labelKey, it.fallback) : undefined}
                      style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center',
                        gap: 10,
                        padding: collapsed ? '9px 10px' : '8px 10px',
                        margin: '1px 0',
                        borderRadius: 'var(--radius-md, 8px)',
                        border: '1px solid transparent',
                        background: active ? 'var(--accent-muted)' : 'transparent',
                        color: active ? 'var(--accent)' : 'var(--text-2)',
                        fontSize: 'var(--text-sm)',
                        fontWeight: active ? 700 : 500,
                        cursor: 'pointer',
                        fontFamily: 'inherit',
                        textAlign: 'left',
                        position: 'relative',
                        transition: 'background 0.12s, color 0.12s',
                        justifyContent: collapsed ? 'center' : 'flex-start',
                      }}
                      onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--text-1)' } }}
                      onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-2)' } }}
                    >
                      <Icon size={16} aria-hidden="true" style={{ flexShrink: 0 }} />
                      {!collapsed && <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tr(it.labelKey, it.fallback)}</span>}
                      {!collapsed && badge != null && badge > 0 && (
                        <span style={{
                          fontSize: 'var(--text-2xs, 10px)', fontWeight: 700,
                          background: 'var(--danger-bg, rgba(239,68,68,0.15))',
                          color: 'var(--danger, #ef4444)',
                          borderRadius: 'var(--radius-full)', padding: '1px 7px', minWidth: 20, textAlign: 'center',
                        }}>{badge > 99 ? '99+' : badge}</span>
                      )}
                      {collapsed && badge != null && badge > 0 && (
                        <span style={{
                          position: 'absolute', top: 4, right: 4,
                          width: 7, height: 7, borderRadius: '50%',
                          background: 'var(--danger, #ef4444)',
                        }} />
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </nav>

        {/* User block */}
        <div style={{ padding: '12px 12px', borderTop: '1px solid var(--surface-4)' }}>
          {!collapsed ? (
            <>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', marginBottom: 4 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                  background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 'var(--text-sm)', fontWeight: 800, color: 'var(--on-accent-light)',
                }}>{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
                <div style={{ overflow: 'hidden', flex: 1 }}>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{client?.full_name || client?.email}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{projectsCount} proyecto{projectsCount === 1 ? '' : 's'}</div>
                </div>
              </div>
              <button
                onClick={logout}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  background: 'transparent', border: '1px solid var(--surface-4)',
                  borderRadius: 'var(--radius-md, 8px)',
                  padding: '7px 10px',
                  color: 'var(--text-2)', fontSize: 'var(--text-sm)', fontWeight: 600,
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
              ><LogOut size={13} /> {tr('logout', 'Cerrar sesión')}</button>
            </>
          ) : (
            <button onClick={() => setCollapsed(false)}
              aria-label={traducir('portalui.expandir_menu')}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'transparent', border: '1px solid var(--surface-4)',
                borderRadius: 'var(--radius-md, 8px)', padding: '8px',
                color: 'var(--text-2)', cursor: 'pointer',
              }}><Menu size={14} /></button>
          )}
        </div>
      </aside>

      {/* ── Main column ─────────────────────────────────────────────────── */}
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Topbar */}
        <header style={{
          height: 56,
          display: 'flex', alignItems: 'center', gap: 16,
          padding: '0 24px',
          background: 'var(--surface-1)',
          borderBottom: '1px solid var(--surface-4)',
          position: 'sticky', top: 0, zIndex: 4,
        }}>
          <button onClick={() => setMobileOpen(true)}
            className="portal-mobile-toggle"
            aria-label={traducir('portalui.abrir_menu')}
            style={{
              display: 'none',
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--text-2)', padding: 4,
            }}><Menu size={18} /></button>

          <div className="u-flex1-min0">
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              {tr(sectionCfg.groupKey, sectionCfg.group)}
            </div>
            <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {tr(sectionCfg.labelKey, sectionCfg.fallback)}
            </div>
          </div>

          <div className="u-row-center-10">
            <button
              onClick={() => setQuickOpen(true)}
              title={traducir('portalui.crear_nuevo')}
              aria-label={traducir('portalui.crear_nuevo_2')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 30, height: 30,
                background: 'var(--accent)', border: 'none',
                borderRadius: 8, color: 'var(--on-accent-light)', cursor: 'pointer',
                fontWeight: 700, lineHeight: 1,
              }}
              onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              <Plus size={16} />
            </button>
            <button
              onClick={() => onSection('support')}
              title="Notificaciones / pendientes"
              aria-label="Notificaciones"
              style={{
                position: 'relative',
                background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                borderRadius: 'var(--radius-md, 8px)',
                width: 34, height: 34,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--text-2)', cursor: 'pointer',
              }}
            >
              <Bell size={15} />
              {(badges?.support || 0) + (badges?.messages || 0) > 0 && (
                <span style={{
                  position: 'absolute', top: -4, right: -4,
                  background: 'var(--danger, #ef4444)', color: 'var(--on-accent-light)',
                  borderRadius: 'var(--radius-full)', fontSize: 'var(--text-3xs, 9px)', fontWeight: 800,
                  minWidth: 16, height: 16, padding: '0 4px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{Math.min((badges?.support || 0) + (badges?.messages || 0), 99)}</span>
              )}
            </button>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 'var(--text-sm)', fontWeight: 800, color: 'var(--on-accent-light)',
            }}>{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
          </div>
        </header>

        {/* Content */}
        <div className="page-content" style={{ flex: 1, padding: '28px 32px 48px', overflowY: 'auto' }}>
          {children}
        </div>
      </main>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div role="presentation" onClick={() => setMobileOpen(false)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 4,
        }} />
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
    <div style={{
      marginBottom: 24,
      paddingBottom: 18,
      borderBottom: '1px solid var(--surface-4)',
    }}>
      {breadcrumb && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          {breadcrumb.map((c, i) => (
            <span key={i} className="u-row-center-6">
              {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: 'var(--text-xs)' }}>›</span>}
              {c.onClick ? (
                <button type="button" onClick={c.onClick} style={{
                  fontSize: 'var(--text-xs)', fontWeight: 600,
                  color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                  background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit',
                }}>{c.label}</button>
              ) : (
                <span style={{
                  fontSize: 'var(--text-xs)', fontWeight: 600,
                  color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>{c.label}</span>
              )}
            </span>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div className="u-min0">
          <div className="u-row-center-12">
            {Icon && (
              <div style={{
                width: 38, height: 38, borderRadius: 'var(--radius-md)',
                background: 'var(--accent-muted)',
                border: '1px solid var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--accent)', flexShrink: 0,
              }}><Icon size={18} /></div>
            )}
            <h1 style={{
              fontSize: 'var(--text-xl-em)', fontWeight: 700,
              color: 'var(--text-1)', letterSpacing: '-0.01em',
              lineHeight: 1.2, margin: 0,
            }}>{title}</h1>
          </div>
          {subtitle && (
            <p style={{
              fontSize: 'var(--text-base)',
              color: 'var(--text-2)',
              margin: '8px 0 0',
              fontWeight: 400,
              paddingLeft: Icon ? 50 : 0,
            }}>{subtitle}</p>
          )}
          {meta && meta.length > 0 && (
            <div style={{ display: 'flex', gap: 14, marginTop: 10, flexWrap: 'wrap', paddingLeft: Icon ? 50 : 0 }}>
              {meta.map((m, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                  {m.icon && <span style={{ opacity: 0.7, display: 'inline-flex' }}>{m.icon}</span>}
                  <span style={{ color: m.color || 'var(--text-2)' }}>{m.value}</span>
                  {m.label && <span className="u-text3">{m.label}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        {actions && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0, flexWrap: 'wrap' }}>
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
  style?: CSSProperties
  accent?: boolean
  padding?: CSSProperties['padding']
  onClick?: (e: ReactMouseEvent<HTMLDivElement> | ReactKeyboardEvent<HTMLDivElement>) => void
}

export function PortalCard({ children, style = {}, accent, padding = 20, onClick }: PortalCardProps) {
  const base: CSSProperties = {
    background: 'var(--surface-2)',
    border: `1px solid ${accent ? 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))' : 'var(--surface-4)'}`,
    borderRadius: 'var(--radius-lg, 12px)',
    padding,
    boxShadow: accent ? '0 0 0 3px color-mix(in srgb, var(--accent) 6%, transparent)' : 'none',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    ...style,
  }
  if (onClick) {
    return (
      <div
        role="button" tabIndex={0}
        onClick={onClick}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(e) } }}
        style={{ ...base, cursor: 'pointer' }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-border-strong, var(--accent-border-strong))' }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = accent ? 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))' : 'var(--surface-4)' }}
      >{children}</div>
    )
  }
  return <div style={base}>{children}</div>
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
    <PortalCard padding={big ? 22 : 18} style={{ minHeight: big ? 132 : 116, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        {Icon && (
          <div style={{
            width: 30, height: 30, borderRadius: 8,
            background: `${toneColor === 'var(--text-1)' ? 'var(--accent-muted)' : alpha(toneColor, '18')}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: toneColor === 'var(--text-1)' ? 'var(--accent)' : toneColor,
          }}><Icon size={15} /></div>
        )}
        {trend !== undefined && trend !== null && (
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: trendColor }}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: big ? 'var(--text-3xl-em, 28px)' : 'var(--text-2xl-em)',
        fontWeight: 700, color: toneColor,
        letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 6,
      }}>{value}</div>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', fontWeight: 500 }}>{label}</div>
      {sub && <div className="u-hint">{sub}</div>}
      {footer && <div style={{ marginTop: 'auto', paddingTop: 10 }}>{footer}</div>}
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 12 }}>
        <div>
          <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)' }}>{title}</div>
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
    <div ref={listRef} role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown} style={{
      display: 'flex', gap: 4, borderBottom: '1px solid var(--surface-4)', marginBottom: 20, flexWrap: 'wrap',
    }}>
      {tabs.map(tab => {
        const active = value === tab.id
        return (
          <button
            key={tab.id} role="tab" aria-selected={active}
            data-tab-id={tab.id} tabIndex={tab.id === focusId ? 0 : -1}
            onClick={() => onChange(tab.id)}
            style={{
              background: 'transparent', border: 'none', borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
              padding: '9px 14px', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 'var(--text-sm)', fontWeight: active ? 700 : 500,
              color: active ? 'var(--accent)' : 'var(--text-2)',
              display: 'inline-flex', alignItems: 'center', gap: 8,
              transition: 'color 0.15s, border-color 0.15s',
            }}
          >
            {tab.icon}
            {tab.label}
            {tab.badge != null && tab.badge > 0 && (
              <span style={{
                background: active ? 'var(--accent-muted)' : 'var(--surface-3)',
                color: active ? 'var(--accent)' : 'var(--text-2)',
                fontSize: 'var(--text-2xs, 10px)', fontWeight: 700, padding: '1px 7px', borderRadius: 'var(--radius-full)',
              }}>{tab.badge}</span>
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
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '48px 24px', textAlign: 'center',
      background: 'var(--surface-2)', border: '1px dashed var(--surface-4)', borderRadius: 'var(--radius-lg, 12px)',
    }}>
      {Icon && (
        <div style={{
          width: 48, height: 48, borderRadius: 12, background: 'var(--accent-muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--accent)', marginBottom: 14,
        }}><Icon size={22} /></div>
      )}
      <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>{title}</div>
      {description && (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', maxWidth: 460, lineHeight: 1.5 }}>
          {description}
        </div>
      )}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
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
      <div style={{ height, background: 'var(--surface-4)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: c, borderRadius: 'var(--radius-full)', transition: 'width 0.6s' }} />
      </div>
      {showLabel && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4, textAlign: 'right' }}>
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
        <span style={{
          display: 'inline-block', width: 12, height: 12,
          border: '2px solid currentColor', borderTopColor: 'transparent',
          borderRadius: '50%', animation: 'portalspin 0.7s linear infinite',
        }} />
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {label && (
        <label style={{
          fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)',
          textTransform: 'uppercase', letterSpacing: '0.07em',
        }}>
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
  if (!open) return null
  return (
    <div role="presentation" onMouseDown={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(8,12,20,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: '40px 24px', zIndex: 'var(--z-modal)', overflowY: 'auto',
    }}>
      <div role="dialog" aria-modal="true" onMouseDown={e => e.stopPropagation()} style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 'var(--radius-xl, 16px)',
        padding: 24, width: '100%', maxWidth: width,
        boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, gap: 16 }}>
          <div>
            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>{title}</h2>
            {subtitle && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: '4px 0 0' }}>{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label="Cerrar" style={{
            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 'var(--radius-sm)', color: 'var(--text-2)', cursor: 'pointer',
            width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}><X size={14} /></button>
        </div>
        {children}
        {footer && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 22, paddingTop: 16, borderTop: '1px solid var(--surface-4)' }}>
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
    <div style={{
      background: c.bg, border: `1px solid ${c.bd}`,
      borderRadius: 'var(--radius-lg, 12px)', padding: '12px 16px',
      display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
    }}>
      {icon && <div style={{ color: c.fg, flexShrink: 0, display: 'inline-flex' }}>{icon}</div>}
      <div className="u-flex1-min0">
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: c.fg }}>{title}</div>
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
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
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
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        {centerTop && <div style={{ fontSize: 'var(--text-xl-em)', fontWeight: 800, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{centerTop}</div>}
        {centerBottom && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{centerBottom}</div>}
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
    <svg width={width} height={height} role="img" aria-label="tendencia">
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
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', marginBottom: 4 }}>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{it.label}</span>
            <span style={{ color: it.color || 'var(--text-1)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{it.value}{it.suffix || ''}</span>
          </div>
          <div style={{ height: 5, borderRadius: 'var(--radius-full)', background: 'var(--surface-4)', overflow: 'hidden' }}>
            <div style={{ width: `${((it.value || 0) / max) * 100}%`, height: '100%', borderRadius: 'var(--radius-full)', background: it.color || 'var(--accent)', transition: 'width 0.6s' }} />
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

