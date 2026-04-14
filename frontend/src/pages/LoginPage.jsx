import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { authApi } from '../services/api'

export default function LoginPage() {
  const { login, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const t = useAppT()
  const [form, setForm] = useState({ username: '', password: '' })
  const [forgotInput, setForgotInput] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState(searchParams.get('reset_token') ? 'reset' : 'login')

  const resetToken = searchParams.get('reset_token') || ''

  const handleSubmit = async () => {
    if (!form.username || !form.password) { setError(t('login.input_error')); return }
    setLoading(true)
    setError('')
    try {
      const user = await login(form.username, form.password)
      navigate(user.role === 'employee' ? '/imputar' : '/dashboard')
    } catch (e) {
      const raw = e.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || t('login.credentials_error')))
    } finally {
      setLoading(false)
    }
  }

  const handleForgotPassword = async () => {
    if (!forgotInput.trim()) {
      setError('Introduce tu email o usuario')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const { data } = await authApi.forgotPassword({ email_or_username: forgotInput.trim() })
      setMessage(data?.message || 'Si la cuenta existe, recibirás un email con instrucciones.')
    } catch (e) {
      const raw = e.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'No se pudo procesar la solicitud'))
    } finally {
      setLoading(false)
    }
  }

  const handleResetPassword = async () => {
    if (!resetToken) {
      setError('Token de restablecimiento inválido')
      return
    }
    if (!newPassword) {
      setError('Introduce la nueva contraseña')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const { data } = await authApi.resetPassword({ token: resetToken, new_password: newPassword })
      setMessage(data?.message || 'Contraseña actualizada correctamente. Ya puedes iniciar sesión.')
      setMode('login')
      setNewPassword('')
      setSearchParams({})
    } catch (e) {
      const raw = e.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'No se pudo restablecer la contraseña'))
    } finally {
      setLoading(false)
    }
  }

  const field = (k) => ({
    value: form[k],
    onChange: (e) => setForm(f => ({ ...f, [k]: e.target.value })),
    onKeyDown: (e) => e.key === 'Enter' && handleSubmit(),
  })

  return (
    <div className="login-layout">
      {/* ── Brand panel (left) ───────────────────────────────── */}
      <div className="login-brand-panel">
        {/* Ambient glow */}
        <div style={{
          position: 'absolute', top: '30%', left: '50%', transform: 'translate(-50%,-50%)',
          width: 400, height: 400,
          background: 'radial-gradient(circle, rgba(79,142,247,0.18) 0%, transparent 65%)',
          pointerEvents: 'none',
        }} />
        <div style={{ position: 'relative', zIndex: 1 }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 40 }}>
            <div style={{
              width: 44, height: 44, background: 'var(--accent)',
              borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 20px rgba(79,142,247,0.4)',
            }}>
              <svg viewBox="0 0 16 16" width="22" height="22" fill="none">
                <path d="M12 4C10.8 2.9 9.5 2.5 8 2.5C5 2.5 2.5 5 2.5 8C2.5 11 5 13.5 8 13.5C9.5 13.5 10.8 13.1 12 12"
                  stroke="white" strokeWidth="1.7" strokeLinecap="round" />
                <rect x="7" y="6.5" width="7" height="1.3" rx="0.65" fill="white" opacity="0.95" />
                <rect x="7" y="9" width="5.5" height="1.3" rx="0.65" fill="white" opacity="0.65" />
              </svg>
            </div>
            <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-1)' }}>
              Clarive
            </span>
          </div>

          <h2 style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.2,
            color: 'var(--text-1)', marginBottom: 12 }}>
            {t('login.brand_title')}
            <br />
            <span style={{ color: 'var(--accent)' }}>{t('login.brand_subtitle')}</span>
          </h2>
          <p style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: 1.6, marginBottom: 32, maxWidth: 320 }}>
            {t('login.brand_description')}
          </p>

          {/* Feature pills */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { icon: '◈', label: t('login.feature_1') },
              { icon: '⏱', label: t('login.feature_2') },
              { icon: '📈', label: t('login.feature_3') },
              { icon: '🤖', label: t('login.feature_4') },
            ].map((f, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10,
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>{f.icon}</span>
                <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{f.label}</span>
              </div>
            ))}
          </div>

          {/* Version badge */}
          <div style={{ marginTop: 40, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: 10, fontWeight: 700, background: 'rgba(79,142,247,0.15)',
              color: 'var(--accent)', borderRadius: 6, padding: '3px 8px',
              border: '1px solid rgba(79,142,247,0.25)', letterSpacing: '0.05em',
            }}>v24</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Enterprise · SOC2 · ISO27001</span>
          </div>
        </div>
      </div>

      {/* ── Form panel (right) ───────────────────────────────── */}
      <div className="login-form-panel">
        <div style={{ width: '100%', maxWidth: 380, animation: 'fadeIn 0.35s ease' }}>
          <h3 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-1)', marginBottom: 6 }}>
            {t('login.welcome_title')}
          </h3>
          <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 32 }}>
            {t('login.welcome_subtitle')}
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {mode === 'login' && (
              <>
                <div className="form-group">
                  <label className="form-label" htmlFor="login-user">{t('login.username_label')}</label>
                  <input
                    id="login-user"
                    {...field('username')}
                    placeholder={t('login.username_placeholder')}
                    autoFocus
                    autoComplete="username"
                    style={{
                      width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)',
                      borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14,
                      outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
                      transition: 'border-color 0.15s',
                    }}
                    onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                    onBlur={e => e.target.style.borderColor = 'var(--surface-5)'}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="login-pass">{t('login.password_label')}</label>
                  <input
                    id="login-pass"
                    {...field('password')}
                    type="password"
                    placeholder={t('login.password_placeholder')}
                    autoComplete="current-password"
                    style={{
                      width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)',
                      borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14,
                      outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
                      transition: 'border-color 0.15s',
                    }}
                    onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                    onBlur={e => e.target.style.borderColor = 'var(--surface-5)'}
                  />
                </div>
              </>
            )}

            {mode === 'forgot' && (
              <div className="form-group">
                <label className="form-label" htmlFor="forgot-user">Email o usuario</label>
                <input
                  id="forgot-user"
                  value={forgotInput}
                  onChange={e => setForgotInput(e.target.value)}
                  placeholder="admin@company.com"
                  autoFocus
                  style={{
                    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)',
                    borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14,
                    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
                  }}
                />
              </div>
            )}

            {mode === 'reset' && (
              <div className="form-group">
                <label className="form-label" htmlFor="reset-pass">Nueva contraseña</label>
                <input
                  id="reset-pass"
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="Nueva contraseña"
                  autoFocus
                  style={{
                    width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)',
                    borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: 14,
                    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
                  }}
                />
              </div>
            )}

            {sessionExpired && (
              <div role="alert" style={{
                background: 'rgba(255,165,0,0.08)', border: '1px solid rgba(255,165,0,0.3)',
                borderRadius: 8, padding: '10px 14px', color: '#e08000', fontSize: 13,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span style={{ flexShrink: 0 }}>🔒</span>
                <span>{t('login.session_expired_message')}</span>
              </div>
            )}

            {error && (
              <div role="alert" style={{
                background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.25)',
                borderRadius: 8, padding: '10px 14px', color: 'var(--danger)', fontSize: 13,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span style={{ flexShrink: 0 }}>⚠</span>
                <span>{error}</span>
              </div>
            )}

            {message && (
              <div role="status" style={{
                background: 'rgba(46,204,113,0.08)', border: '1px solid rgba(46,204,113,0.25)',
                borderRadius: 8, padding: '10px 14px', color: '#2ecc71', fontSize: 13,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span style={{ flexShrink: 0 }}>✓</span>
                <span>{message}</span>
              </div>
            )}

            <button
              onClick={mode === 'login' ? handleSubmit : (mode === 'forgot' ? handleForgotPassword : handleResetPassword)}
              disabled={loading}
              className="btn-primary"
              style={{ width: '100%', padding: '12px', marginTop: 4, fontSize: 14, fontWeight: 700 }}
            >
              {loading ? (
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <span style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: 'white', borderRadius: '50%',
                    animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
                  {t('login.loading_button')}
                </span>
              ) : (mode === 'login' ? t('login.login_button') : (mode === 'forgot' ? 'Enviar enlace' : 'Restablecer contraseña'))}
            </button>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: -4 }}>
              {mode === 'login' && (
                <button
                  type="button"
                  onClick={() => { setMode('forgot'); setError(''); setMessage('') }}
                  style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, padding: 0 }}
                >
                  ¿Olvidaste tu contraseña?
                </button>
              )}
              {mode !== 'login' && (
                <button
                  type="button"
                  onClick={() => { setMode('login'); setError(''); setMessage(''); setSearchParams({}) }}
                  style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, padding: 0 }}
                >
                  Volver al login
                </button>
              )}
            </div>
          </div>

          <p style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 11, marginTop: 28, lineHeight: 1.5 }}>
            {t('login.ad_note')}
            <br />
            <span style={{ color: 'var(--text-4)' }}>{t('login.help_text')}</span>
          </p>
        </div>
      </div>
    </div>
  )
}
