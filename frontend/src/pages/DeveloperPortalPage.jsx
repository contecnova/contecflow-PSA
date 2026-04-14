/**
 * DeveloperPortalPage — Manage OAuth2 applications
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, EmptyState, Spinner } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import { openConfirmGlobal } from '../context/ConfirmContext'

const FS = {
  width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13,
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
}
const LS = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
const MONO = { fontFamily: "'Space Mono', monospace", background: 'var(--surface-3)', borderRadius: 6, padding: '6px 10px', fontSize: 12, color: 'var(--text-1)', border: '1px solid var(--surface-4)', wordBreak: 'break-all', display: 'block' }

const AVAILABLE_SCOPES = ['read', 'write', 'projects', 'tasks', 'timesheets', 'billing', 'admin']

function AppModal({ app, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const t = useAppT()
  const isEdit = !!app

  const [f, setF] = useState({
    name: app?.name || '',
    description: app?.description || '',
    homepage_url: app?.homepage_url || '',
    redirect_uris: app?.redirect_uris?.join('\n') || '',
    scopes: app?.scopes || ['read'],
  })
  const [newSecret, setNewSecret] = useState(null)

  const set = k => e => setF(p => ({ ...p, [k]: e.target.value }))
  const toggleScope = (s) => setF(p => ({
    ...p,
    scopes: p.scopes.includes(s) ? p.scopes.filter(x => x !== s) : [...p.scopes, s],
  }))

  const { mutate, isPending } = useMutation({
    mutationFn: (data) => {
      const payload = { ...data, redirect_uris: data.redirect_uris.split('\n').map(u => u.trim()).filter(Boolean) }
      return isEdit
        ? api.patch(`/developer/apps/${app.id}`, payload).then(r => r.data)
        : api.post('/developer/apps', payload).then(r => r.data)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries(['developer-apps'])
      toast.success(isEdit ? t('developer.app_updated') : t('developer.app_created'))
      if (saved.client_secret) {
        setNewSecret({ client_id: saved.client_id, client_secret: saved.client_secret })
      } else {
        onClose()
      }
    },
    onError: e => toast.error(extractErr(e, t('developer.app_saved_error'))),
  })

  if (newSecret) return (
    <Modal open title={t('developer.app_created')} onClose={onClose} width={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ background: '#1a3a2a', border: '1px solid #2d6a4f', borderRadius: 10, padding: 16 }}>
          <p style={{ color: '#b7e4c7', fontSize: 13, marginBottom: 12, fontWeight: 600 }}>
            {t('developer.secret_warning')}
          </p>
          <div style={{ marginBottom: 10 }}>
            <label style={{ ...LS, color: '#68d391' }}>{t('developer.client_id')}</label>
            <code style={MONO}>{newSecret.client_id}</code>
          </div>
          <div>
            <label style={{ ...LS, color: '#68d391' }}>{t('developer.client_secret')}</label>
            <code style={MONO}>{newSecret.client_secret}</code>
          </div>
        </div>
        <Button onClick={onClose}>{t('developer.got_it')}</Button>
      </div>
    </Modal>
  )

  return (
    <Modal open title={isEdit ? t('developer.edit_app', { name: app.name }) : t('developer.new_oauth_app')} onClose={onClose} width={540}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={LS}>{t('developer.app_name_label')}</label>
          <input value={f.name} onChange={set('name')} style={FS} placeholder={t('developer.app_name_placeholder')} />
        </div>
        <div>
          <label style={LS}>{t('developer.app_description_label')}</label>
          <textarea value={f.description} onChange={set('description')} style={{ ...FS, resize: 'vertical' }} rows={2} />
        </div>
        <div>
          <label style={LS}>{t('developer.app_homepage_label')}</label>
          <input value={f.homepage_url} onChange={set('homepage_url')} style={FS} placeholder={t('developer.app_homepage_placeholder')} />
        </div>
        <div>
          <label style={LS}>{t('developer.app_redirect_label')}</label>
          <textarea value={f.redirect_uris} onChange={set('redirect_uris')} style={{ ...FS, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }} rows={3}
            placeholder={t('developer.app_redirect_placeholder')} />
        </div>
        <div>
          <label style={LS}>{t('developer.app_scopes_label')}</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {AVAILABLE_SCOPES.map(s => (
              <button key={s} onClick={() => toggleScope(s)} style={{
                padding: '5px 12px', borderRadius: 20, border: `1px solid ${f.scopes.includes(s) ? 'var(--accent)' : 'var(--surface-4)'}`,
                background: f.scopes.includes(s) ? 'var(--accent-muted)' : 'transparent',
                color: f.scopes.includes(s) ? 'var(--accent)' : 'var(--text-2)',
                fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
              }}>{s}</button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>{t('developer.cancel_btn')}</Button>
          <Button onClick={() => mutate(f)} disabled={isPending || !f.name || f.scopes.length === 0} loading={isPending}>
            {isEdit ? t('developer.save_btn') : t('developer.create_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function AppDetail({ app, onClose, onRotated }) {
  const toast = useToast()
  const t = useAppT()
  const { mutate: rotate, isPending: rotating } = useMutation({
    mutationFn: () => api.post(`/developer/apps/${app.id}/rotate-secret`).then(r => r.data),
    onSuccess: (data) => onRotated(data),
    onError: e => toast.error(extractErr(e, t('developer.secret_rotated_error'))),
  })

  const copy = (text) => { navigator.clipboard.writeText(text); toast.success(t('developer.copied')) }

  return (
    <Modal open title={t('developer.credentials_modal_title', { name: app.name })} onClose={onClose} width={540}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label style={LS}>{t('developer.client_id')}</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <code style={{ ...MONO, flex: 1 }}>{app.client_id}</code>
            <Button variant="secondary" onClick={() => copy(app.client_id)} style={{ fontSize: 12, flexShrink: 0 }}>{t('developer.copy_btn')}</Button>
          </div>
        </div>
        <div>
          <label style={LS}>{t('developer.client_secret')}</label>
          <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>{t('developer.secret_not_shown')}</p>
          <Button variant="secondary" onClick={() => openConfirmGlobal({
            title: t('developer.rotate_confirm_title'),
            message: t('developer.rotate_confirm_message'),
            onConfirm: () => rotate(),
          })} loading={rotating}>
            {t('developer.rotate_secret_btn')}
          </Button>
        </div>
        <div>
          <label style={LS}>{t('developer.token_endpoint')}</label>
          <code style={MONO}>{window.location.origin}/api/v1/developer/token</code>
        </div>
        <div>
          <label style={LS}>{t('developer.userinfo_endpoint')}</label>
          <code style={MONO}>{window.location.origin}/api/v1/developer/userinfo</code>
        </div>
        <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: 12, fontSize: 12, color: 'var(--text-2)' }}>
          <strong>{t('developer.client_credentials_example')}</strong>
          <pre style={{ marginTop: 8, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--text-1)' }}>{`POST /api/v1/developer/token
Content-Type: application/json

{
  "grant_type": "client_credentials",
  "client_id": "${app.client_id}",
  "client_secret": "<tu_secreto>",
  "scope": "${app.scopes?.join(' ') || 'read'}"
}`}</pre>
        </div>
      </div>
    </Modal>
  )
}

export default function DeveloperPortalPage() {
  const toast = useToast()
  const t = useAppT()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [viewCreds, setViewCreds] = useState(null)
  const [rotatedSecret, setRotatedSecret] = useState(null)

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ['developer-apps'],
    queryFn: () => api.get('/developer/apps').then(r => r.data),
  })

  const { mutate: deleteApp } = useMutation({
    mutationFn: (id) => api.delete(`/developer/apps/${id}`),
    onSuccess: () => { qc.invalidateQueries(['developer-apps']); toast.success(t('developer.app_deleted')) },
    onError: e => toast.error(extractErr(e, t('developer.app_delete_error'))),
  })

  return (
    <div style={{ padding: 32, maxWidth: 960, margin: '0 auto' }}>
      <PageHeader
        title={t('developer.portal_title')}
        subtitle={t('developer.portal_subtitle')}
        actions={<Button onClick={() => setShowCreate(true)}>{t('developer.new_app_btn')}</Button>}
      />

      {isLoading ? <Spinner /> : apps.length === 0 ? (
        <EmptyState
          title={t('developer.no_apps')}
          subtitle={t('developer.no_apps_subtitle')}
          action={<Button onClick={() => setShowCreate(true)}>{t('developer.create_app_btn')}</Button>}
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16, marginTop: 8 }}>
          {apps.map(app => (
            <div key={app.id} style={{
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 12, padding: 20,
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{app.name}</div>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                  background: app.is_active ? '#2d6a4f' : 'var(--surface-4)',
                  color: app.is_active ? '#b7e4c7' : 'var(--text-3)',
                }}>{app.is_active ? t('developer.app_card_active') : t('developer.app_card_inactive')}</span>
              </div>
              {app.description && <p style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10, lineHeight: 1.4 }}>{app.description}</p>}
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>{t('developer.client_id')}</div>
                <code style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-2)' }}>{app.client_id}</code>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12 }}>
                {app.scopes?.map(s => (
                  <span key={s} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: 'var(--surface-3)', color: 'var(--text-2)', border: '1px solid var(--surface-4)' }}>{s}</span>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Button variant="secondary" onClick={() => setViewCreds(app)} style={{ fontSize: 12 }}>{t('developer.credentials_btn')}</Button>
                <Button variant="secondary" onClick={() => setEditing(app)} style={{ fontSize: 12 }}>{t('developer.edit_btn')}</Button>
                <Button variant="danger" style={{ fontSize: 12 }} onClick={() =>
                  openConfirmGlobal({ title: t('developer.delete_app_title'), message: t('developer.delete_app_confirm', { name: app.name }), onConfirm: () => deleteApp(app.id) })
                }>{t('developer.delete_btn')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <AppModal onClose={() => setShowCreate(false)} />}
      {editing   && <AppModal app={editing} onClose={() => setEditing(null)} />}
      {viewCreds && !rotatedSecret && (
        <AppDetail app={viewCreds} onClose={() => setViewCreds(null)} onRotated={(d) => setRotatedSecret(d)} />
      )}
      {rotatedSecret && (
        <Modal open title={t('developer.new_secret_generated')} onClose={() => { setRotatedSecret(null); setViewCreds(null) }} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ background: '#1a3a2a', border: '1px solid #2d6a4f', borderRadius: 10, padding: 14 }}>
              <p style={{ color: '#b7e4c7', fontSize: 13, marginBottom: 10, fontWeight: 600 }}>
                {t('developer.save_new_secret')}
              </p>
              <label style={{ ...LS, color: '#68d391' }}>{t('developer.client_secret')}</label>
              <code style={{ ...MONO }}>{rotatedSecret.client_secret}</code>
            </div>
            <Button onClick={() => { setRotatedSecret(null); setViewCreds(null) }}>{t('developer.understood_btn')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
