/**
 * useAppName — el nombre que se enseña como marca de la aplicación.
 *
 * Con sesión: `app_name` de la marca de la empresa (`/orgs/{org}/branding`; sin
 * marca propia el backend devuelve su `PROJECT_NAME`). Sin sesión o mientras
 * carga: `PRODUCT_NAME`.
 */
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { settingsApi } from '../services/api'
import { PRODUCT_NAME } from '../constants/brand'
import { STALE_5_MIN_MS } from '../constants/timings'

export function useAppName(): string {
  const { user } = useAuth()
  const org = user?.organization_id ?? null
  const { data } = useQuery({
    queryKey: ['branding', org],
    enabled: !!org,
    queryFn: () => settingsApi.branding(org as string).then(r => r.data as { app_name?: string }),
    staleTime: STALE_5_MIN_MS,
    retry: false,
  })
  return data?.app_name?.trim() || PRODUCT_NAME
}
