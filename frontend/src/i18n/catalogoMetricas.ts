/**
 * Nombres de los catálogos del backend que se ven en pantalla: métricas del
 * explorador de informes (`GET /analytics/catalogue`), sus categorías y las
 * métricas del motor de alertas y de previsión del BI.
 *
 * El backend manda el nombre en castellano; aquí cada código pasa por
 * `etiquetaCodigo` con su clave de catálogo (`catalogo_metrica.<id>`…) en los
 * tres idiomas. Si el diccionario no conoce el código (una métrica nueva, o una
 * métrica personalizada de la empresa) se muestra el nombre tal como llegó.
 *
 * Las etiquetas del backend llevan `¤` donde va la moneda de la empresa; el
 * diccionario conserva ese marcador y se sustituye aquí por el símbolo.
 */
import { etiquetaCodigo } from './etiquetaCodigo'

type Traducir = Parameters<typeof etiquetaCodigo>[0]

const conSimbolo = (texto: string, simbolo?: string): string =>
  simbolo ? texto.split('¤').join(simbolo) : texto

/** Nombre de una métrica del catálogo de analítica. */
export function etiquetaMetrica(t: Traducir, id: string | null | undefined, respaldo?: string | null, simbolo?: string): string {
  return conSimbolo(etiquetaCodigo(t, 'catalogo_metrica', id, respaldo), simbolo)
}

/** Descripción de una métrica del catálogo de analítica. */
export function descripcionMetrica(t: Traducir, id: string | null | undefined, respaldo?: string | null): string {
  return etiquetaCodigo(t, 'catalogo_metrica_descripcion', id, respaldo)
}

/** Categoría de métricas («Horas», «Service Desk»…). */
export function etiquetaCategoriaMetrica(t: Traducir, categoria: string | null | undefined): string {
  return etiquetaCodigo(t, 'catalogo_categoria', categoria, categoria)
}

/** Métrica del motor de alertas o de previsión del BI. */
export function etiquetaMetricaBi(t: Traducir, clave: string | null | undefined, respaldo?: string | null, simbolo?: string): string {
  return conSimbolo(etiquetaCodigo(t, 'catalogo_metrica_bi', clave, respaldo), simbolo)
}
