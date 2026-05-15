/**
 * useDocCollab — Yjs CRDT collaboration over existing ws/doc backend protocol.
 *
 * Transport payloads are base64-encoded Yjs binary updates.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import * as Y from 'yjs'
// TODO type: services/api still JS.
import api from '../services/api'

type Block = unknown

interface YObserveEvent {
  transaction: { origin: unknown }
}

interface UnsubRef {
  docUpdate: ((update: Uint8Array, origin: unknown) => void) | null
  textObserve: ((evt: YObserveEvent) => void) | null
}

export interface UseDocCollabResult {
  connected: boolean
  peers: number
  sendUpdate: (blocks: Block[]) => void
}

// TODO type: vite import.meta.env not declared globally yet.
const VITE_WS_URL = (import.meta as unknown as { env?: { VITE_WS_URL?: string } }).env?.VITE_WS_URL
const WS_BASE: string = VITE_WS_URL || window.location.origin.replace(/^http/, 'ws')
const BACKOFF_CAP_MS = 30_000

function uint8ToBase64(uint8: Uint8Array): string {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < uint8.length; i += chunkSize) {
    const chunk = uint8.subarray(i, i + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

function base64ToUint8(base64: string): Uint8Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

export function useDocCollab(docId: string | undefined, onRemoteUpdate?: (blocks: Block[]) => void): UseDocCollabResult {
  const wsRef = useRef<WebSocket | null>(null)
  const ydocRef = useRef<Y.Doc | null>(null)
  const ytextRef = useRef<Y.Text | null>(null)
  const retryRef = useRef<number>(0)
  const cancelledRef = useRef<boolean>(false)
  const unsubRef = useRef<UnsubRef>({ docUpdate: null, textObserve: null })
  const [peers, setPeers] = useState<number>(0)
  const [connected, setConnected] = useState<boolean>(false)

  const applyLocalBlocks = useCallback((blocks: Block[]) => {
    const ydoc = ydocRef.current
    const ytext = ytextRef.current
    if (!ydoc || !ytext) return
    const serialized = JSON.stringify(Array.isArray(blocks) ? blocks : [])
    ydoc.transact(() => {
      ytext.delete(0, ytext.length)
      ytext.insert(0, serialized)
    }, 'local-ui')
  }, [])

  useEffect(() => {
    if (!docId) return

    cancelledRef.current = false
    retryRef.current = 0

    const ydoc = new Y.Doc()
    const ytext = ydoc.getText('blocks')
    ydocRef.current = ydoc
    ytextRef.current = ytext

    const onDocUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin === 'remote') return
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      try {
        ws.send(JSON.stringify({ type: 'update', data: uint8ToBase64(update) }))
      } catch {
        // ignore transient socket errors
      }
    }

    const onTextObserve = (evt: YObserveEvent) => {
      if (evt.transaction.origin !== 'remote') return
      try {
        const raw = ytext.toString()
        const blocks = raw ? JSON.parse(raw) : []
        onRemoteUpdate?.(Array.isArray(blocks) ? blocks : [])
      } catch {
        // ignore malformed payload
      }
    }

    ydoc.on('update', onDocUpdate)
    ytext.observe(onTextObserve)
    unsubRef.current = { docUpdate: onDocUpdate, textObserve: onTextObserve }

    async function connect() {
      if (cancelledRef.current) return
      try {
        const { data } = await api.get('/ws/token')
        const token = (data as { token: string }).token
        if (cancelledRef.current) return

        const url = `${WS_BASE}/api/v1/ws/doc/${encodeURIComponent(docId!)}?token=${encodeURIComponent(token)}`
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          if (cancelledRef.current) { ws.close(); return }
          retryRef.current = 0
          setConnected(true)
          try {
            const state = Y.encodeStateAsUpdate(ydoc)
            if (state?.length) {
              ws.send(JSON.stringify({ type: 'update', data: uint8ToBase64(state) }))
            }
          } catch {
            // ignore bootstrap sync errors
          }
        }

        ws.onclose = () => {
          setConnected(false)
          setPeers(0)
          wsRef.current = null
          if (!cancelledRef.current) {
            const delay = Math.min(1000 * 2 ** retryRef.current, BACKOFF_CAP_MS)
            retryRef.current += 1
            setTimeout(connect, delay)
          }
        }

        ws.onerror = () => {
          ws.close()
        }

        ws.onmessage = (event: MessageEvent) => {
          try {
            const msg = JSON.parse(event.data as string) as { type?: string; data?: string; peers?: number }
            if (msg.type === 'update' && msg.data) {
              try {
                const update = base64ToUint8(msg.data)
                Y.applyUpdate(ydoc, update, 'remote')
              } catch {
                // ignore malformed update
              }
            } else if (msg.type === 'joined' || msg.type === 'left') {
              setPeers(msg.peers ?? 0)
            }
          } catch {
            // ignore malformed websocket messages
          }
        }
      } catch {
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

      if (unsubRef.current.textObserve && ytextRef.current) {
        ytextRef.current.unobserve(unsubRef.current.textObserve)
      }
      if (unsubRef.current.docUpdate && ydocRef.current) {
        ydocRef.current.off('update', unsubRef.current.docUpdate)
      }
      ydocRef.current?.destroy()
      ydocRef.current = null
      ytextRef.current = null
    }

  }, [docId, onRemoteUpdate])

  return { connected, peers, sendUpdate: applyLocalBlocks }
}
