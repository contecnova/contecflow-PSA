// Paneles auxiliares del detalle de ticket (aprobacion, sugerencia de IA, seguir y fusionar). 23-11-2026: troceado de TicketDetail sin cambio de comportamiento.
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Input, Textarea } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdApprovalsApi, ticketsApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { TICKET_LINK_SEARCH_LIMIT } from '../../constants/pagination'
import { type Aprobacion, LS, type Sugerencia, colorVar } from './TicketDetailComun'

/** Estado de la aprobación y, para quien la tiene que dar, los botones. */
export function AprobacionDelTicket({ ticket, yo, rechazando, motivo, setRechazando, setMotivo }: {
  ticket: { id: string; approval: Aprobacion | null }; yo: { id?: string; role?: string } | null
  rechazando: boolean; motivo: string; setRechazando: (v: boolean) => void; setMotivo: (v: string) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  // 19-11-2026: decidir en lugar del aprobador es de quien administra el service desk (matriz de permisos).
  const administraSd = useAuth().puede('sd.administrar')
  const a = ticket.approval
  const decidir = useMutation({
    mutationFn: (d: { decision: string; comment?: string }) => sdApprovalsApi.decide(ticket.id, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-ticket', ticket.id] })
      qc.invalidateQueries({ queryKey: ['sd-approvals-mine'] })
      setRechazando(false); setMotivo('')
      toast.success(t('sd_cfg.apr_done'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!a) return null
  const puedeDecidir = a.status === 'pending' && (a.approver_user_id === yo?.id || administraSd)
  const color = a.status === 'approved' ? COLOR.success : a.status === 'rejected' ? COLOR.danger : COLOR.warning
  const texto = a.status === 'pending' ? t('sd_cfg.apr_pending', { name: a.approver_name ?? '—' })
    : t(a.status === 'approved' ? 'sd_cfg.apr_approved' : 'sd_cfg.apr_rejected', { name: a.decided_by_name ?? '—' })
  return (
    <div role="status" className="tkd-approval" style={colorVar(color)}>
      <div className="tkd-approval__text">{texto}</div>
      {a.comment && <div className="u-text2-sm">{a.comment}</div>}
      {puedeDecidir && !rechazando && (
        <div className="u-row-8">
          <Button onClick={() => decidir.mutate({ decision: 'approved' })} loading={decidir.isPending}>{t('sd_cfg.apr_approve')}</Button>
          <Button variant="secondary" onClick={() => setRechazando(true)}>{t('sd_cfg.apr_reject')}</Button>
        </div>
      )}
      {puedeDecidir && rechazando && (
        <div className="u-stack-8">
          <label htmlFor="apr-motivo" className={LS}>{t('sd_cfg.apr_reason')}</label>
          <Textarea id="apr-motivo" aria-label={t('sd_cfg.apr_reason')} value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} autoFocus inputClassName="tkd-input" />
          <div className="u-row-8">
            <Button variant="secondary" onClick={() => setRechazando(false)}>{t('common.cancel')}</Button>
            <Button disabled={!motivo.trim()} loading={decidir.isPending}
              onClick={() => decidir.mutate({ decision: 'rejected', comment: motivo.trim() })}>{t('sd_cfg.apr_reject')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Lo que acompaña al borrador: artículos y documentos en que apoyarse. */
export function ApoyoDeLaSugerencia({ s }: { s: Sugerencia }) {
  const t = useAppT()
  return (
    <div className="ds-card tkd-card-stack">
      {s.ai_error && <div role="status" className="tkd-warning">{s.ai_error}</div>}
      {(s.kb_matches ?? []).length > 0 && (
        <div>
          <div className="tkd-ai-title">{t('sd_cfg.ai_related')}</div>
          {(s.kb_matches ?? []).map(k => <div key={k.id}><strong>{k.number}</strong> {k.title}</div>)}
        </div>
      )}
      {s.documents_configured && (
        <div>
          <div className="tkd-ai-title">{t('sd_cfg.ai_documents')}</div>
          {s.documents_error ? <div className="tkd-warning">{s.documents_error}</div>
            : (s.documents ?? []).length === 0 ? <div className="u-text3">{t('sd_cfg.ai_no_documents')}</div>
            : (s.documents ?? []).map(d => (
              <div key={d.document_id} className="tkd-mb-4">
                <strong>{d.title}</strong>
                <div className="u-text2">{d.snippet}</div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

/** Seguir el ticket (recibir sus avisos sin ser el agente) y fusionar duplicados. */
export function SeguirYFusionar({ ticketId }: { ticketId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const [numero, setNumero] = useState('')
  const [motivo, setMotivo] = useState('')
  const { data: seguidores = [] } = useQuery<{ user_id: string; user_name?: string }[]>({
    queryKey: ['sd-ticket-watchers', ticketId],
    queryFn: () => ticketsApi.watchers(ticketId).then(r => r.data),
  })
  const sigo = seguidores.some(s => s.user_id === user?.id)
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const alternar = useMutation({
    mutationFn: () => sigo ? ticketsApi.unwatch(ticketId) : ticketsApi.watch(ticketId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-ticket-watchers', ticketId] }), onError: err,
  })
  const fusionar = useMutation({
    mutationFn: async () => {
      const buscado = numero.trim().toUpperCase()
      const lista = await ticketsApi.list({ search: buscado, page_size: TICKET_LINK_SEARCH_LIMIT }).then(r => r.data)
      const duplicado = lista.find(x => x.number === buscado && x.id !== ticketId)
      if (!duplicado) throw new Error(t('sd_cfg.m_not_found'))
      await ticketsApi.mergeInto(ticketId, { merged_ticket_id: duplicado.id, reason: motivo || null })
      return buscado
    },
    onSuccess: (n: string) => { setNumero(''); setMotivo(''); qc.invalidateQueries({ queryKey: ['sd-ticket', ticketId] }); toast.success(t('sd_cfg.m_done', { n })) },
    onError: (e: unknown) => toast.error(e instanceof Error && e.message ? e.message : extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  // 23-11-2026: fusionar tickets es irreversible: pide confirmación antes de buscar y fusionar.
  const confirmarFusion = () => openConfirmGlobal({
    message: t('sd_cfg.m_confirmar_fusion', { n: numero.trim().toUpperCase() }),
    confirmLabel: t('sd_cfg.m_do'),
    danger: true,
    onConfirm: () => fusionar.mutate(),
  })
  return (
    <div className="ds-card tkd-card-stack tkd-card-stack--16">
      <div className="tkd-watch-row">
        <span className="tkd-watchers">
          <strong>{t('sd_cfg.w_followers')}:</strong> {seguidores.length ? seguidores.map(s => s.user_name).join(', ') : t('sd_cfg.w_nobody')}
        </span>
        <Button variant="secondary" onClick={() => alternar.mutate()} loading={alternar.isPending}>{sigo ? t('sd_cfg.w_unfollow') : t('sd_cfg.w_follow')}</Button>
      </div>
      <div className="u-wrap-center-8">
        <span className="u-600">{t('sd_cfg.m_title')}</span>
        <Input aria-label={t('sd_cfg.m_number')} placeholder={t('sd_cfg.m_number')} value={numero} onChange={e => setNumero(e.target.value)} className="tkd-input--merge-n" />
        <Input aria-label={t('sd_cfg.m_reason')} placeholder={t('sd_cfg.m_reason')} value={motivo} onChange={e => setMotivo(e.target.value)} className="tkd-input--merge-r" />
        <Button variant="secondary" disabled={!numero.trim()} loading={fusionar.isPending} onClick={() => confirmarFusion()}>{t('sd_cfg.m_do')}</Button>
      </div>
    </div>
  )
}
