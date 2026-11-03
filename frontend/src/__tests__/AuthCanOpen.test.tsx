// Auditoría 2026-11: el acceso por módulo de los roles no se aplicaba. /auth/me
// trae ahora `blocked_routes` y `canOpen` las cierra (menú y enrutador).
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../services/api', () => ({
  default: {
    get: () => Promise.resolve({ data: { id: 'u1', username: 'u', role: 'employee', blocked_routes: ['/projects'] } }),
    post: () => Promise.resolve({ data: {} }),
  },
}))
vi.mock('./ToastContext', () => ({ useToast: () => ({ warning: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ warning: vi.fn(), error: vi.fn() }) }))
vi.mock('../hooks/useIdleTimeout', () => ({ useIdleTimeout: () => ({ showWarning: false, secondsLeft: 0, dismiss: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppLang: () => ({ t: (k: string) => k }) }))

import { AuthProvider, useAuth } from '../context/AuthContext'

function Sonda() {
  const { user, canOpen } = useAuth()
  if (!user) return <span>cargando</span>
  return <span>{`${canOpen('/projects')}|${canOpen('/projects/42')}|${canOpen('/tasks')}|${canOpen('/projects-dashboard')}`}</span>
}

describe('canOpen', () => {
  beforeEach(() => localStorage.setItem('cf_authed', '1'))
  it('cierra la ruta del módulo y sus subrutas, y nada más', async () => {
    render(<AuthProvider><Sonda /></AuthProvider>)
    expect(await screen.findByText('false|false|true|true')).toBeTruthy()
  })
})
