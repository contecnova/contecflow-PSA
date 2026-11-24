/**
 * Menú desplegable pequeño del cuaderno (barra del editor y árbol): un botón de
 * icono que abre una lista de acciones. Esc y clic fuera lo cierran.
 */
import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { IconButton, Pulsable } from '../ui'

export interface OpcionDeMenu {
  id: string
  label: string
  icon?: ReactNode
  onSelect: () => void
  disabled?: boolean
  peligro?: boolean
}

export default function Menu({ etiqueta, icono, opciones, alinear = 'izquierda' }: {
  etiqueta: string; icono: ReactNode; opciones: OpcionDeMenu[]; alinear?: 'izquierda' | 'derecha'
}) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef<HTMLDivElement>(null)
  const id = useId()
  useEffect(() => {
    if (!abierto) return undefined
    const fuera = (e: MouseEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierto(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setAbierto(false) }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', fuera); document.removeEventListener('keydown', esc) }
  }, [abierto])
  return (
    <div className="cdn-menu" ref={caja}>
      <IconButton ariaLabel={etiqueta} title={etiqueta} aria-haspopup="menu" aria-expanded={abierto} aria-controls={id}
        onClick={() => setAbierto(a => !a)} className="cdn-boton">
        {icono}
      </IconButton>
      {abierto && (
        <div id={id} role="menu" className={`cdn-menu__lista cdn-menu__lista--${alinear}`}>
          {opciones.map(o => (
            <Pulsable key={o.id} role="menuitem" disabled={o.disabled}
              className={`cdn-menu__item${o.peligro ? ' cdn-menu__item--peligro' : ''}`}
              onClick={() => { setAbierto(false); o.onSelect() }}>
              {o.icon}<span>{o.label}</span>
            </Pulsable>
          ))}
        </div>
      )}
    </div>
  )
}
