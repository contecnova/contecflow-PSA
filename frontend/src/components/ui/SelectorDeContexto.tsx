import type { ReactNode } from 'react'
import './SelectorDeContexto.css'

/**
 * SelectorDeContexto — la barra de contexto de una pantalla (proyecto, cliente,
 * unidad, sprint, periodo…): una tarjeta con uno o varios campos del kit con
 * etiqueta (`<Select label=… />`, `<SelectorDePeriodo label=… />`) y un hueco
 * opcional de acciones. Es el patrón de Matriz RACI y el único permitido: ningún
 * selector de contexto va suelto, a todo el ancho ni con etiqueta propia.
 */
export interface SelectorDeContextoProps {
  /** Campos del kit con etiqueta. */
  children: ReactNode
  /** Botones a la derecha de los campos. */
  acciones?: ReactNode
  className?: string
}

export default function SelectorDeContexto({ children, acciones, className }: SelectorDeContextoProps) {
  return (
    <div className={`ui-card ui-contexto${className ? ` ${className}` : ''}`}>
      <div className="ui-contexto__campos">{children}</div>
      {acciones && <div className="ui-contexto__acciones">{acciones}</div>}
    </div>
  )
}
