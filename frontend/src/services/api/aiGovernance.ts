/**
 * services/api/aiGovernance.ts — /ai-governance (políticas y registro de uso de IA).
 *
 * Auditoría 2026-11: AIHubPage lo pedía con `fetch` directo, sin el refresco de
 * sesión ni el desenvoltorio de respuestas del cliente.
 */
import api from './_core'

export const aiGovernanceApi = {
  policies:      () => api.get('/ai-governance/policies'),
  auditLog:      (params?: { limit?: number }) => api.get('/ai-governance/audit-log', { params }),
  auditLogStats: () => api.get('/ai-governance/audit-log/stats'),
}
