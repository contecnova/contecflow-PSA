/**
 * Edición simultánea de una página del cuaderno (Yjs) por `/ws/notebook/{id}`.
 *
 * Mismo protocolo que `/ws/doc` (hooks/useDocCollab.ts): actualizaciones Yjs en
 * base64. Diferencias: el `Y.Doc` lo crea el editor (TipTap Collaboration) y se
 * manda el estado completo al entrar y cada vez que entra otra persona, para que
 * quien llega tarde reciba lo que aún no se guardó. Ticket de un solo uso
 * (`/ws/ticket`), reconexión con espera creciente. Solo se conecta si la página
 * está compartida (`activo`).
 */
import { useEffect, useRef, useState } from 'react'
import * as Y from 'yjs'
import api, { apiWsUrl } from '../../services/api'

const TOPE_ESPERA_MS = 30_000

export function aBase64(u: Uint8Array): string {
  let s = ''
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000))
  return btoa(s)
}

export function deBase64(b: string): Uint8Array {
  const bin = atob(b)
  const u = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) u[i] = bin.charCodeAt(i)
  return u
}

export const ORIGEN_REMOTO = 'cuaderno-remoto'

export function useColaboracion(pageId: string | null, ydoc: Y.Doc | null, activo: boolean): { conectado: boolean; companeros: number } {
  const [conectado, setConectado] = useState(false)
  const [companeros, setCompaneros] = useState(0)
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!pageId || !ydoc || !activo) return undefined
    let cancelado = false
    let intentos = 0
    let temporizador: ReturnType<typeof setTimeout> | null = null

    const mandarEstado = () => {
      const s = ws.current
      if (s?.readyState === WebSocket.OPEN) {
        try { s.send(JSON.stringify({ type: 'update', data: aBase64(Y.encodeStateAsUpdate(ydoc)) })) } catch { /* reintenta al reconectar */ }
      }
    }
    const alCambiar = (u: Uint8Array, origen: unknown) => {
      if (origen === ORIGEN_REMOTO) return
      const s = ws.current
      if (s?.readyState === WebSocket.OPEN) {
        try { s.send(JSON.stringify({ type: 'update', data: aBase64(u) })) } catch { /* ídem */ }
      }
    }
    ydoc.on('update', alCambiar)

    const reintentar = () => {
      if (cancelado) return
      const espera = Math.min(1000 * 2 ** intentos, TOPE_ESPERA_MS)
      intentos += 1
      temporizador = setTimeout(conectar, espera)
    }

    async function conectar() {
      if (cancelado) return
      try {
        const ticket = ((await api.get('/ws/ticket')).data as { ticket?: string })?.ticket
        if (cancelado || !ticket) { reintentar(); return }
        const s = new WebSocket(apiWsUrl(`/ws/notebook/${encodeURIComponent(pageId!)}?ticket=${encodeURIComponent(ticket)}`))
        ws.current = s
        s.onopen = () => { intentos = 0; setConectado(true); mandarEstado() }
        s.onclose = () => { setConectado(false); setCompaneros(0); ws.current = null; reintentar() }
        s.onerror = () => s.close()
        s.onmessage = ev => {
          try {
            const m = JSON.parse(ev.data as string) as { type?: string; data?: string; peers?: number; user_id?: string }
            if (m.type === 'update' && m.data) {
              Y.applyUpdate(ydoc, deBase64(m.data), ORIGEN_REMOTO)
            } else if (m.type === 'joined' || m.type === 'left') {
              setCompaneros(Math.max(0, (m.peers ?? 1) - 1))
              if (m.type === 'joined') mandarEstado()
            }
          } catch { /* mensaje roto: se ignora */ }
        }
      } catch {
        reintentar()
      }
    }
    void conectar()

    return () => {
      cancelado = true
      if (temporizador) clearTimeout(temporizador)
      ydoc.off('update', alCambiar)
      ws.current?.close()
      ws.current = null
      setConectado(false)
      setCompaneros(0)
    }
  }, [pageId, ydoc, activo])

  return { conectado, companeros }
}
