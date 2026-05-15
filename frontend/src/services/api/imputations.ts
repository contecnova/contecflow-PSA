/**
 * Imputations (time tracking) + timer + timesheets.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

// TODO type: tighten against `app/schemas/imputation.py`.
export interface ImputationCreatePayload extends JsonBody {
  project_id: Id
  task_id?: Id | null
  date: string
  hours: number
  description?: string
}

export const imputationsApi = {
  list:          (params?: Params): Promise<Response<unknown>> => api.get('/imputations', { params }),
  myWeek:        (params?: Params): Promise<Response<unknown>> => api.get('/imputations/my/week', { params }),
  create:        (data: ImputationCreatePayload): Promise<Response<unknown>> => api.post('/imputations', data),
  update:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/imputations/${id}`, data),
  delete:        (id: Id): Promise<Response<unknown>> => api.delete(`/imputations/${id}`),
  approve:       (id: Id): Promise<Response<unknown>> => api.post(`/imputations/${id}/approve`),
  reject:        (id: Id): Promise<Response<unknown>> => api.post(`/imputations/${id}/reject`),
  timerCurrent:  (): Promise<Response<unknown>> => api.get('/imputations/timer/current'),
  timerStart:    (data: JsonBody): Promise<Response<unknown>> => api.post('/imputations/timer/start', data),
  timerPause:    (): Promise<Response<unknown>> => api.post('/imputations/timer/pause'),
  timerResume:   (): Promise<Response<unknown>> => api.post('/imputations/timer/resume'),
  timerCancel:   (): Promise<Response<unknown>> => api.post('/imputations/timer/cancel'),
  timerStop:     (data: JsonBody): Promise<Response<unknown>> => api.post('/imputations/timer/stop', data),
}

export const timesheetsApi = {
  my:        (): Promise<Response<unknown>> => api.get('/timesheets/my'),
  pending:   (): Promise<Response<unknown>> => api.get('/timesheets/pending'),
  team:      (): Promise<Response<unknown>> => api.get('/timesheets/team'),
  weekLines: (weekStart: string): Promise<Response<unknown>> => api.get(`/timesheets/my/${weekStart}/lines`),
  submit:    (weekStart: string): Promise<Response<unknown>> => api.post(`/timesheets/my/${weekStart}/submit`),
  review:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/timesheets/${id}/review`, data),
}
