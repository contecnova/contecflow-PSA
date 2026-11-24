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
import { useNavigate } from 'react-router-dom'
import React, { type CSSProperties, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { usersApi, authApi, preferenciasDeAvisosApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import useUserPreferences from '../../hooks/useUserPreferences'
import { useAppLang } from '../../i18n/AppLangContext'
import { Bell, Languages, Palette, ShieldCheck, SlidersHorizontal, UserRound } from 'lucide-react'
import { Avatar, Button, Checkbox, IconButton, Pulsable, useErroresDeCampo, Input, cambiosGuardados } from '../ui'
import { EVENTO_PERSONALIZAR_MENU } from './menuLateral'
import { Drawer } from '../ui/Drawer'
import { useTabListKeys } from '../ui/Tabs'
import PasskeysSection from '../security/PasskeysSection'
import { AVAILABLE_LANGUAGES } from '../../i18n/appTranslations'
import { applyAccent as applyAccentToDom } from '../../utils/appearance'
import { localeActivo } from '../../utils/helpers'
import { ACENTO_POR_DEFECTO, PALETA_DE_ACENTO } from '../../constants/theme'
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

// 23-11-2026 (M14): la paleta de acentos vive en constants/theme.ts (datos hex).
const ACCENT_PRESETS = PALETA_DE_ACENTO

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
  // 23-11-2026 (M7 del 04): sin recarga y directo a la ruta final (antes /mfa → /settings/mfa).
  const navigate = useNavigate()
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

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate: saveProfile, isPending: savingProfile } = useMutation({
    mutationFn: (data: ProfileForm) => usersApi.updateMe(data),
    onMutate: () => campos.limpiar(),
    onSuccess: (res: { data: unknown }) => {
      setUser(res.data as import('../../context/AuthContext').User)
      qc.invalidateQueries({ queryKey: ['auth-me'] })
      toast.success(traducir('userprofilepanel.perfil_actualizado'))
      // Guardado sin cerrar el panel: ya no hay cambios que avisar (kit, 23-11-2026).
      cambiosGuardados()
    },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => { if (!campos.recoger(e)) toast.error(e?.response?.data?.detail || traducir('userprofilepanel.error_guardar')) },
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
    cambiosGuardados()
  }

  // ── Contraseña ──────────────────────────────────────────────────────────────
  const [pwForm, setPwForm] = useState<PasswordForm>({ current: '', new: '', confirm: '' })
  const camposPw = useErroresDeCampo()
  const msgPw = (k: string) => camposPw.de(k) ? <div className="u-field-error">{camposPw.de(k)}</div> : null
  const { mutate: changePassword, isPending: changingPw } = useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) => authApi.changePassword(data),
    onMutate: () => camposPw.limpiar(),
    onSuccess: () => { toast.success(traducir('userprofilepanel.contrasena_actualizada')); setPwForm({ current:'', new:'', confirm:'' }); cambiosGuardados() },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } } }) => { if (!camposPw.recoger(e)) toast.error(e?.response?.data?.detail || traducir('userprofilepanel.error_contrasena')) },
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
          <Pulsable aria-label={traducir('common.close')} onClick={onClose} className="usprpa-box-3" data-cierra-dialogo="">✕</Pulsable>
        </div>

        {/* Tabs */}
        <div className="usprpa-grid-4 user-profile-panel-e2" role="tablist" ref={teclasTabs.listRef} onKeyDown={teclasTabs.onKeyDown} aria-label={traducir('perfilpanel.tab_perfil')} style={{ '--user-profile-panel-grid-template-columns': `repeat(${TABS.length}, minmax(0, 1fr))` } as CSSProperties}>
          {TABS.map(({ id, label, Icono }) => (
            <IconButton ariaLabel={label} className={`usprpa-stack-1 userprof-sx1 user-profile-panel-e3 ${tab === id ? 'user-profile-panel-m4' : 'user-profile-panel-m5'}`} key={id} role="tab" data-tab-id={id} aria-selected={tab === id} tabIndex={teclasTabs.focusId === id ? 0 : -1} onClick={() => setTab(id)} title={label}
              style={{ '--user-profile-panel-border': `1px solid ${tab === id ? 'var(--accent)' : 'transparent'}` } as CSSProperties}>
              <Icono size={16} aria-hidden />
              <span className="usprpa-box-4">{label}</span>
            </IconButton>
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
                <Input label={traducir('userprofilepanel.email')} id={`${idCampo}-1`} value={profileForm.email} onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))} type="email" placeholder={traducir('userprofilepanel.ph_email')} />{msg('email')}
              </div>

              {/* Nombre */}
              <div className="u-grid2-10">
                <div>
                  <Input label={traducir('userprofilepanel.nombre')} id={`${idCampo}-2`} value={profileForm.first_name} onChange={e => setProfileForm(f => ({ ...f, first_name: e.target.value }))} placeholder={traducir('userprofilepanel.ph_nombre')} />{msg('first_name')}
                </div>
                <div>
                  <Input label={traducir('userprofilepanel.apellidos')} id={`${idCampo}-3`} value={profileForm.last_name} onChange={e => setProfileForm(f => ({ ...f, last_name: e.target.value }))} placeholder={traducir('userprofilepanel.ph_apellidos')} />{msg('last_name')}
                </div>
              </div>

              <div>
                <Input label={traducir('userprofilepanel.cargo')} id={`${idCampo}-4`} value={profileForm.job_title} onChange={e => setProfileForm(f => ({ ...f, job_title: e.target.value }))} placeholder={traducir('userprofilepanel.ph_cargo')} />{msg('job_title')}
              </div>

              <div>
                <Input label={traducir('userprofile.telefono')} id={`${idCampo}-5`} value={profileForm.phone} onChange={e => setProfileForm(f => ({ ...f, phone: e.target.value }))} placeholder="+34 600 000 000" type="tel" />{msg('phone')}
              </div>

              <div>
                <Input label={traducir('userprofile.url_de_avatar_opcional')} id={`${idCampo}-6`} value={profileForm.avatar_url} onChange={e => setProfileForm(f => ({ ...f, avatar_url: e.target.value }))} placeholder="https://..." />{msg('avatar_url')}
                {profileForm.avatar_url && (
                  <img src={profileForm.avatar_url} alt="preview"
                    loading="lazy" decoding="async"
                    className="usprpa-box-8"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                )}
              </div>

              <Pulsable className={`usprpa-box-25 ${savingProfile ? 'user-profile-panel-m6' : 'user-profile-panel-m7'}`} onClick={() => saveProfile(profileForm)} disabled={savingProfile}>
                {savingProfile ? traducir('userprofilepanel.guardando') : `✓ ${traducir('userprofilepanel.guardar_perfil')}`}
              </Pulsable>
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
                    <Pulsable aria-pressed={localTheme === t.id} className={`usprpa-row-4 userprof-sx2 user-profile-panel-e3 ${localTheme === t.id ? 'user-profile-panel-m8' : 'user-profile-panel-m9'}`} key={t.id} onClick={() => applyTheme(t.id)} style={{ '--user-profile-panel-border': `1px solid ${localTheme === t.id ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
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
                    </Pulsable>
                  ))}
                </div>
              </div>

              {/* Color de acento */}
              <div>
                <div className="usprpa-box-9">
                  {traducir('userprofile.color_de_acento')}
                </div>
                <Pulsable className={`usprpa-box-26 ${localAccent === null ? 'user-profile-panel-m4' : 'user-profile-panel-m12'}`} onClick={() => applyAccent(null)} aria-pressed={localAccent === null}>
                  {localAccent === null ? '✓ ' : ''}{traducir('userprofile.acento_del_tema')}
                </Pulsable>
                <div className="usprpa-grid-1">
                  {ACCENT_PRESETS.map(p => (
                    <Pulsable aria-pressed={localAccent === p.color} className={`usprpa-box-27 user-profile-panel-e13 ${localAccent === p.color ? 'user-profile-panel-m14' : 'user-profile-panel-m15'}`} aria-label={traducir(`userprofilepanel.acento_${p.clave}`)} key={p.color} onClick={() => applyAccent(p.color)}
                      title={traducir(`userprofilepanel.acento_${p.clave}`)}
                      style={{ '--user-profile-panel-background': p.color, '--user-profile-panel-outline': localAccent === p.color ? `3px solid ${p.color}` : 'none' } as CSSProperties}>{null}</Pulsable>
                  ))}
                </div>
                <div className="u-row-center-10">
                  <input type="color" value={localAccent ?? ACENTO_POR_DEFECTO} aria-label={traducir('userprofile.color_personalizado')}
                    onChange={e => applyAccent(e.target.value)}
                    className="usprpa-box-12" />
                  <div>
                    <div className="ds-codigo usprpa-txt-2">
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
                    <Pulsable className={`usprpa-box-28 userprof-sx1 user-profile-panel-e3 ${localDensity === val ? 'user-profile-panel-m4' : 'user-profile-panel-m16'}`} key={val} onClick={() => setLocalDensity(val)} style={{ '--user-profile-panel-border': `1px solid ${localDensity === val ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                      {label}
                    </Pulsable>
                  ))}
                </div>
              </div>

              {/* Menú lateral personalizable (23-11-2026): abre el modo «Personalizar menú» del propio menú. */}
              <div>
                <div className="usprpa-box-9">{traducir('menu_personal.perfil_titulo')}</div>
                <div className="u-hint">{traducir('menu_personal.perfil_texto')}</div>
                <Button variant="secondary" size="sm" icon={<SlidersHorizontal size={13} />}
                  onClick={() => { window.dispatchEvent(new CustomEvent(EVENTO_PERSONALIZAR_MENU)); onClose() }}>
                  {traducir('menu_personal.personalizar')}
                </Button>
              </div>

              <Pulsable onClick={saveAppearance} className="usprpa-box-15">
                ✓ {traducir('userprofilepanel.guardar_apariencia')}
              </Pulsable>
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
                  <Pulsable aria-pressed={isPending} className={`usprpa-row-5 userprof-sx3 user-profile-panel-e3 ${isPending ? 'user-profile-panel-m8' : 'user-profile-panel-m9'}`} key={lang.code} onClick={() => setPendingLang(lang.code)} style={{ '--user-profile-panel-border': `1px solid ${isPending ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    <span className="usprpa-txt-4">{lang.code.toUpperCase()}</span>
                    <span className={`usprpa-box-29 ${isPending ? 'user-profile-panel-m10' : 'user-profile-panel-m11'}`}>
                      {lang.label}
                    </span>
                    {isPending && <span className="usprpa-txt-5">✓</span>}
                  </Pulsable>
                )
              })}
              <Pulsable className={`usprpa-box-30 ${pendingLang === activeLang ? 'user-profile-panel-m17' : 'user-profile-panel-m7'}`} onClick={() => {
                  setLang(pendingLang)  // lo guarda en el servidor (Layout)
                  const label = LANGUAGES.find(l => l.code === pendingLang)?.label
                  toast.success(traducir('userprofilepanel.idioma_cambiado', { idioma: label ?? pendingLang }))
                }} disabled={pendingLang === activeLang}>
                ✓ {traducir('userprofilepanel.guardar_idioma')}
              </Pulsable>
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
                      <Input label={label} id={`${idCampo}-pw-${key}`} type="password" value={pwForm[key]} onChange={e => { camposPw.limpiar(); setPwForm(f => ({ ...f, [key]: e.target.value })) }} placeholder={ph} />
                      {msgPw(key === 'current' ? 'current_password' : key === 'new' ? 'new_password' : key)}
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
                <Pulsable className={`usprpa-box-31 ${user?.mfa_enabled ? 'user-profile-panel-m18' : 'user-profile-panel-m19'}`} onClick={() => { navigate('/settings/mfa'); onClose() }}>
                  {user?.mfa_enabled ? traducir('userprofilepanel.gestionar_mfa') : `🛡 ${traducir('userprofilepanel.activar_mfa')}`}
                </Pulsable>
              </div>

              <PasskeysSection />

              {!user?.sso_provider && (
                <Pulsable className={`usprpa-box-25 ${changingPw || !pwForm.current || !pwForm.new ||
                      pwForm.new !== pwForm.confirm || pwForm.new.length < 8 ? 'user-profile-panel-m17' : 'user-profile-panel-m7'}`} disabled={changingPw || !pwForm.current || !pwForm.new ||
                    pwForm.new !== pwForm.confirm || pwForm.new.length < 8} onClick={() => changePassword({
                    current_password: pwForm.current,
                    new_password: pwForm.new,
                  })}>
                  {changingPw ? traducir('userprofilepanel.guardando') : `✓ ${traducir('userprofilepanel.guardar_seguridad')}`}
                </Pulsable>
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
const TIPOS_DE_AVISO = new Set(["task_assigned","task_mentioned","task_due_soon","task_overdue","sprint_started","sprint_ending","expense_approved","expense_rejected","milestone_approved","milestone_rejected","ticket_assigned","ticket_replied","ticket_resolved","ticket_created","ticket_updated","ticket_sla_warning","ticket_sla_breached","ticket_escalated","approval_requested","project_risk_high","timesheet_reminder","timesheet_approved","budget_warning","mention","automation","system"])

function PreferenciasDeAviso() {
  const toast = useToast()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const { data } = useQuery<{ types: { type: string; channels: string[] }[]; preferences: Record<string, Record<string, boolean>>; digest?: boolean }>({
    queryKey: ['notification-preferences'],
    queryFn: () => preferenciasDeAvisosApi.leer<{ types: { type: string; channels: string[] }[]; preferences: Record<string, Record<string, boolean>>; digest?: boolean }>().then(r => r.data),
  })
  const [prefs, setPrefs] = useState<Record<string, Record<string, boolean>> | null>(null)
  const [resumen, setResumen] = useState<boolean | null>(null)
  const actuales = prefs ?? data?.preferences ?? {}
  const resumenActual = resumen ?? !!data?.digest
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => preferenciasDeAvisosApi.guardar({ preferences: actuales, digest: resumenActual }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notification-preferences'] }); setPrefs(null); setResumen(null); cambiosGuardados(); toast.success(traducir('userprofilepanel.guardado')) },
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
                <Checkbox aria-label={traducir(c === 'app' ? 'userprofilepanel.aviso_por_app' : 'userprofilepanel.aviso_por_correo', { aviso: nombreDelAviso(t.type) })}
                  checked={actuales[t.type]?.[c] ?? true} onChange={m => cambiar(t.type, c, m)} />
              ) : <span className="usprpa-txt-8">—</span>}
            </span>
          ))}
        </div>
      ))}
      <Checkbox className="usprpa-row-3" label={traducir('userprofile.resumen_diario')} checked={resumenActual} onChange={m => setResumen(m)} />
      <div className="usprpa-sp-2">
        <Pulsable className={`usprpa-box-32 ${prefs === null && resumen === null ? 'user-profile-panel-m20' : 'user-profile-panel-m21'}`} disabled={isPending || (prefs === null && resumen === null)} onClick={() => guardar()}>
          {isPending ? traducir('userprofilepanel.guardando') : traducir('common.save')}
        </Pulsable>
      </div>
    </div>
  )
}
