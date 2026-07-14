import api from './api'

export const settingsApi = {
  // General
  getGeneral: () => api.get('/settings/general'),
  updateSetting: (key: any, value: any) => api.patch(`/settings/general/${key}`, { value }),

  // Project types
  getProjectTypes: () => api.get('/settings/project-types'),
  createProjectType: (data: Record<string, unknown>) => api.post('/settings/project-types', data),
  updateProjectType: (id: any, data: Record<string, unknown>) => api.patch(`/settings/project-types/${id}`, data),
  deleteProjectType: (id: any) => api.delete(`/settings/project-types/${id}`),

  // Project statuses
  getProjectStatuses: () => api.get('/settings/project-statuses'),
  createProjectStatus: (data: Record<string, unknown>) => api.post('/settings/project-statuses', data),
  updateProjectStatus: (id: any, data: Record<string, unknown>) => api.patch(`/settings/project-statuses/${id}`, data),
  deleteProjectStatus: (id: any) => api.delete(`/settings/project-statuses/${id}`),

  // Task statuses
  getTaskStatuses: () => api.get('/settings/task-statuses'),
  createTaskStatus: (data: Record<string, unknown>) => api.post('/settings/task-statuses', data),
  updateTaskStatus: (id: any, data: Record<string, unknown>) => api.patch(`/settings/task-statuses/${id}`, data),
  deleteTaskStatus: (id: any) => api.delete(`/settings/task-statuses/${id}`),

  // Departments
  getDepartments: () => api.get('/settings/departments'),
  createDepartment: (data: Record<string, unknown>) => api.post('/settings/departments', data),
  updateDepartment: (id: any, data: Record<string, unknown>) => api.patch(`/settings/departments/${id}`, data),
  deleteDepartment: (id: any) => api.delete(`/settings/departments/${id}`),

  // Holidays
  getHolidays: () => api.get('/settings/holidays'),
  createHoliday: (data: Record<string, unknown>) => api.post('/settings/holidays', data),
  updateHoliday: (id: any, data: Record<string, unknown>) => api.patch(`/settings/holidays/${id}`, data),
  deleteHoliday: (id: any) => api.delete(`/settings/holidays/${id}`),

  // Runtime-flag groups (SLA / health / semantic / password_policy / locale)
  getRuntimeGroup: (group: any) => api.get(`/settings/runtime/${group}`),
  updateRuntimeSetting: (group: any, key: any, value: any) =>
    api.put(`/settings/runtime/${group}/${key}`, { value: String(value) }),
}

// Advanced config API
export const advancedConfigApi = {
  // Roles
  getRoles: () => api.get('/advanced-config/roles'),
  getModules: () => api.get('/advanced-config/modules'),
  createRole: (data: Record<string, unknown>) => api.post('/advanced-config/roles', data),
  updateRole: (id: any, data: Record<string, unknown>) => api.patch(`/advanced-config/roles/${id}`, data),
  deleteRole: (id: any) => api.delete(`/advanced-config/roles/${id}`),

  // Task types
  getTaskTypes: () => api.get('/advanced-config/task-types'),
  createTaskType: (data: Record<string, unknown>) => api.post('/advanced-config/task-types', data),
  updateTaskType: (id: any, data: Record<string, unknown>) => api.patch(`/advanced-config/task-types/${id}`, data),
  deleteTaskType: (id: any) => api.delete(`/advanced-config/task-types/${id}`),

  // Alert configs
  getAlertConfigs: () => api.get('/advanced-config/alert-configs'),
  updateAlertConfig: (alertType: any, data: Record<string, unknown>) => api.patch(`/advanced-config/alert-configs/${alertType}`, data),

  // Rate tables
  getRateTables: () => api.get('/advanced-config/rate-tables'),
  createRateTable: (data: Record<string, unknown>) => api.post('/advanced-config/rate-tables', data),
  deleteRateTable: (id: any) => api.delete(`/advanced-config/rate-tables/${id}`),
  addRateEntry: (tableId: any, data: Record<string, unknown>) => api.post(`/advanced-config/rate-tables/${tableId}/entries`, data),
  updateRateEntry: (tableId: any, entryId: any, data: Record<string, unknown>) => api.patch(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`, data),
  deleteRateEntry: (tableId: any, entryId: any) => api.delete(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`),

  // Vacation policies
  getVacationPolicies: () => api.get('/advanced-config/vacation-policies'),
  createVacationPolicy: (data: Record<string, unknown>) => api.post('/advanced-config/vacation-policies', data),
  updateVacationPolicy: (id: any, data: Record<string, unknown>) => api.patch(`/advanced-config/vacation-policies/${id}`, data),
  deleteVacationPolicy: (id: any) => api.delete(`/advanced-config/vacation-policies/${id}`),
  getVacationBalances: (year: any) => api.get(`/advanced-config/vacation-balances?year=${year}`),
  updateVacationBalance: (userId: any, year: any, days: any) => api.patch(`/advanced-config/vacation-balances/${userId}?year=${year}&days_entitled=${days}`),

  // Offices
  getOffices: () => api.get('/advanced-config/offices'),
  createOffice: (data: Record<string, unknown>) => api.post('/advanced-config/offices', data),
  updateOffice: (id: any, data: Record<string, unknown>) => api.patch(`/advanced-config/offices/${id}`, data),
  deleteOffice: (id: any) => api.delete(`/advanced-config/offices/${id}`),

  // Numbering
  getNumbering: () => api.get('/advanced-config/numbering'),
  updateNumbering: (entity: any, data: Record<string, unknown>) => api.patch(`/advanced-config/numbering/${entity}`, data),
  resetNumbering: (entity: any) => api.post(`/advanced-config/numbering/${entity}/reset`),

  // Custom fields
  getCustomFields: (entity?: any) => api.get(`/advanced-config/custom-fields${entity ? `?entity=${entity}` : ''}`),
  createCustomField: (data: Record<string, unknown>) => api.post('/advanced-config/custom-fields', data),
  updateCustomField: (id: any, data: Record<string, unknown>) => api.patch(`/advanced-config/custom-fields/${id}`, data),
  deleteCustomField: (id: any) => api.delete(`/advanced-config/custom-fields/${id}`),

  // Templates
  getTemplates: () => api.get('/advanced-config/templates'),
  createTemplate: (data: Record<string, unknown>) => api.post('/advanced-config/templates', data),
  deleteTemplate: (id: any) => api.delete(`/advanced-config/templates/${id}`),
  applyTemplate: (templateId: any, projectId: any, startDate?: any) => api.post(`/advanced-config/templates/${templateId}/apply/${projectId}${startDate ? `?start_date=${startDate}` : ''}`),
}
