// Marco del portal de cliente (navegacion lateral, cabecera y avisos). 23-11-2026: troceado de PortalUI sin cambio de comportamiento.
import { useEffect, useState } from 'react'
import type { CSSProperties, ComponentType, ReactNode } from 'react'
import { LayoutDashboard, FlaskConical, Lightbulb, Map, BookOpen, FileText, Receipt, Headphones, MessageSquare, Settings, LogOut, Bell, Menu, Plus, Sparkles, PanelLeftClose } from 'lucide-react'
import { useClientAuth, useLang } from './portalClientContext'
import PortalQuickCreateMenu from './PortalQuickCreateMenu'
import CampanaDelPortal from './CampanaDelPortal'
import { Buscador, Pulsable } from '../../components/ui'

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
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('portal_sidebar_collapsed') === '1' } catch { /* accesorio: sin almacenamiento (23-11-2026) */ return false } })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [quickOpen, setQuickOpen] = useState(false)

  useEffect(() => { try { localStorage.setItem('portal_sidebar_collapsed', collapsed ? '1' : '0') } catch { /* accesorio: sin almacenamiento, no se recuerda el menú plegado */ } }, [collapsed])

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
            <div className="portui-row-23 portal-ui-e5" style={{ '--portal-ui-background': `linear-gradient(135deg, ${branding?.primary_color || 'var(--accent)'}, var(--purple))` } as CSSProperties}>◈</div>
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
            <Buscador className="portui-box-4" value={filter} onChange={setFilter} placeholder={traducir('portalui.buscar')} aria-label={traducir('portalui.filtrar_menu')} />
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
