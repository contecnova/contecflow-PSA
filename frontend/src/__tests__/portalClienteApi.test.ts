// Auditoría 2026-11: el cliente HTTP del portal solo desenvolvía listas; el
// login responde `{data, meta}` y nadie podía entrar al portal.
import { describe, it, expect } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { CLIENT_API } from '../pages/portal-client/portalClientContext'

const responder = (body: unknown) => {
  CLIENT_API.defaults.adapter = async (config: InternalAxiosRequestConfig) =>
    ({ data: body, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse)
}

describe('CLIENT_API', () => {
  it('desenvuelve el sobre de objeto {data, meta}', async () => {
    responder({ data: { ok: true, client: { id: 'c1' } }, meta: null })
    const res = await CLIENT_API.post('/portal/auth/login', {})
    expect(res.data.client.id).toBe('c1')
  })
  it('no toca un objeto que solo tiene una clave data', async () => {
    responder({ data: [1, 2], weeks: 3 })
    const res = await CLIENT_API.get('/x')
    expect(res.data).toEqual({ data: [1, 2], weeks: 3 })
  })
})
