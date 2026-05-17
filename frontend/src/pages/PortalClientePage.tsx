// @ts-nocheck
/**
 * PortalClientePage — Portal externo del cliente.
 *
 * Estructura: Shell (sidebar + topbar al estilo backoffice) + secciones
 * rediseñadas (PortalDashboard, PortalUAT, PortalFeatureRequests, ...).
 *
 * Auth: separado del backoffice (ClientUser). Ver portalClientContext.jsx.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Settings, User, Palette, Globe, ShieldCheck, KeyRound,
  Save, Sparkles, Languages,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import {
  CLIENT_API, LangContext, useLang, useClientAuth,
  ClientAuthProvider, LoginScreen,
} from './portal-client/portalClientContext'
import {
  PortalShell, PortalPageHeader, PortalCard, PortalSection,
  PortalButton, PortalField, PortalInput, PortalSelect, PortalBadge,
  PortalBanner,
} from './portal-client/PortalUI'
import { PortalDashboard } from './portal-client/PortalDashboard'
import {
  PortalUAT, PortalFeatureRequests, PortalMessages,
  PortalInvoices, PortalRoadmap, PortalDocuments, PortalWiki,
} from './portal-client/PortalAdvancedSections'
import { PortalSupportDesk } from './portal-client/PortalSupportDesk'
import { PortalSurveys } from './portal-client/PortalSurveys'
import PortalAIChatWidget from './portal-client/PortalAIChatWidget'

// ── Inner app (con cliente autenticado) ──────────────────────────────────────
function PortalApp({ changeLang }) {
  const qc = useQueryClient()
  const { client } = useClientAuth()
  const [section, setSection] = useState('dashboard')

  const { data: branding } = useQuery({
    queryKey: ['portal-branding'],
    queryFn: () => CLIENT_API.get('/portal/branding').then(r => r.data),
    enabled: !!client,
  })

  const { data: surveys = [] } = useQuery({
    queryKey: ['portal-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
    enabled: !!client, staleTime: 60000,
  })

  // Badges para sidebar y topbar
  const { data: dash } = useQuery({
    queryKey: ['portal-dashboard'],
    queryFn: () => CLIENT_API.get('/portal/dashboard').then(r => r.data),
    enabled: !!client, staleTime: 30000, refetchOnWindowFocus: false,
  })
  const { data: tickets = [] } = useQuery({
    queryKey: ['portal-sd-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data),
    enabled: !!client, staleTime: 30000,
  })
  const { data: docs = [] } = useQuery({
    queryKey: ['portal-docs-client'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data),
    enabled: !!client, staleTime: 30000,
  })
  const { data: invoices = [] } = useQuery({
    queryKey: ['portal-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
    enabled: !!client, staleTime: 30000,
  })
  const { data: frs = [] } = useQuery({
    queryKey: ['portal-frs-client'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data),
    enabled: !!client, staleTime: 30000,
  })
  const { data: uats = [] } = useQuery({
    queryKey: ['portal-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data),
    enabled: !!client, staleTime: 30000,
  })

  const pendingSurveys = surveys.filter(s => s.status === 'pending').length

  const badges = {
    support:   tickets.filter(t => t.status === 'pending_client').length,
    documents: docs.filter(d => d.requires_signature && !d.signed_by_client).length,
    invoices:  invoices.filter(i => i.client_approval_status === 'pending').length,
    requests:  frs.filter(f => f.status === 'estimated' && f.client_approved == null).length,
    uat:       uats.filter(u => ['pending', 'in_progress'].includes(u.status)).length,
    messages:  dash?.kpis?.unread_messages || 0,
    surveys:   pendingSurveys,
  }

  // WebSocket portal-notifications con reconexión exponencial.
  useEffect(() => {
    if (!client) return
    let socket = null
    let pingInterval = null
    let reconnectTimer = null
    let cancelled = false
    let attempt = 0
    const MAX_ATTEMPTS = 5

    const connect = async () => {
      if (cancelled || attempt >= MAX_ATTEMPTS) return
      attempt++
      try {
        const ticketRes = await CLIENT_API.get('/ws/portal-ticket')
        const ticket = ticketRes?.data?.ticket
        if (!ticket || cancelled) return
        const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = `${wsProto}://${window.location.host}/api/v1/ws/portal-notifications?ticket=${encodeURIComponent(ticket)}`
        socket = new window.WebSocket(wsUrl)
        socket.onopen = () => { attempt = 0 }
        socket.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            if (msg?.type === 'portal_notifications') {
              qc.invalidateQueries(['portal-dashboard'])
              qc.invalidateQueries(['portal-messages-client'])
              qc.invalidateQueries(['portal-conversations-client'])
              qc.invalidateQueries(['portal-sd-tickets'])
              qc.invalidateQueries(['portal-invoices'])
              qc.invalidateQueries(['portal-docs-client'])
              qc.invalidateQueries(['portal-frs-client'])
              qc.invalidateQueries(['portal-uat'])
              qc.invalidateQueries(['portal-surveys'])
            }
          } catch { /* network garbage */ }
        }
        socket.onclose = (ev) => {
          if (cancelled) return
          if (ev.code === 1000 || ev.code === 1001) return
          const delay = Math.min(1000 * 2 ** (attempt - 1), 30000)
          reconnectTimer = window.setTimeout(connect, delay)
        }
        socket.onerror = () => { /* onclose follows */ }
        if (pingInterval) window.clearInterval(pingInterval)
        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      } catch {
        if (!cancelled && attempt < MAX_ATTEMPTS) {
          const delay = Math.min(1000 * 2 ** (attempt - 1), 30000)
          reconnectTimer = window.setTimeout(connect, delay)
        }
      }
    }
    connect()
    return () => {
      cancelled = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (pingInterval) window.clearInterval(pingInterval)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
    }
  }, [client, qc])

  return (
    <PortalShell section={section} onSection={setSection} branding={branding} badges={badges}>
      {pendingSurveys > 0 && section !== 'profile' && section !== 'surveys' && (
        <button type="button"
          onClick={() => setSection('surveys')}
          style={{
            background: 'transparent', border: 'none', padding: 0,
            display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          <PortalBanner
            tone="info"
            icon={<Sparkles size={18} />}
            title={`Tienes ${pendingSurveys} encuesta(s) pendiente(s)`}
            body="Tu opinión nos ayuda a mejorar — responde en menos de 1 minuto. Pulsa aquí."
          />
        </button>
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
      {section === 'profile'    && <PortalMyProfile changeLang={changeLang} />}
      {/* I26: widget flotante de IA, visible desde cualquier sección del portal */}
      <PortalAIChatWidget />
    </PortalShell>
  )
}

// ── Mi perfil rediseñado ─────────────────────────────────────────────────────
function PortalMyProfile({ changeLang }) {
  const { client } = useClientAuth()
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('profile')
  const [form, setForm] = useState({
    full_name: client?.full_name || '',
    phone: client?.phone || '',
    job_title: client?.job_title || '',
  })
  const [pendingLang, setPendingLang] = useState(client?.language || 'es')
  const [pwdForm, setPwdForm] = useState({ new_pwd: '', confirm: '' })
  const [pwdError, setPwdError] = useState('')
  const [savedProfile, setSavedProfile] = useState(false)
  const [savedLanguage, setSavedLanguage] = useState(false)
  const [themeMode, setThemeMode] = useState(() => localStorage.getItem('portal_theme_mode') || 'freight')

  const { data: me } = useQuery({
    queryKey: ['portal-me'],
    queryFn: () => CLIENT_API.get('/portal/auth/me').then(r => r.data),
  })

  const LANGUAGES = [
    { code: 'es', label: 'Español' },  { code: 'en', label: 'English' },
    { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' },
    { code: 'pt', label: 'Português' }, { code: 'it', label: 'Italiano' },
    { code: 'pl', label: 'Polski' },   { code: 'zh', label: '中文' },
  ]
  const THEMES = [
    { id: 'freight', label: 'Freight Pro', desc: 'Tema principal de Contecflow', icon: '🚚' },
    { id: 'dark',    label: 'Oscuro',      desc: 'Estilo oscuro clásico',         icon: '🌙' },
    { id: 'midnight', label: 'Midnight',   desc: 'Oscuro profundo',               icon: '🌌' },
    { id: 'slate',   label: 'Slate',       desc: 'Gris neutro',                   icon: '⬛' },
    { id: 'light',   label: 'Claro',       desc: 'Fondo claro',                   icon: '☀️' },
    { id: 'high-contrast', label: 'Alto contraste', desc: 'Máxima legibilidad',   icon: '◑' },
    { id: 'system',  label: 'Sistema',     desc: 'Sigue el sistema operativo',    icon: '💻' },
  ]
  const TABS = [
    { id: 'profile',    label: 'Perfil',      icon: <User size={13} /> },
    { id: 'appearance', label: 'Apariencia',  icon: <Palette size={13} /> },
    { id: 'language',   label: 'Idioma',      icon: <Languages size={13} /> },
    { id: 'security',   label: 'Seguridad',   icon: <ShieldCheck size={13} /> },
  ]

  const applyTheme = (id) => {
    setThemeMode(id)
    if (id === 'system') {
      const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    } else {
      document.documentElement.setAttribute('data-theme', id)
    }
  }
  // Aplica el tema una sola vez al montar (los cambios manuales pasan por applyTheme directamente).
  useEffect(() => {
    applyTheme(themeMode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { mutate: saveProfile, isPending: saving } = useMutation({
    mutationFn: d => CLIENT_API.patch('/portal/auth/me', d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-me'])
      setSavedProfile(true)
      setTimeout(() => setSavedProfile(false), 3000)
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const { mutate: saveLanguage, isPending: savingLanguage } = useMutation({
    mutationFn: lang => CLIENT_API.patch('/portal/auth/me', { language: lang }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-me'])
      localStorage.setItem('portal_lang', pendingLang)
      try {
        const saved = JSON.parse(localStorage.getItem('client_user') || '{}')
        saved.language = pendingLang
        localStorage.setItem('client_user', JSON.stringify(saved))
      } catch { /* noop */ }
      if (changeLang) changeLang(pendingLang)
      setSavedLanguage(true)
      setTimeout(() => setSavedLanguage(false), 3000)
    },
    onError: e => toast.error(extractErr(e, 'Error al cambiar idioma')),
  })

  const { mutate: savePwd, isPending: changingPwd } = useMutation({
    mutationFn: d => CLIENT_API.patch('/portal/auth/me', { password: d.new_pwd }).then(r => r.data),
    onSuccess: () => { setPwdForm({ new_pwd: '', confirm: '' }); toast.success('Contraseña actualizada') },
    onError: e => {
      const raw = e?.response?.data?.detail
      setPwdError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'Error al cambiar contraseña'))
    },
  })

  const handlePwdChange = () => {
    setPwdError('')
    if (pwdForm.new_pwd !== pwdForm.confirm) { setPwdError('Las contraseñas no coinciden'); return }
    if (pwdForm.new_pwd.length < 6) { setPwdError('Mínimo 6 caracteres'); return }
    savePwd(pwdForm)
  }

  const saveAppearance = () => {
    localStorage.setItem('portal_theme_mode', themeMode)
    applyTheme(themeMode)
    toast.success('Apariencia guardada')
  }

  const permissions = [
    { key: 'can_approve_deliverables', label: 'Aprobar entregables' },
    { key: 'can_request_changes',      label: 'Solicitar cambios' },
    { key: 'can_view_budget',          label: 'Ver presupuesto' },
    { key: 'can_view_team',            label: 'Ver equipo' },
  ]

  return (
    <div>
      <PortalPageHeader
        title="Mi perfil"
        subtitle="Datos personales, idioma, apariencia y seguridad."
        icon={Settings}
      />

      {/* Identity card */}
      <PortalCard style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{
            width: 64, height: 64, borderRadius: 16,
            background: 'linear-gradient(135deg, var(--accent), var(--purple, #7c3aed))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 'var(--text-xl-em)', fontWeight: 800, color: '#fff', flexShrink: 0,
          }}>{client?.full_name?.charAt(0)?.toUpperCase() || '?'}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 800 }}>{client?.full_name}</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{client?.email}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
              {client?.job_title && `${client.job_title} · `}{client?.company || client?.organization_name}
            </div>
          </div>
        </div>
      </PortalCard>

      {/* Sub-tabs */}
      <div role="tablist" aria-label="Mi perfil" style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--surface-4)', marginBottom: 20, flexWrap: 'wrap' }}>
        {TABS.map(tb => (
          <button key={tb.id} role="tab" aria-selected={tab === tb.id}
            onClick={() => setTab(tb.id)}
            style={{
              background: 'transparent', border: 'none',
              borderBottom: `2px solid ${tab === tb.id ? 'var(--accent)' : 'transparent'}`,
              padding: '9px 14px', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 'var(--text-sm)', fontWeight: tab === tb.id ? 700 : 500,
              color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)',
              display: 'inline-flex', alignItems: 'center', gap: 6,
            }}>{tb.icon} {tb.label}</button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'profile' && (
        <PortalCard>
          <PortalSection title="Información personal">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
              <PortalField label="Nombre visible">
                <PortalInput value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
              </PortalField>
              <PortalField label="Cargo / Rol">
                <PortalInput value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} />
              </PortalField>
              <PortalField label="Teléfono">
                <PortalInput value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
              </PortalField>
            </div>
            <PortalBanner tone="info" icon={<KeyRound size={16} />}
              title="Email no editable"
              body={`Tu email (${client?.email}) es tu identificador. Si necesitas cambiarlo, contacta con el equipo.`} />
            {savedProfile && (
              <PortalBanner tone="success" title="Perfil actualizado correctamente" />
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <PortalButton icon={<Save size={13} />} loading={saving} onClick={() => saveProfile(form)}>
                Guardar cambios
              </PortalButton>
            </div>
          </PortalSection>

          <div style={{ marginTop: 22, paddingTop: 18, borderTop: '1px solid var(--surface-4)' }}>
            <PortalSection title="Mi acceso" hint="Permisos asignados por tu gestor">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
                {permissions.map(p => (
                  <div key={p.key} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 14px',
                    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                    borderRadius: 10,
                  }}>
                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{p.label}</span>
                    <PortalBadge tone={me?.[p.key] ? 'success' : 'default'}>{me?.[p.key] ? 'Sí' : 'No'}</PortalBadge>
                  </div>
                ))}
              </div>
            </PortalSection>
          </div>
        </PortalCard>
      )}

      {tab === 'appearance' && (
        <PortalCard>
          <PortalSection title="Tema del portal">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, marginBottom: 14 }}>
              {THEMES.map(th => {
                const active = themeMode === th.id
                return (
                  <button key={th.id} onClick={() => applyTheme(th.id)} style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    borderRadius: 10,
                    border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
                    background: active ? 'var(--accent-muted)' : 'var(--surface-3)',
                    cursor: 'pointer', fontFamily: 'inherit',
                  }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: active ? 'var(--accent)' : 'var(--text-1)', marginBottom: 2 }}>
                      <span style={{ marginRight: 6 }}>{th.icon}</span>{th.label}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{th.desc}</div>
                  </button>
                )
              })}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <PortalButton icon={<Save size={13} />} onClick={saveAppearance}>Guardar apariencia</PortalButton>
            </div>
          </PortalSection>
        </PortalCard>
      )}

      {tab === 'language' && (
        <PortalCard>
          <PortalSection title="Idioma del portal">
            <PortalField label="Selecciona idioma">
              <PortalSelect value={pendingLang} onChange={e => setPendingLang(e.target.value)}>
                {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </PortalSelect>
            </PortalField>
            {savedLanguage && (
              <div style={{ marginTop: 12 }}>
                <PortalBanner tone="success" title="Idioma actualizado" />
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
              <PortalButton icon={<Globe size={13} />} loading={savingLanguage}
                onClick={() => saveLanguage(pendingLang)}>Guardar idioma</PortalButton>
            </div>
          </PortalSection>
        </PortalCard>
      )}

      {tab === 'security' && (
        <PortalCard>
          <PortalSection title="Cambiar contraseña" hint="Mínimo 6 caracteres">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <PortalField label="Nueva contraseña">
                <PortalInput type="password" value={pwdForm.new_pwd}
                  onChange={e => setPwdForm(f => ({ ...f, new_pwd: e.target.value }))} placeholder="Nueva contraseña" />
              </PortalField>
              <PortalField label="Confirmar nueva contraseña">
                <PortalInput type="password" value={pwdForm.confirm}
                  onChange={e => setPwdForm(f => ({ ...f, confirm: e.target.value }))} placeholder="Repite la contraseña" />
              </PortalField>
            </div>
            {pwdError && (
              <div style={{ marginTop: 12 }}>
                <PortalBanner tone="danger" title={pwdError} />
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
              <PortalButton icon={<KeyRound size={13} />} loading={changingPwd}
                disabled={!pwdForm.new_pwd || !pwdForm.confirm}
                onClick={handlePwdChange}>Cambiar contraseña</PortalButton>
            </div>
            <div style={{ marginTop: 14, fontSize: 'var(--text-xs)', color: 'var(--text-3)', lineHeight: 1.6 }}>
              Elige una contraseña segura que no uses en otros servicios. Si la olvidas, contacta con el equipo para que te la restablezcan.
            </div>
          </PortalSection>
        </PortalCard>
      )}
    </div>
  )
}

// ── Root ─────────────────────────────────────────────────────────────────────
export default function PortalClientePage() {
  const _t = useAppT()
  const [lang, setLang] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('client_user') || 'null')
      if (saved?.language) return saved.language
    } catch { /* noop */ }
    return localStorage.getItem('portal_lang') || 'es'
  })
  const changeLang = (l) => { setLang(l); localStorage.setItem('portal_lang', l) }
  return (
    <LangContext.Provider value={lang}>
      <ClientAuthProvider>
        <PortalClienteInner changeLang={changeLang} currentLang={lang} />
      </ClientAuthProvider>
    </LangContext.Provider>
  )
}

function PortalClienteInner({ changeLang, currentLang }) {
  const _toast = useToast()
  const { client } = useClientAuth()
  return client
    ? <PortalApp changeLang={changeLang} currentLang={currentLang} />
    : <LoginScreen changeLang={changeLang} currentLang={currentLang} />
}
