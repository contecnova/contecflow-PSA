import * as React from 'react'
import { useCambiosSinGuardar, type CambiosSinGuardar } from './useCambiosSinGuardar'

/** Dialogos abiertos, del de abajo al de arriba. Esc solo cierra el de arriba. */
const pila: symbol[] = []

export interface OpcionesDeDialogo {
  /** false: no pregunta por cambios sin guardar (solo lectura, confirmaciones). */
  avisarSinGuardar?: boolean
  /** Controlado por la pantalla: manda sobre la deteccion automatica. */
  cambiosSinGuardar?: boolean
}

export interface DialogoEditable<T extends HTMLElement = HTMLDivElement> {
  ref: React.RefObject<T>
  /** Cierre por gesto del usuario (fondo, X, Esc): pregunta si hay cambios. */
  pedirCierre: () => void
  sinGuardar: CambiosSinGuardar<T>
}

/**
 * Comportamiento de dialogo accesible: trampa de foco, Esc para cerrar,
 * devolver el foco al cerrar y (23-11-2026) aviso de cambios sin guardar.
 *
 * Auditoria 2026-11: vivia solo dentro de `Modal`; los dialogos con overlay
 * propio (25, en 15 ficheros) no tenian trampa de foco y la mitad no cerraba
 * con Esc. El hook da el comportamiento sin imponer el aspecto de `Modal`.
 *
 * Cambios sin guardar (`useCambiosSinGuardar`): Esc y cualquier boton con
 * `data-cierra-dialogo` (la X de un Drawer o de un dialogo propio) preguntan
 * antes de cerrar si el usuario ha tocado algo. El fondo lo pone quien pinta
 * el dialogo: debe llamar a `pedirCierre`, no a `onClose`.
 *
 * Uso: `const { ref, pedirCierre } = useDialogoEditable(abierto, cerrar)` y
 * `ref` en el elemento con `role="dialog" aria-modal="true"`.
 */
export function useDialogoEditable<T extends HTMLElement = HTMLDivElement>(
  open: boolean | undefined,
  onClose: (() => void) | undefined,
  opciones: OpcionesDeDialogo = {},
): DialogoEditable<T> {
  const ref = React.useRef<T>(null)
  const onCloseRef = React.useRef(onClose)
  React.useEffect(() => { onCloseRef.current = onClose })

  const sinGuardar = useCambiosSinGuardar<T>(open, {
    ref,
    activo: opciones.avisarSinGuardar !== false,
    cambiosSinGuardar: opciones.cambiosSinGuardar,
  })
  const { estaSucio, confirmarCierre } = sinGuardar

  const pedirCierre = React.useCallback(() => {
    // Sin cambios se cierra al momento (sin esperar a una promesa).
    if (!estaSucio()) { onCloseRef.current?.(); return }
    void confirmarCierre().then(ok => { if (ok) onCloseRef.current?.() })
  }, [estaSucio, confirmarCierre])
  const pedirCierreRef = React.useRef(pedirCierre)
  React.useEffect(() => { pedirCierreRef.current = pedirCierre })

  // El foco previo se lee al renderizar la apertura: en el efecto ya podria
  // tenerlo un `autoFocus` de dentro del dialogo.
  const abiertoAntes = React.useRef(false)
  const previo = React.useRef<HTMLElement | null>(null)
  if (open && !abiertoAntes.current && typeof document !== 'undefined') {
    previo.current = document.activeElement as HTMLElement | null
  }
  abiertoAntes.current = Boolean(open)

  React.useEffect(() => {
    if (!open) return
    const el = ref.current
    if (!el) return
    const id = Symbol('dialogo')
    pila.push(id)
    const enfocables = () => el.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )
    if (!el.contains(document.activeElement)) enfocables()[0]?.focus()

    const trampa = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const lista = enfocables()
      if (lista.length === 0) { e.preventDefault(); return }
      const primero = lista[0]
      const ultimo = lista[lista.length - 1]
      if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus() }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus() }
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && pila[pila.length - 1] === id) pedirCierreRef.current()
    }
    // La X de quien pinta el contenido (Drawer, dialogos propios): si hay
    // cambios, se para el clic antes de que llegue a React y se pregunta.
    const equis = (e: MouseEvent) => {
      const boton = (e.target as Element | null)?.closest?.('[data-cierra-dialogo]')
      if (!boton || !el.contains(boton)) return
      if (boton.closest('[aria-modal="true"]') !== el) return
      if (!estaSucio()) return
      e.preventDefault()
      e.stopPropagation()
      pedirCierreRef.current()
    }

    el.addEventListener('keydown', trampa)
    el.addEventListener('click', equis, true)
    document.addEventListener('keydown', esc)
    const anterior = previo.current
    return () => {
      el.removeEventListener('keydown', trampa)
      el.removeEventListener('click', equis, true)
      document.removeEventListener('keydown', esc)
      const i = pila.indexOf(id)
      if (i >= 0) pila.splice(i, 1)
      anterior?.focus?.()
    }
  }, [open, estaSucio])

  return React.useMemo(() => ({ ref, pedirCierre, sinGuardar }), [pedirCierre, sinGuardar])
}

/**
 * Forma corta (compatibilidad): solo el `ref`. Esc y `data-cierra-dialogo`
 * ya preguntan por cambios sin guardar; para el fondo, usar
 * `useDialogoEditable` y su `pedirCierre`.
 */
export function useDialogo<T extends HTMLElement = HTMLDivElement>(
  open: boolean | undefined,
  onClose: (() => void) | undefined,
  opciones: OpcionesDeDialogo = {},
): React.RefObject<T> {
  return useDialogoEditable<T>(open, onClose, opciones).ref
}
