/**
 * Canal de correo entrante: buzón, pasarela y lo último que ha entrado.
 *
 * Es la misma pantalla desde Service Desk → Configuración y desde Ajustes →
 * Email-to-ticket: antes la de Ajustes explicaba un flujo que ya no existe
 * («se asigna al primer agente») y enseñaba una URL de webhook equivocada.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdInboundApi } from '../../services/api'

type Entrada = { id: string; received_at?: string; sender?: string; outcome: string; reason?: string; ticket_id?: string; ticket_number?: string }
type Prueba = { ok: boolean; unread?: number; error?: string; protocol?: string }
type Pasada = { created?: number; commented?: number; ignored?: number; failed?: number; error?: string }

const LS: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)', display: 'block',
  marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }
const COLOR_RESULTADO: Record<string, string> = {
  created: COLOR.success, commented: 'var(--accent)', ignored: 'var(--text-3)', failed: COLOR.danger,
}

export default function ConfigCorreoEntrante() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [prueba, setPrueba] = useState<Prueba | null>(null)
  const webhook = `${window.location.origin}/api/v1/sd/inbound-email`

  const { data: entradas = [], isLoading } = useQuery<Entrada[]>({
    queryKey: ['sd-inbound-messages'],
    queryFn: () => sdInboundApi.messages(30).then(r => r.data as Entrada[]),
  })
  const probar = useMutation({
    mutationFn: () => sdInboundApi.test().then(r => r.data as Prueba),
    onSuccess: setPrueba,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const leer = useMutation({
    mutationFn: () => sdInboundApi.run().then(r => r.data as Pasada),
    onSuccess: (r: Pasada) => {
      qc.invalidateQueries({ queryKey: ['sd-inbound-messages'] })
      if (r.error) toast.error(r.error)
      else toast.success(t('sd_cfg.mail_run_done', {
        created: r.created ?? 0, commented: r.commented ?? 0, ignored: r.ignored ?? 0, failed: r.failed ?? 0,
      }))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', maxWidth: 720 }}>{t('sd_cfg.mail_intro')}</div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <div className="ds-card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={LS}>{t('sd_cfg.mail_mailbox')}</span>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('sd_cfg.mail_mailbox_help')}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button variant="secondary" onClick={() => { window.location.href = '/settings?tab=integrations' }}>{t('sd_cfg.mail_credentials')}</Button>
            <Button variant="secondary" onClick={() => probar.mutate()} loading={probar.isPending}>{t('sd_cfg.mail_test')}</Button>
            <Button onClick={() => leer.mutate()} loading={leer.isPending}>{t('sd_cfg.mail_run')}</Button>
          </div>
          {prueba && (
            <div role="status" style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: prueba.ok ? COLOR.success : COLOR.danger }}>
              {prueba.ok ? t('sd_cfg.mail_ok', { n: prueba.unread ?? 0 }) : prueba.error}
            </div>
          )}
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
            <strong>{t('sd_cfg.mail_address')}:</strong> {t('sd_cfg.mail_address_help')}
          </div>
        </div>

        <div className="ds-card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={LS}>{t('sd_cfg.mail_gateway')}</span>
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('sd_cfg.mail_gateway_help')}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input readOnly value={webhook} aria-label={t('sd_cfg.mail_gateway')}
              style={{ flex: 1, minWidth: 0, padding: '8px 12px', borderRadius: 8, border: '1px solid var(--surface-4)',
                background: 'var(--surface-3)', color: 'var(--text-1)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' }} />
            <Button variant="secondary" onClick={() => { navigator.clipboard.writeText(webhook); toast.success(t('sd_cfg.mail_copy')) }}>
              {t('sd_cfg.mail_copy')}
            </Button>
          </div>
        </div>
      </div>

      <div>
        <span style={LS}>{t('sd_cfg.mail_log')}</span>
        {isLoading ? <Spinner /> : entradas.length === 0 ? (
          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('sd_cfg.mail_log_empty')}</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
              <tbody>
                {entradas.map(e => (
                  <tr key={e.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    <td style={{ padding: '7px 8px', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{e.received_at ? new Date(e.received_at).toLocaleString() : ''}</td>
                    <td style={{ padding: '7px 8px', color: 'var(--text-2)' }}>{e.sender}</td>
                    <td style={{ padding: '7px 8px', fontWeight: 600, color: COLOR_RESULTADO[e.outcome] ?? 'var(--text-2)', whiteSpace: 'nowrap' }}>
                      {t(`sd_cfg.mail_out_${e.outcome}`)}
                    </td>
                    <td style={{ padding: '7px 8px' }}>
                      {e.ticket_id
                        ? <a href={`/service-desk?ticket=${e.ticket_id}`} style={{ color: 'var(--accent)', fontWeight: 600 }}>{e.ticket_number}</a>
                        : <span style={{ color: 'var(--text-3)' }}>{e.reason}</span>}
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
