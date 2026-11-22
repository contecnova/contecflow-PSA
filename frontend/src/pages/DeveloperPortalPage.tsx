/**
 * DeveloperPortalPage — Manage OAuth2 applications
 */
import { useState, useId } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { developerAppsApi, apiUrl, apiUrlAbsoluta } from '../services/api'
import type { AplicacionOAuth, SecretoRotado } from '../services/api/tipos-plataforma'
import { Button, Modal, EmptyState, Spinner, StatusBadge, Pulsable, useErroresDeCampo, Input, Textarea } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, AppWindow, Code2, Copy, Plus, RotateCw } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAppT } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import { openConfirmGlobal } from '../context/ConfirmContext'
import './DeveloperPortalPage.css'

interface AppFormState {
  name: string
  description: string
  homepage_url: string
  redirect_uris: string
  scopes: string[]
}


// Los de app/core/credenciales_delegadas.py (ALCANCES_VALIDOS); faltaba `expenses`.
const AVAILABLE_SCOPES = ['read', 'write', 'projects', 'tasks', 'timesheets', 'billing', 'expenses', 'admin']

function AppModal({ app, onClose }: { app?: AplicacionOAuth | null; onClose: () => void }) {
  const idCampo = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const t = useAppT()
  const isEdit = !!app

  const [f, setF] = useState<AppFormState>({
    name: app?.name || '',
    description: app?.description || '',
    homepage_url: app?.homepage_url || '',
    redirect_uris: app?.redirect_uris?.join('\n') || '',
    scopes: app?.scopes || ['read'],
  })
  const [newSecret, setNewSecret] = useState<SecretoRotado | null>(null)

  const set = (k: keyof AppFormState) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF((p) => ({ ...p, [k]: e.target.value }))
  const toggleScope = (s: string) => setF(p => ({
    ...p,
    scopes: p.scopes.includes(s) ? p.scopes.filter(x => x !== s) : [...p.scopes, s],
  }))

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: AppFormState) => {
      const payload = { ...data, redirect_uris: data.redirect_uris.split('\n').map(u => u.trim()).filter(Boolean) }
      return isEdit
        ? developerAppsApi.update(app.id, payload).then(r => r.data)
        : developerAppsApi.create(payload).then(r => r.data)
    },
    onSuccess: (saved: AplicacionOAuth) => {
      qc.invalidateQueries({ queryKey: ['developer-apps'] })
      toast.success(isEdit ? t('developer.app_updated') : t('developer.app_created'))
      if (saved.client_secret) {
        setNewSecret({ client_id: saved.client_id, client_secret: saved.client_secret })
      } else {
        onClose()
      }
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('developer.app_saved_error'))) },
  })

  if (newSecret) return (
    <Modal open title={t('developer.app_created')} onClose={onClose} width={520}>
      <div className="u-stack-16">
        <div className="devp-card">
          <p className="devp-text">
            <AlertTriangle size={14} aria-hidden /> {t('developer.secret_warning')}
          </p>
          <div className="u-mb-10">
            <label className="developer-portal-page-e1">{t('developer.client_id')}</label>
            <code className="ds-codigo developer-portal-page-e6">{newSecret.client_id}</code>
          </div>
          <div>
            <label className="developer-portal-page-e1">{t('developer.client_secret')}</label>
            <code className="ds-codigo developer-portal-page-e6">{newSecret.client_secret}</code>
          </div>
        </div>
        <Button onClick={onClose}>{t('developer.got_it')}</Button>
      </div>
    </Modal>
  )

  return (
    <Modal open title={isEdit ? t('developer.edit_app', { name: app.name }) : t('developer.new_oauth_app')} onClose={onClose} width={540}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="developer-portal-page-e7">{t('developer.app_name_label')}</label>
          <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={f.name} onChange={set('name')} placeholder={t('developer.app_name_placeholder')} inputClassName="developer-portal-page-e8" />{msg('name')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="developer-portal-page-e7">{t('developer.app_description_label')}</label>
          <Textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={f.description} onChange={set('description')} rows={2} inputClassName="developer-portal-page-e2" />{msg('description')}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="developer-portal-page-e7">{t('developer.app_homepage_label')}</label>
          <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={f.homepage_url} onChange={set('homepage_url')} placeholder={t('developer.app_homepage_placeholder')} inputClassName="developer-portal-page-e8" />{msg('homepage_url')}
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="developer-portal-page-e7">{t('developer.app_redirect_label')}</label>
          <Textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={f.redirect_uris} onChange={set('redirect_uris')} rows={3} placeholder={t('developer.app_redirect_placeholder')} inputClassName="ds-codigo developer-portal-page-e3" />{msg('redirect_uris')}
        </div>
        <div>
          <label className="developer-portal-page-e7">{t('developer.app_scopes_label')}</label>
          <div className="u-wrap-8">
            {AVAILABLE_SCOPES.map(s => (
              <Pulsable type="button" key={s} aria-pressed={f.scopes.includes(s)} onClick={() => toggleScope(s)} className={`devp-btn develope-sx3 ${f.scopes.includes(s) ? 'develope-sx4' : 'develope-sx5'} developer-portal-page-e4`} style={{ '--developer-portal-page-border': `1px solid ${f.scopes.includes(s) ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>{t(`developer.scope_${s}`)}</Pulsable>
            ))}
          </div>
        </div>
        <div className="devp-row">
          <Button variant="secondary" onClick={onClose}>{t('developer.cancel_btn')}</Button>
          <Button onClick={() => mutate(f)} disabled={isPending || !f.name || f.scopes.length === 0} loading={isPending}>
            {isEdit ? t('developer.save_btn') : t('developer.create_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function AppDetail({ app, onClose, onRotated }: { app: AplicacionOAuth; onClose: () => void; onRotated: (data: SecretoRotado) => void }) {
  const toast = useToast()
  const t = useAppT()
  const { mutate: rotate, isPending: rotating } = useMutation({
    mutationFn: () => developerAppsApi.rotateSecret(app.id).then(r => r.data),
    onSuccess: (data: SecretoRotado) => onRotated(data),
    onError: (e: unknown) => toast.error(extractErr(e, t('developer.secret_rotated_error'))),
  })

  const copy = (text?: string) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    toast.success(t('developer.copied'))
  }

  return (
    <Modal open title={t('developer.credentials_modal_title', { name: app.name })} onClose={onClose} width={540}>
      <div className="u-stack-16">
        <div>
          <label className="developer-portal-page-e7">{t('developer.client_id')}</label>
          <div className="u-row-center-8">
            <code className="ds-codigo developer-portal-page-e5">{app.client_id}</code>
            <Button variant="secondary" icon={<Copy size={14} />} onClick={() => copy(app.client_id)} className="develope-sx1">{t('developer.copy_btn')}</Button>
          </div>
        </div>
        <div>
          <label className="developer-portal-page-e7">{t('developer.client_secret')}</label>
          <p className="devp-text-2">{t('developer.secret_not_shown')}</p>
          <Button variant="secondary" icon={<RotateCw size={14} />} onClick={() => openConfirmGlobal({
            title: t('developer.rotate_confirm_title'),
            message: t('developer.rotate_confirm_message'),
            onConfirm: () => rotate(),
          })} loading={rotating}>
            {t('developer.rotate_secret_btn')}
          </Button>
        </div>
        <div>
          <label className="developer-portal-page-e7">{t('developer.token_endpoint')}</label>
          <code className="ds-codigo developer-portal-page-e6">{apiUrlAbsoluta('/developer/token')}</code>
        </div>
        <div>
          <label className="developer-portal-page-e7">{t('developer.userinfo_endpoint')}</label>
          <code className="ds-codigo developer-portal-page-e6">{apiUrlAbsoluta('/developer/userinfo')}</code>
        </div>
        <div className="devp-card-2">
          <strong>{t('developer.client_credentials_example')}</strong>
          <pre className="ds-codigo ds-codigo--bloque devp-box">{`POST ${apiUrl('/developer/token')}
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

export default function DeveloperPortalPage(): JSX.Element {
  const toast = useToast()
  const t = useAppT()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<AplicacionOAuth | null>(null)
  const [viewCreds, setViewCreds] = useState<AplicacionOAuth | null>(null)
  const [rotatedSecret, setRotatedSecret] = useState<SecretoRotado | null>(null)

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ['developer-apps'],
    queryFn: () => developerAppsApi.list().then(r => r.data),
  })

  const { mutate: deleteApp } = useMutation({
    mutationFn: (id: string | number) => developerAppsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['developer-apps'] }); toast.success(t('developer.app_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('developer.app_delete_error'))),
  })

  return (
    <PageShell>
      <PageHeader
        icon={<Code2 size={18} />}
        title={t('nav.developer_portal')}
        subtitle={t('developer.portal_subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('developer.new_app_btn')}</Button>}
        showListExport={apps.length > 0}
        exportTargetSelector='[data-export-table="developer-apps-list"]'
        exportFilePrefix='developer_apps'
      />

      {isLoading ? <Spinner /> : apps.length === 0 ? (
        <EmptyState
          icon={<AppWindow size={28} />}
          title={t('developer.no_apps')}
          description={t('developer.no_apps_subtitle')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('developer.new_app_btn')}</Button>}
        />
      ) : (
        <div data-export-table="developer-apps-list" className="devp-grid">
          {apps.map(app => (
            <div key={app.id} className="devp-card-3">
              <div className="devp-row-2">
                <div className="devp-box-2">{app.name}</div>
                <StatusBadge kind={app.is_active ? 'success' : 'neutral'}>{app.is_active ? t('developer.app_card_active') : t('developer.app_card_inactive')}</StatusBadge>
              </div>
              {app.description && <p className="devp-text-3">{app.description}</p>}
              <div className="u-mb-10">
                <div className="devp-box-3">{t('developer.client_id')}</div>
                <code className="ds-codigo u-text2-mono-xs">{app.client_id}</code>
              </div>
              <div className="devp-row-3">
                {app.scopes?.map(s => (
                  <span key={s} className="devp-card-4">{AVAILABLE_SCOPES.includes(s) ? t(`developer.scope_${s}`) : s}</span>
                ))}
              </div>
              <div className="u-wrap-8">
                <Button variant="secondary" onClick={() => setViewCreds(app)} className="develope-sx2">{t('developer.credentials_btn')}</Button>
                <Button variant="secondary" onClick={() => setEditing(app)} className="develope-sx2">{t('developer.edit_btn')}</Button>
                <Button variant="danger" className="develope-sx2" onClick={() =>
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
          <div className="u-stack-12">
            <div className="devp-card-5">
              <p className="devp-text-4">
                <AlertTriangle size={14} aria-hidden /> {t('developer.save_new_secret')}
              </p>
              <label className="developer-portal-page-e1">{t('developer.client_secret')}</label>
              <code className="ds-codigo developer-portal-page-e6">{rotatedSecret.client_secret}</code>
            </div>
            <Button onClick={() => { setRotatedSecret(null); setViewCreds(null) }}>{t('developer.understood_btn')}</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
