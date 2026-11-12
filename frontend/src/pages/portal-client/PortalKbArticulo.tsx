/**
 * Lectura de un artículo de la base de conocimiento en el portal (revisión 2026-11).
 *
 * Las dos listas del portal (Wiki → Base de conocimiento y Soporte → Base de
 * conocimiento) enseñaban el artículo y no se podía abrir. El detalle ya existía
 * (`GET /sd/kb/{id}`, que cuenta la visita) y el voto también
 * (`POST /sd/kb/{id}/helpful`).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen } from 'lucide-react'
import { CLIENT_API } from './portalClientContext'
import { PortalButton, PortalCard, PortalPageHeader } from './PortalUI'
import MarkdownText from '../../components/ui/MarkdownText'
import { useAppLang } from '../../i18n/AppLangContext'

type Articulo = { id: string; number?: string; title: string; body?: string; summary?: string; tags?: string; view_count?: number; helpful_count?: number }

export default function PortalKbArticulo({ id, onVolver, migas }: { id: string; onVolver: () => void; migas: string }) {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const [votado, setVotado] = useState<boolean | null>(null)
  const { data, isLoading, isError } = useQuery<Articulo>({
    queryKey: ['portal-kb-articulo', id],
    queryFn: () => CLIENT_API.get(`/sd/kb/${id}`).then(r => r.data as Articulo),
  })
  const votar = useMutation({
    mutationFn: (util: boolean) => CLIENT_API.post(`/sd/kb/${id}/helpful`, null, { params: { helpful: util } }),
    onSuccess: (_r, util) => { setVotado(util); qc.invalidateQueries({ queryKey: ['portal-kb'] }); qc.invalidateQueries({ queryKey: ['portal-wiki-kb'] }) },
  })
  const volver = <PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={onVolver}>{t('portalkb.volver')}</PortalButton>
  if (isLoading) return <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>…</div>
  if (isError || !data) return <div>{volver}<p className="u-text2">{t('portalkb.no_disponible')}</p></div>
  return (
    <div>
      <PortalPageHeader title={data.title} icon={BookOpen}
        breadcrumb={[{ label: migas, onClick: onVolver }, { label: data.title }]} actions={volver} />
      <PortalCard>
        {data.number && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8 }}>{data.number}</div>}
        <MarkdownText text={data.body || data.summary || ''} style={{ fontSize: 'var(--text-md)', lineHeight: 1.65, color: 'var(--text-1)' }} />
        {data.tags && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 16 }}>🏷 {data.tags}</div>}
      </PortalCard>
      <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
        {votado === null ? (
          <>
            {t('portalkb.util_pregunta')}
            <PortalButton size="sm" variant="secondary" onClick={() => votar.mutate(true)} loading={votar.isPending}>👍 {t('portalkb.si')}</PortalButton>
            <PortalButton size="sm" variant="secondary" onClick={() => votar.mutate(false)} loading={votar.isPending}>👎 {t('portalkb.no')}</PortalButton>
          </>
        ) : t(votado ? 'portalkb.gracias_si' : 'portalkb.gracias_no')}
      </div>
    </div>
  )
}
