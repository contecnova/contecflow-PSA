/**
 * Menú lateral de la persona (23-11-2026, «menú personalizable»): su preferencia
 * (`user_preferences.extra.menu`, le sigue en cualquier equipo) o, si no tiene,
 * la de su rol en su empresa (Configuración › «Menú por defecto»).
 * La lógica pura está en `permisos/menuPersonal.ts`.
 */
import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { menuPorDefectoApi } from '../services/api'
import { STALE_5_MIN_MS } from '../constants/timings'
import useUserPreferences from './useUserPreferences'
import { menuEfectivo, normalizarPreferencia, type PreferenciaDeMenu } from '../permisos/menuPersonal'

export interface MenuPersonal {
  /** La que se aplica (personal → rol → null = orden del código). */
  efectivo: PreferenciaDeMenu | null
  /** ¿Tiene la persona un menú propio (distinto del de su rol)? */
  personalizado: boolean
  guardar: (p: PreferenciaDeMenu) => void
  /** Borra el menú propio: vuelve al de su rol. */
  restablecer: () => void
}

export function useMenuPersonal(): MenuPersonal {
  const { user } = useAuth()
  const { prefs, save } = useUserPreferences()
  const { data: delRol = null } = useQuery<PreferenciaDeMenu | null>({
    queryKey: ['menu-default-mine', user?.id],
    queryFn: () => menuPorDefectoApi.mio().then(r => normalizarPreferencia(r.data)).catch(() => null),
    enabled: !!user?.id,
    staleTime: STALE_5_MIN_MS,
    retry: false,
  })
  const crudo = (prefs?.extra as Record<string, unknown> | null | undefined)?.menu
  const personal = useMemo(() => normalizarPreferencia(crudo), [crudo])
  const guardar = useCallback((p: PreferenciaDeMenu) => save({ extra: { menu: p } }), [save])
  const restablecer = useCallback(() => save({ extra: { menu: null } }), [save])
  return { efectivo: menuEfectivo(personal, delRol), personalizado: !!personal, guardar, restablecer }
}

export default useMenuPersonal
