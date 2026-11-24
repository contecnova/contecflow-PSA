// Secciones de mensajes y facturas del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Receipt, MessageSquare, CheckCircle2, MessagesSquare, FileQuestion } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate } from '../../utils/helpers'
import { ClientGovernedConversationInbox } from '../../components/portal/GovernedConversations'
import ChatColaboracionDelPortal from '../../components/portal/ChatColaboracionDelPortal'
import { CLIENT_API, useErrorDelPortal, useLang, useClientAuth } from './portalClientContext'
import { PortalPageHeader, PortalCard, PortalEmpty, PortalButton, PortalField, PortalTextarea, PortalTabs, formatMoney, metaItems, MONEDA_PORTAL_POR_DEFECTO } from './PortalUI'
import { type ClientInvoice, type ClientProject, StatusBadge } from './PortalAdvancedComun'

// ════════════════════════════════════════════════════════════════════════════
// PortalMessages — usa el nuevo dominio collaboration via /portal/collaboration/*
// (sustituye al inbox antiguo, manteniendo el componente gobernado como
// segunda pestaña para compatibilidad con conversaciones legacy).
// ════════════════════════════════════════════════════════════════════════════
export function PortalMessages() {
  const traducir = useLang()
  const t = useLang()
  const { client } = useClientAuth()
  const [tab, setTab] = useState('chat')

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

      {/* 24-11-2026 (docs/portal/CHAT_DEL_PORTAL.md §9): el chat de colaboración con
          adjuntos, emojis, reacciones, citas, edición con rastro, enlaces, leído,
          «escribiendo…» y llamadas que solo inicia el equipo. */}
      {tab === 'chat' && (
        <ChatColaboracionDelPortal vacio={
          <PortalEmpty icon={MessageSquare} title={traducir('portaladvanced.aun_no_tienes_conversaciones')}
            description={traducir('portaladvanced.cuando_el_equipo_te_invite_a_un')} />
        } />
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
