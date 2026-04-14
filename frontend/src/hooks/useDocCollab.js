/**
 * useDocCollab — WebSocket-based real-time collaboration hook for wiki docs.
 *
 * Automatically fetches a short-lived WS token from GET /api/v1/ws/token,
 * then connects to ws://.../api/v1/ws/doc/<docId>?token=<jwt>
 * and broadcasts/receives block updates so multiple editors stay in sync.
 *
 * Reconnects with exponential back-off (1s → 2s → 4s … cap 30s) on close.
 *
 * Protocol:
 *   Send:    { type: 'update',    data: JSON.stringify(blocks) }
 *   Receive: { type: 'update',    data: '...', from: '<userId>' }
 *            { type: 'joined',    user_id: '...', peers: N }
 *            { type: 'left',      user_id: '...', peers: N }
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import api from '../services/api'

const WS_BASE = (import.meta.env.VITE_WS_URL || window.location.origin.replace(/^http/, 'ws'))
const BACKOFF_CAP_MS = 30_000

export function useDocCollab(docId, onRemoteUpdate) {
  const wsRef        = useRef(null)
  const retryRef     = useRef(0)      // attempt counter for back-off
  const cancelledRef = useRef(false)
  const [peers, setPeers]         = useState(0)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!docId) return

    cancelledRef.current = false
    retryRef.current = 0

    async function connect() {
      if (cancelledRef.current) return
      try {
        const { data } = await api.get('/ws/token')
        const token = data.token
        if (cancelledRef.current) return

        const url = `${WS_BASE}/api/v1/ws/doc/${encodeURIComponent(docId)}?token=${encodeURIComponent(token)}`
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          if (cancelledRef.current) { ws.close(); return }
          retryRef.current = 0   // reset back-off on successful connect
          setConnected(true)
        }

        ws.onclose = () => {
          setConnected(false)
          setPeers(0)
          wsRef.current = null
          if (!cancelledRef.current) {
            // Exponential back-off: 1s, 2s, 4s, 8s … capped at 30s
            const delay = Math.min(1000 * 2 ** retryRef.current, BACKOFF_CAP_MS)
            retryRef.current += 1
            setTimeout(connect, delay)
          }
        }

        ws.onerror = () => {
          // onclose fires right after onerror; let it handle reconnect
          ws.close()
        }

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'update' && msg.data) {
              try {
                const blocks = JSON.parse(msg.data)
                onRemoteUpdate?.(blocks)
              } catch { /* ignore malformed */ }
            } else if (msg.type === 'joined' || msg.type === 'left') {
              setPeers(msg.peers ?? 0)
            }
          } catch { /* ignore */ }
        }
      } catch {
        // Token fetch failed — retry with back-off
        if (!cancelledRef.current) {
          const delay = Math.min(1000 * 2 ** retryRef.current, BACKOFF_CAP_MS)
          retryRef.current += 1
          setTimeout(connect, delay)
        }
      }
    }

    connect()

    return () => {
      cancelledRef.current = true
      wsRef.current?.close()
      wsRef.current = null
      setConnected(false)
      setPeers(0)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId])

  const sendUpdate = useCallback((blocks) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'update', data: JSON.stringify(blocks) }))
    }
  }, [])

  return { connected, peers, sendUpdate }
}
