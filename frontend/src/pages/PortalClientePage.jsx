/**
 * PortalClientePage – The external-facing client portal.
 * Accessed at /portal — uses separate client auth (ClientUser, not User).
 * This is what the CLIENT sees, not the internal team.
 *
 * Shared context, auth, API client, and styles live in portal-client/portalClientContext.jsx
 */
import { extractErr } from '../utils/helpers'
import { useState, useEffect } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../i18n/AppLangContext'
import {
  CLIENT_API, LangContext, useLang, useClientAuth,
  ClientAuthProvider, S, LoginScreen,
} from './portal-client/portalClientContext'
import { PortalDashboard } from './portal-client/PortalContentSections'
import {
  PortalUAT,
  PortalFeatureRequests,
  PortalMessages,
  PortalInvoices,
  PortalRoadmap,
  PortalDocuments,
  PortalWiki,
} from './portal-client/PortalAdvancedSections'
import { PortalSupportDesk } from './portal-client/PortalSupportDesk'

function PortalApp({ changeLang, _currentLang }) {
  const { client, logout } = useClientAuth()
  const qc = useQueryClient()
  const t = useLang()
  const [section, setSection] = useState('dashboard')

  const { data: branding } = useQuery({
    queryKey: ['portal-branding'],
    queryFn: () => CLIENT_API.get('/portal/branding').then(r => r.data),
    enabled: !!client,
  })

  const { data: surveys = [] } = useQuery({
    queryKey: ['portal-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
    enabled: !!client,
  })
  const pendingSurveys = surveys.filter(s => s.status === 'pending').length

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
            }
          } catch {
            // Ignore malformed payloads from network middleboxes.
          }
        }

        socket.onclose = (ev) => {
          if (cancelled) return
          // Only reconnect on abnormal close; skip if server rejected (4xx-equiv code 4003/1008)
          if (ev.code === 1000 || ev.code === 1001) return
          const delay = Math.min(1000 * 2 ** (attempt - 1), 30000)
          reconnectTimer = window.setTimeout(connect, delay)
        }

        socket.onerror = () => {
          // onerror is always followed by onclose — reconnect logic handled there
        }

        if (pingInterval) window.clearInterval(pingInterval)
        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      } catch {
        // WS is optional; portal works with polling queries.
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

  const SECTIONS = [
    { id: 'dashboard', icon: '◈',  label: t('nav_dashboard') },
    { id: 'uat',       icon: '🧪', label: t('nav_uat') },
    { id: 'requests',  icon: '💡', label: t('nav_requests') },
    { id: 'roadmap',   icon: '🗺️', label: t('nav_roadmap') },
    { id: 'wiki',      icon: '📚', label: t('nav_wiki') },
    { id: 'documents', icon: '📄', label: t('nav_documents') },
    { id: 'invoices',  icon: '🧾', label: 'Facturas' },
    { id: 'support',   icon: '🛎️', label: t('nav_support') },
    { id: 'messages',  icon: '💬', label: t('nav_messages') },
    { id: 'profile',   icon: '⚙️', label: 'Mi perfil' },
  ]

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--surface-0)' }}>
      {/* Sidebar */}
      <aside style={{ width: 220, background: 'var(--portal-deep)', borderRight: '1px solid var(--surface-4)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '20px 20px', borderBottom: '1px solid var(--surface-4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            {branding?.logo_url ? (
              <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} style={{ width: 28, height: 28, borderRadius: 7, objectFit: 'cover', border: '1px solid var(--surface-4)' }} />
            ) : (
              <div style={{ width: 28, height: 28, background: `linear-gradient(135deg, ${branding?.primary_color || '#4f8ef7'}, var(--surface-0))`, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 800 }}>◈</div>
            )}
            <span style={{ fontWeight: 800, fontSize: "var(--text-lg-em)" }}>{branding?.brand_name || t('portal')}</span>
          </div>
        </div>

        <nav style={{ flex: 1, padding: '12px 10px' }}>
          {SECTIONS.map(s => (
            <button key={s.id} onClick={() => setSection(s.id)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, border: `1px solid ${section === s.id ? 'var(--accent-glow)' : 'transparent'}`, background: section === s.id ? 'var(--accent-muted)' : 'transparent', color: section === s.id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-base)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', marginBottom: 2, textAlign: 'left' }}>
              <span style={{ fontSize: "var(--text-lg)" }}>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </nav>

        <div style={{ padding: '12px 10px', borderTop: '1px solid var(--surface-4)' }}>
          <div style={{ padding: '8px 12px', marginBottom: 4, display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
              {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{client?.full_name}</div>
              <button onClick={() => setSection('profile')} style={{ background: 'none', border: 'none', padding: 0, fontSize: "var(--text-sm)", color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>⚙️ Mi perfil</button>
            </div>
          </div>
          <button onClick={logout} style={{ ...S.btnSec, width: '100%', padding: '8px 12px', fontSize: "var(--text-base)" }}>⏻ {t('logout')}</button>
        </div>
      </aside>

      {/* Content */}
      <main style={{ flex: 1, overflowY: 'auto', padding: 32, color: 'var(--text-1)' }}>
        {pendingSurveys > 0 && (
          <button type="button" style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 10, padding: '12px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', width: '100%', textAlign: 'left', fontFamily: 'inherit' }} onClick={() => setSection('surveys')}>
            <span style={{ fontSize: "var(--text-2xl)" }}>⭐</span>
            <div>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--success)' }}>Tienes {pendingSurveys} encuesta(s) pendiente(s)</div>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>Tu opinión nos ayuda a mejorar. Solo toma 1 minuto.</div>
            </div>
          </button>
        )}

        {section === 'dashboard'  && <PortalDashboard />}
        {section === 'uat'        && <PortalUAT />}
        {section === 'requests'   && <PortalFeatureRequests />}
        {section === 'roadmap'    && <PortalRoadmap />}
        {section === 'wiki'       && <PortalWiki />}
        {section === 'documents'  && <PortalDocuments />}
        {section === 'invoices'   && <PortalInvoices />}
        {section === 'support'    && <PortalSupportDesk />}
        {section === 'messages'   && <PortalMessages />}
        {section === 'profile'    && <PortalMyProfile changeLang={changeLang} />}
      </main>
    </div>
  )
}

// ── Mi Perfil (cliente) ───────────────────────────────────────────────────────
function PortalMyProfile({ changeLang }) {
  const { client } = useClientAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('profile')
  const [form, setForm] = useState({
    full_name: client?.full_name || '',
    phone: client?.phone || '',
    job_title: client?.job_title || '',
  })
  const [pendingLang, setPendingLang] = useState(client?.language || 'es')
  const [pwdForm, setPwdForm]   = useState({ current: '', new_pwd: '', confirm: '' })
  const [savedProfile, setSavedProfile] = useState(false)
  const [savedLanguage, setSavedLanguage] = useState(false)
  const [pwdError, setPwdError] = useState('')
  const [themeMode, setThemeMode] = useState(() => localStorage.getItem('portal_theme_mode') || 'freight')

  // Obtener config del portal para saber qué puede editar
  const { data: me } = useQuery({
    queryKey: ['portal-me'],
    queryFn: () => CLIENT_API.get('/portal/auth/me').then(r => r.data),
  })

  const LANGUAGES = [
    { code: 'es', label: 'Español' }, { code: 'en', label: 'English' },
    { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' },
    { code: 'pt', label: 'Português' }, { code: 'it', label: 'Italiano' },
    { code: 'pl', label: 'Polski' }, { code: 'zh', label: '中文' },
  ]

  const THEMES = [
    { id: 'freight', label: 'Freight Pro', icon: '🚚', desc: 'Tema principal de Contecflow' },
    { id: 'dark', label: 'Oscuro', icon: '🌙', desc: 'Estilo oscuro clásico' },
    { id: 'midnight', label: 'Midnight', icon: '🌌', desc: 'Oscuro profundo' },
    { id: 'slate', label: 'Slate', icon: '⬛', desc: 'Gris neutro' },
    { id: 'light', label: 'Claro', icon: '☀️', desc: 'Fondo claro' },
    { id: 'high-contrast', label: 'Alto contraste', icon: '◑', desc: 'Máxima legibilidad' },
    { id: 'system', label: 'Sistema', icon: '💻', desc: 'Sigue tu sistema operativo' },
  ]

  const applyTheme = (themeId) => {
    setThemeMode(themeId)
    if (themeId === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
    } else {
      document.documentElement.setAttribute('data-theme', themeId)
    }
  }

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
    onSuccess: () => { setPwdForm({ current: '', new_pwd: '', confirm: '' }); toast.success('✅ Contraseña actualizada correctamente') },
    onError: e => { const raw = e?.response?.data?.detail; setPwdError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'Error al cambiar contraseña')) },
  })

  const handlePwdChange = () => {
    setPwdError('')
    if (pwdForm.new_pwd !== pwdForm.confirm) { setPwdError('Las contraseñas no coinciden'); return }
    if (pwdForm.new_pwd.length < 6) { setPwdError('La contraseña debe tener al menos 6 caracteres'); return }
    savePwd(pwdForm)
  }

  const saveAppearance = () => {
    localStorage.setItem('portal_theme_mode', themeMode)
    applyTheme(themeMode)
    toast.success('Apariencia guardada')
  }

  const TABS = [
    { id: 'profile',  label: '👤 Perfil' },
    { id: 'appearance', label: '🎨 Apariencia' },
    { id: 'language', label: '🌐 Idioma' },
    { id: 'security', label: 'Seguridad' },
  ]

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, marginBottom: 4 }}>Mi perfil</div>
        <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>Gestiona tus datos personales y preferencias</div>
      </div>

      {/* Avatar + info rápida */}
      <div style={{ ...S.card, display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20 }}>
        <div style={{ width: 56, height: 56, borderRadius: 14, background: 'linear-gradient(135deg, var(--accent-border), var(--purple-border))', border: '1px solid var(--accent-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-2xl)", fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
          {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
        </div>
        <div>
          <div style={{ fontSize: "var(--text-17)", fontWeight: 800 }}>{client?.full_name}</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{client?.email}</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
            {client?.job_title && `${client.job_title} · `}{client?.company}
          </div>
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--surface-4)', paddingBottom: 10 }}>
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${tab === tb.id ? 'var(--accent-glow)' : 'transparent'}`,
              background: tab === tb.id ? 'var(--accent-muted)' : 'transparent', color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: "var(--text-sm)", fontWeight: tab === tb.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            {tb.label}
          </button>
        ))}
      </div>

      {/* Tab: Perfil */}
      {tab === 'profile' && (
        <div style={S.card}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Información personal</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
            <div>
              <label style={S.label}>Nombre visible</label>
              <input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={S.input} />
            </div>
            <div>
              <label style={S.label}>Cargo / Rol</label>
              <input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={S.input} />
            </div>
            <div>
              <label style={S.label}>Teléfono</label>
              <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} style={S.input} placeholder="Teléfono" />
            </div>
          </div>
          <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--surface-4)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
            🔒 El email (<strong style={{ color: 'var(--text-1)' }}>{client?.email}</strong>) es tu identificador de acceso y no puede modificarse. Contacta con el equipo si necesitas cambiarlo.
          </div>
          {savedProfile && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--success)' }}>
              ✅ Perfil actualizado correctamente
            </div>
          )}
          <button onClick={() => saveProfile(form)} disabled={saving}
            style={{ ...S.btn, opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Guardando...' : '💾 Guardar cambios'}
          </button>

          <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--surface-4)' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Mi acceso</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>Estos permisos son asignados por tu gestor.</div>
            {[
              { key: 'can_approve_deliverables', label: 'Aprobar entregables' },
              { key: 'can_request_changes', label: 'Solicitar cambios' },
              { key: 'can_view_budget', label: 'Ver presupuesto' },
              { key: 'can_view_team', label: 'Ver equipo' },
            ].map(p => (
              <div key={p.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, padding: '8px 10px', background: 'var(--surface-4)', borderRadius: 8 }}>
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{p.label}</span>
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: me?.[p.key] ? 'var(--success)' : 'var(--text-3)' }}>{me?.[p.key] ? 'Sí' : 'No'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Apariencia */}
      {tab === 'appearance' && (
        <div style={S.card}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Tema del portal</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
            {THEMES.map(th => (
              <button
                key={th.id}
                onClick={() => applyTheme(th.id)}
                style={{
                  textAlign: 'left',
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: `1px solid ${themeMode === th.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  background: themeMode === th.id ? 'var(--accent-muted)' : 'var(--surface-1)',
                  color: themeMode === th.id ? 'var(--accent)' : 'var(--text-2)',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 2 }}>{th.icon} {th.label}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{th.desc}</div>
              </button>
            ))}
          </div>
          <button onClick={saveAppearance} style={S.btn}>🎨 Guardar apariencia</button>
        </div>
      )}

      {/* Tab: Idioma */}
      {tab === 'language' && (
        <div style={S.card}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Idioma del portal</div>
          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>Selecciona idioma</label>
            <select value={pendingLang} onChange={e => setPendingLang(e.target.value)} style={S.input}>
              {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          {savedLanguage && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--success)' }}>
              ✅ Idioma actualizado correctamente
            </div>
          )}
          <button onClick={() => saveLanguage(pendingLang)} disabled={savingLanguage}
            style={{ ...S.btn, opacity: savingLanguage ? 0.6 : 1 }}>
            {savingLanguage ? 'Guardando...' : '🌐 Guardar idioma'}
          </button>
        </div>
      )}

      {/* Tab: Seguridad */}
      {tab === 'security' && (
        <div style={S.card}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Cambiar contraseña</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={S.label}>Nueva contraseña</label>
              <input type="password" value={pwdForm.new_pwd} onChange={e => setPwdForm(f => ({ ...f, new_pwd: e.target.value }))} style={S.input} placeholder="Nueva contraseña" />
            </div>
            <div>
              <label style={S.label}>Confirmar nueva contraseña</label>
              <input type="password" value={pwdForm.confirm} onChange={e => setPwdForm(f => ({ ...f, confirm: e.target.value }))} style={S.input} />
            </div>
          </div>
          {pwdError && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--danger)' }}>
              ✗ {pwdError}
            </div>
          )}
          <button onClick={handlePwdChange} disabled={changingPwd || !pwdForm.new_pwd || !pwdForm.confirm}
            style={{ ...S.btn, opacity: (changingPwd || !pwdForm.new_pwd) ? 0.6 : 1 }}>
            {changingPwd ? 'Actualizando...' : '🔑 Cambiar contraseña'}
          </button>
          <div style={{ marginTop: 16, fontSize: "var(--text-xs)", color: 'var(--text-3)', lineHeight: 1.6 }}>
            Elige una contraseña segura que no uses en otros servicios. Si olvidas tu contraseña, contacta con el equipo para que te la restablezcan.
          </div>
        </div>
      )}

    </div>
  )
}


// ── Root export ───────────────────────────────────────────────────────────────
export default function PortalClientePage() {
  const _t = useAppT()
  const [lang, setLang] = useState(() => {
    // Prioridad: idioma del perfil del cliente > localStorage > 'es'
    try {
      const savedClient = JSON.parse(localStorage.getItem('client_user') || 'null')
      if (savedClient?.language) return savedClient.language
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
  return client ? <PortalApp changeLang={changeLang} currentLang={currentLang} /> : <LoginScreen changeLang={changeLang} currentLang={currentLang} />
}
