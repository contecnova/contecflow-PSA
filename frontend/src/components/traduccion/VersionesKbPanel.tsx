/**
 * VersionesKbPanel — versiones de un artículo de la base de conocimiento en otros
 * idiomas (traducción en tiempo real, 16-11-2026).
 *
 * 17-11-2026: el panel es el genérico (`VersionesPanel`), el mismo de avisos y
 * catálogo; aquí solo va el adaptador de la KB (`/translation/kb/{id}`, campos
 * título, resumen y contenido).
 */
import { useMemo } from 'react'
import { traduccionApi, type VersionKb } from '../../services/api/traduccion'
import VersionesPanel, { type AdaptadorDeVersiones, type VersionGenerica } from './VersionesPanel'

const CAMPOS = [
  { clave: 'title', etiqueta: 'traduccion_admin.kb_campo_titulo', obligatorio: true },
  { clave: 'summary', etiqueta: 'traduccion_admin.kb_campo_resumen' },
  { clave: 'body', etiqueta: 'traduccion_admin.kb_campo_cuerpo', multilinea: true, obligatorio: true },
]

function generica(v: VersionKb): VersionGenerica {
  return {
    id: v.id, language: v.language, status: v.status, outdated: v.outdated, review_comment: v.review_comment,
    campos: { title: v.title, summary: v.summary ?? '', body: v.body },
  }
}

export default function VersionesKbPanel({ articleId }: { articleId: string }) {
  const adaptador = useMemo<AdaptadorDeVersiones>(() => ({
    clave: ['traduccion-kb', articleId],
    campos: CAMPOS,
    listar: () => traduccionApi.versionesKb(articleId).then(d => ({ ...d, items: d.items.map(generica) })),
    generar: languages => traduccionApi.generarKb(articleId, languages),
    editar: (language, c) => traduccionApi.editarKb(articleId, language, { title: c.title, summary: c.summary, body: c.body }),
    revisar: (language, d) => traduccionApi.revisarKb(articleId, language, d),
    borrar: language => traduccionApi.borrarKb(articleId, language),
  }), [articleId])
  return <VersionesPanel adaptador={adaptador} />
}
