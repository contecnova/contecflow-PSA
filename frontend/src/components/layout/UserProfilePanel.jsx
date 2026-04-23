/**
 * UserProfilePanel — Panel lateral de perfil de usuario
 * Se abre al hacer clic en el nombre/avatar en el footer del sidebar.
 * 
 * Secciones:
 * 1. Mi perfil (editar nombre, teléfono, cargo, avatar)
 * 2. Apariencia (tema: dark/light/midnight/slate/high-contrast, acento, densidad)
 * 3. Idioma
 * 4. Seguridad (cambio de contraseña, MFA)
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import useUserPreferences from '../../hooks/useUserPreferences'
import { useAppLang } from '../../i18n/AppLangContext'
import { Avatar } from '../ui'

// ── Temas disponibles ─────────────────────────────────────────────────────────
const THEMES = [
  { id: 'dark',          label: 'Oscuro',         icon: '🌙', desc: 'Azul pizarra — predeterminado' },
  { id: 'midnight',      label: 'Midnight',        icon: '🌌', desc: 'Oscuro profundo, casi negro' },
  { id: 'slate',         label: 'Slate',           icon: '⬛', desc: 'Gris neutro estilo GitHub' },
  { id: 'light',         label: 'Claro',           icon: '☀️', desc: 'Fondo blanco, texto oscuro' },
  { id: 'high-contrast', label: 'Alto contraste',  icon: '◑',  desc: 'Máximo contraste, accesible' },
  { id: 'system',        label: 'Sistema',         icon: '💻', desc: 'Sigue la preferencia del SO' },
]

const ACCENT_PRESETS = [
  { label: 'Azul',    color: 'var(--accent)' },
  { label: 'Índigo',  color: '#7c3aed' },
  { label: 'Teal',    color: '#1d9e75' },
  { label: 'Cyan',    color: '#0ea5e9' },
  { label: 'Rosa',    color: '#f43f5e' },
  { label: 'Ámbar',   color: '#f59e0b' },
  { label: 'Verde',   color: '#16a34a' },
  { label: 'Coral',   color: '#f97316' },
]

const LANGUAGES = [
  { code: 'es', label: 'Español',   flag: '🇪🇸' },
  { code: 'en', label: 'English',   flag: '🇬🇧' },
  { code: 'fr', label: 'Français',  flag: '🇫🇷' },
  { code: 'de', label: 'Deutsch',   flag: '🇩🇪' },
  { code: 'pt', label: 'Português', flag: '🇵🇹' },
  { code: 'it', label: 'Italiano',  flag: '🇮🇹' },
  { code: 'pl', label: 'Polski',    flag: '🇵🇱' },
  { code: 'zh', label: '中文',       flag: '🇨🇳' },
]

const IS = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}

export default function UserProfilePanel({ onClose }) {
  const { user, setUser } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const { prefs, save: savePrefs } = useUserPreferences()
  const { lang: activeLang, setLang } = useAppLang()

  const [tab, setTab] = useState('profile')

  // ── Perfil ──────────────────────────────────────────────────────────────────
  const [profileForm, setProfileForm] = useState({
    first_name: user?.first_name || '',
    last_name:  user?.last_name  || '',
    phone:      user?.phone      || '',
    job_title:  user?.job_title  || '',
    avatar_url: user?.avatar_url || '',
  })

  const { mutate: saveProfile, isPending: savingProfile } = useMutation({
    mutationFn: (data) => api.patch('/users/me', data),
    onSuccess: (res) => {
      setUser(res.data)
      qc.invalidateQueries({ queryKey: ['auth-me'] })
      toast.success('Perfil actualizado')
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al guardar'),
  })

  // ── Apariencia ──────────────────────────────────────────────────────────────
  const [localTheme,   setLocalTheme]   = useState(prefs?.theme_mode  || 'dark')
  const [localAccent,  setLocalAccent]  = useState(
    (prefs?.accent_color && /^#[0-9a-fA-F]{6}$/.test(prefs.accent_color))
      ? prefs.accent_color
      : '#4f8ef7'
  )
  const [localDensity, setLocalDensity] = useState(prefs?.ui_density  || 'normal')

  const applyTheme = (themeId) => {
    setLocalTheme(themeId)
    if (themeId === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    } else {
      document.documentElement.setAttribute('data-theme', themeId)
    }
  }

  const applyAccent = (color) => {
    setLocalAccent(color)
    const root = document.documentElement
    root.style.setProperty('--accent', color)
    root.style.setProperty('--accent-muted', color + '14')
    root.style.setProperty('--accent-glow',  color + '26')
  }

  const saveAppearance = () => {
    savePrefs({ theme_mode: localTheme, accent_color: localAccent, ui_density: localDensity })
    toast.success('Apariencia guardada')
  }

  // ── Contraseña ──────────────────────────────────────────────────────────────
  const [pwForm, setPwForm] = useState({ current: '', new: '', confirm: '' })
  const { mutate: changePassword, isPending: changingPw } = useMutation({
    mutationFn: (data) => api.post('/auth/change-password', data),
    onSuccess: () => { toast.success('Contraseña actualizada'); setPwForm({ current:'', new:'', confirm:'' }) },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al cambiar contraseña'),
  })

  const TABS = [
    { id: 'profile',    label: '👤 Perfil' },
    { id: 'appearance', label: '🎨 Apariencia' },
    { id: 'language',   label: '🌐 Idioma' },
    { id: 'security',   label: '🔐 Seguridad' },
  ]

  return (
    <>
      {/* Overlay */}
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          zIndex: 299, backdropFilter: 'blur(2px)' }} />

      {/* Panel */}
      <div style={{ position: 'fixed', bottom: 0, left: 0, width: 380, zIndex: 300,
        background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)',
        borderTop: '1px solid var(--surface-4)', borderRadius: '0 16px 0 0',
        display: 'flex', flexDirection: 'column',
        maxHeight: '90vh', boxShadow: '4px -4px 32px rgba(0,0,0,0.4)' }}>

        {/* Header del panel */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)',
          display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
          <Avatar name={user?.full_name} size={44} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.full_name}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)',
              textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 1 }}>
              {user?.role} · {user?.department || 'Sin departamento'}
            </div>
          </div>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-3)',
              cursor: 'pointer', fontSize: 20, padding: '0 4px' }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 2, padding: '8px 12px',
          borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ padding: '6px 10px', borderRadius: 7, fontSize: 11, fontWeight: 600,
                border: `1px solid ${tab === t.id ? 'rgba(79,142,247,0.4)' : 'transparent'}`,
                background: tab === t.id ? 'var(--accent-muted)' : 'transparent',
                color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Contenido */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

          {/* ── PERFIL ───────────────────────────────────────────────────────── */}
          {tab === 'profile' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Info no editable */}
              <div style={{ padding: '10px 14px', background: 'var(--surface-3)',
                borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
                <div>👤 Usuario: <strong style={{ color: 'var(--text-1)' }}>{user?.username}</strong></div>
                <div style={{ marginTop: 4 }}>📧 Email: <strong style={{ color: 'var(--text-1)' }}>{user?.email}</strong></div>
                <div style={{ marginTop: 2, fontSize: 11, color: 'var(--text-3)' }}>
                  El usuario y email los gestiona el administrador
                </div>
              </div>

              {/* Nombre */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    display: 'block', marginBottom: 4 }}>Nombre</label>
                  <input value={profileForm.first_name}
                    onChange={e => setProfileForm(f => ({ ...f, first_name: e.target.value }))}
                    style={IS} placeholder="Tu nombre" />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    display: 'block', marginBottom: 4 }}>Apellidos</label>
                  <input value={profileForm.last_name}
                    onChange={e => setProfileForm(f => ({ ...f, last_name: e.target.value }))}
                    style={IS} placeholder="Tus apellidos" />
                </div>
              </div>

              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>Cargo</label>
                <input value={profileForm.job_title}
                  onChange={e => setProfileForm(f => ({ ...f, job_title: e.target.value }))}
                  style={IS} placeholder="Ej: Senior Developer, Project Manager..." />
              </div>

              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>Teléfono</label>
                <input value={profileForm.phone}
                  onChange={e => setProfileForm(f => ({ ...f, phone: e.target.value }))}
                  style={IS} placeholder="+34 600 000 000" type="tel" />
              </div>

              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>URL de avatar (opcional)</label>
                <input value={profileForm.avatar_url}
                  onChange={e => setProfileForm(f => ({ ...f, avatar_url: e.target.value }))}
                  style={IS} placeholder="https://..." />
                {profileForm.avatar_url && (
                  <img src={profileForm.avatar_url} alt="preview"
                    style={{ width: 40, height: 40, borderRadius: '50%',
                      marginTop: 6, objectFit: 'cover',
                      border: '2px solid var(--surface-4)' }}
                    onError={e => { e.target.style.display = 'none' }} />
                )}
              </div>

              <button onClick={() => saveProfile(profileForm)} disabled={savingProfile}
                style={{ padding: '10px', background: 'var(--accent)', border: 'none',
                  borderRadius: 8, color: '#fff', cursor: savingProfile ? 'wait' : 'pointer',
                  fontSize: 13, fontFamily: 'inherit', fontWeight: 600,
                  opacity: savingProfile ? 0.7 : 1 }}>
                {savingProfile ? 'Guardando...' : '✓ Guardar perfil'}
              </button>
            </div>
          )}

          {/* ── APARIENCIA ───────────────────────────────────────────────────── */}
          {tab === 'appearance' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Tema */}
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  Tema de color
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {THEMES.map(t => (
                    <button key={t.id} onClick={() => applyTheme(t.id)}
                      style={{ display: 'flex', alignItems: 'center', gap: 12,
                        padding: '10px 14px', borderRadius: 9, textAlign: 'left',
                        background: localTheme === t.id ? 'var(--accent-muted)' : 'var(--surface-3)',
                        border: `1px solid ${localTheme === t.id ? 'rgba(79,142,247,0.5)' : 'var(--surface-4)'}`,
                        cursor: 'pointer', fontFamily: 'inherit', width: '100%' }}>
                      <span style={{ fontSize: 20, flexShrink: 0 }}>{t.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600,
                          color: localTheme === t.id ? 'var(--accent)' : 'var(--text-1)' }}>
                          {t.label}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1 }}>
                          {t.desc}
                        </div>
                      </div>
                      {localTheme === t.id && (
                        <span style={{ color: 'var(--accent)', fontSize: 14 }}>✓</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Color de acento */}
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  Color de acento
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 6, marginBottom: 10 }}>
                  {ACCENT_PRESETS.map(p => (
                    <button key={p.color} onClick={() => applyAccent(p.color)}
                      title={p.label}
                      style={{ aspectRatio: '1', borderRadius: 8, background: p.color, border: 'none',
                        cursor: 'pointer', transition: 'transform .1s',
                        outline: localAccent === p.color ? `3px solid ${p.color}` : 'none',
                        outlineOffset: 2,
                        transform: localAccent === p.color ? 'scale(1.15)' : 'scale(1)' }} />
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <input type="color" value={localAccent}
                    onChange={e => applyAccent(e.target.value)}
                    style={{ width: 36, height: 36, border: 'none', borderRadius: 7,
                      cursor: 'pointer', padding: 0, background: 'none' }} />
                  <div>
                    <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>
                      {localAccent}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>Color personalizado</div>
                  </div>
                  {/* Preview */}
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
                    <div style={{ width: 28, height: 28, borderRadius: 6,
                      background: localAccent }} />
                    <div style={{ width: 28, height: 28, borderRadius: 6,
                      background: localAccent + '20', border: `1px solid ${localAccent}` }} />
                  </div>
                </div>
              </div>

              {/* Densidad */}
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  Densidad de la interfaz
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[
                    ['compact',     '▤ Compacta'],
                    ['normal',      '▥ Normal'],
                    ['comfortable', '▦ Confortable'],
                  ].map(([val, label]) => (
                    <button key={val} onClick={() => setLocalDensity(val)}
                      style={{ flex: 1, padding: '8px 4px', borderRadius: 8, fontSize: 11,
                        fontWeight: 600, border: `1px solid ${localDensity === val ? 'rgba(79,142,247,0.5)' : 'var(--surface-4)'}`,
                        background: localDensity === val ? 'var(--accent-muted)' : 'var(--surface-3)',
                        color: localDensity === val ? 'var(--accent)' : 'var(--text-2)',
                        cursor: 'pointer', fontFamily: 'inherit' }}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <button onClick={saveAppearance}
                style={{ padding: '10px', background: 'var(--accent)', border: 'none',
                  borderRadius: 8, color: '#fff', cursor: 'pointer',
                  fontSize: 13, fontFamily: 'inherit', fontWeight: 600 }}>
                ✓ Guardar apariencia
              </button>
            </div>
          )}

          {/* ── IDIOMA ───────────────────────────────────────────────────────── */}
          {tab === 'language' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ padding: '10px 14px', background: 'var(--accent-muted)',
                border: '1px solid rgba(79,142,247,0.25)', borderRadius: 8,
                fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5, marginBottom: 4 }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>Idioma activo: </span>
                {LANGUAGES.find(l => l.code === activeLang)?.flag} {LANGUAGES.find(l => l.code === activeLang)?.label}
                <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-3)' }}>
                  La navegación cambia al instante. El contenido de las páginas se traduce progresivamente.
                </div>
              </div>
              {LANGUAGES.map(lang => {
                const isActive = activeLang === lang.code
                return (
                  <button key={lang.code}
                    onClick={() => {
                      setLang(lang.code)
                      savePrefs({ language: lang.code })
                      toast.success(`Idioma cambiado a ${lang.label}`)
                    }}
                    style={{ display: 'flex', alignItems: 'center', gap: 14,
                      padding: '12px 16px', borderRadius: 10, textAlign: 'left',
                      background: isActive ? 'var(--accent-muted)' : 'var(--surface-3)',
                      border: `1px solid ${isActive ? 'rgba(79,142,247,0.5)' : 'var(--surface-4)'}`,
                      cursor: 'pointer', fontFamily: 'inherit', width: '100%',
                      transition: 'all .15s' }}>
                    <span style={{ fontSize: 24 }}>{lang.flag}</span>
                    <span style={{ fontSize: 13, fontWeight: 600,
                      color: isActive ? 'var(--accent)' : 'var(--text-1)', flex: 1 }}>
                      {lang.label}
                    </span>
                    {isActive && <span style={{ color: 'var(--accent)', fontSize: 14, fontWeight: 700 }}>✓</span>}
                  </button>
                )
              })}
            </div>
          )}

          {/* ── SEGURIDAD ────────────────────────────────────────────────────── */}
          {tab === 'security' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Info sesión */}
              <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                borderRadius: 8, fontSize: 12 }}>
                <div style={{ color: 'var(--text-2)', marginBottom: 6 }}>Sesión actual</div>
                <div style={{ color: 'var(--text-1)' }}>
                  Último acceso: {user?.last_login
                    ? new Date(user.last_login).toLocaleDateString('es-ES', {
                        day:'2-digit', month:'short', year:'numeric',
                        hour:'2-digit', minute:'2-digit' })
                    : 'No disponible'}
                </div>
                <div style={{ color: 'var(--text-2)', marginTop: 2 }}>
                  MFA: {user?.mfa_enabled ? '✅ Activado' : '⚠️ Desactivado'}
                </div>
              </div>

              {/* Cambio de contraseña */}
              {!user?.sso_provider && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                    Cambiar contraseña
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {[
                      ['current', 'Contraseña actual', 'Tu contraseña actual'],
                      ['new',     'Nueva contraseña',  'Mínimo 8 caracteres'],
                      ['confirm', 'Confirmar nueva',   'Repite la nueva contraseña'],
                    ].map(([key, label, ph]) => (
                      <div key={key}>
                        <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                          textTransform: 'uppercase', letterSpacing: '0.07em',
                          display: 'block', marginBottom: 4 }}>{label}</label>
                        <input type="password" value={pwForm[key]}
                          onChange={e => setPwForm(f => ({ ...f, [key]: e.target.value }))}
                          style={IS} placeholder={ph} />
                      </div>
                    ))}
                    {pwForm.new && pwForm.confirm && pwForm.new !== pwForm.confirm && (
                      <div style={{ fontSize: 11, color: 'var(--danger)' }}>
                        ✗ Las contraseñas no coinciden
                      </div>
                    )}
                    <button
                      disabled={changingPw || !pwForm.current || !pwForm.new ||
                        pwForm.new !== pwForm.confirm || pwForm.new.length < 8}
                      onClick={() => changePassword({
                        current_password: pwForm.current,
                        new_password: pwForm.new
                      })}
                      style={{ padding: '9px', background: 'var(--accent)', border: 'none',
                        borderRadius: 8, color: '#fff', fontSize: 12,
                        fontFamily: 'inherit', fontWeight: 600,
                        cursor: 'pointer', opacity: changingPw ? 0.7 : 1 }}>
                      {changingPw ? 'Cambiando...' : '🔐 Cambiar contraseña'}
                    </button>
                  </div>
                </div>
              )}

              {user?.sso_provider && (
                <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                  borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
                  Tu cuenta usa SSO ({user.sso_provider}). La contraseña se gestiona
                  desde tu proveedor de identidad corporativo.
                </div>
              )}

              {/* MFA */}
              <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                borderRadius: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Autenticación de dos factores (MFA)
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                  {user?.mfa_enabled
                    ? 'MFA activado. Tu cuenta está protegida con autenticación de doble factor.'
                    : 'MFA desactivado. Actívalo para mayor seguridad.'}
                </div>
                <button
                  onClick={() => window.location.href = '/mfa'}
                  style={{ padding: '7px 14px', background: user?.mfa_enabled ? 'var(--surface-4)' : 'var(--accent)',
                    border: 'none', borderRadius: 7, color: user?.mfa_enabled ? 'var(--text-2)' : '#fff',
                    fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                  {user?.mfa_enabled ? 'Gestionar MFA' : '🛡 Activar MFA'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
