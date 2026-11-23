/**
 * PortalClientePage — Portal externo del cliente.
 *
 * Estructura: Shell (sidebar + topbar al estilo backoffice) + secciones
 * rediseñadas (PortalDashboard, PortalUAT, PortalFeatureRequests, ...).
 *
 * Auth: separado del backoffice (ClientUser). Ver portalClientContext.jsx.
 */
import type { CSSProperties } from 'react'
import { PRODUCT_NAME } from '../constants/brand'
import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Settings, User, Palette, Globe, ShieldCheck, KeyRound,
  Save, Sparkles, Languages,
  Truck, Moon, Stars, Square, Sun, Contrast, Monitor,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import {
  CLIENT_API, LangContext, useLang, useClientAuth,
  ClientAuthProvider, LoginScreen, TextosDeInterfazDelPortal, useErrorDelPortal,
  PersonalizacionesDelPortal,
} from './portal-client/portalClientContext'
import { CambioDeContrasenaObligatorio } from './portal-client/CambioDeContrasenaObligatorio'
import {
  PortalShell, PortalPageHeader,
  PortalCard, PortalSection, PortalTabs,
  PortalButton, PortalField,
  PortalInput, PortalSelect,
  PortalBadge, PortalBanner,
} from './portal-client/PortalUI'
import { STALE_DEFAULT_MS, STALE_SHORT_MS, UI_FEEDBACK_LONG_MS } from '../constants/timings'
import { PORTAL_LANGUAGES, idiomaInicialDelPortal } from '../i18n/portalTranslations'
import { fijarIdiomaDeFormato } from '../utils/helpers'


// ── Tipos locales del dominio del portal ─────────────────────────────────────
interface PortalClientUser {
  id?: string
  email?: string
  name?: string
  full_name?: string
  language?: string
  organization_name?: string
  company?: string
  job_title?: string
  phone?: string
  project_id?: string
  project_ids?: string[]
  projects?: unknown[]
  [k: string]: unknown
}
interface ClientAuthValue { client: PortalClientUser | null; [k: string]: unknown }
type ChangeLangFn = (lang: string) => void
interface PortalListItem {
  status?: string
  requires_signature?: boolean
  signed_by_client?: boolean
  client_approval_status?: string
  client_approved?: unknown
  [k: string]: unknown
}
interface PortalDashboardData {
  kpis?: { unread_messages?: number; [k: string]: unknown }
  [k: string]: unknown
}
import { PortalDashboard } from './portal-client/PortalDashboard'
import {
  PortalUAT, PortalFeatureRequests, PortalMessages,
  PortalInvoices, PortalRoadmap, PortalDocuments, PortalWiki,
} from './portal-client/PortalAdvancedSections'
import { PortalSupportDesk } from './portal-client/PortalSupportDesk'
import { PortalSurveys } from './portal-client/PortalSurveys'
import { PortalNotificaciones } from './portal-client/PortalNotificaciones'
import { CLAVE_AVISOS_DEL_PORTAL } from './portal-client/CampanaDelPortal'
import usePortalEnVivo from './portal-client/usePortalEnVivo'
import PortalAIChatWidget from './portal-client/PortalAIChatWidget'
import { Pulsable, useErroresDeCampo } from '../components/ui'
import './PortalClientePage.css'

// ── Inner app (con cliente autenticado) ──────────────────────────────────────
// El tema del portal se guarda aparte del de la aplicacion interna. Se aplica
// al entrar en el portal (login incluido). Antes solo lo aplicaba «My profile»
// al abrirse: hasta entonces el portal heredaba el tema que hubiera en la
// pagina y, al entrar en el perfil, cambiaba de golpe.
const CLAVE_TEMA_PORTAL = 'portal_theme_mode'

function temaGuardadoDelPortal(): string {
  try { return localStorage.getItem(CLAVE_TEMA_PORTAL) || 'freight' } catch { /* accesorio: sin almacenamiento */ return 'freight' }
}

function aplicarTemaDelPortal(id: string) {
  const efectivo = id === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : id
  document.documentElement.setAttribute('data-theme', efectivo)
}

function PortalApp({ changeLang }: { changeLang: ChangeLangFn }) {
  return <PortalAppContenido changeLang={changeLang} />
}

function PortalAppContenido({ changeLang }: { changeLang: ChangeLangFn }) {
  const qc = useQueryClient()
  const t = useLang()
  const { client } = (useClientAuth() ?? { client: null }) as ClientAuthValue
  // Un enlace con `?ticket=` viene de un correo del Service Desk: se abre en
  // Soporte, que es donde vive el ticket.
  const [section, setSection] = useState(
    () => new URLSearchParams(window.location.search).has('ticket') ? 'support' : 'dashboard')

  const { data: branding } = useQuery({
    queryKey: ['portal-branding'],
    queryFn: () => CLIENT_API.get('/portal/branding').then(r => r.data),
    enabled: !!client,
  })

  const { data: surveys = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_DEFAULT_MS,
  })

  // Badges para sidebar y topbar
  const { data: dash } = useQuery<PortalDashboardData>({
    queryKey: ['portal-dashboard'],
    queryFn: () => CLIENT_API.get('/portal/dashboard').then(r => r.data as PortalDashboardData),
    enabled: !!client, staleTime: STALE_SHORT_MS, refetchOnWindowFocus: false,
  })
  const { data: tickets = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-sd-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_SHORT_MS,
  })
  const { data: docs = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-docs-client'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_SHORT_MS,
  })
  const { data: invoices = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_SHORT_MS,
  })
  const { data: frs = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-frs-client'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_SHORT_MS,
  })
  const { data: uats = [] } = useQuery<PortalListItem[]>({
    queryKey: ['portal-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data as PortalListItem[]),
    enabled: !!client, staleTime: STALE_SHORT_MS,
  })

  const pendingSurveys = surveys.filter(s => s.status === 'pending').length

  const badges = {
    support:   tickets.filter(t => t.status === 'pending_client').length,
    documents: docs.filter(d => d.requires_signature && !d.signed_by_client).length,
    invoices:  invoices.filter(i => i.client_approval_status === 'pending').length,
    requests:  frs.filter(f => f.status === 'estimated' && f.client_approved == null).length,
    uat:       uats.filter(u => ['pending', 'in_progress'].includes(String(u.status))).length,
    messages:  dash?.kpis?.unread_messages || 0,
    surveys:   pendingSurveys,
  }

  // WebSocket del portal, compartido (`usePortalEnVivo`, 17-11-2026: también lo
  // usa el chat en vivo). `avisosEnVivo`: con el socket abierto la campana no sondea.
  const avisosEnVivo = usePortalEnVivo(!!client, (msg) => {
    if (msg?.type !== 'portal_notifications') return
    for (const clave of ['portal-dashboard', 'portal-messages-client', 'portal-conversations-client', 'portal-sd-tickets',
      'portal-invoices', 'portal-docs-client', 'portal-frs-client', 'portal-uat', 'portal-surveys', CLAVE_AVISOS_DEL_PORTAL]) {
      qc.invalidateQueries({ queryKey: [clave] })
    }
  })

  return (
    <PortalShell section={section} onSection={setSection} branding={branding} badges={badges} avisosEnVivo={avisosEnVivo}>
      {pendingSurveys > 0 && section !== 'profile' && section !== 'surveys' && (
        <Pulsable className="pcl-btn-ghost"
          onClick={() => setSection('surveys')}
        >
          <PortalBanner
            tone="info"
            icon={<Sparkles size={18} />}
            title={(pendingSurveys === 1 ? t('surveys_banner_title_one') : t('surveys_banner_title_other')).replace('{{n}}', String(pendingSurveys))}
            body={t('surveys_banner_body')}
          />
        </Pulsable>
      )}

      {section === 'dashboard'  && <PortalDashboard onNavigate={setSection} />}
      {section === 'roadmap'    && <PortalRoadmap />}
      {section === 'uat'        && <PortalUAT />}
      {section === 'requests'   && <PortalFeatureRequests />}
      {section === 'support'    && <PortalSupportDesk />}
      {section === 'messages'   && <PortalMessages />}
      {section === 'documents'  && <PortalDocuments />}
      {section === 'wiki'       && <PortalWiki />}
      {section === 'invoices'   && <PortalInvoices />}
      {section === 'surveys'    && <PortalSurveys />}
      {section === 'notifications' && <PortalNotificaciones onSection={setSection} enVivo={avisosEnVivo} />}
      {section === 'profile'    && <PortalMyProfile changeLang={changeLang} />}
      {/* I26: widget flotante de IA, visible desde cualquier sección del portal */}
      <PortalAIChatWidget />
    </PortalShell>
  )
}

// ── Mi perfil rediseñado ─────────────────────────────────────────────────────
function PortalMyProfile({ changeLang }: { changeLang: ChangeLangFn }) {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const { client } = (useClientAuth() ?? { client: null }) as ClientAuthValue
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('profile')
  const [form, setForm] = useState({
    full_name: client?.full_name || '',
    phone: client?.phone || '',
    job_title: client?.job_title || '',
  })
  const [pendingLang, setPendingLang] = useState(client?.language || idiomaInicialDelPortal())
  const [pwdForm, setPwdForm] = useState({ current: '', new_pwd: '', confirm: '' })
  const [pwdError, setPwdError] = useState('')
  const camposPerfil = useErroresDeCampo()
  const camposPwd = useErroresDeCampo({ password: 'new_pwd', current_password: 'current' })
  const [savedProfile, setSavedProfile] = useState(false)
  const [savedLanguage, setSavedLanguage] = useState(false)
  const [themeMode, setThemeMode] = useState(temaGuardadoDelPortal)

  const { data: me } = useQuery<Record<string, unknown>>({
    queryKey: ['portal-me'],
    queryFn: () => CLIENT_API.get('/portal/auth/me').then(r => r.data as Record<string, unknown>),
  })

  const LANGUAGES = PORTAL_LANGUAGES
  const THEMES = [
    { id: 'freight', label: 'Freight Pro', desc: traducir('portal_perfil.tema_freight_desc', { producto: PRODUCT_NAME }), icon: <Truck size={14} /> },
    { id: 'dark',    label: traducir('portal_perfil.tema_oscuro'), desc: traducir('portal_perfil.tema_oscuro_desc'), icon: <Moon size={14} /> },
    { id: 'midnight', label: 'Midnight',   desc: traducir('portal_perfil.tema_midnight_desc'), icon: <Stars size={14} /> },
    { id: 'slate',   label: 'Slate',       desc: traducir('portal_perfil.tema_slate_desc'), icon: <Square size={14} /> },
    { id: 'light',   label: traducir('portal_perfil.tema_claro'), desc: traducir('portal_perfil.tema_claro_desc'), icon: <Sun size={14} /> },
    { id: 'high-contrast', label: traducir('portal_perfil.tema_alto_contraste'), desc: traducir('portal_perfil.tema_alto_contraste_desc'), icon: <Contrast size={14} /> },
    { id: 'system',  label: traducir('portal_perfil.tema_sistema'), desc: traducir('portal_perfil.tema_sistema_desc'), icon: <Monitor size={14} /> },
  ]
  const TABS = [
    { id: 'profile',    label: traducir('portal_perfil.tab_perfil'), icon: <User size={14} /> },
    { id: 'appearance', label: traducir('portal_perfil.tab_apariencia'), icon: <Palette size={14} /> },
    { id: 'language',   label: traducir('portal_perfil.tab_idioma'), icon: <Languages size={14} /> },
    { id: 'security',   label: traducir('portal_perfil.tab_seguridad'), icon: <ShieldCheck size={14} /> },
  ]

  // Elegir un tema lo previsualiza; si se sale sin guardar, vuelve el guardado.
  const applyTheme = (id: string) => {
    setThemeMode(id)
    aplicarTemaDelPortal(id)
  }
  useEffect(() => () => aplicarTemaDelPortal(temaGuardadoDelPortal()), [])

  const { mutate: saveProfile, isPending: saving } = useMutation({
    mutationFn: (d: Record<string, unknown>) => CLIENT_API.patch('/portal/auth/me', d).then(r => r.data),
    onMutate: () => camposPerfil.limpiar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-me'] })
      setSavedProfile(true)
      setTimeout(() => setSavedProfile(false), UI_FEEDBACK_LONG_MS)
    },
    onError: (e: unknown) => { if (!camposPerfil.recoger(e)) toast.error(errorDe(e, traducir('portal_perfil.error_guardar'))) },
  })

  const { mutate: saveLanguage, isPending: savingLanguage } = useMutation({
    mutationFn: (lang: string) => CLIENT_API.patch('/portal/auth/me', { language: lang }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-me'] })
      // 23-11-2026: todo el bloque de localStorage va protegido (puede estar bloqueado).
      try {
        localStorage.setItem('portal_lang', pendingLang)
        const saved = JSON.parse(localStorage.getItem('client_user') || '{}')
        saved.language = pendingLang
        localStorage.setItem('client_user', JSON.stringify(saved))
      } catch { /* accesorio: sin almacenamiento o dato corrupto; el idioma ya está guardado en la ficha del servidor */ }
      if (changeLang) changeLang(pendingLang)
      setSavedLanguage(true)
      setTimeout(() => setSavedLanguage(false), UI_FEEDBACK_LONG_MS)
    },
    onError: (e: unknown) => toast.error(errorDe(e, traducir('portal_perfil.error_idioma'))),
  })

  const { mutate: savePwd, isPending: changingPwd } = useMutation({
    onMutate: () => camposPwd.limpiar(),
    mutationFn: (d: { current: string; new_pwd: string; confirm: string }) => CLIENT_API.patch('/portal/auth/me', { password: d.new_pwd, current_password: d.current }).then(r => r.data),
    onSuccess: () => { setPwdForm({ current: '', new_pwd: '', confirm: '' }); toast.success(traducir('portal_perfil.contrasena_actualizada')) },
    onError: (e: unknown) => {
      // 16-11-2026: el error del servidor llega con código y se pinta en el idioma del portal.
      if (!camposPwd.recoger(e)) setPwdError(errorDe(e, traducir('portal_perfil.error_contrasena')))
    },
  })

  const handlePwdChange = () => {
    setPwdError('')
    if (pwdForm.new_pwd !== pwdForm.confirm) { setPwdError(traducir('portal_perfil.contrasenas_no_coinciden')); return }
    // El servidor exige 8 (antes la pantalla aceptaba 6 y el servidor lo rechazaba).
    if (pwdForm.new_pwd.length < 8) { setPwdError(traducir('portal_perfil.minimo_8')); return }
    savePwd(pwdForm)
  }

  const saveAppearance = () => {
    try { localStorage.setItem(CLAVE_TEMA_PORTAL, themeMode) } catch { /* sin almacenamiento */ }
    applyTheme(themeMode)
    toast.success(traducir('portal_perfil.apariencia_guardada'))
  }

  const permissions = [
    { key: 'can_approve_deliverables', label: traducir('portal_perfil.perm_aprobar') },
    { key: 'can_request_changes',      label: traducir('portal_perfil.perm_cambios') },
    { key: 'can_view_budget',          label: traducir('portal_perfil.perm_presupuesto') },
    { key: 'can_view_team',            label: traducir('portal_perfil.perm_equipo') },
  ]

  return (
    <div>
      <PortalPageHeader
        title={traducir('portal_perfil.mi_perfil')}
        subtitle={traducir('portal_perfil.mi_perfil_sub')}
        icon={Settings}
      />

      {/* Identity card */}
      <PortalCard className="portalcl-sx4">
        <div className="pcl-row">
          <div className="pcl-row-2">{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
          <div className="u-flex1-min0">
            <div className="pcl-text-lg-strong">{client?.full_name}</div>
            <div className="u-text2-sm">{client?.email}</div>
            <div className="u-text3-xs-mt2">
              {client?.job_title && `${client.job_title} · `}{client?.company || client?.organization_name}
            </div>
          </div>
        </div>
      </PortalCard>

      {/* Sub-tabs */}
      <PortalTabs tabs={TABS} value={tab} onChange={setTab} ariaLabel={traducir('portal_perfil.mi_perfil')} />

      {/* Tab content */}
      {tab === 'profile' && (
        <PortalCard>
          <PortalSection title={traducir('portalcliente.informacion_personal')}>
            <div className="pcl-grid">
              <PortalField label={traducir('portal_perfil.nombre_visible')} error={camposPerfil.de('full_name')}>
                <PortalInput value={form.full_name} onChange={(e: ChangeEvent<HTMLInputElement>) => { camposPerfil.limpiar('full_name'); setForm(f => ({ ...f, full_name: e.target.value })) }} />
              </PortalField>
              <PortalField label={traducir('portal_perfil.cargo')} error={camposPerfil.de('job_title')}>
                <PortalInput value={form.job_title} onChange={(e: ChangeEvent<HTMLInputElement>) => { camposPerfil.limpiar('job_title'); setForm(f => ({ ...f, job_title: e.target.value })) }} />
              </PortalField>
              <PortalField label={traducir('portalcliente.telefono')} error={camposPerfil.de('phone')}>
                <PortalInput value={form.phone} onChange={(e: ChangeEvent<HTMLInputElement>) => { camposPerfil.limpiar('phone'); setForm(f => ({ ...f, phone: e.target.value })) }} />
              </PortalField>
            </div>
            <PortalBanner tone="info" icon={<KeyRound size={16} />}
              title={traducir('portalcliente.email_no_editable')}
              body={traducir('portal_perfil.email_identificador', { email: client?.email ?? '' })} />
            {savedProfile && (
              <PortalBanner tone="success" title={traducir('portal_perfil.perfil_actualizado')} />
            )}
            <div className="u-row-end">
              <PortalButton icon={<Save size={13} />} loading={saving} onClick={() => saveProfile(form)}>
                {traducir('portal_perfil.guardar_cambios')}
              </PortalButton>
            </div>
          </PortalSection>

          <div className="pcl-box">
            <PortalSection title={traducir('portal_perfil.mi_acceso')} hint={traducir('portal_perfil.mi_acceso_hint')}>
              <div className="pcl-grid-2">
                {permissions.map(p => (
                  <div className="pcl-row-4" key={p.key}>
                    <span className="u-text2-sm">{p.label}</span>
                    <PortalBadge tone={me?.[p.key] ? 'success' : 'default'}>{me?.[p.key] ? traducir('portal_perfil.si') : traducir('portal_perfil.no')}</PortalBadge>
                  </div>
                ))}
              </div>
            </PortalSection>
          </div>
        </PortalCard>
      )}

      {tab === 'appearance' && (
        <PortalCard>
          <PortalSection title={traducir('portalcliente.tema_del_portal')}>
            <div className="pcl-grid-3">
              {THEMES.map(th => {
                const active = themeMode === th.id
                return (
                  <Pulsable className="pcl-btn" key={th.id} aria-pressed={active} onClick={() => applyTheme(th.id)} style={{ '--pcl-btn-border': `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`, '--pcl-btn-background': active ? 'var(--accent-muted)' : 'var(--surface-3)' } as CSSProperties}>
                    <div className="pcl-text-sm-strong" style={{ '--pcl-text-sm-strong-color': active ? 'var(--accent)' : 'var(--text-1)' } as CSSProperties}>
                      <span className="pcl-text" aria-hidden="true">{th.icon}</span>{th.label}
                    </div>
                    <div className="u-text3-xs">{th.desc}</div>
                  </Pulsable>
                )
              })}
            </div>
            <div className="u-row-end">
              <PortalButton icon={<Save size={13} />} onClick={saveAppearance}>{traducir('portal_perfil.guardar_apariencia')}</PortalButton>
            </div>
          </PortalSection>
        </PortalCard>
      )}

      {tab === 'language' && (
        <PortalCard>
          <PortalSection title={traducir('portalcliente.idioma_del_portal')}>
            <PortalField label={traducir('portal_perfil.selecciona_idioma')}>
              <PortalSelect value={pendingLang} onChange={(e: ChangeEvent<HTMLSelectElement>) => setPendingLang(e.target.value)}>
                {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </PortalSelect>
            </PortalField>
            {savedLanguage && (
              <div className="pcl-text-2">
                <PortalBanner tone="success" title={traducir('portal_perfil.idioma_actualizado')} />
              </div>
            )}
            <div className="pcl-row-5">
              <PortalButton icon={<Globe size={13} />} loading={savingLanguage}
                onClick={() => saveLanguage(pendingLang)}>{traducir('portal_perfil.guardar_idioma')}</PortalButton>
            </div>
          </PortalSection>
        </PortalCard>
      )}

      {tab === 'security' && (
        <PortalCard>
          <PortalSection title={traducir('portalcliente.cambiar_contrasena')} hint={traducir('portal_perfil.minimo_8')}>
            <div className="u-stack-12">
              <PortalField label={traducir('portal_perfil.contrasena_actual')} error={camposPwd.de('current')}>
                <PortalInput type="password" autoComplete="current-password" value={pwdForm.current}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => { camposPwd.limpiar('current'); setPwdForm(f => ({ ...f, current: e.target.value })) }} placeholder={traducir('portal_perfil.contrasena_actual')} />
              </PortalField>
              <PortalField label={traducir('portalcliente.nueva_contrasena')} error={camposPwd.de('new_pwd')}>
                <PortalInput type="password" value={pwdForm.new_pwd}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => { camposPwd.limpiar('new_pwd'); setPwdForm(f => ({ ...f, new_pwd: e.target.value })) }} placeholder={traducir('portalcliente.nueva_contrasena')} />
              </PortalField>
              <PortalField label={traducir('portalcliente.confirmar_nueva_contrasena')}>
                <PortalInput type="password" value={pwdForm.confirm}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setPwdForm(f => ({ ...f, confirm: e.target.value }))} placeholder={traducir('portalcliente.repite_la_contrasena')} />
              </PortalField>
            </div>
            {pwdError && (
              <div className="pcl-text-2">
                <PortalBanner tone="danger" title={pwdError} />
              </div>
            )}
            <div className="pcl-row-5">
              <PortalButton icon={<KeyRound size={13} />} loading={changingPwd}
                disabled={!pwdForm.current || !pwdForm.new_pwd || !pwdForm.confirm}
                onClick={handlePwdChange}>{traducir('portalcliente.cambiar_contrasena')}</PortalButton>
            </div>
            <div className="pcl-text-muted-xs">
              {traducir('portalcliente.elige_una_contrasena_segura_que_no_uses')}
            </div>
          </PortalSection>
        </PortalCard>
      )}
    </div>
  )
}

// ── Root ─────────────────────────────────────────────────────────────────────
export default function PortalClientePage() {
  // Incidencia 5 (23-11-2026): usuario > empresa > navegador > inglés.
  const [lang, setLang] = useState<string>(idiomaInicialDelPortal)
  const changeLang: ChangeLangFn = (l) => {
    setLang(l)
    try { localStorage.setItem('portal_lang', l) } catch { /* accesorio: sin almacenamiento, el idioma no se recuerda entre visitas */ }
  }
  // Fechas y números en el idioma del cliente, no en el del operador que haya
  // usado este navegador (16-11-2026). Se fija en el render —no en un efecto—
  // para que el primer pintado ya salga bien; al salir del portal se suelta.
  fijarIdiomaDeFormato(lang)
  useEffect(() => () => fijarIdiomaDeFormato(null), [])
  return (
    <LangContext.Provider value={lang}>
      {/* 16-11-2026: el kit y el aviso global, en el idioma del portal y con las
          personalizaciones del administrador (que necesitan la sesión). */}
      <ClientAuthProvider>
        <PersonalizacionesDelPortal>
          <TextosDeInterfazDelPortal>
            <PortalClienteInner changeLang={changeLang} currentLang={lang} />
          </TextosDeInterfazDelPortal>
        </PersonalizacionesDelPortal>
      </ClientAuthProvider>
    </LangContext.Provider>
  )
}

function PortalClienteInner({ changeLang, currentLang }: { changeLang: ChangeLangFn; currentLang: string }) {
  const _toast = useToast()
  useEffect(() => { aplicarTemaDelPortal(temaGuardadoDelPortal()) }, [])
  const { client } = (useClientAuth() ?? { client: null }) as ClientAuthValue
  // Revisión 2026-11: el idioma guardado en la ficha del cliente manda al
  // entrar; antes solo se miraba este navegador y en otro salía en español.
  const idiomaDeLaFicha = (client as { language?: string } | null)?.language
  useEffect(() => {
    if (idiomaDeLaFicha && idiomaDeLaFicha !== currentLang) changeLang(idiomaDeLaFicha)
  }, [idiomaDeLaFicha])  // eslint-disable-line react-hooks/exhaustive-deps
  // 23-11-2026: con la contraseña generada por el sistema, primero se cambia
  // (el servidor responde 403 `portal_cambio_de_contrasena_obligatorio` al resto).
  if (client && (client as { must_change_password?: boolean }).must_change_password) {
    return <CambioDeContrasenaObligatorio />
  }
  return client
    ? <PortalApp changeLang={changeLang} />
    : <LoginScreen _changeLang={changeLang} _currentLang={currentLang} />
}
