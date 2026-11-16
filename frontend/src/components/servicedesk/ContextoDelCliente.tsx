/**
 * ContextoDelCliente — quién pide y qué tiene (mejoras de mercado 16-11-2026):
 * su cliente y contrato, sus tickets abiertos y recientes, su satisfacción y,
 * si la empresa usa Licencias y activos, los equipos y licencias que tiene
 * asignados ahora mismo él o su cliente.
 */
import { useQuery } from '@tanstack/react-query'
import { Laptop, KeyRound, UserRound } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { Section, Spinner, StatusBadge } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { fmtDate } from '../../utils/helpers'
import { puestoDelAgenteApi } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

export default function ContextoDelCliente({ ticketId, onAbrir }: { ticketId: string; onAbrir?: (id: string) => void }) {
  const t = useAppT()
  const { data, isLoading, isError } = useQuery({ queryKey: ['sdm-contexto', ticketId], queryFn: () => puestoDelAgenteApi.contexto(ticketId), retry: false })
  return (
    <Section title={<span className="u-row-center-6"><UserRound size={16} aria-hidden="true" />{t('sd_mercado.contexto_titulo')}</span>} className="u-mb-20">
      {isLoading ? <Spinner size={16} /> : isError || !data ? <div className="u-text3-xs">{t('sd_mercado.error_carga')}</div> : (
        <div className="u-stack-10">
          <dl className="sdm-kv">
            <dt>{t('sd_mercado.solicitante')}</dt><dd>{data.requester.name || '—'} <span className="u-text3-xs">{etiquetaCodigo(t, 'sd_mercado.tipo_persona', data.requester.kind)}</span></dd>
            {data.requester.email && <><dt>{t('sd_mercado.correo')}</dt><dd>{data.requester.email}</dd></>}
            {data.requester.phone && <><dt>{t('sd_mercado.telefono')}</dt><dd>{data.requester.phone}</dd></>}
            <dt>{t('sd_mercado.cliente')}</dt><dd>{data.client?.name || '—'}</dd>
            <dt>{t('sd_mercado.contrato')}</dt><dd>{data.contract?.name || '—'}</dd>
            <dt>{t('sd_mercado.tickets_abiertos')}</dt><dd>{data.open_tickets} / {data.total_tickets}</dd>
            <dt>{t('sd_mercado.satisfaccion')}</dt><dd>{data.avg_csat ?? '—'}</dd>
          </dl>
          {data.recent_tickets.length > 0 && (
            <div className="u-stack-6">
              <div className="ds-eyebrow">{t('sd_mercado.tickets_recientes')}</div>
              {data.recent_tickets.map(r => (
                <div key={r.id} className="u-row-center-8 sdm-wrap">
                  {onAbrir ? <button type="button" className="u-btn-outline-sm" onClick={() => onAbrir(r.id)}>{r.number}</button> : <span className="u-mono">{r.number}</span>}
                  <span className="u-flex1-min0 u-text2-xs">{r.title}</span>
                  <StatusBadge caps={false}>{etiquetaCodigo(t, 'estado', r.status)}</StatusBadge>
                  <span className="u-text3-xs">{r.created_at ? fmtDate(r.created_at) : ''}</span>
                </div>
              ))}
            </div>
          )}
          {data.alm.available && (
            <div className="sdm-grid">
              <div className="u-stack-6">
                <div className="ds-eyebrow u-row-center-6"><Laptop size={12} aria-hidden="true" />{t('sd_mercado.equipos')}</div>
                {data.alm.assets.length === 0 ? <span className="u-text3-xs">{t('sd_mercado.ninguno')}</span> : data.alm.assets.map(a => (
                  <div key={a.id} className="u-text2-xs sdm-wrap">{a.name}{a.asset_tag ? ` · ${a.asset_tag}` : ''}{a.serial_number ? ` · ${a.serial_number}` : ''}</div>
                ))}
              </div>
              <div className="u-stack-6">
                <div className="ds-eyebrow u-row-center-6"><KeyRound size={12} aria-hidden="true" />{t('sd_mercado.licencias')}</div>
                {data.alm.licenses.length === 0 ? <span className="u-text3-xs">{t('sd_mercado.ninguna')}</span> : data.alm.licenses.map(l => (
                  <div key={l.id} className="u-text2-xs sdm-wrap">{l.name}{l.quantity > 1 ? ` × ${l.quantity}` : ''}{l.until ? ` · ${t('sd_mercado.hasta')} ${fmtDate(l.until)}` : ''}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Section>
  )
}
