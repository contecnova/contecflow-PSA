/**
 * TicketDetail — ficha del ticket (panel lateral del Service Desk).
 *
 * 16-11-2026 (pasada de diseño): acciones rápidas, editar y resolver con
 * `Button` e icono lucide (eran botones propios con ▶ ✓ ↑ ↺ ⏸ ✂ ✕ ✏); cerrar
 * con icono X; sin emojis en los tipos y prioridades del editor; el
 * historial y los vínculos con el nombre del campo y los valores traducidos
 * (antes `status: in_progress → resolved`). La traducción en tiempo real
 * (TextoTraducido, VistaPreviaDeSalida) queda igual.
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import TextoTraducido from '../../components/traduccion/TextoTraducido'
import VistaPreviaDeSalida, { type SalidaAlCliente } from '../../components/traduccion/VistaPreviaDeSalida'
import { claveDeTraduccion, useConfigDeTraduccion, useMensajesTraducidos, type ElementoATraducir } from '../../hooks/useTraduccion'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { ArrowUpCircle, CheckCircle2, ChevronDown, ChevronRight, Pause, Pencil, Play, Scissors, Sparkles, Undo2, X, Zap } from 'lucide-react'
import { Button, Spinner, Modal, Pulsable, Select, Checkbox, Input, Textarea, IconButton } from '../../components/ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import DocumentsPanel from '../../components/DocumentsPanel'
import DocumentosDeFicha from '../../components/conectores/DocumentosDeFicha'
import LeccionesDeOrigen from '../../components/lecciones/LeccionesDeOrigen'
import PanelIaDelTicket from '../../components/servicedesk/PanelIaDelTicket'
import CorregirAsignacion from '../../components/asignacion-ia/CorregirAsignacion'
import PanelTicketAPr from '../../components/ticket-a-pr/PanelTicketAPr'
import EstadoDeCicloDeVida from '../../components/servicedesk/EstadoDeCicloDeVida'
import AvisoDeColision from '../../components/servicedesk/AvisoDeColision'
import ContextoDelCliente from '../../components/servicedesk/ContextoDelCliente'
import AdjuntosPorCanalDelTicket from '../../components/servicedesk/AdjuntosPorCanalDelTicket'
import { RecursoDelTicket } from '../../components/alm/EnlaceTicketRecurso'
import { COLOR } from '../../constants/theme'
import { almExtApi, ticketsApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { PBadge, SBadge, fmtDate, fmtMinutes } from './sdUtils'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './TicketDetail.css'
import { LS, type Sugerencia, type TicketComment, type TicketHistoryEntry, type TicketLink, type UcContract, colorVar, lineaDeHistorial } from './TicketDetailComun'
import { CannedResponsePicker, SplitTicketModal, TicketEditModal } from './TicketDetailModales'
import { ApoyoDeLaSugerencia, AprobacionDelTicket, SeguirYFusionar } from './TicketDetailPaneles'
import { ESTADO_TICKET, ESTADOS_TICKET_RESUELTOS, ESTADOS_TICKET_TERMINADOS } from '../../constants/estadosDeTicket'

// ── TicketDetail (main) ────────────────────────────────────────────────────────
export default function TicketDetail({ ticketId, onClose, embedded = false }: { ticketId: string | null | undefined; onClose: () => void; embedded?: boolean }) {
  const t = useAppT()
  const puedeVerTicketAPr = useAuth().puede('ticket_pr.ver')
  const qc = useQueryClient()
  const toast = useToast()
  const [commentText, setCommentText] = useState('')
  // Nota interna: no la ve el solicitante ni se le envia por correo.
  const [notaInterna, setNotaInterna] = useState(false)
  const [showCanned, setShowCanned] = useState(false)
  const [timeMin, setTimeMin] = useState('')
  const [timeUnit, setTimeUnit] = useState('minutes')
  const [facturable, setFacturable] = useState(false)
  const [editAssign, setEditAssign] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showSplit, setShowSplit] = useState(false)
  // Resolver pide el texto: es lo que recibe el solicitante en el correo.
  const [resolviendo, setResolviendo] = useState(false)
  const [textoResolucion, setTextoResolucion] = useState('')
  const { user: yo } = useAuth()
  const [sugerencia, setSugerencia] = useState<Sugerencia | null>(null)
  const [rechazando, setRechazando] = useState(false)
  const [motivo, setMotivo] = useState('')
  // Traducción en tiempo real (16-11-2026): lo que recibirá el cliente (vista previa revisada).
  const [salida, setSalida] = useState<SalidaAlCliente | null>(null)
  const [salidaDesfasada, setSalidaDesfasada] = useState(false)
  const { lang } = useAppLang()

  const { data: ticket, isLoading } = useQuery({
    queryKey: ['sd-ticket', ticketId],
    queryFn: () => ticketsApi.get(ticketId).then(r => r.data),
    enabled: !!ticketId,
    refetchInterval: POLL_FREQUENT_MS,
  })

  // Traducción en tiempo real: ticket (título y descripción) y comentarios, también las
  // notas internas (entre operadores sí se traducen; jamás salen al cliente), en una
  // sola petición. Solo lo que no está ya en el idioma de la interfaz (o no se sabe), y
  // el ticket siempre que lo haya creado el sistema (se pinta en el idioma de quien mira).
  const { data: configTrad } = useConfigDeTraduccion()
  const traduce = !!configTrad?.enabled
  const aTraducir = useMemo<ElementoATraducir[]>(() => {
    if (!ticket) return []
    const otroIdioma = (l?: string | null) => !l || l.toLowerCase() !== lang.toLowerCase()
    const items: ElementoATraducir[] = []
    if (ticket.system_template || (traduce && otroIdioma(ticket.language))) items.push({ type: 'ticket', id: ticket.id })
    if (traduce) {
      for (const c of ticket.comments ?? []) if (otroIdioma(c.language)) items.push({ type: 'ticket_comment', id: c.id })
    }
    return items
  }, [ticket, lang, traduce])
  const { porClave: traducciones, isFetching: traduciendo } = useMensajesTraducidos(aTraducir, aTraducir.length > 0)
  const pedidos = useMemo(() => new Set(aTraducir.map(i => `${i.type}:${i.id}`)), [aTraducir])
  /** La traducción de un campo y si se está esperando. */
  const tradDe = (type: 'ticket' | 'ticket_comment', id: string, field = 'body') => {
    const tr = traducciones.get(claveDeTraduccion(type, id, field))
    return { traduccion: tr, cargando: !tr && traduciendo && pedidos.has(`${type}:${id}`) }
  }
  const { data: users = [] } = useListaDeUsuarios()
  const { data: links = [] } = useQuery<TicketLink[]>({
    queryKey: ['sd-ticket-links', ticketId],
    queryFn: () => ticketsApi.links(ticketId).then(r => r.data),
    enabled: !!ticketId,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] })
    qc.invalidateQueries({ queryKey: ['sd-tickets'] })
  }

  // UC: solo hace falta mientras se espera a un tercero (o si ya hay contrato).
  const conUc = ticket?.status === 'pending_third' || !!ticket?.uc_contract_id
  const { data: contratosUc = [] } = useQuery({
    queryKey: ['alm-contracts'],
    queryFn: () => almExtApi.contracts().then(r => r.data ?? []),
    enabled: conUc,
    select: (cs: UcContract[]) => cs.filter(c => (c.resolution_hours > 0 || c.response_hours > 0) && c.status === 'active'),
  })
  const { mutate: anotarRespuesta, isPending: anotando } = useMutation({
    mutationFn: () => ticketsApi.update(ticketId, { uc_vendor_responded: true }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: elegirUc } = useMutation({
    mutationFn: (id: string) => ticketsApi.update(ticketId, { uc_contract_id: id }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    // Respuesta pública con vista previa revisada: el cliente recibe `client_text` y
    // `body` queda como original del agente. Las notas internas no llevan nada de esto.
    mutationFn: () => ticketsApi.comment(ticketId, {
      body: commentText, is_public: !notaInterna,
      ...(!notaInterna && salida ? salida : {}),
    }),
    onSuccess: () => { invalidate(); setCommentText(''); toast.success(t('service_desk.comment_added')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: suggestReply, isPending: suggestingReply } = useMutation({
    mutationFn: () => ticketsApi.aiSuggest(ticketId, { content: commentText }),
    onSuccess: res => {
      const datos = res.data
      setSugerencia(datos ?? null)
      const draft = datos?.draft || ''
      // Sin IA se dice, y los articulos y documentos se ensenan igual.
      if (!draft) { toast.error(datos?.ai_error || t('common.error')); return }
      setCommentText(prev => prev ? `${prev}\n\n${draft}` : draft)
    },
    onError: e => toast.error(extractErr(e, t('ticketdetail.error_sugerir'))),
  })
  const { mutate: logTime, isPending: loggingTime } = useMutation({
    mutationFn: () => ticketsApi.timelog(ticketId, { minutes: Number(timeMin), unit: timeUnit, billable: facturable }),
    onSuccess: res => {
      invalidate(); setTimeMin('')
      // Dice si el tiempo llegó a los partes o por qué no: sin eso, el agente
      // daba por imputado lo que se había quedado en el ticket.
      const r = res.data
      if (r?.timesheet === 'created') toast.success(t('sd_cfg.time_to_timesheet', { h: r.hours ?? 0 }))
      else if (r?.timesheet === 'skipped') toast.info(t('sd_cfg.time_not_to_timesheet', { reason: r.reason ?? '' }))
      else toast.success(t('ticketdetail.n_min', { n: timeMin }))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: restorePending, isPending: restoringPending } = useMutation({
    mutationFn: () => ticketsApi.restorePending(ticketId),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.qa_back_ok')) },
    onError: e => toast.error(extractErr(e, t('service_desk.qa_back_error'))),
  })
  const { mutate: updateTicket } = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketsApi.update(ticketId, data),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_updated')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: escalate } = useMutation({
    mutationFn: () => ticketsApi.escalate(ticketId),
    onSuccess: () => { invalidate(); toast.success(t('service_desk.ticket_escalated')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: pauseSLA } = useMutation({
    mutationFn: () => ticketsApi.slaPause(ticketId, { note: t('ticketdetail.nota_pausa_sla') }),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_paused')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: resumeSLA } = useMutation({
    mutationFn: () => ticketsApi.slaResume(ticketId),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-sla-events'] }); toast.success(t('service_desk.sla_resumed')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!ticketId) return null

  const colorSla = (estado?: string) => estado === 'breached' ? COLOR.danger
    : estado === 'at_risk' ? COLOR.warning : estado === 'paused' ? 'var(--text-2)' : COLOR.success
  const textoSla = (estado?: string) => estado ? t(`sd_cfg.sla_${estado}`) : ''
  const slaColor = colorSla(ticket?.sla_resolution_status)

  return (
    <div className={embedded ? 'tkd-panel tkd-panel--embedded' : 'tkd-panel tkd-panel--floating'}>
      {/* Header */}
      <div className="tkd-head">
        <div className="tkd-head__top">
          <div>
            {isLoading ? <Spinner /> : <>
              <div className="tkd-head__meta">
                <span className="tkd-head__number">{ticket?.number}</span>
                <span className="u-text3-xs">{ticket?.type_label}</span>
                <PBadge v={ticket?.priority} />
                <SBadge v={ticket?.status ?? ''} />
              </div>
              {ticket && <TextoTraducido className="tkd-head__title" original={ticket.title} {...tradDe('ticket', ticket.id, 'title')} />}
            </>}
          </div>
          <div className="tkd-head__tools">
            {ticket && (
              <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={() => setShowEdit(true)}>{t('common.edit')}</Button>
            )}
            <IconButton variante="caja" onClick={onClose} ariaLabel={t('ticketdetail.cerrar_detalle')} title={t('ticketdetail.cerrar_detalle')}><X size={18} aria-hidden="true" /></IconButton>
          </div>
        </div>
        {ticket && (
          <div className="tkd-qa-row">
            {!ESTADOS_TICKET_TERMINADOS.includes(ticket.status) && <>
              {ticket.status !== ESTADO_TICKET.enCurso && (
                <Button size="sm" variant="secondary" icon={<Play size={13} />} onClick={() => updateTicket({ status: ESTADO_TICKET.enCurso })}>{t('sd_cfg.qa_start')}</Button>
              )}
              <Button size="sm" icon={<CheckCircle2 size={13} />} onClick={() => { setTextoResolucion(ticket.resolution || ''); setResolviendo(true) }}>{t('sd_cfg.qa_resolve')}</Button>
              <Button size="sm" variant="secondary" icon={<ArrowUpCircle size={13} />} onClick={() => escalate()}>{t('sd_cfg.qa_escalate')}</Button>
              {(ticket.status === 'pending_client' || ticket.status === 'pending_third') && (
                <Button size="sm" variant="secondary" icon={<Undo2 size={13} />} onClick={() => restorePending()} disabled={restoringPending}>{t('service_desk.qa_back_to_previous')}</Button>
              )}
              {(ticket.sla_resolution_status === 'paused' || ticket.sla_response_status === 'paused')
                ? <Button size="sm" variant="secondary" icon={<Play size={13} />} onClick={() => resumeSLA()}>{t('service_desk.qa_resume_sla')}</Button>
                : <Button size="sm" variant="secondary" icon={<Pause size={13} />} onClick={() => pauseSLA()}>{t('service_desk.qa_pause_sla')}</Button>}
              <Button size="sm" variant="secondary" icon={<Scissors size={13} />} onClick={() => setShowSplit(true)}>{t('service_desk.qa_split')}</Button>
            </>}
            {ticket.status === 'resolved' && (
              <Button size="sm" variant="secondary" icon={<X size={13} />} onClick={() => updateTicket({ status: ESTADO_TICKET.cerrado })}>{t('ticketdetail.cerrar')}</Button>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      <div className="tkd-body">
        {isLoading ? <div className="tkd-loading"><Spinner /></div> : ticket && <>
          {/* Petición madre y tareas de cumplimiento */}
          {ticket.parent && (
            <div className="tkd-parent">
              <Link to={`/service-desk?ticket=${ticket.parent.id}`} className="u-accent">{t('sd_cfg.ff_parent', { n: ticket.parent.number })}</Link>
            </div>
          )}
          {(ticket.fulfillment_tasks ?? []).length > 0 && (
            <div className="ds-card tkd-ff">
              <div className="tkd-ff__title">{t('sd_cfg.ff_tasks')}</div>
              {ticket.fulfillment_tasks.map(ft => (
                <div key={ft.id} className="tkd-ff__row">
                  <Link to={`/service-desk?ticket=${ft.id}`} className="tkd-ff__link">{ft.number}</Link>
                  <span className="u-flex1">{ft.title.split(' · ').slice(1).join(' · ') || ft.title}</span>
                  <span className="u-text3">{ft.group_name}{ft.assignee_name ? ` · ${ft.assignee_name}` : ''}</span>
                  {ft.sla_resolution_due && <span className={ft.sla_breached ? 'u-danger u-text3-xs' : 'u-text3-xs'}>{fmtDate(ft.sla_resolution_due)}</span>}
                  <SBadge v={ft.status} />
                </div>
              ))}
              {(ticket.fulfillment_plan ?? []).filter(p => p.status === 'planned').map(p => (
                <div key={p.task_id} className="tkd-ff__row">
                  <span className="u-text3-xs">{t('sd_mercado.etapa_n', { n: p.stage })}</span>
                  <span className="u-flex1">{p.title}</span>
                  <span className="u-text3-xs">{t('sd_mercado.tarea_prevista')}</span>
                </div>
              ))}
            </div>
          )}
          {/* Aprobación del catálogo */}
          {ticket.approval && (
            <AprobacionDelTicket ticket={ticket} yo={yo} rechazando={rechazando} motivo={motivo}
              setRechazando={setRechazando} setMotivo={setMotivo} />
          )}
          {/* SLA status */}
          <div className="tkd-sla" style={colorVar(slaColor)}>
            <div>
              <div className="tkd-eyebrow">{t('service_desk.detail_sla_response')}</div>
              <div className="tkd-sla__value" style={colorVar(colorSla(ticket.sla_response_status))}>
                {textoSla(ticket.sla_response_status)} · {fmtDate(ticket.sla_response_due)}
              </div>
            </div>
            <div>
              <div className="tkd-eyebrow">{t('service_desk.detail_sla_resolution')}</div>
              <div className="tkd-sla__value">
                {textoSla(ticket.sla_resolution_status)} · {fmtDate(ticket.sla_resolution_due)}
              </div>
            </div>
            {ticket.ola_due && (
              <div className="u-col-full">
                <div className="tkd-eyebrow">{t('sd_cfg.ola_of_queue', { group: ticket.assigned_group_name ?? '' })}</div>
                <div className="tkd-sla__value" style={colorVar(colorSla(ticket.ola_breached ? 'breached' : 'ok'))}>
                  {textoSla(ticket.ola_breached ? 'breached' : 'ok')} · {fmtDate(ticket.ola_due)}
                </div>
              </div>
            )}
            {conUc && (
              <div className="u-col-full">
                <label htmlFor="uc-contrato" className="tkd-eyebrow tkd-eyebrow--label">
                  {t('sd_cfg.uc_of_vendor')}
                </label>
                {ticket.uc_response_due && (
                  <div className="tkd-sla__value tkd-sla__value--mb tkd-sla__uc"
                    style={colorVar(ticket.uc_vendor_responded_at ? 'var(--text-2)' : colorSla(ticket.uc_response_breached ? 'breached' : 'ok'))}>
                    <span>{t('sd_cfg.uc_response')}: {ticket.uc_vendor_responded_at
                      ? t('sd_cfg.uc_responded_at', { fecha: fmtDate(ticket.uc_vendor_responded_at) })
                      : `${textoSla(ticket.uc_response_breached ? 'breached' : 'ok')} · ${fmtDate(ticket.uc_response_due)}`}</span>
                    {!ticket.uc_vendor_responded_at && ticket.status === 'pending_third' && (
                      <Button size="xs" variant="secondary" onClick={() => anotarRespuesta()} disabled={anotando}>{t('sd_cfg.uc_vendor_responded')}</Button>
                    )}
                  </div>
                )}
                {ticket.uc_due && (
                  <div className="tkd-sla__value tkd-sla__value--mb" style={colorVar(colorSla(ticket.uc_breached ? 'breached' : 'ok'))}>
                    {t('sd_cfg.uc_resolution')}: {textoSla(ticket.uc_breached ? 'breached' : 'ok')} · {fmtDate(ticket.uc_due)}
                  </div>
                )}
                <Select suelto placeholder={false} tamano="sm" id="uc-contrato" value={ticket.uc_contract_id ?? ''} onChange={e => e.target.value && elegirUc(e.target.value)}
                  className="tkd-sel">
                  <option value="">{contratosUc.length ? t('sd_cfg.uc_choose') : t('sd_cfg.uc_none')}</option>
                  {contratosUc.map(c => (
                    <option key={c.id} value={c.id}>{c.vendor_name ? `${c.vendor_name} · ` : ''}{c.title} ({[c.response_hours && t('sd_cfg.uc_resp_h', { n: c.response_hours }), c.resolution_hours && t('sd_cfg.uc_hours', { n: c.resolution_hours })].filter(Boolean).join(' / ')})</option>
                  ))}
                </Select>
              </div>
            )}
          </div>

          {/* Info grid */}
          <div className="tkd-facts">
            {[
              [t('service_desk.detail_requester'), ticket.requester_name || '—'],
              [t('common.assigned_to'), ticket.assigned_to_name || t('service_desk.unassigned')],
              [t('service_desk.detail_group'), ticket.assigned_group_name || '—'],
              [t('service_desk.detail_project'), ticket.project_name || '—'],
              [t('service_desk.detail_ci'), ticket.ci_name || '—'],
              [t('service_desk.detail_time_spent'), fmtMinutes(ticket.time_spent_minutes)],
              [t('service_desk.detail_created'), fmtDate(ticket.created_at)],
              [t('service_desk.detail_updated'), fmtDate(ticket.updated_at)],
            ].map(([label, val]) => (
              <div key={label} className="tkd-fact">
                <div className="tkd-eyebrow">{label}</div>
                <div className="tkd-fact__value">{val}</div>
              </div>
            ))}
          </div>

          {/* Reasignar */}
          <div className="u-mb-16">
            <Pulsable aria-expanded={editAssign} onClick={() => setEditAssign(e => !e)} className="tkd-link-btn">
              {editAssign ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />} {t('ticketdetail.reasignar')}
            </Pulsable>
            {/* 23-11-2026: la IA eligió mal → persona correcta (aprende el motor) y se reasigna. */}
            <CorregirAsignacion itemType="ticket" itemId={ticketId} asignadoActual={ticket.assigned_to_id}
              onCorregida={async uid => { await ticketsApi.update(ticketId, { assigned_to_user_id: uid }); invalidate() }} />
            {editAssign && (
              <div className="tkd-assign-row">
                <Select suelto placeholder={false} aria-label={t('service_desk.detail_select_agent')} value="" onChange={e => e.target.value && updateTicket({ assigned_to_user_id: e.target.value })} className="tkd-input--flex1">
                  <option value="" disabled>{t('service_desk.detail_select_agent')}</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </Select>
              </div>
            )}
          </div>

          {/* Descripción */}
          <div className="u-mb-20">
            <div className="tkd-section-title">{t('common.description')}</div>
            <TextoTraducido className="tkd-text-box" original={ticket.description ?? ''} {...tradDe('ticket', ticket.id, 'description')} />
          </div>

          {ticket.dynamic_fields && Object.keys(ticket.dynamic_fields).length > 0 && (
            <div className="u-mb-20">
              <div className="tkd-section-title">
                {t('ticketdetail.campos_dinamicos')}
              </div>
              <div className="u-grid2-10">
                {Object.entries(ticket.dynamic_fields).map(([k, v]) => (
                  <div key={k} className="tkd-fact">
                    <div className="tkd-eyebrow">{k}</div>
                    <div className="tkd-fact__value tkd-fact__value--pre">{String(v ?? '—')}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ticket.resolution && (
            <div className="u-mb-20">
              <div className="tkd-section-title tkd-section-title--ok">{t('service_desk.edit_resolution')}</div>
              <div className="tkd-resolution">
                {ticket.resolution}
              </div>
            </div>
          )}

          {links.length > 0 && (
            <div className="u-mb-20">
              <div className="tkd-section-title">
                {t('service_desk.detail_linked')} ({links.length})
              </div>
              {links.map(lk => (
                <div key={lk.link_id} className="tkd-link-row">
                  <span className="tkd-link-row__type">{etiquetaCodigo(t, 'ticketdetail.enlace', lk.link_type)}</span>
                  <span className="tkd-link-row__number">{lk.ticket_number}</span>
                  <span className="tkd-link-row__title">{lk.ticket_title}</span>
                  <SBadge v={lk.ticket_status} />
                </div>
              ))}
            </div>
          )}

          <AvisoDeColision ticketId={ticket.id} escribiendo={commentText.trim().length > 0} />
          <EstadoDeCicloDeVida ticketId={ticket.id} onCambio={invalidate} />
          <ContextoDelCliente ticketId={ticket.id} />
          <PanelIaDelTicket ticketId={ticket.id} tieneGrupo={!!ticket.assigned_group_id} onCambio={invalidate} />
          {/* «Del ticket al PR» (migración 203): agente de código que propone el arreglo como PR. */}
          {puedeVerTicketAPr && <PanelTicketAPr tipo="ticket" id={ticket.id} />}

          {/* Licencias y hardware, fase 4: el equipo o la licencia del ticket. */}
          <RecursoDelTicket ticketId={ticket.id} />

          {/* Time logging */}
          <div className="u-mb-20">
            <div className="tkd-section-title">{t('service_desk.detail_log_time')}</div>
            <div className="u-row-8">
              <Input type="number" aria-label={t('service_desk.detail_time_spent')} placeholder={t('service_desk.detail_time_spent')} value={timeMin} onChange={e => setTimeMin(e.target.value)} className="tkd-input--flex1" />
              <Select suelto placeholder={false} aria-label={t('ticketdetail.unidad')} value={timeUnit} onChange={e => setTimeUnit(e.target.value)} className="tkd-input--unit">
                <option value="minutes">{t('ticketdetail.unidad_min')}</option>
                <option value="hours">{t('ticketdetail.unidad_h')}</option>
                <option value="days">{t('ticketdetail.unidad_d')}</option>
              </Select>
              <Checkbox className="tkd-check tkd-check--nowrap" checked={facturable} onChange={setFacturable} aria-label={t('sd_cfg.time_billable')} label={t('sd_cfg.time_billable')} />
              <Button onClick={() => logTime()} disabled={loggingTime || !timeMin} loading={loggingTime}>{t('service_desk.detail_add_btn')}</Button>
            </div>
          </div>

          {/* Comments */}
          <div className="u-mb-20">
            <div className="tkd-section-title tkd-section-title--12">
              {t('ticketdetail.comentarios', { n: (ticket.comments || []).length })}
            </div>
            <div className="tkd-comments">
              {(ticket.comments || []).map((c: TicketComment) => (
                <div key={c.id} className="tkd-comment">
                  <div className="tkd-comment__head">
                    <span className="u-text1-sm-600">
                      {c.author_name}
                      {c.is_public === false && <span className="tkd-comment__internal">{t('service_desk.internal_note')}</span>}
                    </span>
                    <span className="u-text3-xs">
                      {fmtDate(c.created_at)}
                      {c.edited_at && !c.retracted_at && <> · {t('ticketdetail.comentario_editado')}</>}
                    </span>
                  </div>
                  {c.retracted_at
                    ? <em className="tkd-comment__body u-text3-xs">{t('ticketdetail.comentario_retirado')}</em>
                    : <TextoTraducido className="tkd-comment__body" original={c.body} {...tradDe('ticket_comment', c.id)} />}
                </div>
              ))}
            </div>
            <div className="tkd-relative">
              {showCanned && (
                <CannedResponsePicker
                  onSelect={text => setCommentText(prev => prev ? prev + '\n\n' + text : text)}
                  onClose={() => setShowCanned(false)}
                />
              )}
              <Textarea aria-label={t('service_desk.detail_send_comment')} placeholder={t('service_desk.detail_send_comment')} value={commentText} onChange={e => setCommentText(e.target.value)} rows={3} className="tkd-input--comment" />
            </div>
            <div className="tkd-tools">
              <Pulsable aria-pressed={showCanned} onClick={() => setShowCanned(s => !s)}
                className="tkd-tool">
                <Zap size={13} aria-hidden="true" />{t('ticketdetail.respuestas_rapidas')}
              </Pulsable>
              <Pulsable onClick={() => suggestReply()} disabled={suggestingReply}
                className="tkd-tool">
                <Sparkles size={13} aria-hidden="true" />{suggestingReply ? t('service_desk.detail_ai_generating') : t('sd_cfg.ai_suggest')}
              </Pulsable>
            </div>
            {sugerencia && <ApoyoDeLaSugerencia s={sugerencia} />}
            <Checkbox className="tkd-check tkd-check--mb" aria-label={t('service_desk.internal_note')} checked={notaInterna} onChange={setNotaInterna} label={t('service_desk.internal_note')} />
            {/* Solo respuestas públicas: las notas internas no salen nunca al cliente. */}
            {!notaInterna && (
              <VistaPreviaDeSalida key={ticket.id} contextType="ticket" contextId={ticket.id} texto={commentText}
                onChange={(s, e) => { setSalida(s); setSalidaDesfasada(e.desfasada) }} />
            )}
            <Button onClick={() => addComment()} disabled={commenting || !commentText || (!notaInterna && salidaDesfasada)} loading={commenting} className="tkd-full">
              {t('service_desk.detail_send_comment')}
            </Button>
          </div>

          <SeguirYFusionar ticketId={ticketId} />
          <div className="u-mb-20"><DocumentsPanel ticketId={ticketId} /></div>
          <div className="u-mb-20"><AdjuntosPorCanalDelTicket ticketId={ticketId} /></div>
          <div className="u-mb-20"><DocumentosDeFicha ficha="ticket" id={ticketId} sugerir /></div>
          <div className="u-mb-20"><LeccionesDeOrigen origen="ticket" id={ticketId} cerrado={ESTADOS_TICKET_RESUELTOS.includes(String(ticket?.status))} /></div>

          {(ticket.history || []).length > 0 && (
            <div>
              <div className="tkd-section-title tkd-section-title--10">{t('service_desk.detail_history')}</div>
              <div className="u-stack-6">
                {ticket.history.slice(-8).reverse().map((h: TicketHistoryEntry, i: number) => (
                  <div key={i} className="tkd-hist">
                    <span className="tkd-hist__text">{lineaDeHistorial(t, h)}</span>
                    <span className="tkd-hist__date">{fmtDate(h.changed_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>}
      </div>

      {showEdit && ticket && (
        <TicketEditModal
          ticket={ticket}
          onClose={() => setShowEdit(false)}
          onSaved={() => { invalidate(); setShowEdit(false); toast.success(t('service_desk.ticket_updated')) }}
        />
      )}
      {resolviendo && ticket && (
        <Modal open title={`${t('sd_cfg.qa_resolve')} ${ticket.number}`} onClose={() => setResolviendo(false)}>
          <div className="u-stack-12">
            <label htmlFor="sd-resolucion" className={LS}>{t('sd_cfg.qa_resolution')}</label>
            <Textarea id="sd-resolucion" aria-label={t('sd_cfg.qa_resolution')} value={textoResolucion} onChange={e => setTextoResolucion(e.target.value)} rows={5} autoFocus inputClassName="tkd-input" />
            <div className="u-text3-xs">{t('sd_cfg.qa_resolution_hint')}</div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setResolviendo(false)}>{t('common.cancel')}</Button>
              <Button disabled={!textoResolucion.trim()} onClick={() => {
                updateTicket({ status: 'resolved', resolution: textoResolucion.trim() })
                setResolviendo(false)
              }} icon={<CheckCircle2 size={14} />}>{t('sd_cfg.qa_resolve')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {showSplit && ticket && (
        <SplitTicketModal
          ticket={ticket}
          onClose={() => setShowSplit(false)}
          onCreated={() => { invalidate(); qc.invalidateQueries({ queryKey: ['sd-tickets'] }) }}
        />
      )}
    </div>
  )
}
