/**
 * BandejaDeCanales — conversaciones de WhatsApp y del chat en vivo del portal
 * (mejoras de mercado 16-11-2026). Las que piden una persona salen primero;
 * el agente la toma (traspaso), contesta por el canal del cliente y la cierra.
 * Cada conversación está atada a su ticket.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessagesSquare, Send } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import { Button, EmptyState, Section, Spinner, StatusBadge, Tabs } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { canalesApi } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

const ESTADO_KIND: Record<string, StatusBadgeKind> = { waiting_agent: 'warning', agent: 'success', bot: 'info', closed: 'neutral' }

export default function BandejaDeCanales({ onAbrirTicket }: { onAbrirTicket: (id: string) => void }) {
  const t = useAppT()
  const [filtro, setFiltro] = useState('waiting_agent')
  const [elegida, setElegida] = useState<string | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['sdm-convs', filtro],
    queryFn: () => canalesApi.conversaciones({ status: filtro === 'open' ? undefined : filtro, page: 1, page_size: 50 }),
    refetchInterval: POLL_FREQUENT_MS,
  })
  const items = data?.items ?? []
  return (
    <Section title={<span className="u-row-center-6"><MessagesSquare size={16} aria-hidden="true" />{t('sd_mercado.conversaciones')}</span>}
      subtitle={t('sd_mercado.conversaciones_desc')}>
      <Tabs variant="underline" size="sm" active={filtro} onChange={id => { setFiltro(id); setElegida(null) }} ariaLabel={t('sd_mercado.conversaciones')}
        items={['waiting_agent', 'agent', 'bot', 'open', 'closed'].map(id => ({ id, label: etiquetaCodigo(t, 'sd_mercado.conv_filtro', id) }))} />
      <div className="u-mb-12" />
      {isLoading ? <Spinner /> : items.length === 0 ? <EmptyState title={t('sd_mercado.sin_conversaciones')} /> : (
        <div className="sdm-grid">
          <ul className="sdm-list">
            {items.map(c => (
              <li key={c.id} className="sdm-list__item">
                <button type="button" className="u-btn-outline-sm u-flex1-min0 sdm-wrap" aria-pressed={elegida === c.id} onClick={() => setElegida(c.id)}>
                  {c.visitor_name || c.external_id || '—'}
                </button>
                <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.canal', c.channel)}</StatusBadge>
                <StatusBadge kind={ESTADO_KIND[c.status] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.conv_estado', c.status)}</StatusBadge>
              </li>
            ))}
          </ul>
          {elegida && <Conversacion id={elegida} onAbrirTicket={onAbrirTicket} />}
        </div>
      )}
    </Section>
  )
}

function Conversacion({ id, onAbrirTicket }: { id: string; onAbrirTicket: (id: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [texto, setTexto] = useState('')
  const { data } = useQuery({ queryKey: ['sdm-conv', id], queryFn: () => canalesApi.conversacion(id), refetchInterval: POLL_FREQUENT_MS })
  useEffect(() => { setTexto('') }, [id])
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sdm-conv', id] }); qc.invalidateQueries({ queryKey: ['sdm-convs'] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const tomar = useMutation({ mutationFn: () => canalesApi.tomar(id), onSuccess: refrescar, onError: err })
  const responder = useMutation({ mutationFn: () => canalesApi.responder(id, texto.trim()), onSuccess: () => { setTexto(''); refrescar() }, onError: err })
  const cerrar = useMutation({ mutationFn: () => canalesApi.cerrar(id), onSuccess: refrescar, onError: err })
  if (!data) return <Spinner />
  const c = data.conversation
  return (
    <div className="ds-card sdm-card">
      <div className="sdm-card__head">
        <span>{c.visitor_name || c.external_id}</span>
        {c.ticket_id && <button type="button" className="u-btn-outline-sm" onClick={() => onAbrirTicket(c.ticket_id as string)}>{c.ticket_number}</button>}
        <span className="ds-toolbar__spacer" />
        {c.status !== 'agent' && c.status !== 'closed' && <Button size="xs" onClick={() => tomar.mutate()} loading={tomar.isPending}>{t('sd_mercado.tomar')}</Button>}
        {c.status !== 'closed' && <Button size="xs" variant="ghost" onClick={() => cerrar.mutate()} disabled={cerrar.isPending}>{t('sd_mercado.cerrar')}</Button>}
      </div>
      <div className="sdm-chat" aria-live="polite">
        {data.messages.map(m => (
          <div key={m.id} className={`sdm-chat__msg${m.direction === 'out' ? ' sdm-chat__msg--mine' : ''}`}>
            {m.author_type === 'system' ? <em>{etiquetaCodigo(t, 'sd_mercado.evento_conv', m.body)}</em> : m.body}
            <div className="u-text3-2xs">{etiquetaCodigo(t, 'sd_mercado.autor', m.author_type)} · {m.created_at ? fmtDate(m.created_at) : ''}</div>
          </div>
        ))}
      </div>
      {c.status !== 'closed' && (
        <div className="u-row-8">
          <textarea className="ds-input u-flex1" rows={2} aria-label={t('sd_mercado.respuesta')} value={texto} onChange={e => setTexto(e.target.value)} />
          <Button icon={<Send size={14} />} onClick={() => responder.mutate()} loading={responder.isPending} disabled={!texto.trim()}>{t('sd_mercado.enviar')}</Button>
        </div>
      )}
    </div>
  )
}
