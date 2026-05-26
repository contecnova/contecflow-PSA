/**
 * services/api/auth.ts — Audit #C10 (gradual split of services/api.ts).
 *
 * Typed surface for /auth endpoints. Replaces the loose definition in _core.ts;
 * the barrel `index.ts` re-exports this AFTER `_core` so the typed version wins.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'

// ── Request / response payloads ──────────────────────────────────────────────

export interface LoginCredentials {
  email: string
  password: string
  mfa_code?: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  mfa_required?: boolean
  mfa_challenge_token?: string
}

export interface MeResponse {
  id: string
  email: string
  full_name: string
  role: string
  is_superadmin: boolean
  organization_id: string | null
  language: string | null
  hourly_rate?: number | null
  picture_url?: string | null
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

export interface LdapSyncResponse {
  synced: number
  failed: number
  details?: Array<{ email: string; status: string }>
}

// ── Typed API surface ────────────────────────────────────────────────────────

export const authApi = {
  login: (credentials: LoginCredentials): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/login', credentials),

  forgotPassword: (payload: ForgotPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/forgot', payload),

  resetPassword: (payload: ResetPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/reset', payload),

  me: (): Promise<AxiosResponse<MeResponse>> =>
    api.get('/auth/me'),

  syncLdap: (): Promise<AxiosResponse<LdapSyncResponse>> =>
    api.post('/auth/ldap/sync'),

  changePassword: (data: ChangePasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/change-password', data),
} as const
