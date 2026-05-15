/**
 * Pipeline (opportunities), NPS, scenarios, performance reviews.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const pipelineApi = {
  list:             (params?: Params): Promise<Response<unknown>> => api.get('/pipeline', { params }),
  get:              (id: Id): Promise<Response<unknown>> => api.get(`/pipeline/${id}`),
  create:           (data: JsonBody): Promise<Response<unknown>> => api.post('/pipeline', data),
  update:           (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/pipeline/${id}`, data),
  delete:           (id: Id): Promise<Response<unknown>> => api.delete(`/pipeline/${id}`),
  activities:       (id: Id): Promise<Response<unknown>> => api.get(`/pipeline/${id}/activities`),
  addActivity:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/pipeline/${id}/activities`, data),
  generateProposal: (id: Id, payload?: JsonBody): Promise<Response<unknown>> =>
    api.post(`/pipeline/${id}/generate-proposal`, payload || {}),
  markProposalSent: (id: Id): Promise<Response<unknown>> => api.post(`/pipeline/${id}/mark-proposal-sent`),
  convertToProject: (id: Id): Promise<Response<unknown>> => api.post(`/pipeline/${id}/convert`),
  getProposal:      (id: Id): Promise<Response<unknown>> => api.get(`/pipeline/${id}/proposal`),
}

export const npsApi = {
  leaderboard:   (): Promise<Response<unknown>> => api.get('/nps/leaderboard'),
  summary:       (id: Id, days?: number): Promise<Response<unknown>> =>
    api.get(`/nps/${id}/summary`, { params: { days } }),
  health:        (id: Id, limit?: number): Promise<Response<unknown>> =>
    api.get(`/nps/${id}/health`, { params: { limit } }),
  healthCompute: (id: Id): Promise<Response<unknown>> => api.post(`/nps/${id}/health-compute`),
  respond:       (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/nps/${id}/responses`, data),
}

export const scenariosApi = {
  list:    (): Promise<Response<unknown>> => api.get('/scenarios'),
  get:     (id: Id): Promise<Response<unknown>> => api.get(`/scenarios/${id}`),
  create:  (data: JsonBody): Promise<Response<unknown>> => api.post('/scenarios', data),
  compute: (id: Id): Promise<Response<unknown>> => api.post(`/scenarios/${id}/compute`),
  delete:  (id: Id): Promise<Response<unknown>> => api.delete(`/scenarios/${id}`),
}

export const performanceApi = {
  cycles:                  (): Promise<Response<unknown>> => api.get('/performance/cycles'),
  myReviews:               (): Promise<Response<unknown>> => api.get('/performance/my-reviews'),
  cycleReviews:            (id: Id): Promise<Response<unknown>> => api.get(`/performance/cycles/${id}/reviews`),
  createCycle:             (data: JsonBody): Promise<Response<unknown>> => api.post('/performance/cycles', data),
  activateCycle:           (id: Id): Promise<Response<unknown>> => api.post(`/performance/cycles/${id}/activate`),
  closeCycle:              (id: Id): Promise<Response<unknown>> => api.post(`/performance/cycles/${id}/close`),
  createReview:            (cycleId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/performance/cycles/${cycleId}/reviews`, data),
  updateReview:            (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/performance/reviews/${id}`, data),
  submitReview:            (id: Id): Promise<Response<unknown>> => api.post(`/performance/reviews/${id}/submit`),
  userHistory:             (userId: Id): Promise<Response<unknown>> => api.get(`/performance/users/${userId}/history`),
  listQuestions:           (cycleId: Id): Promise<Response<unknown>> =>
    api.get(`/performance/cycles/${cycleId}/questions`),
  addQuestion:             (cycleId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/performance/cycles/${cycleId}/questions`, data),
  updateQuestion:          (qId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/performance/questions/${qId}`, data),
  deleteQuestion:          (qId: Id): Promise<Response<unknown>> => api.delete(`/performance/questions/${qId}`),
  seedDefaultQuestions:    (cycleId: Id): Promise<Response<unknown>> =>
    api.post(`/performance/cycles/${cycleId}/questions/seed-default`),
  cloneQuestions:          (cycleId: Id, sourceId: Id): Promise<Response<unknown>> =>
    api.post(`/performance/cycles/${cycleId}/clone-questions/${sourceId}`),
  eligibleReviewers:       (cycleId: Id, revieweeId: Id, type: string): Promise<Response<unknown>> =>
    api.get(`/performance/cycles/${cycleId}/eligible-reviewers/${revieweeId}/${type}`),
  listCampaigns:           (cycleId: Id): Promise<Response<unknown>> =>
    api.get(`/performance/cycles/${cycleId}/campaigns`),
  createCampaign:          (cycleId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/performance/cycles/${cycleId}/campaigns`, data),
  closeCampaign:           (id: Id): Promise<Response<unknown>> => api.post(`/performance/campaigns/${id}/close`),
  campaignDashboard:       (id: Id): Promise<Response<unknown>> => api.get(`/performance/campaigns/${id}/dashboard`),
  campaignDashboardPdf:    (id: Id): Promise<Response<Blob>> =>
    api.get(`/performance/campaigns/${id}/dashboard.pdf`, { responseType: 'blob' }),
  campaignReviews:         (id: Id): Promise<Response<unknown>> => api.get(`/performance/campaigns/${id}/reviews`),
  history360:              (userId: Id): Promise<Response<unknown>> =>
    api.get(`/performance/users/${userId}/360-history`),
  orgKpis:                 (): Promise<Response<unknown>> => api.get('/performance/kpis'),
  cycleKpis:               (id: Id): Promise<Response<unknown>> => api.get(`/performance/cycles/${id}/kpis`),
  runReminders:            (): Promise<Response<unknown>> => api.post('/performance/admin/run-reminders'),
  listUserPlans:           (userId: Id): Promise<Response<unknown>> =>
    api.get(`/performance/users/${userId}/dev-plans`),
  getPlan:                 (id: Id): Promise<Response<unknown>> => api.get(`/performance/dev-plans/${id}`),
  createPlan:              (data: JsonBody): Promise<Response<unknown>> => api.post('/performance/dev-plans', data),
  updatePlan:              (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/performance/dev-plans/${id}`, data),
  addGoal:                 (planId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/performance/dev-plans/${planId}/goals`, data),
  updateGoal:              (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/performance/dev-goals/${id}`, data),
  deleteGoal:              (id: Id): Promise<Response<unknown>> => api.delete(`/performance/dev-goals/${id}`),
}
