/**
 * Página incrustada (18-11-2026; patrón único desde el 24-11-2026, paso 1 de estabilidad de diseño).
 *
 * Una pantalla de módulo entera (`PageShell` + `PageHeader`) se puede montar dentro de otra:
 *   - en Configuración (`/settings/:seccion`, a la derecha de la navegación de ajustes): Tarifas,
 *     Tipos de incidencia, Políticas, AI Hub…;
 *   - en una pestaña de otra pantalla: Tiempo (Registrar, Cronómetro, Semana), la ficha del
 *     proyecto (Gantt, Sprints, Hitos, RACI, UAT), Campos personalizados por proyecto.
 *
 * El contenedor la envuelve en `<PaginaIncrustada.Provider value={…}>` y la pantalla NO cambia:
 *   - `PageShell` no añade el relleno ni el ancho máximo de página (ya los pone el contenedor);
 *   - `PageHeader` no repite la cabecera de página: si el contenedor le da `titulo` (Configuración:
 *     el título y la descripción de la sección del catálogo) lo pinta como cabecera de sección
 *     (`<h2>`, tamaño de sección, icono sin caja); si no se lo da (pestaña, o sección que ya pinta
 *     su tarjeta con título), solo deja la barra de acciones a la derecha. Nunca pinta migas ni se
 *     fija arriba. El botón «Exportar Excel» es el de la pantalla incrustada (sabe qué lista
 *     exportar y cuándo hay algo); por eso el contenedor NO pone el suyo (`showListExport={false}`).
 * Regla y capturas: docs/GUIA_DE_DISENO.md §7.1.
 */
import { createContext, useContext, type ReactNode } from 'react'

export interface DatosDeIncrustacion {
  /** Título de la sección que da el contenedor (Configuración). Sin él: solo barra de acciones. */
  titulo?: ReactNode
  /** Descripción de una línea bajo el título (la del catálogo de Configuración). */
  descripcion?: ReactNode
}

/** `null` = página normal; un objeto = página incrustada en otra (Configuración o pestaña). */
export const PaginaIncrustada = createContext<DatosDeIncrustacion | null>(null)

/** Nombre anterior (18-11-2026): el contexto nació para Configuración. */
export const IncrustadaEnAjustes = PaginaIncrustada

/** Datos de la incrustación, o `null` si la página se pinta sola. */
export function usePaginaIncrustada(): DatosDeIncrustacion | null {
  return useContext(PaginaIncrustada)
}

/** `true` si la página se está pintando dentro de otra (Configuración o una pestaña). */
export function useIncrustadaEnAjustes(): boolean {
  return useContext(PaginaIncrustada) !== null
}

/** Valor para una pestaña: la pestaña ya nombra la pantalla, así que sin título. */
export const EN_PESTANA: DatosDeIncrustacion = Object.freeze({})
