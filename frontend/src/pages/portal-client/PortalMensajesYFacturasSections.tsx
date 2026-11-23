// Secciones de mensajes y facturas del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Receipt, MessageSquare, CheckCircle2, MessagesSquare, FileQuestion } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate, fmtDateTime } from '../../utils/helpers'
import { ClientGovernedConversationInbox } from '../../components/portal/GovernedConversations'
import { CLIENT_API, useErrorDelPortal, useLang, useClientAuth } from './portalClientContext'
import { PortalPageHeader, PortalCard, PortalEmpty, PortalButton, PortalField, PortalTextarea, PortalTabs, formatMoney, metaItems, MONEDA_PORTAL_POR_DEFECTO } from './PortalUI'
import { POLL_FAST_MS, POLL_FREQUENT_MS } from '../../constants/timings'
import { Pulsable, Textarea } from '../../components/ui'
import { type ClientInvoice, type ClientProject, type CollabConversation, type CollabMessage, StatusBadge } from './PortalAdvancedComun'

// ════════════════════════════════════════════════════════════════════════════
// PortalMessages — usa el nuevo dominio collaboration via /portal/collaboration/*
// (sustituye al inbox antiguo, manteniendo el componente gobernado como
// segunda pestaña para compatibilidad con conversaciones legacy).
// ════════════════════════════════════════════════════════════════════════════
export function PortalMessages() {
  const traducir = useLang()
  const t = useLang()
  const { client } = useClientAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState('chat')
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  // 16-11-2026: los errores de `/portal/collaboration/*` llegan con código (`err_srv.*`).
  const toast = useToast()
  const errorDe = useErrorDelPortal()

  const { data: conversations = [], isLoading } = useQuery<CollabConversation[]>({
    queryKey: ['portal-collab-conversations'],
    queryFn: () => CLIENT_API.get('/portal/collaboration/conversations').then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: messages = [] } = useQuery<CollabMessage[]>({
    queryKey: ['portal-collab-messages', activeConvId],
    queryFn: () => CLIENT_API.get(`/portal/collaboration/conversations/${activeConvId}/messages`).then(r => r.data),
    enabled: !!activeConvId,
    refetchInterval: POLL_FAST_MS,
  })

  const send = useMutation({
    mutationFn: () => CLIENT_API.post('/portal/collaboration/messages', { conversation_id: activeConvId, body: draft }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-collab-messages', activeConvId] })
      qc.invalidateQueries({ queryKey: ['portal-collab-conversations'] })
      setDraft('')
    },
    onError: (e: unknown) => toast.error(errorDe(e, t('pas_err_generic'))),
  })

  useEffect(() => {
    if (!activeConvId && conversations.length > 0) setActiveConvId(conversations[0].id)
  }, [conversations, activeConvId])

  const projectOptions = Array.isArray(client?.projects)
    ? (client.projects as ClientProject[]).map(p => ({ id: p.id, name: p.name || p.code || p.id, code: p.code || '' }))
    : []
  // La sesión tipa `project_id` como `string | number`; el backend lo da como UUID (texto).
  const proyectoDeSesion = client?.project_id as string | null | undefined
  const fallbackProject = proyectoDeSesion ? [{ id: proyectoDeSesion, name: proyectoDeSesion, code: '' }] : []

  const tabs = [
    { id: 'chat', label: t('pas_tab_chat'), icon: <MessagesSquare size={14} /> },
    { id: 'governed', label: t('pas_tab_formal'), icon: <FileQuestion size={14} /> },
  ]

  return (
    <div>
      <PortalPageHeader
        title={traducir('chat.messages')}
        subtitle={traducir('portaladvanced.chat_unificado_con_el_equipo_del_proyecto')}
        icon={MessageSquare}
      />

      <PortalTabs tabs={tabs} value={tab} onChange={setTab} ariaLabel={traducir('chat.messages')} />

      {tab === 'chat' && (
        isLoading ? <div className="poadse-box-13">{traducir('common.loading')}</div> :
        conversations.length === 0 ? (
          <PortalEmpty icon={MessageSquare} title={traducir('portaladvanced.aun_no_tienes_conversaciones')}
            description={traducir('portaladvanced.cuando_el_equipo_te_invite_a_un')} />
        ) : (
          <div className="poadse-grid-1">
            <PortalCard padding={10} className="portalad-sx4">
              {conversations.map(c => (
                <Pulsable className={`poadse-box-29 ${activeConvId === c.id ? 'portal-advanced-sections-m7' : 'portal-advanced-sections-m8'}`} key={c.id} onClick={() => setActiveConvId(c.id)}>{c.title}</Pulsable>
              ))}
            </PortalCard>
            <PortalCard padding={0} className="portalad-sx5">
              <div className="poadse-box-14">
                {messages.map(m => (
                  <div key={m.id} className="u-mb-10">
                    <div className="u-text3-xs">
                      {m.author_name || (m.client_user_id === client?.id ? t('pas_you') : t('dashboard_team'))} · {fmtDateTime(m.sent_at)}
                    </div>
                    <div className="poadse-txt-4">{m.body}</div>
                  </div>
                ))}
              </div>
              <div className="poadse-row-15">
                <Textarea aria-label={traducir('portaladvanced.escribe_un_mensaje')} value={draft} onChange={e => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (draft.trim()) send.mutate() } }}
                  placeholder={traducir('portaladvanced.escribe_un_mensaje')} rows={1}
                  className="u-flex1-min0" inputClassName="poadse-box-15" />
                <PortalButton size="sm" onClick={() => draft.trim() && send.mutate()} disabled={!draft.trim()}>{traducir('chat.send')}</PortalButton>
              </div>
            </PortalCard>
          </div>
        )
      )}

      {tab === 'governed' && (
        <ClientGovernedConversationInbox
          title={t('messages_team_title')}
          emptyTitle={t('messages_empty')}
          emptyDescription={t('messages_empty')}
          projectOptions={projectOptions.length ? projectOptions : fallbackProject}
          initialProjectId={proyectoDeSesion || ''}
        />
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalInvoices
// ════════════════════════════════════════════════════════════════════════════
export function PortalInvoices() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [reasonByInvoice, setReasonByInvoice] = useState<Record<string, string>>({})
  const defaultCurrency = MONEDA_PORTAL_POR_DEFECTO

  const { data: invoices = [], isLoading } = useQuery<ClientInvoice[]>({
    queryKey: ['portal-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
  })

  const { mutate: approveInvoice, isPending } = useMutation({
    mutationFn: ({ invoiceId, approved, reason }: { invoiceId: string; approved: boolean; reason?: string }) => CLIENT_API.post(`/portal/invoices/${invoiceId}/approve`, { approved, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-invoices'] })
      qc.invalidateQueries({ queryKey: ['portal-dashboard'] })
      toast.success(traducir('chat.decision_registrada'))
    },
    onError: (e: unknown) => toast.error(errorDe(e, t('pas_err_generic'))),
  })

  const totals = invoices.reduce((acc: { total: number; paid: number; overdue: number; pending: number }, i) => {
    const v = Number(i.total || 0)
    acc.total += v
    if (i.status === 'paid') acc.paid += v
    if (i.status === 'overdue') acc.overdue += v
    if (['sent', 'submitted', 'pending'].includes(i.status)) acc.pending += v
    return acc
  }, { total: 0, paid: 0, overdue: 0, pending: 0 })
  const currency = invoices[0]?.currency || defaultCurrency

  return (
    <div>
      <PortalPageHeader
        title={traducir('nav.invoices')}
        subtitle={traducir('portaladvanced.aprueba_o_rechaza_las_facturas_pendientes_y')}
        icon={Receipt}
        meta={metaItems([
          { value: invoices.length, label: t('pas_meta_invoices') },
          { value: formatMoney(totals.paid, currency), label: t('pas_meta_collected'), color: 'var(--success)' },
          { value: formatMoney(totals.pending, currency), label: t('pas_meta_pending_amount'), color: 'var(--warning)' },
          totals.overdue > 0 && { value: formatMoney(totals.overdue, currency), label: t('pas_meta_overdue'), color: 'var(--danger)' },
        ])}
      />

      {isLoading ? (
        <div className="poadse-box-5">{traducir('common.loading')}</div>
      ) : invoices.length === 0 ? (
        <PortalEmpty icon={Receipt} title={traducir('portaladvanced.sin_facturas')} description={traducir('portaladvanced.cuando_se_emitan_facturas_en_este_proyecto')} />
      ) : (
        <div className="u-stack-12">
          {invoices.map(inv => {
            const cur = inv.currency || defaultCurrency
            const reason = reasonByInvoice[inv.id] || ''
            return (
              <PortalCard key={inv.id}>
                <div className="poadse-row-16">
                  <div className="u-flex1-min0">
                    <div className="u-text3-mono-xs">#{inv.number || inv.id}</div>
                    <div className="poadse-txt-2">{inv.client_name || t('pas_invoice')}</div>
                    <div className="poadse-row-17">
                      <span>{traducir('portaladvanced.emitida')} {fmtDate(inv.issue_date)}</span>
                      <span>{traducir('portaladvanced.vence')} {fmtDate(inv.due_date)}</span>
                    </div>
                  </div>
                  <div className="poadse-txt-5">
                    <div className="poadse-txt-6">{formatMoney(inv.total, cur)}</div>
                    <StatusBadge status={inv.status} />
                  </div>
                </div>
                <div className="poadse-box-16">
                  {traducir('portaladvanced.base_iva', { base: formatMoney(inv.subtotal, cur), iva: formatMoney(inv.tax_amount, cur) })}
                </div>
                {inv.client_approval_status === 'pending' && (
                  <>
                    <PortalField label={traducir('portaladvanced.comentario_opcional')}>
                      <PortalTextarea rows={2}
                        value={reason}
                        onChange={e => setReasonByInvoice(prev => ({ ...prev, [inv.id]: e.target.value }))}
                        placeholder={traducir('portaladvanced.motivo_si_rechazas_observaciones')}
                      />
                    </PortalField>
                    <div className="poadse-row-18">
                      <PortalButton variant="danger" size="sm" loading={isPending}
                        onClick={() => approveInvoice({ invoiceId: inv.id, approved: false, reason })}>{traducir('aus.rechazar')}</PortalButton>
                      <PortalButton size="sm" icon={<CheckCircle2 size={13} />} loading={isPending}
                        onClick={() => approveInvoice({ invoiceId: inv.id, approved: true, reason })}>{traducir('aus.aprobar')}</PortalButton>
                    </div>
                  </>
                )}
              </PortalCard>
            )
          })}
        </div>
      )}
    </div>
  )
}
