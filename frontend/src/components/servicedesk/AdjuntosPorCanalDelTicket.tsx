/**
 * AdjuntosPorCanalDelTicket — enviar un documento del ticket por su conversación
 * de WhatsApp o Slack desde la ficha del ticket (17-11-2026).
 *
 * Solo aparece si el ticket tiene una conversación de canal abierta. Usa el mismo
 * envío que la bandeja (`POST /sd/channels/conversations/{id}/attachments`): la
 * ventana de 24 h de WhatsApp, el hilo de Slack, la auditoría y los errores con
 * código (traducidos por `extractErr`) son los mismos.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Paperclip } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Input, Select } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { canalesApi } from '../../services/api/serviceDeskMercado'
import { Ventana } from './BandejaDeCanales'

export default function AdjuntosPorCanalDelTicket({ ticketId }: { ticketId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const clave = ['sd-ticket-canales', ticketId]
  const { data } = useQuery({ queryKey: clave, queryFn: () => canalesApi.delTicket(ticketId) })
  const [convId, setConvId] = useState('')
  const [documento, setDocumento] = useState('')
  const [texto, setTexto] = useState('')

  const convs = data?.conversations ?? []
  const conv = convs.find(c => c.id === convId) ?? convs[0]
  const enviar = useMutation({
    mutationFn: () => canalesApi.enviarAdjunto(conv!.id, documento, texto.trim() || undefined),
    onSuccess: () => {
      setDocumento(''); setTexto('')
      toast.success(t('sd_mercado.adjunto_enviado'))
      qc.invalidateQueries({ queryKey: clave })
      qc.invalidateQueries({ queryKey: ['sdm-conv', conv?.id] })
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!conv) return null
  const fueraDeVentana = conv.channel === 'whatsapp' && conv.whatsapp_window?.open === false
  return (
    <div className="u-stack-6">
      <div className="tkd-section-title">{t('sd_mercado.adjunto_por_canal')}</div>
      <div className="u-row-8">
        {convs.length > 1 ? (
          <Select suelto tamano="sm" aria-label={t('sd_mercado.conversaciones')} value={conv.id}
            onChange={e => setConvId(e.target.value)}
            options={convs.map(c => ({ value: c.id, label: `${etiquetaCodigo(t, 'sd_mercado.canal', c.channel)} · ${c.visitor_name || c.external_id || ''}` }))} />
        ) : (
          <span className="u-text3-xs">{etiquetaCodigo(t, 'sd_mercado.canal', conv.channel)} · {conv.visitor_name || conv.external_id}</span>
        )}
        <Ventana c={conv} />
      </div>
      {(data?.attachments.length ?? 0) === 0 ? (
        <div className="u-text3-xs">{t('sd_mercado.sin_adjuntos_del_ticket')}</div>
      ) : (
        <div className="u-row-8">
          <Select suelto tamano="sm" className="u-flex1" aria-label={t('sd_mercado.adjunto_del_ticket')} value={documento}
            placeholder={t('sd_mercado.elige_adjunto')} onChange={e => setDocumento(e.target.value)}
            options={(data?.attachments ?? []).map(a => ({ value: a.id, label: a.file_name || a.title }))} />
          <Input aria-label={t('sd_mercado.texto_del_adjunto')} placeholder={t('sd_mercado.texto_del_adjunto')} value={texto}
            maxLength={1024} onChange={e => setTexto(e.target.value)} />
          <Button size="sm" variant="secondary" icon={<Paperclip size={14} />} onClick={() => enviar.mutate()}
            loading={enviar.isPending} disabled={!documento || fueraDeVentana}>{t('sd_mercado.enviar_adjunto')}</Button>
        </div>
      )}
    </div>
  )
}
