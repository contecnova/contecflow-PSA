/**
 * Canal de correo entrante: buzón, pasarela y lo último que ha entrado.
 *
 * Es la misma pantalla desde Service Desk → Configuración y desde Ajustes →
 * Email-to-ticket: antes la de Ajustes explicaba un flujo que ya no existe
 * («se asigna al primer agente») y enseñaba una URL de webhook equivocada.
 *
 * 16-11-2026 (pasada de diseño): campo de la dirección con `ds-input`, botón
 * Copiar con icono, registro vacío con EmptyState, fechas con fmtDateTime,
 * resultado de cada correo con StatusBadge y textos de ayuda sin jerga.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Inbox, KeyRound } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Spinner, StatusBadge, TablaSimple } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { sdInboundApi, apiUrlAbsoluta } from '../../services/api'
import type { SdPruebaDeBuzon } from '../../services/api/tipos-sd'
import './ConfigCorreoEntrante.css'

const KIND_RESULTADO: Record<string, StatusBadgeKind> = {
  created: 'success', commented: 'accent', ignored: 'neutral', failed: 'danger',
}

export default function ConfigCorreoEntrante() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [prueba, setPrueba] = useState<SdPruebaDeBuzon | null>(null)
  const webhook = apiUrlAbsoluta('/sd/inbound-email')

  const { data: entradas = [], isLoading } = useQuery({
    queryKey: ['sd-inbound-messages'],
    queryFn: () => sdInboundApi.messages().then(r => r.data),
  })
  const probar = useMutation({
    mutationFn: () => sdInboundApi.test().then(r => r.data),
    onSuccess: setPrueba,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const leer = useMutation({
    mutationFn: () => sdInboundApi.run().then(r => r.data),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-inbound-messages'] })
      if ('error' in r) toast.error(r.error)
      else toast.success(t('sd_cfg.mail_run_done', {
        created: r.created, commented: r.commented, ignored: r.ignored, failed: r.failed,
      }))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div className="u-stack-20">
      <div className="cocoen-intro">{t('sd_cfg.mail_intro')}</div>

      <div className="cocoen-grid-1">
        <div className="ds-card">
          <span className="cocoen-ls">{t('sd_cfg.mail_mailbox')}</span>
          <div className="u-text2-sm">{t('sd_cfg.mail_mailbox_help')}</div>
          <div className="u-wrap-8">
            <Button variant="secondary" icon={<KeyRound size={14} />} onClick={() => { window.location.href = '/settings?tab=integrations' }}>{t('sd_cfg.mail_credentials')}</Button>
            <Button variant="secondary" onClick={() => probar.mutate()} loading={probar.isPending}>{t('sd_cfg.mail_test')}</Button>
            <Button onClick={() => leer.mutate()} loading={leer.isPending}>{t('sd_cfg.mail_run')}</Button>
          </div>
          {prueba && (
            <div role="status">
              <StatusBadge kind={prueba.ok ? 'success' : 'danger'} caps={false}>
                {prueba.ok ? t('sd_cfg.mail_ok', { n: prueba.unread ?? 0 }) : prueba.error}
              </StatusBadge>
            </div>
          )}
          <div className="u-text2-xs">
            <strong>{t('sd_cfg.mail_address')}:</strong> {t('sd_cfg.mail_address_help')}
          </div>
        </div>

        <div className="ds-card">
          <span className="cocoen-ls">{t('sd_cfg.mail_gateway')}</span>
          <div className="u-text2-sm">{t('sd_cfg.mail_gateway_help')}</div>
          <div className="cocoen-copy">
            <input readOnly value={webhook} aria-label={t('sd_cfg.mail_gateway')}
              className="ds-input cocoen-url ds-campo-codigo" />
            <Button variant="secondary" icon={<Copy size={14} />} onClick={() => { navigator.clipboard.writeText(webhook); toast.success(t('sd_cfg.cfg_copied')) }}>
              {t('sd_cfg.mail_copy')}
            </Button>
          </div>
        </div>
      </div>

      <div>
        <span className="cocoen-ls">{t('sd_cfg.mail_log')}</span>
        {isLoading ? <Spinner /> : entradas.length === 0 ? (
          <EmptyState icon={<Inbox size={28} />} title={t('sd_cfg.mail_log_empty')} />
        ) : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table-sm">
              <tbody>
                {entradas.map(e => (
                  <tr key={e.id} className="u-border-b">
                    <td className="cocoen-fecha">{e.received_at ? fmtDateTime(e.received_at) : ''}</td>
                    <td className="cocoen-celda cocoen-celda--texto">{e.sender}</td>
                    <td className="cocoen-celda">
                      <StatusBadge kind={KIND_RESULTADO[e.outcome] ?? 'neutral'} caps={false}>{t(`sd_cfg.mail_out_${e.outcome}`)}</StatusBadge>
                    </td>
                    <td className="cocoen-celda">
                      {e.ticket_id
                        ? <a href={`/service-desk?ticket=${e.ticket_id}`} className="cocoen-enlace">{e.ticket_number}</a>
                        : <span className="u-text2">{e.reason}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </div>
    </div>
  )
}
