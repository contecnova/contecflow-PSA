import * as React from 'react'
import { useTextoUi } from './useTextoUi'

/**
 * Cambios sin guardar (23-11-2026).
 *
 * Incidencia de usuario: «al editar, si haces clic fuera del formulario, se
 * cierra sin preguntar y se pierden los cambios». Estándar del kit: si el
 * usuario ha tocado algo dentro de un diálogo (Modal, Drawer, PortalModal o un
 * diálogo propio con `useDialogo`), cerrar con clic fuera, Escape o la X
 * pregunta antes; navegar a otra pantalla por un enlace interno y cerrar o
 * recargar la pestaña también.
 *
 * Cómo sabe que hay cambios, sin tocar cada pantalla:
 *  - Escucha en fase de captura `input` y `change` dentro del contenedor. El
 *    valor de cada campo se apunta al recibir el foco (`focusin`); si el
 *    usuario lo deja como estaba, deja de contar.
 *  - Los controles del kit que no son nativos (SelectRico, CampoFecha)
 *    disparan `ui:cambio` (`avisarCambio`).
 *  - No cuentan: búsquedas (`type="search"`, `role="searchbox"`), lo marcado
 *    con `data-sin-guardar="ignorar"` ni lo que pase en un diálogo anidado.
 *  - La pantalla puede mandar: `cambiosSinGuardar` (controlado) o
 *    `useSinGuardarDelDialogo().reiniciar()` tras guardar sin cerrar.
 *
 * El cierre programático (la pantalla llama a su `onClose` tras guardar o
 * pone `open=false`) no pregunta: solo preguntan los gestos de cierre que
 * pasan por el kit.
 *
 * Es solo interfaz: no hay nada que auditar en servidor (no se guarda nada).
 */

/** Evento que disparan los controles no nativos al cambiar por el usuario. */
export const EVENTO_CAMBIO = 'ui:cambio'

/** Avisa al diálogo que lo contenga de que el usuario ha cambiado un valor. */
export function avisarCambio(el: EventTarget | null | undefined): void {
  if (!el || typeof CustomEvent === 'undefined') return
  el.dispatchEvent(new CustomEvent(EVENTO_CAMBIO, { bubbles: true }))
}

export interface TextosDeDescarte {
  titulo: string
  mensaje: string
  descartar: string
  seguir: string
}

/** Pregunta de descarte: resuelve true si el usuario descarta. */
export type PreguntaDeDescarte = (textos: TextosDeDescarte) => Promise<boolean>

let preguntaDeDescarte: PreguntaDeDescarte | null = null

/**
 * La pone `ConfirmProvider` al montarse (diálogo de confirmación único del
 * producto). Se inyecta para no importar `context/` desde el kit (ciclo).
 */
export function fijarPreguntaDeDescarte(fn: PreguntaDeDescarte | null): void {
  preguntaDeDescarte = fn
}

let preguntando = false

/** Pregunta (una sola vez a la vez). Sin proveedor, deja cerrar como antes. */
function preguntar(textos: TextosDeDescarte): Promise<boolean> {
  if (preguntando) return Promise.resolve(false)
  if (!preguntaDeDescarte) return Promise.resolve(true)
  preguntando = true
  return preguntaDeDescarte(textos).finally(() => { preguntando = false })
}

// ── Registro global: navegación y cierre de pestaña ─────────────────────────
interface Guardia {
  estaSucio: () => boolean
  descartar: () => void
  textos: () => TextosDeDescarte
}

const guardias: Guardia[] = []

/** La guardia sucia de más arriba (la última abierta), si la hay. */
function guardiaSucia(): Guardia | undefined {
  for (let i = guardias.length - 1; i >= 0; i -= 1) {
    if (guardias[i].estaSucio()) return guardias[i]
  }
  return undefined
}

/** true si algún diálogo abierto tiene cambios sin guardar. */
export function hayCambiosSinGuardar(): boolean {
  return guardiaSucia() !== undefined
}

/**
 * Tras guardar SIN cerrar (paneles con varias secciones que se guardan por
 * separado): olvida los cambios del diálogo de más arriba. Se puede llamar
 * desde fuera del diálogo (p. ej. en el `onSuccess` de la mutación).
 */
export function cambiosGuardados(): void {
  guardias[guardias.length - 1]?.descartar()
}

/**
 * Para cierres hechos a mano por una pantalla (clic fuera de un panel propio,
 * atajos de teclado): resuelve true si no hay cambios o el usuario descarta.
 */
export function confirmarDescarte(): Promise<boolean> {
  const sucia = guardiaSucia()
  if (!sucia) return Promise.resolve(true)
  return preguntar(sucia.textos()).then(ok => {
    if (ok) guardias.slice().forEach(g => g.descartar())
    return ok
  })
}

const alSalir = (e: BeforeUnloadEvent) => {
  if (!hayCambiosSinGuardar()) return
  e.preventDefault()
  // Los navegadores antiguos lo piden; el texto lo pone el navegador.
  e.returnValue = ''
}

/**
 * Enlaces internos (`<a href>`, `<Link>`, `<NavLink>`): la app usa
 * `BrowserRouter`, sin data router, así que `useBlocker` no sirve. Se
 * intercepta el clic en captura sobre `document` (antes que React, que escucha
 * en `#root`) y, si el usuario descarta, se repite el clic.
 */
const alPulsarEnlace = (e: MouseEvent) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
  if (!a) return
  if ((a.target && a.target !== '_self') || a.hasAttribute('download')) return
  let url: URL
  try { url = new URL(a.href, window.location.href) } catch { return }
  if (url.origin !== window.location.origin) return
  // Un ancla dentro de la misma página no sale de ella.
  if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return
  const sucia = guardiaSucia()
  if (!sucia) return
  e.preventDefault()
  e.stopPropagation()
  void preguntar(sucia.textos()).then(ok => {
    if (!ok) return
    guardias.slice().forEach(g => g.descartar())
    if (a.isConnected) a.click()
    else window.location.assign(url.href)
  })
}

function registrar(g: Guardia): () => void {
  guardias.push(g)
  if (guardias.length === 1 && typeof window !== 'undefined') {
    window.addEventListener('beforeunload', alSalir)
    document.addEventListener('click', alPulsarEnlace, true)
  }
  return () => {
    const i = guardias.indexOf(g)
    if (i >= 0) guardias.splice(i, 1)
    if (guardias.length === 0 && typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', alSalir)
      document.removeEventListener('click', alPulsarEnlace, true)
    }
  }
}

/** Solo tests: vacía el registro y la pregunta en curso. */
export function _reiniciarCambiosSinGuardar(): void {
  guardias.length = 0
  preguntando = false
  if (typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', alSalir)
    document.removeEventListener('click', alPulsarEnlace, true)
  }
}

// ── Detección ───────────────────────────────────────────────────────────────
const TIPOS_SIN_DATOS = new Set(['search', 'button', 'submit', 'reset', 'image'])

/** Valor comparable de un control, o null si no se puede comparar. */
function valorDe(n: Element): string | null {
  if (n instanceof HTMLInputElement) {
    if (n.type === 'checkbox' || n.type === 'radio') return String(n.checked)
    if (n.type === 'file') return null
    return n.value
  }
  if (n instanceof HTMLTextAreaElement) return n.value
  if (n instanceof HTMLSelectElement) return Array.from(n.selectedOptions).map(o => o.value).join('\u0000')
  if (n instanceof HTMLElement && n.isContentEditable) return n.innerHTML
  return null
}

function ignorado(n: Element): boolean {
  if (n.closest('[data-sin-guardar="ignorar"]')) return true
  if (n.getAttribute('role') === 'searchbox') return true
  return n instanceof HTMLInputElement && TIPOS_SIN_DATOS.has(n.type)
}

export interface OpcionesSinGuardar<T extends HTMLElement = HTMLDivElement> {
  /** false: no vigila (diálogos de solo lectura o de confirmación). */
  activo?: boolean
  /** Controlado por la pantalla: si se pasa, manda sobre la detección. */
  cambiosSinGuardar?: boolean
  /** Contenedor a vigilar; si no se pasa, se usa el `ref` devuelto. */
  ref?: React.RefObject<T>
}

export interface CambiosSinGuardar<T extends HTMLElement = HTMLDivElement> {
  /** Ponerlo en el contenedor del formulario (si no se pasó uno). */
  ref: React.RefObject<T>
  /** ¿Hay cambios sin guardar ahora mismo? */
  estaSucio: () => boolean
  /** Marca cambios a mano (controles propios que no disparan `input`). */
  marcarSucio: () => void
  /** Olvida los cambios (p. ej. tras guardar sin cerrar). */
  reiniciar: () => void
  /** Resuelve true si se puede cerrar: no hay cambios o el usuario descarta. */
  confirmarCierre: () => Promise<boolean>
}

/**
 * Vigila los cambios del usuario dentro de un contenedor mientras `abierto`.
 * Lo usan `useDialogo` (y con él Modal, Drawer y PortalModal); una pantalla con
 * un panel de edición propio puede usarlo directamente.
 */
export function useCambiosSinGuardar<T extends HTMLElement = HTMLDivElement>(
  abierto: boolean | undefined,
  opciones: OpcionesSinGuardar<T> = {},
): CambiosSinGuardar<T> {
  const propia = React.useRef<T>(null)
  const ref = opciones.ref ?? propia
  const activo = opciones.activo !== false
  const t = useTextoUi()

  const config = React.useRef({ activo, forzado: opciones.cambiosSinGuardar, t })
  React.useEffect(() => { config.current = { activo, forzado: opciones.cambiosSinGuardar, t } })

  const estado = React.useRef({ marcado: false, campos: new Set<Element>(), originales: new WeakMap<Element, string | null>() })

  const reiniciar = React.useCallback(() => {
    estado.current = { marcado: false, campos: new Set<Element>(), originales: new WeakMap<Element, string | null>() }
  }, [])
  const marcarSucio = React.useCallback(() => { estado.current.marcado = true }, [])
  const estaSucio = React.useCallback(() => {
    const c = config.current
    if (!c.activo) return false
    if (typeof c.forzado === 'boolean') return c.forzado
    const e = estado.current
    return e.marcado || e.campos.size > 0
  }, [])
  const textos = React.useCallback((): TextosDeDescarte => {
    const tr = config.current.t
    return {
      titulo: tr('sin_guardar.titulo'),
      mensaje: tr('sin_guardar.mensaje'),
      descartar: tr('sin_guardar.descartar'),
      seguir: tr('sin_guardar.seguir'),
    }
  }, [])
  const confirmarCierre = React.useCallback(async () => {
    if (!estaSucio()) return true
    const ok = await preguntar(textos())
    if (ok) reiniciar()
    return ok
  }, [estaSucio, textos, reiniciar])

  // Cada apertura empieza limpia.
  React.useEffect(() => { if (abierto) reiniciar() }, [abierto, reiniciar])

  React.useEffect(() => {
    if (!abierto || !activo) return undefined
    const el = ref.current
    if (!el) return undefined

    /** El control, si es de este contenedor (no de un diálogo anidado). */
    const propio = (n: EventTarget | null): Element | null => {
      if (!(n instanceof Element) || !el.contains(n)) return null
      const dialogo = n.closest('[aria-modal="true"]')
      if (dialogo && dialogo !== el && el.contains(dialogo)) return null
      return n
    }
    const alEnfocar = (ev: Event) => {
      const n = propio(ev.target)
      if (!n) return
      const e = estado.current
      if (!e.originales.has(n)) e.originales.set(n, valorDe(n))
    }
    const alCambiar = (ev: Event) => {
      const n = propio(ev.target)
      if (!n || ignorado(n)) return
      const e = estado.current
      const v = valorDe(n)
      if (v !== null && e.originales.has(n) && e.originales.get(n) === v) e.campos.delete(n)
      else e.campos.add(n)
    }
    const alAvisar = (ev: Event) => {
      const n = propio(ev.target)
      if (n && !ignorado(n)) estado.current.marcado = true
    }
    el.addEventListener('focusin', alEnfocar, true)
    el.addEventListener('input', alCambiar, true)
    el.addEventListener('change', alCambiar, true)
    el.addEventListener(EVENTO_CAMBIO, alAvisar, true)
    const quitar = registrar({ estaSucio, descartar: reiniciar, textos })
    return () => {
      el.removeEventListener('focusin', alEnfocar, true)
      el.removeEventListener('input', alCambiar, true)
      el.removeEventListener('change', alCambiar, true)
      el.removeEventListener(EVENTO_CAMBIO, alAvisar, true)
      quitar()
    }
  }, [abierto, activo, ref, estaSucio, reiniciar, textos])

  return React.useMemo(
    () => ({ ref, estaSucio, marcarSucio, reiniciar, confirmarCierre }),
    [ref, estaSucio, marcarSucio, reiniciar, confirmarCierre],
  )
}

// ── Contexto para el contenido del diálogo ──────────────────────────────────
export interface SinGuardarDelDialogo {
  estaSucio: () => boolean
  marcarSucio: () => void
  reiniciar: () => void
}

const NADA: SinGuardarDelDialogo = { estaSucio: () => false, marcarSucio: () => {}, reiniciar: () => {} }

export const SinGuardarContext = React.createContext<SinGuardarDelDialogo>(NADA)

/**
 * Para el contenido de un Modal/Drawer: `reiniciar()` tras guardar sin cerrar,
 * `marcarSucio()` desde un control propio. Fuera de un diálogo no hace nada.
 */
export function useSinGuardarDelDialogo(): SinGuardarDelDialogo {
  return React.useContext(SinGuardarContext)
}
