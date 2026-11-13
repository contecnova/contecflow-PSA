import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import api from '../services/api'
import { useToast } from './ToastContext'
import { useIdleTimeout } from '../hooks/useIdleTimeout'
import { useAppLang } from '../i18n/AppLangContext'
import { useDialogo } from '../components/ui/useDialogo'
import { SESSION_EXPIRED_NOTICE_MS } from '../constants/timings'

// Prevent Vite from hot-replacing this module individually: a partial HMR reload
// creates a new context reference while AuthProvider still injects the old one,
// causing "useAuth must be used inside AuthProvider" in consumers.
// Audit #C9: `.decline()` is removed from Vite's typings but still functions; cast
// to keep strict mode happy without altering runtime behaviour.
if (import.meta.hot) (import.meta.hot as { decline?: () => void }).decline?.()

// ── Public domain types ─────────────────────────────────────────────────
// Other modules (hooks, pages, components) import these via:
//   import type { Role, User, AuthContextValue } from '../context/AuthContext'

/**
 * Application-level user role.
 * 'superadmin' is the cross-org platform owner; it intentionally bypasses
 * most role checks (see hasRole logic).
 */
export type Role =
  | 'admin'
  | 'pm'
  | 'team_lead'
  | 'employee'
  | 'hr'
  | 'finance'
  | 'sales'
  | 'client'
  | 'superadmin'
  | string

/**
 * Shape of the user returned by /auth/me and /auth/login.
 * Keep this loose: the backend may add fields without breaking the contract.
 */
export interface User {
  id: string
  username: string
  email?: string
  full_name?: string | null
  role: Role
  is_active?: boolean
  is_superadmin?: boolean
  organization_id?: string | null
  department?: string | null
  hourly_rate?: number | null
  // Allow forwards-compatible extra fields from the API.
  [key: string]: unknown
}

/**
 * Reactive state exposed by the auth context.
 */
export interface AuthState {
  user: User | null
  loading: boolean
  sessionExpired: boolean
}

/**
 * Full value returned by `useAuth()`.
 */
export interface AuthContextValue extends AuthState {
  setUser: (user: User | null) => void
  /** Call after /auth/login succeeds (no MFA) to set state. */
  login: (username: string, password: string) => Promise<User>
  /** Call after MFA or passkey verification — cookies already set by backend. */
  acceptSession: (userData: User) => void
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
  /** False when the user's role closes the module this route belongs to. */
  canOpen: (path: string) => boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

// Key used to hint that an active session cookie may exist.
// The value is never a token — it's only used to avoid a guaranteed-401
// /auth/me call when the user is definitely not logged in.
const SESSION_HINT_KEY = 'cf_authed'

// Storage keys that are tied to the current user's session and must be
// cleared on logout. UI-only preferences (theme, language, pinned routes,
// column visibility, dashboard layouts, etc.) are intentionally NOT listed
// here so they survive between sessions on the same device.
const SESSION_STORAGE_KEYS: readonly string[] = [
  SESSION_HINT_KEY,
  'nexusassist_last_conversation_id', // points to a per-user AI conversation
]
const SESSION_SESSIONSTORAGE_KEYS: readonly string[] = [
  'collab-notif-asked', // "have we asked this user for OS notif permission yet?"
]

function clearSessionStorage(): void {
  try {
    SESSION_STORAGE_KEYS.forEach(k => {
      try { localStorage.removeItem(k) } catch { /* noop */ }
    })
    SESSION_SESSIONSTORAGE_KEYS.forEach(k => {
      try { sessionStorage.removeItem(k) } catch { /* noop */ }
    })
  } catch { /* noop */ }
}

interface AuthProviderProps {
  children?: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { t } = useAppLang()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [sessionExpired, setSessionExpired] = useState<boolean>(false)
  const [idleEnabled, setIdleEnabled] = useState<boolean>(false)
  const [idleMinutes, setIdleMinutes] = useState<number>(30)
  const toast = useToast()

  useEffect(() => {
    // Skip the operator-session restore entirely on the client portal — that
    // route uses its own ClientAuthContext (ClientUser ≠ User) and the
    // operator /auth/me would always 401 there, polluting the console.
    const path = typeof window !== 'undefined' ? window.location.pathname : ''
    if (path === '/portal' || path.startsWith('/portal/')) {
      setLoading(false)
      return
    }
    // Only attempt session restoration if a hint says the user logged in before.
    // This avoids an unnecessary 401 on first visit / after logout.
    if (!localStorage.getItem(SESSION_HINT_KEY)) {
      setLoading(false)
      return
    }
    // Restore session by validating the httpOnly cookie via /auth/me.
    // No token is read from localStorage — cookies are sent automatically.
    // TODO type: services/api still JS, response shape inferred from User
    api.get('/auth/me')
      .then((res: { data: User }) => { setUser(res.data) })
      .catch(() => {
        localStorage.removeItem(SESSION_HINT_KEY)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  // Fetch idle timeout settings whenever a user session is active
  useEffect(() => {
    if (!user) return
    // TODO type: services/api still JS — settings is array of {key,value}
    api.get('/settings/general').then((res: { data: Array<{ key: string; value: string }> }) => {
      const settings = res.data || []
      const find = (k: string): string | undefined => settings.find(s => s.key === k)?.value
      const enabled = find('idle_timeout_enabled')
      const minutes = find('idle_timeout_minutes')
      if (enabled !== undefined) setIdleEnabled(enabled === 'true')
      if (minutes !== undefined) setIdleMinutes(Math.max(1, parseInt(minutes, 10) || 30))
    }).catch(() => {})
  }, [user])

  // Listen for session-expired events fired by the axios interceptor when
  // a token refresh fails. Show a brief message before clearing the session.
  useEffect(() => {
    const handler = () => {
      clearSessionStorage()
      setUser(null)
      setSessionExpired(true)
      // Auto-clear the banner after 4 seconds so the login page is clean
      setTimeout(() => setSessionExpired(false), SESSION_EXPIRED_NOTICE_MS)
    }
    window.addEventListener('auth:session-expired', handler)
    return () => window.removeEventListener('auth:session-expired', handler)
  }, [])

  // 429 — Rate limit global handler: shows a toast whenever any endpoint is throttled
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ retryAfter?: number }>).detail
      const retryAfter = detail?.retryAfter
      const msg = retryAfter
        ? `Demasiadas peticiones. Espera ${retryAfter}s antes de reintentar.`
        : 'Demasiadas peticiones. Espera un momento antes de reintentar.'
      toast.warning(msg, 5000)
    }
    window.addEventListener('api:rate-limited', handler)
    return () => window.removeEventListener('api:rate-limited', handler)
  }, [toast])

  const acceptSession = useCallback((userData: User): void => {
    localStorage.setItem(SESSION_HINT_KEY, '1')
    setUser(userData)
    setSessionExpired(false)
    // Las rutas cerradas por el rol llegan completas en /auth/me (el paso de
    // MFA o de passkey devuelve un usuario sin ellas).
    api.get('/auth/me').then((res: { data: User }) => setUser(res.data)).catch(() => { /* la sesión ya está */ })
  }, [])

  const login = useCallback(async (username: string, password: string): Promise<User> => {
    // TODO type: services/api still JS — response shape from /auth/login
    const { data } = await api.post('/auth/login', { username, password }) as { data: { user: User } }
    // Tokens are now stored in httpOnly cookies set by the server.
    // We only keep the user profile in React state (never in localStorage).
    acceptSession(data.user)
    return data.user
  }, [acceptSession])

  const logout = useCallback(async (): Promise<void> => {
    // Notify subscribers (chat presence, etc.) BEFORE invalidating the cookie
    // so they can stop firing requests that would otherwise return 401.
    try { window.dispatchEvent(new CustomEvent('auth:logout-start')) } catch { /* noop */ }
    try {
      await api.post('/auth/logout')
    } catch { /* noop */ }
    // Clear all session-scoped storage (cookie hint, per-user AI conv id,
    // notification-permission flag, etc.). UI prefs are kept on purpose.
    clearSessionStorage()
    setUser(null)
  }, [])

  const hasRole = useCallback((...roles: Role[]): boolean => {
    if (!user) return false
    return roles.includes(user.role)
  }, [user])

  const canOpen = useCallback((path: string): boolean => {
    const blocked = Array.isArray(user?.blocked_routes) ? (user?.blocked_routes as string[]) : []
    return !blocked.some(b => path === b || path.startsWith(b + '/'))
  }, [user])

  // Idle timeout — only active when user is logged in
  const { showWarning, secondsLeft, dismiss } = useIdleTimeout({
    enabled: !!user && idleEnabled,
    timeoutMinutes: idleMinutes,
    onTimeout: logout,
    warningSeconds: 60,
  })
  // Auditoria 2026-11 (#41): el aviso de sesion era un overlay sin trampa de
  // foco ni Esc. Esc = "continuar sesion" (lo mismo que el boton principal).
  const avisoRef = useDialogo<HTMLDivElement>(showWarning, dismiss)

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, acceptSession, logout, hasRole, canOpen, sessionExpired }}>
      {children}
      {showWarning && (
        <div role="presentation" style={{
          position: 'fixed', inset: 0, zIndex: 'var(--z-drag)',
          background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div ref={avisoRef} role="alertdialog" aria-modal="true" aria-labelledby="aviso-sesion-titulo" aria-describedby="aviso-sesion-texto" tabIndex={-1} style={{
            background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
            borderRadius: 16, padding: '32px 36px', maxWidth: 400, width: '90%',
            boxShadow: '0 8px 40px rgba(0,0,0,0.4)', textAlign: 'center',
          }}>
            <div aria-hidden="true" style={{ fontSize: 40, marginBottom: 12 }}>⏱️</div>
            <h3 id="aviso-sesion-titulo" style={{ margin: '0 0 8px', color: 'var(--text-1)', fontSize: 'var(--text-lg)', fontWeight: 700 }}>
              {t('authcontext.sesion_a_punto_de_expirar')}
            </h3>
            <p id="aviso-sesion-texto" style={{ color: 'var(--text-2)', margin: '0 0 24px', fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
              {t('authcontext.tu_sesion_se_cerrara_por_inactividad_en')}{' '}
              <strong style={{ color: secondsLeft <= 15 ? 'var(--danger)' : 'var(--accent)' }}>
                {secondsLeft}s
              </strong>.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                onClick={dismiss}
                style={{
                  background: 'var(--accent)', color: 'var(--surface-0)', border: 'none',
                  borderRadius: 8, padding: '10px 24px', fontWeight: 700,
                  cursor: 'pointer', fontSize: 'var(--text-sm)',
                }}
              >
                {t('authcontext.continuar_sesion')}
              </button>
              <button
                onClick={logout}
                style={{
                  background: 'transparent', color: 'var(--text-3)',
                  border: '1px solid var(--surface-4)', borderRadius: 8,
                  padding: '10px 20px', cursor: 'pointer', fontSize: 'var(--text-sm)',
                }}
              >
                {t('authcontext.cerrar_sesion')}
              </button>
            </div>
          </div>
        </div>
      )}
    </AuthContext.Provider>
  )
}

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
