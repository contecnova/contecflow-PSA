import { describe, it, expect, vi } from 'vitest'
import {
  debeRefrescar,
  trasEscritura,
  registrarClienteDeConsultas,
  AGRUPAR_ESCRITURAS_MS,
} from '../../services/api/refrescoTrasEscritura'

describe('refrescoTrasEscritura', () => {
  it('refresca tras escrituras y no tras lecturas ni rutas excluidas', () => {
    expect(debeRefrescar('post', '/clients')).toBe(true)
    expect(debeRefrescar('PATCH', '/clients/1/contacts/2')).toBe(true)
    expect(debeRefrescar('get', '/clients')).toBe(false)
    expect(debeRefrescar('post', '/auth/login')).toBe(false)
    expect(debeRefrescar('post', '/translation/messages')).toBe(false)
    expect(debeRefrescar(undefined, '/clients')).toBe(false)
  })

  it('agrupa varias escrituras seguidas en un solo refresco', () => {
    vi.useFakeTimers()
    const invalidateQueries = vi.fn()
    registrarClienteDeConsultas({ invalidateQueries } as never)
    trasEscritura('post', '/clients')
    trasEscritura('put', '/clients/1')
    trasEscritura('get', '/clients')
    vi.advanceTimersByTime(AGRUPAR_ESCRITURAS_MS)
    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({ refetchType: 'active' })
    vi.useRealTimers()
  })
})
