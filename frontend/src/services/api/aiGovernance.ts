/**
 * services/api/aiGovernance.ts — /ai-governance (políticas y registro de uso de IA).
 *
 * Auditoría 2026-11: AIHubPage lo pedía con `fetch` directo, sin el refresco de
 * sesión ni el desenvoltorio de respuestas del cliente.
 */
import api from './_core'
import type { ParamsPeriodoApi } from '../../utils/periodo'

// Periodo libre (16-11-2026): registro y estadísticas aceptan el periodo del
// selector (`desde`/`hasta`/`days`/`tz`). El registro pagina con `page_size`.
export const aiGovernanceApi = {
  policies:      () => api.get('/ai-governance/policies'),
  auditLog:      (params?: Partial<ParamsPeriodoApi> & { page?: number; page_size?: number }) => api.get('/ai-governance/audit-log', { params }),
  auditLogStats: (params?: Partial<ParamsPeriodoApi>) => api.get('/ai-governance/audit-log/stats', { params }),
}
