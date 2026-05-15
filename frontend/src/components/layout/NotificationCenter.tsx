/**
 * NotificationCenter v23 — Centro de notificaciones en el sidebar
 * Muestra alertas, vencimientos, asignaciones recientes
 */
import _React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api, { alertsApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'

const _TYPE_CFG: Record<string, { icon: string; color: string }> = {
  alert:      { icon: '🔔', color: 'var(--warning)' },
  task:       { icon: '▦',  color: 'var(--success)' },
  ticket:     { icon: '🎫', color: 'var(--purple)' },
  milestone:  { icon: '⬟', color: 'var(--accent)' },
  default:    { icon: '●',  color: 'var(--text-2)' },
}

// TODO type: notification payload — needs shared type from alerts API
interface NotificationItem {
  id: string | number
  title: string
  message?: string
  severity?: string
  created_at?: string
  is_read?: boolean
  _source?: string
}

interface Props {
  collapsed?: boolean
}

export default function NotificationCenter({ collapsed }: Props) {
  const [open, setOpen] = useState<boolean>(false)
  const nav = useNavigate()
  const qc = useQueryClient()
  const { user, loading } = useAuth()

  // ── WebSocket para notificaciones en tiempo real ─────────────────────────────
  const [wsAlerts, setWsAlerts] = useState<NotificationItem[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (loading || !user) {
      wsRef.current?.close()
      wsRef.current = null
      return undefined
    }

    let cancelled = false
    let ping: ReturnType<typeof setInterval> | undefined
    ;(async () => {
      try {
        const { data } = await api.get('/ws/ticket')  // cookie-authenticated
        if (cancelled) return
        // Elegir la URL del WebSocket de forma elegante y configurable
        let wsBase = import.meta.env.VITE_WS_URL
        if (!wsBase) {
          // Si no hay variable, usar el host actual pero adaptando protocolo y puerto
          const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
          // Si el backend está en otro puerto, usarlo
          const apiUrl = import.meta.env.VITE_API_URL || '/api/v1'
          try {
            const url = new URL(apiUrl, window.location.origin)
            wsBase = `${proto}://${url.hostname}:${url.port || (proto === 'wss' ? '443' : '80')}`
          } catch {
            wsBase = `${proto}://${window.location.hostname}:8000`
          }
        }
        const wsUrl = `${wsBase}/api/v1/ws/notifications?ticket=${data.ticket}`
        const ws = new window.WebSocket(wsUrl)
        wsRef.current = ws
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'notifications') {
              setWsAlerts(msg.items || [])
            }
          } catch { /* noop */ }
        }
        ws.onclose = () => { wsRef.current = null }
        // Ping cada 30s para mantener conexión viva
        ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
        }, 30000)
      } catch { /* no WS fallback ok */ }
    })()
    return () => { cancelled = true; clearInterval(ping); wsRef.current?.close() }
  }, [loading, user])

  const { data: httpAlerts = [] } = useQuery<NotificationItem[]>({
    queryKey: ['notif-alerts'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data?.items ?? r.data ?? []).catch(() => []),
    refetchInterval: wsRef.current ? 120000 : 30000,  // sondeo más lento si hay WS
  })

  // Combinar alertas HTTP con notificaciones WS (WS tiene prioridad)
  const wsNotifs: NotificationItem[] = wsAlerts.map(n => ({ ...n, is_read: false, _source: 'ws' }))
  const httpAlertsFilt: NotificationItem[] = (httpAlerts || []).filter(a => !wsNotifs.find(n => n.id === a.id))

  const alerts: NotificationItem[] = [...wsNotifs, ...httpAlertsFilt]
  const unread = alerts.filter(a => !a.is_read).length

  const { mutate: markRead } = useMutation({
    mutationFn: (id: NotificationItem['id']) => api.patch(`/alerts/${id}`, { is_read: true }),
    onSuccess: () => qc.invalidateQueries(['notif-alerts']),
  })

  const { mutate: markAllRead } = useMutation({
    mutationFn: () => Promise.all(alerts.filter(a => !a.is_read).map(a => api.patch(`/alerts/${a.id}`, { is_read: true }))),
    onSuccess: () => qc.invalidateQueries(['notif-alerts']),
  })

  const SEV_COLOR: Record<string, string> = { critical: 'var(--danger)', warning: 'var(--warning)', info: 'var(--accent)', low: 'var(--text-2)' }

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        title={collapsed ? `Alertas del sistema (${unread})` : undefined}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 9,
          padding: collapsed ? '9px 11px' : '8px 10px',
          borderRadius: 7, border: `1px solid ${open ? 'rgba(79,142,247,0.21)' : 'transparent'}`,
          background: open ? 'rgba(79,142,247,0.09)' : 'transparent',
          color: open ? 'var(--accent)' : 'var(--text-2)',
          cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 500,
          transition: 'all 0.12s', position: 'relative',
        }}
      >
        <span style={{ fontSize: "var(--text-md)", flexShrink: 0, width: 17, textAlign: 'center', position: 'relative' }}>
          🔔
          {unread > 0 && (
            <span style={{
              position: 'absolute', top: -4, right: -4, background: 'var(--danger)',
              color: '#fff', fontSize: "var(--text-8)", fontWeight: 800, borderRadius: '50%',
              width: 13, height: 13, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>{unread > 9 ? '9+' : unread}</span>
          )}
        </span>
        {!collapsed && <span>Alertas</span>}
        {!collapsed && unread > 0 && (
          <span style={{ marginLeft: 'auto', background: 'var(--danger-bg)', color: 'var(--danger)',
            borderRadius: 10, padding: '1px 6px', fontSize: "var(--text-2xs)", fontWeight: 700 }}>{unread}</span>
        )}
      </button>

      {/* Panel desplegable */}
      {open && (
        <div style={{
          position: 'fixed', left: collapsed ? 60 : 214, top: 'auto',
          width: 340, maxHeight: 480,
          background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
          borderRadius: 12, boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
          zIndex: 9999, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--surface-4)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>
                🔔 Alertas del sistema
                {unread > 0 && <span style={{ marginLeft: 6, background: 'var(--danger-bg)', color: 'var(--danger)',
                  borderRadius: 10, padding: '1px 7px', fontSize: "var(--text-2xs)" }}>{unread} nuevas</span>}
              </div>
              <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 2 }}>
                SLA vencidos · tareas atrasadas · alertas de proyecto
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {unread > 0 && (
                <button onClick={() => markAllRead()} style={{ fontSize: "var(--text-xs)", color: 'var(--accent)',
                  background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>
                  Marcar todo leído
                </button>
              )}
              <button onClick={() => setOpen(false)} style={{ fontSize: "var(--text-lg)", color: 'var(--text-2)',
                background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
            </div>
          </div>

          <div style={{ overflowY: 'auto', flex: 1 }}>
            {alerts.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
                <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 8 }}>✓</div>
                Sin notificaciones pendientes
              </div>
            ) : alerts.slice(0, 20).map(a => (
              <button key={a.id}
                onClick={() => { markRead(a.id); setOpen(false); nav('/alerts') }}
                style={{
                  padding: '12px 16px', borderBottom: '1px solid var(--surface-4)',
                  cursor: 'pointer', background: a.is_read ? 'transparent' : 'rgba(79,142,247,0.02)',
                  display: 'flex', gap: 10, alignItems: 'flex-start',
                  transition: 'background 0.1s',
                  width: '100%',
                  borderLeft: 'none',
                  borderRight: 'none',
                  borderTop: 'none',
                  textAlign: 'left',
                }}
                type="button"
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
                onMouseLeave={e => e.currentTarget.style.background = a.is_read ? 'transparent' : 'rgba(79,142,247,0.02)'}
              >
                <div style={{ width: 8, height: 8, borderRadius: '50%', marginTop: 4, flexShrink: 0,
                  background: SEV_COLOR[a.severity] || 'var(--text-2)',
                  opacity: a.is_read ? 0.3 : 1 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: a.is_read ? 400 : 600,
                    color: a.is_read ? 'var(--text-2)' : 'var(--text-1)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {a.title}
                  </div>
                  {a.message && (
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {a.message}
                    </div>
                  )}
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 3 }}>
                    {a.created_at?.slice(0, 16)?.replace('T', ' ')}
                  </div>
                </div>
                {!a.is_read && (
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', flexShrink: 0, marginTop: 4 }} />
                )}
              </button>
            ))}
          </div>

          <div style={{ padding: '10px 16px', borderTop: '1px solid var(--surface-4)' }}>
            <button onClick={() => { nav('/alerts'); setOpen(false) }}
              style={{ width: '100%', background: 'transparent', border: '1px solid var(--surface-4)',
                borderRadius: 8, color: 'var(--text-2)', padding: '7px', cursor: 'pointer',
                fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              Ver todas las alertas →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
