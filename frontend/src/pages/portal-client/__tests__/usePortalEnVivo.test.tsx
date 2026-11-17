// WebSocket del portal compartido (17-11-2026): la página del portal y el chat
// en vivo usan una sola conexión; el chat manda «escribiendo» y «leído» por ella.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'

const h = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../portalClientContext', () => ({ CLIENT_API: { get: h.get } }))
vi.mock('../../../services/api/urls', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../services/api/urls')>()),
  apiWsUrl: (p: string) => `ws://x${p}`,
}))

import usePortalEnVivo, { _reiniciarPortalEnVivo, enviarPorElPortal } from '../usePortalEnVivo'
import { enviarPorAvisosEnVivo } from '../../../hooks/useAvisosEnVivo'

class SocketDoble {
  static CONNECTING = 0
  static OPEN = 1
  static creados: SocketDoble[] = []
  readyState = 0
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn(() => { this.readyState = 3 })
  send = vi.fn()
  constructor(url: string) { this.url = url; SocketDoble.creados.push(this) }
  abrir() { this.readyState = 1; this.onopen?.() }
}

beforeEach(() => {
  _reiniciarPortalEnVivo()
  SocketDoble.creados = []
  vi.stubGlobal('WebSocket', SocketDoble)
  h.get.mockReset().mockResolvedValue({ data: { ticket: 'tk' } })
})

function Uso({ id, log }: { id: string; log: string[] }) {
  const vivo = usePortalEnVivo(true, m => log.push(`${id}:${String(m.type)}:${String(m.event ?? '')}`))
  return <span data-testid={id}>{vivo ? 'si' : 'no'}</span>
}

describe('usePortalEnVivo', () => {
  it('una conexión para la página y el chat; los dos reciben; manda solo con el socket abierto', async () => {
    const log: string[] = []
    const { getByTestId, unmount } = render(<><Uso id="pagina" log={log} /><Uso id="chat" log={log} /></>)
    await waitFor(() => expect(SocketDoble.creados).toHaveLength(1))
    expect(h.get).toHaveBeenCalledWith('/ws/portal-ticket')
    expect(SocketDoble.creados[0].url).toBe('ws://x/ws/portal-notifications?ticket=tk')
    expect(enviarPorElPortal({ type: 'livechat_typing', conversation_id: 'c1' })).toBe(false)
    act(() => SocketDoble.creados[0].abrir())
    expect(getByTestId('chat')).toHaveTextContent('si')
    expect(enviarPorElPortal({ type: 'livechat_typing', conversation_id: 'c1' })).toBe(true)
    expect(JSON.parse(SocketDoble.creados[0].send.mock.calls[0][0])).toEqual({ type: 'livechat_typing', conversation_id: 'c1' })
    act(() => SocketDoble.creados[0].onmessage?.({ data: JSON.stringify({ type: 'livechat', event: 'message', conversation_id: 'c1' }) }))
    expect(log.sort()).toEqual(['chat:livechat:message', 'pagina:livechat:message'])
    const s = SocketDoble.creados[0]
    unmount()
    expect(s.close).toHaveBeenCalled()
    expect(enviarPorElPortal({ type: 'livechat_read' })).toBe(false)
  })

  it('reintenta si el socket se cae sin cerrarse bien', async () => {
    vi.useFakeTimers()
    try {
      render(<Uso id="chat" log={[]} />)
      await vi.waitFor(() => expect(SocketDoble.creados).toHaveLength(1))
      act(() => { SocketDoble.creados[0].abrir(); SocketDoble.creados[0].onclose?.({ code: 1006 }) })
      expect(SocketDoble.creados[0]).toBeDefined()
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
      expect(SocketDoble.creados.length).toBe(2)
    } finally { vi.useRealTimers() }
  })
})

describe('enviarPorAvisosEnVivo', () => {
  it('sin socket de avisos abierto no manda nada', () => {
    expect(enviarPorAvisosEnVivo({ type: 'channel_watch' })).toBe(false)
  })
})
