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
  ClipboardList, HelpCircle, GitBranch, Clock, Bot, ArrowRight, MessagesSquare, Eye, ThumbsUp, Tag,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate, fmtDateTime } from '../../utils/helpers'
import { CLIENT_API, useErrorDelPortal, useLang, useIdiomaDelPortal, useEtiquetaEstado, rellenar } from './portalClientContext'
import PortalKbArticulo from './PortalKbArticulo'
import { EVENTO_ABRIR_TICKET } from './CampanaDelPortal'
import TraduccionAutomatica, { MarcaDeTraduccion, textoDe } from './TraduccionAutomatica'
import { PortalAsistente, PortalChatEnVivo } from './PortalAsistenteYChat'
import {
  PortalPageHeader, PortalCard,
  PortalEmpty, PortalBadge,
  PortalButton, PortalModal,
  PortalField, PortalInput,
  PortalSelect, PortalTextarea,
  PortalBanner, PortalTabs,
} from './PortalUI'
import { DYNAMIC_FORM_OPTIONS_LIMIT } from '../../constants/pagination'
import './PortalSupportDesk.css'
import { CampoFecha } from '../../components/ui/SelectorDeFecha'
import { textosDeFechaDelPortal } from '../../i18n/fechaPortal'
import { Buscador, useErroresDeCampo } from '../../components/ui'
import { type Announcement, type CatalogGroup, type ContextItem, type ContextOptions, type DynamicField, type DynamicRules, type KbArticle, PRIORITY_COLORS, PRIORITY_TONE, STATUS_TONE, TYPE_ICON, type Ticket, type TicketDetail } from './PortalSupportDeskComun'
import { SugerenciasDeLaKb } from './PortalSugerenciasDeLaKb'

export function PortalSupportDesk() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const _t = useLang()
  const etiquetaEstado = useEtiquetaEstado()
  // Prioridad en el idioma del portal por su código (`prio_<código>`): la
  // etiqueta que manda el servidor está en castellano (16-11-2026).
  const etiquetaPrioridad = (codigo?: string | null, respaldo?: string | null) => {
    if (!codigo) return respaldo || ''
    const v = _t(`prio_${codigo}`)
    return v !== `prio_${codigo}` ? v : (respaldo || codigo)
  }
  /** Nombre visible de un campo del ticket (historial, ruta sugerida): nunca la clave interna. */
  const nombreDeCampo = (campo?: string) => {
    if (!campo) return ''
    const clave = `psd_field_${campo}`
    const v = _t(clave)
    if (v && v !== clave) return v
    const texto = campo.replace(/_/g, ' ')
    return texto.charAt(0).toUpperCase() + texto.slice(1)
  }
  const valorDeCampo = (campo: string | undefined, valor: unknown) => {
    if (valor == null || valor === '') return '—'
    if (campo === 'status') return etiquetaEstado(String(valor))
    if (campo === 'priority') return etiquetaPrioridad(String(valor))
    // Incidencia 3 (23-11-2026): la cola y los valores de serie, por su nombre.
    const clave = campo === 'queue' ? `psd_cola_${valor}` : `psd_opcion_${valor}`
    const v = _t(clave)
    if (v && v !== clave) return v
    const texto = String(valor).replace(/_/g, ' ')
    return texto.charAt(0).toUpperCase() + texto.slice(1)
  }
  /** Etiqueta de los campos dinámicos de serie (`affected_environment`…) en el idioma del portal. */
  const campoDeSerie = (id?: string) => {
    if (!id) return null
    const clave = `psd_campo_${id}`
    const v = _t(clave)
    return v && v !== clave ? v : null
  }
  /** Opción de un desplegable dinámico en el idioma del portal (el valor guardado no cambia). */
  const opcionDinamica = (op: string) => {
    const clave = `psd_opcion_${op}`
    const v = _t(clave)
    return v && v !== clave ? v : op
  }
  const idioma = useIdiomaDelPortal()
  const toast = useToast()
  const qc = useQueryClient()
  // `?ticket=<id>` abre ese ticket: es a donde lleva el enlace de los correos.
  const [selectedId, setSelectedId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get('ticket'))
  // La campana de la cabecera (16-11-2026) abre un ticket aunque Soporte ya
  // esté en pantalla: avisa con `EVENTO_ABRIR_TICKET`.
  useEffect(() => {
    const abrir = (e: Event) => {
      const id = (e as CustomEvent<string>).detail
      if (id) setSelectedId(id)
    }
    window.addEventListener(EVENTO_ABRIR_TICKET, abrir)
    return () => window.removeEventListener(EVENTO_ABRIR_TICKET, abrir)
  }, [])
  const [showCreate, setShowCreate] = useState(false)
  // «Ver original» del formulario de alta: catálogo y etiquetas de los campos dinámicos.
  const [formularioOriginal, setFormularioOriginal] = useState(false)
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
    // 16-11-2026: nombres y descripciones en el idioma del portal (si la empresa traduce).
    queryKey: ['portal-sd-catalog', idioma],
    queryFn: () => CLIENT_API.get('/sd/catalog', { params: { public_only: true, lang: idioma } }).then(r => r.data as CatalogGroup[]),
  })
  const { data: kbArticles = [] } = useQuery<KbArticle[]>({
    queryKey: ['portal-kb', searchKB, idioma],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined, lang: idioma } }).then(r => r.data as KbArticle[]),
  })
  const { data: announcements = [] } = useQuery<Announcement[]>({
    queryKey: ['portal-sd-anns', idioma],
    queryFn: () => CLIENT_API.get('/sd/announcements', { params: { lang: idioma } }).then(r => r.data as Announcement[]),
  })
  const { data: ticketDetail } = useQuery<TicketDetail>({
    queryKey: ['portal-sd-ticket', selectedId],
    queryFn: () => CLIENT_API.get(`/sd/tickets/client/${selectedId}`).then(r => r.data as TicketDetail),
    enabled: !!selectedId,
  })
  const { data: dynamicRules } = useQuery<DynamicRules>({
    // 16-11-2026: las etiquetas de los campos en el idioma del portal (si la empresa traduce).
    queryKey: ['portal-sd-dynamic-forms', idioma],
    queryFn: () => CLIENT_API.get('/sd/dynamic-forms/public', { params: { lang: idioma } }).then(r => r.data as DynamicRules),
  })
  const { data: contextOptions = { clients: [], services: [], cis: [] } } = useQuery<ContextOptions>({
    queryKey: ['portal-sd-dynamic-forms-context', createForm.service_item_id],
    queryFn: () => CLIENT_API.get('/sd/dynamic-forms/public/context-options', {
      params: { service_item_id: createForm.service_item_id || undefined, limit: DYNAMIC_FORM_OPTIONS_LIMIT },
    }).then(r => r.data as ContextOptions),
  })

  const [dynamicValues, setDynamicValues] = useState<Record<string, string>>({})
  const campos = useErroresDeCampo()

  const { mutate: createTicket, isPending: creatingTicket } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post('/sd/tickets/client', d),
    onMutate: () => campos.limpiar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-sd-tickets'] })
      setShowCreate(false)
      setCreateForm({ title: '', description: '', ticket_type: 'incident', urgency: 'medium', impact: 'user', service_item_id: '', ci_id: '' })
      setDynamicValues({})
      toast.success(traducir('portalsupportdesk.ticket_abierto'))
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(errorDe(e, traducir('error_inesperado'))) },
  })
  const { mutate: addComment } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post(`/sd/tickets/${selectedId}/comments/client`, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portal-sd-ticket', selectedId] }),
    onError: (e: unknown) => toast.error(errorDe(e, traducir('error_inesperado'))),
  })
  const { mutate: submitCSAT } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.post(`/sd/tickets/${selectedId}/csat`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-sd-ticket', selectedId] }); toast.success(traducir('portalsupportdesk.gracias_por_tu_valoracion')) },
    onError: (e: unknown) => toast.error(errorDe(e, traducir('error_inesperado'))),
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

  // Idioma de origen si algo del catálogo o de las etiquetas llegó traducido automáticamente.
  const origenDelCatalogo = useMemo(() => {
    for (const cat of catalog) {
      if (cat.translated_from) return cat.translated_from
      const s = (cat.services || []).find(x => x.translated_from)
      if (s) return s.translated_from
    }
    return null
  }, [catalog])
  const origenDeLosCampos = visibleDynamicFields.find(f => f.translated_from)?.translated_from ?? null

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
    { id: 'tickets', label: _t('support_tab_tickets'), icon: <Headphones size={14} />, badge: tickets.length },
    { id: 'kb',      label: _t('support_tab_kb'),      icon: <BookOpen size={14} /> },
    { id: 'announcements', label: _t('support_tab_ann'), icon: <Megaphone size={14} />, badge: announcements.length },
    // Mejoras de mercado 16-11-2026: asistente que actúa y chat en vivo con traspaso a agente
    // (pestañas de primer nivel: antes iban en una segunda barra dentro de «Asistente»).
    { id: 'assistant', label: _t('sdm_asistente'), icon: <Bot size={14} /> },
    { id: 'chat', label: _t('sdm_chat'), icon: <MessagesSquare size={14} /> },
  ]

  // ── Detail view ────────────────────────────────────────────────────────────
  if (tab === 'tickets' && selectedId) {
    return (
      <div>
        <PortalPageHeader
          title={ticketDetail?.title || traducir('common.loading')}
          icon={Headphones}
          breadcrumb={[
            { label: _t('nav_support'), onClick: () => setSelectedId(null) },
            { label: ticketDetail?.number || '...' },
          ]}
          meta={ticketDetail ? [
            { value: ticketDetail.number, color: 'var(--text-3)' },
            ticketDetail.assigned_to_name && { value: ticketDetail.assigned_to_name, label: _t('support_agent') },
            ticketDetail.sla_resolution_due && { value: fmtDateTime(ticketDetail.sla_resolution_due), label: _t('support_sla') },
          ].filter(Boolean) : []}
          actions={<PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={() => setSelectedId(null)}>{traducir('chat.back')}</PortalButton>}
        />

        {!ticketDetail ? (
          <div className="posude-box-1">{traducir('portalsupportdesk.cargando_ticket')}</div>
        ) : (
          <>
            <div className="posude-row-1">
              <PortalBadge tone={ticketDetail.approval_status === 'pending' ? 'warning' : (STATUS_TONE[ticketDetail.status || ""] || 'default')}>{ticketDetail.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : etiquetaEstado(ticketDetail.status)}</PortalBadge>
              <PortalBadge tone={PRIORITY_TONE[ticketDetail.priority || ""] || 'default'}>{etiquetaPrioridad(ticketDetail.priority, ticketDetail.priority_label)}</PortalBadge>
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
                      <div className="posude-txt-1">{nombreDeCampo(k)}</div>
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
                    <PortalButton key={n} variant="secondary" size="sm" icon={<Star size={14} />}
                      onClick={() => submitCSAT({ score: n })}>{n}</PortalButton>
                  ))}
                </div>
              </PortalCard>
            )}
            {ticketDetail.csat_score && (
              <PortalBanner tone="success" icon={<Star size={16} />} title={rellenar(_t('psd_csat_given'), { n: ticketDetail.csat_score })} body={_t('psd_csat_thanks')} />
            )}

            {Array.isArray(ticketDetail.history) && ticketDetail.history.length > 0 && (
              <PortalCard className="portalsu-sx1">
                <div className="posude-box-2">{traducir('portalsupportdesk.actividad_del_ticket')}</div>
                <div className="u-stack-8">
                  {ticketDetail.history.slice(-8).reverse().map((h, idx) => (
                    <div key={`${h.changed_at}-${idx}`} className="posude-box-3">
                      <div className="u-text3-2xs">{fmtDateTime(h.changed_at)} · {h.changed_by || _t('psd_system')}</div>
                      <div className="posude-box-4 posude-cambio">
                        <span>{nombreDeCampo(h.field)}:</span> <span>{valorDeCampo(h.field, h.old_value)}</span>
                        <ArrowRight size={12} aria-hidden="true" />
                        <span>{valorDeCampo(h.field, h.new_value)}</span>
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
                      <div className="u-text3-xs-mt2">{fmtDateTime(ev.starts_at)}{ev.ends_at ? ` – ${fmtDateTime(ev.ends_at)}` : ''}</div>
                    </div>
                  ))}
                </div>
              </PortalCard>
            )}

            <div className="u-mb-16">
              <div className="posude-box-10">{traducir('portalsupportdesk.conversacion')}</div>
              {ticketDetail.comments?.filter(c => c.is_public).map(c => {
                // 16-11-2026: los comentarios del sistema (plantilla del servidor,
                // ya en el idioma del cliente) van del lado del equipo y sin nombre técnico.
                const delEquipo = c.author_type === 'agent' || c.author_type === 'system'
                const autor = c.author_type === 'system' ? traducir('ticket_autor_sistema') : c.author_name
                return (
                <div key={c.id} className="posude-row-4">
                  <div className={`posude-row-13 ${delEquipo ? 'portal-support-desk-m1' : 'portal-support-desk-m2'}`}>{autor?.split(' ').map(w => w[0]).join('').slice(0, 2)}</div>
                  <div className="u-flex1-min0">
                    <div className="posude-row-5">
                      <span className="u-sm-700">{autor}</span>
                      <span className="u-text3-xs">{fmtDateTime(c.created_at)}</span>
                      {c.author_type === 'agent' && <PortalBadge tone="accent">{traducir('agent_dashboard.agent')}</PortalBadge>}
                      {c.edited_at && !c.retracted_at && <span className="u-text3-xs">({traducir('ticket_comentario_editado')})</span>}
                    </div>
                    <div className={`posude-box-18 portalsu-sx4 portal-support-desk-e3 ${delEquipo ? 'portal-support-desk-m4' : 'portal-support-desk-m5'}`} style={{ '--portal-support-desk-border': `1px solid ${delEquipo ? 'var(--surface-4)' : 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))'}` } as CSSProperties}>{c.retracted_at ? <em>{traducir('ticket_comentario_retirado')}</em> : c.body}</div>
                  </div>
                </div>
                )
              })}
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
        title={_t('nav_support')}
        subtitle={traducir('portalsupportdesk.tickets_de_soporte_base_de_conocimiento_y')}
        icon={Headphones}
        meta={[
          { value: openTickets, label: _t('psd_meta_open'), color: 'var(--accent)' },
          { value: pendingClient, label: _t('psd_meta_waiting'), color: pendingClient ? 'var(--warning)' : 'var(--text-3)' },
          { value: announcements.length, label: _t('psd_meta_announcements') },
        ]}
        actions={
          <PortalButton icon={<Plus size={14} />} onClick={() => { setDynamicValues({}); setShowCreate(true) }}>{traducir('portaldashboard.abrir_ticket')}</PortalButton>
        }
      />

      {announcements.filter(a => a.show_to_clients).map(a => (
        <TraduccionAutomatica key={a.id} item={a}>
          {texto => (
            <PortalBanner
              tone={a.type === 'outage' ? 'danger' : a.type === 'maintenance' ? 'warning' : 'info'}
              icon={a.type === 'outage' ? <AlertTriangle size={18} /> : a.type === 'maintenance' ? <Wrench size={18} /> : <Megaphone size={18} />}
              title={texto('title', a.title)} body={texto('body', a.body)}
            />
          )}
        </TraduccionAutomatica>
      ))}

      {pendingClient > 0 && (
        <PortalBanner tone="warning" icon={<Clock size={18} />}
          title={rellenar(_t(pendingClient === 1 ? 'psd_waiting_title_one' : 'psd_waiting_title_other'), { n: pendingClient })}
          body={_t('psd_waiting_body')}
        />
      )}

      <PortalTabs tabs={tabs} value={tab} onChange={setTab} ariaLabel={_t('nav_support')} />

      {/* Tickets */}
      {tab === 'assistant' && <PortalAsistente />}
      {tab === 'chat' && <PortalChatEnVivo />}
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
                        <span>{traducir('portalsupportdesk.creado')} {fmtDate(tk.created_at)}</span>
                        {tk.assigned_to_name && <span>{traducir('portalsupportdesk.asignado')} {tk.assigned_to_name}</span>}
                      </div>
                    </div>
                    <div className="u-row-center-6">
                      <span className="posude-txt-4 portal-support-desk-e9" style={{ '--portal-support-desk-color': PRIORITY_COLORS[tk.priority || ""] || 'var(--text-2)' } as CSSProperties}>{etiquetaPrioridad(tk.priority, tk.priority_label)}</span>
                      <PortalBadge tone={tk.approval_status === 'pending' ? 'warning' : (STATUS_TONE[tk.status || ""] || 'default')}>{tk.approval_status === 'pending' ? traducir('sd_cfg.apr_portal_pending') : etiquetaEstado(tk.status)}</PortalBadge>
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
          <Buscador className="posude-box-11" value={searchKB} onChange={setSearchKB} placeholder={traducir('portalsupportdesk.buscar_articulo')} />
          {kbArticles.length === 0 ? (
            <PortalEmpty icon={searchKB ? Search : BookOpen} title={searchKB ? rellenar(_t('support_kb_no_results'), { q: searchKB }) : _t('wiki_kb_empty')} />
          ) : (
            <div className="u-stack-10">
              {kbArticles.map(a => (
                <PortalCard key={a.id} onClick={() => setArticuloAbierto(a.id as string)}>
                  <div className="posude-row-11">
                    <div className="u-sm-700">{a.title}</div>
                    <div className="u-text3-xs posude-con-icono"><Eye size={12} aria-label={_t('pas_views')} />{a.view_count ?? 0}<ThumbsUp size={12} aria-label={_t('pas_helpful')} />{a.helpful_count ?? 0}</div>
                  </div>
                  {a.summary && <p className="posude-box-12">{a.summary}</p>}
                  {a.tags && <div className="u-text3-xs posude-con-icono"><Tag size={12} aria-hidden="true" />{a.tags}</div>}
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
                      <TraduccionAutomatica item={a}>
                        {texto => (
                          <>
                            <div className="posude-box-13">{texto('title', a.title)}</div>
                            <p className="posude-box-14">{texto('body', a.body)}</p>
                          </>
                        )}
                      </TraduccionAutomatica>
                      {a.starts_at && <div className="posude-box-15">{fmtDateTime(a.starts_at)}{a.ends_at && ` – ${fmtDateTime(a.ends_at)}`}</div>}
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
          body={_t('psd_kb_banner_body')} />
        {catalog.length > 0 && (
          <PortalField label={traducir('portalsupportdesk.servicio_del_catalogo')} error={campos.de('service_item_id')}>
            <PortalSelect value={createForm.service_item_id}
              onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('service_item_id'); setCreateForm(f => ({ ...f, service_item_id: e.target.value })) }}>
              <option value="">{traducir('invoices.select')}</option>
              {catalog.map(cat => (
                <optgroup key={cat.id} label={textoDe(cat, 'name', cat.name, formularioOriginal)}>
                  {cat.services.map(s => <option key={s.id} value={s.id}>{textoDe(s, 'name', s.name, formularioOriginal)} {traducir('portalsupportdesk.sla')} {s.sla_resolution_hours}h</option>)}
                </optgroup>
              ))}
            </PortalSelect>
            {/* Un solo «Ver original» para todo el catálogo: dentro de un selector no cabe una marca por opción. */}
            <MarcaDeTraduccion origen={origenDelCatalogo} verOriginal={formularioOriginal}
              onAlternar={() => setFormularioOriginal(v => !v)} />
          </PortalField>
        )}
        {(contextOptions.cis || []).length > 0 && (
          <PortalField label={traducir('portalsupportdesk.ci_afectado_opcional')} error={campos.de('ci_id')}>
            <PortalSelect value={createForm.ci_id || ''}
              onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('ci_id'); setCreateForm(f => ({ ...f, ci_id: e.target.value })) }}>
              <option value="">{traducir('invoices.select')}</option>
              {(contextOptions.cis || []).map(ci => (
                <option key={ci.id} value={ci.id}>{ci.code ? `${ci.code} - ` : ''}{ci.name}</option>
              ))}
            </PortalSelect>
          </PortalField>
        )}
        <div className="posude-stack-1">
          <PortalField label={traducir('portalsupportdesk.tipo_de_ticket')} error={campos.de('ticket_type')}>
            <div className="u-wrap-8">
              {([
                ['incident', _t('ticket_type_incident'), Bug],
                ['service_request', _t('ticket_type_request'), ClipboardList],
                ['question', _t('ticket_type_question'), HelpCircle],
              ] as [string, string, typeof Bug][]).map(([v, l, Icon]) => (
                <PortalButton key={v} size="sm" icon={<Icon size={14} />}
                  variant={createForm.ticket_type === v ? 'primary' : 'secondary'}
                  onClick={() => { campos.limpiar('ticket_type'); setCreateForm(f => ({ ...f, ticket_type: v })) }}>{l}</PortalButton>
              ))}
            </div>
          </PortalField>
          <PortalField label={traducir('portalsupportdesk.titulo')} required error={campos.de('title')}>
            <PortalInput value={createForm.title} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('title'); setCreateForm(f => ({ ...f, title: e.target.value })) }} placeholder={traducir('portalsupportdesk.resumen_claro_del_problema')} />
          </PortalField>
          <SugerenciasDeLaKb texto={createForm.title} onResuelto={() => { setDynamicValues({}); setShowCreate(false) }} />
          <PortalField label={traducir('portalsupportdesk.descripcion')} required error={campos.de('description')} hint={_t('psd_desc_hint')}>
            <PortalTextarea rows={4} value={createForm.description} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('description'); setCreateForm(f => ({ ...f, description: e.target.value })) }} placeholder={traducir('portalsupportdesk.describe_el_problema_o_solicitud')} />
          </PortalField>
          <div className="u-grid2-12">
            <PortalField label={traducir('service_desk.edit_urgency')} error={campos.de('urgency')}>
              <PortalSelect value={createForm.urgency} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('urgency'); setCreateForm(f => ({ ...f, urgency: e.target.value })) }}>
                <option value="critical">{traducir('portalsupportdesk.critica_el_negocio_esta_parado')}</option>
                <option value="high">{traducir('portalsupportdesk.alta_funcionalidad_importante_no_funciona')}</option>
                <option value="medium">{traducir('portalsupportdesk.media_hay_un_workaround')}</option>
                <option value="low">{traducir('portalsupportdesk.baja_problema_menor')}</option>
              </PortalSelect>
            </PortalField>
            <PortalField label={traducir('cmdb.impact')} error={campos.de('impact')}>
              <PortalSelect value={createForm.impact} onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { campos.limpiar('impact'); setCreateForm(f => ({ ...f, impact: e.target.value })) }}>
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
              body={Object.entries(routingHint).map(([k, v]) => `${nombreDeCampo(k)}: ${valorDeCampo(k, v)}`).join(' · ')}
            />
          )}

          {origenDeLosCampos && (
            <MarcaDeTraduccion origen={origenDeLosCampos} verOriginal={formularioOriginal}
              onAlternar={() => setFormularioOriginal(v => !v)} />
          )}
          {visibleDynamicFields.map((f) => (
            <PortalField key={f.id} label={(!formularioOriginal && campoDeSerie(f.id)) || textoDe(f, 'label', f.label, formularioOriginal)} required={f.required}>
              {f.type === 'select' ? (
                <PortalSelect
                  value={dynamicValues[f.id] || ''}
                  onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                >
                  <option value="">{traducir('invoices.select')}</option>
                  {(f.options || []).map(op => <option key={op} value={op}>{opcionDinamica(op)}</option>)}
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
                f.type === 'date' ? (
                  // Selector de fecha del kit (16-11-2026): el formato del idioma del portal, no el del navegador.
                  <CampoFecha
                    idioma={idioma}
                    textos={textosDeFechaDelPortal(idioma)}
                    value={dynamicValues[f.id] || ''}
                    onChange={v => setDynamicValues(prev => ({ ...prev, [f.id]: v }))}
                  />
                ) : (
                  <PortalInput
                    type="text"
                    value={dynamicValues[f.id] || ''}
                    onChange={(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                  />
                )
              )}
            </PortalField>
          ))}
        </div>
      </PortalModal>
    </div>
  )
}
