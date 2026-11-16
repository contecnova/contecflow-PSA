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
import { PRODUCT_NAME } from '../../constants/brand'
import React, { type CSSProperties, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api, { usersApi, authApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import useUserPreferences from '../../hooks/useUserPreferences'
import { useAppLang } from '../../i18n/AppLangContext'
import { Bell, Languages, Palette, ShieldCheck, UserRound } from 'lucide-react'
import { Avatar } from '../ui'
import { Drawer } from '../ui/Drawer'
import { useTabListKeys } from '../ui/Tabs'
import PasskeysSection from '../security/PasskeysSection'
import { AVAILABLE_LANGUAGES } from '../../i18n/appTranslations'
import { applyAccent as applyAccentToDom } from '../../utils/appearance'
import { localeActivo } from '../../utils/helpers'
import './UserProfilePanel.css'

// ── Temas disponibles ─────────────────────────────────────────────────────────
// Nombre y descripción: userprofilepanel.tema_<clave> y tema_<clave>_desc.
const THEMES = [
  { id: 'freight',       clave: 'freight',       icon: '🚚' },
  { id: 'dark',          clave: 'dark',          icon: '🌙' },
  { id: 'midnight',      clave: 'midnight',      icon: '🌌' },
  { id: 'slate',         clave: 'slate',         icon: '⬛' },
  { id: 'light',         clave: 'light',         icon: '☀️' },
  { id: 'high-contrast', clave: 'high_contrast', icon: '◑' },
  { id: 'system',        clave: 'system',        icon: '💻' },
]

// Son DATOS, no estilo: se guardan como `accent_color` y applyAccent() sólo
// acepta #rrggbb. Con var() (lo que dejó el codemod de colores) el preset no
// hacía nada. Hex a propósito.
// Nombre: userprofilepanel.acento_<clave>.
const ACCENT_PRESETS = [
  { clave: 'indigo',  color: '#4f8ef7' },
  { clave: 'violeta', color: '#a78bfa' },
  { clave: 'teal',    color: '#1d9e75' },
  { clave: 'azul',    color: '#60a5fa' },
  { clave: 'rosa',    color: '#f43f5e' },
  { clave: 'ambar',   color: '#f59e0b' },
  { clave: 'verde',   color: '#34d399' },
  { clave: 'coral',   color: '#fb923c' },
]

// Auditoría 2026-08 (hallazgo 16): aquí había una lista de idiomas escrita a
// mano, distinta del registro de src/i18n. Dos fuentes de verdad para lo mismo:
// este panel ofrecía siete idiomas mientras el registro marcaba dos como
// ocultos, así que un usuario podía elegir uno que la aplicación no soportaba.
// Ahora sale del registro único.
const LANGUAGES = AVAILABLE_LANGUAGES


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
  const idCampo = React.useId()
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
      toast.success(traducir('userprofilepanel.perfil_actualizado'))
    },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e?.response?.data?.detail || traducir('userprofilepanel.error_guardar')),
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
    toast.success(traducir('userprofilepanel.apariencia_guardada'))
  }

  // ── Contraseña ──────────────────────────────────────────────────────────────
  const [pwForm, setPwForm] = useState<PasswordForm>({ current: '', new: '', confirm: '' })
  const { mutate: changePassword, isPending: changingPw } = useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) => authApi.changePassword(data),
    onSuccess: () => { toast.success(traducir('userprofilepanel.contrasena_actualizada')); setPwForm({ current:'', new:'', confirm:'' }) },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => toast.error(e?.response?.data?.detail || traducir('userprofilepanel.error_contrasena')),
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

  const teclasTabs = useTabListKeys(TABS.map(x => x.id), tab, setTab)

  return (
    <>
      {/* Auditoria 2026-11 (#41): overlay y panel hechos a mano, sin trampa de
          foco ni Esc -> Drawer del kit, anclado abajo a la izquierda como antes. */}
      <Drawer onClose={onClose} ariaLabel={traducir('perfilpanel.tab_perfil')} width="min(380px, 100vw)"
        backdrop="var(--overlay-scrim)"
        className="user-profile-panel-e1">

        {/* Header del panel */}
        <div className="usprpa-row-1">
          <Avatar name={user?.full_name ?? undefined} size={44} url={undefined} />
          <div className="u-flex1-min0">
            <div className="usprpa-box-1">
              {user?.full_name}
            </div>
            <div className="usprpa-box-2">
              {user?.role} · {user?.department || traducir('userprofilepanel.sin_departamento')}
            </div>
          </div>
          <button type="button" aria-label={traducir('common.close')} onClick={onClose}
            className="usprpa-box-3">✕</button>
        </div>

        {/* Tabs */}
        <div className="usprpa-grid-4 user-profile-panel-e2" role="tablist" ref={teclasTabs.listRef} onKeyDown={teclasTabs.onKeyDown} aria-label={traducir('perfilpanel.tab_perfil')} style={{ '--user-profile-panel-grid-template-columns': `repeat(${TABS.length}, minmax(0, 1fr))` } as CSSProperties}>
          {TABS.map(({ id, label, Icono }) => (
            <button className={`usprpa-stack-1 userprof-sx1 user-profile-panel-e3 ${tab === id ? 'user-profile-panel-m4' : 'user-profile-panel-m5'}`} key={id} type="button" role="tab" data-tab-id={id} aria-selected={tab === id} tabIndex={teclasTabs.focusId === id ? 0 : -1} onClick={() => setTab(id)} title={label}
              style={{ '--user-profile-panel-border': `1px solid ${tab === id ? 'var(--accent)' : 'transparent'}` } as CSSProperties}>
              <Icono size={16} aria-hidden />
              <span className="usprpa-box-4">{label}</span>
            </button>
          ))}
        </div>

        {/* Contenido */}
        <div className="usprpa-box-5">

          {/* ── PERFIL ───────────────────────────────────────────────────────── */}
          {tab === 'profile' && (
            <div className="u-stack-14">
              {/* Info general */}
              <div className="usprpa-box-6">
                <div>👤 {traducir('userprofilepanel.usuario')} <strong className="u-text1">{user?.username}</strong></div>
                <div className="usprpa-sp-1">📧 {traducir('userprofilepanel.email_dos_puntos')} <strong className="u-text1">{profileForm.email || user?.email}</strong></div>
                <div className="u-text3-xs-mt2">
                  {traducir('userprofile.los_cambios_se_aplican_al_mismo_recurso')}
                </div>
              </div>

              <div>
                <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="usprpa-box-7">{traducir('userprofilepanel.email')}</label>
                <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={profileForm.email}
                  onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))}
                  className="usprpa-is" type="email" placeholder={traducir('userprofilepanel.ph_email')} />
              </div>

              {/* Nombre */}
              <div className="u-grid2-10">
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="usprpa-box-7">{traducir('userprofilepanel.nombre')}</label>
                  <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={profileForm.first_name}
                    onChange={e => setProfileForm(f => ({ ...f, first_name: e.target.value }))}
                    className="usprpa-is" placeholder={traducir('userprofilepanel.ph_nombre')} />
                </div>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="usprpa-box-7">{traducir('userprofilepanel.apellidos')}</label>
                  <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={profileForm.last_name}
                    onChange={e => setProfileForm(f => ({ ...f, last_name: e.target.value }))}
                    className="usprpa-is" placeholder={traducir('userprofilepanel.ph_apellidos')} />
                </div>
              </div>

              <div>
                <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="usprpa-box-7">{traducir('userprofilepanel.cargo')}</label>
                <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={profileForm.job_title}
                  onChange={e => setProfileForm(f => ({ ...f, job_title: e.target.value }))}
                  className="usprpa-is" placeholder={traducir('userprofilepanel.ph_cargo')} />
              </div>

              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="usprpa-box-7">{traducir('userprofile.telefono')}</label>
                <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={profileForm.phone}
                  onChange={e => setProfileForm(f => ({ ...f, phone: e.target.value }))}
                  className="usprpa-is" placeholder="+34 600 000 000" type="tel" />
              </div>

              <div>
                <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="usprpa-box-7">{traducir('userprofile.url_de_avatar_opcional')}</label>
                <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={profileForm.avatar_url}
                  onChange={e => setProfileForm(f => ({ ...f, avatar_url: e.target.value }))}
                  className="usprpa-is" placeholder="https://..." />
                {profileForm.avatar_url && (
                  <img src={profileForm.avatar_url} alt="preview"
                    loading="lazy" decoding="async"
                    className="usprpa-box-8"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                )}
              </div>

              <button type="button" className={`usprpa-box-25 ${savingProfile ? 'user-profile-panel-m6' : 'user-profile-panel-m7'}`} onClick={() => saveProfile(profileForm)} disabled={savingProfile}>
                {savingProfile ? traducir('userprofilepanel.guardando') : `✓ ${traducir('userprofilepanel.guardar_perfil')}`}
              </button>
            </div>
          )}

          {tab === 'notifications' && <PreferenciasDeAviso />}

          {/* ── APARIENCIA ───────────────────────────────────────────────────── */}
          {tab === 'appearance' && (
            <div className="u-stack-20">

              {/* Tema */}
              <div>
                <div className="usprpa-box-9">
                  {traducir('userprofile.tema_de_color')}
                </div>
                <div className="u-stack-6">
                  {THEMES.map(t => (
                    <button type="button" aria-pressed={localTheme === t.id} className={`usprpa-row-4 userprof-sx2 user-profile-panel-e3 ${localTheme === t.id ? 'user-profile-panel-m8' : 'user-profile-panel-m9'}`} key={t.id} onClick={() => applyTheme(t.id)}
                      style={{ '--user-profile-panel-border': `1px solid ${localTheme === t.id ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                      <span className="usprpa-box-10">{t.icon}</span>
                      <div className="u-flex1-min0">
                        <div className={`usprpa-txt-9 ${localTheme === t.id ? 'user-profile-panel-m10' : 'user-profile-panel-m11'}`}>
                          {traducir(`userprofilepanel.tema_${t.clave}`)}
                        </div>
                        <div className="usprpa-box-11">
                          {traducir(`userprofilepanel.tema_${t.clave}_desc`, { producto: PRODUCT_NAME })}
                        </div>
                      </div>
                      {localTheme === t.id && (
                        <span className="usprpa-txt-1">✓</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Color de acento */}
              <div>
                <div className="usprpa-box-9">
                  {traducir('userprofile.color_de_acento')}
                </div>
                <button className={`usprpa-box-26 ${localAccent === null ? 'user-profile-panel-m4' : 'user-profile-panel-m12'}`} onClick={() => applyAccent(null)} aria-pressed={localAccent === null}>
                  {localAccent === null ? '✓ ' : ''}{traducir('userprofile.acento_del_tema')}
                </button>
                <div className="usprpa-grid-1">
                  {ACCENT_PRESETS.map(p => (
                    <button type="button" aria-pressed={localAccent === p.color} className={`usprpa-box-27 user-profile-panel-e13 ${localAccent === p.color ? 'user-profile-panel-m14' : 'user-profile-panel-m15'}`} aria-label={traducir(`userprofilepanel.acento_${p.clave}`)} key={p.color} onClick={() => applyAccent(p.color)}
                      title={traducir(`userprofilepanel.acento_${p.clave}`)}
                      style={{ '--user-profile-panel-background': p.color, '--user-profile-panel-outline': localAccent === p.color ? `3px solid ${p.color}` : 'none' } as CSSProperties} />
                  ))}
                </div>
                <div className="u-row-center-10">
                  <input type="color" value={localAccent ?? '#4f8ef7'} aria-label={traducir('userprofile.color_personalizado')}
                    onChange={e => applyAccent(e.target.value)}
                    className="usprpa-box-12" />
                  <div>
                    <div className="usprpa-txt-2">
                      {localAccent ?? traducir('userprofile.acento_del_tema')}
                    </div>
                    <div className="u-text3-2xs">{traducir('userprofile.color_personalizado')}</div>
                  </div>
                  {/* Preview */}
                  <div className="usprpa-row-2">
                    <div className="usprpa-box-13" />
                    <div className="usprpa-box-14" />
                  </div>
                </div>
              </div>

              {/* Densidad */}
              <div>
                <div className="usprpa-box-9">
                  {traducir('userprofile.densidad_de_la_interfaz')}
                </div>
                <div className="u-row-8">
                  {([
                    ['compact',     '▤ Compacta'],
                    ['normal',      '▥ Normal'],
                    ['comfortable', '▦ Confortable'],
                  ] as Array<[string, string]>).map(([val, label]) => (
                    <button className={`usprpa-box-28 userprof-sx1 user-profile-panel-e3 ${localDensity === val ? 'user-profile-panel-m4' : 'user-profile-panel-m16'}`} key={val} onClick={() => setLocalDensity(val)}
                      style={{ '--user-profile-panel-border': `1px solid ${localDensity === val ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <button type="button" onClick={saveAppearance}
                className="usprpa-box-15">
                ✓ {traducir('userprofilepanel.guardar_apariencia')}
              </button>
            </div>
          )}

          {/* ── IDIOMA ───────────────────────────────────────────────────────── */}
          {tab === 'language' && (
            <div className="u-stack-8">
              <div className="usprpa-box-16">
                <span className="usprpa-txt-3">{traducir('userprofilepanel.idioma_activo')} </span>
                {LANGUAGES.find(l => l.code === activeLang)?.label}
                <div className="u-hint">
                  {traducir('userprofile.la_navegacion_cambia_al_instante_el_contenido')}
                </div>
              </div>
              {LANGUAGES.map(lang => {
                const isPending = pendingLang === lang.code
                return (
                  <button type="button" aria-pressed={isPending} className={`usprpa-row-5 userprof-sx3 user-profile-panel-e3 ${isPending ? 'user-profile-panel-m8' : 'user-profile-panel-m9'}`} key={lang.code}
                    onClick={() => setPendingLang(lang.code)}
                    style={{ '--user-profile-panel-border': `1px solid ${isPending ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    <span className="usprpa-txt-4">{lang.code.toUpperCase()}</span>
                    <span className={`usprpa-box-29 ${isPending ? 'user-profile-panel-m10' : 'user-profile-panel-m11'}`}>
                      {lang.label}
                    </span>
                    {isPending && <span className="usprpa-txt-5">✓</span>}
                  </button>
                )
              })}
              <button type="button" className={`usprpa-box-30 ${pendingLang === activeLang ? 'user-profile-panel-m17' : 'user-profile-panel-m7'}`}
                onClick={() => {
                  setLang(pendingLang)  // lo guarda en el servidor (Layout)
                  const label = LANGUAGES.find(l => l.code === pendingLang)?.label
                  toast.success(traducir('userprofilepanel.idioma_cambiado', { idioma: label ?? pendingLang }))
                }}
                disabled={pendingLang === activeLang}>
                ✓ {traducir('userprofilepanel.guardar_idioma')}
              </button>
            </div>
          )}

          {/* ── SEGURIDAD ────────────────────────────────────────────────────── */}
          {tab === 'security' && (
            <div className="u-stack-16">
              {/* Info sesión */}
              <div className="usprpa-box-17">
                <div className="usprpa-box-18">{traducir('userprofile.sesion_actual')}</div>
                <div className="u-text1">
                  {traducir('userprofile.ultimo_acceso')} {user?.last_login
                    ? new Date(user.last_login as string).toLocaleDateString(localeActivo(), {
                        day:'2-digit', month:'short', year:'numeric',
                        hour:'2-digit', minute:'2-digit' })
                    : 'No disponible'}
                </div>
                <div className="usprpa-box-19">
                  MFA: {user?.mfa_enabled ? '✅ Activado' : '⚠️ Desactivado'}
                </div>
              </div>

              {/* Cambio de contraseña */}
              {!user?.sso_provider && (
                <div className="u-stack-8">
                  <div className="usprpa-box-20">
                    {traducir('userprofile.cambiar_contrasena')}
                  </div>
                  {([
                    ['current', traducir('userprofilepanel.pwd_actual'), traducir('userprofilepanel.ph_pwd_actual')],
                    ['new',     traducir('userprofilepanel.pwd_nueva'),  traducir('userprofilepanel.ph_pwd_nueva')],
                    ['confirm', traducir('userprofilepanel.pwd_confirmar'),   traducir('userprofilepanel.ph_pwd_confirmar')],
                  ] as Array<[keyof PasswordForm, string, string]>).map(([key, label, ph]) => (
                    <div key={key}>
                      <label id={`${idCampo}-pw-${key}-et`} htmlFor={`${idCampo}-pw-${key}`} className="usprpa-box-7">{label}</label>
                      <input id={`${idCampo}-pw-${key}`} aria-labelledby={`${idCampo}-pw-${key}-et`} type="password" value={pwForm[key]}
                        onChange={e => setPwForm(f => ({ ...f, [key]: e.target.value }))}
                        className="usprpa-is" placeholder={ph} />
                    </div>
                  ))}
                  {pwForm.new && pwForm.confirm && pwForm.new !== pwForm.confirm && (
                    <div className="usprpa-txt-6">
                      {traducir('userprofile.las_contrasenas_no_coinciden')}
                    </div>
                  )}
                </div>
              )}

              {Boolean(user?.sso_provider) && (
                <div className="usprpa-box-21">
                  {traducir('userprofilepanel.cuenta_sso', { proveedor: String(user?.sso_provider) })}{traducir('userprofile.la_contrasena_se_gestiona_desde_tu_proveedor')}
                </div>
              )}

              {/* MFA */}
              <div className="usprpa-box-22">
                <div className="usprpa-box-23">
                  {traducir('userprofile.autenticacion_de_dos_factores_mfa')}
                </div>
                <div className="usprpa-box-24">
                  {user?.mfa_enabled
                    ? traducir('userprofilepanel.mfa_activado')
                    : traducir('userprofilepanel.mfa_desactivado')}
                </div>
                <button type="button" className={`usprpa-box-31 ${user?.mfa_enabled ? 'user-profile-panel-m18' : 'user-profile-panel-m19'}`}
                  onClick={() => window.location.href = '/mfa'}>
                  {user?.mfa_enabled ? traducir('userprofilepanel.gestionar_mfa') : `🛡 ${traducir('userprofilepanel.activar_mfa')}`}
                </button>
              </div>

              <PasskeysSection />

              {!user?.sso_provider && (
                <button className={`usprpa-box-25 ${changingPw || !pwForm.current || !pwForm.new ||
                      pwForm.new !== pwForm.confirm || pwForm.new.length < 8 ? 'user-profile-panel-m17' : 'user-profile-panel-m7'}`}
                  disabled={changingPw || !pwForm.current || !pwForm.new ||
                    pwForm.new !== pwForm.confirm || pwForm.new.length < 8}
                  onClick={() => changePassword({
                    current_password: pwForm.current,
                    new_password: pwForm.new,
                  })}>
                  {changingPw ? traducir('userprofilepanel.guardando') : `✓ ${traducir('userprofilepanel.guardar_seguridad')}`}
                </button>
              )}
            </div>
          )}
        </div>
      </Drawer>
    </>
  )
}


// Revisión 2026-11: qué avisos quiere cada uno y por qué canal.
// Nombre de cada tipo: userprofilepanel.aviso_<tipo>; si el servidor manda uno nuevo, se ve su código.
const TIPOS_DE_AVISO = new Set(["task_assigned","task_mentioned","task_due_soon","task_overdue","sprint_started","sprint_ending","expense_approved","expense_rejected","ticket_assigned","ticket_replied","ticket_resolved","ticket_created","ticket_updated","ticket_sla_warning","ticket_sla_breached","ticket_escalated","approval_requested","project_risk_high","timesheet_reminder","timesheet_approved","budget_warning","mention","automation","system"])

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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notification-preferences'] }); setPrefs(null); setResumen(null); toast.success(traducir('userprofilepanel.guardado')) },
    onError: () => toast.error(traducir('userprofilepanel.no_se_pudo_guardar')),
  })
  const nombreDelAviso = (tipo: string) => TIPOS_DE_AVISO.has(tipo) ? traducir(`userprofilepanel.aviso_${tipo}`) : tipo
  const cambiar = (tipo: string, canal: string, v: boolean) =>
    setPrefs({ ...actuales, [tipo]: { ...(actuales[tipo] || {}), [canal]: v } })
  return (
    <div className="u-stack-6">
      <div className="usprpa-grid-2">
        <span>{traducir('userprofilepanel.col_aviso')}</span><span className="usprpa-txt-7">{traducir('userprofilepanel.col_app')}</span><span className="usprpa-txt-7">{traducir('userprofilepanel.col_correo')}</span>
      </div>
      {(data?.types || []).map(t => (
        <div key={t.type} className="usprpa-grid-3">
          <span>{nombreDelAviso(t.type)}</span>
          {['app', 'email'].map(c => (
            <span key={c} className="usprpa-txt-7">
              {t.channels.includes(c) ? (
                <input type="checkbox" aria-label={traducir(c === 'app' ? 'userprofilepanel.aviso_por_app' : 'userprofilepanel.aviso_por_correo', { aviso: nombreDelAviso(t.type) })}
                  checked={actuales[t.type]?.[c] ?? true} onChange={e => cambiar(t.type, c, e.target.checked)} />
              ) : <span className="usprpa-txt-8">—</span>}
            </span>
          ))}
        </div>
      ))}
      <label className="usprpa-row-3">
        <input type="checkbox" aria-label={traducir('userprofile.resumen_diario')} checked={resumenActual} onChange={e => setResumen(e.target.checked)} />
        {traducir('userprofile.resumen_diario')}
      </label>
      <div className="usprpa-sp-2">
        <button className={`usprpa-box-32 ${prefs === null && resumen === null ? 'user-profile-panel-m20' : 'user-profile-panel-m21'}`} type="button" disabled={isPending || (prefs === null && resumen === null)} onClick={() => guardar()}>
          {isPending ? traducir('userprofilepanel.guardando') : traducir('common.save')}
        </button>
      </div>
    </div>
  )
}
