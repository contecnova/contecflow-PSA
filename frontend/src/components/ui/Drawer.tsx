import * as React from 'react'
import { useDialogoEditable } from './useDialogo'
import { SinGuardarContext } from './useCambiosSinGuardar'
import './Drawer.css'
import type { CSSProperties } from 'react'

/**
 * Panel lateral (drawer) accesible y compartido.
 *
 * Auditoria 2026-11: habia cinco paneles laterales hechos a mano (alertas,
 * documento, anomalias de imputacion, proveedor de IA, detalle de tarea), cada
 * uno con su fondo, su z-index y su forma de cerrar; dos no tenian trampa de
 * foco y uno no cerraba con Esc. Este componente pone el fondo, la posicion,
 * `role="dialog"`, la trampa de foco, Esc y la devolucion del foco
 * (`useDialogo`); el contenido (cabecera incluida) lo pone quien lo usa.
 *
 * Variantes:
 *  - `flotante`: separado 12px del borde, con esquinas redondeadas y alto
 *    ajustado al contenido.
 *  - `borde`: pegado al borde derecho, alto completo.
 *
 * Cambios sin guardar (23-11-2026): el fondo, Esc y la X preguntan antes de
 * cerrar si el usuario ha tocado algo. La X la pone quien usa el Drawer: debe
 * llevar `data-cierra-dialogo` para que el kit la reconozca.
 */
interface DrawerProps {
  /** Por defecto abierto: muchos paneles se montan solo cuando se muestran. */
  open?: boolean
  onClose: () => void
  /** Nombre accesible del dialogo. */
  ariaLabel?: string
  ariaLabelledby?: string
  /** Ancho maximo del panel (px o medida CSS). */
  width?: number | string
  variant?: 'flotante' | 'borde'
  /** z-index del fondo y del panel. */
  zIndex?: number | string
  /** Color del fondo que cubre la pagina. */
  backdrop?: string
  /** Clases extra del panel (se suman a `drawer drawer--<variante>`). */
  className?: string
  /** Estilos extra del panel; ganan sobre los de la variante. */
  style?: React.CSSProperties
  children?: React.ReactNode
  /** false en paneles de solo lectura: no preguntan por cambios sin guardar. */
  avisarSinGuardar?: boolean
  /** Controlado por la pantalla: manda sobre la deteccion automatica. */
  cambiosSinGuardar?: boolean
}

export function Drawer({
  open = true, onClose, ariaLabel, ariaLabelledby, width = 480,
  variant = 'flotante', zIndex = 'var(--z-drawer)', backdrop = 'var(--overlay-scrim-soft)',
  className, style, children, avisarSinGuardar = true, cambiosSinGuardar,
}: DrawerProps) {
  const { ref, pedirCierre, sinGuardar } = useDialogoEditable<HTMLDivElement>(open, onClose, { avisarSinGuardar, cambiosSinGuardar })
  if (!open) return null
  return (
    <>
      {/* El fondo es un atajo de raton; la via accesible es Esc o el boton de cerrar. */}
      <div className="uidraw-box-1 drawer-e1"
        role="presentation"
        onMouseDown={e => { e.preventDefault(); pedirCierre() }}
        style={{ '--drawer-z-index': zIndex, '--drawer-background': backdrop } as CSSProperties}
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledby}
        tabIndex={-1}
        className={`drawer drawer--${variant}${className ? ` ${className}` : ''}`}
        style={{ '--drawer-width': typeof width === 'number' ? `${width}px` : width, '--drawer-z-index': zIndex, ...style } as CSSProperties}
      >
        <SinGuardarContext.Provider value={sinGuardar}>{children}</SinGuardarContext.Provider>
      </div>
    </>
  )
}
