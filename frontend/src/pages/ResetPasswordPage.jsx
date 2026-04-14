import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../services/api'

function strengthScore(password) {
  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[A-Z]/.test(password)) score += 1
  if (/[a-z]/.test(password)) score += 1
  if (/[0-9]/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1
  return Math.min(score, 5)
}

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const score = useMemo(() => strengthScore(password), [password])
  const strengthLabel = ['Muy debil', 'Debil', 'Aceptable', 'Buena', 'Fuerte', 'Excelente'][score]

  const submit = async () => {
    if (!token) {
      setError('El enlace de restablecimiento es invalido o esta incompleto.')
      return
    }
    if (!password) {
      setError('Introduce una nueva contrasena.')
      return
    }
    if (password !== confirmPassword) {
      setError('Las contrasenas no coinciden.')
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const { data } = await authApi.resetPassword({ token, new_password: password })
      setSuccess(data?.message || 'Contrasena actualizada correctamente.')
      setTimeout(() => navigate('/login'), 1200)
    } catch (e) {
      const raw = e.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'No se pudo restablecer la contrasena.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-layout">
      <div className="login-brand-panel">
        <div style={{ position: 'relative', zIndex: 1 }}>
          <h2 style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.2, color: 'var(--text-1)', marginBottom: 12 }}>
            Restablecer
            <br />
            <span style={{ color: 'var(--accent)' }}>contrasena</span>
          </h2>
          <p style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: 1.6, marginBottom: 20, maxWidth: 320 }}>
            Define una contrasena nueva para volver a entrar en tu cuenta.
          </p>
          <Link to="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: 13 }}>
            Volver al inicio de sesion
          </Link>
        </div>
      </div>

      <div className="login-form-panel">
        <div style={{ width: '100%', maxWidth: 380 }}>
          <h3 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-1)', marginBottom: 8 }}>
            Nueva contrasena
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nueva contrasena"
              autoComplete="new-password"
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
            />

            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirmar contrasena"
              autoComplete="new-password"
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
            />

            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
              Fortaleza: <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{strengthLabel}</span>
            </div>

            {error && (
              <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.25)', borderRadius: 8, padding: '10px 14px', color: 'var(--danger)', fontSize: 13 }}>
                {error}
              </div>
            )}

            {success && (
              <div style={{ background: 'rgba(46,204,113,0.08)', border: '1px solid rgba(46,204,113,0.25)', borderRadius: 8, padding: '10px 14px', color: '#2ecc71', fontSize: 13 }}>
                {success}
              </div>
            )}

            <button
              type="button"
              onClick={submit}
              disabled={loading}
              className="btn-primary"
              style={{ width: '100%', padding: '12px', marginTop: 4, fontSize: 14, fontWeight: 700 }}
            >
              {loading ? 'Actualizando...' : 'Actualizar contrasena'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
