import * as React from 'react'

/** Dialogos abiertos, del de abajo al de arriba. Esc solo cierra el de arriba. */
const pila: symbol[] = []

/**
 * Comportamiento de dialogo accesible: trampa de foco, Esc para cerrar y
 * devolver el foco al cerrar.
 *
 * Auditoria 2026-11: vivia solo dentro de `Modal`; los dialogos con overlay
 * propio (25, en 15 ficheros) no tenian trampa de foco y la mitad no cerraba
 * con Esc. El hook da el comportamiento sin imponer el aspecto de `Modal`.
 *
 * Uso: `const ref = useDialogo(abierto, cerrar)` y `ref` en el elemento con
 * `role="dialog" aria-modal="true"`.
 */
export function useDialogo<T extends HTMLElement = HTMLDivElement>(
  open: boolean | undefined,
  onClose: (() => void) | undefined,
): React.RefObject<T> {
  const ref = React.useRef<T>(null)
  const onCloseRef = React.useRef(onClose)
  React.useEffect(() => { onCloseRef.current = onClose })

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
      if (e.key === 'Escape' && pila[pila.length - 1] === id) onCloseRef.current?.()
    }

    el.addEventListener('keydown', trampa)
    document.addEventListener('keydown', esc)
    const anterior = previo.current
    return () => {
      el.removeEventListener('keydown', trampa)
      document.removeEventListener('keydown', esc)
      const i = pila.indexOf(id)
      if (i >= 0) pila.splice(i, 1)
      anterior?.focus?.()
    }
  }, [open])

  return ref
}
