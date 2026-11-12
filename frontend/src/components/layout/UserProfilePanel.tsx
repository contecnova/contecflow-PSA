/**
 * UserProfilePanel — Panel lateral de perfil de usuario
 * Se abre al hacer clic en el nombre/avatar en el footer del sidebar.
 * 
 * Secciones:
 * 1. Mi perfil (editar nombre, teléfono, cargo, avatar)
 * 2. Apariencia (tema: freight/dark/light/midnight/slate/high-contrast, acento, densidad)
 * 3. Idioma
 * 4. Seguridad (cambio de contraseña, MFA)
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { usersApi, authApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import useUserPreferences from '../../hooks/useUserPreferences'
import { useAppLang } from '../../i18n/AppLangContext'
import { Bell, Languages, Palette, ShieldCheck, UserRound } from 'lucide-react'
import { Avatar } from '../ui'
import PasskeysSection from '../security/PasskeysSection'
import { AVAILABLE_LANGUAGES } from '../../i18n/appTranslations'
import { applyAccent as applyAccentToDom } from '../../utils/appearance'
import { localeActivo } from '../../utils/helpers'

// ── Temas disponibles ─────────────────────────────────────────────────────────
const THEMES = [
  { id: 'freight',       label: 'Freight Pro',    icon: '🚚', desc: 'Estilo ERP industrial (principal)' },
  { id: 'dark',          label: 'Oscuro clásico', icon: '🌙', desc: 'Azul pizarra de Contecflow' },
  { id: 'midnight',      label: 'Midnight',        icon: '🌌', desc: 'Oscuro profundo, casi negro' },
  { id: 'slate',         label: 'Slate',           icon: '⬛', desc: 'Gris neutro estilo GitHub' },
  { id: 'light',         label: 'Claro',           icon: '☀️', desc: 'Fondo blanco, texto oscuro' },
  { id: 'high-contrast', label: 'Alto contraste',  icon: '◑',  desc: 'Máximo contraste, accesible' },
  { id: 'system',        label: 'Sistema',         icon: '💻', desc: 'Sigue la preferencia del SO' },
]

// Son DATOS, no estilo: se guardan como `accent_color` y applyAccent() sólo
// acepta #rrggbb. Con var() (lo que dejó el codemod de colores) el preset no
// hacía nada. Hex a propósito.
const ACCENT_PRESETS = [
  { label: 'Índigo',  color: '#4f8ef7' },
  { label: 'Violeta', color: '#a78bfa' },
  { label: 'Teal',    color: '#1d9e75' },
  { label: 'Azul',    color: '#60a5fa' },
  { label: 'Rosa',    color: '#f43f5e' },
  { label: 'Ámbar',   color: '#f59e0b' },
  { label: 'Verde',   color: '#34d399' },
  { label: 'Coral',   color: '#fb923c' },
]

// Auditoría 2026-08 (hallazgo 16): aquí había una lista de idiomas escrita a
// mano, distinta del registro de src/i18n. Dos fuentes de verdad para lo mismo:
// este panel ofrecía siete idiomas mientras el registro marcaba dos como
// ocultos, así que un usuario podía elegir uno que la aplicación no soportaba.
// Ahora sale del registro único.
const LANGUAGES = AVAILABLE_LANGUAGES

const IS: React.CSSProperties = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)",
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}

interface ProfileForm {
  email: string
  first_name: string
  last_name: string
  phone: string
  job_title: string
  avatar_url: string
}

interface PasswordForm {
  current: string
  new: string
  confirm: string
}

interface Props {
  onClose: () => void
}

export default function UserProfilePanel({ onClose }: Props) {
  const { t: traducir } = useAppLang()
  const { user, setUser } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const { prefs, save: savePrefs } = useUserPreferences()
  const { lang: activeLang, setLang } = useAppLang()

  const [tab, setTab] = useState<string>('profile')

  // ── Idioma (local pending antes de guardar) ─────────────────────────────────
  const [pendingLang, setPendingLang] = useState<string>(activeLang)

  // ── Perfil ──────────────────────────────────────────────────────────────────
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    email:      (user?.email      as string) || '',
    first_name: (user?.first_name as string) || '',
    last_name:  (user?.last_name  as string) || '',
    phone:      (user?.phone      as string) || '',
    job_title:  (user?.job_title  as string) || '',
    avatar_url: (user?.avatar_url as string) || '',
  })

  const { mutate: saveProfile, isPending: savingProfile } = useMutation({
    mutationFn: (data: ProfileForm) => usersApi.updateMe(data),
    onSuccess: (res: { data: unknown }) => {
      setUser(res.data as import('../../context/AuthContext').User)
      qc.invalidateQueries({ queryKey: ['auth-me'] })
      toast.success('Perfil actualizado')
    },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e?.response?.data?.detail || 'Error al guardar'),
  })

  // ── Apariencia ──────────────────────────────────────────────────────────────
  const [localTheme,   setLocalTheme]   = useState<string>(prefs?.theme_mode  || 'freight')
  // null: el acento del tema (cada tema trae el suyo)
  const [localAccent,  setLocalAccent]  = useState<string | null>(
    (prefs?.accent_color && /^#[0-9a-fA-F]{6}$/.test(prefs.accent_color)) ? prefs.accent_color : null
  )
  const [localDensity, setLocalDensity] = useState<string>(prefs?.ui_density  || 'normal')

  const applyTheme = (themeId: string) => {
    setLocalTheme(themeId)
    if (themeId === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    } else {
      document.documentElement.setAttribute('data-theme', themeId)
    }
  }

  const applyAccent = (color: string | null) => {
    setLocalAccent(color)
    applyAccentToDom(color)
  }

  const saveAppearance = () => {
    savePrefs({ theme_mode: localTheme, accent_color: localAccent, ui_density: localDensity })
    toast.success('Apariencia guardada')
  }

  // ── Contraseña ──────────────────────────────────────────────────────────────
  const [pwForm, setPwForm] = useState<PasswordForm>({ current: '', new: '', confirm: '' })
  const { mutate: changePassword, isPending: changingPw } = useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) => authApi.changePassword(data),
    onSuccess: () => { toast.success('Contraseña actualizada'); setPwForm({ current:'', new:'', confirm:'' }) },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e?.response?.data?.detail || 'Error al cambiar contraseña'),
  })

  // Cinco pestañas en 380 px: columnas iguales con el icono encima, para que
  // ninguna se salga del panel (antes «Avisos» quedaba fuera del borde).
  const TABS = [
    { id: 'profile',       label: traducir('perfilpanel.tab_perfil'),     Icono: UserRound },
    { id: 'appearance',    label: traducir('perfilpanel.tab_apariencia'), Icono: Palette },
    { id: 'language',      label: traducir('perfilpanel.tab_idioma'),     Icono: Languages },
    { id: 'security',      label: traducir('perfilpanel.tab_seguridad'),  Icono: ShieldCheck },
    { id: 'notifications', label: traducir('perfilpanel.tab_avisos'),     Icono: Bell },
  ]

  return (
    <>
      {/* Overlay */}
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          zIndex: 299, backdropFilter: 'blur(2px)' }} />

      {/* Panel */}
      <div style={{ position: 'fixed', bottom: 0, left: 0, width: 'min(380px, 100vw)', zIndex: 300,
        background: 'var(--surface-1)', borderRight: '1px solid var(--surface-4)',
        borderTop: '1px solid var(--surface-4)', borderRadius: '0 16px 0 0',
        display: 'flex', flexDirection: 'column',
        maxHeight: '90vh', boxShadow: '4px -4px 32px rgba(0,0,0,0.4)' }}>

        {/* Header del panel */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)',
          display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
          <Avatar name={user?.full_name ?? undefined} size={44} url={undefined} />
          <div className="u-flex1-min0">
            <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.full_name}
            </div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)',
              textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 1 }}>
              {user?.role} · {user?.department || 'Sin departamento'}
            </div>
          </div>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-3)',
              cursor: 'pointer', fontSize: "var(--text-xl)", padding: '0 4px' }}>✕</button>
        </div>

        {/* Tabs */}
        <div role="tablist" style={{ display: 'grid', gridTemplateColumns: `repeat(${TABS.length}, minmax(0, 1fr))`, gap: 4,
          padding: '8px 12px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          {TABS.map(({ id, label, Icono }) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} title={label}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, minWidth: 0,
                padding: '6px 4px', borderRadius: 8, fontSize: "var(--text-2xs)", fontWeight: 600,
                border: `1px solid ${tab === id ? 'var(--accent)' : 'transparent'}`,
                background: tab === id ? 'var(--accent-muted)' : 'transparent',
                color: tab === id ? 'var(--accent)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit' }}>
              <Icono size={16} aria-hidden />
              <span style={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
            </button>
          ))}
        </div>

        {/* Contenido */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

          {/* ── PERFIL ───────────────────────────────────────────────────────── */}
          {tab === 'profile' && (
            <div className="u-stack-14">
              {/* Info general */}
              <div style={{ padding: '10px 14px', background: 'var(--surface-3)',
                borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                <div>👤 Usuario: <strong className="u-text1">{user?.username}</strong></div>
                <div style={{ marginTop: 4 }}>📧 Email: <strong className="u-text1">{profileForm.email || user?.email}</strong></div>
                <div style={{ marginTop: 2, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                  {traducir('userprofile.los_cambios_se_aplican_al_mismo_recurso')}
                </div>
              </div>

              <div>
                <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>Email</label>
                <input value={profileForm.email}
                  onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))}
                  style={IS} type="email" placeholder="nombre@empresa.com" />
              </div>

              {/* Nombre */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    display: 'block', marginBottom: 4 }}>Nombre</label>
                  <input value={profileForm.first_name}
                    onChange={e => setProfileForm(f => ({ ...f, first_name: e.target.value }))}
                    style={IS} placeholder="Tu nombre" />
                </div>
                <div>
                  <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    display: 'block', marginBottom: 4 }}>Apellidos</label>
                  <input value={profileForm.last_name}
                    onChange={e => setProfileForm(f => ({ ...f, last_name: e.target.value }))}
                    style={IS} placeholder="Tus apellidos" />
                </div>
              </div>

              <div>
                <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>Cargo</label>
                <input value={profileForm.job_title}
                  onChange={e => setProfileForm(f => ({ ...f, job_title: e.target.value }))}
                  style={IS} placeholder="Ej: Senior Developer, Project Manager..." />
              </div>

              <div>
                <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>{traducir('userprofile.telefono')}</label>
                <input value={profileForm.phone}
                  onChange={e => setProfileForm(f => ({ ...f, phone: e.target.value }))}
                  style={IS} placeholder="+34 600 000 000" type="tel" />
              </div>

              <div>
                <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em',
                  display: 'block', marginBottom: 4 }}>{traducir('userprofile.url_de_avatar_opcional')}</label>
                <input value={profileForm.avatar_url}
                  onChange={e => setProfileForm(f => ({ ...f, avatar_url: e.target.value }))}
                  style={IS} placeholder="https://..." />
                {profileForm.avatar_url && (
                  <img src={profileForm.avatar_url} alt="preview"
                    loading="lazy" decoding="async"
                    style={{ width: 40, height: 40, borderRadius: '50%',
                      marginTop: 6, objectFit: 'cover',
                      border: '2px solid var(--surface-4)' }}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                )}
              </div>

              <button onClick={() => saveProfile(profileForm)} disabled={savingProfile}
                style={{ padding: '10px', background: 'var(--accent)', border: 'none',
                  borderRadius: 8, color: 'var(--on-accent-light)', cursor: savingProfile ? 'wait' : 'pointer',
                  fontSize: "var(--text-base)", fontFamily: 'inherit', fontWeight: 600,
                  opacity: savingProfile ? 0.7 : 1 }}>
                {savingProfile ? 'Guardando...' : '✓ Guardar perfil'}
              </button>
            </div>
          )}

          {tab === 'notifications' && <PreferenciasDeAviso />}

          {/* ── APARIENCIA ───────────────────────────────────────────────────── */}
          {tab === 'appearance' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Tema */}
              <div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  {traducir('userprofile.tema_de_color')}
                </div>
                <div className="u-stack-6">
                  {THEMES.map(t => (
                    <button key={t.id} onClick={() => applyTheme(t.id)}
                      style={{ display: 'flex', alignItems: 'center', gap: 12,
                        padding: '10px 14px', borderRadius: 9, textAlign: 'left',
                        background: localTheme === t.id ? 'var(--accent-muted)' : 'var(--surface-3)',
                        border: `1px solid ${localTheme === t.id ? 'rgba(79,142,247,0.5)' : 'var(--surface-4)'}`,
                        cursor: 'pointer', fontFamily: 'inherit', width: '100%' }}>
                      <span style={{ fontSize: "var(--text-xl)", flexShrink: 0 }}>{t.icon}</span>
                      <div className="u-flex1-min0">
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 600,
                          color: localTheme === t.id ? 'var(--accent)' : 'var(--text-1)' }}>
                          {t.label}
                        </div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 1 }}>
                          {t.desc}
                        </div>
                      </div>
                      {localTheme === t.id && (
                        <span style={{ color: 'var(--accent)', fontSize: "var(--text-md)" }}>✓</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Color de acento */}
              <div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  {traducir('userprofile.color_de_acento')}
                </div>
                <button onClick={() => applyAccent(null)} aria-pressed={localAccent === null}
                  style={{ marginBottom: 8, padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: "var(--text-sm)", border: '1px solid var(--surface-4)',
                    background: localAccent === null ? 'var(--accent-muted)' : 'var(--surface-3)',
                    color: localAccent === null ? 'var(--accent)' : 'var(--text-1)' }}>
                  {localAccent === null ? '✓ ' : ''}{traducir('userprofile.acento_del_tema')}
                </button>
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
                <div className="u-row-center-10">
                  <input type="color" value={localAccent ?? '#4f8ef7'} aria-label={traducir('userprofile.color_personalizado')}
                    onChange={e => applyAccent(e.target.value)}
                    style={{ width: 36, height: 36, border: 'none', borderRadius: 7,
                      cursor: 'pointer', padding: 0, background: 'none' }} />
                  <div>
                    <div style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>
                      {localAccent ?? traducir('userprofile.acento_del_tema')}
                    </div>
                    <div className="u-text3-2xs">Color personalizado</div>
                  </div>
                  {/* Preview */}
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
                    <div style={{ width: 28, height: 28, borderRadius: 6,
                      background: 'var(--accent)' }} />
                    <div style={{ width: 28, height: 28, borderRadius: 6,
                      background: 'var(--accent-muted)', border: '1px solid var(--accent)' }} />
                  </div>
                </div>
              </div>

              {/* Densidad */}
              <div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)',
                  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  {traducir('userprofile.densidad_de_la_interfaz')}
                </div>
                <div className="u-row-8">
                  {([
                    ['compact',     '▤ Compacta'],
                    ['normal',      '▥ Normal'],
                    ['comfortable', '▦ Confortable'],
                  ] as Array<[string, string]>).map(([val, label]) => (
                    <button key={val} onClick={() => setLocalDensity(val)}
                      style={{ flex: 1, padding: '8px 4px', borderRadius: 8, fontSize: "var(--text-xs)",
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
                  borderRadius: 8, color: 'var(--on-accent-light)', cursor: 'pointer',
                  fontSize: "var(--text-base)", fontFamily: 'inherit', fontWeight: 600 }}>
                ✓ Guardar apariencia
              </button>
            </div>
          )}

          {/* ── IDIOMA ───────────────────────────────────────────────────────── */}
          {tab === 'language' && (
            <div className="u-stack-8">
              <div style={{ padding: '10px 14px', background: 'var(--accent-muted)',
                border: '1px solid rgba(79,142,247,0.25)', borderRadius: 8,
                fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5, marginBottom: 4 }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>Idioma activo: </span>
                {LANGUAGES.find(l => l.code === activeLang)?.flag} {LANGUAGES.find(l => l.code === activeLang)?.label}
                <div className="u-hint">
                  {traducir('userprofile.la_navegacion_cambia_al_instante_el_contenido')}
                </div>
              </div>
              {LANGUAGES.map(lang => {
                const isPending = pendingLang === lang.code
                return (
                  <button key={lang.code}
                    onClick={() => setPendingLang(lang.code)}
                    style={{ display: 'flex', alignItems: 'center', gap: 14,
                      padding: '12px 16px', borderRadius: 10, textAlign: 'left',
                      background: isPending ? 'var(--accent-muted)' : 'var(--surface-3)',
                      border: `1px solid ${isPending ? 'rgba(79,142,247,0.5)' : 'var(--surface-4)'}`,
                      cursor: 'pointer', fontFamily: 'inherit', width: '100%',
                      transition: 'all .15s' }}>
                    <span style={{ fontSize: "var(--text-2xl)" }}>{lang.flag}</span>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 600,
                      color: isPending ? 'var(--accent)' : 'var(--text-1)', flex: 1 }}>
                      {lang.label}
                    </span>
                    {isPending && <span style={{ color: 'var(--accent)', fontSize: "var(--text-md)", fontWeight: 700 }}>✓</span>}
                  </button>
                )
              })}
              <button
                onClick={() => {
                  setLang(pendingLang)  // lo guarda en el servidor (Layout)
                  const label = LANGUAGES.find(l => l.code === pendingLang)?.label
                  toast.success(`Idioma cambiado a ${label}`)
                }}
                disabled={pendingLang === activeLang}
                style={{ padding: '10px', background: 'var(--accent)', border: 'none',
                  borderRadius: 8, color: 'var(--on-accent-light)', cursor: pendingLang === activeLang ? 'default' : 'pointer',
                  fontSize: "var(--text-base)", fontFamily: 'inherit', fontWeight: 600,
                  opacity: pendingLang === activeLang ? 0.5 : 1, marginTop: 4 }}>
                ✓ Guardar idioma
              </button>
            </div>
          )}

          {/* ── SEGURIDAD ────────────────────────────────────────────────────── */}
          {tab === 'security' && (
            <div className="u-stack-16">
              {/* Info sesión */}
              <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                borderRadius: 8, fontSize: "var(--text-sm)" }}>
                <div style={{ color: 'var(--text-2)', marginBottom: 6 }}>{traducir('userprofile.sesion_actual')}</div>
                <div className="u-text1">
                  {traducir('userprofile.ultimo_acceso')} {user?.last_login
                    ? new Date(user.last_login as string).toLocaleDateString(localeActivo(), {
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
                <div className="u-stack-8">
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>
                    {traducir('userprofile.cambiar_contrasena')}
                  </div>
                  {([
                    ['current', 'Contraseña actual', 'Tu contraseña actual'],
                    ['new',     'Nueva contraseña',  'Mínimo 8 caracteres'],
                    ['confirm', 'Confirmar nueva',   'Repite la nueva contraseña'],
                  ] as Array<[keyof PasswordForm, string, string]>).map(([key, label, ph]) => (
                    <div key={key}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)',
                        textTransform: 'uppercase', letterSpacing: '0.07em',
                        display: 'block', marginBottom: 4 }}>{label}</label>
                      <input type="password" value={pwForm[key]}
                        onChange={e => setPwForm(f => ({ ...f, [key]: e.target.value }))}
                        style={IS} placeholder={ph} />
                    </div>
                  ))}
                  {pwForm.new && pwForm.confirm && pwForm.new !== pwForm.confirm && (
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--danger)' }}>
                      {traducir('userprofile.las_contrasenas_no_coinciden')}
                    </div>
                  )}
                </div>
              )}

              {Boolean(user?.sso_provider) && (
                <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                  borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  Tu cuenta usa SSO ({String(user?.sso_provider)}{traducir('userprofile.la_contrasena_se_gestiona_desde_tu_proveedor')}
                </div>
              )}

              {/* MFA */}
              <div style={{ padding: '12px 14px', background: 'var(--surface-3)',
                borderRadius: 8 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 4 }}>
                  {traducir('userprofile.autenticacion_de_dos_factores_mfa')}
                </div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                  {user?.mfa_enabled
                    ? 'MFA activado. Tu cuenta está protegida con autenticación de doble factor.'
                    : 'MFA desactivado. Actívalo para mayor seguridad.'}
                </div>
                <button
                  onClick={() => window.location.href = '/mfa'}
                  style={{ padding: '7px 14px', background: user?.mfa_enabled ? 'var(--surface-4)' : 'var(--accent)',
                    border: 'none', borderRadius: 7, color: user?.mfa_enabled ? 'var(--text-2)' : '#fff',
                    fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                  {user?.mfa_enabled ? 'Gestionar MFA' : '🛡 Activar MFA'}
                </button>
              </div>

              <PasskeysSection />

              {!user?.sso_provider && (
                <button
                  disabled={changingPw || !pwForm.current || !pwForm.new ||
                    pwForm.new !== pwForm.confirm || pwForm.new.length < 8}
                  onClick={() => changePassword({
                    current_password: pwForm.current,
                    new_password: pwForm.new,
                  })}
                  style={{ padding: '10px', background: 'var(--accent)', border: 'none',
                    borderRadius: 8, color: 'var(--on-accent-light)', fontSize: "var(--text-base)",
                    fontFamily: 'inherit', fontWeight: 600,
                    cursor: changingPw || !pwForm.current || !pwForm.new ||
                      pwForm.new !== pwForm.confirm || pwForm.new.length < 8 ? 'default' : 'pointer',
                    opacity: changingPw || !pwForm.current || !pwForm.new ||
                      pwForm.new !== pwForm.confirm || pwForm.new.length < 8 ? 0.5 : 1 }}>
                  {changingPw ? 'Guardando...' : '✓ Guardar seguridad'}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}


// Revisión 2026-11: qué avisos quiere cada uno y por qué canal.
const NOMBRE_DEL_AVISO: Record<string, string> = {
  task_assigned: 'Me asignan una tarea', task_mentioned: 'Me mencionan en una tarea', task_due_soon: 'Tarea a punto de vencer',
  task_overdue: 'Tarea vencida', sprint_started: 'Empieza un sprint', sprint_ending: 'Acaba un sprint',
  expense_approved: 'Gasto aprobado', expense_rejected: 'Gasto rechazado', ticket_assigned: 'Me asignan un ticket',
  ticket_replied: 'Respuesta en un ticket', ticket_resolved: 'Ticket resuelto', ticket_created: 'Ticket nuevo',
  ticket_updated: 'Ticket actualizado', ticket_sla_warning: 'SLA en riesgo', ticket_sla_breached: 'SLA incumplido',
  ticket_escalated: 'Ticket escalado', approval_requested: 'Aprobación pendiente', project_risk_high: 'Riesgo alto en un proyecto',
  timesheet_reminder: 'Recordatorio de horas', timesheet_approved: 'Horas aprobadas', budget_warning: 'Aviso de presupuesto',
  mention: 'Menciones', automation: 'Automatizaciones', system: 'Sistema',
}

function PreferenciasDeAviso() {
  const toast = useToast()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const { data } = useQuery<{ types: { type: string; channels: string[] }[]; preferences: Record<string, Record<string, boolean>>; digest?: boolean }>({
    queryKey: ['notification-preferences'],
    queryFn: () => api.get('/users/me/notification-preferences').then(r => r.data),
  })
  const [prefs, setPrefs] = useState<Record<string, Record<string, boolean>> | null>(null)
  const [resumen, setResumen] = useState<boolean | null>(null)
  const actuales = prefs ?? data?.preferences ?? {}
  const resumenActual = resumen ?? !!data?.digest
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => api.put('/users/me/notification-preferences', { preferences: actuales, digest: resumenActual }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notification-preferences'] }); setPrefs(null); setResumen(null); toast.success('Guardado') },
    onError: () => toast.error('No se pudo guardar'),
  })
  const cambiar = (tipo: string, canal: string, v: boolean) =>
    setPrefs({ ...actuales, [tipo]: { ...(actuales[tipo] || {}), [canal]: v } })
  return (
    <div className="u-stack-6">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 70px 70px', fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontWeight: 700 }}>
        <span>Aviso</span><span style={{ textAlign: 'center' }}>App</span><span style={{ textAlign: 'center' }}>Correo</span>
      </div>
      {(data?.types || []).map(t => (
        <div key={t.type} style={{ display: 'grid', gridTemplateColumns: '1fr 70px 70px', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
          <span>{NOMBRE_DEL_AVISO[t.type] || t.type}</span>
          {['app', 'email'].map(c => (
            <span key={c} style={{ textAlign: 'center' }}>
              {t.channels.includes(c) ? (
                <input type="checkbox" aria-label={`${NOMBRE_DEL_AVISO[t.type] || t.type} por ${c === 'app' ? 'la aplicación' : 'correo'}`}
                  checked={actuales[t.type]?.[c] ?? true} onChange={e => cambiar(t.type, c, e.target.checked)} />
              ) : <span style={{ color: 'var(--text-4)' }}>—</span>}
            </span>
          ))}
        </div>
      ))}
      <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, fontSize: 'var(--text-sm)' }}>
        <input type="checkbox" checked={resumenActual} onChange={e => setResumen(e.target.checked)} />
        {traducir('userprofile.resumen_diario')}
      </label>
      <div style={{ marginTop: 10 }}>
        <button type="button" disabled={isPending || (prefs === null && resumen === null)} onClick={() => guardar()}
          style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', opacity: prefs === null && resumen === null ? 0.6 : 1 }}>
          {isPending ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </div>
  )
}
