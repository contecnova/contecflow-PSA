/**
 * Marca «Traducido automáticamente» del portal de clientes (16-11-2026).
 *
 * El servidor traduce al idioma del cliente lo que escriben los operadores
 * (avisos, wiki del portal, catálogo, etiquetas de los formularios dinámicos:
 * `app/services/traduccion/contenido_del_portal.py`) y cada elemento traducido
 * llega con `translated_from` (idioma de origen) y `original` (`{campo: texto}`).
 *
 * Es la variante del portal de `components/traduccion/TextoTraducido` (que es de
 * operador y usa su traductor): mismos estilos (`traduccion.css`), textos del
 * portal en sus 8 idiomas (`traduccion_portal.*`).
 *
 * - `MarcaDeTraduccion`: solo la línea de la marca, controlada (para listas que
 *   comparten un único «Ver original», como el catálogo dentro de un selector).
 * - `TraduccionAutomatica`: un elemento con su propio «Ver original»; los hijos
 *   reciben `texto(campo, actual)`, que da el original cuando se pide.
 */
import { useState, type ReactNode } from 'react'
import { Languages } from 'lucide-react'
import { useIdiomaDelPortal, useLang } from './portalClientContext'
import '../../components/traduccion/traduccion.css'
import { Button } from '../../components/ui'

/** Lo que el servidor añade a un elemento traducido. */
export interface ContenidoTraducido {
  translated_from?: string | null
  language?: string | null
  original?: Record<string, string> | null
}

/** Nombre del idioma `codigo` en el idioma de la pantalla (`Intl`, sin diccionario). */
export function nombreDelIdioma(codigo: string | null | undefined, idiomaDeLaPantalla: string): string {
  if (!codigo) return ''
  try {
    return new Intl.DisplayNames([idiomaDeLaPantalla], { type: 'language' }).of(codigo) ?? codigo
  } catch {
    return codigo
  }
}

/** ¿El elemento viene traducido automáticamente? */
export function estaTraducido(item: ContenidoTraducido | null | undefined): boolean {
  return !!item?.translated_from
}

/** El texto de `campo` del elemento: el original si se pide y existe; si no, `actual`. */
export function textoDe(item: ContenidoTraducido | null | undefined, campo: string,
  actual: string | null | undefined, verOriginal: boolean): string {
  const original = item?.original?.[campo]
  return verOriginal && typeof original === 'string' ? original : (actual ?? '')
}

interface MarcaProps {
  /** Idioma de origen (`translated_from`). */
  origen: string | null | undefined
  verOriginal: boolean
  onAlternar: () => void
  /** Sin original que enseñar, solo la marca (sin botón). */
  puedeVerOriginal?: boolean
}

/** La línea «Traducido automáticamente del X · Ver original». */
export function MarcaDeTraduccion({ origen, verOriginal, onAlternar, puedeVerOriginal = true }: MarcaProps) {
  const t = useLang()
  const lang = useIdiomaDelPortal()
  if (!origen) return null
  const idioma = nombreDelIdioma(origen, lang)
  return (
    <div className="trad-marca">
      <Languages size={12} aria-hidden="true" />
      <span>{verOriginal
        ? t('traduccion_portal.marca_original', { idioma })
        : t('traduccion_portal.marca_auto', { idioma })}</span>
      {puedeVerOriginal && (
        <Button variant="link" size="xs" className="trad-enlace" aria-pressed={verOriginal} onClick={onAlternar}>
          {verOriginal ? t('traduccion_portal.ver_traduccion') : t('traduccion_portal.ver_original')}
        </Button>
      )}
    </div>
  )
}

interface Props {
  item: ContenidoTraducido | null | undefined
  /** `texto(campo, actual)`: lo que hay que pintar de ese campo. */
  children: (texto: (campo: string, actual: string | null | undefined) => string, verOriginal: boolean) => ReactNode
}

/** Un elemento con la marca debajo si llegó traducido; si no, tal cual. */
export default function TraduccionAutomatica({ item, children }: Props) {
  const [verOriginal, setVerOriginal] = useState(false)
  const traducido = estaTraducido(item)
  const ver = traducido && verOriginal
  const texto = (campo: string, actual: string | null | undefined) => textoDe(item, campo, actual, ver)
  if (!traducido) return <>{children(texto, false)}</>
  return (
    <div className="trad-bloque" lang={ver ? item?.translated_from ?? undefined : item?.language ?? undefined}>
      {children(texto, ver)}
      <MarcaDeTraduccion origen={item?.translated_from} verOriginal={ver}
        onAlternar={() => setVerOriginal(v => !v)}
        puedeVerOriginal={!!item?.original && Object.keys(item.original).length > 0} />
    </div>
  )
}
