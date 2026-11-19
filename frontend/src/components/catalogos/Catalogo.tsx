/**
 * Piezas para pintar un catálogo de clave del backend (19-11-2026): las
 * `<option>` de un selector y la etiqueta de una clave. Leen `useCatalogo`
 * (una consulta compartida y cacheada), así que se pueden usar en filas de
 * tabla sin multiplicar peticiones.
 */
import { useCatalogo } from '../../hooks/useCatalogo'
import type { NombreDeCatalogo } from '../../services/api/catalogos'

/** Las `<option>` del catálogo (valores activos de la empresa), con su etiqueta traducida. */
export function OpcionesDeCatalogo({ catalogo }: { catalogo: NombreDeCatalogo }) {
  const { opciones } = useCatalogo(catalogo)
  return <>{opciones.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</>
}

/** La etiqueta traducida de una clave (o la de la empresa, o la clave tal cual). */
export function EtiquetaDeCatalogo({ catalogo, clave }: { catalogo: NombreDeCatalogo; clave: string | null | undefined }) {
  const { etiqueta } = useCatalogo(catalogo)
  return <>{etiqueta(clave)}</>
}
