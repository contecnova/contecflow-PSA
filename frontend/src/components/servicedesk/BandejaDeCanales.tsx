/**
 * BandejaDeCanales — conversaciones de WhatsApp, Slack y del chat en vivo del portal
 * (mejoras de mercado 16-11-2026). Las que piden una persona salen primero;
 * el agente la toma (traspaso), contesta por el canal del cliente y la cierra.
 * Cada conversación está atada a su ticket.
 *
 * Traducción en tiempo real (16-11-2026): los mensajes del cliente y de los agentes se
 * enseñan en el idioma del operador (`TextoTraducido`; los eventos del sistema no), y la
 * respuesta se puede previsualizar y corregir en el idioma del cliente (`VistaPreviaDeSalida`).
 *
 * 16-11-2026 (pasada de diseño): pestañas de filtro con <Tabs> estándar (antes
 * subrayadas y pequeñas), conversación elegida marcada con --accent, vacío con
 * icono lucide y hora en cada mensaje (fmtDateTime).
 *
 * 17-11-2026 (canales en tiempo real): va por el WebSocket de avisos
 * (`useAvisosEnVivo`): la bandeja se apunta (`channel_watch`) y recibe al momento
 * los mensajes, «escribiendo…», «leído» y traspasos; manda los suyos. Sondea
 * solo si el socket no está. Enseña cómo salió cada mensaje (plantilla, fallo,
 * fuera de ventana), la ventana de 24 h de WhatsApp y permite enviar un
 * documento del ticket por el canal.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCheck, Clock, MessagesSquare, Paperclip, Send } from 'lucide-react'
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import { Button, EmptyState, Pulsable, Section, Select, Spinner, StatusBadge, Tabs } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { canalesApi, type Conversacion as ConversacionDeCanal, type MensajeDeCanal } from '../../services/api/serviceDeskMercado'
import TextoTraducido from '../traduccion/TextoTraducido'
import VistaPreviaDeSalida, { type SalidaAlCliente } from '../traduccion/VistaPreviaDeSalida'
import { claveDeTraduccion, useConfigDeTraduccion, useMensajesTraducidos, type ElementoATraducir } from '../../hooks/useTraduccion'
import useAvisosEnVivo, { enviarPorAvisosEnVivo, type MensajeDeAvisos } from '../../hooks/useAvisosEnVivo'
import './sdMercado.css'

const ESTADO_KIND: Record<string, StatusBadgeKind> = { waiting_agent: 'warning', agent: 'success', bot: 'info', closed: 'neutral' }
const ENTREGA_KIND: Record<string, StatusBadgeKind> = { template: 'info', failed: 'danger', outside_window: 'warning' }
/** Latido de la bandeja abierta (el servidor la olvida a los 90 s sin él). */
const LATIDO_DE_BANDEJA_MS = 30_000
/** Cuánto dura el «escribiendo…» sin otro aviso, y cada cuánto se avisa como mucho. */
const ESCRIBIENDO_MS = 6000
const AVISO_DE_ESCRITURA_MS = 3000

/** Lo que llega por el WebSocket de la bandeja (`type: sd_channel`). */
interface AvisoDeCanal { event: string; conversation_id: string; who?: string; name?: string; read_at?: string; by?: string }

export default function BandejaDeCanales({ onAbrirTicket }: { onAbrirTicket: (id: string) => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const [filtro, setFiltro] = useState('waiting_agent')
  const [elegida, setElegida] = useState<string | null>(null)
  const [ultimoAviso, setUltimoAviso] = useState<AvisoDeCanal | null>(null)
  const enVivo = useAvisosEnVivo(true, useCallback((m: MensajeDeAvisos) => {
    if (m.type !== 'sd_channel' || typeof m.conversation_id !== 'string') return
    const aviso = m as unknown as AvisoDeCanal
    if (aviso.event === 'message' || aviso.event === 'status') {
      qc.invalidateQueries({ queryKey: ['sdm-convs'] })
      qc.invalidateQueries({ queryKey: ['sdm-conv', aviso.conversation_id] })
    }
    setUltimoAviso(aviso)
  }, [qc]))
  // La bandeja se apunta mientras está abierta (y al reconectar).
  useEffect(() => {
    if (!enVivo) return undefined
    enviarPorAvisosEnVivo({ type: 'channel_watch' })
    qc.invalidateQueries({ queryKey: ['sdm-convs'] })
    const id = setInterval(() => enviarPorAvisosEnVivo({ type: 'channel_watch' }), LATIDO_DE_BANDEJA_MS)
    return () => clearInterval(id)
  }, [enVivo, qc])
  const { data, isLoading } = useQuery({
    queryKey: ['sdm-convs', filtro],
    queryFn: () => canalesApi.conversaciones({ status: filtro === 'open' ? undefined : filtro, page: 1, page_size: 50 }),
    refetchInterval: enVivo ? false : POLL_FREQUENT_MS,
  })
  const items = data?.items ?? []
  return (
    <Section title={<span className="u-row-center-6"><MessagesSquare size={16} aria-hidden="true" />{t('sd_mercado.conversaciones')}</span>}
      subtitle={t('sd_mercado.conversaciones_desc')}>
      <Tabs active={filtro} onChange={id => { setFiltro(id); setElegida(null) }} ariaLabel={t('sd_mercado.conversaciones')}
        items={['waiting_agent', 'agent', 'bot', 'open', 'closed'].map(id => ({ id, label: etiquetaCodigo(t, 'sd_mercado.conv_filtro', id) }))} />
      {isLoading ? <Spinner /> : items.length === 0 ? <EmptyState icon={<MessagesSquare size={28} />} title={t('sd_mercado.sin_conversaciones')} /> : (
        <div className="sdm-grid">
          <ul className="sdm-list">
            {items.map(c => (
              <li key={c.id} className="sdm-list__item">
                <Pulsable className="u-btn-outline-sm sdm-chip u-flex1-min0 sdm-wrap" aria-pressed={elegida === c.id} onClick={() => setElegida(c.id)}>
                  {c.visitor_name || c.external_id || '—'}
                </Pulsable>
                <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.canal', c.channel)}</StatusBadge>
                <StatusBadge kind={ESTADO_KIND[c.status] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.conv_estado', c.status)}</StatusBadge>
              </li>
            ))}
          </ul>
          {elegida && <Conversacion id={elegida} onAbrirTicket={onAbrirTicket} enVivo={enVivo}
            aviso={ultimoAviso?.conversation_id === elegida ? ultimoAviso : null} />}
        </div>
      )}
    </Section>
  )
}

function Entrega({ m }: { m: MensajeDeCanal }) {
  const t = useAppT()
  if (!m.delivery_status || m.delivery_status === 'sent') return null
  return <StatusBadge kind={ENTREGA_KIND[m.delivery_status] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.entrega', m.delivery_status)}</StatusBadge>
}

function Ventana({ c }: { c: ConversacionDeCanal }) {
  const t = useAppT()
  const v = c.whatsapp_window
  if (!v) return null
  if (v.open) {
    return <span className="u-row-center-6 u-text3-xs"><Clock size={12} aria-hidden="true" />
      {t('sd_mercado.ventana_abierta').replace('{{hasta}}', v.expires_at ? fmtDateTime(v.expires_at) : '—')}</span>
  }
  return <StatusBadge kind={v.template ? 'info' : 'warning'} caps={false}>
    {t(v.template ? 'sd_mercado.ventana_cerrada_plantilla' : 'sd_mercado.ventana_cerrada')}</StatusBadge>
}

function Conversacion({ id, onAbrirTicket, enVivo, aviso }: { id: string; onAbrirTicket: (id: string) => void; enVivo: boolean; aviso: AvisoDeCanal | null }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { lang } = useAppLang()
  const [texto, setTexto] = useState('')
  const [salida, setSalida] = useState<SalidaAlCliente | null>(null)
  const [desfasada, setDesfasada] = useState(false)
  const [adjunto, setAdjunto] = useState('')
  const [clienteEscribe, setClienteEscribe] = useState(false)
  const [leidoPorCliente, setLeidoPorCliente] = useState<string | null>(null)
  const avisoDeEscritura = useRef(0)
  const { data } = useQuery({ queryKey: ['sdm-conv', id], queryFn: () => canalesApi.conversacion(id),
    refetchInterval: enVivo ? false : POLL_FREQUENT_MS })
  useEffect(() => { setTexto(''); setAdjunto(''); setClienteEscribe(false); setLeidoPorCliente(null) }, [id])
  // Avisos en vivo de esta conversación: el cliente escribe o ha leído.
  useEffect(() => {
    if (!aviso) return undefined
    if (aviso.event === 'typing' && aviso.who === 'customer') {
      setClienteEscribe(true)
      const fin = setTimeout(() => setClienteEscribe(false), ESCRIBIENDO_MS)
      return () => clearTimeout(fin)
    }
    if (aviso.event === 'message') setClienteEscribe(false)
    if (aviso.event === 'read' && aviso.by === 'customer' && aviso.read_at) setLeidoPorCliente(aviso.read_at)
    return undefined
  }, [aviso])
  // Leído por el agente: lo que el cliente escribió y el agente tiene delante.
  const ultimoDelCliente = [...(data?.messages ?? [])].reverse().find(m => m.direction === 'in')?.id
  useEffect(() => {
    if (ultimoDelCliente && document.visibilityState === 'visible') enviarPorAvisosEnVivo({ type: 'channel_read', conversation_id: id })
  }, [id, ultimoDelCliente])
  // Mensajes del cliente y de agentes que no están en el idioma del operador (o no se sabe).
  const { data: configTrad } = useConfigDeTraduccion()
  const aTraducir = useMemo<ElementoATraducir[]>(() => (data?.messages ?? [])
    .filter(m => (m.author_type === 'customer' || m.author_type === 'agent')
      && (!m.language || m.language.toLowerCase() !== lang.toLowerCase()))
    .map((m): ElementoATraducir => ({ type: 'channel_message', id: m.id })), [data?.messages, lang])
  const { porClave, isFetching: traduciendo } = useMensajesTraducidos(aTraducir, !!configTrad?.enabled)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sdm-conv', id] }); qc.invalidateQueries({ queryKey: ['sdm-convs'] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const tomar = useMutation({ mutationFn: () => canalesApi.tomar(id), onSuccess: refrescar, onError: err })
  const responder = useMutation({ mutationFn: () => canalesApi.responder(id, texto.trim(), salida), onSuccess: () => { setTexto(''); refrescar() }, onError: err })
  const enviarAdjunto = useMutation({ mutationFn: () => canalesApi.enviarAdjunto(id, adjunto), onSuccess: () => { setAdjunto(''); refrescar() }, onError: err })
  const cerrar = useMutation({ mutationFn: () => canalesApi.cerrar(id), onSuccess: refrescar, onError: err })
  const escribiendo = (valor: string) => {
    setTexto(valor)
    const ahora = Date.now()
    if (valor.trim() && ahora - avisoDeEscritura.current > AVISO_DE_ESCRITURA_MS) {
      avisoDeEscritura.current = ahora
      enviarPorAvisosEnVivo({ type: 'channel_typing', conversation_id: id })
    }
  }
  if (!data) return <Spinner />
  const c = data.conversation
  const leidoHasta = leidoPorCliente || c.client_read_at || null
  const ultimoMio = [...data.messages].reverse().find(m => m.direction === 'out' && m.author_type === 'agent')
  const leido = !!(ultimoMio?.created_at && leidoHasta && Date.parse(leidoHasta) >= Date.parse(ultimoMio.created_at))
  const adjuntables = (c.channel === 'whatsapp' || c.channel === 'slack') && (data.attachments?.length ?? 0) > 0
  return (
    <div className="ds-card sdm-card">
      <div className="sdm-card__head">
        <span>{c.visitor_name || c.external_id}</span>
        {c.ticket_id && <Pulsable className="u-btn-outline-sm" onClick={() => onAbrirTicket(c.ticket_id as string)}>{c.ticket_number}</Pulsable>}
        <Ventana c={c} />
        <span className="ds-toolbar__spacer" />
        {c.status !== 'agent' && c.status !== 'closed' && <Button size="xs" onClick={() => tomar.mutate()} loading={tomar.isPending}>{t('sd_mercado.tomar')}</Button>}
        {c.status !== 'closed' && <Button size="xs" variant="ghost" onClick={() => cerrar.mutate()} disabled={cerrar.isPending}>{t('sd_mercado.cerrar')}</Button>}
      </div>
      <div className="sdm-chat" aria-live="polite">
        {data.messages.map(m => (
          <div key={m.id} className={`sdm-chat__msg${m.direction === 'out' ? ' sdm-chat__msg--mine' : ''}`}>
            {m.author_type === 'system' ? <em>{etiquetaCodigo(t, 'sd_mercado.evento_conv', m.body)}</em> : (() => {
              const tr = porClave.get(claveDeTraduccion('channel_message', m.id))
              const pedido = aTraducir.some(a => a.id === m.id)
              return <TextoTraducido original={m.body} traduccion={tr} cargando={!tr && traduciendo && pedido} />
            })()}
            {m.attachment_document_id && (
              <div className="u-row-center-6 u-text3-xs"><Paperclip size={12} aria-hidden="true" />{m.attachment_name || t('sd_mercado.adjunto')}</div>
            )}
            <div className="u-row-center-6 u-text3-2xs">
              {etiquetaCodigo(t, 'sd_mercado.autor', m.author_type)} · {m.created_at ? fmtDateTime(m.created_at) : ''}
              <Entrega m={m} />
              {m.id === ultimoMio?.id && leido && <span className="u-row-center-6"><CheckCheck size={12} aria-hidden="true" />{t('sd_mercado.leido')}</span>}
            </div>
          </div>
        ))}
        {clienteEscribe && <div className="u-text3-xs" role="status">{t('sd_mercado.cliente_escribiendo')}</div>}
      </div>
      {c.status !== 'closed' && (
        <div className="u-row-8">
          <textarea className="ds-input u-flex1" rows={2} aria-label={t('sd_mercado.respuesta')} value={texto} onChange={e => escribiendo(e.target.value)} />
          <Button icon={<Send size={14} />} onClick={() => responder.mutate()} loading={responder.isPending} disabled={!texto.trim() || desfasada}>{t('sd_mercado.enviar')}</Button>
        </div>
      )}
      {c.status !== 'closed' && adjuntables && (
        <div className="u-row-8">
          <Select suelto tamano="sm" className="u-flex1" aria-label={t('sd_mercado.adjunto_del_ticket')} value={adjunto}
            placeholder={t('sd_mercado.elige_adjunto')} onChange={e => setAdjunto(e.target.value)}
            options={(data.attachments ?? []).map(a => ({ value: a.id, label: a.file_name || a.title }))} />
          <Button size="sm" variant="secondary" icon={<Paperclip size={14} />} onClick={() => enviarAdjunto.mutate()}
            loading={enviarAdjunto.isPending} disabled={!adjunto}>{t('sd_mercado.enviar_adjunto')}</Button>
        </div>
      )}
      {c.status !== 'closed' && (
        <VistaPreviaDeSalida key={id} contextType="conversation" contextId={id} texto={texto}
          onChange={(s, e) => { setSalida(s); setDesfasada(e.desfasada) }} />
      )}
    </div>
  )
}
