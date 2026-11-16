/**
 * ConfigCanales — qué canales tiene la empresa y qué dirección configurar en
 * cada uno (mejoras de mercado 16-11-2026). Las credenciales se guardan en
 * Ajustes → Credenciales (cifradas); aquí solo se ve el estado.
 * 16-11-2026 (pasada de diseño): vacío con icono lucide, direcciones legibles
 * y textos de ayuda sin jerga técnica.
 */
import { useQuery } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { EmptyState, Section, Spinner, StatusBadge } from '../../components/ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { apiUrlAbsoluta } from '../../services/api/urls'
import { canalesApi } from '../../services/api/serviceDeskMercado'
import '../../components/servicedesk/sdMercado.css'

export default function ConfigCanales() {
  const t = useAppT()
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const { data, isLoading } = useQuery({ queryKey: ['sdm-canales'], queryFn: canalesApi.estado, enabled: esAdmin })
  if (!esAdmin) return <EmptyState icon={<Lock size={28} />} title={t('sd_mercado.solo_admin')} />
  if (isLoading || !data) return <Spinner />
  const canales: [string, boolean, string[]][] = [
    ['slack', data.slack, [data.endpoints.slack_commands, data.endpoints.slack_interactions]],
    ['teams', data.teams, [data.endpoints.teams_messages]],
    ['whatsapp', data.whatsapp, [data.endpoints.whatsapp_webhook]],
    ['livechat', data.livechat, []],
  ]
  return (
    <Section title={t('sd_mercado.canales_titulo')} subtitle={t('sd_mercado.canales_desc')}>
      <ul className="sdm-list">
        {canales.map(([canal, listo, rutas]) => (
          <li key={canal} className="sdm-list__item">
            <div className="u-flex1-min0 u-stack-6">
              <div className="u-wrap-8"><span className="u-text1-sm-600">{etiquetaCodigo(t, 'sd_mercado.canal', canal)}</span>
                <StatusBadge kind={listo ? 'success' : 'warning'} caps={false}>{t(listo ? 'sd_mercado.configurado' : 'sd_mercado.sin_configurar')}</StatusBadge></div>
              <div className="u-text2-xs">{t(`sd_mercado.canal_ayuda_${canal}`)}</div>
              {rutas.map(r => <code key={r} className="sdm-code sdm-wrap">{apiUrlAbsoluta(r.replace(/^\/api\/v1/, ''))}</code>)}
            </div>
          </li>
        ))}
      </ul>
    </Section>
  )
}
