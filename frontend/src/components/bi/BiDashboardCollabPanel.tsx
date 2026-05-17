/**
 * BiDashboardCollabPanel.jsx — Colaboración en dashboards BI.
 *
 * Endpoints (todos bajo /api/v1):
 *   GET   /bi/collaboration/comments?dashboard_key=&widget_id=&include_resolved=  -> { items, count }
 *   POST  /bi/collaboration/comments                                              { dashboard_key, widget_id, message }
 *   PATCH /bi/collaboration/comments/{id}/resolve
 *   GET   /bi/collaboration/shared-views                                          -> { items }
 *   POST  /bi/collaboration/shared-views                                          { name, dashboard_key, filters }
 *   PATCH /bi/collaboration/shared-views/{id}                                     { active }
 *   GET   /bi/collaboration/dashboards/{key}/shares                               -> { items }
 *   POST  /bi/collaboration/dashboards/{key}/shares                               { target_user_id, target_user_name, permission }
 *   DEL   /bi/collaboration/dashboards/{key}/shares/{shareId}
 *   GET   /bi/collaboration/dashboards/{key}/versions                             -> { items }
 *   POST  /bi/collaboration/dashboards/{key}/versions/{versionId}/restore
 *   GET   /bi/collaboration/notifications?include_read=false                      -> { items }
 *   PATCH /bi/collaboration/notifications/{id}                                    { is_read }
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biCollaborationApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { MessageCircle, Eye, Share2, Plus, Trash2, Lock, CheckCircle, Clock, Bell, History } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'

type ApiError = { response?: { data?: { detail?: string } } }

const SHARE_PERMISSIONS = [
  { value: 'view',  label: 'Ver',     color: 'var(--text-3)' },
  { value: 'edit',  label: 'Editar',  color: 'var(--warning)' },
  { value: 'admin', label: 'Admin',   color: 'var(--danger)' },
]
const PERMISSION_LABEL: Record<string, string> = Object.fromEntries(SHARE_PERMISSIONS.map(p => [p.value, p.label]))
const PERMISSION_COLOR: Record<string, string> = Object.fromEntries(SHARE_PERMISSIONS.map(p => [p.value, p.color]))

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const inputBase: React.CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}
const chip = (color: string): React.CSSProperties => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

interface BiDashboardCollabPanelProps {
  dashboardKey?: string
}

export default function BiDashboardCollabPanel({ dashboardKey = 'main' }: BiDashboardCollabPanelProps) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('comments')
  const [newComment, setNewComment] = useState<string>('')
  const [viewName, setViewName] = useState<string>('')
  const [shareUserId, setShareUserId] = useState<string>('')
  const [shareUserName, setShareUserName] = useState<string>('')
  const [sharePermission, setSharePermission] = useState<string>('view')

  const { data: commentsData, isLoading: commentsLoading } = useQuery({
    queryKey: ['bi-collab-comments', dashboardKey],
    queryFn: () => biCollaborationApi.listComments({ dashboard_key: dashboardKey, include_resolved: false }).then(r => r.data),
  })

  const { data: viewsData, isLoading: viewsLoading } = useQuery({
    queryKey: ['bi-collab-views', dashboardKey],
    queryFn: () => biCollaborationApi.listSharedViews({}).then(r => r.data),
    enabled: tab === 'views',
  })

  const { data: sharesData, isLoading: sharesLoading } = useQuery({
    queryKey: ['bi-collab-shares', dashboardKey],
    queryFn: () => biCollaborationApi.listDashboardShares(dashboardKey).then(r => r.data),
    enabled: tab === 'shares',
  })

  const { data: versionsData, isLoading: versionsLoading } = useQuery({
    queryKey: ['bi-collab-versions', dashboardKey],
    queryFn: () => biCollaborationApi.listDashboardVersions(dashboardKey).then(r => r.data),
    enabled: tab === 'versions',
  })

  const { data: notificationsData, isLoading: notificationsLoading } = useQuery({
    queryKey: ['bi-collab-notifications', dashboardKey],
    queryFn: () => biCollaborationApi.listNotifications({ dashboard_key: dashboardKey, include_read: false }).then(r => r.data),
    enabled: tab === 'notifications',
    refetchInterval: 15_000,
  })

  const addCommentMutation = useMutation<unknown, ApiError, { dashboard_key: string; widget_id: string; message: string }>({
    mutationFn: (data) => biCollaborationApi.createComment(data).then(r => r.data),
    onSuccess: () => {
      setNewComment('')
      qc.invalidateQueries({ queryKey: ['bi-collab-comments', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al añadir comentario'),
  })

  const resolveCommentMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (id) => biCollaborationApi.resolveComment(id).then(r => r.data),
    onSuccess: () => {
      toast.success('Comentario resuelto')
      qc.invalidateQueries({ queryKey: ['bi-collab-comments', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al resolver'),
  })

  const saveViewMutation = useMutation<unknown, ApiError, { name: string; dashboard_key: string; filters: Record<string, unknown> }>({
    mutationFn: (data) => biCollaborationApi.createSharedView(data).then(r => r.data),
    onSuccess: () => {
      setViewName('')
      toast.success('Vista compartida guardada')
      qc.invalidateQueries({ queryKey: ['bi-collab-views', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al guardar vista'),
  })

  const toggleViewMutation = useMutation<unknown, ApiError, { id: string; active: boolean }>({
    mutationFn: ({ id, active }) => biCollaborationApi.patchSharedView(id, { active }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-views', dashboardKey] }),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al actualizar vista'),
  })

  const shareDashboardMutation = useMutation<unknown, ApiError, { target_user_id: string; target_user_name: string; permission: string }>({
    mutationFn: (data) => biCollaborationApi.shareDashboard(dashboardKey, data).then(r => r.data),
    onSuccess: () => {
      setShareUserId('')
      setShareUserName('')
      toast.success('Acceso compartido')
      qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al compartir'),
  })

  const revokeShareMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (shareId) =>
      biCollaborationApi.revokeShare(dashboardKey, shareId).then(r => r.data),
    onSuccess: () => {
      toast.success('Acceso revocado')
      qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al revocar'),
  })

  const restoreVersionMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (versionId) =>
      biCollaborationApi.restoreDashboardVersion(dashboardKey, versionId).then(r => r.data),
    onSuccess: () => {
      toast.success('Versión restaurada')
      qc.invalidateQueries({ queryKey: ['bi-collab-versions', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al restaurar'),
  })

  const markNotificationReadMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (notificationId) =>
      biCollaborationApi.patchNotification(notificationId, { is_read: true }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] }),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al marcar leída'),
  })

  const comments = commentsData?.items ?? commentsData?.comments ?? []
  const views = viewsData?.items ?? viewsData?.views ?? []
  const shares = sharesData?.items ?? sharesData?.shares ?? []
  const versions = versionsData?.items ?? versionsData?.versions ?? []
  const notifications = notificationsData?.items ?? notificationsData?.notifications ?? []

  function submitComment() {
    const msg = newComment.trim()
    if (!msg) return
    addCommentMutation.mutate({ dashboard_key: dashboardKey, widget_id: 'main', message: msg })
  }

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <MessageCircle size={18} style={{ color: 'var(--purple)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('bi.collab.title', 'Colaboración en dashboards BI')}
          </h2>
        </div>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
          dashboard_key: <span style={{ fontFamily: 'var(--font-mono)' }}>{dashboardKey}</span>
        </span>
      </div>

      <Tabs
        items={[
          { id: 'comments',      label: t('bi.collab.comments', 'Comentarios') },
          { id: 'views',         label: t('bi.collab.views', 'Vistas compartidas') },
          { id: 'shares',        label: t('bi.collab.shares', 'Accesos') },
          { id: 'versions',      label: t('bi.collab.versions', 'Versiones') },
          { id: 'notifications', label: t('bi.collab.notifications', 'Notificaciones') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Colaboración BI"
      />

      {/* Comments */}
      {tab === 'comments' && (
        <div>
          <div style={fieldLabel}>{t('bi.collab.add_comment', 'Añadir comentario')}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              type="text"
              placeholder="Escribe un comentario para este dashboard…"
              value={newComment}
              onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitComment()}
              style={{ ...inputBase, flex: 1 }}
            />
            <Button
              onClick={submitComment}
              disabled={!newComment.trim() || addCommentMutation.isPending}
              loading={addCommentMutation.isPending}
              icon={<Plus size={13} />}
            >Comentar</Button>
          </div>

          {commentsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : comments.length === 0 ? (
            <EmptyState icon="💬" title={t('bi.collab.no_comments', 'Sin comentarios todavía')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
              {comments.map(c => (
                <div key={c.id} style={{
                  padding: '10px 14px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  borderRadius: 8,
                  opacity: c.resolved ? 0.55 : 1,
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {c.message}
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <span>{c.author_name ?? c.user_id ?? 'Usuario'}</span>
                        {c.widget_id && <span>· widget {c.widget_id}</span>}
                        {c.created_at && <span>· {new Date(c.created_at).toLocaleString()}</span>}
                        {c.resolved && <span style={chip('var(--success)')}>resuelto</span>}
                      </div>
                    </div>
                    {!c.resolved && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => resolveCommentMutation.mutate(c.id)}
                        loading={resolveCommentMutation.isPending && resolveCommentMutation.variables === c.id}
                        icon={<CheckCircle size={12} />}
                      >Resolver</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Shared views */}
      {tab === 'views' && (
        <div>
          <div style={fieldLabel}>{t('bi.collab.save_view', 'Guardar vista actual')}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              type="text"
              placeholder="Nombre de la vista compartida…"
              value={viewName}
              onChange={e => setViewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && viewName.trim() && saveViewMutation.mutate({ name: viewName.trim(), dashboard_key: dashboardKey, filters: {} })}
              style={{ ...inputBase, flex: 1 }}
            />
            <Button
              onClick={() => viewName.trim() && saveViewMutation.mutate({ name: viewName.trim(), dashboard_key: dashboardKey, filters: {} })}
              disabled={!viewName.trim() || saveViewMutation.isPending}
              loading={saveViewMutation.isPending}
              icon={<Eye size={13} />}
            >Guardar vista</Button>
          </div>

          {viewsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : views.length === 0 ? (
            <EmptyState icon="👁" title={t('bi.collab.no_views', 'Sin vistas guardadas')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {views.map(v => (
                <div key={v.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 14px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  borderRadius: 8, gap: 10, flexWrap: 'wrap',
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{v.name}</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                      {v.dashboard_key} {v.created_at && `· ${new Date(v.created_at).toLocaleDateString()}`}
                      {v.created_by_name && ` · ${v.created_by_name}`}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={chip(v.active === false ? 'var(--text-3)' : 'var(--accent)')}>
                      {v.active === false ? 'Inactiva' : 'Activa'}
                    </span>
                    <Button
                      size="xs"
                      variant="secondary"
                      onClick={() => toggleViewMutation.mutate({ id: v.id, active: !(v.active === false ? false : true) })}
                    >{v.active === false ? 'Activar' : 'Desactivar'}</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Shares */}
      {tab === 'shares' && (
        <div>
          <div style={fieldLabel}>Compartir con un usuario</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="user_id"
              value={shareUserId}
              onChange={e => setShareUserId(e.target.value)}
              style={{ ...inputBase, flex: '1 1 140px' }}
            />
            <input
              type="text"
              placeholder="Nombre visible"
              value={shareUserName}
              onChange={e => setShareUserName(e.target.value)}
              style={{ ...inputBase, flex: '1 1 160px' }}
            />
            <select
              value={sharePermission}
              onChange={e => setSharePermission(e.target.value)}
              style={{ ...inputBase, width: 130 }}
            >
              {SHARE_PERMISSIONS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <Button
              onClick={() => shareUserId.trim() && shareUserName.trim() && shareDashboardMutation.mutate({
                target_user_id: shareUserId.trim(),
                target_user_name: shareUserName.trim(),
                permission: sharePermission,
              })}
              disabled={!shareUserId.trim() || !shareUserName.trim() || shareDashboardMutation.isPending}
              loading={shareDashboardMutation.isPending}
              icon={<Share2 size={13} />}
            >Compartir</Button>
          </div>

          {sharesLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : shares.length === 0 ? (
            <EmptyState icon="🔗" title="Sin accesos compartidos" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {shares.map(s => (
                <div key={s.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 14px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  borderRadius: 8, gap: 10, flexWrap: 'wrap',
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>
                      {s.target_user_name || s.user_name || s.target_user_id || s.user_id}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{s.target_user_id || s.user_id}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {s.permission === 'view' && <Lock size={12} style={{ color: 'var(--text-3)' }} />}
                    <span style={chip(PERMISSION_COLOR[s.permission] || 'var(--text-3)')}>
                      {PERMISSION_LABEL[s.permission] || s.permission}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`¿Revocar acceso de ${s.target_user_name || s.user_name}?`)) {
                          revokeShareMutation.mutate(s.id)
                        }
                      }}
                      title="Revocar acceso"
                      style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        color: 'var(--text-3)', padding: 4, display: 'inline-flex',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
                      onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Versions */}
      {tab === 'versions' && (
        <div>
          <div style={fieldLabel}>Historial de versiones del dashboard</div>
          {versionsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : versions.length === 0 ? (
            <EmptyState icon="📜" title="Sin versiones guardadas" description="Las ediciones del dashboard se guardan automáticamente como versiones." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
              {versions.map(v => (
                <div key={v.id} style={{
                  padding: '10px 14px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  borderRadius: 8,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)' }}>
                      <History size={12} style={{ display: 'inline', marginRight: 6, color: 'var(--text-3)' }} />
                      Versión {v.version}
                    </div>
                    {v.change_log && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 4 }}>
                        {v.change_log}
                      </div>
                    )}
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <Clock size={11} />
                      {v.created_at ? new Date(v.created_at).toLocaleString() : ''}
                      {v.created_by_name && ` · ${v.created_by_name}`}
                    </div>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm(`¿Restaurar versión ${v.version}? Se creará una nueva versión con este contenido.`)) {
                        restoreVersionMutation.mutate(v.id)
                      }
                    }}
                    loading={restoreVersionMutation.isPending && restoreVersionMutation.variables === v.id}
                  >Restaurar</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Notifications */}
      {tab === 'notifications' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 8, flexWrap: 'wrap' }}>
            <div style={fieldLabel}>Notificaciones de colaboración (no leídas)</div>
            <span style={chip('var(--accent)')}>{notifications.length}</span>
          </div>
          {notificationsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : notifications.length === 0 ? (
            <EmptyState icon="🔔" title="Sin notificaciones pendientes" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
              {notifications.map(n => (
                <div key={n.id} style={{
                  padding: '10px 14px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--surface-4)',
                  borderRadius: 8,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Bell size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>
                        {n.event_type || n.type || 'evento'}
                      </span>
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>
                      {n.message || n.dashboard_key || ''}
                      {n.created_at && ` · ${new Date(n.created_at).toLocaleString()}`}
                    </div>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => markNotificationReadMutation.mutate(n.id)}
                    loading={markNotificationReadMutation.isPending && markNotificationReadMutation.variables === n.id}
                    icon={<CheckCircle size={12} />}
                  >Marcar leída</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
