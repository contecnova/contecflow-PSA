/**
 * RevisionDeContenidoDelPortal — pantalla de revisión de las versiones de avisos
 * y del catálogo en los idiomas del portal (17-11-2026).
 *
 * Cada aviso activo y cada categoría y servicio del catálogo, con cuántas
 * versiones tiene en revisión, publicadas, rechazadas y desactualizadas (el
 * original cambió después). Primero lo que pide atención. «Revisar» abre el
 * panel de versiones (`VersionesDeContenidoPanel`): generar, corregir,
 * publicar o rechazar.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Folder, Languages, Megaphone, Package } from 'lucide-react'
import { Button, EmptyState, Segmentado, Spinner, StatusBadge, TablaSimple } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { traduccionApi, type FilaDeRevisionDeContenido, type TipoDeContenidoDelPortal } from '../../services/api/traduccion'
import { errorDeTraduccion } from '../../hooks/useTraduccion'
import { extractErr } from '../../utils/helpers'
import { DialogoDeVersionesDeContenido } from './VersionesDeContenidoPanel'

const CLAVE = ['traduccion-contenido', 'resumen'] as const

const ICONO: Record<TipoDeContenidoDelPortal, typeof Folder> = {
  announcement: Megaphone,
  catalog_category: Folder,
  catalog_service: Package,
}

const pendiente = (f: FilaDeRevisionDeContenido) => f.counts.in_review + f.counts.draft + f.outdated > 0

export default function RevisionDeContenidoDelPortal() {
  const t = useAppT()
  const qc = useQueryClient()
  const [filtro, setFiltro] = useState('pendientes')
  const [abierta, setAbierta] = useState<FilaDeRevisionDeContenido | null>(null)
  const { data, isLoading, isError, error } = useQuery({ queryKey: CLAVE, queryFn: traduccionApi.resumenDeContenido })

  if (isLoading) return <Spinner />
  if (isError || !data) return <p className="trad-kb__error" role="alert">{errorDeTraduccion(t, extractErr(error, ''))}</p>

  const filas = filtro === 'pendientes' ? data.items.filter(pendiente) : data.items
  const refrescar = () => qc.invalidateQueries({ queryKey: CLAVE })

  return (
    <section className="u-stack-12" aria-label={t('traduccion_admin.portal_revision_titulo')}>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">
          {t('traduccion_admin.portal_revision_desc')}
          {!data.enabled && <> {t('traduccion_admin.portal_desactivado')}</>}
          {!data.can_review && <> {t('traduccion_admin.portal_solo_revisores')}</>}
        </div>
        <Segmentado aria-label={t('traduccion_admin.portal_filtro')} valor={filtro} onChange={setFiltro} opciones={[
          { valor: 'pendientes', etiqueta: t('traduccion_admin.portal_filtro_pendientes') },
          { valor: 'todo', etiqueta: t('traduccion_admin.portal_filtro_todo') },
        ]} />
      </div>

      {filas.length === 0 ? (
        <EmptyState icon={<Languages size={28} />} title={t('traduccion_admin.portal_revision_vacia')}
          description={t('traduccion_admin.portal_revision_vacia_desc')} />
      ) : (
        <TablaSimple etiqueta={t('traduccion_admin.portal_revision_titulo')}>
          <thead>
            <tr>
              <th scope="col">{t('traduccion_admin.portal_col_contenido')}</th>
              <th scope="col">{t('traduccion_admin.portal_col_estado')}</th>
              <th scope="col"><span className="u-sr-only">{t('traduccion_admin.portal_revisar')}</span></th>
            </tr>
          </thead>
          <tbody>
            {filas.map(f => {
              const Icono = ICONO[f.content_type]
              return (
                <tr key={`${f.content_type}-${f.content_id}`}>
                  <td>
                    <div className="u-row-center-6">
                      <Icono size={14} aria-hidden="true" />
                      <span className="u-600">{f.label}</span>
                      <span className="u-text3-xs">{t(`traduccion_admin.portal_tipo.${f.content_type}`)}</span>
                    </div>
                  </td>
                  <td>
                    <div className="u-wrap-8">
                      {f.counts.in_review + f.counts.draft > 0 && <StatusBadge kind="warning" caps={false}>{t('traduccion_admin.portal_n_en_revision', { n: f.counts.in_review + f.counts.draft })}</StatusBadge>}
                      {f.counts.published > 0 && <StatusBadge kind="success" caps={false}>{t('traduccion_admin.portal_n_publicadas', { n: f.counts.published })}</StatusBadge>}
                      {f.counts.rejected > 0 && <StatusBadge kind="danger" caps={false}>{t('traduccion_admin.portal_n_rechazadas', { n: f.counts.rejected })}</StatusBadge>}
                      {f.outdated > 0 && <StatusBadge kind="orange" caps={false}>{t('traduccion_admin.portal_n_desactualizadas', { n: f.outdated })}</StatusBadge>}
                      {f.languages.length === 0 && <span className="u-text3-xs">{t('traduccion_admin.portal_sin_versiones_corto')}</span>}
                    </div>
                  </td>
                  <td>
                    <Button size="xs" variant="secondary" icon={<Languages size={12} />} onClick={() => setAbierta(f)}
                      title={t('traduccion_admin.portal_revisar_x', { nombre: f.label })}>
                      {t('traduccion_admin.portal_revisar')}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </TablaSimple>
      )}

      {abierta && (
        <DialogoDeVersionesDeContenido tipo={abierta.content_type} id={abierta.content_id} etiqueta={abierta.label}
          onClose={() => { setAbierta(null); refrescar() }} alCambiar={refrescar} />
      )}
    </section>
  )
}
