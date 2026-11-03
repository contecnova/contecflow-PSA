/**
 * PortalSupportDesk — service desk del cliente con el lenguaje del backoffice.
 * Tickets, KB y comunicados.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Headphones, Plus, Search, ArrowLeft, Megaphone, Bug, BookOpen,
  AlertTriangle, Wrench, CheckCircle2, Star, Send,
  ClipboardList, HelpCircle, GitBranch, Clock,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { CLIENT_API, useLang } from './portalClientContext'
import {
  PortalPageHeader as PortalPageHeaderBase, PortalCard as PortalCardBase,
  PortalEmpty as PortalEmptyBase, PortalBadge as PortalBadgeBase,
  PortalButton as PortalButtonBase, PortalModal as PortalModalBase,
  PortalField as PortalFieldBase, PortalInput as PortalInputBase,
  PortalSelect as PortalSelectBase, PortalTextarea as PortalTextareaBase,
  PortalBanner as PortalBannerBase,
} from './PortalUI'
import { useAppLang } from '../../i18n/AppLangContext'
import { useTabListKeys } from '../../components/ui/Tabs'

// PortalUI is untyped JS: alias each component to accept partial props so
// optional props need not be passed explicitly (behavior unchanged).
type AnyProps = Record<string, unknown>
type AnyComp = (p: AnyProps) => JSX.Element
const PortalPageHeader = PortalPageHeaderBase as unknown as AnyComp
const PortalCard = PortalCardBase as unknown as AnyComp
const PortalEmpty = PortalEmptyBase as unknown as AnyComp
const PortalBadge = PortalBadgeBase as unknown as AnyComp
const PortalButton = PortalButtonBase as unknown as AnyComp
const PortalModal = PortalModalBase as unknown as AnyComp
const PortalField = PortalFieldBase as unknown as AnyComp
const PortalInput = PortalInputBase as unknown as AnyComp
const PortalSelect = PortalSelectBase as unknown as AnyComp
const PortalTextarea = PortalTextareaBase as unknown as AnyComp
const PortalBanner = PortalBannerBase as unknown as AnyComp

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
      params: { service_item_id: createForm.service_item_id || undefined, limit: 60 },
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
      toast.success('Ticket abierto')
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-sd-ticket', selectedId] }); toast.success('Gracias por tu valoración') },
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
          actions={<PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={() => setSelectedId(null)}>Volver</PortalButton>}
        />

        {!ticketDetail ? (
          <div style={{ color: 'var(--text-3)', padding: 60, textAlign: 'center' }}>Cargando ticket...</div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
              <PortalBadge tone={ticketDetail.approval_status === 'pending' ? 'warning' : (STATUS_TONE[ticketDetail.status || ""] || 'default')}>{ticketDetail.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : (ticketDetail.status_label || ticketDetail.status)}</PortalBadge>
              <PortalBadge tone={PRIORITY_TONE[ticketDetail.priority || ""] || 'default'}>{ticketDetail.priority_label}</PortalBadge>
            </div>

            <PortalCard style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Objetos vinculados</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>Cliente</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2 }}>{ticketDetail.client_name || '—'}</div>
                </div>
                <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>Servicio</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2 }}>{ticketDetail.service_item_name || '—'}</div>
                </div>
                <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', gridColumn: '1/-1' }}>
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>CI vinculado</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2 }}>{ticketDetail.ci_name || '—'}</div>
                </div>
              </div>
            </PortalCard>

              <PortalCard style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{traducir('portalsupportdesk.descripcion_original')}</div>
              <p style={{ fontSize: 'var(--text-sm)', lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>{ticketDetail.description}</p>
            </PortalCard>

            {ticketDetail.dynamic_fields && Object.keys(ticketDetail.dynamic_fields).length > 0 && (
              <PortalCard style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                  Campos adicionales
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {Object.entries(ticketDetail.dynamic_fields).map(([k, v]) => (
                    <div key={k} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', textTransform: 'uppercase' }}>{k}</div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2, whiteSpace: 'pre-wrap' }}>{String(v ?? '—')}</div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            {ticketDetail.resolution && (
              <PortalCard style={{ marginBottom: 14, borderColor: 'var(--success-border, rgba(16,185,129,0.3))' }}>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CheckCircle2 size={13} /> {traducir('portalsupportdesk.resolucion_del_equipo')}
                </div>
                <p style={{ fontSize: 'var(--text-sm)', lineHeight: 1.7, margin: 0 }}>{ticketDetail.resolution}</p>
              </PortalCard>
            )}

            {ticketDetail.csat_requested_at && !ticketDetail.csat_score && (
              <PortalCard style={{ marginBottom: 14, borderColor: 'var(--success-border, rgba(16,185,129,0.3))' }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Star size={14} style={{ color: 'var(--warning)' }} /> {traducir('portalsupportdesk.como_valorarias_la_atencion_recibida')}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[1, 2, 3, 4, 5].map(n => (
                    <button key={n} onClick={() => submitCSAT({ score: n })} style={{
                      flex: 1, padding: '12px', borderRadius: 10,
                      border: '1px solid var(--surface-4)', background: 'var(--surface-3)',
                      color: 'var(--text-1)', cursor: 'pointer',
                      fontSize: 'var(--text-md-em)', fontFamily: 'inherit',
                    }}>{'⭐'.repeat(n)}</button>
                  ))}
                </div>
              </PortalCard>
            )}
            {ticketDetail.csat_score && (
              <PortalBanner tone="success" icon={<Star size={16} />} title={`Valoración: ${ticketDetail.csat_score}/5`} body="Gracias por tu feedback" />
            )}

            {Array.isArray(ticketDetail.history) && ticketDetail.history.length > 0 && (
              <PortalCard style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{traducir('portalsupportdesk.actividad_del_ticket')}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {ticketDetail.history.slice(-8).reverse().map((h, idx) => (
                    <div key={`${h.changed_at}-${idx}`} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{h.changed_at} · {h.changed_by || 'Sistema'}</div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2 }}>
                        {h.field}: {String(h.old_value ?? '—')} → {String(h.new_value ?? '—')}
                      </div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            {upcomingEvents.length > 0 && (
              <PortalCard style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{traducir('portalsupportdesk.calendario_de_eventos')}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {upcomingEvents.map((ev) => (
                    <div key={ev.id} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', fontWeight: 700 }}>{ev.title}</div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>{ev.starts_at}{ev.ends_at ? ` → ${ev.ends_at}` : ''}</div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, marginBottom: 12 }}>{traducir('portalsupportdesk.conversacion')}</div>
              {ticketDetail.comments?.filter(c => c.is_public).map(c => (
                <div key={c.id} style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                    background: c.author_type === 'agent'
                      ? 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))'
                      : 'linear-gradient(135deg, var(--success, #10b981), var(--accent))',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 'var(--text-xs)', fontWeight: 800, color: '#fff',
                  }}>{c.author_name?.split(' ').map(w => w[0]).join('').slice(0, 2)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 10, marginBottom: 4, alignItems: 'baseline', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{c.author_name}</span>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{c.created_at}</span>
                      {c.author_type === 'agent' && <PortalBadge tone="accent">Agente</PortalBadge>}
                    </div>
                    <div style={{
                      background: c.author_type === 'agent' ? 'var(--surface-3)' : 'var(--accent-muted)',
                      border: `1px solid ${c.author_type === 'agent' ? 'var(--surface-4)' : 'var(--accent-border, rgba(79,142,247,0.25))'}`,
                      borderRadius: 10, padding: '10px 14px', fontSize: 'var(--text-sm)', lineHeight: 1.6,
                    }}>{c.body}</div>
                  </div>
                </div>
              ))}
            </div>

            {!['closed', 'cancelled'].includes(ticketDetail.status || '') && (
              <PortalCard>
                <PortalField label="Tu respuesta">
                  <PortalTextarea rows={4} value={newComment} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setNewComment(e.target.value)} placeholder="Escribe tu respuesta..." />
                </PortalField>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                  <PortalButton icon={<Send size={13} />} disabled={!newComment.trim()}
                    onClick={() => { addComment({ body: newComment, is_public: true }); setNewComment('') }}>
                    Enviar respuesta
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
        subtitle="Tickets de soporte, base de conocimiento y comunicados del equipo."
        icon={Headphones}
        meta={[
          { value: openTickets, label: 'tickets abiertos', color: 'var(--accent)' },
          { value: pendingClient, label: 'esperan tu respuesta', color: pendingClient ? 'var(--warning)' : 'var(--text-3)' },
          { value: announcements.length, label: 'comunicados activos' },
        ]}
        actions={
          <PortalButton icon={<Plus size={14} />} onClick={() => { setDynamicValues({}); setShowCreate(true) }}>Abrir ticket</PortalButton>
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

      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" aria-label="Service Desk" style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--surface-4)', marginBottom: 18, flexWrap: 'wrap' }}>
        {tabs.map(tb => (
          <button key={tb.id} type="button" role="tab" data-tab-id={tb.id}
            tabIndex={tb.id === teclas.focusId ? 0 : -1} aria-selected={tab === tb.id}
            onClick={() => setTab(tb.id)}
            style={{
              background: 'transparent', border: 'none',
              borderBottom: `2px solid ${tab === tb.id ? 'var(--accent)' : 'transparent'}`,
              padding: '9px 14px', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 'var(--text-sm)', fontWeight: tab === tb.id ? 700 : 500,
              color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)',
              display: 'inline-flex', alignItems: 'center', gap: 6,
            }}>{tb.icon} {tb.label}</button>
        ))}
      </div>

      {/* Tickets */}
      {tab === 'tickets' && (
        tickets.length === 0 ? (
          <PortalEmpty icon={Headphones} title={traducir('portalsupportdesk.no_tienes_tickets')}
            description="¿Necesitas ayuda? Abre un ticket y el equipo te atenderá en plazo SLA."
            action={<PortalButton icon={<Plus size={14} />} onClick={() => { setDynamicValues({}); setShowCreate(true) }}>Abrir ticket</PortalButton>}
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {tickets.map(tk => {
              const TypeIcon = TYPE_ICON[tk.ticket_type || ""] || Headphones
              return (
                <PortalCard key={tk.id} onClick={() => setSelectedId(tk.id)}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{tk.number}</span>
                        <TypeIcon size={13} style={{ color: 'var(--text-2)' }} />
                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{tk.title}</span>
                      </div>
                      <div style={{ display: 'flex', gap: 12, fontSize: 'var(--text-xs)', color: 'var(--text-3)', flexWrap: 'wrap' }}>
                        <span>Creado: {tk.created_at}</span>
                        {tk.assigned_to_name && <span>Asignado: {tk.assigned_to_name}</span>}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <span style={{
                        fontSize: 'var(--text-xs)', fontWeight: 700,
                        color: PRIORITY_COLORS[tk.priority || ""] || 'var(--text-2)',
                      }}>{tk.priority_label}</span>
                      <PortalBadge tone={tk.approval_status === 'pending' ? 'warning' : (STATUS_TONE[tk.status || ""] || 'default')}>{tk.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : (tk.status_label || tk.status)}</PortalBadge>
                    </div>
                  </div>
                  {tk.status === 'pending_client' && (
                    <div style={{
                      marginTop: 10, padding: '8px 12px',
                      background: 'var(--warning-bg, rgba(245,158,11,0.12))',
                      borderRadius: 8, fontSize: 'var(--text-xs)',
                      color: 'var(--warning)', fontWeight: 700,
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                    }}><Clock size={12} /> {traducir('portalsupportdesk.esperan_tu_respuesta_clic_para_abrir')}</div>
                  )}
                  {tk.csat_requested_at && !tk.csat_score && (
                    <div style={{
                      marginTop: 8, padding: '6px 12px',
                      background: 'var(--success-bg, rgba(16,185,129,0.12))',
                      borderRadius: 8, fontSize: 'var(--text-xs)',
                      color: 'var(--success)', fontWeight: 700,
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                    }}><Star size={12} /> {traducir('portalsupportdesk.valora_la_atencion_recibida')}</div>
                  )}
                </PortalCard>
              )
            })}
          </div>
        )
      )}

      {/* KB */}
      {tab === 'kb' && (
        <>
          <div style={{ marginBottom: 16, position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none' }} />
            <PortalInput value={searchKB} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setSearchKB(e.target.value)} placeholder={traducir('portalsupportdesk.buscar_articulo')}
              style={{ paddingLeft: 34, fontSize: 'var(--text-md)', padding: '11px 12px 11px 34px' }} />
          </div>
          {kbArticles.length === 0 ? (
            <PortalEmpty icon={Search} title={searchKB ? `Sin resultados para "${searchKB}"` : 'Base de conocimiento vacía'} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {kbArticles.map(a => (
                <PortalCard key={a.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{a.title}</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>👁 {a.view_count} · ✓ {a.helpful_count}</div>
                  </div>
                  {a.summary && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: '0 0 8px' }}>{a.summary}</p>}
                  {a.tags && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>🏷 {a.tags}</div>}
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {announcements.map(a => {
              const Icon = a.type === 'outage' ? AlertTriangle : a.type === 'maintenance' ? Wrench : a.type === 'resolved' ? CheckCircle2 : Megaphone
              const tone = a.type === 'outage' ? 'danger' : a.type === 'maintenance' ? 'warning' : a.type === 'resolved' ? 'success' : 'accent'
              const color = tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : tone === 'success' ? 'var(--success)' : 'var(--accent)'
              return (
                <PortalCard key={a.id}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--surface-3)', color, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon size={15} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 4 }}>{a.title}</div>
                      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: 0 }}>{a.body}</p>
                      {a.starts_at && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6 }}>{a.starts_at}{a.ends_at && ` → ${a.ends_at}`}</div>}
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
        subtitle="Cuéntanos qué necesitas. Sigue las plantillas si te ayuda."
        width={620}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => { setDynamicValues({}); setShowCreate(false) }}>Cancelar</PortalButton>
            <PortalButton loading={creatingTicket} disabled={!createForm.title || !createForm.description}
              onClick={() => createTicket({ ...createForm, dynamic_fields: dynamicValues })}>Abrir ticket</PortalButton>
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
              <option value="">Seleccionar...</option>
              {catalog.map(cat => (
                <optgroup key={cat.id} label={`${cat.icon || ''} ${cat.name}`}>
                  {cat.services.map(s => <option key={s.id} value={s.id}>{s.name} — SLA {s.sla_resolution_hours}h</option>)}
                </optgroup>
              ))}
            </PortalSelect>
          </PortalField>
        )}
        {(contextOptions.cis || []).length > 0 && (
          <PortalField label="CI afectado (opcional)">
            <PortalSelect value={createForm.ci_id || ''}
              onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, ci_id: e.target.value }))}>
              <option value="">Seleccionar...</option>
              {(contextOptions.cis || []).map(ci => (
                <option key={ci.id} value={ci.id}>{ci.code ? `${ci.code} - ` : ''}{ci.name}</option>
              ))}
            </PortalSelect>
          </PortalField>
        )}
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <PortalField label={traducir('portalsupportdesk.tipo_de_ticket')}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {([
                ['incident', 'Incidencia', Bug],
                ['service_request', 'Solicitud', ClipboardList],
                ['question', 'Consulta', HelpCircle],
              ] as [string, string, typeof Bug][]).map(([v, l, Icon]) => (
                <button key={v} onClick={() => setCreateForm(f => ({ ...f, ticket_type: v }))} style={{
                  flex: 1, minWidth: 110,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  padding: '10px',
                  background: createForm.ticket_type === v ? 'var(--accent-muted)' : 'var(--surface-3)',
                  border: `1px solid ${createForm.ticket_type === v ? 'var(--accent)' : 'var(--surface-4)'}`,
                  borderRadius: 8,
                  color: createForm.ticket_type === v ? 'var(--accent)' : 'var(--text-2)',
                  cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 700, fontFamily: 'inherit',
                }}><Icon size={14} /> {l}</button>
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <PortalField label="Urgencia">
              <PortalSelect value={createForm.urgency} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, urgency: e.target.value }))}>
                <option value="critical">{traducir('portalsupportdesk.critica_el_negocio_esta_parado')}</option>
                <option value="high">{traducir('portalsupportdesk.alta_funcionalidad_importante_no_funciona')}</option>
                <option value="medium">{traducir('portalsupportdesk.media_hay_un_workaround')}</option>
                <option value="low">Baja — problema menor</option>
              </PortalSelect>
            </PortalField>
            <PortalField label="Impacto">
              <PortalSelect value={createForm.impact} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setCreateForm(f => ({ ...f, impact: e.target.value }))}>
                <option value="enterprise">{traducir('portalsupportdesk.toda_la_empresa')}</option>
                <option value="department">Mi departamento</option>
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
                  <option value="">Seleccionar...</option>
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
                    {contextSuggestionsForField(f).map((op, idx) => <option key={`${f.id}-${idx}`} value={op} />)}
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
    const h = setTimeout(() => setConsulta(texto.trim()), 400)
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
      style={{ border: '1px solid var(--accent)', background: 'var(--accent-muted)', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <strong style={{ fontSize: 'var(--text-sm)' }}>{traducir('sd_cfg.kb_suggest_title')}</strong>
      {sugerencias.slice(0, 3).map(a => (
        <div key={a.id} style={{ background: 'var(--surface-1)', borderRadius: 8, padding: '8px 10px' }}>
          <button type="button" onClick={() => setAbierto(abierto === a.id ? null : a.id)} aria-expanded={abierto === a.id}
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit', color: 'var(--accent)', fontWeight: 600, textAlign: 'left' }}>
            {a.title}
          </button>
          {abierto === a.id && (
            <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', whiteSpace: 'pre-wrap' }}>{detalle?.body ?? a.summary ?? ''}</div>
              <div><PortalButton onClick={() => resuelto.mutate(a.id)} loading={resuelto.isPending}>{traducir('sd_cfg.kb_solved')}</PortalButton></div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
