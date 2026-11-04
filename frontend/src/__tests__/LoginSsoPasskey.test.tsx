// Auditoría 2026-11: la vuelta del proveedor SSO (?code&state) no se canjeaba
// en ningún sitio, y «Entrar con passkey» llamaba a /auth/login con la
// contraseña vacía. Ahora se canjea el código y la passkey va sola.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { acceptSession, api } = vi.hoisted(() => ({ acceptSession: vi.fn(), api: {
  listSsoProviders: vi.fn(() => Promise.resolve({ data: [] })),
  ssoCallback: vi.fn(() => Promise.resolve({ data: { user: { id: 'u1', username: 'u', role: 'pm' } } })),
  passkeyLoginStart: vi.fn(() => Promise.resolve({ data: { options: { challenge: 'AA' }, webauthn_challenge_token: 'tok' } })),
  passkeyLoginFinish: vi.fn(() => Promise.resolve({ data: { user: { id: 'u2', username: 'v', role: 'employee' } } })),
  login: vi.fn(),
} }))
vi.mock('../services/api', () => ({ authApi: api }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ acceptSession, sessionExpired: false }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => Object.assign((k: string) => k, { t: (k: string) => k }), useAppLang: () => ({ t: (k: string) => k, lang: 'es', setLang: vi.fn() }) }))
vi.mock('../components/LangSelector', () => ({ default: () => null }))
vi.mock('../lib/webauthn', () => ({ webauthnSupported: () => true, startAuthentication: vi.fn(() => Promise.resolve({ id: 'cred' })) }))

import LoginPage from '../pages/LoginPage'

describe('LoginPage', () => {
  beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })

  it('canjea el código cuando el proveedor SSO vuelve a /login', async () => {
    sessionStorage.setItem('cf_sso_config', 'cfg-1')
    render(<MemoryRouter initialEntries={['/login?code=abc&state=xyz.sig']}><LoginPage /></MemoryRouter>)
    await waitFor(() => expect(api.ssoCallback).toHaveBeenCalledWith('cfg-1', expect.objectContaining({ code: 'abc', state: 'xyz.sig' })))
    await waitFor(() => expect(acceptSession).toHaveBeenCalled())
  })

  it('la passkey entra sin usuario ni contraseña', async () => {
    render(<MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>)
    fireEvent.click(await screen.findByText('login.passkey_button'))
    await waitFor(() => expect(api.passkeyLoginFinish).toHaveBeenCalledWith({ webauthn_challenge_token: 'tok', credential: { id: 'cred' } }))
    expect(api.login).not.toHaveBeenCalled()
    await waitFor(() => expect(acceptSession).toHaveBeenCalled())
  })
})
