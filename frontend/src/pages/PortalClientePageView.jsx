/**
 * PortalClientePage – The external-facing client portal.
 * Accessed at /portal — uses separate client auth (ClientUser, not User).
 * This is what the CLIENT sees, not the internal team.
 *
 * Shared context, auth, API client, and styles live in portal-client/portalClientContext.js
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
  PortalStats,
} from './portal-client/PortalAdvancedSections'
import { PortalSupportDesk } from './portal-client/PortalSupportDesk'

function PortalApp({ changeLang, _currentLang }) {
  const { client, logout } = useClientAuth()
  const toast = useToast()
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
    let cancelled = false

    const connect = async () => {
      try {
        const ticketRes = await CLIENT_API.get('/ws/portal-ticket')
        const ticket = ticketRes?.data?.ticket
        if (!ticket || cancelled) return

        const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = `${wsProto}://${window.location.host}/api/v1/ws/portal-notifications?ticket=${encodeURIComponent(ticket)}`
        socket = new window.WebSocket(wsUrl)

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

        socket.onerror = () => {
          toast.error('No se pudo conectar al canal realtime del portal')
        }

        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      } catch {
        // WS is optional; portal works with polling queries.
      }
    }

    connect()
    return () => {
      cancelled = true
      if (pingInterval) window.clearInterval(pingInterval)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
    }
  }, [client, qc, toast])

  const SECTIONS = [
    { id: 'dashboard', icon: '◈',  label: t('nav_dashboard') },
    { id: 'stats',     icon: '📊', label: t('nav_stats') },
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
      <aside style={{ width: 220, background: 'var(--portal-deep)', borderRight: '1px solid #1a2640', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '20px 20px', borderBottom: '1px solid #1a2640' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            {branding?.logo_url ? (
              <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} style={{ width: 28, height: 28, borderRadius: 7, objectFit: 'cover', border: '1px solid #1a2640' }} />
            ) : (
              <div style={{ width: 28, height: 28, background: `linear-gradient(135deg, ${branding?.primary_color || '#00d4ff'}, #0f172a)`, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800 }}>◈</div>
            )}
            <span style={{ fontWeight: 800, fontSize: 14 }}>{branding?.brand_name || t('portal')}</span>
          </div>
        </div>

        <nav style={{ flex: 1, padding: '12px 10px' }}>
          {SECTIONS.map(s => (
            <button key={s.id} onClick={() => setSection(s.id)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, border: `1px solid ${section === s.id ? 'var(--accent-glow)' : 'transparent'}`, background: section === s.id ? 'var(--accent-muted)' : 'transparent', color: section === s.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', marginBottom: 2, textAlign: 'left' }}>
              <span style={{ fontSize: 15 }}>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </nav>

        <div style={{ padding: '12px 10px', borderTop: '1px solid #1a2640' }}>
          <div style={{ padding: '8px 12px', marginBottom: 4, display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
              {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{client?.full_name}</div>
              <button onClick={() => setSection('profile')} style={{ background: 'none', border: 'none', padding: 0, fontSize: 10, color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>⚙️ Mi perfil</button>
            </div>
          </div>
          <button onClick={logout} style={{ ...S.btnSec, width: '100%', padding: '7px 12px', fontSize: 12 }}>⏻ {t('logout')}</button>
        </div>
      </aside>

      {/* Content */}
      <main style={{ flex: 1, overflowY: 'auto', padding: 32, color: 'var(--text-1)' }}>
        {pendingSurveys > 0 && (
          <button type="button" style={{ background: 'var(--success-bg)', border: '1px solid #00e5a040', borderRadius: 10, padding: '12px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', width: '100%', textAlign: 'left', fontFamily: 'inherit' }} onClick={() => setSection('surveys')}>
            <span style={{ fontSize: 20 }}>⭐</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--success)' }}>Tienes {pendingSurveys} encuesta(s) pendiente(s)</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Tu opinión nos ayuda a mejorar. Solo toma 1 minuto.</div>
            </div>
          </button>
        )}

        {section === 'dashboard'  && <PortalDashboard />}
        {section === 'stats'      && <PortalStats />}
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
  const { client, _login } = useClientAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const _t = useLang()

  const [tab, setTab] = useState('info')
  const [form, setForm] = useState({
    full_name: client?.full_name || '',
    phone: client?.phone || '',
    job_title: client?.job_title || '',
    language: client?.language || 'es',
  })
  const [pwdForm, setPwdForm]   = useState({ current: '', new_pwd: '', confirm: '' })
  const [saved, setSaved]       = useState(false)
  const [pwdError, setPwdError] = useState('')

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

  const { mutate: saveProfile, isPending: saving } = useMutation({
    mutationFn: d => CLIENT_API.patch('/portal/auth/me', d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-me'])
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      // Actualizar el idioma si cambió
      if (form.language !== client?.language) {
        localStorage.setItem('portal_lang', form.language)
        if (changeLang) changeLang(form.language)
        // Actualizar el client guardado en localStorage
        try {
          const saved = JSON.parse(localStorage.getItem('client_user') || '{}')
          saved.language = form.language
          localStorage.setItem('client_user', JSON.stringify(saved))
        } catch { /* noop */ }
        // Recargar para aplicar nuevas traducciones
        window.location.reload()
      }
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
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

  const TABS = [
    { id: 'info',     label: 'Mis datos' },
    { id: 'security', label: 'Seguridad' },
    { id: 'access',   label: 'Mi acceso' },
  ]

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Mi perfil</div>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Gestiona tus datos personales y preferencias</div>
      </div>

      {/* Avatar + info rápida */}
      <div style={{ ...S.card, display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20 }}>
        <div style={{ width: 56, height: 56, borderRadius: 14, background: 'linear-gradient(135deg, #00d4ff30, #7c3aed30)', border: '1px solid #00d4ff30', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
          {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
        </div>
        <div>
          <div style={{ fontSize: 17, fontWeight: 800 }}>{client?.full_name}</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{client?.email}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {client?.job_title && `${client.job_title} · `}{client?.company}
          </div>
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #1a2640', paddingBottom: 10 }}>
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${tab === tb.id ? 'var(--accent-glow)' : 'transparent'}`,
              background: tab === tb.id ? 'var(--accent-muted)' : 'transparent', color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: tab === tb.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            {tb.label}
          </button>
        ))}
      </div>

      {/* Tab: Mis datos */}
      {tab === 'info' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Información personal</div>
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
            <div>
              <label style={S.label}>Idioma del portal</label>
              <select value={form.language} onChange={e => setForm(f => ({ ...f, language: e.target.value }))} style={S.input}>
                {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--surface-4)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
            🔒 El email (<strong style={{ color: 'var(--text-1)' }}>{client?.email}</strong>) es tu identificador de acceso y no puede modificarse. Contacta con el equipo si necesitas cambiarlo.
          </div>
          {saved && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 8, fontSize: 12, color: 'var(--success)' }}>
              ✅ Perfil actualizado correctamente
              {form.language !== client?.language && ' · La página se recargará para aplicar el nuevo idioma'}
            </div>
          )}
          <button onClick={() => saveProfile(form)} disabled={saving}
            style={{ ...S.btn, opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Guardando...' : '💾 Guardar cambios'}
          </button>
        </div>
      )}

      {/* Tab: Seguridad */}
      {tab === 'security' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Cambiar contraseña</div>
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
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, fontSize: 12, color: 'var(--danger)' }}>
              ✗ {pwdError}
            </div>
          )}
          <button onClick={handlePwdChange} disabled={changingPwd || !pwdForm.new_pwd || !pwdForm.confirm}
            style={{ ...S.btn, opacity: (changingPwd || !pwdForm.new_pwd) ? 0.6 : 1 }}>
            {changingPwd ? 'Actualizando...' : '🔑 Cambiar contraseña'}
          </button>
          <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6 }}>
            Elige una contraseña segura que no uses en otros servicios. Si olvidas tu contraseña, contacta con el equipo para que te la restablezcan.
          </div>
        </div>
      )}

      {/* Tab: Mi acceso */}
      {tab === 'access' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Mis permisos en el portal</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>Estos permisos son asignados por tu gestor y no pueden modificarse desde aquí.</div>
          {[
            { key: 'can_approve_deliverables', label: 'Aprobar entregables', desc: 'Puedes validar o rechazar entregables del proyecto' },
            { key: 'can_request_changes', label: '↩ Solicitar cambios', desc: 'Puedes enviar solicitudes de cambio al equipo' },
            { key: 'can_view_budget', label: 'Ver presupuesto', desc: 'Puedes ver el consumo vs presupuesto del proyecto' },
            { key: 'can_view_team', label: 'Ver equipo', desc: 'Puedes ver los miembros del equipo asignado' },
          ].map(p => (
            <div key={p.key} style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, padding: '10px 12px',
              background: me?.[p.key] ? 'var(--success-bg)' : 'var(--surface-4)', border: `1px solid ${me?.[p.key] ? 'var(--success-bg)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
              <span style={{ fontSize: 16 }}>{me?.[p.key] ? '✅' : '⛔'}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: me?.[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.desc}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-4)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
            📧 Email de acceso: <strong style={{ color: 'var(--text-1)' }}>{client?.email}</strong>
            {me?.language && <span style={{ marginLeft: 12 }}>🌍 Idioma: <strong style={{ color: 'var(--text-1)' }}>{me.language.toUpperCase()}</strong></span>}
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
