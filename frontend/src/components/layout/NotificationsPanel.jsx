/**
 * NotificationsPanel — Bell icon with dropdown notification list
 * Shows unread count badge, marks as read on click
 */
import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'

export default function NotificationsPanel() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const qc = useQueryClient()

  const { data, refetch } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get('/enterprise/notifications', { params: { page_size: 15 } }).then(r => r.data),
    refetchInterval: 30000,
  })

  const notifications = data?.notifications || []
  const unreadCount = data?.unread_count || 0

  const { mutate: markRead } = useMutation({
    mutationFn: id => api.post(`/enterprise/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries(['notifications']),
  })
  const { mutate: markAll } = useMutation({
    mutationFn: () => api.post('/enterprise/notifications/read-all'),
    onSuccess: () => qc.invalidateQueries(['notifications']),
  })

  // Close on click outside
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const timeAgo = (dateStr) => {
    if (!dateStr) return ''
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'ahora'
    if (mins < 60) return `${mins}m`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h`
    return `${Math.floor(hours / 24)}d`
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {/* Bell button */}
      <button
        onClick={() => { setOpen(o => !o); if (!open) refetch() }}
        style={{
          position: 'relative',
          background: 'none',
          border: '1px solid var(--surface-4)',
          borderRadius: 8,
          padding: '6px 10px',
          color: 'var(--text-2)',
          cursor: 'pointer',
          fontSize: "var(--text-lg)",
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.15s',
        }}
        title="Notificaciones"
      >
        🔔
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute',
            top: -4, right: -4,
            background: 'var(--danger)',
            color: '#fff',
            fontSize: "var(--text-2xs)",
            fontWeight: 700,
            borderRadius: '50%',
            minWidth: 16,
            height: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 3px',
            border: '2px solid var(--surface-0)',
          }}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: 0,
          marginTop: 8,
          width: 360,
          background: 'var(--surface-2)',
          border: '1px solid var(--surface-4)',
          borderRadius: 12,
          boxShadow: '0 16px 48px #00000080',
          zIndex: 1000,
          overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid var(--surface-4)' }}>
            <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>
              Notificaciones
              {unreadCount > 0 && <span style={{ marginLeft: 8, fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 7px', borderRadius: 20, background: 'var(--danger-bg)', color: 'var(--danger)' }}>{unreadCount} sin leer</span>}
            </span>
            {unreadCount > 0 && (
              <button onClick={() => markAll()}
                style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                Marcar todas como leídas
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-3)' }}>
                <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 8 }}>🔕</div>
                <div style={{ fontSize: "var(--text-base)" }}>Sin notificaciones</div>
              </div>
            ) : (
              notifications.map(n => (
                <button
                  key={n.id}
                  onClick={() => { if (!n.is_read) markRead(n.id); if (n.action_url) { window.location.href = n.action_url; setOpen(false) } }}
                  style={{
                    display: 'flex',
                    gap: 12,
                    padding: '12px 18px',
                    borderBottom: '1px solid #1e2d4520',
                    cursor: n.action_url ? 'pointer' : 'default',
                    background: n.is_read ? 'transparent' : 'rgba(79,142,247,0.04)',
                    transition: 'background 0.1s',
                    width: '100%',
                    borderLeft: 'none',
                    borderRight: 'none',
                    borderTop: 'none',
                    textAlign: 'left',
                  }}
                  type="button"
                  onMouseEnter={e => { if (n.action_url) e.currentTarget.style.background = 'var(--surface-3)' }}
                  onMouseLeave={e => e.currentTarget.style.background = n.is_read ? 'transparent' : 'rgba(79,142,247,0.04)'}
                >
                  <div style={{
                    width: 36, height: 36,
                    background: n.color + '20',
                    border: `1px solid ${n.color}40`,
                    borderRadius: 10,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: "var(--text-lg)", flexShrink: 0,
                  }}>
                    {n.icon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 2 }}>
                      <span style={{ fontSize: "var(--text-base)", fontWeight: n.is_read ? 400 : 700, color: n.is_read ? 'var(--text-2)' : 'var(--text-1)', lineHeight: 1.3 }}>
                        {n.title}
                      </span>
                      <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', flexShrink: 0, marginLeft: 8 }}>{timeAgo(n.created_at)}</span>
                    </div>
                    {n.body && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', lineHeight: 1.4 }}>{n.body}</div>}
                  </div>
                  {!n.is_read && (
                    <div style={{ width: 7, height: 7, borderRadius: '50%', background: n.color, flexShrink: 0, marginTop: 4 }} />
                  )}
                </button>
              ))
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div style={{ padding: '10px 18px', borderTop: '1px solid var(--surface-4)', textAlign: 'center' }}>
              <button
                onClick={() => { api.delete('/enterprise/notifications/clear-old', { params: { days: 90 } }).then(() => qc.invalidateQueries(['notifications'])) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                Limpiar notificaciones leídas (+90d)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
