/**
 * useInvalidate — Estrategia global de invalidación de cache
 *
 * Mapa de qué queries invalidan qué otras queries relacionadas.
 * Cuando una mutación tiene éxito, llama a invalidate('resource')
 * y este hook invalida automáticamente TODAS las queries que dependan de ese recurso.
 */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

// Mapa de dependencias: cuando se muta X, invalidar también Y, Z...
const INVALIDATION_MAP = {
  tasks: [
    'tasks', 'gantt-tasks', 'project', 'dash-kpis', 'dash-sd-kpi',
    'backlog', 'kanban', 'sprints', 'capacity', 'resource-forecast',
    'profitability', 'bi-kpis',
  ],
  projects: [
    'projects', 'projects-list', 'project', 'dash-kpis', 'clients',
    'profitability', 'bi-kpis', 'bi-prof-summary', 'pipeline',
    'resource-forecast', 'gantt-tasks',
  ],
  timesheets: [
    'imputations', 'dash-kpis', 'profitability', 'bi-kpis',
    'resource-forecast', 'capacity',
  ],
  invoices: [
    'invoices', 'dash-kpis', 'profitability', 'bi-kpis',
    'bi-revenue', 'clients',
  ],
  clients: [
    'clients', 'client-360', 'pipeline', 'invoices',
    'bi-top-clients', 'dash-kpis',
  ],
  users: [
    'users', 'team', 'capacity', 'resource-forecast',
    'dash-kpis', 'approvals-pending-badge',
  ],
  approvals: [
    'approvals', 'approvals-pending-badge', 'approval-stats',
    'dash-kpis',
  ],
  service_desk: [
    'sd-tickets', 'sd-stats', 'sd-queue', 'sd-itil-metrics', 'sd-agent-perf',
    'alerts-count', 'notif-alerts', 'dash-sd-kpi', 'dash-recent-tickets',
  ],
  tickets: [
    'sd-tickets', 'sd-stats', 'sd-queue', 'sd-itil-metrics', 'sd-agent-perf',
    'sd-ticket', 'sd-sla-events', 'sd-ticket-links',
    'alerts-count', 'notif-alerts', 'dash-sd-kpi', 'dash-recent-tickets',
  ],
  sd_ticket: [
    'sd-ticket', 'sd-tickets', 'sd-queue', 'sd-itil-metrics',
    'sd-sla-events', 'sd-ticket-links', 'dash-sd-kpi',
  ],
  sd_changes: [
    'sd-changes', 'sd-change-detail', 'sd-itil-metrics',
    'dash-sd-kpi', 'dash-recent-tickets',
  ],
  sd_problems: [
    'sd-problems', 'sd-kedb', 'sd-itil-metrics',
  ],
  sd_major_incidents: [
    'sd-major-incidents', 'sd-itil-metrics',
  ],
  sd_config: [
    'sd-catalog', 'sd-sla-policies', 'sd-groups', 'sd-templates',
    'sd-routing-rules',
  ],
  milestones: [
    'milestones', 'invoices', 'profitability',
    'bi-kpis', 'dash-kpis',
  ],
  capacity: [
    'capacity', 'capacity-board', 'resource-forecast',
    'forecast-heatmap', 'forecast-summary', 'bi-utilization',
    'dash-kpis', 'users-load',
  ],
  resource_forecast: [
    'forecast-heatmap', 'forecast-summary', 'forecast-user',
    'capacity', 'capacity-board', 'bi-utilization',
  ],
  expenses: [
    'expenses', 'profitability', 'bi-kpis', 'dash-kpis',
  ],
  risks: [
    'risks', 'project', 'dash-kpis',
  ],
  sprints: [
    'sprints', 'backlog', 'kanban', 'tasks', 'dash-kpis',
  ],
}

export function useInvalidate() {
  const qc = useQueryClient()

  const invalidate = useCallback((resource, extraKeys = []) => {
    const keys = [
      ...(INVALIDATION_MAP[resource] || [resource]),
      ...extraKeys,
    ]
    // Deduplicar y invalidar
    const unique = [...new Set(keys)]
    unique.forEach(key => {
      qc.invalidateQueries({ queryKey: [key], exact: false })
    })
  }, [qc])

  // Invalidación genérica de todo (para operaciones masivas)
  const invalidateAll = useCallback(() => {
    qc.invalidateQueries()
  }, [qc])

  return { invalidate, invalidateAll }
}
