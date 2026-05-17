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
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './AuthContext'
import { useToast } from './ToastContext'
// TODO type: services/collaborationApi still JS — types inferred at the call site
import { collabApi } from '../services/collaborationApi'
import { API_BASE } from '../constants/api'
import { resolveWsBase } from '../utils/wsUtils'

// ── Public domain types ─────────────────────────────────────────────────

/**
 * A chat message as broadcast over the WebSocket.
 * The backend currently sends a loose envelope; consumers should treat
 * unknown fields as optional.
 */
export interface ChatMessage {
  id?: string
  conversation_id?: string
  user_id?: string
  user_name?: string
  user?: { id?: string; name?: string }
  body?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

/**
 * Presence record for a single user.
 */
export interface Presence {
  user_id: string
  status: 'online' | 'away' | 'busy' | 'offline' | string
  last_seen?: string | null
  [key: string]: unknown
}

/**
 * Discriminated union of every WS event the chat realtime layer recognises.
 * Unknown event types are accepted but not narrowed further.
 */
export type WSEvent =
  | { type: 'message.created'; conversation_id?: string; payload?: ChatMessage; user_id?: string }
  | { type: 'message.updated'; conversation_id?: string; payload?: ChatMessage }
  | { type: 'message.deleted'; conversation_id?: string; payload?: ChatMessage }
  | { type: 'message.pinned'; conversation_id?: string; payload?: ChatMessage }
  | { type: 'message.unpinned'; conversation_id?: string; payload?: ChatMessage }
  | { type: 'reaction.added' | 'reaction.removed' | string; conversation_id?: string; payload?: unknown }
  | { type: 'read.updated'; conversation_id?: string; payload?: unknown }
  | { type: 'notification.new'; conversation_id?: string; payload?: unknown }
  | { type: 'presence.updated'; conversation_id?: string; payload?: Presence }
  | { type: 'typing'; conversation_id?: string; user_id?: string; payload?: unknown }
  | { type: string; conversation_id?: string; user_id?: string; payload?: unknown }

/**
 * Payload sent over the WS via `send()`. Strings are passed through
 * verbatim; objects are JSON-encoded.
 */
export type SendPayload = string | Record<string, unknown>

export interface ChatRealtimeContextValue {
  unread: number
  refresh: () => Promise<void> | void
  send: (payload: SendPayload) => boolean
  consumeUnread: (count?: number) => void
  clearUnread: () => void
}

const defaultContextValue: ChatRealtimeContextValue = {
  unread: 0,
  refresh: () => {},
  send: () => false,
  consumeUnread: () => {},
  clearUnread: () => {},
}

const ChatRealtimeContext = createContext<ChatRealtimeContextValue>(defaultContextValue)

export function useChatRealtime(): ChatRealtimeContextValue {
  return useContext(ChatRealtimeContext)
}

interface ChatRealtimeProviderProps {
  children?: ReactNode
}

export default function ChatRealtimeProvider({ children }: ChatRealtimeProviderProps) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const location = useLocation()

  const [unread, setUnread] = useState<number>(0)
  const wsRef = useRef<WebSocket | null>(null)

  // Keep the latest pathname + active conv id (from ?conv=) in refs so the
  // single useEffect WS handler doesn't tear down on every route change.
  const locationRef = useRef(location)
  useEffect(() => { locationRef.current = location }, [location])

  const refresh = useCallback(async (): Promise<void> => {
    if (!user?.id) return
    try {
      // TODO type: collabApi still JS — returns notification array
      const list: unknown[] = await collabApi.listNotifications(true)
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

  // Pide permiso para notificaciones del SO una vez tras el primer login en
  // este navegador (idempotente). Si el usuario lo deniega, no insistimos.
  useEffect(() => {
    if (!user?.id) return
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'default') return
    const KEY = 'collab-notif-asked'
    if (sessionStorage.getItem(KEY)) return
    sessionStorage.setItem(KEY, '1')
    try { Notification.requestPermission().catch(() => {}) } catch { /* noop */ }
  }, [user?.id])

  // Single WebSocket for the whole app
  useEffect(() => {
    if (!user?.id) return

    let cancelled = false
    let stoppedByLogout = false
    let ws: WebSocket | undefined
    let pingInterval: ReturnType<typeof setInterval> | undefined
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0

    const connect = async (): Promise<void> => {
      if (cancelled || stoppedByLogout || attempt >= 8) return
      attempt += 1
      try {
        // #45: kept as fetch() — side-effects/realtime/optimistic
        const r = await fetch(`${API_BASE}/ws/ticket`, { credentials: 'include' })
        if (!r.ok) {
          // Token might have just expired — give up quietly; useEffect will
          // remount when user changes.
          return
        }
        const { ticket } = (await r.json()) as { ticket?: string }
        if (!ticket || cancelled) return
        const wsBase = resolveWsBase()
        ws = new WebSocket(`${wsBase}/api/v1/collaboration/ws?ticket=${encodeURIComponent(ticket)}`)
        wsRef.current = ws
        ws.onopen = () => { attempt = 0 }
        ws.onmessage = (event: MessageEvent) => {
          try {
            const ev = JSON.parse(event.data as string) as WSEvent
            handleEvent(ev)
          } catch { /* noop */ }
        }
        ws.onclose = (closeEv: CloseEvent) => {
          wsRef.current = null
          if (cancelled || stoppedByLogout || closeEv.code === 1000) return
          // 4401 = ticket inválido/expirado · 4403 = usuario sin permiso (p.ej.
          // superadmin sin organización). Son rechazos definitivos: no
          // reintentamos para no spammear consola/red.
          if (closeEv.code === 4401 || closeEv.code === 4403) return
          reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
        }
        if (pingInterval) clearInterval(pingInterval)
        pingInterval = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
        }, 25000)
      } catch {
        if (!cancelled && !stoppedByLogout) {
          reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** (attempt - 1), 30000))
        }
      }
    }

    function handleEvent(ev: WSEvent): void {
      if (!ev?.type) return
      if (ev.type === 'message.created' && ev.conversation_id) {
        // TODO type: @tanstack/react-query v5 invalidateQueries signature
        qc.invalidateQueries(['collab-messages', ev.conversation_id] as unknown as Parameters<typeof qc.invalidateQueries>[0])
        qc.invalidateQueries(['collab-conversations'] as unknown as Parameters<typeof qc.invalidateQueries>[0])
        notifyNewMessage(ev)
      } else if (
        ev.type === 'message.updated' || ev.type === 'message.deleted' ||
        ev.type.startsWith?.('reaction.') || ev.type === 'message.pinned' ||
        ev.type === 'message.unpinned' || ev.type === 'read.updated'
      ) {
        if (ev.conversation_id) qc.invalidateQueries(['collab-messages', ev.conversation_id] as unknown as Parameters<typeof qc.invalidateQueries>[0])
      } else if (ev.type === 'notification.new') {
        qc.invalidateQueries(['collab-notifications'] as unknown as Parameters<typeof qc.invalidateQueries>[0])
        refresh()
      } else if (ev.type === 'presence.updated') {
        qc.invalidateQueries(['collab-presence'] as unknown as Parameters<typeof qc.invalidateQueries>[0])
      } else if (ev.type === 'typing') {
        window.dispatchEvent(new CustomEvent('collab:typing', { detail: ev }))
      }
    }

    function notifyNewMessage(ev: WSEvent): void {
      // Don't notify your own messages
      const payload = (ev as { payload?: ChatMessage }).payload
      const senderId = payload?.user_id || (ev as { user_id?: string }).user_id
      if (senderId && senderId === user?.id) return

      const path = locationRef.current?.pathname || ''
      const onChatPage = path.startsWith('/chat') && !path.startsWith('/chat/admin')
      const activeConvId = onChatPage ? new URLSearchParams(locationRef.current?.search).get('conv') : null
      const sameConv = activeConvId && ev.conversation_id === activeConvId
      // If user is reading the conversation, no popup needed
      if (sameConv && document.visibilityState === 'visible') return

      // Increment unread (the server is the source of truth via refresh, but
      // we bump optimistically so the badge feels responsive)
      setUnread((n) => n + 1)

      const senderName = payload?.user_name || payload?.user?.name || 'Nuevo mensaje'
      const body = (payload?.body || '').toString().slice(0, 140) || 'Adjunto / actividad nueva'

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
            window.location.href = `/chat?conv=${encodeURIComponent(ev.conversation_id || '')}`
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
        .finally(() => {
          // TODO type: @tanstack/react-query v5 invalidateQueries signature
          qc.invalidateQueries(['collab-notifications'] as unknown as Parameters<typeof qc.invalidateQueries>[0])
          refresh()
        })
    }
  }, [location.pathname, user?.id, refresh, qc])

  const send = useCallback((payload: SendPayload): boolean => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    try { ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload)); return true }
    catch { return false }
  }, [])

  const consumeUnread = useCallback((count: number = 1): void => {
    const n = Number(count || 0)
    if (n <= 0) return
    setUnread((prev) => Math.max(0, prev - n))
  }, [])

  const clearUnread = useCallback((): void => {
    setUnread(0)
  }, [])

  return (
    <ChatRealtimeContext.Provider value={{ unread, refresh, send, consumeUnread, clearUnread }}>
      {children}
    </ChatRealtimeContext.Provider>
  )
}
