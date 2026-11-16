/**
 * PortalSupportDesk — service desk del cliente con el lenguaje del backoffice.
 * Tickets, KB y comunicados.
 */
import { type CSSProperties, useEffect, useMemo, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Headphones, Plus, Search, ArrowLeft, Megaphone, Bug, BookOpen,
  AlertTriangle, Wrench, CheckCircle2, Star, Send,
  ClipboardList, HelpCircle, GitBranch, Clock, Bot,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { CLIENT_API, useLang } from './portalClientContext'
import PortalKbArticulo from './PortalKbArticulo'
import PortalAsistenteYChat from './PortalAsistenteYChat'
import {
  PortalPageHeader, PortalCard,
  PortalEmpty, PortalBadge,
  PortalButton, PortalModal,
  PortalField, PortalInput,
  PortalSelect, PortalTextarea,
  PortalBanner,
} from './PortalUI'
import { useAppLang } from '../../i18n/AppLangContext'
import { useTabListKeys } from '../../components/ui/Tabs'
import { SLOW_INPUT_DEBOUNCE_MS } from '../../constants/timings'
import { DYNAMIC_FORM_OPTIONS_LIMIT } from '../../constants/pagination'
import './PortalSupportDesk.css'


const PRIORITY_TONE: Record<string, string> = {
  p1_critical: 'danger',
  p2_high:     'orange',
  p3_medium:   'warning',
  p4_low:      'default',
}
const PRIORITY_COLORS: Record<string, string> = {
  p1_critical: 'var(--danger)',
  p2_high:     'var(--orange)',
  p3_medium:   'var(--warning)',
  p4_low:      'var(--text-2)',
}
const STATUS_TONE: Record<string, string> = {
  new: 'default', assigned: 'accent', in_progress: 'accent',
  pending_client: 'warning', pending_third: 'warning',
  resolved: 'success', closed: 'default', cancelled: 'default',
}
const TYPE_ICON: Record<string, typeof Bug> = {
  incident: Bug, service_request: ClipboardList, change: GitBranch, question: HelpCircle,
}

interface Ticket {
  id: string
  number?: string
  title?: string
  ticket_type?: string
  status?: string
  status_label?: string
  approval_status?: string | null
  priority?: string
  priority_label?: string
  created_at?: string
  assigned_to_name?: string
  csat_requested_at?: string
  csat_score?: number
}
interface TicketComment {
  id: string
  author_type?: string
  author_name?: string
  created_at?: string
  body?: string
  is_public?: boolean
}
interface TicketHistory {
  changed_at?: string
  changed_by?: string
  field?: string
  old_value?: unknown
  new_value?: unknown
}
interface TicketDetail extends Ticket {
  client_name?: string
  service_item_name?: string
  ci_name?: string
  description?: string
  resolution?: string
  sla_resolution_due?: string
  dynamic_fields?: Record<string, unknown>
  comments?: TicketComment[]
  history?: TicketHistory[]
}
interface CatalogService { id: string; name?: string; sla_resolution_hours?: number }
interface CatalogGroup { id: string; icon?: string; name?: string; services: CatalogService[] }
interface KbArticle { id: string; title?: string; summary?: string; tags?: string; view_count?: number; helpful_count?: number }
interface Announcement {
  id: string
  type?: string
  title?: string
  body?: string
  show_to_clients?: boolean
  starts_at?: string
  ends_at?: string
}
interface ContextItem { id?: string; name?: string; code?: string; [k: string]: unknown }
interface ContextOptions { clients: ContextItem[]; services: ContextItem[]; cis: ContextItem[] }
interface DynamicField {
  id: string
  label?: string
  type?: string
  required?: boolean
  options?: string[]
  visible_when?: { field?: string; equals?: unknown; in?: unknown[] }
  data_source?: string
  data_attribute?: string
}
interface RoutingHint { when?: { field?: string; equals?: unknown; in?: unknown[] }; set?: Record<string, unknown> }
interface DynamicRules { fields?: DynamicField[]; routing_hints?: RoutingHint[] }

export function PortalSupportDesk() {
  const { t: traducir } = useAppLang()
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  // `?ticket=<id>` abre ese ticket: es a donde lleva el enlace de los correos.
  const [selectedId, setSelectedId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get('ticket'))
  const [showCreate, setShowCreate] = useState(false)
  const [searchKB, setSearchKB] = useState('')
  // Revisión 2026-11: el artículo se listaba y no se podía abrir.
  const [articuloAbierto, setArticuloAbierto] = useState<string | null>(null)
  const [tab, setTab] = useState('tickets')
  const [newComment, setNewComment] = useState('')
  const [createForm, setCreateForm] = useState({
    title: '', description: '', ticket_type: 'incident',
    urgency: 'medium', impact: 'user', service_item_id: '', ci_id: '',
  })

  const { data: tickets = [] } = useQuery<Ticket[]>({
    queryKey: ['portal-sd-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data as Ticket[]),
  })
  const { data: catalog = [] } = useQuery<CatalogGroup[]>({
    queryKey: ['portal-sd-catalog'],
    queryFn: () => CLIENT_API.get('/sd/catalog?public_only=true').then(r => r.data as CatalogGroup[]),
  })
  const { data: kbArticles = [] } = useQuery<KbArticle[]>({
    queryKey: ['portal-kb', searchKB],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined } }).then(r => r.data as KbArticle[]),
  })
  const { data: announcements = [] } = useQuery<Announcement[]>({
    queryKey: ['portal-sd-anns'],
    queryFn: () => CLIENT_API.get('/sd/announcements').then(r => r.data as Announcement[]),
  })
  const { data: ticketDetail } = useQuery<TicketDetail>({
    queryKey: ['portal-sd-ticket', selectedId],
    queryFn: () => CLIENT_API.get(`/sd/tickets/client/${selectedId}`).then(r => r.data as TicketDetail),
    enabled: !!selectedId,
  })
  const { data: dynamicRules } = useQuery<DynamicRules>({
    queryKey: ['portal-sd-dynamic-forms'],
    queryFn: () => CLIENT_API.get('/sd/dynamic-forms/public').then(r => r.data as DynamicRules),
  })
  const { data: contextOptions = { clients: [], services: [], cis: [] } } = useQuery<ContextOptions>({
    queryKey: ['portal-sd-dynamic-forms-context', createForm.service_item_id],
    queryFn: () => CLIENT_API.get('/sd/dynamic-forms/public/context-options', {
      params: { service_item_id: createForm.service_item_id || undefined, limit: DYNAMIC_FORM_OPTIONS_LIMIT },
    }).then(r => r.data as ContextOptions),
  })

  const [dynamicValues, setDynamicValues] = useState<Record<string, string>>({})

  const { mutate: createTicket, isPending: creatingTicket } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post('/sd/tickets/client', d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-sd-tickets'] })
      setShowCreate(false)
      setCreateForm({ title: '', description: '', ticket_type: 'incident', urgency: 'medium', impact: 'user', service_item_id: '', ci_id: '' })
      setDynamicValues({})
      toast.success(traducir('portalsupportdesk.ticket_abierto'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: addComment } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post(`/sd/tickets/${selectedId}/comments/client`, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-sd-ticket', selectedId] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: submitCSAT } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post(`/sd/tickets/${selectedId}/csat`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-sd-ticket', selectedId] }); toast.success(traducir('portalsupportdesk.gracias_por_tu_valoracion')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const pendingClient = tickets.filter(t => t.status === 'pending_client').length
  const openTickets = tickets.filter(t => !['closed', 'cancelled', 'resolved'].includes(t.status || '')).length

  const visibleDynamicFields = useMemo(() => {
    const fields = dynamicRules?.fields || []
    const source: Record<string, unknown> = { ...createForm, ...dynamicValues }
    return fields.filter((f: DynamicField) => {
      const cond = f?.visible_when
      if (!cond || !cond.field) return true
      const current = source[cond.field]
      if (Object.prototype.hasOwnProperty.call(cond, 'equals')) return current === cond.equals
      if (Array.isArray(cond.in)) return cond.in.includes(current)
      return true
    })
  }, [dynamicRules, createForm, dynamicValues])

  const routingHint = useMemo(() => {
    const hints = dynamicRules?.routing_hints || []
    const cf: Record<string, unknown> = createForm
    for (const h of hints) {
      const w = h?.when || {}
      if (!w.field) continue
      const current = cf[w.field]
      if ((Object.prototype.hasOwnProperty.call(w, 'equals') && current === w.equals) ||
          (Array.isArray(w.in) && w.in.includes(current))) {
        return h?.set || null
      }
    }
    return null
  }, [dynamicRules, createForm])

  const upcomingEvents = useMemo(() => {
    return (announcements || [])
      .filter((a: Announcement) => a.show_to_clients && a.starts_at)
      .sort((a: Announcement, b: Announcement) => String(a.starts_at || '').localeCompare(String(b.starts_at || '')))
      .slice(0, 5)
  }, [announcements])

  const contextSuggestionsForField = (f: DynamicField): string[] => {
    const source = f?.data_source || (f?.type || '').replace('context_', '')
    if (source === 'ci') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.cis || []).map((ci: ContextItem) => String(ci[attr] || ci.name || ci.code || ''))
    }
    if (source === 'service') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.services || []).map((s: ContextItem) => String(s[attr] || s.name || ''))
    }
    if (source === 'client') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.clients || []).map((c: ContextItem) => String(c[attr] || c.name || ''))
    }
    return []
  }

  const tabs = [
    { id: 'tickets', label: `Tickets (${tickets.length})`, icon: <Headphones size={13} /> },
    { id: 'kb',      label: 'Base de conocimiento',        icon: <BookOpen size={13} /> },
    { id: 'announcements', label: `Comunicados (${announcements.length})`, icon: <Megaphone size={13} /> },
    // Mejoras de mercado 16-11-2026: asistente que actúa y chat en vivo con traspaso a agente.
    { id: 'assistant', label: _t('sdm_titulo'), icon: <Bot size={13} /> },
  ]
  // Antes del return de detalle: un hook no puede quedar detrás de un return.
  const teclas = useTabListKeys(tabs.map(x => x.id), tab, setTab)

  // ── Detail view ────────────────────────────────────────────────────────────
  if (tab === 'tickets' && selectedId) {
    return (
      <div>
        <PortalPageHeader
          title={ticketDetail?.title || 'Cargando...'}
          icon={Headphones}
          breadcrumb={[
            { label: 'Service Desk', onClick: () => setSelectedId(null) },
            { label: ticketDetail?.number || '...' },
          ]}
          meta={ticketDetail ? [
            { value: ticketDetail.number, color: 'var(--text-3)' },
            ticketDetail.assigned_to_name && { value: ticketDetail.assigned_to_name, label: 'agente' },
            ticketDetail.sla_resolution_due && { value: ticketDetail.sla_resolution_due, label: 'SLA resolución' },
          ].filter(Boolean) : []}
          actions={<PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={() => setSelectedId(null)}>{traducir('chat.back')}</PortalButton>}
        />

        {!ticketDetail ? (
          <div className="posude-box-1">{traducir('portalsupportdesk.cargando_ticket')}</div>
        ) : (
          <>
            <div className="posude-row-1">
              <PortalBadge tone={ticketDetail.approval_status === 'pending' ? 'warning' : (STATUS_TONE[ticketDetail.status || ""] || 'default')}>{ticketDetail.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : (ticketDetail.status_label || ticketDetail.status)}</PortalBadge>
              <PortalBadge tone={PRIORITY_TONE[ticketDetail.priority || ""] || 'default'}>{ticketDetail.priority_label}</PortalBadge>
            </div>

            <PortalCard className="portalsu-sx1">
              <div className="posude-box-2">{traducir('portalsupportdesk.objetos_vinculados')}</div>
              <div className="posude-grid-1">
                <div className="posude-box-3">
                  <div className="posude-txt-1">{traducir('chat.client')}</div>
                  <div className="posude-box-4">{ticketDetail.client_name || '—'}</div>
                </div>
                <div className="posude-box-3">
                  <div className="posude-txt-1">{traducir('cmdb.type_service')}</div>
                  <div className="posude-box-4">{ticketDetail.service_item_name || '—'}</div>
                </div>
                <div className="posude-box-5">
                  <div className="posude-txt-1">{traducir('portalsupportdesk.ci_vinculado')}</div>
                  <div className="posude-box-4">{ticketDetail.ci_name || '—'}</div>
                </div>
              </div>
            </PortalCard>

              <PortalCard className="portalsu-sx1">
              <div className="posude-box-2">{traducir('portalsupportdesk.descripcion_original')}</div>
              <p className="posude-box-6">{ticketDetail.description}</p>
            </PortalCard>

            {ticketDetail.dynamic_fields && Object.keys(ticketDetail.dynamic_fields).length > 0 && (
              <PortalCard className="portalsu-sx1">
                <div className="posude-box-2">
                  {traducir('portalsupportdesk.campos_adicionales')}
                </div>
                <div className="posude-grid-1">
                  {Object.entries(ticketDetail.dynamic_fields).map(([k, v]) => (
                    <div key={k} className="posude-box-3">
                      <div className="posude-txt-1">{k}</div>
                      <div className="posude-box-7">{String(v ?? '—')}</div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            {ticketDetail.resolution && (
              <PortalCard className="portalsu-sx2">
                <div className="posude-row-2">
                  <CheckCircle2 size={13} /> {traducir('portalsupportdesk.resolucion_del_equipo')}
                </div>
                <p className="posude-box-8">{ticketDetail.resolution}</p>
              </PortalCard>
            )}

            {ticketDetail.csat_requested_at && !ticketDetail.csat_score && (
              <PortalCard className="portalsu-sx2">
                <div className="posude-row-3">
                  <Star size={14} className="portalsu-sx3" /> {traducir('portalsupportdesk.como_valorarias_la_atencion_recibida')}
                </div>
                <div className="u-row-8">
                  {[1, 2, 3, 4, 5].map(n => (
                    <button key={n} onClick={() => submitCSAT({ score: n })} className="posude-box-9">{'⭐'.repeat(n)}</button>
                  ))}
                </div>
              </PortalCard>
            )}
            {ticketDetail.csat_score && (
              <PortalBanner tone="success" icon={<Star size={16} />} title={`Valoración: ${ticketDetail.csat_score}/5`} body="Gracias por tu feedback" />
            )}

            {Array.isArray(ticketDetail.history) && ticketDetail.history.length > 0 && (
              <PortalCard className="portalsu-sx1">
                <div className="posude-box-2">{traducir('portalsupportdesk.actividad_del_ticket')}</div>
                <div className="u-stack-8">
                  {ticketDetail.history.slice(-8).reverse().map((h, idx) => (
                    <div key={`${h.changed_at}-${idx}`} className="posude-box-3">
                      <div className="u-text3-2xs">{h.changed_at} · {h.changed_by || 'Sistema'}</div>
                      <div className="posude-box-4">
                        {h.field}: {String(h.old_value ?? '—')} → {String(h.new_value ?? '—')}
                      </div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            {upcomingEvents.length > 0 && (
              <PortalCard className="portalsu-sx1">
                <div className="posude-box-2">{traducir('portalsupportdesk.calendario_de_eventos')}</div>
                <div className="u-stack-8">
                  {upcomingEvents.map((ev) => (
                    <div key={ev.id} className="posude-box-3">
                      <div className="posude-txt-2">{ev.title}</div>
                      <div className="u-text3-xs-mt2">{ev.starts_at}{ev.ends_at ? ` → ${ev.ends_at}` : ''}</div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            <div className="u-mb-16">
              <div className="posude-box-10">{traducir('portalsupportdesk.conversacion')}</div>
              {ticketDetail.comments?.filter(c => c.is_public).map(c => (
                <div key={c.id} className="posude-row-4">
                  <div className={`posude-row-13 ${c.author_type === 'agent' ? 'portal-support-desk-m1' : 'portal-support-desk-m2'}`}>{c.author_name?.split(' ').map(w => w[0]).join('').slice(0, 2)}</div>
                  <div className="u-flex1-min0">
                    <div className="posude-row-5">
                      <span className="u-sm-700">{c.author_name}</span>
                      <span className="u-text3-xs">{c.created_at}</span>
                      {c.author_type === 'agent' && <PortalBadge tone="accent">{traducir('agent_dashboard.agent')}</PortalBadge>}
                    </div>
                    <div className={`posude-box-18 portalsu-sx4 portal-support-desk-e3 ${c.author_type === 'agent' ? 'portal-support-desk-m4' : 'portal-support-desk-m5'}`} style={{ '--portal-support-desk-border': `1px solid ${c.author_type === 'agent' ? 'var(--surface-4)' : 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))'}` } as CSSProperties}>{c.body}</div>
                  </div>
                </div>
              ))}
            </div>

            {!['closed', 'cancelled'].includes(ticketDetail.status || '') && (
              <PortalCard>
                <PortalField label={traducir('portalsupportdesk.tu_respuesta')}>
                  <PortalTextarea rows={4} value={newComment} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setNewComment(e.target.value)} placeholder={traducir('portalsupportdesk.escribe_tu_respuesta')} />
                </PortalField>
                <div className="posude-row-6">
                  <PortalButton icon={<Send size={13} />} disabled={!newComment.trim()}
                    onClick={() => { addComment({ body: newComment, is_public: true }); setNewComment('') }}>
                    {traducir('clientstabs.enviar_respuesta')}
                  </PortalButton>
                </div>
              </PortalCard>
            )}
          </>
        )}
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div>
      <PortalPageHeader
        title="Service Desk"
        subtitle={traducir('portalsupportdesk.tickets_de_soporte_base_de_conocimiento_y')}
        icon={Headphones}
        meta={[
          { value: openTickets, label: 'tickets abiertos', color: 'var(--accent)' },
          { value: pendingClient, label: 'esperan tu respuesta', color: pendingClient ? 'var(--warning)' : 'var(--text-3)' },
          { value: announcements.length, label: 'comunicados activos' },
        ]}
        actions={
          <PortalButton icon={<Plus size={14} />} onClick={() => { setDynamicValues({}); setShowCreate(true) }}>{traducir('portaldashboard.abrir_ticket')}</PortalButton>
        }
      />

      {announcements.filter(a => a.show_to_clients).map(a => (
        <PortalBanner key={a.id}
          tone={a.type === 'outage' ? 'danger' : a.type === 'maintenance' ? 'warning' : 'info'}
          icon={a.type === 'outage' ? <AlertTriangle size={18} /> : a.type === 'maintenance' ? <Wrench size={18} /> : <Megaphone size={18} />}
          title={a.title} body={a.body}
        />
      ))}

      {pendingClient > 0 && (
        <PortalBanner tone="warning" icon={<Clock size={18} />}
          title={`${pendingClient} ticket(s) esperan tu respuesta`}
          body="Pulsa el ticket para responder y desbloquear el avance del equipo."
        />
      )}

      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" aria-label="Service Desk" className="posude-row-7">
        {tabs.map(tb => (
          <button className={`posude-row-14 portal-support-desk-e6 ${tab === tb.id ? 'portal-support-desk-m7' : 'portal-support-desk-m8'}`} key={tb.id} type="button" role="tab" data-tab-id={tb.id}
            tabIndex={tb.id === teclas.focusId ? 0 : -1} aria-selected={tab === tb.id}
            onClick={() => setTab(tb.id)}
            style={{ '--portal-support-desk-border-bottom': `2px solid ${tab === tb.id ? 'var(--accent)' : 'transparent'}` } as CSSProperties}>{tb.icon} {tb.label}</button>
        ))}
      </div>

      {/* Tickets */}
      {tab === 'assistant' && <PortalAsistenteYChat />}
      {tab === 'tickets' && (
        tickets.length === 0 ? (
          <PortalEmpty icon={Headphones} title={traducir('portalsupportdesk.no_tienes_tickets')}
            description={traducir('portalsupportdesk.necesitas_ayuda_abre_un_ticket_y_el')}
            action={<PortalButton icon={<Plus size={14} />} onClick={() => { setDynamicValues({}); setShowCreate(true) }}>{traducir('portaldashboard.abrir_ticket')}</PortalButton>}
          />
        ) : (
          <div className="u-stack-10">
            {tickets.map(tk => {
              const TypeIcon = TYPE_ICON[tk.ticket_type || ""] || Headphones
              return (
                <PortalCard key={tk.id} onClick={() => setSelectedId(tk.id)}>
                  <div className="posude-row-8">
                    <div className="u-flex1-min0">
                      <div className="posude-row-9">
                        <span className="u-text3-mono-xs">{tk.number}</span>
                        <TypeIcon size={13} className="u-text2" />
                        <span className="u-sm-700">{tk.title}</span>
                      </div>
                      <div className="posude-row-10">
                        <span>{traducir('portalsupportdesk.creado')} {tk.created_at}</span>
                        {tk.assigned_to_name && <span>{traducir('portalsupportdesk.asignado')} {tk.assigned_to_name}</span>}
                      </div>
                    </div>
                    <div className="u-row-center-6">
                      <span className="posude-txt-4 portal-support-desk-e9" style={{ '--portal-support-desk-color': PRIORITY_COLORS[tk.priority || ""] || 'var(--text-2)' } as CSSProperties}>{tk.priority_label}</span>
                      <PortalBadge tone={tk.approval_status === 'pending' ? 'warning' : (STATUS_TONE[tk.status || ""] || 'default')}>{tk.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : (tk.status_label || tk.status)}</PortalBadge>
                    </div>
                  </div>
                  {tk.status === 'pending_client' && (
                    <div className="posude-row-17"><Clock size={12} /> {traducir('portalsupportdesk.esperan_tu_respuesta_clic_para_abrir')}</div>
                  )}
                  {tk.csat_requested_at && !tk.csat_score && (
                    <div className="posude-row-18"><Star size={12} /> {traducir('portalsupportdesk.valora_la_atencion_recibida')}</div>
                  )}
                </PortalCard>
              )
            })}
          </div>
        )
      )}

      {/* KB */}
      {tab === 'kb' && articuloAbierto && (
        <PortalKbArticulo id={articuloAbierto} onVolver={() => setArticuloAbierto(null)} migas={traducir('portalkb.migas_soporte')} />
      )}
      {tab === 'kb' && !articuloAbierto && (
        <>
          <div className="posude-box-11">
            <Search size={14} className="portalsu-sx5" />
            <PortalInput value={searchKB} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setSearchKB(e.target.value)} placeholder={traducir('portalsupportdesk.buscar_articulo')}
              className="portal-support-desk-e12" />
          </div>
          {kbArticles.length === 0 ? (
            <PortalEmpty icon={Search} title={searchKB ? `Sin resultados para "${searchKB}"` : 'Base de conocimiento vacía'} />
          ) : (
            <div className="u-stack-10">
              {kbArticles.map(a => (
                <PortalCard key={a.id} onClick={() => setArticuloAbierto(a.id as string)}>
                  <div className="posude-row-11">
                    <div className="u-sm-700">{a.title}</div>
                    <div className="u-text3-xs">👁 {a.view_count} · ✓ {a.helpful_count}</div>
                  </div>
                  {a.summary && <p className="posude-box-12">{a.summary}</p>}
                  {a.tags && <div className="u-text3-xs">🏷 {a.tags}</div>}
                </PortalCard>
              ))}
            </div>
          )}
        </>
      )}

      {/* Announcements */}
      {tab === 'announcements' && (
        announcements.length === 0 ? (
          <PortalEmpty icon={Megaphone} title={traducir('portalsupportdesk.sin_comunicados_activos')} />
        ) : (
          <div className="u-stack-10">
            {announcements.map(a => {
              const Icon = a.type === 'outage' ? AlertTriangle : a.type === 'maintenance' ? Wrench : a.type === 'resolved' ? CheckCircle2 : Megaphone
              const tone = a.type === 'outage' ? 'danger' : a.type === 'maintenance' ? 'warning' : a.type === 'resolved' ? 'success' : 'accent'
              const color = tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : tone === 'success' ? 'var(--success)' : 'var(--accent)'
              return (
                <PortalCard key={a.id}>
                  <div className="posude-row-12">
                    <div className="posude-row-15 portal-support-desk-e9" style={{ '--portal-support-desk-color': color } as CSSProperties}>
                      <Icon size={15} />
                    </div>
                    <div className="u-flex1-min0">
                      <div className="posude-box-13">{a.title}</div>
                      <p className="posude-box-14">{a.body}</p>
                      {a.starts_at && <div className="posude-box-15">{a.starts_at}{a.ends_at && ` → ${a.ends_at}`}</div>}
                    </div>
                  </div>
                </PortalCard>
              )
            })}
          </div>
        )
      )}

      <PortalModal
        open={showCreate}
        onClose={() => { setDynamicValues({}); setShowCreate(false) }}
        title={traducir('portalsupportdesk.abrir_nuevo_ticket')}
        subtitle={traducir('portalsupportdesk.cuentanos_que_necesitas_sigue_las_plantillas_si')}
        width={620}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => { setDynamicValues({}); setShowCreate(false) }}>{traducir('common.cancel')}</PortalButton>
            <PortalButton loading={creatingTicket} disabled={!createForm.title || !createForm.description}
              onClick={() => createTicket({ ...createForm, dynamic_fields: dynamicValues })}>{traducir('portaldashboard.abrir_ticket')}</PortalButton>
          </>
        }
      >
        <PortalBanner tone="info" icon={<BookOpen size={16} />}
          title={traducir('portalsupportdesk.has_revisado_la_base_de_conocimiento')}
          body="Muchos casos están ya documentados — revisa la KB antes de abrir un ticket nuevo." />
        {catalog.length > 0 && (
          <PortalField label={traducir('portalsupportdesk.servicio_del_catalogo')}>
            <PortalSelect value={createForm.service_item_id}
              onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, service_item_id: e.target.value }))}>
              <option value="">{traducir('invoices.select')}</option>
              {catalog.map(cat => (
                <optgroup key={cat.id} label={`${cat.icon || ''} ${cat.name}`}>
                  {cat.services.map(s => <option key={s.id} value={s.id}>{s.name} {traducir('portalsupportdesk.sla')} {s.sla_resolution_hours}h</option>)}
                </optgroup>
              ))}
            </PortalSelect>
          </PortalField>
        )}
        {(contextOptions.cis || []).length > 0 && (
          <PortalField label={traducir('portalsupportdesk.ci_afectado_opcional')}>
            <PortalSelect value={createForm.ci_id || ''}
              onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, ci_id: e.target.value }))}>
              <option value="">{traducir('invoices.select')}</option>
              {(contextOptions.cis || []).map(ci => (
                <option key={ci.id} value={ci.id}>{ci.code ? `${ci.code} - ` : ''}{ci.name}</option>
              ))}
            </PortalSelect>
          </PortalField>
        )}
        <div className="posude-stack-1">
          <PortalField label={traducir('portalsupportdesk.tipo_de_ticket')}>
            <div className="u-wrap-8">
              {([
                ['incident', 'Incidencia', Bug],
                ['service_request', 'Solicitud', ClipboardList],
                ['question', 'Consulta', HelpCircle],
              ] as [string, string, typeof Bug][]).map(([v, l, Icon]) => (
                <button className={`posude-row-16 portalsu-sx6 portal-support-desk-e3 ${createForm.ticket_type === v ? 'portal-support-desk-m10' : 'portal-support-desk-m11'}`} key={v} onClick={() => setCreateForm(f => ({ ...f, ticket_type: v }))} style={{ '--portal-support-desk-border': `1px solid ${createForm.ticket_type === v ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}><Icon size={14} /> {l}</button>
              ))}
            </div>
          </PortalField>
          <PortalField label={traducir('portalsupportdesk.titulo')} required>
            <PortalInput value={createForm.title} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, title: e.target.value }))} placeholder={traducir('portalsupportdesk.resumen_claro_del_problema')} />
          </PortalField>
          <SugerenciasDeLaKb texto={createForm.title} onResuelto={() => { setDynamicValues({}); setShowCreate(false) }} />
          <PortalField label={traducir('portalsupportdesk.descripcion')} required hint="Cuanto más contexto añadas, antes te resolveremos">
            <PortalTextarea rows={4} value={createForm.description} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, description: e.target.value }))} placeholder={traducir('portalsupportdesk.describe_el_problema_o_solicitud')} />
          </PortalField>
          <div className="u-grid2-12">
            <PortalField label={traducir('service_desk.edit_urgency')}>
              <PortalSelect value={createForm.urgency} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, urgency: e.target.value }))}>
                <option value="critical">{traducir('portalsupportdesk.critica_el_negocio_esta_parado')}</option>
                <option value="high">{traducir('portalsupportdesk.alta_funcionalidad_importante_no_funciona')}</option>
                <option value="medium">{traducir('portalsupportdesk.media_hay_un_workaround')}</option>
                <option value="low">{traducir('portalsupportdesk.baja_problema_menor')}</option>
              </PortalSelect>
            </PortalField>
            <PortalField label={traducir('cmdb.impact')}>
              <PortalSelect value={createForm.impact} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, impact: e.target.value }))}>
                <option value="enterprise">{traducir('portalsupportdesk.toda_la_empresa')}</option>
                <option value="department">{traducir('portalsupportdesk.mi_departamento')}</option>
                <option value="user">{traducir('portalsupportdesk.solo_a_mi')}</option>
                <option value="minimal">{traducir('portalsupportdesk.minimo')}</option>
              </PortalSelect>
            </PortalField>
          </div>

          {routingHint && (
            <PortalBanner
              tone="info"
              icon={<GitBranch size={14} />}
              title={traducir('portalsupportdesk.ruta_sugerida_automaticamente')}
              body={Object.entries(routingHint).map(([k, v]) => `${k}=${v}`).join(', ')}
            />
          )}

          {visibleDynamicFields.map((f) => (
            <PortalField key={f.id} label={f.label + (f.required ? ' *' : '')}>
              {f.type === 'select' ? (
                <PortalSelect
                  value={dynamicValues[f.id] || ''}
                  onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                >
                  <option value="">{traducir('invoices.select')}</option>
                  {(f.options || []).map(op => <option key={op} value={op}>{op}</option>)}
                </PortalSelect>
              ) : f.type === 'textarea' ? (
                <PortalTextarea
                  rows={4}
                  value={dynamicValues[f.id] || ''}
                  onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                />
              ) : (f.type || '').startsWith('context_') ? (
                <>
                  <PortalInput
                    list={`portal-dyn-${f.id}-options`}
                    value={dynamicValues[f.id] || ''}
                    onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                  />
                  <datalist id={`portal-dyn-${f.id}-options`}>
                    {contextSuggestionsForField(f).map((op, idx) => <option key={`${f.id}-${idx}`} value={op} aria-label={op} />)}
                  </datalist>
                </>
              ) : (
                <PortalInput
                  type={f.type === 'date' ? 'date' : 'text'}
                  value={dynamicValues[f.id] || ''}
                  onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                />
              )}
            </PortalField>
          ))}
        </div>
      </PortalModal>
    </div>
  )
}


/**
 * Mientras el cliente escribe el título, los artículos públicos que podrían
 * resolverle el problema. Si uno se lo resuelve, no abre la petición y queda
 * contado como desvío en el artículo.
 */
function SugerenciasDeLaKb({ texto, onResuelto }: { texto: string; onResuelto: () => void }) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [consulta, setConsulta] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  useEffect(() => {
    const h = setTimeout(() => setConsulta(texto.trim()), SLOW_INPUT_DEBOUNCE_MS)
    return () => clearTimeout(h)
  }, [texto])
  const { data: sugerencias = [] } = useQuery<{ id: string; title: string; summary?: string | null }[]>({
    queryKey: ['portal-kb-suggest', consulta],
    queryFn: () => CLIENT_API.get('/sd/kb/suggest', { params: { q: consulta } }).then(r => r.data as { id: string; title: string; summary?: string | null }[]),
    enabled: consulta.length >= 4,
  })
  const { data: detalle } = useQuery<{ body?: string }>({
    queryKey: ['portal-kb-article', abierto],
    queryFn: () => CLIENT_API.get(`/sd/kb/${abierto}`).then(r => r.data as { body?: string }),
    enabled: !!abierto,
  })
  const resuelto = useMutation({
    mutationFn: (id: string) => CLIENT_API.post(`/sd/kb/${id}/deflected`),
    onSuccess: () => { toast.success(traducir('sd_cfg.kb_solved_thanks')); onResuelto() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (consulta.length < 4 || sugerencias.length === 0) return null
  return (
    <div role="region" aria-label={traducir('sd_cfg.kb_suggest_title')}
      className="posude-stack-2">
      <strong className="u-sm">{traducir('sd_cfg.kb_suggest_title')}</strong>
      {sugerencias.slice(0, 3).map(a => (
        <div key={a.id} className="posude-box-16">
          <button type="button" onClick={() => setAbierto(abierto === a.id ? null : a.id)} aria-expanded={abierto === a.id}
            className="posude-box-17">
            {a.title}
          </button>
          {abierto === a.id && (
            <div className="posude-stack-3">
              <div className="posude-txt-3">{detalle?.body ?? a.summary ?? ''}</div>
              <div><PortalButton onClick={() => resuelto.mutate(a.id)} loading={resuelto.isPending}>{traducir('sd_cfg.kb_solved')}</PortalButton></div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
