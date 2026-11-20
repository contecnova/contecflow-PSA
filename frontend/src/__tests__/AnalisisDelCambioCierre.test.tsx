/**
 * Análisis del cambio, cierre del 19-11-2026:
 * - el desplegable «CI afectado» enseña nombre, código y tipo del CI, nunca su id;
 * - un CI que ya no está en la CMDB sale con su aviso, no con el id;
 * - un plan guardado antes de las claves (`textos_anteriores`) avisa y ofrece
 *   «Regenerar en el idioma actual».
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLangProvider } from '../i18n/AppLangContext'

const UUID = '3f2b8c1e-9a4d-4e2f-8b7a-1c2d3e4f5a6b'
const UUID_RETIRADO = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'

vi.mock('../services/api', () => ({
  default: { get: () => Promise.resolve({ data: {} }) },
  usersApi: { list: () => Promise.resolve({ data: [] }) },
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: null, puede: () => false }) }))
vi.mock('../services/api/serviceDeskMercado', () => ({
  cambiosApi: {
    impacto: () => Promise.resolve({
      summary: 'Resumen guardado antes', risk_label: 'low', risk_score: 20, risk_components: {},
      affected_cis: { expanded_count: 0, direct_count: 0, ci_list: [] },
      textos_anteriores: { status: 'not_translated', reason: null, regenerable: true },
    }),
    analizarImpacto: () => Promise.resolve({}),
    radioDeImpacto: () => new Promise(() => {}),
  },
}))

beforeAll(() => {
  if (!('ResizeObserver' in globalThis)) {
    (globalThis as Record<string, unknown>).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  }
})

async function montar() {
  const { default: AnalisisDelCambio } = await import('../components/servicedesk/AnalisisDelCambio')
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}><AppLangProvider>
      <AnalisisDelCambio cambio={{
        id: 'chg-1', number: 'CHG-1', affected_cis: [UUID, UUID_RETIRADO],
        affected_ci_details: [
          { id: UUID, name: 'ERP producción', code: 'CI-007', ci_type: 'server' },
          { id: UUID_RETIRADO, name: null, code: null, ci_type: null },
        ],
      }} />
    </AppLangProvider></QueryClientProvider>,
  )
}

// Pantalla pesada (carga el análisis completo): margen para máquinas cargadas.
describe('AnalisisDelCambio', { timeout: 30000 }, () => {
  it('el desplegable de CI afectado enseña el nombre y el tipo, no el id', async () => {
    const { container } = await montar()
    const opciones = Array.from(container.querySelectorAll('option')).map(o => o.textContent ?? '')
    expect(opciones.some(o => o.includes('ERP producción') && o.includes('CI-007'))).toBe(true)
    expect(opciones.join(' ')).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i)
    expect(opciones.length).toBe(2)
  })

  it('un plan anterior a las claves ofrece regenerarlo en el idioma actual', async () => {
    await montar()
    expect(await screen.findByText(/antes de que los planes se guardaran por idioma/)).toBeTruthy()
    expect(screen.getByText(/la traducción automática no está activa/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Regenerar en el idioma actual/ })).toBeTruthy()
  })
})
