/**
 * Etiqueta traducida de un código que viene del backend o de una constante
 * compartida (estado, prioridad, rol, tipo…).
 *
 * Un único sitio para todas las pantallas: la clave es `<catalogo>.<codigo>`
 * (p. ej. `estado.in_progress`) y, si el diccionario no la define, se devuelve
 * el nombre que mandó el backend (`respaldo`) o, en último caso, el código tal
 * cual. Así un código nuevo del backend se ve (sin traducir) en vez de romper
 * la pantalla o enseñar una clave interna.
 */
/** Cualquier `t` de la app (con o sin proveedor): solo se le pide clave y, si la acepta, respaldo. */
type Traducir = (clave: string, segundo?: never) => string

/** Normaliza el código para que sea un segmento de clave válido (sin tildes: «Formación» → `formacion`). */
function segmento(codigo: string): string {
  return codigo
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

export function etiquetaCodigo(
  t: Traducir,
  catalogo: string,
  codigo: string | null | undefined,
  respaldo?: string | null,
): string {
  if (codigo == null || codigo === '') return respaldo ?? ''
  const seg = segmento(String(codigo))
  const visible = respaldo || String(codigo)
  if (!seg) return visible
  return (t as unknown as (c: string, r?: string) => string)(`${catalogo}.${seg}`, visible)
}
