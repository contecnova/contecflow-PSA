/**
 * Etiqueta tipo OneNote dentro de una nota (`noteTag`): su icono, color y nombre
 * (las de fábrica traducidas, `cuaderno.tag_<clave>`; las de la empresa y las
 * propias con su nombre).
 */
import type { NodeViewProps } from '@tiptap/react'
import { NodeViewWrapper } from '@tiptap/react'
import { useAppT } from '../../i18n/AppLangContext'
import type { Etiqueta } from '../../services/api/cuaderno'
import { IconoDeEtiqueta, nombreDeEtiqueta } from './comun'

export default function EtiquetaEnLinea({ node, extension }: NodeViewProps) {
  const t = useAppT()
  const clave = String(node.attrs.key || '')
  const lista = (extension.options as { etiquetas?: () => Etiqueta[] }).etiquetas?.() ?? []
  const e = lista.find(x => x.key === clave)
  return (
    <NodeViewWrapper as="span" className={`cdn-etiqueta cdn-color--${e?.color || 'gray'}`} contentEditable={false}
      data-note-tag={clave}>
      <IconoDeEtiqueta icono={e?.icon} />
      <span>{nombreDeEtiqueta(t, e, clave)}</span>
    </NodeViewWrapper>
  )
}
