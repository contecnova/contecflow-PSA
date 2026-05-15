/**
 * BI / analytics — OLAP, narrative, ML, governance, alerts, bookmarks,
 * report builders, forecasting, anomaly/churn, GDPR, dashboard collab,
 * query builder, conditional delivery, ETL, Office 365, observability.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const analyticsApi = {
  query:          (metricId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/analytics/query/${metricId}`, { params }),
  filterOptions:  (): Promise<Response<unknown>> => api.get('/analytics/filters/options'),
  hoursWeek:      (params?: Params): Promise<Response<unknown>> => api.get('/analytics/hours_by_week', { params }),
  utilization:    (params?: Params): Promise<Response<unknown>> => api.get('/analytics/utilization/advanced', { params }),
  metricBreaches: (params?: Params): Promise<Response<unknown>> =>
    api.get('/analytics/alerts/metric-breaches', { params }),
  narrative:        (params?: Params): Promise<Response<unknown>> => api.get('/analytics/narrative', { params }),
  ask:              (question: string): Promise<Response<unknown>> => api.post('/analytics/ask', { question }),
  olapKpis:         (params?: Params): Promise<Response<unknown>> => api.get('/analytics/olap/kpis', { params }),
  olapFunnel:       (): Promise<Response<unknown>> => api.get('/analytics/olap/pipeline-funnel'),
  olapPortfolio:    (): Promise<Response<unknown>> => api.get('/analytics/olap/portfolio-health'),
  olapMargin:       (months?: number): Promise<Response<unknown>> =>
    api.get('/analytics/olap/margin-evolution', { params: { months } }),
  olapUtilization:  (): Promise<Response<unknown>> => api.get('/analytics/olap/utilization'),
  catalogue:        (): Promise<Response<unknown>> => api.get('/analytics/catalogue'),
}

export const biCollaborationApi = {
  listComments:            (params?: Params): Promise<Response<unknown>> => api.get('/bi/collaboration/comments', { params }),
  createComment:           (payload: JsonBody): Promise<Response<unknown>> => api.post('/bi/collaboration/comments', payload),
  resolveComment:          (commentId: Id): Promise<Response<unknown>> =>
    api.patch(`/bi/collaboration/comments/${commentId}/resolve`),
  listSharedViews:         (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/collaboration/shared-views', { params }),
  createSharedView:        (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/collaboration/shared-views', payload),
  patchSharedView:         (viewId: Id, payload: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/collaboration/shared-views/${viewId}`, payload),
  governanceOverview:      (): Promise<Response<unknown>> => api.get('/bi/governance/overview'),
  governanceRules:         (): Promise<Response<unknown>> => api.get('/bi/governance/rules'),
  updateGovernanceRules:   (payload: JsonBody): Promise<Response<unknown>> => api.patch('/bi/governance/rules', payload),
  runGovernanceChecks:     (): Promise<Response<unknown>> => api.post('/bi/governance/run-checks'),
  lastGovernanceRun:       (): Promise<Response<unknown>> => api.get('/bi/governance/last-run'),
  listDashboardShares:     (key: string): Promise<Response<unknown>> =>
    api.get(`/bi/collaboration/dashboards/${key}/shares`),
  shareDashboard:          (key: string, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/bi/collaboration/dashboards/${key}/shares`, data),
  revokeShare:             (key: string, shareId: Id): Promise<Response<unknown>> =>
    api.delete(`/bi/collaboration/dashboards/${key}/shares/${shareId}`),
  listDashboardVersions:   (key: string): Promise<Response<unknown>> =>
    api.get(`/bi/collaboration/dashboards/${key}/versions`),
  restoreDashboardVersion: (key: string, versionId: Id): Promise<Response<unknown>> =>
    api.post(`/bi/collaboration/dashboards/${key}/versions/${versionId}/restore`),
  listNotifications:       (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/collaboration/notifications', { params }),
  patchNotification:       (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/collaboration/notifications/${id}`, data),
}

export const biIntelligenceApi = {
  revenueForecast:           (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/intelligence/ml/forecast/revenue', { params }),
  revenueAnomalies:          (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/intelligence/ml/anomalies/revenue', { params }),
  listConnectors:            (): Promise<Response<unknown>> => api.get('/bi/intelligence/connectors'),
  patchConnector:            (name: string, payload: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/intelligence/connectors/${name}`, payload),
  syncConnector:             (name: string): Promise<Response<unknown>> =>
    api.post(`/bi/intelligence/connectors/${name}/sync`),
  reportPresets:             (): Promise<Response<unknown>> => api.get('/bi/intelligence/reports/presets'),
  previewPreset:             (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/intelligence/reports/preview', payload),
  queryBuilderSchema:        (): Promise<Response<unknown>> => api.get('/bi/intelligence/query-builder/schema'),
  queryBuilderPreview:       (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/intelligence/query-builder/preview', payload),
  queryBuilderTemplates:     (): Promise<Response<unknown>> => api.get('/bi/intelligence/query-builder/templates'),
  saveQueryBuilderTemplate:  (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/intelligence/query-builder/templates', payload),
  deleteQueryBuilderTemplate:(id: Id): Promise<Response<unknown>> =>
    api.delete(`/bi/intelligence/query-builder/templates/${id}`),
  deliveryOverview:          (): Promise<Response<unknown>> => api.get('/bi/intelligence/delivery/overview'),
  runDeliveryNow:            (reportId: Id): Promise<Response<unknown>> =>
    api.post(`/bi/intelligence/delivery/run/${reportId}`),
  realtimeToken:             (): Promise<Response<unknown>> => api.get('/bi/intelligence/realtime/token'),
}

export const biPlatformApi = {
  sdkManifest:           (): Promise<Response<unknown>> => api.get('/bi/platform/embed/sdk'),
  embedSettings:         (): Promise<Response<unknown>> => api.get('/bi/platform/embed/settings'),
  patchEmbedSettings:    (payload: JsonBody): Promise<Response<unknown>> =>
    api.patch('/bi/platform/embed/settings', payload),
  embedToken:            (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/platform/embed/token', payload),
  connectorCatalog:      (): Promise<Response<unknown>> => api.get('/bi/platform/connectors/catalog'),
  patchCatalogConnector: (name: string, p: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/platform/connectors/catalog/${name}`, p),
  listCustomConnectors:  (): Promise<Response<unknown>> => api.get('/bi/platform/connectors/custom'),
  createCustomConnector: (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/platform/connectors/custom', payload),
  deleteCustomConnector: (id: Id): Promise<Response<unknown>> => api.delete(`/bi/platform/connectors/custom/${id}`),
  testCustomConnector:   (id: Id): Promise<Response<unknown>> => api.post(`/bi/platform/connectors/custom/${id}/test`),
  lineage:               (): Promise<Response<unknown>> => api.get('/bi/platform/governance/lineage'),
  upsertLineageEdge:     (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/platform/governance/lineage/edges', payload),
  logAccess:             (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/platform/governance/audit/access', payload),
  createSnapshot:        (datasetKey: string, p: JsonBody): Promise<Response<unknown>> =>
    api.post(`/bi/platform/versioning/${datasetKey}/snapshots`, p),
  listSnapshots:         (datasetKey: string): Promise<Response<unknown>> =>
    api.get(`/bi/platform/versioning/${datasetKey}/snapshots`),
  diffSnapshots:         (datasetKey: string, fromId: Id, toId: Id): Promise<Response<unknown>> =>
    api.get(`/bi/platform/versioning/${datasetKey}/diff`, { params: { from_id: fromId, to_id: toId } }),
}

export const biSmartAlertsApi = {
  supportedMetrics:   (): Promise<Response<unknown>> => api.get('/bi/alerts/supported-metrics'),
  listRules:          (): Promise<Response<unknown>> => api.get('/bi/alerts/rules'),
  createRule:         (payload: JsonBody): Promise<Response<unknown>> => api.post('/bi/alerts/rules', payload),
  updateRule:         (ruleId: Id, payload: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/alerts/rules/${ruleId}`, payload),
  deleteRule:         (ruleId: Id): Promise<Response<unknown>> => api.delete(`/bi/alerts/rules/${ruleId}`),
  evaluate:           (): Promise<Response<unknown>> => api.post('/bi/alerts/evaluate'),
  getHistory:         (limit = 100): Promise<Response<unknown>> => api.get('/bi/alerts/history', { params: { limit } }),
  acknowledge:        (alertId: Id): Promise<Response<unknown>> =>
    api.post(`/bi/alerts/history/${alertId}/acknowledge`),
  seedDefaults:       (): Promise<Response<unknown>> => api.post('/bi/alerts/seed-defaults'),
  listCustomMetrics:  (): Promise<Response<unknown>> => api.get('/bi/alerts/custom-metrics'),
  createCustomMetric: (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/alerts/custom-metrics', payload),
  deleteCustomMetric: (key: string): Promise<Response<unknown>> => api.delete(`/bi/alerts/custom-metrics/${key}`),
}

export const biBookmarksApi = {
  list:   (): Promise<Response<unknown>> => api.get('/bi/bookmarks'),
  create: (payload: JsonBody): Promise<Response<unknown>> => api.post('/bi/bookmarks', payload),
  get:    (id: Id): Promise<Response<unknown>> => api.get(`/bi/bookmarks/${id}`),
  update: (id: Id, payload: JsonBody): Promise<Response<unknown>> => api.patch(`/bi/bookmarks/${id}`, payload),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/bi/bookmarks/${id}`),
}

export const biGovernanceAuditApi = {
  logAccessEvent:         (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/governance/audit/access', payload),
  getAccessHistory:       (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/governance/audit/access', { params }),
  listLineage:            (target_table?: string): Promise<Response<unknown>> =>
    api.get('/bi/governance/lineage', { params: target_table ? { target_table } : undefined }),
  trackLineage:           (payload: JsonBody): Promise<Response<unknown>> =>
    api.post('/bi/governance/lineage', payload),
  listFieldSensitivity:   (dataset_id?: string): Promise<Response<unknown>> =>
    api.get('/bi/governance/field-sensitivity', { params: dataset_id ? { dataset_id } : undefined }),
  upsertFieldSensitivity: (payload: JsonBody): Promise<Response<unknown>> =>
    api.put('/bi/governance/field-sensitivity', payload),
}

export const biReportBuilderV2Api = {
  listPresets:    (params?: Params): Promise<Response<unknown>> => api.get('/bi/reports/v2/presets', { params }),
  getPreset:      (presetId: Id): Promise<Response<unknown>> => api.get(`/bi/reports/v2/presets/${presetId}`),
  categories:     (): Promise<Response<unknown>> => api.get('/bi/reports/v2/categories'),
  customize:      (presetId: Id, payload: JsonBody): Promise<Response<unknown>> =>
    api.post(`/bi/reports/v2/presets/${presetId}/customize`, payload),
  resetCustomize: (presetId: Id): Promise<Response<unknown>> =>
    api.delete(`/bi/reports/v2/presets/${presetId}/customize`),
  preview:        (presetId: Id, limit = 50): Promise<Response<unknown>> =>
    api.get(`/bi/reports/v2/presets/${presetId}/preview`, { params: { limit } }),
  export:         (presetId: Id, format = 'json'): Promise<Response<unknown>> =>
    api.get(`/bi/reports/v2/presets/${presetId}/export`, { params: { format } }),
}

export const biForecastingApi = {
  getMetrics:    (): Promise<Response<unknown>> => api.get('/bi/forecasting/metrics'),
  forecast:      (metric: string, params?: Params): Promise<Response<unknown>> =>
    api.get(`/bi/forecasting/${metric}`, { params }),
  multiForecast: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/forecasting/multi', data),
  listMetrics:   (): Promise<Response<unknown>> => api.get('/bi/forecast/metrics'),
  run:           (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/forecast', data),
}

export const biAnomalyApi = {
  getInfo:      (): Promise<Response<unknown>> => api.get('/bi/anomaly/info'),
  detect:       (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/anomaly/detect', data),
  predictChurn: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/anomaly/churn', data),
  churnPredict: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/churn/predict', data),
}

export const biGdprApi = {
  recordConsent:         (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/gdpr/consent', data),
  getConsent:            (params?: Params): Promise<Response<unknown>> => api.get('/bi/gdpr/consent', { params }),
  listConsents:          (): Promise<Response<unknown>> => api.get('/bi/gdpr/consents'),
  getConsentHistory:     (userId: Id): Promise<Response<unknown>> => api.get(`/bi/gdpr/consent/${userId}/history`),
  createDsr:             (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/gdpr/dsr', data),
  getDsr:                (id: Id): Promise<Response<unknown>> => api.get(`/bi/gdpr/dsr/${id}`),
  listDsr:               (params?: Params): Promise<Response<unknown>> => api.get('/bi/gdpr/dsr', { params }),
  resolveDsr:            (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/bi/gdpr/dsr/${id}/resolve`, data),
  executeDsrErasure:     (id: Id): Promise<Response<unknown>> => api.post(`/bi/gdpr/dsr/${id}/erasure-execute`),
  executeDsrPortability: (id: Id): Promise<Response<unknown>> => api.post(`/bi/gdpr/dsr/${id}/portability-export`),
  setFieldMask:          (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/gdpr/field-masks', data),
  getFieldMasks:         (): Promise<Response<unknown>> => api.get('/bi/gdpr/field-masks'),
  getStats:              (): Promise<Response<unknown>> => api.get('/bi/gdpr/stats'),
}

export const biDashboardCollabApi = {
  addComment:     (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/collab/comments', data),
  listComments:   (params?: Params): Promise<Response<unknown>> => api.get('/bi/collab/comments', { params }),
  resolveComment: (id: Id): Promise<Response<unknown>> => api.patch(`/bi/collab/comments/${id}/resolve`),
  saveView:       (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/collab/views', data),
  listViews:      (params?: Params): Promise<Response<unknown>> => api.get('/bi/collab/views', { params }),
  addReaction:    (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/collab/reactions', data),
}

export const biQueryBuilderApi = {
  getSchema:    (params?: Params): Promise<Response<unknown>> => api.get('/bi/query-builder/schema', { params }),
  previewQuery: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/query-builder/preview', data),
  saveQuery:    (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/query-builder/queries', data),
  listQueries:  (): Promise<Response<unknown>> => api.get('/bi/query-builder/queries'),
  executeQuery: (id: Id): Promise<Response<unknown>> => api.post(`/bi/query-builder/queries/${id}/execute`),
  deleteQuery:  (id: Id): Promise<Response<unknown>> => api.delete(`/bi/query-builder/queries/${id}`),
}

export const biConditionalDeliveryApi = {
  createRule: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/delivery/rules', data),
  listRules:  (): Promise<Response<unknown>> => api.get('/bi/delivery/rules'),
  updateRule: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/bi/delivery/rules/${id}`, data),
  deleteRule: (id: Id): Promise<Response<unknown>> => api.delete(`/bi/delivery/rules/${id}`),
  evaluate:   (id: Id, data: JsonBody = {}): Promise<Response<unknown>> =>
    api.post(`/bi/delivery/rules/${id}/evaluate`, data),
}

export const biEtlApi = {
  listConnectors: (): Promise<Response<unknown>> => api.get('/bi/etl/connectors'),
  getConnector:   (id: Id): Promise<Response<unknown>> => api.get(`/bi/etl/connectors/${id}`),
  triggerSync:    (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/bi/etl/connectors/${id}/sync`, data),
  getLog:         (id: Id): Promise<Response<unknown>> => api.get(`/bi/etl/connectors/${id}/log`),
  getData:        (id: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/bi/etl/data/${id}`, { params }),
}

export const biO365Api = {
  getConfig:   (): Promise<Response<unknown>> => api.get('/bi/o365/config'),
  saveConfig:  (data: JsonBody): Promise<Response<unknown>> => api.put('/bi/o365/config', data),
  triggerSync: (data: JsonBody): Promise<Response<unknown>> => api.post('/bi/o365/sync', data),
  getReport:   (name: string, params?: Params): Promise<Response<unknown>> =>
    api.get(`/bi/o365/reports/${name}`, { params }),
  getAdoption: (): Promise<Response<unknown>> => api.get('/bi/o365/adoption'),
  getSyncLog:  (): Promise<Response<unknown>> => api.get('/bi/o365/sync-log'),
}

export const predictiveObservabilityApi = {
  status:         (orgId?: Id): Promise<Response<unknown>> =>
    api.get('/bi/predictive/observability/status', { params: orgId ? { organization_id: orgId } : {} }),
  health:         (params?: Params): Promise<Response<unknown>> =>
    api.get('/bi/predictive/observability/health', { params }),
  triggerRetrain: (): Promise<Response<unknown>> => api.post('/bi/predictive/observability/trigger-retrain'),
}

export const predictionsApi = {
  overrunRisk:   (projectId: Id): Promise<Response<unknown>> =>
    api.post('/predictions/overrun-risk', { project_id: projectId }),
  portfolioRisk: (): Promise<Response<unknown>> => api.get('/predictions/portfolio-risk'),
  train:         (): Promise<Response<unknown>> => api.post('/predictions/train'),
  models:        (): Promise<Response<unknown>> => api.get('/predictions/models'),
  logs:          (params?: Params): Promise<Response<unknown>> => api.get('/predictions/logs', { params }),
}
