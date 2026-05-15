/**
 * Training — courses, certifications, enrollments, skills.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const trainingApi = {
  courses:      (params?: Params): Promise<Response<unknown>> => api.get('/training/courses', { params }),
  course:       (id: Id): Promise<Response<unknown>> => api.get(`/training/courses/${id}`),
  createCourse: (data: JsonBody): Promise<Response<unknown>> => api.post('/training/courses', data),
  updateCourse: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/training/courses/${id}`, data),
  deleteCourse: (id: Id): Promise<Response<unknown>> => api.delete(`/training/courses/${id}`),
  certs:        (params?: Params): Promise<Response<unknown>> => api.get('/training/certifications', { params }),
  cert:         (id: Id): Promise<Response<unknown>> => api.get(`/training/certifications/${id}`),
  createCert:   (data: JsonBody): Promise<Response<unknown>> => api.post('/training/certifications', data),
  updateCert:   (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/training/certifications/${id}`, data),
  deleteCert:   (id: Id): Promise<Response<unknown>> => api.delete(`/training/certifications/${id}`),
  enroll:       (data: JsonBody): Promise<Response<unknown>> => api.post('/training/enrollments', data),
  enrollments:  (params?: Params): Promise<Response<unknown>> => api.get('/training/enrollments', { params }),
}

export const skillsApi = {
  catalog:         (): Promise<Response<unknown>> => api.get('/skills/catalog'),
  createCatalog:   (data: JsonBody): Promise<Response<unknown>> => api.post('/skills/catalog', data),
  deleteCatalog:   (id: Id): Promise<Response<unknown>> => api.delete(`/skills/catalog/${id}`),
  userSkills:      (userId: Id): Promise<Response<unknown>> => api.get(`/skills/users/${userId}`),
  userHistory:     (userId: Id): Promise<Response<unknown>> => api.get(`/skills/users/${userId}/history`),
  addUserSkill:    (userId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/skills/users/${userId}`, data),
  removeUserSkill: (userId: Id, skillId: Id): Promise<Response<unknown>> =>
    api.delete(`/skills/users/${userId}/${skillId}`),
  matrix:          (): Promise<Response<unknown>> => api.get('/skills/matrix'),
  search:          (params?: Params): Promise<Response<unknown>> => api.get('/skills/search', { params }),
}
