/**
 * ChatRealtimeProvider — single, app-wide WebSocket for /collaboration.
 *
 * Lives at the AppShell level so chat events arrive while the user is on any
 * page. Responsibilities:
 *   • Maintain the WebSocket connection (auto-reconnect, ping/pong).
 *   • Invalidate React Query caches for messages / conversations / presence /
 *     notifications.
 *   • Track an unread counter for the nav badge.
 *   • Surface a toast (and a desktop notification when permitted) when a new
 *     message arrives in a conversation other than the one you're looking at.
 *   • Re-emit `collab:typing` and `collab:resync` as DOM events for ChatPage.
 */
import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './AuthContext'
import { useToast } from './ToastContext'
import { collabApi } from '../services/collaborationApi'

const ChatRealtimeContext = createContext({ unread: 0, refresh: () => {}, send: () => false })

export function useChatRealtime() {
  return useContext(ChatRealtimeContext)
}

export default function ChatRealtimeProvider({ children }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const location = useLocation()

  const [unread, setUnread] = useState(0)
  const wsRef = useRef(null)

  // Keep the latest pathname + active conv id (from ?conv=) in refs so the
  // single useEffect WS handler doesn't tear down on every route change.
  const locationRef = useRef(location)
  useEffect(() => { locationRef.current = location }, [location])

  const refresh = useCallback(async () => {
    if (!user?.id) return
    try {
      const list = await collabApi.listNotifications(true)
      setUnread((list || []).length)
    } catch { /* noop */ }
  }, [user?.id])

  useEffect(() => {
    if (!user?.id) {
      setUnread(0)
      return
    }
    refresh()
    const t = setInterval(refresh, 60_000)
    return () => clearInterval(t)
  }, [user?.id, refresh])

  // Single WebSocket for the whole app
  useEffect(() => {
    if (!user?.id) return

    let cancelled = false
    let stoppedByLogout = false
    let ws
    let pingInterval
    let reconnectTimer
    let attempt = 0

    const connect = async () => {
      if (cancelled || stoppedByLogout || attempt >= 8) return
      attempt += 1
      try {
        const r = await fetch('/api/v1/ws/ticket', { credentials: 'include' })
        if (!r.ok) {
          // Token might have just expired — give up quietly; useEffect will
          // remount when user changes.
          return
        }
        const { ticket } = await r.json()
        if (!ticket || cancelled) return
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        ws = new WebSocket(`${proto}://${window.location.host}/api/v1/collaboration/ws?ticket=${encodeURIComponent(ticket)}`)
        wsRef.current = ws
        ws.onopen = () => { attempt = 0 }
        ws.onmessage = (event) => {
          try {
            const ev = JSON.parse(event.data)
            handleEvent(ev)
          } catch { /* noop */ }
        }
        ws.onclose = (closeEv) => {
          wsRef.current = null
          if (cancelled || stoppedByLogout || closeEv.code === 1000) return
          reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
        }
        if (pingInterval) clearInterval(pingInterval)
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
        }, 25000)
      } catch {
        if (!cancelled && !stoppedByLogout) {
          reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
        }
      }
    }

    function handleEvent(ev) {
      if (!ev?.type) return
      if (ev.type === 'message.created' && ev.conversation_id) {
        qc.invalidateQueries(['collab-messages', ev.conversation_id])
        qc.invalidateQueries(['collab-conversations'])
        notifyNewMessage(ev)
      } else if (
        ev.type === 'message.updated' || ev.type === 'message.deleted' ||
        ev.type.startsWith?.('reaction.') || ev.type === 'message.pinned' ||
        ev.type === 'message.unpinned' || ev.type === 'read.updated'
      ) {
        if (ev.conversation_id) qc.invalidateQueries(['collab-messages', ev.conversation_id])
      } else if (ev.type === 'notification.new') {
        qc.invalidateQueries(['collab-notifications'])
        refresh()
      } else if (ev.type === 'presence.updated') {
        qc.invalidateQueries(['collab-presence'])
      } else if (ev.type === 'typing') {
        window.dispatchEvent(new CustomEvent('collab:typing', { detail: ev }))
      }
    }

    function notifyNewMessage(ev) {
      // Don't notify your own messages
      const senderId = ev.payload?.user_id || ev.user_id
      if (senderId && senderId === user.id) return

      const path = locationRef.current?.pathname || ''
      const onChatPage = path.startsWith('/chat') && !path.startsWith('/chat/admin')
      const activeConvId = onChatPage ? new URLSearchParams(locationRef.current?.search).get('conv') : null
      const sameConv = activeConvId && ev.conversation_id === activeConvId
      // If user is reading the conversation, no popup needed
      if (sameConv && document.visibilityState === 'visible') return

      // Increment unread (the server is the source of truth via refresh, but
      // we bump optimistically so the badge feels responsive)
      setUnread((n) => n + 1)

      const senderName = ev.payload?.user_name || ev.payload?.user?.name || 'Nuevo mensaje'
      const body = (ev.payload?.body || '').toString().slice(0, 140) || 'Adjunto / actividad nueva'

      // In-app toast (the toast API takes only msg + duration)
      try { toast.info(`${senderName}: ${body}`, 6000) } catch { /* noop */ }

      // Native desktop notification when tab is hidden
      try {
        if (typeof Notification !== 'undefined' &&
            Notification.permission === 'granted' &&
            document.visibilityState !== 'visible') {
          const n = new Notification(senderName, {
            body, icon: '/favicon.ico', tag: `collab-${ev.conversation_id}`,
          })
          n.onclick = () => {
            try { window.focus() } catch { /* noop */ }
            window.location.href = `/chat?conv=${encodeURIComponent(ev.conversation_id)}`
            n.close()
          }
        }
      } catch { /* noop */ }
    }

    connect()

    const onResync = () => {
      try {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'resync' }))
        }
      } catch { /* noop */ }
    }
    const onLogout = () => {
      stoppedByLogout = true
      try { wsRef.current?.close(1000, 'logout') } catch { /* noop */ }
    }
    window.addEventListener('collab:resync', onResync)
    window.addEventListener('auth:logout-start', onLogout)
    window.addEventListener('auth:session-expired', onLogout)

    return () => {
      cancelled = true
      window.removeEventListener('collab:resync', onResync)
      window.removeEventListener('auth:logout-start', onLogout)
      window.removeEventListener('auth:session-expired', onLogout)
      if (pingInterval) clearInterval(pingInterval)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      try { ws && ws.readyState === WebSocket.OPEN && ws.close(1000, 'unmount') } catch { /* noop */ }
      wsRef.current = null
    }
    // user.id is the only relevant input — the rest are stable refs/methods
    // and we want a single connection per session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  // When the user opens /chat, clear the badge: optimistically zero the
  // counter and persist the change server-side via markAllRead. We then
  // re-sync from the server once it has applied the change.
  useEffect(() => {
    if (!user?.id) return
    if (location.pathname.startsWith('/chat') && !location.pathname.startsWith('/chat/admin')) {
      setUnread(0)
      collabApi.markAllRead()
        .catch(() => {})
        .finally(() => { qc.invalidateQueries(['collab-notifications']); refresh() })
    }
  }, [location.pathname, user?.id, refresh, qc])

  const send = useCallback((payload) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    try { ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload)); return true }
    catch { return false }
  }, [])

  return (
    <ChatRealtimeContext.Provider value={{ unread, refresh, send }}>
      {children}
    </ChatRealtimeContext.Provider>
  )
}
