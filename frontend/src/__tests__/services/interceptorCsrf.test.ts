// Auditoría 05 (C.2), 23-11-2026: el interceptor de peticiones del cliente
// (`_core.ts`) manda `X-CSRF-Token` (cookie `csrf_token`) solo en los métodos
// que escriben, y el de respuestas desenvuelve los sobres.
import { describe, it, expect, afterEach } from 'vitest'
import type { InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import api from '../../services/api/_core'

type Capturada = { config: InternalAxiosRequestConfig }

// Adaptador falso: devuelve lo que se le pida sin red y guarda la petición.
function conAdaptador(cuerpo: unknown, capturas: Capturada[]) {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    capturas.push({ config })
    return { data: cuerpo, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse
  }
}

afterEach(() => { document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' })

describe('interceptores de _core', () => {
  it('añade X-CSRF-Token en POST y no en GET', async () => {
    document.cookie = 'csrf_token=abc123; path=/'
    const capturas: Capturada[] = []
    conAdaptador({ ok: true }, capturas)
    await api.get('/cualquiera')
    await api.post('/cualquiera', {})
    const cab = (i: number) => (capturas[i].config.headers as unknown as Record<string, string>)['X-CSRF-Token']
    expect(cab(0)).toBeUndefined()
    expect(cab(1)).toBe('abc123')
  })

  it('desenvuelve {items, meta}', async () => {
    conAdaptador({ items: [1, 2], meta: { total: 2 } }, [])
    const r = await api.get('/lista') as AxiosResponse<number[]> & { meta?: { total: number } }
    expect(r.data).toEqual([1, 2])
    expect(r.meta).toEqual({ total: 2 })
  })
})
