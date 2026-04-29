/**
 * BiDashboardCollabPanel.jsx — BI Dashboard Collaboration panel.
 * Comments, shared views, and reactions on BI dashboards.
 * Connects to /api/v1/bi/collab/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { MessageCircle, Eye, ThumbsUp, CheckCircle, Plus } from 'lucide-react'

const REACTIONS = ['👍', '👎', '🔥', '❓', '⚠️']

export default function BiDashboardCollabPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()
  const [tab, setTab] = useState('comments')
  const [newComment, setNewComment] = useState('')
  const [commentDashboard, setCommentDashboard] = useState('main')
  const [viewName, setViewName] = useState('')

  const { data: commentsData } = useQuery({
    queryKey: ['bi-collab-comments'],
    queryFn: () => api.get('/bi/collab/comments').then(r => r.data),
  })

  const { data: viewsData } = useQuery({
    queryKey: ['bi-collab-views'],
    queryFn: () => api.get('/bi/collab/views').then(r => r.data),
    enabled: tab === 'views',
  })

  const addCommentMutation = useMutation({
    mutationFn: (data) => api.post('/bi/collab/comments', data).then(r => r.data),
    onSuccess: () => { setNewComment(''); qc.invalidateQueries({ queryKey: ['bi-collab-comments'] }) },
  })

  const resolveCommentMutation = useMutation({
    mutationFn: (id) => api.patch(`/bi/collab/comments/${id}/resolve`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-comments'] }),
  })

  const saveViewMutation = useMutation({
    mutationFn: (data) => api.post('/bi/collab/views', data).then(r => r.data),
    onSuccess: () => { setViewName(''); qc.invalidateQueries({ queryKey: ['bi-collab-views'] }) },
  })

  const reactionMutation = useMutation({
    mutationFn: (data) => api.post('/bi/collab/reactions', data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-collab-comments'] }),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const comments = commentsData?.comments ?? commentsData?.items ?? []
  const views = viewsData?.views ?? viewsData?.items ?? []

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <MessageCircle className="w-5 h-5 text-indigo-500" />
        <h2 className="text-lg font-bold">{t('bi.collab.title', 'Colaboración en Dashboards BI')}</h2>
      </div>

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-5">
        {[['comments', 'Comentarios'], ['views', 'Vistas compartidas']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === id ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {t(`bi.collab.${id}`, label)}
          </button>
        ))}
      </div>

      {tab === 'comments' && (
        <div className="space-y-4">
          {/* Add comment */}
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Dashboard ID (ej: main)"
              value={commentDashboard}
              onChange={e => setCommentDashboard(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm w-36 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <input
              type="text"
              placeholder={t('bi.collab.add_comment', 'Añadir comentario...')}
              value={newComment}
              onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newComment && addCommentMutation.mutate({ dashboard_id: commentDashboard, text: newComment })}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <button
              onClick={() => newComment && addCommentMutation.mutate({ dashboard_id: commentDashboard, text: newComment })}
              disabled={!newComment}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 hover:bg-indigo-700"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          {/* Comment list */}
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {comments.map((c) => (
              <div key={c.id} className={`rounded-lg border px-4 py-3 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'} ${c.resolved ? 'opacity-50' : ''}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-sm">{c.text}</p>
                    <p className="text-xs text-gray-400 mt-1">{c.author_name ?? c.user_id ?? 'Usuario'} · {c.dashboard_id}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {REACTIONS.map(r => (
                      <button key={r} onClick={() => reactionMutation.mutate({ comment_id: c.id, reaction: r })}
                        className="text-xs hover:scale-125 transition-transform">{r}</button>
                    ))}
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
              onClick={() => viewName && saveViewMutation.mutate({ name: viewName, dashboard_id: 'main', shared: true, filters: {} })}
              disabled={!viewName}
              className="flex items-center gap-1 px-4 py-1.5 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 hover:bg-indigo-700"
            >
              <Eye className="w-4 h-4" />
              {t('bi.collab.save_view', 'Guardar vista')}
            </button>
          </div>

          <div className="space-y-2">
            {views.map((v) => (
              <div key={v.id} className={`flex items-center justify-between px-4 py-2 rounded-lg ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <div>
                  <span className="font-medium text-sm">{v.name}</span>
                  <p className="text-xs text-gray-400">{v.dashboard_id} · {v.created_at ? new Date(v.created_at).toLocaleDateString() : ''}</p>
                </div>
                {v.shared && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 flex items-center gap-1">
                    <ThumbsUp className="w-3 h-3" /> Compartida
                  </span>
                )}
              </div>
            ))}
            {!views.length && <p className="text-sm text-gray-400">{t('bi.collab.no_views', 'Sin vistas guardadas')}</p>}
          </div>
        </div>
      )}
    </div>
  )
}
