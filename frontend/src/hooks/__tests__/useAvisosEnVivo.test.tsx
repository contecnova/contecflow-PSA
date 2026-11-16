// WebSocket de avisos compartido (16-11-2026): una conexión por pestaña aunque
// lo usen la campana y la bandeja a la vez.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'

const h = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../services/api', () => ({ default: { get: h.get }, apiWsUrl: (p: string) => `ws://x${p}` }))

import useAvisosEnVivo, { _reiniciarAvisosEnVivo } from '../useAvisosEnVivo'

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
  _reiniciarAvisosEnVivo()
  SocketDoble.creados = []
  vi.stubGlobal('WebSocket', SocketDoble)
  h.get.mockReset().mockResolvedValue({ data: { ticket: 'tk' } })
})

function Uso({ id, log }: { id: string; log: string[] }) {
  const vivo = useAvisosEnVivo(true, m => log.push(`${id}:${String(m.type)}`))
  return <span data-testid={id}>{vivo ? 'si' : 'no'}</span>
}

describe('useAvisosEnVivo', () => {
  it('dos usuarios comparten un socket; los dos reciben cada mensaje; el último lo cierra', async () => {
    const log: string[] = []
    const { getByTestId, unmount } = render(<><Uso id="campana" log={log} /><Uso id="bandeja" log={log} /></>)
    await waitFor(() => expect(SocketDoble.creados).toHaveLength(1))
    expect(h.get).toHaveBeenCalledTimes(1)
    expect(SocketDoble.creados[0].url).toBe('ws://x/ws/notifications?ticket=tk')
    act(() => SocketDoble.creados[0].abrir())
    expect(getByTestId('campana')).toHaveTextContent('si')
    expect(getByTestId('bandeja')).toHaveTextContent('si')
    act(() => SocketDoble.creados[0].onmessage?.({ data: JSON.stringify({ type: 'notifications', count: 1 }) }))
    expect(log.sort()).toEqual(['bandeja:notifications', 'campana:notifications'])
    const s = SocketDoble.creados[0]
    unmount()
    expect(s.close).toHaveBeenCalled()
  })
})
