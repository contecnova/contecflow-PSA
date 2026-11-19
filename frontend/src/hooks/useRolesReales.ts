/**
 * Roles base reales para los selectores (19-11-2026, matriz de permisos).
 *
 * La lista sale del backend (`GET /auth/roles`, `app/core/capacidades.py`):
 * solo los que existen en `users.role`. Sustituye a las listas escritas a mano
 * en las páginas (aprobaciones, flujos, documentos, equipos, SSO…), algunas
 * con roles inexistentes (designer, finance, developer).
 *
 * La etiqueta: la traducción `rol_usuario.<id>` del idioma actual y, si falta,
 * la que manda el backend para ese idioma.
 */
import { useQuery } from '@tanstack/react-query'
import { authApi } from '../services/api'
import type { RolReal } from '../services/api/auth'
import { useAppT } from './useAppT'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'

export type OpcionDeRol = { id: string; etiqueta: string; interno: boolean }

export function useRolesReales(opciones: { soloInternos?: boolean } = {}): OpcionDeRol[] {
  const { t, lang } = useAppT()
  const { data } = useQuery<RolReal[]>({
    queryKey: ['roles-reales'],
    queryFn: () => authApi.roles().then(r => r.data.items),
    staleTime: Infinity,
  })
  const idioma = (lang === 'en' || lang === 'zh' ? lang : 'es') as keyof RolReal['etiquetas']
  return (data ?? [])
    .filter(r => !opciones.soloInternos || r.interno)
    .map(r => ({ id: r.id, interno: r.interno, etiqueta: etiquetaCodigo(t as never, 'rol_usuario', r.id, r.etiquetas[idioma]) }))
}
