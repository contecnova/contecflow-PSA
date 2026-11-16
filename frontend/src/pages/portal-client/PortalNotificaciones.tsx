/**
 * PortalNotificaciones — todos los avisos del cliente («Ver todas» de la
 * campana de la cabecera). 16-11-2026.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell, CheckCheck } from 'lucide-react'
import { useLang } from './portalClientContext'
import { PortalButton, PortalCard, PortalEmpty, PortalPageHeader, PortalTabs } from './PortalUI'
import {
  CLAVE_AVISOS_DEL_PORTAL, avisoParaLaBandeja, irAlAviso, portalAvisosApi, useAvisosDelPortal,
  type AvisoDelPortal,
} from './CampanaDelPortal'
import { ListaDeAvisos, type AvisoDeLaBandeja } from '../../components/avisos/BandejaDesplegable'
import { Spinner } from '../../components/ui'
import { STALE_LIVE_MS } from '../../constants/timings'

export function PortalNotificaciones({ onSection, enVivo = false }: { onSection: (s: string) => void; enVivo?: boolean }) {
  const t = useLang()
  const [filtro, setFiltro] = useState<'todas' | 'sin_leer'>('todas')
  const { contador, marcarUno, marcarTodos } = useAvisosDelPortal(enVivo)
  const { data: avisos = [], isLoading } = useQuery<AvisoDelPortal[]>({
    queryKey: [CLAVE_AVISOS_DEL_PORTAL, 'pagina', filtro],
    queryFn: () => portalAvisosApi.lista(undefined, filtro === 'sin_leer'),
    staleTime: STALE_LIVE_MS,
  })
  const porId = new Map(avisos.map(a => [String(a.id), a]))

  const elegir = (v: AvisoDeLaBandeja) => {
    if (!v.leido) marcarUno.mutate(v.id)
    irAlAviso(porId.get(v.id), onSection)
  }

  return (
    <div>
      <PortalPageHeader
        title={t('portal_avisos.titulo')}
        subtitle={t('portal_avisos.subtitulo')}
        icon={Bell}
        actions={contador > 0 ? (
          <PortalButton variant="secondary" icon={<CheckCheck size={14} />} loading={marcarTodos.isPending}
            onClick={() => marcarTodos.mutate()}>
            {t('portal_avisos.marcar_todas')}
          </PortalButton>
        ) : undefined}
      />
      <PortalTabs
        ariaLabel={t('portal_avisos.titulo')}
        value={filtro}
        onChange={id => setFiltro(id as 'todas' | 'sin_leer')}
        tabs={[
          { id: 'todas', label: t('portal_avisos.todas') },
          { id: 'sin_leer', label: t('portal_avisos.no_leido'), badge: contador },
        ]}
      />
      <PortalCard padding={0}>
        {isLoading ? (
          <div className="bandeja-desplegable__estado"><Spinner size={20} label={t('portal_avisos.cargando')} /></div>
        ) : avisos.length === 0 ? (
          <PortalEmpty icon={Bell} title={filtro === 'sin_leer' ? t('portal_avisos.vacio_sin_leer') : t('portal_avisos.vacio')} />
        ) : (
          <ListaDeAvisos avisos={avisos.map(a => avisoParaLaBandeja(a, t))} noLeido={t('portal_avisos.no_leido')} onElegir={elegir} />
        )}
      </PortalCard>
    </div>
  )
}
