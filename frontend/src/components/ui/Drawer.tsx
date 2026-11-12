import * as React from 'react'
import { useDialogo } from './useDialogo'

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
  /** Estilos extra del panel; ganan sobre los de la variante. */
  style?: React.CSSProperties
  children?: React.ReactNode
}

const BASE: React.CSSProperties = {
  position: 'fixed',
  background: 'var(--surface-1)',
  display: 'flex', flexDirection: 'column',
  boxShadow: '-8px 0 32px rgba(0,0,0,0.4)',
  outline: 'none',
}

const VARIANTES: Record<'flotante' | 'borde', React.CSSProperties> = {
  flotante: {
    top: 12, right: 12,
    maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 24px)',
    border: '1px solid var(--surface-4)', borderRadius: 12,
    overflow: 'hidden',
  },
  borde: {
    top: 0, right: 0, bottom: 0,
    maxWidth: '95vw',
    borderLeft: '1px solid var(--surface-4)',
  },
}

export function Drawer({
  open = true, onClose, ariaLabel, ariaLabelledby, width = 480,
  variant = 'flotante', zIndex = 'var(--z-drawer)', backdrop = 'rgba(0,0,0,0.35)',
  style, children,
}: DrawerProps) {
  const ref = useDialogo<HTMLDivElement>(open, onClose)
  if (!open) return null
  return (
    <>
      {/* El fondo es un atajo de raton; la via accesible es Esc o el boton de cerrar. */}
      <div
        role="presentation"
        onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, zIndex, background: backdrop }}
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledby}
        tabIndex={-1}
        style={{ ...BASE, ...VARIANTES[variant], width, zIndex, ...style }}
      >
        {children}
      </div>
    </>
  )
}
