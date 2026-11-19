/**
 * Matriz de permisos (19-11-2026): el único modo de preguntar por un permiso
 * en la pantalla. Rutas, menú, pestañas y botones usan esto; nada de
 * `hasRole(...)` ni `user.role === 'admin'`.
 *
 *   const puedeEditar = usePermiso('proyectos.gestionar')
 *   const { puede } = usePuede(); puede('sd.administrar')
 *
 * Las capacidades llegan del backend en `/auth/me` (`user.capacidades`):
 * superadmin y roles personalizados ya vienen resueltos allí.
 */
import { useAuth } from '../context/AuthContext'
import type { Capacidad } from './capacidades'

export type { Capacidad } from './capacidades'

/** `true` si el usuario actual tiene la capacidad. */
export function usePermiso(capacidad: Capacidad): boolean {
  return useAuth().puede(capacidad)
}

/** La función `puede` del usuario actual, para varias preguntas a la vez. */
export function usePuede(): { puede: (capacidad: Capacidad) => boolean } {
  const { puede } = useAuth()
  return { puede }
}
