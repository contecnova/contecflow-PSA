import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import './BotonConContador.css'

/**
 * BotonConContador y Contador (24-11-2026, pedido del usuario con captura).
 *
 * Antes cada contador de la barra superior era distinto: la bandeja (sobre) se ponía del color de aviso
 * con el número AL LADO del icono, y la campana y el chat llevaban una pelotita roja con el número
 * ENCIMA sin cambiar de color. El estándar es el de la bandeja, en todas partes:
 *
 * - `BotonConContador`: botón de solo icono de una barra (campana, bandeja, chat…) con contador de
 *   pendientes. Sin pendientes, neutro; con pendientes, el botón entero toma el color del tono
 *   (fondo, borde e icono, con tokens) y el número va AL LADO del icono («99+» desde 100). Mismo
 *   tamaño en todas las barras (`--alto-control-sm`). El nombre accesible lo da quien llama y DEBE
 *   llevar el número («Notificaciones: 3 sin leer»); el número visible es `aria-hidden`.
 * - `Contador`: el mismo número como pastilla (menús laterales, junto al nombre de la entrada) o,
 *   con `punto`, la marca sin número del menú plegado.
 *
 *   <BotonConContador icono={<Inbox />} contador={n} tono="aviso" to="/inbox" ariaLabel={t('…', { n })} />
 *   <Contador n={pendientes} tono="peligro" />
 *
 * Tonos: `peligro` (alertas), `aviso` (pendientes de hacer: bandeja, aprobaciones, avisos sin leer),
 * `acento` (mensajes sin leer del chat).
 */
export type TonoDeContador = 'aviso' | 'peligro' | 'acento'

/** «99+» a partir de 100. */
export function textoDeContador(n: number): string {
  return n > 99 ? '99+' : String(n)
}

export interface BotonConContadorProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label' | 'className'> {
  /** Icono lucide (el kit le da el tamaño). */
  icono: ReactNode
  /** Pendientes; con 0 el botón queda neutro y sin número. */
  contador: number
  /** Nombre accesible CON el número (traducido por quien llama). */
  ariaLabel: string
  tono?: TonoDeContador
  /** Panel abierto o pantalla activa: borde y color de acento. */
  activo?: boolean
  /** Ruta: el botón es un enlace de navegación (`NavLink`). */
  to?: string
  /** Texto visible opcional junto al icono (p. ej. el chat minimizado). */
  texto?: ReactNode
  /** Clases para colocarlo (nunca para cambiar su tamaño ni sus colores). */
  className?: string
}

export function BotonConContador({
  icono, contador, ariaLabel, tono = 'aviso', activo = false, to, texto, className, title, type = 'button', ...resto
}: BotonConContadorProps) {
  const n = Math.max(0, Math.floor(Number(contador) || 0))
  const clases = [
    'ui-boton-contador',
    n > 0 ? `ui-boton-contador--${tono}` : '',
    activo ? 'ui-boton-contador--activo' : '',
    className ?? '',
  ].filter(Boolean).join(' ')
  const contenido = (
    <>
      {icono}
      {texto != null && <span className="ui-boton-contador__texto">{texto}</span>}
      {n > 0 && <span className="ui-boton-contador__numero" aria-hidden="true">{textoDeContador(n)}</span>}
    </>
  )
  if (to) {
    return (
      <NavLink to={to} className={({ isActive }) => (isActive && !activo ? `${clases} ui-boton-contador--activo` : clases)}
        aria-label={ariaLabel} title={title ?? ariaLabel}>
        {contenido}
      </NavLink>
    )
  }
  return (
    <button {...resto} type={type} className={clases} aria-label={ariaLabel} title={title ?? ariaLabel}>
      {contenido}
    </button>
  )
}

export interface ContadorProps {
  n: number
  tono?: TonoDeContador
  /** Solo la marca, sin número (menú plegado). */
  punto?: boolean
  /** Clases para colocarlo. */
  className?: string
  /** Nombre accesible si el número no lo dice ya el texto de al lado. */
  ariaLabel?: string
}

export function Contador({ n, tono = 'aviso', punto = false, className, ariaLabel }: ContadorProps) {
  const valor = Math.max(0, Math.floor(Number(n) || 0))
  if (valor === 0) return null
  const clases = `ui-contador ui-contador--${tono}${punto ? ' ui-contador--punto' : ''}${className ? ` ${className}` : ''}`
  if (punto) return <span className={clases} aria-hidden={ariaLabel ? undefined : true} aria-label={ariaLabel} role={ariaLabel ? 'img' : undefined} />
  return <span className={clases} aria-label={ariaLabel}>{textoDeContador(valor)}</span>
}

export default BotonConContador
