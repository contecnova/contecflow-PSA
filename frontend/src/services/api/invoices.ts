/**
 * Invoices, accounting hub, revenue (legacy + ASC 606), budgets, billing report templates, smart-match.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const invoicesApi = {
  list:           (params?: Params): Promise<Response<unknown>> => api.get('/invoices', { params }),
  get:            (id: Id): Promise<Response<unknown>> => api.get(`/invoices/${id}`),
  summary:        (): Promise<Response<unknown>> => api.get('/invoices/summary'),
  create:         (data: JsonBody): Promise<Response<unknown>> => api.post('/invoices', data),
  updateStatus:   (id: Id, status: string): Promise<Response<Blob | unknown>> =>
    api.patch(`/invoices/${id}/status`, { status }),
  pdf:            (id: Id): Promise<Response<Blob>> => api.get(`/invoices/${id}/pdf`, { responseType: 'blob' }),
  fromTimesheets: (data: JsonBody): Promise<Response<unknown>> => api.post('/invoices/from-timesheets', data),
}

export const accountingApi = {
  syncStatus:   (): Promise<Response<unknown>> => api.get('/accounting/sync-status'),
  xeroTest:     (): Promise<Response<unknown>> => api.post('/accounting/xero/test'),
  qbTest:       (): Promise<Response<unknown>> => api.post('/accounting/qb/test'),
  pushInvoice:  (data: JsonBody): Promise<Response<unknown>> => api.post('/accounting/push-invoice', data),
  pushBulk:     (data: JsonBody): Promise<Response<unknown>> => api.post('/accounting/push-invoices-bulk', data),
  xeroContacts: (): Promise<Response<unknown>> => api.get('/accounting/xero/contacts'),
}

export const revenueApi = {
  rules:       (): Promise<Response<unknown>> => api.get('/revenue/rules'),
  summary:     (): Promise<Response<unknown>> => api.get('/revenue/summary'),
  createRule:  (data: JsonBody): Promise<Response<unknown>> => api.post('/revenue/rules', data),
  autoCompute: (period: string): Promise<Response<unknown>> => api.post('/revenue/auto-compute', { period }),
  compute:     (id: Id, period: string): Promise<Response<unknown>> => api.post(`/revenue/rules/${id}/compute`, { period }),
}

export const revenueRecognitionApi = {
  dashboard:             (year: number, months?: number): Promise<Response<unknown>> =>
    api.get('/revenue-recognition/dashboard', { params: { year, months } }),
  contracts:             (params?: Params): Promise<Response<unknown>> => api.get('/revenue-recognition/contracts', { params }),
  getContract:           (id: Id): Promise<Response<unknown>> => api.get(`/revenue-recognition/contracts/${id}`),
  createContract:        (data: JsonBody): Promise<Response<unknown>> => api.post('/revenue-recognition/contracts', data),
  updateContract:        (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/revenue-recognition/contracts/${id}`, data),
  deleteContract:        (id: Id): Promise<Response<unknown>> => api.delete(`/revenue-recognition/contracts/${id}`),
  obligations:           (contractId: Id): Promise<Response<unknown>> =>
    api.get(`/revenue-recognition/contracts/${contractId}/obligations`),
  createObligation:      (contractId: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.post(`/revenue-recognition/contracts/${contractId}/obligations`, d),
  updateObligation:      (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/revenue-recognition/obligations/${id}`, data),
  deleteObligation:      (id: Id): Promise<Response<unknown>> => api.delete(`/revenue-recognition/obligations/${id}`),
  entries:               (params?: Params): Promise<Response<unknown>> => api.get('/revenue-recognition/entries', { params }),
  reverseEntry:          (id: Id): Promise<Response<unknown>> => api.post(`/revenue-recognition/entries/${id}/reverse`),
  periodCloses:          (): Promise<Response<unknown>> => api.get('/revenue-recognition/period-closes'),
  closePeriod:           (data: JsonBody): Promise<Response<unknown>> => api.post('/revenue-recognition/period-closes', data),
  reopenPeriod:          (year: number, month: number): Promise<Response<unknown>> =>
    api.delete(`/revenue-recognition/period-closes/${year}/${month}`),
  runMonthly:            (data: JsonBody): Promise<Response<unknown>> => api.post('/revenue-recognition/run-monthly', data),
}

export const budgetsApi = {
  list:        (year?: number): Promise<Response<unknown>> => api.get('/budgets', { params: { year } }),
  summary:     (year?: number): Promise<Response<unknown>> => api.get('/budgets/summary', { params: { year } }),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/budgets', data),
  updateEntry: (id: Id, month: number, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/budgets/${id}/entry`, { month, ...data }),
  approve:     (id: Id): Promise<Response<unknown>> => api.post(`/budgets/${id}/approve`),
}

export const templatesApi = {
  list:        (): Promise<Response<unknown>> => api.get('/billing-reports/templates'),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/billing-reports/templates', data),
  instantiate: (tplId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/billing-reports/templates/${tplId}/instantiate`, data),
}

export const billingSmartMatchApi = {
  match: (data: JsonBody): Promise<Response<unknown>> => api.post('/billing-reports/smartmatch', data),
}
