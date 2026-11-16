/**
 * services/api/periodo.ts — /periodo (periodo libre en informes, 16-11-2026).
 * Límites que aplica la API a `desde`/`hasta`/`granularidad` (ajustes en caliente
 * del grupo `informes`). Ver `app/core/periodo.py`.
 */
import api from './_core'
import type { LimitesPeriodo } from '../../utils/periodo'

export const periodoApi = {
  limites: (): Promise<LimitesPeriodo & { granularidades: string[] }> =>
    api.get('/periodo/limites').then(r => {
      const d = r.data as { data?: unknown } | LimitesPeriodo
      return ((d && typeof d === 'object' && 'data' in d ? d.data : d) as LimitesPeriodo & { granularidades: string[] })
    }),
}
