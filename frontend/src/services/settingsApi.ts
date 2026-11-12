import type { AxiosResponse } from 'axios'
import api, { type PathId } from './api'

/** `SettingOut` (app/schemas/settings.py). */
export interface SettingOut {
  key: string
  value: string | null
  description: string | null
}

/** `DepartmentOut` (app/schemas/settings.py). */
export interface DepartmentOut {
  id: string
  name: string
  description: string | null
  manager_id: string | null
  area_id: string | null
  is_active: boolean
}

/** Rol tal como lo devuelve `list_roles` (app/services/advanced_config_service.py). */
export interface CustomRole {
  id: string
  name: string
  description: string | null
  color: string | null
  is_system: boolean
  module_access: Record<string, unknown>
  permissions: Record<string, unknown>
}

/** Elemento de `/advanced-config/modules`. */
export interface ModuleOption {
  id: string
  label: string
}

export const settingsApi = {
  // General
  getGeneral: (): Promise<AxiosResponse<SettingOut[]>> => api.get('/settings/general'),
  updateSetting: (key: PathId, value: string): Promise<AxiosResponse<SettingOut>> => api.patch(`/settings/general/${key}`, { value }),

  // Departments
  getDepartments: (): Promise<AxiosResponse<DepartmentOut[]>> => api.get('/settings/departments'),
  createDepartment: (data: Record<string, unknown>) => api.post('/settings/departments', data),
  updateDepartment: (id: PathId, data: Record<string, unknown>) => api.patch(`/settings/departments/${id}`, data),
  deleteDepartment: (id: PathId) => api.delete(`/settings/departments/${id}`),
}

// Advanced config API
export const advancedConfigApi = {
  // Roles
  getRoles: (): Promise<AxiosResponse<CustomRole[]>> => api.get('/advanced-config/roles'),
  getModules: (): Promise<AxiosResponse<ModuleOption[]>> => api.get('/advanced-config/modules'),
  createRole: (data: Record<string, unknown>) => api.post('/advanced-config/roles', data),
  updateRole: (id: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/roles/${id}`, data),
  deleteRole: (id: PathId) => api.delete(`/advanced-config/roles/${id}`),

  // Task types
  getTaskTypes: () => api.get('/advanced-config/task-types'),
  createTaskType: (data: Record<string, unknown>) => api.post('/advanced-config/task-types', data),
  updateTaskType: (id: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/task-types/${id}`, data),
  deleteTaskType: (id: PathId) => api.delete(`/advanced-config/task-types/${id}`),

  // Alert configs
  getAlertConfigs: () => api.get('/advanced-config/alert-configs'),
  updateAlertConfig: (alertType: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/alert-configs/${alertType}`, data),

  // Rate tables
  getRateTables: () => api.get('/advanced-config/rate-tables'),
  createRateTable: (data: Record<string, unknown>) => api.post('/advanced-config/rate-tables', data),
  deleteRateTable: (id: PathId) => api.delete(`/advanced-config/rate-tables/${id}`),
  addRateEntry: (tableId: PathId, data: Record<string, unknown>) => api.post(`/advanced-config/rate-tables/${tableId}/entries`, data),
  updateRateEntry: (tableId: PathId, entryId: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`, data),
  deleteRateEntry: (tableId: PathId, entryId: PathId) => api.delete(`/advanced-config/rate-tables/${tableId}/entries/${entryId}`),

  // Vacation policies
  getVacationPolicies: () => api.get('/advanced-config/vacation-policies'),
  createVacationPolicy: (data: Record<string, unknown>) => api.post('/advanced-config/vacation-policies', data),
  deleteVacationPolicy: (id: PathId) => api.delete(`/advanced-config/vacation-policies/${id}`),
  getVacationBalances: (year: PathId) => api.get(`/advanced-config/vacation-balances?year=${year}`),
  updateVacationBalance: (userId: PathId, year: PathId, days: number) => api.patch(`/advanced-config/vacation-balances/${userId}?year=${year}&days_entitled=${days}`),

  // Offices
  getOffices: () => api.get('/advanced-config/offices'),
  createOffice: (data: Record<string, unknown>) => api.post('/advanced-config/offices', data),
  updateOffice: (id: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/offices/${id}`, data),
  deleteOffice: (id: PathId) => api.delete(`/advanced-config/offices/${id}`),

  // Numbering
  getNumbering: () => api.get('/advanced-config/numbering'),
  updateNumbering: (entity: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/numbering/${entity}`, data),
  resetNumbering: (entity: PathId) => api.post(`/advanced-config/numbering/${entity}/reset`),

  // Custom fields
  getCustomFields: (entity?: PathId) => api.get(`/advanced-config/custom-fields${entity ? `?entity=${entity}` : ''}`),
  createCustomField: (data: Record<string, unknown>) => api.post('/advanced-config/custom-fields', data),
  updateCustomField: (id: PathId, data: Record<string, unknown>) => api.patch(`/advanced-config/custom-fields/${id}`, data),
  deleteCustomField: (id: PathId) => api.delete(`/advanced-config/custom-fields/${id}`),

  // Templates
  getTemplates: () => api.get('/advanced-config/templates'),
  createTemplate: (data: Record<string, unknown>) => api.post('/advanced-config/templates', data),
  deleteTemplate: (id: PathId) => api.delete(`/advanced-config/templates/${id}`),
}
