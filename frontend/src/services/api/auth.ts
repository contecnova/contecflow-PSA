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
  username: string
  password: string
  mfa_code?: string
}

export interface LoginResponse {
  access_token?: string
  refresh_token?: string
  token_type?: 'bearer'
  user?: Record<string, unknown>
  mfa_required?: boolean
  mfa_challenge_token?: string
  mfa_methods?: string[]
}

export interface MfaValidatePayload {
  mfa_challenge_token: string
  code: string
}

export interface PasskeyStartPayload {
  mfa_challenge_token: string
}

export interface PasskeyFinishPayload {
  mfa_challenge_token: string
  webauthn_challenge_token: string
  credential: Record<string, unknown>
}

export interface SsoProvider {
  id: string
  provider: string
  name: string
  icon?: string
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
  email_or_username: string
}

export interface ResetPasswordPayload {
  token: string
  new_password: string
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

// ── Typed API surface ────────────────────────────────────────────────────────

export const authApi = {
  login: (credentials: LoginCredentials): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/login', credentials),

  validateMfa: (payload: MfaValidatePayload): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/mfa/validate', payload),

  startPasskeyAuth: (payload: PasskeyStartPayload): Promise<AxiosResponse<{ options: Record<string, unknown>; webauthn_challenge_token: string }>> =>
    api.post('/auth/mfa/webauthn/authenticate/start', payload),

  finishPasskeyAuth: (payload: PasskeyFinishPayload): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/mfa/webauthn/authenticate/finish', payload),

  listSsoProviders: (): Promise<AxiosResponse<SsoProvider[]>> =>
    api.get('/auth/sso/providers'),

  authorizeSso: (providerId: string, redirectUri: string): Promise<AxiosResponse<{ authorization_url?: string }>> =>
    api.get(`/auth/sso/${providerId}/authorize`, { params: { redirect_uri: redirectUri } }),

  forgotPassword: (payload: ForgotPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/forgot', payload),

  resetPassword: (payload: ResetPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/reset', payload),

  me: (): Promise<AxiosResponse<MeResponse>> =>
    api.get('/auth/me'),

  changePassword: (data: ChangePasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/change-password', data),
} as const
