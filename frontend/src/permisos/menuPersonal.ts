/**
 * Menú lateral personalizable (23-11-2026, feedback de usuarios): orden de las
 * categorías, orden de las pestañas y pestañas ocultas de cada persona.
 *
 * Reglas:
 * - **Ocultar no quita permisos.** `aplicarMenu` recibe el menú YA filtrado por
 *   la matriz de permisos (`navegacion.ts`) y solo puede quitar o reordenar: una
 *   ruta no permitida que esté en la preferencia no aparece nunca. La ruta oculta
 *   se sigue abriendo (por URL, migas, ⌘K: nada de eso lee esta preferencia).
 * - **Tolerante a cambios del menú** (`version`): ids y rutas que ya no existen
 *   se ignoran; las categorías y pestañas nuevas salen al final y visibles.
 * - **De dónde sale**: la de la persona (`user_preferences.extra.menu`) o, si no
 *   tiene, la de su rol en su empresa (Configuración › «Menú por defecto»,
 *   `GET /settings/menu-default/mine`), o el orden del código. «Restablecer»
 *   borra la de la persona y vuelve a la del rol.
 *
 * El backend valida la misma forma (`app/services/settings_service/menu_por_defecto.py`).
 */

/** Versión del esquema (la misma que `VERSION` del backend). */
export const VERSION_DEL_MENU = 1

export interface PreferenciaDeMenu {
  version: number
  /** Ids de categoría en el orden elegido. */
  orden: string[]
  /** Rutas ocultas por categoría. */
  ocultas: Record<string, string[]>
  /** Orden de las pestañas por categoría. */
  orden_pestanas: Record<string, string[]>
}

export const MENU_DE_FABRICA: PreferenciaDeMenu = { version: VERSION_DEL_MENU, orden: [], ocultas: {}, orden_pestanas: {} }

type ItemBase = { to?: string; divider?: boolean }
type GrupoBase<I extends ItemBase = ItemBase> = { id?: string; items: I[] }

const textos = (v: unknown): string[] =>
  Array.isArray(v) ? [...new Set(v.filter((x): x is string => typeof x === 'string'))] : []

const porCategoria = (v: unknown): Record<string, string[]> => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return {}
  const salida: Record<string, string[]> = {}
  for (const [k, lista] of Object.entries(v as Record<string, unknown>)) {
    const l = textos(lista)
    if (l.length) salida[k] = l
  }
  return salida
}

/**
 * La preferencia leída del servidor, limpia; `null` si no hay o no tiene forma
 * de menú. Una versión posterior se lee igual (los campos solo se añaden).
 */
export function normalizarPreferencia(crudo: unknown): PreferenciaDeMenu | null {
  if (!crudo || typeof crudo !== 'object' || Array.isArray(crudo)) return null
  const c = crudo as Record<string, unknown>
  const version = typeof c.version === 'number' && c.version >= 1 ? c.version : VERSION_DEL_MENU
  return {
    version: Math.max(version, VERSION_DEL_MENU),
    orden: textos(c.orden),
    ocultas: porCategoria(c.ocultas),
    orden_pestanas: porCategoria(c.orden_pestanas),
  }
}

/** La que manda: la de la persona, si no la de su rol, si no ninguna (orden del código). */
export function menuEfectivo(personal: PreferenciaDeMenu | null | undefined, delRol: PreferenciaDeMenu | null | undefined): PreferenciaDeMenu | null {
  return personal ?? delRol ?? null
}

/** `elems` en el orden de `orden` (lo que no está en `orden`, nuevo, al final y en su orden de fábrica). */
export function ordenarSegun<T>(elems: T[], clave: (e: T) => string, orden: string[] | undefined): T[] {
  if (!orden?.length) return [...elems]
  const pos = new Map(orden.map((id, i) => [id, i]))
  return elems
    .map((e, i) => ({ e, i, p: pos.get(clave(e)) }))
    .sort((a, b) => {
      if (a.p !== undefined && b.p !== undefined) return a.p - b.p
      if (a.p !== undefined) return -1
      if (b.p !== undefined) return 1
      return a.i - b.i
    })
    .map(x => x.e)
}

/** Las pestañas de una categoría en el orden elegido (todas, ocultas incluidas). */
export function pestanasOrdenadas<I extends ItemBase>(grupo: GrupoBase<I>, pref: PreferenciaDeMenu | null): I[] {
  const reales = grupo.items.filter(i => !i.divider && i.to)
  return ordenarSegun(reales, i => i.to || '', pref?.orden_pestanas[grupo.id || ''])
}

/** Las categorías en el orden elegido (con todas sus pestañas). */
export function categoriasOrdenadas<G extends GrupoBase>(grupos: G[], pref: PreferenciaDeMenu | null): G[] {
  return ordenarSegun(grupos, g => g.id || '', pref?.orden)
}

export function estaOculta(pref: PreferenciaDeMenu | null, grupoId: string, ruta: string): boolean {
  return !!pref?.ocultas[grupoId]?.includes(ruta)
}

/**
 * El menú que se pinta: categorías y pestañas en su orden, sin las ocultas.
 * `grupos` llega ya filtrado por permisos: esto solo quita y reordena.
 */
export function aplicarMenu<I extends ItemBase, G extends GrupoBase<I>>(grupos: G[], pref: PreferenciaDeMenu | null): G[] {
  if (!pref) return grupos
  return categoriasOrdenadas(grupos, pref).map(g => ({
    ...g,
    items: pestanasOrdenadas(g, pref).filter(i => !estaOculta(pref, g.id || '', i.to || '')),
  }))
}

const copia = (pref: PreferenciaDeMenu | null): PreferenciaDeMenu => ({
  version: VERSION_DEL_MENU,
  orden: [...(pref?.orden ?? [])],
  ocultas: Object.fromEntries(Object.entries(pref?.ocultas ?? {}).map(([k, v]) => [k, [...v]])),
  orden_pestanas: Object.fromEntries(Object.entries(pref?.orden_pestanas ?? {}).map(([k, v]) => [k, [...v]])),
})

/** Muestra u oculta una pestaña. */
export function alternarOculta(pref: PreferenciaDeMenu | null, grupoId: string, ruta: string): PreferenciaDeMenu {
  const nueva = copia(pref)
  const actual = nueva.ocultas[grupoId] ?? []
  const lista = actual.includes(ruta) ? actual.filter(r => r !== ruta) : [...actual, ruta]
  if (lista.length) nueva.ocultas[grupoId] = lista
  else delete nueva.ocultas[grupoId]
  return nueva
}

/** Mueve un elemento de `desde` a `hasta` (índices de `ids`). */
export function mover(ids: string[], desde: number, hasta: number): string[] {
  if (desde < 0 || desde >= ids.length || hasta < 0 || hasta >= ids.length || desde === hasta) return [...ids]
  const r = [...ids]
  const [e] = r.splice(desde, 1)
  r.splice(hasta, 0, e)
  return r
}

/** Nuevo orden de categorías. `ids`: el orden que se ve ahora (todas las de la persona). */
export function moverCategoria(pref: PreferenciaDeMenu | null, ids: string[], desde: number, hasta: number): PreferenciaDeMenu {
  return { ...copia(pref), orden: mover(ids, desde, hasta) }
}

/** Nuevo orden de pestañas de una categoría. `rutas`: el orden que se ve ahora. */
export function moverPestana(pref: PreferenciaDeMenu | null, grupoId: string, rutas: string[], desde: number, hasta: number): PreferenciaDeMenu {
  const nueva = copia(pref)
  nueva.orden_pestanas[grupoId] = mover(rutas, desde, hasta)
  return nueva
}
