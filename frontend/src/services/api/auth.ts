/**
 * Auth endpoints — login, password flows, /me, LDAP sync, MFA.
 */
import { api } from './client'
import type { Id, JsonBody, Response } from './types'

// TODO type: refine against `app/schemas/auth.py` once consolidated.
export interface LoginCredentials {
  username: string
  password: string
  mfa_code?: string
}

export interface ForgotPasswordPayload {
  email: string
}

export interface ResetPasswordPayload {
  token: string
  new_password: string
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

export const authApi = {
  login:          (credentials: LoginCredentials): Promise<Response<unknown>> => api.post('/auth/login', credentials),
  forgotPassword: (payload: ForgotPasswordPayload): Promise<Response<unknown>> => api.post('/auth/password/forgot', payload),
  resetPassword:  (payload: ResetPasswordPayload): Promise<Response<unknown>> => api.post('/auth/password/reset', payload),
  me:             (): Promise<Response<unknown>> => api.get('/auth/me'),
  syncLdap:       (): Promise<Response<unknown>> => api.post('/auth/ldap/sync'),
  changePassword: (data: ChangePasswordPayload): Promise<Response<unknown>> => api.post('/auth/change-password', data),
}

export const mfaApi = {
  status:  (): Promise<Response<unknown>> => api.get('/mfa/status'),
  setup:   (): Promise<Response<unknown>> => api.post('/mfa/setup'),
  verify:  (code: string): Promise<Response<unknown>> => api.post('/mfa/verify', { code }),
  disable: (code: string): Promise<Response<unknown>> => api.delete('/mfa/disable', { data: { code } }),
}

// User-costs (cost-per-hour, salary, employer cost)
export const userCostsApi = {
  listCountries:    (): Promise<Response<unknown>> => api.get('/user-costs/countries'),
  upsertCountry:    (data: JsonBody): Promise<Response<unknown>> => api.post('/user-costs/countries', data),
  seedCountries:    (force?: boolean): Promise<Response<unknown>> =>
    api.post('/user-costs/countries/seed', null, { params: { force: !!force } }),
  updateCountry:    (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/user-costs/countries/${id}`, d),
  deleteCountry:    (id: Id): Promise<Response<unknown>> => api.delete(`/user-costs/countries/${id}`),
  listProfiles:     (uid: Id): Promise<Response<unknown>> => api.get(`/user-costs/users/${uid}/profiles`),
  createProfile:    (uid: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/user-costs/users/${uid}/profiles`, d),
  active:           (uid: Id, on?: string): Promise<Response<unknown>> =>
    api.get(`/user-costs/users/${uid}/active`, { params: { on } }),
  preview:          (uid: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/user-costs/users/${uid}/preview`, d),
  updateProfile:    (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/user-costs/profiles/${id}`, d),
  deleteProfile:    (id: Id): Promise<Response<unknown>> => api.delete(`/user-costs/profiles/${id}`),
  summary:          (on?: string): Promise<Response<unknown>> => api.get('/user-costs/summary', { params: { on } }),
}
