// Auditoría 2026-11: el panel de finanzas leía los totales en la raíz (vienen en
// `portfolio`) y la tabla de proyectos `revenue_actual`/`cost_actual`, que no
// existen: ingresos 0 arriba y el presupuesto como ingreso abajo. El pipeline
// leia `value`/`status`, que tampoco vienen.
import { vi, describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const respuestas: Record<string, unknown> = {
  '/profitability/summary': { projects: [], portfolio: { total_revenue: 123456, total_cost: 23456 } },
  '/pipeline': [
    { id: 'o1', stage: 'proposal', expected_revenue: 70000 },
    { id: 'o2', stage: 'won', expected_revenue: 400000 },
    { id: 'o3', stage: 'lost', expected_revenue: 800000 },
  ],
  '/profitability/projects': [
    { project_id: 'p1', project_name: 'ERP Acme', client_name: 'Acme', billing_revenue: 50000,
      internal_cost: 30000, budget_amount: 999999 },
  ],
}

vi.mock('../services/api', () => ({
  default: { get: (url: string) => Promise.resolve({ data: respuestas[url] ?? [] }) },
  unwrapList: (r: { data: unknown }) => r.data,
  currencyApi: { rates: () => Promise.resolve({ data: [] }), upsert: vi.fn() },
  userCostsApi: { summary: () => Promise.resolve({ data: null }) },
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => ({ useAppLang: () => ({ t: (k: string) => k, lang: 'en' }) }))

import FinanceDashboardPage from '../pages/FinanceDashboardPage'

describe('FinanceDashboardPage', () => {
  it('enseña los totales de portfolio y los ingresos facturados de cada proyecto', async () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <FinanceDashboardPage />
        </QueryClientProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('123,456')).toBeTruthy()
    expect(await screen.findByText('ERP Acme')).toBeTruthy()
    expect(screen.getAllByText('50,000').length).toBeGreaterThan(0)
    expect(screen.getAllByText('30,000').length).toBeGreaterThan(0)
    expect(screen.queryByText('999,999')).toBeNull()
    // Pipeline: solo las abiertas (ni ganadas ni perdidas), con `expected_revenue`.
    expect(screen.getAllByText('70,000').length).toBeGreaterThan(0)
    expect(screen.getByText('1 oportunidades abiertas')).toBeTruthy()
  })
})
