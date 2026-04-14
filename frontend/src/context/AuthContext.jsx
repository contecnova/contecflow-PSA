import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    // Restore session by validating the httpOnly cookie via /auth/me.
    // No token is read from localStorage — cookies are sent automatically.
    api.get('/auth/me')
      .then(res => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  // Listen for session-expired events fired by the axios interceptor when
  // a token refresh fails. Show a brief message before clearing the session.
  useEffect(() => {
    const handler = () => {
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
    setUser(data.user)
    setSessionExpired(false)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch { /* noop */ }
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
