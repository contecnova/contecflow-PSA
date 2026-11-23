// 23-11-2026 (auditoría 05, A.3): un solo desenvoltorio de sobres para el
// cliente de la aplicación (`_core.ts`) y el del portal.
import { describe, it, expect } from 'vitest'
import type { AxiosResponse } from 'axios'
import { desenvolverSobre } from '../../services/api/clienteBase'

const resp = (data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config: {} }) as unknown as AxiosResponse<unknown>

describe('desenvolverSobre', () => {
  it('lista {items, meta}: data es el array y meta la paginación', () => {
    const r = desenvolverSobre(resp({ items: [1, 2], meta: { total: 2 } }))
    expect(r.data).toEqual([1, 2])
    expect(r.meta).toEqual({ total: 2 })
  })

  it('objeto {data, meta}: data es el contenido', () => {
    const r = desenvolverSobre(resp({ data: { id: 'x' }, meta: { ok: true } }))
    expect(r.data).toEqual({ id: 'x' })
    expect(r.meta).toEqual({ ok: true })
  })

  it('no toca payloads con más claves ni arrays sueltos', () => {
    expect(desenvolverSobre(resp({ data: 1, weeks: 2 })).data).toEqual({ data: 1, weeks: 2 })
    expect(desenvolverSobre(resp({ items: [1], meta: {}, extra: 1 })).data).toEqual({ items: [1], meta: {}, extra: 1 })
    expect(desenvolverSobre(resp([1, 2])).data).toEqual([1, 2])
  })
})
