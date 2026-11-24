import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react'
import './IconButton.css'

/** Aspecto del botón: `simple` (por defecto, sin borde: barras, cabeceras de
 *  modal, campos) o `caja` (cuadrado con borde fino: acciones de tarjeta y fila). */
export type VarianteIconButton = 'simple' | 'caja'
/** Color del icono y del borde (solo en `caja`). */
export type TonoIconButton = 'neutro' | 'peligro' | 'acento'
/** Alto (= ancho) de la caja: xs 26 px, sm 32 px, md 38 px (tokens --alto-control-*). */
export type TamanoIconButton = 'xs' | 'sm' | 'md'

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  /** Obligatorio: es lo único que nombra el botón (lector de pantalla y tooltip). */
  ariaLabel: string
  title?: string
  children: ReactNode
  /** Clases extra (se suman a `icon-button`). */
  className?: string
  style?: CSSProperties
  type?: 'button' | 'submit' | 'reset'
  /** `caja`: cuadrado de tamaño fijo, borde --surface-4, icono centrado. Estándar
   *  de editar/borrar/más/copiar en tarjetas y filas (DESIGN_SYSTEM.md). */
  variante?: VarianteIconButton
  /** Solo con `variante="caja"`. Por defecto `neutro`. */
  tono?: TonoIconButton
  /** Solo con `variante="caja"`. Por defecto `sm` (32 px, icono 16 px). */
  tamano?: TamanoIconButton
}

export default function IconButton({
  ariaLabel,
  title,
  children,
  className,
  style,
  type = 'button',
  variante = 'simple',
  tono = 'neutro',
  tamano = 'sm',
  ...rest
}: IconButtonProps) {
  if (import.meta.env.DEV && !ariaLabel) {
    throw new Error('IconButton requires an ariaLabel prop for accessibility.')
  }

  const clases = ['icon-button']
  if (variante === 'caja') clases.push('icon-button--caja', `icon-button--${tamano}`, `icon-button--${tono}`)
  if (className) clases.push(className)

  return (
    <button
      type={type}
      aria-label={ariaLabel}
      title={title || ariaLabel}
      className={clases.join(' ')}
      style={style}
      {...rest}
    >
      {children}
    </button>
  )
}
