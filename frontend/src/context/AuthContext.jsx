import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

// Key used to hint that an active session cookie may exist.
// The value is never a token — it's only used to avoid a guaranteed-401
// /auth/me call when the user is definitely not logged in.
const SESSION_HINT_KEY = 'cf_authed'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    // Only attempt session restoration if a hint says the user logged in before.
    // This avoids an unnecessary 401 on first visit / after logout.
    if (!localStorage.getItem(SESSION_HINT_KEY)) {
      setLoading(false)
      return
    }
    // Restore session by validating the httpOnly cookie via /auth/me.
    // No token is read from localStorage — cookies are sent automatically.
    api.get('/auth/me')
      .then(res => { setUser(res.data) })
      .catch(() => {
        localStorage.removeItem(SESSION_HINT_KEY)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  // Listen for session-expired events fired by the axios interceptor when
  // a token refresh fails. Show a brief message before clearing the session.
  useEffect(() => {
    const handler = () => {
      localStorage.removeItem(SESSION_HINT_KEY)
      setUser(null)
      setSessionExpired(true)
      // Auto-clear the banner after 4 seconds so the login page is clean
      setTimeout(() => setSessionExpired(false), 4000)
    }
    window.addEventListener('auth:session-expired', handler)
    return () => window.removeEventListener('auth:session-expired', handler)
  }, [])

  const login = useCallback(async (username, password) => {
    const { data } = await api.post('/auth/login', { username, password })
    // Tokens are now stored in httpOnly cookies set by the server.
    // We only keep the user profile in React state (never in localStorage).
    localStorage.setItem(SESSION_HINT_KEY, '1')
    setUser(data.user)
    setSessionExpired(false)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch { /* noop */ }
    localStorage.removeItem(SESSION_HINT_KEY)
    setUser(null)
  }, [])

  const hasRole = useCallback((...roles) => {
    if (!user) return false
    return roles.includes(user.role)
  }, [user])

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, logout, hasRole, sessionExpired }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
