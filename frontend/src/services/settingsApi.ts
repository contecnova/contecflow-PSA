import api from './api'

export const settingsApi = {
  // General
  getGeneral: () => api.get('/settings/general'),
  updateSetting: (key, value) => api.patch(`/settings/general/${key}`, { value }),

  // Project types
  getProjectTypes: () => api.get('/settings/project-types'),
  createProjectType: (data) => api.post('/settings/project-types', data),
  updateProjectType: (id, data) => api.patch(`/settings/project-types/${id}`, data),
  deleteProjectType: (id) => api.delete(`/settings/project-types/${id}`),

  // Project statuses
  getProjectStatuses: () => api.get('/settings/project-statuses'),
  createProjectStatus: (data) => api.post('/settings/project-statuses', data),
  updateProjectStatus: (id, data) => api.patch(`/settings/project-statuses/${id}`, data),
  deleteProjectStatus: (id) => api.delete(`/settings/project-statuses/${id}`),

  // Task statuses
  getTaskStatuses: () => api.get('/settings/task-statuses'),
  createTaskStatus: (data) => api.post('/settings/task-statuses', data),
  updateTaskStatus: (id, data) => api.patch(`/settings/task-statuses/${id}`, data),
  deleteTaskStatus: (id) => api.delete(`/settings/task-statuses/${id}`),

  // Departments
  getDepartments: () => api.get('/settings/departments'),
  createDepartment: (data) => api.post('/settings/departments', data),
  updateDepartment: (id, data) => api.patch(`/settings/departments/${id}`, data),
  deleteDepartment: (id) => api.delete(`/settings/departments/${id}`),

  // Holidays
  getHolidays: () => api.get('/settings/holidays'),
  createHoliday: (data) => api.post('/settings/holidays', data),
  updateHoliday: (id, data) => api.patch(`/settings/holidays/${id}`, data),
  deleteHoliday: (id) => api.delete(`/settings/holidays/${id}`),

  // Runtime-flag groups (SLA / health / semantic / password_policy / locale)
  getRuntimeGroup: (group) => api.get(`/settings/runtime/${group}`),
  updateRuntimeSetting: (group, key, value) =>
    api.put(`/settings/runtime/${group}/${key}`, { value: String(value) }),
}

// Advanced config API
export const advancedConfigApi = {
  // Roles
  getRoles: () => api.get('/advanced-config/roles'),
  getModules: () => api.get('/advanced-config/modules'),
  createRole: (data) => api.post('/advanced-config/roles', data),
  updateRole: (id, data) => api.patch(`/advanced-config/roles/${id}`, data),
  deleteRole: (id) => api.delete(`/advanced-config/roles/${id}`),

  // Task types
  getTaskTypes: () => api.get('/advanced-config/task-types'),
  createTaskType: (data) => api.post('/advanced-config/task-types', data),
  updateTaskType: (id, data) => api.patch(`/advanced-config/task-types/${id}`, data),
  deleteTaskType: (id) => api.delete(`/advanced-config/task-types/${id}`),

  // Alert configs
  getAlertConfigs: () => api.get('/advanced-config/alert-configs'),
  updateAlertConfig: (alertType, data) => api.patch(`/advanced-config/alert-configs/${alertType}`, data),

  // Rate tables
  getRateTables: () => api.get('/advanced-config/rate-tables'),
  createRateTable: (data) => api.post('/advanced-config/rate-tables', data),
  deleteRateTable: (id) => api.delete(`/advanced-config/rate-tables/${id}`),
  addRateEntry: (tableId, data) => api.post(`/advanced-config/rate-tables/${tableId}/entries`, data),
  updateRateEntry: (tableId, entryId, data) => api.patch(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`, data),
  deleteRateEntry: (tableId, entryId) => api.delete(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`),

  // Vacation policies
  getVacationPolicies: () => api.get('/advanced-config/vacation-policies'),
  createVacationPolicy: (data) => api.post('/advanced-config/vacation-policies', data),
  updateVacationPolicy: (id, data) => api.patch(`/advanced-config/vacation-policies/${id}`, data),
  deleteVacationPolicy: (id) => api.delete(`/advanced-config/vacation-policies/${id}`),
  getVacationBalances: (year) => api.get(`/advanced-config/vacation-balances?year=${year}`),
  updateVacationBalance: (userId, year, days) => api.patch(`/advanced-config/vacation-balances/${userId}?year=${year}&days_entitled=${days}`),

  // Offices
  getOffices: () => api.get('/advanced-config/offices'),
  createOffice: (data) => api.post('/advanced-config/offices', data),
  updateOffice: (id, data) => api.patch(`/advanced-config/offices/${id}`, data),
  deleteOffice: (id) => api.delete(`/advanced-config/offices/${id}`),

  // Numbering
  getNumbering: () => api.get('/advanced-config/numbering'),
  updateNumbering: (entity, data) => api.patch(`/advanced-config/numbering/${entity}`, data),
  resetNumbering: (entity) => api.post(`/advanced-config/numbering/${entity}/reset`),

  // Custom fields
  getCustomFields: (entity) => api.get(`/advanced-config/custom-fields${entity ? `?entity=${entity}` : ''}`),
  createCustomField: (data) => api.post('/advanced-config/custom-fields', data),
  updateCustomField: (id, data) => api.patch(`/advanced-config/custom-fields/${id}`, data),
  deleteCustomField: (id) => api.delete(`/advanced-config/custom-fields/${id}`),

  // Templates
  getTemplates: () => api.get('/advanced-config/templates'),
  createTemplate: (data) => api.post('/advanced-config/templates', data),
  deleteTemplate: (id) => api.delete(`/advanced-config/templates/${id}`),
  applyTemplate: (templateId, projectId, startDate) => api.post(`/advanced-config/templates/${templateId}/apply/${projectId}${startDate ? `?start_date=${startDate}` : ''}`),
}
