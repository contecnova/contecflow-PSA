/**
 * Canal de correo entrante: buzón, pasarela y lo último que ha entrado.
 *
 * Es la misma pantalla desde Service Desk → Configuración y desde Ajustes →
 * Email-to-ticket: antes la de Ajustes explicaba un flujo que ya no existe
 * («se asigna al primer agente») y enseñaba una URL de webhook equivocada.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdInboundApi, apiUrlAbsoluta } from '../../services/api'
import type { SdPruebaDeBuzon } from '../../services/api/tipos-sd'
import './ConfigCorreoEntrante.css'

const COLOR_RESULTADO: Record<string, string> = {
  created: COLOR.success, commented: 'var(--accent)', ignored: 'var(--text-3)', failed: COLOR.danger,
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
      <div className="cocoen-box-1">{t('sd_cfg.mail_intro')}</div>

      <div className="cocoen-grid-1">
        <div className="ds-card cocoen-stack-1">
          <span className="cocoen-ls">{t('sd_cfg.mail_mailbox')}</span>
          <div className="u-text2-sm">{t('sd_cfg.mail_mailbox_help')}</div>
          <div className="u-wrap-8">
            <Button variant="secondary" onClick={() => { window.location.href = '/settings?tab=integrations' }}>{t('sd_cfg.mail_credentials')}</Button>
            <Button variant="secondary" onClick={() => probar.mutate()} loading={probar.isPending}>{t('sd_cfg.mail_test')}</Button>
            <Button onClick={() => leer.mutate()} loading={leer.isPending}>{t('sd_cfg.mail_run')}</Button>
          </div>
          {prueba && (
            <div className="cocoen-txt-2" role="status" style={{ color: prueba.ok ? COLOR.success : COLOR.danger }}>
              {prueba.ok ? t('sd_cfg.mail_ok', { n: prueba.unread ?? 0 }) : prueba.error}
            </div>
          )}
          <div className="u-text3-xs">
            <strong>{t('sd_cfg.mail_address')}:</strong> {t('sd_cfg.mail_address_help')}
          </div>
        </div>

        <div className="ds-card cocoen-stack-1">
          <span className="cocoen-ls">{t('sd_cfg.mail_gateway')}</span>
          <div className="u-text2-sm">{t('sd_cfg.mail_gateway_help')}</div>
          <div className="u-row-8">
            <input readOnly value={webhook} aria-label={t('sd_cfg.mail_gateway')}
              className="cocoen-box-2" />
            <Button variant="secondary" onClick={() => { navigator.clipboard.writeText(webhook); toast.success(t('sd_cfg.mail_copy')) }}>
              {t('sd_cfg.mail_copy')}
            </Button>
          </div>
        </div>
      </div>

      <div>
        <span className="cocoen-ls">{t('sd_cfg.mail_log')}</span>
        {isLoading ? <Spinner /> : entradas.length === 0 ? (
          <div className="u-text3-sm">{t('sd_cfg.mail_log_empty')}</div>
        ) : (
          <div className="u-scroll-x">
            <table className="u-table-sm">
              <tbody>
                {entradas.map(e => (
                  <tr key={e.id} className="u-border-b">
                    <td className="cocoen-box-3">{e.received_at ? new Date(e.received_at).toLocaleString(localeActivo()) : ''}</td>
                    <td className="cocoen-box-4">{e.sender}</td>
                    <td className="cocoen-box-5" style={{ color: COLOR_RESULTADO[e.outcome] ?? 'var(--text-2)' }}>
                      {t(`sd_cfg.mail_out_${e.outcome}`)}
                    </td>
                    <td className="cocoen-sp-1">
                      {e.ticket_id
                        ? <a href={`/service-desk?ticket=${e.ticket_id}`} className="cocoen-txt-1">{e.ticket_number}</a>
                        : <span className="u-text3">{e.reason}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
