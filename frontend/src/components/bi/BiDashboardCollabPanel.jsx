/**
 * BiDashboardCollabPanel.jsx — Complete BI Dashboard Collaboration UI
 *
 * Features:
 * - Comments with resolution on dashboard widgets
 * - Shared views with persistent filters
 * - Dashboard sharing with permission management
 * - Collaboration notifications
 * - Dashboard version history with restore
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import {
  MessageCircle,
  Eye,
  Share2,
  Plus,
  Trash2,
  Lock,
  CheckCircle,
  Clock,
} from 'lucide-react'

const SHARE_PERMISSIONS = [
  { value: 'view', label: 'Ver' },
  { value: 'edit', label: 'Editar' },
  { value: 'admin', label: 'Admin' },
]

export default function BiDashboardCollabPanel({ dashboardKey = 'main' }) {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()
  const [tab, setTab] = useState('comments')
  const [newComment, setNewComment] = useState('')
  const [viewName, setViewName] = useState('')
  const [shareUserId, setShareUserId] = useState('')
  const [shareUserName, setShareUserName] = useState('')
  const [sharePermission, setSharePermission] = useState('view')

  const { data: commentsData, isLoading: commentsLoading } = useQuery({
    queryKey: ['bi-collab-comments', dashboardKey],
    queryFn: () =>
      api.get('/bi/collaboration/comments', {
        params: { dashboard_key: dashboardKey },
      }).then(r => r.data),
  })

  const { data: viewsData, isLoading: viewsLoading } = useQuery({
    queryKey: ['bi-collab-views', dashboardKey],
    queryFn: () => api.get('/bi/collaboration/shared-views').then(r => r.data),
    enabled: tab === 'views',
  })

  const { data: sharesData, isLoading: sharesLoading } = useQuery({
    queryKey: ['bi-collab-shares', dashboardKey],
    queryFn: () =>
      api.get(`/bi/collaboration/dashboards/${dashboardKey}/shares`).then(r => r.data),
    enabled: tab === 'shares',
  })

  const { data: versionsData, isLoading: versionsLoading } = useQuery({
    queryKey: ['bi-collab-versions', dashboardKey],
    queryFn: () =>
      api.get(`/bi/collaboration/dashboards/${dashboardKey}/versions`).then(r => r.data),
    enabled: tab === 'versions',
  })

  const { data: notificationsData, isLoading: notificationsLoading } = useQuery({
    queryKey: ['bi-collab-notifications', dashboardKey],
    queryFn: () =>
      api.get('/bi/collaboration/notifications', {
        params: { dashboard_key: dashboardKey, include_read: false },
      }).then(r => r.data),
    enabled: tab === 'notifications',
    refetchInterval: 5000,
  })

  const addCommentMutation = useMutation({
    mutationFn: (data) => api.post('/bi/collaboration/comments', data).then(r => r.data),
    onSuccess: () => {
      setNewComment('')
      qc.invalidateQueries({ queryKey: ['bi-collab-comments', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
  })

  const resolveCommentMutation = useMutation({
    mutationFn: (id) => api.patch(`/bi/collaboration/comments/${id}/resolve`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-comments', dashboardKey] }),
  })

  const saveViewMutation = useMutation({
    mutationFn: (data) => api.post('/bi/collaboration/shared-views', data).then(r => r.data),
    onSuccess: () => {
      setViewName('')
      qc.invalidateQueries({ queryKey: ['bi-collab-views', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
  })

  const shareDashboardMutation = useMutation({
    mutationFn: (data) =>
      api.post(`/bi/collaboration/dashboards/${dashboardKey}/shares`, data).then(r => r.data),
    onSuccess: () => {
      setShareUserId('')
      setShareUserName('')
      qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
  })

  const revokeShareMutation = useMutation({
    mutationFn: (shareId) =>
      api.delete(`/bi/collaboration/dashboards/${dashboardKey}/shares/${shareId}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] }),
  })

  const restoreVersionMutation = useMutation({
    mutationFn: (versionId) =>
      api.post(`/bi/collaboration/dashboards/${dashboardKey}/versions/${versionId}/restore`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bi-collab-versions', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
  })

  const markNotificationReadMutation = useMutation({
    mutationFn: (notificationId) =>
      api.patch(`/bi/collaboration/notifications/${notificationId}`, { is_read: true }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] }),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const comments = commentsData?.comments ?? commentsData?.items ?? []
  const views = viewsData?.views ?? viewsData?.items ?? []
  const shares = sharesData?.items ?? []
  const versions = versionsData?.items ?? []
  const notifications = notificationsData?.items ?? []

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <MessageCircle className="w-5 h-5 text-indigo-500" />
        <h2 className="text-lg font-bold">{t('bi.collab.title', 'Colaboración en Dashboards BI')}</h2>
      </div>

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-5">
        {[
          ['comments', 'Comentarios'],
          ['views', 'Vistas compartidas'],
          ['shares', 'Accesos'],
          ['versions', 'Versiones'],
          ['notifications', 'Notificaciones'],
        ].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === id ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {t(`bi.collab.${id}`, label)}
          </button>
        ))}
      </div>

      {tab === 'comments' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder={t('bi.collab.add_comment', 'Añadir comentario...')}
              value={newComment}
              onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newComment && addCommentMutation.mutate({ dashboard_key: dashboardKey, widget_id: 'main', message: newComment })}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <button
              onClick={() => newComment && addCommentMutation.mutate({ dashboard_key: dashboardKey, widget_id: 'main', message: newComment })}
              disabled={!newComment}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 hover:bg-indigo-700"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto">
            {commentsLoading && <p className="text-sm text-gray-400">Cargando...</p>}
            {comments.map((c) => (
              <div key={c.id} className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'} ${c.resolved ? 'opacity-50' : ''}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-sm">{c.message}</p>
                    <p className="text-xs text-gray-400 mt-1">{c.author_name ?? c.user_id ?? 'Usuario'} · {c.dashboard_key}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {!c.resolved && (
                      <button onClick={() => resolveCommentMutation.mutate(c.id)}
                        className="ml-1 text-green-500 hover:text-green-600" title="Resolver">
                        <CheckCircle className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {!comments.length && <p className="text-sm text-gray-400">{t('bi.collab.no_comments', 'Sin comentarios todavía')}</p>}
          </div>
        </div>
      )}

      {tab === 'views' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder={t('bi.collab.view_name', 'Nombre de la vista...')}
              value={viewName}
              onChange={e => setViewName(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <button
              onClick={() => viewName && saveViewMutation.mutate({ name: viewName, dashboard_key: dashboardKey, filters: {} })}
              disabled={!viewName}
              className="flex items-center gap-1 px-4 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 hover:bg-indigo-700"
            >
              <Eye className="w-4 h-4" />
              {t('bi.collab.save_view', 'Guardar vista')}
            </button>
          </div>

          <div className="space-y-2">
            {viewsLoading && <p className="text-sm text-gray-400">Cargando...</p>}
            {views.map((v) => (
              <div key={v.id} className={`flex items-center justify-between px-4 py-2 rounded-lg ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <div>
                  <span className="font-medium text-sm">{v.name}</span>
                  <p className="text-xs text-gray-400">{v.dashboard_key} · {v.created_at ? new Date(v.created_at).toLocaleDateString() : ''}</p>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 flex items-center gap-1">
                  <Eye className="w-3 h-3" /> Guardada
                </span>
              </div>
            ))}
            {!views.length && <p className="text-sm text-gray-400">{t('bi.collab.no_views', 'Sin vistas guardadas')}</p>}
          </div>
        </div>
      )}

      {tab === 'shares' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="ID usuario"
              value={shareUserId}
              onChange={e => setShareUserId(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <input
              type="text"
              placeholder="Nombre usuario"
              value={shareUserName}
              onChange={e => setShareUserName(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <select
              value={sharePermission}
              onChange={e => setSharePermission(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm w-28 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            >
              {SHARE_PERMISSIONS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            <button
              onClick={() => shareUserId && shareUserName && shareDashboardMutation.mutate({ target_user_id: shareUserId, target_user_name: shareUserName, permission: sharePermission })}
              disabled={!shareUserId || !shareUserName}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 hover:bg-indigo-700"
            >
              <Share2 className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto">
            {sharesLoading && <p className="text-sm text-gray-400">Cargando...</p>}
            {shares.map((s) => (
              <div key={s.id} className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">{s.user_name}</p>
                    <p className="text-xs text-gray-400 mt-1">{s.user_id} · {s.permission}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.permission === 'view' && <Lock className="w-4 h-4 text-gray-500" />}
                    <button
                      onClick={() => revokeShareMutation.mutate(s.id)}
                      className="text-red-500 hover:text-red-600"
                      title="Revocar"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {!shares.length && <p className="text-sm text-gray-400">Sin accesos compartidos</p>}
          </div>
        </div>
      )}

      {tab === 'versions' && (
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {versionsLoading && <p className="text-sm text-gray-400">Cargando...</p>}
          {versions.map((v) => (
            <div key={v.id} className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <p className="text-sm font-semibold">Versión {v.version}</p>
                  <p className="text-xs text-gray-400 mt-1">{v.change_log || 'Sin descripción'}</p>
                  <p className="text-xs text-gray-400 mt-1"><Clock className="w-3 h-3 inline mr-1" />{v.created_at ? new Date(v.created_at).toLocaleString() : ''}</p>
                </div>
                <button
                  onClick={() => restoreVersionMutation.mutate(v.id)}
                  className="text-indigo-500 hover:text-indigo-600 text-xs"
                >
                  Restaurar
                </button>
              </div>
            </div>
          ))}
          {!versions.length && <p className="text-sm text-gray-400">Sin versiones aún</p>}
        </div>
      )}

      {tab === 'notifications' && (
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {notificationsLoading && <p className="text-sm text-gray-400">Cargando...</p>}
          {notifications.map((n) => (
            <div key={n.id} className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <p className="text-sm font-medium">{n.event_type}</p>
                  <p className="text-xs text-gray-400 mt-1">{n.dashboard_key}</p>
                </div>
                <button
                  onClick={() => markNotificationReadMutation.mutate(n.id)}
                  className="text-green-500 hover:text-green-600"
                  title="Marcar leída"
                >
                  <CheckCircle className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
          {!notifications.length && <p className="text-sm text-gray-400">Sin notificaciones pendientes</p>}
        </div>
      )}
    </div>
  )
}
