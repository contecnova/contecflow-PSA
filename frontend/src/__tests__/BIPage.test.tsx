// Auditoría 2026-11: el panel ejecutivo leía `revenue_total`, `cost_total`…,
// que `get_kpi_summary` no devuelve, y enseñaba 0 € con cualquier dato.
import { vi, describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../services/api', () => ({
  // useFormatoMoneda lee la moneda de la empresa (/settings/org-defaults).
  default: { get: () => Promise.resolve({ data: { currency: 'EUR' } }) },
  analyticsApi: { olapKpis: () => Promise.resolve({ data: {
    hours_mtd: 312.5, cost_mtd: 18450, billability_pct: 72.4, active_projects: 7, avg_margin_pct: 31.2,
    high_risk_projects: 2, open_opps: 5, pipeline_weighted: 96000, won_revenue: 240000, source: 'postgres',
  } }) },
  dashboardApi: { projectsHealth: () => Promise.resolve({ data: [
    { project_id: 'p1', project_name: 'ERP Acme', status: 'active', risk_level: 'high', budget_used_pct: 81, progress_pct: 64 },
  ] }) },
}))
vi.mock('../services/biOfflineDb', () => ({
  purgeExpiredBiCache: vi.fn(), cacheBiKpis: vi.fn(), getCachedBiKpis: vi.fn(),
  cacheBiProjects: vi.fn(), getCachedBiProjects: vi.fn(),
}))
vi.mock('../i18n/AppLangContext', () => ({ useAppT: () => (k: string) => k, useAppLang: () => ({ lang: 'en' }) }))
vi.mock('../hooks/useMediaQuery', () => ({ default: () => false }))
vi.mock('../components/bi/NarrativeCard', () => ({ default: () => null }))
vi.mock('../components/bi/AskDataWidget', () => ({ default: () => null }))
vi.mock('../components/layout/PageHeader', () => ({ default: () => null }))
vi.mock('../components/layout/PageShell', () => ({ default: ({ children }: { children: JSX.Element }) => <div>{children}</div> }))

import BIPage from '../pages/BIPage'

describe('BIPage', () => {
  it('enseña los KPI que devuelve el servidor', async () => {
    // Los importes salen en el idioma activo (localeActivo) con la moneda de la empresa.
    localStorage.setItem('contecflow_operator_lang', 'en')
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BIPage />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('€18,450')).toBeTruthy()
    expect(screen.getByText('312.5')).toBeTruthy()
    expect(screen.getByText('31.2%')).toBeTruthy()
    expect(screen.getByText('€96,000')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
    expect(screen.getAllByText('ERP Acme').length).toBeGreaterThan(0)
    expect(screen.getAllByText('81.0%').length).toBeGreaterThan(0)
  })
})
