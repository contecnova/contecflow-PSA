/**
 * VersionesDeContenidoPanel — versiones de un aviso o de una categoría o
 * servicio del catálogo en los idiomas del portal (17-11-2026).
 *
 * El panel genérico (`VersionesPanel`) con el adaptador de
 * `/translation/portal-content/{tipo}/{id}`. Nacen en revisión; las publica un
 * revisor (administrador o cola de revisores); el portal sirve la publicada y,
 * sin ella, la traducción automática marcada.
 */
import { useMemo } from 'react'
import { Modal } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { traduccionApi, type TipoDeContenidoDelPortal, type VersionDeContenido } from '../../services/api/traduccion'
import VersionesPanel, { type AdaptadorDeVersiones, type CampoDeVersion, type VersionGenerica } from './VersionesPanel'

const CAMPOS: Record<TipoDeContenidoDelPortal, CampoDeVersion[]> = {
  announcement: [
    { clave: 'title', etiqueta: 'traduccion_admin.kb_campo_titulo', obligatorio: true },
    { clave: 'body', etiqueta: 'traduccion_admin.portal_campo_mensaje', multilinea: true },
  ],
  catalog_category: [
    { clave: 'name', etiqueta: 'traduccion_admin.portal_campo_nombre', obligatorio: true },
    { clave: 'description', etiqueta: 'traduccion_admin.portal_campo_descripcion', multilinea: true },
  ],
  catalog_service: [
    { clave: 'name', etiqueta: 'traduccion_admin.portal_campo_nombre', obligatorio: true },
    { clave: 'description', etiqueta: 'traduccion_admin.portal_campo_descripcion', multilinea: true },
  ],
}

function generica(v: VersionDeContenido): VersionGenerica {
  return { id: v.id, language: v.language, status: v.status, outdated: v.outdated, review_comment: v.review_comment, campos: v.fields ?? {} }
}

export function claveDeVersionesDeContenido(tipo: TipoDeContenidoDelPortal, id: string) {
  return ['traduccion-contenido', tipo, id] as const
}

export default function VersionesDeContenidoPanel({ tipo, id, alCambiar }: {
  tipo: TipoDeContenidoDelPortal; id: string; alCambiar?: () => void
}) {
  const adaptador = useMemo<AdaptadorDeVersiones>(() => ({
    clave: claveDeVersionesDeContenido(tipo, id),
    campos: CAMPOS[tipo],
    listar: () => traduccionApi.versionesDeContenido(tipo, id).then(d => ({ ...d, items: d.items.map(generica) })),
    generar: languages => traduccionApi.generarContenido(tipo, id, languages),
    editar: (language, campos) => traduccionApi.editarContenido(tipo, id, language, campos),
    revisar: (language, d) => traduccionApi.revisarContenido(tipo, id, language, d),
    borrar: language => traduccionApi.borrarContenido(tipo, id, language),
    textos: {
      sin_versiones: 'traduccion_admin.portal_sin_versiones',
      desactivado: 'traduccion_admin.portal_desactivado',
      desfasada_ayuda: 'traduccion_admin.portal_desfasada_ayuda',
    },
    alCambiar,
  }), [tipo, id, alCambiar])
  return <VersionesPanel adaptador={adaptador} />
}

/** El panel en un diálogo: lo abren el catálogo, los avisos y la pantalla de revisión. */
export function DialogoDeVersionesDeContenido({ tipo, id, etiqueta, onClose, alCambiar }: {
  tipo: TipoDeContenidoDelPortal; id: string; etiqueta: string; onClose: () => void; alCambiar?: () => void
}) {
  const t = useAppT()
  return (
    <Modal open onClose={onClose} size="lg" title={t('traduccion_admin.portal_versiones_de', { nombre: etiqueta })}>
      <VersionesDeContenidoPanel tipo={tipo} id={id} alCambiar={alCambiar} />
    </Modal>
  )
}
