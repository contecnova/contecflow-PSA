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
 *   GET   /bi/collaboration/dashboards/{key}/shares                               -> lista
 *   POST  /bi/collaboration/dashboards/{key}/shares                               { target_user_id, target_user_name, permission }
 *   DEL   /bi/collaboration/dashboards/{key}/shares/{shareId}
 *   GET   /bi/collaboration/dashboards/{key}/versions                             -> lista
 *   POST  /bi/collaboration/dashboards/{key}/versions/{versionId}/restore
 *   GET   /bi/collaboration/notifications?include_read=false                      -> lista
 *   PATCH /bi/collaboration/notifications/{id}                                    { is_read }
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biCollaborationApi } from '../../services/api'
import type { ComentarioBi } from '../../services/api/tipos-grc'
import { useAppT } from '../../i18n/AppLangContext'
import { MessageCircle, Eye, Share2, Plus, Trash2, Lock, CheckCircle, Clock, Bell, History } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { localeActivo } from '../../utils/helpers'
import { POLL_LIVE_MS } from '../../constants/timings'
import './BiDashboardCollabPanel.css'
import { chipColor } from '../../utils/estilos'

type ApiError = { response?: { data?: { detail?: string } } }

const SHARE_PERMISSIONS = [
  { value: 'view',  label: 'Ver',     color: 'var(--text-3)' },
  { value: 'edit',  label: 'Editar',  color: 'var(--warning)' },
  { value: 'admin', label: 'Admin',   color: 'var(--danger)' },
]
const PERMISSION_LABEL: Record<string, string> = Object.fromEntries(SHARE_PERMISSIONS.map(p => [p.value, p.label]))
const PERMISSION_COLOR: Record<string, string> = Object.fromEntries(SHARE_PERMISSIONS.map(p => [p.value, p.color]))

interface BiDashboardCollabPanelProps {
  dashboardKey?: string
}


export default function BiDashboardCollabPanel({ dashboardKey = 'main' }: BiDashboardCollabPanelProps) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { confirmar } = useConfirm()
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
    refetchInterval: POLL_LIVE_MS,
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
      toast.success(t('bidashboardcollab.comentario_resuelto'))
      qc.invalidateQueries({ queryKey: ['bi-collab-comments', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al resolver'),
  })

  const saveViewMutation = useMutation<unknown, ApiError, { name: string; dashboard_key: string; filters: Record<string, unknown> }>({
    mutationFn: (data) => biCollaborationApi.createSharedView(data).then(r => r.data),
    onSuccess: () => {
      setViewName('')
      toast.success(t('bidashboardcollab.vista_compartida_guardada'))
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
      toast.success(t('bidashboardcollab.acceso_compartido'))
      qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] })
      qc.invalidateQueries({ queryKey: ['bi-collab-notifications', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al compartir'),
  })

  const revokeShareMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (shareId) =>
      biCollaborationApi.revokeShare(dashboardKey, shareId).then(r => r.data),
    onSuccess: () => {
      toast.success(t('bidashboardcollab.acceso_revocado'))
      qc.invalidateQueries({ queryKey: ['bi-collab-shares', dashboardKey] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al revocar'),
  })

  const restoreVersionMutation = useMutation<unknown, ApiError, string>({
    mutationFn: (versionId) =>
      biCollaborationApi.restoreDashboardVersion(dashboardKey, versionId).then(r => r.data),
    onSuccess: () => {
      toast.success(t('bidashboardcollab.version_restaurada'))
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

  // Todas son APIListResponse: llegan como lista (tipos-grc, tipos-bi).
  const comments: ComentarioBi[] = commentsData ?? []
  const views = viewsData ?? []
  const shares = sharesData ?? []
  const versions = versionsData ?? []
  const notifications = notificationsData ?? []

  function submitComment() {
    const msg = newComment.trim()
    if (!msg) return
    addCommentMutation.mutate({ dashboard_key: dashboardKey, widget_id: 'main', message: msg })
  }

  return (
    <Card className="bidashbo-sx1">
      <div className="bidacopa-row-1">
        <div className="u-row-center-8">
          <MessageCircle size={18} className="bidashbo-sx2" />
          <h2 className="bidacopa-box-1">
            {t('bi.collab.title', 'Colaboración en dashboards BI')}
          </h2>
        </div>
        <span className="u-text3-xs">
          dashboard_key: <span className="u-mono">{dashboardKey}</span>
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
          <div className="bidacopa-fieldlabel">{t('bi.collab.add_comment', 'Añadir comentario')}</div>
          <div className="bidacopa-row-2">
            <input aria-label={t('bidashboardcollab.escribe_un_comentario_para_este_dashboard')}
              type="text"
              placeholder={t('bidashboardcollab.escribe_un_comentario_para_este_dashboard')}
              value={newComment}
              onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitComment()}
              className="bidacopa-inputbase"
            />
            <Button
              onClick={submitComment}
              disabled={!newComment.trim() || addCommentMutation.isPending}
              loading={addCommentMutation.isPending}
              icon={<Plus size={13} />}
            >{t('bidashboardcollab.comentar')}</Button>
          </div>

          {commentsLoading ? (
            <div className="bidacopa-row-3"><Spinner /></div>
          ) : comments.length === 0 ? (
            <EmptyState icon="💬" title={t('bi.collab.no_comments', 'Sin comentarios todavía')} />
          ) : (
            <div className="bidacopa-stack-1">
              {comments.map(c => (
                <div className={`bidacopa-box-3 ${c.resolved ? 'bi-dashboard-collab-panel-m1' : 'bi-dashboard-collab-panel-m2'}`} key={c.id}>
                  <div className="bidacopa-row-4">
                    <div className="u-flex1-min0">
                      <div className="bidacopa-txt-1">
                        {c.message}
                      </div>
                      <div className="bidacopa-row-5">
                        <span>{c.author_name ?? 'Usuario'}</span>
                        {c.widget_id && <span>{t('bidashboardcollab.widget')} {c.widget_id}</span>}
                        {c.created_at && <span>· {new Date(c.created_at).toLocaleString(localeActivo())}</span>}
                        {c.resolved && <span className="chip-dato" style={chipColor('var(--success)')}>{t('bidashboardcollab.resuelto')}</span>}
                      </div>
                    </div>
                    {!c.resolved && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => resolveCommentMutation.mutate(c.id)}
                        loading={resolveCommentMutation.isPending && resolveCommentMutation.variables === c.id}
                        icon={<CheckCircle size={12} />}
                      >{t('alerts.resolve')}</Button>
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
          <div className="bidacopa-fieldlabel">{t('bi.collab.save_view', 'Guardar vista actual')}</div>
          <div className="bidacopa-row-2">
            <input aria-label={t('bidashboardcollab.nombre_de_la_vista_compartida')}
              type="text"
              placeholder={t('bidashboardcollab.nombre_de_la_vista_compartida')}
              value={viewName}
              onChange={e => setViewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && viewName.trim() && saveViewMutation.mutate({ name: viewName.trim(), dashboard_key: dashboardKey, filters: {} })}
              className="bidacopa-inputbase"
            />
            <Button
              onClick={() => viewName.trim() && saveViewMutation.mutate({ name: viewName.trim(), dashboard_key: dashboardKey, filters: {} })}
              disabled={!viewName.trim() || saveViewMutation.isPending}
              loading={saveViewMutation.isPending}
              icon={<Eye size={13} />}
            >{t('datagovernance.guardar_vista')}</Button>
          </div>

          {viewsLoading ? (
            <div className="bidacopa-row-3"><Spinner /></div>
          ) : views.length === 0 ? (
            <EmptyState icon="👁" title={t('bi.collab.no_views', 'Sin vistas guardadas')} />
          ) : (
            <div className="u-stack-6">
              {views.map(v => (
                <div key={v.id} className="bidacopa-row-6">
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{v.name}</div>
                    <div className="u-text3-xs-mt2">
                      {v.dashboard_key} {v.created_at && `· ${new Date(v.created_at).toLocaleDateString(localeActivo())}`}
                      {v.created_by_name && ` · ${v.created_by_name}`}
                    </div>
                  </div>
                  <div className="u-row-center-8">
                    <span className="chip-dato" style={chipColor(v.active === false ? 'var(--text-3)' : 'var(--accent)')}>
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
          <div className="bidacopa-fieldlabel">{t('bidashboardcollab.compartir_con_un_usuario')}</div>
          <div className="bidacopa-row-7">
            <input aria-label="user_id"
              type="text"
              placeholder="user_id"
              value={shareUserId}
              onChange={e => setShareUserId(e.target.value)}
              className="bidacopa-inputbase2"
            />
            <input aria-label={t('portal_perfil.nombre_visible')}
              type="text"
              placeholder={t('portal_perfil.nombre_visible')}
              value={shareUserName}
              onChange={e => setShareUserName(e.target.value)}
              className="bidacopa-inputbase3"
            />
            <select
              value={sharePermission}
              onChange={e => setSharePermission(e.target.value)}
              className="bidacopa-inputbase4"
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
            >{t('pagina_docs.compartir')}</Button>
          </div>

          {sharesLoading ? (
            <div className="bidacopa-row-3"><Spinner /></div>
          ) : shares.length === 0 ? (
            <EmptyState icon="🔗" title={t('bidashboardcollab.sin_accesos_compartidos')} />
          ) : (
            <div className="u-stack-6">
              {shares.map(s => (
                <div key={s.id} className="bidacopa-row-6">
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600">
                      {s.user_name || s.user_id}
                    </div>
                    <div className="u-text3-xs-mt2">
                      <span className="u-mono">{s.user_id}</span>
                    </div>
                  </div>
                  <div className="u-row-center-8">
                    {s.permission === 'view' && <Lock size={12} className="bidashbo-sx3" />}
                    <span className="chip-dato" style={chipColor(PERMISSION_COLOR[s.permission] || 'var(--text-3)')}>
                      {PERMISSION_LABEL[s.permission] || s.permission}
                    </span>
                    <button aria-label={t('bidashboardcollab.revocar_acceso')}
                      type="button"
                      onClick={async () => {
                        if (await confirmar({ message: `¿Revocar acceso de ${s.user_name || s.user_id}?`, danger: true, confirmLabel: 'Revocar' })) {
                          revokeShareMutation.mutate(s.id)
                        }
                      }}
                      title={t('bidashboardcollab.revocar_acceso')}
                      className="bidacopa-row-8"
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
          <div className="bidacopa-fieldlabel">{t('bidashboardcollab.historial_de_versiones_del_dashboard')}</div>
          {versionsLoading ? (
            <div className="bidacopa-row-3"><Spinner /></div>
          ) : versions.length === 0 ? (
            <EmptyState icon="📜" title={t('bidashboardcollab.sin_versiones_guardadas')} description={t('bidashboardcollab.las_ediciones_del_dashboard_se_guardan_automaticamente')} />
          ) : (
            <div className="bidacopa-stack-1">
              {versions.map(v => (
                <div key={v.id} className="bidacopa-row-9">
                  <div className="u-flex1-min0">
                    <div className="bidacopa-txt-2">
                      <History size={12} className="bidashbo-sx4" />
                      {t('bidashboardcollab.version')} {v.version}
                    </div>
                    {v.change_log && (
                      <div className="bidacopa-box-2">
                        {v.change_log}
                      </div>
                    )}
                    <div className="bidacopa-row-10">
                      <Clock size={11} />
                      {v.created_at ? new Date(v.created_at).toLocaleString(localeActivo()) : ''}
                      {v.created_by_name && ` · ${v.created_by_name}`}
                    </div>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={async () => {
                      if (await confirmar({ message: `¿Restaurar versión ${v.version}? Se creará una nueva versión con este contenido.`, confirmLabel: 'Restaurar' })) {
                        restoreVersionMutation.mutate(v.id)
                      }
                    }}
                    loading={restoreVersionMutation.isPending && restoreVersionMutation.variables === v.id}
                  >{t('wiki.restaurar')}</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Notifications */}
      {tab === 'notifications' && (
        <div>
          <div className="bidacopa-row-11">
            <div className="bidacopa-fieldlabel">{t('bidashboardcollab.notificaciones_de_colaboracion_no_leidas')}</div>
            <span className="chip-dato" style={chipColor('var(--accent)')}>{notifications.length}</span>
          </div>
          {notificationsLoading ? (
            <div className="bidacopa-row-3"><Spinner /></div>
          ) : notifications.length === 0 ? (
            <EmptyState icon="🔔" title={t('bidashboardcollab.sin_notificaciones_pendientes')} />
          ) : (
            <div className="bidacopa-stack-1">
              {notifications.map(n => (
                <div key={n.id} className="bidacopa-row-12">
                  <div className="u-flex1-min0">
                    <div className="u-row-center-6">
                      <Bell size={12} className="bidashbo-sx5" />
                      <span className="u-text1-sm-600">
                        {n.event_type}
                      </span>
                    </div>
                    <div className="u-hint">
                      {n.dashboard_key}
                      {n.created_at && ` · ${new Date(n.created_at).toLocaleString(localeActivo())}`}
                    </div>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => markNotificationReadMutation.mutate(n.id)}
                    loading={markNotificationReadMutation.isPending && markNotificationReadMutation.variables === n.id}
                    icon={<CheckCircle size={12} />}
                  >{t('bidashboardcollab.marcar_leida')}</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
