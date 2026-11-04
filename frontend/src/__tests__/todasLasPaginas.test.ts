// Auditoría 2026-11: los selectores se quedaban en las 50 primeras filas.
import { vi, describe, it, expect } from 'vitest'

const get = vi.fn()
vi.mock('../services/api/_core', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

import { todasLasPaginas } from '../services/api/todasLasPaginas'

function pagina(n: number, desde: number, total: number) {
  return { data: Array.from({ length: n }, (_, i) => ({ id: desde + i })), meta: { total } }
}

describe('todasLasPaginas', () => {
  it('recorre todas las páginas, sin el alias limit', async () => {
    get.mockReset()
    get.mockResolvedValueOnce(pagina(200, 0, 450)).mockResolvedValueOnce(pagina(200, 200, 450)).mockResolvedValueOnce(pagina(50, 400, 450))
    const r = await todasLasPaginas<{ id: number }>('/projects', { status: 'active', limit: 100 })
    expect(r.data).toHaveLength(450)
    expect(get).toHaveBeenCalledTimes(3)
    expect(get.mock.calls[2][1]).toEqual({ params: { status: 'active', page: 3, page_size: 200 } })
  })
  it('con page explícita hace una sola petición', async () => {
    get.mockReset()
    get.mockResolvedValueOnce(pagina(20, 0, 999))
    const r = await todasLasPaginas('/projects', { page: 2, page_size: 20 })
    expect(get).toHaveBeenCalledTimes(1)
    expect(r.data).toHaveLength(20)
  })
})
