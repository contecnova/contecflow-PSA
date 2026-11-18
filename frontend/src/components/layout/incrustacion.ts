/**
 * Página incrustada en Configuración (18-11-2026).
 *
 * La reorganización de Configuración monta pantallas de módulo enteras
 * (Tarifas, Flujos de estado, Políticas, AI Hub…) dentro de `/settings/:seccion`,
 * a la derecha de la navegación de ajustes. Con este contexto a `true`,
 * `PageShell` no añade el relleno ni el ancho máximo de página (ya los pone la
 * pantalla de Configuración) y `PageHeader` pinta su título como cabecera de
 * sección (`<h2>`, tamaño de sección) en lugar de título de página (`<h1>`), así
 * todas las secciones tienen el mismo aspecto sin tocar cada pantalla.
 */
import { createContext, useContext } from 'react'

export const IncrustadaEnAjustes = createContext(false)

/** `true` si la página se está pintando dentro de Configuración. */
export function useIncrustadaEnAjustes(): boolean {
  return useContext(IncrustadaEnAjustes)
}
